<!-- Strategy Proposal queue — filed 2026-07-11 by the ADR-0050 DoD#3 audit (blunder-buster-class finding).
Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md

WHY THIS FILE: the DoD#3 audit (docs/adr/0050-multi-step-lethal-verification-tool.md) hand-drove mega_lucario
f26/f48 through the seeded engine and found their ideal lines are KOs, NOT this-turn wins (Tangela is a
1-prize target and the opp bench is full → the KO takes a prize but passes to the opponent). So they are
CORRECTLY refuted by engine_confirms (a WIN gate) — NOT closed-form-only, NOT missed wins, and NOT filed as
lethal. But the audit surfaced a separate, real TACTICAL defect underneath: decide()'s post-grab cascade
promotes the WRONG benched body and forfeits the KO. This record captures that KO-quality steering gap.
Distinct from the sibling `capability-gap-damage-boost-item-lethal.md` (f24, a real missed WIN). -->

## promote-the-KO-attacker after an energy grab (tactical cascade steering)
- id: promote-ko-attacker-post-grab
- source: blunder-buster
- target_layer: planner-code
- for: general
- candidate_signal: extend an existing signal — the post-grab tactical cascade / promote-target valuation (`_grab_lethal_tactical` and the promote-slot picker `best_promote_slot` / `is_best_promote_target`, src/common/strategy/). After a grab that yields the Energy a benched attacker needs, the retreat→promote must bring up the benched body whose affordable attack **KOs the opp Active**, and attach the fetched Energy to THAT body — not a lesser benched attacker whose swing does not KO. KO-aware promote/attach, not "promote the highest-HP" or "promote any ready attacker".
- verification_contract: verifier
- provenance: docs/adr/0050-multi-step-lethal-verification-tool.md (DoD#3 audit) | corrections 84890060:f26, 84890060:f48 | fixtures tests/fixtures/corrections/ml_lethal_recover_energy_retreat_ko_f26.json, ml_lethal_recover_energy_via_gong_f48.json (both seeded: search_begin_input + own_prizes) | [[lethal-verification-tool-grill]] | [[retreat-to-promote-deferrals]]
- status: open

**Spec (authoring spec — thin fodder, not finished code):**
At f26 (my prizes 6; my Active Lunatone 110/1{F}/retreat 1, Bench Solrock 110/0E and **Mega Lucario ex**
340/0E; opp Active **Tangela 80**, opp Bench full — Tangela + Dwebble + Teal Mask Ogerpon) the grab fix is
applied — `decide()` correctly fetches the Basic {F} Energy. But the post-grab cascade then **promotes
Solrock and swings Cosmic Beam 70 < 80 → no KO** (probe-verified: ctx-3 promote → Solrock). The KO line was
right there:

> attach the fetched {F} → **Mega Lucario ex** (Bench) → retreat Lunatone (its 1 {F} pays retreat 1) →
> promote **Mega Lucario ex** → **Aura Jab 130 ≥ Tangela 80 → KO** (Aura Jab then reattaches up to 3 {F}
> from discard to the Bench, re-arming the line).

f48 is the same board and same defect via a Fighting Gong fetch (two benched Mega Lucario ex). Card facts
verified at source: Solrock **Cosmic Beam {F} 70** ("does nothing without Lunatone on your Bench"); Mega
Lucario ex **Aura Jab {F} 130**; Lunatone retreat 1 with 1 {F} attached (retreat is payable).

**Why this is tactical, NOT lethal (and why `engine_confirms` must NOT gate it).** Tangela is a 1-prize
regular Pokémon and the opponent's Bench is full, so the KO takes one prize (6→5) and passes the turn — a
real KO, not a this-turn win. `engine_confirms` (the ADR-0050 WIN gate) therefore refutes these lines *by
category*, and is the wrong gate here. The defect is that a 130-damage KO of the Active is strictly better
than a 70-damage non-KO, and the cascade picks the worse body. This is KO-quality tactics (prize + tempo),
so it routes to the **tactical / promote-valuation** layer, not the Lethal Solver.

**Why not a naive weight/when().** "Promote Mega Lucario ex" or "attach to the wincon" in isolation is inert
or harmful — the value is the whole *attach-to-the-KO-body → retreat → promote-that-body → attack*
composition landing the KO. The fix is a **KO-aware promote/attach valuation**: when a benched body, given
the Energy now attachable (in hand / just fetched / on the retreating Active), has an affordable attack that
KOs the opp Active, prefer promoting THAT body (and attaching the Energy to it) over a benched attacker that
does not KO. Reuse the min-bound damage/affordability oracle already behind `_develop_wins` /
`_best_affordable_ko_value`, in KO (not win) mode.

**Guardrails (definition-of-done):**
- **KO-gated, not win-gated** — fires only when the promote+attach+attack composition lands a real KO of the
  opp Active; inert when no benched body reaches a KO (must not perturb the develop/setup cascades on boards
  where no KO exists).
- **Typed, funded affordability** — the promoted body's KO must be payable by Energy the board actually
  provides (attached + the one fetched/retreating {F}); never assume Energy the board can't fund; respect
  attack Energy types (an Aura Jab {F} slot is not paid by a wild).
- **Promote the funded body** — bring up the Mega Lucario ex that carries (or receives) the {F}, via
  `best_promote_slot` / `is_best_promote_target`, not a bare copy.
- **KO ≥ non-KO only** — this is a tie-break toward the KO; it must never override a genuine this-turn WIN
  (the Lethal Solver still runs first) nor a forgo-KO directive (ADR-0045 S4) where taking the KO wakes a
  bigger threat.

**Verify (verifier contract — a KO-quality fixtured retest, NOT engine_confirms).**
- *Before→after on the fixtures:* at f26 and f48, `decide()`'s cascade promotes **Mega Lucario ex** and
  lands the **Aura Jab 130 KO** of Tangela (live_trace shows the KO taken / the promoted body = ML ex), where
  today it promotes Solrock and swings 70 for no KO. Surface `chosen`/promote-target before→after.
- *No regression:* suite-green (`python -m pytest tests/ -q`); the applied lethals still behave
  (`ms_lethal_recover_energy_to_win_f110` still confirms; f24's win still targets via engine_confirms); a
  focused `tests/strategy/test_planner*.py` gates the f26/f48 promote-target.
- **Do NOT** add these to the `engine_confirms` multi-step lethal gate — they are KOs, not wins; that gate
  refutes them correctly and is category-mismatched here.

**Relation.** Underneath the same f26/f48 fixtures whose *win-gate* audit outcome is recorded in
docs/adr/0050 (DoD#3) and [[lethal-verification-tool-grill]]. Sibling — but distinct goal — of the missed-win
`capability-gap-damage-boost-item-lethal.md` (f24). All three touch the retreat→promote→act cascade; this one
is the tactical KO-steering slice, cheap relative to the two lethal-generator builds.
