# ADR-0076 — The opponent-target slot family splits by instrument shape: held-card keep pricing extends the Needs assignment; target-ranking reads the marginal directly

**Status:** Accepted (grilled 2026-07-27, `/grill-with-docs` on #186 — three locked decisions). Build
= #186 (S2 + S3b), consumed by #187 (S4-deny), #188 (S4-snipe), #189 (S4-gust), #190 (S5). #186 is one
of five sub-issues split from #143 (tracker #136) — see #143's closing comment.

**Renumbered from 0074 → 0076 on rebase (2026-07-27).** Three open branches each authored an ADR-0074;
first-merged keeps the number (the 0071/#163 precedent), so #175 KEEPS 0074, #177 took 0075, and this
one took 0076. Every in-repo reference was moved with it; main's #175 references were left alone.

**Context issues:** #186 (this grill), #143 (the un-split original, closed), #136 (the Value System
build tracker), `docs/plans/opponent-value-equation-unification.md` (the design this ADR turns into a
build ruling), ADR-0065 (the Needs / `keep_v2` precedent this extends).

## Context

The unification design doc's O1 ruling (2026-07-22, "Option B: the assignment") says the
opponent-target marginal should be realized as ONE board-wide Needs slot assignment: every opponent
body is a slot, and "my available removal instruments this turn (snipe rider, gust, Hammer,
forced-promo chip) are the cards being assigned to those slots." Read literally, that implies
extending `needs.py`'s existing bitmask-DP solver — today `deny_slot` (`needs.py:182`), consumed only
by the keep/discard resolver (`src/common/CONTEXT.md`'s Card-Worth Oracle entry: Needs is "WHAT the
position requires: deadline-tagged slots + the exact-assignment marginal `keep_v2`") — uniformly
across all four instruments.

Reading the live code surfaced a mismatch: `baseline_snipe.py` and
`strategy/doctrines/doctrine_gust.py` (the snipe/gust target-pickers) import `needs.py` **nowhere**
today. They are independent play-time deciders answering "which opponent body do I hit," with no
held-card keep/discard question involved. Only `deny_slot` genuinely fits the DP's shape, because a
Hammer (or a gust/forced-promo Trainer card) is a scarce HELD CARD whose keep-vs-play value the DP
prices; a snipe rider is not a held card at all — it rides an attack already committed to, and the
DAMAGE select just offers a target choice among already-available options.

## Decision

The opponent-target family splits along what each instrument actually *is*, rather than one uniform
DP extension:

1. **Held-card instruments (deny, gust, forced-promo)** — extend the existing DP assignment
   (`needs.py`'s `Slot` / `assignment_value` / `keep_v2` family) to keep-price these Trainer cards
   against the same per-body opponent-target slots `deny_slot` already occupies. This requires
   **migrating** `needs.SUPPLIES`'s current `"gust"` tag routing — today aliased into the `"deny"`
   kind (the `deny_tags` eligibility set built at `pilot.py:3678`) — onto its own slot kind, and
   adding a `"promo_chip"` kind for forced-promotion cards. Not an addition beside deny; a schema
   split of existing eligibility.
2. **Snipe** — does **not** enter the DP. It reads the shared per-body value function
   (`needs.opponent_target_value` + `needs.phase_scale`) directly, bypassing the assignment entirely,
   because there is no scarce held card whose keep-value competes for the slot.
3. **The sweep/adjudication is centralized in #186.** The same per-body number feeds all three
   downstream S4 swaps (#187/#188/#189), so #186 runs the corpus sweep (23 DAMAGE frames + the gust
   frames + the Hammer frames, the design doc's own S3b acceptance bar) and adjudicates disagreements
   with the user itself — even though #186 ships nothing live except the S2 piece below — rather than
   letting each S4 issue re-litigate the same shared value through its own instrument's lens.

**Decision 0 (S2 scope, prerequisite to the above).** `discard_recur_fuel` goes live only on the
`incoming()` ceiling-policy path (survival: `active_doomed` / the doom-relax gate), because raising a
threat number is the fail-scared, safe direction. It does **not** go live on `turns_to_afford` (the
deny/posture clock): lowering that turn count is the fail-slow, unsafe direction the design doc itself
flags as needing calibration this issue doesn't yet have — over-crediting it would over-spend a scarce
Hammer/Guzma on a refueler that isn't actually that close. That adoption is explicitly deferred, owned
by #187 or a dedicated follow-up, not silently dropped.

## Consequences

- `baseline_snipe.py` gains its first-ever dependency on the Needs module family
  (`opponent_target_value` / `phase_scale`) — but not on the DP assignment itself.
- `doctrine_gust.py`'s Trainer-card holding logic and the deny-slot emission both route through the
  generalized DP; `needs.SUPPLIES`'s `"gust"` tag entry is **migrated**, not just extended, so existing
  eligibility behavior for held Guzma-class cards changes shape even before any live decider swap
  fires — #186's own test coverage should call this out explicitly so it isn't an invisible side
  effect of "shadow, decides nothing."
- #187 (S4-deny), #188 (S4-snipe), #189 (S4-gust) each inherit an adjudicated, corpus-validated
  per-body value and only grill their own slot-kind wiring + kill-switch; none re-opens the
  shared-value question.
- #186 ships an intentionally asymmetric Threat Clock read: more cautious about survival immediately,
  unchanged for deny/posture until a calibrated follow-up lands.

## Amendment A — forced-promotion pre-chip is a snipe-family read, not a held card (2026-07-27, build)

Building #186 surfaced a factual error in the Decision above. Read at source
(`baseline_snipe.py`'s `snipe-the-forced-promotion` rung, `Context.target_is_forced_promotion`,
`Pilot._forced_promotion_key`, ADR-0044): "forced-promo chip" is the ADR-0044 Forced-Promotion Read —
a DAMAGE-select target-priority rung that pre-chips whichever bench body the opponent will be forced
to promote next turn. It is not a Trainer card at all, held or otherwise; it lives entirely inside the
snipe family's existing target-picking logic, gated by `Pilot.forced_promotion` (an existing kill-switch,
default ON since 2026-07-06 — unrelated to this issue). The design doc's own description at the point
it names the instruments ("Snipe rider, gust+KO, Hammer strip, forced-promotion pre-chip are the SAME
question, different instrument") already says this; Decision 1 above misread the later "cards being
assigned to those slots" phrasing as implying a held card for every instrument, including this one.

**Corrected split:**

- **Held-card instruments needing the DP: deny (Hammer) and gust (Guzma/Boss's-Orders-class Trainer
  cards) only.** No `"promo_chip"` slot kind is added to `needs.py` — there is no held card it would
  price.
- **Direct-value-read instruments (DAMAGE-select target choices, no held card): snipe AND
  forced-promotion pre-chip both.** Both read `needs.opponent_target_value` / `needs.phase_scale`
  directly; #188 (S4-snipe) is where either or both are actually wired in as the live decider.

This does not change the grill's underlying ruling (split by instrument SHAPE, not treat all four
uniformly) — it corrects which instruments fall on which side of that split. Consequences and the
build plan below are updated accordingly; nothing in `needs.SUPPLIES` names a `promo_chip` kind.

## Amendment B — the S2 integration point, and the sweep result (2026-07-27, build)

Two things settled during the build that the grill's Decision 0 didn't pin precisely enough to code
against directly.

**Where S2 actually lands.** `active_doomed`'s worst-case leg (`combat.active_doomed`) never called
`combat.incoming` at all — it's built on the older `incoming_active_damage` / `forward_incoming_damage`
pair, which is unconditionally worst-case and doesn't gate on Energy affordability, so feeding fuel
into it would change nothing. The actual place fuel matters is the matched-Read RELAX path
(`doomed_incoming`, the CHARGED policy) — and that path already shipped its own coarse fuel guard,
`Pilot._doom_recur_fueled` (2026-07-23): whenever a recur-fueled line is merely POSSIBLE, the relax
stands down entirely, never checking whether the fuel actually matters. Its own docstring names the
target precisely — *"the S2 recur read models the fuel; the doom swap only refuses to relax across
it"* — so S2 going live here means quantifying that guard, not wiring a new `incoming()` consumer:
`Pilot.recur_fuel_relax` (OFF by default) augments the opponent Active's Energy with its real
`discard_recur_fuel` reload before the charged relax check runs, so a line whose fuel still can't
afford its attack is told apart from one where it does — recovering a legitimate relax the boolean
guard was blocking for no reason, never manufacturing a doom the worst-case oracle didn't already cry.
Resolved from the code itself (`_active_doomed`, `_doom_recur_fueled`, `combat.active_doomed`), not
re-litigated with the user — it doesn't change the ruling (S2 stays survival-only, fail-scared-safe),
only which function it wires into.

**The sweep found nothing to adjudicate.** `tools/train/probes/threat_sweep.py --slots` (new: replays
every corpus frame through a shipped pilot and a second one with `gust_target_slots` forced ON, and
flags any decided-pick disagreement) ran clean: **331 frames checked, 0 flips, 1 unreplayable.** The
DOOM/RECUR/TARGET sweep numbers were re-run for drift and match the design doc's recorded figures
exactly (259/274 DOOM agreement, 15 one-directional disagreements; 43 RECUR frames, 41 moved; TARGET
unchanged) — the S3 refactor (extracting `_opponent_target_rows` as the shared computation both the
shadow and the live `gust_target` emission read) is confirmed behavior-preserving. With zero
disagreements, there was nothing for decision 3's adjudication to rule on.

## Amendment C — the caching promise, and why both flags stay OFF (2026-07-27, code-review)

`/code-review`'s Spec pass on this build caught two real gaps against Decision 0/2 above and this
ADR's own Amendment B.

**The "shared, cached" value wasn't actually cached.** Amendment B's S3 refactor shared the
*computation* (one function, `_opponent_target_rows`) but not the *result* — the shadow and the live
`gust_target` emission each called it fresh, so a decision with both paths active ran the per-body
`turns_to_ko_me` simulation twice. Fixed: `_board()` now resolves it once per decision and stashes it
(`self._opponent_target_cache`, the `_opp_attack_context` stash precedent); both consumers read the
cache, falling back to a fresh compute only when called directly off a hand-built `board` that never
went through `_board()` (the existing shadow tests' pattern). A new test
(`test_gust_target_slot_resolver.py::test_the_per_body_value_resolves_once_per_decision_and_is_shared`)
spies on `_opponent_target_rows` and asserts neither consumer recomputes.

**`recur_fuel_relax` was never actually corpus-swept.** The original PROFILE comment claimed it was
"corpus-swept clean," but `threat_sweep.py --slots` only forced `gust_target_slots` — `recur_fuel_relax`
had only the four synthetic unit tests (`test_recur_fuel_relax.py`) behind it, no real-corpus check.
Fixed: `sweep_slots` now forces each flag independently and reports both; re-run, **both are 0 flips
across the same 331 frames.**

**Neither flag arms, and the PROFILE comment's reason was wrong.** The original comments said arming
was "#187/#189's scope" — but those issues are chartered for the deny/snipe/gust DECIDER SWAPS, not
for arming #186's own foundation flags. The real reason is standing directive 6 (ADR-0072): every
mid-build decider swap needs the paired-A/B gauntlet tripwire (`gauntlet_swap_ab.py --stage
mid-build`, ~36 min of real games) **in addition to** a deterministic corpus check before arming ON —
a `threat_sweep.py --slots` clean run is evidence toward that bar, not the bar itself. That gauntlet
run is real, uncommitted follow-up work (not scoped into #186's spec, and not run here given its
cost), so both flags ship OFF on that basis — corrected in both PROFILE comments.

## Amendment D — the gauntlet ran; both flags armed ON (2026-07-27, follow-up)

Amendment C's deferred gauntlet run was completed the same day, closing the gap it named.

**Instrument choice.** `gauntlet_swap_ab.py --stage mid-build` (directive 6's example command) A/Bs
two *builds* via staged bundles — the right tool once a swap deletes what a flag used to fall back
to. Neither `recur_fuel_relax` nor `gust_target_slots` deletes anything (both are pure additive
kill-switches; the OFF path is fully intact) — so `gauntlet_ab.py`, the same-code flag-overlay A/B
(`--overlay {"params": {"<flag>": true}}`), is the mechanically correct fit, not a substitution for
the swap tool. That script's own baked-in verdict line applies the ORIGINAL Tier-5 rule
(`delta >= 0 AND CI-lo >= -1%`) predating ADR-0072's mid-build re-scoping — its printed "FLIP: False"
was disregarded and the actual ADR-0072 mid-build Tripwire (`crashes == 0 AND CI-lo >= -5%`, no delta
clause) applied by hand to the raw aggregate instead. Run at `-n 200` across the three
historically-calibrated agents (dragapult_ex, mega_lucario, mega_starmie — matching directive 6's own
"~2400 games" sizing; `grimmsnarl_ex` also exists but wasn't part of that original calibration and
was left out to keep the run comparable).

**Results, both clearing the Tripwire:**
- `recur_fuel_relax`: aggregate delta +2.4%, 95% CI [-1.1%, +5.9%], 0 crashes / 2400 games.
- `gust_target_slots`: aggregate delta -0.75%, 95% CI [-4.3%, +2.8%], 0 crashes / 2400 games — one
  individual matchup (mega_lucario vs mega_starmie) swung -11.5pp. The Tripwire screens catastrophes,
  not regressions (directive 6: "not a claim of non-regression"), so this single-matchup wobble is
  flagged for the ladder-corrections loop to watch rather than treated as disqualifying — the
  aggregate clears the bound the gate actually sets.

**Decision: both flags armed ON** in `runtime.py`'s `PROFILE` (and mirrored in
`tests/agents/test_runtime.py`'s `EXPECTED_SHIPPED`) — both mandatory mid-build gates (deterministic
corpus check, paired-A/B tripwire) are now cleared for both.

## Amendment E — the Discrimination Gate, run late; and the currency debt handed to #189 (2026-07-27, code-review)

A second `/code-review` pass (Opus) after Amendment D found two things Amendment D should have
carried, plus one design debt that is not this issue's to settle.

**The Discrimination Gate was skipped before arming, and has now been run.** ADR-0072 decision 2
makes *both* merit gates mandatory. Amendment D's arming leaned on the Tripwire plus a bespoke
`threat_sweep.py --slots` sweep, and never ran `leaf_lab.py diff --baseline
data/leaf_lab/baseline.json`. Run now, it reports **`GATE: FAIL` — 2 unruled `OK → MISS`**
(`85163634|1|decision|41` rank 1→2, `86091435|0|decision|13` rank 1→4) with 5 `MISS → OK`.

**Those two are NOT caused by this branch.** A control run with both flags forced OFF on the same
tree reports the identical 2 regressions at identical ranks and the identical 5 improvements — this
branch is **gate-identical to main**. They are the pre-existing baseline drift this very ADR's
source already recorded: ADR-0072's own "separate finding the control run turned up, also unruled"
names the same two frames and ranks against `data/leaf_lab/baseline.json` pinned at `81eac82`, and
prescribes the fix — *"run the gate on `main` before the next swap, not after it."* The arming in
Amendment D stands: it introduces no new gate regression. The process error was running the gate
after the arming decision rather than before it.

**Superseded by main during the rebase (2026-07-27) — the two frames are now RULED.** This amendment
originally reported both frames as still unowned. That is no longer true: `main` has since held both
out explicitly — `86091435|0|decision|13` to **#189** (gusting, `1120eaa`) and
`85163634|1|decision|41` to **#143** (the targeting equation, `bc069bd`), alongside `6faee00`
ruling the two #141 reds. So the debt this amendment flagged as unowned was picked up independently
while this branch was open, and the gate's `HELD OUT` mechanism (ADR-0072 decision 4) now carries
them. Recorded rather than silently deleted, because the sequencing is the point: the finding was
real when written and was resolved elsewhere, not by this branch.

**Decision Gate: judged N/A, recorded here rather than left silent.** ADR-0072 names "the phase's
`tools/train/probes/*_decider_sweep.py`", and no such sweep exists for #186 — correctly, because
#186 swaps no decider and deletes no rungs (the condition ADR-0069 §8's protocol is written for).
`threat_sweep.py --slots` (0 decision flips / 331 frames, both flags, independently) is the
stand-in. Recorded as a judgement so a later reader sees it was decided, not overlooked.

**The currency debt — handed to #189, not settled here (user ruling, 2026-07-27).** Decision 1
above prices `gust_target` by `opponent_target_value`, which is denominated in **prize-equivalents**
(max ~3.9 for a 3-prize body with 8 survival turns bought). Every other slot kind in the same
*summed* `_keep_slot_dp` assignment is denominated in **card-worth points** (wincon 30.0,
`discard_eot` 30.0, `deny` 10.0, Energy 8.0). So a gust card can no longer out-compete any other
slot kind, where at deny's 10.0 tier it competed with Energy and recycle — and `needs.py`'s own
module docstring says slots are "valued in the ONE currency". This also overturns the WP-N8
precedent Decision 1 cites (*the marginal is a tier; the damage magnitude stays on the play-side
rungs*) without saying so. It is currently **latent, not firing**: 331 corpus frames show 0 decision
flips because the general-worth floor absorbs the drop. The fix needs a *derived* prize↔worth
conversion — inventing a scaling constant is precisely the fudge ADR-0065 forbids — so it belongs to
**#189 (S4-gust)**, which reworks this marginal and must rule the denomination as part of its own
grill. Flagged there rather than patched here.

## Alternatives rejected

- **Flat shared value function, no DP extension for gust/forced-promo.** Simpler — one function, four
  independent callers — but reopens O1's already-locked ruling (2026-07-22) without saying so, and
  gives up the no-double-spend / cross-repricing guarantee across a held Hammer and a held Guzma that
  O1 specifically chose the assignment to buy.
- **Full live adoption of S2 on both clocks now.** Faster — one flag instead of a split — but ships
  the deny-side change in a direction the design doc itself calls unsafe, with no derived discount to
  calibrate it: the "magic-number fudge" ADR-0065's standing discipline forbids.
- **Defer sweep adjudication to each S4 issue.** Less up-front work, but risks the same per-body
  number being ruled differently by three separate instrument-scoped grills looking at the same
  corpus frame.
