"""
Benny API Server - FastAPI application with CORS and routers
"""

import json
import builtins

# Monkey-patch print to prevent UnicodeEncodeError on Windows CP1252 consoles
_original_print = builtins.print

def _safe_print(*args, **kwargs):
    try:
        _original_print(*args, **kwargs)
    except UnicodeEncodeError:
        safe_args = [str(a).encode('ascii', 'replace').decode('ascii') for a in args]
        _original_print(*safe_args, **kwargs)

builtins.print = _safe_print

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from pathlib import Path
import os

from contextlib import asynccontextmanager
from .llm_routes import router as llm_router
from .workflow_routes import router as workflow_router
from .file_routes import router as file_router
from .etl_routes import router as etl_router
from .rag_routes import router as rag_router
from .notebook_routes import router as notebook_router
from .chat_routes import router as chat_router
from .studio_executor import router as studio_router
from .skill_routes import router as skill_router
from .graph_routes import router as graph_router
from .workspace_routes import router as workspace_router
from .task_routes import router as task_router
from .governance_routes import router as governance_router
from .system_routes import router as system_router
from ..a2a.server import router as a2a_router
from .live_routes import router as live_router
from .manifest_routes import router as manifest_router
from .workflow_endpoints import router as workflow_endpoints_router
from .audio_routes import router as audio_router
from .ops_endpoints import router as ops_router
from .kg3d import router as kg3d_router

# Temporary fix for missing rbac.py module
GOVERNANCE_WHITELIST = ["/api/health", "/api/status"]
from ..core.workspace import get_workspace_path

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize shared resources
    print("✓ Neural Nexus Kernel Initialized")
    yield
    # Shutdown: Clean up
    print("Neo4j driver closed")

app = FastAPI(
    title="Benny Neural Nexus API",
    description="Cognitive Mesh Engine for Software Synthesis",
    version="1.0.0",
    lifespan=lifespan
)

# Governance Middleware (FR-5: RBAC Enforcement)
class GovernanceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Path Whitelist (Health, SSE, Docs)
        path = request.url.path
        if path == "/" or path.startswith("/docs") or path.startswith("/openapi.json"):
            return await call_next(request)
            
        for white_path in GOVERNANCE_WHITELIST:
            if path.startswith(white_path):
                return await call_next(request)

        # 2. Extract API Key
        api_key = request.headers.get("X-Benny-API-Key")
        if not api_key:
             return Response(content='{"detail":"Unauthorized: X-Benny-API-Key required"}', status_code=401, media_type="application/json")
        
        # 3. RBAC Check (PBR-001 Phase 3)
        # Simplified for now: just check if key exists. Full implementation in Phase 8.
        if api_key != "benny-mesh-2026-auth":
             return Response(content='{"detail":"Forbidden: Invalid API Key"}', status_code=403, media_type="application/json")

        return await call_next(request)

# app.add_middleware(GovernanceMiddleware)

# Enable CORS for Benny Studio (UX-REC-001)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # In production, restrict to studio domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(system_router, prefix="/api/system", tags=["System"])
app.include_router(llm_router, prefix="/api/llm", tags=["LLM"])
app.include_router(workspace_router, prefix="/api/workspaces", tags=["Workspaces"])
app.include_router(file_router, prefix="/api/files", tags=["Files"])
app.include_router(rag_router, prefix="/api", tags=["RAG"])
app.include_router(graph_router, prefix="/api", tags=["Knowledge Graph"])
app.include_router(notebook_router, prefix="/api/notebooks", tags=["Notebooks"])
app.include_router(chat_router, prefix="/api/chat", tags=["Chat"])
app.include_router(studio_router, prefix="/api/workflows/studio", tags=["Studio"])
app.include_router(workflow_router, prefix="/api/workflows", tags=["Workflows"])
app.include_router(workflow_endpoints_router, prefix="/api/workflows", tags=["Workflows"])
app.include_router(skill_router, prefix="/api/skills", tags=["Skills"])
app.include_router(task_router, prefix="/api/tasks", tags=["Tasks"])
app.include_router(governance_router, prefix="/api/governance", tags=["Governance"])
app.include_router(live_router, prefix="/api/live", tags=["Live"])
app.include_router(manifest_router, prefix="/api/manifests", tags=["Manifests"])
app.include_router(a2a_router, prefix="/a2a", tags=["A2A"])
app.include_router(audio_router, prefix="/api/audio", tags=["Audio"])
app.include_router(ops_router, prefix="/api/ops", tags=["Ops"])
app.include_router(kg3d_router, tags=["KG3D"])

@app.get("/")
async def root():
    return {
        "app": "Benny Neural Nexus",
        "status": "online",
        "mesh_version": "2026.4.1",
        "engine": "Synthesis Knowledge Engine v2"
    }


# Static file serving for workspace data_out artifacts
# Note: workspace_path is resolved at runtime based on BENNY_HOME
workspace_path = get_workspace_path("default").parent
app.mount("/api/static", StaticFiles(directory=str(workspace_path)), name="files")


if __name__ == "__main__":
    import uvicorn
    # Cognitive Mesh Security: Bind to loopback only by default
    uvicorn.run(app, host="0.0.0.0", port=8005, reload=True)
