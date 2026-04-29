"""LLM-driven Pypes manifest generator.

Mirrors the pattern of ``benny/graph/manifest_runner.plan_from_requirement``
but emits a ``PypesManifest`` (declarative DAG) instead of a swarm DAG.

Design rules
------------
* **Sandbox, not gate.** The generated manifest is a *draft* — the user
  reviews / edits the JSON before approving with ``--run`` or piping it
  into ``benny pypes run``. The planner never auto-executes a pipeline
  it just authored.
* **Always uses ``call_model()``.** Per ``CLAUDE.md`` rule #1 the planner
  must route through the offline-aware dispatcher, never raw LiteLLM.
* **Strict schema prompt.** The system prompt embeds an abridged JSON
  spec of ``PypesManifest`` plus the registered operation list so the
  model has everything it needs to emit a valid manifest in one shot.
* **Validation as a hard gate.** Output is parsed against the Pydantic
  ``PypesManifest`` model — if it fails, we surface the validation
  error so the caller can either retry, edit, or pick a stronger model.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

from pydantic import ValidationError

from .models import PypesManifest
from .registry import default_registry

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# PROMPT TEMPLATES
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """\
You are the Benny Pypes Planner — an expert at translating a plain-English
data-engineering requirement into a strictly-typed `PypesManifest` JSON
document.

A PypesManifest is a declarative, DAG-based transformation contract built on
the bronze -> silver -> gold medallion pattern with full CLP (Conceptual /
Logical / Physical) lineage. Every step is engine-agnostic and is dispatched
through the registered operation set.

# OUTPUT RULES (follow exactly)

1. Respond with **only one JSON object** — no commentary, no markdown fence,
   no leading text. Just the raw JSON for the PypesManifest.
2. The top-level object MUST include all required fields:
   `schema_version` ("1.0"), `kind` ("pypes_pipeline"), `id`, `name`,
   `workspace`, `governance`, `clp`, `steps`. Optional but recommended:
   `description`, `variables`, `reports`, `config`, `tags`.
3. Each step must include `id`, `engine` ("pandas" or "polars"), `stage`
   ("bronze" | "silver" | "gold"), `inputs` (list[str]), `outputs`
   (list[str]), and either `operations` or `sub_manifest_uri`.
4. Bronze steps load raw data and MUST set `source.uri` + `source.format`.
   Use `${data_dir}` (a manifest variable you also declare) — never an
   absolute filesystem path.
5. Step graph rules:
   - The first bronze step's `inputs` MUST be `[]`.
   - Every named upstream output (any string in `inputs`) must be produced
     by some other step's `outputs`.
   - Step ids are unique. Output names are unique across the whole manifest.
6. Add `post_validations` to silver and gold steps where it makes sense
   (`completeness`, `uniqueness`, `thresholds`, `row_count`, `move_analysis`).
7. Always emit at least one Gold step. Add a `reports` array for the user.
8. Use ONLY the registered operations listed below — never invent ones.

# REGISTERED OPERATIONS

{operations}

# REPORT KINDS

financial_risk | threshold_breaches | move_analysis | generic_summary

# MINIMAL TEMPLATE (shape, not content)

