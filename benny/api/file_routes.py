"""
File Routes - Upload, list, and manage workspace files
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from pathlib import Path
from typing import List
import shutil

from ..core.workspace import get_workspace_path, get_workspace_files


router = APIRouter()


@router.post("/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    workspace: str = "default",
    subdir: str = "data_in"
):
    """Upload a file to workspace data_in directory"""
    try:
        # Validate file type
        allowed_extensions = {'.pdf', '.txt', '.md', '.json'}
        file_ext = Path(file.filename).suffix.lower()
        
        if file_ext not in allowed_extensions:
            raise HTTPException(
                400, 
                f"File type {file_ext} not allowed. Allowed: {', '.join(allowed_extensions)}"
            )
        
        # Save file
        target_dir = get_workspace_path(workspace, subdir)
        target_dir.mkdir(parents=True, exist_ok=True)
        
        file_path = target_dir / file.filename
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        return {
            "status": "uploaded",
            "filename": file.filename,
            "path": str(file_path),
            "size": file_path.stat().st_size
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Upload failed: {str(e)}")


@router.get("/files")
async def list_files(workspace: str = "default"):
    """List all files in workspace data_in and data_out"""
    try:
        data_in_files = get_workspace_files(workspace, "data_in")
        data_out_files = get_workspace_files(workspace, "data_out")
        
        return {
            "workspace": workspace,
            "data_in": data_in_files,
            "data_out": data_out_files,
            "total": len(data_in_files) + len(data_out_files)
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to list files: {str(e)}")


@router.delete("/files/{filename}")
async def delete_file(
    filename: str,
    workspace: str = "default",
    subdir: str = "data_in"
):
    """Delete a file from workspace"""
    try:
        file_path = get_workspace_path(workspace, subdir) / filename
        
        if not file_path.exists():
            raise HTTPException(404, f"File not found: {filename}")
        
        if not file_path.is_file():
            raise HTTPException(400, f"Not a file: {filename}")
        
        file_path.unlink()
        
        return {
            "status": "deleted",
            "filename": filename
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Delete failed: {str(e)}")
