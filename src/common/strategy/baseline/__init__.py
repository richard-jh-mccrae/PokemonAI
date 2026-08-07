"""Deck-agnostic **baseline** rules, clustered by the **decision-context** they fire on (ADR-0025).
Each `baseline_*` module is pure-data General-Strategy Hypotheses — NO Pilot Mixin (the contrast with
a `doctrines/` doctrine, which owns closed-form code). A findability split only: the Pilot scores
everything as one flat sum, so cluster boundaries and order are runtime-irrelevant.

Mirrors the `doctrines/__init__` idiom — re-export each cluster's `HYPOTHESES` under an aliased name —
and, because there are many clusters (vs. 4 doctrines), additionally owns the combined
`BASELINE_HYPOTHESES` roster so `general_strategy` stays a clean baseline + doctrines assembly.
(The Tool cluster was promoted to the Tool DOCTRINE — `doctrines/doctrine_tool.py`, ADR-0028.)

**Four more clusters are GONE, not empty** (POC-T4/5, Issue #386): HEAL, RETREAT, SEQUENCING and
DISRUPTION. Every rung in them was a MAIN-phase positional claim, and the sequence composer
(`common.composer`) now prices that whole family by differencing end states — a heal by the survival
delta it buys, a free dig by the board the extra cards reach, a hand-disruption play by what it does
to both hands, and `retreat-to-wall-the-line` by scoring the maneuver's later steps in the same
sequence rather than paying a flat +30 for its first. A rung asserting a preference the leaf can
compute is a second opinion about the same board (ADR-0092 decision 4). The modules were deleted
rather than emptied, for the reason the BENCH note below already gives.

The rungs by name, because a deleted module takes its own fold map with it and
`tools/train/reviewed_audit.py` reads these blocks to answer *"where did this rung go?"* for the 17
closures in `data/corrections/reviewed_audit_allowlist.json` that name one:

* `dig-before-commit` (+20) and `use-the-draw-engine-ability` -> DELETED into the composer's
  sequence search. Both said *"take the informative, reversible action before the committing one"*,
  which is what a beam over within-turn sequences does by construction — the dig's successor states
  are the ones it scores. `_finish_turn_last`'s tiers survive **for these two**; only the flat
  endorsements are gone.

  ⚠️ **That sentence used to read "the tiers SURVIVE" without qualification, and for two of them it
  was FALSE ON THE DAY IT WAS WRITTEN.** A tier that triggers off a rung ID dies with the rung, and
  two did: the KO-enabling-gust tier and the wall-retreat tier matched
  `gust-for-the-ko` / `gust-for-the-loaded-equal-ko` / `retreat-to-wall-the-line` as inline string
  literals in `pilot._finish_turn_last`, so from this fold onward both branches were unreachable.
  Nothing went red — a retired id in a live string literal reads as live to every instrument, which
  is why the false claim survived a full CI run and a review. Both branches are now deleted with the
  loss recorded at the site, and `tests/strategy/test_rung_id_literals_are_live.py` is the interlock
  that fails the next one.
* `gust-for-the-loaded-equal-ko` -> DELETED with `gust-for-the-ko` below, and named here because it
  was omitted from this map entirely: it is the sibling gate for the loaded-attacker EQUAL-prize
  case, and a rung absent from the map is a rung `reviewed_audit.py` cannot answer for.
* `dont-waste-clutch-heal` -> DELETED; a heal is priced by the survival delta it buys.
* `deploy-hp-tool` and `hold-the-retreat-tool-with-no-retreat` -> DELETED with the Tool doctrine's
  MAIN-phase half.
* `gust-for-the-ko` -> DELETED; the gust's value is the board it produces. **Note the seam does not
  yet reach it** — `CLAUSE_WRITES['gust']` is non-empty, so `_covers` refuses the transition
  (Issue #300), and `poc_t4_flips.py` records the two corpus frames that lose their assertion by it.
* `play-energy-denial` (+20 flat) -> was ALREADY RETIRED 2026-07-14 by ADR-0062, replaced by
  `_DENIAL_PLAY_W`'s per-damage-point pricing. Its retirement record lived in the deleted
  `baseline_disruption.py`; it is repeated here because deleting a module deletes the history of
  rungs it retired MONTHS earlier, and that history is the audit's whole answer column.

The BENCH cluster is GONE, not empty (Issue #261 item 2d). ADR-0086 deleted nine of its ten rules
into the Deploy Marginal; ADR-0096 decision 2 deleted the tenth, `keep-a-bench` (+60) — it guarded
nothing `Pilot._empty_bench_forced` does not already guarantee (the filter runs AFTER
`_finish_turn_last`, so it wins outright), and it WAS the spare-body cliff: a body priced 1.96 on a
non-empty Bench against 61.96 on an empty one, the entire gap being that rung. The escalating slot
price that replaces the cliff is T3's `development` term family (`state_value.REGISTRY`), not a
rung. A module holding an empty tuple would read as a cluster that merely lost its members.
"""
from common.strategy.baseline.baseline_energy import HYPOTHESES as ENERGY_HYPOTHESES
from common.strategy.baseline.baseline_evolution import HYPOTHESES as EVOLUTION_HYPOTHESES
from common.strategy.baseline.baseline_opening import HYPOTHESES as OPENING_HYPOTHESES
from common.strategy.baseline.baseline_phases import HYPOTHESES as PHASES_HYPOTHESES
from common.strategy.baseline.baseline_posture import HYPOTHESES as POSTURE_HYPOTHESES
from common.strategy.baseline.baseline_promote import HYPOTHESES as PROMOTE_HYPOTHESES
from common.strategy.baseline.baseline_snipe import HYPOTHESES as SNIPE_HYPOTHESES

# Full baseline roster, authored order; order runtime-irrelevant (Pilot sums scores), kept stable for
# legibility. (Tool rules promoted to Tool DOCTRINE `doctrines/doctrine_tool.py` once needing board-math; ADR-0028.)
BASELINE_HYPOTHESES = (
    ENERGY_HYPOTHESES + SNIPE_HYPOTHESES + PROMOTE_HYPOTHESES
    + EVOLUTION_HYPOTHESES + OPENING_HYPOTHESES + PHASES_HYPOTHESES
    + POSTURE_HYPOTHESES)

__all__ = [
    "BASELINE_HYPOTHESES",
    "ENERGY_HYPOTHESES", "SNIPE_HYPOTHESES", "PROMOTE_HYPOTHESES",
    "EVOLUTION_HYPOTHESES", "OPENING_HYPOTHESES", "PHASES_HYPOTHESES",
    "POSTURE_HYPOTHESES",
]
