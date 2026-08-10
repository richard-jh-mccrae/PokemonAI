"""The sound-rule whitelist, as data (ADR-0099, Issue #259).

The rules that survive the POC's purge because they encode game structure or fail-direction policy
rather than a strategy hypothesis. `validate()` rejects an entry missing its type's mandatory field.
`docs/plans/value-system-poc-plan.md` §6 renders the same ``id`` column and `test_sound_rules.py`
cross-checks the two, so the doc and the data cannot drift.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

STRUCTURAL = "structural"
PROVISIONAL = "provisional"
AUTHORED_SCAFFOLD = "authored-scaffold"
#: The exact string is shared with Issue #264's disposition table — do not reword it.
COMPOSED_INTO_THE_LEAF = "composed-into-the-leaf"

TYPES = frozenset({STRUCTURAL, PROVISIONAL, AUTHORED_SCAFFOLD, COMPOSED_INTO_THE_LEAF})

#: :data:`COMPOSED_INTO_THE_LEAF` is deliberately absent: it is math, not a guard.
DECIDER_TYPES = frozenset({STRUCTURAL, PROVISIONAL, AUTHORED_SCAFFOLD})


@dataclass(frozen=True)
class SoundRule:
    """One whitelist entry. ``id`` is the stable slug a commit message or a track issue cites."""

    id: str
    #: The rule, filter, rung or constant, named as it appears in the source.
    entry: str
    type: str
    #: The board fact this guards, or the policy it encodes.
    fact: str
    reason: str
    retirement_test: str = ""
    reconciliation: str = ""
    #: The `state_value` term family that absorbs this equation's math once it stops deciding.
    composed_into: str = ""


WHITELIST: tuple[SoundRule, ...] = (
    SoundRule(
        id="ko-score-band",
        entry="`KO_SCORE` structural band + `_LINE_CAP` invariant",
        type=STRUCTURAL,
        fact="a prize is worth more than any positional term",
        reason="The positional caps SUM to 590 (readiness 300 + survival 50 + threat 100 + value 40 "
               "+ line 100) against KO_SCORE 1000, deliberately, so no positional term can outrank a "
               "real prize. `_LINE_CAP` is the line term's 100 (`strategy/planner.py`), one summand "
               "of that band rather than the band itself. The invariant is what makes "
               "'un-outbiddable' expressible at all. "
               "**OWED A RULING — Issue #369** (repointed 2026-08-03 off Issue #330, which closed "
               "`completed` the same day once its buildable half — this repoint and the two "
               "strict-xfail TARGET tests below — landed; #330 was itself repointed off POC-T3, "
               "Issue #262, which closed `completed` 2026-08-02 with the ruling undelivered. This "
               "was the only outstanding structural-invariant debt in the whitelist and it must not "
               "go unowned again, which is the exact failure this entry's closing sentence guards "
               "against). "
               "Issue #369 rather than Issue #263: Issue #369 IS this entry's question — *does a "
               "banked prize outbid `survival`* — and it carries both the measurement (22 corpus "
               "frames, held out on `owner: \"#369\"`, five of them ALSO claimed by Issue #291's "
               "T3.5 closeout and ruled by Issue #370) and the two strict-xfail TARGET tests in "
               "`test_state_value.py` that pass the day the debt is discharged. Issue #263's "
               "`attack_ev` wiring (developer-ruled 2026-08-02) is a MECHANISM that may discharge "
               "it, not the debt itself; pointing the debt there would let Issue #263 retire this "
               "entry by landing, whether or not the pair invariant then holds. Issue #369 is "
               "itself blocked on Issue #263 landing before it can re-measure. "
               "`state_value` does NOT reproduce that "
               "arithmetic: `survival` is prize-denominated and uncapped (a 3-prize body they can "
               "Knock Out costs three times a 1-prize one, and a cap under a prize would erase the "
               "distinction and price a heal at ~0), and `hand`/`development` carry runaway guards "
               "at 1.5 prizes each rather than the incumbent 0.04/0.1 (transcribed, they saturate, "
               "and a saturated term has zero derivative — so under 1-ply differencing every play "
               "touching it prices at 0 delta and is never explored). What T3 preserves is the rule "
               "restated on DELTAS: an absolute positional level cancels in "
               "`state_value(after) - state_value(before)`, so what could outbid a prize is a single "
               "play's MOVE, and the per-body bounds hold that under 1.0. That restatement is a "
               "change to a ratified structural entry and is filed in the wave-3 packet; it is "
               "recorded here rather than left as a docstring claim, because a whitelist that "
               "describes a band the code abandoned is worse than one that says so. "
               "**The band has TWO terminal constants, not one (Issue #362).** `LOSS_PRIZES` was "
               "derived at the T3 swap; the mirror `WIN_PRIZES` was not, and until Issue #362 the "
               "planner's coin-free-win short-circuit paid a transcribed `KO_SCORE x (start_prizes "
               "+ 1)` that a merely-WINNING position out-scored on 4 of the 26 corpus frames that "
               "reach a simulated win. Both are now derived from the same summands, both live in "
               "`state_value.py`, and the leaf's own `_LINE_CAP` is covered by the win band's prize "
               "of headroom rather than by a second constant.",
    ),
    SoundRule(
        id="setup-never-bench",
        entry="Set-Up never-bench (ADR-0086 decision 9)",
        type=STRUCTURAL,
        fact="pregame Bench placement",
        reason="Deferring to my own first turn is WEAKLY DOMINANT, from three source-checked facts: "
               "the placement is optional ('up to 5', rulebook L97); no attack reaches me first in "
               "either seat (docs/rules.md §2); and of the 21 damage-counter Abilities in the card "
               "data, ZERO sit on a Basic, so no Ability damage reaches me either. Deferring also "
               "BUYS the bench-drop Abilities, which are unsatisfiable before the game starts.",
    ),
    SoundRule(
        id="empty-bench-filter",
        entry="empty-Bench forced deploy filter (`_empty_bench_forced`)",
        type=PROVISIONAL,
        fact="empty Bench under a knock-outable Active",
        reason="Guards a LOSS condition (docs/rules.md §7 case 2: an Active Knocked Out with nothing "
               "to promote ends the match). Unconditional for now because the read that would "
               "replace it depends on the CombatMath/StateModel completeness T1 is delivering — the "
               "very gap that caused this POC replan.",
        retirement_test="After T1 (Issue #260): measure `reachable_incoming`'s answer rate over "
                        "every post-setup empty-Bench corpus frame. Retire IFF the read answers on "
                        "all of them AND both gates stay green with the filter removed — at which "
                        "point `_predicted_loss` is the sole guard on this fact.",
    ),
    SoundRule(
        id="predicted-loss",
        entry="`state_value._predicted_loss` case 2 (−KO_SCORE bench-empty doom, ADR-0064)",
        type=STRUCTURAL,
        fact="empty Bench under a knock-outable Active",
        reason="The SAME fact as `empty-bench-filter`, and deliberately so: this is the doom-gated "
               "form (bench empty AND `combat.reachable_incoming >= my_hp`) that becomes the SOLE "
               "guard once the filter retires. Two entries on one fact is the double-counting rule "
               "being paid down on a schedule, not an exception to it — which is why the filter is "
               "typed provisional and this one is not. "
               "**RE-HOMED, not retired, at POC-T4/5 (Issue #386):** the entry used to name "
               "`planner._predicted_loss`, the terminal rung, which was deleted with the rung ladder "
               "the composer replaces. The fact did not move — `state_value._predicted_loss` is the "
               "port of that exact rung and reads the same CombatMath gate, so this is one entry "
               "changing address rather than a guard going away. Note the whitelist named a deleted "
               "function while staying green: `test_sound_rules` keys on `id` and `fact`, so nothing "
               "checks that an `entry` still resolves.",
    ),
    SoundRule(
        id="prize-lethality",
        entry="`state_value._predicted_loss` case 1 (`LOSS_PRIZES` prize lethality, ADR-0064 "
              "Amendment B)",
        type=STRUCTURAL,
        fact="a body whose Knock Out gives the opponent their last prize",
        reason="A SECOND win condition (`docs/rules.md` §7 case 1: *you win when you take your last "
               "prize card*), guarded by the same term and the same clock as case 2 — a DIFFERENT "
               "fact, which is why it is its own entry rather than a reworded one. Why it can only "
               "live on the terminal term, and why consulting their prize count there is not a "
               "disjointness breach, are ADR-0064 Amendment B's to argue. Binary for the POC.",
    ),
    SoundRule(
        id="information-before-commitment",
        entry="`_finish_turn_last` — the information-before-commitment boundary",
        type=STRUCTURAL,
        fact="within-turn action ordering",
        reason="An informative, reversible action weakly dominates a committing one: the engine "
               "re-presents the menu after every non-ending action, so taking the dig first cannot "
               "cost the commitment but can improve it. NOT derivable by the planner — both orders "
               "reach the same end state, so no function of that state separates them "
               "(ADR-0095 decision 3). Narrowed from 'the sequencing tiers': the old line was "
               "unfalsifiable, and was in fact FALSE in the free band, where tier 0 conflated "
               "'free' with 'informative'.",
    ),
    SoundRule(
        id="doom-ceiling-fail-direction",
        entry="worst-case doom ceiling as the survival fail-direction",
        type=STRUCTURAL,
        fact="which way an unknown survival read errs",
        reason="A fail-direction policy, not an estimate: when the clock cannot answer, assume the "
               "worse outcome for me. Becomes a POLICY PARAMETER after T1's fold of the legacy doom "
               "pair, which is a change of shape, not of doctrine.",
    ),
    SoundRule(
        id="declaration-rungs",
        entry="opening / mulligan declaration rungs",
        type=STRUCTURAL,
        fact="the opening declaration",
        reason="Deck-DECLARED, never tuned — the deck's own statement of what it opens on. A "
               "declaration is data the deck author wrote, so there is no weight here to delete.",
    ),
    SoundRule(
        id="lethal-solver-preemption",
        entry="Lethal-Solver preemption above the planner",
        type=STRUCTURAL,
        fact="a verified winning line",
        reason="Sound win detection outranks every heuristic by construction: a confirmed win ends "
               "the game, so no positional value can be worth more. It sits ABOVE the composer for "
               "the same reason it sits above the Turn Goal today.",
    ),
    SoundRule(
        id="firing-equation-constants",
        entry="authored constants inside firing equations (ROLE_TIER / TAG_TIER, readiness-leaf "
              "values, planner sub-prize constants, confidence seeds, the refresh swing's "
              "opponent-side STRIP / GIFT / FRESH per-card prices, the free-Item hold floor "
              "`hold_value.ITEM_HOLD_FLOOR` and its seam rate `currency.ITEM_HOLD_WORTH_RATE`, "
              "the gust-target seam's `currency.GUST_TARGET_BAND`, and the opponent role sheet's "
              "`scouting.matchup_plan._ROLE_PRIORITY` — the SAME class, and it joins this existing "
              "entry rather than opening its own (Issue #395 D9). It was an authored magnitude table "
              "inside an equation whose shape is right, covered by no whitelist row at all, and that "
              "gap predates the issue; a NEW entry would need its own non-empty reconciliation, while "
              "reusing this row's `fact=` string turns `undeclared_double_guarding()` red and "
              "cosmetically differentiating it makes that detector pass VACUOUSLY, which is worse. "
              "Its ORDER is what decides at this seam and its magnitudes are the tunable part; the "
              "table is now derived from `ROLE_REGISTRY`, so the numbers have one home) — and, "
               "since POC-T3, the `state_value` scale anchors and runaway guards: `_READINESS_W`, "
               "`_SATURATED`, `_ROLE_FLOOR`, `_PROXIMITY_W`, `_DEPLOY_PRIZE_BAND`, "
               "`_BENCH_SLOT_PRICE` and the four family caps. `_THREAT_CAP` was in that list for a "
               "second reason between 2026-08-02 and 2026-08-03 (Issue #262): it was the one family "
               "cap with NO scale anchor in front of it, so it bound on 100% of inputs and `threat` "
               "answered one bit rather than grading. **Issue #329 closed that half and this entry "
               "did not grow**: the anchor is `state_value._THREAT_W = _THREAT_CAP / "
               "needs.TARGET_VALUE_CEILING` — the numerator already on this list, the denominator "
               "itself derived from the card set's own largest prize value and the existing "
               "survival cap (the same derivation the `GUST_TARGET_BAND` note below cites) — so it "
               "introduces no new magnitude and adds no "
               "scaffold debt. `_THREAT_CAP` itself is unmoved at 0.1 — the anchor went in FRONT of "
               "the guard, which is what leaves `POSITIONAL_MAX` (3.4) and the `LOSS_PRIZES` (28.9) "
               "derived from it byte-identical. Measured after the change: the guard bites on 45 of "
               "614 non-empty corpus inputs rather than 614, and 33 distinct inputs now reach 28 "
               "distinct outputs rather than 1. `_THREAT_CAP` remains listed here for the ORIGINAL "
               "reason it and its three siblings are — an authored magnitude inside an equation "
               "whose shape is right",
        type=AUTHORED_SCAFFOLD,
        fact="magnitudes inside equations that already fire correctly",
        reason="Tolerated for the POC: these sit INSIDE equations whose shape is right, so they "
               "scale an answer rather than decide one. Deleting them would remove working "
               "behaviour to no benefit before there is anything fitted to replace them.",
        reconciliation="Queued wholesale for the post-POC learning phases (Issues #146–#148). Not "
                       "individually reconciled — the queue is the commitment. ONE member carries a "
                       "named PREREQUISITE besides the queue: the refresh swing's `_REFRESH_OPPONENT_HAND_STRIP` (4) "
                       "/ `_REFRESH_OPPONENT_HAND_GIFT` (8) (ADR-0101, Issue #261 item 2b, discharging Issue #222). "
                       "Grading them is designed (hand-disruption-grill-spec.md design A) and PARKED "
                       "on measurement — 59.4% of an opponent's representative build prices "
                       "`role_value` 0 today, and the missing 59% is exactly their attackers and "
                       "wincons, so a derived GIFT would be biased in ADR-0060's CRITICAL direction. "
                       "⚠️ ISSUE #395 BUILT THE SHEET AND DID NOT DISCHARGE THIS. The prerequisite as "
                       "written named gusting-keepcost-design.md §2's shared opponent role sheet, and "
                       "that sheet now exists (`matchup_plan.ROLE_REGISTRY` + `derive_general_roles`) "
                       "— but it is an ORDINAL PRIORITY over bodies IN PLAY, and grading a hand strip "
                       "needs a WORTH over cards we cannot see, an expectation across their "
                       "representative build. Those are different quantities and the second does not "
                       "arrive by citing the first; `card_worth.role_value` is untouched by that "
                       "issue, so the 59.4% is unchanged and remains the reason. The condition is "
                       "restated as the quantity rather than the artifact: these retire when an "
                       "opponent-build WORTH exists, not when a role sheet does. The mirror at "
                       "`pilot.py`'s refresh-rate block carries the same correction, made in the "
                       "same commit — it states the same ruling in its own words rather than "
                       "byte-identically, and NOTHING enforces the pairing, so a later edit to one "
                       "must be made to the other by hand. A SECOND member joined 2026-08-02 (Issue #261 item 2f) "
                       "and it is a net REDUCTION, not an addition: `_DENIAL_ITEM_COST = 10` was an "
                       "authored constant hard-gated to one card class, and `hold_value.ITEM_HOLD_FLOOR` "
                       "is the same number generalised onto the Needs assignment as a FLOOR, with the "
                       "~1.0 worth<->damage rate it silently implied now named as "
                       "`currency.ITEM_HOLD_WORTH_RATE` beside `DEPLOY_BAND`. Both carry the deploy "
                       "band's reconciliation debt: if a general Worth Damage Rate is derived (the "
                       "`poc-worth-prize-rate` entry is the candidate), they are checked against it, "
                       "and a disagreement is evidence about ONE of the two. A THIRD member joined "
                       "2026-08-02 (Issue #313 item 2g) and it adds no NUMBER at all: "
                       "`currency.GUST_TARGET_BAND` IS `TAG_TIER['gust']`, already listed above, read "
                       "at import as the ceiling of a ratio whose divisor "
                       "(`needs.TARGET_VALUE_CEILING`) is derived from the card set's own largest "
                       "prize value and the existing survival cap. Its rate "
                       "(`GUST_TARGET_WORTH_RATE`, ~2.564 worth per prize-equivalent) is the "
                       "quotient, not an authored figure — but it is listed here because its "
                       "reconciliation is the sharpest of the three: composing the two SHIPPED legs "
                       "(`PRIZE_DAMAGE_RATE` 100 / `ITEM_HOLD_WORTH_RATE` 1.0) says ~100 worth per "
                       "prize, a ~39x disagreement recorded in `currency.py` rather than smoothed "
                       "over. `state_value.worth_to_prizes` SETTLED it (POC-T3, 2026-08-02) and settled it "
                       "by REFERENT rather than by moving either number: the gust rate converts a "
                       "prize-equivalent INTO Worth to rank a slot inside a Worth-denominated DP, "
                       "while the scaffold converts a HELD CARD's Worth into prizes to price "
                       "spending it — same pair, opposite directions, different referents. The "
                       "reductio is that at the gust seam's rate a held `ROLE_TIER['win_condition']` "
                       "prices at 11.7 prizes, nearly twice the six that END the match. So Worth is "
                       "an ORDINAL priority scale inside an assignment, not a quantity globally "
                       "exchangeable with prizes, and no general rate is owed. "
                       "The T3 additions are "
                       "NOT free inventions: each is anchored to the constant it replaces at the "
                       "same band (old Issue #145's seeding method 1, the currency-zone rule) — "
                       "`_READINESS_W` to `planner._READINESS_ATTACK_W`, `_SATURATED` to "
                       "`planner._READINESS_SATURATED`, `_ROLE_FLOOR` to the bottom rung of "
                       "`ROLE_TIER`, `_PROXIMITY_W` to `needs._PHASE_PRIZE_W`, `_DEPLOY_PRIZE_BAND` "
                       "and `_BENCH_SLOT_PRICE` to `currency.DEPLOY_BAND`. "
                       "`test_state_value.py` asserts the first two against the planner directly, "
                       "because that import would be a cycle in the source.",
    ),
    SoundRule(
        id="poc-worth-prize-rate",
        entry="`state_value.worth_to_prizes` (private authored rate)",
        type=AUTHORED_SCAFFOLD,
        fact="the Worth -> prize exchange rate",
        reason="Needed because differencing makes every card-spending play cross the scale boundary: "
               "the card is in `hand` (Worth) before and on the board (prizes) after, so the Worth "
               "does not cancel. Pricing the hand at zero instead was rejected — it makes every free "
               "Item strictly worth playing.",
        reconciliation="AUTHORED 1/120 prizes per Worth point, stated against every rate "
                       "`currency.py` catalogues rather than dropped in beside them (ADR-0097 "
                       "decision 1). The catalogue grew to FOUR while T3 was in flight, so all four "
                       "are reconciled: worth<->damage deploy 0.83 (the ANCHOR — 25/30 over "
                       "PRIZE_DAMAGE_RATE IS this constant), trainer `ITEM_HOLD_WORTH_RATE` 1.0 "
                       "(within 20%; it replaced the deleted `_DENIAL_ITEM_COST` this note used to "
                       "cite), energy ~6.7 (DISAGREES ~8x, a real referent difference — a card in "
                       "hand vs fuel already attached); and on the SAME prize<->worth pair, "
                       "`GUST_TARGET_WORTH_RATE` 2.564 worth/prize against this constant's 120, "
                       "~47x. That last one is SETTLED by referent, not split — see the "
                       "`firing-equation-constants` entry above and the reductio it records. "
                       "Composing the two shipped legs (PRIZE_DAMAGE_RATE / ITEM_HOLD_WORTH_RATE) "
                       "gives a second same-pair reading, 100 worth per prize, which this 120 sits "
                       "inside 20% of — so two independent readings agree and one is explained. "
                       "Retires when a post-POC fit against ruled spend-vs-hold frames converges. "
                       "`common/currency.py` and `test_currency.py` stay untouched — including its "
                       "now-stale forward pointer saying this constant 'is None and T3 owns "
                       "authoring it', which is left for its owning track to correct rather than "
                       "edited here.",
    ),
    SoundRule(
        id="apply-seam-coverage-floors",
        entry="apply-seam per-option-kind coverage floors",
        type=AUTHORED_SCAFFOLD,
        fact="how much parity evidence an option kind needs before it is trusted",
        reason="The floors turn a thin parity fixture into a BUILD FAILURE rather than a silent gap "
               "— the exposure accepted when the engine route was declined (ADR-0098 "
               "decision 3). A floor is authored because there is no principled derivation of 'enough "
               "evidence' yet.",
        reconciliation="Reviewed post-POC as the option-kind table grows; a floor that never fails "
                       "is as uninformative as one that always does.",
    ),
    SoundRule(
        id="composer-budget-caps",
        entry="`composer.BEAM_WIDTH` / `composer.SEQUENCE_DEPTH` / `composer.EPSILON` "
              "(+ `board_expectation.BRANCH_CAP`, declared here rather than three times)",
        type=AUTHORED_SCAFFOLD,
        fact="how much of the sequence tree one decision may explore",
        reason="Structural search caps, not tuned strategy: they bound WHAT IS EXPLORED, never what "
               "a candidate is worth, and every one of them reports its truncation rather than "
               "capping in silence (`ComposerResult.stats`, `Expectation.truncated`). Owed by "
               "Issue #385, which builds the composer and is therefore the first issue for which a "
               "budget cap exists to be spent — `board_expectation`'s header and `board_choice`'s "
               "both state the debt and name this entry. "
               "THREE usages, not two, and the third is a REUSE rather than a new number: "
               "(1) the beam's own width / depth / epsilon; "
               "(2) `board_expectation.BRANCH_CAP` = 12, the expectation-branch cap on a CHANCE "
               "node; and (3) that same `BRANCH_CAP`, read by `board_choice.deferred_target` as the "
               "Target-Ranker top-`m` on a CHOICE node. A choice node and a chance node cost the "
               "same thing — leaf evaluations on one option — so they take the same cap, and a "
               "second constant for one fact is exactly the drift this whitelist exists to prevent. "
               "Derived from the two measurements already on the record rather than guessed: "
               "post-Option-Equivalence menu width P50 6 / P95 12 / max 23 and leaf P95 6.57 ms "
               "(Issue #291 §3a, over the 372 corpus frames both gates replay), against the "
               "grader's per-decision FLOOR of >= 3.0 s (2 vCPU x ~10 min per player per match, "
               "P95 137 / max 198 decisions per match over the 377 committed native traces). "
               "A full run costs at most (1 + 3 x 4) x 12 = 156 leaf evaluations ~ 1.03 s, i.e. "
               "~34% of that floor — then MEASURED end to end at those caps, on an idle box: "
               "per-decision median 24.8-26.5 ms, P95 0.40-0.43 s, max 1.31-1.40 s, so the max sits "
               "at ~44-47% of the floor and the bound holds. The measurement CORRECTED the bound's "
               "form in one respect: the arithmetic is quoted at the P95 width and therefore bounds "
               "the P95 decision, not the max one — corpus-wide leaf evaluations are 3515 and the "
               "widest frame costs 323 against the 156 that form predicts, while the same formula "
               "at the observed MAX width gets it right ((1 + 3 x 4) x 27 = 351). Quote both widths "
               "or neither. The cost is leaf-bound and not beam-bound (~100% of the widest frame is "
               "inside `state_value`), and re-sizing was measured rather than assumed: k in "
               "{2,3,4} x depth in {2,3,4} does not move the corpus max outside noise, since leaf "
               "evaluations SATURATE at depth 2. Shrinking a cap that does not move the metric "
               "would be a constant changed to look responsive, so the caps stand as derived. "
               "The width is a TIME budget and not an acceptance-COVERAGE one, and the two readings "
               "disagree: the human-ruled first step lands at rank P50 2 / P90 6 / P95 7 over the "
               "361 gradeable frames, so k=4 reaches 81.7% of them (k=5 88.1%, k=6 93.6%). Acceptance "
               "frame f82's ruled step sits at rank 5 and is therefore OUT of the hard top-k; it is "
               "reported rather than widened around, per Issue #385 §S12.2's *a near-miss re-sizes "
               "from the measurement, it does not get widened until it passes*. "
               "⚠️ Wall-clock is only meaningful on an IDLE machine: a first pass taken while a "
               "full pytest run was in flight read max 2.45-4.05 s and raised a false "
               "crosses-the-grader-floor alarm that an independent re-measurement refuted. The "
               "leaf-eval count is identical under load and idle, so cross-check against it before "
               "believing a millisecond figure. See `composer.BEAM_WIDTH`'s own note for the "
               "machine. Anchored on the WIDTH half deliberately, for the reason `BRANCH_CAP` "
               "records: the width is exactly 12 on every run while the millisecond half moves "
               "~10% run-to-run and ~45% between boxes, so a cap keyed to a wall-clock figure is a "
               "property of whoever ran it last. EPSILON is not authored at all — it is "
               "`family_diag.DECIDER_FLOOR`, the corpus-calibrated threshold below which a family "
               "cannot be any frame's decider, carried under its own name because `tools/` must "
               "never be a `src/` dependency and asserted equal by test. It is SWEPT rather than "
               "assumed (`composer_lab.py --epsilon-sweep`); the sweep now MOVES (three plateaus "
               "over {0.0 ... 0.1}) where before deferred-target expansion it did not move at all, "
               "which was a symptom — every option priced exactly 0.0, so nothing could be NEAR a "
               "tie. The reading is recorded on the constant.",
        reconciliation="Issue #496's opt-in depth-wide exact-dedup replay was rejected for production: "
                       "383-frame P50/P95/max = 0.328/4.559/59.867 s, so P95 exceeded both this "
                       "rule's committed 0.40-0.43 s ceiling and the 3 s grader floor. Neither the "
                       "ceiling nor the constants were raised; exact dedup and continuation remain "
                       "disabled by default pending developer review. "
                       "Re-measured on GRADER hardware post-POC (Issue #273, POC-B3) — the figures "
                       "above are a DEV-MACHINE number and Issue #291 §3a says so in as many "
                       "words. The derived per-decision P95 it rests on is additionally a LOWER "
                       "BOUND on the leaf half alone; the apply-seam transition cost joined the "
                       "measurable set only at Issue #382 and the composer's own wall-clock is "
                       "reported by `tools/train/composer_lab.py`. Re-fit when both halves are "
                       "measured on the grader.",
    ),
    # ── composed-into-the-leaf ────────────────────────────────────────────────────────────────────
    # Listed, not deleted: losing decider status is not licence to delete the math.
    SoundRule(
        id="attach-value-composed",
        entry="`attach_value` (ADR-0069)",
        type=COMPOSED_INTO_THE_LEAF,
        fact="the marginal value of attaching an Energy",
        reason="Its axes-sum shape is ratified and stays ratified; what changes is its ROLE. Under "
               "1-ply differencing the ordering comes from `state_value(after) − state_value(before)` "
               "for every option uniformly, so a per-seam equation that also ordered would be a "
               "second opinion on the same question. The math survives as leaf internals, and "
               "optionally as a pruning approximation.",
        composed_into="readiness",
    ),
    SoundRule(
        id="evolve-value-composed",
        entry="`evolve_value` (ADR-0070)",
        type=COMPOSED_INTO_THE_LEAF,
        fact="the marginal value of evolving a body",
        reason="Same role change. Its body-substituted delta-in-damage IS how the readiness family "
               "prices a body swap, so deleting it would delete the only worked derivation of that "
               "delta and leave T2 re-deriving it from nothing.",
        composed_into="readiness",
    ),
    SoundRule(
        id="promote-retreat-value-composed",
        # "ADR-0073" now resolves to the fetch ADR — PR #267 renumbered this half to 0100.
        entry="`promote_retreat_value` (Issue #141; ADR-0100, was ADR-0073 before PR #267)",
        type=COMPOSED_INTO_THE_LEAF,
        fact="the marginal value of changing who is Active",
        reason="Same role change. The sub-lethal residual it computes is a survival/threat reading "
               "the leaf needs whether or not anything still orders by it.",
        composed_into="survival",
    ),
    SoundRule(
        id="deploy-value-composed",
        entry="`deploy_value` (ADR-0086)",
        type=COMPOSED_INTO_THE_LEAF,
        fact="the marginal value of putting a body into play",
        reason="Same role change, and the one with the sharpest deletion hazard: ADR-0096 already "
               "deleted `keep-a-bench` off this list, so a reader could reasonably conclude the "
               "whole Bench-pricing story was purged. It was not — the bench slot priced as a "
               "scarce resource is exactly this equation, and it becomes development-family math.",
        composed_into="development",
    ),
)

BY_ID = {r.id: r for r in WHITELIST}


def validate(rules: Sequence[SoundRule] = WHITELIST) -> list[str]:
    """Every way an entry fails the typing discipline, as readable problems. Empty is the contract."""
    problems: list[str] = []
    seen: set[str] = set()
    for r in rules:
        if r.id in seen:
            problems.append(f"{r.id}: duplicate id")
        seen.add(r.id)
        if r.type not in TYPES:
            problems.append(f"{r.id}: type {r.type!r} is not one of {sorted(TYPES)}")
        if not r.fact.strip():
            problems.append(f"{r.id}: names no board fact — cannot be checked for double-counting")
        if not r.reason.strip():
            problems.append(f"{r.id}: gives no reason for surviving the purge")
        if r.type == PROVISIONAL and not r.retirement_test.strip():
            problems.append(f"{r.id}: provisional entries MUST carry a dated retirement test")
        if r.type == AUTHORED_SCAFFOLD and not r.reconciliation.strip():
            problems.append(f"{r.id}: authored-scaffold entries MUST carry a reconciliation note")
        if r.type == COMPOSED_INTO_THE_LEAF and not r.composed_into.strip():
            problems.append(f"{r.id}: composed-into-the-leaf entries MUST name the state_value term "
                            f"family that absorbs them — an unnamed destination is how a "
                            f"no-longer-deciding equation gets deleted by the next track")
        if r.type != COMPOSED_INTO_THE_LEAF and r.composed_into.strip():
            problems.append(f"{r.id}: only composed-into-the-leaf entries name a destination term "
                            f"family — this one still decides something")
        if r.type == STRUCTURAL and (r.retirement_test.strip() or r.reconciliation.strip()):
            problems.append(f"{r.id}: structural entries are permanent — a retirement test or "
                            f"reconciliation here means the type is wrong")
    return problems


#: The one fact guarded twice on purpose: `empty-bench-filter` retires INTO `predicted-loss`.
#: Both share one ``fact`` string deliberately — differentiating them makes the detector vacuous.
SCHEDULED_PAIRS: tuple[tuple[str, ...], ...] = (
    ("empty-bench-filter", "predicted-loss"),
)


def deciders(rules: Sequence[SoundRule] = WHITELIST) -> tuple[SoundRule, ...]:
    """The entries that still DECIDE at runtime — the one-guard-per-fact rule's population."""
    return tuple(r for r in rules if r.type in DECIDER_TYPES)


