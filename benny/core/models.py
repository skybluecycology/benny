"""
Multi-Model Orchestration - LiteLLM integration with local/cloud providers
"""

import os
import httpx
from typing import Optional, Dict, Any, List
from litellm import completion
import logging
from .litert_engine import LiteRTEngine
import datetime
from .event_bus import event_bus
import json

# Local Executor imports (added for direct access)
from .local_executor import resolve_executor

logger = logging.getLogger(__name__)

# Registry of local providers and their base URLs
LOCAL_PROVIDERS = {
    "ollama": {
        "port": 11434,
        "base_url": "http://localhost:11434/v1",
        "doc_url": "https://ollama.com",
    },
    "lemonade": {
        "port": 13305,
        "base_url": "http://127.0.0.1:13305/api/v1",
        "docs": "https://github.com/benny/lemonade",
        "startup_cmd": "LemonadeServer.exe serve --port 13305",
        "check_url": "http://127.0.0.1:13305/api/v1/models"
    },
    "fastflowlm": {
        "port": 52625,
        "base_url": "http://localhost:52625/v1",
        "docs": "https://github.com/benny/fastflow",
    },
    "lmstudio": {
        "port": 1234,
        "base_url": "http://localhost:1234/v1",
        "docs": "https://lmstudio.ai",
    }
}

MODEL_REGISTRY = {
    # Cloud providers
    "openai/gpt-4o": {
        "provider": "openai",
        "model": "gpt-4o",
        "cost_per_1k": 0.03
    },
    "anthropic/claude-3-sonnet": {
        "provider": "anthropic",
        "model": "claude-3-sonnet-20240229",
        "cost_per_1k": 0.015
    },
    # Local models for privacy and cost savings
    "local_lemonade": {
        "model": "openai/deepseek-r1-8b-FLM",
        "provider": "lemonade",
        "cost_per_1k": 0.0,
        "use_for": ["offline", "sensitive_data", "testing", "reasoning", "content_generation"]
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
    },
    "local_lmstudio": {
        "model": "openai/Gemma-4-E4B-it-GGUF", # Optimized ID for Lemonade-compatible requests
        "provider": "lmstudio",
        "cost_per_1k": 0.0,
        "use_for": ["offline", "sensitive_data", "testing", "reasoning"]
    },
    "local_litert": {
        "model": "litert/gemma-4-E4B-it.litertlm",
        "provider": "litert",
        "cost_per_1k": 0.0,
        "use_for": ["on-device", "offline", "npu-accelerated", "testing", "gemma-4"]
    },
    "voice_speed": {
        "model": "openai/qwen3-tk-4b-FLM",
        "provider": "lemonade",
        "cost_per_1k": 0.0,
        "use_for": ["voice", "speed", "high_speed", "low_latency"]
    }
}


# =============================================================================
# PORTABILITY / OFFLINE HARDENING (PBR-001 Phase 3)
# =============================================================================

# Prefixes that identify a model string as pointing at a local provider.
# ``litert`` is the only one that doesn't carry a live process — it's an
# on-device inference engine — but it is still "local" for the purposes of
# offline/local-only policy.
_LOCAL_PREFIXES: tuple[str, ...] = tuple(f"{name}/" for name in LOCAL_PROVIDERS.keys())


def is_local_model(model_name: str) -> bool:
    """Return True if ``model_name`` is served by a local provider."""
    if model_name.startswith(_LOCAL_PREFIXES) or model_name.startswith("litert/"):
        return True
    
    # Check if it's a registry key pointing to a local provider
    if model_name in MODEL_REGISTRY:
        provider = MODEL_REGISTRY[model_name].get("provider", "").lower()
        if provider in LOCAL_PROVIDERS or provider == "litert":
            return True
            
    return False


def _offline_enabled() -> bool:
    """Return True if the BENNY_OFFLINE kill-switch is active."""
    return os.environ.get("BENNY_OFFLINE", "").lower() in ("1", "true", "yes")


class OfflineRefusal(Exception):
    """Raised when a non-local model is requested while offline mode is active."""

# =============================================================================
# MODEL RESOLUTION
# =============================================================================

def get_model_config(model_id: str) -> Dict[str, Any]:
    """Resolve a model ID to a provider and configuration."""
    if model_id in MODEL_REGISTRY:
        return MODEL_REGISTRY[model_id]
    
    # Handle direct provider/model strings
    if "/" in model_id:
        provider, model = model_id.split("/", 1)
        config = {
            "provider": provider,
            "model": model,
            "cost_per_1k": 0.0
        }
        # Inject base_url for local providers if not in registry
        if provider in LOCAL_PROVIDERS:
            config["base_url"] = LOCAL_PROVIDERS[provider]["base_url"]
        return config
    
    return {
        "provider": "openai",
        "model": model_id,
        "cost_per_1k": 0.0
    }

