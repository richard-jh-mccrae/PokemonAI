# Wave-3 packet — POC-T4/5 (Issue #386): the composer takes the wheel

The sequence composer (`common.composer.compose`) is armed as the MAIN single-pick decider at
`plan_turn`, and the rung ladder it replaces is deleted. This packet is everything that needs a human
ruling, plus the things that turned out to be wrong on the way here.

Nothing below was conformed into either `baseline.json`. **A baseline is a ruling record.** The
Decision Gate died once already by auto-recapture and it is not being revived that way.

The two design decisions this branch makes are recorded in
[ADR-0131](../adr/0131-a-decider-must-not-decide-what-its-own-numbers-say-it-has-no-view-on.md);
§5 below is their measurement.

## 1. What the gates say

| gate | result |
|---|---|
| Decision (`decider_lab diff`) | **FAIL** — 44 unruled REGRESSION, 28 ruled, 2 voided |
| Discrimination (`leaf_lab diff`) | **FAIL** — 61 unruled OK→MISS, 50 ruled, 6 voided |
| `composer_lab` (374 frames, 278 composed) | composer == ruled **88/270**; == chosen 60/278; RULED 1st admitted 355/364 |

The Decision Gate failing is not a surprise and is not a defect: the whole change is that a different
mechanism decides, so every frame where the two mechanisms disagree shows up here. The gate's job is
to make sure none of them passes unseen, and that is what the 44 rows are.

The Discrimination Gate's 61 are **attributed**: identical at the bare swap commit, with all of
this branch's later `src/` changes stashed and the revert asserted by `git diff --stat`. They are
the swap, not the fixes layered on it.

## 2. The flip table — 16 corpus frames, machine-readable

`tests/strategy/poc_t4_flips.py`. Each row: fixture, what the human ruled, what the composer plays,
and the diagnosis. Every row is `xfail(strict=True)`, so a frame that starts agreeing again turns the
suite **red** and forces someone back to promote it.

### REFUSAL (4) — the seam cannot model the human's option, so no weighting reaches it

These are coverage work, not rulings. Two distinct causes survive (the third, `deterministic=None`, retired itself — see §5):

| cause | frames | seam's own words |
|---|---|---|
| **RNG** | `ml0705_petrel_over_lillies_f27`, `ml0705_refill_undeployable_f44` | 1227 Lillie's Determination: clause `shuffle_own_hand_in` consults RNG — *"a simulated shuffle is one sample, not a distribution"* |
| **MULTI-WRITE** | `dragapult_poffin_whiff_take_gust_ko_f79`, `dragapult_gust_ko_over_accel_f81` | choice key `gust`: `CLAUSE_WRITES['gust']` is non-empty (`bodies_in_play`, `special_conditions`, `transient_grants`) — Issue #300 `_covers` |

**The gust hole, as a number rather than an impression.** `poc_t4_flips.GUST_REFUSALS` names
**five** frames refused for one cause — `dragapult_poffin_whiff_take_gust_ko_f79`,
`dragapult_gust_ko_over_accel_f81`, `pilot_cd91`, `85163079|30`, `86091435|119`. Between them they
are the *only* decision-level coverage the gust doctrine had. `test_gust.py`'s deletion note named
two of them as its successors; they do not carry the fact. One `_covers` change fixes all five.

