"""Two turn-level reads taken before anything is scored: which Plan we are on, and how far to trust the Read.

Separate from `pilot.py` so the fact assemblers can call them without importing the Pilot back."""
from __future__ import annotations


from common.strategy import Plan


# Posture confidence (ADR-0026): γ ∈ [0,1] the generic-core levers scale by.
_POSTURE_GAMMA_LO = 0.5     # below this top-posterior, Posture off (recognition too weak to act on)

_POSTURE_GAMMA_HI = 0.85    # at/above this, Posture at full strength

def _posture_gamma(read) -> float:
    """Posture confidence γ ∈ [0,1] (ADR-0026). An unknown/unrecognized opponent gives 0, so Posture
    contributes nothing rather than guessing."""
    if read is None or not read.candidates:
        return 0.0
    top = read.confidence[0] if read.confidence else 0.0
    ramp = max(0.0, min(1.0, (top - _POSTURE_GAMMA_LO) / (_POSTURE_GAMMA_HI - _POSTURE_GAMMA_LO)))
    return ramp * (1.0 - read.unknown_mass)

def choose_plan(state: dict, strategy, stats=None) -> Plan:
    """SETUP until a win-condition Line's payoff is in play with enough Energy to attack; then RACE.
    (STABILIZE / CLOSE arrive with their own signals.)"""
    me = state["players"][state["yourIndex"]]
    board = [p for p in (me.get("active") or []) + (me.get("bench") or []) if p]
    for line in strategy.lines:
        threshold = line.ready.energy
        if threshold is None:                          # derive "online" from cheapest attack
            threshold = _min_attack_cost(stats, line.payoff)
        if any(p["id"] == line.payoff and len(p.get("energies", [])) >= threshold for p in board):
            return Plan.RACE
    return Plan.SETUP

def _min_attack_cost(stats, payoff: int, default: int = 1) -> int:
    """The payoff's cheapest attack cost. `default` when unknown — never 0, so nothing is 'online' bare."""
    stat = stats.get(payoff) if stats else None
    cost = getattr(stat, "minAttackCost", None) if stat else None
    return cost if cost is not None else default
