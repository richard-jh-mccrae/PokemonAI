<!-- Strategy Proposal queue — filed 2026-07-11 by the ADR-0050 DoD#3 audit (blunder-buster-class finding).
Contract: .claude/skills/update-strategy/references/strategy_proposal_contract.md

WHY THIS FILE: DoD#3 of the multi-step lethal verification tool (docs/adr/0050-multi-step-lethal-verification-tool.md)
re-verified the applied lethals end-to-end. mega_lucario f24 is a REAL this-turn win the Pilot misses — a
damage-boost-Item composition no `_family_win_candidates` tier builds and no decide() hook steers. The
verification tool (its prior blocker) now EXISTS, so this is drainable, not blocked. Sibling of the still-deferred
`capability-gap-retreat-to-item-lock.md` and `lethal-retreat-enabler` (docs/todo/lethal-retreat-tool-enabler.md):
same retreat→promote→act shape, different enabler (a damage-boost Item instead of a retreat Tool / an energy fetch). -->

## promote-and-boost-to-lethal (Lethal Solver generator + steering)
- id: damage-boost-item-lethal
- source: blunder-buster
- target_layer: planner-code
- for: general
- candidate_signal: needs a new signal — a new `_family_win_candidates` tier (src/common/strategy/planner.py) that composes **promote a benched {F} attacker → play N damage-boost Items → swing lethal**, min-bound sound; PLUS decide() follow-up steering hooks (retreat the Active, promote the RIGHT benched body, play the boost Item(s), attack) so the cascade completes. DEPENDENCY: a `damage_boost_active` behavioral read for Premium Power Pro (card id 1141, "+30 dmg to your opponent's Active from your {F} Pokémon this turn") — currently untagged; model it like the Ignition/`discard_eot` burst in `_attach_provided`/`_best_affordable_ko_value` (a per-turn flat rider on the attacker's damage, typed to {F}, capped by copies in hand + Item-play legality).
- verification_contract: verifier
- provenance: docs/adr/0050-multi-step-lethal-verification-tool.md (DoD#3) | correction 84889011:f24 | fixture tests/fixtures/corrections/ml_lethal_retreat_boost_to_ko_f24.json (seeded: search_begin_input + own_prizes) | pinned target tests/strategy/test_lethal_helpers.py::test_engine_confirms_multi_step_line_proves_a_real_missed_win | [[retreat-to-promote-deferrals]] | [[lethal-verification-tool-grill]]
- status: open

**Spec (authoring spec — thin fodder, not finished code):**
The Lethal Solver's ONE generator family (`_family_win_candidates`, ADR-0037) has no tier that reaches a win
by **boosting a benched attacker's damage with an Item, then promoting it**. At f24 (my prizes 6, opp Active
Duraludon 130 HP, **opp bench empty**) the sound line is a bench-empty win:

> attach {F}→Solrock (bench) → play 2× **Premium Power Pro** (+30 each to {F} attacks vs the opp Active) →
> retreat Lunatone (its {F} pays the retreat cost) → promote Solrock → **Cosmic Beam 70 + 60 = 130**, an
> exact OHKO of Duraludon 130. Opp has no Pokémon to promote → win (`docs/rules.md` §7.2).

`engine_confirms` returns **True driving the full explicit line** and **False on `[correct]`-only** — the win
is real, but `decide()` picks Meowth ex (a setup tutor) and never composes the line, so at runtime it is
missed. (Cosmic Beam's "does nothing without Lunatone on your Bench" is satisfied *after* the retreat benches
Lunatone; its "damage isn't affected by Weakness/Resistance" does NOT block the Item, which adds "before
applying Weakness and Resistance".)

This is a **capability-gap (planner-code), NOT a weight/when()**. A naive "play Premium Power Pro" or "attach
to a benched Solrock" rule is inert or harmful in isolation — the value exists only as one step of the whole
composition. The fix is a generator that builds the full boosted line, min-bound sound (worst-coin floors,
exact prize/bench-empty win test, typed {F} boost affordability), engine-verified on every lock; plus the
follow-up steering so `decide()` drives retreat → promote-the-boosted-attacker → play-the-Item(s) → attack.
The Solver's one catastrophic error is a PHANTOM win, so author the follow-up encodings against
`tools/sim/lethal_probe.py` (real select encodings), never guessed.

**Guardrails (definition-of-done):**
- **Inert** where no benched {F} attacker + damage-boost Item combine to a KO-that-wins (verify no-op on
  mega_starmie; and on the mega_lucario boards where the win isn't there — e.g. f26/f48, which are KOs not
  wins, must NOT be mis-generated as wins).
- **Sound win test only** — the boosted KO must take my last prize OR empty the opp bench (rider snipes
  under-counted); a boosted KO that merely takes a prize is NOT a win and belongs to the tactical layer, not
  this tier.
- **Typed, capped boost** — the +30 applies only to a {F} attacker vs the Active, only for Items actually in
  hand and legally playable this turn; never assume a boost the board can't fund.
- **Promote the boosted body, not a bare copy** — reuse `best_promote_slot` / `is_best_promote_target` so the
  retreat/SWITCH pick brings up the Solrock carrying the {F}, not the other one.

**Verify:** the ADR-0050 engine-cascade gate (authoring-gates.md → `planner-code`, multi-step lethal).
- *Target is real (already pinned):* `engine_confirms(f24, pilot, line=<full line>) is True`.
- *Fix works:* once the tier + steering hooks ship, `engine_confirms(f24, pilot) is True` on the
  `[correct]`-only form (decide() now completes it) + suite-green (`python -m pytest tests/ -q`) + a focused
  `tests/strategy/test_planner*.py` gating f24's state. A closed-form-only line (recognition fires, cascade
  refutes) is a false-green → `engine_confirms` returns False.

**Priority / relation.** Sibling of two deferred retreat→promote compositions ([[retreat-to-promote-deferrals]]):
`lethal-retreat-enabler` (energy/Tool enables a free retreat into a benched attacker) and
`capability-gap-retreat-to-item-lock` (disruptor, tempo not lethal). All three want the same generator shape —
**retreat → promote a benched body → act** — differing only in the enabler and the goal. Worth grilling whether
one generator family covers the lethal variants (damage-boost-Item + retreat-enabler) before authoring
separately. Now UNBLOCKED: the engine-backed verification tool they all waited on is built (ADR-0050).
