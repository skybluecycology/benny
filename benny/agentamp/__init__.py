"""benny.agentamp — AgentAmp: skinnable, pluggable agentic cockpit (AAMP-001 Phase 1).

Public surface:
  contracts  — Pydantic models for SkinManifest, SkinTokens, etc.
  signing    — sign_skin_pack() / verify_skin_pack()
  skin       — load() — open .aamp zip with path-traversal guard + sig verify
  scaffold   — scaffold_skin() — deterministic draft tree generator

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

__all__ = [
    # contracts
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
    # exceptions
    "SkinPathEscape",
    "SkinSignatureMissing",
    "SkinSignatureInvalid",
    # functions
    "load",
    "sign_skin_pack",
    "verify_skin_pack",
    "scaffold_skin",
]
