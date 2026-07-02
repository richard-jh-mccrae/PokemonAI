# Roadmap — graduating the Pilot: cheap f75 → Posture → Tier-1 Search → Self-play & Value Model

**Status:** plan (2026-06-27). Sequencing + concrete scope for the four next capability jumps past the
Tier-0 rules Pilot. Trigger-gated, not date-gated. Anchored to
[ADR-0007](../adr/0007-learning-is-one-offline-value-model.md),
[ADR-0008](../adr/0008-pilot-is-a-layered-rules-pipeline.md),
[ADR-0009](../adr/0009-training-methodology.md), [agent-architecture.md](../agent-architecture.md).

## TL;DR — the dependency chain

```
M0 cheap f75            M1 self-play PRE-FILTER     M2 Posture            M3 Tier-1 Search       M4 Value Model
(forward evo graph)  →  (cheap A/B, NOT the gate)→  (the Read → play)  →  (escalation+budget) →  (replay-trained leaf eval)
ship next round         foundational, build early   Read already built    Search API exists      heaviest, last
```

- **M1 is foundational**, not last: you cannot triage M2/M3/M4 changes without a cheap offline A/B.
  It is a **pre-filter, not the gate** — the real Kaggle ladder stays authoritative (ADR-0009 Job C);
  trust *negative* signals (drop clearly-worse configs), treat positives as hints (ADR-0021).
- **"Training via self-play" ≠ RL.** ADR-0007 rejects RL-from-scratch. Self-play is the **evaluator + on-policy
  filler + source of our own games to correct**; the **value model is supervised on mined replays**. Keep these separate.
- Two unknowns are already resolved: the **Read is built** (`src/common/scouting/`), the **Search API exists**
  (`search_begin`/`search_step`/`search_end` in `src/cg/api.py`). That de-risks M2 and M3.

## Where we are
- Tier-0 rules Pilot built end-to-end: `Score = Σ wₕ·firesₕ + tactical`, `choose_plan` SETUP→RACE, decision trace.
- Blunder pipeline working: corrections → verified Hypotheses (ADR-0015/0017/0018); `search_budget=0` ships.
- `search_budget` lives in `Strategy.params` (ADR-0019); Tier-1 telemetry reserved.

## Cross-cutting hard gates (apply to every milestone)
- **Runtime:** CPU-only, no internet, ~10 min/match, no cross-match state → **all training offline, inference cheap**.
- **Never crash/time out:** any new layer degrades to the Tier-0 legal fallback.
- **Legibility (Strategy category, ADR-0012):** rules stay the backbone; learned/searched layers are measured
  experiments kept behind the ladder, with the heuristic as fallback.

---

## M0 — Cheap f75: forward evolution-threat signal  ·  *ship in the next blunder round*

**Why now:** contained infra, needs no Posture, clears the last open correction from this round.
See [[snipe-threat-two-signals]].

**Entry:** none.

**Build** — design grilled & adversarially reviewed 2026-06-28; see [ADR-0020](../adr/0020-forward-evolution-index-is-a-provider-primitive.md) and `[[snipe-threat-two-signals]]`.
1. **Forward evolution index = provider primitive** (NOT a public `all_stats()`). Build it **inside**
   `EngineCardStatProvider`/`DictCardStatProvider` from the `{cardId: CardStat}` cache they already
   enumerate: a pure `_build_forward_index(cache)` that inverts `evolvesFrom` (a *name*) into
   `name → {descendant cardIds}`, walks multi-hop (cycle/depth-guarded), and exposes
   `forward_max_damage(card_id) -> int` = max printed damage over **descendants only** (0 if none).
   Build it in the SAME lazy `if self._cache is None` block as `.get()` (factor `_ensure_cache()`) so the
   two never diverge. **Key by name; fold MAX over all same-name printings** (154 names have >1 printing;
   Riolu=3 ids). `evolvesFrom` is `None` for Basics in the engine (not the CSV `"n/a"`); 0 orphans.
