# Seam handoff: the discard convergence + the deploy-now spike (run SOLO, last)

**Parallel-session slot D — do NOT run concurrently with seams B/C** (it re-baselines
`doctrine_fetch.py`'s `_DISCARD` ladder and its whole test surface). Start it only after the other
seams merge, rebased on everything.

**Corpus acceptance PAIR (the built-in guard):**
- `86091435-68` (xfail-strict) must FLIP: don't pitch a Drakloak that can EVOLVE the active Dreepy
  *this turn* (then Recon Directive draws).
- `83686860-18` (substance PIN) must HOLD: a Drakloak with a benched copy already covering the
  evolution is still correctly pitched.
A flat keep-floor cannot tell these boards apart — that discrimination is the seam's whole point,
and it is why this was NOT hacked in as a rung during the gate-library Stage 1 build (the
gate-library scope doc — retired 2026-07-19, all four gate legs built — recorded the deliberate
deferral; see ADR-0065 §Build status and its grab/pitch finding).

## Grill status: ⚠️ the keep-cost math is grilled — the LADDER-REPLACEMENT PATH IS NOT

What IS grilled (spec Rounds 6-8): `keep_cost = role_value × [P(need met by deadline | keep) −
P(met | shuffle/pitch)]`, **sets not sums** (discard PAIRS valued jointly — `_shed_signals`'
independent top-2 is called out as the naive form), zone/deck-signed. The oracle side exists:
`card_worth.keep_cost` + `TAG_TIER` + `gate_library.deploy_odds` (Stage 1: the CLOSED/undeployable
discount is built; the OPEN-and-mine deploy-NOW spike is this seam's extension).

What is NOT grilled — the migration itself. The 2026-07-18 investigation (ADR-0065 §grab/pitch
finding) established that the `_DISCARD` ladder is a mature, correction-tuned 12-rung system that
already prices roles AND redundancy, with premise gates the pure oracle lacks (e.g. `keep-key`'s
burst floor decays on `active_fully_powered`). A wholesale swap re-baselines ~8 tuned pins
(`test_discard_selection.py`, `test_fetch_doctrine.py` discard tests, the corpus discard-pair
SUBSTANCE PINS + subset PINS) for one measured flip. **Grill the migration design before touching
code.** Candidate paths to grill:
1. **Full replacement** — the rungs become one `keep_cost_gated` term (roles/tags/gates all inside
   the oracle). Cleanest currency; highest re-baseline risk; every premise gate must land as a gate-
   library stage or it is LOST.
2. **Magnitude re-point** — the rungs keep their `when=` routing (the tuned premise gates) but their
   WEIGHTS derive from `role_value`/`keep_cost` instead of hand-tuned constants. Half-converged;
   grill whether that violates the one-currency rule or honours it (the rungs become consumers).
3. **Spike-only first** — extend `gate_library.deploy_odds` with the OPEN-and-mine spike (evolvable
   NOW + sole covering copy → deadline_odds spikes the keep) and inject it into the discard pick via
   ONE new floor that reads `keep_cost_gated`… this is the "flat rung" shape the user explicitly
   rejected (2026-07-18: "moving away from the single card held value equation to just more if/else
   statements") UNLESS it lands as path 1/2's first stage. Do not resurrect it standalone.

**Also in scope once the path is settled:** the SET semantics (`_shed_signals`' top-2 and the real
2-card discard pick should value the PAIR jointly — the second copy of a line prices differently
after the first is committed; the `_greedy_grab` virtual-board pattern is the in-repo precedent for
"re-score after each commitment").

## Build plan (after the grill — likely its own ADR or an ADR-0065 amendment)

1. Grill the migration path (above) — with the user; record the ruling.
2. RED: the acceptance pair + the existing discard surface as the declared re-baseline set.
3. Implement per the ruling; extend `gate_library.deploy_odds` with the deploy-now spike (a
   PARAMETER of the equation — deadline this-turn — never a bare rung).
4. Full-family re-audit per the currency-zone rule: all discard pins, the corpus, the six ADR-0060
   pins, gamble suite, broad sweep. Expect deliberate re-baselines; justify each in the commit.
5. Promote `86091435-68`; verify `83686860-18` held; update the findings + scope docs.

## Conflicts with other seams

Everything: `doctrine_fetch.py` (B and C edit other sections), `gate_library.py`, `card_worth.py`,
the corpus file, the discard test surface. Hence: solo, last, rebased.
