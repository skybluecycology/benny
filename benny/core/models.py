"""
Multi-Model Orchestration - LiteLLM integration with local/cloud providers
"""

import os
from typing import Optional, Dict, Any, List
from litellm import completion


# =============================================================================
# PRECONFIGURED LOCAL LLM PROVIDERS
# =============================================================================

LOCAL_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "lemonade": {
        "name": "Lemonade",
        "port": 8000,
        "base_url": "http://localhost:8000/api/v1",
        "api_key": "not-needed",
        "description": "AMD NPU accelerated inference",
        "startup_cmd": "lemonade-server serve --port 8000",
        "check_url": "http://localhost:8000/api/v1/models"
    },
    "ollama": {
        "name": "Ollama",
        "port": 11434,
        "base_url": "http://localhost:11434/v1",
        "api_key": "ollama",
        "description": "Popular local LLM server",
        "startup_cmd": "ollama serve",
        "check_url": "http://localhost:11434/v1/models"
    },
    "fastflowlm": {
        "name": "FastFlowLM",
        "port": 52625,
        "base_url": "http://localhost:52625/v1",
        "api_key": "not-needed",
        "description": "Intel NPU accelerated inference",
        "startup_cmd": None,  # Manual start required
        "check_url": "http://localhost:52625/v1/models"
    }
}


# =============================================================================
# MODEL REGISTRY (Cloud + Local)
# =============================================================================

MODEL_REGISTRY: Dict[str, Dict[str, Any]] = {
    # Cloud models for high-quality reasoning
    "reasoning": {
        "model": "gpt-4-turbo",
        "provider": "openai",
        "cost_per_1k": 0.01,
        "use_for": ["planning", "complex_analysis"]
    },
    "writing": {
        "model": "claude-3-sonnet-20240229",
        "provider": "anthropic",
        "cost_per_1k": 0.003,
        "use_for": ["content_generation", "summarization"]
    },
    "fast": {
        "model": "gpt-3.5-turbo",
        "provider": "openai",
        "cost_per_1k": 0.0005,
        "use_for": ["simple_tasks", "classification"]
    },
    # Local models for privacy and cost savings
    "local_lemonade": {
        "model": "openai/DeepSeek-R1-Distill-Llama-8B-FLM",
        "provider": "lemonade",
        "cost_per_1k": 0.0,
        "use_for": ["offline", "sensitive_data", "testing"]
    },
    "local_ollama": {
        "model": "ollama/llama3",
        "provider": "ollama",
        "cost_per_1k": 0.0,
        "use_for": ["offline", "sensitive_data"]
    },
    "local_fastflow": {
        "model": "openai/deepseek-r1:8b",
        "provider": "fastflowlm",
        "cost_per_1k": 0.0,
        "use_for": ["intel_npu", "offline", "testing", "reasoning"]
    }
}


def configure_local_provider(provider: str = "ollama", port: Optional[int] = None) -> Dict[str, Any]:
    """
    Configure environment for local LLM provider.
    
    Args:
        provider: Provider name (lemonade, ollama, fastflowlm)
        port: Optional custom port override
        
    Returns:
        Configuration dict with provider details
    """
    config = LOCAL_PROVIDERS.get(provider, LOCAL_PROVIDERS["ollama"])
    actual_port = port or config["port"]
    
    base_url = config["base_url"].replace(str(config["port"]), str(actual_port))
    os.environ["OPENAI_API_BASE"] = base_url
    os.environ["OPENAI_API_KEY"] = config["api_key"]
    
    return {
        "provider": provider,
        "port": actual_port,
        "base_url": base_url,
        "name": config["name"]
    }


def get_model_for_task(task_type: str) -> str:
    """
    Intelligent model routing based on task type.
    
    Args:
        task_type: Type of task (planning, summarization, offline, etc.)
        
    Returns:
        Model identifier string for LiteLLM
    """
    for profile in MODEL_REGISTRY.values():
        if task_type in profile["use_for"]:
            return profile["model"]
    return MODEL_REGISTRY["reasoning"]["model"]


def get_available_models() -> List[Dict[str, Any]]:
    """Get list of all configured models with metadata"""
    return [
        {
            "id": key,
            "model": profile["model"],
            "provider": profile["provider"],
            "cost_per_1k": profile["cost_per_1k"],
            "use_for": profile["use_for"]
        }
        for key, profile in MODEL_REGISTRY.items()
    ]


def get_model_config(model_id: str) -> Dict[str, Any]:
    """
    Get configuration for a specific model.
    
    Args:
        model_id: Model ID or LiteLLM model string
        
    Returns:
        Model configuration dict with base_url and api_key if local
    """
    # Check if it's a registered model ID
    if model_id in MODEL_REGISTRY:
        profile = MODEL_REGISTRY[model_id]
        provider = profile["provider"]
        model = profile["model"]
    else:
        # Parse LiteLLM model string like "ollama/llama3"
        if "/" in model_id:
            provider = model_id.split("/")[0]
            model = model_id
        else:
            provider = "openai"
            model = model_id
    
    config = {
        "model": model,
        "provider": provider
    }
    
    # Add local provider configuration
    if provider in LOCAL_PROVIDERS:
        local_config = LOCAL_PROVIDERS[provider]
        config["base_url"] = local_config["base_url"]
        config["api_key"] = local_config["api_key"]
    
    return config


async def call_model(
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 1000,
    fallbacks: Optional[List[str]] = None
) -> str:
    """
    Call LLM with fallback support.
    
    Args:
        model: Model identifier
        messages: Chat messages
        temperature: Sampling temperature
        max_tokens: Max tokens to generate
        fallbacks: Fallback models if primary fails
        
    Returns:
        Generated text response
    """
    try:
        response = completion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            fallbacks=fallbacks or []
        )
        return response.choices[0].message.content
    except Exception as e:
        if fallbacks:
            for fallback in fallbacks:
                try:
                    response = completion(
                        model=fallback,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    return response.choices[0].message.content
                except:
                    continue
        raise e
