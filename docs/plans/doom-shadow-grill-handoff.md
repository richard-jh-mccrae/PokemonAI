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

---

# RULED (2026-07-23) — the grill's verdict, frame-by-frame, and the shipped swap

Sweep regenerated first (`--doom`): same 259/274, same 15, all incumbent-doomed / curve-safe,
`incoming = 0`. Every card fact below was verified at source (`data/EN_Card_Data.csv`,
`docs/rules.md`, `src/common/card_functions.json`, the frames' own `obs`) — several of the
handoff table's starting guesses did not survive contact.

## What the source-verification changed

1. **The pool has GENERIC supporter accel.** Crispin (1198) and Waitress (1235) are
   `energy_accel`-tagged Supporters ANY deck can run: each beats the curve's `attached + 1`
   affordability gate by exactly one (rules.md §3: 1 manual attach + 1 Supporter per turn).
   The 85058574 (Munkidori) opponent had a **Crispin visibly in its discard** — not hypothetical.
2. **Weakness ×2 is live in one frame.** Riolu (677) is {P}-weak; Munkidori's Mind Bend
   ({P}●, 60) doubles to **120 ≥ 70** once affordable. The "safe" curve read there was wrong.
3. **Ignition's burst is Evolution-gated and colourless-only** ({C} on a Basic, {C}{C}{C} on an
   Evolution) — already modelled by `incoming(charged=...)`'s `burst_on_evo`. Neo Upper Energy
   (typed 2-unit on a Stage 2) and Team Rocket's Energy (2-unit on TR bodies) are the other
   multi-unit specials; neither touches these 15.
4. **Damage-boost surface is bounded**: vs a non-ex Active only Kieran (+30, a Supporter — it
   COMPETES with Crispin for the one-Supporter slot); Maximum Belt (+50) / Brave Bangle (+30)
   only vs an ex.
5. **Hand size caps the burst.** The Terapagos frames' opponent held 2 cards: Area Zero + bench-out
   + Crispin needs more cards than the hand had; visible bench (3) caps Unified Beatdown at 90.
6. **The handoff's "Archaludon at 1e genuinely can't reach" claim was WRONG** — manual + Crispin
   = 3 {M} reaches Metal Defender 220. Only the 0-Energy frames are genuinely out of reach.

## Per-frame rulings

