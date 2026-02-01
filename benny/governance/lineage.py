"""
Benny Governance - OpenLineage integration for data lineage tracking
Emits lineage events to Marquez for full auditability
"""

import os
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
import json
import httpx

from openlineage.client import OpenLineageClient
from openlineage.client.run import Run, RunEvent, RunState, Job
from openlineage.client.facet import (
    BaseFacet,
    SqlJobFacet,
    DocumentationJobFacet,
    SourceCodeLocationJobFacet,
)


# =============================================================================
# CONFIGURATION
# =============================================================================

MARQUEZ_URL = os.getenv("MARQUEZ_URL", "http://localhost:5000")
NAMESPACE = os.getenv("LINEAGE_NAMESPACE", "benny")


# =============================================================================
# CUSTOM FACETS
# =============================================================================

@dataclass
class LLMCallFacet(BaseFacet):
    """Custom facet for LLM call metadata"""
    model: str
    provider: str
    temperature: float
    max_tokens: int
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    
    _additional_skip_redact: List[str] = field(default_factory=lambda: ["model", "provider"])


@dataclass  
class WorkflowExecutionFacet(BaseFacet):
    """Custom facet for workflow execution metadata"""
    workflow_id: str
    workspace: str
    nodes_executed: List[str]
    execution_time_ms: int
    status: str


@dataclass
class ToolExecutionFacet(BaseFacet):
    """Custom facet for tool execution metadata"""
    tool_name: str
    tool_args: Dict[str, Any]
    success: bool
    error_message: Optional[str] = None


# =============================================================================
# LINEAGE CLIENT
# =============================================================================

