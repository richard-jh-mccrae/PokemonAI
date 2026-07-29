# ADR-0077 — The value currencies are three scales bridged by DERIVED rates, and building the bridge is a shared-layer prerequisite, not an instrument swap

**Status:** Accepted (grilled 2026-07-28, `/grill-with-docs` on #187 — six locked decisions). Build =
a new **S3c** prerequisite issue; consumed by #187 (S4-deny), #188 (S4-snipe), #189 (S4-gust).
Nothing here is built yet, and two of the decisions are **conditional on measurements that have not
been run** (see *The two go/no-go gates*).

⚠️ **Number claimed at grill time.** Per `docs/adr/README.md`'s recurring lesson (0071, then 0074 ×3),
the number settles at merge time — expect to renumber on rebase and keep references greppable.

**Context issues:** #187 (this grill), #186 / ADR-0076 (the slot-family split this extends and partly
supersedes), #136 (the Value System build tracker), #143 (the un-split original, closed),
`docs/plans/opponent-value-equation-unification.md` (the design), ADR-0062 (the denial oracle),
ADR-0073 (the Prize Damage Rate), ADR-0065 (the no-fudge discipline this is disciplined by).

## Context

#187 was chartered as *"the shortest hop of the three S4 swaps"* — repoint deny's grading at the
shared opponent-target marginal built in #186, since deny already lives in the Needs assignment.
Reading the live code found the charter's premise wrong in four separate ways, and every one of them
points at the same missing layer.

**1. The charter names two surfaces as one.** `needs.deny_slot`'s value is **not** `_opp_denial_best`.
`pilot.py:3713` passes `oracle_value = TAG_TIER["gust"]` (a flat **10.0**) graded `/2^turns_to_ready`;
the ADR-0062 oracle survives there only as a `> 0` bite gate (`_denial_at`, `pilot.py:3724`).
`_opp_denial_best` has exactly one live consumer in the tree — `_denial_play_tactical`
(`pilot.py:4919-4922`), the play-side rung. Deny has **three** independent surfaces:

| | surface | question | value today |
|---|---|---|---|
| (a) | `needs.deny_slot` @ `pilot.py:3729` | is a held Hammer worth KEEPING? | flat `TAG_TIER["gust"]` 10.0, `/2^t` |
| (b) | `_denial_play_tactical` @ `pilot.py:4902` | do I FIRE it now? | `coin × W × opp_denial_best − item_cost` |
| (c) | `_denial_target_tactical` @ `pilot.py:4924` | which Energy do I STRIP? | `W × area_weight × _denial_at(body)` |

**2. A Hammer has no worth floor — deny is not gust.** Crushing Hammer (1120) and Enhanced Hammer
(1081) each carry exactly one tag, `energy_denial`, which is in neither `ROLE_TIER` nor `TAG_TIER`, so
`_role_value` → **0.0** → the `worth * deploy > 0` gate at `pilot.py:3786` fails → **no general-worth
slot**. `needs.SUPPLIES` says it outright (`needs.py:285-288`): *"the deny leg is their only pricing —
a Crushing/Enhanced Hammer carries no ROLE/TAG tier, so without this route the resolver would price it
0 and the hedge would carry it forever."* ADR-0076 Amendment E's currency debt was measured at **0
decision flips** because Boss's Orders carries `TAG_TIER["gust"] = 10.0` and kept a general-worth floor
(~10 × 0.45 ≈ 4.5) that absorbed the drop. Deny has no such floor. Its slice is also **survival-only**
(a strip takes no prizes — the design doc calls deny *"pure tempo"*, line 50), so it is structurally
capped by `_SURVIVAL_CAP = 0.9` against gust's 3.9. A naive slice-read takes a Hammer's only keep price
from **10.0 → ≤ 0.9** inside a *summed* DP against Energy 8.0 / `clutch_heal` 20.0 / `discard_eot`
30.0. Every Hammer sheds at the first discard.

