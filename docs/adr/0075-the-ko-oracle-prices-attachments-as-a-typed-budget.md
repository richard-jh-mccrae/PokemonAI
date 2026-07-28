# ADR-0075: The KO oracle prices attachments as a typed Budget, once, for every line

**Status.** Accepted (grilled 2026-07-27, `/grill-with-docs` on issue #177 — seven locked
decisions). Build: #177. Extends **ADR-0067** (the Attach Budget's epistemic split) into the lethal
solver; extends and **amends ADR-0074 decision 3** (the Probability Leg, #175 — see decision 7);
constrains **ADR-0030 / ADR-0037** (the eager lethal solver) and **ADR-0052** (the one KO band);
gated by **ADR-0072** (mid-build swaps are gated by deterministic instruments).

**Renumbered 0074 → 0075 on rebase (2026-07-27).** #175's *A probability may WEIGHT a ranked value,
never GATE a lock* merged to `main` first and keeps 0074, per the README's first-merged rule. Both
were grilled the same day off the same #142 split; the collision was foreseen during this grill and
resolved mechanically.

**Context issues:** #177 (this build), #142 (Phase 1d — folded the composed pair and extracted
`attach_budget_for_card`), #175 (the depletion tail — **merged**, ADR-0074), #136
(the Value System tracker whose directive 6 ADR-0072 rewrote).

## Context

`_best_affordable_ko_value` — the one band every hypothetical attacker is priced on (ADR-0052) —
takes a **count** of Energy. Everything above it therefore had to answer "how much can I attach
this turn?" as an integer, and two different answers grew:

- `_play_accel_extra` (`planner.py:2735`): a min-bound flat `+1`, feeding **five** call sites via
  `accel_free` / `accel_sup`. It asserts one wild unit and cannot express a target restriction.
