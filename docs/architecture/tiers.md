# The decision architecture — tier vocabulary and what actually decides

The T0–T6 names are used throughout the code and ADRs; this file is the only place they are defined.
It carries **no %-complete marks**: those were the reason the six per-tier docs rotted and were
deleted (they described the 2026-07-05 rung ladder, which POC-T4/5 replaced at MAIN). The owning ADR
is the record for every decision below; `common.runtime.PROFILE` is the authority on what is armed.

## What decides a MAIN single-pick frame

`PlannerMixin.plan_turn` (`src/common/strategy/planning/turn_line.py`), top rung first — the first
rung to return a line wins:

| # | rung | owner |
|---|---|---|
| 1 | `_win_line` — the Lethal Solver's **sound** lock; never enters ranking | ADR-0030 |
| 2 | `_closed_form_candidates` → `_commit_best` — KO-for-prizes, and KO-the-key-threat | ADR-0037 |
| 3 | `_best_gamble_line` — closed-form expectimax over outcome classes | ADR-0039 |
| 4 | `_composer_line` — **the MAIN decider**: scores a whole turn by differencing end states, `state_value(end) + terminal_ev`. Unflagged and ungated | ADR-0092, ADR-0131 |

Every **other** context (search, snipe, mulligan, multi-select) and any MAIN frame all four decline
defers to the tuned rung scoring — T0 below, which is why it is still the universal fallback.

## The tier names

| Tier | Name | Owner | State |
|---|---|---|---|
| T0 | Rules & Tuned Scoring | ADR-0008, ADR-0012 | live — fallback for every context above |
| T1 | Turn Planner | ADR-0031, ADR-0037 | live |
| T2 | Chance & EV (Gamble Lines) | ADR-0039 | live, `gamble_lines` |
| T3 | Match Objectives (KO Race, Prize Path) | ADR-0040 | live, `objectives_race/_path/_phases` |
| T4 | Opponent Model | ADR-0047 | live, `opp_resource_reads` |
| T5 | Automatic Value Model | ADR-0042 | **built, parked OFF** (`value_model`) — paired-delta A/B regressed −0.55%, CI [−1.27, +0.16] |
| T6 | Escalation Search | ADR-0043 | **deleted** 2026-07-17 (ADR-0064 decision 6). `search_budget` survives as a telemetry label; there is no switch |

Sound rungs are never overridden by a learned or searched seam, which is why parking T5 costs
nothing. The boundary of the differencing thesis is ADR-0131: a decider must not decide what its own
numbers say it has no view on — `sound_rules` keeps the orderings no function of the end state can
separate.