**3. There is no slice for deny to read.** `_opponent_target_rows` (`pilot.py:7222-7233`) computes
`prize_advance = combat.prize_value(b)` — its own docstring says *"the **if-KO'd** term"* — and
`survival_shift = turns_to_ko_me(bodies **without b**) − turns_to_ko_me(bodies)`. Both terms model
**removal**. A Hammer removes nothing; it strips one Energy off a body that stays. #186 built the
removal Δ because gust and snipe are what it served. The design doc always specified per-instrument Δ
(line 132-134: *"each plugs its own `Δ` into the two terms"*) — it simply was not built.

**4. There are three scales, not two, and two of them are provably incoherent.** `needs.py`'s "ONE
currency" claim scopes to the DP slots only. The live scales are **card-worth points** (`ROLE_TIER`
caps 30, `ENERGY_TIER` 8, `TAG_TIER` 10–30), **damage / tactical** (`_DENIAL_PLAY_W = 1.0` points per
damage point, `ENERGY_RECOVER = 75` "chip-scale", `KO_SCORE = 1000`), and **prize-equivalents**
(`needs.opponent_target_value`, 0–3.9). ADR-0073 already bridges prizes↔damage. Nothing bridges
worth↔anything, and two shipped constant-pairs price the same object on both scales with answers ~9×
apart:

| object | card-worth | damage / tactical | implied rate |
|---|---|---|---|
| keeping a gust/denial Trainer | `TAG_TIER["gust"]` **10.0** | `_DENIAL_ITEM_COST` **10** | ~1 dmg per worth-pt |
| one Energy | `ENERGY_TIER` **8.0** | `ENERGY_RECOVER` **75** | ~9.4 dmg per worth-pt |

So the worth bridge cannot be read off existing constants by matching a pair. The precedent is a
warning, not a reassurance: ADR-0073 records that the superseded `_PRIZE_UNIT = 12` was wrong by
roughly 8× and made the shipped equation *"endorse feeding a 3-prize body to save a 40-point band."*
Same failure mode, same order of magnitude.

## Decision

**1. The deny instrument reads the shared marginal on ALL THREE surfaces, routed by ADR-0076's
instrument-shape split.** Surface (a) reads its slice out of the DP assignment (deny is a scarce held
card — ADR-0076 Decision 1); surfaces (b) and (c) read `needs.opponent_target_value` / `phase_scale`
**directly, bypassing the DP**, because by the time either fires the card is already committed and no
keep-value competes for the slot — the same carve-out ADR-0076 Decision 2 + Amendment A made for snipe
and the forced-promotion pre-chip.

This **deliberately overturns the WP-N8 ruling** that the damage magnitude stays on the play-side rungs
(design doc's ADR-0062 seam bullet; restated in-code at `pilot.py:3690`). WP-N8 was ruled for the
keep/play split, before the assignment fold existed. Leaving it standing means the Hammer is fired on a
damage read and aimed on a prize read — two currencies inside one instrument, which is the incoherence
Amendment E had to write an amendment about.

**2. A prize-denominated marginal is NEVER consumed raw across a scale boundary.** Every consumer
converts at a **derived** rate. Two bridges are needed and they are not the same number:

- **prize-eq → damage/tactical: already exists.** `PRIZE_DAMAGE_RATE = 100.0`
  (`promote_retreat_value.py:63`, ADR-0073) — the median HP-per-prize over all 1061 bodies in
  `data/EN_Card_Data.csv`, *recomputed from the CSV by `test_promote_retreat_value.py:77`* rather than
  pinned. No new constant, no new derivation. It is currently a single-consumer constant living in a
  promote/retreat module; S3c **hoists it to a shared home**, because three more consumers are arriving.
- **prize-eq → card-worth: does NOT exist, and ADR-0073 scoped it out on purpose.** That ADR's own
  glossary `_Avoid_` line reads: *"`KO_SCORE` (the KO's dominance band, deliberately unbounded by this
  rate), **Worth** (the card/role tier currency)."* The missing primitive is the third leg — a **Worth
  Damage Rate** (damage per card-worth point) — from which the prize→worth conversion composes as
  `PRIZE_DAMAGE_RATE / WORTH_DAMAGE_RATE`. One new rate, not two, and it names the incoherence in
  Context §4 as the thing it resolves.

