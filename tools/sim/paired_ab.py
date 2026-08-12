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
_REG_TOL = 0.01            # a CI lower bound below −1% is a real regression → park (POST-COMPOSITION)
MID_BUILD_REG_TOL = 0.05   # mid-build (ADR-0072): the widest bound the standing n=200/arm/matchup
                           # run can adjudicate. Wide on purpose — it excludes CATASTROPHES only.


def matchup_delta(on_wins: int, on_n: int, off_wins: int, off_n: int) -> tuple[float, float]:
    """One matchup's win-rate delta (value-on − value-off vs the same opponent) and its variance (the
    sum of the two independent binomial-proportion variances)."""
    p_on = on_wins / on_n
    p_off = off_wins / off_n
    var = p_on * (1 - p_on) / on_n + p_off * (1 - p_off) / off_n
    return p_on - p_off, var


def paired_delta(matchups) -> dict:
    """Equal-weighted mean delta across ``(on_wins, on_n, off_wins, off_n)`` matchups with a 95% CI.
    The mean of independent per-matchup deltas has variance ``Σ var_i / k²``."""
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
    """The POST-COMPOSITION flip rule (ADR-0072 decision 1): ON iff delta ≥ 0 AND CI lower bound ≥
    −``reg_tol`` AND zero crashes. Mid-build, use `mid_build_verdict` instead."""
    return result["delta"] >= 0 and result["ci_lo"] >= -reg_tol and crashes == 0


def mid_build_verdict(result: dict, *, crashes: int, reg_tol: float = MID_BUILD_REG_TOL) -> bool:
    """The mid-build TRIPWIRE (ADR-0072 decision 1): zero crashes AND CI lower bound ≥ −``reg_tol``,
    with NO delta clause. It claims no catastrophe — NOT non-regression; merit needs separate evidence."""
    return result["ci_lo"] >= -reg_tol and crashes == 0


#: The two stage rules (ADR-0072 decision 1). Lives HERE, beside both verdict functions, not in one
#: runner: a second copy of "which rule graded this run" is what mislabelled a whole runner.
STAGES = {
    "mid-build": (mid_build_verdict, MID_BUILD_REG_TOL,
                  "CI-lo>=-0.05 AND crashes==0 (NO delta clause)", "TRIPWIRE"),
    "post-composition": (flips_on, _REG_TOL,
                         "delta>=0 AND CI-lo>=-0.01 AND crashes==0", "FLIP"),
}
