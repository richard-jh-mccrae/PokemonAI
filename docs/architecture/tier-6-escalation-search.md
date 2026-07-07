# Tier 6 — Escalation Search

**Status: ~75% built, still DEFAULT OFF** (built 2026-07-05, `/tdd`, ADR-0043; the DENSITY trigger +
engine-backed fixture added 2026-07-05 — the trigger fires + commits but its mirror A/B **regressed**
(ON 44 %), so it stays parked OFF; see Acceptance / ADR-0043 Amendment). The narrow, budgeted engine tree for the one thing closed-form provably
cannot see: **opponent choice**. Demoted by the 2026-07-05 grilling from "the" multi-turn answer (old
M3) to the last-resort residue handler — KO-Race arithmetic (T3) owns the dominant multi-turn case.
**Two triggers now feed it:** the close-attack-tie (structurally ~unreachable for our decks — a firing
diagnostic saw 0 commits over 646 real mega_starmie decisions, since ≥2 affordable attacks occur on
only 0 / 0.3 / 1.5 % of MAIN menus) and the **opponent-disruption-DENSITY** trigger that replaced it as
the real unlock (fires + commits on real boards — see *Built — density trigger*).
**Upstream:** the two triggers; the opponent-reply proxy policy; the T5 leaf.
**Downstream:** overrides the tuned pick only when it triggers, strictly wins, AND stays in budget.

## Final design

- **Trigger, not always-on**: fires only when the closed-form layers cannot discriminate —
  KO-Race tie within ε at attack choice, or an opponent-choice-dominated board (disruption /
  gust / heal density flagged from Function Tags + Brief). Everything else never pays a step.
- **Mechanics**: depth 2–3 over the Engine Search (`search_begin/step/end/release`); my nodes drive
  real candidate lines; opponent nodes play the γ-gated predicted deck's plausible replies (T4) —
  verdicts trusted per the prediction-invariance rule (prefer conclusions robust across the
  overlay's uncertainty).
- **Budget = hard invariant**: per-move step cap derived from measured `search_step` cost
  (~0.1 ms) against the 10-min match bank; the T1/T0 answer is computed FIRST and returned
  unconditionally on exhaustion — never-crash/never-timeout is structural, not aspirational.
- **Leaf** = T5 value model when present, closed-form scalar otherwise.
- Tier-1 telemetry keys (tree depth/branches, reserved since ADR-0019) get wired here.

## Built (the 55%) — 2026-07-05, ADR-0043

- **The trigger** (`_close_attack_tie`, REQ-ESCALATE-0001): fires only on ATTACK options within
  `_ESCALATE_EPS` tactical points; a clear leader / lone attack / KO-on-menu short-circuit to no
  escalation, so plain boards pay zero.
- **Depth-2 evaluation** (`_two_ply_value` over `_simulate_line(opponent_reply=True)`): sims each
  tied attack through my turn AND the opponent's reply (our own policy as the proxy) to the start of
  my next turn, leaf = the T5 value model when present else the closed-form scalar; an opponent-reply
  WIN scores −KO_SCORE (avoid the attack that hands them the game).
- **Conservative commit**: the best two-ply attack commits only if it strictly beats the tuned
  tie-pick's own two-ply value; else defer (escalation breaks a tie, never overturns a clear pick).
- **Hard per-move budget** (`_search_steps` capped at `search_budget`; the reply sim halts when
  spent) + **never-time-out** (engine absent / slip → None → tuned pick). The Tier-1 `_simulate_line`
  path is byte-identical when `opponent_reply=False`. Committed lines ride telemetry under
  `goal="escalation"`. Gated REQ-ESCALATE-0001..0003; DEFAULT OFF.

## Built — density trigger (2026-07-05, the real unlock)

The close-attack-tie trigger is structurally near-unreachable for our decks (0 commits / 646 real
mega_starmie decisions). `_escalate` is now a **two-trigger dispatcher**: when the attack-tie yields no
candidates it falls through to the opponent-disruption-DENSITY trigger, which fires on board TEXTURE,
not on 2+ affordable attacks — the deferred refinement, now built.

- **Signal is generic** (`_opp_disruption_density`; Fork A = tags+Read, authored-brief field deferred):
  a weighted count of the opponent's `_DISRUPT_TAGS` (`gust`/`switch`/`heal`/`hand_disruption`/
  `energy_denial`) capability from **Function Tags over the opponent's REVEALED cards** (active/bench/
  discard, full weight — certain) **plus the Read's Representative-Build predictions** (`expected_cards`
  at `gamma * inclusion_prob` — the Brief-gated hidden-deck signal; the matched Brief participates via
  the gamma-gated Read, no brief-schema change). `_density_dominated` fires at `_ESCALATE_DENSITY` (2.0).
