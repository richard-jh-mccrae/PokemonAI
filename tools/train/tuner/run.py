"""Tuner orchestration: featurize each Correction, route by attribution, fit weights / propose.

Pure of I/O and engine: takes the Corrections, a constructed Pilot, and the authored seed
weights; returns the tuned overrides + Hypothesis proposals + skips. The CLI (`tune.py`) wires
the store, the engine-backed Pilot, and `tuned.json` around this.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .featurize import featurize
from .fit import fit_weights, ranking_constraint
from .propose import ProposedHypothesis, propose_hypothesis


@dataclass
class TuneResult:
    overrides: dict                                  # {hyp_id: weight} -> tuned.json
    proposals: list[ProposedHypothesis] = field(default_factory=list)
    skipped: list = field(default_factory=list)      # [(correction, reason)]


def tune(corrections, pilot, seeds: dict) -> TuneResult:
    """Route each Correction by derived attribution: `hypothesis:*` → a ranking constraint
    (W, fed to the weight fit); `missing_hypothesis` → a Hypothesis proposal (H); `tactical`
    or no-obs → skipped."""
    constraints, proposals, skipped = [], [], []
    for corr in corrections:
        if corr.obs is None:
            skipped.append((corr, "no obs (backfill from replay)"))
            continue
        feat = featurize(corr, pilot)
        if feat.attribution.startswith("hypothesis:"):
            constraints.append(ranking_constraint(feat))
        elif feat.attribution == "missing_hypothesis":
            proposals.append(propose_hypothesis(corr))
        else:
            skipped.append((corr, feat.attribution))
    overrides = fit_weights(constraints, seeds) if constraints else dict(seeds)
    return TuneResult(overrides=overrides, proposals=proposals, skipped=skipped)
