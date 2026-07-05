# Final Architecture — the Tier Map

**Status:** accepted design (grilled 2026-07-05, `/grill-with-docs`). One doc per tier, each with a
%-complete mark. Decisions recorded in
[ADR-0039](../adr/0039-gamble-lines-are-closed-form-expectimax-over-outcome-classes.md) and
[ADR-0040](../adr/0040-match-judgment-is-per-turn-closed-form-objectives.md); new glossary terms
(*Chance Node, Outcome Class, Gamble Line, KO Race, Prize Path, Path Denial*) in
[src/common/CONTEXT.md](../../src/common/CONTEXT.md). **Supersedes**
[roadmap-search-posture-learning.md](../todo/roadmap-search-posture-learning.md) as the architecture
reference (that file stays as M0–M4 milestone history).

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
T5 Value Model — leaf refinement; features = T3/T4 primitives
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
| 5 | [Value Model](tier-5-value-model.md) | **5%** | One supervised P(win) leaf over T3/T4 features — the single learned seam |
| 6 | [Escalation Search](tier-6-escalation-search.md) | **10%** | Narrowly-triggered budgeted engine tree for opponent-choice residue |

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
