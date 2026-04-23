# Knowledge Enrichment Workflow

**Purpose**: Bridge the Notebook knowledge graph and the Studio code graph by creating `CORRELATES_WITH` edges that link `Concept` nodes (extracted from architecture documents) to `CodeEntity` nodes (extracted from source code). Once this pipeline has run, the **ENRICH toggle** in Benny Studio overlays semantic meaning onto the structural code graph.

---

## 1. What This Does

```
Architecture PDFs / UML docs          Source code (Python, TS, JS)
        ↓                                       ↓
  [Docling extract]                    [Tree-Sitter scan]
        ↓                                       ↓
  Concept nodes in Neo4j             File/Class/Function nodes in Neo4j
        ↓                                       ↓
  [Deep synthesis]                             ↓
  REL {predicate} edges              DEFINES / DEPENDS_ON / INHERITS edges
        ↓                                       ↓
              [Semantic correlation (Neural Spark)]
                          ↓
            CORRELATES_WITH {confidence, rationale} edges
                          ↓
          Studio ENRICH toggle — amber dashed overlay
```

**End state**: hovering a `Function` node in Studio shows amber lines to the `Concept` nodes from your UML docs that semantically match it, with a confidence score.

---

## 2. CLI: `benny enrich`

The enrichment pipeline is a fixed 7-task DAG. It does not require LLM planning.

### 2.1 Generate manifest only (review before running)

```bash
benny enrich \
    --workspace c5_test \
    --src src/dangpy \
    --out plans/c5_enrich.json

# Review the manifest
cat plans/c5_enrich.json | jq '.plan.waves'

# Then run when ready
benny run plans/c5_enrich.json --json
```

### 2.2 Generate and run immediately

```bash
benny enrich \
    --workspace c5_test \
    --src src/dangpy \
    --run
```

### 2.3 Full options

```
benny enrich [OPTIONS]

Options:
  --workspace TEXT        Target workspace (default: c5_test)
  --src TEXT              Source path to scan, relative to workspace (default: src/)
  --model TEXT            LLM model ID (defaults to active manager selection)
  --threshold FLOAT       Semantic correlation confidence threshold 0.0–1.0 (default: 0.70)
  --strategy {safe,aggressive}
                          Correlation strategy (default: aggressive)
  --out TEXT              Write manifest JSON to path without running
  --run                   Execute the manifest immediately after building
  --json                  Emit full RunRecord JSON on completion (implies --run)
```

### 2.4 Running on a different workspace

```bash
# Any workspace with architecture docs in staging/ and code in src/
benny enrich \
    --workspace my_project \
    --src src/my_package \
    --threshold 0.65 \
    --strategy safe \
    --run
```

---

## 3. Manifest Template

The canonical manifest template is at [`manifests/templates/knowledge_enrichment_pipeline.json`](../../manifests/templates/knowledge_enrichment_pipeline.json).

Copy and customise for a specific workspace:

```bash
cp manifests/templates/knowledge_enrichment_pipeline.json \
   $BENNY_HOME/workspaces/my_project/manifests/knowledge_enrichment.json

# Edit: workspace, inputs.context.src_path, config.model
# Then run:
benny run $BENNY_HOME/workspaces/my_project/manifests/knowledge_enrichment.json
```

---

## 4. Pipeline DAG

```
Wave 0 (parallel):
  pdf_extract   → Convert staging/ PDFs/docs to Markdown (Docling)
  code_scan     → Tree-Sitter scan of src/ → Neo4j code graph

Wave 1:
  rag_ingest    → Chunk + embed Markdown → ChromaDB  [depends: pdf_extract]

Wave 2:
  deep_synthesis → Extract Concept triples → Neo4j REL edges  [depends: rag_ingest]

Wave 3:
  semantic_correlate → Neural Spark: POST /api/rag/correlate  [depends: code_scan, deep_synthesis]
                       Creates CORRELATES_WITH {confidence, rationale} edges

Wave 4 (parallel):
  validate_enrichment → Assert CORRELATES_WITH edges > 0  [depends: semantic_correlate]
  generate_report     → Write data_out/enrichment_report.md [depends: validate_enrichment]
```

**Skill hints** (maps to executor routing):

| Task | Skill hint | API endpoint |
|------|-----------|--------------|
| `pdf_extract` | `extract_pdf` | POST `/api/files/upload` (Docling) |
| `code_scan` | `code_scan` | POST `/api/graph/code/generate` |
| `rag_ingest` | `rag_ingest` | POST `/api/files/process` |
| `deep_synthesis` | `rag_ingest` | POST `/api/graph/synthesize` |
| `semantic_correlate` | `semantic_correlate` | POST `/api/rag/correlate` |
| `validate_enrichment` | `validate_enrichment` | GET `/api/graph/code/lod?tier=1` |
| `generate_report` | `rag_ingest` | POST `/api/rag/chat` (synthesis) |

