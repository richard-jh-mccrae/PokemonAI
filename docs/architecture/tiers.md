# Final Architecture — the Tier Map

**Status:** accepted design (grilled 2026-07-05, `/grill-with-docs`). One doc per tier, each with a
%-complete mark. Decisions recorded in
[ADR-0039](../adr/0039-gamble-lines-are-closed-form-expectimax-over-outcome-classes.md) and
[ADR-0040](../adr/0040-match-judgment-is-per-turn-closed-form-objectives.md); new glossary terms
(*Chance Node, Outcome Class, Gamble Line, KO Race, Prize Path, Path Denial*) in
[src/common/CONTEXT.md](../../src/common/CONTEXT.md). **Supersedes**
[roadmap-search-posture-learning.md](../todo/roadmap-search-posture-learning.md) as the architecture
reference (that file stays as M0–M4 milestone history).

> **Convention & executable twin.** This map follows the locked
> [naming convention](../naming-convention.md) — dotted sub-tiers `T<n>.<m>`, the word "tier"
> reserved for runtime decision layers, and a mandatory status tag on every node. The **executable
> twin** of this map is [`src/common/tiers.py`](../../src/common/tiers.py): the machine-readable
> Tier Map kept in sync with this doc, in which **each `PROFILE` kill-switch is pinned to exactly one
> tier node** (`tests/common/test_tiers.py` fails if a switch is left unplaced). Read that file for
> the authoritative sub-tier names, numbers, and per-node flags/status.

## Thesis

The strongest consistent pilot is NOT a W/L-trained policy — W/L stays the **gate** (M1 A/B +
ladder), Corrections stay the **teacher**, and match-scale judgment is **computed, not learned**:

- every turn ends in the best *reachable* end-of-turn board (Tier 1, built);
- stochastic actions are priced by **exact** expectation, not vibes or thresholds (Tier 2);
- every turn carries match-scale intent: a live **Prize Path** in both directions and a **KO Race**
  read — "force them to take 7 prizes", "KO 2 Megas or snipe 3 smalls" become arithmetic (Tier 3);
- the not-yet-visible opponent enters only γ-gated through the Read (Tier 4);
- one supervised model refines leaf *judgment* only (Tier 5); a narrow engine tree handles the
  opponent-choice residue closed-form provably cannot (Tier 6).

Rules stay the backbone (ADR-0008/0012 legibility gate); every tier degrades to the tier below;
nothing may crash or time out (~10 min/match, CPU-only, offline).

## The map

```
T4 Opponent Model — Read γ-overlay + Matchup Briefs
        │ predicted bodies/attackers (γ-gated)
        ▼
T3 Match Objectives — Prize Path (both sides) · Path Denial · KO Race · derived phases
        │ conditions goals, targets, promote/bench, weight bands — re-derived every turn
        ▼
T1 Turn Planner — Goal Ladder: sound win rung › heuristic lines › T2 Gamble Lines
        │ leaf-eval (closed-form now, T5 when trained)      ▲ exact odds
        ▼                                                   │
T0 Rules & Tuned Scoring ◄──────────────────────── T2 Chance/EV (closed-form expectimax)
   (fallback for every tier; scores non-MAIN contexts)
T5 Automatic Value Model — leaf refinement; features = T3/T4 primitives
T6 Escalation Search — trigger: KO-Race tie / opponent-choice boards; hard budget
```

## Tiers & completion

