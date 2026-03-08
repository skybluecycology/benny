"""
GraphState - Core state schema for all workflows
"""

from typing import TypedDict, Annotated, List, Optional, Any, Dict
from langchain_core.messages import BaseMessage
import operator


def add_messages(left: List[BaseMessage], right: List[BaseMessage]) -> List[BaseMessage]:
    """Reducer that appends new messages to existing list"""
    return left + right


def add_results(left: List[Dict], right: List[Dict]) -> List[Dict]:
    """Reducer that appends partial results from parallel executors"""
    return left + right


class GraphState(TypedDict):
    """
    Core state schema for all Benny workflows.
    
    Attributes:
        messages: Conversation history with reducer for appending
        context: Data references, configuration, runtime context
        artifacts: List of generated file paths
        errors: Error accumulator for debugging
        workspace_id: Active workspace for multi-tenant isolation
        trace_context: W3C traceparent for distributed tracing
        current_node: Currently executing node (for UI updates)
        execution_id: Unique ID for this workflow execution
    """
    messages: Annotated[List[BaseMessage], add_messages]
    context: dict
    artifacts: List[str]
    errors: List[str]
    workspace_id: str
    trace_context: dict
    current_node: Optional[str]
    execution_id: Optional[str]


# =============================================================================
# SWARM STATE - Extended state for parallel task execution
# =============================================================================

class TaskItem(TypedDict):
    """Individual task in the swarm plan"""
    task_id: str
    description: str
    status: str  # pending, running, completed, failed
    skill_hint: Optional[str]  # Suggested skill from benny/skills/


class PartialResult(TypedDict):
    """Result from a single executor"""
    task_id: str
    content: Optional[str]
    error: Optional[str]
    execution_time_ms: int


class SwarmState(TypedDict):
    """
    Extended state for Swarm Planner workflow.
    Supports parallel execution with reducer-based result merging.
    
    Design Principles:
    - Assemblage: State as persistent memory for time-travel debugging
    - Bricolage: Planner looks for existing skills before LLM generation
    - Kludge: Aggregator handles partial failures gracefully
    """
    # Core identifiers
    execution_id: str
    workspace: str
    
    # Messages and context
    messages: Annotated[List[BaseMessage], add_messages]
    original_request: str
    
    # Planning
    plan: Optional[List[TaskItem]]
    plan_approved: bool
    revision_count: int  # Track replanning cycles
    
    # Execution - uses reducer for parallel writes
    partial_results: Annotated[List[PartialResult], operator.add]
    
    # Output
    final_document: Optional[str]
    artifact_path: Optional[str]
    
    # Governance
    governance_url: Optional[str]
    
    # Error handling
    errors: Annotated[List[str], operator.add]
    status: str  # pending, planning, executing, aggregating, completed, partial_success, failed
    
    # Configuration
    model: str
    max_concurrency: int


def create_swarm_state(
    execution_id: str,
    workspace: str = "default",
    original_request: str = "",
    model: str = "ollama/llama3.2",
    max_concurrency: int = 1
) -> SwarmState:
    """Create initial state for a new swarm workflow execution"""
    return SwarmState(
        execution_id=execution_id,
        workspace=workspace,
        messages=[],
        original_request=original_request,
        plan=None,
        plan_approved=False,
        revision_count=0,
        partial_results=[],
        final_document=None,
        artifact_path=None,
        governance_url=None,
        errors=[],
        status="pending",
        model=model,
        max_concurrency=max_concurrency
    )


def create_initial_state(
    workspace_id: str = "default",
    context: Optional[dict] = None,
    trace_context: Optional[dict] = None
) -> GraphState:
    """Create initial state for a new workflow execution"""
    return GraphState(
        messages=[],
        context=context or {},
        artifacts=[],
        errors=[],
        workspace_id=workspace_id,
        trace_context=trace_context or {},
        current_node=None,
        execution_id=None
    )

