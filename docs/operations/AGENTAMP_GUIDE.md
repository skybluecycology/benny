# AgentAmp — Skinnable, Pluggable Agentic Cockpit

AgentAmp turns Benny's CLI and Studio surfaces into a **Winamp-style cockpit for the agentic era**. Skin packs customise every visual surface — colours, typography, motion, sound cues, CLI glyphs, and WebGL visualisers — without touching the deterministic core.

**Phase 1 ships:** skin pack format, HMAC signing, scaffold + pack + sign + install CLI tools.
**Later phases add:** AgentVis plugins, DSP-A spectrum, Equalizer panel, Textual TUI, `skin_designer` LLM skill, marketplace.

Full requirements: [docs/requirements/11/requirement.md](../requirements/11/requirement.md)
Acceptance matrix: [docs/requirements/11/acceptance_matrix.md](../requirements/11/acceptance_matrix.md)

---

## TL;DR — Create and install your first skin

```bash
# 1. Scaffold a new skin draft
benny agentamp scaffold-skin my-team-skin

# 2. Edit the draft
#    $BENNY_HOME/agentamp/drafts/my-team-skin/skin.manifest.json
#    Add sprites, shaders, sounds as needed.

# 3. Pack the draft into a .aamp zip
benny agentamp pack $BENNY_HOME/agentamp/drafts/my-team-skin --out my-team-skin.aamp

# 4. Sign it with your HMAC key
benny agentamp sign my-team-skin.aamp

# 5. Install it
benny agentamp install my-team-skin.aamp --workspace default
```

The skin is now in `$BENNY_HOME/agentamp/registry/my-team-skin/`.

---

## Skin pack format (`.aamp`)

A `.aamp` file is a standard ZIP containing:

```
skin.manifest.json      ← normative root (required)
sprites/                ← PNG/SVG sprite sheets (optional)
shaders/                ← GLSL ES 3.00 fragment shaders (optional)
sounds/                 ← OGG/MP3 sound cues (optional)
README.md               ← human-readable notes (optional)
```

### `skin.manifest.json` fields

| Field | Type | Description |
|-------|------|-------------|
| `schema_version` | `"1.0"` | Fixed at Phase 1 |
| `id` | string | Unique identifier — used as the registry folder name |
| `tokens` | object | Design tokens: `color`, `font`, `motion`, `spacing` |
| `sprites` | array | `{ id, uri, width, height }` |
| `shaders` | array | `{ id, stage, uri }` — `stage` is `"pre"` or `"post"` |
| `sounds` | array | `{ id, uri, trigger }` — `trigger` is an SSE event name |
| `cli_palette` | object | `{ ansi: {...}, glyphs: { bullet, running, done, failed, warning, paused } }` |
| `layout` | object | `{ windows: [...], minimode: { rows, cols } }` |
| `plugins` | array | AgentVis plugin refs (Phase 2+) |
| `permissions` | object | `{ events, egress, audio, haptic }` — `egress: []` = deny-all |
| `signature` | object or `null` | `{ algorithm, value, signed_at }` — `null` in drafts |

Minimal example:

```jsonc
{
  "schema_version": "1.0",
  "id": "my-team-skin",
  "tokens": {
    "color": {
      "bg": "#0d1117",
      "surface": "#161b22",
      "accent": "#58a6ff",
      "text": "#c9d1d9",
      "muted": "#6e7681"
    },
    "font": { "family": "JetBrains Mono, monospace", "size_base": 13 },
    "motion": { "enabled": true, "reduced": false },
    "spacing": { "unit": 8 }
  },
  "permissions": { "events": [], "egress": [], "audio": false, "haptic": false },
  "signature": null
}
```

---

## CLI reference

### `scaffold-skin`

```bash
benny agentamp scaffold-skin <skin_id> [--drafts-dir <path>]
```

Creates a deterministic draft tree under `drafts_dir/<skin_id>/` (default: `$BENNY_HOME/agentamp/drafts/`).

- Always emits `"signature": null` — auto-signing is forbidden (GATE-AAMP-AUTOSIGN-1).
- Idempotent: calling twice with the same id produces identical `skin.manifest.json`.
- `skin_id` must match `[A-Za-z0-9][A-Za-z0-9_-]{0,63}`.

### `pack`

```bash
benny agentamp pack <draft_dir> --out <path.aamp>
```

Zips the draft directory into a `.aamp` file. All files under `draft_dir/` are included, sorted deterministically. Run `sign` before `install`.

### `sign`

```bash
benny agentamp sign <path.aamp>
```

Computes an HMAC-SHA256 over the manifest's canonical payload and writes the `signature` object back into `skin.manifest.json` inside the zip.

The key is resolved from `BENNY_HMAC_KEY` (hex-encoded 32-byte secret) — the same env var used by `benny/sdlc/checkpoint.py` and `benny/core/manifest_hash.py`. In dev environments, a built-in fallback key is used automatically, but production deployments **must** set `BENNY_HMAC_KEY`.

```bash
# Set key (hex-encode a 32-byte secret)
export BENNY_HMAC_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")

# Persist it in your .env / service config for all Benny processes
```

### `install`

```bash
benny agentamp install <path.aamp> [--workspace <ws>] [--dev-mode]
```

