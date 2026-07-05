# ADR-0040: Match-level judgment is per-turn closed-form objectives (Prize Path × KO Race → derived phases)

**Status.** Accepted (grilled 2026-07-05, `/grill-with-docs`). **Built 2026-07-05 (`/tdd`)**: KO
Race (`objectives.py`, the `a21472` gate GREEN), two-sided Prize Path + denial consumers, derived
hysteretic phases + the 24-site gate-ban migration (lint-guarded), and the γ-continuous predicted-
attacker overlay; switches `objectives_race`/`objectives_path`/`objectives_phases` **default ON**
(joint A/B 50%, CI 48–53, Battle #57; post-overlay consumer A/B 52%, CI 50–54, Battle #59; 0
crashes throughout). Build
record: [docs/architecture/tier-3-match-objectives.md](../architecture/tier-3-match-objectives.md)
(~75%) and [tier-4-opponent-model.md](../architecture/tier-4-opponent-model.md) (the overlay).
Terms added to [src/common/CONTEXT.md](../../src/common/CONTEXT.md): *Prize Path*, *Path Denial*,
*KO Race*. **Partially reverses** the prescription in
[deferred-multi-turn-criticals.md](../todo/deferred-multi-turn-criticals.md) ("do not bolt
multi-turn onto the closed-form Planner; it belongs behind the engine-search escalation + the
value-model leaf-eval") — that doc carries a correction note pointing here.

**Context.** The Pilot had no model of the prize race: which KOs advance whose win, which of my
bodies should absorb the next KO, whether to spend turns denying rather than racing. The fragments
that existed (interpose promote, `_prize_value` weighting, key-threat rung, Survival Window) are
local. Meanwhile the two match-scale intents that decide real games — "make them take 7 prizes,
not 6" (2× Mega Starmie ex + Cinderace = 3+3+1) and "KO 2 Mega Lucarios OR avoid the second and
snipe 3 smalls" — are pure arithmetic over prize values ({1,2,3}, verified `docs/rules.md` §6) and
turns-to-KO. The live blunder `a21472` (Nebula 210 vs Jetting 120+50: the 440-HP wall dies in 3
turns under EVERY ordering, so the 100 incidental bench chip onto Riolu decides) needs exactly
turns-to-KO sequence arithmetic — the same epistemic tier as the existing Incoming/Survival Window
closed-forms, NOT a game tree. Reserving all multi-turn reasoning for engine search + value model
was over-deferral: opponent-*static* multi-turn arithmetic is sound where it claims soundness, and
the truly opponent-*choice*-dominated residue is small.

**Decision.** A per-turn **Match-Objective layer** above the Turn Planner, all closed-form,
re-derived every turn, never a lock:

1. **Prize Path, two-sided**: enumerate assignments of KOs over the other side's KO-able bodies
   whose prize values ({1,2,3}; ≤6 bodies a side ⇒ trivial subset-sums) sum to the remaining
   prizes — my cheapest feasible acquisition path AND their cheapest path through my board —
   feasibility-weighted by KO-Race turns + replacement. Mild **stickiness** (path-switch penalty)
   for coherence; a ranking objective that conditions target/promote/bench/develop scoring, never a
   committed plan.
2. **Path Denial**: bench discipline, promote order (interpose generalized), and KO-priority terms
   that lengthen their cheapest path ("force 7").
3. **KO Race**: closed-form turns-to-KO both directions, over attack SEQUENCES with riders credited
   to on-path targets (fixes `a21472`); their direction generalizes Survival Window board-wide;
   yields the race posture (turns ahead/behind).
4. **Phases are derived, not authored — and ADVISORY, never gates** (contract hardened in the
   2026-07-05 phase grilling): `Plan` becomes a pure function of the objectives — behind-in-race +
   their-path-imminent → STABILIZE; my-path ≤2 prizes or lethal-adjacent → CLOSE; else SETUP→RACE.
   One source of truth: a phase can never contradict the math that justifies it. The contract:
   (a) **gate ban** — no rule may key eligibility to `plan == X`; the label carries only SMALL
   additive weight bands, so a wrong phase read costs a few biased points for a turn, never a
   silenced rule family (existing SETUP/RACE-gated rules migrate to the underlying readiness
   signals via Alignment Passes); (b) **band magnitude scales with input confidence** (γ, doom
   margin) — an obscure read biases ~nothing; (c) the label is **hysteretic** (enter/exit
   thresholds differ) to kill near-threshold oscillation, while the underlying continuous terms
   react same-turn — label lag is cosmetic; (d) derivation is **memoryless**, so transitions run
   backwards as freely as forwards; (e) **phase-ablation invariant** — a label-off A/B must land
   within noise, permanently; a phase that moves win-rate has become load-bearing, which is a
   design violation, not a tuning target. STABILIZE/CLOSE stop being dead enum values; deck
   Strategies keep their readiness parameters.
5. **The their-side is γ-gated two-layer** (with ADR-0026): a visible-board floor plus the Read's
   predicted overlay (dossier evolution paths / Brief corrections, weighted by confidence γ) — so
   "avoid the second Mega Lucario" is decidable BEFORE it is benched; unknown opponent → γ→0 →
   floor only → structurally no regression.
6. **Scope boundary**: exact arithmetic under the standing-board assumption. Boards where opponent
   choice dominates (retreat/heal/gust webs) belong to the narrowly-triggered engine-tree
   escalation ([tier-6](../architecture/tier-6-escalation-search.md)); the objectives themselves
   never lock a multi-turn claim.

**Rejected.**
- **A committed match plan** (choose THE path once, replan on invalidation): brittle under reveals
  and prize swings; commitment without soundness is the phantom-lethal mistake at match scale.
  Stickiness buys the coherence without the brittleness.
- **Prize trajectory as a leaf term only**: invisible to candidate GENERATION (never generates
  "snipe Riolu because it completes the 1-1-1-3 path") and illegible.
- **An authored phase state machine**: a second, coarser judge of facts the objectives already
  measure — able to contradict them; every deck re-litigates thresholds (the reason M2 deferred
  STABILIZE once already). Forward-only transitions would additionally be wrong — real matches
  regress (CLOSE back to RACE when the opponent stabilizes).
- **Phases as hard gates** (`when: plan == X` eligibility, the status-quo pattern extended to
  STABILIZE/CLOSE): a mode is a step function over continuous, *estimated* inputs — threshold
  cliffs at the margins, rule families silenced outright on a wrong read, eligibility whipsawed by
  quick transitions. The 4–4 trade-vs-wall stress case (doom math says STABILIZE, favorability +
  race delta say keep trading) misfires catastrophically under gates and costs a few weight points
  under bands.
- **Visible-board-only their-side**: structurally blind to the second-Lucario class of decisions.
- **Brief-worst-case-always**: no confidence scaling; over-denial vs stumbling opponents; the
  un-Brief'd tail gets nothing.
- **Engine-tree search as the multi-turn foundation** (the old M3 framing): prediction-poisoned at
  every opponent node and budget-expensive; demoted to the residue handler.

**Consequences.** `choose_plan` is rewritten as a derived function (Score-Diff-gated where neutral).
The value model's feature vector becomes these primitives (path feasibilities, race deltas, denial
margin — ADR-0007's open "feature encoding" question resolved by architecture;
[tier-5](../architecture/tier-5-value-model.md)). The trace prints both live cheapest paths + the
race delta every turn. `a21472`'s definition-of-done moves here (a REQ gate through the real
Pilot); `b4649` stays the covered exemplar — mine a fresh failing example before building denial
beyond the objective terms.
