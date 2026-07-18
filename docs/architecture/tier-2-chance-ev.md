# Tier 2 — Chance & EV (Gamble Lines)

**Status: ~70% complete** (built 2026-07-05, `/tdd`; A/B **52%** CI 50–54, 0 crashes, 2000 games —
Battle Result #58 — default ON). Design in
[ADR-0039](../adr/0039-gamble-lines-are-closed-form-expectimax-over-outcome-classes.md). Prices
stochastic actions by **exact** expectation instead of flat penalties or not at all.
**Upstream:** deck tracker (exact own-deck composition) + Deck-Content Odds (ADR-0029); effect
compendium for branch valuation.
**Downstream:** a candidate family on T1's Goal Ladder; fallback EV terms in T0 for non-MAIN
contexts.

## Final design (ADR-0039)

- **Gamble Line** = a Turn Line with exactly ONE **Chance Node** (depth-1 by definition), valued as
  `EV = Σ P(class)·value(best follow-up | class)` over **Outcome Classes** — macro-partitions
  sharing one best follow-up ("≥1 {W} Basic among the 6 drawn" vs "Ignition redrawn, no {W}" vs
  "neither"), never raw card permutations.
- **Probabilities are exact**: own-deck composition = decklist − seen (deck tracker); unseen copies
  split hypergeometrically over hidden prizes (`deck_odds.py`). No sampling, no engine sim through
  the chance node — the Engine Search fork is ONE predicted determinization and its verdict is
  untrusted for prediction-dependent outcomes (the glossary's prediction-invariance rule).
- **Branch valuation is closed-form**: max over legal follow-ups using the compendium's damage
  math + development value — the same evaluators T1 rungs already use.
- **Competition rule**: Gamble Lines rank against deterministic lines by EV on the ladder; the sound
  win rung preempts every gamble; Lethal/Incoming keep worst-case (EV never enters sound math).
  Break-even is EV equality — never a fixed probability threshold.
- **v1 scope** (grilled): ① Hand-Refresh supporters — both *whether* (upgrades ADR-0024's deferred
  pull-EV) and *sequencing* (bank the attach before the shuffle vs gamble for a better draw);
  ② fetch hit/whiff EV inside lines (upgrades the flat `dont-search-a-probable-whiff` −25);
  ③ coin-attack EV for heuristic **ranking** only. Opponent-side stochastics excluded (no exact
  tracker — that's T4 territory).

## The canonical example (facts at source)

Mega Starmie ex Active, 0 Energy; hand: Lillie's Determination (*shuffle hand into deck, draw 6*),
Ignition Energy (*{C}{C}{C}, discard at end of turn*); opponent Active Water-weak.
- **Deterministic line**: attach Ignition → Lillie's → Nebula Beam ●●● 210 — which *ignores
  Weakness* (the ×2 is wasted) and the energy evaporates at end of turn.
- **Gamble line**: Lillie's first (Ignition shuffled away — the stake), then per class: {W} drawn →
  attach → Jetting Blow {W} = **240 with Weakness + 50 snipe**, energy persists; Ignition redrawn →
  Nebula 210 anyway; neither → no attack.
The right choice is EV equality over those classes — board-dependent, not "P > 50%".

## Built (the 70%) — 2026-07-05

- **The Gamble rung** (`planner._best_gamble_line`, kill-switch `gamble_lines`, ON): below every
  deterministic goal, plays a Hand Refresh FIRST when the draw's exact-odds EV beats the banked
  line — KO-enabling Outcome Classes (`_gamble_ko_classes`: type-aware one-attach-short analysis
  over `AttackStat.energyTypes`), tracker-anchored hypergeometrics (`deck_odds.draw_hit_probability`,
  fail-closed), the deterministic baseline (`_gamble_det_baseline` = best menu tactical or best
  after-attach chip), per-refresh draw branches (`_DRAW_COUNTS`). Stands down: mid-sim / KO on the
  menu / protected hand / pre-anchor / hand already holds the enabler. Trace prints P, the class,
  and the EV-vs-held comparison. Gated REQ-GAMBLE-0001..0005 (`tests/strategy/test_gamble.py`) —
  the canonical Lillie's board commits the gamble at 230 HP and stands down at 200.
- **The type-payable fix** (`Pilot._attack_type_payable`): the attach-lethal hook no longer counts
  Ignition's {C}{C}{C} as funding Jetting Blow's {W} — the false KO_SCORE unlock that produced the
  original attach-then-Nebula blunder. (The same count-blindness in `_best_affordable_ko_value` /
  `_develop_wins` is engine-verify-backstopped live and spun off as its own task.)
- **Coin-EV ranking**: a coin/conditional CHIP ranks by its min/max mean (rides `objectives_race`);
  the KO test, Lethal floor, and Incoming ceiling untouched.
- Substrate (pre-existing): deck tracker prize-exact resolution, ADR-0029 odds, sound oracle,
  Shuffle-Refresh Layer A + `dont-refresh-into-a-probable-miss`, Fetch comparator. **Fetch
  hit/whiff EV** is satisfied by design: planner tutor lines gate SOUND (`deck_definitely_has`),
  the score layer keeps the ADR-0029 probabilistic threshold rule.

## Gap to final (the 30%)

1. **Recovery classes** — BUILT since (the `_gamble_burst_copies` miss-branch redraw term;
   `test_recovery_class_counts_the_held_burst_energy_copies`).
2. Multi-class EV across several enabling attacks/refreshes in one menu (today: best single class).
3. Hand-disruption side-value for Judge-class refreshes (opponent hand unknown — heuristic term).
4. T0 fallback EV terms for non-MAIN contexts.
5. Pre-anchor gambles via the ADR-0029 prize-split hypergeometric — now fully SPECIFIED (below).

## Fetch-chain closure & card worth — the 2026-07-17 grill (designed; observability built)

**Background (the writeup story).** The v1 gamble counts *literal* enabling cards as outs — 4 Water
Energy in a 30-card deck is a 4-out draw. The owner's insight (2026-07-16): the real outs are the
**transitive closure** of everything that legally *reaches* the target this turn — tutors (Energy
Search → any Basic Energy; Fighting Gong → {F} only), recyclers (Energy Retrieval, from the fully
visible discard), and draw engines (Drakloak's Recon, Dudunsparce's Run Away Draw) — so the naive
hypergeometric systematically under-prices gambles, and the agent passes on wins it could assemble.
A 14-round adversarial grill ([hypergeometric-fetch-closure.md](../plans/hypergeometric-fetch-closure.md))
turned that into a full spec. Its through-line — the finding that ties the whole feature together —
is that every hardcoded limit examined dissolved into a **derived quantity**: the one-hop limit
(Items reach Energy at depth 1 *by construction of this card pool*), the exactly-one-short gate
(→ shortfall ≤ 1 + reachable accel attaches), the exact-tracker requirement (→ the ADR-0029
prize-split weights the window sum, ≤5 `comb` terms), the engine-recursion cutoff (→ bounded by
eligible pre-evolutions on the visible board), and the proximity/horizon multipliers (→ deadlines
priced by the same closure). **Key simplification:** every tutor in this set is a whole-deck search,
so interior hops are *deterministic given unprized* — P(assemble) = one window hypergeometric on the
closure's entry points × prize-split factors. No simulation, no sampling, Tier-0 closed-form
throughout.

**Why it matters for the competition:** the same primitive prices BOTH sides of every shuffle,
fetch, and discard — the gain side (outs by this turn's deadline) and the cost side (a shuffled
card's re-access odds by *its* deadline = graded keep-value), unifying four previously-separate
valuations (fetch grab/pitch, refresh card-swing, gamble keep-floors, the develop-leaf plan credit)
behind one card-worth oracle. Outcome classes generalize from Energy to an **enabler taxonomy**
(energy / evolution / gust / damage-pump / switch-heal / bench-fill) plus the **development gamble**
(hunt a plan piece — the empty-bench Turbo Flare → Staryu case), with the to-gamble bar staying the
EV comparison, never a fixed probability. Acceptance is the owner's own tagged blunder corpus
(~70 shuffle/fetch corrections) replayed through the real `decide()`.

**Built already (suite-green):** the three-deck tag-completeness audit (7 boolean lapses fixed, two
consumers recalibrated — the audit itself demonstrated the calibrated-currency lesson live), and
**full gamble observability**: the rung emits its complete working (pool, det, classes with sought
out-card ids, per-option p·EV) or its named stand-down reason on the `@T` stderr record, rendered
as a dropdown in the blunder shell — so every future closure stage lands observable from day one.
Build order: [hypergeometric-fetch-closure-build-handoff.md](../plans/hypergeometric-fetch-closure-build-handoff.md).

**Built (2026-07-18) — the gamble GAIN side, suite-green:**
- **WP1 — Stage-1 fetch-closure outs** (`_fetch_reaches_slot`): a KO class's outs are no longer
  literal Basic Energy only — a drawable card with a `basic_energy` **FETCH clause** (whole-deck
  search: Energy Search / Fighting Gong {F}-locked / Energy Search Pro; or recycle from the visible
  discard: Night Stretcher / Energy Retrieval / Max Rod) joins the entry points when its target is
  reachable. The recycle branch makes a class EXIST that the literal reading could not (deck-closure ∪
  discard-closure). The tutor/recycle predicates (type-lock, zone, target class) live in the card
  **representation** — `card_effects.json` FETCH clauses (ADR-0032), authored in `effect_overrides.json`
  and verified against engine card text — so the closure never parses card text (Round-11 ruling);
  Fighting Gong's {F}-lock is its `energy_type: 6` clause, which the generic `tutor_energy` tag can't
  carry. Closure out-ids flow into the trace's `sought`.
- **WP2 — pre-anchor gambles priced** (`_prize_split_hit`): the `if not deck_known_counts: return None`
  stand-down (which priced every pre-anchor gamble at zero) is replaced by the prize-split-weighted
  window sum — the decklist is fully known, only the unseen copies' prize assignment is random, so
  P(assemble) = Σⱼ [C(deck,j)·C(prizes,u−j)/C(deck+prizes,u)] × window(j), ≤ u+1 `comb` terms. The
  anchored path is byte-for-byte unchanged. The trace records `anchored` + `prizes_hidden`.
- **WP5 — the evolution-KO class** (`_gamble_evolution_ko_classes`, the spec's highest-value un-built
  class): where `_gamble_ko_classes` prices only the current Active's attacks, this prices "draw an
  evolution of my (evolution-eligible) Active → evolve → ITS attack KOs with the carried Energy + one
  attach" (rules.md §4: evolving keeps Energy, a Mega ex does NOT end the turn). Outs = the evolution's
  copies ∪ the Item Pokémon-tutor closure (Ultra Ball / Poké Pad / Mega Signal). Voided when the
  evolution is in hand (the deterministic evolve-KO owns it). The Pokémon-tutor closure reads the
  representation too (`_fetch_reaches_pokemon` over FETCH clauses): Poké Pad's `no_rule_box` clause
  correctly excludes a Rule-Box Mega ex — the parametric fact the `tutor_pokemon` tag can't carry.

**Fetch-clause tier (WP3, fetch portion built):** the tutor/recycle predicates now live in
`card_effects.json` as `fetch` clauses (`target` / `zone` / `energy_type` / `no_rule_box` / `hp_max` /
`no_ability`), authored in `effect_overrides.json` and verified at source — the Round-11 ruling that the
card representation carries every mechanical need so text is never parsed. **`doctrine_fetch._FETCH_FILTERS`
(the fifth private-valuation shadow) is RETIRED:** `_search_deck_set` and the whiff/redundancy/
confirmed-hit signals now read the clauses through one shared predicate (`_fetch_target_matches`), also
consumed by the gamble closure (`_fetch_reaches_slot` / `_fetch_reaches_pokemon`) — one representation,
one predicate. The migration sharpened the fetch-sets to exactly what each card can pull (Fighting Gong
→ Basic-only Pokémon, Poké Pad → no-Rule-Box, Hilda → Evolutions only), a pure precision gain.

**Still designed, not built:** WP3 remainder (the draw-engine + accel clauses), WP4
(Stage-2 draw engines — the two-window closed form), WP5's remaining classes (gust / damage-pump /
survival / bench-fill), WP6 (the replaceability-floor keep-value — re-audits ADR-0060), WP7 (the
`fetch_closure.py` + `card_worth.py` oracle cluster + skill loop), and the correction-seeded corpus.

## Acceptance — met 2026-07-05

Lillie's-class fixture flips exactly on the EV comparison (REQ-GAMBLE-0001/0002); suite 1269
green; A/B 52% (CI 50–54), 0 crashes → `gamble_lines` default ON; trace carries the class + odds.