---

## 5. Prerequisites

Before running the pipeline:

```bash
# 1. Services must be up
benny up --home $BENNY_HOME
benny doctor --home $BENNY_HOME

# 2. Workspace must exist
benny status --home $BENNY_HOME

# 3. Architecture documents must be in staging/
ls $BENNY_HOME/workspaces/c5_test/staging/
# Expected: *.pdf, *.docx, or *.md files containing UML / architecture content

# 4. Source code must be in src/
ls $BENNY_HOME/workspaces/c5_test/src/
# Expected: Python/TS/JS source tree

# 5. Check RAG status before running
curl -H "X-Benny-API-Key: benny-mesh-2026-auth" \
     "http://127.0.0.1:8005/api/rag/status?workspace=c5_test"
```

---

## 6. Monitoring the Run

```bash
# Follow execution events in real time (after benny enrich --run)
curl -N \
     -H "X-Benny-API-Key: benny-mesh-2026-auth" \
     -H "Accept: text/event-stream" \
     http://127.0.0.1:8005/api/workflows/execute/<manifest_id>

# Check run history
benny runs ls --workspace c5_test --limit 5
benny runs show <run_id>

# Check CORRELATES_WITH edges were created (Neo4j Browser: http://localhost:7474)
# MATCH (c:Concept)-[r:CORRELATES_WITH]->(e:CodeEntity {workspace: 'c5_test'})
# RETURN c.name, r.confidence, e.name, e.type
# ORDER BY r.confidence DESC LIMIT 25

# Or via API
curl -H "X-Benny-API-Key: benny-mesh-2026-auth" \
     "http://127.0.0.1:8005/api/graph/stats?workspace=c5_test" | jq '.relationship_types'
```

---

## 7. Using the ENRICH Toggle in Studio

Once the pipeline completes:

1. Open Benny Studio in the browser (default: **http://localhost:3000**)
2. Select workspace **c5_test** from the workspace selector
3. Navigate to the **Studio** tab → **Code Graph** view
4. In the **Graph_Commands** panel (right side), click **ENRICH**
   - Button turns amber and label changes to **ENRICHED**
   - The graph re-fetches with Concept nodes and `CORRELATES_WITH` edges included
5. Hover any code symbol — amber dashed lines show which architecture concepts map to it, with confidence percentage

**Visual language**:
- Amber dashed lines = `CORRELATES_WITH` (semantic, from knowledge graph)
- Solid coloured lines = structural edges (`DEFINES`, `DEPENDS_ON`, `INHERITS`)
- Magenta spheres = `Concept` nodes from architecture documents
- Toggle off: `ENRICH` — removes enrichment edges, returns to pure code structure view

---

## 8. Troubleshooting

| Symptom | Check | Fix |
|---------|-------|-----|
| `validate_enrichment` fails — zero edges | Check `deep_synthesis` output: did triples get extracted? | Re-run with more permissive model; check `$BENNY_HOME/logs/api.log` |
| Studio shows ENRICHED but no amber lines | `visibleTypes` doesn't include `Concept` | Open Studio settings → re-enable `Concept` in node type filter |
| Low confidence scores (all < 0.3) | Architecture docs may be too abstract | Try `--strategy safe` with `--threshold 0.50`; check that docs reference code symbol names |
| `code_scan` wave fails | Tree-Sitter language support | Ensure Python, TypeScript, or JavaScript parsers are available: `pip show tree-sitter-python` |
| Pipeline re-runs but no new edges | `MERGE` deduplication | This is correct behaviour — edges are idempotent. To force re-correlation: `DELETE CORRELATES_WITH` edges in Neo4j first |

### Force re-correlation (Neo4j Browser)

```cypher
MATCH (c:Concept)-[r:CORRELATES_WITH]->(e:CodeEntity {workspace: 'c5_test'})
DELETE r
```

Then re-run: `benny enrich --workspace c5_test --src src/dangpy --run`

---

## 9. c5_test Specific Notes

c5_test is the primary enrichment experiment workspace:
- **`staging/`**: UML diagrams and architecture PDFs have been ingested (Docling already run)
- **`src/dangpy`**: Python codebase targeted for code graph analysis
- **Current state**: Knowledge graph has `Concept` nodes; code graph may not yet be populated
- **Next step**: `benny enrich --workspace c5_test --src src/dangpy --run`

After a successful run, view the enrichment report:
```bash
cat $BENNY_HOME/workspaces/c5_test/data_out/enrichment_report.md
```