2. **New Context signal** `target_forward_damage: int | None` — set per bench-target option in
   `Pilot._context` by a `_target_forward_damage` helper cloned from `_target_energy` (guard
   DAMAGE/CARD/BENCH). **Fail-closed, coded defensively** — `_context` is NOT exception-wrapped, so the
   helper must return `None` on `stats is None`, `getattr(self.stats, 'forward_max_damage', None)` missing,
   unresolved option, or no chain. The 100 threshold is **not** applied here.
3. **New Hypothesis** `snipe-the-evolving-threat` (`src/common/strategy/baseline/baseline_snipe.py`): weight **18**,
   status `testing`, `when = select_context == DAMAGE and not target_is_threat and
   (target_forward_damage or 0) >= EVOLVING_THREAT_DMG` (=100, the tunable constant). Document in the
   rationale that `snipe-the-weakest` (15) **stacks additively** (a low-HP evolving target = 18+15).

**Files:** `scouting/provider.py`, `pilot.py` (`_context`), `general_strategy.py`, tests.
**Tests (`REQ-GEN-0022`):** index (Riolu→270; dead-end→0; branching multi-hop max; cycle terminates;
same-name MAX-fold), provider `forward_max_damage`, `_context` signal (incl. `stats=None`→None),
hypothesis (fires on Riolu-class; silent on dead-end & on `target_is_threat`; ranks evolving>weakest,
threat>evolving), a DAMAGE-context **only-intended-rules-fire** guard, and the f75 regression.
Also fix `tests/scouting/test_scouting_provider.py` fixture `evolvesFrom="Lucario"` → `"Riolu"`.
**Accept:** f75 (ep81905522) satisfied in `tune.py` (verified: margin 33>0), corpus ≥ current, suite green.
On ship, **remove** the `81905522-75` deferred entry from `data/corrections/reviewed.json`.
**Known M0 gaps (documented, not fixed):** bench-damage-immune pre-evos are wastefully sniped (no
immunity field on `CardStat` yet); affordability ignored (opponent-agnostic upper bound — M2 Read refines).
**Note:** this is the **generic** version (any deck). Opponent-*accuracy* (will they actually evolve it?) is an M2 refinement.

---

## M1 — Self-play Pre-filter: cheap offline A/B (NOT the gate)  ·  ✅ *BUILT & verified 2026-06-30*

**Status: BUILT.** The whole M1 surface ships and is tested (28 tests; smoke A/B confirmed end-to-end):
seat-balancing (`seat_plan`/`balanced_tally`/`by_seat`) + the `name@overlay.json` config overlay
(→ `AGENT_OVERLAY`, `common/config.py`) in `tools/sim/battle.py`; the Battle Result → `data/battles.jsonl`
in `tools/sim/result.py`; the M1b own-game corpus in `tools/sim/selfplay.py` ([ADR-0022](../adr/0022-selfplay-corpus-uses-cabt-env-path.md)).
A/B a config with `python tools/sim/battle.py <agent> <agent>@overlay.json`. The build notes below are
retained as the as-built record.

**Why early:** later milestones each claim "X helps"; a cheap offline A/B triages configs before spending a
scarce real-ladder submission. It is a **Pre-filter, not the gate** — the real Kaggle ladder stays
authoritative (ADR-0009 Job C). Local self-play is noisy/mirror-biased, so trust *negative* signals (drop
clearly-worse configs); a positive is only a hint. *(Grilled & measured 2026-06-28; see [ADR-0021](../adr/0021-prefilter-balances-seats.md).)*

**Entry:** a working packaged agent (have it) + the cabt engine (have it). The existing **Battle** harness
(`tools/sim/battle.py`) already runs N-match A/B in **isolated subprocesses** with Wilson CI + parallelism —
M1 **extends it**; **`tools/selfplay/` is dropped** (it would duplicate Battle and misuse "ladder", which
the glossary reserves for the real competition).

