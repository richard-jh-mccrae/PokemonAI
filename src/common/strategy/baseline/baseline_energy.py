"""BASELINE cluster: ENERGY — what is LEFT of the Energy rungs after the attach decider (ADR-0069).

The energy-attach decision is no longer a pile of tuned Hypotheses. Nineteen of the 23 rungs that
used to live here were DELETED in the Phase-1a swap (#139): their logic is now stated arithmetic in
`Pilot._attach_value` — the axes-sum marginal (attack axis + Retreat Equity + Ability Fuel −
evaporation loss) that DECIDES every energy attach and every accel-recipient pick. They were not
suppressed behind a flag; a weight coincidence that no longer exists cannot re-enter tuning.

What each deleted family became — the fold map, kept here because this file is where a reader looks
for a rung that is gone:

  * concentrate / build-active / power-up / spread / concentrate-accel / feed-the-accelerator /
    arm-the-doomed / advance-the-accel-pieces  ->  the ATTACK AXIS
    (`max(this_turn, build, accel_value)`): tonight's counterfactual under the full Attach Budget,
    typed convex build toward the line payoff, and the forward build an accelerator's routed Energy
    buys. Concentrate falls out of convexity; arm-the-doomed out of the survival gate crediting ANY
    attack tonight, not only the biggest.
  * dont-waste-discard-energy / dont-attach-discard-energy-turn1 / conserve-burst-when-no-ko /
    conserve-discard-energy-prefer-basic / prefer-reusable-over-burst  ->  the BURST discipline:
    honest printed provision, the evaporation loss (an uncashed one-shot scores MINUS its worth, so
    End beats torching an Ignition on turn 1), the no-KO cap against the best reusable Basic in hand,
    and the resource tie-break.
  * dont-fund-the-non-attacking-body / dont-power-the-draw-engine  ->  the BOARD-EVALUATED role
    gate, which zeroes the ATTACK AXIS only (a role-gated body still banks mobility and fuel) and
    only while a real attacker alternative is in play.
  * dont-feed-the-doomed / dont-overbuild-the-doomed-wincon  ->  the SURVIVAL gate and its
    evolution-escape (a doomed wincon-Line pre-evolution keeps build credit: Energy carries through
    evolution, and a Mega evolving does not end the turn).
  * dont-waste-off-type-energy  ->  EMERGENT. Build is a typed slot-fraction by the same matcher
    reachability uses, so an Energy that fills no slot scores zero build — and a colourless slot
    absorbs any type, which the old colourless-blind boolean could not see.
  * fuel-the-dormant-ability  ->  the ABILITY FUEL channel, additive rather than a tie-break.
  * attach-energy-last  ->  a decide()-only ORDERING deferral. Sequencing is structural in
    `Pilot._finish_turn_last`'s tiers (free development 0 -> Supporter 1 -> ATTACH 2 -> hand-shuffle
    3 -> turn-enders 4), so attach-late no longer costs an attach any SCORE — which is what let the
    desperation floor stop depending on out-scoring a −5.

What survives is STRUCTURE, not value — positional facts the marginal has no way to express. Each
is held to an EXECUTABLE band constraint asserted in `tests/strategy/test_attach_bands.py`: a
positional prior may break a tie, never override one real build step.

NO Pilot Mixin — the valuation half of energy lives in the Pilot per ADR-0016.
"""
from common.strategy.context import _ACTIVE, _ATTACH, _ATTACH_FROM, _ATTACKER_ROLES, _PLAY
from common.strategy.strategy import Hypothesis

