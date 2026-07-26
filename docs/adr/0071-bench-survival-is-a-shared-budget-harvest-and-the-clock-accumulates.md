# ADR-0071: Bench survival is a shared-budget harvest, and the clock accumulates

**Status.** Accepted (grilled 2026-07-26, `/grill-with-docs` on issue #163 — twelve locked
decisions). Build: #163, branching off `main` **after #166 (Phase 1b) merges** — decision 5.
Companion vocabulary: **Bench Harvest** in the Agent Runtime
[`CONTEXT.md`](../../src/common/CONTEXT.md). Amends **ADR-0070 §9** (the bench branch it corrects,
recorded there as amendment D) and the shipped `turns_to_ko_me` semantics; inherits the
caller-passed-conservatism convention from **ADR-0064 Decision 1** (`charged`) and **ADR-0070 §9**
(`my_benched`); reuses **ADR-0068**'s snapshot for the self-side bench.

## Context

`CombatMath.turns_to_ko_me` asks *"can the opponent's reachable damage fell THIS body?"* once per
body, independently. On the Bench that damage is a rider, and a rider is a **shared budget**:
attacking ends your turn (`docs/rules.md` §5, rulebook L150), so one turn of bench damage is exactly
**one attack's payload from one attacker**. Dragapult ex's Phantom Dive puts *"6 damage counters on
your opponent's Benched Pokémon in any way you like"* — 60 damage distributed across the whole
Bench, verified at `data/EN_Card_Data.csv` row 121 — not 60 per body.

Read per-body, the survival term credits rescuing one benched Pokémon as though the entire spread
were dedicated to it. The opponent simply redirects the counters onto another body still in range.
**The rescue does not deny a knockout — it only picks which body dies.**

The frame that surfaced it (`dp_evolve_energized_line_body_first_f82`): bench Dreepy 50/70,
Dunsparce 50/70, Dreepy 50/70 against a 60 spread. Evolving one Dreepy to Drakloak lifts it to 70/90
and out of range, and the evolve decider credited that at **37.5 damage-points** — but bench 4 is
another Dreepy at 50 and the Dunsparce is at 50, so a body dies regardless.

Three facts found during the grill widened the defect beyond the filed report:

1. **The call site cannot express the fix.** `turns_to_ko_me(my_body, opp_bodies)` is handed my body
   and their bodies. Contention among *my own* bodies is not mispriced at that interface — it is
   **unrepresentable**.
2. **The snipe rider is shared too.** The pool carries **3** distributable spreads (Hex Hurl 20,
   Cursed Drop 40, Phantom Dive 60) and **10** single-target snipes; **no attack carries both**. A
   single-target snipe of 50 also kills at most one benched body, so evolving its target merely
   redirects it. The issue's title says "spread"; the mechanism covers the majority of the surface.
3. **The bench clock is a step function.** `turns_to_ko_me` is contractually one-swing, and on the
   bench `incoming` is constant in `t` (`t` moves only the energy budget). So the bench answer is
   binary — 1 or `max_t + 1` = 9 — and any rescue clearing a single threshold is handed the entire
   horizon. Damage counters persist; a 70-HP body behind a 60 spread falls on turn 2, not never.
   This inflates in the SAME direction as the shared-budget defect.

Point 3 is not a new semantic. `src/common/CONTEXT.md`'s **Threat Clock** entry already specifies
*"accumulating over turns when one hit doesn't KO (the Survival Window generalized)"*, and the
offensive twin `turns_to_ko` is already rate-based (`ceil(hp / best per-turn damage)`, the ADR-0040
KO Race core). The shipped `turns_to_ko_me` is the outlier, diverged from its own documented design.

