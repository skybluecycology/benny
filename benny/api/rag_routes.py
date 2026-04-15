"""
RAG Routes - Document ingestion and semantic search
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from pathlib import Path
import fitz  # PyMuPDF
import httpx

from ..core.workspace import get_workspace_path
from ..core.extraction import extract_structured_text
from ..tools.knowledge import get_chromadb_client
from ..core.models import LOCAL_PROVIDERS
from ..core.task_manager import task_manager
from ..governance.lineage import track_workflow_start, track_workflow_complete, track_aer
from ..governance.permission_manifest import register_manifest, create_ephemeral_manifest
import uuid
import json
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class IngestRequest(BaseModel):
    workspace: str = "default"
    files: Optional[List[str]] = None
    notebook_id: Optional[str] = None
    batch_size: Optional[int] = 500



class QueryRequest(BaseModel):
    query: str
    workspace: str = "default"
    top_k: int = 5
    selected_sources: Optional[List[str]] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    mode: str = "semantic" # "semantic" or "graph_agent"

class AdaptiveRAGRequest(BaseModel):
    query: str
    workspace: str = "default"
    model: str = "Qwen3-8B-Hybrid"
    max_retries: int = 3

class AdaptiveRAGResponse(BaseModel):
    answer: Optional[str]
    route: str
    route_explanation: str
    documents_retrieved: int
    documents_relevant: int
    retry_count: int
    execution_trace: List[str]
    hallucination_check: Optional[bool]
    answer_quality: Optional[bool]

@router.post("/rag/ingest")
async def ingest_files(request: IngestRequest):
    """Ingest files from data_in into ChromaDB using structured extraction (Docling)."""
    run_id = str(uuid.uuid4())
    task = task_manager.create_task(request.workspace, "rag_ingest", task_id=run_id)
    
    try:
        track_workflow_start(run_id, "rag_ingest", request.workspace, inputs=request.files or [])
        task_manager.add_aer_entry(
            run_id, 
            intent=f"Ingesting {len(request.files) if request.files else 'all'} files from data_in",
            observation="Initialization complete",
            plan=f"1. Extract text via Docling 2. Chunk 3. Batch upsert to ChromaDB ({collection_name if 'collection_name' in locals() else 'knowledge'})"
        )
    except Exception as e:
        logger.warning("Lineage tracking failed (init): %s", e)

    try:
        data_in_path = get_workspace_path(request.workspace, "data_in")
        if not data_in_path.exists():
            task_manager.update_task(run_id, status="failed", message="No files found in data_in")
            raise HTTPException(404, "No files found in data_in")
        
        # Get files to ingest
        if request.files:
            file_paths = [data_in_path / f for f in request.files]
        else:
            file_paths = list(data_in_path.glob("*.*"))
        
        # Filter for supported types
        supported = ['.txt', '.md', '.pdf', '.docx', '.pptx', '.html']
        file_paths = [f for f in file_paths if f.suffix.lower() in supported]
        
        if not file_paths:
            task_manager.update_task(run_id, status="failed", message="No supported files found")
            raise HTTPException(404, "No supported files found")
        
        # Get ChromaDB client
        client = get_chromadb_client(request.workspace)
        collection_name = f"notebook_{request.notebook_id}" if request.notebook_id else "knowledge"
        collection = client.get_or_create_collection(collection_name)

        # Update task total steps
        task_manager.update_task(run_id, total_steps=len(file_paths), progress=10)
        
        ingested = []
        for idx, file_path in enumerate(file_paths):
            try:
                msg = f"Processing {file_path.name} ({idx+1}/{len(file_paths)})..."
                task_manager.update_task(
                    run_id, 
                    message=msg, 
                    current_step=idx+1,
                    metadata={
                        "stage": "EXTRACTING",
                        "current_file": file_path.name
                    }
                )
                
                # Emit AER for extraction
                try:
                    track_aer(run_id, "rag_ingest", f"Extracting {file_path.name}", "Docling engine started")
                except Exception:
                    pass
                text = extract_structured_text(file_path)
                
                # Simple chunking (split by paragraphs)
                chunks = [c.strip() for c in text.split('\n\n') if c.strip()]
                
                if chunks:
                    task_manager.update_task(run_id, metadata={"stage": "INDEXING", "current_file": file_path.name, "chunks": len(chunks)})
                    
                    # 1. DELETE old entries for this source to prevent duplicates
                    collection.delete(where={"source": file_path.name})

                    # 2. UPLOAD in batches
                    batch_size = request.batch_size or 500
                    for i in range(0, len(chunks), batch_size):
                        batch_chunks = chunks[i:i + batch_size]
                        batch_ids = [f"{file_path.stem}_{j}" for j in range(i, i + len(batch_chunks))]
                        batch_metadatas = [{"source": file_path.name, "chunk_index": j} for j in range(i, i + len(batch_chunks))]
                        
                        collection.add(documents=batch_chunks, metadatas=batch_metadatas, ids=batch_ids)
                        
                        # Emit AER for commit
                        perc = (i + len(batch_chunks)) / len(chunks) * 100
                        task_manager.update_task(run_id, metadata={
                            "stage": "INDEXING", 
                            "current_file": file_path.name, 
                            "chunks": len(chunks),
                            "indexed_count": i + len(batch_chunks)
                        })
                        try:
                            track_aer(run_id, "rag_ingest", f"Committing chunks for {file_path.name}", f"Committed {i+len(batch_chunks)}/{len(chunks)} chunks ({perc:.0f}%)")
                        except Exception:
                            pass
                
                ingested.append({"file": file_path.name, "chunks": len(chunks)})
                task_manager.update_task(run_id, progress=10 + int(90 * (idx+1) / len(file_paths)))
                
            except Exception as e:
                task_manager.add_aer_entry(run_id, "Error", f"Failed {file_path.name}: {str(e)}")
                ingested.append({"file": file_path.name, "error": str(e)})
        
        task_manager.update_task(run_id, status="completed", progress=100, message="Ingestion finished successfully")
        try:
            track_workflow_complete(
                run_id, 
                "rag_ingest", 
                request.workspace, 
                ["extraction", "chunking", "upsert"], 
                0, 
                outputs=[f"chromadb:{collection_name}"]
            ) 
        except Exception:
            pass
        
        return {
            "status": "completed",
            "run_id": run_id,
            "workspace": request.workspace,
            "ingested": ingested,
            "total_documents": collection.count()
        }
        
    except Exception as e:
        task_manager.update_task(run_id, status="failed", message=str(e))
        raise HTTPException(500, f"Ingestion failed: {str(e)}")


@router.get("/rag/logs")
async def get_rag_logs(workspace: str = "default"):
    """Get the latest ingestion tasks from TaskManager."""
    try:
        tasks = task_manager.list_tasks(workspace)
        rag_tasks = [t for t in tasks if t.type == "rag_ingest"]
        if not rag_tasks:
            return {"tasks": []}
        
        # Sort by updated_at descending
        rag_tasks.sort(key=lambda x: x.updated_at, reverse=True)
        
        return {"tasks": [t.model_dump() for t in rag_tasks[:5]]}
    except Exception as e:
        return {"error": str(e), "tasks": []}


@router.get("/rag/status")
async def get_rag_status(workspace: str = "default"):
    """Get RAG status and document count"""
    try:
        client = get_chromadb_client(workspace)
        collection = client.get_or_create_collection("knowledge")
        
        # Get unique sources - optimized by only fetching metadatas
        all_data = collection.get(include=['metadatas'])
        sources = set()
        for meta in all_data['metadatas']:
            sources.add(meta.get('source', 'Unknown'))
        
        return {
            "workspace": workspace,
            "total_chunks": collection.count(),
            "unique_documents": len(sources),
            "documents": list(sources),
            "sources": list(sources) # Alias for consistency with graph API
        }

    except Exception as e:
        raise HTTPException(500, f"Status check failed: {str(e)}")


@router.post("/rag/query")
async def query_rag(request: QueryRequest):
    """Test semantic search"""
    try:
        client = get_chromadb_client(request.workspace)
        collection = client.get_or_create_collection("knowledge")
        
        if collection.count() == 0:
            return {
                "results": [],
                "message": "Knowledge base is empty"
            }
        
        results = collection.query(
            query_texts=[request.query],
            n_results=min(request.top_k, collection.count())
        )
        
        formatted_results = []
        for doc, meta, distance in zip(
            results['documents'][0],
            results['metadatas'][0],
            results['distances'][0]
        ):
            formatted_results.append({
                "text": doc,
                "source": meta.get('source', 'Unknown'),
                "relevance": round((1 - distance) * 100, 1)
            })
        

        return {
            "query": request.query,
            "results": formatted_results,
            "count": len(formatted_results)
        }
        
    except Exception as e:
        raise HTTPException(500, f"Query failed: {str(e)}")


@router.post("/rag/chat")
async def chat_rag(request: QueryRequest):
    """RAG-augmented chat for workspace documents or Neural Graph Agent"""
    try:
        # Handle Graph Agent Mode
        if request.mode == "graph_agent":
            # 1. Load the System Workflow Definition
            from .workflow_routes import workflow_storage
            from .studio_executor import topological_sort, _run_workflow_background, StudioExecuteRequest
            
            wf_def = workflow_storage.get_workflow("System_GraphChatAgent")
            if not wf_def:
                 # Fallback/Safety: In case file is not found, we could return error 
                 # but let's try to be robust. 
                 raise HTTPException(404, "System_GraphChatAgent workflow definition not found.")

            # 2. Trigger Workflow Execution
            run_id = f"chat-agent-{uuid.uuid4().hex[:8]}"
            
            # Map workflow definition to request nodes/edges
            nodes = wf_def.get("nodes", [])
            edges = wf_def.get("edges", [])
            
            # Update the LLM node with the user's specific request and provider/model choice
            for node in nodes:
                if node.get("type") == "llm":
                    if "config" not in node["data"]: node["data"]["config"] = {}
                    if request.model:
                        node["data"]["config"]["model"] = request.model
            
            from pydantic import TypeAdapter
            from .studio_executor import StudioNode, StudioEdge
            
            pydantic_nodes = [StudioNode(**n) for n in nodes]
            pydantic_edges = [StudioEdge(**e) for e in edges]
            
            execute_req = StudioExecuteRequest(
                nodes=pydantic_nodes,
                edges=pydantic_edges,
                workspace=request.workspace,
                message=request.query
            )
            
            # Sort and Run
            sorted_nodes = topological_sort(pydantic_nodes, pydantic_edges)
            
            # We run this synchronously for the chat endpoint to get the final answer
            # but we still want the standard audit trail.
            # However, _run_workflow_background is designed for fire-and-forget.
            # Let's use a simpler execution for synchronous chat return while maintaining audit.
            
            # For simplicity in this implementation, we will manually run the nodes 
            # or use the background task with an Event wait.
            # Actually, let's just use the execution logic directly to wait for final_output.
            
            context = {"message": request.query, "workspace": request.workspace}
            final_answer = ""
            
            # Security: Register ephemeral manifest for this specific chat agent run
            # This allows the agent to use its assigned tools in a Least-Privilege scope
            chat_manifest = create_ephemeral_manifest(run_id, ["query_graph", "search_kb", "read_file"])
            register_manifest(chat_manifest)
            logger.info(f"Registered ephemeral security manifest for Agent Run '{run_id}'")

            # Initial track
            track_workflow_start(run_id, "chat_graph_agent", request.workspace, inputs=[request.query])
            task_manager.create_task(request.workspace, "chat_graph_agent", task_id=run_id)

            from .studio_executor import execute_trigger_node, execute_llm_node, execute_data_node
            
            for node in sorted_nodes:
                try:
                    logger.info(f"Executing Agent Node: {node.id} ({node.type})")
                    if node.type == "trigger":
                        output = await execute_trigger_node(node, request.query, context)
                    elif node.type == "llm":
                        # Attach the run_id for auditing AND as agent_id for manifest lookup
                        output = await execute_llm_node(node, context, request.workspace, run_id=run_id, agent_id=run_id)
                        if output.get("response"):
                            context["llm_output"] = output["response"]
                            final_answer = output["response"]
                    elif node.type == "data":
                        # Support checking graph context optionally
                        output = await execute_data_node(node, context, request.workspace)
                    else:
                        output = {"message": f"Skipping node type: {node.type}"}
                        
                    # Check for explicit errors returned by node handlers
                    if output.get("error"):
                        logger.error(f"Node {node.id} returned error: {output['error']}")
                        final_answer = f"Agent execution stopped at node '{node.id}': {output['error']}"
                        break
                        
                except Exception as e:
                    logger.error(f"Agent Node {node.id} crashed: {e}", exc_info=True)
                    final_answer = f"Error in agent reasoning at node '{node.id}': {str(e)}"
                    break

            track_workflow_complete(run_id, "chat_graph_agent", request.workspace, ["reasoning"], 0)
            task_manager.update_task(run_id, status="completed" if final_answer else "failed", progress=100)

            # Detail the failure if final_answer still empty
            if not final_answer:
                 final_answer = "The Neural Graph Agent failed to generate a response. This could be due to model connectivity issues or an empty graph. Please check your Forge workspace or diagnostics."

            return {
                "answer": final_answer,
                "sources": ["Neural Graph", "Workspace Files"],
                "query": request.query,
                "mode": "graph_agent",
                "run_id": run_id
            }

        # 1. Retrieve context (LEGACY MODE)
        client = get_chromadb_client(request.workspace)
        collection = client.get_or_create_collection("knowledge")
        
        context_text = ""
        sources = []
        
        if collection.count() > 0:
            import re
            from pathlib import Path
            all_data = collection.get(include=['metadatas'])
            available_sources = set(meta.get('source', 'Unknown') for meta in all_data['metadatas'] if 'source' in meta)
            
            mentioned_sources = []
            
            if request.selected_sources and len(request.selected_sources) > 0:
                # Explicitly user-selected sources
                mentioned_sources = [s for s in request.selected_sources if s in available_sources]
            else:
                # Smart guessing based on query
                query_lower = request.query.lower()
                for source in available_sources:
                    source_stem = Path(source).stem.lower()
                    words = [w for w in set(re.split(r'[^a-zA-Z0-9]', source_stem)) if len(w) > 3]
                    for w in words:
                        if w in query_lower:
                            mentioned_sources.append(source)
                            break
                        
            results_list = []
            
            if mentioned_sources:
                k_per_source = max(3, request.top_k // len(mentioned_sources))
                for source in mentioned_sources:
                    try:
                        res = collection.query(
                            query_texts=[request.query],
                            n_results=min(k_per_source, collection.count()),
                            where={"source": source}
                        )
                        if res['documents'] and res['documents'][0]:
                            for doc, meta in zip(res['documents'][0], res['metadatas'][0]):
                                results_list.append((doc, meta))
                    except Exception:
                        pass
                
                # add a few general query chunks too
                try:
                    gen_res = collection.query(
                        query_texts=[request.query],
                        n_results=min(3, collection.count())
                    )
                    if gen_res['documents'] and gen_res['documents'][0]:
                        for doc, meta in zip(gen_res['documents'][0], gen_res['metadatas'][0]):
                            results_list.append((doc, meta))
                except Exception:
                    pass
            else:
                try:
                    res = collection.query(
                        query_texts=[request.query],
                        n_results=min(request.top_k, collection.count())
                    )
                    if res['documents'] and res['documents'][0]:
                        for doc, meta in zip(res['documents'][0], res['metadatas'][0]):
                            results_list.append((doc, meta))
                except Exception:
                    pass

            seen_docs = set()
            for doc, meta in results_list:
                if doc not in seen_docs:
                    seen_docs.add(doc)
                    source = meta.get('source', 'Unknown')
                    context_text += f"[Source: {source}]\n{doc}\n\n"
                    sources.append(source)

        
        # 2. Build Prompt
        system_prompt = """You are a helpful AI assistant for the user's workspace.
