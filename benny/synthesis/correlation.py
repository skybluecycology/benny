"""
Correlation Engine - Linking the Knowledge Graph (Concepts) to the Code Graph (Symbols/Files).
Supports Safe (exact match) and Aggressive (semantic similarity) strategies.
"""

import logging
import asyncio
from typing import List, Dict, Any, Optional
from ..core.graph_db import get_driver, read_session, write_session
from .engine import get_embedding

logger = logging.getLogger(__name__)

async def run_safe_correlation(workspace: str):
    """
    Connects Concepts to Code Symbols that have the exact same name.
    Strategy: 'safe'
    """
    driver = get_driver()
    query = """
    MATCH (c:Concept {workspace: $workspace})
    MATCH (s:CodeEntity {workspace: $workspace})
    WHERE s.type IN ['File', 'Class', 'Interface', 'Function', 'Variable']
      AND toLower(c.name) = toLower(s.name)
    MERGE (c)-[r:CORRELATES_WITH]->(s)
    ON CREATE SET r.strategy = 'safe', r.confidence = 1.0, r.created_at = timestamp()
    ON MATCH SET r.strategy = 'safe', r.confidence = 1.0
    RETURN count(r) as links
    """
    with driver.session() as session:
        result = session.run(query, workspace=workspace)
        summary = result.single()
        logger.info(f"Safe Correlation: Created {summary['links'] if summary else 0} links in workspace {workspace}")
        return summary["links"] if summary else 0

async def run_aggressive_correlation(workspace: str, threshold: float = 0.70):
    """
    Connects Concepts to Code Symbols using embedding similarity.
    Strategy: 'aggressive'
    """
    # 1. Fetch all concepts without embeddings (or all if we want to refresh)
    concept_query = """
    MATCH (c:Concept {workspace: $workspace})
    RETURN c.name as name, id(c) as id
    """
    
    symbol_query = """
    MATCH (s:CodeEntity {workspace: $workspace})
    WHERE s.type IN ['File', 'Class', 'Interface', 'Function']
    RETURN s.name as name, s.summary as summary, id(s) as id
    """
    
    concepts = []
    symbols = []
    
    with read_session() as session:
        res_c = session.run(concept_query, workspace=workspace)
        concepts = [dict(record) for record in res_c]
        
        res_s = session.run(symbol_query, workspace=workspace)
        symbols = [dict(record) for record in res_s]

    if not concepts or not symbols:
        return 0

    logger.info(f"Aggressive Correlation: Comparing {len(concepts)} concepts vs {len(symbols)} symbols")

    # 2. Get embeddings (batching for performance)
    # This is a placeholder for a more complex batching logic
    concept_embeddings = {}
    for c in concepts:
        concept_embeddings[c["id"]] = await get_embedding(c["name"])
        
    symbol_embeddings = {}
    for s in symbols:
        text = f"{s['name']}: {s.get('summary', '')}"
        symbol_embeddings[s["id"]] = await get_embedding(text)

    # 3. Compute cosine similarity and link
    import numpy as np
    links_created = 0
    
    for c_id, c_vec in concept_embeddings.items():
        c_vec = np.array(c_vec)
        for s_id, s_vec in symbol_embeddings.items():
            s_vec = np.array(s_vec)
            
            # Simple cosine similarity
            norm_c = np.linalg.norm(c_vec)
            norm_s = np.linalg.norm(s_vec)
            if norm_c > 0 and norm_s > 0:
                sim = np.dot(c_vec, s_vec) / (norm_c * norm_s)
                
                if sim >= threshold:
                    write_query = """
                    MATCH (c) WHERE id(c) = $c_id
                    MATCH (s) WHERE id(s) = $s_id
                    MERGE (c)-[r:CORRELATES_WITH]->(s)
                    ON CREATE SET r.strategy = 'aggressive', r.confidence = $sim, r.created_at = timestamp()
                    ON MATCH SET r.strategy = 'aggressive', r.confidence = $sim
                    """
                    with write_session() as session:
                        session.run(write_query, c_id=c_id, s_id=s_id, sim=float(sim))
                    links_created += 1

    logger.info(f"Aggressive Correlation: Created {links_created} links with threshold {threshold}")
    return links_created

async def run_full_correlation_suite(workspace: str, threshold: float = 0.70):
    """Run all correlation strategies."""
    safe_count = await run_safe_correlation(workspace)
    aggressive_count = await run_aggressive_correlation(workspace, threshold=threshold)
    return {
        "safe_links": safe_count,
        "aggressive_links": aggressive_count
    }
