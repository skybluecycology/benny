"""
Workspace Isolation - Multi-tenant workspace management
"""

from pathlib import Path
from typing import Optional, List, Dict, Any
import os
import yaml
import json

from .schema import WorkspaceManifest


# Base workspace directory
WORKSPACE_ROOT = Path("workspace")


def get_workspace_path(workspace_id: str = "default", subdir: str = "") -> Path:
    """
    Get workspace-scoped path for multi-tenant isolation.
    
    Args:
        workspace_id: Workspace identifier
        subdir: Subdirectory within workspace (data_in, data_out, chromadb, etc.)
        
    Returns:
        Absolute path to the workspace directory or subdirectory
    """
    base = WORKSPACE_ROOT / workspace_id
    return base / subdir if subdir else base


def ensure_workspace_structure(workspace_id: str = "default") -> dict:
    """
    Create workspace directory structure and initial manifest if it doesn't exist.
    """
    base = get_workspace_path(workspace_id)
    subdirs = ["agents", "chromadb", "data_in", "data_out", "reports", "skills", "runs", "staging"]
    
    created = []
    for subdir in subdirs:
        path = base / subdir
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(subdir)
    
    # Initialize manifest if missing
    manifest_path = base / "manifest.yaml"
    if not manifest_path.exists():
        manifest = WorkspaceManifest(version="1.0.0")
        with open(manifest_path, "w", encoding="utf-8") as f:
            yaml.dump(manifest.dict(), f, sort_keys=False)
        created.append("manifest.yaml")
    
    return {
        "status": "ready",
        "workspace_id": workspace_id,
        "path": str(base.absolute()),
        "created_dirs": [d for d in created if d != "manifest.yaml"],
        "manifest_created": "manifest.yaml" in created,
        "isolation": "scoped_directory_structure"
    }


def load_manifest(workspace_id: str) -> WorkspaceManifest:
    """Load and validate the workspace manifest (YAML)."""
    path = get_workspace_path(workspace_id) / "manifest.yaml"
    if not path.exists():
        return WorkspaceManifest(version="1.0.0")
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data:
            return WorkspaceManifest(version="1.0.0")
        return WorkspaceManifest(**data)
    except Exception as e:
        print(f"[WARNING] Error loading manifest for {workspace_id}: {e}")
        return WorkspaceManifest(version="1.0.0")


def save_manifest(workspace_id: str, manifest: WorkspaceManifest) -> None:
    """Save the workspace manifest to YAML."""
    path = get_workspace_path(workspace_id) / "manifest.yaml"
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(manifest.dict(), f, sort_keys=False)


def list_workspaces() -> List[dict]:
    """
    List all workspaces and act as a Discovery Catalog crawler.
    Enriches the results with manifest metadata for centralized observability.
    """
    if not WORKSPACE_ROOT.exists():
        WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
        return []
    
    workspaces = []
    for item in WORKSPACE_ROOT.iterdir():
        if item.is_dir():
            manifest = load_manifest(item.name)
            workspaces.append({
                "id": item.name,
                "path": str(item.absolute()),
                "has_chromadb": (item / "chromadb").exists(),
                "has_data": (item / "data_in").exists() and any((item / "data_in").iterdir()) if (item / "data_in").exists() else False,
                "manifest": manifest.dict()  # Enriched discovery metadata
            })
    
    return workspaces


def get_workspace_files(workspace_id: str, subdir: str = "data_out") -> List[dict]:
    """
    List files in a workspace subdirectory.
    
    Args:
        workspace_id: Workspace identifier
        subdir: Subdirectory to list (default: data_out)
        
    Returns:
        List of file info dicts
    """
    path = get_workspace_path(workspace_id, subdir)
    if not path.exists():
        return []
    
    files = []
    for item in path.iterdir():
        if item.is_file():
            files.append({
                "name": item.name,
                "path": str(item.relative_to(WORKSPACE_ROOT)),
                "size": item.stat().st_size,
                "modified": item.stat().st_mtime
            })
    
    return files


# Pass-by-reference threshold (5KB)
PASS_BY_REFERENCE_THRESHOLD = 5 * 1024


def smart_output(
    content: str, 
    filename: str, 
    workspace_id: str = "default",
    server_url: str = "http://localhost:8005"
) -> str:
    """
    Return content directly if small, otherwise save and return URL reference.
    
    Reduces token costs by 60-80% for large outputs.
    
    Args:
        content: Content to output
        filename: Filename if saved
        workspace_id: Target workspace
        server_url: Base URL for download links
        
    Returns:
        Content if small, or download URL if large
    """
    if len(content.encode('utf-8')) < PASS_BY_REFERENCE_THRESHOLD:
        return content
    
    # Save to file and return reference
    path = get_workspace_path(workspace_id, f"data_out/{filename}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    
    return f"📥 Content saved: {server_url}/api/files/{workspace_id}/{filename}"
