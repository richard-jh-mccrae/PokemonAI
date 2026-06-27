# Roadmap — graduating the Pilot: cheap f75 → Posture → Tier-1 Search → Self-play & Value Model

**Status:** plan (2026-06-27). Sequencing + concrete scope for the four next capability jumps past the
Tier-0 rules Pilot. Trigger-gated, not date-gated. Anchored to
[ADR-0007](../adr/0007-learning-is-one-offline-value-model.md),
[ADR-0008](../adr/0008-pilot-is-a-layered-rules-pipeline.md),
[ADR-0009](../adr/0009-training-methodology.md), [agent-architecture.md](../agent-architecture.md).

## TL;DR — the dependency chain

```
M0 cheap f75            M1 self-play LADDER        M2 Posture            M3 Tier-1 Search       M4 Value Model
(forward evo graph)  →  (evaluator + A/B gate)  →  (the Read → play)  →  (escalation+budget) →  (replay-trained leaf eval)
ship next round         foundational, build early   Read already built    Search API exists      heaviest, last
```

- **M1 is foundational**, not last: you cannot validate M2/M3/M4 without a ladder A/B gate (ADR-0009 Job C).
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

**Build**
1. **Forward evolution index.** `CardStat` exposes `stage` + `evolvesFrom` (pre-evo *name*) but no forward map.
   Build `name → [cards whose evolvesFrom == name]`, walk multi-hop (Riolu→Lucario→Mega Lucario), read the
   eventual form's `maxDamage`. **Load-bearing prerequisite:** the stat provider must **enumerate all cards**
   (today it's lookup-by-id) — add an `all_stats()` / iteration path to `src/common/scouting/provider.py`.
2. **New Context signal** `target_evolves_into_attacker: bool` — set per bench-target option in `Pilot._context`
   (parallel to `target_energy`), true when the targeted Basic's forward chain reaches a high-`maxDamage` form.
3. **New Hypothesis** `snipe-the-evolving-threat` (general, `src/common/general_strategy.py`): fires at
   `select_context == DAMAGE` when `target_evolves_into_attacker` and the target carries no Energy (the
   energy case is already `snipe-the-threat`).

**Files:** `scouting/provider.py`, `pilot.py` (`_context`), `general_strategy.py`, tests.
**Tests:** `REQ-GEN-####` — fires on Riolu-class target, not on a bare dead-end Basic; no double-count with `snipe-the-threat`.
**Accept:** f75 (ep81905522) satisfied in `tune.py`, corpus ≥ current, suite green. Document the `maxDamage` threshold choice.
**Note:** this is the **generic** version (any deck). Opponent-*accuracy* (will they actually evolve it?) is an M2 refinement.

---

## M1 — Self-play ladder: the evaluator / A/B gate  ·  *foundational, build before M2–M4*

**Why early:** every later milestone claims "X helps" — only a ladder win-rate can confirm it (ADR-0009 Job C).
Self-play is **not** a trainer here; it is the evaluator + a source of our own games to feed the blunder inspector.

**Entry:** a working packaged agent (have it) + the cabt engine (have it; `tools/sim/check_agent.py` already self-matches).

**Build** (`tools/selfplay/`, [planned] in the layout)
1. **Ladder runner** `ladder.py A B -n N`: run N offline self-matches config-A vs config-B on the pinned engine,
   report win-rate + Wilson CI. Deterministic seeds (pass seeds in; no `Date.now`/RNG in the harness).
2. **Config = a Strategy + overrides + `search_budget`** (so it A/Bs weights, Posture-on/off, Tier-0 vs Tier-1).
   Reuse the Playability harness from `tools/sim/check_agent.py`.
3. **On-policy correction source:** dump our own games as replays the blunder inspector can tag (closes the
   ADR-0009 "own-Pilot blunder-correction — the gold signal" loop).

**Files:** `tools/selfplay/ladder.py`, small reuse of `tools/sim/`.
**Accept:** `python tools/selfplay/ladder.py mega_starmie-default mega_starmie-tuned -n 200` → stable win-rate + CI;
reproducible from a seed; emits taggable game logs.
**Risk:** match cost — keep N modest, parallelize across cores offline (training-time only, not grader).

---

## M2 — Posture: wire the Read → play (+ accurate f75)  ·  *the Read is built; this is wiring*

**Entry:** M1 (to measure). The Read already exists (`scouting/scout.py`,`read.py`,`scorer.py`,`matchup.py`).

**Build** — the three seams from [ADR-0008](../adr/0008-pilot-is-a-layered-rules-pipeline.md), **all confidence-gated**
(unknown opponent → Posture ≈ off; recognised → ramps):
1. **Generic core** in the Pilot: seek the Read's `targets`, avoid its `threats`, calibrate aggression to
   favourability. Deck-agnostic, free for every deck. Carry the Read on `Context`.
2. **Deck-specific Read-conditioned Hypotheses** in `agents/<deck>/strategy.py`.
3. **Feed the predicted opponent deck into `search_begin`** — *defer the wiring to M3* (it's a Tier-1 input).

**Accurate f75 (the refinement):** the Read names the opponent Archetype → whether Riolu→Mega Lucario is a real line
*in this matchup* → upgrade M0's generic signal with Read confidence (gate up when recognised, fall back to the
generic graph when unknown).

**Files:** `pilot.py` (Context carries Read; Posture core), `general_strategy.py`, `agents/<deck>/strategy.py`,
scouting wiring at `main.py`.
**Accept:** ladder A/B (M1) — Posture-on ≥ Posture-off vs **recognised** opponents; **unknown** opponent → no regression
(Posture ≈ off). Decision trace still emits a one-line rationale (legibility).

---

## M3 — Tier-1 Search: escalation under a budget  ·  *Search API exists; build the policy*

**Entry trigger:** Tier-0 rules **plateau** — new corrections become "an extra ply would have caught it"
(multi-step tactical) rather than "a rule was missing." M1 ladder to validate.

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
- **DE-RISKED:** engine Search API exists (`cg/api.py search_begin/step/end`); the Read is built (`scouting/`).
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