`86091435|119` is the one to look at hardest: it is not a correction the composer disagrees with, it
is a line a human **explicitly adjudicated as better** (2026-07-19, the 2-prize drag-and-spread over
the correction's 1-prize development) that the seam now cannot see at all.

### VALUATION (12) — the seam priced it and ranked something above it

These are the real rulings. `d()` are 1-ply deltas in prizes.

| frame | ruled → composer | d(ruled) | d(composer) | note |
|---|---|---|---|---|
| `pr_whether_should_retreat_f37` | [3] → [2] | 0.0022 | **2.4333** | widest margin in the table |
| `dragapult_concentrate_line_preevo_f85` | [3] → [7] | **−0.03** | 2.25 | composer prices the human's play *below doing nothing* |
| `dp_evolve_the_draw_engine_f40` | [0] → [1] | −0.0039 | 1.0 | promoted TARGET→PIN when `evolve_value` landed; the composer moves it back |
| `dp_hold_evolve_until_typed_ready_f35` | [1] → [0] | 0.075 | 0.5923 | **re-classified from REFUSAL** |
| `dp_evolve_energized_line_body_first_f82` | [1] → [2] | 0.1832 | 0.2763 | |
| `ml_air_balloon_on_the_active_f87` | [0] → [7] | 0.0 | 0.075 | a Tool attach is not an Energy attach |
| `pr_whether_dont_retreat_f9` | [1] → [0] | 0.0 | 0.0622 | terminal option, priced by terminal EV — valuation by construction |
| `dragapult_hammer_no_threat_f6` | [2] → [4] | **0.075** | 0.0667 | same shape — **re-classified from REFUSAL** |
| `dragapult_dont_feed_draw_engine_f21` | [1] → [4] | 0.0667 | 0.0670 | 3 ten-thousandths of a prize decide it |
| `ml_ppp_attack_transient_locked_f69` | [1] → [0] | 0.0 | 0.0 | an exact TIE — the defer fires, so this disagreement is the LADDER's |
| `ml_dont_wake_the_giant_with_the_locking_ko_f88` | [1] → [0] | **2.509** | 0.075 | see below |
| `ml_lethal_retreat_boost_to_ko_f24` | [5] → [3] | 0.0015 | 0.0 | the defer fires; the LADDER answers, and answers [3] |

**`f88` is the row to read first.** The composer prices the human's ruling at **2.509 prizes** and
the option it actually plays at **0.075** — a 33× gap in the ruling's favour at one ply — and plays
the 0.075 anyway. The entire decision is therefore coming from what the sequence does after its first
step. It is the most expensive depth effect in the table.

Three sub-shapes worth ruling separately:

1. **Depth effects** (`f88`, `dragapult_hammer_no_threat_f6`) — the ruled option prices *higher* at
   1 ply and still loses, so the decision comes from the SEQUENCE. A 1-ply weight cannot fix these
   and a 1-ply reading cannot diagnose them. `f88`'s 33× gap makes it the clearest specimen.
2. **The defer fired** (`ml_ppp_attack_transient_locked_f69`, `ml_lethal_retreat_boost_to_ko_f24`) —
   the composer abstained, so what disagrees with the ruling here is the tuned LADDER. Ruling these
   changes nothing about the composer; they are on this list so nobody mistakes them for its work.
3. **Wide margins** (`f37`, `f85`, `dp_evolve_the_draw_engine_f40`) — the composer is confidently
   opposed to the ruling. These are where a human is most needed.
4. **Near-ties above the floor** (`dragapult_dont_feed_draw_engine_f21`, 0.0667 vs 0.0670) — three
   ten-thousandths of a prize decide it, which is real to `_SCORE_PLACES` and meaningless to a
   player. The defer deliberately does NOT catch these; widening it from a float-noise floor to a
   band is a different ruling nobody has made.

## 3. Six frames the swap FIXES

Two the composer solves outright — `82525741-78` and `85058574-114`, open blunders the rung ladder
never got. Both were `xfail(strict=True)` TARGETS; their XPASS is what forced them to PINS.

Four more the tie-defer restores — `86091728-19`, `83661652-29`, `83661652-40`, `85058574-16` — plus
three flip-table rows (§5). On all seven of those the composer's numbers tied, it abstained, and the
structural sequencer played the human's ruling.

`strict` is doing the work in both directions here: it is what surfaced the two wins, and what
forced the seven retirements. A non-strict xfail table would have absorbed all nine silently.

## 4. A shipped wiring gap, found and fixed here

`_composer_line` — the one caller that holds a Pilot — never passed `compose`'s `shed` seam. Left
`None`, a costed search REFUSES by name rather than being priced unpaid, so **the composer had no
opinion about Ultra Ball**, the pool's most-played Item. `Pilot.cost_shed_indices` exists for exactly
that call and says so in its own docstring; it sat unused.

The part that matters more than the bug: **`tools/train/composer_lab.py` has always passed it**, and
records in its own comment that *"without this an Ultra Ball refuses — 65 of the corpus's 69
cost-refused steps"*. So for as long as production went unwired, every POC-T4/5 measurement was taken
on a composer strictly better-informed than the one that shipped. A seam wired in the lab and not in
production is worse than one wired in neither, because the measurement says it works.

Measured cost of wiring it, both arms run with the revert asserted by `git diff --stat`:

| | unruled | ruled |
|---|---|---|
| without `shed` | 56 | 31 |
| with `shed` | 58 | 33 |

Four frames gain a new unruled regression (`82228640│0│decision│7`, `83967841│1│decision│17`,
`85163634│1│decision│17`, `85058574│1│decision│88`); none is fixed. Those four are the composer
*acquiring an opinion* on frames where it previously abstained — which is the point. Two of them
(`83967841-17`, `85163634-17`) are now `POC_T4_FLIPS` rows in `test_hyperclosure_corpus.py` with
that cause written on them, and one (`ml0705_ultraball_starved_f17`) is a flip-table row for the
same reason. Guarded by `tests/strategy/test_composer_seams_are_wired.py`.

These numbers predate the tie-defer of §5, which takes the totals to 44/28/2; the arms are quoted as
measured so the shed decision stands on its own comparison.

## 5. A whitelisted sound rule the swap broke, and the fourth defer (ADR-0131)

**`sound_rules.information-before-commitment` stopped working.** ADR-0095 decision 3 rules that this
ordering is *"NOT derivable by the planner — both orders reach the same end state, so no function of
that state separates them."* Two independent things had to be repaired:

1. **The rung's endorsement was load-bearing for the tier.** `_finish_turn_last` gates on
   `traces[i].score <= 0` ("only an endorsed action sequences early"). With `dig-before-commit` (+20)
   deleted, ADR-0095's own anchor frame prices Pokégear 3.0 at exactly **0.00**, so it drops to
   `_TIER_ENDER` and the boundary underneath never runs on it. The boundary was intact the whole
   time; its input had been removed. Fixed with a four-fenced carve-out — `_PLAY` only, `== 0` not
   `>= 0`, not `cost_discard`, and *nothing fired* — which is exactly the ADR's own case and not the `>= 0` loosening
   ADR-0069 measured and rejected.

   **The fourth fence was missing at first and the suite caught it.** A score of 0 has two very
   different causes: *nothing prices this option* (the Pokégear, once `dig-before-commit` went) and
   *a rung deliberately NEUTRALISED it* (Mega Signal under `dont-tutor-the-held-wincon`, which nets
   a redundant tutor to exactly zero). Without `not traces[i].fired` the carve-out sequenced a search
   the ladder had just refused **first** — found by
   `test_benchless_agent_refreshes_over_a_redundant_wincon_tutor`, whose whole subject is a
   neutralised tutor.

2. **The composer overrode it anyway, on a tie.** On that frame the composer prices **seven of ten
   options at exactly 0.0** — the ruled dig, both Hammers, both Tools, an attach and End — and
   `selection_key` handed the turn to the attach. That is ADR-0095 decision 3 happening in front of
   us: a function of the end state cannot separate two orders that reach the same end state.

So `_composer_line` gains a **fourth defer**, the same kind as its three existing ones — a refusal to
guess. When another menu index's best sequence ties the chosen one at `composer._SCORE_PLACES` (the
same float-noise floor `selection_key` uses, so the two cannot drift into a decision that is a tie to
one and not the other), the composer abstains and the tuned scoring keeps the turn. Equivalence-class
ties are unaffected: the ladder picks a class member too.

