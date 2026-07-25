# ADR-0069: The attach marginal is an axes-sum, and the decider may say no

**Status.** Accepted (grilled 2026-07-25, `/grill-with-docs` on issue #139 — thirteen locked
decisions). Build: #139 (Phase 1a of the Value System, tracker #136) — the FIRST no-shadow decider
swap, so its shape (fold → delete → retune → corpus re-rule → paired A/B) is the pattern 1b–1e
follow. Companion vocabulary: **Retreat Equity · Ability Fuel** in the Agent Runtime
[`CONTEXT.md`](../../src/common/CONTEXT.md); the Budget/reachability family is ADR-0067 (#137);
the snapshot it reads is ADR-0068 (#138); the shadow-era rulings it amends are the 2026-07-21
attach grill (`docs/plans/attach-valuation-grill-spec.md`).

## Context

The energy-attach decision was a pile of 23 tuned Hypotheses (`baseline_energy.py`) whose
magnitudes encoded logic as weight coincidences: the desperation attach lived at `+15 − 12 = +3`,
the doomed-Active arm existed only for the biggest attack (`attach_completes_biggest_attack`), and
Ignition's real provision was falsified to 1 unit unless a KO justified 3. The shadow oracle
(`pilot._attach_value`) priced attaches in one damage currency but decided nothing, was count-based
(a {R} on a {P}-needing body read as progress), budget-blind (`this_turn` saw only the manual +1),
and hard-gated a non-attacking role to marginal 0 — which, with the positive rungs deleted and the
−12 guard surviving, would have scored the only-legal-home attach at −12: BELOW End, inverting the
behavior the rung pair deliberately protected.

Facts that shaped the rulings (verified 2026-07-25 at source):

- Lunatone (675) attacks without Solrock — Power Gem {F}{F} 50 is unconditional; the partner
  condition is on its Ability (and on Solrock's Cosmic Beam). What zeroes a lone Lunatone is the
  deck-declared partner gate, i.e. a ROLE claim, not a card fact.
- Retreat slots are colourless (rules.md §per-turn: pay the printed Retreat cost in any Energy), so
  mobility value is type-agnostic — exactly the value an off-type desperation attach buys. TEF
  Dunsparce (65) has NO retreat cost: a retreat-funding term is structurally zero on it, so the f21
  "don't feed Dunsparce the only {D}" lesson survives any mobility credit.
- Munkidori (112): Mind Bend costs {P}●, Adrena-Brain wants a {D} attached. A {D} fills the ●
  slot (colourless absorbs any type) AND wakes the Ability — two INDEPENDENT card features on one
  Energy. Under a `max` combiner they tie with a plain {P}; only a sum ranks {D} first.
- Ignition (17) provides {C} on a Basic, {C}{C}{C} on an Evolution, discards at end of turn — and
  colourless provision pays only colourless slots under typed matching.
- Mega Starmie ex (1031): Jetting Blow {W} 120 / Nebula Beam ●●● 210. The corpus case "arm the
  doomed Active with the attack it unlocks TONIGHT, even a non-biggest, non-KO one" is pure
  arithmetic (120 tonight > ~70 bench build) — the rung layer lost it because its arm exemption
  was biggest-attack-only.
- The attach-first-before-Lillie's ordering is owned OUTSIDE this decider (`attach-before-hand-
  shuffle` fires on the shuffle PLAY; `_finish_turn_last` tiers attach before tier-3 finishers).

## Decision

**1. The marginal is an axes-sum: max WITHIN an axis, sum ACROSS axes.**
`marginal = attack_axis + retreat_equity + ability_fuel − evaporation_loss`, with
`attack_axis = max(this_turn, build, accel_value)`. The three attack terms re-read ONE progress
(max prevents double-pay); Retreat Equity and Ability Fuel are independent card features (sum is
honest — the Munkidori {D} beats the {P} outright, no tie-break).

**2. `this_turn` is a true counterfactual under the full Attach Budget.**
`best_dmg(B | Budget with E committed) − best_dmg(B | manual leg unspent)` — typed and sound both
legs (ADR-0067 machinery, one Budget per candidate body). An attach is credited tonight only for
what it UNIQUELY adds; budget-completable attacks stop reading as unreachable (the f70 class) and
type-unpayable ones stop reading as reachable.

**3. Build is typed slot-fraction; off-type waste is emergent, not a flag.**
`(matched/total_slots)² × maxDamage` by greedy typed assignment against the line-payoff attack's
cost shape (same matcher as `reachable_attach` — two matchers may not disagree). An Energy that
fills no slot earns zero build; `_attach_type_wasted` and its rung retire. The old boolean was
colourless-blind (it called Munkidori's {D} wasted); the typed fraction cannot be.

**4. Gates land per-axis.** The role gate and overkill cap zero the ATTACK AXIS only — a
role-gated body still banks mobility/fuel. The evaporation gate is global (a card that leaves play
at end of turn banks nothing durable). The role gate is BOARD-EVALUATED (the Ruling-6 pattern
generalized): "this body's job is not attacking" gates only while an attacker-role/Line
alternative is IN PLAY; a lone or attacker-less board prices the body by its printed attack. The
survival gate learns the evolution-escape: a doomed wincon-Line pre-evolution keeps build credit
(Energy carries through evolution; Megas do not end the turn on evolving — rulebook delta).

**5. Burst units are honest; conservation is in-equation.** Ignition counts what it provides
(3 colourless units on an Evolution — a card fact, never bent by opponent HP). The spend
discipline that the unit-gate smuggled: (a) an attach that EVAPORATES uncashed scores
`− worth(E)` — End beats torching an Ignition, no −60 rung; (b) a cashable burst's tonight-credit
is capped at the best reusable-in-hand equivalent UNLESS the burst's attack converts a KO;
(c) reusable-over-burst stays the `resource_cost` tie-break. Consequence: the tactical's
never-negative clamp is REMOVED — the decider may push an attach below End.

**6. Prize math stays out** (Ruling 4 re-affirmed for the decider era). The race belongs to
#145's one scalar; the sole frame that wanted it (`85058574-121`) needed planner-scope reads no
local term supplies. The corpus protocol converts any future disagreement into #145 evidence.

**7. Nineteen of 23 rungs delete; three survive + one ordering mechanism.** Deleted: the 8 folded
positives, the 5-rung burst family, both role guards, both doom guards, the waste flagger, the
fuel rung. Survivors — structure, not value: `use-acceleration` (PLAY-side, currency-clean),
`prefer-active-attach-in-setup` and `feed-the-line-for-disruptor-lock` under EXECUTABLE band
constraints (each must sit below one scaled convex build step / re-derived vs the new band, as
test-asserted inequalities). `attach-energy-last` converts from a −5 weight to a decide()-only
ordering deferral (the `attach_to_needy_line` mechanism), TIER-AWARE: it stands down against
`shuffle_hand` finishers, so development → attach → hand-shuffle → attack is structural, not a
coincidence of −5 vs −60.

**8. The swap protocol: diff while both deciders exist, one batched review, then delete.**
Build behind the flag; sweep flag-ON vs flag-OFF over the corpus + all pinned attach frames +
the grill's synthetic pins (Mega-Starmie tempo arm, lone-Lunatone desperation, Munkidori {D}>{P},
TEF-Dunsparce zero); every flip user-ruled in ONE sitting with the axes breakdown shown; then the
deletion commit; then the paired A/B gauntlet (directive 6) before merge.

**9. The fourth shadow retires; OFF is degraded-mode, not rollback.** The per-option axes rows
become the DECIDER'S legible working on the decision record (the substrate #146/#148 consume);
the agreement bit dies with the shadow wrapper. `attach_value` ships ON as the emergency lever,
and OFF is documented + pinned as "attach endorsements silent" — the deleted rungs are NOT
resurrectable, per the tracker's deletion directive.

## Consequences

- The equation is legible where the pile was folklore: every case the rungs hand-encoded
  (concentrate, arm-the-doomed, conserve-the-burst, don't-fund-utility, desperation, fuel,
  Active-vs-bench tempo) is now an arithmetic consequence of nine stated rules — and the three
  standing-down exemptions the rungs needed (`bench_line_member_needs`, go-down-swinging,
  only-legal-home) are EMERGENT from band ordering, per-axis gating, and board evaluation.
- The retune is constraint-first: the feasible scale region is solved from written inequalities
  (which are CI-asserted against the shipped constants), THEN corpus `score_diff` picks within it,
  THEN the A/B confirms. No number is folklore.
- Cost accepted: a hypothetical-body Budget build per option (bounded by the menu; closed-form),
  and the one-sitting review of every corpus flip. Ladder risk is accepted per directive 2.
- The desperation floor depends on the Retreat Equity band clearing zero competitors only (End) —
  the −5 that would have silently killed it is gone from the score channel by ruling 7.

## Amendments from the build (2026-07-25, #139)

Five refinements the corpus forced during the swap. Each STATES a rule the decision above implied but
did not spell out; none reverses a ruling. Evidence: `docs/plans/attach-decider-swap-review.md`.

1. **The survival gate has a THIS-TURN half.** Decision 4 gave it a build half only, so a doomed
   Active could be armed in front of an available pivot — 83007714-65, the charter frame of the very
   rung being deleted. Tonight's credit now stands down on a doomed Active when a ready benched
   win-condition exists AND the engine is offering the retreat. The MENU read is load-bearing:
   82525101-69 has a "ready" bench Mega too poor to pay its own 2-cost retreat, and arming the doomed
   Active for 120 is the play there.
2. **A burst earns no BUILD, ever.** Decision 5 made the units honest and capped tonight's credit, but
   build is FORWARD value and a `discard_eot` card is discarded at end of turn. Without this the
   honest 3 units read as a full payoff build and out-bid the reusable Basic underneath the cap.
3. **The role gate reads the deck's DECLARED roles.** A body given roles, none of them an attacker
   Role, has been declared a non-attacking plan piece — the general form of the `engine`-only read,
   and what catches a `counter_mover` or a sacrificial `starter`. Its exemption set is ADR-0048's
   BROADENED line set, so a secondary attacker's base (`evolution_base`) is a plan piece too.
4. **The gate stays IN PLAY, not per-colour.** Making it "an attacker who can use THIS colour" was
   measured: it fixes two follow-up doctrine pins and INVERTS the committed 86091728-19 correction.
   The correction wins; the doctrine's real content is a resource-sequencing claim no gate expresses.
5. **The scale is 1.0, not 0.3.** Solved constraint-first, then corpus score-diff: agreement is flat
   over [1.0, 1.5] and three regressions worse at the shadow-era seed, which was sized against a flat
   +15 rung floor that no longer exists. At 1.0 the marginal IS a damage currency. The two surviving
   band-constrained weights were re-derived against it (`prefer-active-attach-in-setup` +8 -> +1;
   `feed-the-line-for-disruptor-lock` +20 -> +55), and the inequalities are CI-asserted in
   `tests/strategy/test_attach_bands.py`.

## Merge evidence (2026-07-25)

Decision 8's paired A/B, run as a BUILD A/B rather than a flag A/B — with the rungs deleted,
`attach_value` OFF is degraded mode and an on/off delta would have measured the decider against
nothing (`tools/sim/gauntlet_swap_ab.py`; six directed matchups, opponent fixed at the pre-swap
build, seat-balanced, n=200 per arm):

**delta +2.92 pp, 95% CI [−0.46, +6.30] pp, 0 crashes in 2400 games** — the grilled flip rule
(`delta >= 0 AND CI-lo >= -1% AND crashes == 0`) PASSES. It passes on the delta, not on precision:
±3.4 pp could never have cleared −1% on width alone. Five of six matchups improve or hold. Full
table: `docs/plans/attach-decider-swap-review.md`.

## Alternatives rejected

- **Budget-as-gate-only `this_turn`** (keep count-delta, veto phantom credit): leaves the f70
  under-read class alive — the budget must ADD credit, not only veto it.
- **A whether-to-attach epsilon floor**: unconditional attach-anyway is a measured blunder class
  (dragapult f21); mobility value must be a priced fact (Retreat Equity), not sentiment.
- **`max` over all five terms**: erases the fuel/mobility signal whenever the colour also fills a
  slot (the common case — ● absorbs everything); double-duty Energy must WIN, so orthogonal
  channels sum.
- **KO-gated burst units**: bends a card fact to encode a spend heuristic; incoherent once the
  counterfactual Budget leg type-matches real provision.
- **Keeping the guards as re-tuned rungs**: their magnitudes were anti-stack calibrations against
  deleted positives (−45 "to cancel that stack"); keeping them re-creates weight-coincidence
  logic plus the below-End inversion on every axis-gated body.
- **A prize-race modifier now**: double-ownership with #145's scalar, zero in-scope corpus demand.
- **Joint numeric optimization** of scale + bands + surviving weights: overfits 130 frames and
  returns the pile's illegibility with extra steps.
