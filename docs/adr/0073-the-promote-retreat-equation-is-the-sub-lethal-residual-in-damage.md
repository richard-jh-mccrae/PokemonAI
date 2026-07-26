# ADR-0073: The promote/retreat equation is the sub-lethal residual, denominated in damage

**Status.** PROPOSED — grill in progress (`/grill-with-docs` on issue #141, Phase 1c of the Value
System, tracker #136). Decisions 1–3 are ruled by the user; further decisions are appended as the
grill settles them, and the status flips to Accepted when it closes. Companion vocabulary:
**Sub-lethal Residual · Prize Damage Rate** in the Agent Runtime
[`CONTEXT.md`](../../src/common/CONTEXT.md). The currency precedent is ADR-0070 decision 1 (#140);
the combiner discipline is ADR-0069 §1 (#139); the layer-ownership test is ADR-0070 amendment J /
**Commutative Set · Maneuver**; the shadow-era rulings this amends are the 2026-07-22 promote/retreat
grill (`docs/plans/promote-retreat-grill-spec.md`, six rulings).

## Context

`common/promote_retreat_value.py` shipped as a REPORTING-ONLY shadow beside the
`baseline_promote` / `baseline_retreat` rungs, emitted at two sites (`pilot._promote_retreat_shadow`
for the body PICK, `_retreat_action_value` for the whether-to-retreat question at MAIN). Standing
directive 1 of #136 forbids shadow staging: 1c must make it the real decider and DELETE the rungs it
replaces. Four offline sweeps (grill spec §Sweep #1–#4) left three obstacles, and grilling them
surfaced that two were misdiagnoses.

Facts that shaped the rulings (verified 2026-07-26 at source):

- `plan_turn` is **MAIN-only** (`planner.py:266`, gate at :283 — `context == _MAIN and maxCount == 1`;
  "every other context defers to the tuned scoring"). The forced promote after our Active is Knocked
  Out is a **TO_ACTIVE** select fired on the OPPONENT's turn: one atomic pick, no sequence.
- ADR-0070 amendment J: "Pricing is **upstream** of the planner: `_engine_leaf_value` builds its end
  state by re-running `decide` greedily, so a mis-priced option corrupts the leaf the planner would
  rank by." #136 defines #165 as composing the equations, "rather than replacing any of them".
- `_retreat_to_lethal_tactical` (`pilot.py:2685`) already prices the retreat-unlocks-a-better-KO
  lookahead, via `combat.best_affordable_ko_value` (:1332) = `KO_SCORE + prize − eff·cost +
  bench_snipe + bench_spread` — **no recover term**, so Mega Lucario ex's Aura Jab ({F} 130, "attach
  up to 3 Basic {F} Energy cards from your discard pile to your Benched Pokémon") ties with Solrock's
  Cosmic Beam ({F} 70) and the retreat is refused. The same rider IS credited on the attack option
  (`_tactical`: `+min(_RECOVER_KO_CAP, _RECOVER_KO·recover)`; `_recover_units` :4215 bounds it by
  printed ceiling, zone fuel, and recipient NEED).
- Prize value: `megaEx` **3**, `ex` **2**, regular **1** (`docs/rules.md` §6,
  `[PROJECT-VERIFIED: "Mega-ex = 2" refuted]`).
- Median HP-per-prize across the set = **100.0** (mean 101.8; per band 90 / 130 / 110), over 1061
  bodies in `data/EN_Card_Data.csv`.
- Card facts behind the worked frames: Drakloak (120) 90 HP, Dragon Headbutt {R}{P} 70; Budew (235)
  30 HP, **no retreat cost**, Itchy Pollen **no cost** 10 damage + "during your opponent's next turn,
  they can't play any Item cards from their hand"; Cinderace (666) 160 HP, 1 prize, Turbo Flare ● 50
  + "search your deck for up to 3 Basic Energy cards and attach them to your Benched Pokémon";
  Mega Starmie ex (1031) 330 HP, 3 prizes, Jetting Blow {W} 120 + 50 bench.

## Decision

**1. The equation is the SUB-LETHAL RESIDUAL, and the layers SUM on the option — the `active_can_ko`
recusal is deleted.**
Sweep #4 made the whether-site withdraw whenever the Active could Knock Out, on the evidence that
`82717711-37`'s correct retreat-to-finisher and `82750161-59`'s wrong pivot both scored `+30`. That
was a misdiagnosis: the equation was asked to carry a KO **delta** it structurally cannot see. Retreat
and promote are a three-part decision (whether · why · who), so each layer prices what it can see, on
the same option, and the parts add — the tactical KO lookahead's delta, plus the equation's sub-lethal
residual, with dependent step-chains held out to #165. The sum cannot double-pay because rulings 4/5
keep the residual strictly sub-lethal. Two structural facts make the alternatives unavailable: the
planner is MAIN-only, so "put the whole family under #165" leaves the forced promote with NO owner;
and the planner CONSUMES pricing, so delegating retreat pricing to it is circular.

**2. `stay_forgone` is DELETED — the option ranking IS the differential.**
Ruling 1 ("the forgone attack is an opportunity-cost subtraction, not a veto") was authored for a
standalone verdict read by its sign. As a per-option score it double-charges: at a MAIN menu the
Active's attack is its OWN option scoring `dmg − eff`, so subtracting `stay_yield` as well counts the
same forgone attack twice against retreating — and at the wrong magnitude, since `stay_yield` is a
`_READY = 40` band proxy rather than the attack's real damage. Ruling 1's substance survives; the
subtraction relocates from a term into the comparison, which is strictly more accurate. `retreat_cost`
stays (a real resource, not an opportunity cost). Consequence: the whether-site's `worth_it` sign bit
dies as an instrument and the sweep is rebuilt as a decider sweep — owed to ADR-0072 regardless.
Consequence: **Finding B2's "stay-to-develop" term may not need building.** Its regressions
(`81905522-47`, `82749168-61` — the attacker one attach from ready) exist because `stay_yield`
under-prices staying; under per-option scoring the ATTACH option carries its own 1a value, whose
`this_turn` is by ADR-0069 decision 2 "a true counterfactual under the full Attach Budget" — i.e.
exactly "one attach from ready" — and `_finish_turn_last` already sequences attach (tier 2) ahead of
retreat (tier 4). Measure before authoring a term.

**3. The residual is DAMAGE-denominated, at a DERIVED prize rate — one currency with 1a and 1b.**
The equation spoke three units at once (band constants `_READY`/`_ACT`/`_STALL`, prize units
`_PRIZE_UNIT = 12`, card Worth `ENERGY_TIER = 8`) and was internally incoherent: at `_PRIZE_UNIT = 12`
a ready wincon (`_READY = 40`) priced at 3.3 prizes. After decision 2 it competes head-on with attack
options priced in damage on the same `score`, so ADR-0070 decision 1 applies verbatim — "two units in
one `score` means every retune on either side silently re-opens the other". Therefore:
`my_yield`'s readiness legs become the body's real reachable damage
(`mine.best_reachable_damage(BodyView(B))`, the call `_evolve_side` already makes), retiring
`_READY` / `_ACT` / `_BEST_BONUS` and making f104's best-target fix EMERGENT rather than a `+5` bonus;
`their_yield` becomes `prizes × 100 × P(they KO B) × prize_map_weight` at the derived **Prize Damage
Rate**; retreat cost routes through ADR-0069 §5c's Worth→damage path. Three amendments the user's
counter-frames forced:

- **3a. The attack leg is KO-RACE-aware, not printed damage.** Drakloak's 70 into a 320 HP wall is a
  five-turn race; ADR-0040's `_race_attack_tactical` already exists because "vs a standing wall the
  single hit is fake value — price the SEQUENCE". Crediting face-value chip would lose the
  retreat-to-Budew frame.
- **3b. The accel dividend re-anchors on `_ENERGY_RECOVER`.** `_DIVIDEND = 5` is ~45× short of the
  `75`-per-Energy the SAME rider earns on the attack option, need-gated by `_recover_units`.
  Retreating INTO Cinderace must credit what attacking WITH Cinderace credits.
- **3c. `tempo_denied` is the one ASSERTED term, and is flagged as such.** Every other term now
  derives from card data or an existing oracle; "a denied Item turn ≈ one prize" does not (though it
  is what the shipped `_ITEM_LOCK_TEMPO = 12` = one `_PRIZE_UNIT` already claims, and
  `_item_lock_live`'s turn ≤ 3 gate already bounds its over-firing). It gets its own ruling.

The two frames that drove this, arithmetic in both currencies:

| frame | shipped (rung units) | ruled (damage) |
|---|---|---|
| Mega Starmie ex (3 prizes, 170 dmg) → Cinderace (1 prize, 50×2 Weakness + 3 accel) | `their_yield` 12, `my_yield` 15+5, preservation **0** → ≈ **+8**, loses to a ~120 attack — **stay (wrong)** | 100 dmg + accel dividend − 100 exposure **+ 300 preserved** — **retreat (right)** |
| Drakloak (90 HP, 70 dmg) → Budew (30 HP, 10 dmg + Item lock) | exposures cancel; `10 + 12` vs 70 — **stay (wrong)** | exposures cancel; `10 + 100` vs a five-turn-race-discounted 70 — **retreat (right)** |

**4. Exposure is PER-BODY, CLOCK-GRADED and AREA-CORRECT — `opp_can_punish` is retired.**
Decision 3 makes a 3-prize exposure worth 300 damage, which promotes `their_yield` to the equation's
largest term and its input to the least sound thing in it. `opp_can_punish = not
board.opp_cannot_punish_wincon` had three defects, all newly load-bearing: it is BOOLEAN (a 300-damage
cliff, where ADR-0070 §4 chose "continuous rather than a cliff"); it reads the WRONG BODY
(`_opp_cannot_punish_wincon` resolves `_best_promote_slot(me)` — my best benched wincon — and the
verdict is then applied to every candidate B, the survival-read transposition of #137's contract
hazard 1, "a Budget is PER-TARGET-BODY"); and it is matched-Read-only, failing to "punishable", so
every body pays full exposure against an unrecognised opponent. Therefore:

```
exposure(B)     = prizes(B) x 100 x _halve(turns_to_ko_me(B) - 1) x prize_map_weight
preservation(A) = prizes(A) x 100 x [ _halve(t_active(A) - 1) - _halve(t_bench(A) - 1) ]
```

`_halve` and `_HORIZON` are REUSED from `evolve_value` (ADR-0070 §6: "the shipped grading convention
— `deny_slot`'s `value / 2**t`, reused rather than a new decay rate invented for this equation"), so
**no new constants**; they move to a shared module now that two equations read them. The area reading
is what makes `preservation` honest: B arrives in the ACTIVE area (the ADR-0071 decision-4
accumulating clock), while A departs to the BENCH, whose leg is the **Bench Harvest** at
`HARVEST_UNAVOIDABLE` — the RESCUE reading, for the reason `_evolve_side` already gives: "a benched
knockout the opponent can simply redirect onto another body in range denies nothing; crediting it
inflates every bench rescue."

Two consequences fall out of card text rather than tuning. The doomed-Mega-Starmie frame needs **no
new term** — the identical KO cancels and the clock DIFFERENCE decides. And the **35 bench-immune
bodies** in this set (`"As long as this Pokémon is on your Bench, prevent all damage done to this
Pokémon by attacks"` — including Dragapult ex (121) and Cinderace ex (153), both in our decks) get
`t_bench = _HORIZON`, i.e. their full prize value as preservation credit: benched, they can only be
reached by a gust. TO VERIFY at build time, not assumed: that `bench_harvest` honours bench-Tera
immunity (`_is_tera` exists at `planner.py:1495` and `_snipe_tera_veto`, but the harvest path is
untraced).

## Consequences

- 1c is a rewrite of the equation's internals, not a two-term completion — but a NET SIMPLIFICATION:
  `_READY`, `_ACT`, `_BEST_BONUS`, `_DIVIDEND` and `_PRIZE_UNIT` are all retired in favour of one
  derived rate and calls to machinery that already exists and is already corpus-tested.
- The corpus re-rule surface is the whole promote/retreat family, not three regressions. Per #136
  directive 2 every flip is re-ruled with the user, never auto-conformed.
- A KO still dominates the residual by construction (`KO_SCORE = 1000` vs residual magnitudes in the
  low hundreds), so deleting the recusal cannot make the agent forfeit an available Knock-Out — the
  two Finding-B1 regressions stop regressing on magnitude, not on abstention.
- Frames whose value is a dependent step-chain are registered `HELD OUT` with `owner: #165`
  (ADR-0072 decisions 3–4), carrying their diagnosis. First entry: the Solrock-vs-Aura-Jab frame,
  invisible today because `best_affordable_ko_value` has no recover term, which a rollout gets for
  free through `_engine_leaf_value`'s wincon-Energy credit.
