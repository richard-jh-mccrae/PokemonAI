<!-- Strategy Proposal queue — blunder-buster round 2026-07-09 (mega_starmie).
Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md
Routing evidence: real-Pilot retests + KO/threat/lethal probes (this session). CRITICAL cohort resolved
separately (C1 covered by recover-to-refill-bench; C2/C3 refuted, human ack, test_blunder_20260709). -->

## snipe-the-real-attacker-not-a-bulky-body
- id: snipe-the-real-attacker-not-a-bulky-body
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: CardStat/provider `forward_max_damage` (EXISTS — Riolu→Mega Lucario ex = 270) + benched-Pokémon attached-energy (`target_is_threat`/imminence) + attacker-vs-support role; reconcile against `snipe-the-forced-promotion` (+40) and `snipe-the-top-threat` (+30) in baseline_snipe.py
- verification_contract: verifier
- provenance: corrections 82224509:f47, 82523811:f41, 82523811:f61, 82753102:f85, 81785223:f39, 81785223:f45, 81905522:f75 | fixtures tests/fixtures/corrections/ms_snipe_evolving_wincon_preevo_f75.json, ms_snipe_riolu_over_lunatone_f47.json, ms_snipe_energized_bench_f39.json, ms_snipe_attacker_line_over_support_f85.json | see [[snipe-threat-two-signals]] (the deferred "evolves-into-attacker" signal, frame 75)
- status: open
- reopened (2026-07-10): the `applied` marking was FALSE for the frame-75 sub-signal — the gating fixture
  `ms_snipe_evolving_wincon_preevo_f75` still fails on the real Pilot (decide()=[1], human correct=[3]).
  `snipe-the-evolving-threat` (+45) was restored and fires on BOTH evolving-threat candidates, but on the
  wanted target [3] it is the ONLY rung (45), while [1] ALSO picks up `snipe-on-the-path` (+12) → 57, so
  the path tie-break out-votes the human's pick. Sub-signals #2 (energized-imminence, f39/f45) and #3
  (attacker-line over bulky support, f85) may be covered by the 2026-07-10 snipe-KO-dominance +
  forced-promotion-readiness work (`blunder-20260710-round.md#snipe-order-a-ko-dominates-the-positional-stack`)
  — re-scope this proposal to the f75 tie-break only: `snipe-the-evolving-threat` must beat, or the
  path axis must stand down under, a competing evolving-threat target the human declines. Verified failing
  on origin/main (baseline_snipe.py unchanged by the intervening lethal-verification PRs).
- for: general

**Spec (authoring spec — thin fodder):**
At a DAMAGE snipe select the agent repeatedly chips a **bulky current body** or a **support piece**
instead of the opponent's **real or developing attacker**. Across 7 corrections (opponents: mega_lucario,
a Latias/Clefairy deck, a Kadabra deck — so this is deck-AGNOSTIC, not a Brief) the human's intent is one
doctrine: **snipe the body that is or becomes the opponent's win-condition-class attacker.** Three
sub-signals, all currently unconsumed by a *firing* rung:

1. **Forward-evolution wincon pre-evo (dominant, 4 corrections).** The provider already computes
   `forward_max_damage` — Riolu = **270** (it becomes Mega Lucario ex) — but no snipe rung fires on it.
   Instead `snipe-the-forced-promotion` (+40) / `snipe-the-top-threat` (+30) land on the *current* bulky
   body (Hariyama, Solrock, Lunatone), which score 0 forward. Because **damage counters carry through
   evolution** (rules.md), pre-chipping Riolu softens the eventual Mega Lucario ex. This is exactly the
   `snipe-the-evolving-threat` signal that baseline_snipe.py:67 RETIRED assuming `snipe-the-top-threat`
   subsumed it — it does not fire here. Restore/replace it: a rung that lifts a bench **pre-evolution whose
   `forward_max_damage` reaches a win-condition-class body**, competitive with the forced-promotion pick.
