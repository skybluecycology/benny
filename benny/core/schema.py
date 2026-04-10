"""
Global Schema - Pydantic models for workspace manifests and governance.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional

class WorkspaceManifest(BaseModel):
    """
    Workspace configuration manifest (manifest.yaml).
    
    This is the "Decentralized Manifest" that teams own in their workspace repo.
    """
    version: str = Field(default="1.0.0", description="Schema version for governance and migrations")
    llm_timeout: float = Field(default=300.0, description="LLX call timeout in seconds")
    default_model: Optional[str] = Field(None, description="Primary model for this workspace")
    embedding_provider: str = Field(default="local", description="Provider for vector embeddings")
    governance_tags: List[str] = Field(default_factory=list, description="Audit and compliance tags")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary extension fields")

    class Config:
        json_schema_extra = {
            "example": {
                "version": "1.0.0",
                "llm_timeout": 600.0,
                "default_model": "gemma-4-26b-a4b",
                "governance_tags": ["high_compliance", "sensitive_data"],
                "metadata": {"owner": "AI Platform Team"}
            }
        }
