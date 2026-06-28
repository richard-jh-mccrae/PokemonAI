---
name: blunder-buster
description: Bust a round of blunder corrections into verified Strategy improvements. Reads the correction log, clusters the missing_hypothesis blunders, authors a general when() trigger per cluster, gates each with the deterministic Verifier, and presents diffs to commit. Invoke as /blunder-buster [corrections.jsonl] (defaults to data/corrections/corrections.jsonl). Use after a round of manual blunder tagging (ADR-0018).
---

# blunder-buster — corrections → verified Strategy improvements

Convert a **round** of blunder Corrections into committed agent improvements. The **Verifier** is
the accuracy gate; the human commits. Never write executable `when()` code into a Strategy without
the Verifier passing **and** human review. See `docs/blunder-tuner.md`, ADR-0017, ADR-0018.

**Invocation:** `/blunder-buster [path/to/corrections.jsonl]` — omit the path to use the main log
(`data/corrections/corrections.jsonl`).

## Rounds & reconciliation (read this first)

There is **one append-only log**; you don't manage per-round files. Each run re-featurizes the
**whole** log against the **current** Strategy, so reconciliation is automatic:

- A blunder you addressed last round is no longer `missing_hypothesis` — the Hypothesis you
  committed now fires on it, so it drops out (becomes weight-tunable or already satisfied).
- Only **still-uncovered** blunders surface as new `missing_hypothesis` clusters.

**The reviewed ledger — don't re-assess what you set aside.** Auto-reconciliation only drops a
blunder once a rule *satisfies* it. A blunder you assessed and **consciously set aside** —
`refuted` (a bad correction, e.g. it forgoes a Knock Out), `deferred` (valid but needs new infra),
or `covered` (already handled) — would otherwise resurface every run. Record those in
`data/corrections/reviewed.json` (step 10); `tune.py` then excludes them from `open[]` /
`UNSATISFIED` and lists them under `reviewed (excluded)` — so each round you only see **new** work.

So the loop is: tag corrections → `/blunder-buster` → author + verify + **commit** + **record
set-asides** → tag more (appended to the same log) → `/blunder-buster` again (prior clusters
auto-drop; reviewed ones stay excluded; only the new patterns appear). **Commit authored
Hypotheses before the next round** so re-featurization sees them.

## Steps

1. **Pick a cluster.** `python tools/train/tune.py --agent <deck> [--store <path>]`, then read the
   durable snapshot it writes: **`data/proposals/<deck>.json`** (`open[]` = the `missing_hypothesis`
   proposals, each with category/episode/frame/`agent_build`; `skipped[]` = tactical/no-obs). Group
   `open` proposals by category + similar rationale into ONE pattern (e.g. the three `bad-target`
   "snipe the highest threat" corrections). Their ids are the **cluster**. (The same `tune.py` run
   also (re)writes `src/agents/<deck>/tuned.json` — the deterministic Tier-0 weight deltas; commit
   it alongside the authored Hypothesis.)
   - **Also mine the `UNSATISFIED` lines** `tune.py` prints: these are *W-route* corrections whose
     `correct ≻ chosen` the weight fit could **not** honour (a conflict between corrections, or a gap
     no existing Hypothesis discriminates). They are prime **H** candidates — treat them like `open`
     proposals and cluster them too. A `tuned.json` of `{}` is normal and honest: it means the round's
     leverage is entirely in new rules, not reweighting (the fit ships weights only when they satisfy
     strictly more corrections than the seeds; lower `--reg` only if you *want* clean corrections to
     move weights more aggressively — the ladder is the real gate).

2. **See how the agent actually decided** (the live trace, ADR-0019). Each Correction may embed
   `live_trace` — the `@T` Decision Telemetry the **shipped** agent emitted at that exact decision
   (`opts[].score / tac / fired:[[hyp_id, weight]]`, `chosen`, `margin`). Read it per cluster member
   to ground authoring in the agent's *real* reasoning: which hypotheses fired on the chosen vs the
   correct option, and by what margin. (If `live_trace` is null, run
   `python tools/train/backfill_obs.py` once the game's `episode-<id>-agent-<seat>-logs.json` is
   collected, or rely on the obs re-derivation.)