{example}
"""


_MINIMAL_EXAMPLE = {
    "schema_version": "1.0",
    "kind": "pypes_pipeline",
    "id": "example-id",
    "name": "Human-readable name",
    "description": "What this pipeline does in one sentence.",
    "workspace": "default",
    "governance": {
        "compliance_tags": ["BCBS-239"],
        "owner": "Risk_Team",
        "criticality": "medium",
        "pii_policy": "block",
    },
    "clp": {
        "conceptual": [{"name": "Trade", "description": "..."}],
        "logical": [
            {
                "entity": "Trade",
                "fields": [
                    {"name": "trade_id", "type": "string", "required": True},
                    {"name": "notional", "type": "float", "required": True},
                ],
            }
        ],
    },
    "variables": {"data_dir": "${benny_home}/data_in"},
    "steps": [
        {
            "id": "bronze_load",
            "stage": "bronze",
            "engine": "pandas",
            "inputs": [],
            "outputs": ["raw_trades"],
            "source": {"uri": "${data_dir}/trades.csv", "format": "csv"},
            "operations": [{"operation": "load", "params": {"source_id": "FRONT_OFFICE"}}],
            "post_validations": {"completeness": ["trade_id"], "uniqueness": ["trade_id"]},
        },
        {
            "id": "silver_clean",
            "stage": "silver",
            "engine": "pandas",
            "inputs": ["raw_trades"],
            "outputs": ["clean_trades"],
            "operations": [
                {"operation": "filter", "params": {"column": "status", "op": "==", "value": "completed"}},
                {"operation": "dedupe", "params": {"subset": ["trade_id"]}},
            ],
        },
        {
            "id": "gold_exposure",
            "stage": "gold",
            "engine": "pandas",
            "inputs": ["clean_trades"],
            "outputs": ["exposure"],
            "operations": [
                {
                    "operation": "aggregate",
                    "params": {
                        "group_by": ["counterparty_id"],
                        "metrics": {"total": "sum(notional)", "trades": "count(trade_id)"},
                    },
                }
            ],
        },
    ],
    "reports": [
        {
            "id": "exposure_report",
            "title": "Counterparty Exposure",
            "kind": "financial_risk",
            "source_step": "gold_exposure",
            "drill_down_by": ["counterparty_id"],
            "metrics": {"total": "sum(total)"},
            "format": "markdown",
            "top_n": 25,
        }
    ],
    "config": {"default_engine": "pandas", "max_concurrency": 2},
    "tags": ["pypes", "demo"],
}


_USER_PROMPT = """\
Requirement:
\"\"\"
{requirement}
\"\"\"

Workspace: `{workspace}`
Manifest id: `{manifest_id}`

Authoring notes:
{notes}

