# ADR-0050: The Lethal Solver's engine verify seeds the EXACT deck; the multi-step verification tool is that seeding + a fixture backfill + a pytest helper

**Status.** Accepted + **Phases 1, 2 AND 3 built** — Phase 3's follow-up hooks shipped 2026-07-13 and
are `PROFILE=True` (`retreat_enabler_lethal`, `disruptor_lock_maneuver`). *(Corrected 2026-07-14: the
body still called Phase 3 "UNBUILT".)* Grilled + TDD-built 2026-07-10 (`/grill-with-docs` +
`/tdd` on `data/handoffs/pokemonai-handoff-lethal-multistep-verification-tool.md`). Supersedes that
handoff's framing of the required capabilities. Phase 3 (the `lethal-retreat-enabler` follow-up hooks)
remains a separate `/update-strategy` task, gated by the `engine_confirms` helper this delivered.

**Built:** `Pilot._exact_own_zones` / `_seed_zones` + `lethal_seed_exact` kill-switch (default on, all
three agents); `tools/train/backfill_seed.py`; `tools/sim/lethal_probe.py`;
`tests/lethal_helpers.py::engine_confirms`; the five lethal fixtures backfilled with seed + `own_prizes`;
the `planner-code` gate + `docs/lethal-verification.md`. Tests: `tests/strategy/test_planner_seed*.py`,
`tests/strategy/test_lethal_helpers.py`, `tests/sim/test_lethal_probe.py`,
`tests/train/test_backfill_seed.py` (suite green, 1456 passed). **DoD #3 audit outcome:** of the applied
lethals, `f110` confirms end-to-end; `f26`/`f48`/`f24` (mega_lucario) do **not** complete under the
policy cascade — a **pre-existing** condition (identical under prefix and exact seeding, so not caused
by this fix), filed for Phase-3/blunder-buster analysis rather than blocking (per the audit policy).

**Context.** The Lethal Solver ([ADR-0030](0030-winning-this-turn-is-an-eager-engine-verified-lethal-solver.md) /
[ADR-0037](0037-lethal-solver-is-the-turn-planners-top-rung.md)) proves a win real with
`_engine_confirms_win` (`planner.py:529`): it forks the native engine from `obs["search_begin_input"]`,
steps a candidate line, then drives *my* follow-up selects through `decide()` to the engine's own
verdict. A refute drops the candidate (never lock a phantom); a **None** verdict keeps the sound
closed-form lock. The handoff asked for a test/probe harness so multi-step lines (retreat/tutor/fetch
compositions — the deferred `lethal-retreat-enabler`, correction `84071010:f15`) could be **verified
end-to-end** and their follow-up selects **probed** to author steering hooks grounded, instead of only
recognized closed-form.

Grounding the handoff against the real engine (2026-07-10) changed the picture on every point:

- **Its two stated blockers are false.** (a) The seed is *not* absent from fixtures — it is stripped
  from the **film obs** (`steps[0][0].visualize[i].obs`, which `backfill_obs.py` copies) but **present
  on the step observation** (`steps[k][seat].observation`). The two objects deep-equal on
  `select`+`current` (verified: 60/60 option frames in `tests/fixtures/match-replay.json`, zero
  collisions), so the seed is recovered by a **content-join**, not a replay-through-`cg.api`
  re-derivation. All source replays are on disk (`data/replays/`). (b) The **end-to-end line driver
  already exists** — `_engine_confirms_win(obs, line_steps, record=)` *is* it, `record=` and all.
- **The motivating win is real.** Hand-driving f15's ideal line through the engine — Petrel → tutor
  Air Balloon → attach onto Active Makuhita → retreat → promote Mega Lucario ex → Aura Jab → cascade —
  returns `result == yourIndex` = **WIN**. There is a genuine win to build toward; the Solver simply
  never composes it.
- **The real blocker is one the handoff never names: prefix seeding.** `_engine_confirms_win`,
  `_simulate_line`, and `_engine_leaf_value` seed the engine's hidden zones with `self.deck[:n]` — a
  prefix of the **id-sorted** decklist. Because `deck.csv` is id-sorted (energy → Pokémon → Trainer),
  the prefix cut lands mid-Trainer and **systematically hides the high-id utility band** — retreat
  enablers, gusts, damage boosters. At f15, `deck[:44]` excludes Air Balloon (id 1174, positions
  45–46), so the Solver's own verify **cannot see the enabling card and false-refutes the line no
  matter how good `decide()` becomes.** This is why low-id fetches (recover a Basic {F} Energy, id 6)
  ship today while retreat-enablers were deferred: the deferral was blamed on missing follow-up hooks,
  but the verifier was structurally blind regardless.

**Decision.** The deliverable is a **seeding fix** plus a **fixture-backfill + pytest helper**, split
in two phases. It does **not** build the deferred lethal proposals — it unblocks them.

