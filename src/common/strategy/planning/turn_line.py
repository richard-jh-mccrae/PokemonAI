"""The `TurnLine` a planner family returns, its goal vocabulary, and the two module helpers that shape one.

Split out of `planner.py` so a family can build a line without importing the planner back."""
from __future__ import annotations


from dataclasses import dataclass


def _prune_none(v):
    """Convert an ``asdict``-ed engine Observation into the dict shape the LIVE obs has. Drops
    None-VALUED dict keys; KEEPS None list ELEMENTS — a facedown slot carries the zone's count."""
    if isinstance(v, dict):
        return {k: _prune_none(x) for k, x in v.items() if x is not None}
    if isinstance(v, list):
        return [_prune_none(x) for x in v]
    return v

_PRIZE_AREA = 6                # AreaType.PRIZE — a hidden-zone pick: the sim's ids are predictions,
                               # so a recorded prize pick is policy-driven at replay (ADR-0037 stage 3)

def _rng_probe(cgapi, my_index: int, *, prize: bool):
    """Build ``saw(observation) -> bool``: did these logs consume engine RANDOMNESS on MY behalf?
    Counts DRAW, deck→LOOKING/DISCARD, any COIN, and (only if ``prize``) a PRIZE move (Issue #178)."""
    _logs = getattr(cgapi, "LogType", None)
    coin_t = getattr(_logs, "COIN", None)
    draw_t = getattr(_logs, "DRAW", None)
    move_t = getattr(_logs, "MOVE_CARD", None)
    _a = getattr(cgapi, "AreaType", None)
    deck_a, prize_a = getattr(_a, "DECK", None), getattr(_a, "PRIZE", None)
    positional = {(int(deck_a), int(x))
                  for x in (getattr(_a, "LOOKING", None), getattr(_a, "DISCARD", None))
                  if deck_a is not None and x is not None}

    def saw(ob) -> bool:
        for lg in (getattr(ob, "logs", None) or ()):
            t = getattr(lg, "type", None)
            if coin_t is not None and t == coin_t:
                return True
            if getattr(lg, "playerIndex", None) != my_index:
                continue
            if draw_t is not None and t == draw_t:
                return True
            if move_t is None or t != move_t:
                continue
            fr, to = getattr(lg, "fromArea", None), getattr(lg, "toArea", None)
            if fr is None:
                continue
            if prize and prize_a is not None and int(fr) == int(prize_a):
                return True
            if to is not None and (int(fr), int(to)) in positional:
                return True
        return False

    return saw

# The fetch CLOSURE's predicates live in the card REPRESENTATION — `card_effects.json` FETCH clauses
# (ADR-0032) — so it NEVER parses card text. A `tutor_energy` tag cannot carry a {F}-lock; a clause can.
_GOAL_LINE = {"ko_on_path": {"ko_for_prizes", "ko_key_threat"},   # the directed goal → the candidate line
              "trade": {"ko_for_prizes"}}                # goals that serve it. `survive` is DROPPED, not
              # left mapping to the empty set, so `_gameplan_goal_bonus` cannot silently pay 0.

@dataclass
class TurnLine:
    """A committed sequence of this-turn actions achieving a **Turn Goal**. ``goal == "win"`` is the
    Lethal Solver's lock; ``verified`` is never False there — a refuted candidate is dropped."""
    next_step: list
    goal: str = ""
    value: float = 0.0
    rationale: str = ""
    ranked_by: str | None = None
    diverged: bool = False
    kind: str = ""
    verified: bool | None = None

_WEIGHTED_GOALS = ("ko_for_prizes", "ko_key_threat")   # the rungs whose prize term #175 weights

def _composed_rank(cand):
    """Order composed KO candidates by EXPECTED prizes (ADR-0074 decision 4) — raw prize count cannot
    express "2 prizes, 40% to whiff". Survival stays the tiebreak below it."""
    prizes, survives, p = cand
    return (prizes * p, survives)
