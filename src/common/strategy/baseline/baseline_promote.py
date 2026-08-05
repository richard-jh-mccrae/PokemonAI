"""BASELINE cluster: PROMOTE — which benched Pokémon to bring up after a Knock Out, at a TO_ACTIVE
select (ADR-0025).

**Emptied by ADR-0100 (#141); ONE rung since ADR-0121 (#406), and it arrived rather than survived.**
All seven ORIGINAL promote rungs are still deleted: the promote/retreat DECIDER
(`common/promote_retreat_value.py`) prices the whole family as the Sub-lethal Residual, in the damage
currency, so what those rungs asserted is now either MEASURED or EMERGENT:

* `promote-the-ko-attacker` (+45) and `promote-the-accelerator-for-the-ko` (+50) → `_promote_ko_tactical`,
  the pick site's own Knock-Out layer, which reuses the SAME `best_affordable_ko_value` oracle the
  retreat comparison uses — so the pick necessarily lands on the body that justified the retreat
  (ADR-0100 §11).
* `promote-the-ready-wincon` (+40) → EMERGENT from `my_yield`, which is the body's real reachable
  damage rather than a readiness band. f104's "the 3-Energy copy over the bare one" fix falls out of
  the damage read instead of needing a `+5` best-target bonus.
* `dont-promote-onto-their-path` (−8) → DELETED as subsumed (§7c), on a card-mechanics argument: the
  promoted body becomes the ACTIVE, and they attack the Active BECAUSE it is the Active. Path
  membership does not change whether it is hit.
* `interpose-the-cheap-attacker-to-preserve-the-wincon` (+50) and `dont-promote-into-their-prize-reach`
  (−20) → EMERGENT from prize Exposure (1 prize costs 100 damage, a Mega ex 300) plus the fatal step.
* `promote-the-staller` (+20) → §6a: a disposable staller decomposes with no remainder into terms the
  equation already builds — its own damage, its LOW exposure ("disposable" IS the exposure term), and
  the preservation credit for the body it replaces.

`prefer-wincon-line-piece` is NOT one of those seven and never lived here. It was authored in
`doctrine_fetch` as a two-context rung — a `_TO_HAND` grab credit `or` a `_TO_ACTIVE` promote credit
— and ADR-0121 retired the whole `_TO_HAND` rung ladder in favour of the grab equation. Splitting it
left the promote leg with no fetch content at all, so it comes to the cluster that owns its context
rather than sitting on as a fetch rung that never fires at a fetch. Pure data, no Mixin.
"""
from common.strategy.context import _TO_ACTIVE
from common.strategy.strategy import Hypothesis

HYPOTHESES = [
    Hypothesis(
        id="prefer-wincon-line-piece",
        rationale="At a PROMOTE, bring up a win-condition Line pre-evolution — but ONLY when the "
                  "payoff is in hand to evolve it THIS turn (`evolve_to_ready_wincon_available`); "
                  "else a bare pre-evolution just exposes a fragile base (see the retired "
                  "`promote-the-staller`, and dragapult f31, where a Stage-0 Dreepy TWO hops from a "
                  "ready attacker was promoted over the right disposable staller). Narrow by "
                  "design: `card_is_line_preevo` is the WIN-CONDITION line only, never ADR-0048's "
                  "broadened recognized-attacker set — that widening was authored for the FETCH "
                  "seam's prize-economy question, which does not arise when a body is already on "
                  "my Bench and the only question is which one takes the hit.\n"
                  "\n"
                  "WHY IT IS NOT SUBSUMED by the promote/retreat decider that dissolved the other "
                  "seven (ADR-0100). That equation's `my_yield` is the body's real reachable damage "
                  "THIS TURN, and a pre-evolution's whole point here is what it becomes NEXT turn "
                  "once the payoff in hand lands on it. The forward hop is exactly the term the "
                  "damage read does not carry, which is why this leg outlived the cluster's "
                  "clear-out. It is the honest residue of a dissolution, recorded rather than "
                  "quietly re-derived — the ADR-0100 §6a treatment applied to the one rung that "
                  "did not decompose without remainder.",
        when=lambda c: (c.card_is_line_preevo and c.select_context == _TO_ACTIVE
                        and c.board.evolve_to_ready_wincon_available),
        weight=18, status="testing"),
]
