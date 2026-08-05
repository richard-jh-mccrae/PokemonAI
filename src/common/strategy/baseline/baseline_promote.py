"""BASELINE cluster: PROMOTE — which benched Pokémon to bring up after a Knock Out, at a TO_ACTIVE
select (ADR-0025).

**EMPTY since ADR-0100 (#141).** All seven promote rungs are DELETED: the promote/retreat DECIDER
(`common/promote_retreat_value.py`) prices the whole family as the Sub-lethal Residual, in the damage
currency, so what these rungs asserted is now either MEASURED or EMERGENT:

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

Kept as a module (rather than deleted outright) because the cluster loader and the Hypothesis-id
registry both expect it, and an empty list is the honest statement that the cluster has no rungs
left. Pure data, no Mixin.
"""

HYPOTHESES = []
