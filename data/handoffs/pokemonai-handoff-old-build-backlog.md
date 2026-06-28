# Handoff — PokemonAI blunder-busting: close out the old-build 11-correction backlog

**Repo:** `C:\Users\Richard\Projects\PokemonAI`  **Agent:** `mega_starmie` (Kaggle Pokémon TCG, Strategy category)
**Date of handoff:** 2026-06-28. **Focus of next session:** finish the last thread from this conversation —
reconcile + close the 11 old-build corrections, then return to the normal tagging loop.

## TL;DR of where we are
- A large blunder-busting round on build `mega_starmie_20260627_93a70be` is **done and verified**:
  the "attack-last → tiered turn-sequencer" rebuild + sub-clusters. Real-Pilot corpus **43/57**
  active correct (21 baseline), **0 regressions, 422 tests pass**, adversarial-reviewed.
- The new build is **100% reconciled** (every correction fixed / `covered` / `deferred`).
- User **submitted agent #4** (the improved agent). Git: the **user is the commit gate** — assume
  this session committed nothing; do not commit/push unless asked.
- We just ran a real-Pilot **smoke-test of the 11 leftover OLD-build corrections** (the
  `bde590c`/`dirty` backlog). Result + the one pending action are below.

## The immediate pending action (this is the whole job)
The 11 old-build corrections were counted "satisfied" by prior rounds' **additive W-route** but the
real Pilot never picked the human's option (see memory [[old-build-real-pilot-backlog]] and the
methodology caveat). I triaged all 11 through the live agent: **in every one the agent now *develops*
(Evolve/Play/Attach) — none attacks or ends early.** So there are no genuine current blunders; it's
within-turn ordering (resolves same turn) plus two already-deferred nuances.

**Pending: the user was asked "ledger the 11 and close the backlog?" and ran /handoff instead — so
this is unconfirmed. Confirm, then execute this disposition** (via `python tools/train/review_correction.py <ep>-<frame> <disp> "<reason>"`):

- **`covered` (8) — agent develops the right thing, different first action, same turn:**
  `81785223-32`, `81785223-38`, `81785223-44` (Evolve Mega before Pokégear) ·
  `81903490-27`, `81904451-6` (Buddy-Poffin/bench-fill before attach) ·
  `81904064-29`, `81905522-47` (Evolve Mega before Lillie's / attach) ·
  `81904064-59` (digs, different draw card; RACE tie)
- **`deferred` (3) — already-known Tier-1 / hand-eval families, no new rule earns its keep:**
  `81903490-49` (Ignition-vs-basic attach — the f25 Ignition-discipline family) ·
  `81903490-74` (Salvatore-rush-evolve vs evolve-manually) ·
  `81904451-50` (Salvatore vs Hilda — tutor-priority)
  *(Note `81904451-6`'s underlying concern is also Ignition-vs-basic; I called the agent-pick soft so
  it's in `covered`, but it's borderline — fine to leave covered.)*

After ledgering: update memory `old-build-real-pilot-backlog.md` from "11 unreconciled" → "reconciled:
all soft-ordering or deferred-family; none a current blunder." Then re-run `python tools/train/tune.py
--agent mega_starmie` to confirm nothing new surfaces.

## Then: the normal loop (only after the user wants it)
`commit this round → tag blunders on the #4 ladder games → /blunder-buster → repeat.` Tag the **new
build's** games (live signal), not old ones. Do NOT grind old builds further.

## Key artifacts — read these, don't re-derive
- **Round report (full narrative of the round + every rule):**
  `docs/tuning/runs/mega_starmie_20260628-170304.md`
- **Method + the critical caveat** (additive W-route ≠ real `decide()`; real Pilot/Verifier is
  authoritative): `docs/tuning/methodology.md` (section 2 blockquote).
- **Reviewed ledger** (set-asides; 29 entries): `data/corrections/reviewed.json`; CLI
  `tools/train/review_correction.py` (`--list`, `--remove`).
- **Memory** (`C:\Users\Richard\.claude\projects\C--Users-Richard-Projects-PokemonAI\memory\`):
  `MEMORY.md` index; esp. `attack-is-turn-ender-develop-first.md`, `promote-after-ko-priority.md`,
  `old-build-real-pilot-backlog.md`, `reviewed-ledger.md`, `forgo-ko-corrections-are-refuted.md`.
- **The rules live in:** `src/common/general_strategy.py` + `src/common/pilot.py`
  (`_finish_turn_last` = the tiered sequencer: tier0 informative dev → tier1 energy attach → tier2
  turn-ending attack). Deck rules: `src/agents/mega_starmie/strategy.py`.

## How to verify a correction the authoritative way (real Pilot, not the tuner)
A reusable script already exists:
`C:\Users\Richard\AppData\Local\Temp\claude\C--Users-Richard-Projects-PokemonAI\a102d401-e22b-4c3f-9fe7-02c0249c46ae\scratchpad\baseline_check.py`
— builds the real `mega_starmie` Pilot, runs `decide()` on every active correction's embedded obs,
prints `review_key -> correct?`. Pattern to reuse: build the Pilot exactly as `tools/train/tune.py:_build_pilot`,
then `set(c.correct) <= set(pilot.decide(c.obs))`. Run pytest with `python -m pytest tests/ -q`
(set `PYTHONIOENCODING=utf-8` for the `→`/curly chars on Windows).

## Standing constraints (carry these)
- **Caveman-lite** chat (~75%), every turn. End every response with a status line (one of
  `Done - Still grilling` / `Grilling Done` / `Done - Still implementing` / `Implementing Done`).
- **User is the commit gate** — don't commit/push unless asked. Never touch the Kaggle token
  (`kaggle_api_token/`, gitignored).
- **Authoritative fix-measure is the real Pilot `decide()` / the Verifier**, not the tuner's W-route
  (it over-reports both ways; e.g. it still PROPOSES f31/f19 which are verified fixed).
- Windows + Linux both first-class (`pathlib`, `encoding="utf-8"`). Python docstrings Google style.

## Suggested skills
- **`blunder-buster`** — the skill for this whole workflow (clustering, the Verifier gate, the
  reviewed ledger, the round report). Invoke it when starting the next tagging round on #4's games.
  Its step 10 (record set-asides) is exactly the ledgering action pending above.
- (Not `deck-genie` — that's for authoring a deck's doctrine from scratch, not relevant here.)
