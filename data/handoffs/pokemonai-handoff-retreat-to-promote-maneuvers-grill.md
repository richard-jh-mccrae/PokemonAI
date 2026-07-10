# Handoff — grill the two deferred retreat-to-promote maneuvers

**Status:** deferred capability-gaps (both), 2026-07-10, from the `/update-strategy` queue drain (PR #67).
**Purpose:** a cold-start grill brief to design the sound build of both. Both are **retreat → promote a
benched body → act** compositions the generators don't yet compose. Both are blocked on the **same
prerequisite** — an engine-backed multi-step verification tool
(`data/handoffs/pokemonai-handoff-lethal-multistep-verification-tool.md`).

---

## Item A — `lethal-retreat-enabler` (a thrown WIN, HIGH value)

**Source:** correction `84071010:f15` (mega_lucario) | proposal record + verdict:
`data/strategy/proposals/blunder-20260709-mega_lucario.md` (status: deferred) | fixture
`tests/fixtures/corrections/ml_dead_hand_full_refresh_f15.json`.

**The win line — CONFIRMED at source 2026-07-10 (re-verify before building; engine + `data/EN_Card_Data.csv`
are ground truth):**
> Play **Team Rocket's Petrel** (1219, Supporter: "search your deck for a **Trainer** card") → fetch
> **Air Balloon** (1174, Pokémon Tool: retreat −{C}{C}; deck runs 2 + a Switch) → attach it to the Active
> **Makuhita** (673, retreat 2) → retreat is now free → **free-retreat** → promote benched **Mega Lucario ex**
> (678, 340 HP, 1 {F}) → **Aura Jab {F} 130 ≥ opp Riolu 80 HP**, opp bench EMPTY → they have no Pokémon to
> promote → **WIN.**

**What it is:** a **Lethal Solver win-line generator** gap (`_family_win_candidates`, planner.py; surfaced via
`_grab_lethal_tactical`, pilot.py). Ships today: the grab-enables-lethal / energy-recover family, and (applied)
`lethal-recover-the-energy-that-wins` handles retreat-into-a-benched-attacker **when the retreat is already
affordable**. This case adds the **retreat-AFFORDABILITY enabler**: play (or tutor-then-play) a retreat Tool
so an otherwise-unaffordable retreat becomes free, THEN promote the attacker. `live_trace.lethal` was null.

**Why it's blocked (two things, both real):**
1. **Follow-up-select steering is absent + un-probeable here.** The Solver's `_engine_confirms_win` cascade
   re-runs `decide()` on every follow-up select (planner.py:602), so confirming this win needs `decide()` to
   drive **tutor → Air Balloon** and **play-Tool → the Active** during the cascade (retreat/promote/attack
   likely ride existing scoring rungs). Those hooks don't exist and can't be authored grounded without
   probing the Petrel-tutor + Air-Balloon-play select encodings — which this single MAIN-menu frame lacks.
2. **The f15 fixture can't exercise the cascade.** It has no `search_begin_input`, so `_engine_confirms_win`
   is a no-op in the unit suite → a closed-form-only retest proves RECOGNITION, not real-play COMPLETION (a
   false-green — [[wroute-satisfied-not-fixed]]). The Solver's one catastrophic error is a **phantom win**
   (a miss costs a turn; a phantom loses the game), so building the hooks blind is the wrong risk.

**Fixture note:** the fixture carries the RETIRED dead-hand framing (`correct:[1]` Lillie's). In the lethal
framing the correct first step is **`[0]` Play Petrel** — the very option logged as the "blunder." Reframe on
build: `correct`→`[0]`, category→missed-lethal, assert `lethal` becomes non-null, add `search_begin_input`.

---

## Item B — `retreat-to-promote-disruptor` (a tempo RECOVERY line, LOW priority)

**Source:** correction `85046350:f20` (dragapult) | record: `data/strategy/proposals/capability-gap-retreat-to-item-lock.md`
(status: deferred) | doc: `docs/todo/retreat-to-item-lock-maneuver.md` | fixture
`tests/fixtures/corrections/dragapult_retreat_to_item_lock_f20.json`.

**The line:** a benched `item_lock` opener (**Budew** 235, Itchy Pollen: 0-cost, 10 dmg, opponent can't play
Items next turn) sits behind a retreatable, non-attacking Active. Sound maneuver: **attach → retreat the
Active (the attached energy pays the retreat) → promote Budew → Itchy Pollen** (item-lock them for their turn).

**What it is:** a **Turn Planner tempo generator** gap (planner.py) — NOT a scoring weight. Today
`dont-feed-the-doomed` (−30, the T2 Active reads worst-case doomed) sinks the step-1 attach-to-Active, and no
generator produces the follow-through, so `decide()` picks a bench attach `[1]`. A naive "attach to the Active"
rung is **actively harmful in isolation** (sinks the turn's energy into a body about to be retreated, with no
follow-through) — the value exists only as step 1 of the whole maneuver.

**Why LOW priority:** its PRIMARY path is APPLIED — `open-the-item-lock-starter` (+35, baseline_opening.py) +
`preferred_start="second"` open Budew Active at the pregame pick, so Itchy Pollen fires T2 with NO maneuver.
This generator matters ONLY when Budew did not open Active (a recovery line). **A valid grill outcome is to
re-scope f20 as covered-by-the-opener and NOT build a planner generator at all.**

**Guardrails (from the doc's definition-of-done):** inert for decks with no benched `item_lock`/disruptor
opener (no-op on mega_starmie / mega_lucario); never retreat a LIVE attacker into a worse board just to lock;
only fire when the item-lock disruption value (opponent is item-reliant this turn) exceeds the forgone
development. Needs an opponent-item-reliance read.

---

## Open questions to grill

1. **Build B at all?** Or re-scope f20 as covered by the shipped pregame opener + `preferred_start="second"`,
   and close it. (Cheapest sound outcome; the recovery line may not be worth a planner rung.)
2. **Prerequisite ordering.** Build the multi-step verification tool FIRST (it unblocks both), then author?
   Or grill the maneuver/generator design in parallel while the tool is built?
3. **Follow-up steering (A).** Does the cascade need a NEW tactical hook per follow-up select (tutor→Tool,
   play-Tool→Active), or does the materialized-replay-after-confirm cover real play (so hooks only fire
   inside the cascade)? Note the circularity: the cascade uses `decide()`, and `decide()` needs the hooks.
4. **Shared abstraction?** A is a Lethal Solver win-line family; B is a Turn Planner tempo family — different
   generators, same retreat→promote→act shape + retreat-affordability enabler. Is there one generator
   primitive both use?
5. **Soundness gates.** A must never lock a phantom win (engine-verify every lock; None-verdict keeps the
   coin-floor). B must never burn a turn (commit only when disruption value > forgone development). Pin each.
6. **Probing.** Use the verification tool's probe mode to dump the Petrel-tutor + Air-Balloon-play + Budew-
   promote select contexts so the hooks are authored against real encodings, not guessed.

## Pointers
- Prerequisite tool handoff: `data/handoffs/pokemonai-handoff-lethal-multistep-verification-tool.md`.
- Applied siblings that establish the pattern: `lethal-recover-the-energy-that-wins` (retreat-into-attacker +
  energy fetch), `open-the-item-lock-starter` (+ `item_lock` tag on Budew 235).
- Solver/planner code: `_family_win_candidates` / `_engine_confirms_win` / `replay_locked_line` (planner.py),
  `_grab_lethal_tactical` (pilot.py). Never touch `src/cg/` ([[src-cg-off-limits]]).
- ADRs: 0030 Lethal Solver, 0031/0037 Turn Planner, 0018/0046 the proposal/apply split.
