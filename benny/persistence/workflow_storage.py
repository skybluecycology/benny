"""
Workflow Storage - File-based persistence for workflow definitions
"""

from pathlib import Path
from typing import List, Dict, Any, Optional
import json
from datetime import datetime


# Storage locations
WORKSPACE_WORKFLOWS = Path("workspace/workflows")
EXAMPLE_WORKFLOWS = Path("benny/examples/workflows")


class WorkflowStorage:
    """Manage workflow persistence across user and system directories"""
    
    def __init__(self):
        # Ensure directories exist
        WORKSPACE_WORKFLOWS.mkdir(parents=True, exist_ok=True)
        EXAMPLE_WORKFLOWS.mkdir(parents=True, exist_ok=True)
    
    def list_workflows(self) -> List[Dict[str, Any]]:
        """List all available workflows (user + examples)"""
        workflows = []
        
        # Load user workflows
        if WORKSPACE_WORKFLOWS.exists():
            for file_path in WORKSPACE_WORKFLOWS.glob("*.json"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        workflows.append({
                            **data,
                            "type": "user",
                            "file_path": str(file_path)
                        })
                except Exception:
                    pass  # Skip invalid files
        
        # Load example workflows
        if EXAMPLE_WORKFLOWS.exists():
            for file_path in EXAMPLE_WORKFLOWS.glob("*.json"):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        workflows.append({
                            **data,
                            "type": "example",
                            "readonly": True,
                            "file_path": str(file_path)
                        })
                except Exception:
                    pass
        
        return workflows
    
    def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific workflow by ID"""
        # Check user workflows first
        user_path = WORKSPACE_WORKFLOWS / f"{workflow_id}.json"
        if user_path.exists():
            with open(user_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {**data, "type": "user"}
        
        # Check examples
        example_path = EXAMPLE_WORKFLOWS / f"{workflow_id}.json"
        if example_path.exists():
            with open(example_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {**data, "type": "example", "readonly": True}
        
        return None
    
    def save_workflow(self, workflow: Dict[str, Any]) -> Dict[str, Any]:
        """Save a workflow to user directory"""
        workflow_id = workflow.get("id")
        if not workflow_id:
            raise ValueError("Workflow must have an 'id' field")
        
        # Add metadata
        workflow["updated_at"] = datetime.now().isoformat()
        if "created_at" not in workflow:
            workflow["created_at"] = workflow["updated_at"]
        
        # Save to user directory
        file_path = WORKSPACE_WORKFLOWS / f"{workflow_id}.json"
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(workflow, f, indent=2)
        
        return {"status": "saved", "id": workflow_id, "path": str(file_path)}
    
    def delete_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """Delete a workflow (user workflows only)"""
        file_path = WORKSPACE_WORKFLOWS / f"{workflow_id}.json"
        
        if not file_path.exists():
            raise FileNotFoundError(f"Workflow not found: {workflow_id}")
        
        file_path.unlink()
        return {"status": "deleted", "id": workflow_id}
