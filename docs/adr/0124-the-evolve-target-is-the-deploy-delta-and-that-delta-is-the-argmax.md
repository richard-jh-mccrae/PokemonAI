# ADR-0124 - The `EVOLVES_FROM` target is the DEPLOY DELTA, and the delta IS the argmax

**Status:** Accepted (Issue #417, 2026-08-06); BUILT. Reuses **ADR-0070**'s equation unchanged — no
new valuation, no new constant. Follows **ADR-0123** (the HEAL target, Issue #409) structurally and
deliberately: same family, same fail-closed discipline, same by-construction validation. Does **not**
amend ADR-0091/ADR-0103 — the canonical-fingerprint tie-break stays exactly as specified; this
removes one more select from the set where it was deciding *by default*.

## Context

`SelectContext.EVOLVES_FROM` (18) appeared **nowhere** in the strategy layer.
`src/common/strategy/context.py` ran `_HEAL = 17` straight into `_ABILITY = 10` / `_ATTACH_FROM = 21`;
no `Hypothesis.when`, no `*_tactical`, no decision row gated on 18 or 19. Measured on `0926eba`:
`grep -rn "_EVOLVES_FROM\|EVOLVES_FROM" src/common` returns **0 matches**, against a positive control
on `_HEAL` that finds its constant, `_heal_target_tactical`'s guard and its registration in
`_option_trace`.

Salvatore (1189) evolves a body straight out of the deck, bypassing hand — *"Search your deck for a
card that has no Abilities and evolves from 1 of your Pokémon, and put it onto that Pokémon to evolve
it"* (`data/EN_Card_Data.csv`, read at source). The engine poses two selects: `EVOLVES_TO` (19 —
which physical deck copy) and then `EVOLVES_FROM` (18 — which of my bodies receives it). On
`ms_mirror_1001` f15 that second menu is three Staryu, and nothing decided between them.

**Two shipped deciders look like they should cover this, and provably cannot.** `_evolve_decision`'s
guard is `ctx.option_type != _EVOLVE`, and `_EVOLVE` (9) is a MAIN-menu ACTION type; measured over
all 377 committed parity traces, **every one of the 12 options across the 7 ctx-18 steps carries
`OptionType.CARD` (3)**. So the decider abstains on every Salvatore target-select, unconditionally.
`_prefer_soonest_arming_evolve` carries the identical `type == _EVOLVE` gate, so its own docstring's
insight — *put the evolution where the Energy already is* — is exactly relevant here and exactly
unreachable here.

With every option at 0.0, `_order_key` fell through to its canonical-fingerprint leg: a
lexicographically sorted JSON board fragment whose first differing field is the AREA,
`AreaType.ACTIVE` 4 against `BENCH` 5. The same string-sort artefact ADR-0123 records for ctx 17.

**`ctx.card_id` is the wrong card here, and that is the trap.** At ctx 18 an option names the BODY,
so `_option_card_id` → `_option_pokemon` resolves the **pre-evolution** (1030 Staryu), not the
evolution being put down. The target rides on `select["contextCard"]["id"]` (1031 on all 7 corpus
steps) — the same field `_attach_value`'s `is_from` branch already reads its own context from. Any
reader that assumes `ctx.card_id` is "the card this option is about", as it is at MAIN, silently
compares each body against ITSELF and ranks every option at a flat zero delta *while looking like it
had priced them*.

## Decision

**1. A fifth context-gated target term, `_evolve_target_tactical`, folded into `_option_trace`'s
`tactical` sum** beside `_gust_target_tactical` (ctx 3), `_snipe_relevance_tactical` (15),
`_heal_target_tactical` (17) and `_denial_target_tactical` (30). A tactical rather than an override
returning `(area, index)`: routing through `tactical` PRESERVES `_order_key`'s canonical tie-break
(ADR-0103) instead of bypassing it.

Named for the CONTEXT, not for Salvatore's card id — any future card posing the same select shape is
covered for free.

**2. The value is `evolve_value` REUSED UNCHANGED — `deploy(R) − deploy(B)`, and no new equation.**
`evolve_value` is a pure function of two `EvolveBody` readings and nothing in it is MAIN-specific.
What the delta already carries is the survival dimension the mechanic creates: evolving keeps
attached cards **and damage counters** (`docs/rules.md` §4), so a *damaged* body arrives relatively
healthier — absolute damage fixed, ceiling jumped — which `EvolveBody.ko` reads off the body's actual
HP at damage time. Nothing extra to model.

**3. The DELTA is the argmax, and that is derived rather than inherited.** It would be easy to read
"delta" as a MAIN-menu habit carried into a select where the evolve is already forced. It is not.
Board value after picking body *i* is

    Σ_j deploy(B_j) + [ deploy(R_i) − deploy(B_i) ]

— the sum runs over every body I have and is CONSTANT across the menu, so `argmax_i delta_i` is
exactly `argmax_i` board value. The forced-ness of the evolve is what makes the delta the whole
decision rather than half of it.

**4. `income_gain` / `income_loss` stay at their `EvolveInputs` defaults, and that is a CARD fact.**
Salvatore's own clause carries `"no_ability": true` (`src/common/card_effects.json` 1189), so the
search target is guaranteed Ability-less and `ready_gain` is 0 **by the card's own restriction**, not
by an assumption about this deck. `ready_loss` is 0 for every body this deck can offer at ctx 18
(Staryu has no Ability). Flagged rather than silently assumed: a deck posing this select over an
Ability-BEARING pre-evolution owes `_evolve_income_delta` plumbing here, and the call site says so.

**5. A SIBLING function, not a widening of `_evolve_decision`'s gate.** That decider's return also
drives `_prefer_soonest_arming_evolve`'s ordering and rides as `evolve_working` on `OptionTrace` for
MAIN-menu telemetry; widening its gate would entangle two established, tested consumers with a select
neither was built to see. **But not a COPY either** — the body-substituted delta (five statements
with three load-bearing comments: the result inherits the Energy, the HP ceiling is the result
card's, and the hypothetical is SUBSTITUTED into the bench so R is not read in isolation) is
extracted to `_evolve_substitution` and called by both. Two hand-rolled copies of that are exactly
what ADR-0087 charges for. `_evolve_decision`'s gate, inputs and return are unchanged, verified by
the Decision Gate reading **byte-identical** before and after over all 371 frames.

**5a. The term takes `ctx`, unlike its ctx-17 sibling, and that asymmetry is deliberate.**
`Context.context_card_id` is the DECLARED store for `select.contextCard` (it already feeds
mega_lucario's ACTIVATE rungs), so the term reads it rather than minting a second walk of the same
JSON path — ADR-0087. `_heal_target_tactical` reads `select.effect.id` raw because **no `Context`
field exists for it**, so the two are not inconsistent; each reads the store where there is one.
`_snipe_relevance_tactical(obs, select, board, option, ctx)` is the shape precedent.

Two further divergences from the issue's literal A1 sketch, both deliberate: `is_active` is read as
`option.get("area") == _ACTIVE` (the sibling's own idiom) rather than the sketch's
`any(raw is p for p in me["active"])`, so it does not depend on object identity surviving the
snapshot; and the snapshot guard is `self._state_model is None` rather than a truthiness test.

**6. Fail CLOSED at 0.0** on an unreadable target (`contextCard` absent), an unresolvable option
body, or no snapshot — matching ADR-0123's R3. Every option then reads 0.0 and the ordering degrades
to today's behaviour rather than to a wrong answer.

**7. `EVOLVES_TO` (19) is MOOT for this card, MEASURED — and the measurement is a tripwire, not a
closure.** All 20 ctx-19 steps in the committed corpus offer `area=DECK` options only, and on every
multi-option menu the revealed candidates are physically distinct copies of ONE species. Picking
among interchangeable copies has no strategic content, so nothing was built. A deck running such a
search over a line with more than one legal target SPECIES needs a real term, and
`test_corpus_ctx19_is_moot_because_every_menu_is_copies_of_one_species` goes red the day one appears.

## Validation

**BY CONSTRUCTION, and that is forced rather than chosen.** Measured over the committed corrections:
**zero** ruled frames carry ctx 18 or ctx 19, so *"no ruled frame moves"* is vacuous here and cannot
be the bar — the same situation ADR-0123 faced. The substitute is that ADR's own, unchanged:

* the **seven real ctx-18 boards** in the parity corpus as constructed fixtures — genuine engine
  output, recorded `choice` DISCARDED because those traces run a randomised capture policy;
* unit assertions on the term's gate, its legs and its fail-closed floor, **each with a positive
  control**: every negative assertion runs against a real board that scores non-zero unmodified,
  because a 0.0 on a purely synthetic fixture proves nothing (`turns_to_afford` returns None without
  a real card table, `p_arrive` is then 0, and every leg collapses for reasons unrelated to the gate);
* both ADR-0072 gates PASS, and the Decision Gate diff is **byte-identical** with the change stashed
  and unstashed — 0 picks moved across the corpus, which is what item 5 above claims.

**The widest board's reading, recorded because it is what a ruling would be about.** On
`ms_mirror_1001` f15 (three Staryu: Active unenergised and doomed at `ko=1`, one benched Staryu
carrying 1 Energy, one empty) the term reads `[3.28, 0.0, 0.0]`. The Active wins on the survival leg
alone — evolving it into a 330-HP body is the only substitution that moves `p_survive` (0.125 →
0.250). **Both benched options tie at exactly 0.0, and the tie is a property of the equation rather
than a failure to look:** on the bench `p_survive` is already 1.0 for the pre-evolution, and
`turns_to_afford` is unchanged by the hop (Nebula Beam's ●●● leaves 2 Energy owed either way), so the
delta cancels on both. ⚠️ **Two consequences are OPEN and flagged rather than resolved here**: the
equation is PRIZE-BLIND by ADR-0070 §5, so putting a 3-prize Mega ex into a doomed Active spot is
priced only through `p_survive` and not through the prizes a knockout would hand over; and the bench
tie means `_prefer_soonest_arming_evolve`'s *"put it where the Energy is"* insight has nothing to
express at this select. Both need a developer ruling on f15, requested with the build and not
guessed at.

## Also in this issue (Part B): the `ATTACH_FROM` half was already built

Cinderace's Turbo Flare poses `ATTACH_TO` (22, which Energy) then `ATTACH_FROM` (21, which bench
body). **The second was NOT a gap**: `_attach_value`'s `is_from` branch (ADR-0069) has priced the
recipient by convex, typed slot-fraction progress since it shipped. Replayed through the live Pilot
against the three real human-ruled ctx-21 Cinderace frames, it agrees with the human on both frames whose
fields are self-consistent. ⚠️ **The issue's own "2 of 3 pass" framing overstates its evidence, and
the build corrects it:** only `83116081-21` is an unambiguous pass — it is the sole frame where the
human OVERRODE the agent (`correct [0]` against `chosen [1]`) and the live decider now lands on the
human's pick, which is also the harder direction (*concentrate onto the already-started body rather
than spread to a fresh one*). On `83007714-22` the record's `chosen` conflicts with its own
rationale, so how much agreement there is worth cannot be settled from the record. Ruling stands:
**no new production code**; the correctness is covered by regression tests
(`test_attach_decider.py` `_CORPUS`) rather than left observed once.

⚠️ **`82224509-31` carries a RATIONALE-vs-FIELDS conflict, reported and not adjudicated.** Its
`rationale` names the empty Staryu (*"Mega Starmie already had 3 basic energy, therefor should have
attached on the other benched mon without any energy"*) while its `correct` field records the
already-full Mega Starmie ex.

**It is NOT a schema violation, and the first draft of this ADR said it was — corrected here because
the difference changes what the developer is being asked.** ADR-0015 does specify that `correct`
*"must … differ from `chosen`"*, and here `correct == chosen == [0]`. But this repo has knowingly
declined to enforce that clause on MANDATORY selects:
`tests/train/test_unstatable_decline_records.py::test_a_mandatory_select_is_never_
excluded_even_when_chosen_equals_correct` rules the shape means *the pick was right*, its own docstring warns that
excluding those records "would blind the gate", and **14 committed records rely on that reading**
(re-measured through the Corpus Reader, not a raw JSONL walk: 17 records carry `chosen == correct`,
14 of them mandatory). So the shape alone settles nothing. What it does is SHARPEN the conflict — the
fields ENDORSE the agent's pick while the rationale CONDEMNS it and names the other body — and
exactly one of the 14 has that problem.

Three independent facts say `correct` is the stale field: the embedded `live_trace` (`chosen: [0]`,
a different artefact from either field), the rationale resolving unambiguously to bench index 1 (the
only body with an empty `energies` list), and the shipped decider already picking that body. No
ranking is asserted until a human re-rules it; `tests/train/test_correction_rationale_conflicts.py`
asserts the conflict so the coverage becomes OWED the moment it is fixed.

`ATTACH_TO` (22) is moot for this deck and MEASURED, not assumed: both real Turbo Flare ctx-22 steps
in the corpus are `minCount`/`maxCount` 0/3 over copies of a SINGLE Basic Energy card, so
`order[:max_count]` taking the first `min(3, offered)` is correct by construction; and
`attach-off-color-at-fixed-recipient` cannot fire on a mono-colour deck (mega_starmie's only Basic
Energy is Water — `deck.txt`, *9 Water Energy SVE 3*; Ignition is a Special and no Turbo Flare
target). Asserted **with its positive control**: the same board posed a Fighting Energy fires the
rung at its full −8, so the silence means something.
