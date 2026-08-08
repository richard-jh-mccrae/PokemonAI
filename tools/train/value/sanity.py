"""Post-train sanity gate for the Automatic Value Model (grilled 2026-07-05, Tier-5 finish plan).

The seed model was trained on a MIRROR-only corpus, so ``favorability`` never varied and its fitted
weight sat at ~0 — the model literally could not use its matchup signal. Before the cross-deck A/B is
worth running, the retrained model must show favorability came ALIVE. If it stays dead even on the
cross-deck corpus, the favorability FEATURE (Tier-4: opp_tempo / Brief coverage) is the bottleneck,
not the model — park T5 pointing there, don't flip a model that can't move a matchup.
"""
from __future__ import annotations

# The dead-vs-live boundary, NOT a strength bar: at corpus scale a standardized logistic weight has
# SE ~= 0.003, so this is ~6 SE off zero while still admitting a WEAK-but-real feature.
_DEFAULT_EPS = 0.02


def favorability_is_live(model: dict, *, eps: float = _DEFAULT_EPS) -> bool:
    """The tell that the Read is wired AND the corpus varies the matchup. A weight within ``eps`` of
    zero is the DEAD pipeline signature: a mirror-only corpus, or a Read-less extractor."""
    feats = model.get("features") or []
    weights = model.get("weights") or []
    if "favorability" not in feats:
        return False
    i = feats.index("favorability")
    if i >= len(weights):
        return False
    return abs(weights[i]) >= eps
