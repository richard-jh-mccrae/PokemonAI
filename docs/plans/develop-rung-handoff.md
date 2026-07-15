# Develop Rung — Handoff (2026-07-16)

Self-contained pickup doc for the **within-turn develop-rollout planner** work. Read this first, then
the two design docs it points to. Companion plans: [turn-planner-develop-rung.md](turn-planner-develop-rung.md)
(the rung + phases + leaf lab) and [phase3-tooling.md](phase3-tooling.md) (the correction→retirement tooling).

## TL;DR

The develop rung is **built (Phases 0–3), armed-ON, and playing setup turns badly** ("almost drunk",
user). The root cause is the one the plan always named: **its end-of-turn LEAF is blind.** The offline
measurement bench (the "leaf lab") is built and gives the baseline — **the leaf ranks the human's intended
pick highest 0 / 2 times.** The next real work is **enriching the leaf against the lab** (then an ML value
net if hand-tuning plateaus). The rung stays **armed** on purpose, to harvest labeled leaf-failure data.

## What the rung is (30-second recap)

The Turn Planner (`plan_turn`, `src/common/strategy/planner.py`) only committed KO/win lines; setup turns
fell to greedy per-frame scoring. The **develop rung** is the deferred bottom rung: on a develop turn
where no higher rung fires **and** greedy is weak/indifferent (`_develop_should_fire`), it rolls out each
candidate first action to its end-of-MY-turn board (`_simulate_line` re-runs the policy to turn end; **no
opponent model**) and commits the option whose board scores highest under `_engine_leaf_value`. It is
armed behind the `develop_rollout` PROFILE flag (**currently ON**).

## Status by phase

| Phase | State | Notes |
|---|---|---|
| 0 — leaf | **enriched but never validated** | `_board_development` credits wincon bodies/energy. The correction-board proof was *deferred to the ladder* — the unfinished bottleneck. |
| 1 — rung | **built** | `_develop_rollout_line`; telemetry `Decision.plan_candidates` + `planned.value`; soundness guard (defers on `KO_SCORE`-class rollout values). |
| 2 — cost/ladder | **armed-ON, shipped** | Cost affordable (~1s/game, 0 crashes/60 games). `develop_rollout: True` in PROFILE; the armed-ON build is submitted (on `main`). |
| 3 — retire whack-a-mole | **capture + consumer built** | `turn_plan` capture + `classify_develop_correction`/`develop_batch_report`. First batch: **0 retire candidates**, 1 cross-turn over-fire. |
| Leaf lab | **built** | Offline leaf measurement via cgpy. **Baseline: leaf ranks `correct` highest 0/2, avg top-tie 2.5.** |

## The diagnosis: why it plays "drunk"

On a develop turn there is no prize/KO, so `_engine_leaf_value` collapses to essentially one term:
`_board_development` ≈ `10·bodies + 5·energy` (+ small wincon credits). That has **no notion of tempo,
holding a resource, sequencing, or cross-turn payoff** — so the rung maximizes "play more stuff" and
**cannot even break ties.** Measured on a real board (`ep86090164`): options 1–4 all score **65** (a
4-way tie), the human's `correct=[0]` scores 60 → ranked **5th of 8**. On another (`correct=[1]`) the
leaf hallucinates a **1075** ("win" from the heuristic sim) and ranks it #1. Blind + degenerate = drunk.

A good develop-turn leaf **is** the parked value-function problem (ADR-0042 learned leaf, shelved at
−0.55%; ADR-0053 ML value net, not started). The closed-form leaf was never going to rank setup boards
well, and the cross-turn reasoning the corrections cite ("evolve *next turn*") is impossible closed-form.

## Decisions in force (user, 2026-07-16)

