<!-- Strategy Proposal — SPLIT OUT of play-energy-denial-threat-and-ko-aware during the /update-strategy
grill (2026-07-09). f6 (worthless strip) was closed by the `opp_active_can_damage_us` gate; f32 needs a
DIFFERENT mechanism (develop-priority) a damage-gate can't provide. Contract:
.claude/skills/update-strategy/references/strategy_proposal_contract.md -->

## advance-the-line-over-a-marginal-energy-strip
- id: advance-line-over-marginal-energy-strip
- source: blunder-buster
- target_layer: general-hypothesis
- for: general
- candidate_signal: a NEW `opp_active_can_ko_us` (the affordable-KO mirror of `_active_can_ko` pointed at us — sibling of the just-shipped `opp_active_can_damage_us`, but with a KO threshold) + `advance-the-evolution-line` (+15, baseline_evolution) vs `play-energy-denial` (+20). Reconcile so a NON-survival strip (opp can hurt us but can't KO us) yields to advancing the win-condition line.
- verification_contract: verifier
- provenance: correction 85046350:f32 (CRITICAL) | fixture tests/fixtures/corrections/dragapult_hammer_over_develop_f32.json | split from `play-energy-denial-threat-and-ko-aware` (data/strategy/proposals/blunder-20260709-dragapult_ex.md, applied 2026-07-09)
- status: applied

**Spec (authoring spec — thin fodder):**
f32 (CRITICAL), turn 4: my Active **Dreepy** (70 HP, 1 {F}); opp Active **Cynthia's Gabite** (Dragonslice
{F} = **40**, cannot KO our 70-HP Dreepy); a wincon-line **evolve Dreepy→Drakloak** is on the menu. The
agent plays **Crushing Hammer** (`play-energy-denial` +20) over the **evolve** (`advance-the-evolution-line`
+15). Human (CRITICAL): don't spend the Hammer on a low-value strip — advance the line toward the
Phantom-Dive KO.

**Why a damage-gate can NOT fix this (the reason it's split out).** The applied `opp_active_can_damage_us`
gate stands play-energy-denial down only when the opp can't hurt us AT ALL (f6, Kyogre = 0). Here Gabite
deals 40 (>0), so that gate keeps the strip live — correctly, because the SAME "opp can't KO us but can
chip" shape is a *wanted* strip in a race (test_blunder_20260629 `test_play_energy_denial_sequences_the_
strip_before_a_higher_value_attack`) and in setup (`..._fires_in_setup_against_a_developing_attacker`). A
KO-threshold gate on play-energy-denial would break both. So f32 is NOT "don't strip a harmless body" — it
is **"advancing the win-condition line outranks a marginal, non-survival strip."**

**Author (general):** a rung that lets `advance-the-evolution-line` (or a broader "develop the wincon line"
signal) beat a `play-energy-denial` strip **when the strip is non-survival** — i.e. gate on a new
`opp_active_can_ko_us` (False here: Gabite 40 < 70) so the reconciliation fires only when denying the
opp's Energy does NOT prevent a KO of us. Keep it inert where the strip IS survival (opp can KO us → strip
wins) and where no wincon-line develop competes (test 239/257 unaffected — they have no evolve on the menu).
Score math to beat: play-energy-denial +20 vs advance-the-evolution-line +15 (drop the mis-fit tuned nudge
if any). **Gate:** f32 flips [2]→[1] (Evolve); no regression on the play-energy-denial ledger
(test_blunder_20260629 :239/:257/:273/:286) or the mega_starmie corpus. Card facts (Gabite Dragonslice
{F} 40, Dreepy 70 HP) are engine ground truth — verify at source.

**update-strategy verdict (2026-07-10): APPLIED — REFRAMED to a Turn-Planner maneuver (f32 retreat frame; f20's attach-half stays deferred — see below).**
The grill rejected the "boost the evolve over the strip" framing: this is NOT evolve-vs-strip, it is the
**retreat-to-promote-the-sacrificial-wall** maneuver (dragapult control identity). My fragile developing
Dreepy (a win-condition LINE pre-evo) retreats behind a benched **Budew** item-lock wall — retreat →
promote Budew → evolve the benched Dreepy→Drakloak (Recon dig) → Crushing Hammer → Itchy Pollen. Budew is
sacrificial; the line assembles safely behind it. This is the SAME maneuver family as the deferred
`retreat-to-promote-disruptor` (f20, same episode 85046350), but the two fixtures capture DIFFERENT frames:
f32 (this record) is the RETREAT frame (Dreepy already energized → retreat now) and is CLOSED here, while
f20 is the earlier ATTACH-enablement frame (Dreepy @0e → feed the active to enable the retreat) which the
shared rung does NOT touch and which STAYS DEFERRED (re-probed 2026-07-10: f20 decide()=[1] unchanged — see
its record `capability-gap-retreat-to-item-lock.md`). Authored as `planner-code`: Board signal `can_wall_line_with_disruptor` (+ helper
`_can_wall_line_with_disruptor`), NEW `retreat-to-wall-the-line` rung (+30, baseline_retreat.py),
`hold-position-in-setup` stands down under the premise, and a **tier-0 branch in `_finish_turn_last`** so
the retreat is sequenced as STEP 1 (the tier system otherwise pins RETREAT to tier 4). VERIFIED
single-frame per the grill (a tempo maneuver's partial completion is non-catastrophic — unlike the lethal
f15, which stays deferred): decide() picks **Retreat [3]** (+30) over the tier-0 evolve (+15) / Hammer
(+20); the follow-through rides existing rungs (`promote-the-staller` on `item_lock`,
`advance-the-evolution-line`, `play-energy-denial`). Fixture `correct` reframed [1]→[3]; full suite green;
pinned by `test_blunder_20260710_split_fixes.py::test_f32_...`. Inert for decks without a benched item-lock
opener (no-op on mega_starmie / mega_lucario). GAIN rides the ladder.
