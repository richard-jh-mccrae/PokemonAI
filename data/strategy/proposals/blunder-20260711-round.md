<!-- Strategy Proposal queue — blunder-buster round 2026-07-11 (all agents).
Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md
Worklist this round = 7 open corrections (dragapult_ex 0, mega_lucario 2, mega_starmie 5).
Terminal outcomes (see the round ledger at the bottom of docs/tuning/runs/ + reviewed.json):
  proposal-routed 5 — 85164605-6 + 85163079-51 + 85058574-16 + 85164605-41 (below); 85164131-22 (CRITICAL)
                       folded into the OPEN blunder-20260709-mega_starmie.md#snipe-the-real-attacker-not-a-bulky-body.
  refuted 1 — 82749168-38 (benched Tera snipe-immune). [Two initial refutes REVERSED 2026-07-11 after human
              verification: 85058574-16 (Lunar Cycle IS correct — deck rule over-fires) and 85164605-41 (Mega
              Signal IS cheaper — the Staryu were evolvable this turn, so Item-fetch+evolve = the Supporter's
              result but preserves the Supporter; planner should prefer the cheapest evolution enabler).]
  covered 1 — 85058574-109 (dragapult_ex Brief already races the Drakloaks; decide()==correct degenerate;
              the multi-turn EXECUTION residual is parked in docs/todo/deferred-multi-turn-criticals.md).
Routing evidence = real-Pilot retests (tools/train/retest_one.py) + card/rule facts read at source. -->