1. **Keep the rung ARMED.** Ladder loss is a non-issue; armed-ON games capture `plan_candidates` = the
   leaf's per-option values, so every tagged turn is a labeled leaf-failure/preference example (the
   training + diagnosis corpus). `_DEVELOP_PLAN_K` was raised 3→50 so the **full** menu ranking is
   captured (the human's later `correct` pick is always in the trace with its value).
2. **Harness first, then the leaf.** The leaf lab (measurement bench) is built. Improve the leaf measured
   on it; escalate to the ML value net only if hand-tuning plateaus. Both are wanted — the lab is the
   *bench*, the ML net is the high-ceiling *payload*.
3. **No gate change off n=1.** The cross-turn over-fire is a single observation; act on a *pattern*, not
   one case. `_DEVELOP_STRONG_SCORE`/`_DEVELOP_TIE_MARGIN` are the knobs when it's real.

## Tools — how to run them

- **Tag turn-planner corrections:** `python tools/train/blunder_correction.py <replay|dir> --team <team>`
  — at **turn** scope, fill *Intended line* + *Expected end-board*; `correct` = the first divergent
  option; the shell shows "your pick currently fires: [rules]" (auto-derived, don't type it).
- **Measure the leaf:** `python tools/train/leaf_lab.py [--agent <deck>]` — re-scores every tagged
  `turn_plan` board offline via cgpy and prints `leaf ranks correct highest: X/Y` + per-correction rank
  and top-tie. **This is the loop for leaf enrichment** — change the leaf, re-run, watch the number move.
- **Route corrections:** `/blunder-buster` — a `scope: turn` + `turn_plan` correction is classified by
  `develop_class` (rung-right / leaf-misrank / rung-inactive) per `references/routing.md`.

## Next steps (priority order)

1. **Enrich the leaf**, measured on the lab. First jobs: (a) **break the ties** — `_board_development`
   needs features that discriminate setup boards (wincon-line completeness, evolution readiness,
   energy-on-attacker vs wasted, bench composition), (b) keep the **phantom `KO_SCORE` sim-wins** from
   dominating the develop leaf (the soundness guard already makes the *rung* defer on them, but the lab
   shows the leaf still emits 1075 — decide whether to clamp them in `_board_development` scoring). Target:
   move `leaf_correct_rate` off 0/2 and shrink `avg_top_tie`.
2. **Grow the corpus** — keep tagging `turn_plan` corrections on armed-ON games.
3. **ML value net (ADR-0053)** if hand-tuning plateaus — the lab validates it the same way.
4. **Phase-3 retirement** only becomes viable once the leaf produces *rung-right* cases (the rung
   reproducing a tuned rule's pick); until then `retire_corroboration` stays empty by design.

## Gotchas — don't relearn these the hard way

- **The rung is only as good as the leaf.** Shipping a rollout on a blind leaf produces drunk play — the
  plan warned this in bold. The leaf is the whole game.
- **`_search_api` seam** (`_simulate_line`): `pilot._search_api` injects an alternate engine (the lab sets
  `cgpy.compat.api`); absent → native. Production is unchanged.
- **Offline reseeding:** inject a placeholder `search_begin_input` so `_simulate_line`'s gate passes; cgpy
  then rebuilds state from the **MAIN-select** board. Non-MAIN / unreseedable boards are skipped+counted.
- **cgpy is parity-limited (~298/434):** its leaf *values* differ slightly from native — **trust the
  ranking, not the absolute value** ([[cgpy-standalone-engine]]).
- **`plan_candidates` exists only on armed-ON games** (needs the live search token). The 335 recorded
  corrections lack the token → the **lab is the only offline leaf-eval path**; you cannot re-derive a new
  leaf's ranking from a recorded correction without cgpy.
- **The Catch-22 (Phase 3):** a strong scoring rule makes greedy look confident → suppresses the rung on
  that rule's own decisions → subsumption can't be pre-proven from telemetry. Nominate retire-candidates
  by *charter*, confirm on the batched R-off ladder run.
- **`train.tuner.retest.retest()` returns a dict** (`r["fixed"]`), not an object.
- **`tune.py` clobbers `tuned.json`** — keep it out of batch commits.

## Where things live

- **Rung + leaf:** `src/common/strategy/planner.py` — `_develop_rollout_line`, `_develop_should_fire`,
  `_board_development`, `_engine_leaf_value`, `_simulate_line` (+ `_search_api` seam); constants
  `_DEVELOP_PLAN_K` / `_DEVELOP_STRONG_SCORE` / `_DEVELOP_TIE_MARGIN` / `_PLANNER_WINCON_*`.
- **Telemetry:** `src/common/telemetry.py` + `src/common/pilot.py` (`Decision.plan_candidates`).
- **Phase-3 consumer:** `tools/train/tuner/develop.py` (`classify_develop_correction`,
  `develop_batch_report`); wired onto `ProposedHypothesis.develop_class` in `tools/train/tuner/propose.py`.
- **Leaf lab:** `tools/train/leaf_lab.py`.
- **Capture:** `tools/train/blunder/correction.py` (`turn_plan`), `shell.py`, `service.py`.
- **Skill:** `.claude/skills/blunder-buster/references/routing.md` (develop-rung rulebook);
  `.claude/skills/update-strategy/references/strategy_proposal_contract.md` (`rule-retirement` layer).
- **Tests:** `tests/strategy/test_develop_rollout_*.py`, `tests/strategy/test_leaf_development.py`,
  `tests/tuner/test_develop_analysis.py`, `tests/tuner/test_leaf_lab.py`, `tests/blunder/test_blunder_turn_plan.py`.

## Branches / PRs

- **`claude/phase3-consumer`** (this branch) — Phase-3 consumer + leaf lab + this handoff → **PR #103**.
- **Merged:** #102 (develop rung Phases 0–3 + `turn_plan` capture). `main` also carries the armed-ON
  submission and the dragapult turn_plan corrections this handoff analyses.

## Related memory / ADRs

[[turn-planner-develop-rung]] · [[phase3-tooling-develop-rung]] · [[leaf-lab-develop-rung]] ·
[[blunder-buster-planner-aware]] · [[value-model-needs-nonmirror-gauntlet]] · [[ml-build-plan-adr-0053]] ·
[[gauntlet-invalid-ladder-only]] · [[cgpy-standalone-engine]]. ADRs: 0031 (Turn Planner), 0042 (value
model, parked), 0053 (ML training), 0059 (cgpy).
