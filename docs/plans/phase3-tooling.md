# Phase 3 tooling — turn-planner corrections → rule retirement

**Status: DESIGNED + capture + consume BUILT 2026-07-15 (test-first). First armed-ON batch (4 dragapult
turn_plan corrections) classified — see "First batch" below. Proof loop (batched R-off ladder) is
maintainer-run.** Phase 3 of the develop rung
([turn-planner-develop-rung.md](turn-planner-develop-rung.md)): retire the per-frame whack-a-mole
scoring rules the develop rollout rung has proven it subsumes. This doc is the grilled design for the
two tools that drive it: the correction-tagging capture (`tools/train/blunder_correction.py` + shell)
and the `blunder-buster` consumption skill.

## The two asks (user, 2026-07-15)

1. Make it **easiest** to record a turn-planner suggestion — an ideal decision sequence + reasoning.
2. Make it **most efficient** for `blunder-buster` to pick those up and drive Phase 3's rule retirement.

## Grilled constraints (why the design is shaped this way)

- **The counterfactual-board wall.** Only the **first divergent** decision has a valid, replayable
  option index. Past it, the ideal line runs through boards the replay never visited (the recorded span
  frames are the agent's *wrong* continuation). `retest_span` stops at first divergence for this reason.
  → the human captures the first pick + prose; the **rung's rollout** supplies sequence validation.
- **`plan_candidates` is the consumption unlock — new games only.** An armed-ON develop decision now
  emits the ranking (committed / greedy / per-candidate value / `diverged`). blunder-buster reads it
  instead of NLP-ing prose. But the 104 legacy sequencing corrections carry none — Phase-3 evidence is
  **armed-ON-era corrections only**; the tagging loop fills the set.
- **The Catch-22.** These rules are `+weight` Hypotheses in the general scoring layer
  (`concentrate-energy-on-wincon: 16.0`, …). The develop rung is planner-code that **preempts scoring**,
  and its gate (`_develop_should_fire`) fires only when greedy is **weak/indifferent**. A strong R makes
  greedy look confident → **suppresses the rung on exactly R's own decisions** → no `plan_candidates`
  there. So subsumption **cannot be pre-proven** from armed-ON-with-R-on telemetry; it is only observable
  once R is turned **off**.

## Capture — `blunder_correction.py` / shell / `Correction` (ask #1)

- **`Correction` += one sparse field** `turn_plan: dict | None = None` = `{intended_line,
  expected_end_board}`. Backward-compatible, auto-serialized (`asdict`); `build_correction` gains a
  `turn_plan=None` param; `record_correction` threads it (via `**identity`).
- **Shell shows two textareas only when `scope: turn`** — *Intended line* (your sequence, prose) and
  *Expected end-board* (what it sets up — the leaf's target). `correct` stays the single first-divergent
  index.
- **`leans_on_rule` is never typed.** On picking `correct`, the shell reads `opts[correct].fired` from
  the embedded live trace and shows *"your pick currently fires: [rules]"*. Derived at consume-time from
  `fired`, never stored (so it can't drift).

## First batch (2026-07-15) — what the consumer found

4 `turn_plan` corrections (all dragapult_ex), classified by `develop_batch_report`:
`{leaf-misrank: 1, rung-inactive: 1, no-prescription: 2}`, **retire_corroboration: `{}` (zero
retirements)**, capability_gaps: 1. The one rung-fired case (`ep86090164`, `correct=[0]`) is the rung
**overriding a correct greedy pick** (committed a supporter at leaf 65 over the human's attach at 50) on
a **cross-turn** board ("save Lillie's — evolve Dunsparce *next turn*") — the within-turn leaf can't see
that horizon. Verdict: **capability-gap + gate concern (`overrode_greedy: true`)**, not retirement fodder.
The honest first-batch signal: refine the leaf/gate (and the augment-not-override threshold) before
retiring anything; the rung's first ladder outing shows it can over-fire on cross-turn setups.

## Consume — `blunder-buster` (ask #2) — BUILT 2026-07-15 (test-first)

Code: `tools/train/tuner/develop.py` — `classify_develop_correction` (per-correction verdict) +
`develop_batch_report` (aggregate: counts, `retire_corroboration` by rule, `leaf_tune`,
`capability_gaps`); wired onto `ProposedHypothesis.develop_class`. Skill: `references/routing.md`
develop-rung rulebook; `strategy_proposal_contract.md` gains the `rule-retirement` target_layer.
Design (unchanged):

- **New routing branch:** `scope: turn` + `turn_plan` present → read `live_trace.plan_candidates` and
  classify: committed == `correct` → **rung-right**; `correct` present, lower value → **leaf mis-rank**
  (Phase-0 leaf fodder, `expected_end_board` vs `plan_candidates[correct].value` is the diagnosis);
  `correct` absent → **gate didn't fire** (threshold fodder); `plan_candidates` absent → **skip**.
- **Retire-candidates nominated by CHARTER,** not subsumption telemetry (the Catch-22 blocks it): R is a
  candidate when its charter ⊆ the rung's within-turn-development mandate (judged from R's
  `when()`/rationale/intent), AND R's domain does **not** extend to KO/lethal turns (else **demote**,
  i.e. narrow its `when()`, not retire).
- **Join** clusters nominated candidates → `rule-retirement` proposals.

## Proof — the loop (ask #2 tail)

- **Batch-all R-off + rung-on → ONE ladder submission** (candidate weights zeroed in the committed
  `tuned.json`; the grader ignores `AGENT_OVERLAY`). A genuinely-subsumed R makes retirement net
  **neutral-to-positive**, so: neutral/positive delta confirms the whole batch in one submission;
  **only a regression triggers a bisect** (split the batch, resubmit).
- **`/update-strategy` applies** via a new `target_layer: rule-retirement` (remove the Hypothesis
  definition + its `tuned.json` weight, ledgered, `verification_contract: seed-ladder`). A cross-skill
  dependency — the one piece outside the two named tools.

## The Phase-3 loop

ship armed-ON (Phase 2) → tag `turn` corrections with `turn_plan` → blunder-buster classifies via
`plan_candidates` + nominates retire-candidates by charter → batch-all R-off ladder submission →
neutral/positive confirms (else bisect) → `/update-strategy` removes the confirmed rules.

## Build sequencing

The **capture** half is the critical path — it must exist before the armed-ON games can be tagged — so
it is built now (test-first). The **consume/proof** half is specced but waits for the dataset (turn
corrections carrying `plan_candidates`), which only exists after the Phase-2 armed-ON submission ladders.

Related: [[turn-planner-develop-rung]] · [[blunder-buster-planner-aware]] · [[gauntlet-invalid-ladder-only]]
