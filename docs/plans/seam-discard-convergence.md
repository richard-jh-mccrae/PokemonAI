# Seam handoff: the discard convergence + the deploy-now spike (run SOLO, last)

**✅ CONVERGED 2026-07-19 — the SWAP IS LIVE.** The card-worth equation now DECIDES the forced
discard (`Pilot.discard_keep_value` armed ON, the `develop_rollout` precedent — in-ladder A/B,
kill-switch if weak), replacing the tuned `_DISCARD` ladder. It matches the human **9/9 on the live
(non-excluded) discard corpus**; the ladder it replaced managed 9/11 on the same set. The ladder
remains as the flag-off fallback (still unit-tested). Remaining follow-ups (below): the duplicate-pair
set semantics (a forced discard-2 of two wincons still prices both keep 0) and folding the now-shadowed
`_DISCARD` rungs out once the A/B clears. The rest of this doc is the build record.

**SHADOW EMITTER BUILT 2026-07-19** (the first equation shipped under the shadow-equations ruling):
`pilot._discard_shadow` computes the oracle's v1 keep-cost at every real discard pick and emits it —
`Decision.discard_shadow` → the sparse `@T` `discard_shadow` key → the blunder-shell ⚖️ dropdown —
deciding NOTHING (the ladder chose; the agreement bit is the record). First corpus sweep (12
recorded discard decisions): **3 agree / 9 disagree**, and the disagreements already localise the
v1 gaps the migration grill needs: (a) ~~a WORTH-DERIVATION gap — an undeclared Line MEMBER (the f68
Drakloak) prices 0~~ **FIXED 2026-07-19** (`planner._role_value` derives `win_condition_base` worth
for every `_line_preevo_set` member — the f68 Drakloak now prices 20; WORTH-ONLY, `c.roles` and the
discard rungs untouched, so the deploy-now spike now has worth to spike but the covered-vs-uncovered
DISCRIMINATION stays this seam's gated work); (b) the documented per-card set-naivety
(duplicate pairs both price 0); (c) the `fuel` term SEES the 84071010-45 discard-as-resource pick
the ladder missed, though the v1 index tie-break among worth-0 rows masks the ranking. These rows
are the grill fodder for the migration-path ruling below.

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

## Grill RULING (2026-07-19, with the user) — gates real, equation shadow, swap gated-last

The migration grill ran on source-verified evidence (the 11-rung ladder mapped against the oracle;
the current 3-agree/9-disagree shadow sweep). Three findings and the ruling:

**Finding 1 — the oracle already prices most of the ladder's CONTENT.** `keep-key` ↔ TAG_TIER
`discard_eot` 30 / wincon 30 / ACE_SPEC 25; `keep-line-base` ↔ `win_condition_base` 20 (incl. the
derived Drakloak); `keep-gust-and-recovery` ↔ TAG_TIER gust/recycle 10; `discard-the-redundant` ↔
`in_play` re-access; `discard-the-hand-duplicate` ↔ `dup_hand` re-access. The magnitudes are largely
already in the currency.

**Finding 2 — the ladder's irreplaceable content is its PREMISE GATES.** Five rungs carry a `when=`
the oracle has no term for: `keep-key`'s `not active_fully_powered` (the burst floor DECAYS once the
Active is powered), `keep-basic-energy-when-starved` (a −12 spike only at `my_active_energy == 0`),
`discard-the-dead-opener` (the `opener` role expired), `discard-the-redundant-tutor` /
`keep-the-evolution-tutor` (gated on `wincon_in_hand` — a need premise). "Every premise gate must
land as a gate-library stage or it is LOST" is the operative constraint.

**Finding 3 — keep-cost STRUCTURALLY cannot rank a discard.** The sweep's dominant disagreement cause
is not wrong magnitudes — it is too many cards pricing to keep 0 (7/7 rows on `84071010-45`, 6/6 on
`86091435-68`), so `eq_pick` falls to raw hand index. A discard is also "which card is actively BEST
GONE" — the `P(met | pitch) − P(met | keep)` term going NEGATIVE when pitching HELPS (fuel / fodder /
dead-role). A keep-FLOOR cannot produce that. **The oracle needs a pitch-preference / zone-signed
term before it can decide a discard at all** — accepted by the user.

