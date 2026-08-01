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
  menu / pre-anchor / hand already holds the enabler. The old binary *protected-hand* veto is
  retired (WP6): each held card's shuffle cost is now GRADED — `_keep_cost = role_value × (1 −
  re-access odds)` (`common/card_worth.py` owns the tier table; `_card_reaccess_outs` is the fetch
  closure pointed backwards), summed into `hand_keep` and folded into the baseline (`ev > det +
  hand_keep`, the winner scores `ev − hand_keep`). A KO gamble now fires while holding a
  *re-accessible* wincon/pre-evo and stands down only when the held plan piece is genuinely
  closure-unreachable. Trace prints P, the class, the EV-vs-held comparison, and a `keep` field.
  Gated REQ-GAMBLE-0001..0005 + WP6 (`tests/strategy/test_gamble.py`, `test_card_worth.py`) —
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

## Fetch-chain closure & card worth — the 2026-07-17 grill (BUILT 2026-07-18/19; living status: ADR-0065)

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
Living build status: [ADR-0065](../adr/0065-card-worth-is-one-marginal-oracle-with-a-closure-graph-backend.md)
§Build status (the build-handoff plan doc is retired — git history).

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
- **The Supporter-slot branch (2026-07-18):** each class now carries a post-Item-refresh Supporter
  supplement — Hilda's energy/evolution fetch, Crispin's unconditional accel, Salvatore's
  rush-evolve, and the Petrel 2-hop (→ an energy/Pokémon-fetch Item still in deck) — applied per
  refresh option ONLY when the refresh is an ITEM (Unfair Stamp) with the one-per-turn Supporter
  slot unspent. 4 of 5 refreshes are Supporters and spend the slot, so their windows price without
  the Supporter outs; the Stamp window prices WITH them — the resource limit is priced, not assumed.
  A held Supporter tutor with a live slot voids the class (the deterministic play-it-now line). The
  trace carries the supplement (`post_item_sought` / `post_item_copies` per class, `post_item_sup`
  per eval row).

**Clause tier (WP3 — fetch, draw-engine, and accel clauses built):** every fetch/tutor/recycle,
draw-ENGINE ability, and Trainer/Supporter accel mechanic the 3 agents use now lives in
`card_effects.json` (ADR-0032), authored in `effect_overrides.json` and verified against engine
ability/attack text — the Round-11 ruling that the card representation carries every mechanical need so
text is never parsed.
- **`fetch` clauses** (`target` / `zone` / `energy_type` / `no_rule_box` / `hp_max` / `no_ability`):
  **`doctrine_fetch._FETCH_FILTERS` (the fifth private-valuation shadow) is RETIRED** — `_search_deck_set`
  and the whiff/redundancy/confirmed-hit signals read the clauses through one shared predicate
  (`_fetch_target_matches`), also consumed by the gamble closure (`_fetch_reaches_slot` /
  `_fetch_reaches_pokemon`). The migration sharpened the fetch-sets to exactly what each card can pull
  (Fighting Gong → Basic-only Pokémon, Poké Pad → no-Rule-Box, Hilda → Evolutions only).
- **`draw` clauses** for the draw-engine abilities (Dudunsparce draw-3-self-shuffle, Drakloak
  look-2-take-1, Fezandipiti ex / Lunatone / Unfair Stamp conditional) — `amount` + `window` + gating
  `condition` + self-effect `rider`; the foundation the Stage-2 draw-engine closed form (WP4) reads.
- **`accel` clauses** for Trainer/Supporter accel (Rosa's discard→Stage-2 prize-behind, Crispin
  deck→attach) — `amount` / `source` / `target` / `condition`; the foundation WP5's shortfall gate reads.
  Attack-based accel stays the AttackStat tier per ADR-0064 (Aura Jab already carries `recoverN`).

**Deck-source attack accel — the Turbo Flare family (built 2026-07-18, derivation-first):**
`AttackStat.recoverSource` ("discard" | "deck") widens the recover-rider family to the 14 deck-source
search-attach attacks (Turbo Flare, the Kaguras, Energy Gift; coin-gated and scope-locked variants
deliberately unmatched — an endorser under-counts). The Tactical development credit
(`_recover_units`) branches its fuel bound by zone: visible discard (Aura Jab) vs deck fuel
(tracker-exact once anchored, else the sound pigeonhole floor `unseen − hidden prizes`), keeping the
need gate — Turbo Flare on an empty bench credits 0 ("firing blanks"), with a benched line pre-evo it
credits the full min(3, fuel, need) ≈ +225, the same scale that tips Aura Jab. The bench-accelerator
body is now DERIVED from that attack fact (`_derived_accel_body_ids` → `_roles_of` injects
`accel_source`, `accel_recipient_missing` unions it), so the whole accel rung family
(open-the-accelerator, develop-the-accel-recipient, feed-the-accelerator, promote) fires for a NEW
Cinderace deck with zero deck rules — mega_starmie's hand-declared Role becomes the confirm, exactly
the Round-9 derive-then-declare shape. For the existing agents the union is a proven no-op (both
already declare it; suite unflipped).

**WP4 — Stage-2 draw engines (built 2026-07-18, test-first):** the two-window closed form ships as
`deck_odds.draw_hit_with_engines` — P(assemble) = P(≥1 out in n) + [P(miss) − P(miss ∧ no usable
engine)] × P(≥1 out in the engine window | thinned pool), iterated per board-supported stage. EXACT
at depth 1 (outs and engines are disjoint classes — pinned against a full exhaustive enumeration,
not a simulation); deeper stages are the spec's same-two-ratios loop with one engine consumed per
stage (documented approximation, measured magnitude ≈ +0.6pp). `planner._gamble_draw_engines`
derives the usable engines from the representation: a `draw` clause with
`condition: once_per_turn_ability` (Drakloak look-2-take-1 → window 2; Dudunsparce draw-3 → window
3; Fezandipiti's post-KO and Lunatone's Solrock+hand-discard gates fail closed) AND an eligible base
in play since last turn — depth = Σ min(copies, eligible bases) per line, never a constant. Window-2
outs are the SAME class outs (the full Stage-1 union); a sought-evolution engine is excluded from
its own class (no double-count); pre-anchor stays plain (anchored-only sharpening). The trace
carries `engine_copies` / `engine_windows` / `engine_ids` per class. On-board engines with unused
abilities remain the sequencing rung's jurisdiction (fire before the refresh, deterministically).

**WP5 — the enabler taxonomy (built 2026-07-18, test-first):** the gamble rung now prices five
Outcome Classes, each with the same void-if-in-hand / det-baseline / trace shape and the post-Item
Supporter supplement — **energy** (WP1), **evolution-KO**, **damage-pump** (`_gamble_pump_ko_classes`:
short by ≤ one boost, gates mirror `_boost_lethal_tactical`'s attacker-type + defender-{ex}; Premium
Power Pro Item always-live, Black Belt's Supporter post-Item), **gust** (`_gamble_gust_ko_classes`:
no direct KO but a benched target reachable — `_gust_best_ko_prizes`; Boss's Orders → supplement),
and the **survival** class (`_gamble_survival_classes`: bench empty + `active_doomed` = a predicted
game loss; averted by **bench-fill** — any benchable Basic or Poffin's fetch — or **heal** — a drawn
heal that lifts the Active above `incoming_active_damage`, Wally's on a damaged Mega ex; value
KO_SCORE, exempt from the keep-value blocker). The one remaining WP5 refinement is the accel-aware
shortfall gate (`shortfall ≤ 1 + reachable accel attaches`); for the 3 agents the only Active-targeting
accel is Crispin (post-Item, dragapult), so it's deferred as narrow + core-gate-touching (the other
decks' accel is bench-targeting: Turbo Flare / Aura Jab).

**WP6 — the replaceability-floor keep-value (built 2026-07-18, test-first):** the gamble's binary
protected-hand veto is replaced by a GRADED shuffle cost. `common/card_worth.py` owns the ONE tuned
currency — `ROLE_TIER` (wincon/attacker 30, line-base/engine/accel/tutor 20-10) + `ENERGY_TIER` (8,
the retired ADR-0060 flat-shed anchor) + `ACE_SPEC_TIER` (25) — and the single `keep_cost` primitive.
The Pilot derives the rest at the decision point: `_card_reaccess_outs` is the fetch closure pointed
backwards (a held card's own deck copies ∪ every deck-search tutor whose FETCH clause reaches it),
`_role_value` reads the tier table (energy / ACE-SPEC fallbacks), `_keep_cost = role_value × (1 −
draw_hit_probability(outs+1, pool, draws))`. `_best_gamble_line` sums `hand_keep` over the held cards
and folds it into the baseline (`ev > det + hand_keep`), so a KO gamble fires while holding a
re-accessible plan piece and only stands down when it is closure-unreachable. The refresh-swing SHED
re-audit (ADR-0060's other jurisdiction) rides into WP7's oracle fold. Gated `test_card_worth.py`
(3) + the WP6 gamble unblock test; strategy/blunder/agents re-audit = no flips.

**WP7 — the card-worth oracle module, core built (2026-07-18, ADR-0065):** the "one module home" seam
is in. `common/fetch_closure.py` owns the tutor/recycle/search graph as pure functions
(`fetch_target_matches` / `reaccess_outs` / `fetch_reaches_pokemon`); the Pilot's closure methods
delegate, so the fetch doctrine, the gamble gain side, and the keep-cost read ONE implementation.
`common/card_worth.py` owns the worth currency + `role_value` / `keep_cost` primitives (the Pilot
delegates). The **refresh SHED** convergence has landed (2026-07-18): `_refresh_swing_tactical`'s flat
`_REFRESH_SHED × cards-lost` became `Σ keep_cost` over the actual hand (`_refresh_shed_keepcost`) — and
since **ADR-0101** (Issue #261 item 2b) that site reads the v2 assignment SET marginal
(`needs.set_keep_v2`) instead, so a shuffled duplicate costs what the PAIR is worth rather than twice
what one copy is; `planner._hand_keep` keeps the summation for the gamble keep-floor alone. And
the four `hold-*` hand-quality guards fold into it — all six ADR-0060 corrections hold, one corpus
target flipped to a pin. The **fetch grab/pitch** shadow was measured and found ALREADY subsumed
(2026-07-18 — its tuned discard ladder prices roles + redundancy; the residue is the gate library's,
see ADR-0065); **TAG_TIER worth coverage** landed 2026-07-19 (`role_value` reads behavioural tags, so
a role-less Ignition / Wally's is no longer shuffled for free — two corpus targets flipped); and the
**gate library Stage 1** (evolution gate) landed 2026-07-18: `keep_cost` gains its `deploy_odds`
deadline factor (`common/gate_library.py`) on both converged keep-value sites — an undeployable
evolution sheds freely.

**Still designed, not built:** the accel-aware shortfall gate (WP5, narrow for these decks), the
plan-tier-credit convergence (the last WP7 shadow), and the skill loop (deck-genie Role Sheet /
deck-align fold). Landed 2026-07-19: the held-card-risk seam and the tutor-chain grab value (corpus
targets `85163634-17` / `85059103-9` promoted), the keep-cost duplicate-copy reconciliation
(`planner._hand_keep` — then one summation for the gamble keep-floor and the refresh SHED; the
refresh half moved to the set marginal in ADR-0101, so the summation is now the gamble's alone), and the
**gate library completed** — fetcher (a provably-dead searcher/recycler sheds free), pressure (the
closing-edge spike; retired `hold-successor-when-doomed`, the last flat refresh guard), and quota
(duplicate once-per-turn cards shed by deadline rank) — ADR-0065 §Build status.

## Acceptance — met 2026-07-05

Lillie's-class fixture flips exactly on the EV comparison (REQ-GAMBLE-0001/0002); suite 1269
green; A/B 52% (CI 50–54), 0 crashes → `gamble_lines` default ON; trace carries the class + odds.
