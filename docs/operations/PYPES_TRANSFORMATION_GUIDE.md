# Benny Pypes — Declarative Transformation Engine

Pypes is Benny's third capability surface — alongside **documents** (RAG / Knowledge Graph) and **code** (Code Graph + Swarm execution). It turns Benny into a **manifest-driven, DAG-based data transformation engine** that can:

- Run bronze → silver → gold pipelines with checkpoints at every step.
- Validate data inline (completeness, uniqueness, thresholds, move-analysis vs. prior runs).
- Generate explainable financial-risk-style reports with drill-down + CLP (Conceptual / Logical / Physical) lineage.
- Re-execute any subset of a previous run from the exact checkpoint where it diverged.
- Speak the same `${BENNY_HOME}` portability and `X-Benny-API-Key` governance as the rest of Benny.

Pypes brings the lessons from `docs/requirements/9/pypes/requirements/previous_project_pain_points.md` (chiefly: *"every transformation step needs a typed contract, a checkpoint, and a way to drill back to the source row"*) into a small, declarative engine that ships natively with Benny.

---

## TL;DR — Run the demo

```bash
# 1. Validate the bundled demo manifest
benny pypes inspect manifests/templates/financial_risk_pipeline.json

# 2. Execute it (creates workspace/pypes_demo/runs/pypes-<run_id>/)
benny pypes run manifests/templates/financial_risk_pipeline.json --workspace pypes_demo

# 3. List prior runs
benny pypes runs --workspace pypes_demo

# 4. Drill into a step's checkpoint with CLP-annotated columns
benny pypes drilldown <run_id> gold_exposure --workspace pypes_demo

# 5. Re-execute from a step (reuses checkpoints for everything before it)
benny pypes rerun <run_id> --from silver_trades --workspace pypes_demo

# 6. Re-render a single report without re-executing the pipeline
benny pypes report <run_id> counterparty_risk --workspace pypes_demo
```

You should see three reports under `workspace/pypes_demo/runs/pypes-<run_id>/reports/`:

| Report | Kind | What it shows |
|--------|------|---------------|
| `counterparty_risk.md`  | `financial_risk`      | Top exposures + threshold breaches + CLP provenance for the gold table |
| `breaches.md`           | `threshold_breaches`  | Every row that breached a `notional` / `total_exposure` cap |
| `exposure_move.md`      | `move_analysis`       | Day-on-day delta vs. the most recent prior run for the same manifest |

---

## Why declarative, why a closed DAG?

The pain points doc is blunt: imperative pipelines built up step-by-step in Python notebooks fail four ways:

1. **No reproducibility.** A bug fix in step 7 forces you to re-execute steps 1–6 — slow and lossy.
2. **No drill-back.** When a regulator asks *"why did `total_exposure = 525M` for CP-TESLA on 22 April?"* the answer requires re-deriving the calculation from logs, screenshots, and tribal memory.
3. **No threshold gating.** Validation lives in dashboards, not in the pipeline; bad data leaks into reports.
4. **No lineage.** OpenLineage / Marquez emissions are bolted on after the fact, never matching the actual graph.

A **closed DAG manifest** fixes all four:

- Every step is a node with declared inputs/outputs — the executor builds the topological order.
- Every step writes a checkpoint, indexed by `step_id` and tied to the exact manifest snapshot for the run.
- Validations are part of the step contract (pre + post), not an afterthought.
- Lineage is emitted from the same model the executor consumes, so the Marquez graph is the actual run.

Agents (planner / swarm) reason about the DAG as data — adding a step is editing a JSON file, not editing Python.

---

## Manifest anatomy

The canonical example is at `manifests/templates/financial_risk_pipeline.json`. The kind is `pypes_pipeline` (versus `swarm_manifest` for LangGraph swarms).

