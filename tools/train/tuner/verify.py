"""The Verifier — the deterministic accuracy gate for an authored Hypothesis (ADR-0018).

Inject the candidate, re-fit weights over *all* Corrections, and accept only if it lets the fit
satisfy its target cluster (`correct ≻ chosen`) without regressing any Correction that was already
satisfied. (Suite-green is a separate `pytest` step the authoring skill runs — it catches
over-firing on non-Correction states.)
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .featurize import featurize
from .fit import ranking_constraint, satisfied_after_fit


@dataclass
class VerifyResult:
    passed: bool
    cluster_satisfied: bool
    regressed: list[int] = field(default_factory=list)     # were satisfied, now violated
    newly_fixed: list[int] = field(default_factory=list)


def _satisfied(corrections, pilot, seeds):
    constraints = [ranking_constraint(featurize(c, pilot)) for c in corrections]
    return satisfied_after_fit(constraints, seeds)


def verify(candidate, corrections, pilot_with, seeds: dict, cluster: list[int]) -> VerifyResult:
    """Gate ``candidate`` against the corpus. ``pilot_with(extra_hyps)`` builds a Pilot with the
    given extra Hypotheses; ``cluster`` are the indices the candidate is meant to fix."""
    base = _satisfied(corrections, pilot_with([]), seeds)
    cand = _satisfied(corrections, pilot_with([candidate]), {**seeds, candidate.id: candidate.weight})

    cluster_satisfied = all(cand[i] for i in cluster)
    regressed = [i for i in range(len(corrections)) if base[i] and not cand[i]]
    newly_fixed = [i for i in range(len(corrections)) if not base[i] and cand[i]]
    return VerifyResult(
        passed=cluster_satisfied and not regressed,
        cluster_satisfied=cluster_satisfied,
        regressed=regressed,
        newly_fixed=newly_fixed,
    )