2. **Energy-attached imminence (81785223 f39/f45).** The benched Lillie's Clefairy ex carries Energy
   (`energies=[6]`) — the only energized bench body, closest to attacking — yet `snipe-the-threat` (+20,
   `target_is_threat`) did NOT fire on it (agent sniped an energyless Latias ex). Verify why
   `target_is_threat`/imminence is not asserting for the energized bench target here.
3. **Attacker-line over bulky support under forced promotion (82753102 f85).** Opp Active (Kadabra) is
   dead → `snipe-the-forced-promotion` fires, but it picks **Dudunsparce (140hp, a bulky support Stage-1)**
   over the **Kadabra → Alakazam attacker line (80hp)** the human wants. The forced-promotion target
   selection ranks by bulk/"ready", not by which line is the real attacker — reconcile its target pick so
   an attacker line beats a bulky support body.

WHY it wins: the human (domain expert) corrected this **consistently across 4+ games**; the enabling signal
(`forward_max_damage`) already exists, only the consuming rung / gating is missing or mis-prioritised.
NOTE the interaction budget: the new/restored rung must reconcile with the deliberate ADR-0044
forced-promotion read (do not silently regress its energized-imminence-mirage suppression) — an
authoring-time concern for update-strategy's grill.

---

## lethal-recover-the-energy-that-wins
- id: lethal-recover-the-energy-that-wins
- source: blunder-buster
- target_layer: planner-code
- candidate_signal: Lethal Solver generator (ADR-0030/0037, planner.py) — the missing lethal-line steps:
  (a) a search/recover step that pulls a Basic Energy enabling a this-turn KO; (b) a **retreat-to-a-
  benched-attacker** promote step (the ko_for_prizes retreat line already exists — extend it into the
  win/KO generator); (c) **stacking damage-boost Items** (Premium Power Pro +30 / Black Belt's Training
  +40, already in the CardStat boost model) to reach a KO threshold. `live_trace.lethal` was null while a
  KO/win existed in all four states.
- verification_contract: verifier
- provenance: correction 84897262:f110 (mega_starmie) | correction 84889011:f24 (mega_lucario, CRITICAL) |
  correction 84890060:f26 (mega_lucario, CRITICAL) | correction 84890060:f48 (mega_lucario) | fixtures
  tests/fixtures/corrections/ms_lethal_recover_energy_to_win_f110.json,
  ml_lethal_retreat_boost_to_ko_f24.json, ml_lethal_recover_energy_retreat_ko_f26.json,
  ml_lethal_recover_energy_via_gong_f48.json | see [[lethal-solver-plan]]
- status: applied
- for: general

**Spec (authoring spec — thin fodder):**
CROSS-AGENT planner-code cluster (mega_starmie + mega_lucario, 2 CRITICAL): across four states a this-turn
**KO or outright WIN** existed whose enabling first step was a resource/positional move the Lethal Solver's
generator does not compose, so `live_trace.lethal` was null and the agent developed instead at the
fetch/attach select. Per ADR-0030 routing this is planner-code, never a weight. The KO-oracle + attach
affordability primitives already exist (`_can_ko`, `predicted_damage`, best-hand-attach, the ko_for_prizes
retreat line, the CardStat damage-boost model); the gap is the **generator** that considers these enabling
steps as part of a lethal line. Four instances, three enabler shapes:

1. **Recover/search the missing Energy (ms 84897262:f110).** Turn 14, my Active Mega Starmie ex 0 Energy,
   bench empty; opp Active Mega Lucario ex at **10 HP**; 2 prizes left. Agent played Night Stretcher
   (correct) but at the recover select grabbed **Staryu** (fetch/develop = 50) over the **Basic {W}
   Energy** (`fetch-energy-when-starved` 35). Recover W → attach → Jetting Blow (120 ≥ 10) → KO → last 2
   prizes → **WIN.**
