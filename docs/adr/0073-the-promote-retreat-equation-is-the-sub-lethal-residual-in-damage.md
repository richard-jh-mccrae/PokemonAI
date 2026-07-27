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

**5. `fetch_enables_p` is retired into a Δ`readiness_p` term, shaped like ADR-0070 decision 3.**
Decision 3 already subsumes the CERTAIN half — `best_reachable_damage` is Budget-aware — so the only
thing left to build is the probabilistic middle, and 1b shipped that shape one phase ago:

```
closure(B) = max over attacks a of  damage(a) x [ readiness_p(B, a | enabler_budget, copies, pool, draws)
                                                - readiness_p(B, a) ]
```

`_evolve_income_delta` (`pilot.py:1829`) is the wiring to copy, so this inherits its fixes rather than
re-earning them — notably `CountTriple.expected` rather than the raw triple, whose absence silently
zeroed three of ADR-0070's terms on every board (#167). Three sub-rulings:

- **Per attack, never `attack_id=None`.** The #137 contract notes that `None` asks the famine question
  across ALL attacks — correct for a boolean, wrong for a magnitude, since the reachable attack may be
  the cheap one while `maxDamage` belongs to the dear one. `max` across attacks (ADR-0069 §1).
- **One Budget per target body, `target_benched` per site** (#137 contract hazard 1).
- **The draw window is SITE-DEPENDENT, and ZERO at the pick site.** `docs/rulebook.txt` L173-176/L183:
  the replacement Active is chosen immediately after the KO'ing attack resolves, or at Checkup — and
  attacking ends your turn (`docs/rules.md` §5). So at a TO_ACTIVE promote **no play window remains**
  and `draws = 0`. This also EXPLAINS the handoff's open puzzle that no corpus frame drives
  `fetch_enables_p` above 0: the term was structurally inert wherever it was mostly being asked. The
  requested fixture must therefore be authored as a **SWITCH/whether** frame, not a TO_ACTIVE one.

The interim `min(1.0, p) x _READY` cap disappears: `Δ ≤ 1` bounds the term below `damage(a)` by
construction, so "closure can never beat actually being ready" becomes structural rather than clamped.

**6. `_STALL` is DELETED as a measured double-count; `tempo_denied` is DERIVED from the Threat Clock.**
The shipped wiring sets `is_staller = ("opener" in tags or item_lock_live)` AND `is_item_lock =
item_lock_live` — both True for a Budew on turn ≤ 3, from ONE card feature through ONE gate, paying
`_STALL` 20 + `_ITEM_LOCK_TEMPO` 12 = **32**. Sweep #3 tuned `_item_lock_live` to stop the +27
over-fires without noticing the credit was doubled at source.

*(a)* A disposable staller decomposes with no remainder into terms decisions 3–4 already build: its own
damage, its LOW `exposure` (1 prize x 100 x clock — "disposable" IS the exposure term), and the
`preservation` credit for the body it replaces (the "wall absorbs a hit" intuition, priced on the body
being protected rather than the wall). `_STALL` was a rung-era proxy for "cheap to lose"; the honest
version now exists, so the proxy goes.

*(b)* `tempo_denied = incoming(my_next_active, t=2) − incoming(my_next_active, t=1)` — one development
step's threat growth, off the live Threat-Clock curve (`combat.py:970`, whose docstring notes `t` moves
only the ENERGY budget since evolution reach is maximal at `t=1`, so the delta IS one step). Gated on
the opponent actually holding live Items — `opponent.copies_left_odds()` filtered by `stats.is_item`
(`provider.py:133`), the shape of `_opp_switch_enabler` but failing **CLOSED** (no matched Read → no
credit), because this term ENDORSES a play and ADR-0067's rule is fail-closed on yield. The grill spec
deferred this term to the unified Threat Clock; that clock is now live, so the deferral's condition is
met. `_ITEM_LOCK_TEMPO` and `_item_lock_live`'s `turn <= 3` both die, and with them the code comment
wishing for "a real opponent-Item-reliance read".

