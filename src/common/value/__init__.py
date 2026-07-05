"""Tier 5 — the Base Value Model (ADR-0007/0042): the single learned seam.

A dependency-free, replay-trained ``state -> P(win)`` estimator whose FEATURES are the Tier-3/Tier-4
objective primitives (race delta, both Prize-Path turns, favorability, development, prize/hand/energy
counts) — the symbolic tiers do the credit assignment a raw-board model would learn from scratch, so
the learned layer is a thin, legible logistic over named features. It **refines judgment only**
(planner leaf blend, capped below a prize; a Score tiebreaker), NEVER overrides a sound rung, and is
**absent-safe**: with no ``model.json`` the loader is a null model (P=0.5, zero influence), so the
closed-form heuristic stays the fallback. Inference is a dot product — trivially within the per-move
budget (the same constraint that rejected card2vec).
"""
from common.value.features import FEATURE_NAMES, features_from_board
from common.value.model import ValueModel

__all__ = ["FEATURE_NAMES", "features_from_board", "ValueModel"]