2. **Search the missing Energy + retreat into a benched attacker (ml 84890060:f26, CRITICAL).** Turn 3,
   my Active Lunatone (1 {F}); benched **Mega Lucario ex 340/340, 0 Energy**; opp Active **80 HP**. Fetch
   a {F} ([1], scored 0) instead of a Riolu ([2], `fetch-base-before-stranded-payoff`+`prefer-wincon-line-
   piece` = 38) → attach to Mega Lucario → free-retreat Lunatone → promote Mega Lucario → **Aura Jab 130 ≥
   80 KO** (and its rider recycles 2 discard {F} to the bench). Same energy-fetch gap as #1 **plus** the
   retreat-to-a-benched-attacker promote step.
3. **Same shape via an Energy tutor (ml 84890060:f48).** Turn 7 ToHand: agent grabbed **Lillie's
   Determination** [0] (`grab-a-draw-supporter-in-setup` 10) over **Fighting Gong** [9] (scored 0) —
   Fighting Gong tutors the {F} that, attached + free-retreat into the ready attacker, delivers the KO.
4. **Stack damage-boost Items + retreat to promote the attacker (ml 84889011:f24, CRITICAL).** Turn 3,
   opp Active **130/130 with an EMPTY bench** (KO = win); I hold **2× Premium Power Pro** + a {F} Energy,
   benched Solrock, benched Lunatone. Line: attach {F} → Solrock ([5]), retreat Lunatone → promote Solrock,
   play **2× Premium Power Pro (+30 each)** → **Cosmic Beam 70+30+30 = 130 = OHKO → WIN** (Lunatone stays
   benched so Cosmic Beam is live; Cosmic Beam ignores W/R). Agent attached to Riolu [6] instead. The
   generator must compose retreat-to-a-benched-attacker **and** stacking the boost Items to reach the KO
   threshold — both already-modeled primitives, never composed into a lethal line.

WHY it wins: two outright thrown WINS (f110, f24) + a missed KO with prize+recycle (f26) — the highest-
value blunder class. All enabling primitives exist; only the solver's line-generator is missing the
compose. `update-strategy` verifies each fixture: decide() takes the lethal-enabling step (the winning grab
/ attach) and `find_lethal_line` locks the KO. NOTE the single-turn boundary — every instance is one of MY
turns (ADR-0031); nothing here needs the deferred multi-turn layer.

---

## discard-a-draw-duplicate-before-an-evolution-tutor
- id: discard-a-draw-duplicate-before-an-evolution-tutor
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: CardStat `cardType`==Supporter + Function Tags (`draw` vs `rush_evolve`/`tutor_mega`) + `card_is_hand_duplicate` — all EXIST; a discard-priority tie-break rung in doctrine_fetch.py's discard side
- verification_contract: verifier
- provenance: correction 83967840:f54 | fixture tests/fixtures/corrections/ms_discard_draw_dupe_before_tutor_f54.json
- status: applied
- for: general

**Spec (authoring spec — thin fodder):**
At a forced 2-card discard with **2 Salvatore + 2 Lillie's Determination** in hand, the agent shed
`[Cinderace (dead opener, +20), Salvatore]` where the human wanted `[Cinderace, a Lillie's]` — keep the
**evolution tutor** (Salvatore, rush-evolve — the deck's only way to field a 2nd Mega Starmie), pitch a
**redundant draw Supporter** (Lillie's, held in 2 copies, plentiful). Both Salvatore and Lillie's currently
fire the SAME rungs — `discard-the-hand-duplicate` (+12) + `keep-engine-supporter-at-discard` (−8) = +4 —
so they TIE and the index tie-break sheds Salvatore first. Add a discard tie-break: **among equal
hand-duplicates, a redundant `draw` Supporter is more sheddable than a `rush_evolve`/`tutor_mega` evolution
tutor** (the tutor is the scarcer, line-enabling value). A small positive shed-bump on the draw duplicate
(or a mild keep-floor on the evolution tutor while the line isn't assembled) breaks the tie the human's way.
Signals all exist; no new infra.