HYPOTHESES = [
    Hypothesis(
        id="use-acceleration",
        rationale="Energy acceleration multiplies the one manual attachment per turn — tempo-positive "
                  "for any deck, so prioritize playing it. SURVIVES the attach-decider swap untouched "
                  "(ADR-0069 §7): this is a PLAY-side source-selection rung, not an attach valuation — "
                  "it says 'play the accelerator', while the decider says where the Energy goes. "
                  "Currency-clean: it never scores an ATTACH option, so it cannot double-count with "
                  "the marginal.",
        when=lambda c: c.option_type == _PLAY and "energy_accel" in c.tags,
        weight=25, status="assumed"),
    Hypothesis(
        id="prefer-active-attach-in-setup",
        rationale="Prefer the ACTIVE attacker over a benched pre-evolution for the turn's manual Energy "
                  "when the marginal is otherwise a DEAD HEAT — the Active can use it THIS turn, fixing "
                  "the tie that left Active Cinderace bare while Energy went to Staryu (ep83007714 f7). "
                  "STANDS DOWN when the Active isn't the deck's attacker — no attacker Role (declared or "
                  "derived accel), off every Line — while a benched Line member sits un-powered "
                  "(`bench_line_member_needs`): a role-less tech Active (Munkidori, 86091728 f19) is "
                  "Active incidentally, so the tie goes back to dead-heat and the decide()-only "
                  "`attach_to_needy_line` tie-break develops the benched line instead.\n"
                  "BAND-CONSTRAINED (ADR-0069 §7): the weight must sit BELOW one scaled convex build "
                  "step, so this positional prior can order equals but can never make a zero-build "
                  "Active out-score a body that gains real progress. It was +8 while the deleted "
                  "positives gave every attach a flat +15 floor; against a continuous marginal that "
                  "same +8 was worth a whole 8-damage build step, which is precisely the weight-"
                  "coincidence logic this swap exists to remove. Re-derived to +1 and test-asserted "
                  "against the thinnest shipped build step.",
        when=lambda c: c.option_type == _ATTACH and c.attach_is_energy
        and c.attach_target_area == _ACTIVE and c.attach_target_needs
        and not c.board.active_doomed
        and not (c.board.bench_line_member_needs                 # an un-powered line waits benched …
                 and not c.attach_target_is_line_member          # … and the Active is off-Line …
                 and not (_ATTACKER_ROLES & set(c.attach_target_roles))),  # … and not a deck attacker
        weight=1, status="testing"),
    Hypothesis(
        id="feed-the-line-for-disruptor-lock",
        rationale="Step 1 of the OFFENSIVE item-lock maneuver (dragapult f20): attach the turn's Energy "
                  "to the fragile line-preevo ACTIVE so it can retreat into a benched item_lock opener "
                  "(Budew) and Itchy-Pollen the opponent's Item turn (`can_lock_line_with_disruptor`). "
                  "The energy is DELIBERATELY spent to pay the enabling retreat, so its worth is the "
                  "LOCK, not the build — a fact no attach marginal can see, which is why this survives "
                  "the swap as structure. Silent for decks with no benched item-lock opener; "
                  "kill-switched via the signal (`disruptor_lock_maneuver`).\n"
                  "BAND-CONSTRAINED (ADR-0069 §7): it must beat a bench recipient's scaled build step "
                  "BY DESIGN, and nothing more — so the weight is re-derived as (one scaled max "
                  "pre-evolution build step, exclusive) .. (twice that, inclusive) and test-asserted. "
                  "Its old +20 was sized to clear a −30 doom rung that no longer exists; against the "
                  "continuous marginal the biggest step a bench Line pre-evolution can offer across "
                  "the shipped decks is Riolu's second {F} toward Mega Brave (3/4 x 270 x 0.25 = "
                  "50.6), so +20 could no longer buy the maneuver at all. The band is computed from "
                  "the SHIPPED decks, not from the one deck that runs the maneuver, because the rung "
                  "is deck-agnostic.",
        when=lambda c: c.board.can_lock_line_with_disruptor and (
            (c.select_context == _ATTACH_FROM and c.option_area == _ACTIVE)
            or (c.option_type == _ATTACH and c.attach_target_area == _ACTIVE)),
        weight=55, status="testing"),
]
