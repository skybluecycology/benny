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
        print(f"[plan] target: {output_spec.word_count_target} words → {output_spec.format.value}")

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
