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
from ..governance.lineage import (
    track_workflow_start, 
    track_workflow_complete,
    get_lineage_client
)


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
    Planner node - decomposes request into tasks.
    Acts as a "bricoleur" by looking for existing skills first.
    """
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
        {{"task_id": "1", "description": "Task description", "skill_hint": "skill_name or null"}}
    ]
}}

Rules:
1. Each task should be independently executable
2. Tasks should be ordered logically
3. Reference skill_hint if an existing skill can help
4. Keep descriptions actionable and specific"""

    user_prompt = f"Decompose this request into tasks:\n\n{state['original_request']}"
    
    try:
        response = await acompletion(
            model=state.get("model", "ollama/llama3.2"),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=2000
        )
        
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
            for t in parsed.get("tasks", []):
                tasks.append(TaskItem(
                    task_id=str(t.get("task_id", str(uuid.uuid4())[:8])),
                    description=t.get("description", ""),
                    status="pending",
                    skill_hint=t.get("skill_hint")
                ))
            
            return {
                "plan": tasks,
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
# NODE: ORCHESTRATOR (Command Pattern)
# =============================================================================

def orchestrator_node(state: SwarmState) -> Command:
    """
    Orchestrator node - reviews plan and routes execution.
    Uses Command for atomic state update + navigation.
    """
    plan = state.get("plan", [])
    revision_count = state.get("revision_count", 0)
    
    # Validation checks
    if not plan:
        return Command(
            update={"status": "failed", "errors": ["No plan generated"]},
            goto=END
        )
    
    if len(plan) < 1:
        return Command(
            update={"status": "failed", "errors": ["Plan must have at least 1 task"]},
            goto=END
        )
    
    # Auto-approve if plan looks reasonable (< 10 tasks, < 3 revisions)
    if len(plan) <= 10 and revision_count < 3:
        return Command(
            update={"plan_approved": True, "status": "executing"},
            goto="dispatcher"
        )
    
    # Too many revisions, force proceed
    if revision_count >= 3:
        return Command(
            update={
                "plan_approved": True, 
                "status": "executing",
                "errors": ["Plan approved after max revisions"]
            },
            goto="dispatcher"
        )
    
    # Plan too large, request revision
    return Command(
        update={"errors": ["Plan has too many tasks, requesting simplification"]},
        goto="planner"
    )


# =============================================================================
# NODE: DISPATCHER (Fan-Out via Send)
# =============================================================================

def dispatcher_node(state: SwarmState) -> List[Send]:
    """
    Dispatcher node - fans out tasks to executor nodes.
    Uses Send API for dynamic parallel execution.
    """
    plan = state.get("plan", [])
    execution_id = state.get("execution_id", "")
    
    sends = []
    for task in plan:
        sends.append(Send(
            "executor",
            {
                "task": task,
                "execution_id": execution_id,
                "workspace": state.get("workspace", "default"),
                "model": state.get("model", "ollama/llama3.2")
            }
        ))
    
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
        
        # Build execution prompt
        if skill_content:
            system_prompt = f"""You are executing a task using a predefined skill.

SKILL INSTRUCTIONS:
{skill_content}

Execute the task following these skill guidelines. Be thorough and comprehensive."""
        else:
            system_prompt = """You are a focused task executor. Complete the given task thoroughly.
Write comprehensive, well-structured content. Be specific and detailed.
If the task requires research or data you don't have, clearly state assumptions."""

        user_prompt = f"Execute this task:\n\n{description}"
        
        response = await acompletion(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,
            max_tokens=3000
        )
        
        content = response.choices[0].message.content
        execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        return {
            "partial_results": [PartialResult(
                task_id=task_id,
                content=content,
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
# NODE: AGGREGATOR (Kludge Pattern)
# =============================================================================

def aggregator_node(state: SwarmState) -> Dict[str, Any]:
    """
    Aggregator node - combines all executor results.
    Implements Kludge pattern for graceful degradation.
    """
    partial_results = state.get("partial_results", [])
    plan = state.get("plan", [])
    execution_id = state.get("execution_id", "")
    workspace = state.get("workspace", "default")
    
    # Separate successes and failures
    successful = [r for r in partial_results if r.get("content")]
    failed = [r for r in partial_results if r.get("error")]
    
    # Build document sections
    sections = []
    
    # Sort by task_id for consistent ordering
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
    
    # Handle failures (Kludge pattern)
    status = "completed"
    if failed:
        if successful:
            status = "partial_success"
            document_parts.append("\n---\n")
            document_parts.append("## ⚠️ Incomplete Sections\n")
            document_parts.append(f"*{len(failed)} of {len(partial_results)} tasks failed*\n")
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
    artifact_filename = f"{execution_id}_swarm_output.md"
    data_in_path = get_workspace_path(workspace, "data_in")
    data_in_path.mkdir(parents=True, exist_ok=True)
    artifact_path = data_in_path / artifact_filename
    artifact_path.write_text(final_document, encoding="utf-8")
    
    # Generate governance URL
    governance_url = get_governance_url(execution_id)
    
    return {
        "final_document": final_document,
        "artifact_path": str(artifact_path),
        "governance_url": governance_url,
        "status": status
    }


# =============================================================================
# GRAPH BUILDER
# =============================================================================

def build_swarm_graph(checkpointer=None) -> StateGraph:
    """Build the Swarm workflow graph"""
    
    graph = StateGraph(SwarmState)
    
    # Add nodes
    graph.add_node("planner", planner_node)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("dispatcher", dispatcher_node)
    graph.add_node("executor", executor_node)
    graph.add_node("aggregator", aggregator_node)
    
    # Add edges
    graph.add_edge(START, "planner")
    graph.add_edge("planner", "orchestrator")
    # Orchestrator uses Command for routing (no explicit edges needed)
    graph.add_edge("dispatcher", "executor")
    graph.add_edge("executor", "aggregator")
    graph.add_edge("aggregator", END)
    
    # Compile with checkpointer
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
    max_concurrency: Optional[int] = None
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
        max_concurrency=concurrency
    )
    
    # Track workflow start
    try:
        track_workflow_start(execution_id, "swarm", workspace)
        print(f"[LINEAGE] Started tracking workflow {execution_id}")
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
        nodes_executed = ["planner", "orchestrator", "dispatcher", "executor", "aggregator"]
        track_workflow_complete(execution_id, "swarm", nodes_executed, execution_time_ms)
        print(f"[LINEAGE] Completed tracking workflow {execution_id} ({execution_time_ms}ms)")
    except Exception as e:
        print(f"[LINEAGE] Failed to track completion: {e}")
    
    return result