| Tier | Doc | % | One line |
|---|---|---|---|
| 0 | [Rules & Tuned Scoring](tier-0-rules-and-scoring.md) | **90%** | Hypotheses + Tactical + compendium, corrections-tuned — the backbone and universal fallback |
| 1 | [Turn Planner](tier-1-turn-planner.md) | **88%** | Rank reachable end-of-turn boards; sound Lethal top rung + the Gamble rung — built, ON |
| 2 | [Chance & EV](tier-2-chance-ev.md) | **70%** | Gamble Lines BUILT 2026-07-05 (A/B 52%, CI 50–54): exact-odds refresh-first KO gambles + coin-EV ranking |
| 3 | [Match Objectives](tier-3-match-objectives.md) | **75%** | BUILT 2026-07-05: KO Race (a21472 green), two-sided Prize Path + denial, derived phases, gate-ban migration |
| 4 | [Opponent Model](tier-4-opponent-model.md) | **70%** | Levers + Briefs shipped (main); the γ-continuous predicted-attacker overlay into T3 BUILT 2026-07-05 |
| 5 | [Automatic Value Model](tier-5-value-model.md) | **`built, gated:off`** | BUILT 2026-07-05 (ADR-0042); cross-deck gauntlet A/B **regressed −0.55%** (CI [−1.27,+0.16], 6 matchups, 0 crashes) → **parked OFF** (features redundant with the closed-form leaf; matchup-conditioned model is the real unlock) |
| 6 | [Escalation Search](tier-6-escalation-search.md) | **`built, gated:off`** | BUILT 2026-07-05 (ADR-0043); attack-tie trigger inert (0/646) + density trigger fires but A/B **regressed to 44%** (PR #39) → **parked OFF** (two-ply proxy loses to the tuned scorer) |

## Sub-tiers (the dotted map)

Dotted sub-tier numbering per the [naming convention](../naming-convention.md), mirroring
[`src/common/tiers.py`](../../src/common/tiers.py) (the authoritative names/numbers/status). A
written reference expands both names, e.g. *T4.2 - Opponent Model, Posture*. Tier-level %-complete
marks live in the table above; sub-tiers carry only a status tag.

| Sub-tier | Status |
|---|---|
| **T1.1 - Turn Planner, Win Rung (Lethal Solver)** | `built` |
| **T1.2 - Turn Planner, KO the Key Threat** | `built` |
| **T1.3 - Turn Planner, KO for Prizes** | `built` |
| **T1.4 - Turn Planner, Stabilize-then-KO** | `built` (structural) |
| **T1.5 - Turn Planner, Develop** | `built` |
| **T3.1 - Match Objectives, Prize Path (+ Denial)** | `built` |
| **T3.2 - Match Objectives, KO Race** | `built` |
| **T3.3 - Match Objectives, Derived Phases** | `built` |
| **T4.1 - Opponent Model, Read** | `built` |
| **T4.2 - Opponent Model, Posture** | `built` |
| **T4.3 - Opponent Model, Matchup Briefs** | `built` |
| **T4.4 - Opponent Model, Learned Matchup Weights** | `grilled, unbuilt` |
| **T6.1 - Escalation Search, Two-ply search** | `built, gated:off` |
| **T6.2 - Escalation Search, Sampled-Belief Search** | `unbuilt (research)` |

(T0, T2, T5 are flat — no sub-tiers.)

## Build order (recommended)

1. **T3 core** — KO Race + Prize Path enumerator: unblocks the live `a21472` blunder, powers phases
   and denial; everything else consumes its primitives.
2. **T2** — Gamble Lines (the Lillie's class: whether + sequencing).
3. **T4 overlay** — γ-gated predicted bodies into T3's their-side (+ levers A/C).
4. **T3 phases** — derive STABILIZE/CLOSE once race/path signals exist.
5. **T5** — value model (its features ARE T3/T4 outputs; building it earlier starves it).
6. **T6** — escalation policy last (its trigger needs T3's tie signal; its leaf wants T5).

Every step ships behind the M1 A/B pre-filter + real-ladder gate (ADR-0009/0021); every step
degrades cleanly to the tier below it.

**Build status (2026-07-05):** all seven tiers have running implementations. **T0–T4 default ON**
(A/Bs 50–52%, 0 crashes) — the shipped agent. **T5 and T6 are built but PARKED DEFAULT OFF, each on
its own A/B evidence** (the grilled flip-**or-park** definition of done):
- **T5** (ADR-0042): the pipeline bug that zeroed favorability in training was found + fixed
  (`_build_pilot` dropped the Read); retrained on a 92k-state cross-deck gauntlet (favorability now
  live); the paired-delta A/B still **regressed −0.55%** → parked. Its features are largely redundant
  with the closed-form leaf the tuned tiers already score; the matchup-conditioned model is the real
  unlock.
- **T6** (ADR-0043): the close-attack-tie trigger is structurally inert for our decks (0/646
  decisions); the added opponent-disruption-density trigger (PR #39) fires but its A/B **regressed to
  44%** → parked. The two-ply our-policy proxy systematically loses to the tuned scorer.

The learned/searched seams never override a sound rung by design, so parking them costs nothing — the
closed-form tiers are the agent. Both stay behind their kill-switches for the deferred unlocks
(matchup-conditioned value model; a real opponent-deck reply model + commit-margin gate for escalation).
