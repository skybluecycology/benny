"""
Skill Routes - REST API for managing workspace skills and catalog
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Any, Optional

from ..core.skill_registry import registry, SkillParameter


router = APIRouter()


class SkillParameterCreate(BaseModel):
    name: str
    type: str
    description: str
    required: bool = True
    default: Optional[Any] = None


class SkillCreate(BaseModel):
    id: str
    name: str
    description: str
    category: str = "custom"
    parameters: List[SkillParameterCreate] = []


@router.get("/skills")
async def list_skills(workspace: str = "default"):
    """Get all available skills (built-in + workspace)"""
    try:
        skills = registry.get_all_skills(workspace)
        return {
            "workspace": workspace,
            "skills": [s.to_dict() for s in skills],
            "count": len(skills)
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to list skills: {str(e)}")


@router.get("/skills/catalog")
async def get_skill_catalog(workspace: str = "default"):
    """Get skills grouped by category for progressive discovery"""
    try:
        catalog = registry.get_catalog(workspace)
        return {
            "workspace": workspace,
            "catalog": catalog
        }
    except Exception as e:
        raise HTTPException(500, f"Failed to get catalog: {str(e)}")


@router.post("/skills")
async def create_skill(request: SkillCreate, workspace: str = "default"):
    """Save a custom skill to the workspace"""
    try:
        # Check if overriding a built-in skill
        builtins = {s.id for s in registry.get_builtin_skills()}
        if request.id in builtins:
            # We allow overriding, but maybe add a warning or specific flag later
            pass
            
        skill_data = request.model_dump()
        result = registry.save_workspace_skill(workspace, skill_data)
        return result
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Failed to save skill: {str(e)}")


@router.delete("/skills/{skill_id}")
async def delete_skill(skill_id: str, workspace: str = "default"):
    """Delete a custom workspace skill"""
    try:
        # Built-in skills cannot be deleted
        builtins = {s.id for s in registry.get_builtin_skills()}
        if skill_id in builtins:
            raise HTTPException(400, f"Cannot delete built-in skill: {skill_id}")
            
        result = registry.delete_workspace_skill(workspace, skill_id)
        return result
    except FileNotFoundError:
        raise HTTPException(404, f"Skill not found in workspace: {skill_id}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to delete skill: {str(e)}")
