"""AAMP-001 Phase 5 — AgentAmp API routes.

Endpoints
---------
  PUT /agentamp/eq
      Apply equalizer knobs to a SwarmManifest.  Validates allow-list,
      evaluates policy, signs the updated manifest, records a ledger entry,
      and returns the result (AAMP-F9, AAMP-F10, AAMP-SEC5, AAMP-COMP1,
      AAMP-COMP2).

Requirements covered
--------------------
  F9     PUT /agentamp/eq — path validation + sign + persist.
  F10    per-task picker via task_ids; knob locks via eq.json.
  SEC5   policy.evaluate(aamp.eq_write) called before any mutation.
  COMP1  ledger entry recorded on every write.
  COMP2  previous_signatures returned in response.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..agentamp.equalizer import (
    EqKnob,
    EqWriteResult,
    apply_eq_write,
)
from ..governance.policy import PolicyDeniedError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agentamp", tags=["agentamp"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class EqWriteRequest(BaseModel):
    """PUT /agentamp/eq request body (AAMP-F9, AAMP-F10)."""

    manifest: Dict[str, Any] = Field(
        ...,
        description="The SwarmManifest dict to edit.",
    )
    knobs: List[EqKnob] = Field(
        ...,
        description="List of equalizer knobs to apply.",
    )
    workspace: str = Field(default="default")
    persona: str = Field(
        default="aamp:user",
        description="Persona making the edit — forwarded to policy evaluation.",
    )
    task_ids: Optional[List[str]] = Field(
        default=None,
        description=(
            "When knobs include tasks[*].* paths, only these task IDs are "
            "updated (per-task picker — AAMP-F10)."
        ),
    )


class EqWriteResponse(BaseModel):
    """PUT /agentamp/eq response body."""

    updated_manifest: Dict[str, Any]
    new_signature: Dict[str, Any]
    previous_signatures: List[Dict[str, Any]]
    ledger_seq: int


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.put("/eq", response_model=EqWriteResponse, summary="Apply equalizer knobs (AAMP-F9)")
async def put_eq(body: EqWriteRequest) -> EqWriteResponse:
    """Apply equalizer knobs to a SwarmManifest.

    Validates each knob path against the allow-list, evaluates
    ``aamp.eq_write`` policy, signs the updated manifest, records a ledger
    entry, and returns the result with preserved previous signatures.

    Returns 422 if any knob path is not allow-listed.
    Returns 403 if policy denies the write.
    """
    benny_home = Path(os.environ.get("BENNY_HOME", Path.home() / ".benny"))

    try:
        result: EqWriteResult = apply_eq_write(
            body.manifest,
            body.knobs,
            workspace=body.workspace,
            benny_home=benny_home,
            persona=body.persona,
            task_ids=body.task_ids,
        )
    except ValueError as exc:
        # EqPathNotAllowed is a ValueError subclass
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PolicyDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error in PUT /agentamp/eq")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return EqWriteResponse(
        updated_manifest=result.updated_manifest,
        new_signature=result.new_signature,
        previous_signatures=result.previous_signatures,
        ledger_seq=result.ledger_seq,
    )
