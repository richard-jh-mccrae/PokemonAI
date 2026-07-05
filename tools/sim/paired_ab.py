"""Paired-delta A/B analysis for the Tier-5 cross-deck gauntlet (grilled 2026-07-05).

Cross-deck, ``deck@on vs deck@off`` is impossible (that IS the useless mirror). Instead, per directed
matchup (our deck D vs a FIXED baseline opponent O≠D), measure ``winrate(D@on vs O) − winrate(D@off vs
O)`` and aggregate equally — the on−off difference subtracts out the raw deck matchup (D may beat O
55% regardless), leaving only the value-model effect. The flip rule ships the learned seam ONLY on a
demonstrated non-regression with zero crashes (never on a green unit suite alone).
"""
from __future__ import annotations

import math

_Z95 = 1.959964            # standard normal 97.5th percentile
_REG_TOL = 0.01            # a CI lower bound below −1% is a real regression → park


def matchup_delta(on_wins: int, on_n: int, off_wins: int, off_n: int) -> tuple[float, float]:
    """One matchup's win-rate delta (value-on − value-off vs the same opponent) and its variance (the
    sum of the two independent binomial-proportion variances)."""
    p_on = on_wins / on_n
    p_off = off_wins / off_n
    var = p_on * (1 - p_on) / on_n + p_off * (1 - p_off) / off_n
    return p_on - p_off, var


def paired_delta(matchups) -> dict:
    """Aggregate the equal-weighted mean delta across ``matchups`` (each a
    ``(on_wins, on_n, off_wins, off_n)`` tuple) with a 95% CI. The mean of independent per-matchup
    deltas has variance ``Σ var_i / k²``."""
    deltas, variances = [], []
    for m in matchups:
        d, v = matchup_delta(*m)
        deltas.append(d)
        variances.append(v)
    k = len(deltas)
    mean = sum(deltas) / k
    var = sum(variances) / (k * k)
    half = _Z95 * math.sqrt(var)
    return {"delta": mean, "ci_lo": mean - half, "ci_hi": mean + half, "n_matchups": k}


def flips_on(result: dict, *, crashes: int, reg_tol: float = _REG_TOL) -> bool:
    """The grilled T5 flip rule: value_model ON iff the aggregate delta ≥ 0 AND the CI lower bound is
    at or above −``reg_tol`` (rules out a real regression) AND zero games crashed. Otherwise park OFF."""
    return result["delta"] >= 0 and result["ci_lo"] >= -reg_tol and crashes == 0