**Build** (extend `tools/sim/battle.py`)
1. **Seat-balancing [required, ADR-0021].** Play N/2 with config-A as `deck0`, N/2 as `deck1`, aggregate A's
   win-rate — else the first/second-player asymmetry (going-first can't attack turn 1; *measured* ~13pt, mirror
   37/63) swamps the config signal. A **balanced mirror's CI must contain 50%** (the fairness check).
2. **Config injection (sub-build 2): a per-contestant experiment overlay.** JSON
   `{overrides:{hyp:weight}, params:{search_budget,…}}` pointed to by an env var (mirrors `AGENT_NO_TELEMETRY`),
   read *first* by a config loader **factored into `common`** so all agents share it, falling back to `tuned.json`.
   **Inert on the grader.** A/Bs weights now and params/flags (Posture, Tier) later without a full build.
3. **Opponent = same-deck self (Q4).** Our full Pilot both seats, differing only by overlay — the opponent
   *has a brain*, so racing / bench-pressure dynamics (what the weights encode) actually arise. **Random opponents
   rejected** (no pressure → those dynamics never occur → win-rate saturates → no discrimination; kept only as a
   crash/floor check). A representative-meta **agent gauntlet** comes later, once meta decks are handcrafted into
   agents (battle.py already does agent-A-vs-B).
4. **Persist a Battle Result (output capture, [ADR-0021](../adr/0021-prefilter-balances-seats.md) amendment).** Today
   `battle.py` only *prints* a report and discards per-Match results. Append one immutable, self-describing row per run
   to a committed `data/battles.jsonl` (reuse `tools/submit/history.py`): an aggregate header (provenance, the **overlay
   measured**, `params` incl. the seat split, `tally`, win-rate + Wilson CI, `hypothesis`) + `matches[]` rows (the source
   of truth — incl. **`a_seat`** so balancing is auditable, `winner_seat`, `crashed_seats`, `end_reason`, `turns`).
   `deck_hash` per contestant; `turns` null on non-clean exits; **no `verdict`** stored (derived on read). A
   SQLite/dashboard read-path is deferred.
5. **Own-game replay corpus (M1b, sequenced after the A/B core) — grilled & revised 2026-06-29, see
   [ADR-0022](../adr/0022-selfplay-corpus-uses-cabt-env-path.md).** A new `tools/sim/selfplay.py`
   (`<agent> -n N [--overlay]`) runs **mirror self-play on the cabt-env path** (`env.run` → `env.toJSON`,
   reusing check_agent) and saves every game to `data/replays/selfplay/<stem>/<episode_id>.json`. **Why
   cabt-env, not battle.py `--save-replays`:** the Tuner needs each Correction's per-frame agent `obs`
   (`featurize` → `pilot.explain(obs)`; no-obs corrections are skipped), and `visualize_data()` lacks
   `obs` — only `env.toJSON()` carries it. The stem matches `provenance` so corrections auto-file under a
   real build folder; `EpisodeId` is globally unique (dedup/review assume it). Mirror-only until handcrafted
   opponents exist (varied-opponent corpus would need battle.py isolation + hand-captured obs — deferred).
   No inspector/Tuner changes (the Correction schema already supports self-play).