| frame | opp Active | can it reach my Active next turn? (worst case, at source) | ruling |
|---|---|---|---|
| 81904451-17 | Ho-Oh 0e | No: Flap ({R}●, 50) affordable via Crispin but 50 < 60; Shining Blaze needs 3; no R-accel body on their junk bench; no generic non-ex damage tool | **B** |
| 82749168-21 | Terapagos ex 0e | No: ●● affordable via Crispin, but 30× visible bench (3) = 90 < 160; hand=2 caps Area-Zero/bench-out; Crown Opal needs 3 typed | **B** |
| 82749168-29 | Terapagos ex 0e | No: same, hand=2, bench 3 → 90 < 160 | **B** |
| 81904064-44 | M-Abomasnow ex 0e | YES: manual W + Crispin W → Hammer-lanche ({W}{W}, 100× top-6 W density, discard already 3W, ceiling 600 ≥ 330); Maximum Belt +50 vs my ex | **C** |
| 85163634-17 | Latias ex 0e | No: Eon Blade needs 3, max 2 attaches; hand=1, no energy in discard, no P-accel body benched — and the correction is fetch-timing anyway | **A** |
| 85058574-69 | Munkidori 0e | YES: manual + Crispin (their deck PROVABLY runs it) → Mind Bend 60 ×2 weakness = 120 ≥ 70 | **A/C** (correction incidental; relax would be WRONG) |
| 85058574-71 | Munkidori 0e | YES: same | **A/C** |
| 86091435-13 | Duraludon 0e | Borderline: Confront 50 < 70, but the forward non-ex Archaludon's Iron Blaster ({M}{M}●, 160) is charged-affordable via burst; correction's `correct` is Retreat — doom SUPPORTS it | **A** (keep doom) |
| 86091435-20 | Duraludon 0e | Same; human wants retreat-into-Budew — doom pressure aligns | **A/B** (keep doom) |
| 86091435-30 | Archaludon ex 0e | No: Metal Defender needs 3 typed {M}, max manual+Crispin=2, burst is colourless-only, opp discard EMPTY (Assemble Alloy dry) | **B** |
| 86091435-35 | Archaludon ex 1e | YES: 1 + manual + Crispin = 3 → Metal Defender 220 | **C** (handoff's arithmetic was wrong) |
| 86091435-60/62/68/69 | Archaludon ex 1e | YES: same (+ Relicanth's Memory Dive adds Duralubeam 130); unmatched Read at these turns anyway | **A** (incidental; stays worst-case) |

## The swap decision: (b) matched-Read-gated — with two grill-found corrections to the plan

**Shipped as `Pilot.doom_matched_relax` (PROFILE ON, kill-switched), RELAX-ONLY:**
`active_doomed = worst_case AND (matched ∧ no-recur-fuel → charged ≥ my_hp)`.

1. **The doom consumer's charged budget is `_DOOM_CHARGED = {base_attach: 2, burst_on_evo: 2}` —
   NOT `_incoming_budget`'s `base_attach: 1`.** The sweep proved base_attach=1 relaxes ALL matched
   frames including Abomasnow (600) and the ×2-weak Munkidori (120): the generic-supporter attach
   (finding 1) must be budgeted for a catastrophe-grade boolean. Under base_attach=2 the corpus
   splits exactly on the rulings: relax {82749168-21, -29, 86091435-30}, keep-doom every C.
2. **Relax-only conjunction (found by the suite, not the grill).** The charged read's wilds+burst
   credit forward forms the incumbent's `attached+1` forward gate does not (1-Energy Makuhita →
   Wild Press 210 ≥ 70) — swapping outright MANUFACTURED doom and regressed the 82525101-14
   Ultra-Ball-discard pin (pitched Ignition to hoard rescue cards: the ADR-0064 §3 play-scared
   phantom). The charged curve may only CLEAR a worst-case cry, never add one.
3. **Recur-fuel guard.** A `discard_energy_recur` line (Assemble Alloy) with Basic Energy visibly
   in their discard refuels outside the attach budget → the relax stands down (synthetic pin).

**Live corpus delta (fresh Pilot per replay): exactly 5 doom flips, 0 regressions.** The three
ruled-B frames relax; two bonus frames (85045840-8/-10, turn-2 0-Energy Kyogre behind the matched
kyogre_mega_abomasnow Brief — the Brief itself says "dead early") relax, and **-10's decision now
matches the human's correction** (attach to Dreepy instead of wasting Boss's Orders). Unmatched
frames (Ho-Oh, Latias, the turn-10 Archaludon run) are byte-identical worst-case.

**Holds:** full suite 3256 passed; discard corpus **12/12**; pins in
`tests/strategy/test_doom_matched_relax.py` (3 relax + 3 keep-doom + unmatched byte-identical +
kill-switch-off byte-identical + recur-guard stand-down), fixtures under
`tests/fixtures/corrections/*doom*`.

## Standing residuals (flagged, not built)

- **Bench-scaling burst under a big hand**: the charged read prices Unified Beatdown off the
  VISIBLE bench; a Terapagos holding Area Zero + a wide hand could exceed it (the omitted
  hand-size-class term). No matched Brief covers a Terapagos-led list today, and the S1b shadow
  keeps reporting — a future Terapagos Brief should carry the caution.
- **On-board accel abilities** (Emboar / Iono's Bellibolt / Metang class) are not in the charged
  budget; none appear in the briefed archetypes' lists. A Brief-derived budget scan (the ADR-0064
  "derived by scan" line) is the proper home if one arrives.
- **`_incoming_budget` (`base_attach: 1`) itself** now looks optimistic-by-one for its OWN
  consumers (the ±50 survival nudge, the promote stand-down) given finding 1 — those are
  sub-catastrophe and fail-closed-gated, so left as-is here; worth its own sweep.

## Local gauntlet A/B (2026-07-23, post-ship) — KEEP ON

