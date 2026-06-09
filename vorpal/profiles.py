"""Listening-target loudness profiles — Phase 27.

Named presets for the mastering stage.  Each profile specifies loudnorm
parameters tuned for a particular playback context.

Profiles:
  headphones: −18 LUFS, LRA=11  (default — current behaviour, good dynamic range)
  car:        −16 LUFS, LRA=8   (louder, tighter compression for noisy environments)
  speaker:    −20 LUFS, LRA=15  (quieter, wide dynamic range for hi-fi speakers)

The profile affects only the mastering stage.  Synthesis cache keys are
independent of profile, so switching profile does not trigger re-synthesis.
"""

from typing import NamedTuple, Optional


class LoudnessProfile(NamedTuple):
    name: str
    target_lufs: float   # integrated loudness target (LUFS)
    target_lra: float    # loudness range target (LU) — controls compression
    target_tp: float     # true peak ceiling (dBTP)
    description: str


PROFILES: dict = {
    "headphones": LoudnessProfile(
        name="headphones",
        target_lufs=-18.0,
        target_lra=11.0,
        target_tp=-1.5,
        description="−18 LUFS, natural dynamics — default for headphone listening",
    ),
    "car": LoudnessProfile(
        name="car",
        target_lufs=-16.0,
        target_lra=8.0,
        target_tp=-1.5,
        description="−16 LUFS, tighter compression — louder and clearer in noisy car environments",
    ),
    "speaker": LoudnessProfile(
        name="speaker",
        target_lufs=-20.0,
        target_lra=15.0,
        target_tp=-1.5,
        description="−20 LUFS, wider dynamics — higher fidelity on home speakers or hi-fi",
    ),
}

DEFAULT_PROFILE = "headphones"


def get_profile(name: Optional[str]) -> LoudnessProfile:
    """Return the named profile, or the default if name is None."""
    if name is None:
        name = DEFAULT_PROFILE
    if name not in PROFILES:
        raise ValueError(
            f"Unknown profile {name!r}. Available: {', '.join(PROFILES)}"
        )
    return PROFILES[name]
