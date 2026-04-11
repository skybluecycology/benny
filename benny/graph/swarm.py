"""
Benny Swarm Graph - LangGraph implementation for parallel task orchestration

Architecture:
- Planner: Bricoleur that decomposes requests, looks for existing skills
- Orchestrator: Reviews plan, uses Command for atomic state+navigation
- Dispatcher: Fan-out via Send API with semaphore-controlled concurrency
- Executor: Code Execution pattern with skill lookup
- Aggregator: Kludge-style graceful degradation for partial failures
"""

from __future__ import annotations

import logging

import os
import json
import asyncio
import uuid
from datetime import datetime
from typing import Literal, Optional, List, Dict, Any
from pathlib import Path

from langgraph.graph import StateGraph, START, END
from langgraph.types import Send, Command
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from litellm import completion, acompletion

logger = logging.getLogger(__name__)

from ..core.state import SwarmState, TaskItem, PartialResult, create_swarm_state
from ..core.workspace import get_workspace_path
from ..core.models import MODEL_REGISTRY, get_model_config
from ..governance.lineage import (
    track_workflow_start, 
    track_workflow_complete,
    get_lineage_client
)
from .wave_scheduler import (
    compute_waves,
    detect_conflicts,
    resolve_conflicts,
    generate_ascii_dag,
    assign_models,
    CircularDependencyError,
)
from ..governance.permission_manifest import create_ephemeral_manifest, register_manifest
from ..core.skill_registry import registry


# =============================================================================
# CONFIGURATION
# =============================================================================

MAX_CONCURRENCY = int(os.getenv("SWARM_MAX_CONCURRENCY", "1"))
SKILLS_DIR = Path(__file__).parent.parent / "skills"
MARQUEZ_WEB_URL = os.getenv("MARQUEZ_WEB_URL", "http://localhost:3001")


def get_governance_url(execution_id: str, workflow_name: str = "swarm") -> str:
    """Generate direct link to Marquez lineage visualization"""
    return f"{MARQUEZ_WEB_URL}/lineage/benny/workflow.{workflow_name}/{execution_id}"


# =============================================================================
# SKILL DISCOVERY (Bricolage Pattern)
# =============================================================================

def discover_skills() -> Dict[str, Dict[str, Any]]:
    """
    Discover available skills from benny/skills/ directory.
    Returns dict of skill_name -> {description, priority}.
    Skills with 'priority: high' in front-matter are ranked first.
    """
    skills = {}
    if SKILLS_DIR.exists():
        for skill_file in SKILLS_DIR.glob("*.md"):
            if skill_file.name.startswith("_"):
                continue
            try:
                content = skill_file.read_text(encoding="utf-8")
                # Extract first line as description
                first_line = content.split("\n")[0].strip("# ")
                # Extract priority from front-matter if present
                priority = "normal"
                if content.startswith("---"):
                    fm_end = content.find("---", 3)
                    if fm_end != -1:
                        fm = content[3:fm_end]
                        if "priority: high" in fm:
                            priority = "high"
                        elif "priority: low" in fm:
                            priority = "low"
                skills[skill_file.stem] = {
                    "description": first_line,
                    "priority": priority 
                }
            except Exception:
                skills[skill_file.stem] = {"description": "Skill available", "priority": "normal"}
    return skills


def get_skill_content(skill_name: str) -> Optional[str]:
    """Load skill content for execution"""
    skill_path = SKILLS_DIR / f"{skill_name}.md"
    if skill_path.exists():
        return skill_path.read_text(encoding="utf-8")
    return None


# =============================================================================
# NODE: PLANNER (Bricoleur)
# =============================================================================

