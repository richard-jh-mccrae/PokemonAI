# ADR-0125 - The Energy PROVISION is ONE seam, and the EXPIRY ships with it or not at all

**Status:** Accepted (Issue #418, 2026-08-06); BUILT. Discharges the paragraph
**ADR-0069 §5** left open and **`CombatMath.without_expiring_energy`**'s docstring named and declined
(Issue #286): *"It is NOT the codebase's only reading of that quantity… folding those three into it
would move `attach_value`, which is not this issue's to move."* This is the issue that moves it, and
the count was **four**, not three. Extends **ADR-0087** (one store per fact) to the provision;
applies **ADR-0067** (fail-closed) at two contracts rather than one; consumes **ADR-0032**'s
parametric tags unchanged — **no card data moved**. Lifts the freeze **ADR-0124** placed on
`_evolve_substitution`'s two model limits, for the first of the two only.

## Context

*"How many units does this Energy card provide this body, in what colour, and does it survive the
turn?"* is ONE question. Measured on `e8141b8`, the tree answered it **six** ways. (Issue #418's
body says *"FIVE answers"* and then enumerates two plus four. Every defect it names is real and
verified below; the count in that one sentence is not.)

Two composed the declared accessors — the colour from `CardStat.energyType`, the count from
`CardFunctions.energy_provision` — and were right: `board_delta._provided_units` (the apply seam)
and `CombatMath._special_energy_groups` (the Attach Budget's hand leg). Four hardcoded *three units
on an Evolution holding a `discard_eot` card, one otherwise*:

| site | what it computed |
|---|---|
| `pilot._attach_provision` | `if burst and evolvesFrom: return 3` / `return 1` |
| `pilot._attach_lethal_tactical` | the same rule inline, plus a SEPARATE `energyType` read |
| `planner._attach_provided` | the same rule inline |
| `planner._best_hand_attach_units` | the same rule inline, over the hand |

**The hardcode is right only by a coincidence of the shipped pool.** Swept over
`src/common/card_functions.json`, exactly three cards carry a provision tag — Boomerang Energy (9)
`provides:1`, Ignition Energy (17) `discard_eot` + `provides:1` + `provides_evo:3`, Telepath Psychic
Energy (19) `provides:1` — so Ignition is the **only** card carrying either `discard_eot` or
`provides_evo`, and it carries both. The two predicates coincide on exactly one row. A card with
`provides_evo` and no rider would have read 1 where it prints N; a `discard_eot` card that is not
three-on-evolution would have read 3 where it prints 2. No test over the shipped pool could catch
either, which is why `tests/strategy/test_provision_seam.py` runs two synthetic cards.

### The over-read that was live

`MySide.best_reachable_damage`'s hypothetical leg was named `extra_energy_ids` and appended straight
onto `energies` — which is a list of `EnergyType` UNIT codes and **not** a fifth card list
(`common/board_cards.py`, Issue #297). Every caller fed it CARD ids:

```python
mine.best_reachable_damage(view, extra_energy_ids=(ecid,) * units)   # pilot._attach_value
```

For a Basic Energy the two coincide — Basic {W} is card 3 and `WATER` is 3 — and the lie is
invisible. Card 17 is not an `EnergyType` at all, so `unit_colours` falls through to the empty set,
which this module reads as **WILD — Energy that pays every slot**:

```
unit_colours(0)  -> frozenset({0})   colourless: pays {C} slots only
unit_colours(17) -> frozenset()      WILD: pays anything
```

Measured on a bare Mega Starmie ex (Jetting Blow **{W}** 120, Nebula Beam ●●● 210): `energies=[17]`
reads Jetting Blow as payable for **120.0**, where the engine's own `[0]` reads **0.0**.
`_attach_lethal_tactical`'s own comment states the rule this violated — *"Ignition can't fund Jetting
Blow's {W}"*. Corpus-wide the issue measured 42 ruled options over-reading `this_turn = 20.0` against
a truth of 0.0, every one an Ignition onto a Staryu.

Two sites the issue did not name carried the same defect and are fixed here: `_burst_capped_tonight`
passed the reusable alternative's card id, and `_reusable_energy_id` admits typed **Special** Energy
(Telepath Psychic is card 19, which resolves to no colour at all); and `TheirSide._recur_energy_ids`
appended Basic-Energy card ids, safe only through the id/type coincidence and documented with a
reason — *"the clock's typed leg matches… by card identity"* — that was not true of `energies`.

### The evolve decider re-derived nothing

`_evolve_substitution` built the hypothetical evolved body as `dict(raw, id=target_cid)`, copying
`energies` verbatim. The apply seam for the very same substitution has always re-derived it
(`board_delta._evolve`), and even carries a self-check that refuses when the provision model
disagrees with the engine. Measured: `grep -n "onto_evolution\|energy_provision" src/common/pilot.py
src/common/strategy/planner.py` → **0 matches**, against a positive control on `board_delta.py` and
`combat.py` that both hit. Neither the Pilot nor the planner had any reading of the evolution clause.

## Decision

**1 — `CombatMath.provision_codes(card_id, holder_stat)` is the single provision reader.** It
returns the `EnergyType` UNIT codes attaching this Energy CARD puts on `energies`, for THIS holder.
The oracle already owned `attach_units`, `_attached_units`, `_special_energy_groups` and
`without_expiring_energy`; the provision belongs beside them. `board_delta._provided_units` was
**moved**, not rewritten — its fail-closed behaviour and its worked Ignition example carry over
intact — and `board_delta` keeps `units_for_cards` as the plural wrapper.

The holder's `CardStat` is the argument rather than an `onto_evolution` boolean, because the
provision is a property of the holder and every caller was deriving the same
`bool(getattr(stat, "evolvesFrom", None))` for itself.

**2 — Three answers, and they are three different facts.** `(code, …)` is the provision;
`()` is a CLAIM of zero (a Pokémon Tool rides `OptionType.ATTACH` too and provides nothing);
`None` is UNREADABLE (ADR-0067). The Tool test is positively `is_tool` rather than
`not is_energy`, because `cardType` is the one `CardStat` field a hand-built board routinely omits
and reading its absence as *"not Energy"* would zero the provision on a board that is merely
under-described.

**3 — Two contracts on one composition.** The apply seam turns `None` into `Unmodellable` — a board
write must refuse rather than guess, and `tools/train/choice_parity.py` records 12 corpus refusals
that are exactly this. The DECIDER cannot refuse: an option must be priced and ordered whatever the
compendium knows, and an attach priced at zero units reads as *"this attach does nothing"*, which is
a confident and wrong claim about a legal play. So `provision_codes_or_floor` substitutes **one
unit** — of the card's own colour when the stat gives one, `WILD_CODE` (`EnergyType.RAINBOW`, which
`unit_colours` already resolves to the wild set) when it does not. One unit, never the
`discard_eot`-shaped guess at three, and both halves reproduce what the retired hardcodes did on the
cards they could not read.

**4 — `extra_energy_ids` is renamed `extra_unit_codes` and re-typed.** A parameter whose name lies
about its contents is not fixed by a comment. Every caller now passes `provision_codes(...)`, which
answers in the engine's vocabulary by construction. `_recur_energy_ids` became `_recur_unit_codes`
and returns `energyType` codes; each code is still SOURCED from a real card in the public discard,
so the reading is unchanged and only the vocabulary is honest.

**5 — `pilot._attach_provision` is DELETED rather than re-pointed.** It took `(target_stat, burst)`
and could not express the colour, which is half the fact — and the half that decides whether the
provision pays the attack it is being credited for. ADR-0069 §5's ruling (the PRINTED provision is a
card fact, never falsified by a valuation heuristic) is unchanged and now lives on the seam.

**6 — `_evolve_substitution` re-derives the result's `energies` through
`CombatMath.restage_energy`**, the body→body sibling of `without_expiring_energy`. It carries the
apply seam's self-check as a DECLINE rather than a refusal: the body comes back **by identity**
whenever the cards cannot be re-derived or the model already disagrees with the board as it stands.
Compounding a provision error we can already see is worse than the under-read it would replace.

**7 — RULED 2026-08-06: `_evolve_side` excludes expiring Energy on BOTH the BODY and the RESULT.**
Developer's ruling, in the terms it was given: *"attaching a vanishing energy to a Pokémon that won't
attack this turn is worthless — worse than worthless, it's negative value, because it wastes the
card."* That applies identically to a body's own forward-readiness clock. `turns_to_afford` is a
FORWARD clock and `MySide.turns_to_afford`'s own docstring already states the rule: *"A FORWARD clock
counting an Energy that will not be there is not conservative, it is wrong."*

### The sequencing constraint, MEASURED

`ms_mirror_1001` f15 bench 0 — a Staryu carrying one Ignition, evolving into Mega Starmie ex, with
bench 1 an otherwise-identical Ignition-less Staryu as the control. All four builds measured on this
branch by substituting the two legs and replaying the frame:

| build | BENCH0 `R.energies` | BENCH0 `B.arm` / `R.arm` | BENCH0 **delta** | BENCH1 delta (control) | ACTIVE delta |
|---|---|---|---|---|---|
| SHIPPED (D3/D4 unfixed) | `[0]` | 2 / 2 | 0.00 | 0.00 | 3.28 |
| **D3 alone** (provision, no expiry) | `[0, 0, 0]` | 2 / **0** | **+157.50** | 0.00 | 3.28 |
| D3 + D4, **RESULT-only** exclusion | `[0, 0, 0]` | 2 / 3 | **−26.25** | 0.00 | 3.28 |
| D3 + D4, **RULED — both sides** | `[0, 0, 0]` | **3 / 3** | **0.00** | 0.00 | 3.28 |

Two rejected alternatives, each recorded because each is a *worse* build than the one that shipped:

* **D3 alone is far worse than the bug it fixes.** Three colourless units are exactly Nebula Beam's
  ●●●, so the evolved body reads *armed now* — delta **+157.50**, the largest number on the menu —
  when the body is BENCHED and cannot attack this turn, and the Ignition is discarded before the
  next one. The truth is three attaches owed. Fixing the provision without the expiry replaces an
  under-read with an over-read six times its size. **They ship together or not at all.**
* **The asymmetric (result-only) fix is a NEW bug, not a partial fix.** It judges the post-evolution
  honestly while still crediting the pre-evolution's vanishing card as forward progress, and the
  mismatch reads as a PENALTY for evolving: **−26.25**, the worst score on the whole menu, for a
  substitution that changes nothing except which body an already-present, already-expiring Energy
  sits on. The ruled build returns bench 0 to a clean **tie** with bench 1 — correct, since once the
  Ignition cannot be trusted for the future the two Staryu ARE identical for this decider — while
  leaving ACTIVE's delta untouched at 3.28, which confirms the fix is targeted and not a blanket
  zeroing. Pinned as a NEGATIVE test
  (`test_the_result_only_exclusion_regression_is_structurally_unreachable`), asserted on the SHAPE —
  no option may score a large-magnitude negative, and no two bodies differing only in an expiring
  Energy may be priced apart — so it survives a re-tuned payoff.

**8 — `_attach_value`'s `this_turn` stays expiry-blind, and the asymmetry is stated rather than
inherited.** `this_turn` counts the Ignition in full when it IS cashable this turn (correct — the
Cinderace/Turbo Flare line, where a same-turn attach fetches three permanent Basic Energy, is a clean
win), while `build` blanket-zeroes for any burst regardless of cashability. Two mechanisms answering
two different questions about the same card in the same term. Neither is this ADR's to move: the
turn-1-going-first Ignition waste the R4 ruling cited as precedent is ALREADY priced, and priced as
strictly negative rather than merely zero, by `_attach_value`'s `evaporation_loss` term (ADR-0069
§7), pinned by `test_an_uncashable_burst_scores_below_ending_the_turn` and
`test_a_benched_burst_evaporates_and_banks_no_channel`. That mechanism prices the ATTACH decision;
R4 prices a body's FORWARD readiness after the Energy is already attached.