def composed(rules: Sequence[SoundRule] = WHITELIST) -> tuple[SoundRule, ...]:
    """The per-seam equations that survive as `state_value` term-family math rather than as rules."""
    return tuple(r for r in rules if r.type == COMPOSED_INTO_THE_LEAF)


def facts_guarded() -> dict:
    """``{fact: [rule ids]}`` — the DECIDER half of the whitelist read as a coverage map."""
    out: dict = {}
    for r in deciders():
        out.setdefault(r.fact, []).append(r.id)
    return out


def undeclared_double_guarding() -> dict:
    """``{fact: [rule ids]}`` for every fact guarded by more than one DECIDER outside
    :data:`SCHEDULED_PAIRS`. Empty is the contract."""
    declared = {frozenset(p) for p in SCHEDULED_PAIRS}
    return {fact: ids for fact, ids in facts_guarded().items()
            if len(ids) > 1 and frozenset(ids) not in declared}


__all__: Sequence[str] = (
    "STRUCTURAL", "PROVISIONAL", "AUTHORED_SCAFFOLD", "COMPOSED_INTO_THE_LEAF", "TYPES",
    "DECIDER_TYPES", "SoundRule", "WHITELIST", "BY_ID", "SCHEDULED_PAIRS", "validate", "deciders",
    "composed", "facts_guarded", "undeclared_double_guarding",
)
