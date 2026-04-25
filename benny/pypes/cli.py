"""`benny pypes` CLI subcommand handlers.

Keeps ``benny_cli.py`` lean — the top-level CLI just registers a
subparser and dispatches through to ``cmd_pypes`` here.

Subcommands:
    benny pypes run <manifest.json>             [--workspace W] [--resume RUN]
    benny pypes inspect <manifest.json>         (print DAG + CLP summary)
    benny pypes runs ls --workspace W           (list prior pypes runs)
    benny pypes drilldown <run_id> <step_id>    [--rows 20]
    benny pypes rerun <run_id> --from <step>    (re-execute from step onward)
    benny pypes report <run_id> <report_id>     (re-render a single report)
    benny pypes registry                        (list registered operations)
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .checkpoints import CheckpointStore
from .engines import available_engines, get_engine
from .models import EngineType, FormatType, PypesManifest, ReportSpec, SourceSpec
from .orchestrator import Orchestrator, load_manifest, run_manifest
from .registry import default_registry
from .reports import render_report


# =============================================================================
# SUBPARSER
# =============================================================================


def add_subparser(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser(
        "pypes",
        help="Declarative transformation engine — turn Benny into a data plane",
        description=(
            "Benny Pypes runs manifest-driven, DAG-based transformations over "
            "tabular data. Inputs are declared, every step's output is "
            "checkpointed, and reports (financial risk, threshold breaches, "
            "move analysis) render with full CLP lineage."
        ),
    )
    pp = p.add_subparsers(dest="pypes_cmd", required=True)

    p_run = pp.add_parser("run", help="Execute a pypes manifest")
    p_run.add_argument("manifest", help="Path to a pypes manifest.json")
    p_run.add_argument("--workspace", default=None, help="Override manifest.workspace")
    p_run.add_argument("--resume", dest="resume_run_id", default=None)
    p_run.add_argument("--only", action="append", default=[], help="Only run the named step (repeatable)")
    p_run.add_argument("--var", action="append", default=[], help="Variable override key=value (repeatable)")
    p_run.add_argument("--json", action="store_true", help="Emit the RunReceipt as JSON")

    p_inspect = pp.add_parser("inspect", help="Print the DAG and CLP summary for a manifest")
    p_inspect.add_argument("manifest", help="Path to a pypes manifest.json")

    p_runs = pp.add_parser("runs", help="List prior pypes runs in a workspace")
    p_runs_sub = p_runs.add_subparsers(dest="runs_cmd", required=True)
    p_runs_ls = p_runs_sub.add_parser("ls")
    p_runs_ls.add_argument("--workspace", default="default")
    p_runs_ls.add_argument("--limit", type=int, default=20)

    p_runs_show = p_runs_sub.add_parser("show")
    p_runs_show.add_argument("run_id")
    p_runs_show.add_argument("--workspace", default="default")

    p_drill = pp.add_parser("drilldown", help="Inspect a step's checkpoint with CLP annotations")
    p_drill.add_argument("run_id")
    p_drill.add_argument("step_id")
    p_drill.add_argument("--workspace", default="default")
    p_drill.add_argument("--rows", type=int, default=20)
    p_drill.add_argument("--json", action="store_true")

    p_rerun = pp.add_parser("rerun", help="Re-execute a prior run starting from a given step")
    p_rerun.add_argument("run_id")
    p_rerun.add_argument("--from", dest="from_step", required=True)
    p_rerun.add_argument("--workspace", default="default")
    p_rerun.add_argument("--json", action="store_true")

    p_report = pp.add_parser("report", help="Re-render a single report from a prior run")
    p_report.add_argument("run_id")
    p_report.add_argument("report_id")
    p_report.add_argument("--workspace", default="default")

    pp.add_parser("registry", help="List every registered operation")


# =============================================================================
# DISPATCH
# =============================================================================


def cmd_pypes(args: argparse.Namespace) -> int:
    cmd = args.pypes_cmd
    if cmd == "run":
        return _cmd_run(args)
    if cmd == "inspect":
        return _cmd_inspect(args)
    if cmd == "runs":
        if args.runs_cmd == "ls":
            return _cmd_runs_ls(args)
        if args.runs_cmd == "show":
            return _cmd_runs_show(args)
    if cmd == "drilldown":
        return _cmd_drilldown(args)
    if cmd == "rerun":
        return _cmd_rerun(args)
    if cmd == "report":
        return _cmd_report(args)
    if cmd == "registry":
        return _cmd_registry(args)
    print(f"unknown pypes subcommand: {cmd}")
    return 1


# =============================================================================
# HANDLERS
# =============================================================================


def _cmd_run(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    if args.workspace:
        manifest.workspace = args.workspace
    variables = _parse_vars(args.var)

    receipt = Orchestrator().run(
        manifest,
        variables=variables,
        resume_from_run_id=args.resume_run_id,
        only_steps=args.only or None,
    )
    if args.json:
        print(receipt.model_dump_json(indent=2))
    else:
        _print_receipt(receipt)
    return 0 if receipt.status != "FAILED" else 1


def _cmd_inspect(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    print(f"manifest: {manifest.id}  ({manifest.name})")
    print(f"workspace: {manifest.workspace}")
    print(f"schema_version: {manifest.schema_version}")
    if manifest.governance.compliance_tags:
        print(f"compliance: {', '.join(manifest.governance.compliance_tags)}")
    print()
    print("DAG:")
    producers: Dict[str, str] = {}
    for s in manifest.steps:
        for o in s.outputs or [s.id]:
            producers[o] = s.id
    for s in manifest.steps:
        deps = sorted({producers[n] for n in s.inputs if n in producers})
        dep_text = ", ".join(deps) if deps else "—"
        ops = ",".join(o.operation for o in s.operations) or (s.sub_manifest_uri or "source")
        print(f"  {s.id:>20}  [{s.stage.value:<6}] engine={s.engine.value:<7} deps={dep_text:<20} ops=[{ops}]")
    if manifest.clp.conceptual:
        print()
        print("CLP:")
        for c in manifest.clp.conceptual:
            tag = f" [{', '.join(c.compliance_tags)}]" if c.compliance_tags else ""
            print(f"  conceptual: {c.name}{tag}")
        for l in manifest.clp.logical:
            for f in l.fields:
                th = f"  th={f.threshold}" if f.threshold else ""
                print(f"  logical:    {l.entity}.{f.name} ({f.type}, required={f.required}){th}")
    if manifest.reports:
        print()
        print("Reports:")
        for r in manifest.reports:
            print(f"  {r.id}  ({r.kind})  <- {r.source_step}  format={r.format}")
    return 0


def _cmd_runs_ls(args: argparse.Namespace) -> int:
    ws_root = _workspace_root(args.workspace)
    runs_dir = ws_root / "runs"
    if not runs_dir.exists():
        print("(no runs)")
        return 0
    entries = sorted(runs_dir.glob("pypes-*"), key=lambda p: p.stat().st_mtime, reverse=True)
    entries = entries[: args.limit]
    print(f"{'run_id':<18} {'manifest':<28} {'status':<10} {'steps':>6}  {'created'}")
    print("-" * 92)
    for run_dir in entries:
        receipt_path = run_dir / "receipt.json"
        if not receipt_path.exists():
            continue
        try:
            r = json.loads(receipt_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        run_id = r.get("run_id", run_dir.name.replace("pypes-", ""))
        print(
            f"{run_id:<18} {r.get('manifest_id',''):<28} {r.get('status',''):<10} "
            f"{len(r.get('step_results', {})):>6}  {r.get('started_at','')}"
        )
    return 0


def _cmd_runs_show(args: argparse.Namespace) -> int:
    receipt_path = _workspace_root(args.workspace) / "runs" / f"pypes-{args.run_id}" / "receipt.json"
    if not receipt_path.exists():
        print(f"run not found: {args.run_id}", flush=True)
        return 1
    print(receipt_path.read_text(encoding="utf-8"))
    return 0


def _cmd_drilldown(args: argparse.Namespace) -> int:
    ws_root = _workspace_root(args.workspace)
    run_dir = ws_root / "runs" / f"pypes-{args.run_id}"
    if not run_dir.exists():
        print(f"run not found: {args.run_id}")
        return 1
    store = CheckpointStore(run_dir)
    if not store.has(args.step_id):
        print(f"no checkpoint for step '{args.step_id}' in run {args.run_id}")
        return 1
    manifest = _load_run_manifest(run_dir)
    step = manifest.step(args.step_id) if manifest else None

    engine = get_engine(EngineType.PANDAS)
    df = store.read(engine, args.step_id)
    rows = engine.to_records(df, limit=args.rows)
    columns = engine.columns(df)

    if args.json:
        print(json.dumps({
            "run_id": args.run_id,
            "step_id": args.step_id,
            "row_count": engine.row_count(df),
            "columns": columns,
            "clp_binding": (step.clp_binding if step else {}) or {},
            "rows": rows,
        }, indent=2, default=str))
        return 0

    print(f"run {args.run_id}  step '{args.step_id}'  rows={engine.row_count(df)}  cols={len(columns)}")
    if step and step.clp_binding:
        print("CLP binding:")
        for col, ref in step.clp_binding.items():
            print(f"  {col:<20} -> {ref}")
    print()
    print("  ".join(columns))
    print("-" * min(100, sum(len(c) + 2 for c in columns)))
    for row in rows:
        print("  ".join(str(row.get(c, "")) for c in columns))
    return 0


def _cmd_rerun(args: argparse.Namespace) -> int:
    ws_root = _workspace_root(args.workspace)
    run_dir = ws_root / "runs" / f"pypes-{args.run_id}"
    manifest = _load_run_manifest(run_dir)
    if manifest is None:
        print(f"cannot load manifest snapshot from run {args.run_id}")
        return 1

    # Compute the set of steps to re-execute: ``from_step`` and all downstream.
    producers: Dict[str, str] = {}
    for s in manifest.steps:
        for o in s.outputs or [s.id]:
            producers[o] = s.id
    reverse: Dict[str, List[str]] = {s.id: [] for s in manifest.steps}
    for s in manifest.steps:
        for name in s.inputs:
            prod = producers.get(name)
            if prod and prod != s.id:
                reverse.setdefault(prod, []).append(s.id)

    only: List[str] = []
    stack = [args.from_step]
    while stack:
        cur = stack.pop()
        if cur in only:
            continue
        only.append(cur)
        stack.extend(reverse.get(cur, []))

    receipt = Orchestrator(workspace_root=ws_root).run(
        manifest,
        resume_from_run_id=args.run_id,
        only_steps=only,
    )
    if args.json:
        print(receipt.model_dump_json(indent=2))
    else:
        _print_receipt(receipt)
    return 0 if receipt.status != "FAILED" else 1


def _cmd_report(args: argparse.Namespace) -> int:
    ws_root = _workspace_root(args.workspace)
    run_dir = ws_root / "runs" / f"pypes-{args.run_id}"
    if not run_dir.exists():
        print(f"run not found: {args.run_id}")
        return 1
    manifest = _load_run_manifest(run_dir)
    if manifest is None:
        print("cannot load manifest snapshot")
        return 1
    report = manifest.report(args.report_id)
    if report is None:
        print(f"report '{args.report_id}' not declared in manifest")
        return 1
    receipt_path = run_dir / "receipt.json"
    from .models import RunReceipt

    receipt = RunReceipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))
    store = CheckpointStore(run_dir)
    path = render_report(
        engine=get_engine(EngineType.PANDAS),
        manifest=manifest,
        spec=report,
        store=store,
        receipt=receipt,
    )
    print(f"wrote {path}")
    return 0


def _cmd_registry(args: argparse.Namespace) -> int:
    print("available engines:", ", ".join(available_engines()))
    print("registered operations:")
    for name in default_registry.names():
        print(f"  - {name}")
    return 0


# =============================================================================
# HELPERS
# =============================================================================


def _parse_vars(items: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for item in items or []:
        if "=" not in item:
            continue
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _workspace_root(workspace: str) -> Path:
    benny_home = os.environ.get("BENNY_HOME")
    base = Path(benny_home) if benny_home else Path.cwd()
    return base / "workspace" / workspace


def _load_run_manifest(run_dir: Path) -> Optional[PypesManifest]:
    snap = run_dir / "manifest_snapshot.json"
    if not snap.exists():
        return None
    return PypesManifest.model_validate_json(snap.read_text(encoding="utf-8"))


def _print_receipt(receipt: Any) -> None:
    print(f"run {receipt.run_id}  manifest={receipt.manifest_id}  status={receipt.status}  duration={receipt.duration_ms}ms")
    for sid, v in receipt.step_results.items():
        fail_count = sum(1 for c in (v.checks or []) if c.get("status") == "FAILED")
        print(f"  {sid:<24} {v.status:<6} rows={v.row_count}  failed_checks={fail_count}")
    if receipt.reports:
        print("reports:")
        for rid, p in receipt.reports.items():
            print(f"  {rid:<24} -> {p}")
    if receipt.errors:
        print("errors:")
        for e in receipt.errors:
            print(f"  - {e}")