**Files:** `tools/sim/battle.py`, `src/common/` (shared config loader), `data/battles.jsonl` (committed, reuse
`tools/submit/history.py`), tests.
**Accept:** balanced mirror CI contains 50%; A/B win-rate + Wilson CI over **N≈400–800 seat-balanced** matches
(throughput ~79 games/s @8 jobs → ~10s, so cost is not a constraint at Tier-0); every run appends a **Battle Result**
to `data/battles.jsonl` with per-Match `a_seat` (balancing auditable) and the overlay-under-test captured;
`--save-replays` output loads in the blunder inspector (M1b). **Reproducibility is statistical** (no engine seed) —
the old "reproducible from a seed" criterion is **retired** (ADR-0021).
**Tests (`REQ-SIM-####`):** seat-balance aggregation + even N/2 split; config-overlay loader (env overlay merges over
`tuned.json`; absent env = today's behavior, grader-inert); report shows balanced aggregate + per-seat split;
Battle Result round-trips (write → reload → aggregates recompute from `matches[]`); `--save-replays` file parses in
the inspector (captured `visualize` sample, no live engine); smoke: tiny balanced mirror runs and returns a report.
**Risk:** match cost is negligible at Tier-0; it only bites at M3/Tier-1 (search) — measure there.

---

## M2 — Posture: wire the Read → play  ·  *grilled & scoped 2026-06-30 → [ADR-0026](../adr/0026-posture-generic-core-is-net-new-read-levers.md), [ADR-0027](../adr/0027-matchup-brief-is-hand-authored-opponent-doctrine.md)*

**Reality check (corrects "the Read is built").** The Read *code* exists
(`scouting/scout.py`,`read.py`,`scorer.py`,`matchup.py`), but no `artifact.json` was compiled/committed,
`pilot.py` never referenced the Scout, and the dossier's compiled `threats`/`targets` (the `engine` role)
were **dead data** — loaded by `artifact.py`, never read by `scout.py` (observed-only intel). So M2 is real
wiring + finishing the documented predicted-intel layer, not a plug-in.

**Entry:** M1 (to measure M2.1b). Artifact compiled+committed (gates M2.0).

**Track 1 — generic Posture core (deck-agnostic; covers all 122 archetypes).** Scoped to the Read's
*net-new* levers only — card facts already do generic seek/avoid (ADR-0026). A behavior-neutral staircase:
1. **M2.0 — wire the Read (Posture-OFF, zero decisions change).** Compile+commit `artifact.json`;
   instantiate the Scout in `main.py`; carry the Read on **`Board`** (per-decision, not `Context`); declare
   `my_archetype="Cinderace / Mega Starmie ex"`; emit the Read in the trace. Verified in isolation.
2. **M2.1a — Scout completes the predicted layer (zero decisions change).** Merge `dossiers[arch]`
   `threats`/`targets` into the Read (`seen`-flagged); Scout-level lib-free tests + trace.
3. **M2.1b — the levers (first behavior change; gates on M1).** **A** favorability — coverage-gated
   aggression↔disruption weight-band scalar, board-dominated, *no* Plan change (STABILIZE stays deferred).
   **C** accurate development — `γ`-gated modulator (both directions) on M0's forward-evo snipe (boost when
   the Read confirms the line, suppress when a recognized archetype doesn't run it, generic fallback when
   unknown). Confidence is a continuous `γ` → unknown opponent `γ→0` → no regression is structural.

**Track 2 — per-archetype Matchup Briefs (head ~8 core strategies; layered on Track 1; ADR-0027).**
Hand-authored, *objective*, shared per-archetype counterplay (gameplan, tempo, exploitable weakness) the
auto-Dossier can't derive — committed at `docs/matchups/<slug>.md` + `src/common/scouting/briefs/<slug>.json`
(beside the artifact, never inside it). Each Brief **self-declares the archetype strings it `covers`** so
variants route to one Brief. A recognized Brief populates `Board` opponent-property fields (`γ`-gated), read
by general/deck Hypotheses like the existing card-fact Posture; each agent *relativizes* it. Engine-removal
lives here. **Division of labor:** `run_meta_tracker.py` owns the meta — it ranks archetypes and exports each
one's representative `deck.csv`/`deck.txt` (reuse `_representative_build` + `render_txt`) to
`data/meta/decks/<slug>/`, incl. variant grouping. The new sibling skill **`matchup-genie`** (deck-genie
flipped to the opponent) owns no meta knowledge: the user points it at **one chosen deck**, and it dumps that
deck → counterplay research fan-out (deck + close variants) → weakness grill → gated `MATCHUP.md` →
self-describing Brief. The user walks the ranking in chunks at their own cadence, measure-and-stop; the tail
gets the generic core alone.

**Seam deferred to M3:** feed the predicted opponent deck into `search_begin` (a Tier-1 input).

