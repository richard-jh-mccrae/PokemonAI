<!-- Strategy Proposal queue — blunder-buster round 2026-07-11 (all agents).
Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md
Worklist this round = 7 open corrections (dragapult_ex 0, mega_lucario 2, mega_starmie 5).
Terminal outcomes (see the round ledger at the bottom of docs/tuning/runs/ + reviewed.json):
  proposal-routed 3 — 85164605-6 + 85163079-51 (below); 85164131-22 (CRITICAL) folded into the OPEN
                       blunder-20260709-mega_starmie.md#snipe-the-real-attacker-not-a-bulky-body cluster.
  refuted 3 — 82749168-38 (benched Tera snipe-immune), 85164605-41 (Salvatore evolves-in-place ≠ Mega
              Signal hand-fetch), 85058574-16 (Lunar-Cycle-away-the-last-{F} forgoes a 30-dmg attack).
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
- status: open
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
- status: open
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