async def planner_node(state: SwarmState) -> Dict[str, Any]:
    """
    Planner node - decomposes request into tasks with dependencies.
    Acts as a "bricoleur" by looking for existing skills first.
    """
    expansion_signals = state.get("expansion_signals", [])
    if expansion_signals:
        tasks = list(state.get("plan", []) or [])
        dependency_graph = dict(state.get("dependency_graph", {}))
        
        for sig in expansion_signals:
            # Simple expansion: 1 signal = 1 sub-task
            # Depth check is already done in monitor, but let's be safe
            if sig["depth"] >= 2:
                continue
                
            new_id = f"{sig['parent_id']}.{len([t for t in tasks if t.get('parent_id') == sig['parent_id']]) + 1}"
            new_task = TaskItem(
                task_id=new_id,
                description=sig["description"],
                status="pending",
                skill_hint=None,
                assigned_skills=[],
                parent_id=sig["parent_id"],
                depth=sig["depth"] + 1,
                wave=0,
                dependencies=[sig["parent_id"]],
                files_touched=[],
                complexity="medium",
                assigned_model=None,
                estimated_tokens=None
            )
            tasks.append(new_task)
            dependency_graph[new_id] = [sig["parent_id"]]
            
        return {
            "plan": tasks,
            "active_task_pool": tasks,
            "dependency_graph": dependency_graph,
            "expansion_signals": [], # Clear signals
            "status": "planning"
        }

    available_skills = discover_skills()
    # Sort by priority (high first)
    priority_order = {"high": 0, "normal": 1, "low": 2}
    sorted_skills = sorted(available_skills.items(), key=lambda x: priority_order.get(x[1].get("priority", "normal"), 1))
    skills_list = "\n".join([f"- {name}: {info['description']} [priority: {info['priority']}]" for name, info in sorted_skills])
    
    system_prompt = f"""You are a task decomposition expert. Break down the user's request into 3-7 discrete, executable tasks.

AVAILABLE SKILLS (prefer these over custom generation):
{skills_list if skills_list else "No pre-built skills available."}

OUTPUT FORMAT (JSON only, no markdown):
{{
    "tasks": [
        {{
            "task_id": "1", 
            "description": "Task description", 
            "skill_hint": "skill_name or null",
            "dependencies": [],
            "files_touched": ["output.md"],
            "complexity": "high|medium|low"
        }}
    ]
}}

Rules:
1. Each task MUST have a unique task_id (use simple strings: "1", "2", "3")
2. dependencies is a list of task_ids that MUST complete before this task starts
3. tasks with no dependencies should have an empty list []
4. files_touched lists any files this task will create or modify
5. complexity helps assign the right model: "high" for analysis, "medium" for writing, "low" for lookups
6. Keep descriptions actionable and specific"""

    user_prompt = f"Decompose this request into tasks:\n\n{state['original_request']}"
    
    try:
        # Resolve model configuration
        # If no model is provided in state, use the active model from the workspace's manager
        workspace_id = state.get("workspace", "default")
        model_id = state.get("model")
        
        if not model_id:
            try:
                model_id = await get_active_model(workspace_id)
                logger.info("Planner using auto-detected model: %s", model_id)
            except Exception as e:
                logger.warning("Could not auto-detect model, falling back to ollama: %s", e)
                model_id = "ollama/llama3.2"
        
        model_cfg = get_model_config(model_id)
        
        payload = {
            "model": model_cfg["model"],
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3,
            "max_tokens": 2000
        }
        
        if "base_url" in model_cfg:
            payload["api_base"] = model_cfg["base_url"]
        if "api_key" in model_cfg:
            payload["api_key"] = model_cfg["api_key"]
            
        response = await acompletion(**payload)
        
        response_text = response.choices[0].message.content
        
        # Parse JSON from response
        try:
            # Handle potential markdown code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]
            
            parsed = json.loads(response_text.strip())
            tasks = []
            dependency_graph = {}
            for t in parsed.get("tasks", []):
                tid = str(t.get("task_id", str(uuid.uuid4())[:8]))
                deps = t.get("dependencies", [])
                tasks.append(TaskItem(
                    task_id=tid,
                    description=t.get("description", ""),
                    status="pending",
                    skill_hint=t.get("skill_hint"),
                    assigned_skills=t.get("assigned_skills", []),
                    parent_id=None,
                    depth=0,
                    wave=0,
                    dependencies=deps,
                    files_touched=t.get("files_touched", []),
                    complexity=t.get("complexity", "medium"),
                    assigned_model=None,
                    estimated_tokens=None
                ))
                dependency_graph[tid] = deps
            
            return {
                "plan": tasks,
                "active_task_pool": tasks,
                "dependency_graph": dependency_graph,
                "status": "planning",
                "revision_count": state.get("revision_count", 0) + 1
            }
        except json.JSONDecodeError:
            return {
                "errors": [f"Failed to parse planner response: {response_text[:200]}"],
                "status": "failed"
            }
            
    except Exception as e:
        logger.error("Planner LLM error: %s", e)
        return {
            "errors": [f"Planner LLM error: {str(e)}"],
            "status": "failed"
        }