async def get_active_model(workspace_id: str = "default", role: str = "chat") -> str:
    """Determine which model is currently 'active' for a role in a workspace."""
    try:
        from .workspace import load_manifest
        manifest = load_manifest(workspace_id)
        
        # 1. Check role-specific mapping
        if hasattr(manifest, "model_roles") and role in manifest.model_roles:
            return manifest.model_roles[role]
            
        # 2. Check workspace default
        if hasattr(manifest, "default_model") and manifest.default_model:
            return manifest.default_model
    except Exception as e:
        print(f"DEBUG: Critical error in get_active_model: {e}")
    
    # 3. Auto-detect local providers (Heartbeat probe)
    # This ensures "it just works" out of the box if Lemonade/Ollama is running
    for provider_name, config in LOCAL_PROVIDERS.items():
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                resp = await client.get(config["base_url"].replace("/v1", "/models"))
                if resp.status_code == 200:
                    # Return first available model from this provider
                    data = resp.json()
                    models = data.get("data", [])
                    if models:
                        model_id = models[0].get("id")
                        return f"{provider_name}/{model_id}"
        except Exception as e:
            # logging.debug(f"Provider {provider_name} not available: {e}")
            pass

    # 4. Global fallback
    return "openai/gpt-4o"

# =============================================================================
# LOGGING & AUDIT
# =============================================================================

def log_llm_call(data: Dict[str, Any]):
    """Log LLM call metadata to a JSONL file for audit and fine-tuning."""
    log_file = os.path.join("logs", "llm_calls.jsonl")
    os.makedirs("logs", exist_ok=True)
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(data) + "\n")

# =============================================================================
# CORE DISPATCHER
# =============================================================================

async def _await_if_needed(obj):
    if hasattr(obj, '__await__'):
        return await obj
    return obj

def _run_completion(**kwargs):
    """Sync wrapper for litellm.completion to allow easy patching."""
    return completion(**kwargs)