**3. The Worth Damage Rate requires a corpus anchor that does not exist yet — capture it BEFORE
building.** Every committed deny fixture is `select.context = 0`, the play/hold decision:
`dragapult_hammer_no_threat_f6`, `dragapult_hammer_over_develop_f32`, `dx_hammer_forward_form_guard_f32`,
`ms_hammer_bench_while_koing_active_f26`, `ms_hammer_forward_form_riolu_f12`,
`ms_hammer_unfavored_override_f17`, `ms_deny_wasted_on_doomed_active_f41`. Not one is a DISCARD select.
`test_needs.py::test_deny_slot_value_grades_by_their_closeness` is a pure shape unit test
(`oracle_value=30.0`, near-vs-far) and pins no magnitude. The one keep-side Hammer ruling that exists,
`86091435-68` (*"the Hammer should be KEPT for the opponent's Active"*), is **REFUTED-AS-LABELED**
(2026-07-19) and sits in `EXCLUDED` in `test_hyperclosure_corpus.py:129`, with its surviving substance
re-pinned as a *deploy-now* test. It is also directional, so it bounds the rate on one side only.

Absent that anchor, any value for the rate is exactly the magic-number fudge ADR-0065 forbids. S3c
therefore **captures the anchor first**: re-adjudicate `86091435-68` as a deny-valuation target, and
sweep the corrections corpus for DISCARD-context frames holding a Hammer, adjudicating any that
discriminate.

**Corpus availability — correcting a claim repeated throughout the design doc.**
`docs/plans/opponent-value-equation-unification.md` describes the corrections corpus as *"gitignored"*
in four places (the S2/S3a sweep bullets, the S1b next-step, the `opp_target_shadow` note), and this
ADR inherited that phrasing. **It is wrong.** `data/corrections/` is **tracked** — 33 files across 30
agent/commit directories, `corrections.jsonl` per directory — and the root `.gitignore` excludes only
`kaggle_api_token/`, `data/meta/`, `data/probe/`, `reports/`, raw replays and the raw strategy sources.
The ADR-0062 Hammer frames are in `data/corrections/mega_starmie_20260630_b7e483a/` (the commit ADR-0062
itself names as the recording point). **Consequence: gate 1 needs no corpus that this repo lacks** — it
needs the strip-Δ (build-shape step 5) and a probe, both ordinary work. The go/no-go is reachable
without waiting on anything external, which the "gitignored" framing implied otherwise.

**4. The shared-layer work splits out as S3c, a prerequisite to all three S4 swaps.** ADR-0076
Decision 3 already established the principle — centralize the shared-value adjudication *"rather than
letting each S4 issue re-litigate the same shared value through its own instrument's lens."* The
denomination escaped that net only because gust's worth floor hid it. S3c owns: both exchange rates
(one hoisted, one corpus-anchored), the **per-instrument Δ** in `_opponent_target_rows` (the strip-Δ
from Context §3), decision 5 below, and the retirement of ADR-0076 Amendment E's deferral.
**#187/#188/#189 then reduce to instrument wiring plus a kill-switch, none re-opening the shared
value** — which is what their charters already claim they are.

Consequently **Amendment E's hand-off of the denomination to #189 is superseded**: the ruling lands in
S3c, ahead of all three, not inside the last of them.