# =============================================================================
# NODE: WAVE SCHEDULER
# =============================================================================

def wave_scheduler_node(state: SwarmState) -> Dict[str, Any]:
    """
    Compute execution waves from the dependency graph.
    Validates no circular dependencies and resolves file conflicts.
    """
    plan = state.get("plan", [])
    dependency_graph = state.get("dependency_graph", {})
    
    if not plan:
        return {"status": "failed", "errors": ["No plan to schedule"]}
    
    try:
        # Step 1: Compute waves from dependencies
        waves = compute_waves(plan, dependency_graph)
        
        # Step 2: Check for file conflicts within each wave
        file_assignments = {
            t["task_id"]: t.get("files_touched", []) for t in plan
        }
        waves = resolve_conflicts(waves, file_assignments)
        
        # Step 3: Update task wave assignments
        task_wave_map = {}
        for wave_idx, wave in enumerate(waves):
            for task_id in wave:
                task_wave_map[task_id] = wave_idx
        
        updated_plan = []
        for task in plan:
            task_copy = dict(task)
            task_copy["wave"] = task_wave_map.get(task["task_id"], 0)
            updated_plan.append(task_copy)
        
        # Step 4: Generate ASCII DAG
        ascii_dag = generate_ascii_dag(updated_plan, dependency_graph, waves)
        
        # Step 5: Assign models based on task complexity and keywords
        model_assignments = assign_models(updated_plan, MODEL_REGISTRY)
        for task in updated_plan:
            if task["task_id"] in model_assignments:
                task["assigned_model"] = model_assignments[task["task_id"]]
        
        return {
            "plan": updated_plan,
            "waves": waves,
            "current_wave": 0,
            "ascii_dag": ascii_dag,
            "status": "scheduled",
        }
    
    except CircularDependencyError as e:
        return {
            "status": "failed",
            "errors": [f"Circular dependency: {str(e)}"],
        }


# =============================================================================
# NODE: ORCHESTRATOR (Command Pattern)
# =============================================================================

def orchestrator_node(state: SwarmState) -> Command:
    """Reviews plan and wave schedule, then routes to dispatcher."""
    plan = state.get("plan", [])
    waves = state.get("waves", [])
    revision_count = state.get("revision_count", 0)
    
    if not plan:
        return Command(update={"status": "failed", "errors": ["No plan generated"]}, goto=END)
    
    if not waves:
        return Command(update={"status": "failed", "errors": ["No waves computed"]}, goto=END)
    
    if len(plan) <= 10 and revision_count < 3:
        return Command(
            update={"plan_approved": True, "status": "executing"},
            goto="dispatcher"
        )
    
    if revision_count >= 3:
        return Command(
            update={"plan_approved": True, "status": "executing", "errors": ["Plan approved after max revisions"]},
            goto="dispatcher"
        )
    
    return Command(
        update={"errors": ["Plan has too many tasks, requesting simplification"]},
        goto="planner"
    )


# =============================================================================
# NODE: DISPATCHER (Fan-Out via Send)
# =============================================================================

def dispatcher_node(state: SwarmState) -> Dict[str, Any]:
    """ Entry point for the current wave's execution. """
    return {"status": "executing"}


def dispatch_tasks(state: SwarmState) -> List[Send]:
    """
    Dynamic router for fan-out tasks.
    Used in conditional edges to spin up parallel executors.
    """
    waves = state.get("waves", [])
    current_wave = state.get("current_wave", 0)
    plan = state.get("plan", [])
    execution_id = state.get("execution_id", "")
    
    if current_wave >= len(waves):
        return []  # Should not happen as context_handover guards this
    
    current_wave_task_ids = set(waves[current_wave])
    wave_tasks = [t for t in plan if t["task_id"] in current_wave_task_ids]
    
    sends = []
    for task in wave_tasks:
        sends.append(Send("executor", {
            "task": task,
            "execution_id": execution_id,
            "workspace": state.get("workspace", "default"),
            "model": task.get("assigned_model") or state.get("model", "ollama/llama3.2"),
            "context_handover": state.get("context_handover", {}),
        }))
    
    return sends


