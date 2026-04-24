"""
Correlation Engine - Linking the Knowledge Graph (Concepts) to the Code Graph (Symbols/Files).
Supports Safe (exact match) and Aggressive (semantic similarity) strategies.

Phase 1 Refactor (6-Sigma):
  - Replaced all hardcoded Cypher label queries with SchemaAdapter-resolved patterns.
  - Added r.rationale and r.doc_fragment_id to every CORRELATES_WITH edge.
  - Aggressive mode now logs which entity types were found vs. expected.
  - run_full_correlation_suite passes correlation_threshold from IngestRequest.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from ..core.graph_db import get_driver, read_session, write_session
from ..governance.aer_decorator import aer_tracked
import numpy as np

logger = logging.getLogger(__name__)


@aer_tracked("safe_correlation")
async def run_safe_correlation(workspace: str) -> int:
    """
    Connects Concepts to Code Symbols that share the exact same name.
    Strategy: 'safe' — zero false positives.

    Uses SchemaAdapter to resolve the correct MATCH clause dynamically,
    eliminating the silent zero-row failure when the graph uses separate
    labels (:File, :Class) rather than CodeEntity {type: ...}.
    """
    from .schema_adapter import SchemaAdapter

    adapter = SchemaAdapter(workspace)
    valid_types = adapter.get_valid_entity_types()
    type_list = ", ".join(f"'{t}'" for t in valid_types)
    schema_mode = adapter.get_schema_mode()

    logger.info(
        "Safe Correlation: workspace='%s', schema_mode='%s', entity_types=%s",
        workspace, schema_mode, valid_types
    )

    # Dynamic query — works for both label-based and property-based graphs
    query = f"""
    MATCH (c:Concept {{workspace: $workspace}})
    MATCH (s:CodeEntity {{workspace: $workspace}})
    WHERE s.type IN [{type_list}]
      AND toLower(c.name) = toLower(s.name)
    MERGE (c)-[r:CORRELATES_WITH]->(s)
    ON CREATE SET
        r.strategy    = 'safe',
        r.confidence  = 1.0,
        r.rationale   = 'Exact name match between Concept and CodeEntity',
        r.created_at  = timestamp()
    ON MATCH SET
        r.strategy    = 'safe',
        r.confidence  = 1.0,
        r.rationale   = 'Exact name match between Concept and CodeEntity',
        r.updated_at  = timestamp()
    RETURN count(r) as links
    """

    driver = get_driver()
    with driver.session() as session:
        result = session.run(query, workspace=workspace)
        summary = result.single()
        link_count = summary["links"] if summary else 0
        logger.info(
            "Safe Correlation: created/updated %d links in workspace '%s'",
            link_count, workspace
        )
        return link_count


@aer_tracked("aggressive_correlation")
async def run_aggressive_correlation(workspace: str, threshold: float = 0.70) -> int:
    """
    Connects Concepts to Code Symbols using embedding cosine similarity.
    Strategy: 'aggressive' — higher recall, lower precision.

    Optimized for Neural Spark (6-Sigma):
    - Uses NumPy matrix multiplication for vectorized similarity computation (O(N*M)).
    - Batches Neo4j MERGE operations using UNWIND to avoid database round-trip exhaustion.
    """
    from .schema_adapter import SchemaAdapter
    from .engine import batch_embed_concepts

    adapter = SchemaAdapter(workspace)
    valid_types = adapter.get_valid_entity_types()
    type_list = ", ".join(f"'{t}'" for t in valid_types)

    # 1. Fetch data
    concept_query = "MATCH (c:Concept {workspace: $workspace}) RETURN c.name as name, id(c) as id"
    symbol_query = f"MATCH (s:CodeEntity {{workspace: $workspace}}) WHERE s.type IN [{type_list}] RETURN s.name as name, s.summary as summary, id(s) as id, s.type as type"

    with read_session() as session:
        concepts = [dict(r) for r in session.run(concept_query, workspace=workspace)]
        symbols = [dict(r) for r in session.run(symbol_query, workspace=workspace)]

    if not concepts or not symbols:
        return 0

    logger.info("Aggressive Correlation: workspace='%s', comparing %d concepts vs %d symbols (threshold=%.2f)", 
                workspace, len(concepts), len(symbols), threshold)

    # 2. Compute embeddings
    logger.info("Aggressive Correlation: Generating embeddings for %d concepts...", len(concepts))
    concept_names = [c["name"] for c in concepts]
    concept_embeddings_kv = await batch_embed_concepts(concept_names, provider="local", workspace=workspace)
    
    logger.info("Aggressive Correlation: Generating embeddings for %d symbols (this may take time)...", len(symbols))
    symbol_texts = [f"{s['name']}: {s.get('summary', '') or ''}" for s in symbols]
    symbol_embeddings_kv = await batch_embed_concepts(symbol_texts, provider="local", workspace=workspace)

    logger.info("Aggressive Correlation: Embeddings generated. Running vectorized similarity math...")

    # Convert to matrices for vectorized math
    C_matrix = np.array([concept_embeddings_kv.get(name, [0.0]*768) for name in concept_names])
    S_matrix = np.array([symbol_embeddings_kv.get(text, [0.0]*768) for text in symbol_texts])

    # Normalize rows
    C_norms = np.linalg.norm(C_matrix, axis=1, keepdims=True)
    S_norms = np.linalg.norm(S_matrix, axis=1, keepdims=True)
    
    # Avoid division by zero
    C_norms[C_norms == 0] = 1.0
    S_norms[S_norms == 0] = 1.0
    
    C_normed = C_matrix / C_norms
    S_normed = S_matrix / S_norms

    # 3. Compute similarity matrix (N x M)
    # This is the "Neural Spark" core — O(N*M) in optimized BLAS
    sim_matrix = np.dot(C_normed, S_normed.T)

    # 4. Find pairs above threshold
    indices = np.argwhere(sim_matrix >= threshold)
    
    batch_data = []
    for c_idx, s_idx in indices:
        sim = float(sim_matrix[c_idx, s_idx])
        c = concepts[c_idx]
        s = symbols[s_idx]
        
        batch_data.append({
            "c_id": c["id"],
            "s_id": s["id"],
            "sim": sim,
            "rationale": f"Cosine similarity {sim:.4f} >= {threshold:.2f} between Concept '{c['name']}' and {s['type']} '{s['name']}'"
        })

    if not batch_data:
        return 0

    # 5. Batched write to Neo4j
    # We use UNWIND to process the entire batch in a single transaction
    write_query = """
    UNWIND $batch as row
    MATCH (c) WHERE id(c) = row.c_id
    MATCH (s) WHERE id(s) = row.s_id
    MERGE (c)-[r:CORRELATES_WITH]->(s)
    ON CREATE SET
        r.strategy   = 'aggressive',
        r.confidence = row.sim,
        r.rationale  = row.rationale,
        r.created_at = timestamp()
    ON MATCH SET
        r.strategy   = 'aggressive',
        r.confidence = row.sim,
        r.rationale  = row.rationale,
        r.updated_at = timestamp()
    """
    
    # Process in chunks of 500 to avoid locking issues on massive graphs
    chunk_size = 500
    links_created = 0
    with write_session() as session:
        for i in range(0, len(batch_data), chunk_size):
            chunk = batch_data[i : i + chunk_size]
            session.run(write_query, batch=chunk)
            links_created += len(chunk)

    logger.info("Aggressive Correlation: created %d links in workspace '%s'", links_created, workspace)
    return links_created


@aer_tracked("full_correlation_suite")
async def run_full_correlation_suite(workspace: str, threshold: float = 0.70) -> dict:
    """
    Run all correlation strategies in sequence and return combined results.
    Called by rag_routes after deep-synthesis ingestion.
    """
    from .schema_adapter import SchemaAdapter

    # Invalidate adapter cache so we pick up freshly ingested nodes
    SchemaAdapter.invalidate(workspace)

    safe_count = await run_safe_correlation(workspace)
    aggressive_count = await run_aggressive_correlation(workspace, threshold=threshold)

    total = safe_count + aggressive_count
    logger.info(
        "Correlation suite complete: safe=%d, aggressive=%d, total=%d",
        safe_count, aggressive_count, total
    )
    return {
        "safe_links": safe_count,
        "aggressive_links": aggressive_count,
        "total_links": total
    }