**5. S2's `discard_recur_fuel` adoption on `turns_to_afford` folds into S3c.** ADR-0076 Decision 0
deferred it and named #187 as its owner. It changes the *shared* clock every instrument's marginal is
built on (`turns_to_ready` sets the deny slot's deadline), so it belongs with the shared-layer work,
before three deciders start reading it. Its stated safety concern also dissolves rather than needing
management: it was called fail-slow-unsafe because over-crediting fuel over-spends a scarce Hammer on a
refueler that is not actually close — but once deny's value is a corpus-anchored marginal instead of a
flat tier, "how close are they" is *priced* rather than *thresholded*, which is the ADR-0060/0062 move
("price the quantity, don't threshold it"). It still ships behind its own kill-switch and sweep.

**6. `_DENIAL_UNFAVORED` is RETIRED; `needs.phase_scale` is its derived successor.** Both say "when the
race is going badly, a strip is worth more", from different inputs — `_unfavored` is Read-derived
(`board.favorability <= _POSTURE_UNFAVORED`, gated on `matchup_coverage`; ADR-0026 Lever A),
`phase_scale` is board-derived (`race_ahead` + `opp_prizes_remaining`). Today only one is on the deny
path; after the swap both would be, **multiplicatively**, since `_DENIAL_UNFAVORED` is deliberately a
scaler (`pilot.py:129-136`: *"A booster must scale the oracle, never add to it"*). The design doc's
ruling 5 already chose the KO-race margin over a blanket favourability multiplier once, at match scale
(the R1 "+76 runaway" guard); making the same call at instrument scale is consistency. `phase_scale` is
additionally bounded [0,1] where the Read-gated scaler is not. This satisfies the standing discipline
literally — *"a graded term REPLACES its guard family and re-audits it, never bolts on beside it"*
(design doc line 363).

### The deny guard re-audit (#187's agenda item 2, answered)

**Deny has no ADR-0044 guard.** ADR-0044 ships `snipe_prize_redundant` and `forced_promotion`, both
snipe-family; the only deny-adjacent constant, `_SNIPE_THREAT_PRIZE_FLOOR = 5` (`pilot.py:164`), is the
snipe prize-redundancy floor and is #188's business. The re-audit that IS owed is of deny's **own**
guard family:

- **Subsumed by the marginal — delete, do not keep beside:** the surplus-energy whiff
  (`denial_value → 0`; the strip-Δ is naturally 0 and reads the whole board's threat rather than one
  body's own attacks), `_DENIAL_FORWARD = 0.5` (S1a established `forward_card_ids` is all-descendants,
  so forward forms are already in the curve), and — **conditional on gate 1 below** —
  `_DENIAL_BENCH = 0.25` (a benched body's strip-Δ is naturally smaller because `turns_to_ko_me` models
  promotion via `opp_active` / `switch_enabler`).
- **NOT subsumed — must survive the swap explicitly:** the `active_can_ko` drop (ADR-0063 —
  `turns_to_ko_me` has no idea I am about to KO their Active, so the marginal will happily price a
  strip on a corpse), `_DENIAL_ITEM_COST = 10` (the keep-side floor, and the anchor gate 1's arithmetic
  runs on), and `coin_odds` (a real probability weighting a ranked value — ADR-0074).

### The two go/no-go gates

Both are measurements, both precede any build, and either can block the swap on a **design** fix rather
than a wiring change.

1. **`m₂₉ < 0.2 < m₁₅`.** With `k_tactical` fixed at `PRIZE_DAMAGE_RATE = 100` (decision 2, so this is
   a falsifiable *prediction*, not a fitted constant) and the play rung
   `0.5 × 100 × m − _DENIAL_ITEM_COST`, ADR-0062's 5/5 requires f29 to HOLD and f15 to PLAY, i.e.
   `m₂₉ < 0.2` and `m₁₅ > 0.2` prize-equivalents. **ADR-0062 gives real reason to doubt this**: it
   records that *"no monotone pricing of magnitude alone can separate them"* — f29's raw denial (70) is
   more than double f15's (30), yet f29 must hold, so only imminence discriminates. The shared marginal
   IS imminence-aware (phase-scaled survival shift), which is why the swap is plausible at all — but it
   is unmeasured. Scale sanity: deny's 0.9 ceiling gives a max play value of +35 against today's
   observed −1.25…+60, so the rate is commensurate before measurement.
2. **A keep-side deny anchor exists after capture** (decision 3). If re-adjudicating `86091435-68` plus
   the DISCARD-context sweep yields nothing that discriminates, the Worth Damage Rate has no derivation
   and S3c must either capture new corrections or fall back to the reduced scope in *Alternatives
   rejected* below, explicitly and in writing.

## Amendment A — gate 1 RAN and FAILED; the marginal cannot carry deny's discrimination (2026-07-28, #199 build)

Steps 3–5 of #199's build shape landed the same day this ADR was written (`common/currency.py`, the
`deny_strip_delta` strip Δ, `tools/train/probes/deny_gate1.py`), and gate 1 was run over all 21 ruled
Hammer frames in `data/corrections/`. **It fails, and the failure is structural rather than a
calibration miss.**