Now emit the PypesManifest as a single JSON object. No prose, no markdown
fence — just the JSON.
"""


# ---------------------------------------------------------------------------
# PUBLIC API
# ---------------------------------------------------------------------------


def plan_pypes_manifest(
    requirement: str,
    *,
    workspace: str = "default",
    model: Optional[str] = None,
    manifest_id: Optional[str] = None,
    extra_notes: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 8192,
) -> Tuple[PypesManifest, Dict[str, Any]]:
    """Generate (and validate) a `PypesManifest` from a plain-English requirement.

    Parameters
    ----------
    requirement
        The free-text spec to turn into a manifest.
    workspace
        Workspace name to bake into the manifest. Defaults to "default".
    model
        Specific model id to call. If ``None``, falls back to
        ``$BENNY_DEFAULT_MODEL`` then to ``benny.core.models.get_active_model``.
    manifest_id
        Optional fixed id. Defaults to ``pypes-<12hex>``.
    extra_notes
        Free-text appended to the user prompt — useful for steering
        ("must include a maturity-bucket gold step", etc.).

    Returns
    -------
    (manifest, meta)
        The validated PypesManifest and a metadata dict with the resolved
        model, the raw response text, and the token usage envelope.

    Raises
    ------
    RuntimeError
        On any LLM or validation failure — the caller decides whether to
        retry, surface the error, or fall back.
    """
    manifest_id = manifest_id or f"pypes-{uuid.uuid4().hex[:12]}"

    # Resolve model lazily so the user can override per-call.
    resolved_model = model or os.environ.get("BENNY_DEFAULT_MODEL")
    if not resolved_model:
        try:
            from ..core.models import get_active_model

            resolved_model = asyncio.run(get_active_model(workspace_id=workspace, role="chat"))
        except Exception as exc:
            log.debug("planner: get_active_model failed (%s)", exc)
    # ``get_active_model`` falls back to ``lemonade/default`` (a non-existent
    # model id) when its heartbeat URL math fails on ``/api/v1`` bases. Probe
    # Lemonade directly and pick a real chat-capable model id instead.
    if not resolved_model or (isinstance(resolved_model, str) and resolved_model.endswith("/default")):
        from .agent_chat import _first_chat_capable_lemonade_model, _first_ollama_model

        real = _first_chat_capable_lemonade_model()
        if real:
            resolved_model = f"lemonade/{real}"
        elif _first_ollama_model():
            resolved_model = f"ollama/{_first_ollama_model()}"
    if not resolved_model:
        # Conservative final default — local-first per Benny's portability guarantee.
        resolved_model = "ollama/llama3.1"

    # ``str.format`` treats every `{...}` as a placeholder. The embedded JSON
    # example contains literal tokens like ``${data_dir}`` whose `{...}` would
    # explode the formatter. Render placeholders manually instead.
    system_content = (
        _SYSTEM_PROMPT
        .replace("{operations}", "\n".join(f"- {n}" for n in default_registry.names()))
        .replace("{example}", json.dumps(_MINIMAL_EXAMPLE, indent=2))
    )
    system_msg = {"role": "system", "content": system_content}
    user_msg = {
        "role": "user",
        "content": _USER_PROMPT.format(
            requirement=requirement.strip(),
            workspace=workspace,
            manifest_id=manifest_id,
            notes=(extra_notes or "(none)").strip(),
        ),
    }

    # Thinking-mode models (Qwen3, QwQ, DeepSeek-R1) default to chain-of-thought
    # that consumes the entire token budget before any JSON is emitted. We
    # mitigate in three layers:
    #   (a) /no_think directive (honored by stock Qwen3 chat templates)
    #   (b) much larger token budget (some finetunes ignore /no_think)
    #   (c) assistant prefill — start the assistant turn with `{` so the
    #       model is forced to continue inside a JSON object instead of
    #       opening with an English preamble.
    is_thinking = _is_thinking_model(resolved_model)
    if is_thinking:
        user_msg = {
            "role": "user",
            "content": "/no_think\n" + user_msg["content"],
        }
        # Quadruple the budget — small finetunes that ignore /no_think still
        # need ~8–12k tokens of slack to ramble *and* then emit the manifest.
        max_tokens = max(max_tokens, 16384)

    raw = _call_llm(
        resolved_model,
        _with_prefill([system_msg, user_msg], is_thinking),
        temperature,
        max_tokens,
    )
    if is_thinking:
        # Re-attach the prefill so `_extract_json` sees a complete `{...}`.
        raw = "{" + raw if not raw.lstrip().startswith("{") else raw
    payload = _extract_json(raw)

    if payload is None:
        # Retry once with a brutally terse prompt that doesn't give the
        # model any room to philosophize. Drop the long schema spec — the
        # first attempt's reasoning burned through it without producing JSON
        # anyway, so a second pass with the same prompt would just repeat.
        retry_user = {
            "role": "user",
            "content": (
                "/no_think\n"
                "Output ONLY a single valid JSON object for a PypesManifest "
                f"with id={manifest_id!r} and workspace={workspace!r}. "
                "No prose, no markdown, no <think> tags, no explanation. "
                "Start your response with `{` and end with `}`. "
                "Required fields: schema_version, kind, id, name, workspace, "
                "governance, clp, steps. The first step must be stage=bronze "
                "with inputs=[] and a source.{uri,format}. "
                "Original requirement: " + requirement.strip()
            ),
        }
        raw = _call_llm(
            resolved_model,
            _with_prefill([system_msg, retry_user], True),
            temperature,
            max_tokens,
        )
        raw = "{" + raw if not raw.lstrip().startswith("{") else raw
        payload = _extract_json(raw)

    if payload is None:
        hint = ""
        if is_thinking:
            hint = (
                "\n\nHint: this model appears to ignore the JSON-only "
                "instruction and emit chain-of-thought instead. Try a "
                "stronger / non-thinking model (e.g. an Ollama llama3.1 "
                "variant or a cloud model) for the planner."
            )
        raise RuntimeError(
            f"Planner: LLM did not return valid JSON.{hint}\n"
            f"--- raw response (showing 4000 of {len(raw)} chars) ---\n"
            f"{raw[:4000]}"
        )

    # Force the manifest_id and workspace the caller asked for so the user can
    # safely diff between successive plan attempts. ``workspace`` is also
    # authoritative (the CLI flag wins over whatever the model invented).
    payload.setdefault("schema_version", "1.0")
    payload.setdefault("kind", "pypes_pipeline")
    payload["id"] = manifest_id
    payload["workspace"] = workspace

    try:
        manifest = PypesManifest.model_validate(payload)
    except ValidationError as exc:
        raise RuntimeError(
            "Planner: model output failed PypesManifest validation:\n"
            f"{exc}\n--- payload ---\n{json.dumps(payload, indent=2)[:4000]}"
        ) from exc

    meta = {
        "model": resolved_model,
        "manifest_id": manifest_id,
        "workspace": workspace,
        "raw_response_chars": len(raw),
    }
    return manifest, meta


# ---------------------------------------------------------------------------
# INTERNALS
# ---------------------------------------------------------------------------


def _call_llm(
    model: str,
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> str:
    """Run ``call_model()`` synchronously, regardless of caller event loop."""
    from ..core.models import call_model

    coro = call_model(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    try:
        return asyncio.run(coro)
    except RuntimeError as exc:
        # Fallback path when an outer loop is already running (rare from CLI).
        if "asyncio.run() cannot be called" in str(exc):
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
        raise


_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

# Trailing comma before `}` or `]` — invalid in standard JSON, common in
# LLM output. Captures the closing bracket so the substitution preserves it.
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")

# Fake "comment" keys some finetunes (notably Qwen3.5-FLM) invent because
# JSON has no native comments. Pattern: ``"_commented_out_<anything>": <value>``
# followed by an optional comma. We strip these key/value pairs entirely.
_COMMENT_KEY_RE = re.compile(
    r'"_commented_out_[^"]*"\s*:\s*'
    r'(?:"[^"]*"|true|false|null|-?\d+(?:\.\d+)?)'
    r'\s*,?',
    re.IGNORECASE,
)

# `// line comment` and `/* block */` — also occasionally hallucinated.
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)

# Models that need /no_think to suppress chain-of-thought preamble.
_THINKING_MODEL_PATTERNS = ("qwen3", "qwq", "deepseek-r1", "deepseek-r2")


def _is_thinking_model(model: str) -> bool:
    lm = model.lower()
    return any(p in lm for p in _THINKING_MODEL_PATTERNS)


def _with_prefill(messages: List[Dict[str, str]], enabled: bool) -> List[Dict[str, str]]:
    """Append an assistant prefill of ``{`` so the model continues inside a
    JSON object instead of opening with English prose.

    OpenAI-compatible servers (Lemonade, Ollama, vLLM) treat a trailing
    assistant message as a partial completion to continue from. The leading
    ``{`` becomes the first token the model sees on its turn — strongly
    biasing it toward completing the JSON literal rather than starting a
    sentence with "Okay, let's tackle...".
    """
    if not enabled:
        return messages
    return list(messages) + [{"role": "assistant", "content": "{"}]


def _repair_json(text: str) -> str:
    """Best-effort cleanup of LLM-emitted JSON quirks before strict parsing.

    Handles three patterns we've observed in the wild from local models:

    1. Trailing commas before ``}`` or ``]`` (some chat templates strip the
       final field-separator handling and the model leaves a stray comma).
    2. ``"_commented_out_..."`` keys — qwen3.5-FLM tries to "comment out"
       fields by inventing fake keys with ``true`` values.
    3. ``//`` and ``/* ... */`` comments — JSON5-style hallucinations.
    """
    text = _BLOCK_COMMENT_RE.sub("", text)
    text = _LINE_COMMENT_RE.sub("", text)
    text = _COMMENT_KEY_RE.sub("", text)
    # Run trailing-comma cleanup *after* comment removal so a deleted
    # `_commented_out_*` pair that left a dangling comma is still cleaned.
    text = _TRAILING_COMMA_RE.sub(r"\1", text)
    return text


def _try_parse(text: str) -> Optional[Dict[str, Any]]:
    """Try strict parse, fall back to repaired parse."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return json.loads(_repair_json(text))
    except json.JSONDecodeError:
        return None


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Be forgiving: strip optional ```json fences, find the outermost JSON object."""
    if not text:
        return None

    # Strip <think>...</think> blocks emitted by reasoning-mode models.
    text = _THINK_RE.sub("", text).strip()

    # 1. Direct parse (with repair fallback).
    payload = _try_parse(text)
    if payload is not None:
        return payload

    # 2. Triple-backtick fenced block.
    m = _FENCE_RE.search(text)
    if m:
        payload = _try_parse(m.group(1))
        if payload is not None:
            return payload

    # 3. Outermost { ... } slice — last resort for chatty models.
    #    Use the *last* closing brace so reasoning text before the JSON doesn't
    #    get included in the slice, and partial-truncated trailing prose is
    #    cut at the final complete brace.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return _try_parse(text[start : end + 1])
    return None