# =============================================================================
# NODE: EXECUTOR (Code Execution Pattern)
# =============================================================================

async def executor_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Executor node - executes a single task.
    Implements Code Execution pattern: generates executable approach.
    """
    task: TaskItem = state.get("task", {})
    task_id = task.get("task_id", "unknown")
    description = task.get("description", "")
    skill_hint = task.get("skill_hint")
    model = state.get("model", "ollama/llama3.2")
    
    start_time = datetime.now()
    
    try:
        # Check for skill to use
        skill_content = None
        if skill_hint:
            skill_content = get_skill_content(skill_hint)

        # NEW: Least Skills Security
        assigned_skills = task.get("assigned_skills", [])
        manifest = create_ephemeral_manifest(task_id, assigned_skills)
        register_manifest(manifest)
        
        # Build tool schemas for LLM
        tools = None
        if assigned_skills:
            # We map assigned_skills (Markdown skill stems) to tools
            # In Phase 7.2, we assume skill IDs match the stems
            tool_schemas = registry.get_tool_schemas(assigned_skills, state.get("workspace", "default"))
            if tool_schemas:
                tools = tool_schemas

        # Build execution prompt
        if skill_content:
            system_prompt = f"""You are executing a task using a predefined skill.

SKILL INSTRUCTIONS:
{skill_content}

Execute the task following these skill guidelines. Be thorough and comprehensive."""
        else:
            system_prompt = """You are a focused task executor. Complete the given task thoroughly.
Write comprehensive, well-structured content. Be specific and detailed.
If the task requires research or data you don't have, clearly state assumptions.