1. Opens the zip and checks every member name for path-traversal sequences.
2. Reads and parses `skin.manifest.json`.
3. Verifies the HMAC signature (`SkinSignatureMissing` if absent, `SkinSignatureInvalid` if wrong).
4. Copies the pack to `$BENNY_HOME/agentamp/registry/<skin_id>/`.
5. Writes an `install.json` receipt.

`--dev-mode` skips signature verification. This flag is blocked at release by `GATE-AAMP-DEVMODE-1` — never use it in production.

Exit codes:
| Code | Meaning |
|------|---------|
| 0 | Installed successfully |
| 1 | I/O or parse error |
| 2 | Security rejection (missing sig, invalid sig, path traversal) |

---

## HMAC key setup

All Benny processes that sign or verify must share the same key:

```bash
# Generate once per environment:
python -c "import secrets; print(secrets.token_hex(32))"
# → e.g. 3f8a2b1c...

# Set in your shell profile / systemd unit / .env:
export BENNY_HMAC_KEY=3f8a2b1c...
```

The same key signs `SwarmManifest` objects, checkpoints, and skin packs — one secret for the whole Benny install.

---

## Security guarantees

| Threat | Mitigation |
|--------|-----------|
| Zip path traversal (e.g. `../evil.py`) | Every member name checked against `_TRAVERSAL_RE` before anything is read; raises `SkinPathEscape` |
| Unsigned or tampered pack installed | HMAC-SHA256 checked on every `install`; no bypass flag in production mode |
| Skin calling external URLs | `permissions.egress` defaults to `[]` (deny-all); enforced by plugin sandbox (Phase 2) |
| Absolute paths in skin assets | SR-1 ratchet gate (`pytest tests/portability/`) catches new violations |
| Auto-signing by LLM design tool | `aamp.designer.auto_sign` is `false` and must remain `false` (GATE-AAMP-AUTOSIGN-1) |

---

## Release gates (`G-AAMP-*`)

These are appended to `docs/requirements/release_gates.yaml` and enforced by `tests/release/test_aamp_release_gate.py` (Phase 9).

| Gate | Condition |
|------|-----------|
| `GATE-AAMP-AUTOSIGN-1` | `aamp.designer.auto_sign = false`; install unconditionally rejects unsigned packs |
| `GATE-AAMP-DEVMODE-1` | `aamp.dev_mode = false` at release |
| `GATE-AAMP-CSP-1` | `aamp.sandbox.csp_strict = true` at release |
| `GATE-AAMP-POLICY-1` | `aamp.policy.auto_load_remote_skins = false` at release |
| `G-AAMP-COV` | Coverage ≥ 85% on `benny/agentamp/**` and `frontend/src/agentamp/**` |
| `G-AAMP-OFF` | `BENNY_OFFLINE=1` end-to-end smoke passes |
| `G-AAMP-SR1` | SR-1 ratchet not raised by AAMP-001 |
| `G-AAMP-SIG` | All shipped reference skins verify under HMAC at boot |
| `G-AAMP-BUNDLE` | UI bundle delta ≤ 350 KB gzipped |
| `G-AAMP-LEDGER` | Every loaded skin/plugin in smoke session has a ledger entry |

---

## Offline use (`BENNY_OFFLINE=1`)

All Phase 1 operations are fully offline-safe:

- `scaffold-skin`, `pack`, `sign`, `install` are stdlib-only — no network calls.
- The HMAC key is read from `BENNY_HMAC_KEY` env var; no key server is contacted.
- The local registry under `$BENNY_HOME/agentamp/registry/` is the only storage target.

Later phases that pull from the remote curated index (`G-AAMP-OFF` gate for Phase 8+) will gate on `BENNY_OFFLINE` and refuse gracefully.

---

## Where the code lives

| Concern | Path |
|---------|------|
| Pydantic contracts (`SkinManifest`, etc.) | `benny/agentamp/contracts.py` |
| HMAC sign / verify | `benny/agentamp/signing.py` |
| Zip loader + path-traversal guard | `benny/agentamp/skin.py` |
| Scaffold generator | `benny/agentamp/scaffold.py` |
| CLI handlers | `benny/agentamp/cli.py` |
| Policy intent constants | `benny/governance/policy.py` (`AAMP_INTENT_*`) |
| Tests | `tests/agentamp/` |
| Release gates config | `docs/requirements/release_gates.yaml` |

---

## Phase roadmap

| Phase | What ships | Guide |
|-------|-----------|-------|
| **1** ✅ | Skin pack format, HMAC signing, scaffold + pack + sign + install | This document |
| 2 | AgentVis plugin SDK, iframe sandbox, CSP enforcement | *(Phase 2 docs)* |
| 3 | DSP-A pipeline — 32-bin spectrum, VU meters, loop heatmap | *(Phase 3 docs)* |
| 4 | Mini-mode (Textual TUI), skinnable CLI palette | *(Phase 4 docs)* |
| 5 | Equalizer panel — manifest knobs (temp, top_p, concurrency, budget) | *(Phase 5 docs)* |
| 6 | Playlist & enqueue, Layout DSL, user state under `$BENNY_HOME` | *(Phase 6 docs)* |
| 7 | Effects pipeline, JSON-LD provenance per plugin invocation | *(Phase 7 docs)* |
| 8 | `skin_designer` LLM skill, local marketplace registry | *(Phase 8 docs)* |
| 9 | Release-gate hardening, compliance pillar §11 | *(Phase 9 docs)* |
