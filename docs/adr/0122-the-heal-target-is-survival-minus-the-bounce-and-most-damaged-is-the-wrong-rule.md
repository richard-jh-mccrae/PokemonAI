# ADR-0122 - The HEAL target is SURVIVAL minus the BOUNCE, and "most damaged" is the wrong rule

**Status:** Accepted (Issue #409, 2026-08-06); BUILT. Does **not** amend ADR-0091/ADR-0103 — the
canonical-fingerprint tie-break stays exactly as specified; this removes a select from the set where
it was deciding *by default*. Does **not** touch ADR-0025's `baseline_heal` rungs (a different
question: whether to play, not which body).

## Context

`SelectContext.HEAL` (17) appeared **nowhere** in the strategy layer. Not as a named constant —
`src/common/strategy/context.py` defined `_DAMAGE = 15` and `_REMOVE_DAMAGE_COUNTER = 16` and then
jumped straight to `40` — not in any `Hypothesis.when`, not in any `*_tactical`, not in any decision
row. Measured on `44734ca5`: `grep -rn "_HEAL\b|== 17" src/common` returns **0 matches**, against a
positive control on `_REMOVE_DAMAGE_COUNTER` that finds its constant plus two live gates.

So at every HEAL target select `score = sum(fired) + tactical` was **0.0 on every option**, and
`_order_key` fell through to its third leg:

```python
return (-trace.score, not trace.attach_to_needy_line, canon, index)
```

`canon` is `option_equivalence.canonical_keys` — a serialized JSON board fragment, sorted
lexicographically. `option_fingerprint` writes `[area, card]`, `AreaType.ACTIVE` is 4 and `BENCH` is
5, so `"4" < "5"` and **the Pilot healed the Active on every board, for every heal card**. Not as a
policy anyone chose: as an artefact of string comparison. Same class of defect `_deploy_decision`
records for `_TO_BENCH` before Issue #261 item 2d.

**Two contexts remove damage from our own bodies and only one had a selector.**
`_best_counter_source_slot` has handled ctx 16 since the counter-mover work; nothing did the
equivalent for 17.

The corpus (all 377 committed parity traces): **15** ctx-17 steps, **11** of them forced (menu width
1) and **4** offering a real choice; Wally's Compassion ×14, Potion ×1; `minCount`/`maxCount` 1/1 on
every one. Six of the **thirteen** cards carrying a `kind: heal` clause in `card_effects.json` can
pose a multi-target select. *(Issue #409's body says "6 of the 14"; the store holds 13 — 1096, 1105,
1112, 1117, 1130, 1147, 1153, 1190, 1212, 1222, 1229, 1241, 1242 — and the issue's own table lists
13. The count is incidental to every ruling, but it is corrected here rather than carried forward.)*

## Decision

### 1. A context-gated TACTICAL, not an override

`_heal_target_tactical`, folded into `_option_trace`'s `tactical` sum beside `_denial_target_tactical`
(ctx 30), `_snipe_relevance_tactical` (ctx 15) and `_gust_target_tactical` (ctx 3). A fourth member of
an established family, and routing through `tactical` **preserves** `_order_key`'s canonical
tie-break rather than bypassing it. The ctx-16 override predates that family and is not extended.

### 2. The objective is SURVIVAL minus the BOUNCE — *not* most-damaged

```
heal_target_value(body) = survival_gain(body) − bounce_cost(body)
```

