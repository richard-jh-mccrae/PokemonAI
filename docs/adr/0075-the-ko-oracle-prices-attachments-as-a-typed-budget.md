# ADR-0074: The KO oracle prices attachments as a typed Budget, once, for every line

**Status.** Accepted (grilled 2026-07-27, `/grill-with-docs` on issue #177 — four locked decisions;
the grill continues on instruments and sequencing, and this doc is amended as they land).
Build: #177. Extends **ADR-0067** (the Attach Budget's epistemic split) into the lethal solver;
constrains **ADR-0030 / ADR-0037** (the eager lethal solver) and **ADR-0052** (the one KO band);
gated by **ADR-0072** (mid-build swaps are gated by deterministic instruments).

**Context issues:** #177 (this build), #142 (Phase 1d — folded the composed pair and extracted
`attach_budget_for_card`), #175 (the depletion tail — re-prices the Budget's deck leg), #136
(the Value System tracker whose directive 6 ADR-0072 rewrote).

## Context

`_best_affordable_ko_value` — the one band every hypothetical attacker is priced on (ADR-0052) —
takes a **count** of Energy. Everything above it therefore had to answer "how much can I attach
this turn?" as an integer, and two different answers grew:

- `_play_accel_extra` (`planner.py:2556`): a min-bound flat `+1`, feeding **seven** call sites via
  `accel_free` / `accel_sup`. It asserts one wild unit and cannot express a target restriction.
- `_composed_budget_units` (`planner.py:2531`, #142): builds the real **Attach Budget** for the
  candidate attacker, then collapses it to `int(Budget.size)` so it can be added to that same count.

Both lose the same thing at the same seam: the Budget knows which *colours* it can realise, and
`energy: int` cannot carry that. Downstream, `attack_type_payable` treats every unit beyond the
body's attached Energy as **wild** — *"each able to cover any one specific slot (fail-open)"*
(`combat.py:490`).

While the accel term was capped at 1 the fail-open cost at most one unit. #177 removes that cap —
which is one of the three things the fold is *for* (Rosa's Encouragement attaches up to 2 from the
discard). A `Budget.size` of 3 handed over as wild will pay a `{P}{P}{P}` cost off a discard pile
holding no `{P}` at all. **The fix, done as a count, manufactures the phantom KO it was meant to
remove** — and a phantom KO is the catastrophic error in this code (ADR-0030's eager solver commits
the turn around it).

The machinery to do it properly already shipped. `CombatMath.reachable_attach` (`combat.py:864`)
answers "can this body pay this attack this turn under this Budget" per-slot and per-option via
`_can_pay(slots, attached + option, budget.caps)`, honouring ADR-0067's capacity groups. Nothing
needed inventing; the lethal solver simply was not asking it.

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

It is **required**, not a convenience. Two of the five folded builders play a Supporter *as their
enabling step* — `_tutor_evolve_ko_candidate` (Salvatore, `rush_evolve`) and
`_supporter_ko_candidate` (Hilda, `tutor_energy`) — which is precisely what
`_play_accel_extra`'s `enabler_consumes_supporter=True` encoded. `attach_budget_for_card` reads
`supporter_played` off the *board*, so without this kwarg the Budget offers Crispin's Supporter
play-set alongside Hilda's: two Supporters in one turn, an illegal line, a phantom KO, and silent.

The shape mirrors `manual_spent` one quota over, and inherits its property — it only ever removes
play-sets, so every existing caller is unchanged and the memo stays exact. The rejected alternatives
were filtering Supporters out of `hand_ids` (unreachable through the primitive without
reintroducing the hand-assembled-kwargs pattern #142's review pass deleted) and post-filtering
`Budget.options` (not viable — an option is a tuple of `AttachUnit` and carries no provenance).

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

`_tutor_evolve_ko_candidate` builds `bodies = active + bench` (`planner.py:2802`) and **loses which
is which**; it takes the `[(p, False)] + [(p, True)]` tagging `_item_evolve_ko_candidate` already
uses (`planner.py:2698`).

`benched=True` for the retreat lines is settled by the clause data, not by judgement:
`card_effects.json` models exactly three `accel` clauses — `any_pokemon/deck` (Crispin),
`stage2/discard/more_prizes` (Rosa's Encouragement), `benched/discard` (Wondrous Patch). **No accel
clause requires an Active target.** So `benched=True` is a strict superset of `benched=False` and it
names a real sequence: attach to the benched body, then retreat, then attack.

### The manual attach is subsumed, never added

The Budget already contains the turn's manual attach (`attach_budget`'s `energy_attached` leg), so
the fold **replaces** the caller's `extra + accel_*` term rather than stacking on it. #142's
precedent is `planner.py:2655`, which passes the Budget's units with no `extra`. Adding them would
double-count the manual attach.

## Consequences

- The lethal solver and the famine oracle share one affordability predicate. A board on which
  `reachable_attach` says "cannot attack" can no longer also carry a lethal claim.
- The fold is **strictly narrowing**: it removes KO claims that exist today, some correctly (phantom
  KOs) and some not. Ruling those flips against ADR-0072's Decision Gate is the bulk of #177's work,
  and #142's green KO corpora re-enter the blast radius — the leaf-lab baseline is re-pinned *after*
  the fold, not before.
- `energy` and `budget` are mutually exclusive on `best_affordable_ko_value`. A required positional
  parameter that is ignored on one leg is a smell; the signature is settled in #177's spec.
- **#175 is reframed.** Its acceptance sketch names "the composed-line accel priced by
  `readiness_p`", and that accel is `_composed_budget_units`, which decision 4 deletes. The
  `readiness_p` ruling lands on the **Budget's deck leg** (`provable=` / `deck_energy_types`, inside
  `attach_budget_for_card`) instead — which is where #175's own scope item 4 already points ("*the
  ruling should be made once for the class*"). Both issues now edit `attach_budget_for_card`:
  #177 adds `supporter_spent`, #175 re-prices the deck leg.
- ADR-0067's epistemic split is unchanged. This ADR changes *what the KO oracle is told*, not what
  the Budget believes: yield still fails closed, deck presence still fails open, and the depletion
  tail is still #175's.