## dont-tutor-a-wincon-with-no-base-to-deploy
- id: dont-tutor-a-wincon-with-no-base-to-deploy
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: reuses `Board.wincon_base_deployable` (=_payoff_immediate_preevo_available, pilot.py:174/2689) + `Board.wincon_in_hand` (:164) + `Context.search_redundant_wincon` (:614/2251) — all EXIST; the fix widens the signal that the existing veto already keys on. No new infra.
- verification_contract: verifier
- provenance: correction 85164605:f6 (mega_starmie) | fixture tests/fixtures/corrections/ms_premature_wincon_tutor_no_base_f6.json | related: the OPEN sibling 85164605:f41 is REFUTED (at turn 5 a Staryu base IS on the bench, so this same signal correctly stays silent there and Salvatore/Mega Signal are productive — the widen does not touch it)
- status: applied (sound rework 2026-07-14; the original −45 widen stays refuted)
- resolution (2026-07-14, deferred-cleanup): the SOUND rework the refute called for ("turn-1 + accelerator-
  active + productive-alternative distinction, plus resequencer-aware ≤0 suppression") is now BUILT as a
  SEPARATE, narrow veto `dont-tutor-the-baseless-wincon-turn-one` (doctrine_fetch.py, −55). It reads a NEW
  third search signal `search_baseless_wincon` (a wincon-ONLY tutor whose payoff is neither in hand/play NOR
  has a deployable base — DISTINCT from `search_redundant_wincon`, so the good-case doctrine is untouched) and
  fires ONLY on `turn<=1 AND reusable_energy_in_hand` (the productive-attach distinguisher). −55 CANCELS the
  full +53 free-dig stack, driving Mega Signal to score ≤0 → `_finish_turn_last` tier 4 (behind the tier-2
  attach) — resequencer-aware, exactly as the refute demanded (merely beating the attach on score leaves it
  tier-0). f6 now FIXED (retest_one + pin test_dont_tutor_the_baseless_wincon_turn_one_f6); the good
  `play-a-tutor-for-the-unfound-wincon` setup tests stay green. The refuted −45-widen approach below remains
  refuted — this is a different, sound mechanism.
- resolution (2026-07-12, update-strategy): REFUTED. The specced −45 widen is unsound on two counts.
  (1) It does NOT flip f6: `decide()` resequences by TIER (`_finish_turn_last`) before score — Mega Signal is a
  tier-0 free dig, so even after the widen drops it 53→8 (below the +18 attach) it still plays before the
  tier-2 attach. Flipping f6 requires driving Mega Signal ≤0 (tier-4), not merely below the attach.
  (2) The widen regresses two green tests encoding the OPPOSITE, sound doctrine — `search-the-confirmed-hit` /
  `play-a-tutor-for-the-unfound-wincon` (+25): "tutor your provably-in-deck win-condition during setup, develop
  the base over coming turns." f6's board (wincon in deck, no base) is exactly that shape, so f6's correction
  directly contradicts an established doctrine. Human verdict: refute. A sound rework (turn-1 + accelerator-active
  + productive-alternative distinction, plus resequencer-aware ≤0 suppression) would be its own larger proposal.
- for: general

**Spec (authoring spec — thin fodder):**
Turn 1, mega_starmie: the Pilot plays **Mega Signal** (Item: "search your deck for a Mega Evolution Pokémon
ex, reveal it, put it into your hand", id 1145) to tutor **Mega Starmie ex** (id 1031) into hand — but
Mega Starmie ex is a Stage-1 that evolves ONLY from **Staryu** (id 1030), and we have **no Staryu in play or
hand**, and Mega Signal cannot fetch one. The fetched wincon sits dead; the human wants the productive play,
attach the Basic {W} to the Active **Cinderace** (id 666, the accelerator). `retest_one` (85164605-6):
Mega Signal scores **53** (`dig-before-commit` 20 + `fetch-when-it-fills-a-need` 8 +
`play-a-tutor-for-the-unfound-wincon` 25) vs the attach **18** — so it wins.

The existing general veto **`dont-tutor-the-held-wincon`** (weight −45, doctrine_fetch.py:459-467) is exactly
the right rung, but its trigger `Context.search_redundant_wincon` — computed in `FetchMixin._search_signals`
(doctrine_fetch.py:106-109) — gates its "undeployable" branch behind `board.wincon_in_play`, so on this
turn-1 board (wincon neither in play NOR in hand) it stays False and the veto is silent. **Widen** the
undeployable branch to fire whenever a **wincon-only** tutor's payoff has no deployable base:
`redundant = bool(wincon) and fetch_set ⊆ wincon and (board.wincon_in_hand or not board.wincon_base_deployable)`
(drop the `board.wincon_in_play` conjunct). The `fetch_set ⊆ wincon` guard keeps flexible tutors (that could
fetch a base) silent; `not wincon_base_deployable` leaves the normal "base benched → fetch the Mega" flow
untouched. Net on f6: Mega Signal 20+8+25−45 = **8 < 18** → attach wins, **FIXED**. Soft (the tutor still
beats End), no new rule/weight — this repairs the signal the existing veto reads.

WHY it wins: tutoring a wincon you cannot deploy is a pure tempo waste turn-1; the human's instinct
("fetching a Mega Starmie here doesn't help us") is the general "don't dig for a payoff with no way to use
it" doctrine, and the veto that encodes it already exists — only its trigger under-fires. The refuted sibling
f41 (turn 5, Staryu on bench) is the built-in counter-fixture proving the widen stays silent when a base IS
deployable.

---

## go-for-broke-on-the-doomed-active-when-the-attach-completes-a-bigger-attack
- id: complete-the-biggest-attack-on-the-doomed-active
- source: blunder-buster
- target_layer: general-hypothesis
- candidate_signal: NEW `Context.attach_completes_biggest_attack: bool` — build in pilot.py's attach section of `_make_context` (near `attach_target_under_max` @2195). For an ATTACH onto the ACTIVE: True iff `len(active.energies) < CardStat.maxDamageCost` AND `len(active.energies) + _attach_provided(...) >= CardStat.maxDamageCost` (this attach crosses the Active up to affording its highest-damage attack THIS turn). Reuses real fields: attach_target_area==_ACTIVE, target `energies`, `CardStat.maxDamageCost` (provider.py:38, verified), planner `_attach_provided` (=1 for a plain Energy). Fail-CLOSED (False when maxDamageCost unknown), matching `_attach_target_under_max`.
- verification_contract: verifier
- provenance: correction 85163079:f51 (mega_starmie) | fixture tests/fixtures/corrections/ms_doomed_active_complete_nebula_f51.json | counter-case to protect: ep83037962:f48 (the motivating case of dont-overbuild-the-doomed-wincon — 1W→2W still short of Nebula) must NOT regress
- status: applied
- resolution (2026-07-12, update-strategy): APPLIED. New `Context.attach_completes_biggest_attack`
  (pilot.py `_attach_completes_biggest_attack` + `_make_context`, ACTIVE-only, provided mirrors the planner's
  `_attach_provided`); gated `dont-overbuild-the-doomed-wincon` with `and not c.attach_completes_biggest_attack`
  (baseline_energy.py). f51 → attach-to-Active [1] (+20 build-active-wincon, −45 gated off) vs Cinderace [2] +15,
  FIXED. f48 counter-case (no real replay frame available) guarded by a synthetic boundary UNIT test in
  tests/strategy/test_attach_discipline.py (1W→2W < CCC=3 → signal False → −45 stays). Full suite green.
- for: general

**Spec (authoring spec — thin fodder):**
Turn 6, mega_starmie: our **doomed** Active Mega Starmie ex (id 1031, 210/330, **2 {W}**) faces the
opponent's 380/430 Mega Starmie ex (Hero's Cape) with an **empty bench** — so they Nebula us for 210 next
turn = lethal, our Active IS doomed. The Pilot attaches the turn's {W} to benched **Cinderace** (60/160,
0e) then swings **Jetting Blow** (120, whose +50 bench rider is wasted — opp bench empty). The human wants
the {W} on the **Active**: 2 {W} + 1 = 3 {W} unlocks **Nebula Beam** (210, ignores effects/W-R) for the last
swing before we die ("our Mega Starmie is lost next turn, so be it — hit them with everything").

