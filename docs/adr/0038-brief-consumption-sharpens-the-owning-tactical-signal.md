# ADR-0038: Brief consumption sharpens the owning Tactical signal (γ-scaled), not parallel Hypotheses

**Status.** Accepted (2026-07-04) and built — then **SUPERSEDED by [ADR-0051](0051-matchup-target-priority-spine.md) (2026-07-12)**: the γ-gated Brief levers (`brief_preevo` / `brief_engine`) are **RETIRED FROM THE CODE**, not merely default-OFF, and the MatchupPlan target-priority spine (`matchup_targeting`, `PROFILE=True`) replaces them. *(Corrected 2026-07-14: this ADR still described `brief_engine` as "wired but default OFF" and carried no superseded marker; `runtime.py:44` had recorded the retirement all along.)*

**Context.** The Matchup-Brief pipeline ([ADR-0027](0027-matchup-brief-is-hand-authored-opponent-doctrine.md))
is built and behavior-neutral: a recognized opponent's Brief lands on `Board.brief` with threats/targets
resolved to ids — and nothing reads them. ADR-0027 sketched consumption as "General or deck Hypotheses
then read those fields." Wiring it surfaced a structural fact: the snipe threat order is ONE Tactical
signal (`Pilot._body_threat_rank`) with three consumers — the snipe Hypotheses (via the
`target_is_top_threat` equality), `Board.strongest_threat_rank`, and the Turn Planner's
KO-the-key-threat rung. A parallel "snipe-the-briefed-target" Hypothesis would weight one select while
the planner keeps ranking by the unboosted order — two disagreeing threat orders — and double-count
with `snipe-the-top-threat`. Lever C (ADR-0026) already set the precedent: a γ-scaled modulation
*inside* the rank, not a Hypothesis.

**Decision.** Brief intel becomes behavior **sharpen-first**: it feeds the existing Tactical machinery
that already owns the decision, scaled by the Read confidence `γ`; a new Hypothesis is minted only for
a behavior nothing owns yet. Boost magnitudes are hand-calibrated Tactical seeds (module constants —
the corrections tuner fits only Hypothesis weights and cannot reach inside a rank function); each
lever sits behind a per-lever kill-switch param (Pilot-ctor default False; each agent's `main.py`
passes True once the lever clears its A/B — the `lethal_verify` pattern).

The two levers this wires, and the dispositions of everything else on the Brief surface:

