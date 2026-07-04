# Blunder-buster round 2026-07-04 — new-deck wiring + general-doctrine gaps

Three agents (mega_lucario, dragapult_ex, mega_starmie). The user's report: "our two new ones played
terribly, the general strategies did not help them at all — are they even wired?" Two true root causes.

## Root cause 1 — the wiring bug (headline)

`mega_lucario/main.py` and `dragapult_ex/main.py` **omitted the five planner/lethal kill-switches**
(`lethal_verify`, `planner_engine_rank`, `planner_key_threat`, `lethal_family`, `lethal_veto`). The
`Pilot.__init__` defaults all five to `False` (the ctor is the raw-scoring layer; the validated-best
deployment config is opted into at the agent level). So both new decks shipped with the **Turn Planner
degraded and the Lethal Solver in legacy mode** — the exact "plan the turn / spot the KO" systems dark.
mega_starmie set them via `_params.get(..., True)`; the deck-genie main.py template didn't.

- **Fix:** added the five lines to both main.py (mirroring mega_starmie) + a new AST invariant test
  `tests/agents/test_agent_wiring.py` — every shipped agent must wire each switch `_params.get(k, True)`,
  so the omission fails CI instead of the grader.
- Also fixed `tune.py:_build_pilot` to pass `attack_stats` + `effects` (it claimed to "mirror main.py
  EXACTLY" but omitted them) — retest/tune now reflect the real shipped agent.

`tune.py` already rebuilds fully-wired, so the wiring bug didn't change the correction worklist — but the
shipped agents were degraded. The discard/grab/attach blunders below are genuine general gaps regardless.

## Root cause 2 — general-doctrine gaps the deep-evolution/multi-type lines exposed

mega_starmie's single-hop Staryu→Mega line, developing via `bench_fill`/Turbo Flare, never exercised these.
The deep lines (Riolu→Mega, Dreepy→Drakloak→Dragapult) play bare Basics from hand, discard their own line
bases for costs, shuffle holding line pieces, run a mid-line evolution, and attach multi-type costs.

## Authored this round (all green; full suite 1218 passed)

| rule / infra | fixes | proof (retest) |
|---|---|---|
| `develop-a-basic-in-setup` (+12) | ml f29 fixed; f33/f40/f44 covered | develops a Basic tier-0 before the chip/shuffle |
| `keep-line-base-at-discard` (−15) + `_BASE_ROLES` exempt | ml f30, dp f18 | keeps Riolu/Makuhita/Dreepy; sheds spent supporter |
| `keep-basic-energy-when-starved` (−12) | dp f11 | keeps the Fire Energy, discards Lillie's |
| `hold-line-piece-dont-shuffle` (−25) + Board.`line_preevo_in_hand` | dp f13 | End turn over shuffling away the fetched Drakloak |
| `advance-the-evolution-line` (+15) | dp f29 | evolves the started line over a spread attach |
| `evolve-the-energized-body-first` (+5) | ms f25 | evolves the 3-Energy Staryu, not the bare one |
| `dont-waste-off-type-energy` (−12) + AttackStat.`energyTypes` + `_attach_type_wasted` | dp f45 | the 2nd-Psychic attach dead-last; completes a line |
| `dont-grab-a-baseless-mid-evolution` (−25) + `card_evolution_baseless`; `grab-a-draw-supporter` Supporter-gate | dp f33 | grabs Munkidori over a baseless 3rd Drakloak |
| `recover-to-refill-bench` (+22) | ms f87/f120 | plays Night Stretcher to refill the empty Bench |
| `_LOOKING`(=12) resolution in `_option_pokemon` | dp f35 covered | Cinderace grab now sees `dont-fetch-the-setup-only-opener` (−60) |
| tool branch-(3) `require_threat` gate (`_WALL_THREAT_TURNS=2`) | ms f12 | Cape not deployed on a safe Cinderace; energy attach wins |

## Terminal-outcome ledger

- **dragapult_ex (7):** all resolved — f11/f13/f18/f33/f35 fixed (W-route drops), f29/f45 covered. Open set empty.
- **mega_lucario (8):** f29/f30/f40 fixed (drop); f19/f31/f33/f44 covered (ledgered); f3 **refuted (CRITICAL — pending ack)**.
- **mega_starmie (10):** f12/f25/f120 fixed (drop); f27/f87 covered (ledgered); f19 refuted (KO); f30/f45/f107 capability-gap (deferred, docs/todo/deferred-multi-turn-criticals.md); f54 **refuted (CRITICAL — pending ack)**.

Method note: the develop-first / recover / KO-deferred fixes are **tier-mediated** (`_finish_turn_last`),
which the score-only Verifier (W-route) can't register — the gate for those is real-Pilot retest +
suite-green, disposition `covered`, per the existing ledger precedent. Native `cg.dll` serializes to one
process (concurrent engine processes deadlock — kill all python between runs).