class BennyLineageClient:
    """
    OpenLineage client wrapper for Benny platform.
    Tracks workflow executions, LLM calls, and tool invocations.
    """
    
    def __init__(self, marquez_url: str = MARQUEZ_URL, namespace: str = NAMESPACE):
        self.namespace = namespace
        self.marquez_url = marquez_url
        self._client: Optional[OpenLineageClient] = None
        self._runs: Dict[str, Run] = {}
    
    @property
    def client(self) -> OpenLineageClient:
        """Lazy-initialize OpenLineage client"""
        if self._client is None:
            self._client = OpenLineageClient(url=f"{self.marquez_url}/api/v1/lineage")
        return self._client
    
    def _create_run(self, run_id: Optional[str] = None) -> Run:
        """Create a new run with generated or provided ID"""
        return Run(runId=run_id or str(uuid.uuid4()))
    
    def _create_job(self, job_name: str, facets: Optional[Dict[str, BaseFacet]] = None) -> Job:
        """Create a job with the given name and facets"""
        return Job(
            namespace=self.namespace,
            name=job_name,
            facets=facets or {}
        )
    
    # -------------------------------------------------------------------------
    # Workflow Events
    # -------------------------------------------------------------------------
    
    def start_workflow(
        self,
        workflow_id: str,
        workflow_name: str,
        workspace: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Emit START event for workflow execution"""
        run = self._create_run(workflow_id)
        self._runs[workflow_id] = run
        
        job = self._create_job(
            job_name=f"workflow.{workflow_name}",
            facets={
                "documentation": DocumentationJobFacet(
                    description=f"Benny workflow: {workflow_name} in workspace {workspace}"
                )
            }
        )
        
        event = RunEvent(
            eventType=RunState.START,
            eventTime=datetime.now(timezone.utc).isoformat(),
            run=run,
            job=job,
            inputs=[],
            outputs=[]
        )
        
        self.client.emit(event)
        return workflow_id
    
    def complete_workflow(
        self,
        workflow_id: str,
        workflow_name: str,
        nodes_executed: List[str],
        execution_time_ms: int,
        outputs: Optional[List[Dict]] = None
    ) -> None:
        """Emit COMPLETE event for workflow execution"""
        run = self._runs.get(workflow_id, self._create_run(workflow_id))
        
        job = self._create_job(
            job_name=f"workflow.{workflow_name}",
            facets={
                "workflow_execution": WorkflowExecutionFacet(
                    workflow_id=workflow_id,
                    workspace="default",
                    nodes_executed=nodes_executed,
                    execution_time_ms=execution_time_ms,
                    status="completed"
                )
            }
        )
        
        event = RunEvent(
            eventType=RunState.COMPLETE,
            eventTime=datetime.now(timezone.utc).isoformat(),
            run=run,
            job=job,
            inputs=[],
            outputs=outputs or []
        )
        
        self.client.emit(event)
        self._runs.pop(workflow_id, None)
    
    def fail_workflow(
        self,
        workflow_id: str,
        workflow_name: str,
        error_message: str
    ) -> None:
        """Emit FAIL event for workflow execution"""
        run = self._runs.get(workflow_id, self._create_run(workflow_id))
        
        job = self._create_job(job_name=f"workflow.{workflow_name}")
        
        event = RunEvent(
            eventType=RunState.FAIL,
            eventTime=datetime.now(timezone.utc).isoformat(),
            run=run,
            job=job,
            inputs=[],
            outputs=[]
        )
        
        self.client.emit(event)
        self._runs.pop(workflow_id, None)
    
    # -------------------------------------------------------------------------
    # LLM Call Events
    # -------------------------------------------------------------------------
    
    def emit_llm_call(
        self,
        parent_run_id: str,
        model: str,
        provider: str,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        usage: Optional[Dict[str, int]] = None
    ) -> str:
        """Emit event for LLM API call"""
        run = self._create_run()
        
        job = self._create_job(
            job_name=f"llm.{provider}.{model.replace('/', '_')}",
            facets={
                "llm_call": LLMCallFacet(
                    model=model,
                    provider=provider,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    prompt_tokens=usage.get("prompt_tokens") if usage else None,
                    completion_tokens=usage.get("completion_tokens") if usage else None,
                    total_tokens=usage.get("total_tokens") if usage else None
                )
            }
        )
        
        event = RunEvent(
            eventType=RunState.COMPLETE,
            eventTime=datetime.now(timezone.utc).isoformat(),
            run=run,
            job=job,
            inputs=[],
            outputs=[]
        )
        
        self.client.emit(event)
        return run.runId
    
    # -------------------------------------------------------------------------
    # Tool Execution Events
    # -------------------------------------------------------------------------
    
    def emit_tool_execution(
        self,
        parent_run_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        success: bool,
        error_message: Optional[str] = None
    ) -> str:
        """Emit event for tool execution"""
        run = self._create_run()
        
        job = self._create_job(
            job_name=f"tool.{tool_name}",
            facets={
                "tool_execution": ToolExecutionFacet(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    success=success,
                    error_message=error_message
                )
            }
        )
        
        event = RunEvent(
            eventType=RunState.COMPLETE if success else RunState.FAIL,
            eventTime=datetime.now(timezone.utc).isoformat(),
            run=run,
            job=job,
            inputs=[],
            outputs=[]
        )
        
        self.client.emit(event)
        return run.runId


# =============================================================================
# GLOBAL CLIENT INSTANCE
# =============================================================================

_lineage_client: Optional[BennyLineageClient] = None


def get_lineage_client() -> BennyLineageClient:
    """Get or create the global lineage client"""
    global _lineage_client
    if _lineage_client is None:
        _lineage_client = BennyLineageClient()
    return _lineage_client


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def track_workflow_start(workflow_id: str, workflow_name: str, workspace: str) -> str:
    """Track workflow start - convenience function"""
    return get_lineage_client().start_workflow(workflow_id, workflow_name, workspace)


def track_workflow_complete(
    workflow_id: str,
    workflow_name: str,
    nodes_executed: List[str],
    execution_time_ms: int
) -> None:
    """Track workflow completion - convenience function"""
    get_lineage_client().complete_workflow(
        workflow_id, workflow_name, nodes_executed, execution_time_ms
    )


def track_llm_call(
    parent_run_id: str,
    model: str,
    provider: str,
    usage: Optional[Dict[str, int]] = None
) -> str:
    """Track LLM call - convenience function"""
    return get_lineage_client().emit_llm_call(
        parent_run_id, model, provider, usage=usage
    )


def track_tool_execution(
    parent_run_id: str,
    tool_name: str,
    tool_args: Dict[str, Any],
    success: bool,
    error_message: Optional[str] = None
) -> str:
    """Track tool execution - convenience function"""
    return get_lineage_client().emit_tool_execution(
        parent_run_id, tool_name, tool_args, success, error_message
    )
