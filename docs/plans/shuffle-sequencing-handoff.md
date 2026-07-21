# Shuffle "sequencing residuals" — handoff (2026-07-21)

Follow-up to the shuffling-value-equation session (PR #124, branch
`claude/shuffling-value-equation-c1z0na`). During that session's verification pass, a refresh-corpus
probe flagged **6 "sequencing" frames** ("attach energy / fetch a body *before* shuffling") as
residual disagreements. This handoff records the **decision-level re-check**, which overturns that:
**there is no open sequencing thread.** It also documents the measurement caveat that produced the
false alarm, and routes the two genuine residuals to their real owners.

## TL;DR

- The refresh-grill probe measures the **isolated `_refresh_swing_tactical` term**, not the agent's
  decision. A positive isolated shuffle swing does NOT mean the agent shuffles — other hypotheses
  (attach-first, `refresh_shuffles_deferred_fetch`, deploy/fetch endorsement) rank the free action
  above the refresh.
- Re-checked at the **decision level** (does `pilot.explain(obs).chosen` match the human's `correct`
  index): **8 of the 10 flagged residuals already match the human exactly**; a 9th avoids the shuffle
  but picks a different non-shuffle action.
- **All 6 "sequencing" frames are already correct** — the live agent attaches/fetches first. No
  sequencer work is needed from the shuffle line.
- Only **1** frame is a real decision-level shuffle miss, and it is **not** sequencing — it is a
  lethal/prize-math frame (below).

## Decision-level evidence (current committed code, `f0dabc2`)

| frame | chosen now | human correct | match | correct action |
|---|---|---|---|---|
| 81905063-10 | [2] | [2] | ✅ | Play Buddy-Buddy Poffin (fetch bodies first) |
| 82523164-11 | [2] | [2] | ✅ | Attach {W} → Cinderace (attach first) |
| 82525101-69 | [2] | [2] | ✅ | Attach {W} → Mega Starmie (attach first) |
| 82525101-87 | [1] | [1] | ✅ | Attach {W} → Mega Starmie (attach first) |
| 82525741-77 | [0] | [0] | ✅ | Attach {W} → Mega Starmie (attach first) |
| 86090147-20 | [4] | [4] | ✅ | Play Poké Pad (fetch a body first) |
| 83117367-34 | [2] | [2] | ✅ | Play Harlequin |
| 83969481-55 (f55) | [4] | [4] | ✅ | Attack with Jetting Blow |
| 82522698-36 | [2] | [5] | ⚠️ | Attach {W} → Mega Starmie — agent avoids the shuffle, picks a different non-shuffle action |
| 83664991-43 | [1] | [3] | ❌ | Attack with Turbo Flare — agent plays Lillie's instead |

Example scores (why the "sequencing" frames are fine): at 82525101-69 the attach options score
**35.0 / 25.0** while the refresh plays score **−34.6**; at 82523164-11 the attaches score **18.0**
and the refresh plays **−50.3**. The agent already does the free action first.

## The two genuine residuals — NOT sequencing, NOT this session's scope

- **82522698-36** — a dominating Mega-vs-Mega mirror with two clutch Wally's Compassion. The agent
  correctly does **not** shuffle (avoids the Harlequin blunder) but picks a different non-shuffle
  action than the human's ideal attach-to-bench. The gap is **clutch-heal / attach-target valuation**,
  owned by the **parallel healing-value session** (already noted there). Not a shuffle miss.
- **83664991-43** — the agent plays Lillie's when the human's correct action is **Attack with Turbo
  Flare** for prize math. This is the one real decision-level case where a refresh is chosen over a
  better line, and it is a **lethal / objectives** concern (the winning/prize-optimal attack must
  out-score the refresh), owned by that layer — not the shuffle-value equation.

## Methodological caveat (for future refresh grills)

`tools/train/probes/needs_sweep.py` and the ad-hoc refresh-grill probe report `swing_v1` /
`swing_v2` / `swing_v2_cyc` — the **isolated** shuffle term. That is the right lens for the
**promotion** question (v1 vs v2 shed pricing), but the **wrong** lens for "does the agent blunder."
For a decision-level verdict, compare `pilot.explain(obs).chosen` against the correction's `correct`
indices (as this handoff does). A positive isolated shuffle swing on a frame the human ruled
"don't shuffle" is expected and benign when the human's correction is "do a free action first" — the
sequencer/other hypotheses carry that decision, and they already do.

## Bottom line

No sequencing follow-up is owed by the shuffle line. The shuffle-value equation is clean at the
decision level across the corpus; the only two decision-level residuals belong to the healing-value
session (82522698-36) and the lethal/objectives layer (83664991-43).
