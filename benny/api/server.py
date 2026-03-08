"""
Benny API Server - FastAPI application with CORS and routers
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# Force reload trigger
from contextlib import asynccontextmanager
from .llm_routes import router as llm_router
from .workflow_routes import router as workflow_router
from .file_routes import router as file_router
from .rag_routes import router as rag_router
from .notebook_routes import router as notebook_router
from .chat_routes import router as chat_router
from .studio_executor import router as studio_router
from .skill_routes import router as skill_router



app = FastAPI(
    title="Benny API",
    description="Deterministic Graph Workflow Platform with Multi-Model AI Orchestration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS for frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(llm_router, prefix="/api/llm", tags=["LLM Management"])
app.include_router(workflow_router, prefix="/api", tags=["Workflows"])
app.include_router(file_router, prefix="/api", tags=["File Management"])
app.include_router(rag_router, prefix="/api", tags=["RAG"])
app.include_router(notebook_router, prefix="/api", tags=["Notebooks"])
app.include_router(chat_router, prefix="/api", tags=["Chat"])
app.include_router(studio_router, prefix="/api", tags=["Studio"])
app.include_router(skill_router, prefix="/api", tags=["Skills"])



@app.get("/")
async def root():
    """API root - health check"""
    return {
        "name": "Benny API",
        "version": "1.0.0",
        "status": "healthy",
        "docs": "/docs"
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok"}


# Serve workspace files
workspace_path = Path("workspace")
if workspace_path.exists():
    app.mount("/files", StaticFiles(directory=str(workspace_path)), name="files")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005, reload=True)
