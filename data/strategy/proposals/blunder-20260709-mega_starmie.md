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
- candidate_signal: Lethal Solver generator (ADR-0030/0037, planner.py) — a search/recover step that pulls a Basic Energy enabling a this-turn KO; `live_trace.lethal` was null while a win existed
- verification_contract: verifier
- provenance: correction 84897262:f110 | fixture tests/fixtures/corrections/ms_lethal_recover_energy_to_win_f110.json | see [[lethal-solver-plan]]
- status: open
- for: general

**Spec (authoring spec — thin fodder):**
A **won game was thrown at a grab select.** Turn 14: my Active Mega Starmie ex has **0 Energy**, bench
empty; opp Active is **Mega Lucario ex at 10 HP** (prize_value 3); I have **2 prizes left**. The agent
played Night Stretcher (correctly — `recover-to-refill-bench`) and, at its ToHand recover select, grabbed
a **Staryu** (`fetch-base-before-stranded-payoff`+`prefer-wincon-line-piece`+`fetch-a-starter` = 50) over
the **Basic {W} Energy** (`fetch-energy-when-starved` = 35) sitting in the discard. But recovering the W
Energy → attach → **Jetting Blow (120 ≥ 10) → KO the 10-HP Mega Lucario ex → take my last 2 prizes → WIN.**
`live_trace.lethal` is null → **the Lethal Solver's generator missed this win-shape** (a discard-recover /
search that supplies the one Energy a this-turn KO needs). Per ADR-0030 routing this is planner-code, never
a weight: extend the solver (or make the grab/recover select honor a solver-locked lethal) so a
recover/search step that completes a this-turn winning KO is generated and forces the winning grab. The
KO-oracle + attach affordability primitives already exist (`_can_ko`, `predicted_damage`, best-hand-attach)
— the gap is the generator that considers *recovering the missing Energy* as a lethal step.

---

## discard-a-draw-duplicate-before-an-evolution-tutor
- id: discard-a-draw-duplicate-before-an-evolution-tutor
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: CardStat `cardType`==Supporter + Function Tags (`draw` vs `rush_evolve`/`tutor_mega`) + `card_is_hand_duplicate` — all EXIST; a discard-priority tie-break rung in doctrine_fetch.py's discard side
- verification_contract: verifier
- provenance: correction 83967840:f54 | fixture tests/fixtures/corrections/ms_discard_draw_dupe_before_tutor_f54.json
- status: open
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
