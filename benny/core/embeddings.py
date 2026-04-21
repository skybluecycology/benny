"""
Torch-free Embedding Utilities - Bypasses WinError 4551 by using HTTP providers.
"""

import os
import httpx
import logging
from typing import List, Optional, Any
import asyncio

logger = logging.getLogger(__name__)

# Use shared client for performance
_async_client: Optional[httpx.AsyncClient] = None
_sync_client: Optional[httpx.Client] = None

def _get_async_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None:
        _async_client = httpx.AsyncClient(timeout=30.0)
    return _async_client

def _get_sync_client() -> httpx.Client:
    global _sync_client
    if _sync_client is None:
        _sync_client = httpx.Client(timeout=30.0)
    return _sync_client

async def get_embedding_async(
    text: str, 
    provider: str = "lemonade", 
    model: str = "nomic-embed-text-v1-GGUF"
) -> List[float]:
    """Get embeddings via HTTP (Async). No Torch/Transformers required."""
    from .models import LOCAL_PROVIDERS
    
    provider_config = LOCAL_PROVIDERS.get(provider)
    if not provider_config:
        # Fallback to Ollama if lemonade is missing
        url = "http://localhost:11434/api/embeddings"
        payload = {"model": "nomic-embed-text", "prompt": text}
        client = _get_async_client()
        response = await client.post(url, json=payload)
    else:
        api_base = provider_config["base_url"]
        url = f"{api_base}/embeddings"
        payload = {"model": model, "input": text}
        client = _get_async_client()
        response = await client.post(url, json=payload)

    if response.status_code == 200:
        data = response.json()
        # Handle both OpenAI format and Ollama format
        if "data" in data:
            return data["data"][0]["embedding"]
        return data.get("embedding", [])
    else:
        logger.error(f"Embedding failed: {response.status_code} - {response.text}")
        return [0.0] * 768 # Fallback to zero vector to prevent crash

def get_embedding_sync(
    text: str, 
    provider: str = "lemonade", 
    model: str = "nomic-embed-text-v1-GGUF"
) -> List[float]:
    """Get embeddings via HTTP (Sync). Used by ChromaDB EmbeddingFunction."""
    from .models import LOCAL_PROVIDERS
    
    provider_config = LOCAL_PROVIDERS.get(provider)
    if not provider_config:
        url = "http://localhost:11434/api/embeddings"
        payload = {"model": "nomic-embed-text", "prompt": text}
    else:
        api_base = provider_config["base_url"]
        url = f"{api_base}/embeddings"
        payload = {"model": model, "input": text}

    client = _get_sync_client()
    try:
        response = client.post(url, json=payload)
        if response.status_code == 200:
            data = response.json()
            if "data" in data:
                return data["data"][0]["embedding"]
            return data.get("embedding", [])
    except Exception as e:
        logger.error(f"Sync embedding failed: {e}")
    
    return [0.0] * 768

# =============================================================================
# CHROMADB INTEGRATION
# =============================================================================

from chromadb.api.types import Documents, EmbeddingFunction, Embeddings

class LocalEmbeddingFunction(EmbeddingFunction):
    """ChromaDB-compatible wrapper for our HTTP embedding utility."""
    def __init__(self, provider: str = "lemonade", model: str = "nomic-embed-text-v1-GGUF"):
        self.provider = provider
        self.model = model

    def __call__(self, input: Documents) -> Embeddings:
        # ChromaDB expects a list of embeddings
        return [get_embedding_sync(text, self.provider, self.model) for text in input]
