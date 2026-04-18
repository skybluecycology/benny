"""
Benny CLI — declarative manifest driver.

Usage:
    benny plan "Generate a 10k-word analyst report comparing X and Y" \\
        --workspace default --output report.md --word-count 10000 \\
        --save manifest.json

    benny run manifest.json

    benny runs ls [--manifest MANIFEST_ID]
    benny runs show RUN_ID

Design: this is the user's main interface to the plan-then-run loop. The
same JSON that appears in `manifest.json` is what the UI canvas renders
and what past runs reference. Share the file → share the workflow.
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
    from benny.graph.manifest_runner import plan_from_requirement
    from benny.persistence import run_store

    output_spec = OutputSpec(
        files=args.output or [],
        format=OutputFormat(args.format) if args.format else OutputFormat.MARKDOWN,
        word_count_target=args.word_count,
        spec=args.spec or "",
    )

    print(f"[plan] requirement: {args.requirement[:120]}{'...' if len(args.requirement) > 120 else ''}")
    print(f"[plan] workspace={args.workspace} model={args.model} max_concurrency={args.max_concurrency}")
    if args.input:
        print(f"[plan] inputs: {args.input}")
    if output_spec.word_count_target:
        print(f"[plan] target: {output_spec.word_count_target} words → {output_spec.format.value}")

    manifest = await plan_from_requirement(
        requirement=args.requirement,
        workspace=args.workspace,
        model=args.model,
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
        print(f"[plan] wrote manifest → {out_path}")
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
    p_plan.add_argument("--model", default="ollama/llama3.2")
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

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
