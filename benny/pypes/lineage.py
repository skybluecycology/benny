"""OpenLineage emission for pypes runs.

Every step produces a START and COMPLETE event attached to the
``benny-pypes`` namespace in Marquez. A custom ``PypesStepFacet``
carries CLP context, the step's validation result summary, and the
checkpoint fingerprint so a drill-back from a Gold aggregate to its
Bronze source is always one query away.

Failures here never propagate — lineage is observability, not a gate.
If Marquez is down, the pipeline keeps running and we log a single
``[pypes.lineage]`` warning.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from .models import PipelineStep, PypesManifest, ValidationResult

log = logging.getLogger(__name__)

_NAMESPACE = "benny-pypes"


def _safe_import_client() -> Optional[Any]:
    try:
        from openlineage.client import OpenLineageClient  # type: ignore
        from openlineage.client.run import (  # type: ignore
            Dataset,
            Job,
            Run,
            RunEvent,
            RunState,
        )

        return {
            "client": OpenLineageClient.from_environment(),
            "Dataset": Dataset,
            "Job": Job,
            "Run": Run,
            "RunEvent": RunEvent,
            "RunState": RunState,
        }
    except Exception as exc:  # pragma: no cover — optional
        log.debug("pypes.lineage: openlineage unavailable (%s)", exc)
        return None


class LineageEmitter:
    """Best-effort OpenLineage emitter. Never raises."""

    def __init__(self, run_id: str, manifest: PypesManifest) -> None:
        self.run_id = run_id
        self.manifest = manifest
        self._bridge = _safe_import_client()
        self._step_run_ids: Dict[str, str] = {}

    # --- public API -------------------------------------------------------

    def run_start(self) -> None:
        self._emit_pipeline("START")

    def run_complete(self, status: str = "SUCCESS") -> None:
        self._emit_pipeline("COMPLETE" if status == "SUCCESS" else "FAIL")

    def step_start(self, step: PipelineStep) -> None:
        self._step_run_ids[step.id] = str(uuid.uuid4())
        self._emit_step(step, "START", validation=None)

    def step_complete(self, step: PipelineStep, validation: ValidationResult) -> None:
        self._emit_step(
            step,
            "COMPLETE" if validation.status != "FAIL" else "FAIL",
            validation=validation,
        )

    # --- internals --------------------------------------------------------

    def _emit_pipeline(self, state: str) -> None:
        if not self._bridge:
            return
        try:
            client = self._bridge["client"]
            Run = self._bridge["Run"]
            Job = self._bridge["Job"]
            RunEvent = self._bridge["RunEvent"]
            RunState = self._bridge["RunState"]
            event = RunEvent(
                eventType=getattr(RunState, state.upper(), RunState.COMPLETE),
                eventTime=_now(),
                run=Run(runId=self.run_id),
                job=Job(namespace=_NAMESPACE, name=f"pypes.{self.manifest.id}"),
                producer="benny.pypes",
                inputs=[],
                outputs=[],
            )
            client.emit(event)
        except Exception as exc:  # pragma: no cover
            log.warning("pypes.lineage: pipeline emit failed: %s", exc)

    def _emit_step(
        self,
        step: PipelineStep,
        state: str,
        validation: Optional[ValidationResult],
    ) -> None:
        if not self._bridge:
            return
        try:
            client = self._bridge["client"]
            Run = self._bridge["Run"]
            Job = self._bridge["Job"]
            Dataset = self._bridge["Dataset"]
            RunEvent = self._bridge["RunEvent"]
            RunState = self._bridge["RunState"]

            step_run_id = self._step_run_ids.get(step.id) or str(uuid.uuid4())
            self._step_run_ids[step.id] = step_run_id

            inputs: List[Any] = [
                Dataset(namespace=_NAMESPACE, name=name) for name in step.inputs
            ]
            outputs: List[Any] = [
                Dataset(namespace=_NAMESPACE, name=name) for name in step.outputs
            ]
            event = RunEvent(
                eventType=getattr(RunState, state.upper(), RunState.COMPLETE),
                eventTime=_now(),
                run=Run(
                    runId=step_run_id,
                    facets=_step_run_facets(self.manifest, step, validation, self.run_id),
                ),
                job=Job(
                    namespace=_NAMESPACE,
                    name=f"pypes.{self.manifest.id}.{step.id}",
                ),
                producer="benny.pypes",
                inputs=inputs,
                outputs=outputs,
            )
            client.emit(event)
        except Exception as exc:  # pragma: no cover
            log.warning("pypes.lineage: step emit failed (%s): %s", step.id, exc)


def _now() -> str:
    from datetime import datetime

    return datetime.utcnow().isoformat() + "Z"


def _step_run_facets(
    manifest: PypesManifest,
    step: PipelineStep,
    validation: Optional[ValidationResult],
    parent_run_id: str,
) -> Dict[str, Any]:
    facets: Dict[str, Any] = {
        "pypes_step": {
            "_producer": "benny.pypes",
            "_schemaURL": "https://benny.io/schemas/pypes-step.json",
            "parent_run_id": parent_run_id,
            "manifest_id": manifest.id,
            "stage": step.stage.value,
            "engine": step.engine.value,
            "deterministic": step.deterministic,
            "clp_binding": step.clp_binding or {},
        }
    }
    if validation is not None:
        facets["pypes_validation"] = {
            "_producer": "benny.pypes",
            "_schemaURL": "https://benny.io/schemas/pypes-validation.json",
            "status": validation.status,
            "row_count": validation.row_count,
            "column_count": validation.column_count,
            "fingerprint": validation.fingerprint,
            "checks": validation.checks[:50],
        }
    if manifest.governance.compliance_tags:
        facets["pypes_governance"] = {
            "_producer": "benny.pypes",
            "_schemaURL": "https://benny.io/schemas/pypes-governance.json",
            "compliance_tags": manifest.governance.compliance_tags,
            "owner": manifest.governance.owner,
            "criticality": manifest.governance.criticality,
        }
    return facets
