# Handoff — an engine-backed verification tool for multi-step turn constructs

**Status:** **BUILT 2026-07-11** — realized as **ADR-0050** (`docs/adr/0050-multi-step-lethal-verification-tool.md`),
merged to `main` via PR #71 (exact seeding + backfill + `engine_confirms` gate + probe) and PR #72
(DoD#3 audit). The grill reframed this handoff: its two stated blockers were false (the seed is a
content-join off the step obs, not a `cg.api` re-derivation; the driver already existed as
`_engine_confirms_win`), and the real blocker — id-sorted decklist-prefix seeding hiding the high-id
enabler band — is what the seeding fix addressed. **Opened:** 2026-07-09 (during `/update-strategy`,
deferring `lethal-retreat-enabler`). **Remaining consumer:** the `lethal-retreat-enabler` follow-up hooks
(Phase 3) — see `docs/todo/lethal-retreat-tool-enabler.md`.

**One line:** Build a test/probe harness that seeds the native engine's `search_begin` from a captured
state and drives a *whole* candidate turn — a first step plus every follow-up select (tutor / play-Tool /
attach / retreat / promote / attack) via the pilot's own `decide()` — to the engine's win **verdict**, so
multi-step Lethal-Solver lines (retreat/tutor/fetch/attach compositions) can be **unit-verified end-to-end**
and their follow-up selects **probed for grounding**, instead of only recognized closed-form.

---

## 1. Why this is needed (the gap that deferred `lethal-retreat-enabler`)

The Lethal Solver (ADR-0030/0037, `src/common/strategy/planner.py`) proves a win is real by
`_engine_confirms_win` (planner.py:529): it forward-simulates a candidate line through the native engine
(`cg.api.search_begin` / `search_step` / `search_end`) and, after the line's own steps, **keeps driving my
cascade selects through `decide()`** (planner.py:602, under the `_planning` guard) until the engine returns
a verdict (`result != -1`). A refute drops the candidate (never lock a phantom); a **None** verdict
(no engine available / undetermined) keeps the sound closed-form lock.

**The seed it needs is `obs["search_begin_input"]`** — an ASCII blob the *native engine itself* emits during
a live battle (`src/cg/game.py:15`) and hands back on each observation. `_engine_confirms_win` returns
`None` immediately without it (planner.py:560).

**Captured correction fixtures do NOT carry `search_begin_input`** (verified 2026-07-09: none of
`ml_dead_hand_full_refresh_f15`, `ml_lethal_recover_energy_retreat_ko_f26`, `ml_lethal_retreat_boost_to_ko_f24`,
`ms_lethal_recover_energy_to_win_f110` have it). So in the unit suite the cascade is a **no-op**: a
multi-step lethal candidate is locked purely on its **closed-form recognition**, and the retest only proves
`decide()` *recognizes* the win at the MAIN menu — **not** that real play *completes* the line (that the
pilot actually drives tutor→the right card, plays the Tool onto the right body, retreats, promotes, and
attacks). A green retest on closed-form alone is the classic false-green ([[wroute-satisfied-not-fixed]]):
the recognition fires, but in a real game the cascade would re-run `decide()` on the follow-up selects, and
if no rung drives them the engine **refutes** the line and the win is silently missed.

Two things are therefore un-doable today for any multi-step lethal:
1. **No end-to-end unit verification** — the fixture can't exercise the cascade, so "real play completes the
   line" is unprovable locally (only the full-game ladder shows it).
2. **No way to author the follow-up steering grounded** — the follow-up selects (e.g. a Trainer-tutor
   `_TO_HAND`, a Pokémon-Tool play + target) aren't present in a single MAIN-menu capture, and there is no
   harness to reach them, so their engine context/option encodings can't be probed. Authoring the hooks
   blind risks the Solver's one catastrophic error (a phantom win loses the game).

### Motivating construct (deferred `lethal-retreat-enabler`, correction 84071010 f15)

Engine-verified this-turn **WIN** the Solver never composes (all card facts confirmed at source
2026-07-09): Active **Makuhita** (retreat 2, 0 energy) blocks a benched **Mega Lucario ex** (340, 1 {F},
Aura Jab {F}=130) from promoting; opp Active **Riolu** 80 HP, **bench empty** (a KO = no Pokémon to
promote = win). Line: **Team Rocket's Petrel** (tutor a Trainer) → fetch **Air Balloon** (−{C}{C} retreat) →
play it onto Makuhita (retreat 2→0) → **free-retreat** → promote **Mega Lucario ex** → **Aura Jab 130 ≥ 80
→ WIN**. The enabling first step is a Supporter that tutors a **retreat Tool**; the follow-up steering
(tutor→Air Balloon, play-Tool→Active) is genuinely absent (`_grab_lethal_tactical` only covers the
energy-recovery lethal), and the f15 fixture can neither exercise the cascade nor expose those follow-up
selects.

## 2. Scope — broad, not f15-specific

The tool must verify **any** multi-select turn construct the min-bound generator family emits or should emit
(`_family_win_candidates`, planner.py:294), so it retires the closed-form/real-play gap for the whole class:

- **retreat-enabler** — attach/tutor a retreat **Tool** (Air Balloon) *or* a **Switch/Scramble Switch** to
  free an Active, then promote a ready benched attacker (the deferred case).
- **energy recover/tutor** — Night Stretcher / Fighting Gong / Super Rod → the Basic Energy a KO needs
  (the applied `lethal-recover-the-energy-that-wins`).
