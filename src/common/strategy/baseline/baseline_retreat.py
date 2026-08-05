"""BASELINE cluster: RETREAT — the open-menu Retreat decision (ADR-0025).

**One rung survives ADR-0100 (#141).** The promote/retreat DECIDER
(`common/promote_retreat_value.py`) now answers the whether-to-retreat question as the Sub-lethal
Residual, so four of the five rungs are DELETED:

* `retreat-to-ready-attacker` (+60) and `swap-out-the-locked-attacker` (+35) → EMERGENT from
  destination value minus retreat cost: a ready benched attacker simply scores more `my_yield` than
  the Active's own option, and a transient-locked attack scores LESS on its own option, so the swap
  wins without a rung asserting it.
* `dont-play-switch-for-no-gain` (−8) → EMERGENT: a switch that gains nothing has a destination value
  no better than staying, and now pays the card's Worth as `retreat_cost`, so it nets below End
  without a penalty rung. Switch-class Items are priced by the same equation as a manual retreat
  (ADR-0100 §11's rider).
* `hold-position-in-setup` (−25) → DELETED on an emergence argument: a setup retreat pays real
  `retreat_cost` for a destination that is not yet worth promoting, so the equation should decline it
  on its own. **This is flagged in ADR-0100 as the WEAKEST claim in the ruling — the one deletion with
  no worked frame behind it — and is the most likely to return as a ruled flip at the Decision Gate.**
  Treat a regression here as expected rather than surprising.

`retreat-to-wall-the-line` SURVIVES because it is not a value claim at all: it is step 1 of a
dependent **Maneuver** (retreat → promote the wall → item-lock → develop behind cover), and a
per-option value equation structurally cannot price a chain whose payoff lands on later steps. Owner
**#165** (the Turn Planner), per ADR-0070 amendment J's layer-ownership test.

Pure data, no Mixin.
"""
from common.strategy.context import _MAIN, _RETREAT
from common.strategy.strategy import Hypothesis

HYPOTHESES = [
    Hypothesis(
        id="retreat-to-wall-the-line",
        rationale="The retreat-to-promote-the-sacrificial-wall maneuver (dragapult f32/f20): when my Active "
                  "is a fragile developing win-condition LINE pre-evo, a benched `item_lock` disruptor "
                  "(Budew) can be promoted as a sacrificial wall, and the opponent's Active can damage the "
                  "line NOW (`can_wall_line_with_disruptor`), RETREAT it — pull the fragile line to the "
                  "Bench to safety, promote the item-lock wall, and evolve + energize the line behind cover "
                  "while the opponent is item-locked. Step 1 of a multi-step turn: `_finish_turn_last` rides "
                  "this retreat TIER-0 (ahead of a free evolve / Item strip) so it happens FIRST, and the "
                  "promote + item-lock + develop follow on later frames. Silent for decks without a benched "
                  "item-lock opener. Budew is sacrificial by design — the opponent KOs it next turn, having "
                  "bought a locked tempo turn while the win-condition line assembles safely. Also fires for "
                  "the OFFENSIVE variant (`can_lock_line_with_disruptor`, dragapult f20): early-game, retreat "
                  "a nothing-better-to-do line-preevo into the item-lock to deny the opponent's Item turn "
                  "even with no incoming damage. SURVIVES the ADR-0100 rung deletion precisely because it is "
                  "a MANEUVER and not a value claim: the payoff lands on the LATER steps, which a per-option "
                  "equation cannot see. Owner #165.",
        when=lambda c: c.select_context == _MAIN and c.option_type == _RETREAT
        and (c.board.can_wall_line_with_disruptor or c.board.can_lock_line_with_disruptor),
        weight=30, status="assumed"),
]