- **Candidate set** (`_top_k_candidates`; Fork B = top-K, K=`_ESCALATE_TOPK`=3): the raw top-K options
  by tactical — NOT a positive-score subset, because a disruption-dense board is exactly where the
  opponent-static tactical ranking is unreliable, so the two-ply **strict-improvement commit gate** (not
  a tactical-sign filter) is the protection. Gated to a combat board: an affordable attack must be on
  the menu, and a KO on the menu short-circuits (a KO dominates — never escalate away from it).
- **Same invariants**: both triggers share `_commit_escalation` — sim each candidate two-ply, commit the
  best ONLY if it strictly beats the tuned pick's own two-ply value, budget-guarded, tuned pick the
  guaranteed fallback. The rationale names the firing trigger (telemetry/correction legibility).
- **Firing diagnostic** (6 mirror games/deck): density flags 66 / 33 / 66 % of MAIN decisions as dense
  and **commits** (strict two-ply upgrade) 42 / 33 / 63 overrides per 6 games for mega_starmie /
  dragapult_ex / mega_lucario — fires AND changes play (vs the attack-tie trigger's 0). Gated
  REQ-ESCALATE-0006/0007/0009 (unit — signal, gating, commit gate) + 0008 (engine: density fires on real
  boards + the seam holds). The live commit is engine-trajectory-dependent (unit-pinned + diagnostic-
  measured, never asserted as a live count — a flaky-test trap Linux CI surfaced).

## Gap to final (the 25%)

1. **Deeper trees** (depth 3+) + a favorability-scaled budget.
2. **A real opponent-deck reply model** (vs the our-policy proxy) from the T4 overlay.
3. **An authored-brief hazard field** (Fork A option 3): let a Brief declare `opp_disruption_density`
   directly, overriding/boosting the generic tags+Read signal per archetype (matchup-genie owns it).

## Acceptance — build met 2026-07-05; A/B regressed → kept OFF

Zero triggers on plain boards (REQ-ESCALATE-0001); defers when off / no budget / no search input
(REQ-ESCALATE-0002); DEFAULT OFF on the shipped Pilot (REQ-ESCALATE-0003); the Tier-1 sim path
unchanged (full suite green). The density trigger fires on real boards and its commit gate holds
(REQ-ESCALATE-0006–0009; the live commit is unit-pinned + diagnostic-measured, not a flaky live count).

**The budgeted ladder A/B ran and REGRESSED** (mega_starmie mirror, escalation ON vs OFF, 1000 games:
**ON 44 %, 95 % CI 41-47 %, 0 crashes**), so the tier stays DEFAULT OFF — built, gated, and parked with
evidence, not shipped. The two-ply overrides systematically lose to the tuned scorer (the closed-form
survival/dev leaf appears to prefer board-preservation over the fast mirror's tempo). The tier's real
unlock is its Gap items — the Tier-5 value-model leaf and a real opponent-deck reply model — not the
trigger breadth; a commit-margin gate + higher density threshold are the cheap salvage knobs first.
See ADR-0043 *Amendment* for the full result and root-cause read.

**Note (2026-07-07, tier-vs-planner review): this park rests on VALID evidence — unlike T5's.** The 44 %
came from a **mega_starmie MIRROR** (both seats the strong deck, only one running escalation), which is
*immune* to the weak-opponent saturation that voids the cross-deck gauntlet as a gain gate
([ADR-0045](../adr/0045-match-scale-planning-is-a-closed-form-directive-game-plan.md) "Gauntlet A/B as the
gain gate … invalid (weak decks)"). A mirror cleanly isolates the feature: neutral → ~50 %, hurts → < 50 %.
Landing at 44 % (CI 41-47, entirely sub-50) is a clear self-inflicted regression, so **as-built T6 genuinely
loses** — the disposition needs no re-test, only the Gap items. Contrast [Tier 5](tier-5-value-model.md),
parked on the *invalid* cross-deck gauntlet. Both unlocks are tracked in
[parked-learned-search-tiers.md](../todo/parked-learned-search-tiers.md).
