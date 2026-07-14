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

## 2026-07-13/14 — 2nd instance (SUPPORT-EX-PIVOT variant): now an OPEN planner-code proposal (blunder-buster, build 2d2a113)

A new correction **85786096:t2 (CRITICAL, `85786096-t2s0`)** re-surfaces this maneuver in a **new shape**. It
was first routed capability-gap and DEFERRED (the offensive `disruptor_lock_maneuver` build was unmerged in the
blunder-buster branch). The branch was then **rebased onto main** (PR #92 / commit 4e38243 merged the build,
now in-tree + default-ON); re-probed against the merged code it STILL blunders, so the user **graduated it to
an open planner-code proposal** — `disruptor-lock-from-a-support-ex-pivot` in
`data/strategy/proposals/blunder-20260713-2d2a113.md`. No longer deferred; the reviewed.json defer was
removed. Fixture: `tests/fixtures/corrections/dragapult_retreat_to_item_lock_fez_pivot_f25.json`.

- **Board (turn 2 vs Cinderace / Mega Starmie ex, gamma 1.0):** Active = **Fezandipiti ex** (id140,
  210/210, {D}, retreat 1) — a **support-ex PIVOT**, NOT a fragile win-condition line pre-evo. Bench holds
  **Budew** (id235, `item_lock`). Hand has one Basic {R}. Human line: attach {R}→Fez → retreat (the {R}
  pays the cost 1) → promote Budew → Itchy Pollen item-lock. `retest_one 85786096-25`: `decide()=[1]` bench,
  `planned=None`, `dont-feed-the-doomed` (−30, baseline_energy.py) sinks the maneuver-enabling active attach.
- **Why `retreat-to-wall-the-line` does NOT cover it:** that built rung (baseline_retreat.py:21) gates on
  `_can_wall_line_with_disruptor` (pilot.py:3555), whose FIRST clause requires
  `ma.id in _line_preevo_set()` — the Active must be a **fragile win-condition LINE pre-evo (Dreepy)**.
  Fezandipiti ex is a support-ex pivot, not a line pre-evo, so the gate is False → nothing fires. The
  built maneuver only recognizes the "wall the fragile line" trigger; this is a **"sac the support-ex pivot
  to open the item-lock"** trigger — a distinct premise. The attach-enablement step (feed a 0-energy Active
  so it can afford the retreat) remains unbuilt for BOTH triggers (that is the still-deferred f20 half).
- **The OFFENSIVE maneuver IS BUILT and now IN-TREE:** the f20 offensive item-lock maneuver shipped as
  **`disruptor_lock_maneuver`** (`_can_lock_line_with_disruptor` + `feed-the-line-for-disruptor-lock` +20;
  commits `4e38243` / `68181a9`), merged to **main** via PR #92 and pulled into this branch by the rebase —
  default-ON (`runtime.py:41`). So t2 is **NOT** a from-scratch build; the framework exists. `cgpy`/
  `lethal_verify` is a **WIN** verifier only (it made the LETHAL f15 safe) — orthogonal to this no-KO tempo
  line, so it was never the blocker either.
- **Why t2 is STILL a gap — a DISTINCT TRIGGER:** the built gate `_can_lock_line_with_disruptor` requires
  `ma.id in _line_preevo_set()` (a **fragile win-condition LINE pre-evo** Active, e.g. Dreepy). At t2 the
  Active is **Fezandipiti ex** (a **support-ex PIVOT**, not a line pre-evo), so the maneuver returns False
  (re-probed against merged code: `decide()=[1]`, `feed-the-line-for-disruptor-lock` does not fire). This is
  a NEW trigger: "sac the retreatable support-ex pivot to open the item-lock," alongside the existing
  "wall/develop the fragile line" trigger.
- **DoD (a SMALL extension — now an OPEN planner-code proposal, not deferred):** extend
  `_can_lock_line_with_disruptor` (OR branch / sibling premise sharing the rung) so the maneuver ALSO fires on
  a **retreatable non-attacking support-ex pivot Active** behind a benched `item_lock` opener, under the SAME
  guards (turn ≤ 2; nothing being developed = no wincon-Line body carries Energy; retreat reachable this turn
  on ≤1 more Energy; Active can't already KO). Verify on BOTH fixtures:
  `dragapult_retreat_to_item_lock_f20.json` (Dreepy-line, now FIXED by the shipped build) AND
  `dragapult_retreat_to_item_lock_fez_pivot_f25.json` (Fez-pivot). Still the RECOVERY line (primary path
  `open-the-item-lock-starter` + `preferred_start="second"` opens Budew Active with no maneuver); rank
  accordingly. **Queued as `disruptor-lock-from-a-support-ex-pivot`** in
  `data/strategy/proposals/blunder-20260713-2d2a113.md` (the reviewed.json `85786096-t2s0` defer was removed).