The ctx-16 rule ("our most-damaged body") is right there and wrong here, and the corpus shows why: at
`v2_ms_mirror_5000` f126 the most-damaged body **is** the Active (120 to the bench's 50), but healing
it under Wally's Compassion bounces its two attached Energy to hand, and `hold-clutch-heal`'s own
rationale is that the play works only when you *"heal, re-power, and still attack the same turn"*.
Most-damaged is a proxy that cannot see the rider. The two legs pull opposite ways by construction —
the Active has the most survival to gain and the most to lose by being stripped — which is exactly
why a one-dimensional rule cannot express the dilemma.

Every option at this select is a heal target, so the two legs are weighed only against each other:
the term is a pure argmax *within* the select and never competes with a scorer elsewhere.

### 3. REACH is the whole survival read, and the bench asymmetry is DERIVED

`survival_gain` = `prize_to_damage(prizes saved)` + `min(hp restored, reach)`, where `reach` is
`incoming(body)` at `Board.incoming_active_damage`'s own policy (`UNCHARGED`, `CURRENT_FORMS_ONLY`).

That one read is area-correct by construction. For the Active it is the opponent's biggest attack;
for a benched body `my_benched=True` routes `CombatMath.form_damage_vs` to the snipe/spread **riders
only** — printed damage always lands on the Active (ADR-0070 §9) — and to a flat 0 for a Tera. So *"a
benched body nobody can hit gains nothing from being healed"* is not an authored discount, it falls
out of a shipped read: reach 0 ⟹ the whole leg is 0.0.

The second term is the same *"score it by what it actually denies"* `_denial_target_tactical` is built
on, at the same 1.0 points per damage. The cap is what makes it a reading rather than a raw count: HP
restored beyond what can be taken back off this body buys nothing.

### 4. `needs.survival_value` was tried here and REJECTED, measured

Recorded because it is the obvious instrument and its failure is not obvious. On paper it is the
right one: the sub-prize turns-of-survival currency over the Δ on `turns_to_ko_me`, exactly as
`_hand_size_relief_tactical` reads it. Two things sank it, both on real corpus boards:

- Its `phase_scale` multiplier is `[0, 1]` and reaches **exactly 0** when I am comfortably ahead. At
  f126 (my 2 Prizes to their 6) it clamps to 0 — zeroing the only discriminator on the very frame
  this issue exists to fix and handing the pick straight back to the string sort. A scaler
  calibrated to stop survival outranking a **prize** has nothing to weigh at a select where every
  option is a heal target.
- The turns-Δ **inverts** the ranking it is asked for. A benched body is chipped for 50 a turn and an
  Active hit for 210, so healing the bench always buys more *turns*: at `v2_ms_mirror_5000` f82 it
  read the bench **90** to the Active's **15**, rewarding a body precisely for being hard to reach.

### 5. The body-generic readers, with the Active callers preserved

`_heal_candidate`, `_heal_averts_doom`, `_heal_restriction_ok` and `_condition_holds` were all
ACTIVE-ONLY — `_heal_candidate`'s docstring says so outright (*"this asks only what MY ACTIVE ends up
on"*). Each becomes the Active-spot reading of a body-generic core, so the two readings cannot drift:

| Active-spot wrapper | body-generic core |
|---|---|
| `_heal_candidate` | `_heal_body_candidate` |
| `_heal_averts_doom` | `_heal_body_averts_doom` |
| `_heal_restriction_ok` | `_heal_restriction_targets(..., is_active=)` |
| `_condition_holds` | `_condition_holds_for(..., cur_hp=, attached=)` |

`active_only` is the whole reason the restriction reader needed the flag: it is the one restriction
whose answer depends on where the body stands, and the Active-only form had to hardcode it `True`.

**This is a claim in Issue #409 that the build REFUTED, and it is recorded rather than quietly
worked around** — the failure mode a self-filed spec exists to produce. The issue's reusable-symbols
table rates `_heal_restriction_ok` *"**yes, body-generic already**"*. It is not: it answers `True`
for `active_only` unconditionally, which is right for its own caller and **wrong for every benched
candidate** — reused as-rated it would have offered a benched Cook / Lumiose Galette / Jumbo Ice
Cream target. The same table omits `_condition_holds` entirely, which was equally Active-only and
needed the same treatment. Two of the four generalisations in the table above were therefore
unplanned.

**Both `condition` gates are per-TARGET at the card text**, verified at source: 1190 Bianca's
Devotion is *"Heal all damage from 1 of your Pokémon that has 30 HP or less remaining"* — the HP
clause qualifies the chosen Pokémon, not the Active. Reading it off the Active while healing a
benched body answers a question about the wrong Pokémon.

**"Preserved bit-for-bit" is MEASURED, not asserted.** `_heal_candidate` used to check `mega_only`
inline and let every other restriction through; it now routes the shared reader, which additionally
refuses an unknown restriction and type-gates `psychic_only`. That is strictly more correct, and it
moves nothing today because **Wally's Compassion is the only `kind: heal` card in any shipped deck**
and its `mega_only` reads identically under both spellings. `test_heal_target.py` asserts that
census, so a deck that later fields Dragon Elixir or Jacinthe turns it red rather than drifting.

### 6. Fail CLOSED, and inherit rather than reopen

An unreadable restriction or an unevaluable condition contributes exactly **0.0**, never a guess —
the ordering then degrades to the previous behaviour rather than to a wrong answer. The legacy
`clutch_heal` Function-Tag fallback stays Active-only for the same reason: the tag records *"full
heal + Energy bounce"* and nothing about which bodies the card may reach, so on a benched candidate
it would be a guess at a restriction rather than a reading of one.

Issue #349's `each_of` / `amount_per` stay unread, **inherited** rather than re-litigated: an
`each_of` card heals every body and so poses no target select at all, which is why widening the
reading to a second area does not widen the question.

### 7. `combat.best_affordable_damage` extracted

`bounce_cost` is `best_affordable(E_before) − best_affordable(E_after)` — the deny oracle's own shape
(ADR-0062) pointed at my own body. That loop was **already spelled out twice**
(`_attach_lethal_tactical`'s inner `best_affordable`, `_gamble_det_baseline`'s scan), so a third
consumer was the moment to extract rather than copy: the count gate and the colour gate must stay in
lockstep, and a copy is free to gain one and not the other. Both prior sites now delegate.

`bounce_cost` is **0.0 for a benched body** — only the Active swings this turn. The `E_after` read
deliberately omits `body`, so post-bounce Energy counts as WILD: a bounce rider returns the cards to
hand and the re-attach may bring back any of the bounced types, which is what
`_stabilize_then_ko_lines` already states when it skips `body`.

## Consequences

**Validation is by construction plus unit assertions, and that is FORCED.** Measured over all 28
committed correction files: **372** ruled frames carry a select context and **zero** are ctx 17 (nor
ctx 16). So *"no ruled frame moves"* is vacuous here and cannot be the bar. What stands in for it:
the four real multi-option ctx-17 boards used as **constructed fixtures** — genuine engine output,
recorded `choice` **discarded**, because every trace's `meta.policy` is `chaos:seed=NNNN` and the
picks are noise — plus leg-by-leg assertions with positive controls.

**Two defects found in the build's own first cut, both by measurement:**

- The restore ceiling is the **body's `maxHp`**, not the card's printed HP. A Hero's Cape (+100) puts
  a 330-HP Mega Starmie ex on 430 and `amount: "all"` heals to that; the printed default under-healed
  `ms_mirror_1001` f90's caped Active by a full 100. It is a parameter, defaulting to the printed HP,
  so the Active callers stay where they were. **The Active path's own read of the printed HP is
  therefore still narrow, and that is left standing deliberately** — moving it would move the
  shipped survival consumers, which is outside this issue's scope.
- `needs.survival_value` (decision 4).

**A measured correction to Issue #409's own reading of f126.** The issue names it as *the*
discriminating frame because healing its Active bounces two attached Energy. On the real board that
costs **nothing**: the hand holds an Ignition Energy ({C}{C}{C} on an Evolution), so the one manual
attach still affords Nebula Beam's ●●● and `best_affordable(before) == best_affordable(after)`.
`bounce_cost` is 0.0 on all four real boards. The dilemma is real but the corpus does not contain it,
so the flip is demonstrated on f126's board with its two Ignition removed — one change, everything
else genuine engine output — where the term picks the **Bench** and the ctx-16 rule would pick the
Active.

That constructed board is also what makes the permutation test non-vacuous: `canonical_keys` picks
the Active on *every* board, so a fixture the equation also resolves to the Active would pass with
the term deleted. A mutation run (the ctx gate forced to `return 0.0`) fails **7** of the module's 23
tests.

**Measured:** Discrimination Gate **PASS** (0 unruled, 67 ruled, 3 voided). Decision Gate **PASS**,
**0 picks moved** — expected, since the term is gated on a context with no rulings, and now recorded
rather than assumed. `tests/strategy` 2523 passed.

**Still owed, and named rather than left silent:** no human ruling exists on any ctx-17 frame. The
four boards above are the natural first entries in `data/corrections/`, and until they are ruled this
term is validated by construction only.