**Result.** 21 ruled frames, 16 agree / 5 disagree — and every disagreement is the same shape: a frame
the corpus rules PLAY where the marginal reads `m = 0.000`, against an incumbent oracle reading 65–140
damage denied. The separation test:

```
min(m | PLAY) = 0.000     max(m | HOLD) = 0.150     => NOT SEPARABLE
```

There is no exchange rate that separates them, so the failure is not about the value of `k`. It is not
about `PRIZE_DAMAGE_RATE` either — that constant only scales an ordering that is already wrong.

**Mechanism, diagnosed.** The shared marginal is *forward-looking*: it prices "turns of MY survival
bought", and the Threat-Clock curve credits the opponent their one manual attach per turn (rules.md
§3). A single Energy strip is therefore **cancelled by construction** whenever the body can afford its
attack again after one attach — which is most of the frames a Hammer is actually played on. ADR-0062's
oracle measures the strip *instantaneously* (`best_affordable(E) − best_affordable(E−1)`) and never
credits the re-attach. Both readings are internally coherent; they answer different questions, and the
question the marginal answers is not the one deny is asking. Pinned as
`test_deny_strip_delta.py::test_the_next_attach_cancels_a_strip_the_body_can_afford_to_lose`.

**Two confounds of my own were checked and ruled out**, so the result is not an artifact of how the Δ
was built:

| variant | what it changes | min(m\|PLAY) | max(m\|HOLD) | verdict |
|---|---|---|---|---|
| slow / last-energy | the shipped Δ (`_DENY_CHARGED`, strips the last Energy) | 0.000 | 0.150 | NOT SEPARABLE |
| slow / best-energy | maximises over WHICH Energy is stripped (typed costs) | 0.000 | 0.150 | NOT SEPARABLE |
| no-attach / best-energy | `base_attach: 0` — no re-attach credit, closest to ADR-0062 | 0.000 | 0.900 | NOT SEPARABLE |

The third variant is the interesting one: dropping the re-attach credit *does* light up the PLAY frames
(0.267 / 0.425 / 0.500 / 0.900 where the slow policy read 0.000) — the mechanism above, confirmed from
the other side. But it lights up the HOLD frames just as much (three at 0.900), so it trades one
failure for another. Excluding `86091435-68` (which this ADR already flags as REFUTED-AS-LABELED and
therefore unreliable) does not rescue any variant: min(m|PLAY) becomes 0.267 against max(m|HOLD) 0.900.

**What this does NOT settle.** Gate 1 tested the marginal against the *play/hold* surface — decision 1's
surface (b). It says nothing yet about surface (a), the keep price, or surface (c), the target pick,
where a forward-looking read may still be the right instrument. And it does not touch gate 2: the Worth
Damage Rate still has no anchor, independently of this result.

**Consequence for the staircase.** Decision 1 as written — deny reads the shared marginal on all three
surfaces — is **not deliverable as specified**, and #187 is blocked on a design decision rather than on
wiring. The live options, for the user to rule in #199:

