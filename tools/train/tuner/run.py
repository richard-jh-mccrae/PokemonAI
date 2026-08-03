"""Tuner orchestration: featurize each Correction, route by attribution, fit weights / propose.

Pure of I/O and engine: takes the Corrections, a constructed Pilot, and the authored seed
weights; returns the tuned overrides + Hypothesis proposals + skips. The CLI (`tune.py`) wires
the store, the engine-backed Pilot, and `tuned.json` around this.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .featurize import featurize
from .fit import DEFAULT_REG, fit_weights, margin_of, ranking_constraint
from .propose import ProposedHypothesis, propose_hypothesis


@dataclass
class TuneResult:
    overrides: dict                                  # {hyp_id: weight} -> tuned.json
    proposals: list[ProposedHypothesis] = field(default_factory=list)
    skipped: list = field(default_factory=list)      # [(correction, reason)]
    n_constraints: int = 0                            # W-route corrections fed to fit
    unsatisfied: list = field(default_factory=list)  # W-route corrections shipped weights can't honour
    base_satisfied: int = 0                           # constraints authored seeds already satisfy
    fit_adopted: bool = False                         # did fit beat seeds (else keep priors)?
    w_items: list = field(default_factory=list)       # [(correction, Constraint)] — for run report


def _n_satisfied(constraints, weights) -> int:
    return sum(1 for c in constraints if margin_of(c, weights) > 0)


def tune(corrections, pilot, seeds: dict, *, reg: float = DEFAULT_REG) -> TuneResult:
    """Route each Correction by derived attribution: `hypothesis:*` → a ranking constraint
    (W, fed to the weight fit); `missing_hypothesis` → a Hypothesis proposal (H); `tactical`
    or no-obs → skipped. A **scoped** Correction (turn, ADR-0049) bypasses the router
    entirely — it is an open plan-layer blunder, never a weight.

    The fit is soft-margin (regularised), so a contradictory W corpus no longer overfits silently.
    Two guards make the output trustworthy:
    - **Adoption gate** — the fitted weights are shipped *only if* they satisfy strictly more
      corrections than the authored seeds; otherwise the drift bought nothing (or traded laterally)
      and we keep the legible priors. (This is why a hand-curated `tuned.json` kept getting reset.)
    - **`unsatisfied`** — the corrections the *shipped* weights still can't honour: genuine conflicts,
      or blunders that need a new Hypothesis (H), not a weight.

    ``reg`` is the conservatism knob (see ``fit.DEFAULT_REG``): higher keeps weights near the authored
    seeds (won't gut a doctrine for a few extra ranks); lower lets clean corrections move them more."""
    constraints, w_corrs, proposals, skipped = [], [], [], []
    for corr in corrections:
        if corr.scope != "decision":
            # A turn blunder is a plan-layer error (ADR-0049): it short-circuits BEFORE
            # `ranking_constraint`, so a sequencing error can never move a Tier-0 weight. The
            # Anchor's fired-Hypothesis diff still travels along, as information for the routing.
            info = (featurize(corr, pilot).attribution
                    if corr.obs is not None and corr.correct else None)
            proposals.append(propose_hypothesis(corr, attribution=info))
            continue
        if corr.obs is None:
            skipped.append((corr, "no obs (backfill from replay)"))
            continue
        feat = featurize(corr, pilot)
        if feat.attribution.startswith("hypothesis:"):
            constraints.append(ranking_constraint(feat))
            w_corrs.append(corr)
        elif feat.attribution == "missing_hypothesis":
            proposals.append(propose_hypothesis(corr))
        else:
            skipped.append((corr, feat.attribution))

    base_satisfied = _n_satisfied(constraints, seeds)
    fitted = fit_weights(constraints, seeds, reg=reg) if constraints else dict(seeds)
    fit_adopted = _n_satisfied(constraints, fitted) > base_satisfied
    overrides = fitted if fit_adopted else dict(seeds)
    unsatisfied = [c for c, con in zip(w_corrs, constraints) if margin_of(con, overrides) <= 0]
    return TuneResult(overrides=overrides, proposals=proposals, skipped=skipped,
                      n_constraints=len(constraints), unsatisfied=unsatisfied,
                      base_satisfied=base_satisfied, fit_adopted=fit_adopted,
                      w_items=list(zip(w_corrs, constraints)))