```jsonc
{
  "schema_version": "1.0",
  "kind": "pypes_pipeline",
  "id": "financial-risk-demo",
  "name": "Market Risk — Counterparty Exposure (Demo)",
  "workspace": "pypes_demo",

  "governance": { "compliance_tags": ["BCBS-239", "SOX"], "owner": "Risk_Quant_Team", "criticality": "high" },

  "clp": {
    "conceptual": [{ "name": "Trade", "owner": "Front Office" }, /* … */],
    "logical":    [{ "entity": "Trade", "fields": [/* typed columns + thresholds */] }],
    "physical":   [{ "entity": "Trade", "uri_template": "data_in/trades.csv", "format": "csv", "primary_key": ["trade_id"] }]
  },

  "variables": { "trades_source": "${benny_home}/manifests/templates/data/trades_sample.csv" },

  "steps": [
    {
      "id": "bronze_trades",
      "stage": "bronze",
      "engine": "pandas",
      "source": { "uri": "${trades_source}", "format": "csv" },
      "operations": [{ "operation": "load", "params": { "source_id": "FRONT_OFFICE" } }],
      "outputs": ["raw_trades"],
      "post_validations": { "completeness": ["trade_id", "trade_date"], "uniqueness": ["trade_id"], "row_count": { "min": 1 } },
      "clp_binding": { "trade_id": "Trade.trade_id", "notional": "Trade.notional" }
    },
    /* silver_trades, silver_trades_usd, gold_exposure … */
  ],

  "reports": [
    { "id": "counterparty_risk", "kind": "financial_risk", "source_step": "gold_exposure", "drill_down_by": ["counterparty_id"], "top_n": 25 },
    { "id": "breaches",          "kind": "threshold_breaches", "source_step": "silver_trades" },
    { "id": "exposure_move",     "kind": "move_analysis", "source_step": "gold_exposure", "top_n": 20 }
  ]
}
```

### Key concepts

| Concept | Where it lives | Why |
|---------|----------------|-----|
| **Stage** (`bronze` / `silver` / `gold` / `raw` / `feature` / `governed`) | `steps[].stage` | Lakehouse convention; gold steps require `clp_binding` so reports can drill back to logical attributes. |
| **CLP** (Conceptual → Logical → Physical) | `clp.*` block + `steps[].clp_binding` | BCBS-239 backbone. Every report annotates each column with its logical attribute and physical source. |
| **Operations** | Built into a registry (`benny.pypes.registry`) | `load`, `filter`, `dedupe`, `standardize`, `calc`, `aggregate`, `sort`, `join`, `union`, plus engine-specific extensions. |
| **Validations** | `pre_validations` / `post_validations` per step | `completeness`, `uniqueness`, `thresholds`, `row_count`, `move_analysis` — all FAIL → step status = `FAIL`, run status = `PARTIAL`. |
| **Variables** | `variables{}` + CLI `--var k=v` + `BENNY_HOME` env | All `${name}` tokens substituted at run-time. `benny_home` is auto-injected so manifests stay portable. |
| **Reports** | `reports[]` block | Kinds: `financial_risk`, `threshold_breaches`, `move_analysis`, `generic_summary`. Each consumes a step's checkpoint. |
| **Engines** | `engine: "pandas" | "polars"` per step | Same operations, different runtime. Engines auto-fall-back (parquet → CSV when pyarrow is missing). |
| **Sub-manifests** | `sub_manifest_uri` on a step | A step can recursively execute another manifest — useful for shared cleansing routines. |

---

## What gets persisted

Every run produces:

```
$BENNY_HOME/workspace/<workspace>/runs/pypes-<run_id>/
├── manifest_snapshot.json     ← exact resolved manifest (variables substituted)
├── receipt.json               ← signed RunReceipt (SHA-256 over status + checkpoints)
├── checkpoints/
│   ├── _index.json            ← step_id → {path, format, row_count, fingerprint}
│   ├── bronze_trades.parquet  ← (or .csv when pyarrow is unavailable)
│   ├── silver_trades.parquet
│   ├── silver_trades_usd.parquet
│   └── gold_exposure.parquet
└── reports/
    ├── counterparty_risk.md
    ├── breaches.md
    └── exposure_move.md
```

A re-run with `--from <step_id>` loads checkpoints for every step *upstream* of `<step_id>` and re-executes from there. Reports re-render against the new outputs — without recomputing the bronze/silver layers if they did not change.

---

## CLI cheatsheet