3. **Read the feature catalog** (author against the LIVE source, never memory):
   - `src/common/pilot.py` — the `Context` / `Board` fields a `when(ctx)` may read.
   - `src/cg/api.py` — `SelectContext` / `OptionType` / `AreaType` / `EnergyType` enums.
   - `src/common/cards.py` + `card_functions.json` — the function **tags**.
   - `src/common/general_strategy.py` + `src/agents/<deck>/strategy.py` — existing Hypotheses as
     **style examples** (mirror their shape).

4. **Author the candidate `when()`** from the cluster's RATIONALES (the authoring spec):
   - Prefer **universal features** (`tags`, `roles`, `board`, `stat`) over hard-coded `card_id`s.
   - Pure + total predicate; seed `weight` in-band (`docs/weights.md`); `status="assumed"`.

5. **Verify** — the gate; iterate until it passes:
   - Build the deck's Pilot (mirror `tools/train/tune.py:_build_pilot`) wrapped as
     `pilot_with(extra) -> Pilot(..., hypotheses=base + extra, ...)`.
   - Load the cluster's Corrections; call `verify(candidate, corrections, pilot_with, seeds,
     cluster)` from `train.tuner.verify`. Require `result.passed` (cluster satisfied + empty
     `regressed`). Too narrow → cluster unsatisfied (broaden); too broad → `regressed` (tighten).

6. **Retest — "see the log after the fix"** (ADR-0019, closes the loop). For each cluster member,
   `retest(correction, pilot_with([candidate]))` from `train.tuner.retest` re-derives the decision
   in the **same `@T` format** as the live log and diffs it against the embedded `live_trace`:
   show `chosen_before → chosen_after`, `margin_before → margin_after`, and require `fixed` (the
   `correct` option is now chosen). This is the before/after proof the blunder is addressed.

7. **Suite-green.** `python -m pytest tests/ -q` — must not break Playability / existing behavior.

8. **Place + present a diff** (the human commits):
   - universal trigger → `src/common/general_strategy.py`
   - deck-specific (`roles`/`lines`/`card_id`s) → `src/agents/<deck>/strategy.py`
   - Set `status="testing"` once the Verifier passed; mark `confirmed`/`refuted` later from ladder A/B.

9. **Write the run report** (the human-readable record + showcase). Step 1's `tune.py` already wrote
   `docs/tuning/runs/<deck>_<timestamp>.md` (what was tuned/why/how much, proposals, unsatisfied) —
   it prints `report -> <path>`. **Append** to that same file an `## Authored this round` section: for
   each Hypothesis you committed, a bullet with its id, the cluster it fixes, the rationale, the seed
   weight + band, and the **retest before/after** from step 6 (`chosen_before → after`,
   `margin_before → after`, `fixed`). This is the per-run learning/progress artifact; keep it succinct
   and explain *why*, not just *what*. The math itself lives once in `docs/tuning/methodology.md` —
   link it, don't re-explain it.

10. **Record what you set aside** (so it never resurfaces). For every `open` proposal / `UNSATISFIED`
    correction you assessed but did **not** author a rule for, record a disposition in the reviewed
    ledger — `python tools/train/review_correction.py <episode>-<frame> <disposition> "<reason>"`:
    - `refuted` — a bad correction (e.g. it forgoes a **KO** / a high-value attack; `tactical ≈ 1000`).
      Also dropped from the weight fit so the bad label stops pressuring weights. (See
      [[forgo-ko-corrections-are-refuted]].)
    - `deferred` — valid but needs new infrastructure (a new `Context` signal); note what's missing.
    - `covered` — already handled by an existing Hypothesis; name it.
    Next `tune.py` run excludes them (shown under `reviewed (excluded)`), so the next round only
    surfaces genuinely new patterns.

## Rules
- One Hypothesis per cluster, verified against **all** its members — not per-correction point-fixes.
- The Verifier is non-negotiable: **no commit without `passed`**.
- Don't invent `ctx` features — only what `Context` / `Board` expose.
- **If you change how tuning works, update the explainer.** Any change to the method itself — the fit
  objective/optimiser, attribution (W vs H), the regularisation/`reg`, the pocket, the adoption gate,
  the verifier/retest — must be reflected in `docs/tuning/methodology.md` (the graded, educational
  write-up) in the same change. Keep the math there in sync with `tools/train/tuner/`.
