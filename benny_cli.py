"""
Benny CLI — declarative manifest driver.

Usage:
    benny plan "Generate a 10k-word analyst report comparing X and Y" \\
        --workspace default --output report.md --word-count 10000 \\
        --save manifest.json

    benny run manifest.json

    benny runs ls [--manifest MANIFEST_ID]
    benny runs show RUN_ID

    benny migrate --from <path> [--to $BENNY_HOME] [--apply]

Design: this is the user's main interface to the plan-then-run loop. The
same JSON that appears in `manifest.json` is what the UI canvas renders
and what past runs reference. Share the file -> share the workflow.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from benny.core.manifest import (
    InputSpec,
    ManifestConfig,
    OutputFormat,
    OutputSpec,
    SwarmManifest,
)


# =============================================================================
# COMMANDS
# =============================================================================


async def cmd_plan(args: argparse.Namespace) -> int:
    from benny.core.models import get_active_model
    from benny.graph.manifest_runner import plan_from_requirement
    from benny.persistence import run_store

    output_spec = OutputSpec(
        files=args.output or [],
        format=OutputFormat(args.format) if args.format else OutputFormat.MARKDOWN,
        word_count_target=args.word_count,
        spec=args.spec or "",
    )

    # Resolve model from manager if not provided
    model = args.model
    if not model:
        model = await get_active_model(args.workspace)

    print(f"[plan] requirement: {args.requirement[:120]}{'...' if len(args.requirement) > 120 else ''}")
    print(f"[plan] workspace={args.workspace} model={model} max_concurrency={args.max_concurrency}")
    if args.input:
        print(f"[plan] inputs: {args.input}")
    if output_spec.word_count_target:
        print(f"[plan] target: {output_spec.word_count_target} words -> {output_spec.format.value}")

    manifest = await plan_from_requirement(
        requirement=args.requirement,
        workspace=args.workspace,
        model=model,
        input_files=args.input or [],
        output_spec=output_spec,
        max_concurrency=args.max_concurrency,
        max_depth=args.max_depth,
        name=args.name,
    )
    manifest.inputs = InputSpec(files=args.input or [])

    if args.save:
        run_store.save_manifest(manifest)
        print(f"[plan] saved to run_store id={manifest.id}")

    out_path = Path(args.out) if args.out else None
    rendered = manifest.model_dump_json(indent=2)
    if out_path:
        out_path.write_text(rendered, encoding="utf-8")
        print(f"[plan] wrote manifest -> {out_path}")
    else:
        print(rendered)

    print(f"[plan] tasks={len(manifest.plan.tasks)} waves={len(manifest.plan.waves)}")
    if manifest.plan.ascii_dag:
        print("\n" + manifest.plan.ascii_dag)
    return 0


async def cmd_run(args: argparse.Namespace) -> int:
    from benny.graph.manifest_runner import execute_manifest
    from benny.persistence import run_store

    manifest = _load_manifest(args.manifest)

    # Persist so runs reference a real, resolvable manifest id.
    run_store.save_manifest(manifest)

    print(f"[run] manifest_id={manifest.id} name={manifest.name!r}")
    print(f"[run] tasks={len(manifest.plan.tasks)} workspace={manifest.workspace}")

    record = await execute_manifest(manifest)
    print(f"[run] run_id={record.run_id} status={record.status.value}")
    if record.duration_ms:
        print(f"[run] duration={record.duration_ms}ms")
    if record.errors:
        print(f"[run] errors: {record.errors}", file=sys.stderr)
    if record.artifact_paths:
        print(f"[run] artifacts: {record.artifact_paths}")
    if record.governance_url:
        print(f"[run] lineage: {record.governance_url}")

    if args.json:
        print(record.model_dump_json(indent=2))
    return 0 if record.status.value in ("completed", "partial_success") else 1


def cmd_runs_ls(args: argparse.Namespace) -> int:
    from benny.persistence import run_store

    recs = run_store.list_runs(
        manifest_id=args.manifest, workspace=args.workspace, limit=args.limit
    )
    if not recs:
        print("[runs] (none)")
        return 0

    print(f"{'RUN ID':<20} {'MANIFEST':<24} {'STATUS':<12} {'STARTED':<26} DURATION")
    for r in recs:
        dur = f"{r.duration_ms}ms" if r.duration_ms else "-"
        started = r.started_at or "-"
        print(f"{r.run_id:<20} {r.manifest_id[:22]:<24} {r.status.value:<12} {started:<26} {dur}")
    return 0


def cmd_runs_show(args: argparse.Namespace) -> int:
    from benny.persistence import run_store

    rec = run_store.get_run(args.run_id)
    if not rec:
        print(f"[runs] not found: {args.run_id}", file=sys.stderr)
        return 1
    print(rec.model_dump_json(indent=2))
    return 0


def cmd_manifests_ls(args: argparse.Namespace) -> int:
    from benny.persistence import run_store

    ms = run_store.list_manifests()
    if not ms:
        print("[manifests] (none)")
        return 0

    print(f"{'ID':<32} {'NAME':<40} TASKS")
    for m in ms:
        print(f"{m.id[:30]:<32} {m.name[:38]:<40} {len(m.plan.tasks)}")
    return 0


async def cmd_enrich(args: argparse.Namespace) -> int:  # noqa: C901 — intentionally long; each section is a clear phase
    """Knowledge enrichment pipeline with Rich live display, OpenLineage events,
    local run folder, and GDPR-compliant audit trail.

    Executes 7 tasks across 5 waves via direct API calls so each task gets its
    own spinner, elapsed time, and lineage event — no LLM planning needed.

    Usage:
        benny enrich --workspace c5_test --src src/dangpy --out plans/enrich.json
        benny enrich --workspace c5_test --src src/dangpy --run
        benny enrich --workspace c5_test --src src/dangpy --json
    """
    import hashlib
    import os
    import time
    import uuid
    from datetime import datetime, timezone

    import httpx
    from rich import box
    from rich.console import Console, Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text

    from benny.core.manifest import ManifestEdge, ManifestPlan, ManifestTask
    from benny.core.manifest_hash import sign_manifest
    from benny.governance.audit import emit_governance_event
    from benny.governance.lineage import BennyLineageClient

    console = Console()

    API_BASE = os.environ.get("BENNY_API_URL", "http://127.0.0.1:8005")
    API_KEY  = os.environ.get("BENNY_API_KEY",  "benny-mesh-2026-auth")
    _H = {"X-Benny-API-Key": API_KEY}
    _HJ = {**_H, "Content-Type": "application/json"}

    # ─── 1. Resolve model ────────────────────────────────────────────────────
    model = args.model
    if not model:
        try:
            from benny.core.models import get_active_model
            model = await get_active_model(args.workspace)
        except Exception:
            model = "lemonade/qwen3-tk-4b-FLM"

    run_it   = args.run_after or args.json
    src_path = args.src.rstrip("/")
    ts       = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    manifest_id = f"enrich-{args.workspace}-{ts}"
    run_id      = uuid.uuid4().hex[:12]
    started_at  = datetime.now(timezone.utc)

    # ─── 2. Build manifest ───────────────────────────────────────────────────
    tasks = [
        ManifestTask(
            id="pdf_extract",
            description="[DETERMINISTIC] Convert staging/ PDFs/docs to Markdown via Docling.",
            skill_hint="extract_pdf",
            deterministic=True,
            skill_args={"src_dir": "staging/"},
            wave=0, complexity="medium", node_type="task",
            files_touched=["staging/"],
        ),
        ManifestTask(
            id="code_scan",
            description=f"[DETERMINISTIC] Tree-Sitter scan of {src_path}/ -> Neo4j code graph.",
            skill_hint="code_scan",
            deterministic=True,
            skill_args={"root_dir": src_path, "deep_scan": True},
            wave=0, complexity="high", node_type="task",
            files_touched=[f"{src_path}/"],
        ),
        ManifestTask(
            id="rag_ingest",
            description="[DETERMINISTIC] Chunk + embed Markdown -> ChromaDB.",
            skill_hint="rag_ingest",
            deterministic=True,
            skill_args={"deep_synthesis": False, "strategy": args.strategy},
            dependencies=["pdf_extract"],
            wave=1, complexity="medium", node_type="task",
        ),
        ManifestTask(
            id="deep_synthesis",
            description="[AGENTIC] Extract knowledge triples (Concept -> Concept) -> Neo4j REL edges.",
            skill_hint="rag_ingest",
            assigned_model=model,
            dependencies=["rag_ingest"],
            wave=2, complexity="high", node_type="task",
        ),
        ManifestTask(
            id="semantic_correlate",
            description=(
                f"[DETERMINISTIC] Neural Spark semantic correlation -> CORRELATES_WITH edges. "
                f"threshold={args.threshold} strategy={args.strategy}."
            ),
            skill_hint="kg3d_ingest",          # registered skill that calls run_full_correlation_suite
            deterministic=True,
            skill_args={"threshold": args.threshold, "strategy": args.strategy},
            dependencies=["code_scan", "deep_synthesis"],
            wave=3, complexity="medium", node_type="task",
        ),
        ManifestTask(
            id="validate_enrichment",
            description="[DETERMINISTIC] Assert CORRELATES_WITH edges > 0 in Neo4j.",
            skill_hint="validate_enrichment",
            deterministic=True,
            skill_args={},
            dependencies=["semantic_correlate"],
            wave=4, complexity="low", node_type="task",
        ),
        ManifestTask(
            id="generate_report",
            description="[AGENTIC] Write enrichment_report.md with statistics and concept-to-code mapping.",
            skill_hint="rag_ingest",
            assigned_model=model,
            dependencies=["validate_enrichment"],
            wave=4, complexity="medium", node_type="output",
            files_touched=["data_out/enrichment_report.md"],
        ),
    ]

    edges = [
        ManifestEdge(id="e_pdf_rag",    source="pdf_extract",        target="rag_ingest",         label="extracted markdown", animated=True),
        ManifestEdge(id="e_rag_synth",  source="rag_ingest",         target="deep_synthesis",      label="indexed corpus",     animated=True),
        ManifestEdge(id="e_code_corr",  source="code_scan",          target="semantic_correlate",  label="code entities",      animated=True),
        ManifestEdge(id="e_synth_corr", source="deep_synthesis",     target="semantic_correlate",  label="knowledge triples",  animated=True),
        ManifestEdge(id="e_corr_val",   source="semantic_correlate", target="validate_enrichment", label="CORRELATES_WITH",    animated=True),
        ManifestEdge(id="e_val_report", source="validate_enrichment",target="generate_report",     label="validated",          animated=True),
    ]

    plan = ManifestPlan(
        tasks=tasks,
        edges=edges,
        waves=[
            ["pdf_extract", "code_scan"],
            ["rag_ingest"],
            ["deep_synthesis"],
            ["semantic_correlate"],
            ["validate_enrichment", "generate_report"],
        ],
        ascii_dag=(
            "pdf_extract --+\n"
            "              +--> rag_ingest --> deep_synthesis --+\n"
            "              |                                    +--> semantic_correlate --> validate_enrichment --> generate_report\n"
            "code_scan ----+--------------------------------------------+\n"
        ),
    )

    manifest = SwarmManifest(
        id=manifest_id,
        name=f"Knowledge Enrichment \u2014 {args.workspace}",
        description="Knowledge enrichment pipeline: extract \u2192 ingest \u2192 synthesise \u2192 correlate \u2192 validate \u2192 report.",
        requirement=(
            "Build the knowledge enrichment overlay for the Studio ENRICH toggle: "
            f"scan source code in {src_path}/, extract knowledge triples from ingested documents, "
            "and create CORRELATES_WITH edges linking concepts to code symbols."
        ),
        workspace=args.workspace,
        inputs=InputSpec(
            files=["staging/", f"{src_path}/"],
            context={
                "src_path": src_path,
                "correlation_threshold": args.threshold,
                "correlation_strategy": args.strategy,
            },
        ),
        outputs=OutputSpec(
            files=["data_out/enrichment_report.md"],
            format=OutputFormat.MARKDOWN,
            spec="Enrichment summary: concept count, code entity count, CORRELATES_WITH edges, confidence distribution.",
        ),
        plan=plan,
        config=ManifestConfig(
            model=model,
            max_concurrency=2,
            max_depth=3,
            skills_allowed=["extract_pdf", "rag_ingest", "code_scan", "kg3d_ingest", "validate_enrichment"],
        ),
        tags=["enrichment", "code-analysis", "knowledge-graph"],
        metadata={
            "src_path": src_path,
            "correlation_threshold": args.threshold,
            "correlation_strategy": args.strategy,
        },
    )
    sign_manifest(manifest)
    rendered = manifest.model_dump_json(indent=2)

    # ─── 3. Write --out path ─────────────────────────────────────────────────
    out_path = Path(args.out) if args.out else None
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")

    # Plan-only mode: show a nice panel and exit
    if not run_it:
        plan_tbl = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan", expand=True)
        plan_tbl.add_column("Wave", justify="center", width=5)
        plan_tbl.add_column("Task ID", min_width=22)
        plan_tbl.add_column("Type", width=14)
        plan_tbl.add_column("Skill hint", width=22)
        plan_tbl.add_column("Description", style="dim")
        for t in tasks:
            tag = "[magenta]AGENTIC[/]" if "[AGENTIC]" in t.description else "[blue]DETERMINISTIC[/]"
            plan_tbl.add_row(str(t.wave), t.id, tag, t.skill_hint or "", t.description[:60])
        console.print()
        console.print(Panel(
            plan_tbl,
            title=f"[bold cyan]Knowledge Enrichment Plan[/]  [dim]{args.workspace}[/]",
            border_style="cyan", padding=(0, 2),
        ))
        if out_path:
            console.print(f"  [dim]Manifest written \u2192[/] {out_path}")
        console.print(f"  [dim]Run with:[/] benny enrich --workspace {args.workspace} --src {args.src} --run\n")
        return 0

    # ─── 4. Create local run folder ──────────────────────────────────────────
    benny_home = Path(os.environ.get("BENNY_HOME", "."))
    run_folder = benny_home / "workspace" / args.workspace / "runs" / f"enrich-{run_id}"
    run_folder.mkdir(parents=True, exist_ok=True)

    (run_folder / "manifest.json").write_text(rendered, encoding="utf-8")

    gdpr: Dict[str, Any] = {
        "schema": "GDPR-data-processing-record-v1",
        "data_controller": "Benny Platform Operator",
        "processing_purpose": (
            "Knowledge graph enrichment — semantic correlation of architecture "
            "documents to source code symbols for developer tooling."
        ),
        "legal_basis": "Legitimate interests (Article 6(1)(f) GDPR) — technical system analysis",
        "data_categories": [
            "Source code file paths, class names, function names (no personal data)",
            "Architecture document text fragments (no personal data)",
            "Graph relationship metadata (no personal data)",
        ],
        "personal_data": False,
        "ai_disclosure": f"AI model used: {model}",
        "retention_days": 90,
        "right_to_erasure": (
            f"Delete run folder: {run_folder}; "
            f"run Cypher: MATCH (c:Concept)-[r:CORRELATES_WITH]->(e:CodeEntity {{workspace: '{args.workspace}'}}) DELETE r"
        ),
        "generated_at": started_at.isoformat(),
        "run_id": run_id,
        "manifest_id": manifest_id,
        "workspace": args.workspace,
    }
    (run_folder / "GDPR_notice.json").write_text(
        json.dumps(gdpr, indent=2, default=str), encoding="utf-8"
    )

    # ─── 5. Header panel ─────────────────────────────────────────────────────
    console.print()
    console.print(Panel.fit(
        f"[bold white]Workspace[/]    [cyan]{args.workspace}[/]\n"
        f"[bold white]Source path[/]  [cyan]{src_path}/[/]\n"
        f"[bold white]Model[/]        [cyan]{model}[/]\n"
        f"[bold white]Threshold[/]    [cyan]{args.threshold}[/]  "
        f"[dim]strategy={args.strategy}[/]\n"
        f"[bold white]Run folder[/]   [dim]{run_folder}[/]\n"
        f"[bold white]Lineage[/]      [link=http://localhost:3010]http://localhost:3010[/link]  "
        f"[dim](Marquez)[/]",
        title="[bold cyan] Benny Knowledge Enrichment [/]",
        border_style="cyan",
        padding=(0, 2),
    ))
    console.print()

    # ─── 5b. Pre-flight: verify API is reachable ────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=5.0) as _hc:
            _probe = await _hc.get(f"{API_BASE}/api/system/pulse", headers=_H)
            _probe.raise_for_status()
    except Exception as _probe_err:
        console.print(
            f"\n[bold red]✗  Cannot reach Benny API at {API_BASE}[/]\n"
            f"   [red]{type(_probe_err).__name__}: {_probe_err}[/]\n\n"
            f"   [dim]Start the server first:[/]\n"
            f"   [bold cyan]benny up --home $BENNY_HOME[/]\n"
        )
        return 1

    # ─── 6. Start OpenLineage workflow ───────────────────────────────────────
    lineage = BennyLineageClient()
    try:
        lineage.start_workflow(
            workflow_id=manifest_id,
            workflow_name=f"Knowledge Enrichment \u2014 {args.workspace}",
            workspace=args.workspace,
            inputs=["staging/", f"{src_path}/"],
            outputs=["data_out/enrichment_report.md"],
            metadata={"run_id": run_id, "model": model, "threshold": args.threshold},
        )
    except Exception:
        pass  # lineage is best-effort; never crash the pipeline

    # ─── 7. Task status state ────────────────────────────────────────────────
    TASK_DEFS = [
        {"id": "pdf_extract",        "wave": 0, "desc": "Convert staging/ PDFs \u2192 Markdown (Docling)"},
        {"id": "code_scan",          "wave": 0, "desc": "Tree-Sitter code scan \u2192 Neo4j graph"},
        {"id": "rag_ingest",         "wave": 1, "desc": "Chunk + embed \u2192 ChromaDB"},
        {"id": "deep_synthesis",     "wave": 2, "desc": "Extract knowledge triples \u2192 Neo4j REL"},
        {"id": "semantic_correlate", "wave": 3, "desc": "Neural Spark \u2192 CORRELATES_WITH edges"},
        {"id": "validate_enrichment","wave": 4, "desc": "Assert CORRELATES_WITH edges exist"},
        {"id": "generate_report",    "wave": 4, "desc": "Write enrichment_report.md"},
    ]

    task_status:  Dict[str, str]             = {t["id"]: "pending"  for t in TASK_DEFS}
    task_elapsed: Dict[str, Optional[float]] = {t["id"]: None       for t in TASK_DEFS}
    task_note:    Dict[str, str]             = {t["id"]: ""         for t in TASK_DEFS}
    task_error:   Dict[str, Optional[str]]   = {t["id"]: None       for t in TASK_DEFS}

    def _make_table() -> Table:
        tbl = Table(
            box=box.ROUNDED, show_header=True, header_style="bold cyan",
            expand=True, border_style="dim",
        )
        tbl.add_column("W", style="dim cyan", width=3, justify="center")
        tbl.add_column("Task", style="bold white", min_width=22)
        tbl.add_column("Status", width=14, justify="center")
        tbl.add_column("Description", style="dim white", ratio=1)
        tbl.add_column("Elapsed", width=8, justify="right")
        tbl.add_column("Notes", style="dim", width=22, no_wrap=True)
        for t in TASK_DEFS:
            st = task_status[t["id"]]
            el = task_elapsed[t["id"]]
            el_str = f"{el:.1f}s" if el is not None else "-"
            st_cell: Text
            if   st == "pending":  st_cell = Text("\u25cb  pending",  style="dim")
            elif st == "running":  st_cell = Text("\u25c9  running",  style="bold yellow")
            elif st == "done":     st_cell = Text("\u2713  done",     style="bold green")
            elif st == "skipped":  st_cell = Text("\u2296  skipped",  style="dim yellow")
            else:                  st_cell = Text("\u2717  failed",   style="bold red")
            tbl.add_row(str(t["wave"]), t["id"], st_cell, t["desc"], el_str, task_note[t["id"]])
        return tbl

    # ─── 8. Per-task API executor ────────────────────────────────────────────
    # Shared state used to pass discovered artefacts between tasks
    # (e.g. pdf_extract finds nested PDFs; rag_ingest uses them)
    task_results: Dict[str, Any] = {}

    async def _run_task(tid: str) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=360.0) as client:
            if tid == "pdf_extract":
                # Recursive scan finds files at ANY depth (handles data_in/staging/*.pdf)
                rr = await client.get(
                    f"{API_BASE}/api/files/recursive-scan", headers=_H,
                    params={"workspace": args.workspace}, timeout=30.0,
                )
                rr.raise_for_status()
                all_files = rr.json().get("files", [])

                def _rel_to(prefix: str, p: str) -> Optional[str]:
                    """If path starts with prefix (Windows or POSIX), return it stripped."""
                    for sep in ("\\", "/"):
                        head = f"{prefix}{sep}"
                        if p.startswith(head):
                            return p[len(head):].replace("\\", "/")
                    return None

                # Collect ingestible docs already under data_in/ (any depth)
                data_in_ingestible: List[str] = []       # relative to data_in/
                data_in_md:         List[str] = []
                staging_top:        List[str] = []       # top-level staging/
                for f in all_files:
                    path = f.get("path", "") or ""
                    name = f.get("name", "") or ""
                    ext  = name.lower().rsplit(".", 1)[-1] if "." in name else ""
                    rel = _rel_to("data_in", path)
                    if rel is not None:
                        if ext in ("pdf", "docx", "pptx", "txt", "html"):
                            data_in_ingestible.append(rel)
                        if ext == "md":
                            data_in_md.append(rel)
                    elif _rel_to("staging", path) is not None:
                        if ext in ("pdf", "docx", "pptx", "txt", "html", "md"):
                            staging_top.append(_rel_to("staging", path) or name)

                # Case A: top-level staging/ has raw docs → flag for later handling
                if staging_top:
                    task_results["staging_files"] = staging_top
                    return {
                        "staging_files": len(staging_top),
                        "files":         staging_top[:5],
                        "status":        "converted",
                    }

                # Case B: markdown already in data_in/ (any depth) → nothing to do
                if data_in_md and not data_in_ingestible:
                    return {
                        "md_files": len(data_in_md),
                        "status":   "already_converted",
                    }

                # Case C: ingestible docs in data_in/ (pdfs in staging/ subdir, etc.)
                # Hand them to rag_ingest via shared task_results
                if data_in_ingestible:
                    task_results["pdf_files"] = data_in_ingestible
                    return {
                        "pdf_count": len(data_in_ingestible),
                        "paths":     data_in_ingestible[:3],
                        "status":    "pdfs_found",
                    }

                # Case D: ChromaDB already has chunks from a previous run
                try:
                    rs = await client.get(
                        f"{API_BASE}/api/rag/status", headers=_H,
                        params={"workspace": args.workspace}, timeout=10.0,
                    )
                    if rs.status_code == 200:
                        chunks = rs.json().get("total_chunks", 0)
                        if chunks > 0:
                            return {
                                "status":     "already_ingested",
                                "rag_chunks": chunks,
                            }
                except Exception:
                    pass

                raise RuntimeError(
                    "No ingestible docs found anywhere under the workspace and "
                    "ChromaDB is empty — upload architecture docs first "
                    "(Studio → Notebook → Upload)."
                )

            elif tid == "code_scan":
                # Start the background Tree-Sitter scan (returns immediately)
                r = await client.post(
                    f"{API_BASE}/api/graph/code/generate", headers=_HJ,
                    json={"workspace": args.workspace, "root_dir": src_path},
                    timeout=30.0,
                )
                r.raise_for_status()
                scan_run_id = r.json().get("run_id", "")
                # Poll GET /api/graph/code until nodes appear (max 6 min, 5 s intervals)
                for _attempt in range(72):
                    await asyncio.sleep(5)
                    try:
                        gr = await client.get(
                            f"{API_BASE}/api/graph/code", headers=_H,
                            params={"workspace": args.workspace},
                            timeout=10.0,
                        )
                        if gr.status_code == 200:
                            gdata = gr.json()
                            nodes = gdata.get("nodes", [])
                            if nodes:
                                return {
                                    "code_nodes": len(nodes),
                                    "run_id":     scan_run_id,
                                    "status":     "complete",
                                }
                    except Exception:
                        pass
                # Scan accepted but we couldn't confirm nodes yet — proceed optimistically
                return {"status": "scan_started", "run_id": scan_run_id}

            elif tid == "rag_ingest":
                # If pdf_extract found nested docs, pass their explicit paths
                # (otherwise /api/rag/ingest only scans data_in/*.* at top level)
                pdf_files = task_results.get("pdf_files")
                body: Dict[str, Any] = {
                    "workspace":      args.workspace,
                    "deep_synthesis": False,
                }
                if pdf_files:
                    body["files"] = pdf_files
                r = await client.post(
                    f"{API_BASE}/api/rag/ingest", headers=_HJ, json=body,
                )
                r.raise_for_status()
                return r.json()

            elif tid == "deep_synthesis":
                r = await client.post(
                    f"{API_BASE}/api/graph/synthesize", headers=_HJ,
                    json={"workspace": args.workspace, "model": model},
                )
                r.raise_for_status()
                return r.json()

            elif tid == "semantic_correlate":
                r = await client.post(
                    f"{API_BASE}/api/rag/correlate", headers=_H,
                    params={"workspace": args.workspace, "threshold": args.threshold},
                )
                r.raise_for_status()
                return r.json()

            elif tid == "validate_enrichment":
                r = await client.get(
                    f"{API_BASE}/api/graph/code/lod", headers=_H,
                    params={"workspace": args.workspace, "tier": 1},
                )
                r.raise_for_status()
                data = r.json()
                corr = [e for e in data.get("edges", []) if e.get("type") == "CORRELATES_WITH"]
                if not corr:
                    raise RuntimeError(
                        f"Zero CORRELATES_WITH edges found in workspace '{args.workspace}'. "
                        "Check that deep_synthesis and semantic_correlate completed successfully."
                    )
                return {"correlates_with_count": len(corr)}

            elif tid == "generate_report":
                # Pull graph stats then write a rich Markdown report
                r = await client.get(
                    f"{API_BASE}/api/graph/stats", headers=_H,
                    params={"workspace": args.workspace},
                )
                r.raise_for_status()
                stats = r.json()
                ntypes = stats.get("node_types", {})
                rtypes = stats.get("relationship_types", {})
                corr_cnt    = rtypes.get("CORRELATES_WITH", 0)
                concept_cnt = ntypes.get("Concept", 0)
                code_cnt    = ntypes.get("CodeEntity", ntypes.get("Function", 0) + ntypes.get("Class", 0))

                report = "\n".join([
                    "# Knowledge Enrichment Report",
                    "",
                    f"**Generated**: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}  ",
                    f"**Workspace**: `{args.workspace}`  ",
                    f"**Model**: `{model}`  ",
                    f"**Threshold**: `{args.threshold}`  ",
                    f"**Strategy**: `{args.strategy}`  ",
                    "",
                    "## Graph Statistics",
                    "",
                    "| Metric | Count |",
                    "|--------|------:|",
                    f"| Concept nodes | {concept_cnt} |",
                    f"| CodeEntity nodes | {code_cnt} |",
                    f"| `CORRELATES_WITH` edges | {corr_cnt} |",
                    "",
                    "## Summary",
                    "",
                    f"{corr_cnt} semantic correlation edge(s) now link {concept_cnt} architecture "
                    f"concept(s) to {code_cnt} code entity node(s) in workspace `{args.workspace}`.",
                    "",
                    "Enable the **ENRICH** toggle in Benny Studio \u2192 Code Graph to see amber "
                    "dashed overlays connecting architecture concepts to source code symbols.",
                    "",
                    "## Run Provenance",
                    "",
                    f"- Run ID: `{run_id}`",
                    f"- Manifest ID: `{manifest_id}`",
                    f"- Run folder: `{run_folder}`",
                    f"- Lineage (Marquez): http://localhost:3010",
                    f"- GDPR notice: `{run_folder / 'GDPR_notice.json'}`",
                    "",
                    "## All Node / Edge Counts",
                    "",
                    "| Type | Count |",
                    "|------|------:|",
                    *[f"| `{k}` | {v} |" for k, v in {**ntypes, **rtypes}.items()],
                ])

                data_out = benny_home / "workspace" / args.workspace / "data_out"
                data_out.mkdir(parents=True, exist_ok=True)
                report_path = data_out / "enrichment_report.md"
                report_path.write_text(report, encoding="utf-8")
                return {"report_path": str(report_path), "corr_count": corr_cnt,
                        "concept_count": concept_cnt, "code_count": code_cnt}

            else:
                raise ValueError(f"Unknown task id: {tid!r}")

    # ─── 9. Execute waves with Rich Live display ──────────────────────────────
    completed_tasks: List[str] = []
    all_errors:      List[str] = []
    final_status = "completed"

    wave_groups: Dict[int, List[str]] = {}
    for t in TASK_DEFS:
        wave_groups.setdefault(t["wave"], []).append(t["id"])

    progress = Progress(
        SpinnerColumn(spinner_name="dots2"),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=28),
        TextColumn("[bold]{task.completed}[/]/[dim]{task.total}[/]"),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    )
    overall = progress.add_task("[cyan]Enrichment pipeline", total=len(TASK_DEFS))

    with Live(console=console, refresh_per_second=8) as live:
        live.update(Group(progress, _make_table()))

        for wave_num in sorted(wave_groups.keys()):
            wave_tids = wave_groups[wave_num]

            if final_status == "failed":
                for tid in [t["id"] for t in TASK_DEFS if task_status[t["id"]] == "pending"]:
                    task_status[tid] = "skipped"
                live.update(Group(progress, _make_table()))
                break

            progress.update(
                overall,
                description=f"[cyan]Wave {wave_num}[/]  [dim]{', '.join(wave_tids)}[/]",
            )
            for tid in wave_tids:
                task_status[tid] = "running"
            live.update(Group(progress, _make_table()))

            wave_t0 = time.monotonic()
            results = await asyncio.gather(
                *[_run_task(tid) for tid in wave_tids], return_exceptions=True
            )

            for tid, result in zip(wave_tids, results):
                elapsed = time.monotonic() - wave_t0
                task_elapsed[tid] = elapsed
                task_ts = datetime.now(timezone.utc).isoformat()

                if isinstance(result, Exception):
                    task_status[tid] = "failed"
                    _raw = str(result)
                    err  = _raw if _raw else f"{type(result).__name__} (no message)"
                    task_error[tid] = err
                    task_note[tid]  = (err[:20] + "\u2026") if len(err) > 20 else err
                    all_errors.append(f"{tid}: {err}")
                    final_status = "failed"
                    try:
                        lineage.emit_tool_execution(
                            manifest_id, tid, {"workspace": args.workspace}, False, err
                        )
                    except Exception:
                        pass
                else:
                    task_status[tid] = "done"
                    completed_tasks.append(tid)
                    # Build a short note from meaningful result keys
                    note_parts: List[str] = []
                    if isinstance(result, dict):
                        s = result.get("status", "")
                        if s == "already_converted":
                            note_parts.append(f"{result.get('data_in_files', 0)} files in data_in")
                        elif result.get("staging_files"):
                            note_parts.append(f"{result['staging_files']} staging files")
                        for key, label in [
                            ("staging_files",        "{v} staging files"),
                            ("data_in_files",        "{v} data_in files"),
                            ("md_files",             "{v} md files"),
                            ("rag_chunks",           "{v} rag chunks"),
                            ("pdf_count",            "{v} PDFs found"),
                            ("code_nodes",           "{v} code nodes"),
                            ("correlates_with_count", "{v} corr. edges"),
                            ("corr_count",            "{v} corr. edges"),
                            ("concept_count",         "{v} concepts"),
                            ("report_path",           "report written"),
                        ]:
                            if key in result:
                                val = result[key]
                                note_parts.append(label.format(v=val) if "{v}" in label else label)
                    task_note[tid] = ", ".join(note_parts[:2])
                    try:
                        lineage.emit_tool_execution(
                            manifest_id, tid, {"workspace": args.workspace}, True
                        )
                    except Exception:
                        pass

                # Write per-task audit record
                task_record: Dict[str, Any] = {
                    "task_id":     tid,
                    "wave":        wave_num,
                    "status":      task_status[tid],
                    "timestamp":   task_ts,
                    "elapsed_s":   round(elapsed, 3),
                    "result":      None if isinstance(result, Exception) else result,
                    "error":       task_error[tid],
                    "lineage_ref": manifest_id,
                    "run_id":      run_id,
                }
                record_json = json.dumps(task_record, indent=2, default=str)
                # SHA-256 integrity seal
                task_record["_sha256"] = hashlib.sha256(record_json.encode()).hexdigest()
                (run_folder / f"task_{tid}.json").write_text(
                    json.dumps(task_record, indent=2, default=str), encoding="utf-8"
                )
                try:
                    emit_governance_event(
                        event_type="ENRICH_TASK_DONE" if task_status[tid] == "done" else "ENRICH_TASK_FAILED",
                        data=task_record,
                        workspace_id=args.workspace,
                    )
                except Exception:
                    pass

                progress.advance(overall)
                live.update(Group(progress, _make_table()))

    # ─── 10. Write summary.json + close lineage ───────────────────────────────
    duration_s = (datetime.now(timezone.utc) - started_at).total_seconds()
    summary: Dict[str, Any] = {
        "run_id":           run_id,
        "manifest_id":      manifest_id,
        "workspace":        args.workspace,
        "src_path":         src_path,
        "model":            model,
        "threshold":        args.threshold,
        "strategy":         args.strategy,
        "status":           final_status,
        "started_at":       started_at.isoformat(),
        "duration_s":       round(duration_s, 2),
        "tasks_completed":  completed_tasks,
        "tasks_failed":     [k for k, v in task_status.items() if v == "failed"],
        "errors":           all_errors,
        "run_folder":       str(run_folder),
        "marquez_url":      "http://localhost:3010",
        "gdpr_notice":      str(run_folder / "GDPR_notice.json"),
    }
    sum_json = json.dumps(summary, indent=2, default=str)
    summary["_sha256"] = hashlib.sha256(sum_json.encode()).hexdigest()
    (run_folder / "summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    try:
        if final_status == "completed":
            lineage.complete_workflow(
                manifest_id,
                f"Knowledge Enrichment \u2014 {args.workspace}",
                args.workspace,
                completed_tasks,
                int(duration_s * 1000),
                ["data_out/enrichment_report.md"],
            )
        else:
            lineage.fail_workflow(
                manifest_id,
                f"Knowledge Enrichment \u2014 {args.workspace}",
                args.workspace,
                "; ".join(all_errors),
            )
    except Exception:
        pass

    try:
        emit_governance_event(
            "ENRICH_RUN_COMPLETE", summary, workspace_id=args.workspace
        )
    except Exception:
        pass

    # ─── 11. Final summary panel ─────────────────────────────────────────────
    ok = final_status == "completed"
    console.print()
    console.print(Rule(f"[bold {'green' if ok else 'red'}]Enrichment {'Complete \u2713' if ok else 'Failed \u2717'}"))

    sum_tbl = Table(box=box.SIMPLE, show_header=False, expand=True)
    sum_tbl.add_column("Key",   style="dim",        width=22)
    sum_tbl.add_column("Value", style="bold white")

    sum_tbl.add_row(
        "Status",
        f"[bold {'green' if ok else 'red'}]{final_status.upper()}[/]",
    )
    sum_tbl.add_row("Duration",        f"{duration_s:.1f}s")
    sum_tbl.add_row("Tasks completed", f"{len(completed_tasks)} / {len(TASK_DEFS)}")
    sum_tbl.add_row("Run ID",          run_id)
    sum_tbl.add_row("Manifest ID",     manifest_id)
    sum_tbl.add_row("Run folder",      str(run_folder))
    sum_tbl.add_row("Lineage",         "[link=http://localhost:3010]http://localhost:3010[/link]  [dim](Marquez)[/dim]")
    if ok:
        sum_tbl.add_row(
            "Studio ENRICH toggle",
            "[link=http://localhost:3000]http://localhost:3000[/link]  \u2192 Studio \u2192 Code Graph \u2192 [cyan]ENRICH[/cyan]",
        )
    sum_tbl.add_row("GDPR notice",     str(run_folder / "GDPR_notice.json"))

    console.print(Panel(
        sum_tbl,
        title="[bold]Run Summary[/]",
        border_style="green" if ok else "red",
        padding=(0, 2),
    ))

    if all_errors:
        console.print()
        console.print("[bold red]Errors:[/]")
        for err in all_errors:
            console.print(f"  [red]\u2717[/] {err}")

    if args.json:
        console.print()
        console.print(json.dumps(summary, indent=2, default=str))

    console.print()
    return 0 if ok else 1


# =============================================================================
# UTILS
# =============================================================================


def _load_manifest(ref: str) -> SwarmManifest:
    """Load a manifest from a file path OR a manifest id in the run_store."""
    path = Path(ref)
    if path.exists():
        return SwarmManifest.model_validate(json.loads(path.read_text(encoding="utf-8")))

    from benny.persistence import run_store

    m = run_store.get_manifest(ref)
    if m:
        return m
    raise FileNotFoundError(f"Manifest not found by path or id: {ref}")


# =============================================================================
# ARGUMENT PARSER
# =============================================================================


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="benny",
        description="Benny — declarative swarm workflow runner",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # plan
    p_plan = sub.add_parser("plan", help="Build a SwarmManifest from a requirement (no execution)")
    p_plan.add_argument("requirement", help="Natural-language requirement")
    p_plan.add_argument("--workspace", default="default")
    p_plan.add_argument("--model", default=None, help="LLM model ID (defaults to active manager selection)")
    p_plan.add_argument("--name", default=None)
    p_plan.add_argument("--input", "-i", action="append", default=[], help="Input file (repeatable)")
    p_plan.add_argument("--output", "-o", action="append", default=[], help="Output file (repeatable)")
    p_plan.add_argument("--format", choices=[f.value for f in OutputFormat], default="md")
    p_plan.add_argument("--word-count", type=int, default=None)
    p_plan.add_argument("--spec", default=None)
    p_plan.add_argument("--max-concurrency", type=int, default=1)
    p_plan.add_argument("--max-depth", type=int, default=3)
    p_plan.add_argument("--out", default=None, help="Write manifest JSON to this path")
    p_plan.add_argument("--no-save", dest="save", action="store_false", default=True)

    # run
    p_run = sub.add_parser("run", help="Execute a SwarmManifest (by path or by id)")
    p_run.add_argument("manifest", help="Path to manifest.json OR manifest id")
    p_run.add_argument("--json", action="store_true", help="Emit the final RunRecord as JSON")

    # runs
    p_runs = sub.add_parser("runs", help="Inspect past runs")
    runs_sub = p_runs.add_subparsers(dest="runs_cmd", required=True)

    p_runs_ls = runs_sub.add_parser("ls", help="List past runs")
    p_runs_ls.add_argument("--manifest", default=None, help="Filter by manifest id")
    p_runs_ls.add_argument("--workspace", default=None)
    p_runs_ls.add_argument("--limit", type=int, default=20)

    p_runs_show = runs_sub.add_parser("show", help="Show a run record")
    p_runs_show.add_argument("run_id")

    # manifests
    p_manifests = sub.add_parser("manifests", help="Manifest management")
    manifests_sub = p_manifests.add_subparsers(dest="manifests_cmd", required=True)
    manifests_sub.add_parser("ls", help="List saved manifests")

    # portable $BENNY_HOME lifecycle (PBR-001 Phase 1a)
    p_init = sub.add_parser("init", help="Create or refresh a portable $BENNY_HOME on the SSD")
    p_init.add_argument("--home", required=True, help="Absolute path to $BENNY_HOME (e.g. D:/optimus)")
    p_init.add_argument("--profile", choices=["app", "native"], required=True)

    p_doctor = sub.add_parser("doctor", help="Validate the portable $BENNY_HOME layout")
    p_doctor.add_argument("--home", required=True, help="Absolute path to $BENNY_HOME")

    p_uninstall = sub.add_parser(
        "uninstall",
        help="Remove the app/runtime boundary (workspaces survive with --keep-data)",
    )
    p_uninstall.add_argument("--home", required=True, help="Absolute path to $BENNY_HOME")
    p_uninstall.add_argument(
        "--keep-data",
        action="store_true",
        help="Preserve workspaces, data, models, config, and state",
    )

    # Service lifecycle (PBR-001 Phase 1b)
    p_up = sub.add_parser("up", help="Start the portable service stack (neo4j, lemonade, api, ui)")
    p_up.add_argument("--home", required=True, help="Absolute path to $BENNY_HOME")
    p_up.add_argument("--only", action="append", default=[], help="Only start the named service (repeatable)")
    p_up.add_argument("--no-wait", dest="wait_healthy", action="store_false", default=True)

    p_down = sub.add_parser("down", help="Stop the portable service stack")
    p_down.add_argument("--home", required=True, help="Absolute path to $BENNY_HOME")
    p_down.add_argument("--only", action="append", default=[], help="Only stop the named service (repeatable)")

    p_status = sub.add_parser("status", help="Report service status")
    p_status.add_argument("--home", required=True, help="Absolute path to $BENNY_HOME")
    p_status.add_argument("--only", action="append", default=[], help="Only report the named service (repeatable)")

    # MCP server (PBR-001 Phase 4)
    p_mcp = sub.add_parser("mcp", help="Start the Model Context Protocol (MCP) server")
    p_mcp.add_argument("--stdio", action="store_true", default=True, help="Use stdio transport (default)")
    p_mcp.add_argument("--port", type=int, default=8000, help="Benny API port to proxy to")

    # enrich — knowledge enrichment pipeline
    p_enrich = sub.add_parser(
        "enrich",
        help="Build and optionally run the knowledge enrichment pipeline (code scan -> synthesis -> correlate)",
    )
    p_enrich.add_argument("--workspace", default="c5_test", help="Target workspace (default: c5_test)")
    p_enrich.add_argument("--src", default="src/", help="Source path to scan with Tree-Sitter (relative to workspace, default: src/)")
    p_enrich.add_argument("--model", default=None, help="LLM model ID (defaults to active manager selection)")
    p_enrich.add_argument("--threshold", type=float, default=0.70, help="Semantic correlation confidence threshold (default: 0.70)")
    p_enrich.add_argument("--strategy", choices=["safe", "aggressive"], default="aggressive", help="Correlation strategy (default: aggressive)")
    p_enrich.add_argument("--out", default=None, help="Write manifest JSON to this path (skips execution)")
    p_enrich.add_argument("--run", dest="run_after", action="store_true", default=False, help="Execute the manifest immediately after building it")
    p_enrich.add_argument("--json", action="store_true", help="Emit the final RunRecord as JSON (implies --run)")

    # migrate (PBR-001 Phase 8)
    p_mig = sub.add_parser("migrate", help="Import legacy installs or relocate workspaces")
    p_mig.add_argument("--from-path", "--from", required=True, help="Source directory to migrate")
    p_mig.add_argument("--to-home", "--to", default=None, help="Target $BENNY_HOME (defaults to current)")
    p_mig.add_argument("--apply", action="store_true", help="Perform actual changes (default is dry-run)")
    p_mig.add_argument("--dry-run", dest="apply", action="store_false")

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "plan":
        return asyncio.run(cmd_plan(args))
    if args.cmd == "run":
        return asyncio.run(cmd_run(args))
    if args.cmd == "runs":
        if args.runs_cmd == "ls":
            return cmd_runs_ls(args)
        if args.runs_cmd == "show":
            return cmd_runs_show(args)
    if args.cmd == "manifests":
        if args.manifests_cmd == "ls":
            return cmd_manifests_ls(args)
    if args.cmd == "init":
        return cmd_init(args)
    if args.cmd == "doctor":
        return cmd_doctor(args)
    if args.cmd == "uninstall":
        return cmd_uninstall(args)
    if args.cmd == "up":
        return cmd_up(args)
    if args.cmd == "down":
        return cmd_down(args)
    if args.cmd == "status":
        return cmd_status(args)
    if args.cmd == "mcp":
        return cmd_mcp(args)
    if args.cmd == "migrate":
        return cmd_migrate(args)
    if args.cmd == "enrich":
        return asyncio.run(cmd_enrich(args))

    parser.print_help()
    return 1


# =============================================================================
# PORTABLE LIFECYCLE COMMANDS (PBR-001 Phase 1a)
# =============================================================================


def cmd_init(args: argparse.Namespace) -> int:
    from benny.portable import home as home_mod

    try:
        bh = home_mod.init(Path(args.home), profile=args.profile)
    except home_mod.PortableHomeError as exc:
        print(f"benny init failed: {exc}", file=sys.stderr)
        return 1
    print(f"initialised $BENNY_HOME at {bh.root} (profile={bh.profile})")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    from benny.portable import home as home_mod

    home_mod.uninstall(Path(args.home), keep_data=bool(args.keep_data))
    print(
        f"uninstalled from {args.home} "
        f"({'data preserved' if args.keep_data else 'data removed'})"
    )
    return 0


def _resolve_home(path_arg: str) -> Any:
    from benny.portable import home as home_mod

    root = Path(path_arg)
    report = home_mod.validate(root)
    if not report.ok:
        raise home_mod.PortableHomeError(
            "home is not initialised or is corrupt: " + "; ".join(report.problems)
        )
    profile = (root / "state" / "profile-lock").read_text(encoding="utf-8").strip()
    return home_mod.BennyHome(root=root, profile=profile)  # type: ignore[arg-type]


def cmd_up(args: argparse.Namespace) -> int:
    from benny.portable import config as cfg_mod
    from benny.portable import runner as runner_mod
    from benny.portable import services as svc_mod

    bh = _resolve_home(args.home)
    cfg = cfg_mod.load(bh.root)
    registry = svc_mod.default_services(cfg)

    selected = args.only or list(registry.keys())
    missing = [n for n in selected if n not in registry]
    if missing:
        print(f"benny up: unknown service(s): {missing}", file=sys.stderr)
        return 2

    specs = [registry[n] for n in selected]
    statuses = runner_mod.up(bh, specs, wait_healthy=args.wait_healthy)
    failed = 0
    for s in statuses:
        state = "healthy" if s.healthy else ("alive" if s.alive else "down")
        print(f"{s.name:<12} {state:<8} pid={s.pid}  {s.health_detail}")
        if not s.alive:
            failed += 1
    return 0 if failed == 0 else 1


def cmd_down(args: argparse.Namespace) -> int:
    from benny.portable import runner as runner_mod

    bh = _resolve_home(args.home)
    stopped = runner_mod.down(bh, args.only or None)
    if not stopped:
        print("benny down: nothing to stop")
        return 0
    for name in stopped:
        print(f"stopped {name}")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from benny.portable import runner as runner_mod

    bh = _resolve_home(args.home)
    statuses = runner_mod.status(bh, args.only or None)
    if not statuses:
        print("benny status: no services tracked (nothing has been started yet)")
        return 0
    print(f"{'SERVICE':<12} {'STATE':<8} {'PID':<8} DETAIL")
    for s in statuses:
        state = "healthy" if s.healthy else ("alive" if s.alive else "down")
        pid = str(s.pid) if s.pid else "-"
        print(f"{s.name:<12} {state:<8} {pid:<8} {s.health_detail}")
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    import subprocess
    import os

    # Implementation invokes python -m benny.mcp.server --stdio
    cmd = [sys.executable, "-m", "benny.mcp.server"]
    if args.stdio:
        cmd.append("--stdio")
    
    # Forward the API port via environment if needed, though server.py 
    # should probably handle config resolution itself.
    env = os.environ.copy()
    env["BENNY_API_PORT"] = str(args.port)

    print(f"[mcp] starting server (stdio transport)...")
    try:
        # MCP server typically communicates over stdin/stdout, so we 
        # replace the current process or use run. 
        # Using subprocess.run so it waits for completion.
        subprocess.run(cmd, env=env, check=True)
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        print(f"[mcp] failed: {e}", file=sys.stderr)
        return 1
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    import asyncio
    import os
    from rich.console import Console
    from rich.table import Table
    from benny.ops.doctor import run_doctor

    console = Console()
    with console.status("[bold green]Running diagnostics..."):
        if args.home:
            os.environ["BENNY_HOME"] = os.path.abspath(args.home)
        report = asyncio.run(run_doctor())

    table = Table(title="Benny System Health (Phase 6)")
    table.add_column("Check", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Message")

    for c in report.checks:
        color = "green" if c.status == "OK" else ("yellow" if c.status == "WARN" else "red")
        table.add_row(c.name, f"[{color}]{c.status}[/{color}]", c.message)

    console.print(table)
    if report.status_code == 0:
        console.print("[bold green]✓ All systems optimal.[/bold green]")
    elif report.status_code == 2:
        console.print("[bold yellow]! System operational with warnings.[/bold yellow]")
    else:
        console.print("[bold red]× Diagnostic errors found.[/bold red]")

    return report.status_code


def cmd_migrate(args: argparse.Namespace) -> int:
    from benny.migrate.importer import MigrationEngine
    import os

    source = Path(args.from_path)
    target = Path(args.to_home or os.environ.get("BENNY_HOME", ".")).absolute()
    
    engine = MigrationEngine(target)
    print(f"[migrate] source={source}")
    print(f"[migrate] target_home={target}")
    print(f"[migrate] mode={'APPLY' if args.apply else 'DRY-RUN'}")
    
    report = engine.migrate_workspace(source, target, dry_run=not args.apply)
    
    for t in report.transforms:
        print(f"  [{t['action']}] {t['file']} {t['details']}")
    
    if report.errors:
        print("\n[migrate] errors:", file=sys.stderr)
        for e in report.errors:
            print(f"  - {e}", file=sys.stderr)
            
    print(f"\n[migrate] complete. rewrites={report.count_rewrites}")
    if not args.apply:
        print("[migrate] DRY-RUN complete. Use --apply to commit changes.")
    return 0 if not report.errors else 1


if __name__ == "__main__":
    sys.exit(main())