**Files:** `tools/meta_tracker/` (artifact compile + deck export), `pilot.py` (Read on `Board`; levers A/C;
brief-populated opponent fields), `scouting/scout.py` (predicted layer), `scouting/briefs/`,
`agents/<deck>/strategy.py` (relativizing Hypotheses), `main.py` (Scout wiring), `docs/matchups/`.
**Accept:** M2.0/M2.1a — suite green, Read in trace, **zero decisions change**. M2.1b — M1 A/B: Posture-on ≥
off vs **recognised**; **unknown** → no regression (`γ→0`). Trace emits a one-line Posture rationale.

---

## M3 — Tier-1 Search: escalation under a budget  ·  *Search API exists; build the policy*  ·  **first slices BUILT**

**Status.** The entry trigger fired (multi-step-sequencing corrections) and the first M3 slices ship: the
**Lethal Solver** ([ADR-0030](../adr/0030-winning-this-turn-is-an-eager-engine-verified-lethal-solver.md),
the sound win-this-turn case) and the **Turn Planner**
([ADR-0031](../adr/0031-turn-planner-is-goal-directed-engine-simulated-tier1-search.md), the general
Goal-Ladder case: goal-directed candidate generation → engine-sim to end-of-turn → leaf-eval ranking,
layer-on-top). Build (2)'s "leaf eval = the Tier-0 score initially" is realized as the closed-form leaf
scalar; the **always-engine-sim** budget question is retired by the cost spike (`search_step`≈0.1 ms).
Remaining M3: the general escalation policy on *arbitrary* effectful decisions, feeding Posture's predicted
opponent deck into `search_begin`, and the Tier-1 telemetry wiring. **Two multi-turn CRITICALs are parked
here** — captured, fixtured, and characterised in
[deferred-multi-turn-criticals.md](deferred-multi-turn-criticals.md): `a21472` (multi-turn attack-sequence —
a **live gap**) needs this deep search; `b4649` (prize-race/tempo — re-measured as **already covered** by
tuned scoring) is the exemplar for the **Prize-Race Planner** and needs the M4 value model, not a lock.

**Entry trigger:** Tier-0 rules **plateau** — new corrections become "an extra ply would have caught it"
(multi-step tactical) rather than "a rule was missing." M1 ladder to validate. *(Fired 2026-07-01.)*

**Build**
1. **Escalation policy** in `pilot.py`: with `search_budget>0`, escalate to the engine Search API **only when it can
   change the decision** — effectful attacks, lethal confirmation, close-line lookahead — else stay Tier-0.
2. **Search driver** (new module) over `search_begin` → `search_step` → `search_end`/`search_release`; **leaf eval =
   the Tier-0 Pilot score initially** (the value model upgrades it in M4); feed Posture's predicted opponent deck into
   `search_begin` (M2 seam 3).
3. **Hard per-move budget** + **never-time-out** guarantee: budget exhausted → return the Tier-0 choice. Wire the
   reserved Tier-1 telemetry (tree depth / branches, ADR-0019).

**Files:** `pilot.py`, new `src/common/search/` driver, `Strategy.params.search_budget`.
**Open risk (the real one now):** **per-move search cost vs the 10-min match bank.** Measure early — how many
`search_step`s fit per move; this sets the budget and whether Tier-1 ships at all.
**Accept:** ladder A/B — Tier-1 ≥ Tier-0 on close lines; **Playability holds** (no crash/timeout) at the chosen budget.

---

## M4 — Value Model (Job B): replay-trained leaf eval  ·  *heaviest, last; plugs into M3*

**Entry:** a replay **data engine** producing labelled states (mined replays, label = eventual winner); M3 to consume
the leaf eval; M1 ladder to validate. Per ADR-0007 this is the **single learned seam**.

