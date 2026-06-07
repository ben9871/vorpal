"""Voice registry — the user-facing voice suite.

Everything the user sees is in this registry: a curated list of narrators
with display names and descriptions.  Engines and blend recipes are
implementation detail.

v1 sources:
- Kokoro single voices (the 8 built-in voices)
- Kokoro blends (weighted mixes of two or more voice embeddings — a new
  narrator for free, no training required)

Blend recipe: {"blend": {"voice_a": weight_a, "voice_b": weight_b}}
Weights need not sum to 1 (they are L1-normalized at synthesis time).

Chunk-cache keys use the *resolved params*, not the registry id, so editing a
blend recipe correctly invalidates only the affected audio.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Optional


@dataclass
class VoiceEntry:
    id: str                     # the user-facing --voice id
    display_name: str           # "Heart" / "Sky Blend"
    engine: str                 # "kokoro"
    params: dict                # {"voice": "af_heart"} or {"blend": {...}, "speed": N}
    description: str            # one-line character description


def _params_cache_key(params: dict) -> str:
    """Stable string for use as the voice component of a chunk-cache key.

    For single voices this is just the voice name; for blends it is a short
    SHA-256 of the sorted JSON so recipe edits invalidate the cache.
    Speed is excluded — it's captured separately in the full cache key formula.
    """
    if "blend" in params:
        blob = json.dumps({"blend": params["blend"]}, sort_keys=True, ensure_ascii=False)
        return "blend_" + hashlib.sha256(blob.encode()).hexdigest()[:16]
    return params.get("voice", "unknown")


# ── curated registry ──────────────────────────────────────────────────────

VOICE_REGISTRY: dict = {
    # ── Kokoro single voices ──────────────────────────────────────────────
    "af_heart": VoiceEntry(
        id="af_heart",
        display_name="Heart",
        engine="kokoro",
        params={"voice": "af_heart"},
        description="Warm, expressive American female — the default narrator",
    ),
    "af_nova": VoiceEntry(
        id="af_nova",
        display_name="Nova",
        engine="kokoro",
        params={"voice": "af_nova"},
        description="Clear, bright American female",
    ),
    "af_sky": VoiceEntry(
        id="af_sky",
        display_name="Sky",
        engine="kokoro",
        params={"voice": "af_sky"},
        description="Lighter, airier American female",
    ),
    "am_echo": VoiceEntry(
        id="am_echo",
        display_name="Echo",
        engine="kokoro",
        params={"voice": "am_echo"},
        description="Resonant American male",
    ),
    "am_michael": VoiceEntry(
        id="am_michael",
        display_name="Michael",
        engine="kokoro",
        params={"voice": "am_michael"},
        description="Steady, neutral American male",
    ),
    "am_fenrir": VoiceEntry(
        id="am_fenrir",
        display_name="Fenrir",
        engine="kokoro",
        params={"voice": "am_fenrir"},
        description="Deep, commanding American male",
    ),
    "bf_emma": VoiceEntry(
        id="bf_emma",
        display_name="Emma",
        engine="kokoro",
        params={"voice": "bf_emma"},
        description="Clear, measured British female",
    ),
    "bm_george": VoiceEntry(
        id="bm_george",
        display_name="George",
        engine="kokoro",
        params={"voice": "bm_george"},
        description="Distinguished British male",
    ),

    # ── Kokoro blends — curated narrators made from voice mixes ──────────
    "blend_warm_bright": VoiceEntry(
        id="blend_warm_bright",
        display_name="Warm-Bright",
        engine="kokoro",
        params={"blend": {"af_heart": 0.65, "af_nova": 0.35}},
        description="Heart's warmth softened with Nova's clarity (female blend)",
    ),
    "blend_deep_steady": VoiceEntry(
        id="blend_deep_steady",
        display_name="Deep-Steady",
        engine="kokoro",
        params={"blend": {"am_fenrir": 0.55, "am_michael": 0.45}},
        description="Fenrir's depth grounded by Michael's steadiness (male blend)",
    ),
    "blend_transatlantic": VoiceEntry(
        id="blend_transatlantic",
        display_name="Transatlantic",
        engine="kokoro",
        params={"blend": {"af_heart": 0.5, "bf_emma": 0.5}},
        description="Equal blend of American Heart and British Emma",
    ),
}


def resolve_voice(voice_id: str) -> Optional[VoiceEntry]:
    """Return the VoiceEntry for the given id, or None if not found."""
    return VOICE_REGISTRY.get(voice_id)


def list_voices() -> list:
    """Return all registry entries as a sorted list."""
    return list(VOICE_REGISTRY.values())
