# Seam handoff: attach-target priority (setup — Active vs the 2nd line)

**STATUS: BUILT & PROMOTED 2026-07-19.** The target flipped and is a corpus PIN; grill ruling and
build record in `docs/plans/combat-tempo-cluster-findings.md` §C. Summary: GENERAL role-keyed
stand-down of `prefer-active-attach-in-setup` (off-Line, no attacker Role, benched Line member
un-powered → the `attach_to_needy_line` tie-break develops the line); the §Build-plan sketch
"Active's next-attack cost already covered" was measured OUT in the grill (the f19 Active is bare).
Promotion also hardened the corpus harness to match attach picks up to interchangeability (074df7c
precedent — `correct` names the second of two identical Dreepy). Focused pin:
`tests/strategy/test_attach_target_priority.py`. Full suite green (3070 passed, 3 xfailed).

**Parallel-session slot A** (smallest; fully independent — see §Conflicts).
**Corpus acceptance target:** `86091728-19` (dragapult_ex), xfail-strict in
`tests/strategy/test_hyperclosure_corpus.py` — the XPASS is the finish line; promote to PIN on flip.

## Context

The correction's original substance (a needless Ultra Ball) is FIXED. The measured residue
(`docs/plans/combat-tempo-cluster-findings.md` §C): at a setup attach, the agent puts the {P} Energy
on the **Active** (score +18: `power-up-attacker` +15, `prefer-active-attach-in-setup` +8,
`attach-energy-last` −5) while the human wants the **benched Dreepy** (+10 — same rungs minus the
active-preference). dragapult_ex is a 2-line deck: developing the second Dreepy line is the play.

## Grill status: ⚠️ NOT grilled

This seam surfaced only in the 2026-07-18 investigation — a single-correction observation. No spec
round covers it. **Before coding, grill the design question:** when does benched-line development
beat the Active attach in setup? Candidate framings to grill against the corrections + STRATEGY.md:
- Is this dragapult-SPECIFIC (a declared 2-line plan → a deck Hypothesis via /update-strategy) or a
  GENERAL rule (e.g. "the Active already has its next attack's cost covered → develop the bench")?
- `prefer-active-attach-in-setup`'s own charter: read its rationale + pinned tests before narrowing
  it. A blanket flip WILL break other agents' setup attach pins.
- Interaction with `attach-solrock-over-line-base` (mega_lucario) and the ADR-0064 accel family —
  the attach-priority lattice is crowded; place the new term in ONE currency zone, don't stack.

## Build plan (after the grill)

1. RED: replay `86091728-19` through the real `explain()` in a new test (the corpus xfail is the
   canonical form; a focused test pinning the rung mechanics is welcome too).
2. Implement the narrowest rung/stand-down the grill settled on (likely: `prefer-active-attach-in-
   setup` stands down when the Active's next-attack cost is already covered AND a declared line's
   base sits benched un-powered — verify both predicates exist on Board/Context before inventing).
3. Broad re-audit: `tests/strategy tests/blunder tests/agents` — attach pins live in
   `test_blunder_*`, `test_setup_bench_decline.py`, the deck strategy tests.
4. Promote the corpus target; update the findings doc.

## Regression surface

All setup-attach pins (the rung fires on every agent's setup). Run the six ADR-0060 refresh pins too
(cheap, shared suite) — attach ordering feeds `attach-before-hand-shuffle`.

## Conflicts with other seams

None of the other three touch the attach rungs. Corpus-file edit on promotion (trivial merge).
