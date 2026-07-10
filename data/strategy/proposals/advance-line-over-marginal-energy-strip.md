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
- status: open

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
