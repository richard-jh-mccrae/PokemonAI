"""Two turn-level reads the Pilot takes before it scores anything: which Plan we are on, and how much to trust the Read.

Split out of `pilot.py` so the fact assemblers can call them without importing the Pilot back."""
from __future__ import annotations


from common.strategy import Plan


# Posture confidence (ADR-0026): continuous γ ∈ [0,1] the generic-core levers scale by. Ramp the
# Read's top posterior over [LO, HI], discount by unmatched mass -> unknown opponent → γ≈0.
_POSTURE_GAMMA_LO = 0.5     # below this top-posterior, Posture off (recognition too weak to act on)

_POSTURE_GAMMA_HI = 0.85    # at/above this, Posture at full strength

def _posture_gamma(read) -> float:
    """Posture confidence γ ∈ [0,1] from the Read (ADR-0026): ramp the top posterior over
    [_POSTURE_GAMMA_LO, _POSTURE_GAMMA_HI], discounted by the unmatched (unknown) mass. 0 when there is no
    Read or it is unrecognized — so an unknown opponent makes Posture contribute nothing (no-regression)."""
    if read is None or not read.candidates:
        return 0.0
    top = read.confidence[0] if read.confidence else 0.0
    ramp = max(0.0, min(1.0, (top - _POSTURE_GAMMA_LO) / (_POSTURE_GAMMA_HI - _POSTURE_GAMMA_LO)))
    return ramp * (1.0 - read.unknown_mass)

def choose_plan(state: dict, strategy, stats=None) -> Plan:
    """Pick this turn's Plan. SETUP until a win-condition Line's payoff is in play with enough
    energy to attack; then RACE. A Line's `ready.energy` is the threshold; when unset (None) it is
    derived from the engine — the payoff's cheapest attack cost, so a 1-Energy attack counts.
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
    """The payoff's cheapest attack's energy cost, read off the engine CardStat (`default` when
    unknown — never 0, so a Pokémon is never 'online' with no Energy)."""
    stat = stats.get(payoff) if stats else None
    cost = getattr(stat, "minAttackCost", None) if stat else None
    return cost if cost is not None else default
