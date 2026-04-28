"""benny.agentamp — AgentAmp: skinnable, pluggable agentic cockpit (AAMP-001).

Public surface (Phase 1)
  contracts  — Pydantic models for SkinManifest, SkinTokens, etc.
  signing    — sign_skin_pack() / verify_skin_pack()
  skin       — load() — open .aamp zip with path-traversal guard + sig verify
  scaffold   — scaffold_skin() — deterministic draft tree generator

Public surface (Phase 2)
  plugins    — PluginManifest, PluginPermissions, filter_events(),
               validate_permissions_subset(), PLUGIN_SANDBOX_ATTRS, PLUGIN_CSP
  sandbox    — SandboxHost, MountedPlugin, PluginPermissionsViolation

Feature flag: ``aamp.enabled`` (AAMP-F32). Checked at CLI dispatch; not re-checked here.
"""

from .contracts import (
    SkinCliPalette,
    SkinGlyphs,
    SkinLayout,
    SkinManifest,
    SkinMinimode,
    SkinPermissions,
    SkinPlugin,
    SkinShader,
    SkinSignature,
    SkinSound,
    SkinSprite,
    SkinTokens,
    SkinWindow,
)
from .skin import (
    SkinPathEscape,
    SkinSignatureInvalid,
    SkinSignatureMissing,
    load,
)
from .signing import sign_skin_pack, verify_skin_pack
from .scaffold import scaffold_skin
from .plugins import (
    PLUGIN_CSP,
    PLUGIN_SANDBOX_ATTRS,
    PLUGIN_WATCHDOG_TIMEOUT_S,
    PluginManifest,
    PluginPermissions,
    filter_events,
    validate_permissions_subset,
)
from .sandbox import (
    MountedPlugin,
    PluginPermissionsViolation,
    SandboxHost,
)

__all__ = [
    # Phase 1 — contracts
    "SkinManifest",
    "SkinTokens",
    "SkinCliPalette",
    "SkinGlyphs",
    "SkinLayout",
    "SkinMinimode",
    "SkinPermissions",
    "SkinPlugin",
    "SkinShader",
    "SkinSignature",
    "SkinSound",
    "SkinSprite",
    "SkinWindow",
    # Phase 1 — exceptions
    "SkinPathEscape",
    "SkinSignatureMissing",
    "SkinSignatureInvalid",
    # Phase 1 — functions
    "load",
    "sign_skin_pack",
    "verify_skin_pack",
    "scaffold_skin",
    # Phase 2 — plugin contracts + constants
    "PluginManifest",
    "PluginPermissions",
    "PLUGIN_SANDBOX_ATTRS",
    "PLUGIN_CSP",
    "PLUGIN_WATCHDOG_TIMEOUT_S",
    "filter_events",
    "validate_permissions_subset",
    # Phase 2 — sandbox host
    "SandboxHost",
    "MountedPlugin",
    "PluginPermissionsViolation",
]