DYNAMIC EXPANSION:
If you identify a complex sub-pillar that requires dedicated research or separate execution, 
you can request a sub-swarm by including [[EXPAND: description of sub-task]] in your output.
Do this sparingly and only for significant knowledge gaps."""

        # Add context handover from previous waves
        context_handover = state.get("context_handover", {})
        if context_handover:
            handover_summary = "\n".join([f"- {k}: {v}" for k, v in context_handover.items()])
            system_prompt += f"\n\nCONTEXT FROM PREVIOUS WAVES:\n{handover_summary}"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Execute this task:\n\n{description}"}
        ]
        
        # Tool-calling loop
        max_steps = 5
        current_step = 0
        executed_tools = []
        final_content = ""

        while current_step < max_steps:
            current_step += 1
            
            # Resolve model configuration
            workspace_id = state.get("workspace", "default")
            model_id = state.get("model")
            
            if not model_id:
                try:
                    model_id = await get_active_model(workspace_id)
                except Exception:
                    model_id = "ollama/llama3.2"
                    
            model_cfg = get_model_config(model_id)
            
            payload = {
                "model": model_cfg["model"],
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 3000
            }
            
            if "base_url" in model_cfg:
                payload["api_base"] = model_cfg["base_url"]
            if "api_key" in model_cfg:
                payload["api_key"] = model_cfg["api_key"]
                
            if tools:
                payload["tools"] = tools

            response = await acompletion(**payload)
            message = response.choices[0].message
            messages.append(message)

            if "tool_calls" in message and message["tool_calls"]:
                for tc in message["tool_calls"]:
                    func_name = tc["function"]["name"]
                    call_id = tc["id"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                    except:
                        args = {}
                    
                    # Execute skill with Least Skill agent_id
                    result_str = registry.execute_skill(
                        func_name, 
                        state.get("workspace", "default"),
                        agent_id=f"task_{task_id}",
                        **args
                    )
                    executed_tools.append({"name": func_name, "args": args})
                    
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call_id,
                        "name": func_name,
                        "content": result_str
                    })
                continue
            else:
                final_content = message.get("content", "")
                break

        execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        return {
            "partial_results": [PartialResult(
                task_id=task_id,
                content=final_content,
                error=None,
                execution_time_ms=execution_time
            )]
        }
        
    except Exception as e:
        execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
        return {
            "partial_results": [PartialResult(
                task_id=task_id,
                content=None,
                error=str(e),
                execution_time_ms=execution_time
            )]
        }


# =============================================================================
# NODE: EXPANSION MONITOR
# =============================================================================

async def expansion_monitor_node(state: SwarmState) -> Dict[str, Any]:
    """Inspects executor results for [[EXPAND]] signals."""
    expansion_signals = []
    results = state.get("partial_results", [])
    plan = state.get("plan", []) or []
    
    import re
    # Match [[EXPAND: description]]
    expand_pattern = re.compile(r"\[\[EXPAND:(.*?)\]\]", re.DOTALL)
    
    for result in results:
        content = result.get("content", "")
        if not content:
            continue
            
        matches = expand_pattern.findall(content)
        if matches:
            parent_task = next((t for t in plan if t["task_id"] == result["task_id"]), None)
            if parent_task:
                current_depth = parent_task.get("depth", 0)
                if current_depth < 2:
                    for desc in matches:
                        expansion_signals.append({
                            "parent_id": result["task_id"],
                            "description": desc.strip(),
                            "depth": current_depth
                        })
                else:
                    logger.warning(f"Task {result['task_id']} reached recursion limit (depth {current_depth})")
                
    return {"expansion_signals": expansion_signals}


# =============================================================================
# NODE: AGGREGATOR (Kludge Pattern)
# =============================================================================

def aggregator_node(state: SwarmState) -> Dict[str, Any]:
    """
    Aggregator node - combines all executor results into final document.
    """
    wave_results = state.get("wave_results", {})
    plan = state.get("plan", [])
    execution_id = state.get("execution_id", "")
    workspace = state.get("workspace", "default")
    
    # Flatten all results from all waves
    all_results = []
    for wave_idx_str in wave_results:
        all_results.extend(wave_results[wave_idx_str])
    
    # Separate successes and failures
    successful = [r for r in all_results if r.get("content")]
    failed = [r for r in all_results if r.get("error")]
    
    # Build document sections
    sections = []
    
    # Sort by original plan order
    task_order = {t["task_id"]: i for i, t in enumerate(plan)} if plan else {}
    successful.sort(key=lambda r: task_order.get(r["task_id"], 999))
    
    for result in successful:
        task = next((t for t in plan if t["task_id"] == result["task_id"]), None)
        task_desc = task["description"] if task else f"Task {result['task_id']}"
        sections.append(f"## {task_desc}\n\n{result['content']}")
    
    # Build final document
    document_parts = [
        f"# Generated Document",
        f"*Execution ID: {execution_id}*",
        f"*Generated at: {datetime.now().isoformat()}*",
        "",
        "---",
        ""
    ]
    document_parts.extend(sections)
    
    # Handle failures (graceful degradation)
    status = "completed"
    if failed:
        if successful:
            status = "partial_success"
            document_parts.append("\n---\n")
            document_parts.append("## ⚠️ Incomplete Sections\n")
            document_parts.append(f"*{len(failed)} of {len(all_results)} tasks failed*\n")
            for result in failed:
                task = next((t for t in plan if t["task_id"] == result["task_id"]), None)
                task_desc = task["description"] if task else f"Task {result['task_id']}"
                document_parts.append(f"- **{task_desc}**: {result['error']}")
        else:
            status = "failed"
            return {
                "status": "failed",
                "errors": [f"All {len(failed)} tasks failed"],
                "final_document": None
            }
    
    final_document = "\n".join(document_parts)
    
    # Save artifact
    # Use output filename from config if defined, or default to execution_id
    output_files_cfg = state.get("output_files", [])
    if output_files_cfg:
        artifact_filename = output_files_cfg[0] # Take first defined output
    else:
        artifact_filename = f"{execution_id}_swarm_output.md"

    data_in_path = get_workspace_path(workspace, "data_in")
    data_in_path.mkdir(parents=True, exist_ok=True)
    artifact_path = data_in_path / artifact_filename
    artifact_path.write_text(final_document, encoding="utf-8")
    
    # Record output in state
    if artifact_filename not in output_files_cfg:
        output_files_cfg.append(artifact_filename)
    
    # Generate governance URL
    governance_url = get_governance_url(execution_id)
    
    return {
        "final_document": final_document,
        "artifact_path": str(artifact_path),
        "output_files": output_files_cfg,
        "governance_url": governance_url,
        "status": status
    }


# =============================================================================
# NODE: CONTEXT HANDOVER
# =============================================================================

async def context_handover_node(state: SwarmState) -> Dict[str, Any]:
    """
    After a wave completes, summarize the delta state for the next wave.
    Trims full outputs to maintain context window budget.
    """
    partial_results = state.get("partial_results", [])
    current_waveIdx = state.get("current_wave", 0)
    waves = state.get("waves", [])
    plan = state.get("plan", [])
    limit = state.get("handover_summary_limit", 500)
    
    # Collect results from the current wave
    current_wave_task_ids = set(waves[current_waveIdx]) if current_waveIdx < len(waves) else set()
    wave_results_list = [r for r in partial_results if r.get("task_id") in current_wave_task_ids]
    
    # Build handover summary
    handover = dict(state.get("context_handover", {}))
    for result in wave_results_list:
        if result.get("content"):
            # Trim to prevent context bloat
            summary = result["content"][:limit]
            if len(result["content"]) > limit:
                summary += "... [truncated]"
            handover[f"task_{result['task_id']}"] = summary
    
    # Store wave results
    wave_results_map = dict(state.get("wave_results", {}))
    wave_results_map[str(current_waveIdx)] = wave_results_list
    
    # Advance to next wave
    next_wave = current_waveIdx + 1
    has_more_waves = next_wave < len(waves)
    
    # Reset partial_results for next wave dispatch
    return {
        "context_handover": handover,
        "wave_results": wave_results_map,
        "current_wave": next_wave,
        "partial_results": [], # Clear for next wave
        "status": "executing" if has_more_waves else "aggregating",
    }


# =============================================================================
# NODE: REVIEW
# =============================================================================

async def review_node(state: SwarmState) -> Dict[str, Any]:
    """
    Post-execution review pass.
    Validates execution quality and identifies gaps.
    """
    wave_results = state.get("wave_results", {})
    plan = state.get("plan", [])
    
    all_results = []
    for wr in wave_results.values():
        all_results.extend(wr)
        
    review_findings = []
    
    # Check 1: All tasks have results
    result_task_ids = {r["task_id"] for r in all_results}
    plan_task_ids = {t["task_id"] for t in plan}
    missing = plan_task_ids - result_task_ids
    if missing:
        review_findings.append({
            "type": "missing_results",
            "severity": "high",
            "message": f"Tasks without results: {', '.join(missing)}",
        })
    
    # Check 2: Error rate
    errors = [r for r in all_results if r.get("error")]
    if all_results:
        error_rate = len(errors) / len(all_results)
        if error_rate > 0:
            review_findings.append({
                "type": "error_rate",
                "severity": "high" if error_rate > 0.5 else "medium",
                "message": f"{len(errors)}/{len(all_results)} tasks failed ({error_rate:.0%} error rate)",
            })
    
    # Check 3: Dependency satisfaction
    dependency_graph = state.get("dependency_graph", {})
    for task in plan:
        deps = dependency_graph.get(task["task_id"], [])
        for dep in deps:
            dep_result = next((r for r in all_results if r["task_id"] == dep), None)
            if dep_result and dep_result.get("error"):
                review_findings.append({
                    "type": "broken_dependency",
                    "severity": "high",
                    "message": f"Task '{task['task_id']}' depends on failed task '{dep}'",
                })
    
    return {
        "review_pass_results": review_findings,
    }


# =============================================================================
# GRAPH BUILDER
# =============================================================================

def build_swarm_graph(checkpointer=None) -> StateGraph:
    """Build the wave-based Swarm workflow graph."""
    
    graph = StateGraph(SwarmState)
    
    # Add nodes
    graph.add_node("planner", planner_node)
    graph.add_node("wave_scheduler", wave_scheduler_node)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("dispatcher", dispatcher_node)
    graph.add_node("executor", executor_node)
    graph.add_node("context_handover", context_handover_node)
    graph.add_node("expansion_monitor", expansion_monitor_node)
    graph.add_node("review", review_node)
    graph.add_node("aggregator", aggregator_node)
    
    # Flow: START → planner → wave_scheduler → orchestrator
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "wave_scheduler")
    graph.add_edge("wave_scheduler", "orchestrator")
    
    # orchestrator routes to dispatcher or planner via Command
    # dispatcher (dynamic fan-out) → executor (parallel tasks) → expansion_monitor (join)
    graph.add_conditional_edges("dispatcher", dispatch_tasks, ["executor"])
    graph.add_edge("executor", "expansion_monitor")
    graph.add_edge("expansion_monitor", "context_handover")
    
    # context_handover decides: more waves → dispatcher, OR done → review
    def after_wave(state: SwarmState) -> str:
        current_waveIdx = state.get("current_wave", 0)
        waves = state.get("waves", [])
        expansion_signals = state.get("expansion_signals", [])
        
        if expansion_signals:
            return "planner"
            
        if current_waveIdx < len(waves):
            return "dispatcher"
        return "review"
    
    graph.add_conditional_edges("context_handover", after_wave, {
        "planner": "planner",
        "dispatcher": "dispatcher",
        "review": "review",
    })
    
    graph.add_edge("review", "aggregator")
    graph.add_edge("aggregator", END)
    
    if checkpointer:
        return graph.compile(checkpointer=checkpointer)
    return graph.compile()


# =============================================================================
# EXECUTION HELPER
# =============================================================================

async def run_swarm_workflow(
    request: str,
    workspace: str = "default",
    model: str = "ollama/llama3.2",
    execution_id: Optional[str] = None,
    max_concurrency: Optional[int] = None,
    input_files: Optional[List[str]] = None,
    output_files: Optional[List[str]] = None,
    config: Optional[Dict[str, Any]] = None
) -> SwarmState:
    """
    Execute the swarm workflow with the given request.
    
    Args:
        request: The user's request to decompose and execute
        workspace: Workspace for file operations
        model: LLM model to use
        execution_id: Optional execution ID (auto-generated if not provided)
        max_concurrency: Override for SWARM_MAX_CONCURRENCY
    
    Returns:
        Final SwarmState with results
    """
    if execution_id is None:
        execution_id = str(uuid.uuid4())
    
    concurrency = max_concurrency or MAX_CONCURRENCY
    
    # Create checkpointer for state persistence
    checkpointer = MemorySaver()
    graph = build_swarm_graph(checkpointer)
    
    # Create initial state
    initial_state = create_swarm_state(
        execution_id=execution_id,
        workspace=workspace,
        original_request=request,
        model=model,
        max_concurrency=concurrency,
        input_files=input_files,
        output_files=output_files,
        config=config
    )
    
    # Track workflow start with declared inputs
    try:
        inputs = [f"data_in/{f}" for f in (input_files or [])]
        track_workflow_start(execution_id, "swarm", workspace, inputs=inputs)
        print(f"[LINEAGE] Started tracking workflow {execution_id} with inputs: {inputs}")
    except Exception as e:
        print(f"[LINEAGE] Failed to track start: {e}")
    
    # Execute graph with concurrency control
    thread_config = {
        "configurable": {"thread_id": execution_id},
        "max_concurrency": concurrency
    }
    
    start_time = datetime.now()
    result = await graph.ainvoke(initial_state, thread_config)
    execution_time_ms = int((datetime.now() - start_time).total_seconds() * 1000)
    
    # Track workflow completion
    try:
        nodes_executed = ["planner", "wave_scheduler", "orchestrator", "dispatcher", "executor", "expansion_monitor", "context_handover", "review", "aggregator"]
        outputs = [f"data_in/{os.path.basename(result.get('artifact_path', ''))}" if result.get('artifact_path') else f"swarm_output_{execution_id}.md"]
        track_workflow_complete(execution_id, "swarm", nodes_executed, execution_time_ms, outputs=outputs)
        print(f"[LINEAGE] Completed tracking workflow {execution_id} ({execution_time_ms}ms) with outputs: {outputs}")
    except Exception as e:
        print(f"[LINEAGE] Failed to track completion: {e}")
    
    return result