**9 — No card data moved.** `card_functions.json`, `card_effects.json` and `card_tags.py` were
already correct and complete. This is entirely a READER consolidation.

## Consequences

**Blast radius: zero ruled decisions, measured with a positive control.** Both ADR-0072 gates were
captured on clean `e8141b8` and re-run against this branch, which isolates this change from the
drift already sitting between `main` and the committed baselines:

```
DECISION GATE      375 frames   agree 255/343 -> 255/343   0 picks moved   PASS
DISCRIMINATION     268 frames   agree 127/244 -> 127/244   0 picks moved   PASS
```

A silent no-op patch reports the same zero, so the instruments were controlled: falsifying
`provision_codes` to return one unit for every Special Energy moves **3** decider picks and **4** leaf
picks and turns BOTH gates red with unruled regressions. The zero is real. Neither baseline was
re-captured, and no ruling was owed.

Why zero, given that f15 moves by a full turn: every ctx-18 frame is unruled (`test_no_ruled_frame_
carries_ctx_18_or_19`), and the D2 phantom `+20` lands on options that lose anyway — a Staryu's Water
Gun never beats the alternatives on the boards that carry it. **The defect was LATENT, not
harmless**: `_attach_lethal_tactical` is a KO_SCORE-class term reading exactly this class of
quantity, and 20 damage decides a lethal on a board the corpus has not yet captured.

