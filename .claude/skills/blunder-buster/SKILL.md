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

So the loop is: tag corrections → `/blunder-buster` → author + verify + **commit** → tag more
(appended to the same log) → `/blunder-buster` again (prior clusters auto-drop; only the new
patterns appear). **Commit authored Hypotheses before the next round** so re-featurization sees them.

## Steps

1. **Pick a cluster.** `python tools/train/tune.py --agent <deck> [--store <path>]`, then read the
   durable snapshot it writes: **`data/proposals/<deck>.json`** (`open[]` = the `missing_hypothesis`
   proposals, each with category/episode/frame/`agent_build`; `skipped[]` = tactical/no-obs). Group
   `open` proposals by category + similar rationale into ONE pattern (e.g. the three `bad-target`
   "snipe the highest threat" corrections). Their ids are the **cluster**. (The same `tune.py` run
   also (re)writes `src/agents/<deck>/tuned.json` — the deterministic Tier-0 weight deltas; commit
   it alongside the authored Hypothesis.)

2. **Read the feature catalog** (author against the LIVE source, never memory):
   - `src/common/pilot.py` — the `Context` / `Board` fields a `when(ctx)` may read.
   - `src/cg/api.py` — `SelectContext` / `OptionType` / `AreaType` / `EnergyType` enums.
   - `src/common/cards.py` + `card_functions.json` — the function **tags**.
   - `src/common/general_strategy.py` + `src/agents/<deck>/strategy.py` — existing Hypotheses as
     **style examples** (mirror their shape).

3. **Author the candidate `when()`** from the cluster's RATIONALES (the authoring spec):
   - Prefer **universal features** (`tags`, `roles`, `board`, `stat`) over hard-coded `card_id`s.
   - Pure + total predicate; seed `weight` in-band (`docs/weights.md`); `status="assumed"`.

4. **Verify** — the gate; iterate until it passes:
   - Build the deck's Pilot (mirror `tools/train/tune.py:_build_pilot`) wrapped as
     `pilot_with(extra) -> Pilot(..., hypotheses=base + extra, ...)`.
   - Load the cluster's Corrections; call `verify(candidate, corrections, pilot_with, seeds,
     cluster)` from `train.tuner.verify`. Require `result.passed` (cluster satisfied + empty
     `regressed`). Too narrow → cluster unsatisfied (broaden); too broad → `regressed` (tighten).

5. **Suite-green.** `python -m pytest tests/ -q` — must not break Playability / existing behavior.

6. **Place + present a diff** (the human commits):
   - universal trigger → `src/common/general_strategy.py`
   - deck-specific (`roles`/`lines`/`card_id`s) → `src/agents/<deck>/strategy.py`
   - Set `status="testing"` once the Verifier passed; mark `confirmed`/`refuted` later from ladder A/B.

## Rules
- One Hypothesis per cluster, verified against **all** its members — not per-correction point-fixes.
- The Verifier is non-negotiable: **no commit without `passed`**.
- Don't invent `ctx` features — only what `Context` / `Board` expose.