- **evolution tutor** — Salvatore / rush-evolve onto an in-play base, then retreat-into + attack (tier 4).
- **multi-develop** — attach + retreat + promote chains; **gust** (Boss's) → KO-able last body.
- **damage-boost stacking** — Premium Power Pro / Black Belt's Training to reach a KO threshold
  (`ml_lethal_retreat_boost_to_ko_f24`).

All of these share the same untested seam: a first step whose *win* depends on `decide()` correctly driving
2–5 follow-up selects. The tool verifies the composition, not just the recognition.

## 3. Required capabilities

**A. Seed capture.** Obtain `search_begin_input` for a captured state. Two paths (build at least one):
  - **Capture-at-source (preferred):** extend the correction/replay capture (the path that writes
    `tests/fixtures/corrections/*.json`) to persist `obs["search_begin_input"]` alongside the frame, so new
    fixtures are cascade-ready. Backfill the existing lethal fixtures by re-deriving the seed (see B).
  - **Re-derive:** from a fixture's `obs["current"]` + the agent's own deck list, replay the game to that
    turn/step through `cg.api` and read back the engine's `search_begin_input` (the same blob `game.py`
    already surfaces). `tools/sim/battle.py` (full-game harness) and `tools/train/backfill_obs.py` are the
    natural homes / prior art.

**B. End-to-end line driver (the core).** Given `(obs_with_seed, first_step_or_line, pilot)`:
  - run `_engine_confirms_win`-style: `search_begin` (hidden zones from the pilot's deck) → `search_step`
    the line's own steps → then loop, calling `pilot.decide()` on each engine select, to a real verdict;
  - return `{verdict: win|lose|undetermined, steps: [...], selects: [{ctx, options, chosen, card_ids}...]}`
    — the full driven cascade, so a test asserts **the engine declares the win** AND inspects *which*
    follow-up options `decide()` picked (did it tutor Air Balloon? play it onto the Active? retreat?).
  - Honor the Solver's soundness invariants: `manual_coin=True` (an unaccounted coin → undetermined, never
    choose heads), opponent-gets-the-turn-unresolved → lose, cascade-cap → undetermined.

**C. Follow-up select probe.** A thin mode of (B) that **dumps each follow-up select's context + options**
(engine `context` enum, option encodings, resolved `card_id`/`inPlayArea`/`inPlayIndex`) reached after a
given first step — so follow-up-steering hooks (e.g. "at a Trainer-tutor `_TO_HAND`, pick a retreat Tool";
"play the Tool onto the Active") are authored against real encodings, not guessed. This is what unblocks
building the hooks the deferred proposal needs.

**D. Pytest surface.** A helper (e.g. `tests/strategy/lethal_helpers.py::engine_confirms(fixture, pilot)`)
that skips cleanly when the native lib is absent (mirror `require_kaggle_environments`) and, when present,
asserts a fixture's multi-step line **wins under the real engine cascade** — turning a closed-form-only
retest into a true end-to-end gate. Gate new planner-code lethal proposals on it.

## 4. Definition of done

1. A fixture (start with a reframed f15 — `correct` → `[0]` Play Petrel, category → missed-lethal, plus a
   captured/derived `search_begin_input`) drives the **full** line through the engine and the helper asserts
   a **win verdict** — i.e. `decide()` demonstrably tutors Air Balloon, plays it onto Makuhita, retreats,
   promotes Mega Lucario ex, and attacks. (This simultaneously **un-blocks** `lethal-retreat-enabler`: with
   the probe from (C), author the generator family + the two follow-up hooks, then this same helper is its
   gate.)
2. The helper skips (not fails) with no native lib, so the offline suite stays green cross-platform.
3. At least the applied lethal fixtures (`*_recover_energy_*`, `*_boost_to_ko_*`) are re-verified end-to-end
   (regression proof that their real-play completion — not just recognition — holds).
4. Capture path (A) writes `search_begin_input` into new correction fixtures by default.
5. Docs: a short `docs/` note + wire the helper into the blunder-buster / update-strategy `planner-code`
   gate (authoring-gates.md) so future multi-step lethal proposals are engine-verified, not closed-form-only.

## 5. Consumers / relationships

- **`/update-strategy`** `planner-code` gate (`.claude/skills/update-strategy/references/authoring-gates.md`):
  today "fixtured retest + suite-green"; upgrade to "engine-cascade-confirmed" for multi-step lines.
- **`/blunder-buster`**: emits `planner-code` proposals with a state fixture; this tool lets those fixtures
  carry the seed so their retest reflects real play.
- **Deferred proposals unblocked:** `lethal-retreat-enabler` (this handoff's trigger) and the sibling
  capability-gap `retreat-to-promote-a-disruptor` (Turn-Planner retreat→promote→item-lock generator,
  data/strategy/proposals/capability-gap-retreat-to-item-lock.md) — both are retreat-to-promote compositions
  whose follow-up steering this tool would verify.
- **Prior art:** `cg.api` search API (`search_begin`/`search_step`/`search_end`, `src/common/CONTEXT.md`
  §search-lookahead), `_engine_confirms_win` / `_simulate_line` (planner.py), `tools/sim/battle.py`,
  `tools/train/backfill_obs.py`, the arena capture (ADR-0033, [[arena-built]]). **Do not touch `src/cg/`**
  (native wrapper — project CLAUDE.md); consume its API, don't modify it.

## 6. Why deferred rather than built now (the honest reason)

The sound, *complete* fix for `lethal-retreat-enabler` needs (a) follow-up steering through the Petrel-tutor
and Air-Balloon-play selects and (b) proof that real play completes the line. (a) can't be authored grounded
without probing those selects, and (b) can't be shown by the f15 fixture (no `search_begin_input`), so both
depend on this tool. Shipping the closed-form recognition alone would pass a unit retest while real play
still (soundly) refutes and misses the win — a false-green. Building the follow-up hooks blind into the
Lethal Solver — where a phantom win *loses the game* — is the wrong risk. This tool removes both blockers
for the whole retreat/tutor/fetch class at once.
