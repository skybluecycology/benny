"""`$BENNY_HOME` layout, init, validate, and uninstall.

This module is the single authority for what a portable Benny install looks
like on disk. The layout is declared once, at the top, and every other piece
of the system resolves paths through a ``BennyHome`` instance.

See PBR-001 §4.1 for the declared shape.
"""
from __future__ import annotations

import dataclasses
import shutil
import uuid
from pathlib import Path
from typing import Iterable, Literal

Profile = Literal["app", "native"]

SCHEMA_VERSION = "1.0.0"

# Shared layout — present under both profiles.
SHARED_DIRS: tuple[str, ...] = (
    "bin",
    "config",
    "data",
    "data/runs",
    "data/lineage",
    "data/vector",
    "data/graph",
    "workspaces",
    "models",
    "logs",
    "tmp",
    "state",
)

# Profile-specific subtrees — mutually exclusive.
APP_DIRS: tuple[str, ...] = ("app",)
NATIVE_DIRS: tuple[str, ...] = ("runtime", "runtime/python", "runtime/node", "runtime/neo4j")

# Config files seeded on fresh init.
_BENNY_TOML_TEMPLATE = """# Portable Benny config (see PBR-001 §4.1).
# Paths declared here MUST be either relative or under this $BENNY_HOME root.
schema_version = "{schema_version}"
profile = "{profile}"

[runtime]
# Port assignments match benny/core/models.py LOCAL_PROVIDERS defaults.
lemonade_port = 13305
neo4j_bolt_port = 7687
neo4j_http_port = 7474
api_port = 8000
ui_port = 5173
"""

_VOICES_JSON = """{
  "_comment": "TTS voice registry; closes the hardcoded af_sky gap (PBR-001 §4.4).",
  "providers": {
    "lemonade": {
      "voices": ["af_sky", "bf_emma", "bm_george", "af_bella"],
      "default": "af_sky"
    }
  }
}
"""

_SERVER_OPS_ALLOWLIST_JSON = """{
  "_comment": "Allow-listed local-LLM server-ops targets (LC-2 scope).",
  "commands": ["status", "health", "start", "stop"],
  "services": ["lemonade", "ollama", "fastflowlm", "neo4j", "marquez"]
}
"""


class PortableHomeError(RuntimeError):
    """Raised on illegal portable-home state transitions."""


@dataclasses.dataclass(frozen=True)
class BennyHome:
    root: Path
    profile: Profile

    @property
    def bin_dir(self) -> Path:
        return self.root / "bin"

    @property
    def config_dir(self) -> Path:
        return self.root / "config"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def workspaces_dir(self) -> Path:
        return self.root / "workspaces"

    @property
    def models_dir(self) -> Path:
        return self.root / "models"

    @property
    def state_dir(self) -> Path:
        return self.root / "state"

    @property
    def profile_subtree(self) -> Path:
        return self.root / ("app" if self.profile == "app" else "runtime")


@dataclasses.dataclass(frozen=True)
class ValidationReport:
    ok: bool
    problems: tuple[str, ...]


# ---- internals -------------------------------------------------------------


def _expected_dirs(profile: Profile) -> Iterable[str]:
    yield from SHARED_DIRS
    yield from (APP_DIRS if profile == "app" else NATIVE_DIRS)


def _read_existing_profile(root: Path) -> Profile | None:
    lock = root / "state" / "profile-lock"
    if not lock.is_file():
        return None
    value = lock.read_text(encoding="utf-8").strip()
    if value not in ("app", "native"):
        return None
    return value  # type: ignore[return-value]


def _seed_state(root: Path, profile: Profile) -> None:
    state = root / "state"
    state.mkdir(parents=True, exist_ok=True)

    device_id_path = state / "device-id"
    if not device_id_path.is_file():
        device_id_path.write_text(str(uuid.uuid4()), encoding="utf-8")

    (state / "schema-version").write_text(SCHEMA_VERSION, encoding="utf-8")
    (state / "profile-lock").write_text(profile, encoding="utf-8")


def _seed_config(root: Path, profile: Profile) -> None:
    config = root / "config"
    config.mkdir(parents=True, exist_ok=True)

    toml_path = config / "benny.toml"
    if not toml_path.is_file():
        toml_path.write_text(
            _BENNY_TOML_TEMPLATE.format(schema_version=SCHEMA_VERSION, profile=profile),
            encoding="utf-8",
        )

    (config / "profile").write_text(profile, encoding="utf-8")

    voices_path = config / "voices.json"
    if not voices_path.is_file():
        voices_path.write_text(_VOICES_JSON, encoding="utf-8")

    allow_path = config / "server_ops_allowlist.json"
    if not allow_path.is_file():
        allow_path.write_text(_SERVER_OPS_ALLOWLIST_JSON, encoding="utf-8")


# ---- public API ------------------------------------------------------------


def init(root: Path, *, profile: Profile) -> BennyHome:
    """Create or refresh a portable $BENNY_HOME. Idempotent within a profile.

    Raises ``PortableHomeError`` if the root was previously initialised with
    a different profile (cross-profile switching is handled by a future
    `benny migrate`, not init).
    """
    if profile not in ("app", "native"):
        raise PortableHomeError(f"unknown profile: {profile!r}")

    root = Path(root)
    existing = _read_existing_profile(root)
    if existing is not None and existing != profile:
        raise PortableHomeError(
            f"profile mismatch: $BENNY_HOME at {root} was initialised as "
            f"{existing!r}; refusing to switch to {profile!r}. "
            "Use `benny migrate` for cross-profile changes."
        )

    for rel in _expected_dirs(profile):
        (root / rel).mkdir(parents=True, exist_ok=True)

    _seed_state(root, profile)
    _seed_config(root, profile)

    return BennyHome(root=root, profile=profile)


def validate(root: Path) -> ValidationReport:
    """FR-1 structural check. Returns a report; never raises for missing dirs."""
    root = Path(root)
    problems: list[str] = []

    profile = _read_existing_profile(root)
    if profile is None:
        return ValidationReport(ok=False, problems=("state/profile-lock missing or invalid",))

    for rel in _expected_dirs(profile):
        if not (root / rel).is_dir():
            problems.append(f"missing directory: {rel}")

    for rel in ("state/device-id", "state/schema-version", "config/benny.toml", "config/profile"):
        if not (root / rel).is_file():
            problems.append(f"missing file: {rel}")

    # Mutually-exclusive subtree invariant.
    if profile == "app" and (root / "runtime").exists():
        problems.append("profile=app but runtime/ exists")
    if profile == "native" and (root / "app").exists():
        problems.append("profile=native but app/ exists")

    return ValidationReport(ok=not problems, problems=tuple(problems))


def uninstall(root: Path, *, keep_data: bool) -> None:
    """Remove the app/runtime boundary. With ``keep_data=True``, workspaces,
    models, data, config, and state survive — only the disposable app layer
    is removed. With ``keep_data=False``, the entire tree is deleted.
    """
    root = Path(root)
    if not root.exists():
        return

    if not keep_data:
        shutil.rmtree(root)
        return

    for rel in APP_DIRS + NATIVE_DIRS:
        victim = root / rel
        if victim.exists():
            shutil.rmtree(victim)
    # `bin/` is part of the app layer under both profiles — remove it too,
    # it will be re-seeded on the next init.
    bin_dir = root / "bin"
    if bin_dir.exists():
        shutil.rmtree(bin_dir)
    # Profile-lock stays: the user's intent (app vs native) is preserved
    # across reinstall.