### Phase 1 — the engine verify seeds the EXACT remaining deck, not a decklist prefix

Every `search_begin` the Pilot issues derives `your_deck` / `your_prize` from the match-scoped own-card
model instead of `self.deck[:n]`:

- **Source already exists.** `_deck_known_counts(me, own_prizes)` (`pilot.py:3359`) returns
  `decklist − visible − prizes` — the EXACT remaining-deck multiset — once the deck tracker has
  anchored the prizes (`obs["own_prizes"]`, [ADR-0029]/`OwnCardModel`), else `None`. `Board.deck_known_counts`
  already carries it. So `your_deck` = that multiset flattened; `your_prize` = `own_prizes` flattened.
- **Soundness is the whole point.** The exact split is sound in both directions; the prefix was
  unsound in *both*. Under-seeding (Air Balloon missing) false-refutes — safe (miss a win, never lock
  a phantom) but coverage-blind. Over-seeding — the prefix seats *all four* Fighting Gongs when one is
  prized, and could seat a **fully-prized** low-id card in the deck → a **false CONFIRM**, the one
  catastrophic Solver error. The fix removes both. NB: the tool must never "dump the deck+prize pool
  into the deck half" (an over-count that re-introduces the false-confirm) — it seeds the exact split
  only.
- **Fallback when unanchored** (`deck_known_counts is None`): **return `None`** (keep the sound
  closed-form verdict). This is near-moot because the fetch tiers that need exact deck content
  (`_family_win_candidates` tiers 3–4) gate on `deck_definitely_has` → `deck_known_counts`, so they are
  only *generated* post-anchor; the develop/direct tiers whose verdict is deck-independent are
  unaffected by the seed either way.
- **Opponent hidden zones stay as-is** (my-deck prefix). A this-turn lethal ends before the opponent
  acts (`_engine_confirms_win` refutes the moment control passes to them), so opponent deck/hand/prize
  content is immaterial to the verdict. `_simulate_line(opponent_reply=True)` (Tier-6 escalation,
  default-OFF, proxy policy) is out of scope.
- **Kill-switched** `lethal_seed_exact` (param, **default ON**), wired in all three agents' `main.py`
  (they share the pattern). A behavior change on a default-ON path, shipped default-on + kill-switch +
  telemetry per [[gauntlet-invalid-ladder-only]] — but uniquely, it is **locally unit-provable**: the
  corrected seed makes the Petrel tutor menu contain the deck-certain Air Balloon that the prefix hid,
  and existing lethals are unchanged.

### Phase 2 — the tool: fixture backfill, follow-up-select probe, pytest helper

- **(A) Backfill.** A one-shot over `tests/fixtures/corrections/*.json` that, per fixture, finds its
  replay by episode id, content-joins `obs → step observation` to copy `search_begin_input`, and
  replays the seat's own observation stream through `OwnCardModel` to write the exact `own_prizes`.
  Both fields also written by the **capture path** going forward (`blunder_correction` /
  `backfill_obs.py`), so new fixtures are cascade-ready by default.
- **(C) Probe.** `tools/sim/lethal_probe.py`: given a seeded fixture + a first step, dump every
  follow-up select's `context`, options, and **resolved** `card_id` / `inPlayArea` / `inPlayIndex`
  (via the Pilot's own `_option_card_id`), so follow-up-steering hooks are authored against real
  encodings. (The grill already surfaced them: MAIN play = type 7 *positional hand index, no card id
  on the option*; tutor pick = type 3; attach = type 8 `inPlayArea` 4=active/5=bench; retreat = type
  12; promote = ctx 3; attack = type 13 `attackId`; an attack's own after-effect is a further cascade
  select.)
- **(D) Helper.** `tests/lethal_helpers.py::engine_confirms(fixture, pilot)` — skips (not
  fails) when the native lib is absent (mirrors the existing `test_*_engine.py`), else backfills the
  seed, seeds the exact deck, drives the fixture's line through `_engine_confirms_win`, and asserts the
  engine's **win verdict**. This turns a closed-form-only retest into a true end-to-end gate. `line=`
  accepts EITHER a single select's picks (the default `[correct]`: one explicit step, `decide()`
  completes it — the gate for a BUILT fix) OR a full explicit multi-step line-of-lists (drive every
  listed select, `decide()` handles only the trailing pure cascades — the proof-of-target for a lethal
  whose follow-up hooks are ~~still UNBUILT~~ **BUILT 2026-07-13** (`retreat_enabler_lethal` + `disruptor_lock_maneuver`, both `PROFILE=True`); DoD #3
  `f24`).