async def call_model(
    model: str,
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int = 2048,
    fallbacks: Optional[List[str]] = None,
    timeout: Optional[float] = None,
    run_id: Optional[str] = None,
    authorized_tools: Optional[List[str]] = None
) -> str:
    print(f"DEBUG: call_model(model='{model}', run_id='{run_id}')")
    """
    Main entry point for LLM inference.
    Handles LiteRT (local), LiteLLM (cloud/local), and system prompt augmentation.
    """
    start_ts = datetime.datetime.now()
    log_data = {
        "ts": start_ts.isoformat(),
        "run_id": run_id,
        "model": model,
        "ok": False
    }

    # 1. OFFLINE KILL-SWITCH (PBR-001 Phase 3)
    if _offline_enabled() and not is_local_model(model):
        raise OfflineRefusal(
            f"BENNY_OFFLINE is set; refusing to call non-local model: {model}"
        )

    # 2. SYSTEM PROMPT AUGMENTATION
    workspace_id = "default"
    for msg in messages:
        if msg.get("role") == "system" and "workspace:" in msg.get("content", ""):
            import re
            match = re.search(r"workspace:\s*(\S+)", msg["content"])
            if match:
                workspace_id = match.group(1)
                break
    
    from ..governance.operating_manual import build_system_prompt_augmentation
    augmentation = build_system_prompt_augmentation(workspace_id, tools=authorized_tools)
    if augmentation:
        system_found = False
        for i, msg in enumerate(messages):
            if msg.get("role") == "system":
                messages[i]["content"] = augmentation + msg.get("content", "")
                system_found = True
                break
        if not system_found:
            messages.insert(0, {"role": "system", "content": augmentation})

    # 3. RESOLVE TIMEOUT
    actual_timeout = timeout
    if actual_timeout is None:
        env_timeout = os.environ.get("BENNY_LLM_TIMEOUT")
        if env_timeout:
            actual_timeout = float(env_timeout)
        else:
            try:
                from .workspace import load_manifest
                manifest = load_manifest(workspace_id)
                actual_timeout = getattr(manifest, "llm_timeout", 300.0)
            except Exception:
                actual_timeout = 300.0

    # 4. LITERT ROUTING (Local On-Device)
    if model.startswith("litert/"):
        try:
            model_id = model.split("/")[-1]
            engine = LiteRTEngine()
            response = await engine.generate(model_id, messages, temperature, max_tokens)
            log_data["ok"] = True
            log_data["provider"] = "litert"
            log_data["duration_ms"] = int((datetime.datetime.now() - start_ts).total_seconds() * 1000)
            log_llm_call(log_data)
            return response
        except Exception as e:
            log_data["error"] = str(e)
            log_llm_call(log_data)
            raise

    # 5. LOCAL EXECUTOR SHORT-CIRCUIT (PBR-001 Phase 5)
    # If the model is local, we bypass LiteLLM to ensure reliability
    if is_local_model(model):
        # Resolve to a specific provider/model string if it's a registry key
        config = get_model_config(model)
        provider = config.get("provider", "").lower()
        model_id = config.get("model", "")
        
        lookup_str = model
        if "/" not in model and provider:
            lookup_str = f"{provider}/{model_id}"
            
        executor = resolve_executor(lookup_str)
        print(f"DEBUG: is_local_model=True, lookup='{lookup_str}', executor={executor}")
        if executor:
            system_msg = None
            user_msg = ""
            for msg in messages:
                if msg.get("role") == "system":
                    system_msg = msg.get("content")
                elif msg.get("role") == "user":
                    user_msg = msg.get("content", "")
            
            try:
                content = await executor.generate(
                    prompt=user_msg, 
                    system=system_msg, 
                    temperature=temperature, 
                    max_tokens=max_tokens,
                    run_id=run_id,
                    timeout=actual_timeout or 300.0
                )
                
                log_data["ok"] = True
                log_data["provider"] = f"local/{executor.provider_name}"
                log_data["duration_ms"] = int((datetime.datetime.now() - start_ts).total_seconds() * 1000)
                try:
                    log_data["tokens_in"] = executor.count_tokens(user_msg + (system_msg or ""))
                    log_data["tokens_out"] = executor.count_tokens(content)
                except Exception: pass
                log_llm_call(log_data)
                return content
            except Exception as e:
                log_data["error"] = str(e)
                log_data["duration_ms"] = int((datetime.datetime.now() - start_ts).total_seconds() * 1000)
                log_llm_call(log_data)
                raise

    # 6. LITELLM DISPATCHER (Cloud)
    try:
        config = get_model_config(model)
        provider = config.get("provider", "openai").lower()
        litellm_model = config["model"]
        
        # Normalize local providers for LiteLLM if they somehow leaked here
        local_mapping = ["lemonade", "fastflowlm", "lmstudio", "ollama"]
        if provider in local_mapping or "base_url" in config:
            if not litellm_model.startswith("openai/"):
                litellm_model = f"openai/{litellm_model.split('/')[-1] if '/' in litellm_model else litellm_model}"
        
        kwargs = {
            "model": litellm_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "fallbacks": fallbacks or []
        }
        
        if "base_url" in config and config["base_url"]:
            kwargs["api_base"] = config["base_url"]
            kwargs["base_url"] = config["base_url"] # Double-bagging for OpenAI v1
            kwargs["custom_llm_provider"] = "openai" # Force OpenAI-compatible mode
        
        # Ensure api_key is set for local providers (LiteLLM requirement for openai/ prefix)
        if "api_key" in config and config["api_key"]:
            kwargs["api_key"] = config["api_key"]
        elif provider in local_mapping or "api_base" in kwargs:
            kwargs["api_key"] = "not-needed"

        if actual_timeout:
            kwargs["timeout"] = actual_timeout

        # DEBUG
        print(f"DEBUG: Calling model={model} via LiteLLM as {litellm_model} @ {kwargs.get('api_base')}")

        response = await _await_if_needed(_run_completion(**kwargs))

        if isinstance(response, str):
            log_data["ok"] = True
            log_data["provider"] = provider
            log_data["duration_ms"] = int((datetime.datetime.now() - start_ts).total_seconds() * 1000)
            log_llm_call(log_data)
            return response
        
        # Robust Content Extraction
        content = ""
        try:
            if hasattr(response, "choices") and len(response.choices) > 0:
                content = response.choices[0].message.content
            elif isinstance(response, dict) and "choices" in response and len(response["choices"]) > 0:
                choice = response["choices"][0]
                content = choice.get("message", {}).get("content", "") if isinstance(choice, dict) else getattr(choice, "message", choice).content
            elif isinstance(response, str):
                content = response
            elif isinstance(response, dict) and "message" in response:
                content = response["message"].get("content", str(response))
            else:
                content = str(response)
        except Exception as ce:
            logger.warning(f"Content extraction error: {ce}")
            content = str(response)

        # Usage Tracking
        try:
             usage = response.get("usage", {}) if hasattr(response, "get") else getattr(response, "usage", {})
             usage_data = usage if isinstance(usage, dict) else (usage.model_dump() if hasattr(usage, 'model_dump') else dict(usage))
             
             event_bus.emit(run_id, "resource_usage", {
                 "model": litellm_model,
                 "provider": provider,
                 "usage": usage_data,
                 "duration_ms": int((datetime.datetime.now() - start_ts).total_seconds() * 1000),
                 "timestamp": datetime.datetime.now().isoformat()
             })
             
             log_data["ok"] = True
             log_data["provider"] = provider
             log_data["tokens_in"] = usage_data.get("prompt_tokens", 0)
             log_data["tokens_out"] = usage_data.get("completion_tokens", 0)
             log_data["duration_ms"] = int((datetime.datetime.now() - start_ts).total_seconds() * 1000)
             log_llm_call(log_data)
        except Exception: pass

        return content

    except Exception as e:
        log_data["error"] = str(e)
        log_data["duration_ms"] = int((datetime.datetime.now() - start_ts).total_seconds() * 1000)
        log_llm_call(log_data)
        
        if fallbacks:
            for fallback in fallbacks:
                try:
                    return await call_model(fallback, messages, temperature, max_tokens, timeout=timeout, run_id=run_id)
                except: continue
        raise e