**THE RULING (user, 2026-07-19): gates real, equation shadow, swap gated-last.** This refines the
seam's "hybrid" (path 1 + 2) and drops path 2's permanent half-state:
1. **Build the pitch-preference term** (Finding 3's prerequisite) into the SHADOW first — it makes
   the shadow able to RANK; re-sweep and read the new agreement rate.
2. **Build the premise gates (Finding 2) as REAL Worth×Gates factors.** A gate is a FACTOR of Worth,
   not a decision — so each fires LIVE everywhere the equation is already consumed (the gamble
   keep-floor, the refresh SHED) the moment it exists, and is therefore its OWN corpus-gated
   behaviour change at those live sites (exactly how the pressure/quota gates landed — re-audit each,
   re-baseline deliberately). The DISCARD decision site is the only thing that stays shadow.
3. **Keep the full discard `keep_cost_gated` equation as a SHADOW emitter** — fully built, firing,
   traceable in the dropdown, deciding nothing — until its agreement rate + the corpus justify the
   swap (the shadow-equations ruling).
4. **The swap is one gated move, LAST:** the equation replaces the ladder wholesale (path 1's end
   state), NOT a permanent "rungs keep routing, weights derived" (path 2 rejected as a half-state).

This matches every other keep_value convergence: the gamble keep-floor and refresh SHED each
converged one at a time under corpus gates; the gate legs are built real-and-firing under corpus
gates; the last/riskiest consumer (discard) rides as a shadow first. Set semantics (the duplicate-pair
naivety) and the worth-0 tie-break are folded into steps 1–3, not separate work.

### Step 1 BUILT 2026-07-19 — the pitch-preference term (into the shadow)

`pilot._discard_shadow` gained the `P(met | pitch) − P(met | keep)` sign: a per-row `pitch` count
over source-checked deadness/zone signals (`dead_opener` = `opener` role spent; `redundant_tutor` =
`wincon_in_hand` + rush_evolve/tutor_mega; `stranded` = payoff with no base; `fodder` = declared
`discard_fodder`; `fuel` = discard-source accel wants it), ranking zero-keep ties by DEADNESS instead
of raw hand index. SHADOW-only, deciding nothing.

**Measured against the HUMAN corpus** (`correct ⊆ picks` over the 12 recorded discard decisions), which
is the metric the swap turns on — NOT equation-vs-ladder:

| | matches human | after step 2 |
|---|---|---|
| tuned `_DISCARD` ladder | 9 / 12 | 9 / 12 |
| the equation (keep + pitch) | 8 / 12 | **11 / 12** |

Step 1 took the equation from "cannot rank" (raw index) to competitive, beating the ladder on 2
discard-as-resource cases (`84071010-45`, `83661652-30`).

### Step 2 BUILT 2026-07-19 — the 3 ladder-wins closed; the equation now BEATS the ladder 11/12 vs 9/12

Each ladder-win was classified at source and fixed by its true mechanism:
- **`82753102-16` → a REAL gate.** `gate_library.need_met_odds` + a `_deploy_odds` branch: a
  `rush_evolve`/`tutor_mega` wincon-tutor whose wincon is IN HAND has its role SATISFIED (the
  fetcher gate's cousin) → deploy_odds 0 → keep 0. Fires LIVE at the gamble keep-floor + refresh
  SHED (corpus-gated: re-audit clean, no pin moved).
- **`83454549-36` → a shadow pitch signal.** `spent_burst` (`discard_eot` + `active_fully_powered`):
  a burst Energy is precious until the Active is powered, then it self-discards at end of turn
  anyway — dead weight. DISCARD-CONTEXT (at a refresh it is a next-turn attach), so it stays in the
  shadow's pitch term, NOT a general Worth gate.
- **`83967840-54` → the worth tie-break.** Among equal (keep, pitch), the LOWER underlying worth
  sheds first — a worth-10 duplicate's redundancy is worth preserving over a worth-0 dreg's
  (sets-not-sums, the first honest step of the joint-pair fix).

The equation now matches the human on **11/12**, beating the tuned ladder's **9/12**; the only
remaining miss is `86091435-68` — the deploy-now spike (the gated evolution-gate extension). The
residual set-naivety (a duplicated wincon in a forced discard-2 still prices keep 0) is the last
open prerequisite. **With the equation now out-scoring the ladder on the corpus, the swap
(step 3-4: `keep_cost_gated` decides, corpus + score-diff gated) is the next decision.**

### 2026-07-19 user re-review of the last miss: the EQUATION'S pick is ruled correct

Reviewing `86091435-68` on the shadow's working, the user ruled the recorded label's 2nd slot
WRONG: the Crushing Hammer should be KEPT and used on the opponent's Active (Archaludon ex, energy
attached) — so the equation's pick (Risky Ruins + a Lillie's; Drakloak AND Hammer both kept) is the
better play, and the recorded correction is REFUTED-as-labeled (reviewed.json; corpus target →
excluded, per the standing corpus discipline). The SURVIVING substance — never pitch the sole
Drakloak that can evolve the Active this turn (evolve first, use Recon Directive; whether Ultra
Ball should be played at all is a separate whether-to-play question) — is preserved as the relaxed
strict-xfail `test_deploy_now_drakloak_is_not_pitched` (the card must not be pitched, whatever
fills the other slot; XPASS = the deploy-now gate or the swap landed → promote).