**Seven rows retired themselves when the defer landed.** Four in `test_hyperclosure_corpus.py`
whose strict xfails XPASSed and were promoted back to PINS — `86091728-19`, `83661652-29`,
`83661652-40`, `85058574-16` — and three in the flip table — on each, the composer's own
numbers tied, the sequencer took the turn back, and it played the human's ruling:

    ml0703_develop_riolu_not_shuffle_f40        VALUATION  ruled [3] -> now [3]
    ml_dont_energize_the_supporter_tutor_f84    VALUATION  ruled [3] -> now [3]
    ml_lunar_cycle_over_inert_bench_attach_f16  REFUSAL    ruled [6] -> now [6]

The last of the three is the interesting one: a REFUSAL that resolved with **no widening of the seam at all**.
The refused option was never the problem — the composer committing a line it had no view on was.

The defer is not free, and two rows say so. `ml_ppp_attack_transient_locked_f69` and
`ml_lethal_retreat_boost_to_ko_f24` still disagree with the ruling, but the disagreement is now the
LADDER's rather than the composer's, because the composer abstained. Both were already failing before
the defer landed, so it neither caused nor fixed them; it changed who owns them.

Measured, because a defer that fires everywhere hollows out the swap:

| | frames | share |
|---|---|---|
| composer decides | 104 | **63.4%** |
| tie-defer | 43 | 26.2% |
| other defer (no `chosen` / coverage gap) | 17 | 10.4% |
| **MAIN single-pick corpus frames** | **164** | |