**The acceptance grep is a weak instrument, and is recorded as one.** Issue #418's item 2 asks that
`grep -rn "discard_eot.*else 1\|3 if .*is_evo" src/` return zero, *"positive control: the same grep on
the pre-fix tree finds four"*. It did find four — but the four were three code sites and a
**docstring**. It never matched `_attach_provision`, whose rule is spelled
`if burst and evolvesFrom: return 3` across two statements, so the grep could not see the very site
D1 names first. The criterion is met and the docstrings that carried the literal were reworded rather
than left to satisfy it falsely, but the guarantee that all four sites are gone comes from reading
them, not from the grep. What actually holds the line is
`test_provision_seam.py` plus the one-call-site property: `CardFunctions.energy_provision` is now
invoked from exactly one place in `src/`.

**One latent disagreement closed on the way.** `_special_energy_groups` and `attach_units` spelled
their colour pool `frozenset({etype})` while `_attached_units` used `unit_colours` — so the hand leg
and the board leg disagreed for `RAINBOW` (a real pool code: Neo Upper 10, Legacy 12, Prism 16 all
print `{A}`) and `TEAM_ROCKET` (Team Rocket's Energy 15). That is the Issue #297 split one door over,
made unreachable today only because none of those five cards carries a `provides:N` tag. Both legs now
run through `units_for_codes`, and `_special_energy_groups`' claim that *"colour follows
`_attached_units` exactly"* is a fact instead of a promise.

**Test fixtures gained their real card facts, and now have ONE copy of them.** Fifteen fixtures
tagged Ignition Energy `["discard_eot"]` alone — asserting a card fact that is not true, and
invisible only because a hardcode was supplying the 3 the missing `provides_evo:3` should have.
Rather than paste the committed triple into seventeen files (the same one-store-per-fact failure this
ADR is about, one layer down), it lives once in **`tests/card_facts.py`** as
`IGNITION_TAGS`/`ignition_tags()`, checked against the store by
`test_the_committed_tags_are_what_the_shared_fixture_claims`. It is a LITERAL rather than a read of
`card_functions.json`, because a constant that loaded the store could only ever agree with it and
would make that assertion vacuous. Two fixtures are deliberately incomplete and say so in their
names: the fail-closed probe `test_an_untagged_special_energy_provides_nothing` and the tag-vs-clause
probe `test_the_strip_reads_the_CLAUSE_not_the_TAG`.

**`attack_type_payable`'s typed-EXTRA leg now reads `unit_colours` too.** It tested
`extra_type not in (None, 0)`, which is *"names one specific colour"* by arithmetic accident rather
than by construction — fine while every caller passed a card's raw `energyType`, and worth making
structural now that `provision_codes_or_floor` can hand that leg `WILD_CODE`. The new test is
`len(unit_colours(extra_type) - {0}) == 1`, which is **behaviour-identical on every code the enum
has**: COLORLESS resolves to `{0}` (which `need` has already filtered out), and RAINBOW,
TEAM_ROCKET and an unknown code each named a `Counter` key `need` never queries, so all four
contributed nothing before and contribute nothing now. The paragraph the method already carries
about an ATTACHED unit that "names no single colour" now describes both of its legs.

**What this does not touch.** `payoff_damage` still pre-credits a pre-evolution with its whole line's
payoff — the second of ADR-0124's two recorded model limits, and the reason both bench deltas cancel
on f15 even after this change. It remains frozen.