Cross-deck paired-delta A/B (`tools/sim/gauntlet_ab.py`, the T5 instrument), 3 agents × 6 directed
matchups × 400 games/battle/side = 4,800 games, jobs=4. Overlay side forced
`doom_matched_relax: false`; baseline = shipped PROFILE (ON) — so delta reads **OFF − ON** (the
tool's hardcoded "FLIP value_model" line does not apply, sign inverted vs its assumption).

| matchup (D vs O) | flag OFF | flag ON | ON advantage |
|---|---|---|---|
| mega_starmie vs mega_lucario | .672 | .667 | −0.5 pt |
| mega_starmie vs dragapult_ex | .895 | .885 | −1.0 pt |
| mega_lucario vs mega_starmie | .323 | .325 | +0.3 pt |
| mega_lucario vs dragapult_ex | .665 | .688 | +2.2 pt |
| dragapult_ex vs mega_starmie | .065 | .102 | +3.7 pt |
| dragapult_ex vs mega_lucario | .287 | .307 | +2.0 pt |

Aggregate OFF−ON = **−1.12 pt** (95% CI [−3.5, +1.2], **0 crashes**) → turning the flag OFF costs
~1 point on average; no matchup shows a significant OFF advantage. Verdict per the armed-ON
convention: **stays ON** (crash-clean, no regression, point estimate favors ON). The gain
concentrates in dragapult_ex — the agent whose Dreepy/Drakloak Actives were chronically
worst-case-doomed against briefed opponents — consistent with the grill's corpus reading. At
n=400 the CI (±2.4 pt) resolves gross regressions only; the ±1% precision tier is the in-place
Kaggle ladder A/B vs the prior flag-off submission once merged.

## Empirical follow-ups (2026-07-23, post-ship) — the audit and the budget sweep

**1. Ground-truth replay audit (`tools/train/probes/doom_audit.py`, TDD).** 60 fresh gauntlet
films (6 pairings incl. mirrors, seat-balanced, crash-clean), every game-seat replayed through a
stateful shipped Pilot (one per game — live-faithful); each turn's last `threat_shadow` classified
against what the film shows happened to that Active on the opponent's next turn (KO = serial
reaches owner's discard; terminal frame covers game-ending KOs). 647 audited turns:

| cohort | n | reading |
|---|---|---|
| FALSE_RELAX | **0** | the relax never cleared a doom that then killed the body |
| RELAX_OK / relax-touched | 2 / 2 (0 died) | the relax fires RARELY live — its A/B gain is a few high-leverage freed decisions, not a broad behavior shift |
| DOOM_HIT / DOOM_PHANTOM | 124 / 104 (45.6% phantom) | the remaining conservatism, quantified ("can KO" ≠ "will KO") |
| SAFE_MISS / SAFE_OK | 23 / 354 (**6.1% miss**) | the WORST-CASE oracle's own blind spot — bodies it called safe that died anyway |
| DODGED | 40 | switched before facing; counterfactual unobservable |

The headline is twofold: the shipped relax shows **zero empirical errors**, and the incumbent
worst-case read itself misses ~6% — many at charged 50–70 vs hp 60–160, consistent with
bench-promoted attackers (outside `active_doomed`'s Active-only contract), Kieran-class +30, and
checkup damage. Those 23 frames (episode/seat/turn/serial in the audit log) are the evidence base
for a promote-threat doom leg — a NEW line, not a doom-swap regression.

**2. `_incoming_budget` base_attach sweep (`tools/train/probes/budget_sweep.py`, TDD).**
The Crispin +1 applied to the `reachable_incoming` seam (the ±50 survival nudge, the loss rung,
the promote stand-down — never the doom path) across all 332 corpus frames: **zero decision flips**
(331 SAME, 1 SKIP). Ruling: the sub-catastrophe consumers are insensitive to the generic-supporter
attach on this corpus — `_incoming_budget` KEEPS `base_attach: 1`; the stricter `_DOOM_CHARGED`
stays a doom-consumer-only budget. The residual flagged in the RULED appendix is closed with
evidence, not changed code.
