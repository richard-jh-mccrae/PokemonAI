---
name: blunder-buster
description: Diagnose and correct Bellman decision blunders from one or more correction JSON records.
disable-model-invocation: true
---

# Blunder Buster

Run only when the user invokes `/blunder-buster` with one or more paths under
`data/corrections/`.

## Triage

1. Read every supplied correction record before changing code. For each, extract the board,
   offered menu, expected decision, observed decision, and stated rationale.
2. Make a compact grouped inventory: correction path -> decision kind -> shared board/value
   pattern -> provisional classification. Group similar patterns before selecting a fix.
3. Classify every correction as exactly one of:
   - **new machinery**: the Bellman model lacks a general state, transition, uncertainty, or value
     term needed to express the decision;
   - **tuning**: existing machinery has the needed terms but their arithmetic, scale, or interaction
     is wrong.

Completion: every supplied correction is classified and similar patterns are grouped.

## Bellman repair loop

Work through corrections one at a time, using the inventory to reuse a general repair when it
explains a group.

1. Trace the correction through `src/common`: state extraction, legal transition construction,
   value families, continuation, uncertainty handling, and root choice. Read the relevant tests
   and docs/ADRs before editing.
2. Derive the missing or misweighted board-state parameter and express the repair as a general
   Bellman equation change. Keep the model deck-neutral and card-neutral: terms describe state,
   action, transition, or uncertainty, never a named card, correction, or one-off scenario.
3. Implement only the general model change. Preserve the distinction between observed facts,
   inferred beliefs, and unknown information.
4. Add one focused regression under `tests/corrections/` for this correction. The test must build
   the recorded state (or the smallest faithful projection), assert the corrected decision/value
   relation, and fail before the repair.
5. Run that correction test and the closest affected Bellman tests. If a grouped repair resolves
   several corrections, add a separate regression for each and run all of them.

Completion: each correction has a passing regression and its expected decision follows from a
general Bellman model change.

## Boundaries

- Treat `src/common` as a Bellman system throughout: value comes from explicit state-value terms,
  transition outcomes, continuation, and uncertainty—not bespoke policy branches.
- Do not add named-card functions, correction-specific conditionals, scenario recognizers, or
  special-case action selection. Refactor any encountered niche logic toward general state/value
  machinery when it is in the edited path.
- Ask the user before proceeding when card text, a game rule, or scenario semantics are uncertain.
  Do not infer missing mechanics.
- If no sound repair exists within the Bellman constraints, stop before implementing an exception.
  Explain the evidence, why the equation cannot represent it, and propose the smallest alternative;
  ask the user to choose.

## Final verification

After all supplied corrections pass individually:

1. Run `python -m pytest tests/corrections/ -q` and the affected Bellman suite. Resolve every
   regression before continuing.
2. Run a serial 10-game mirror match of the repaired agent. Time every agent callback and every
   match with a generic harness measurement; if none exists, add reusable nonproduction timing
   instrumentation rather than timing a named-card path. Report average/minimum/maximum decision
   time and average/minimum/maximum match time, including the exact command and build or
   working-tree target used.
3. Report the inventory, new-machinery versus tuning outcomes, equation-level changes, test paths,
   verification results, and timing summary.

Completion: every supplied correction regression passes, the full correction suite passes, and the
10-game mirror timing summary is reported.