**Stated honestly:** this swaps one proxy for a better-grounded one, not for an identity. Item lock
denies ITEMS while the curve delta measures a whole development step, so the term is a **CEILING**.
The over-credit direction is exactly Sweep #2 Finding A's over-fire, and the Item-copies gate is what
bounds it.

**7. The endgame/positional constants collapse: `_FATAL_STEP` repriced at the dominance band,
`_NEAR_GOAL`/`_GOAL_BAND` and `_PATH_TAX` deleted.**

*(a)* The fatal-prize step — `prizes(B) >= opp_prizes_remaining >= 2`, i.e. Knocking B Out ENDS the
match — is subtracted at **`KO_SCORE`**, the constant that already means "dominates any sub-lethal
quantity" on the positive side, and gated on decision 4's clock (`turns_to_ko_me(B) == 1`) rather than
the retired boolean, keeping ruling 5's provable-KO stand-down. A finite dominance band, not a veto:
when EVERY option is fatal the residual still orders them, which a veto cannot.

**Considered and rejected: giving this to the doom layer / #142.** `_active_doomed` (`pilot.py:6735`)
is "the opponent can KO my Active next turn" — a BOOLEAN, worst-case, γ-gated read about one body. It
owns DETECTION, not cost, and #142's charter is re-pointing famine/posture/doom onto
`reachable_attach`, not acquiring a new responsibility. Splitting the term would put "will they KO B"
in one layer and "what that costs" in another — the pathology decision 1 rejects — and would route a
terminal-cost decision through a boolean, re-opening the cliff decision 4 removed. The detection IS
already the doom family's: `turns_to_ko_me` is the graded member of the same CombatMath family.

**CAVEAT, recorded so it is inherited rather than forgotten (user ruling, 2026-07-26).** This
subtraction is a **local stand-in for a BOARD-LEVEL fact**. Nothing in the codebase today owns "they
take their last prizes" — the nearest is `planner.py:3162`'s `_READINESS_FLOOR = 8.0` binary credit for
"a bench exists", which is win-condition 2, not the prize count. Because only this equation prices it,
the attach or evolve decider can still walk us into the same loss from a different seam. The correct
home for a cross-decider "don't lose the game" term is **#145's `state_value`** — prize-denominated
and whole-board by charter. #145 should ABSORB this term rather than let it duplicate.

*(b)* `_NEAR_GOAL` / `_GOAL_BAND` (exposure super-linear over their last two prizes) DELETE as
**emergent**: the fatal condition is `prizes(B) >= opp_prizes_remaining`, so as their count falls
progressively more of our bodies become fatal automatically. The escalation near their goal is a
consequence of the condition; modelling it twice is two mechanisms for one effect.

*(c)* `_PATH_TAX` DELETES as **subsumed**, on a card-mechanics argument: the promoted body becomes the
ACTIVE, and they attack the Active because it is the Active — path membership does not change whether
it is hit. What the flag really encodes ("its prizes complete their route") is now exactly
`prizes x 100` plus the fatal step. Path reasoning still earns its keep where targeting is a CHOICE —
the Bench — which decision 4's `preservation` leg already models via the Bench Harvest.

(b) and (c) are ARGUMENTS that the effects are emergent, not measurements. If the corpus disagrees at
the Decision Gate they return as ruled flips.

**8. Retreat cost is the BUILD it destroys plus the resource premium — and the cost READ becomes
grant-aware, fail-closed.**
`retreat_worth = _effective_retreat_cost(ma) x ENERGY_TIER` priced a Mega's retreat at 16 in
card-Worth units — the third currency decision 3 set out to eliminate, and near-free against attacks
scoring hundreds. Replaced by the exact mirror of the attach decider (1a prices an attach as `+build`;
a retreat pays `−build`), so the two cannot disagree about what an Energy is worth:

```
retreat_cost = [ build_standing(A) - build_standing(A less the N discarded) ]
             + _ATTACH_RESOURCE_TIEBREAK x SUM( worth(e) - ENERGY_TIER )
```

