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


@dataclass
class UnionVerifyResult:
    """The parallel-mode JOIN gate (ADR-0018): every authored Hypothesis verified TOGETHER against
    the union of all Corrections, so one fan-out cluster's rule can't silently regress another's."""
    passed: bool
    clusters_satisfied: dict              # cluster label -> bool (satisfied in the union)
    regressed: list[int] = field(default_factory=list)     # were satisfied pre-round, now violated
    newly_fixed: list[int] = field(default_factory=list)


def _satisfied(corrections, pilot, seeds):
    constraints = [ranking_constraint(featurize(c, pilot)) for c in corrections]
    return satisfied_after_fit(constraints, seeds)


def _base_hyp_ids(pilot) -> set:
    """The Hypothesis ids already in a Pilot (general + deck), per ``pilot.py`` scoring."""
    return {h.id for h in (*pilot.general.hypotheses, *pilot.strategy.hypotheses)}


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


def union_verify(authored, corrections, pilot_with, seeds: dict,
                 clusters: dict[str, list[int]]) -> UnionVerifyResult:
    """Join gate for parallel-mode fan-out: verify EVERY authored Hypothesis at once against the
    UNION of all Corrections (ADR-0018).

    Where per-cluster ``verify`` compares *pre-round* vs *pre-round + one candidate*, this compares
    a **seeds-only baseline** against the **all-rules-merged** world — the only comparison that can
    reveal cluster A's rule regressing cluster B's already-satisfied Correction. Two wiring hazards
    make that comparison meaningless if a hand-rolled join gets them wrong, so both are enforced here:

    1. **No double-count.** All ``authored`` rules are injected via a single ``pilot_with(authored)``
       with the matching union seeds — never layered on a pilot that already holds them. (``score``
       sums every fired weight with no dedupe, ``pilot.py``; a duplicated id is silently double-
       weighted and flips which option wins.) Duplicate authored ids raise.
    2. **Clean baseline.** ``pilot_with([])`` must be the pre-round strategy with NONE of this
       round's authored rules — otherwise their interference sits in both ``base`` and ``union`` and
       ``regressed`` can never see it. A contaminated baseline raises.

    Args:
        authored: the round's authored Hypotheses (each with ``.id`` / ``.weight``), one per fixed
            cluster — exactly once each.
        corrections: the full corpus to (re-)rank. Include the previously-``covered`` Corrections,
            not just the parallel-batch members — a new rule can steal a covered Correction's option.
        pilot_with: ``pilot_with(extra_hyps) -> Pilot`` whose ``general.hypotheses +
            strategy.hypotheses`` == base + extra. ``pilot_with([])`` MUST be seeds-only.
        seeds: the pre-round seed weights (no authored ids).
        clusters: label -> the Correction indices that cluster is meant to fix.

    Returns:
        ``UnionVerifyResult``: ``passed`` iff every cluster is satisfied in the union AND nothing
        previously satisfied regressed.
    """
    ids = [h.id for h in authored]
    dups = sorted({i for i in ids if ids.count(i) > 1})
    if dups:
        raise ValueError(f"duplicate authored hypothesis ids {dups} — each authored Hypothesis must "
                         "appear once across the fan-out (a dict-merge of seeds would drop one)")

    base_pilot = pilot_with([])
    contaminated = sorted(_base_hyp_ids(base_pilot) & set(ids))
    if contaminated:
        raise ValueError(f"baseline pilot_with([]) already contains authored hyps {contaminated} — it "
                         "must be the pre-round strategy (seeds-only), none of this round's authored rules")

    base = _satisfied(corrections, base_pilot, seeds)
    union_seeds = {**seeds, **{h.id: h.weight for h in authored}}
    union = _satisfied(corrections, pilot_with(list(authored)), union_seeds)

    n = len(corrections)
    regressed = [i for i in range(n) if base[i] and not union[i]]
    newly_fixed = [i for i in range(n) if not base[i] and union[i]]
    clusters_satisfied = {label: all(union[i] for i in members) for label, members in clusters.items()}
    return UnionVerifyResult(
        passed=all(clusters_satisfied.values()) and not regressed,
        clusters_satisfied=clusters_satisfied,
        regressed=regressed,
        newly_fixed=newly_fixed,
    )