Answer questions based on the provided context.
If the answer is not in the context, say so, but you can use general knowledge to help explain if relevant.
CRITICAL: You MUST cite your sources directly inline in the text when you use information from the context. 
Use the exact explicit format: [Source: filename.ext] right after the relevant statement.
Example: The revenue increased by 20% [Source: financial_report.pdf]."""

        user_prompt = f"""CONTEXT FROM DOCUMENTS:
{context_text if context_text else "No specific documents found."}

USER QUESTION:
{request.query}

ANSWER:"""

        # 3. Call LLM
        try:
            # Configure provider settings
            provider_name = request.provider or "fastflowlm"
            provider_config = LOCAL_PROVIDERS.get(provider_name, LOCAL_PROVIDERS["fastflowlm"])
            
            debug_response = {}
            payload = {}
            
            # Configure API base and key for this request
            # Note: litellm uses env vars, but we can pass api_base/api_key explicitly if needed
            # or set them temproarily. Since requests might be concurrent, 
            # passing params to completion() is safer if supported, but for local use 
            # env vars are often expected.
            
            # For local models, we construct the model string expected by litellm
            # E.g. "openai/custom" pointing to local base_url
            

            # Determine model name
            if request.model:
                # Lemonade models are often registered as e.g 'amd/Qwen3...' but the backend
                # expects just the base name when chatting.
                model_name = request.model.split('/')[-1]
            else:
                if provider_name == "ollama":
                    model_name = "llama3"
                elif provider_name == "lemonade":
                    model_name = "amd/Qwen3-8B-Hybrid-quantized_int4-float16-cpu-onnx"
                elif provider_name == "fastflowlm":
                    model_name = "gemma3:4b"
                else:
                    model_name = "default"

            # Use httpx for direct API call to avoid litellm dependency issues
            api_base = provider_config["base_url"]
            chat_url = f"{api_base}/chat/completions"
            
            # Combine system and user prompt to ensure compatibility with all local models
            if provider_name == "fastflowlm":
                # FastFlowLM (Gemma 3) prefers acceptable instruction format.
                # Use a specific structure that proved to work in testing.
                # We limit context to ~4000 chars to avoid overflowing local model context window (often 8k or 4k)
                safe_context = context_text[:4000] if context_text else "No specific documents found."
                content = f"Instructions: {system_prompt}\n\nContext:\n{safe_context}\n\nUser Question: {request.query}\n\nAnswer:"
            else:
                 content = f"{system_prompt}\n\n{user_prompt}"
            
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "user", "content": content}
                ],
                "temperature": 0.7
            }
            
            # print(f"DEBUG PAYLOAD: {json.dumps(payload)}")
            
            print(f"DEBUG: Calling {chat_url} with model {model_name}")
            
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(
                    chat_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code == 200:
                    data = response.json()
                    answer = data['choices'][0]['message']['content']
                    debug_response = data
                else:
                    error_msg = f"Status {response.status_code}: {response.text}"
                    print(f"LLM Error: {error_msg}")
                    answer = f"Error from {request.provider}: {error_msg}"
                    debug_response = {"error": error_msg}

        except Exception as llm_error:
            error_details = str(llm_error) if str(llm_error) else repr(llm_error)
            print(f"LLM Exception: {error_details}")
            answer = f"Connection error with {request.provider}: {error_details}. Please check if the service is running or if the model timed out preparing the response."
            debug_response = {"exception": error_details}

        return {
            "answer": answer,
            "sources": list(set(sources)),
            "query": request.query,
            "debug_payload": payload,
            "debug_response": debug_response
        }

    except Exception as e:
        raise HTTPException(500, f"Chat failed: {str(e)}")


from fastapi import Response

@router.post("/rag/adaptive-query", response_model=AdaptiveRAGResponse)
async def adaptive_rag_query(request: AdaptiveRAGRequest, response: Response):
    """
    Adaptive RAG query — self-correcting retrieval pipeline.
    Routes queries through no_retrieval / single_step / multi_hop 
    with quality grading and automatic query rewriting.
    """
    from ..core.adaptive_rag import run_adaptive_rag
    
    try:
        result = await run_adaptive_rag(
            query=request.query,
            workspace=request.workspace,
            model=request.model,
            max_retries=request.max_retries,
        )
        
        # Set the strategy header
        response.headers["X-RAG-Strategy"] = result.get("route", "single_step")
        
        return AdaptiveRAGResponse(
            answer=result.get("generation"),
            route=result.get("route", "single_step"),
            route_explanation=result.get("route_explanation", ""),
            documents_retrieved=len(result.get("documents", [])),
            documents_relevant=len(result.get("graded_documents", [])),
            retry_count=result.get("retry_count", 0),
            execution_trace=result.get("execution_trace", []),
            hallucination_check=result.get("hallucination_check"),
            answer_quality=result.get("answer_quality"),
        )
    except Exception as e:
        raise HTTPException(500, f"Adaptive RAG failed: {str(e)}")
