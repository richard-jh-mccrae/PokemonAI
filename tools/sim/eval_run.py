"""Statistical planning helpers for paired evaluation runs.

The live legacy evaluation runner was removed with the old agent runtime.  These
stdlib-only helpers remain the contract for sizing common-opponent evaluations.
"""
from __future__ import annotations

_Z_POWER = 2.80

PRESETS = {"quick": 0.05, "default": 0.03, "fine": 0.02}
DEFAULT_PRESET = "default"


def per_arm_games(delta: float) -> int:
    """Return games per arm for 95% confidence and 80% power."""
    if delta <= 0:
        raise ValueError(f"delta must be positive, got {delta}")
    return round(0.5 * (_Z_POWER / delta) ** 2)


def preset_delta(preset: str) -> float:
    """Resolve a named detectable win-rate delta."""
    if preset not in PRESETS:
        raise ValueError(f"unknown preset {preset!r} (choose from {sorted(PRESETS)})")
    return PRESETS[preset]


def games_per_matchup(per_arm_total: int, n_opponents: int) -> int:
    """Spread a per-arm game budget across opponents without under-buying."""
    if n_opponents <= 0:
        return 0
    return max(1, -(-per_arm_total // n_opponents))


def matchup_cells(opponents: list[str]) -> list[dict[str, object]]:
    """Return one evaluation cell per opponent and seat."""
    return [{"opponent": opponent, "seat": seat} for opponent in opponents for seat in (0, 1)]
