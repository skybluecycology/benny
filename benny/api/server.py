"""
Benny API Server - FastAPI application with CORS and routers
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from contextlib import asynccontextmanager
from .llm_routes import router as llm_router
from .workflow_routes import router as workflow_router
from .file_routes import router as file_router
from .rag_routes import router as rag_router
from .notebook_routes import router as notebook_router
from .chat_routes import router as chat_router
from .studio_executor import router as studio_router
from .skill_routes import router as skill_router
from .graph_routes import router as graph_router


@asynccontextmanager
async def lifespan(app):
    """Initialize services on startup, cleanup on shutdown."""
    # Startup
    try:
        from benny.core.graph_db import init_schema
        init_schema()
        print("✅ Neo4j schema initialized")
    except Exception as e:
        print(f"⚠️ Neo4j not available: {e}")
    yield
    # Shutdown
    try:
        from benny.core.graph_db import close_driver
        close_driver()
        print("🔌 Neo4j driver closed")
    except Exception:
        pass


app = FastAPI(
    title="Benny API",
    description="Deterministic Graph Workflow Platform with Multi-Model AI Orchestration",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
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
app.include_router(graph_router, prefix="/api", tags=["Knowledge Graph"])


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

