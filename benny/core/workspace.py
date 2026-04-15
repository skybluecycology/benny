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
    Strictly validates that the path is within WORKSPACE_ROOT to prevent traversal.
    
    Args:
        workspace_id: Workspace identifier
        subdir: Subdirectory within workspace (data_in, data_out, chromadb, etc.)
        
    Returns:
        Absolute path to the workspace directory or subdirectory
    """
    # 1. Resolve potential traversal before joining
    # We use .absolute() to ensure we aren't tricked by relative paths
    root_abs = WORKSPACE_ROOT.absolute()
    
    # Construct the target path
    target = root_abs / workspace_id
    if subdir:
        target = target / subdir
        
    target_abs = target.absolute()
    
    # 2. Strict validation: Target must be a child of root_abs
    try:
        if os.path.commonpath([str(root_abs), str(target_abs)]) != str(root_abs):
            raise PermissionError(f"Path traversal attempt detected: {workspace_id}/{subdir}")
    except ValueError:
        raise PermissionError(f"Invalid workspace path: {workspace_id}/{subdir}")
        
    return target_abs


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
    
    # Create default Operating Manuals if they don't exist
    _create_default_manual(base / "SOUL.md", """# Name
Benny

# Purpose
Enterprise cognitive mesh orchestration platform for structured knowledge work.

# Communication Style
Professional, precise, and transparent. Always explain reasoning.

# Core Values
- Accuracy over speed
- Transparency in all reasoning
- Human oversight for critical decisions
- Data privacy and security

# Boundaries
- Never modify production data without explicit human approval
- Always cite sources when providing information
- Escalate to human reviewers when confidence is below 70%
- Never expose credentials or sensitive information in outputs
""")

    _create_default_manual(base / "USER.md", """# Organization
[Your Organization Name]

# Authorized Personnel
- [Admin Name] (Admin)

# Domain Context
[Describe your business domain and subject matter]

# Compliance Requirements
- All outputs must be auditable via governance logs
- PII must be handled per applicable regulations
""")

    _create_default_manual(base / "AGENTS.md", """# Coding Standards
- Use type hints in all Python functions
- Follow PEP 8 style guidelines
- Write docstrings for all public functions

# Tool Usage Policies
- Always use call_model() for LLM calls, never raw litellm
- Use the SkillRegistry for tool execution
- Log all file system operations

# Forbidden Actions
- Do not delete files outside the workspace directory
- Do not make external API calls without RBAC authorization
- Do not bypass governance middleware
- Do not store credentials in plain text

# Output Formatting
- Use Markdown for all generated documents
- Include timestamps and provenance in generated artifacts
""")

    # Create security subdirectories
    for sec_dir in ["policies", "agents", "credentials"]:
        path = base / sec_dir
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created.append(sec_dir)

    return {
        "status": "ready",
        "workspace_id": workspace_id,
        "path": str(base.absolute()),
        "created_dirs": [d for d in created if d != "manifest.yaml"],
        "manifest_created": "manifest.yaml" in created,
        "isolation": "scoped_directory_structure"
    }


def _create_default_manual(path: Path, content: str) -> None:
    """Create a default manual file if it doesn't exist."""
    if not path.exists():
        try:
            path.write_text(content.strip(), encoding="utf-8")
        except Exception as e:
            # We don't want task saving to crash the main process
            import logging
            logging.error(f"TaskManager persistence failed for {path}: {e}")


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
    try:
        path = get_workspace_path(workspace_id, subdir)
        if not path.exists():
            return []
        
        files = []
        try:
            for item in path.iterdir():
                if item.is_file():
                    try:
                        files.append({
                            "name": item.name,
                            "path": str(item.relative_to(WORKSPACE_ROOT.absolute())),
                            "size": item.stat().st_size,
                            "modified": item.stat().st_mtime
                        })
                    except Exception:
                        continue # Skip problematic files
        except Exception:
            return []
        
        return files
    except Exception as e:
        import logging
        logging.error(f"Error listing files for {workspace_id}/{subdir}: {e}")
        return []


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
    # Ensure we strip BOM to avoid confusion in MIME detection downstream
    content = content.lstrip('\ufeff')
    
    if len(content.encode('utf-8', errors='replace')) < PASS_BY_REFERENCE_THRESHOLD:
        return content
    
    # Save to file and return reference
    path = get_workspace_path(workspace_id, f"data_out/{filename}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    
    return f"📥 Content saved: {server_url}/api/files/{workspace_id}/{filename}"
