# Doom-shadow grill — adjudicate the 15 disagreements before the survival swap (handoff, 2026-07-22)

**For a session ruling the doom `threat_shadow` disagreements frame-by-frame.** Parent design:
`opponent-value-equation-unification.md` (the Opponent Value Equation / Threat-Clock unification; S1b
built the doom shadow, this grill is S1's tail). PR context: the S1–S3a shadows merged via #134.

## The one job

The **survival doom read** (`combat.active_doomed`, 18 call sites — heal / retreat / tool-deploy /
posture / leaf survival) is worst-case by design (ADR-0064 §2: a hidden Ignition-class burst must never
leave survival under-prepared — the planner_6858 lesson). S1b built the **curve re-expression**
(`combat.doomed_incoming` = `incoming(t=1, ceiling) ≥ my_hp`) as a SHADOW beside it, deciding nothing.

The sweep (`python tools/train/probes/threat_sweep.py --doom`, over `data/corrections`, 274 frames)
found: **agree 259/274; 15 disagreements, ALL one direction — incumbent says doomed, curve says safe,
every one with `incoming = 0`.** The grill's job: **rule each of the 15** so we know whether — and how —
to swap `active_doomed` onto the curve. **Do NOT swap before this grill** (ADR-0064 reverted exactly this
once). Acceptance = a per-frame ruling → the swap decision (full swap / matched-Read-gated / keep
worst-case + adopt the curve only where safe).

## Why every disagreement is `incoming = 0`

The curve's ceiling read gates the opponent's current form on affordability (`can_pay_cheapest(attached +
1)`), and omits the `hand_size_attacker` forward counter. `active_doomed` does neither (it credits the
biggest attack unconditionally, and adds the hand-size forward term). So the 15 are all cases where the
opponent's Active **provably cannot afford any attack next turn** (its cheapest costs more than
`attached + 1`), yet worst-case still cries doom. The question per frame: is relaxing that SAFE (they
truly can't reach me), or is worst-case right (hidden accel / burst / deck-density the visible read
can't see)?

## The 15 frames (extracted 2026-07-22; regenerate via the snippet below)

Legend: `ctx` = the select context (doom only *matters* when a survival rung could fire — retreat/heal/
attach-for-defense); `oppE` = opponent Active's attached Energy; `minCost/maxDmg` = its cheapest attack
cost / biggest damage; `discE` = opponent's discard Basic-Energy counts (the S2 refuel pool).

| frame | agent | ctx | my Active hp | opp Active (oppE, minCost, maxDmg) | oppFwd | discE | correction is about | bucket? |
|---|---|---|---|---|---|---|---|---|
| 81904451-17 | mega_starmie | play | Staryu 60 | Ho-Oh (0e, 2, 100) | — | {} | **bad_retreat**: "attack over retreat" | **B** doom-relevant, curve aligns |
| 82749168-21 | mega_starmie | play | Cinderace 160 | Terapagos ex (0e, 2, 180) | — | {2:1} | wasted Crushing Hammer (bare Active) | B/C |
| 82749168-29 | mega_starmie | play | Cinderace 160 | Terapagos ex (0e, 2, 180) | — | {2:2} | wasted Crushing Hammer (bare Active) | B/C |
| 81904064-44 | mega_starmie | play | Mega Starmie ex 330 | Mega Abomasnow ex (0e, 2, 200) | — | {3:3} | sequencing (Lillie's) | **C** hidden Hammer-lanche density |
| 85163634-17 | mega_starmie | play | Cinderace 160 | Latias ex (0e, 3, 200) | — | {} | missed_win (fetch timing) | A/C |
| 85058574-69 | mega_lucario | play | Riolu 70 | Munkidori (0e, 2, 60) | — | {2:1} | don't play Premium Power Pro | **A** incidental |
| 85058574-71 | mega_lucario | select | Riolu 70 | Munkidori (0e, 2, 60) | — | {2:1} | fetch line (Fighting Gong) | **A** incidental |
| 86091435-13 | dragapult_ex | play | Dreepy 70 | Duraludon (0e, 2, 130) | Archaludon ex | {} | wasted Boss's ("no difference") | A |
| 86091435-20 | dragapult_ex | play | Dreepy 70 | Duraludon (0e, 2, 130) | Archaludon ex | {} | retreat into Budew, item-lock | A/B |
| 86091435-30 | dragapult_ex | play | Drakloak 90 | Archaludon ex (0e, 3, 220) | — | {} | don't attach a useless energy | **A** incidental |
| 86091435-35 | dragapult_ex | play | Drakloak 90 | Archaludon ex (1e, 3, 220) | — | {} | Drakloak ability before evolving | **A** incidental |
| 86091435-60 | dragapult_ex | play | Dreepy 70 | Archaludon ex (1e, 3, 220) | — | {} | attach before shuffling | **A** incidental |
| 86091435-62 | dragapult_ex | skill | Dreepy 70 | Archaludon ex (1e, 3, 220) | — | {} | play Last-Ditch Catch | **A** incidental |
| 86091435-68 | dragapult_ex | discard | Dreepy 70 | Archaludon ex (1e, 3, 220) | — | {} | don't discard Drakloak | **A** incidental |
| 86091435-69 | dragapult_ex | select | Dreepy 70 | Archaludon ex (1e, 3, 220) | — | {} | bench Dunsparce not Fez | **A** incidental |

## The proposed triage (starting hypothesis — confirm/overturn each frame)

- **Bucket A — doom is INCIDENTAL** (~10 frames). The correction is about my own play (fetch, attach
  order, discard, bench, skill) and has nothing to do with survival; relaxing doom changes nothing about
  the ruled decision. These do NOT belong in the swap acceptance bar — verify that no survival rung's
  output flips on the frame, then set aside. NOTE the Archaludon frames (86091435-30..69) have EMPTY
  discard, so S2's refuel is 0 — Archaludon at 1e genuinely can't reach its 3-cost 220 next turn
  (`1 + 1 < 3`); the curve's "not doomed" is arithmetically correct there, and the corrections are about
  Drakloak/attach sequencing regardless.
- **Bucket B — doom relaxation ALIGNS with the human** (the retreat/hammer frames). 81904451-17 is the
  cleanest: worst-case doom (Ho-Oh 100 ≥ Staryu 60) can push a defensive retreat, but Ho-Oh has 0 Energy
  and can't attack next turn — the human says "attack over retreat," which is exactly what relaxing doom
  supports. Evidence FOR the swap.
- **Bucket C — hidden-reach CAUTION** (the swap could be unsafe). 81904064-44: Mega Abomasnow ex's
  Hammer-lanche is a HIDDEN deck-density scaler (`100×` Basic {W} off their top 6 — coverage-review
  finding) that the visible affordability read can't see, and their discard holds {W} ({3:3}); worst-case
  doom may be correctly scared. Terapagos ex / Latias ex likewise warrant a check for hidden accel/burst.
  These decide whether the swap must be **matched-Read-gated** (relax only behind a recognised deck) or
  keep worst-case for the survival boolean and adopt the curve only for the non-catastrophe consumers.

## The output this grill produces

1. A per-frame ruling (A / B / C + a one-line reason), verifying card facts AT SOURCE (`docs/rules.md`,
   `data/EN_Card_Data.csv`, `cg.api`), not from this table.
2. The **swap decision** for `active_doomed`, one of: (a) full swap to `doomed_incoming` (if every B holds
   and no C bites); (b) **matched-Read-gated relax** (worst-case default, curve only behind a γ-matched
   Brief — the ADR-0064 §4 asymmetry: existence for threat, matched-Read for safety); (c) keep the
   survival boolean worst-case, adopt the curve only for consumers where under-preparing is recoverable.
   The likely answer is (b), mirroring `_incoming_budget`.
3. If (b): wire it behind a kill-switch, shadow-confirm byte-identical where unmatched, and add the ruled
   B-frames as pins. Hold the discard corpus 12/12 and the full suite; fresh Pilot per replay.

## Reproduce / regenerate

```
python tools/train/probes/threat_sweep.py --doom      # the 259/274 + the 15-frame disagreement list
python tools/train/retest_one.py <agent> <ep>-<frame> # single-frame replay through the shipped Pilot
```
The per-frame table above was produced by replaying each frame's `obs` through `tune._build_pilot(agent)`
and reading `combat` / the correction record (the snippet is in this session's history; re-derivable in
minutes). `Pilot._threat_shadow` emits `{doom_old, doom_curve, doom_incoming, my_hp, agree}` live.

## Standing cautions

- **The hidden-burst lesson is load-bearing** (ADR-0064, `docs/todo/incoming-affordability.md`): a blind
  affordability cap on the survival boolean was BUILT and REVERTED once (planner_6858 — a Mega Starmie
  mirror at 1 Energy held a hidden Ignition and fired Nebula Beam). Bucket C is where this bites; default
  to worst-case when unsure.
- Verify every card fact at source (CLAUDE.md); the table's `maxDmg`/costs are a starting index, not truth.
- Shadow-first, fresh Pilot per replay, hold the suite + the discard corpus 12/12 (the standing bars).
- The swap is S1's tail only; the deny/snipe/gust legs of the Opponent Value Equation (S3b, Option B) are
  a separate line and do not block on this.
