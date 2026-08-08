# ADR-0039: Gamble Lines are closed-form expectimax over Outcome Classes

**Status.** Accepted (grilled 2026-07-05, `/grill-with-docs`). **Built 2026-07-05 (`/tdd`)**: the
Gamble rung (`planner._best_gamble_line`, switch `gamble_lines`) + `deck_odds.draw_hit_probability`
+ the type-payable attach fix + coin-EV ranking; gated REQ-GAMBLE-0001..0005; A/B **52%**
(CI 50–54, 0 crashes, 2000 games, Battle Result #58) → **default ON**. Build record:
[docs/architecture/tiers.md](../architecture/tiers.md) (T2). Terms in
[src/common/CONTEXT.md](../../src/common/CONTEXT.md): *Chance Node*, *Outcome Class*, *Gamble Line*.

**Context.** The Turn Planner (ADR-0031/0037) is deterministic: `_simulate_line` auto-resolves
coins and no candidate line reasons through a stochastic action. So the Pilot cannot weigh the
canonical decision class: Mega Starmie ex Active with 0 Energy, hand = Lillie's Determination
(*shuffle hand into deck, draw 6*) + Ignition Energy (*{C}{C}{C}, discard at end of turn*),
opponent Water-weak. Attach-Ignition→Lillie's→Nebula (●●● 210, ignores Weakness, energy evaporates)
is safe; Lillie's-FIRST gambles the Ignition into the deck for a chance at a {W} Basic → Jetting
Blow = 240 with Weakness + 50 snipe + a persisting energy. Choosing needs expectation over the
draw. Two facts constrain the mechanism: (1) the Engine Search fork instantiates ONE predicted
ordering of hidden zones — simming through a chance node yields a *sample*, and the glossary's
prediction-invariance rule already declares such verdicts untrusted; (2) my own deck's composition
is EXACTLY known (decklist − seen, prize uncertainty hypergeometric — deck tracker + ADR-0029), so
draw/fetch probabilities are computable in closed form, no sampling needed.

**Decision.** Stochastic actions are planned as **Gamble Lines**: a Turn Line containing exactly
ONE **Chance Node**, branching into **Outcome Classes** (macro-partitions sharing one best
follow-up — "≥1 {W} Basic among the 6" / "Ignition redrawn, no {W}" / "neither" — never raw
permutations), each class weighted by exact tracker hypergeometrics and valued closed-form (max
over legal follow-ups, the compendium's damage/development math). Line value = the EV; Gamble Lines
compete on the Goal Ladder against deterministic lines by that EV. Constraints:

1. **Sound math is untouchable** — the win rung preempts every gamble; Lethal/Incoming stay
   worst-case; EV never enters them (the glossary's Damage-Formula avoid-note stands).
2. **Depth-1** — one Chance Node per line; a line needing two gambles is not generated (budget +
   compounding-error guard).
3. **Break-even is EV equality** — never a fixed probability threshold ("P > 50%" is wrong: the
   payoffs are asymmetric and board-dependent).
4. **v1 scope**: Hand-Refresh supporters (whether + sequencing — upgrades ADR-0024's deferred
   pull-EV), fetch hit/whiff EV (upgrades the flat `dont-search-a-probable-whiff`), coin-attack EV
   for heuristic RANKING only.
5. Own-side only: opponent hidden zones are the Read's territory (γ-gated overlay, ADR-0026/0040),
   never a Chance Node.

**Rejected.**
- **Monte-Carlo determinizations through the engine** (sample K orderings, sim, average): K× sim
  cost per candidate, ranking noise at affordable K, prediction-poisoned by construction, and the
  trace degrades to "sampled 20 futures" — illegible. Exact closed-form probabilities are available;
  sampling would be strictly worse.
- **Score-layer EV terms as the primary mechanism** (flat tuned pull-EV on the option): cannot
  discover conditional sequencing — "Lillie's first, then attach whichever energy arrives" — which
  is the point of the capability. Kept only as the fallback tier for non-MAIN contexts where the
  planner never runs.
- **Opponent-side stochastics in scope**: no exact tracker exists for their zones; including them
  would poison exact probabilities with guesses.

**Consequences.** The trace prints each Outcome Class with its probability and branch value plus
the EV-vs-deterministic comparison (writeup-grade legibility, ADR-0012). The deck tracker becomes a
hard dependency of planning (already match-scoped). Corrections can now target gamble judgment
(wrong class partition / wrong branch value) instead of being forced into weight noise. ADR-0024's
"pull-EV deferred" is discharged here.