`retest_one` (85163079-51): attach→active scores **−25** = `build-active-wincon`(+20) +
`dont-overbuild-the-doomed-wincon`(**−45**); attach→Cinderace bench scores **+15** (`power-up-attacker`).
So `dont-overbuild-the-doomed-wincon`'s −45 alone flips the pick. That rule's premise — "the doomed Active
won't live to fire the bigger attack, so don't sink energy into it" — is **false when this very attach turns
the bigger attack ON this same turn**. **Fix:** add `and not c.attach_completes_biggest_attack` to the
`when()` of `dont-overbuild-the-doomed-wincon` (src/common/strategy/baseline/baseline_energy.py:202-205).
The NEW completion signal is required (not a blanket `not attach_target_under_max`): the rule's own
motivating case **ep83037962 f48** is 1 {W} → 2 {W}, still short of Nebula (dies before the 3rd) — a blanket
gate would regress it, but `attach_completes_biggest_attack` is False there (2 < maxDamageCost 3). Predicted:
removing the −45 leaves opt[1] at **+20 > +15** → **FIXED**, and the resulting attack is Nebula 210 vs the
wasted Jetting 120. Not lethal either way (380-HP wall survives both), so a decision-scope `when()`-gate is
correct — no planner/lethal route.

WHY it wins: it lets the agent cash the last productive swing off a doomed body instead of stranding energy
on a bench piece and firing a bench-rider into an empty bench. The distinction ("completes the biggest attack
THIS turn" vs "overbuilds for a turn that won't come") is precise and fixture-guarded on both sides.

---

## lunar-cycle-the-last-{F}-when-the-active-is-a-weak-preevo-and-the-engine-is-online
- id: lunar-cycle-over-last-f-attach-weak-preevo
- source: blunder-buster
- target_layer: deck-strategy
- candidate_signal: `Board.in_play_ids` (LUNATONE + SOLROCK online — the exact gate the sibling `grab-the-playable-item` Gong rule already uses) + `Board.hand_basic_energy` + `Board.energy_placeable` (all EXIST, used by the current rule) + a **weak-active-pre-evo** read: the Active is a pre-evolution whose own affordable attack this turn is a minor chip (≈30) far below its forward form's output — derive from the provider's `forward_max_damage` (pilot.py:2566/3247, EXISTS) vs the Active's own `CardStat.maxDamage`/attack costs. If a clean boolean doesn't fall out, `candidate_signal: "needs a new signal"` (a small `active_is_weak_preevo` in Board scope).
- verification_contract: verifier
- provenance: correction 85058574:f16 (mega_lucario) | fixture tests/fixtures/corrections/ml_lunar_cycle_over_last_f_attach_f16.json | REVERSES the 2026-07-11 initial refute (spun-off investigation, human verdict): Lunar Cycle IS correct; the deck rule over-fires
- status: applied
- resolution (2026-07-12, update-strategy): APPLIED. New qualified `Board.active_is_weak_preevo`
  (pilot.py `_active_is_weak_preevo`: Active is a win-condition line pre-evo whose own maxDamage ≤ ½ its
  `forward_max_damage` — Riolu 30 vs Mega Lucario ex 130/270). Narrowed `dont-lunar-cycle-away-the-last-attachable-f`
  to stand down when engine-online AND weak-preevo active. NOTE: standing the −30 down was NECESSARY but NOT
  SUFFICIENT (Lunar Cycle then sat at 0, below the +13/+10 attaches — the proposal's "narrow the when()" mechanism
  was incomplete), so ALSO added a positive sibling `lunar-cycle-the-weak-preevo-last-f` (+20) firing on the exact
  complement of the guard's stand-down (mutually exclusive by construction). f16 → Lunar Cycle [6] +20 > Solrock
  attach [4] +13, FIXED. Full suite green.
- for: deck:mega_lucario

**Spec (authoring spec — thin fodder):**
Turn 2 (P2), mega_lucario: Active **Riolu** (id 677, pre-evo of Mega Lucario ex) 0e; bench Lunatone (675)
+ Solrock (676); hand holds exactly **one Basic {F}** (the only energy) + Judge×2, Unfair Stamp, Gravity
Mountain. The human wants **Lunar Cycle** (Lunatone Ability: discard a Basic {F} → **draw 3**) — early-game
acceleration off the online Solrock↔Lunatone engine. The Pilot instead attaches the {F} to a bench body
(Solrock, the `attach-solrock-over-line-base` quirk — see NOTE), scoring 0 board progress.

The defect is **`dont-lunar-cycle-away-the-last-attachable-f`** (deck rule, src/agents/mega_lucario/
strategy.py ~L272-285, weight −30) **over-firing**. Its rationale is *"attach the last {F} FIRST, then Lunar
Cycle still fires the same turn on the **surplus** — a hold, not a blanket decline."* That premise is **false
when the single {F} IS the whole attach**: attaching it leaves **no surplus** to cycle, so the guard doesn't
*defer* the cycle — it **kills** it. `retest_one` (85058574-16): Lunar Cycle [6] = **−30** (this rule alone),
buried below both attaches ([2] active Riolu +10, [4] bench Solrock +13). W-route can only nudge it to −27
(competing frames where the rule is correct pin it) → **UNSATISFIED, needs a `when()`-narrowing, not a
weight** (featurization already blames this hypothesis from [6] — no re-tag).

**Narrow the `when()` to stand down** (let Lunar Cycle fire) when BOTH: (a) the Solrock↔Lunatone engine is
online (`LUNATONE in board.in_play_ids and SOLROCK in board.in_play_ids`) — so the discarded {F} is
**Aura-Jab-recoverable** from the pile and the deck is energy-rich (11 {F} + 4 Fighting Gong, a deck
constant); AND (b) the Active is a **weak pre-evo** whose attach only buys a ~30 chip (the payoff of an
attach scales with the ACTIVE's output — Aura Jab 130 / Cosmic Beam 70 — not a soon-to-evolve 30-damage
Riolu). Under both, draw-3 acceleration > 30 chip, and the {F} is not truly "stranded" (recoverable). The
rule must STILL fire (hold the {F}) when the Active is a real attacker whose attach enables a big hit, or the
engine is offline — the verifier gate re-measures the f16 fixture (correct=[6]≻both attaches) AND must
regress none of the frames where the −30 discipline is correct (the T6' probe cases in the rationale).

NOTE — the secondary `attach-solrock-over-line-base` (+3) quirk that tips [4] over [2] among the attaches is
**real but MOOT here** (the correct play is neither attach). Do NOT chase it off f16 — it only bites on a
frame where Lunar Cycle is unavailable / the engine is offline; investigate it there (spun-off task).

---

## ko_for_prizes should evolve with the cheapest enabler (free direct-evolve > Item tutor > Supporter tutor)
- id: planner-prefer-cheapest-evolution-enabler
- source: blunder-buster
- target_layer: planner-code
- candidate_signal: the ko_for_prizes evolution-enabler step in planner.py already commits an evolution tutor (see the covered precedent 83455356:f11, `test_planner_engine.py::test_critical_a212_*`). The missing discrimination = card-cost/type of the enabler: `CardStat.cardType` (Item vs Supporter, EXISTS) + "evolved form already in hand AND pre-evo directly evolvable this turn" (a legal direct-evolve option is present in the select → `appearThisTurn==False` on the pre-evo + the Stage-1 in hand). No new board infra beyond reading the option list the planner already enumerates.
- verification_contract: verifier
- provenance: correction 85164605:f41 (mega_starmie) | fixture tests/fixtures/corrections/ms_prefer_cheap_evolution_enabler_f41.json | REVERSES the 2026-07-11 initial refute (human verdict, verified against the match: the Staryu were played a prior turn → evolvable this turn) | do NOT regress the covered precedent 83455356:f11 (Salvatore IS the only enabler there — no Mega in hand → the Supporter tutor is correct)
- status: applied (both halves — free-evolve 2026-07-12; item-tutor composer 2026-07-14, flag OFF)
- resolution (2026-07-14, deferred-cleanup): the ITEM-tutor half is now BUILT. `_item_evolve_ko_candidate`
  (planner.py) composes play-Item(`tutor_mega`/`tutor_pokemon`) → evolve a this-turn-evolvable in-play body
  (`appearThisTurn==False`, rules.md §4) → attach → KO, requiring the fetched form be provably deck-present
  (`deck_definitely_has`) and fetchable by the item's class, emitting a COMPOSITE line committed at step[0]=the
  Item, tiered at the reserved `_PLANNER_ENABLER_ITEM=4`. Behind the `enabler_item_composer` runtime flag
  DEFAULT OFF (narrowly scoped single-item→single-evolve→attack; broader chains left as TODO). Tests in
  test_deferred_planner_cluster.py. Enable + ladder-validate to activate.
- resolution (2026-07-12, update-strategy): PARTIALLY APPLIED. Built the FREE-DIRECT-EVOLVE half in planner.py
  `_ko_for_prizes_lines`: new `_free_evolve_ko_candidate` branch (type-9 EVOLVE onto a bench body, option presence =
  legality, no `appearThisTurn` read) + a sub-prize cost tier on `ln.value` (`_PLANNER_ENABLER_FREE=8` for
  retreat/free-evolve, `_PLANNER_ENABLER_ITEM=4` reserved, tutor=0) so the cheaper enabler wins `max()` without
  outranking a real prize/survival delta. Human-locked target: f41 → [4] free direct-evolve (fixture correct
  [3]→[4], correct_label updated; new test_f41 in test_planner_engine.py). a212/f11 (Salvatore-only) stays green —
  the tier only reorders when a cheaper enabler co-exists. Full suite green.
  DEFERRED — the ITEM-tutor half (prefer Mega Signal over Salvatore when NO free-evolve exists, the 2nd-Staryu
  frame not in this fixture). Definition-of-done: a multi-step enabler composer that recognises an Item whose
  fetch target is an evolution of an in-play, this-turn-evolvable body, verifies the fetched form is deck-present
  (tracker), and emits a COMPOSITE lethal line whose first committed step is the Item but whose value reflects the
  downstream evolve+attach KO. The generator currently emits one TurnLine per single option and cannot chain
  play-item(fetch) + separate manual-evolve; `_PLANNER_ENABLER_ITEM` is wired and waiting for that composer.
- for: general

**Spec (authoring spec — thin fodder):**
Turn 5 (P2), mega_starmie. Board (verified from the f41 obs): Active **Cinderace** (1e); **bench 2× Staryu, BOTH
`appearThisTurn=False` → evolvable this turn** (bench0 carries **3 {W}**); hand = **Mega Starmie ex** (1),
**Mega Signal** (Item), **2× Salvatore** (Supporter), Boss's Orders, Lillie's, Wally's, Ultra Ball. Opp Active
Kadabra 80/80. The Planner's `ko_for_prizes` line commits **Salvatore** (`planned` step[0], "evolution tutor
unlocks a 1-prize KO") — a **Supporter** — to field a Mega Starmie ex attacker. The human: *"Mega Signal, an
Item, is less expensive than a Supporter — just play that instead"* (correct=[3]).

The human is right, and the initial refute (that Mega Signal "only hand-fetches, doesn't evolve" and would be a
"redundant duplicate") was **wrong**: because the Staryu is **evolvable this turn**, Mega Signal (Item) →
fetch the Mega → the same-turn manual **Evolve** (select options [4]/[5], type-9, are legally offered) reaches
the identical board as Salvatore's search-evolve — but **spends an Item, not the scarce Supporter** (Boss's
Orders is in hand and wants that Supporter slot for a gust-KO). And with **two** Staryu and only one Mega in
hand, the fetched 2nd Mega is not redundant. Both tutors score an identical −17 in the weight layer
(`dig-before-commit` +20, `dont-tutor-the-held-wincon` −45, `fetch-when-it-fills-a-need` +8), so scoring can
never break this — **the Planner commits Salvatore**, so the fix is planner-code, never a weight/when().

**Author:** in the `ko_for_prizes` evolution-enabler selection, rank enablers by cost — prefer, in order,
(1) a **free direct-evolve** (the evolved form is already in hand and the pre-evo is directly evolvable this
turn — options [4]/[5] here, strictly the cheapest: no card leaves the deck, no tutor spent), then (2) an
**Item** tutor (Mega Signal), then (3) a **Supporter** tutor (Salvatore). The human's correct=[3] is the
**floor** (anything-but-the-Supporter); the true optimum is arguably the free direct-evolve [4] — resolve the
exact target at authoring (the fixture pins correct=[3]; if the author lands on [4], update the fixture and
note it). **Regression guard:** the covered precedent **83455356:f11** must stay green — there the Mega is NOT
in hand and Salvatore is the *only* enabler, so the Supporter tutor is correctly committed
(`test_planner_engine.py::test_critical_a212_*`).
