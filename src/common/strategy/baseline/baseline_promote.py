"""BASELINE cluster: PROMOTE — which benched Pokémon to bring up after a Knock Out, at a TO_ACTIVE
select (ADR-0025).

**EMPTY since ADR-0100 (#141).** All seven promote rungs are DELETED: the promote/retreat DECIDER
(`common/promote_retreat_value.py`) prices the whole family as the Sub-lethal Residual, in the damage
currency, so what these rungs asserted is now either MEASURED or EMERGENT. Per-rung fold map:
`tools/rung_registry.py` (`FOLDED`, ADR-0100 group); the reasoning is the ADR's.

Kept as a module (rather than deleted outright) because the cluster loader and the Hypothesis-id
registry both expect it, and an empty list is the honest statement that the cluster has no rungs
left. Pure data, no Mixin.
"""

HYPOTHESES = []