1. **Take the recorded fallback** (this ADR's *Alternatives rejected*, "reduced scope"): the play rung
   keeps the ADR-0062 damage oracle, and the marginal is adopted only where it is the right question.
   The grill anticipated this outcome and named it the honest fallback; it now has evidence behind it
   rather than being a hedge.
2. **Give deny a non-forward-looking Δ** — price the strip instantaneously inside the shared value
   function rather than through `turns_to_ko_me`. This keeps one currency but concedes that deny's Δ is
   a different *kind* of quantity from gust's and snipe's, which weakens the one-backend claim.
3. **Rule that the corpus is wrong** on some of the 5 disagreements. Not to be reached for lightly, but
   two of them (`82523811-15`, `82523811-79`) have never been re-reviewed, and `86091435-68` is already
   refuted-as-labeled — so the adjudication session gate 2 needs anyway is the natural place to look.

Recorded here rather than in a review doc because it changes what decision 1 can promise.

## Consequences

- **#187 is not the shortest hop of the three S4 swaps; it is the longest.** Deny is the only
  instrument whose card has no worth floor and no keep-side corpus anchor. Snipe is now the shortest —
  ADR-0076 Decision 2 + Amendment A keep it outside the DP entirely, so it needs no keep-side
  conversion at all. The design doc's deny → snipe → gust ordering still stands, but **behind S3c**,
  and its stated rationale ("lowest-risk hop first") is wrong on the evidence and should not be relied
  on again.
- **#187's charter text needs correcting** on two points of fact: `_opp_denial_best` is not the deny
  slot's value source, and the swap covers three surfaces rather than one.
- `needs.deny_slot`'s docstring is **stale** — it claims *"The VALUE comes from the shipped denial
  oracle (ADR-0062 `_opp_denial_best` — consumed, never re-derived)"* while the caller passes
  `TAG_TIER["gust"]`. Corrected in this change; the WP-N8 currency ruling that made it stale is
  itself overturned by decision 1, so the docstring now records both.
- `PRIZE_DAMAGE_RATE` gains three consumers and moves out of `promote_retreat_value.py`. Its
  CSV-recomputing test moves with it — the property that makes it falsifiable is the point, not an
  incidental.
- `ms_hammer_unfavored_override_f17` is a direct test of `_DENIAL_UNFAVORED` and **must be re-derived**
  under `phase_scale` when decision 6 lands. ADR-0026's Lever A loses a consumer and needs a note.
- ADR-0076 Amendment E's *"handed to #189, not settled here"* is superseded (Amendment F, recorded
  there).
- #136's tracker gains a node; #143's five-way split becomes six.

## Alternatives rejected

- **Read the slice naively and accept the collapse.** The literal charter. Takes a Hammer's only keep
  price from 10.0 to ≤ 0.9 with no floor beneath it; every Hammer sheds at the first discard. Rejected
  on the arithmetic.
- **One global constant across both scales.** What the grill's second question originally proposed.
  Rejected once the third scale was found: nothing in the corpus supports equating worth and damage,
  and pinning the single constant on the 5/5 pushes gust's slot ceiling to ~43, above `discard_eot`'s
  30.0 — a large uncommanded change to an instrument #189 owns.
- **Per-instrument ceiling normalization** (deny's 0.9 ↦ 10.0, gust's 3.9 ↦ 10.0). Preserves both
  incumbents exactly at top-of-band and needs no derivation, but a maximal deny then *equals* a maximal
  gust inside the DP — discarding the cross-instrument comparability O1/Option B chose the assignment
  to buy.
- **Set the worth rate to preserve the incumbent** (10.0 ÷ 0.9 ≈ 11.1) and call it a calibration. Fast
  and unblocking. It is a taste constant with a derivation-shaped explanation — the exact thing
  ADR-0065 forbids and the exact shape of the `_PRIZE_UNIT = 12` error.
- **Reduced scope: swap (b)+(c) only; leave the DP slot at 10.0 with the marginal replacing `/2^t` as
  the grade.** No worth rate needed, no fudge, no collapse, no gust movement, deliverable immediately.
  **This remains the honest fallback if gate 2 fails** — recorded here rather than dropped, and if
  taken it must be stated as a scope reduction in the ADR rather than glossed.
- **Keep the denomination inside #187** (amending ADR-0076 from an instrument-scoped issue). Fewest
  moving parts, and it is where the problem bites — but it puts a cross-instrument ruling inside an
  instrument-scoped issue, which is the anti-pattern ADR-0076 Decision 3 exists to prevent, and leaves
  #189's charter contradicting #187's output.
- **Reverse the order to gust-first (#189)**, where Amendment E already chartered the denomination.
  Gust is the largest fold of the three (the whole merged SUM lifted into the assignment) and its debt
  is latent, so there is no forcing function — the worst place to also carry a foundational ruling.
