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
    get_mapped_sources, delete_source_from_graph
)
from ..synthesis.engine import (
    extract_triples, detect_conflicts, find_synthesis,
    cross_domain_analogy, get_embedding, compute_cluster_similarities
)
from ..core.workspace import get_workspace_path
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
    try:
        return get_full_graph(workspace)
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch graph: {str(e)}")


@router.get("/graph/stats")
async def graph_statistics(workspace: str = "default"):
    """Get graph statistics (node / edge counts)."""
    try:
        return get_graph_stats(workspace)
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch stats: {str(e)}")


@router.get("/graph/sources")
async def graph_sources(workspace: str = "default"):
    """Get list of source documents mapped in the graph."""
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
                segments.append({"title": current_title, "content": '\n'.join(current_content)})
            current_title = header_match.group(2).strip()
            current_content = [line]
        else:
            current_content.append(line)
            
    if ''.join(current_content).strip():
        segments.append({"title": current_title, "content": '\n'.join(current_content)})
        
    # If no headers found at all, just return one big segment
    if not segments:
        return [{"title": "Main Content", "content": text}]
        
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
    inference_delay: float = 2.0
):
    """Internal helper to run the triple extraction -> storage pipeline."""
    # Step 1: Chunk the text by markdown headers
    sections = _split_markdown_into_segments(text)
    
    triples = []
    print(f"Hierarchical parsing initiated for {source_name}: {len(sections)} sections found.")
    
    # Process each section independently (L2 agent extraction)
    for index, sec in enumerate(sections):
        title = sec['title']
        content = sec['content']
        # Skip microscopic/empty sections
        if len(content.strip()) < 50:
            continue
            
        print(f"  -> Extracting points from section {index+1}/{len(sections)}: '{title}'")
        sec_triples = await extract_directed_triples_from_section(
            text=content,
            section_title=f"{source_name} - {title}",
            direction=direction,
            provider=provider,
            model=model,
            inference_delay=inference_delay
        )
        if sec_triples:
            for t in sec_triples:
                t.append(title)
            triples.extend(sec_triples)
            
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
            model=model
        )
    
    # Step 3: Store triples in Neo4j
    stored = []
    all_concepts = set()
    for t in triples:
        subj = t[0]
        pred = t[1]
        obj = t[2]
        sec_title = t[3] if len(t) > 3 else source_name
        
        try:
            result = add_triple(
                subject=subj, predicate=pred, obj=obj,
                workspace=workspace,
                source_name=source_name,
                section=f"{source_name} - {sec_title}"
            )
            stored.append(result)
            all_concepts.add(subj)
            all_concepts.add(obj)
            
            # Link to source mapping
            add_source_link(subj, source_name, workspace)
            add_source_link(obj, source_name, workspace)
        except Exception as e:
            print(f"Error storing triple {t}: {e}")
    
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
                            print(f"⚠️ Vector Embedding bypassed: Could not connect to {actual_emb_provider} API.")
                            printed_conn_error = True
                    else:
                        if not printed_conn_error:
                            print(f"⚠️ Embedding failed for '{concept_name}': {e}")
                            printed_conn_error = True
    
    return {
        "status": "ingested",
        "triples_extracted": len(triples),
        "triples_stored": len(stored),
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
        
        graph_summary = "\n".join(lines[:50])  # Cap to avoid huge prompts
        
        analogies = await find_synthesis(
            graph_summary=graph_summary,
            provider=request.provider,
            model=request.model
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
        
        result = await cross_domain_analogy(
            concept=request.concept,
            relationships=relationships,
            target_domain=request.target_domain,
            provider=request.provider,
            model=request.model
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