```bash
# Validate without executing
benny pypes inspect <manifest.json>

# Execute (override variables, skip steps, run only one)
benny pypes run <manifest.json> --workspace <ws> \
                                --var trades_source=$PWD/data_in/feb.csv \
                                --only bronze_trades silver_trades

# List runs in a workspace
benny pypes runs --workspace <ws> --limit 20

# Drill into a checkpoint (rows + CLP annotations)
benny pypes drilldown <run_id> <step_id> --workspace <ws> --rows 50

# Re-execute downstream of a step (reuses prior checkpoints)
benny pypes rerun <run_id> --from <step_id> --workspace <ws>

# Re-render one report from a prior run
benny pypes report <run_id> <report_id> --workspace <ws>

# Inspect the registered operation/engine catalog
benny pypes registry
```

---

## HTTP API (Studio integration)

Every CLI action has a paired endpoint under `/api/pypes/`. All endpoints require the standard `X-Benny-API-Key: benny-mesh-2026-auth` header.

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/api/pypes/registry`                           | List operations + engines |
| `POST` | `/api/pypes/validate`                           | Validate manifest, return DAG order + CLP gaps |
| `POST` | `/api/pypes/run`                                | Execute (`{manifest, variables, only_steps, resume_from_run_id}`) |
| `GET`  | `/api/pypes/runs?workspace=<ws>`                | List prior runs |
| `GET`  | `/api/pypes/runs/{run_id}?workspace=<ws>`       | Receipt + manifest snapshot |
| `GET`  | `/api/pypes/runs/{run_id}/steps/{step_id}`      | Drill-down rows + CLP binding |
| `POST` | `/api/pypes/runs/{run_id}/rerun`                | Re-execute from `from_step` |
| `POST` | `/api/pypes/runs/{run_id}/reports/{report_id}` | Re-render a single report |

The Studio surface is `frontend/src/components/Studio/PipelineCanvas.tsx`. It loads a run via the API, renders the DAG with stage-coloured nodes, colours each node by validation status, and drills down into the checkpoint when you click a step.

---

## Lineage and audit

Pypes runs emit OpenLineage events through the same emitter the swarm uses. With Marquez running:

```bash
docker compose up -d marquez-db marquez-api marquez-web
# then open http://localhost:3010 — pypes runs appear as their own jobs/datasets
```

The signed `receipt.json` plus the `manifest_snapshot.json` give you a tamper-evident audit trail without needing Marquez at all — useful for offline / portable Benny.

---

## Where the source lives

| File | Role |
|------|------|
| `benny/pypes/models.py`         | Pydantic schema (`PypesManifest`, `PipelineStep`, `RunReceipt`, `ValidationResult`, etc.) |
| `benny/pypes/registry.py`       | Operation registry — register your own with `@registry.register("my_op")` |
| `benny/pypes/engines/pandas_impl.py` | Default execution engine (also used to read checkpoints) |
| `benny/pypes/engines/polars_impl.py` | Polars engine for high-throughput steps |
| `benny/pypes/orchestrator.py`   | Topological execution + checkpoints + sub-manifest recursion |
| `benny/pypes/validators.py`     | Completeness / uniqueness / thresholds / move-analysis |
| `benny/pypes/reports.py`        | Markdown renderers for the four report kinds |
| `benny/pypes/checkpoints.py`    | Parquet + CSV fallback checkpoint store |
| `benny/pypes/lineage.py`        | OpenLineage emitter |
| `benny/pypes/cli.py`            | argparse subcommands wired into `benny_cli.py` |
| `benny/api/pypes_routes.py`     | FastAPI router mounted at `/api/pypes` |
| `manifests/templates/financial_risk_pipeline.json` | The investment-bank demo manifest |
| `manifests/templates/data/trades_sample.csv`       | Demo trades (intentionally includes threshold breaches) |
| `frontend/src/components/Studio/PipelineCanvas.tsx`| Studio DAG visualisation + drill-down panel |

---

## See also

- [SAD §3.6 Pypes Transformation Engine](../../architecture/SAD.md) — architectural placement
- [BENNY_OPERATING_MANUAL.md](BENNY_OPERATING_MANUAL.md) — full run book
- [LOG_AND_LINEAGE_GUIDE.md](LOG_AND_LINEAGE_GUIDE.md) — Marquez + Phoenix observability
- [`docs/requirements/9/pypes/requirements/`](../../requirements/9/pypes/requirements/) — original requirement docs and pain-point retrospective