- **`fragile_preevo` lever (`brief_preevo`).** `rank += γ · _BRIEF_PREEVO_SNIPE_BOOST` in
  `_body_threat_rank` for ids in `Board.brief_target_ids("fragile_preevo")` — **tier-crossing**
  (200000 > the 100000 energized tier): a bare briefed pre-evolution overtakes energized bodies once
  γ ≳ 0.5, so authored payoff-denial ("snipe Riolu before it evolves — deny the 3-prize Mega for a
  1-prize trade") dominates the generic imminence signal as recognition firms. The deadline physics
  justify crossing: the pre-evo evolves NEXT turn or the window is gone. Accepted, documented cost: on
  pure-chip boards (no KO-able target) we chip the bare pre-evo over an energized attacker. Plus the
  matching γ-scaled sub-prize gust-target tie-break (sibling of `_gust_forward_denial`) so the gust
  pick and the snipe order agree.
- **`engine` lever (`brief_engine`).** Sub-tier `rank += γ · _BRIEF_ENGINE_SNIPE_BOOST` (500, peer of
  the hand-size boost) + the matching gust tie-break, for `brief_target_ids("engine")` — hard-gated on
  `Board.opp_property("opp_is_engine_dependent")`. No deadline → imminence keeps priority (an
  energized live attacker still outranks the engine body). Built now with zero true-asserting Briefs
  (the shipped Lucario Brief judged it FALSE): the registry carries no unwired key, and the next Brief
  asserting true gets a live lever with zero code.
- **Covered — no lever (recorded in docs/scouting.md).** `prize_liability` targets: `_prize_value`
  reads ex/Mega off `CardStat`, `gust_best_ko_prizes` already drags up the max-prize KO-able body, the
  Lethal Solver does prize math, and `stall_target_is_keystone` already strands an un-KO-able key
  attacker. `threats`: the rank sees them by printed damage; the defensive half is the shipped
  forward-doom in `active_doomed`. Weakness ×2 stays the KO oracle's — Brief levers set the
  *gameplan* (which body wins the queue), never combat math.
- **Deferred — consumption unwired.** `opp_donk_vulnerable` (its snipe half is delivered by the
  preevo lever; the residual "early aggression" half) and `opp_tempo` (race/stabilize): both collide
  with ADR-0026's killed framings — an authored prior must not drive the Plan, and diffuse aggression
  boosts were considered-rejected. Unblock = a true-asserting Brief in the meta plus correction
  evidence naming a concrete decision. Nothing wired → no double-count with Lever A favorability.
- **Never overrides a KO — structural.** Boosts change which body wins a *rank*; `snipe-for-the-ko`
  (and `KO_SCORE`-class tactical) dominate any non-KO co-fire by construction, and the gust terms are
  sub-prize tie-breaks that never beat a prize difference.
- **Evidence gate per lever.** (1) unit fixtures (fires when recognized + role present + gate true;
  silent at γ=0 / no Brief / switch off; KO supremacy). (2) real A/B vs the in-repo `mega_lucario`
  agent (the covered archetype): **non-degradation beyond noise** — improvement is the hope, not the
  gate (1–2k games can't power small edges, and the lever also serves future Briefs). (3) neutrality:
  mirror A/B vs an uncovered opponent expects zero effect. The engine lever, lacking a real opponent,
  substitutes the ADR-0026 faked-belief stress leg: a test Brief asserting true force-fires it; a
  wrong assertion must cost nothing measurable.

**Built + measured 2026-07-04 (1000 games/leg, 0 crashes across 4000).** `brief_preevo` cleared all
three legs → **default ON** in every agent: real leg vs the in-repo `mega_lucario` 68% (CI 65–71) vs
baseline 69% (CI 66–72) — non-degradation at an already-crushed matchup (the Psychic-OHKO machinery
owns the headline; the lever refines target picks at the margin and serves future Briefs); neutrality
mirror 52% (CI 48–55). `brief_engine` **failed its stress leg → stays wired but default OFF**: a
deliberately wrong `opp_is_engine_dependent` Brief against the Starmie mirror force-fired the lever at
46% (CI 43–49) vs the same pairing's 52% (CI 48–55) noise floor — a wrong assertion costs ~4%, NOT
self-limiting like the favorability weight-band. Consequences: (1) the switch arms per the gate — the
first REAL true-asserting Brief must clear its own matchup A/B, then `brief_engine` moves to
default-ON (`ARMED_OFF_SWITCHES` → `REQUIRED_SWITCHES` in `test_agent_wiring.py`); (2) asserting
`opp_is_engine_dependent` in a Brief is a HIGH-BAR authoring call — it now moves play, and the wrong
call is priced.

**Considered options.**
- *Every lever a Hypothesis* (ADR-0027's literal sketch) — rejected: a second threat order the planner
  does not inherit, plus double-counting with `snipe-the-top-threat`; tuner-learnability wasn't worth
  incoherent targeting.
- *All-Tactical, no Hypothesis seam ever* — rejected: future Brief behaviors nothing owns (e.g. a
  tempo rule with evidence) still need the Hypothesis instrument.
- *Params-fed boost magnitudes* — deferred until a deck disagrees with a magnitude; the mechanism
  stays Tactical either way, only the number would move into `Strategy.params`.
- *Strict-improvement A/B bar* — rejected: underpowered samples would block doctrine-true levers on
  noise.

**Consequences.** Adding a posture stays one JSON: role-keyed targets and gated bools flow into the
same two boosts with zero code. The threat order stays single — snipe, planner, and gust move
together. ADR-0027's consumption sentence is superseded in part (sharpen-first; Hypotheses remain the
fallback instrument). Boost constants are hand seeds the tuner can't fit — if corrections ever demand
per-deck magnitudes, promote them to params. CONTEXT.md gains the **Lever** term; the Posture entry
drops the retired seek/avoid framing.
