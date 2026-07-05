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
   Automatic Value Model when present, else the closed-form scalar). An opponent-reply WIN scores −KO_SCORE
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

## Amendment — the opponent-disruption-DENSITY trigger (2026-07-05)

**Context.** A firing diagnostic showed the close-attack-tie trigger is structurally near-unreachable
for our decks: **0 escalations committed over 646 real mega_starmie decisions**, because ≥2
simultaneously-affordable attacks on the Active occur on only 0 / 0.3 / 1.5 % of MAIN menus for
mega_starmie / mega_lucario / dragapult_ex. The tier was effectively inert. The Consequences above named
the fix — "an opponent-choice-dominated board (disruption / gust / heal density flagged from Function
Tags + Brief)" — as a deferred refinement; this amendment builds it.

**Decision.** A **second trigger** feeds the same budgeted depth-2 tree. `_escalate` is now a
dispatcher: attack-tie first, then — when it yields no candidates — the **density trigger**, firing on
board TEXTURE rather than on 2+ affordable attacks. Both share `_commit_escalation` (sim two-ply,
commit only on strict improvement over the tuned pick, budget-guarded, tuned pick the fallback).

1. **Signal — generic, from Function Tags + the Read** (`_opp_disruption_density`; Fork A, human-picked
   over an authored-brief field). A weighted count of the opponent's `_DISRUPT_TAGS`
   (`gust`/`switch`/`heal`/`hand_disruption`/`energy_denial`, verified in `card_functions.json`)
   capability: the opponent's REVEALED cards (active/bench/discard) at full weight (certain) plus the
   Read's Representative-Build predictions (`expected_cards`) at `gamma * inclusion_prob` — the
   Brief-gated hidden-deck signal (the matched Brief participates through the gamma-gated Read; **no
   brief-schema change**). `_density_dominated` fires at `_ESCALATE_DENSITY` (2.0). Keeps the tier
   deck-agnostic, matching its generic-residue-handler identity.
2. **Candidate set — raw top-K** (`_top_k_candidates`, K=`_ESCALATE_TOPK`=3; Fork B, human-picked over a
   narrower attack-vs-develop pair). The top-K options by tactical, NOT filtered to positive scores: a
   disruption-dense board is exactly where the opponent-static tactical ranking is unreliable, so the
   two-ply **strict-improvement commit gate** — not a tactical-sign filter — is what protects a weak
   line. Gated to a combat-relevant board (an affordable attack must be on the menu) with the same
   KO-on-menu short-circuit (a KO dominates — escalation never talks us out of it). *Override
   justification differs from attack-tie:* not tie-closeness but board-texture unreliability — yet the
   commit is equally conservative (the tuned pick is evaluated on the same two-ply footing and only a
   strictly-better line overrides).

**Rejected (Fork A alternative).** An **authored per-archetype brief hazard field**: legible and
matchup-genie-owned, but a schema + 4-brief + verification blast radius, and largely redundant with the
Read (which already encodes the archetype). Kept as a future opt-in override (tier-6 doc, Gap #3).

**Evidence.** Firing diagnostic (6 mirror games/deck): density flags 66 / 33 / 66 % of MAIN decisions as
dense and **commits** 42 / 33 / 63 strict-two-ply overrides per 6 games (mega_starmie / dragapult_ex /
mega_lucario) — it fires AND changes play, the unlock the attack-tie trigger lacked. The default-OFF
corpus retest is unchanged (`_escalate` returns at its first guard when off). Gated REQ-ESCALATE-0006/
0007/0009 (unit — signal, gating, and the commit gate pinned with stubbed two-ply values) + 0008
(engine, density fires on real boards + the seam holds). The live *commit* is trajectory-dependent
(Linux CI can see 0 over the 4 games Windows commits several), so it is unit-pinned + diagnostic-measured,
never asserted as a live count.

**A/B — REGRESSES; kept DEFAULT OFF (2026-07-05).** mega_starmie mirror, escalation ON (`search_budget`
400) vs OFF, 1000 games: **ON 44 % (95 % CI 41-47 %), 0 crashes** — a clean ~12-point regression, both
seats < 50 %. The trigger works mechanically (fires + commits) but its two-ply overrides *systematically
lose* to the tuned scorer, so the density trigger **does NOT flip ON**; it stays built, gated, and
DEFAULT OFF (like the value model / `brief_engine` — a search seam ships only after a passing A/B, and
this one failed). **Root-cause read** (not yet isolated): the leaf that ranks the escalation candidates
is the closed-form scalar (survival + development weighted), which appears to systematically prefer the
slower, board-preserving line over the fast Mega-ex mirror's tempo — a race the tuned aggressive pick
wins. This points the tier's *real* unlock at its already-listed gaps, not the trigger: the **Tier-5
value-model leaf** (P(win), replacing the survival/dev scalar) and a **real opponent-deck reply model**
(vs the our-policy proxy). A commit-MARGIN gate (override only on a *substantial* two-ply gap) + a higher
`_ESCALATE_DENSITY` are the cheap salvage knobs to sweep before those, if the trigger is revisited.
