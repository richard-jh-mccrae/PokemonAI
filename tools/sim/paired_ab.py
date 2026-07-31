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
MID_BUILD_REG_TOL = 0.05   # mid-build (ADR-0072): the bound the standing n=200/arm/matchup run can
                           # actually adjudicate. Achieved half-width there is ~3.4 pp, so a truly
                           # neutral swap clears −5 pp with margin; −3 pp would need ~7,100 games and
                           # −1 pp ~28,000. Wide on purpose: it excludes CATASTROPHES, nothing more.


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
    at or above −``reg_tol`` (rules out a real regression) AND zero games crashed. Otherwise park OFF.

    This is the **post-composition** rule (#136 directive 6, ADR-0072 decision 1): it applies from
    #145 onward, once `state_value` and the Turn Planner consume the equations and a positive
    win-rate delta is a meaningful thing to demand. Mid-build, use `mid_build_verdict`."""
    return result["delta"] >= 0 and result["ci_lo"] >= -reg_tol and crashes == 0


def mid_build_verdict(result: dict, *, crashes: int, reg_tol: float = MID_BUILD_REG_TOL) -> bool:
    """The **mid-build Tripwire** (ADR-0072 decision 1, #167): zero crashes AND a CI lower bound at or
    above −``reg_tol``. **There is no delta clause.**

    A mid-build decider swap (Phases 1a–1g) is not trying to raise win rate — it makes ONE axis
    correct in ONE currency so #165 and #145 can compose the axes. Phase 1b measured what happens
    when `flips_on` is pointed at such a swap: −1.17 pp, 95% CI [−4.59, +2.25], 0 crashes / 2400
    games, verdict False — while the pooled 4800-game estimate (−1.06 pp, CI [−3.90, +1.78])
    demonstrated neither a regression nor a non-regression. Clearing `ci_lo >= −1%` near a zero delta
    needs n ≈ 2340/arm/matchup (~28,000 games, 8–10 h), and even then `delta >= 0` is a coin flip on a
    neutral swap — so the clause can only ever be passed by a swap with a positive win-rate effect.

    What this verdict claims is therefore deliberately narrow: **no catastrophe, and no crashes.** It
    is NOT a claim of non-regression. Merit belongs to the two deterministic per-frame gates
    (`train.gates`) — the Decision Gate and the Discrimination Gate — which answer exactly rather
    than statistically. The delta, CI and achieved half-width are recorded beside this verdict and
    never gate.
    """
    return result["ci_lo"] >= -reg_tol and crashes == 0


#: The two stage rules of #136 directive 6 (ADR-0072 decision 1). ``mid-build`` (Phases 1a–1g) is the
#: Tripwire — crashes==0 AND CI-lo >= -5%, NO delta clause; merit lives in the two deterministic
#: per-frame gates (`train.gates`). ``post-composition`` (#145 onward) is `flips_on` verbatim.
#:
#: Lives HERE, beside the two verdict functions, rather than in one runner (Issue #228). It was
#: private to `gauntlet_swap_ab.py`, so the OVERLAY runner (`gauntlet_ab.py`) had no way to name its
#: stage and printed `flips_on`'s post-composition verdict for a mid-build swap — the exact
#: mislabelling ADR-0072 Amendment B fixed on the swap runner, surviving on its sibling. A second
#: copy of "which rule graded this run" is the one thing that must not exist in two places.
STAGES = {
    "mid-build": (mid_build_verdict, MID_BUILD_REG_TOL,
                  "CI-lo>=-0.05 AND crashes==0 (NO delta clause)", "TRIPWIRE"),
    "post-composition": (flips_on, _REG_TOL,
                         "delta>=0 AND CI-lo>=-0.01 AND crashes==0", "FLIP"),
}