- `_composed_budget_units` (`planner.py:2684`, #142): builds the real **Attach Budget** for the
  candidate attacker, then collapses it to `int(Budget.size)` so it can be added to that same count.
  It serves the two composed builders (`_item_evolve_ko_candidate`, `_rare_candy_ko_candidate`).

Both lose the same thing at the same seam: the Budget knows which *colours* it can realise, and
`energy: int` cannot carry that. Downstream, `attack_type_payable` treats every unit beyond the
body's attached Energy as **wild** — *"each able to cover any one specific slot (fail-open)"*
(`combat.py:573`).

While the accel term was capped at 1 the fail-open cost at most one unit. #177 removes that cap —
which is one of the three things the fold is *for* (Rosa's Encouragement attaches up to 2 from the
discard). A `Budget.size` of 3 handed over as wild will pay a `{P}{P}{P}` cost off a discard pile
holding no `{P}` at all. **The fix, done as a count, manufactures the phantom KO it was meant to
remove** — and a phantom KO is the catastrophic error in this code (ADR-0030's eager solver commits
the turn around it).

The machinery to do it properly already shipped. `CombatMath.reachable_attach` (`combat.py:953`)
answers "can this body pay this attack this turn under this Budget" per-slot and per-option via
`_can_pay(slots, attached + option, budget.caps)`, honouring ADR-0067's capacity groups. Nothing
needed inventing; the lethal solver simply was not asking it.

### What #175 changed under this grill, and what it did not

ADR-0074 merged mid-grill. Its decision 3 states that *"`best_affordable_ko_value` gains a
typed-`Budget` entry point beside the int one"* and that the fold *"retires an independent latent
weakness: `_composed_budget_units` ... collapses a typed Budget to `Budget.size`."* **Neither
description matches the shipped code**, and this ADR records the gap rather than inheriting it:

- What shipped is `attack_p=None` (`combat.py:1515`) — a **probability callable**, not a typed
  affordability entry point. The affordability test is unchanged: `cost > energy` plus
  `attack_type_payable(..., wild_units=wild)`.
- `_composed_budget_units` is **still present** (`planner.py:2684`, still `int(budget.size)`).
  #175 added `_composed_budget` (the Budget object) and `_composed_attack_p` *beside* it.

The effect this ADR wants nevertheless half-exists, by a side door: `Budget.realising_p` returns
**0.0 when no assignment pays at all** (`combat.py:104`), and `val *= attack_p(aid)` then zeroes the
KO. So typed refusal does occur — **for the two composed call sites only, and only while
`deck_energy_p` is non-empty**. Decisions 6 and 7 close both halves of that gap.

## Decision 1 — the KO oracle takes a Budget, and affordability is typed

`best_affordable_ko_value` grows a `budget: Budget | None` leg. When a Budget is supplied, the
affordability test for each attack becomes

```
any(_can_pay(slots, attached + tuple(option), budget.caps) for option in budget.options)
```

with `slots = self._attack_slots(aid)` and `attached = self._attached_units(body)` — the same
predicate `reachable_attach` uses, so a famine read and a lethal read can never disagree about what
is payable. The `energy: int` leg stays for callers that genuinely have no Budget (the retreat scan
at `pilot.py:2991` and the tactical lookaheads); this is an added leg, not a replacement.

The oracle's existing two-object split is what makes this work for a *hypothetical* attacker:
attacks are read off `attacker_id`'s `CardStat` (the evolved form, not yet in play) while the
attached units come from `body` (the pre-evolution body that carries the Energy). `reachable_attach`
cannot be called directly for these lines, because it reads both from one body.

## Decision 2 — the Budget is authoritative and exclusive, and fails CLOSED

When `budget` is passed it is the whole affordability truth: the `cost > energy` gate and the
`attack_type_payable` call are both bypassed. `_can_pay` already subsumes the count (it returns
False when `len(units) < len(slots)`), and it is strictly stronger than the type guard, so a
conjunctive form buys nothing.

The two predicates have **opposite fail directions** and this decision picks `reachable_attach`'s:
an attack whose slots do not resolve is skipped and **makes no claim**, where `attack_type_payable`
returns True *"whenever the attack record doesn't resolve"*. That is the under-fire direction
ADR-0030's solver requires — the guarded failure is a phantom KO, and fail-open is exactly the wrong
way to be wrong about it.

**The divergence is verified inert on real data.** Both paths already fail closed when the record is
missing entirely (`attack_cost` defaults to 99; `_attack_slots` returns `()`). They part only on a
record that resolves with `cost == 0`, and `data/EN_Card_Data.csv` contains **no attack with a blank
or zero Cost** (checked 2026-07-27; the 454 `n/a` Cost rows are non-attack lines). So decision 2
costs no reachable KO line, and option "keep the fail-open escape" was rejected as an escape hatch
for a case that does not exist, bought at the price of two contracts inside one function.

## Decision 3 — "this line spends the Supporter slot" is a Budget quota, not builder bookkeeping

`StateModel.attach_budget_for_card` gains `supporter_spent: bool = False`, folded into the memo key
beside `manual_spent` / `provable` and passed down as
`supporter_played=self.supporter_played or supporter_spent`.

`combat.attach_budget` already takes `supporter_played` and already builds its play-sets off it
(`playsets = [items] + ([] if supporter_played else [items + [s] for s in supporters])`), so this is
a pass-through on the `StateModel` face — no clause-interpreter change.

It is **required**, not a convenience — but the rule for WHICH lines set it was corrected during
the build, and the shipped rule is narrower than this decision first stated.

**Ship rule: the Supporter leg is CLOSED unless this line's committed FIRST STEP is that
Supporter, and that Supporter is itself the Budget's energy source.**

| line | `supporter_spent` | why |
|---|---|---|
| retreat · evolve-the-Active · free-evolve | **True** | tiered free-or-cheap *because* they spend no card; their Budget must not include a Supporter's yield |
| `_supporter_ko_candidate` (Hilda, `tutor_energy`) | **False** | Hilda IS the line's energy source — measured on real cards, her Budget is size 1 with the leg open and **0** with it closed, so closing it makes the line structurally dead |
| `_tutor_evolve_ko_candidate` (Salvatore, `rush_evolve`) | **True** | no accel tag, so it contributes nothing to the Budget and merely SPENDS the slot |

The first row is what the build got wrong initially, and `planner_4298` (frame `83053965-28`)
caught it: with the leg open on the retreat line, a KO funded by Hilda's deck fetch was claimed by
`_retreat_ko_candidate` while tiered `_PLANNER_ENABLER_FREE` — "spends no card/slot" — so the plan
committed Retreat instead of the human-ruled Hilda. **That inverts ADR-0031's rule that an enabler
PRESERVING deck/slot resources outranks a tutor reaching the SAME KO**, and it is a hazard the fold
creates generically: the typed Budget enumerates every playable accel/tutor in hand, Supporters
included, so *every* line becomes potentially Supporter-funded unless told otherwise.

Double-counting is structurally impossible in the open case: each Supporter is a separate
alternative play-set, so a hand holding both Hilda and Crispin still yields size 1, never 2
(measured). `_retreat_ko_candidate`'s kwarg is keyword-only and **defaults True**, so the safe
reading is the one a new caller gets without thinking about it.

The rejected alternatives were filtering Supporters out of `hand_ids` (unreachable through the
primitive without reintroducing the hand-assembled-kwargs pattern #142's review pass deleted) and
post-filtering `Budget.options` (not viable — an option is a tuple of `AttachUnit` and carries no
provenance).

## Decision 4 — one pricing path for all seven KO lines; both adapters are deleted

`_play_accel_extra` **and** `_composed_budget_units` are removed. All seven call sites — the five
`_play_accel_extra` fed (retreat-KO, evolve-KO, free-evolve-KO, tutor-evolve-KO, supporter-KO) and
the two #142 folded (`_item_evolve_ko_candidate`, `_rare_candy_ko_candidate`) — pass a Budget built
for their own attacker.

Keeping the composed pair on `Budget.size` was rejected because the two paths point in **opposite**
directions, and that is not cosmetic. The typed path is strictly narrower than the wild one
(decision 1), so an evolved attacker reached through `_item_evolve_ko_candidate` would keep claiming
a KO on wild units that the *same board* reached through `_free_evolve_ko_candidate` correctly
refuses. Two builders, one board, opposite answers, permanently.

`_composed_budget_units` has no referent once the oracle takes a Budget: its entire body is
`int(model.mine.attach_budget_for_card(card_id, benched=benched).size)` — a lossy adapter to a shape
this ADR removes.

### The target body, per builder

Getting this wrong is silent, so it is recorded rather than left to the reader. `attacker_id` names
the card whose *attacks* are read; `body` carries the *attached* Energy; `benched` places the target
for a bench-restricted clause.

| builder | `attacker_id` | `body` | `benched` |
|---|---|---|---|
| `_retreat_ko_candidate` | the benched body itself | that body | True |
| `_evolve_ko_candidate` | the in-hand evolved form | my Active | False |
| `_free_evolve_ko_candidate` | the in-hand evolved form | `bench[inPlayIndex]` | True |
| `_tutor_evolve_ko_candidate` | the fetched evolution | the iterated body | per body |
| `_supporter_ko_candidate` | delegates to `_retreat_ko_candidate` | — | True |

`_tutor_evolve_ko_candidate` builds `bodies = active + bench` and **loses which is which**; it takes
the `[(p, False)] + [(p, True)]` tagging `_item_evolve_ko_candidate` already uses.

`benched=True` for the retreat lines is settled by the clause data, not by judgement:
`card_effects.json` models exactly three `accel` clauses — `any_pokemon/deck` (Crispin),
`stage2/discard/more_prizes` (Rosa's Encouragement), `benched/discard` (Wondrous Patch). **No accel
clause requires an Active target.** So `benched=True` is a strict superset of `benched=False` and it
names a real sequence: attach to the benched body, then retreat, then attack.

### The manual attach is subsumed, never added

The Budget already contains the turn's manual attach (`attach_budget`'s `energy_attached` leg), so
the fold **replaces** the caller's `extra + accel_*` term rather than stacking on it. #142's
precedent is `_item_evolve_ko_candidate`, which passes the Budget's units with no `extra`. Adding
them would double-count the manual attach.

## Decision 5 — the Decision Gate probe is lane-precise on the emitted KO lines

ADR-0072 decision 2 requires **both** deterministic gates, and #177's acceptance sketch names only
one. All three instruments apply, since #177 is a mid-build swap (a Phase 1d spin-off):

- **Decision Gate** — a new `tools/train/probes/lethal_ko_decider_sweep.py` on
  `attach_decider_sweep.py`'s pattern: two fresh Pilots per frame, OLD vs NEW, comparing the
  `TurnLine`s out of `_ko_for_prizes_lines` as `(goal, resolved first-step slot, prizes)`.
  Slot-resolved `(area, position)`, **never** the raw option index — that is
  `attach_decider_sweep.py`'s recorded lesson (frames `82523811-59`, `82750161-59`). Zero unruled
  `REGRESSION` frames.
- **Discrimination Gate** — `leaf_lab.py capture|diff` against the pinned
  `data/leaf_lab/baseline.json`, verdict via `tools/train/gates.py`. Zero unruled `OK → MISS` flips.
- **Tripwire** — `gauntlet_swap_ab.py --stage mid-build` (`paired_ab.py:mid_build_verdict`):
  `crashes == 0 AND ci_lo >= -0.05`, graded on the post-deletion code.

**Lane-precise, not whole-decision.** ADR-0072's finding 2 is the precedent and it cuts against the
obvious reading: `evolve_decider_sweep.py` *was* lane-precise, *was* structurally blind to
continuation collateral, and *"scored 0 REGRESSION honestly."* The remedy ADR-0072 chose was not to
widen the sweep — it was to add the corpus-wide second gate. The two gates are designed to have
complementary blindness, and duplicating one inside the other buys nothing.

The decisive case is the one only a lane-precise sweep sees. This fold is strictly narrowing, so it
removes KO claims that were **outranked anyway**: the line vanishes, the final pick is identical,
and a whole-decision comparison reports SAME. That population is exactly where the silent
target-body bugs live — the `benched` flags above and the `supporter_spent` quota — so those flips
must reach the ruling table.

**Consequence for the build shape.** Both code paths must be alive at once, so `_play_accel_extra`
and `_composed_budget_units` survive behind a flag until a separate deletion commit — ADR-0069 §8's
fold → sweep → delete shape, and the reason `attach_decider_sweep.py` records that *"zeroing rather
than deleting is what lets this run BEFORE the deletion commit."*

## Decision 6 — the five lines join the Probability Leg

ADR-0074 decision 1 rules that a consumer whose output is a **compared scalar** weights by the
probability. The five `_play_accel_extra` builders emit `TurnLine`s into the **same**
`ko_for_prizes` ladder as the two composed builders — but they pass no `attack_p`, so #175 left one
ladder ranking five unweighted lines against two weighted ones. A 2-prize retreat-KO scores full
`KO_SCORE` while a composed 2-prize line discounted to `0.87 ×` loses to it for no reason but wiring.

`_composed_attack_p` (`planner.py:2718`) generalises to serve all seven, built from the same
per-attacker Budget decision 4 already requires. This is not scope creep onto #177 — it is the
ranking inconsistency #175 created, and #177 is the only issue touching these five call sites.

The Win Rung still never calls it (ADR-0074 decision 1: a consumer that GATES may not read a
probability), and `_tutor_energy_certain` / `deck_definitely_has` remain its sound legs.

## Decision 7 — refusal and ranking are separate concerns, on separate parameters

`best_affordable_ko_value` carries **both**: `budget=` decides *whether* the KO is real (decisions 1
and 2 — `_can_pay` per option, unconditional, fail-CLOSED), and `attack_p=` decides *what it is
worth* (ADR-0074, weighted, ranked consumers only). An attack refused by `budget=` is **skipped**,
never merely multiplied by zero.

**This amends ADR-0074 decision 3.** The "typed-`Budget` entry point beside the int one" that
decision describes is what this ADR actually builds; what #175 shipped under that sentence is the
probability hook. The two documents are reconciled here rather than left to disagree.

**Why the emergent refusal is not enough.** Under #175 alone, a KO claim is refused only because a
**ranking** input happened to be populated: `attack_realising_p` returns `1.0` when `p_by_type` is
falsy (`combat.py:1484`) and `_composed_attack_p` returns `None` in the same case, so both fall back
to the wild fail-open path. That inverts ADR-0074's own Leg Assignment — whether an output *gates*
is supposed to select the leg, not whether an unrelated map is non-empty. A phantom KO would
reappear in precisely the states where the probability machinery goes quiet, which is the hardest
failure mode to find.

Separating them is also what makes the contract testable. Under one merged mechanism, "unpayable"
and "payable but 13 % likely" are both approximately `0.0` and no test can pin which property it is
asserting. Under two, each gets its own assertion.

**Accepted cost:** the two mechanisms must not double-count. The order is refuse-then-weight — an
attack that fails `_can_pay` never reaches the `attack_p` multiplication.

## Consequences

- The lethal solver and the famine oracle share one affordability predicate. A board on which
  `reachable_attach` says "cannot attack" can no longer also carry a lethal claim.
- The fold is **strictly narrowing**: it removes KO claims that exist today, some correctly (phantom
  KOs) and some not. Ruling those flips against ADR-0072's Decision Gate is the bulk of #177's work,
  and #142's green KO corpora re-enter the blast radius — the leaf-lab baseline is re-pinned *after*
  the fold, not before.
- `energy` and `budget` are mutually exclusive on `best_affordable_ko_value`. A required positional
  parameter that is ignored on one leg is a smell; the signature is settled in #177's spec.
- **The feared #175 collision did not materialise in code, only in ADR numbering.** #175 left
  `attach_budget_for_card` untouched (`state_model.py:579` still carries only `manual_spent` /
  `provable`), so decision 3's `supporter_spent` lands conflict-free. #175's title named the wrong
  instrument (`readiness_p`); its own grill corrected it to `p_contains` / `CountTriple.p_any`, and
  the leg it re-prices is `deck_energy_p`, not the one this ADR touches.
- ADR-0067's epistemic split is unchanged. This ADR changes *what the KO oracle is told*, not what
  the Budget believes: yield still fails closed, deck presence still fails open, and the depletion
  ramp stays priced by ADR-0074's Probability Leg.
- Two adapters die and one generalises: `_play_accel_extra` and `_composed_budget_units` are
  deleted; `_composed_attack_p` widens from two call sites to seven. `_composed_budget` survives as
  the shared Budget accessor both mechanisms read, so reach, refusal and probability can never be
  computed off different budgets.

## Build record (2026-07-28, #177)

Both deterministic gates ADR-0072 decision 2 mandates were run before the deletion commit, and
**both PASS**.

**Decision Gate** — `tools/train/probes/lethal_ko_decider_sweep.py`, lane-precise on the emitted
`ko_for_prizes` lines, OLD (`_play_accel_extra` + `_composed_budget_units`) vs NEW (typed Budget):

```
frames with a KO line: 32   agree: 31   flips: 1   errors: 0
FIX 0 · REGRESSION 0 · NARROWED 0 · DIVERGENT 1 · unlabelled 0
DECISION GATE: PASS  (zero unruled REGRESSION)
```

The single flip is `82749168-29` (mega_starmie, turn 6) and it is the fold working: NEW emits a
2-prize line OLD structurally cannot see. Salvatore evolves a benched Staryu into Mega Starmie ex
(Salvatore's printed text permits evolving a body put into play this turn) → Ignition Energy
attaches, providing `{C}{C}{C}` on an Evolution → free retreat (Cinderace, retreat 0) → Nebula Beam
`{C}{C}{C}` 210 ≥ Terapagos ex's 130 HP. OLD cannot reach it because `accel_sup` zeroes when
Salvatore is itself the enabling Supporter, leaving one wild unit — enough for Jetting Blow's 120,
ten short of the 130. **This is the "Hand Special Energy becomes visible" benefit #177 named**, and
it is target-conditional in a way a flat `+1` cannot express: Ignition's 3-unit provision applies
only to an Evolution, resolved against the *evolved* card's stats.

The frame's `correct` label was **re-ruled** with the user during this sitting (`correct=[2]` →
`[10]`, the Salvatore line) — the original tagging fixed the wasted Crushing Hammer but forgoed the
knockout. The turn is aggressive-correct because the hand holds a SECOND Ignition Energy plus two
Basic `{W}`, so spending the first (which discards at end of turn regardless) does not cost the
follow-up.

**Discrimination Gate** — `leaf_lab.py diff` against the pinned `data/leaf_lab/baseline.json`, with
the swap ON:

```
267 frames compared · gated on 264 · held out 3
GATE: PASS  (zero unruled OK->MISS; 0 unruled, 3 ruled)
```

The fold introduces **zero** new `OK → MISS` flips. The three held out are `main`'s own
pre-existing reds, ruled during this sitting and encoded in the Held-out Ledger rather than
absorbed: `85163634|1|decision|41` → **#143**, `86091435|0|decision|13` → **#189**, plus the
inherited `85164605|1|decision|41` → #145. That run also discharged the control measurement commit
`a127e81` asked for — *"run the gate on `main` BEFORE the next swap, not after it"* — confirming
both reds predate #177 and are deterministic (three independent process runs each), so they are not
#160's RNG.

Re-run on the FINAL post-deletion code it reads the same, and one more frame improved:
`82749168|1|decision|29` joins as `MISS → OK` — the frame whose label this sitting re-ruled, now
scored correct — for **6** improvements against 0 unruled regressions.

**Full suite:** 3920 passed, 2 skipped, 4 xfailed.

### The deletion exposed three latent defects, fixed here

Named because two would have stayed hidden indefinitely:

1. **`threat_shadow` was branch-dependent.** `explain`'s planner branch never emitted it; the
   non-planner branch always did. Invisible until the planner commits a line on a *pinned* frame —
   which this fold caused at `82749168-29`, blanking the shadow
   (`ms_doom_relax_bare_terapagos_f29`). A per-decision diagnostic must not depend on which branch
   decided, so the branch is fixed rather than the test.
2. **The enabler-cost tier was inverted by the fold**, caught by `planner_4298` (frame
   `83053965-28`). The Budget enumerates every playable accel/tutor in hand, Supporters included,
   so `_retreat_ko_candidate` could claim a KO funded by Hilda's fetch while tiered
   `_PLANNER_ENABLER_FREE` — "spends no card/slot". The plan then committed Retreat instead of the
   human-ruled Hilda. **The Supporter leg is now open only for the line whose committed FIRST STEP
   is that Supporter**: closed for retreat/evolve/free-evolve (tiered free-or-cheap precisely
   because they spend no card), open for `_supporter_ko_candidate` (Hilda IS its energy source —
   measured: her Budget is size 1 open, 0 closed), closed for `_tutor_evolve_ko_candidate`
   (Salvatore spends the slot and contributes no Energy). This restores ADR-0031's rule that an
   enabler PRESERVING deck/slot resources outranks a tutor reaching the SAME KO.
3. **Two energy-tutor tests were passing against a tutor that contributed nothing** — a Function
   Tag with no `CardStat`, and `_attach_contribution` rejects an unknown card *before* it reads
   tags (fail-CLOSED, ADR-0067). Their deck also held no Energy for a deck-sourced fetch to find.

Defect 2 is the one worth carrying forward: the Decision Gate did **not** catch it, because the
sweep compares only the KO-line frames in `data/corrections` and `planner_4298` is a fixture. A
lane-precise sweep bounded by the corrections corpus has that blind spot by construction.

**Still owed:** the mid-build **Tripwire** (`gauntlet_swap_ab.py --stage mid-build`,
`crashes == 0 AND ci_lo >= -0.05`). ADR-0072 decision 1 grades it on the post-deletion code, so it
runs against this commit range, not before it.

**One pin admitted rather than measured.** `mine.deck_energy_p` entered the leaf profile as a new
`KO_LINE_PROFILE` set on the argument that it is the THIRD projection of the same
`deck_energy_counts` derivation already pinned — a dict comprehension over an already-memoized map,
not a second walk over my zones. `test_the_leaf_profile_is_bounded_as_the_145_tripwire`'s own
message asks for a measurement against the 2-vCPU grader bank before re-pinning; that measurement
was argued, not taken, and the reasoning is recorded at the constant.

### What the deletion removed

`_play_accel_extra` and `_composed_budget_units` are gone, and with them two flags that had nothing
left to gate. `play_accel_lethal` had exactly one non-test consumer — `_play_accel_extra` itself.
`ko_budget_pricing` existed only so the sweep could compare both arms before this commit; with the
OLD path deleted there is no alternative branch, and a kill-switch that cannot switch is a lie, so
it is removed rather than armed-ON. That is the one place this build departs from the `evolve_value`
/ `attach_value` precedent, where OFF survives as documented *degraded mode* — here OFF would be
unreachable code.

`tests/strategy/test_play_accel_lethal.py` is deleted (it tests the retired `+1` semantics, and its
end-to-end cases build a bare `Board` with no `StateModel`, so they cannot be ported).
`tests/strategy/test_ko_budget_pricing.py` replaces it at the oracle seam, pinning typed refusal,
count subsumption, fail-closed-on-unresolvable-slots, and the refuse-then-weight separation.
`lethal_ko_decider_sweep.py` is deleted with its OLD arm — its record is this section.
