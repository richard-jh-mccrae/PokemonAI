# capability-gap: retreat-to-promote-a-disruptor maneuver (Turn Planner generator)

> **BUILT 2026-07-13 (`disruptor_lock_maneuver`, default ON, kill-switched; user decision to ship-and-
> refine).** Key diagnosis: the shipped `retreat-to-wall-the-line` premise (`can_wall_line_with_disruptor`)
> needs the opp to threaten damage, which is FALSE at f20 (0-Energy Gible) — so f20 is OFFENSIVE item-lock
> disruption, not defensive walling. New signal `can_lock_line_with_disruptor` (early + fragile line-preevo
> Active + benched `item_lock` opener + reachable cheap retreat + Active can't KO) + rung
> `feed-the-line-for-disruptor-lock` (+20, the attach step) + `retreat-to-wall-the-line`/`hold-position-in-
> setup` broadened to the offensive signal (the retreat step). `decide()`=[0] (was [1]); zero dragapult
> regression. Value is matchup-dependent (a 30-HP Budew may concede a prize) — kill-switch is the lever.
> Tests: `tests/strategy/test_blunder_20260710_split_fixes.py`.

**Status:** PARTIAL (2026-07-10, PR #70). The maneuver's RETREAT frame is BUILT as `retreat-to-wall-the-line` (see the f32 sibling `85046350:f32`). This fixture's ATTACH-enablement frame (Dreepy @0e, AttachFrom — feed the active line-preevo to enable the wall-retreat) is STILL DEFERRED: re-probed 2026-07-10, `decide()=[1]` bench unchanged (`dont-feed-the-doomed` −30 sinks the correct active attach). Ledgered `deferred` in `data/corrections/reviewed.json` (85046350-20).
**Fixture:** `tests/fixtures/corrections/dragapult_retreat_to_item_lock_f20.json`
**Correction:** 85046350:f20 (dragapult_ex, `slow_setup`).

## The blunder

Turn 2, AttachFrom recipient pick. Board: my Active **Dreepy (0e)**; bench Dreepy (0e), **Budew (0e)**,
Dunsparce (0e); opp Active Cynthia's Gible. The human wants the energy on the **active Dreepy** as **step 1 of
a maneuver**: attach → **retreat** Dreepy (paying the retreat cost with that energy) → promote **Budew** to the
Active spot → **Itchy Pollen** item-locks the opponent for their turn. `dont-feed-the-doomed` (−30, the T2
active reads worst-case doomed) sinks the active-Dreepy option; the agent attaches to a bench Dreepy instead.
Real Pilot re-measure (this session, `tune._build_pilot('dragapult_ex').decide`): `decide()` = `[1]` (bench
Dreepy), unchanged from the recorded blunder — **not** already covered.

## Why it is a capability-gap, not a weight/when()

The narrow decision ("attach to active vs bench Dreepy") is only sound as **step 1** of the whole maneuver. A
naive "attach to the active" rule would be **actively harmful** in isolation — it would sink the turn's energy
into a body about to be retreated (the energy is discarded to pay retreat), with no follow-through, because the
Pilot has **no generator** that then retreats-and-promotes-the-disruptor and attacks with it. The sound line
(attach → retreat → promote item-lock opener → Itchy Pollen) is a single-turn **multi-step maneuver**, and the
closed-form Turn Planner (ADR-0031/0037) has no rung that generates *retreat-to-promote-a-disruptor*. Building
one is a designed-but-unbuilt planner layer — hence a capability-gap, not a missing signal.

Note the primary intended mechanism for this deck is upstream and **already shipped**:
`open-the-item-lock-starter` (+35, baseline_opening.py) + `preferred_start="second"` open **Budew Active** at
the pregame `_SETUP_ACTIVE` pick, making Itchy Pollen fire T2 with no maneuver. This maneuver only matters when
Budew did NOT open Active (not in the opening hand), so it is a **recovery** line — lower priority.

## Definition of done

A Turn Planner generator (planner.py) that, when an `item_lock` (or other high-value disruptor) opener sits on
the bench behind a retreatable, non-attacking Active, produces the line **retreat → promote the disruptor →
attack (Itchy Pollen)** and scores it against the held line, committing it when the tempo/disruption value
beats developing normally. Verify:
- `decide()` on `dragapult_retreat_to_item_lock_f20.json` promotes Budew and item-locks (the maneuver
  materialises), OR the fixture is re-scoped if the pregame opener is judged sufficient.
- Inert for decks with no benched `item_lock`/disruptor opener; never retreats a live attacker into a worse
  board just to lock.
- Guard against wasting a turn: only fire when the item-lock's disruption value (opponent is item-reliant this
  turn) exceeds the forgone development.

Related: [[m2-posture-plan]] (opponent-filtered disruption), `open-the-item-lock-starter`, the ADR-0031
single-turn planner boundary (`docs/todo/deferred-multi-turn-criticals.md`).
