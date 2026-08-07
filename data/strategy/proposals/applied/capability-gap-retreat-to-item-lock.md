<!-- Strategy Proposal queue — promoted 2026-07-09 by strategy-ingest from an internal capability-gap doc.
Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md

WHY THIS FILE: docs/todo/retreat-to-item-lock-maneuver.md is a blunder-buster capability-gap (dragapult
85046350:f20) that was ledgered `deferred` in reviewed.json and only MENTIONED as a set-aside in
blunder-20260709-dragapult_ex.md — it had no drainable `## ` record, so update-strategy could not pick it
up. strategy-ingest was pointed at the doc to promote it into a drainable planner-code proposal. The rich
source stays in docs/todo/ (its home); this record links to it. Source is tagged `blunder-buster` because
that is the finding's true analytical origin (verifier gate, fixture re-measure) — strategy-ingest only
routed it into the queue. -->

## retreat-to-promote-a-disruptor (Turn Planner generator)
- id: retreat-to-promote-a-disruptor
- source: blunder-buster
- target_layer: planner-code
- for: general
- candidate_signal: needs a new signal — a Turn Planner generator (planner.py) keyed on a benched `item_lock` opener behind a retreatable, non-attacking Active, gated by an opponent-item-reliance / disruption-value read. DEPENDENCY: the `item_lock` behavioral tag on Budew (card id 235) — currently untagged; also proposed by `open-the-item-lock-starter` in data/strategy/proposals/deck-genie-20260709-dragapult_ex.md.
- verification_contract: verifier
- provenance: docs/todo/retreat-to-item-lock-maneuver.md | correction 85046350:f20 (reviewed.json "85046350-20", deferred) | fixture tests/fixtures/corrections/dragapult_retreat_to_item_lock_f20.json | [[dragapult-ex-built]] | related [[m2-posture-plan]] (opponent-filtered disruption)
- status: applied (2026-07-13 — `disruptor_lock_maneuver`, the OFFENSIVE item-lock variant; see docs/todo/retreat-to-item-lock-maneuver.md)

