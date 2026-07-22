"""Evolve-value oracle — docs/plans/evolve-valuation-grill-spec.md.

The evolve decision as ONE equation, replacing the `baseline_evolution.py` rung pile (+ the dragapult
`hold-evolution` deck rung): the marginal change in board need-coverage an evolve produces, priced in
the one currency (Needs). No per-case rungs — the whole "when and how to evolve" mechanic is this
function reading the board.

    evolve_value(body B → result R) =
        deploy_gain(R)        the worth of having R on board, readiness-conditioned (the line/deploy Δ)
      + income_gain(R)        R's own draw/dig ability turned ON
      − income_loss(B)        B's draw/dig ability the evolve FORFEITS (the hold pressure)
      − exposure_cost(R)      R fragile in a threatened slot
      (+ doom override)       secure the body when the opponent can ACTUALLY KO it this turn (scoped)

The unification (why no readiness GATE is needed): megas (Staryu/Riolu — no pre-evo ability) have
income_loss 0, so an evolve is always net-positive → they evolve on sight; dragapult's Drakloak carries
a PERSISTENT Recon stream, so evolving into an unready Dragapult only fires once deploy_gain exceeds
that stream — "delay until strictly necessary" DERIVED, not asserted. Calibrated at the old rung
currency (ROLE_TIER + the +40/+15/+5 seeds) so the fold holds the suite.

Emitted REPORTING-ONLY on `OptionTrace.evolve_shadow` until the swap gate
(`tests/strategy/test_evolve_valuation_corpus.py`) is green.
"""
from __future__ import annotations

from dataclasses import dataclass

from common import needs

# Calibration constants — the old rung currency (baseline_evolution.py seeds + ROLE_TIER).
_DEPLOY_WINCON_READY = 40.0     # evolve into the payoff that can ATTACK now (was `evolve-into-wincon`)
_DEPLOY_WINCON_UNREADY = 10.0   # the payoff on board but not yet attacking — insurance/body only
_DEPLOY_LINE = 15.0             # advance a MID-line pre-evo (was `advance-the-evolution-line`)
_ENERGIZED_BONUS = 5.0          # which-body: the body already carrying Energy (was the two `+5` rungs)
_ENGINE = float(needs.ROLE_TIER["engine"])   # a draw/dig ability's per-turn worth (12)


@dataclass
class EvolveInputs:
    """The board facts an evolve option's value reads — filled by the Pilot, so the equation stays a
    pure function of the situation."""
    result_has_draw: bool = False       # R carries a draw/dig ability (turned ON by evolving)
    result_ability_oneshot: bool = False  # R's ability self-shuffles (a one-shot burst, not a stream)
    body_has_draw: bool = False         # B carries a draw/dig ability (FORFEITED by evolving)
    body_ability_oneshot: bool = False
    result_is_wincon: bool = False      # R carries a win_condition / primary_attacker Role
    result_is_line_preevo: bool = False  # R is a MID-line pre-evolution (advances the line, not payoff)
    result_can_attack_now: bool = False  # R can TYPED-pay a valued attack on the body's current Energy
    body_has_energy: bool = False       # the evolving body already carries Energy (which-body tie-break)
    hold_turns: int = 1                 # turns the body would keep a PERSISTENT engine before it's
                                        # usable as the payoff (turns_to_ready, typed) — the stream length
    engines_online: int = 0             # draw engines already online (slot saturation)
    body_doomed_affordable: bool = False  # the opponent can ACTUALLY KO this body next turn (SCOPED —
                                        # their real turns_to_ready, not the affordability-blind oracle)


@dataclass
class EvolveValue:
    """The evolve value with its inner terms (gamble-trace legibility). ``total`` is the sum."""
    deploy: float = 0.0
    income_gain: float = 0.0
    income_loss: float = 0.0
    doom: float = 0.0
    total: float = 0.0


def _ability_income(has_draw: bool, oneshot: bool, engines_online: int, hold_turns: int) -> float:
    """cover(a draw/dig ability) in the one currency. A ONE-SHOT (self-shuffle: Run Away Draw) is a
    single deadline-0 burst worth one engine-tier; a PERSISTENT engine (Recon) is a STREAM worth the
    tier over the turns it stays online (`hold_turns`). Saturates with an engine already up."""
    if not has_draw:
        return 0.0
    base = float(needs.draw_engine_slot(engines_online=engines_online).value)
    return base if oneshot else base * max(1, int(hold_turns))


def evolve_value(inp: EvolveInputs) -> EvolveValue:
    """The value of an EVOLVE option in the one currency (see module docstring)."""
    # deploy_gain — the worth of having R on board.
    if inp.result_is_wincon:
        deploy = _DEPLOY_WINCON_READY if inp.result_can_attack_now else _DEPLOY_WINCON_UNREADY
    elif inp.result_is_line_preevo:
        deploy = _DEPLOY_LINE
    else:
        deploy = 0.0                                    # a utility body: its worth IS its income
    if inp.body_has_energy and (inp.result_is_wincon or inp.result_is_line_preevo):
        deploy += _ENERGIZED_BONUS                      # which-body: advance the energized one

    income_gain = _ability_income(inp.result_has_draw, inp.result_ability_oneshot,
                                  inp.engines_online, inp.hold_turns)
    income_loss = _ability_income(inp.body_has_draw, inp.body_ability_oneshot,
                                  inp.engines_online, inp.hold_turns)

    # doom override: if the opponent can ACTUALLY KO this body next turn, securing the (usually sturdier)
    # evolved body is worth the payoff-ready deploy even when it can't yet attack — the ability stream is
    # moot if the body dies. Scoped to a REAL threat (not the affordability-blind doom oracle).
    doom = (_DEPLOY_WINCON_READY - deploy) if (inp.body_doomed_affordable and inp.result_is_wincon) else 0.0

    total = deploy + income_gain - income_loss + doom
    return EvolveValue(deploy=deploy, income_gain=income_gain, income_loss=income_loss,
                       doom=doom, total=total)
