"""
Studio Executor - Execute visual node graphs from the Studio canvas
Interprets nodes + edges and runs them in topological order
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import asyncio
import json
import httpx
from typing import AsyncGenerator, Dict, Any, List, Optional
import uuid
import logging
from datetime import datetime

from ..core.models import LOCAL_PROVIDERS, call_model, get_model_config, get_active_model
from ..governance.lineage import (
    track_workflow_start, 
    track_workflow_complete, 
    track_llm_call, 
    track_tool_execution,
    track_policy_breach
)
from ..governance.execution_audit import (
    emit_execution_failure,
    emit_node_execution_state,
    emit_execution_checkpoint,
    ExecutionPhase
)
from ..core.task_manager import task_manager
from ..core.workspace import get_workspace_path
from ..tools.knowledge import get_chromadb_client

router = APIRouter()

# Event buffers for SSE streaming (run_id → list of SSE event dicts)
_execution_events: Dict[str, list] = {}
_execution_event_flags: Dict[str, asyncio.Event] = {}
# HITL responses waiting to be picked up (run_id → asyncio.Queue)
_hitl_responses: Dict[str, asyncio.Queue] = {}




def _emit_execution_event(run_id: str, event_type: str, data: Dict[str, Any]):
    """Push an event into the buffer for SSE consumers."""
    if run_id not in _execution_events:
        logging.warning(f"[AUDIT] _emit_execution_event called but run_id not found: {run_id}")
        _execution_events[run_id] = []
    
    event = {
        "type": event_type,
        "timestamp": datetime.now().isoformat(),
        **data,
    }
    _execution_events[run_id].append(event)
    logging.info(f"[AUDIT] Event emitted | run_id: {run_id} | type: {event_type} | total events: {len(_execution_events[run_id])}")
    
    # Signal any waiting SSE consumers
    flag = _execution_event_flags.get(run_id)
    if flag:
        flag.set()
        logging.info(f"[AUDIT] Signaled event flag for {run_id}")
    else:
        logging.warning(f"[AUDIT] No event flag found for {run_id}")


@router.get("/workflows/execute/{run_id}/events")
async def stream_execution_events(run_id: str):
    """SSE endpoint for real-time execution events."""
    logging.info(f"[AUDIT] SSE stream requested for run_id: {run_id}")
    logging.info(f"[AUDIT] Active run_ids in _execution_events: {list(_execution_events.keys())}")
    
    if run_id not in _execution_events:
        logging.error(f"[AUDIT] Run ID not found in _execution_events: {run_id}")
        logging.error(f"[AUDIT] Available run_ids: {list(_execution_events.keys())}")
    
    async def event_generator() -> AsyncGenerator[str, None]:
        _execution_event_flags[run_id] = asyncio.Event()
        last_index = 0
        logging.info(f"[AUDIT] Event generator started for {run_id}")
        
        while True:
            events = _execution_events.get(run_id, [])
            logging.info(f"[AUDIT] Checking events for {run_id} | total events: {len(events)} | last_index: {last_index}")
            
            while last_index < len(events):
                event = events[last_index]
                event_json = json.dumps(event)
                logging.info(f"[AUDIT] Yielding event #{last_index} for {run_id} | type: {event.get('type')}")
                yield f"data: {event_json}\n\n"
                last_index += 1
                
                # Check if execution is done
                if event["type"] in ("workflow_completed", "workflow_failed"):
                    logging.info(f"[AUDIT] Execution complete for {run_id} | final event: {event['type']}")
                    return
            
            # Wait for new events
            _execution_event_flags[run_id].clear()
            try:
                # 30s heartbeat timeout
                await asyncio.wait_for(_execution_event_flags[run_id].wait(), timeout=30.0)
                logging.info(f"[AUDIT] Event flag signaled for {run_id}")
            except asyncio.TimeoutError:
                logging.info(f"[AUDIT] Heartbeat sent for {run_id}")
                yield f"data: {json.dumps({'type': 'heartbeat'})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@router.post("/workflows/execute/{run_id}/hitl-response")
async def submit_hitl_response(run_id: str, response: Dict[str, Any]):
    """Submit a HITL response to resume a paused workflow."""
    if run_id not in _hitl_responses:
        raise HTTPException(404, f"Active run not found: {run_id}")
    
    # Push the response to the queue for the background worker
    await _hitl_responses[run_id].put(response)
    
    _emit_execution_event(run_id, "hitl_response_received", {
        "decision": response.get("decision"),
    })
    
    return {"status": "received", "run_id": run_id}


class StudioNode(BaseModel):
    id: str
    type: str  # trigger, llm, tool, data, logic
    position: Dict[str, float] = {}
    data: Dict[str, Any] = {}


class StudioEdge(BaseModel):
    id: str
    source: str
    target: str


class StudioExecuteRequest(BaseModel):
    nodes: List[StudioNode]
    edges: List[StudioEdge]
    workspace: str = "default"
    message: Optional[str] = None  # User message for trigger nodes


class NodeResult(BaseModel):
    node_id: str
    node_type: str
    status: str  # success, error
    output: Any = None
    error: Optional[str] = None


class StudioExecuteResponse(BaseModel):
    status: str
    node_results: List[NodeResult]
    artifact_path: Optional[str] = None
    final_output: Optional[str] = None


def topological_sort(nodes: List[StudioNode], edges: List[StudioEdge]) -> List[StudioNode]:
    """Sort nodes in execution order based on edges"""
    node_map = {n.id: n for n in nodes}
    in_degree = {n.id: 0 for n in nodes}
    adjacency = {n.id: [] for n in nodes}

    for edge in edges:
        if edge.target in in_degree:
            in_degree[edge.target] += 1
        if edge.source in adjacency:
            adjacency[edge.source].append(edge.target)

    # Kahn's algorithm
    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    sorted_ids = []

    while queue:
        nid = queue.pop(0)
        sorted_ids.append(nid)
        for neighbor in adjacency.get(nid, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return [node_map[nid] for nid in sorted_ids if nid in node_map]


async def execute_trigger_node(node: StudioNode, message: str, context: Dict) -> Dict:
    """Execute a trigger node — captures the user message"""
    trigger_type = (node.data.get("config") or {}).get("triggerType", "chat")
    return {
        "message": message or "No message provided",
        "trigger_type": trigger_type
    }


async def execute_data_node(node: StudioNode, context: Dict, workspace: str) -> Dict:
    """Execute a data node — RAG search or file write"""
    config = node.data.get("config") or {}
    operation = config.get("operation", "search")

    if operation == "search":
        # RAG search on workspace ChromaDB
        query = context.get("message", "")
        try:
            client = get_chromadb_client(workspace)
            collection = client.get_or_create_collection("knowledge")

            if collection.count() == 0:
                return {"results": [], "message": "Knowledge base empty — please ingest documents first"}

            results = collection.query(
                query_texts=[query],
                n_results=min(5, collection.count())
            )

            formatted = []
            context_text = ""
            for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                source = meta.get("source", "Unknown")
                formatted.append({"text": doc, "source": source})
                context_text += f"[Source: {source}]\n{doc}\n\n"

            return {
                "results": formatted,
                "context_text": context_text,
                "count": len(formatted)
            }
        except Exception as e:
            return {"error": str(e), "results": []}

    elif operation == "write":
        # Write the LLM output to a .md file
        content = context.get("llm_output", "No content generated")
        filename = config.get("path", "output.md")
        if not filename.endswith(".md"):
            filename += ".md"

        try:
            out_path = get_workspace_path(workspace, "data_out") / filename
            out_path.parent.mkdir(parents=True, exist_ok=True)

            # Build a proper markdown document
            md_content = f"# {filename.replace('.md', '').replace('_', ' ').title()}\n\n"
            md_content += f"*Generated by Benny Studio — {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n"
            md_content += "---\n\n"
            md_content += content

            out_path.write_text(md_content, encoding="utf-8")

            return {
                "written": True,
                "path": str(out_path),
                "filename": filename,
                "download_url": f"http://localhost:8005/api/files/{workspace}/data_out/{filename}"
            }
        except Exception as e:
            return {"error": str(e), "written": False}

    elif operation == "read":
        # Use 'path' from config, fallback to 'label' if not specified
        filename = config.get("path") or node.data.get("label", "")
        
        if not filename:
            return {
                "error": "Data node read operation requires 'path' in config or 'label' for filename",
                "hint": "Configure the path field or ensure label contains the filename"
            }
        
        try:
            path = get_workspace_path(workspace, "data_in") / filename
            if not path.exists():
                path = get_workspace_path(workspace, "data_out") / filename
            
            if path.exists():
                content = path.read_text(encoding="utf-8")
                return {"content": content, "filename": filename}
            return {"error": f"File not found: {filename}", "looked_in": ["data_in", "data_out"]}
        except Exception as e:
            return {"error": f"Failed to read file '{filename}': {str(e)}"}

    elif operation == "adaptive_search":
        from ..core.adaptive_rag import run_adaptive_rag
        
        query = context.get("message", "")
        max_retries = int(config.get("maxRetries", 3))
        
        try:
            result = await run_adaptive_rag(
                query=query,
                workspace=workspace,
                model=config.get("model", "Qwen3-8B-Hybrid"),
                max_retries=max_retries,
            )
            
            answer = result.get("generation", "")
            context_text = ""
            for doc in result.get("graded_documents", []):
                context_text += f"[Source: {doc.get('source', 'Unknown')}]\n{doc.get('content', '')}\n\n"
            
            return {
                "results": result.get("graded_documents", []),
                "context_text": context_text,
                "answer": answer,
                "route": result.get("route", "single_step"),
                "retry_count": result.get("retry_count", 0),
                "count": len(result.get("graded_documents", [])),
            }
        except Exception as e:
            return {"error": str(e), "results": []}

    return {"error": f"Unknown data operation: {operation}"}


async def execute_llm_node(node: StudioNode, context: Dict, workspace: str, run_id: Optional[str] = None) -> Dict:
    """
    Execute an LLM Agent node with tool-calling capabilities.
    The agent receives attached skills and autonomously decides to call them.
    """
    from ..core.skill_registry import registry
    from ..core.models import get_active_model
    import json

    config = node.data.get("config") or {}
    
    # Model priority: node config → workspace default → auto-detect
    model_id = config.get("model")
    if not model_id or model_id == "Qwen3-8B-Hybrid":
        try:
            model_id = await get_active_model(workspace)
            logging.info(f"LLM Node using auto-detected model: {model_id}")
        except Exception:
            model_id = "Qwen3-8B-Hybrid"
            
    model_cfg = get_model_config(model_id)
    model_name = model_cfg["model"]
    system_prompt = config.get("systemPrompt", "You are a helpful AI assistant.")
    attached_skills = config.get("skills", [])  # List of skill IDs

    # Get tool schemas for the attached skills
    tools = None
    if attached_skills:
        tool_schemas = registry.get_tool_schemas(attached_skills, workspace)
        if tool_schemas:
            tools = tool_schemas

    # Build initial messages array
    messages = [
        {"role": "system", "content": system_prompt}
    ]

    user_message = context.get("message", "")
    rag_context = context.get("context_text", "")
    
    if rag_context:
        messages.append({
            "role": "user", 
            "content": f"CONTEXT FROM PREVIOUS NODES:\n{rag_context}\n\nUSER QUESTION:\n{user_message}"
        })
    else:
        messages.append({"role": "user", "content": user_message})

    # Determine provider config from registry
    api_base = model_cfg.get("base_url")
    if not api_base:
        # Fallback to lemonade/ollama if registry didn't have a base_url (unlikely for local)
        provider_config = LOCAL_PROVIDERS.get("lemonade", LOCAL_PROVIDERS.get("ollama"))
        api_base = provider_config["base_url"]
        
    chat_url = f"{api_base}/chat/completions"
    
    # Tool-calling loop (max 5 iterations to prevent infinite loops)
    max_steps = 5
    current_step = 0
    total_tokens = 0
    executed_tools = []

    async with httpx.AsyncClient(timeout=300.0) as client:
        while current_step < max_steps:
            current_step += 1
            
            payload = {
                "model": model_name,
                "messages": messages,
                "temperature": config.get("temperature", 0.7)
            }
            if tools:
                payload["tools"] = tools

            try:
                response = await client.post(
                    chat_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
            except Exception as e:
                return {"error": f"LLM connection error: {str(e)}", "response": None}

            if response.status_code != 200:
                # FastFlowLM models might not support tools properly.
                # If tool-calling fails, try a fallback without tools.
                if tools and ("tool" in response.text.lower() or "function" in response.text.lower()):
                    payload.pop("tools")
                    response = await client.post(chat_url, json=payload, headers={"Content-Type": "application/json"})
                    if response.status_code != 200:
                        return {"error": f"LLM error: {response.status_code} {response.text}", "response": None}
                else:
                    return {"error": f"LLM error: {response.status_code} {response.text}", "response": None}

            data = response.json()
            message = data["choices"][0]["message"]
            usage = data.get("usage", {})
            total_tokens += usage.get("total_tokens", 0)

            # Record LLM call to Governance Log
            if run_id:
                track_llm_call(
                    parent_run_id=run_id,
                    model=model_name,
                    provider="lemonade", 
                    usage=usage,
                    parent_job_name="studio_workflow"
                )

            # Record assistant message
            messages.append(message)

            # Check if LLM wants to call tools
            if "tool_calls" in message and message["tool_calls"]:
                tool_calls = message["tool_calls"]
                
                # Execute each tool call
                for tc in tool_calls:
                    func_name = tc["function"]["name"]
                    call_id = tc["id"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except json.JSONDecodeError:
                        args = {}

                    # Run the skill via registry
                    result_str = registry.execute_skill(func_name, workspace, **args)
                    executed_tools.append({"name": func_name, "args": args})

                    # Track tool execution in audit log
                    if run_id:
                        track_tool_execution(
                            parent_run_id=run_id,
                            tool_name=func_name,
                            tool_args=args, # Refactored to tool_args
                            success=True,
                            parent_job_name="studio_workflow"
                        )

                    # Add tool response to messages
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": func_name,
                        "content": result_str
                    })
                
                # Loop continues to send tool results to LLM
                continue

            # If no tool calls, this is the final answer
            answer = message.get("content", "")
            return {
                "response": answer,
                "model": model_name,
                "tokens": total_tokens,
                "tool_executions": executed_tools
            }

        # If loop maxes out
        return {
            "error": "Agent execution max steps reached",
            "response": messages[-1].get("content", ""),
            "tool_executions": executed_tools
        }



async def _run_workflow_background(
    run_id: str,
    request: StudioExecuteRequest,
    sorted_nodes: List[StudioNode]
):
    """Background task to execute workflow and emit SSE events."""
    logging.info(f"[AUDIT] Background task started | run_id: {run_id} | workspace: {request.workspace} | nodes: {len(sorted_nodes)}")
    
    context: Dict[str, Any] = {
        "message": request.message or "",
        "workspace": request.workspace
    }

    node_results: List[NodeResult] = []
    artifact_path = None
    final_output = None
    overall_status = "completed"
    
    try:
        # Emit initialization checkpoint
        logging.info(f"[AUDIT] Emitting initialization checkpoint for {run_id}")
        emit_execution_checkpoint(
            run_id,
            request.workspace,
            "initialization",
            {"nodes_count": len(sorted_nodes), "message": request.message}
        )
        
        logging.info(f"[AUDIT] Starting node execution loop for {run_id} | nodes: {[n.id for n in sorted_nodes]}")

        for node in sorted_nodes:
            logging.info(f"[AUDIT] Executing node {node.id} (type: {node.type}) for run_id: {run_id}")
            
            # Emit Start Event
            _emit_execution_event(run_id, "node_started", {
                "nodeId": node.id,
                "nodeName": node.data.get("label", node.type),
            })
            
            emit_execution_checkpoint(
                run_id,
                request.workspace,
                f"node_start_{node.id}",
                {"node_type": node.type, "node_label": node.data.get("label", node.id)}
            )
            
            try:
                if node.type == "trigger":
                    output = await execute_trigger_node(node, request.message or "", context)
                    context["message"] = output.get("message", context["message"])

                elif node.type == "data":
                    output = await execute_data_node(node, context, request.workspace)
                    if "context_text" in output:
                        context["context_text"] = output["context_text"]
                    if output.get("written"):
                        artifact_path = output.get("path")

                elif node.type == "llm":
                    output = await execute_llm_node(node, context, request.workspace, run_id=run_id)
                    if output.get("response"):
                        context["llm_output"] = output["response"]
                        final_output = output["response"]

                elif node.type == "a2a":
                    output = await execute_a2a_node(node, context, request.workspace)
                    if output.get("response"):
                        context["llm_output"] = output["response"]
                        final_output = output["response"]

                elif node.type == "intervention":
                    output = await execute_intervention_node(node, context, request.workspace, run_id)

                elif node.type == "tool":
                    output = {"message": "Tool node executed (stub)"}

                elif node.type == "logic":
                    output = {"message": "Logic node passed"}

                else:
                    output = {"message": f"Unknown node type: {node.type}"}

                has_error = "error" in output and output["error"]
                status = "error" if has_error else "success"
                
                # Emit node execution state to audit log
                emit_node_execution_state(
                    run_id,
                    request.workspace,
                    node.id,
                    status,
                    inputs={"node_config": node.data},
                    outputs=output,
                    error=output.get("error") if has_error else None
                )
                
                # Emit Completion Event
                _emit_execution_event(run_id, "node_completed" if not has_error else "node_error", {
                    "nodeId": node.id,
                    "output": str(output.get("response", output.get("message", "")))[:500],
                    "error": output.get("error") if has_error else None,
                    "reasoning": output.get("reasoning_trace") # Placeholder for AER
                })

                node_results.append(NodeResult(
                    node_id=node.id,
                    node_type=node.type,
                    status=status,
                    output=output,
                    error=output.get("error") if has_error else None
                ))
                
                if has_error:
                    overall_status = "failed"
                    break

            except Exception as e:
                logging.error(f"Node execution failed: {str(e)}", exc_info=True)
                
                # Emit detailed failure with full context and stack trace
                emit_execution_failure(
                    run_id,
                    request.workspace,
                    ExecutionPhase.EXECUTION,
                    e,
                    node_id=node.id,
                    context={
                        "node_type": node.type,
                        "node_label": node.data.get("label", node.id),
                        "node_config": node.data,
                        "execution_context": {k: str(v)[:200] for k, v in context.items()},  # Truncate large values
                        "previous_results": [{"node_id": r.node_id, "status": r.status} for r in node_results]
                    }
                )
                
                # Emit node failure state
                emit_node_execution_state(
                    run_id,
                    request.workspace,
                    node.id,
                    "failed",
                    error=str(e)
                )
                
                _emit_execution_event(run_id, "node_error", {
                    "nodeId": node.id,
                    "error": str(e),
                })
                node_results.append(NodeResult(
                    node_id=node.id,
                    node_type=node.type,
                    status="error",
                    error=str(e)
                ))
                overall_status = "failed"
                break

        # Finalize Event
        final_event_type = "workflow_completed" if overall_status == "completed" else "workflow_failed"
        _emit_execution_event(run_id, final_event_type, {
            "outputs": {"final_output": final_output} if overall_status == "completed" else {},
            "error": "One or more nodes failed" if overall_status == "failed" else None
        })
        
        # Emit finalization checkpoint
        emit_execution_checkpoint(
            run_id,
            request.workspace,
            "finalization",
            {
                "status": overall_status,
                "nodes_executed": len(node_results),
                "nodes_failed": len([r for r in node_results if r.status == "error"])
            }
        )

    except Exception as e:
        """Catch any unhandled exceptions outside the node execution loop"""
        logging.error(f"Workflow execution error outside node loop: {str(e)}", exc_info=True)
        overall_status = "failed"
        
        # Emit comprehensive failure event
        emit_execution_failure(
            run_id,
            request.workspace,
            ExecutionPhase.INITIALIZATION,
            e,
            context={
                "nodes_count": len(sorted_nodes),
                "node_results_so_far": len(node_results),
                "workflow_phase": "pre-execution or post-execution"
            }
        )

    finally:
        # Cleanup HITL queue if any
        if run_id in _hitl_responses:
            del _hitl_responses[run_id]
        
        # Finalize Audit
        task_manager.update_task(run_id, status=overall_status, progress=100)
        track_workflow_complete(run_id, "studio_workflow", [r.node_type for r in node_results], 0)


@router.post("/workflows/execute")
async def execute_studio_workflow(request: StudioExecuteRequest):
    """Start Studio node graph execution in background."""
    logging.info(f"[AUDIT] /api/workflows/execute called | workspace={request.workspace} | message={request.message[:50] if request.message else 'none'} | nodes={len(request.nodes)} | edges={len(request.edges)}")
    
    if not request.nodes:
        logging.error("[AUDIT] No nodes in workflow - rejecting request")
        raise HTTPException(400, "No nodes in workflow")

    # Sort nodes in execution order
    try:
        sorted_nodes = topological_sort(request.nodes, request.edges)
        logging.info(f"[AUDIT] Topologically sorted {len(sorted_nodes)} nodes: {[n.id for n in sorted_nodes]}")
    except Exception as e:
        logging.error(f"[AUDIT] Failed to sort nodes topologically: {str(e)}", exc_info=True)
        raise HTTPException(400, f"Invalid workflow graph: {str(e)}")

    run_id = f"run-{uuid.uuid4().hex[:8]}"
    logging.info(f"[AUDIT] Created run_id: {run_id}")
    
    # Initialize buffers
    _execution_events[run_id] = []
    _hitl_responses[run_id] = asyncio.Queue()
    logging.info(f"[AUDIT] Initialized execution buffers for {run_id}")
    
    # Start task tracking and lineage
    task_manager.create_task(request.workspace, "studio_workflow", task_id=run_id)
    track_workflow_start(
        run_id, 
        "studio_workflow", 
        request.workspace,
        inputs=[f"node_{n.id}" for n in request.nodes],
        outputs=[f"studio_run_{run_id}"]
    )
    logging.info(f"[AUDIT] Started task tracking and lineage for {run_id}")

    # Launch background task with proper error handling
    task = asyncio.create_task(_run_workflow_background(run_id, request, sorted_nodes))
    logging.info(f"[AUDIT] Launched background task for {run_id}")
    
    # Add callback to handle unhandled exceptions in background task
    def handle_exception(future):
        try:
            future.result()
        except Exception as e:
            logging.error(f"[AUDIT] Unhandled exception in workflow {run_id}: {str(e)}", exc_info=True)
            # Ensure failure is recorded
            try:
                emit_execution_failure(
                    run_id,
                    request.workspace,
                    ExecutionPhase.EXECUTION,
                    e,
                    context={"error_location": "task callback"}
                )
                task_manager.update_task(run_id, status="failed", message=f"Background task failed: {str(e)[:200]}")
            except Exception as callback_error:
                logging.error(f"[AUDIT] Failed to emit failure for {run_id}: {str(callback_error)}")
    
    task.add_done_callback(handle_exception)

    response_data = {"run_id": run_id, "status": "started"}
    logging.info(f"[AUDIT] Returning response: {response_data}")
    return response_data



async def execute_intervention_node(node: StudioNode, context: Dict, workspace: str, run_id: str) -> Dict:
    """
    Execute an Intervention node. 
    Checks if context matches a 'breach' condition. 
    If so, pauses execution and waits for HITL response.
    """
    config = node.data.get("config") or {}
    rule = config.get("rule", "")  # e.g. a regex or keyword
    description = config.get("description", "Policy violation detected")
    
    # Simple check: if 'rule' is found in context['llm_output'] or context['message']
    input_text = str(context.get("llm_output", context.get("message", "")))
    
    is_breached = False
    if rule and rule.lower() in input_text.lower():
        is_breached = True
    
    if is_breached:
        # 1. Log Exception in Lineage
        track_policy_breach(
            run_id=run_id,
            node_id=node.id,
            rule=rule,
            description=description,
            content_snippet=input_text[:200]
        )
        
        # 2. Emit HITL Required Event
        _emit_execution_event(run_id, "hitl_required", {
            "nodeId": node.id,
            "nodeName": node.data.get("label", "Intervention"),
            "action_description": description,
            "reasoning": f"Data contains restricted pattern: '{rule}'",
            "current_state_summary": f"Breach detected in node output. Waiting for manual override.",
            "options": [
                {"label": "Approve (Override)", "value": "approve", "description": "Proceed despite breach"},
                {"label": "Reject", "value": "reject", "description": "Stop workflow"},
                {"label": "Edit & Resume", "value": "edit", "description": "Modify content then proceed"}
            ]
        })
        
        # 3. Wait for HITL Response
        if run_id not in _hitl_responses:
            _hitl_responses[run_id] = asyncio.Queue()
            
        try:
            # Wait with a long timeout (1 hour)
            response = await asyncio.wait_for(_hitl_responses[run_id].get(), timeout=3600.0)
            
            decision = response.get("decision", "reject")
            if decision == "reject":
                return {"error": "Workflow rejected by human in the loop", "status": "rejected"}
            
            if decision == "edit":
                edits = response.get("edits", {})
                new_content = edits.get("modified_content", input_text)
                # Update context with edited content
                if "llm_output" in context:
                    context["llm_output"] = new_content
                else:
                    context["message"] = new_content
                return {"message": "Breach edited and approved", "status": "edited"}
                
            return {"message": "Breach overridden and approved", "status": "approved"}
            
        except asyncio.TimeoutError:
            return {"error": "HITL response timed out after 1 hour", "status": "timeout"}
            
    return {"message": "No breach detected", "status": "bypass"}


async def execute_a2a_node(node: StudioNode, context: Dict, workspace: str) -> Dict:
    """Execute an A2A delegation node — sends task to a remote agent."""
    from ..a2a.client import A2AClient, A2AClientError
    
    config = node.data.get("config") or {}
    agent_url = config.get("agentUrl", "")
    timeout = float(config.get("timeout", 300))
    
    if not agent_url:
        return {"error": "No agent URL configured", "response": None}
    
    message = context.get("message", "") or context.get("llm_output", "")
    
    try:
        client = A2AClient(api_key="benny-mesh-2026-auth", timeout=timeout)
        
        # Send task
        task = await client.send_task(agent_url, message, workspace)
        
        # Poll for completion
        final_task = await client.poll_until_complete(
            agent_url, task.id,
            max_wait=timeout
        )
        
        # Extract response
        response_text = ""
        for msg in final_task.messages:
            if msg.role == "agent":
                for part in msg.parts:
                    if part.type.value == "text":
                        response_text += part.content
        
        return {
            "response": response_text,
            "task_id": final_task.id,
            "status": final_task.status.value,
            "artifacts": [a.model_dump() for a in final_task.artifacts],
        }
    except A2AClientError as e:
        return {"error": str(e), "response": None}
    except Exception as e:
        return {"error": f"A2A execution failed: {str(e)}", "response": None}
