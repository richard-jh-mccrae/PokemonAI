<!-- Strategy Proposal queue — blunder-buster round 2026-07-09 (dragapult_ex). REVISED after user review.
Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md

WHY REVISED: the first pass routed only the 8 corrections tune.py flagged OPEN and trusted its "13/18
W-route satisfied" count. A decide() sweep of EVERY dragapult correction (this session) proved the
"satisfied" set folded 5 STILL-BROKEN frames — incl. 2 CRITICALs (f32, f79) — into cosmetic weight nudges
([[wroute-satisfied-not-fixed]]). 11 frames actually blunder on the live Pilot; all are now routed here.

THE ROOT (answers "why don't the general strategies help this new deck?"): the general rules are CORRECT
but gated on win-condition / KO / threat / energy SIGNALS that were only ever exercised by the two earlier
decks (mega_starmie, mega_lucario — both SINGLE-HOP lines, CHEAP-attack KOs, mono-color, mono-threat).
Dragapult's shape (a 2-STAGE line, KO via the EXPENSIVE Phantom Dive, off-color {D} Munkidori fuel, a
disruption/gust game) makes those signals mis-fire or stand down, so the EXISTING rules go silent or target
the wrong body. The fixes below are mostly SIGNAL/GATE corrections to EXISTING rules (so the deck stops
running effectively uncovered), NOT new deck-specific weights.

decide() sweep (live dragapult Pilot): blunders now = f6, f10, f14, f18, f20, f21, f31, f32, f79, f81, f85.
  covered (decide()==correct): f8 (degenerate), f45 (gamble stands down, dig-tie -> Poké Pad) — ledgered.
  capability-gap: f20 retreat-to-item-lock maneuver — docs/todo/retreat-to-item-lock-maneuver.md.
The tuned.json weight nudges the fit made for the "satisfied" frames (e.g. play-energy-denial 20->17) are
MIS-FITS — they weaken a general rule for every deck without fixing dragapult; update-strategy should author
the GATE below and drop those nudges. -->

