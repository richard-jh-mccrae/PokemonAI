"""Evolve-value oracle (SHADOW) — docs/plans/evolve-valuation-grill-spec.md.

The evolve decision as ONE equation: the marginal change in board need-coverage an evolve produces,
priced in the one currency (Needs). Emitted REPORTING-ONLY per the shadow-equations ruling — it does
NOT drive decisions yet; the `baseline_evolution.py` rungs (+ the dragapult `hold-evolution` deck rung)
still decide. The corpus family (`tests/strategy/test_evolve_valuation_corpus.py`) is the swap gate.

Built increment by increment (grill rulings 2026-07-15):
  * income Δ  — cover(R's draw/dig ability) − cover(B's), sign = turn-on (+) vs turn-off (−)   [THIS]
  * readiness — typed `fund_attack` the result buys (AttackStat.energyTypes, turns_to_ready)     [TODO]
  * line/deploy — deploy_now + line_slots, readiness-conditioned                                 [TODO]
  * exposure  — fragility × slot-threat, from line-shape                                         [TODO]
  * scoped doom — opponent turns_to_ready carve-out                                              [TODO]
"""
from __future__ import annotations

from dataclasses import dataclass

from common import needs


@dataclass
class EvolveValue:
    """The shadow evolve value with its inner terms (the gamble-trace legibility pattern). ``total``
    is the running sum of the terms built so far — REPORTING-ONLY until the swap."""
    income: float = 0.0          # Δ draw/dig ability income: cover(result) − cover(body)
    total: float = 0.0


def _ability_income(functions, cid, engines_online: int) -> float:
    """cover(a body's draw/dig ability) in the one currency: the `draw_engine` slot value when the card
    carries a `draw`/`dig` Function Tag (Drakloak Recon, Dudunsparce Run Away Draw), else 0. The
    persistent-vs-one-shot MAGNITUDE split (stream × turns_to_ready vs deadline-0 burst) is a later
    increment; this is the sign-correct base."""
    if cid is None or functions is None:
        return 0.0
    tags = functions.tags(cid)
    if "draw" in tags or "dig" in tags:
        return float(needs.draw_engine_slot(engines_online=engines_online).value)
    return 0.0


def evolve_value(functions, *, result_cid, body_cid, engines_online: int = 0) -> EvolveValue:
    """The SHADOW value of an EVOLVE option, body ``body_cid`` → result ``result_cid``.

    Increment 1 — the ability-income Δ: turning a draw/dig engine ON (result has one, body did not → +)
    or OFF (body had one, result does not → −). ``engines_online`` feeds the slot's saturation."""
    income = (_ability_income(functions, result_cid, engines_online)
              - _ability_income(functions, body_cid, engines_online))
    return EvolveValue(income=income, total=income)
