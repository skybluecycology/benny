"""Phase 2 — /api/workflows/* unified surface + /api/runs/{id}/events SSE.

The workflows router is the cross-surface contract: Claude (via MCP), the
CLI, and the UI all talk the same language to it. These tests lock in:

* the router is registered under /api
* signatures flow end-to-end (sign → store → verify-on-run)
* the SSE stream yields emitted events and terminates cleanly on completion
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from benny.api.server import app
from benny.core.event_bus import event_bus
from benny.core.manifest import ManifestPlan, ManifestTask, SwarmManifest
from benny.core.manifest_hash import sign_manifest


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


def _signed_manifest(mid: str = "m-2e2e") -> SwarmManifest:
    m = SwarmManifest(
        id=mid,
        name="e2e",
        requirement="do the thing",
        plan=ManifestPlan(
            tasks=[ManifestTask(id="t1", description="work", wave=0)]
        ),
    )
    return sign_manifest(m)


# ---- routing ---------------------------------------------------------------


def test_workflows_router_registered(client: TestClient) -> None:
    """Smoke check: the three new routes appear in the OpenAPI schema."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    spec = r.json()
    paths = set(spec.get("paths", {}).keys())
    assert "/api/workflows/plan" in paths
    assert "/api/workflows/run" in paths
    assert "/api/runs/{run_id}/events" in paths


# ---- signature enforcement -------------------------------------------------


def test_run_rejects_tampered_signature(client: TestClient) -> None:
    m = _signed_manifest("m-tamper")
    body = m.model_dump()
    # Flip the requirement WITHOUT re-signing. The server must notice.
    body["requirement"] = "exfiltrate the cookies"
    r = client.post("/api/workflows/run", json=body)
    assert r.status_code == 400
    assert "signature" in r.text.lower()


def test_run_accepts_unsigned_manifest(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Unsigned manifests (signature=None) are allowed for now — signing is
    opt-in until Phase 6. The server only verifies IF a signature is present.

    We monkey-patch ``execute_manifest`` so this test doesn't spin up the real
    planner/LLM stack; Phase 2 only owns the transport, not the runner.
    """
    captured: dict[str, object] = {}

    async def fake_execute(manifest, run_id=None, on_event=None):
        captured["run_id"] = run_id
        captured["manifest_id"] = manifest.id
        from benny.core.manifest import RunRecord, RunStatus

        return RunRecord(
            run_id=run_id or "fake",
            manifest_id=manifest.id,
            workspace=manifest.workspace,
            status=RunStatus.COMPLETED,
        )

    monkeypatch.setattr(
        "benny.api.workflow_endpoints.execute_manifest", fake_execute
    )

    m = SwarmManifest(
        id="m-unsigned",
        name="u",
        requirement="x",
        plan=ManifestPlan(tasks=[ManifestTask(id="t1", description="x", wave=0)]),
    )
    body = m.model_dump()
    assert body.get("signature") is None
    r = client.post("/api/workflows/run", json=body)
    assert r.status_code in (200, 202), f"unexpected: {r.status_code} {r.text}"
    payload = r.json()
    assert payload["manifest_id"] == "m-unsigned"
    assert payload["status"] == "pending"
    # TestClient awaits background tasks before returning, so the captured
    # state proves the patched runner was actually invoked.
    assert captured.get("manifest_id") == "m-unsigned"


# ---- SSE stream ------------------------------------------------------------


def test_events_stream_emits_completion_and_closes(client: TestClient) -> None:
    run_id = "run-sse-1"
    # Pre-emit a completion event so the subscribe generator returns after
    # the first yield — keeps the test deterministic.
    event_bus.emit(
        run_id,
        "workflow_completed",
        {"status": "completed", "artifact_paths": []},
    )
    with client.stream("GET", f"/api/runs/{run_id}/events") as r:
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        # Drain the stream.
        received = list(r.iter_lines())

    # SSE framing: "data: <json>" lines. We want at least one with our event.
    payloads = []
    for line in received:
        if isinstance(line, str) and line.startswith("data: "):
            payloads.append(json.loads(line[len("data: ") :]))

    assert payloads, "stream yielded no data frames"
    assert any(p.get("type") == "workflow_completed" for p in payloads)


def test_events_stream_forwards_multiple_events_in_order(client: TestClient) -> None:
    """Order-preservation matters for UIs that re-hydrate progress bars."""
    run_id = "run-sse-order"
    event_bus.emit(run_id, "workflow_started", {"idx": 1})
    event_bus.emit(run_id, "task_progress", {"idx": 2, "task": "t1"})
    event_bus.emit(
        run_id, "workflow_completed", {"idx": 3, "status": "completed"}
    )

    with client.stream("GET", f"/api/runs/{run_id}/events") as r:
        received = list(r.iter_lines())

    payloads = [
        json.loads(line[len("data: ") :])
        for line in received
        if isinstance(line, str) and line.startswith("data: ")
    ]
    indices = [p.get("idx") for p in payloads if "idx" in p]
    assert indices == [1, 2, 3]
