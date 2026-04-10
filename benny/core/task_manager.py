import threading
import json
import uuid
from typing import Dict, Optional, List
from datetime import datetime
from pathlib import Path

from .schema import Task, TaskStatus
from .workspace import get_workspace_path
from ..governance.audit import emit_governance_event

class TaskManager:
    """
    Central registry for background tasks with persistence.
    """
    def __init__(self):
        self._tasks: Dict[str, Task] = {}
        self._lock = threading.Lock()

    def create_task(self, workspace: str, task_type: str, task_id: Optional[str] = None) -> Task:
        """Create and register a new task."""
        tid = task_id or str(uuid.uuid4())
        task = Task(
            task_id=tid,
            workspace=workspace,
            type=task_type,
            status=TaskStatus.RUNNING,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat()
        )
        with self._lock:
            self._tasks[tid] = task
        self.save_task(task)
        return task

    def update_task(self, task_id: str, **kwargs) -> Optional[Task]:
        """Update an existing task in-memory and on disk."""
        with self._lock:
            if task_id not in self._tasks:
                return None
            
            task = self._tasks[task_id]
            for key, value in kwargs.items():
                if hasattr(task, key):
                    # Handle Pydantic model attribute updates
                    if key == "aer_log" and isinstance(value, list):
                        task.aer_log.extend(value)
                    elif key == "status":
                        setattr(task, key, TaskStatus(value))
                    else:
                        setattr(task, key, value)
            
            task.updated_at = datetime.now().isoformat()
            self.save_task(task)
            return task

    def add_aer_entry(self, task_id: str, intent: str, observation: str, inference: str = "", plan: str = ""):
        """Helper to add a structured Agent Execution Record entry."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "intent": intent,
            "observation": observation,
            "inference": inference,
            "plan": plan
        }
        self.update_task(task_id, aer_log=[entry])

    def get_task(self, task_id: str) -> Optional[Task]:
        """Retrieve a task by ID."""
        with self._lock:
            return self._tasks.get(task_id)

    def list_tasks(self, workspace: Optional[str] = None) -> List[Task]:
        """List all tasks, optionally filtered by workspace."""
        with self._lock:
            if workspace:
                return [t for t in self._tasks.values() if t.workspace == workspace]
            return list(self._tasks.values())

    def save_task(self, task: Task):
        """Persist task to workspace/runs/task_registry.json"""
        try:
            runs_dir = get_workspace_path(task.workspace, "runs")
            runs_dir.mkdir(parents=True, exist_ok=True)
            registry_path = runs_dir / "task_registry.json"
            
            # Load existing
            registry = {}
            if registry_path.exists():
                try:
                    with open(registry_path, "r", encoding="utf-8") as f:
                        registry = json.load(f)
                except json.JSONDecodeError:
                    registry = {}
            
            # Update
            registry[task.task_id] = task.model_dump()
            
            # Save
            with open(registry_path, "w", encoding="utf-8") as f:
                json.dump(registry, f, indent=2)

            # Local Governance Audit
            emit_governance_event(
                event_type="TASK_METADATA_UPDATE",
                data=task.model_dump(),
                workspace_id=task.workspace
            )
        except Exception as e:
            # We don't want task saving to crash the main process
            print(f"[ERROR] TaskManager persistence failed for {task.task_id}: {e}")

# Global instance
task_manager = TaskManager()