Nothing shipped is wrong from the bench branch itself — it is new surface added in #140 with no
existing consumers (ADR-0070 §9). But three consumers are queued on it (1b's `p_survive`, 1c's
promote/retreat, 1d's famine/posture/doom), and the accumulation half of the fix touches the ACTIVE
path, where `survival_shift` (`pilot.py:6577`) is a **shipped** consumer feeding
`needs.opponent_target_value`.

**The delicate part is the fail direction.** Per-body worst case is *conservative* for a threat read
(it over-counts their reach) but *inflationary* for a rescue read (it over-credits saving one body).
Those pull opposite ways, which is why one read has served both until now.

## Decision

**1. The bench survival answer is a SET, not a per-body boolean — the Bench Harvest.** The question
becomes *"given one turn of their rider payload, which of my benched bodies do they take?"*
Per-body survival is a query on that set, and rescue value is the **marginal** — the change in their
harvest when a body's HP moves. Redirected counters produce a zero delta by construction, with no
calibration. A per-body clock cannot express a shared-budget fact at any price, and the set-level
answer is what 1c (choosing between bodies) and 1d (how much of my board falls) each need; leaving it
an implementation detail would have all three consumers re-derive it — the drift `_build_standing`
was extracted to prevent (ADR-0070).

**2. The budget is ONE attack's full rider payload, and the two riders keep their printed shapes.**
`benchSnipe` is **indivisible** (single-target text — all of it on one body); `benchSpread` is
**divisible** in 10-point counters ("in any way you like"). The opponent picks the attack. Solved by
enumerating snipe targets (≤5 bodies, plus "no snipe") around the existing `best_ko_subset` knapsack
over the spread — ≈200 subset evaluations. `_bench_rider`'s worst case ("an attack could aim both at
one body") survives as one enumerated allocation rather than as an assumption. Rejected: one fungible
pool over `snipe + spread`, which would split a 50-point snipe 20/30 across two bodies and take a
knockout the card cannot take — a second wrong answer pointing the opposite way.

**3. Two Harvest Readings, caller-passed, defaulting conservative.** `POSSIBLE` = in the harvest
under SOME optimal allocation (the threat/doom reading, and the **default**, so an undeclared caller
is safe). `UNAVOIDABLE` = in the harvest under EVERY optimal allocation (the rescue/value reading,
declared by `_evolve_side` and by 1c/1d's rescue legs). On f82's three-way tie, `POSSIBLE` preserves
the full 37.5 inflation and `UNAVOIDABLE` yields Δ = 0. Both are true statements about different
questions, which is the fail-direction conflict named in the Context; a single reading cannot serve
both. `UNAVOIDABLE` everywhere was rejected — two Dreepy at 50 behind a 60 spread means one dies for
certain while neither is unavoidable, exactly the phantom safety ADR-0070 §9 refused to grant. A
probability over the argmax was rejected as a uniform prior nothing verifies.

**4. BOTH areas accumulate across turns.** `turns_to_ko_me` becomes
`min{ t : Σᵢ₌₁..ᵗ incoming(i) ≥ hp }` on the Active, and on the Bench the first `t` at which my body
falls in the harvest of `t` allocated payloads. Areas do not contend: printed damage always lands on
the Active, riders always on the Bench, so the reads stay independent by card mechanics rather than
by assumption. The Active leg was ruled IN SCOPE (user, 2026-07-26) rather than split off — shipping
a knowingly one-swing Active semantic to protect a measurement is the tail wagging the dog, and this
issue's own thesis is that deferring a read fix means re-tuning consumers later.

**5. Accumulation composes as the SUM OF PER-TURN MAXIMA**, not a per-attacker race. `incoming`
keeps its scalar contract, its memoization and its four other callers untouched; only the comparison
changes. This errs pessimistic — it charges nothing for the retreat that switching attackers costs —
which is the repo's stated convention for threat reads (the bounded-pessimism guard, ADR-0064) and
the direction that *deflates* rescue credit. Consequence to state plainly: `turns_to_ko_me` is
deliberately NOT the exact mirror of single-attacker `turns_to_ko`. A per-attacker race was rejected
for forbidding promotion entirely and for requiring `incoming` to expose per-body damage.

**6. Promotion is an ENERGY affordability read, never a turn surcharge.** Corrected at the grill
(user, 2026-07-26): retreat is an ordinary turn action (`docs/rules.md:74`), limited to once per turn
and paid in **Energy discard** (`:89`); attacking ends the turn, so retreat-then-attack is legal in
one turn. A benched attacker owes Energy, not tempo — the CONTEXT.md Threat Clock entry's "promotion
surcharge (bringing it Active)" is wrong about the mechanic and is corrected by this ADR. A non-Active
body is admitted to `incoming` when `len(opp_active.energies) >= retreat_cost(opp_active)`, or the
Read credits a switch/gust enabler, or the body is their Active; an unknown retreat cost admits
(fail-open). Their Active being Asleep/Paralyzed blocks retreat (`rules.md:167`) and may tighten the
gate where the engine exposes it. Charging the retreat discard across the accumulation was REJECTED:
it turns a closed-form projection into a simulation of THEIR choices, which the Threat Clock's own
definition parks (*"opponent-static closed-form… never a claim about opponent CHOICE"*).

**7. The seam: a pure `CombatMath` primitive, the snapshot owns my bench, the caller declares the
reading.** `CombatMath.bench_harvest(my_bench, payload, *, reading) -> frozenset[int]` sits beside
`best_ko_subset` / `spread_ko_prizes` — pure, board-free, unit-testable. `StateModel` gains
`my_bench_raws`, mirroring the existing `body_raws` for their side; because it is a lazy pure
snapshot (ADR-0068) the bench cannot shift under a memoized read. Memo keys extend to
`(id(my_body), reading)`. Putting the harvest inside `incoming` was rejected — squeezing a set answer
through a scalar return is how the per-body framing became load-bearing in the first place.

**8. The opponent maximizes PRIZE VALUE, with a SUB-PRIZE wincon tie-break.** Knocking out a benched
Pokémon takes prizes exactly as an Active one does (`rules.md` §6), so the objective inherits
`best_ko_subset`'s existing prize argmax and its cheapest-set tiebreak verbatim — one implementation
of one fact. The comparator then gains a third key, after `prize` and before `cost`: the count of my
bodies carrying `_ATTACKER_ROLES` (`context.py:84` — `win_condition`, `primary_attacker`,
`secondary_attacker`, `win_condition_base`, `accel_source`), deck-declared via `strategy.roles`, so a
deck declaring no roles degrades to pure prize-max (`planner.py:66-67`'s existing fallback).

The narrow `_WINCON_ROLES` was verified **inert** on the Bench: in `dragapult_ex`'s `ROLES`, Dreepy is
`win_condition_base`, Munkidori is `counter_mover`, and Dunsparce carries no Role at all — the
wincon itself is usually Active or in hand. This is a *preference*, not a magnitude: it cannot
express "they would forfeit a prize to kill my engine". That mirrors the discipline this codebase
already set for the symmetric case — `opponent_target_value`'s survival term is deliberately
*"SUB-prize… breaks ties among prize outcomes but never overrides a real prize difference"* — and it
adds no constant, in a subsystem that just deleted five on the grounds that no number is folklore
(ADR-0069). An additive premium and a derived-from-my-own-clock premium were both rejected: the
first invents a constant, the second is circular (the survival read is an input to the value model
that would price it) and belongs wherever #145's `state_value` lands.

**9. #166 merges BEFORE #163 branches.** ADR-0070 §11 set the protocol — branching off unmerged work
leaves any regression ambiguous between two changes. #166's paired A/B measures 1b alone against the
shipped agent; #163 then branches off that `main` so its own delta is attributable to the survival
read. Folding #163 into #166 was rejected as exactly that confound, made worse by #163 now touching a
shipped decider. Rebasing #166 onto #163 was rejected for discarding a completed 24-frame sweep whose
6-FIX / 0-REGRESSION result would need re-gathering against a moving foundation. **Accepted cost:**
the agent ships the inflated bench-rescue credit for one issue's duration.

**10. Verification is unit pins plus re-derived existing pins — no corpus sweep, no paired A/B**
(user ruling, 2026-07-26). Pins: snipe indivisibility (the property a naive knapsack silently
violates), `POSSIBLE` vs `UNAVOIDABLE` on a tied bench, Tera exclusion (`rules.md` §11), empty
budget, the wincon tie-break, and the f82 bench shape. `tests/strategy/test_opponent_target_value.py`
(:76-83) asserts `turns_to_ko_me == 1` and `== 3`; under accumulation those move and MUST be
**re-derived by hand** from card facts with the derivation stated in the test — not updated to
whatever the new code prints (ADR-0070 amendment A: a number that cannot be derived is folklore).

**f82 does NOT become a corpus pin here.** Its decision is Turn-Planner scope (ADR-0070 amendment C,
tracked on #165); #163 pins its bench SHAPE as a unit test on the survival read, and asserts nothing
about the action taken.

## Amendments from the build

**A. `best_harvest` GENERALISES `best_ko_subset` rather than wrapping it.** Decision 2 described the
solver as *"enumerating snipe targets around the existing `best_ko_subset` knapsack"*. That shape
does not compose with decision 4: once the budget accumulates, each candidate subset has its own
post-snipe residual, so the knapsack's fixed-HP items are no longer the right items. The solver
enumerates subsets directly (bench ≤ 5, so ≤ 32) and, per subset, spends the indivisible units
greedily — largest unit onto largest remaining need, which is exact for equal-size units because
maximising `Σ min(unit·kᵢ, hpᵢ)` under a unit budget is separable and concave. `best_ko_subset` is
untouched and still serves the offensive side.

**B. f82's two strict xfails were PROMOTED to pins — ADR-0070 amendment C's premise was the
inflation itself.** That amendment recorded *"the evolve equation's standalone read is CORRECT (it
prefers the benched body, whose clocks genuinely move)"*. The clocks did **not** genuinely move: the
bench held two more bodies at 50 against a single 60 spread, so evolving one Dreepy out of range only
chose which body died. Measured here, the benched option falls from **37.5 to 25.0** against the
Active's **30.0**, and both bodies now read `ko = 2` — evolving buys exactly **zero** survival, with
the residual 25.0 coming from terms that are not the survival leg. The Pilot reaches the human's
answer with no lethal tier having landed, so the **CROSS-LAYER REQUIREMENT those xfails carried is
discharged**. The five-step maneuver is still the better play and still belongs to #165; what is
retired is the claim that the pin *depends* on it. (Same tripwire as f40 in #166 — a strict xfail
that XPASSes is the design telling you a premise moved.)

**C. The result must be SUBSTITUTED into the bench, not read alone.** Found during the build, and a
direct consequence of making survival sensitive to a body's company: `_evolve_decision` builds the
evolved form as `dict(raw, id=…)`, a COPY, so it is not the pre-evolution's bench entry. Read naively
the pre-evolution is scored among its bench-mates and the result in isolation — and the result then
looks fragile for no reason but being alone, which is a fact about the read, not about evolving. Both
sides now see the same bench with exactly one body swapped, which is ADR-0070's own
body-substituted-delta framing made true of the bench read. Pinned by
`test_a_bodys_survival_depends_on_the_company_it_keeps`.

**D. The promotion gate ships CALLER-PASSED and default-OPEN.** Decision 6 put the gate on
`incoming`, which could be read as applying it to every consumer. It must not: the gate makes a
threat read *less* pessimistic, and `CONTEXT.md`'s Threat Clock entry explicitly protects the
survival-critical worst-case path — *"it does NOT feed the survival-critical one-turn `active_doomed`
boolean, which stays worst-case — a hidden Ignition-class burst must never be under-counted"*. So
`opp_active` defaults to `None` (gate open, today's behaviour) and is opted into by the two ADR-0071
consumers. Same convention as `my_benched` and `reading`: the conservative answer is what an
undeclared caller gets.

**E. Decision 10's re-derivation found the existing pins UNCHANGED, and the reason matters.**
`test_opponent_target_value.py`'s `turns_to_ko_me == 1` / `== 3` survive accumulation — not by luck:
the fast attacker deals its whole 100 at `t=1`, and the slow one is cost-3 off 0 Energy so it deals
literally 0 at `t=1` and `t=2`, leaving the running sum `0 + 0 + 100` to first reach 100 at `t=3`.
Accumulation moves a pin only when an earlier turn contributes non-zero damage. The derivation is
written into the test so the numbers are not mistaken for untouched ones.

**F. The attack CHOICE is solved, not pre-filtered — decision 2's shape was unsound as written.**
The first build picked each turn's payload by the summed metric `_bench_rider` already uses, then
harvested with it. Adversarial review killed it: a 70-point single-target snipe outranks a 60-point
spread on that sum, yet the snipe fells one 20 HP body where the spread fells three. Selecting by a
proxy **understates** their reach — phantom bench safety on the `POSSIBLE` reading, precisely the
fail direction ADR-0070 §9 refused. Which attack they use is part of the allocation being solved, so
every affordable payload is scored and their own objective picks. `bench_harvest` therefore takes a
LIST of candidate payloads rather than one. Pinned by
`test_the_attack_choice_is_solved_not_pre_filtered_by_total_rider`.

**G. The seam names differ from decision 7, and one of its clauses is moot.** Shipped is
`_SideBase.bench_raws` (both sides, mirroring `body_raws`) rather than `StateModel.my_bench_raws` —
the fact is one side's, so it belongs on the side. Decision 7 also required memo keys to extend to
`(id(my_body), reading)`; they do not, because `TheirSide.turns_to_ko_me` is one-sided and therefore
cannot be bench-aware at all. It is left ACTIVE-only and labelled as such in the source, so a future
caller cannot mistake it for the harvest-aware read. `_affords` was extracted from
`_reach_form_damage` in the same spirit — one owner for affordability, since #163 added a second
consumer — and `_attacker_forms` likewise, after the duplicated enumeration had already drifted (the
rider read was skipping ADR-0064's `evo_min_energy` guard).

**H. The switch-enabler leg of decision 6 is NOT built.** It shipped first as a plumbed-but-never-
passed `switch_enabler` parameter, which is dead surface pretending to be a feature; it is removed.
The gate therefore reads retreat affordability only, and an opponent holding a `switch`/`gust` card
defeats it. Recorded below as exposure rather than left as an unused hook.

## Accepted exposure

Named so a later frame can point at them, rather than discovered:

- **`survival_shift`'s re-scaling ships unmeasured at the decider level.** Decisions 4-6 change the
  inputs to a shipped consumer (`pilot.py:6577` → `needs.opponent_target_value` → gust/KO-target
  selection), and decision 10's gates gate the *oracle*, not the *decider*. A gust-selection
  regression would not be caught by #163's own verification.
- **The prize-sacrificing opponent is un-modelled.** Decision 8's tie-break cannot represent an
  opponent who gives up a prize to kill an engine piece.
- **Ability-placed bench damage is invisible.** `_bench_rider` reads *attack* riders only; an Ability
  that places counters on the Bench contributes nothing to the payload. Pre-existing, fail-open,
  unchanged by this ADR and deliberately not smuggled into it.
- **A hidden switch card defeats the promotion gate** (amendment H). The gate reads their Active's
  retreat affordability, which is visible; whether they hold a `switch`/`gust` is not, and no Read
  signal is wired. A benched attacker they can promote for free therefore reads one turn further off
  than it is. Bounded: it affects only the two consumers that opt into the gate.
- **Asleep/Paralyzed on their Active is not read**, though it blocks retreat (`rules.md:167`) and
  would tighten the gate. `CombatMath` never receives the Board, which is where the condition signal
  lives (`opp_active_condition_gift`), so wiring it is a plumbing change this issue did not take.

## Consequences

- `turns_to_ko_me` changes meaning for BOTH areas and gains a `reading` parameter; its two direct
  callers (`pilot.py:6577`, `_evolve_side` at `pilot.py:1685`) must each state their claim.
- `incoming` gains the promotion gate on its body loop — a shared function, four reads, Active path
  included.
- `CombatMath` gains `bench_harvest`; `StateModel` gains `my_bench_raws`.
- The CONTEXT.md **Threat Clock** entry's promotion-surcharge sentence is corrected by decision 6,
  and its "accumulating over turns" clause becomes true of the code for the first time.
- The bench branch's consumers (1b, 1c, 1d) calibrate once, against a corrected read.

## Alternatives rejected

Recorded inline with each decision above: the fungible rider pool (2), the single Harvest Reading in
either direction and the argmax-probability (3), deferring the Active leg (4), the per-attacker race
and the rate model (5), the turn surcharge and the retreat-discard bookkeeping (6), the harvest
inside `incoming` and the Pilot-level assembly (7), body-count and damage objectives plus the
additive and derived wincon premiums (8), folding into or rebasing #166 (9), the full ADR-0069 swap
protocol (10).