## line-readiness-signals-model-the-multi-stage-line
- id: line-readiness-signals-model-the-multi-stage-line
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: three EXISTING signals must become evolution-DISTANCE / pre-evo aware: `board.priority_wincon_slot` (pilot.py:2561 — include the win-condition-LINE pre-evo closest to the PAYOFF cost, not only the evolved wincon), `board.wincon_base_deployable` (deployable only when the IMMEDIATE pre-evo is in play/hand), `_evolve_to_ready_wincon_available` (pilot.py:2503 — the benched pre-evo must be the wincon's IMMEDIATE pre-evolution, one hop). Plus `promote-the-staller` (baseline_promote.py:78) must recognise an `item_lock` body (Budew id 235) as a disposable staller, not only `opener`.
- verification_contract: verifier
- provenance: corrections 85045840:f14 (CRITICAL), 85046350:f31 (CRITICAL), 85046350:f85 | fixtures tests/fixtures/corrections/dragapult_fetch_stranded_payoff_f14.json, dragapult_promote_over_fragile_base_f31.json, dragapult_concentrate_line_preevo_f85.json | [[promote-after-ko-priority]]
- status: open
- for: general

**Spec (authoring spec — thin fodder):**
Dreepy→Drakloak→Dragapult ex is the corpus's FIRST 2-stage line. Every win-condition-line signal was written
against single-hop lines (Staryu→Mega Starmie ex, Riolu→Mega Lucario ex) where "a line pre-evo in play" ≡
"the payoff is one hop / one evolution from ready." For a 2-stage line that equivalence is false, and three
EXISTING general rules silently fail:

- **f85 concentrate (`concentrate-energy-on-wincon`, +25 — EXISTS, does not fire).** `priority_wincon_slot`
  scans only `_wincon_set()` = the evolved Dragapult ex; the bench holds pre-evo Dreepys, so it returns None
  and concentrate stands down → `power-up-attacker` spreads {P} to a BARE Dreepy instead of finishing the
  started 1e Dreepy toward Phantom Dive (F+P). **This is exactly the rule the user expected to cover it.**
  Fix: `priority_wincon_slot` also considers the win-condition-LINE pre-evo carrying the most energy while
  short of the PAYOFF's cost.
- **f14 fetch (`fetch-base-before-stranded-payoff`, +20 — EXISTS, stands down).** `wincon_base_deployable`
  returns True off the active Dreepy (a Stage-0 base), so the guard stands down and the agent grabs a
  Dragapult ex that STRANDS in hand (2 evolutions away, no Rare Candy) onto an empty bench. Fix: deployable
  only when the IMMEDIATE pre-evo (Drakloak) is in play/hand.
- **f31 promote (`promote-the-staller`, +20 — EXISTS, stands down; `prefer-wincon-line-piece` mis-fires).**
  `_evolve_to_ready_wincon_available` returns True (wincon in hand + a line pre-evo on bench) even though the
  bench body is a Stage-0 Dreepy two hops from a ready attacker — so `prefer-wincon-line-piece` promotes the
  fragile bare Dreepy and `promote-the-staller` stands down. Fix: require the IMMEDIATE pre-evo (one hop);
  AND teach `promote-the-staller` to treat `item_lock` (Budew) as a disposable staller.

**Why one proposal:** all three are the SAME distance-blind root; a single evolution-distance helper (immediate
pre-evo of the payoff) feeds all three signals. NO-OP for single-hop decks (verify inert on mega_starmie /
mega_lucario). Gate: fixtures flip f85 [4]→[3], f14 [6]→a developing Basic, f31 [0]→[1] Budew; all three inert
on the single-hop decks.

---

## play-energy-denial-threat-and-ko-aware
- id: play-energy-denial-threat-and-ko-aware
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: gate `play-energy-denial` (baseline_disruption.py:15) on (a) `board.active_can_ko` (pilot.py:3054, best AFFORDABLE attack — EXISTS) instead of / in addition to `active_cheap_attack_kos`, so a Phantom-Dive (expensive-attack) KO stands the strip down; (b) a "the opp Active's energized attack actually damages us" read — the Effect-Compendium AttackStat/oracle (ADR-0032, [[effect-compendium-plan]]) already models conditional/zero-damage attacks (Kyogre needs energy in the opponent's discard). candidate_signal for (b) may be "needs a new board field: opp_active_attack_threatens".
- verification_contract: verifier
- provenance: corrections 85045840:f6, 85046350:f32 (CRITICAL) | fixtures tests/fixtures/corrections/dragapult_hammer_no_threat_f6.json, dragapult_hammer_over_develop_f32.json | [[ignition-energy-discipline]]
- status: open
- for: general

**Spec (authoring spec — thin fodder):**
"Yet again this deck used a Crushing Hammer on an opponent we were going to KO." The stand-down EXISTS but is
keyed on `active_cheap_attack_kos` — the CHEAPEST attack. mega_starmie KOs with cheap Jetting Blow, so it
works there; dragapult KOs with **Phantom Dive, its EXPENSIVE attack**, so the gate never sees the KO and the
Hammer is spent on a body that's about to leave play. Fix (a): also stand down on `active_can_ko` (best
affordable attack KOs), the signal that already exists for exactly this "big-attack KO" case (it backs the
survival-heal suppressor). Second failure (f6): `play-energy-denial` fires whenever `opp_active_has_energy`,
but **Kyogre's attack does damage only if the opponent has energy in its discard** — it cannot hurt us, so
the strip is worthless. Fix (b): gate on the opp Active's energized attack actually threatening us (the Effect
Compendium already classifies conditional/zero-damage attacks). f32: with (a)+(b) plus develop-priority, a
low-value strip loses to `advance-the-evolution-line`. **Why it wins:** "don't strip a body you're KOing or
that can't hurt you" is universal; the current rule wastes a premium disruption Item across every non-cheap-KO
deck. NOTE: the fit's play-energy-denial 20→17 nudge (from these frames) is a mis-fit — author the GATE, drop
the nudge. Gate: fixtures flip f6 [1]→[2] and f32 [2]→[1]; verify no regression on the mega_starmie
play-energy-denial ledger (82748422 f26 etc.).

---

## energy-color-and-attach-target-discipline
- id: energy-color-and-attach-target-discipline
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: (f18) `_TO_HAND` energy fetch — prefer an energy TYPE in the win-condition attack's cost over an off-color utility energy no in-play body needs (tie-break under the type-BLIND `fetch-energy-when-starved`, doctrine_fetch.py:344). (f21) `_ATTACH` — a penalty when the target is a DRAW-ENGINE utility body (own `draw`/`stall`, OR evolves into a `draw`/`stall` Pokémon: Dunsparce id 305 → Dudunsparce id 66) and NOT a win-condition/attacker body; sibling of `power-up-attacker` (baseline_energy.py:31).
- verification_contract: verifier
- provenance: corrections 85046350:f18, 85046350:f21 (CRITICAL) | fixtures tests/fixtures/corrections/dragapult_fetch_attack_color_f18.json, dragapult_dont_feed_draw_engine_f21.json
- status: open
- for: general