and unruled Decision-Gate regressions go **58 → 44**. Guarded by
`tests/strategy/test_composer_defers_on_a_tie.py`, including the other direction — the defer must NOT
fire on a frame with a 2.43-prize margin, or the floor has become a band.

### A gap the defer closed that was already written down

`tests/strategy/test_attack_value.py` had a test named
`test_the_MAIN_attack_veto_is_no_longer_CONSULTED_by_the_decider`, asserting a real hole: `_tactical`
prices a revealing-nothing Seek Inspiration at `-KO_SCORE`, the composer does not read `_tactical`,
and a 0-damage attack and an End reach the same end state — so the composer scored both 0.0 and took
the attack. `ko-score-band` is a whitelisted STRUCTURAL sound rule, and it was invisible.

The defer closes it, and by the right route: 0.0 against 0.0 is the composer saying it has no view,
so it abstains and the veto is consulted again. The test is now
`test_the_MAIN_attack_veto_survives_the_swap_BY_THE_COMPOSER_ABSTAINING`, with three independently
falsifiable links — the veto is computed, the composer declines to overrule it, the turn ends.

## 6. One more telemetry gap, closed

A composer-decided record could not name the option it committed. `_composer_trace["steps"]` is the
chosen sequence's step indices — and a TERMINAL line (an attack, an End) has no steps, so `steps` was
`[]` and the block explained a pick it could not identify. `first_index` is now emitted beside it.
Found by `test_telemetry_reorder_markers.py`, which had to be re-pointed anyway: `deferred` and
`reordered` are computed by `_finish_turn_last`, which a composer-decided frame never reaches, so
asserting them there was asserting a mechanism that did not decide.

## 7. Three instruments that returned clean wrong answers

The diagnosis column in §2 is the fourth attempt. The first three each produced a plausible,
self-consistent, wrong table — recorded because the next person will reach for the same tools:

1. **A bare `apply_option` is not what the composer asks.** It refuses a `_PLAY` whose clauses reveal
   information; `compose` routes that case to `board_expectation` and prices it. This invented an
   entire *"REVEAL family"* of coverage ceilings out of frames that are priced and rulable.
2. **`ruled_index in compose(...).order` is vacuous.** `_refuse` emits a `_Ranked` with `delta=0.0`,
   so a refused option sits in `order` beside the priced ones. Everything came back PRICED.
3. **`_frame_of(option)` cannot be reconstructed by the caller.** A fixture's option dict carries no
   serials, so its frame is `(hand None, body None)` while the gaps `compose` emits carry real ones.
   Never matched, so again everything came back PRICED.

What works: a refusal is a per-option property, so compose a menu holding **that option alone** and
read `gaps`. It discriminates 5 REFUSED / 12 PRICED, which is the positive control.

Net: **3 of 8 rows recorded as REFUSAL were valuation disagreements**, and 2 more were right for the
wrong reason. `test_poc_t4_flips.py` now re-measures every row's diagnosis, which is the guard whose
absence let three rows sit mis-classified.

## 8. Two capability losses, pinned rather than deleted

