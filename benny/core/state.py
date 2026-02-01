"""
GraphState - Core state schema for all workflows
"""

from typing import TypedDict, Annotated, List, Optional, Any
from langchain_core.messages import BaseMessage


def add_messages(left: List[BaseMessage], right: List[BaseMessage]) -> List[BaseMessage]:
    """Reducer that appends new messages to existing list"""
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