- **(DoD #3) Re-verify the applied lethals end-to-end** — their first-ever engine-cascade check.
  `f110` (low-id {W} fetch) already confirms and is the tool's hook-free proof-of-life. If any applied
  lethal is found **closed-form-only** (the cascade refutes a shipped line), that is the tool
  succeeding: **file it as a new Correction / capability-gap and do not block** (a false-refute is
  safe — it misses a win, never locks a phantom). DoD #3 reads "N re-verified: M confirm, K
  characterized closed-form-only and filed."

  **DoD #3 result (2026-07-11): 4 re-verified — 1 confirm, 2 win-gate-N/A, 1 real missed win filed.**
  Each ideal line was hand-driven to the engine's own verdict; win conditions checked at source
  (`docs/rules.md` §6–7: megaEx=3 / ex=2 / regular=1 prize; win = last prize OR opponent has no Pokémon
  to promote).
  - **`f110` (mega_starmie) — CONFIRM.** A genuine this-turn win: opp Active is a 10-HP Mega Lucario ex,
    my prizes = 2 → Jetting Blow 120 KOs it and takes my last prizes. The hook-free proof-of-life.
  - **`f26` + `f48` (mega_lucario) — win-gate N/A, NOT closed-form-only.** Their ideal lines (grab {F} →
    attach the benched Mega Lucario ex → retreat → promote it → Aura Jab 130 KO Tangela 80, recycling 2
    {F} to the bench) are real **KOs, not this-turn wins**: prizes = 6, Tangela is a 1-prize regular
    (6→5), opp bench is full (3 / 5) → control passes to the opponent (verdict `False`, a true handoff
    refute, not a cap-`None`). They ship via `_grab_lethal_tactical`, which scores **"any KO, not just a
    win"** and names `ml f26/f48` outright; the grab fix IS applied (`decide()` picks the correct fetch).
    `engine_confirms` is a **win** gate, so it refutes them by category, not defect — do **not** file as
    missed wins and do **not** gate KO-tactical fixtures on it. (Residual, tactical: `decide()`'s
    post-grab cascade retreats and promotes **Solrock**, swinging 70 and leaving the Aura Jab KO — a
    KO-quality steering gap, not a lethal.)
  - **`f24` (mega_lucario) — real missed win, filed.** A bench-empty win: attach {F}→Solrock, play 2×
    Premium Power Pro (+30 each to {F} attacks), retreat Lunatone, promote Solrock, Cosmic Beam 70+60 =
    130 OHKOs Duraludon 130 with the opp bench empty. `engine_confirms` returns **True on the full
    explicit line** and **False on `[correct]`-only** (`decide()` picks Meowth ex; no
    `_family_win_candidates` tier composes a damage-boost-Item lethal). Filed as capability-gap
    `data/strategy/proposals/applied/capability-gap-damage-boost-item-lethal.md` (Phase-3 sibling of
    `lethal-retreat-enabler`); pinned by `test_engine_confirms_multi_step_line_proves_a_real_missed_win`.
- **(DoD #5) Gate.** Wire `engine_confirms` into the `planner-code` authoring gate
  (`update-strategy/references/authoring-gates.md`) — multi-step lethal proposals become
  engine-cascade-confirmed, not closed-form-only — plus a short `docs/` note.

### Out of scope (Phase 3, separate — the consumers this unblocks)

`lethal-retreat-enabler` and the sibling `retreat-to-item-lock` each need a NEW
`_family_win_candidates` tier **and** follow-up steering hooks in `decide()` (tutor→the right Tool,
play-Tool→Active, retreat, promote) — the same class of work, default-ON Solver behavior. They are
authored via `/update-strategy` under the ADR-0046 producer/apply split, each **gated by the Phase 2
helper** (f15 → WIN is that follow-up's gate, not this task's). Keeping them out preserves the tool as
a reusable capability and prevents a hook bug and a seeding bug from landing together.

**Consequences.**

- The Solver's engine verify becomes sound (removes the latent false-confirm path) and complete for
  the high-id utility band, at ~10 lines per call site reusing existing machinery.
- Multi-step lethal fixtures gain `search_begin_input` + `own_prizes`; the offline suite stays green
  cross-platform (the helper skips without the native lib).
- The tool may reveal shipped lethals are closed-form-only; that is a logged win, not a regression.
- The deferred retreat/tutor/fetch class is unblocked as a whole, authored grounded via the probe and
  gated by the helper — not built blind into the one place a phantom win *loses the game*.

**Provenance / prior art.** `_engine_confirms_win` / `_simulate_line` (`planner.py`), `cg.api`
search API (`src/common/CONTEXT.md` §search-lookahead), `_deck_known_counts` + `OwnCardModel`
([ADR-0029]), `backfill_obs.py`, `tools/sim/battle.py`. Corrections `84071010:f15` (motivating),
`*_recover_energy_*` / `*_boost_to_ko_*` (DoD #3). Do not touch `src/cg/` ([[src-cg-off-limits]]).
See [[lethal-verification-tool-grill]], [[retreat-to-promote-deferrals]].