Both are `xfail(strict=True)`, so each turns RED the day something re-wires the signal — which is
exactly when a human should look.

* **Matchup favorability no longer reaches the refresh decision.**
  `dont-gift-a-refresh-when-favored` was the only consumer of the Read's Lever A here. Measured: the
  same gift board prices **4.0 at favorability 0.7, 0.5 and 0.3** — the number does not move. The
  GIFT/STRIP half survives and survives well (4.0 vs 36.0 for the same Judge), so what was lost is
  precisely the matchup steer ADR-0041 built the Read for. Pin:
  `test_posture_read.test_matchup_favorability_still_reaches_the_refresh_decision`.
* **The clutch heal's gate is no longer conditional.** `hold-clutch-heal` held the save while a KO
  was on the board and fired it when none was. After the deletion the heal prices **0.0 on both**
  boards. The stand-down still "passes" — but because the option is invisible, not because the gate
  works. Pin: `test_blunder_20260701.test_the_clutch_heal_gate_is_still_conditional`.

An unconsumed Board signal is an unbuilt feature; these are recorded so neither reads as a pass.

## 9. A false claim in this branch's own prose, caught and corrected

`src/agents/dragapult_ex/strategy.py` justified deleting `play-risky-ruins-when-net-positive` (+15)
by asserting the leaf took the family over: *"its worth is … a `state_value` delta, and the composer
scores the Stadium play as an ordinary MODELLED option"*. That is **false**, and `state_value` says
so in its own `development.blind_to`: *"the STADIUM — `model.stadium` has a supplier and no reader,
so playing or replacing one prices exactly 0."*

Measured on both of that deck's Risky Ruins boards: the composer MODELS the Stadium play — no
coverage gap — and prices it at exactly **0.0**. That is worse than a refusal, because a refusal is
visible in `gaps` and a 0.0 reads as a considered valuation.

The rung stays deleted (a flat +15 standing in for an unmeasured quantity is what this issue exists
to stop), the note is corrected to say what is owed, and two strict xfails in
`tests/agents/test_dragapult_ex_triggers.py` go RED the day `development` grows the read. Recorded at
this length because it is the exact failure mode `CLAUDE.md` warns about: a deletion rationale
asserting evidence nobody gathered.

## 10. Fixture bugs the composer exposed

Hand-built fixtures encoded facts the rung ladder never checked. Three classes, all corrected:

* **Omitted `cardType`.** `board_delta` routes an ATTACH on `stat.is_energy`, a `cardType` test. Test
  literals omitted it for years because Function Tags were enough. The seam then refuses with
  *"neither Energy nor a Tool"* — a message that reads exactly like a coverage ceiling and is not.
* **Illegal menus.** `test_cost_discard_search_…` handed Ultra Ball (*"discard 2 other cards"*) a
  2-card hand — one other card, so the play is illegal under the engine's own `handOthers` gate. The
  test asserted a sequencing rule about an option that could never be played.
* **Boards too sparse to difference.** `test_build_active_wincon_prefers_active_over_a_bench_copy`
  offers the same Energy to two identical Mega Starmie ex; the composer prices them equal *to the
  last bit*, correctly — the end-of-turn boards are identical, and what makes the Active right is
  that it can ATTACK, which lives in `terminal_ev` and needs an attack on the menu. There is none.

That last one is a limit on what a hand-built fixture can say about a differencing decider, not a
limit on the decider — and it is the honest reason those tests now assert the ladder's own ranking
rather than the decision.

## 11. What is NOT proven

* No ladder win-rate claim. Per the standing mission the deliverable is the differencing system, not
  agreement, and a cross-deck gauntlet proves nothing about gain.
* The 58 unruled Decision-Gate rows are unruled. This packet routes them; it does not settle them.
* `RULED 1st admitted 355/364` counts terminals and refusals, which are admitted unconditionally at
  delta 0.0 — only **96** earned a scored top-k slot. Quoting the first number alone would overstate
  beam quality by ~3.7×.
* 241 of 278 composed frames still carry a coverage gap somewhere on the menu.
* Off-policy exposure is REPORTED, not filtered: 46/270 ruled MAIN frames (Issue #412).
