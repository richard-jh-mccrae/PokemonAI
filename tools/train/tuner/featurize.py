"""Featurize a Correction by replaying the Pilot on its embedded agent observation.

The Pilot's ``explain(obs)`` returns an ``OptionTrace`` per option whose ``.fired`` is the
set of Hypotheses that fired (the feature vector) and ``.tactical`` the combat term. We read
those for the ``chosen`` and ``correct`` options and derive the attribution (ADR-0017).
"""
from __future__ import annotations

from dataclasses import dataclass

from .attribution import derive_attribution


@dataclass
class Featurization:
    attribution: str
    chosen_fired: list[str]      # Hypothesis ids that fired for the chosen option
    correct_fired: list[str]     # ... for the correct option
    tactical_delta: float        # tactical(correct) - tactical(chosen)


def featurize(correction, pilot) -> Featurization:
    """Replay ``pilot`` on ``correction.obs`` and diff the fired Hypotheses (chosen vs correct)."""
    if correction.obs is None:
        raise ValueError("correction has no embedded obs; backfill it from the replay (ADR-0017)")
    traces = pilot.explain(correction.obs).options
    chosen = traces[correction.chosen[0]]
    correct = traces[correction.correct[0]]
    chosen_fired = [h.id for h, _ in chosen.fired]
    correct_fired = [h.id for h, _ in correct.fired]
    tactical_delta = correct.tactical - chosen.tactical
    return Featurization(
        attribution=derive_attribution(chosen_fired, correct_fired, tactical_delta),
        chosen_fired=chosen_fired,
        correct_fired=correct_fired,
        tactical_delta=tactical_delta,
    )