Worked: Mega Starmie ex at 3/3 of Nebula Beam is `(3/3)^2 x 210 = 210`; after paying retreat 2,
`(1/3)^2 x 210 = 23` — the retreat costs **187 damage** of build, which is two turns of attaching
thrown away and is exactly why "insanely retreat happy" opened this grill. Free-retreat bodies pay 0.
`_effective_retreat_cost` still supplies N (Air Balloon aware). **Zero new constants.** Retreat slots
being colourless (`docs/rules.md` §89), the discarded set is the greedy cheapest-to-lose typed choice
— competent play, not optimism; VERIFY at build time that the engine lets us choose. Deliberately NOT
refunded for discard-recursion decks (Aura Jab attaches Basic {F} from the discard): `_recover_units`
already credits that recycling on the attack option, and discounting here would pay it twice.

**The cost READ becomes grant-aware.** `retreatReduction` is parsed from skill text, **Tool-only and
flat** (`provider.py:58`). This set has five other shapes and one is in our decks: **Rescue Board**
(1157) is a Tool but CONDITIONAL ("{C} less; no Retreat Cost at HP <= 30"), and **Latias ex** (184,
"Your Basic Pokémon in play have no Retreat Cost") is a BOARD-LEVEL Ability that `_effective_retreat_
cost` cannot see — and `slowking` runs it (`grimmsnarl_ex`/`mega_lucario` run Air Balloon, handled;
`dragapult_ex`/`mega_starmie` neither). Under a flat `x 8` a missed reduction cost 8 points; under the
convex build delta, over-charging one Energy on a 3-slot attacker is `(3/3)^2 - (2/3)^2 = 5/9 x
maxDamage` ~ **117 damage of phantom cost**, systematic on an archetype built around free-retreat
pivoting. So the read is extended at the PROVIDER seam (ADR-0056's one card-knowledge seam, where
`hpBonus`/`recoil`/`benchSnipeDamage` are already text-parsed) to cover the conditional Tool and
board-level grants scoped by their own predicate — **fail-CLOSED: an unreadable or unmodelled grant
charges the PRINTED cost**, erring toward not retreating, never toward the retreat-happy pathology.
Scoped to the shapes our decks and the tracked meta run, one named test each — NOT a general effects
DSL. The engine cannot supply this: `retreatCost` exists only on `CardData` (`api.py:468`), the static
printed value; the in-play `Pokemon` carries no effective-cost field.

**9. ONE evaluator, three call sites — the two-site divergence becomes structurally impossible.**
The whether-site priced the retreat option off its own best-destination loop while a SEPARATE path
picked the body at the follow-up SWITCH select, so the agent could retreat BECAUSE Cinderace is worth
promoting and then promote Budew. They already diverged: two near-duplicate `PromoteRetreatInputs`
constructions (`pilot.py:1971` pick, `:2056` whether) disagreeing on `on_their_path` (**hardcoded
`False`** at the whether site), `is_best_target`, `can_attack` and `prize_value`. Decisions 3 and 7c
dissolve two of those four, but not the structure that produced them. Therefore:

```
promote_value(B) = my_yield(B) + closure(B) - exposure(B) + tempo_denied(B) - fatal(B)
retreat_option   = max over bench B of promote_value(B)  +  preservation(A) - retreat_cost(A)
pick_option(B)   = promote_value(B)
```

`preservation(A)` and `retreat_cost(A)` are CONSTANT across destinations, so they belong only on the
whether-site's retreat option and are correctly absent from the pick site, where they could change no
ordering. The forced TO_ACTIVE promote is the same `promote_value(B)` with no A-side terms at all.
Consequence: the pick site stops reading `ctx.*` Context flags and reads the BODY — the direction
decisions 3/4 force anyway, since both need `BodyView`/clock reads rather than Context booleans. Some
Board flags may thereby lose their last consumer.

**10. HORIZON is ruled PER TERM, not globally** (the grill agenda's own recommendation). `my_yield` is
this-turn damage plus closure odds (decisions 3, 5); `exposure`/`preservation` are the N-turn
accumulating clock (decision 4); `tempo_denied` is the `t=2 − t=1` curve delta (decision 6). Both
"curve terms" the 2026-07-22 spec deferred to the unified Threat Clock — the preservation dividend and
the tempo slip — are hereby LIVE, because that clock shipped. The 1-exchange slice is retired.

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