**Spec (authoring spec — thin fodder, not finished code):**
The closed-form Turn Planner (ADR-0031/0037) has no rung that generates a single-turn
**retreat-to-promote-a-disruptor** maneuver. When a high-value disruptor opener — `item_lock` (Budew's
Itchy Pollen: 0-cost, 10 dmg, opponent can't play Items next turn) — sits on the bench behind a
retreatable, non-attacking Active, the sound line is: **attach → retreat the Active (the attached energy
pays the retreat) → promote the disruptor → attack (Itchy Pollen)**, item-locking the opponent for their
turn. Today `dont-feed-the-doomed` (−30, the T2 active reads worst-case doomed) sinks the step-1
attach-to-Active option, and no generator produces the follow-through, so `decide()` picks a bench attach
(`[1]`) and the maneuver never materializes.

This is a **capability-gap (planner-code), NOT a weight/when()**. A naive "attach to the active" rule
would be *actively harmful* in isolation: it sinks the turn's energy into a body about to be retreated
(the energy is discarded to pay retreat) with no follow-through, because the Pilot has no generator that
then retreats-and-promotes-the-disruptor and attacks. The value only exists as **step 1 of the whole
maneuver**, so the fix must be a generator that builds and scores the full line against developing
normally, and commits it when the tempo/disruption value beats the forgone development.

Guardrails (from the doc's definition-of-done):
- **Inert** for decks with no benched `item_lock`/disruptor opener (verify no-op on mega_starmie /
  mega_lucario).
- **Never** retreat a live attacker into a worse board just to lock.
- **Only fire** when the item-lock's disruption value (opponent is item-reliant this turn) exceeds the
  forgone development — guard against burning a turn.

**Priority — this is a RECOVERY line, not the primary mechanism.** The intended path is upstream and
already shipped/queued: `open-the-item-lock-starter` (+35, baseline_opening.py) + `preferred_start="second"`
open **Budew Active** at the pregame `_SETUP_ACTIVE` pick (see
data/strategy/proposals/deck-genie-20260709-dragapult_ex.md), so Itchy Pollen fires T2 with no maneuver.
This generator matters only when Budew did **not** open Active. Rank the build accordingly.

**Verify:** `decide()` on `dragapult_retreat_to_item_lock_f20.json` promotes Budew and item-locks (the
maneuver materializes), OR the fixture is re-scoped if the pregame opener alone is judged sufficient and the
recovery line is not worth a planner rung.

**update-strategy verdict (2026-07-09): DEFERRED — capability-gap (confirmed).** This IS a planner-code
capability-gap as authored: a naive attach-to-Active weight is actively harmful in isolation, so the sound
fix is a Turn-Planner generator that composes attach → retreat → promote-the-disruptor → Itchy Pollen and
commits only when the disruption value beats the forgone development. Deferred for two reasons: (1) it is a
low-priority RECOVERY line — its PRIMARY path is APPLIED (`open-the-item-lock-starter` +35 at baseline_opening.py
+ `preferred_start="second"`), so Budew opens Active and Itchy Pollen fires T2 with NO maneuver; this generator
only matters when Budew did not open Active. (2) It is a retreat-to-promote MULTI-STEP composition whose
completion the single-frame f20 fixture cannot verify (no `search_begin_input`) — the SAME blocker as the
deferred `lethal-retreat-enabler`, and its handoff explicitly covers this case:
**`data/handoffs/pokemonai-handoff-lethal-multistep-verification-tool.md`** (a broad engine-backed harness for
retreat/tutor/fetch compositions). **Definition-of-done:** build that tool, then author the Turn-Planner
retreat-to-promote-disruptor generator gated on an opponent-item-reliance read, verified by f20 materializing
the maneuver (or re-scope f20 as covered-by-the-opener if the recovery line proves not worth a rung).

**update-strategy UPDATE (2026-07-10): PARTIAL — the RETREAT frame is built (with f32); THIS attach-enablement frame is NOT, so f20 STAYS DEFERRED.** The sibling
correction **f32** (same episode 85046350) made this maneuver's value vivid, and the grill concluded the
multi-step-verification-tool blocker does NOT apply here: that blocker is for **lethal** lines (a phantom
win loses the game), but this is a **TEMPO** maneuver — its first step (Retreat) is single-frame
verifiable and a partial completion is non-catastrophic. So it was built now WITHOUT the tool (which stays
the blocker for the LETHAL `lethal-retreat-enabler` f15 ONLY). Authored as `retreat-to-wall-the-line`
(planner-code): Board signal `can_wall_line_with_disruptor` + `_can_wall_line_with_disruptor`, a **tier-0
branch in `_finish_turn_last`** (so RETREAT sequences as step 1 instead of its default tier 4), and a
`hold-position-in-setup` stand-down. Full authored change + verification in the f32 record
the applied `advance-line-over-marginal-energy-strip` proposal (file removed after application); pinned by
`tests/strategy/test_blunder_20260710_split_fixes.py::test_f32_...`. **CORRECTION (2026-07-10): f20 is NOT
closed — only f32's retreat frame is.** The shared `retreat-to-wall-the-line` rung fires on the RETREAT
option (f32: Dreepy already energized). THIS fixture is the earlier ATTACH-enablement frame (Dreepy @0
Energy, AttachFrom ctx 21 — feed the ACTIVE line-preevo so it can later retreat), which the rung does NOT
touch: re-probed 2026-07-10, decide()=[1] bench, correct=[0] active — STILL the blunder (`dont-feed-the-
doomed` -30 sinks the active attach +5 below the bench +15). **Definition-of-done (revised):** author a
rung that endorses attaching to the fragile line-preevo Active when `can_wall_line_with_disruptor` holds
AND the retreat becomes affordable next turn (so the maneuver is REACHABLE from a 0-Energy start, not only
when Dreepy is coincidentally energized). The primary path remains the pregame opener
(`open-the-item-lock-starter` + `preferred_start="second"`); this maneuver is the RECOVERY line for when
Budew did not open Active. NOTE: the opponent-item-reliance gate in
the original DoD was NOT added — the trigger uses `opp_active_can_damage_us` (protect the fragile line
when threatened); an item-reliance read stays a possible refinement.
