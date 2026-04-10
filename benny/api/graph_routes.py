"""
Graph Routes - API endpoints for the Synthesis Knowledge Engine.

Provides CRUD for the knowledge graph, synthesis operations, 
real-time graph data for the 3D visualization, and SSE progress streaming.
"""

import asyncio
import hashlib
import json
import logging
import re
import uuid
from typing import List, Optional, Dict, Any, AsyncGenerator

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..core.graph_db import (
    verify_connectivity, init_schema, get_full_graph, get_neighbors,
    get_graph_stats, add_triple, add_source_link, add_conflict,
    add_analogy, set_concept_embedding, vector_search,
    get_mapped_sources, delete_source_from_graph,
    create_synthesis_run, get_synthesis_history, delete_synthesis_run,
    update_graph_centrality, batch_add_triples, get_recent_updates
)
from ..synthesis.engine import (
    extract_triples, detect_conflicts, find_synthesis,
    cross_domain_analogy, get_embedding, compute_cluster_similarities,
    parallel_extract_triples, extract_directed_triples_from_section,
    batch_embed_concepts, deduplicate_triples
)
from ..core.workspace import get_workspace_path, load_manifest
from ..core.extraction import extract_structured_text
from ..core.schema import (
    KnowledgeTriple, SynthesisConfig, IngestionEvent, IngestionEventType
)

logger = logging.getLogger(__name__)

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
async def full_graph(
    workspace: str = "default",
    page: Optional[int] = None,
    page_size: int = 200,
    show_all: bool = False
):
    """
    Get the knowledge graph for visualization (nodes + edges).
    
    Modes:
      - ?show_all=true: Complete graph (no pagination)
      - ?page=0&page_size=200: Paginated for large graphs
      - Default: First 200 nodes + their edges
    """
    conn = verify_connectivity()
    if conn["status"] != "connected":
        raise HTTPException(status_code=503, detail=f"Neo4j not available: {conn.get('error')}")
    try:
        return get_full_graph(workspace, page=page, page_size=page_size, show_all=show_all)
    except Exception as e:
        raise HTTPException(500, f"Failed to fetch graph: {str(e)}")


@router.get("/graph/stats")
async def graph_statistics(workspace: str = "default"):
    """Get graph statistics (node / edge counts) — single optimised query."""
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
async def get_recent_graph_updates(workspace: str = "default", seconds: int = 10):
    """
    Get graph updates from the last N seconds using real timestamp filtering.
    Used for real-time 'fly-to-continent' visualization during ingestion.
    """
    try:
        return get_recent_updates(workspace, seconds)
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
# INGESTION EVENT BUS (for SSE streaming)
# =============================================================================

# In-memory event queues per run_id
_ingestion_events: Dict[str, asyncio.Queue] = {}


async def _emit_event(event: IngestionEvent):
    """Push an event to the run's event queue for SSE streaming."""
    run_id = event.run_id
    if run_id in _ingestion_events:
        await _ingestion_events[run_id].put(event)
    # Also log for non-SSE observability
    logger.info("[%s] %s: %s", run_id[:8], event.event.value, event.message)


async def _event_generator(run_id: str) -> AsyncGenerator[str, None]:
    """Async generator that yields SSE events for a given run_id."""
    queue = _ingestion_events.get(run_id)
    if not queue:
        return

    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=120.0)
            yield event.to_sse()
            if event.event in (IngestionEventType.COMPLETED, IngestionEventType.ERROR):
                break
        except asyncio.TimeoutError:
            # Send keepalive
            yield ": keepalive\n\n"