**Build**
1. **State-feature encoding** — the highest-leverage surface (ADR-0007). Engineered features over the observation
   (board, energy, prizes, hand size, the Read's archetype/confidence).
2. **Supervised trainer** (`tools/train/value/`, [planned]): LightGBM, `state → P(win)`. Build order
   **general → matchup-conditioned → per-deck** (3→2→1) as data justifies.
3. **Loader + consumption** (`src/common/value/`, [planned]): load once at import; consume as the **Search leaf eval**
   (M3) and a **tiebreaker** in the Score layer. Heuristic stays the fallback.

**Files:** `tools/train/value/`, `src/common/value/`, hook in `pilot.py` + the M3 driver.
**Open:** feature encoding; replay volume for matchup/per-deck tiers; **inference within budget** (same constraint that
rejected card2vec — the model must run cheap at grader time).
**Accept:** ladder A/B — value-on ≥ heuristic-only; inference within the per-move budget; clean fallback when the model
is absent.

---

## Decision log
- **DE-RISKED:** engine Search API exists (`cg/api.py search_begin/step/end`); the Read *code* is built
  (`scouting/`) — though M2 grilling found it **unwired** (no compiled artifact, Scout absent from `pilot.py`,
  predicted-intel layer incomplete; corrected in [ADR-0026](../adr/0026-posture-generic-core-is-net-new-read-levers.md)).
- **RESOLVED (M1, grilled 2026-06-28 → [ADR-0021](../adr/0021-prefilter-balances-seats.md)):** M1 is a *pre-filter,
  not the gate*; **extend `tools/sim/battle.py`** (drop `tools/selfplay/`); **seat-balancing is required** (measured
  ~13pt first/second skew; engine has **no seed** → reproducibility is statistical); config via an **env-var experiment
  overlay** factored into `common`; opponent = **same-deck self** now (gauntlet later; random rejected); own-game
  taggable replays via `--save-replays`/`visualize_data()` (M1b), not the cabt-env path.
- **RESOLVED (M2, grilled 2026-06-30 → [ADR-0026](../adr/0026-posture-generic-core-is-net-new-read-levers.md),
  [ADR-0027](../adr/0027-matchup-brief-is-hand-authored-opponent-doctrine.md)):** the generic Posture core is scoped
  to the Read's *net-new* levers — **A** favorability (board-dominated weight-band, no Plan change) + **C** `γ`-gated
  accurate-development modulator on M0; generic seek/avoid stays card-fact; STABILIZE deferred. Wiring is a
  behavior-neutral staircase (M2.0 Read→`Board` → M2.1a Scout predicted layer → M2.1b levers). Per-archetype
  counterplay is a hand-authored, shared **Matchup Brief** (≠ the auto-Dossier), produced by a new **`matchup-genie`**
  skill and consumed via `Board` opponent-property fields; engine-removal lives there.
- **FOUND (separate blunder):** the Pilot has no `IS_FIRST` handler → it always elects to go first (the worse side),
  a ~13pt self-inflicted loss; tracked for `/blunder-buster`.
- **OPEN (resolve early, cheap to check):** per-move Tier-1 cost (M3); value-model feature encoding + replay volume (M4).
- **REJECTED (ADR-0007):** RL / self-play as the primary trainer; neural policy / learned card embeddings.

## References
- ADRs: [0003](../adr/0003-scouting-knowledge-is-a-shipped-artifact.md) (the Read is a shipped artifact),
  [0007](../adr/0007-learning-is-one-offline-value-model.md) (one value model),
  [0008](../adr/0008-pilot-is-a-layered-rules-pipeline.md) (layers + Posture + search_budget),
  [0009](../adr/0009-training-methodology.md) (three training jobs), [0019](../adr/0019-submissions-are-traceable-and-tracked.md).
- Docs: [agent-architecture.md](../agent-architecture.md), [scouting.md](../scouting.md),
  [general-strategy.md](../general-strategy.md), [tuning/methodology.md](../tuning/methodology.md).
- Memory: `snipe-threat-two-signals`, `agent-decision-architecture`, `kaggle-execution-model`, `card2vec-rejected`.
