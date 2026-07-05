# ADR-0043: Escalation Search is a budgeted depth-2 tree on a close attack tie

**Status.** Accepted + **Built 2026-07-05** (`/tdd`, Tier 6). The narrowly-triggered engine tree for
the one thing closed-form provably cannot see — **opponent choice**. Build record:
[docs/architecture/tier-6-escalation-search.md](../architecture/tier-6-escalation-search.md).

**Context.** Tiers 0-3 are opponent-*static*: the KO Race, Incoming, and the Prize Path all assume
the opponent's board answers as it stands. But two attacks can price identically this turn and leave
very different boards after the opponent's best REPLY (a retreat, a heal, a gust, a counter-attack).
The roadmap reserved a Tier-1 engine tree for exactly this; ADR-0040 then demoted it from "the
multi-turn answer" (the KO Race owns opponent-static multi-turn) to the **residue handler**: only the
opponent-choice-dominated case remains. The 10-min match bank makes an always-on tree the dominant
cost risk, so the tier must be narrow and budget-bounded.

**Decision.** A **budgeted depth-2 tree, triggered only on a close attack tie**, with the tuned pick
as the guaranteed fallback (`planner.py`, kill-switch `escalation`, needs `search_budget > 0`).

1. **Trigger** (`_close_attack_tie`): fire only when the top ATTACK options are within
   `_ESCALATE_EPS` tactical points of each other — the race tie closed-form can't separate. A clear
   leader, a lone attack, or a KO on the menu (KO_SCORE-class) all short-circuit to no escalation, so
   only genuinely ambiguous attack picks pay the engine.
2. **Depth-2 evaluation** (`_two_ply_value` over `_simulate_line(opponent_reply=True)`): sim each
   tied attack through MY turn AND the opponent's reply — continuing the engine steps through the
   opponent's turn using **our own policy as the reply proxy** (better than random; the same
   competent policy self-play already uses) — until it is my turn again, then read the leaf (the
   Base Value Model when present, else the closed-form scalar). An opponent-reply WIN scores −KO_SCORE
   (the worst outcome), so escalation actively avoids the attack that hands them the game.
3. **Commit conservatively**: the best two-ply attack commits ONLY if it strictly beats the tuned
   tie-pick's own two-ply value; otherwise defer. Escalation never overturns a clear tuned pick — it
   breaks a tie the tuned layer flagged as close.
4. **Hard per-move budget + never-time-out**: every reply step decrements `_search_steps`, capped at
   `search_budget`; on exhaustion the sim halts and the tuned pick stands. Engine absent / any slip →
   None → tuned scoring decides. **Default OFF** (like the value model — a search seam ships only
   after its own ladder A/B at a measured budget).

**Rejected.**
- **Always-on shallow search** on every MAIN decision: pays the prediction-poisoned opponent model on
  every move, multiplies per-decision cost against the 10-min bank, and mostly re-derives what the
  closed-form tiers already know. Worst cost/benefit.
- **Dropping the tier entirely**: leaves boards where the wall can retreat/heal/gust out of the
  KO-Race math permanently mispriced, with no mechanism to ever catch them.
- **A real opponent-deck model at the reply node** (vs our-policy proxy): needs the Read's predicted
  deck driven through a separate strategy — heavier, and prediction-poisoned the same way; the
  our-policy proxy is the cheap, competent first cut (the value model refines the leaf regardless).

**Consequences.** `_simulate_line` gains an `opponent_reply` mode (the Tier-1 path is byte-identical
when off). The trigger keeps the tree off plain boards (cost stays zero there). A committed
escalation rides telemetry under `goal="escalation"`. Deeper trees (depth 3+), a real opponent-deck
reply model, and a favorability-scaled budget are future refinements gated on this tier's first A/B.