**Spec (authoring spec — thin fodder):**
The energy signals are color-blind and attacker-blind, so the deck's off-color {D} (niche Munkidori fuel) is
mis-handled twice. **f18 fetch:** `fetch-energy-when-starved` (+35) ties every energy type; the tie-break
grabs {D} over {R}=Fire, a Phantom Dive cost color (F+P). Fix: prefer an on-attack-color energy over an
off-color utility energy no in-play body needs. **f21 attach (CRITICAL):** the only energy is {D}; because
Dunsparce has a Colorless-cost attack, `power-up-attacker` (+15) treats it as an "attacker" and sinks the
Munkidori fuel into the **Dunsparce → Dudunsparce DRAW ENGINE**. Fix: penalise attaching to a draw-engine
utility body (own `draw`/`stall`, or evolves into one — Dunsparce is currently untagged, so read
`evolvesInto` OR tag it) that isn't a win-condition/attacker. **Why it wins:** "fetch the color your attack
needs; don't power a Pokémon that will never attack" is universal energy discipline (Bibarel/Bidoof,
Dunsparce/Dudunsparce); silent for single-color / no-draw-engine decks. Gate: fixtures flip f18 [0]→[1] and
f21 [4]→[2]; inert on mega_starmie/mega_lucario.

---

## spend-boss-orders-on-the-ko-not-setup
- id: spend-boss-orders-on-the-ko-not-setup
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: reconcile the gust rungs by KO payoff — `gust-for-the-ko` (+50) must SEQUENCE/rank above a setup accel or bench-fill when a gust enables a this-turn KO (currently it fires but is tiered behind tier-0 develops in `_finish_turn_last`, and loses the one-Supporter-per-turn slot to `use-acceleration`); `gust-for-the-stall` (+10) must NOT spend Boss's Orders on a valueless early-setup gust. Co-signal (f79): extend the whiff guard `dont-search-an-empty-deck`/`dont-search-a-probable-whiff` (doctrine_fetch.py) to Buddy-Buddy Poffin's bench-fill fetch when no fetchable ≤70 Basic remains.
- verification_contract: verifier
- provenance: corrections 85046350:f10, 85046350:f79 (CRITICAL), 85046350:f81 | fixtures tests/fixtures/corrections/dragapult_gust_wasted_in_setup_f10.json, dragapult_poffin_whiff_take_gust_ko_f79.json, dragapult_gust_ko_over_accel_f81.json | [[snipe-threat-two-signals]]
- status: open
- for: general

**Spec (authoring spec — thin fodder):**
Boss's Orders is dragapult's premium gust — the disruption deck's payoff-converter — but it is valued wrong at
both ends. **f81:** with Dragapult ex online, the agent plays **Crispin** (accel Supporter, +45) which consumes
the one-Supporter-per-turn slot and FORFEITS **Boss's Orders** (gust-for-the-ko +50) — the human's line gusts
Cynthia's Roserade (130hp), Phantom-Dives it for the KO AND spread-KOs the benched Gible = 2 prizes, and
removes Roserade's *Cheer on to Glory* Garchomp-damage-boost. **f79 (CRITICAL):** same board — the agent plays
**Buddy-Buddy Poffin** which WHIFFS (the deck has no fetchable ≤70 Basic left; the human saves it as Ultra Ball
fodder) instead of the gust-KO. Both lose because `gust-for-the-ko` (+50), though the highest-SCORED option, is
tiered behind tier-0 setup plays in `_finish_turn_last`, so a setup card is the first (and Supporter-spending)
action. **f10 (inverse):** early setup, empty bench — `gust-for-the-stall` (+10) drags a Snover for nothing;
the human saves Boss's Orders and develops. **Author:** (1) a gust that ENABLES a this-turn KO sequences as a
KO-setup (ahead of generic develop / above a setup accel Supporter), not as tier-0 filler; (2) `gust-for-the-stall`
stands down (or nets below develop) when the gust achieves no board value in setup; (3) [co-fix] the whiff guard
covers Buddy-Buddy Poffin's exhausted bench-fill. **Why it wins:** "spend your gust on the prize, hold it in
setup" is universal gust discipline; silent for decks without a gust Supporter. Gate: fixtures flip f81 [1]→[2],
f79 [2]→[4], f10 [1]→[2]; verify no regression on mega_starmie's gust ledger (gust-for-the-ko / gust-snipe cases).
