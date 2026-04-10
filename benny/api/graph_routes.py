"""
Graph Routes - API endpoints for the Synthesis Knowledge Engine.

Provides CRUD for the knowledge graph, synthesis operations, 
and real-time graph data for the 3D visualization.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from ..core.graph_db import (
    verify_connectivity, init_schema, get_full_graph, get_neighbors,
    get_graph_stats, add_triple, add_source_link, add_conflict,
    add_analogy, set_concept_embedding, vector_search,
    get_mapped_sources, delete_source_from_graph,
    create_synthesis_run, get_synthesis_history, delete_synthesis_run,
    update_graph_centrality, batch_add_triples
)
from ..synthesis.engine import (
    extract_triples, detect_conflicts, find_synthesis,
    cross_domain_analogy, get_embedding, compute_cluster_similarities,
    parallel_extract_triples
)
from ..core.workspace import get_workspace_path, load_manifest
from ..core.extraction import extract_structured_text


router = APIRouter()


# =============================================================================
# MODELS
# =============================================================================

class TripleRequest(BaseModel):
    subject: str
    predicate: str
    object: str
    source_name: Optional[str] = None
    workspace: str = "default"
    timestamp: Optional[str] = None


class IngestTextRequest(BaseModel):
    text: str
    source_name: str = "manual"
    workspace: str = "default"
    provider: str = "lemonade"
    model: Optional[str] = None
    embed: bool = True
    embedding_provider: str = "local"
    embedding_model: Optional[str] = "nomic-embed-text-v1-GGUF"
    direction: Optional[str] = ""
    inference_delay: Optional[float] = 2.0


class IngestFilesRequest(BaseModel):
    files: List[str]
    workspace: str = "default"
    provider: str = "lemonade"
    model: Optional[str] = None
    embed: bool = True
    embedding_provider: str = "local"
    embedding_model: Optional[str] = "nomic-embed-text-v1-GGUF"
    direction: Optional[str] = ""
    inference_delay: Optional[float] = 2.0


class SynthesizeRequest(BaseModel):
    workspace: str = "default"
    provider: str = "lemonade"
    model: Optional[str] = None


class CrossDomainRequest(BaseModel):
    concept: str
    target_domain: str
    workspace: str = "default"
    provider: str = "lemonade"
    model: Optional[str] = None


class EmbedConceptRequest(BaseModel):
    concept: str
    workspace: str = "default"
    provider: str = "local"
    model: Optional[str] = None


class VectorSearchRequest(BaseModel):
    query: str
    workspace: str = "default"
    top_k: int = 10
    provider: str = "local"
    model: Optional[str] = None


class ClusterRequest(BaseModel):
    concepts: Optional[List[str]] = None
    workspace: str = "default"
    threshold: float = 0.75


class RunIDRequest(BaseModel):
    run_id: str
    workspace: str = "default"


# =============================================================================
# STATUS & SCHEMA
# =============================================================================

@router.get("/graph/status")
async def graph_status():
    """Check Neo4j connectivity and return graph statistics."""
    conn = verify_connectivity()
    if conn["status"] == "connected":
        stats = get_graph_stats()
        conn["stats"] = stats
    return conn


@router.post("/graph/init")
async def initialize_graph():
    """Initialize the Neo4j schema (constraints, indexes)."""
    try:
        result = init_schema()
        return result
    except Exception as e:
        raise HTTPException(500, f"Schema init failed: {str(e)}")


# =============================================================================
# GRAPH CRUD
# =============================================================================

@router.get("/graph/full")
async def full_graph(workspace: str = "default"):
    """Get the complete knowledge graph for visualization (nodes + edges)."""
    conn = verify_connectivity()
    if conn["status"] != "connected":
        raise HTTPException(status_code=503, detail=f"Neo4j not available: {conn.get('error')}")
    try:
        return get_full_graph(workspace)
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch graph: {str(e)}")


@router.get("/graph/stats")
async def graph_statistics(workspace: str = "default"):
    """Get graph statistics (node / edge counts)."""
    conn = verify_connectivity()
    if conn["status"] != "connected":
        raise HTTPException(status_code=503, detail=f"Neo4j not available: {conn.get('error')}")
    try:
        return get_graph_stats(workspace)
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch stats: {str(e)}")


@router.get("/graph/sources")
async def graph_sources(workspace: str = "default"):
    """Get list of source documents mapped in the graph."""
    conn = verify_connectivity()
    if conn["status"] != "connected":
        raise HTTPException(status_code=503, detail=f"Neo4j not available: {conn.get('error')}")
    try:
        return {"sources": get_mapped_sources(workspace)}
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch sources: {str(e)}")


@router.delete("/graph/sources/{filename}")
async def delete_graph_source(filename: str, workspace: str = "default"):
    """Delete a source and all its associated triples from the graph."""
    try:
        return delete_source_from_graph(filename, workspace)
    except Exception as e:
        raise HTTPException(500, f"Failed to delete source: {str(e)}")


@router.get("/graph/neighbors/{concept}")
async def concept_neighbors(concept: str, workspace: str = "default", depth: int = 1):
    """Get neighbourhood of a concept up to N hops."""
    try:
        return get_neighbors(concept, workspace, depth)
    except Exception as e:
        raise HTTPException(500, f"Neighbor query failed: {str(e)}")


@router.get("/graph/history")
async def graph_history(workspace: str = "default"):
    """Get historical synthesis runs for a workspace."""
    try:
        return {"history": get_synthesis_history(workspace)}
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch history: {str(e)}")


@router.delete("/graph/runs/{run_id}")
async def delete_run(run_id: str, workspace: str = "default"):
    """Delete a specific synthesis run and its associated graph data."""
    try:
        # 1. Delete from graph
        graph_result = delete_synthesis_run(run_id, workspace)
        
        # 2. Delete file artifacts if they exist
        data_path = get_workspace_path(workspace, f"runs/{run_id}")
        if data_path.exists():
            import shutil
            shutil.rmtree(data_path)
            
        return {**graph_result, "files_deleted": True}
    except Exception as e:
        raise HTTPException(500, f"Failed to delete run: {str(e)}")


@router.get("/graph/recent")
async def get_recent_updates(workspace: str = "default", seconds: int = 10):
    """
    Get graph updates from the last N seconds. 
    Used for real-time 'fly-to-continent' visualization during ingestion.
    """
    try:
        graph = get_full_graph(workspace)
        # Filter for very recent ones (simplified for now: just return last 50 edges)
        # Real implementation would use timestamp property comparison in Cypher
        recent_edges = graph["edges"][-50:] if graph["edges"] else []
        return {"edges": recent_edges}
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch recent updates: {str(e)}")


@router.post("/graph/triple")
async def create_triple(request: TripleRequest):
    """Manually add a single triple to the graph."""
    try:
        result = add_triple(
            subject=request.subject,
            predicate=request.predicate,
            obj=request.object,
            workspace=request.workspace,
            source_name=request.source_name,
            timestamp=request.timestamp
        )
        return result
    except Exception as e:
        raise HTTPException(500, f"Failed to add triple: {str(e)}")


# =============================================================================
# SYNTHESIS OPERATIONS
# =============================================================================

@router.post("/graph/ingest")
async def ingest_text(request: IngestTextRequest):
    """
    Ingest text: extract triples via LLM, store in Neo4j, optionally embed concepts.
    """
    try:
        return await _process_content_to_graph(
            text=request.text,
            source_name=request.source_name,
            workspace=request.workspace,
            provider=request.provider,
            model=request.model,
            embed=request.embed,
            embedding_provider=request.embedding_provider,
            embedding_model=request.embedding_model,
            direction=request.direction,
            inference_delay=request.inference_delay
        )
    except Exception as e:
        raise HTTPException(500, f"Ingestion failed: {str(e)}")


@router.post("/graph/ingest-files")
async def ingest_files_to_graph(request: IngestFilesRequest):
    """
    Ingest selected files from the workspace: extract structured text (Docling),
    then run the synthesis ingestion pipeline for each file.
    """
    try:
        data_in_path = get_workspace_path(request.workspace, "data_in")
        results = []
        
        for filename in request.files:
            file_path = data_in_path / filename
            if not file_path.exists():
                print(f"File not found: {filename}")
                continue
                
            # Step 1: Extract structured text via Docling
            text = extract_structured_text(file_path)
            
            if not text.strip():
                print(f"No content extracted from {filename}")
                continue
                
            # Step 2: Process to graph
            file_result = await _process_content_to_graph(
                text=text,
                source_name=filename,
                workspace=request.workspace,
                provider=request.provider,
                model=request.model,
                embed=request.embed,
                embedding_provider=request.embedding_provider,
                embedding_model=request.embedding_model,
                direction=request.direction,
                inference_delay=request.inference_delay
            )
            results.append({
                "file": filename,
                "status": file_result.get("status"),
                "triples": file_result.get("triples_extracted", 0)
            })
            
        return {
            "status": "completed",
            "files_processed": len(results),
            "details": results
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Batch file ingestion failed: {str(e)}")


from ..synthesis.engine import (
    extract_triples, detect_conflicts, find_synthesis,
    cross_domain_analogy, get_embedding, compute_cluster_similarities,
    extract_directed_triples_from_section
)

def _split_markdown_into_segments(text: str) -> List[Dict[str, str]]:
    """Splits markdown text into logical sections based on headers."""
    import re
    segments = []
    lines = text.split('\n')
    current_title = "Introduction / Main"
    current_content = []
    
    for line in lines:
        header_match = re.match(r'^(#{1,3})\s+(.*)', line)
        if header_match:
            # Save the previous chunk
            if ''.join(current_content).strip():
                segments.append({"title": current_title, "text": '\n'.join(current_content)})
            current_title = header_match.group(2).strip()
            current_content = [line]
        else:
            current_content.append(line)
            
    if ''.join(current_content).strip():
        segments.append({"title": current_title, "text": '\n'.join(current_content)})
        
    # If no headers found at all, just return one big segment
    if not segments:
        return [{"title": "Main Content", "text": text}]
        
    return segments

async def _process_content_to_graph(
    text: str,
    source_name: str,
    workspace: str,
    provider: str,
    model: Optional[str],
    embed: bool,
    embedding_provider: str,
    embedding_model: Optional[str] = None,
    direction: str = "",
    inference_delay: float = 2.0,
    run_id: Optional[str] = None
):
    import uuid
    import hashlib
    import json
    
    # Step 0: Ensure Run ID and Partition Key
    if not run_id:
        run_id = str(uuid.uuid4())
    
    pk_source = f"{model or 'default'}-{source_name}"
    partition_key = hashlib.sha256(pk_source.encode()).hexdigest()
    
    # Step 0a: Check Neo4j connectivity
    from ..core.graph_db import verify_connectivity
    conn = verify_connectivity()
    if conn["status"] != "connected":
        raise HTTPException(
            status_code=503,
            detail=f"Knowledge Graph database not available: {conn.get('error', 'Unknown connection error')}"
        )
    
    manifest = load_manifest(workspace)
    llm_timeout = manifest.llm_timeout
    
    # Create SynthesisRun record
    create_synthesis_run(
        run_id=run_id,
        partition_key=partition_key,
        model=model or "default",
        workspace=workspace,
        files=[source_name],
        version="1.0.0",
        artifact_path=str(get_workspace_path(workspace, f"runs/{run_id}"))
    )
    
    # Step 1: Parallel Extraction of Triples
    sections = _split_markdown_into_segments(text)
    print(f"Hierarchical parallel parsing initiated for {source_name}: {len(sections)} sections found.")
    
    # Filter microscopic sections early
    active_sections = [s for s in sections if len(s['text'].strip()) >= 50]
    
    triples = await parallel_extract_triples(
        sections=active_sections,
        direction=direction,
        provider=provider,
        model=model,
        parallel_limit=4, # Hardcoded limit for stability
        inference_delay=inference_delay,
        timeout=llm_timeout
    )
            
    if not triples:
        return {"status": "no_triples_found", "triples_extracted": 0}
    
    # Step 2: Check for conflicts against existing graph
    existing = []
    try:
        graph = get_full_graph(workspace)
        for edge in graph.get("edges", []):
            if edge.get("type") == "RELATES_TO":
                src_name = next((n["name"] for n in graph["nodes"] if n["id"] == edge["source"]), "")
                tgt_name = next((n["name"] for n in graph["nodes"] if n["id"] == edge["target"]), "")
                if src_name and tgt_name:
                    existing.append([src_name, edge.get("predicate", ""), tgt_name])
    except Exception:
        pass
    
    conflicts = []
    if existing:
        conflicts = await detect_conflicts(
            existing_triples=existing,
            new_triples=triples,
            provider=provider,
            model=model,
            timeout=llm_timeout
        )
    
    # Step 3: Store triples in Neo4j (Batch Mode)
    stored_result = batch_add_triples(
        triples=triples,
        workspace=workspace,
        source_name=source_name,
        run_id=run_id
    )
    print(f"[SUCCESS] Batched {stored_result['count']} triples into Neo4j successfully.")
            
    # Step 3b: Save Artifacts to Workspace Disk
    try:
        run_dir = get_workspace_path(workspace, f"runs/{run_id}")
        run_dir.mkdir(parents=True, exist_ok=True)
        
        # 1. Triples JSON
        with open(run_dir / "extraction.json", "w", encoding="utf-8") as f:
            json.dump(triples, f, indent=2)
            
        # 2. Metadata JSON
        meta = {
            "run_id": run_id,
            "partition_key": partition_key,
            "model": model,
            "source": source_name,
            "timestamp": str(manifest.llm_timeout), # placeholder
            "triples_count": len(triples)
        }
        with open(run_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)
            
        # 3. Simple Summary Markdown
        summary = f"# Synthesis Report: {source_name}\n\n"
        summary += f"- **Model**: {model or 'default'}\n"
        summary += f"- **Triples Extracted**: {len(triples)}\n\n"
        summary += "## Core Points\n"
        for t in triples[:10]: # Top 10 for summary
            summary += f"- {t.get('subject')} {t.get('predicate')} {t.get('object')} (Confidence: {t.get('confidence')})\n"
        
        with open(run_dir / "summary.md", "w", encoding="utf-8") as f:
            f.write(summary)
            
    except Exception as e:
        print(f"Failed to save artifacts: {e}")
    
    # Step 4: Store conflicts
    for conflict in conflicts:
        try:
            add_conflict(
                concept_a=conflict["concept_a"],
                concept_b=conflict["concept_b"],
                description=conflict.get("description", ""),
                workspace=workspace
            )
        except Exception:
            pass
    
    # Step 5: Embed concepts (if requested)
    embedded_count = 0
    if embed:
        all_concepts = set()
        for t in triples:
            if t.get("subject"):
                all_concepts.add(t.get("subject"))
            if t.get("object"):
                all_concepts.add(t.get("object"))
        
        printed_conn_error = False
        for concept_name in all_concepts:
            # Use active provider for local embeddings instead of assuming Ollama
            actual_emb_provider = provider if embedding_provider == "local" else embedding_provider
            
            try:
                emb = await get_embedding(
                    concept_name,
                    provider=actual_emb_provider,
                    model=embedding_model
                )
                if emb:
                    set_concept_embedding(concept_name, emb, workspace)
                    embedded_count += 1
            except Exception as e:
                err_str = str(e)
                if "connection" in err_str.lower() or "connecterror" in err_str.lower():
                    if not printed_conn_error:
                        print(f"[WARNING] Vector Embedding bypassed: Could not connect to {actual_emb_provider} API.")
                        printed_conn_error = True
                else:
                    if not printed_conn_error:
                        print(f"[WARNING] Embedding failed for '{concept_name}': {e}")
                        printed_conn_error = True
    
    # Step 6: Update Graph Centrality for visual sizing
    try:
        update_graph_centrality(workspace)
    except Exception:
        pass
    
    return {
        "status": "ingested",
        "run_id": run_id,
        "partition_key": partition_key,
        "triples_extracted": len(triples),
        "triples_stored": stored_result.get("count", 0) if "stored_result" in locals() else 0,
        "conflicts_detected": len(conflicts),
        "concepts_embedded": embedded_count,
        "triples": triples,
        "conflicts": conflicts
    }

@router.post("/graph/synthesize")
async def synthesize(request: SynthesizeRequest):
    """
    Run the Synthesis Layer: find structural isomorphisms across the graph.
    
    This is the "So What?" — the aha moment.
    """
    try:
        # Build a text summary of the graph for the LLM
        graph = get_full_graph(request.workspace)
        
        if not graph["nodes"]:
            return {"analogies": [], "message": "Graph is empty. Ingest some text first."}
        
        # Build summary
        lines = []
        node_map = {n["id"]: n["name"] for n in graph["nodes"]}
        for edge in graph["edges"]:
            src = node_map.get(edge["source"], "?")
            tgt = node_map.get(edge["target"], "?")
            rel_type = edge.get("type", "")
            pred = edge.get("predicate", "")
            label = pred if pred else rel_type
            lines.append(f"  {src} --[{label}]--> {tgt}")
        
        # Load manifest for timeout
        manifest = load_manifest(request.workspace)
        llm_timeout = manifest.llm_timeout
        
        analogies = await find_synthesis(
            graph_summary=graph_summary,
            provider=request.provider,
            model=request.model,
            timeout=llm_timeout
        )
        
        # Store discovered analogies in the graph
        for a in analogies:
            try:
                add_analogy(
                    concept_a=a["concept_a"],
                    concept_b=a["concept_b"],
                    description=a.get("description", ""),
                    pattern=a.get("pattern", ""),
                    workspace=request.workspace
                )
            except Exception:
                pass
        
        return {
            "status": "synthesized",
            "analogies_found": len(analogies),
            "analogies": analogies
        }
        
    except Exception as e:
        raise HTTPException(500, f"Synthesis failed: {str(e)}")


@router.post("/graph/cross-domain")
async def cross_domain(request: CrossDomainRequest):
    """Map a concept into a different domain (e.g., 'Show me X in Physics')."""
    try:
        # Get the concept's relationships
        neighbors = get_neighbors(request.concept, request.workspace, depth=2)
        
        rel_lines = []
        node_map = {n["id"]: n["name"] for n in neighbors["nodes"]}
        for edge in neighbors["edges"]:
            src = node_map.get(edge["source"], "?")
            tgt = node_map.get(edge["target"], "?")
            rel_lines.append(f"{src} --[{edge.get('predicate', edge.get('type', ''))}]--> {tgt}")
        
        relationships = "\n".join(rel_lines) if rel_lines else "No relationships found."
        
        # Load manifest for timeout
        manifest = load_manifest(request.workspace)
        llm_timeout = manifest.llm_timeout
        
        result = await cross_domain_analogy(
            concept=request.concept,
            relationships=relationships,
            target_domain=request.target_domain,
            provider=request.provider,
            model=request.model,
            timeout=llm_timeout
        )
        
        return {
            "concept": request.concept,
            "target_domain": request.target_domain,
            "result": result
        }
        
    except Exception as e:
        raise HTTPException(500, f"Cross-domain analogy failed: {str(e)}")


# =============================================================================
# EMBEDDING & CLUSTERING
# =============================================================================

@router.post("/graph/embed")
async def embed_concept(request: EmbedConceptRequest):
    """Compute and store an embedding for a concept."""
    try:
        emb = await get_embedding(
            request.concept,
            provider=request.provider,
            model=request.model
        )
        set_concept_embedding(request.concept, emb, request.workspace)
        return {
            "status": "embedded",
            "concept": request.concept,
            "dimensions": len(emb)
        }
    except Exception as e:
        raise HTTPException(500, f"Embedding failed: {str(e)}")


@router.post("/graph/search")
async def semantic_search(request: VectorSearchRequest):
    """Find concepts similar to a query by vector similarity."""
    try:
        query_emb = await get_embedding(
            request.query,
            provider=request.provider,
            model=request.model
        )
        results = vector_search(query_emb, request.workspace, request.top_k)
        return {"query": request.query, "results": results}
    except Exception as e:
        raise HTTPException(500, f"Vector search failed: {str(e)}")


@router.post("/graph/clusters")
async def find_clusters(request: ClusterRequest):
    """Find conceptual clusters (the 'Venn' overlap) using embedding similarity."""
    try:
        concepts = request.concepts
        if not concepts:
            # Use all concepts with embeddings
            from ..core.graph_db import get_driver
            driver = get_driver()
            with driver.session() as session:
                result = session.run("""
                    MATCH (c:Concept {workspace: $workspace})
                    WHERE c.embedding IS NOT NULL
                    RETURN c.name AS name
                """, workspace=request.workspace)
                concepts = [r["name"] for r in result]
        
        if len(concepts) < 2:
            return {"clusters": [], "message": "Need at least 2 embedded concepts."}
        
        clusters = await compute_cluster_similarities(
            concepts=concepts,
            workspace=request.workspace,
            threshold=request.threshold
        )
        
        return {"clusters": clusters, "count": len(clusters)}
        
    except Exception as e:
        raise HTTPException(500, f"Clustering failed: {str(e)}")