**The scoreboard after the re-review:** on the surviving labeled decisions the equation matches the
human **11/11** vs the ladder's **9/11** — and on the refuted 12th, the equation's pick is the one
the user endorsed. The equation now strictly dominates the ladder on every recorded discard
decision. The remaining pre-swap items are the deploy-now spike (now also the relaxed target's
flip) and the set-naivety; step 3-4 (the swap) awaits the user's go.

### Steps 3-4 BUILT 2026-07-19 — the deploy-now spike + the LIVE SWAP

**The deploy-now spike (the flagship discrimination):** `Board.deploy_now_ids` +
`planner._deploy_now_ids` (a hand evolution with an ELIGIBLE in-play base this turn — matching
`evolvesFrom` name, `appearThisTurn` False, turn ≥ 2) wired as a **closing edge** in
`_gate_closing`: pitching forfeits a live tempo play re-access can't restore, so keep spikes to full
worth even with a same-card copy in play. Flips `86091435-68` (open Drakloak kept) while
`83686860-18` still pitches correctly (its base was placed this turn → not in `deploy_now_ids`) — the
covered-vs-open pair a flat floor never separated. Fires live at the gamble/refresh keep-sites too.

**The engine-supporter premise gate (Finding 2's 5th, closed for the swap):** a draw/search/heal
SUPPORTER that is not `hand_disruption` gets a discard-context WORTH floor
(`_ENGINE_SUPPORTER_KEEP = 8`, mirroring `keep-engine-supporter-at-discard` −8) — a WORTH floor, not
a keep floor, so a duplicate or need-met engine supporter still sheds. Without it the equation pitched
an engine Lillie's over `hand_disruption` filler.

**The swap:** `Pilot.discard_keep_value` (PROFILE armed ON). At a forced discard `_evaluate` calls
`_discard_equation_pick` — the `picks` cheapest-to-lose cards by the equation's ranking
(`_discard_equation_rows`, shared with the shadow) — instead of the ladder order. OFF is
byte-identical (ladder decides, equation shadows). Acceptance: **9/9 live discard corpus** (ladder
9/11); all discard PINS/SUBSTANCE_PINS green; the relaxed `test_deploy_now_drakloak_is_not_pitched`
XPASSed → promoted to a plain pin; the synthetic `test_discard_selection` scenarios (flag-off ladder)
unchanged and the equation reproduces their picks. Full suite 3114 passed.

### Still open (post-swap follow-ups)
- **Set semantics** (the last naivety): a forced discard-2 of two identical wincons still prices both
  keep 0 (each points at the other as re-access) — the joint-pair (re-score after each commitment,
  the `_greedy_grab` pattern) fix. Rare in practice (the corpus never hit it live).
- **Fold the shadowed `_DISCARD` rungs** out of `doctrine_fetch` once the in-ladder A/B clears the
  swap (the elegance-pressure step of the shadow-equations ruling — fewer features firing in
  combination). Until then the ladder stays as the kill-switch fallback.

## Grill status: ⚠️ the keep-cost math is grilled — the LADDER-REPLACEMENT PATH IS NOW RULED (above)

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