@router.get("/graph/ingest/events/{run_id}")
async def stream_ingestion_events(run_id: str):
    """
    SSE endpoint: stream real-time progress events for an ingestion run.
    Connect with EventSource in the browser.
    """
    if run_id not in _ingestion_events:
        raise HTTPException(404, f"No active ingestion for run_id: {run_id}")

    return StreamingResponse(
        _event_generator(run_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


# =============================================================================
# MARKDOWN SEGMENTATION
# =============================================================================

def _split_markdown_into_segments(text: str) -> List[Dict[str, str]]:
    """Splits markdown text into logical sections based on headers."""
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


# =============================================================================
# SYNTHESIS OPERATIONS
# =============================================================================

@router.post("/graph/ingest")
async def ingest_text(request: IngestTextRequest):
    """
    Ingest text: extract triples via LLM, store in Neo4j, optionally embed concepts.
    """
    try:
        result = await _process_content_to_graph(
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
        return result
    except Exception as e:
        raise HTTPException(500, f"Ingestion failed: {str(e)}")


@router.post("/graph/ingest-files")
async def ingest_files_to_graph(request: IngestFilesRequest, background_tasks: BackgroundTasks):
    """
    Ingest selected files from the workspace as a background task.
    Returns immediately with a run_id for SSE progress tracking.
    """
    run_id = str(uuid.uuid4())

    # Create event queue for SSE streaming
    _ingestion_events[run_id] = asyncio.Queue()

    # Start background processing
    background_tasks.add_task(
        _background_ingest_files,
        run_id=run_id,
        files=request.files,
        workspace=request.workspace,
        provider=request.provider,
        model=request.model,
        embed=request.embed,
        embedding_provider=request.embedding_provider,
        embedding_model=request.embedding_model,
        direction=request.direction,
        inference_delay=request.inference_delay
    )

    return {
        "status": "accepted",
        "run_id": run_id,
        "sse_url": f"/api/graph/ingest/events/{run_id}",
        "message": f"Background ingestion started for {len(request.files)} file(s)"
    }


async def _background_ingest_files(
    run_id: str,
    files: List[str],
    workspace: str,
    provider: str,
    model: Optional[str],
    embed: bool,
    embedding_provider: str,
    embedding_model: Optional[str],
    direction: str,
    inference_delay: float
):
    """Background task for batch file ingestion with SSE event emission."""
    results = []
    event_callback = _emit_event

    await event_callback(IngestionEvent(
        event=IngestionEventType.STARTED,
        run_id=run_id,
        message=f"Starting ingestion of {len(files)} file(s)",
        data={"files": files, "total": len(files)}
    ))

    try:
        data_in_path = get_workspace_path(workspace, "data_in")

        for file_idx, filename in enumerate(files):
            # Sanitize filename to prevent path traversal
            safe_filename = re.sub(r'[^\w\-._]', '_', filename)
            file_path = data_in_path / filename
            if not file_path.exists():
                logger.warning("File not found: %s", filename)
                continue

            # Step 1: Extract structured text via Docling
            text = extract_structured_text(file_path)

            if not text.strip():
                logger.warning("No content extracted from %s", filename)
                continue

            # Step 2: Process to graph
            file_result = await _process_content_to_graph(
                text=text,
                source_name=filename,
                workspace=workspace,
                provider=provider,
                model=model,
                embed=embed,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
                direction=direction,
                inference_delay=inference_delay,
                run_id=run_id,
                event_callback=event_callback
            )
            results.append({
                "file": filename,
                "status": file_result.get("status"),
                "triples": file_result.get("triples_extracted", 0)
            })

        await event_callback(IngestionEvent(
            event=IngestionEventType.COMPLETED,
            run_id=run_id,
            message=f"Ingestion complete: {len(results)} file(s) processed",
            data={
                "files_processed": len(results),
                "details": results
            }
        ))

    except Exception as e:
        logger.error("Background ingestion failed: %s", e, exc_info=True)
        await event_callback(IngestionEvent(
            event=IngestionEventType.ERROR,
            run_id=run_id,
            message=f"Ingestion failed: {str(e)}"
        ))

    finally:
        # Clean up event queue after a delay (allow SSE client to receive final event)
        await asyncio.sleep(5)
        _ingestion_events.pop(run_id, None)


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
    run_id: Optional[str] = None,
    event_callback: Optional[Any] = None
):
    """Core ingestion pipeline: extract -> validate -> store -> embed -> centrality."""
    # Step 0: Ensure Run ID and Partition Key
    if not run_id:
        run_id = str(uuid.uuid4())

    pk_source = f"{model or 'default'}-{source_name}"
    partition_key = hashlib.sha256(pk_source.encode()).hexdigest()

    # Step 0a: Check Neo4j connectivity
    conn = verify_connectivity()
    if conn["status"] != "connected":
        raise HTTPException(
            status_code=503,
            detail=f"Knowledge Graph database not available: {conn.get('error', 'Unknown connection error')}"
        )

    manifest = load_manifest(workspace)
    llm_timeout = manifest.llm_timeout
    synthesis_config = manifest.synthesis

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
    logger.info("Hierarchical parallel parsing initiated for %s: %d sections found.", source_name, len(sections))

    # Filter microscopic sections early
    active_sections = [s for s in sections if len(s['text'].strip()) >= synthesis_config.min_section_chars]

    triples = await parallel_extract_triples(
        sections=active_sections,
        direction=direction,
        provider=provider,
        model=model,
        parallel_limit=synthesis_config.parallel_limit,
        inference_delay=inference_delay,
        timeout=llm_timeout,
        config=synthesis_config,
        event_callback=event_callback
    )

    if not triples:
        return {"status": "no_triples_found", "triples_extracted": 0}

    # Step 2: Check for conflicts against existing graph
    existing = []
    try:
        graph = get_full_graph(workspace, show_all=True)
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
            timeout=llm_timeout,
            config=synthesis_config
        )

    if event_callback:
        await event_callback(IngestionEvent(
            event=IngestionEventType.CONFLICTS_CHECKED,
            run_id=run_id,
            source_name=source_name,
            message=f"Conflict check: {len(conflicts)} conflicts found",
            data={"conflicts": len(conflicts)}
        ))

    # Step 3: Store triples in Neo4j (Batch Mode)
    # Convert KnowledgeTriple objects to dicts for batch storage
    triple_dicts = [t.model_dump() if isinstance(t, KnowledgeTriple) else t for t in triples]
    stored_result = batch_add_triples(
        triples=triples,
        workspace=workspace,
        source_name=source_name,
        run_id=run_id
    )
    logger.info("[SUCCESS] Batched %d triples into Neo4j successfully.", stored_result['count'])

    if event_callback:
        await event_callback(IngestionEvent(
            event=IngestionEventType.STORED,
            run_id=run_id,
            source_name=source_name,
            message=f"Stored {stored_result['count']} triples",
            data={"count": stored_result["count"]}
        ))

    # Step 3b: Save Artifacts to Workspace Disk
    try:
        run_dir = get_workspace_path(workspace, f"runs/{run_id}")
        run_dir.mkdir(parents=True, exist_ok=True)

        # 1. Triples JSON
        with open(run_dir / "extraction.json", "w", encoding="utf-8") as f:
            json.dump(triple_dicts, f, indent=2, default=str)

        # 2. Metadata JSON
        meta = {
            "run_id": run_id,
            "partition_key": partition_key,
            "model": model,
            "source": source_name,
            "triples_count": len(triples),
            "conflicts_count": len(conflicts)
        }
        with open(run_dir / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        # 3. Simple Summary Markdown
        summary = f"# Synthesis Report: {source_name}\n\n"
        summary += f"- **Model**: {model or 'default'}\n"
        summary += f"- **Triples Extracted**: {len(triples)}\n"
        summary += f"- **Conflicts**: {len(conflicts)}\n\n"
        summary += "## Core Points\n"
        for t in triples[:10]:  # Top 10 for summary
            if isinstance(t, KnowledgeTriple):
                summary += f"- {t.subject} {t.predicate} {t.object} (Confidence: {t.confidence})\n"
            elif isinstance(t, dict):
                summary += f"- {t.get('subject')} {t.get('predicate')} {t.get('object')} (Confidence: {t.get('confidence')})\n"

        with open(run_dir / "summary.md", "w", encoding="utf-8") as f:
            f.write(summary)

    except Exception as e:
        logger.error("Failed to save artifacts: %s", e)

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

    # Step 5: Embed concepts (batch mode)
    embedded_count = 0
    if embed:
        all_concepts = set()
        for t in triples:
            if isinstance(t, KnowledgeTriple):
                if t.subject:
                    all_concepts.add(t.subject)
                if t.object:
                    all_concepts.add(t.object)
            elif isinstance(t, dict):
                if t.get("subject"):
                    all_concepts.add(t.get("subject"))
                if t.get("object"):
                    all_concepts.add(t.get("object"))

        # Use active provider for local embeddings instead of assuming Ollama
        actual_emb_provider = provider if embedding_provider == "local" else embedding_provider

        embeddings = await batch_embed_concepts(
            concepts=list(all_concepts),
            provider=actual_emb_provider,
            model=embedding_model,
            batch_size=synthesis_config.embedding_batch_size,
            event_callback=event_callback if event_callback else None
        )

        for concept_name, emb in embeddings.items():
            if emb:
                set_concept_embedding(concept_name, emb, workspace)
                embedded_count += 1

    # Step 6: Update Graph Centrality for visual sizing
    try:
        update_graph_centrality(workspace)
        if event_callback:
            await event_callback(IngestionEvent(
                event=IngestionEventType.CENTRALITY_UPDATED,
                run_id=run_id,
                message="Centrality scores updated"
            ))
    except Exception:
        pass

    return {
        "status": "ingested",
        "run_id": run_id,
        "partition_key": partition_key,
        "triples_extracted": len(triples),
        "triples_stored": stored_result.get("count", 0),
        "conflicts_detected": len(conflicts),
        "concepts_embedded": embedded_count,
        "triples": triple_dicts,
        "conflicts": conflicts
    }


@router.post("/graph/synthesize")
async def synthesize(request: SynthesizeRequest):
    """
    Run the Synthesis Layer: find structural isomorphisms across the graph.
    
    This is the "So What?" - the aha moment.
    """
    try:
        # Build a text summary of the graph for the LLM
        graph = get_full_graph(request.workspace, show_all=True)

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

        # FIX: Build the graph_summary string from lines
        graph_summary = "\n".join(lines)

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
