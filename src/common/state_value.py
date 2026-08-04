"""**State Value** — the ONE prize-denominated scalar for a board (POC-T3, contract frozen by
POC-T0 / Issue #259, ADR-0092).

`state_value(model)` answers *what is this position worth, in prizes?* Every play is then priced by
**differencing** it — `value(play) = state_value(after) − state_value(before)` — with `after`
produced closed-form by `common.apply_option`. One mechanism replaces ~60 hypothesis rungs.

**IMPLEMENTED by T3 (Issue #262).** T0 (Issue #259) shipped the registry, the signatures and the
docstrings; this module now carries the equations. Nothing here invents math: every family is a
composition of an already-FIRING equation, and where a coverage gap remains it is NAMED in
:attr:`TermFamily.blind_to` rather than priced at a silent zero:

    prize_race    `StateModel.prize_race`
    survival      `theirs.turns_to_ko_me` (Bench-Harvest kwargs threaded) + `grading.halve`
    threat        `needs.opponent_target_value` + `needs.phase_scale`
    readiness     `mine.readiness_p` + `mine.turns_to_afford`, the forward leg discounted by
                  `theirs.turns_to_ko_me` through the same `grading.halve` `survival` grades with,
                  all at `planner._READINESS_ATTACK_W`'s band
    hand          `needs.assignment_split` — `set_keep_v2`'s own `_keep_slot_dp`, read as its two
                  halves rather than as the set marginal, so `coverage` and `re_access` arrive
                  separately the way the frozen composition asks for them
    development   `currency.deploy_relevance_to_damage` (the deploy marginal's own bridge) and
                  `EvolveBody.p_arrive`'s `halve(hops)` grading

**`development` composes those two BRIDGES, not `deploy_value()` and `evolve_value()` themselves**,
and the distinction is stated rather than glossed because the issue's one-line summary reads the
other way. Both functions answer a MARGINAL question — *what would adding, or evolving, this be
worth* — and take inputs a board does not carry (a capacity-bounded Needs assignment, ability odds,
`this_turn` damage). Summing marginals over bodies already in play would answer a different question
from the one a STATE valuation asks, and would double-count against `readiness` besides. What
transfers intact is their currency and their decay convention, which is what keeps this family and
those deciders from forming different opinions about the same body. Recorded as a deviation for the
wave packet, not filed as equivalent.

## Unit basis

Prizes. Damage crosses on `currency.PRIZE_DAMAGE_RATE` (DERIVED — the median HP-per-prize over the
card set, recomputed from the CSV by `test_currency.py`). Worth crosses ONLY on
:data:`POC_WORTH_PRIZE_RATE`, the authored scaffold below.

**One prize == `KO_SCORE` in the incumbent leaf's units.** The planner's leaf multiplies this
scalar by `KO_SCORE` to keep speaking the axis its other rungs and its `>= KO_SCORE` win veto are
written on (`strategy/planner.py`). That is not a fudge factor: `_leaf_value`'s dominant term was
already literally `KO_SCORE * prizes`, so the conversion is the identity the old composition was
built around, and it is why the `_LINE_CAP` band transfers unchanged (below).

## Two bands, and why a fact belongs to one of them

`ko-score-band` (`sound_rules.py`, `structural`) says a prize is never outbid by a positional term.
So the families split:

* **Prize-denominated** — `prize_race` and `survival`. These forecast REAL prize flow (the count
  itself; bodies of mine that will fall on THEIR clock, needing no action of mine), so they are
  UNCAPPED: bounding them would make "they knock out my 3-prize wincon next turn" score the same as
  "they knock out a 1-prize Basic", which is the discrimination the whole scalar exists to provide,
  and would price a heal — the family that motivated differencing in the first place — at ~0.
* **Positional** — `threat`, `readiness`, `hand`, `development`. These price the board's shape
  rather than a prize. Each crosses into the positional zone on a shipped SCALE anchor
  (`_READINESS_W` off `planner._READINESS_ATTACK_W`; `_DEPLOY_PRIZE_BAND` off `currency.DEPLOY_BAND`;
  `POC_WORTH_PRIZE_RATE` for the hand) and is then bounded by a RUNAWAY GUARD that must not bite in
  normal play. The constants block explains why the incumbent leaf's total caps could not simply be
  transcribed: at honest prize scale they saturate, and a saturated term has zero derivative, which
  under 1-ply differencing prunes every play that touches it.

`threat` sits on the positional side and `survival` does not. That asymmetry is deliberate:
converting their exposure into a prize takes an ATTACK, and `attack_ev` prices that attack at the
terminal action, so crediting the full prize on the board as well would pay twice for one Knock Out
— and `score(sequence) = state_value(end board) + EV(terminal)` sums the two, which makes the double
count structural rather than occasional. Their exposure is still worth something standing (it
constrains what they can afford to leave in front), and that is what the capped term keeps. The
incumbent leaf drew the same line with the same numbers: `_predicted_loss` at −`KO_SCORE` against
`threat_removed` scaled by 0.1 and capped at 100.

:data:`LOSS_PRIZES` then sits above BOTH, DERIVED from the rulebook maxima rather than authored, so
the terminal `_predicted_loss` dominance the incumbent −`KO_SCORE` rung had is preserved by
construction instead of by a hopeful constant. :data:`WIN_PRIZES` is its mirror on the other side —
the planner's terminal verdict for an ACHIEVED win — and it was added late (Issue #362) for exactly
the reason the loss side was derived in the first place: the leaf's transcribed win magnitude stopped
dominating the moment two families went uncapped, and nothing re-checked the comparison.

## Old Issue #145's five amendments, each with its disposition

Issue #262 carries them forward by name ("its amendments A-E carry over"), so each is answered here
rather than left for a reader to check off:

* **A — incremental leaf evaluation.** Met as memo-per-model; see :func:`state_value`, which records
  why cross-model deltas are not the POC's answer.
* **B — attack value is a random variable.** Met by :func:`attack_ev`: `ko_probability` carries the
  residual uncertainty, so a coin attack is the same equation rather than an archetype branch.
* **C — shared term basis, weights never gate a term's existence.** Met by construction: all six
  families are evaluated for every board and every deck, and a structurally inapplicable one reaches
  zero through its own inputs (no forward form -> `evolve_marginal` 0) rather than through an `if`.
* **D — deterministic tie-breaks.** NOT this track's, and deliberately: Issue #262's fourth
  amendment moved the rule to Issue #263, leaving T3 only `state_value`'s own bit-identical
  determinism, which the purity test asserts.
* **E — phase/regime-bucketed weight sets.** NOT BUILT, and this is the one to argue with. E asks for
  separate weight sets keyed on prizes-remaining and a race/interaction classifier, explicitly
  scoping the real version to "Phase 4" — the learning phases (Issues #146-#148) ADR-0092 cut from
  the POC. What exists instead is the single regime scalar already shipped: `needs.phase_scale`,
  read by `threat` through `opponent_target_value`, which is keyed on exactly E's cheap
  discriminator (the opponent's prize proximity). So the POC has E's *discriminator* and none of its
  *bucketing*. Recorded as a gap rather than claimed as met.

## The double-counting rule

**Every board fact enters through exactly ONE term family.** :data:`REGISTRY` records which, and —
just as load-bearing — what each family deliberately does NOT read. A play that changes state and
that no family prices comes out at 0, and a silent 0 is indistinguishable from a correct 0 unless
the gap is NAMED. So a coverage gap is a T3/T4 defect with an address, not a mystery.

The rule is enforced by test, not by convention: `test_state_value.py` asserts the `reads` sets are
pairwise disjoint and that every `does_not_read` entry is claimed by some other family.

## What this CANNOT price, by construction

Information ordering. Playing an informative card before a committing one versus after reaches the
**same end state**, so no function of the end state can separate them — see
`apply_option`'s own note and ADR-0095 decision 3. Information-first sequencing therefore stays
a structural rule on the whitelist (`_finish_turn_last`'s information-before-commitment boundary),
and is not a gap in this registry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Iterable, Mapping, NamedTuple, Sequence

from common import currency, needs as _needs
from common.card_worth import ROLE_TIER
from common.grading import HORIZON, halve
from common.strategy.context import _BENCH_MAX

if TYPE_CHECKING:                      # the seam, expressed without importing the Pilot's world at
    from common.state_model import StateModel   # runtime — `deploy_value`'s "no engine, no obs" rule

#: **The Worth -> prize scaffold** (ADR-0097, ratified wave 1). Damage-per-worth-point is the
#: bridge `common/currency.py` deliberately does NOT hold: the anchor gate was RUN and FAILED twice
#: (ADR-0080 for deny, ADR-0086 for deploy), so the constant is absent there BY DESIGN, not pending.
#:
#: **AUTHORED, NOT DERIVED.** It is module-local on purpose and must never migrate into
#: `common/currency.py` — that module's contract is "DERIVED and never tuned", and this is the
#: opposite. `test_currency.py` stays untouched; ADR-0080's measurement remains the historical record
#: of what was true.
#:
#: **Why it is needed now when it was not before.** ADR-0086's underivability argument was
#: *structural*: "a deploy is never exclusive with a damage-denominated option ... so it cannot TRADE
#: against one". Under differencing that premise is VOID. `state_value(after) − state_value(before)`
#: puts the card in `hand` (Worth-denominated) on one side and on the board (`readiness` /
#: `development`, prize-denominated) on the other, so the Worth does NOT cancel — on every play that
#: spends a card. The corpus consequently begins generating anchors (every ruled spend-vs-hold frame)
#: that the old architecture structurally could not produce.
#:
#: **Reconciliation, recorded rather than hidden** (ADR-0097 decision 1). Converted to
#: damage-per-worth-point this must be stated against the three rates already catalogued in
#: `currency.py`, which disagree by ~6.7x among themselves:
#:
#:     trainer   TAG_TIER["gust"] 10.0  vs  ITEM_HOLD_WORTH_RATE 1.0   ~1.0
#:     energy    ENERGY_TIER      8.0   vs  ENERGY_RECOVER  160/3      ~6.7
#:     deploy    DEPLOY_BAND / DEPLOY_WORTH_SCALE = 25/30              ~0.83
#:
#: A value landing far outside that spread is evidence about the INCUMBENTS as much as about this
#: constant — ADR-0078's own rule. Whitelisted `authored-scaffold`; retires when a post-POC fit
#: against ruled spend-vs-hold frames converges.
#:
#: **The value itself is T3's** (Issue #262), authored with its reasoning recorded below.
#:
#: **AUTHORED at 1/120 prizes per Worth point** — i.e. 0.8333 damage per Worth point once multiplied
#: back through `PRIZE_DAMAGE_RATE`. ADR-0097 decision 1 requires that number to be stated against
#: the incumbents rather than dropped in beside them. The catalogue has grown to FOUR since that
#: decision was written (POC-T2 items 2f and 2g landed two of them), so all four are stated:
#:
#:     worth <-> damage
#:     deploy    DEPLOY_BAND / DEPLOY_WORTH_SCALE = 25/30      0.833 dmg/worth   <- ANCHOR
#:     trainer   currency.ITEM_HOLD_WORTH_RATE                 1.0               agrees within 20%
#:     energy    ENERGY_TIER 8.0 vs ENERGY_RECOVER 160/3        6.67             DISAGREES ~8x
#:
#:     prize <-> worth  (the SAME pair this constant crosses — directly comparable, no bridge)
#:     gust      currency.GUST_TARGET_WORTH_RATE   2.564 worth/prize    vs THIS 120  DISAGREES ~47x
#:
#: The trainer row used to read `_DENIAL_ITEM_COST 10` against `TAG_TIER["gust"] 10.0`. That constant
#: is DELETED (Issue #261 item 2f): the ~1.0 it implied is now the explicit, seam-scoped
#: `currency.ITEM_HOLD_WORTH_RATE`. Same number, strictly better evidenced — and it composes with
#: `PRIZE_DAMAGE_RATE` into a second same-pair reading, 100 worth per prize, which this constant's
#: 120 sits inside 20% of.
#:
#: ⚠️ **The gust row is the one `currency.py` asks this constant to SETTLE, and it settles by
#: REFERENT rather than by moving either number.** `GUST_TARGET_WORTH_RATE` converts a
#: prize-equivalent INTO Worth so an opponent-target slot can be ranked inside a Worth-denominated DP
#: against other slots; this constant converts a HELD CARD's Worth into prizes so spending it can be
#: priced against a board. Same pair, opposite directions, different referents — the resolution the
#: energy outlier below already got. The reductio settles which is which: at the gust seam's rate a
#: held `ROLE_TIER["win_condition"]` would price at **11.7 prizes**, nearly twice the six that END
#: the match, whereas here it is 0.25. So the ~47x is not a constant awaiting a split; it is evidence
#: that Worth is an ORDINAL priority scale INSIDE an assignment rather than a quantity globally
#: exchangeable with prizes — which is `currency.py`'s own reading of it ("that scale's whole range
#: is 0-30 by construction ... Pricing the hand ON ITS OWN SCALE is what the DP is for"). Averaging
#: the two would break both seams at once and would manufacture exactly the general Worth Damage Rate
#: ADR-0080 ran a gate to establish does not exist.
#:
#: The deploy rate is the anchor for two reasons, both stated rather than assumed. It is the only
#: one `currency.py` *labels* a worth↔damage rate ("Stated plainly rather than buried … It IS a
#: worth↔damage rate, scoped to one seam") and the only one carrying an explicit reconciliation
#: debt, which adopting it here discharges in the direction of evidence. And the trainer rate — an
#: independent seam, derived from a different pair of constants — lands within 20% of it, so two of
#: the three catalogued rates already agree to within the precision an authored POC scaffold can
#: honestly claim.
#:
#: **The energy outlier is recorded, not smoothed.** ADR-0078's rule is that a disagreement is
#: evidence about ONE of the two, so: `ENERGY_TIER` (8.0) prices an Energy CARD sitting in hand,
#: while `ENERGY_RECOVER` (160/3) prices a unit of Energy already ATTACHED and recovered onto a
#: body — the median damage-per-Energy over the 305 multi-Energy attacks in the set. Those are two
#: different objects (a card I might play vs. fuel already burning), and a card in hand is worth
#: less than the attached unit it might become, so the ~8x gap is at least partly a real
#: difference in referent rather than a contradiction. Adopting the energy rate here would price a
#: single held Basic Energy at 0.53 prizes — more than half a Knock Out for one card — which the
#: corpus would have to fight on every attach frame.
#:
#: Sanity, since an authored constant should be sanity-checkable in one line: a held wincon
#: (`ROLE_TIER["win_condition"]` 30.0) prices at 0.25 prizes, and a held typed Basic Energy
#: (`ENERGY_TIER` 8.0) at 0.067.
#:
#: **Retirement test (ADR-0097 decision 2), pre-registered here:** post-POC, fit this rate against
#: the ruled spend-vs-hold frames the differencing architecture now generates; retire the authored
#: value iff the fit converges. **ADR-0097 decision 3:** ADR-0080/0086's underivability finding is
#: recorded VOID — its premise (a deploy can never trade against a damage-denominated option) does
#: not survive differencing, because `state_value(after) − state_value(before)` puts the card in
#: `hand` on one side and on the board on the other, so the Worth does not cancel.
#:
#: `tests/strategy/test_state_value.py` asserts the arithmetic above rather than the literal, so
#: the anchor cannot drift silently if `currency.py` re-derives one of its constants.
#: **A LITERAL, not a live expression.** Computing it from `currency.DEPLOY_BAND /
#: DEPLOY_WORTH_SCALE / PRIZE_DAMAGE_RATE` was tried and reverted: it would make an *authored*
#: scaffold silently track three DERIVED constants, so a `currency.py` re-derivation would move this
#: number with no ruling and no note — the exact opposite of module-local and authored. The anchor is
#: still enforced, but by a TEST that fails loudly rather than by an expression that adjusts quietly
#: (`test_state_value.py::test_the_worth_scaffold_is_reconciled_against_its_anchor_...`), which is
#: `test_currency.py`'s own discipline pointed the other way.
POC_WORTH_PRIZE_RATE: float | None = 1.0 / 120.0

# ── the positional band ───────────────────────────────────────────────────────────────────────────
#
# **What `ko-score-band` actually requires, stated before the constants that serve it.** The rule is
# that a positional term never outbids a prize. In a DIFFERENCING architecture the quantity that can
# outbid anything is a DELTA, not a level: every absolute positional value appears on both sides of
# `state_value(after) - state_value(before)` and cancels. So the binding constraint is *no single
# play may move the positional families by a prize*, which per-body and per-play bounds enforce and a
# family TOTAL cap does not.
#
# That distinction is why the incumbent leaf's total caps are not all carried over verbatim. Carried
# at their old numbers against honest prize-denominated inputs they SATURATE — a 210-damage wincon
# prices at 2.1 prizes of raw payoff against a 0.12 per-body cap — and a saturated term has zero
# derivative, which under 1-ply differencing means every attach, deploy and evolve onto that body
# prices at exactly 0 delta and is never explored. Pruning-by-saturation is the same failure the
# ordering ruling exists to prevent, arriving through a cap instead of through a missing equation.
#
# So each band below is stated with the job it does: a SCALE anchor (what converts the shipped
# equation's units into the positional zone, per old Issue #145's currency-zone rule — replace at
# the same band, never stack) or a RUNAWAY GUARD (a bound that must not bite in normal play).

#: **Scale anchor for `readiness`.** `planner._READINESS_ATTACK_W` (0.45) is the shipped conversion
#: from a body's reachable damage into readiness score; re-expressed at 1 prize == `KO_SCORE` against
#: a payoff already divided by `PRIZE_DAMAGE_RATE` it is `0.45 * 100 / 1000`. Carried at the same
#: band rather than re-derived, so this swap moves no readiness magnitude.
#:
#: It is also the term's MEANING, not merely its size: readiness prices POTENTIAL. The prize for
#: actually swinging belongs to `attack_ev` at the terminal action, so pricing a body's full swing
#: here would pay for one Knock Out twice — the same double-count the `threat` cap prevents on the
#: other side of the board. `test_state_value.py` asserts this against `planner._READINESS_ATTACK_W`
#: (importing the planner HERE would be a cycle: the planner's leaf imports this module).
_READINESS_W = 0.045
#: `planner._READINESS_BODY_CAP` 120 / `KO_SCORE` — a RUNAWAY GUARD. With `_READINESS_W` applied the
#: biggest body in the set lands near 0.095, so this bounds a single body's readiness swing under a
#: prize without biting.
_READINESS_BODY_CAP = 0.12
#: `planner._READINESS_CAP` 300 / `KO_SCORE` — the whole board's readiness. Runaway guard.
_READINESS_CAP = 0.3
#: `planner._PLANNER_THREAT_CAP` 100 / `KO_SCORE`, and it carries the same meaning it always had:
#: their exposure is a standing POSITION, and the prize for actually converting it is `attack_ev`'s
#: at the terminal action. See :func:`threat` for why the my-side/their-side asymmetry is real.
#:
#: A RUNAWAY GUARD, like its three positional siblings, and since Issue #329 it behaves like one: with
#: :data:`_THREAT_W` in front of it the guard bites on **45 of 614** non-empty corpus inputs (7.3%)
#: rather than on 100%. It bites at all because `threat` sums over up to six targets while the anchor's
#: divisor is ONE target's ceiling — 5 prizes of simultaneously-reachable exposure is exactly the
#: extreme board a runaway guard is for. **Do not fold the anchor into this number.**
#: :data:`POSITIONAL_MAX` sums the four positional caps and :data:`LOSS_PRIZES` is derived from that
#: sum, so shrinking `_THREAT_CAP` would silently move the predicted-loss dominance constant.
_THREAT_CAP = 0.1
#: **`threat`'s scale anchor — DERIVED, not authored** (Issue #329, ADR-0107's form applied to the
#: third member of the opponent-target family).
#:
#: T3 ported the incumbent rung `min(_PLANNER_THREAT_CAP, _PLANNER_THREAT_W * threat_removed)`, whose
#: input is a printed attack's DAMAGE and whose weight is 0.1 *per damage point* — so its guard bit
#: only past 1000 damage. The port re-denominated the input into PRIZES and carried the cap across
#: **without the weight**, leaving `threat` the one positional family with a runaway guard and no
#: scale anchor. Measured consequence, over one full leaf pass (2061 calls, 614 non-empty): 33
#: distinct input sums collapsed to exactly 2 distinct outputs.
#:
#: Both operands are already-shipped constants, so this adds no scaffold debt. The divisor is
#: `needs.TARGET_VALUE_CEILING` (3.9 = `MAX_PRIZE_VALUE` 3 + `_SURVIVAL_CAP` 0.9), the true ceiling of
#: `opponent_target_value` *as a function* and ADR-0107's own choice for the sibling `gust_target`
#: seam. Measured against the alternative `_MAX_PRIZE_VALUE` (3.0) on the same 614 inputs: 3.9 yields
#: **28** distinct outputs with the guard biting 45 times, 3.0 yields 26 with it biting 180 times.
_THREAT_W = _THREAT_CAP / _needs.TARGET_VALUE_CEILING

#: **The per-body deploy band, in prizes** — `currency.DEPLOY_BAND` (25 damage) across
#: `PRIZE_DAMAGE_RATE`. The ratified ADR-0086 answer to "what is one body on the board worth", reused
#: rather than re-banded, so `development`'s per-body contribution and `deploy_value`'s own output
#: are the same number in two denominations.
_DEPLOY_PRIZE_BAND = currency.DEPLOY_BAND / currency.PRIZE_DAMAGE_RATE

#: The price of the LAST Bench slot, in prizes (Issue #232). Set to :data:`_DEPLOY_PRIZE_BAND` by
#: derivation rather than by taste: the last slot costs exactly what the best possible body is worth,
#: so filling it with a maximum-relevance body is a wash and filling it with a spare Basic is a
#: measured loss. That IS the spare-body cliff Issue #232 describes, priced instead of ruled — the
#: flat +60 `keep-a-bench` rung it replaces read 1.96 on a non-empty Bench against 61.96 on an empty
#: one, and the entire gap was the rung.
_BENCH_SLOT_PRICE = _DEPLOY_PRIZE_BAND

#: `development`'s runaway guard: a full board at the maximum per-body band. Not a tuner — a board
#: of six wincons genuinely is worth more than one prize of position, and saying otherwise would
#: flatten exactly the boards the develop rung has to tell apart.
_DEVELOPMENT_CAP = (_BENCH_MAX + 1) * _DEPLOY_PRIZE_BAND

#: `hand`'s runaway guard, and the incumbent `pilot._HAND_READINESS_CAP` (40 / `KO_SCORE` = 0.04) is
#: deliberately NOT carried over. That cap belonged to `leaf_hand_value`, an armed-OFF experimental
#: term measured as "a wash", at an implicit rate ~16x smaller than the wave-1-ratified
#: :data:`POC_WORTH_PRIZE_RATE`; against this rate it would bite at a Worth of 4.8 — below a single
#: typed Basic Energy — and price every card play at 0 delta. The guard instead says a hand cannot be
#: worth more than a full board of the best bodies, which is a statement about the game rather than
#: about a retired experiment.
_HAND_CAP = _DEVELOPMENT_CAP

#: Prize-proximity weight in :func:`prize_race`. ANCHORED to `needs._PHASE_PRIZE_W` (0.5), the
#: shipped weight for exactly this fact — how much closer-to-your-last-prize sharpens a position —
#: rather than a fresh seed. Sub-prize by construction: the proximity leg is a difference of two
#: `halve` values, so it can move the scalar by at most ±0.5 prizes while the LEAD leg moves by a
#: full prize per prize taken. The lead can therefore never be inverted by the proximity term.
_PROXIMITY_W = 0.5

# ── the terminal band ─────────────────────────────────────────────────────────────────────────────

#: A full Bench plus the Active. Verified at source: *"Each player may have up to 5 Pokemon on the
#: Bench at any one time"* (`docs/rulebook.txt` L75, restated L122); `strategy/context._BENCH_MAX`
#: is the same 5 and is what this reads, so the two cannot drift.
_MAX_BODIES = _BENCH_MAX + 1
#: The biggest prize yield in the set — a Mega Evolution Pokemon ex. Verified at source:
#: `docs/rules.md` §6's prize table (`megaEx` -> 3, `[RULE: L333]`), and `CardStat.prize_value` is
#: the runtime authority that returns it.
_MAX_PRIZE_VALUE = 3.0
#: The Prize count both players race down from. Verified at source: *"Prize cards are 6 cards that
#: each player sets aside"* (`docs/rulebook.txt` L57, and the setup step at L102). Read from
#: `needs` rather than re-declared — one fact, one home (ADR-0087).
_PRIZES_START = _needs._PRIZES_START

#: **A predicted GAME LOSS, in prizes — DERIVED, not authored.**
#:
#: The incumbent rung returned a flat −`KO_SCORE` and relied on the positional band (590 < 1000) to
#: stay dominant. Two of this module's families are prize-denominated and UNCAPPED, so that
#: arithmetic no longer holds and a transcribed −1.0 would be silently outbid by, say, two exposed
#: ex bodies. Rather than authoring a bigger number, the magnitude is computed from the largest sum
#: the other families can express on ANY legal board:
#:
#:     survival    _MAX_BODIES x _MAX_PRIZE_VALUE  — every body of mine, all Mega ex, all doomed
#:     prize_race  _PRIZES_START + _PROXIMITY_W     — the whole race plus its proximity leg
#:     positional  the four caps above
#:
#: plus one strict prize of headroom. `test_state_value.py` asserts the domination directly, so the
#: derivation is checked rather than trusted — which matters because every summand here is a
#: constant somebody could later move.
#: Everything the four positional families can express at once — their runaway guards, summed.
POSITIONAL_MAX = _THREAT_CAP + _READINESS_CAP + _HAND_CAP + _DEVELOPMENT_CAP

LOSS_PRIZES = (
    _MAX_BODIES * _MAX_PRIZE_VALUE
    + _PRIZES_START + _PROXIMITY_W
    + POSITIONAL_MAX
    + 1.0)

#: **An ACHIEVED GAME WIN, in prizes — DERIVED, not authored** (Issue #362). The mirror of
#: :data:`LOSS_PRIZES`, and the one the T3 swap forgot.
#:
#: `planner._engine_leaf_value` short-circuits a coin-free simulated win to a dominant terminal value.
#: Its magnitude was `KO_SCORE * (start_prizes + 1)`, and that term is **prizes still REMAINING when
#: the line began** — `_simulate_line` reads `len(me["prize"])`, the same expression
#: `state_model.prizes_remaining` is ("Prizes this side still needs to take"), never `prizes_taken`.
#: So the old magnitude ran BACKWARDS: it paid a win the most (7000) when six prizes were still to
#: take and the least (1000-2000) when the win was about to land. Against the retired hand-composed
#: leaf even the floor was dominant — the whole positional band summed to 590 against `KO_SCORE`
#: 1000. Against THIS module it is not. `prize_race`'s lead leg has unit slope and is deliberately
#: uncapped, so a merely-WINNING position out-scores a won GAME: measured over the committed corpus,
#: 26 frames reach a coin-free simulated win and on **4** of them a non-winning option scored higher —
#: worst `82749168|1|decision|88`, a won 2000 against a non-win 6789.9, on a frame whose own winning
#: board scores 6.909985 prizes. That worst case is the inversion's signature: one prize remaining is
#: the position closest to victory and drew the second-smallest payout the formula could produce.
#: `tools/train/probes/win_band_sweep.py` re-runs the measurement.
#:
#: Derived the same way its mirror is, from the largest sum the families can express on any legal
#: board, plus one strict prize of headroom:
#:
#:     prize_race  _PRIZES_START + _PROXIMITY_W   — the whole race plus its proximity leg
#:     positional  the four caps above
#:     survival    NOTHING — non-positive by construction, so it can only push a board DOWN
#:
#: Two summands of `LOSS_PRIZES` are therefore absent, and the difference is exactly
#: `_MAX_BODIES x _MAX_PRIZE_VALUE`. That summand exists on the loss side because the terminal charge
#: sits INSIDE `survival` and has to out-dominate that family's own exposure sum; a win REPLACES the
#: whole scalar, so it has nothing of the kind to clear. `test_state_value.py` asserts the domination
#: rather than the literal, and asserts `survival`'s sign rather than arguing it.
#:
#: **The leaf's line account is not in here, and that is the boundary.** `_engine_leaf_value` adds
#: `min(_LINE_CAP, line_val)` OUTSIDE the scalar, so the win has to clear that as well; the prize of
#: headroom covers `_LINE_CAP`'s 0.1 prizes ten times over and `test_planner.py` is where the leaf's
#: own axis is asserted. This module owns the band, the planner owns its axis.
WIN_PRIZES = (
    _PRIZES_START + _PROXIMITY_W
    + POSITIONAL_MAX
    + 1.0)


class ExposedBody(NamedTuple):
    """One of MY bodies as `survival` reads it.

    NAMED rather than a bare ``(float, int)`` because this is a FROZEN contract and T3 implements
    against it months from now: an anonymous pair invites a transposed call that still type-checks,
    still runs, and prices the board wrong in a direction nobody would think to look for."""

    #: Prizes the opponent collects if this body is Knocked Out (`combat.prize_value`).
    prize_at_risk: float
    #: Turns until they can Knock it Out. The grading is `halve(turns_to_ko_me - 1)`, so 1 = now.
    turns_to_ko_me: int


class ReadyBody(NamedTuple):
    """One of MY bodies as `readiness` reads it. Named for the same reason as :class:`ExposedBody`,
    and more urgently — three consecutive floats are trivially transposable."""

    #: What this body achieves once it is online, in prizes.
    payoff: float
    #: Probability it gets there, from the Attach-Budget / readiness-odds machinery. In [0, 1].
    readiness_odds: float
    #: How much this body's role matters to the current plan. In [0, 1].
    role_relevance: float


@dataclass(frozen=True)
class TermFamily:
    """One entry in the coverage map — a family, the facts it prices, and the facts it refuses.

    ``does_not_read`` is not documentation. It is the mechanism that turns a coverage gap into a
    findable defect: a fact appearing in one family's ``does_not_read`` and in no family's ``reads``
    is a hole with an address, which is the difference between "T4 mis-prices this" and "nobody can
    work out why this scores 0"."""

    #: The family's name, and its key in the `working` breakdown.
    name: str
    #: Board facts this family PRICES. Pairwise disjoint across the registry — the double-counting
    #: rule, asserted by test.
    reads: tuple[str, ...]
    #: Facts this family deliberately leaves to another family. Every entry must be some other
    #: family's `reads`, or it names a gap.
    does_not_read: tuple[str, ...]
    #: One line on how the family composes. The frozen semantics; T3 implements against it.
    composition: str
    #: **The blind-spot checklist** (added by T3 for Issue #263's ordering ruling): board dimensions
    #: this family plausibly OUGHT to price and knowingly does not — because no supplier exists yet,
    #: or because the fact is out of the POC's scope. `does_not_read` names facts another family
    #: owns; these are owned by NOBODY, which is a different and more dangerous thing.
    #:
    #: Load-bearing rather than documentation. Under uniform 1-ply differencing a play that moves
    #: only a dimension listed here prices at exactly 0 delta, and at ordering time 0 means *never
    #: explored* — not merely undervalued. Issue #263's composer reads :func:`blind_spots` directly
    #: to tell a genuine zero from an uncovered one, so each entry is written as
    #: ``"dimension — why it is uncovered / who owns closing it"``.
    blind_to: tuple[str, ...] = ()


#: **The coverage map.** The 2026-07-31 value-stack audit's Board-signal map is the checklist this
#: was built against; the six families are ADR-0092 §4-T0's.
REGISTRY: tuple[TermFamily, ...] = (
    TermFamily(
        name="prize_race",
        reads=("my_prizes_remaining", "their_prizes_remaining"),
        does_not_read=("prize_at_risk", "opponent_target_value"),
        composition="Lead plus proximity over the two prize counts. The RACE only — what a body is "
                    "worth when it falls is `survival` (mine) or `threat` (theirs), so the prize "
                    "VALUES of individual bodies are deliberately absent here. One reader arrives "
                    "from the other side and must not mistake it for a breach: `survival`'s "
                    "terminal `_predicted_loss` ALSO reads `their_prizes_remaining`, as a "
                    "win-condition TEST rather than as race value (ADR-0064 Amendment B, Issue "
                    "#283). Lead-and-proximity stays this family's alone.",
        blind_to=(
            "deck_count / deck-out proximity — win condition 3 (`docs/rules.md` §7) is a second "
            "race and no family reads either side's deck count. A mill or a heavy-draw line moves "
            "it and prices 0. Owned post-POC; the corpus has no deck-out frames.",
            "turn number / who went first — the tempo half of a race. `model.turn` exists; no "
            "family reads it, so a line that trades a turn for position prices the trade at 0.",
        ),
    ),
    TermFamily(
        name="survival",
        reads=("prize_at_risk", "turns_to_ko_me", "bench_harvest", "predicted_loss"),
        does_not_read=("my_prizes_remaining", "readiness_odds"),
        composition="Sum over MY bodies, both areas, of prize_at_risk x halve(turns_to_ko_me - 1), "
                    "Bench-Harvest-aware. Both of this family's damage reads — the "
                    "`turns_to_ko_me` clock and `_predicted_loss`'s Incoming — are taken at "
                    "`damage_context(attacker='theirs')`, so a scaling attack of theirs prices its "
                    "actual damage rather than its printed 0 (Issue #280); the direction is the "
                    "attacker's, and on a survival read the attacker is them. "
                    "`_predicted_loss` (ADR-0064) survives here as a TERMINAL "
                    "term at `LOSS_PRIZES`, outside the positional band by construction. The band "
                    "is the SUM of the positional caps (readiness 300 + survival 50 + threat 100 + "
                    "value 40 + line 100 = 590) against KO_SCORE 1000, of which `_LINE_CAP` is the "
                    "line term's 100 (`strategy/planner.py`) — a loss-avoidance value cannot be "
                    "both bounded under that band AND un-outbiddable, so it is neither. That "
                    "terminal term prices BOTH loss conditions of `docs/rules.md` §7 a next-turn "
                    "Knock Out can reach (ADR-0064 Amendment B, Issue #283): case 2, no Pokémon in "
                    "play to promote, and case 1, the Knock Out takes their LAST prize. "
                    "**Case 1 consults `their_prizes_remaining`, and that is not a disjointness "
                    "breach**, which is stated here because it is the first thing a reader of the "
                    "tuples will suspect. It is consulted as a WIN-CONDITION TEST and never as race "
                    "value: does THIS body's prize yield cover what they still need? Lead and "
                    "proximity stay `prize_race`'s alone and this family prices neither. The "
                    "registry fact remains `predicted_loss` — already in `reads` — because what "
                    "enters the scalar is the terminal verdict, not their count; the count is an "
                    "input to that verdict the way `turns_to_ko_me`'s own inputs are. Splitting the "
                    "count into a second fact string to make the read visible was considered and "
                    "rejected: `sound_rules.SCHEDULED_PAIRS` records the same temptation and the "
                    "same answer — a fact renamed to dodge a detector makes the detector pass "
                    "VACUOUSLY. Which is exactly why this paragraph exists instead.",
        blind_to=(
            "the MARGIN below the case-1 win-condition test — a body whose loss hands them 2 of "
            "the 3 prizes they need is worse than the flat exposure above and prices identically "
            "to one that hands them none, so moving a body across that margin is a genuine 0 "
            "delta. BINARY is Issue #283's explicit POC ruling (a terminal term firing on a "
            "non-terminal fact is the worse error), which makes this an OWNED zero rather than an "
            "oversight: the graded form is the named post-POC question and nobody prices it today.",
            "special_conditions — Asleep/Paralyzed/Poisoned/Burned change what survives and what "
            "can act, and `snapshot_coverage` lists the zone as OWED (no snapshot home). Curing a "
            "condition therefore prices 0. Owned by T1 (Issue #260) via the completeness contract.",
            "attached_tools — a defensive Tool's survival contribution (ADR-0028's math) has no "
            "snapshot home either, so equipping one prices 0 at ordering time. Same owner.",
            "healing that does NOT move `turns_to_ko_me` — the clock is integer turns, so a heal "
            "smaller than one turn of incoming is invisible here. Real, accepted at POC bar: the "
            "clock is the shipped survival vocabulary and a sub-turn HP term would be new math.",
        ),
    ),
    TermFamily(
        name="threat",
        reads=("opponent_target_value", "my_reachable_kos", "denied_forward_payoff"),
        does_not_read=("turns_to_ko_me", "their_prizes_remaining"),
        composition="Their exposure to ME: per-body `needs.opponent_target_value` over the Knock "
                    "Outs I can reach, across BOTH seats. The mirror of `survival`, and the reason "
                    "THIS family must not read a clock — `turns_to_ko_me` is THEIR clock on MY "
                    "bodies, which says nothing about how exposed THEIR bodies are to me, so "
                    "reading it here would be a genuine second pricing of `survival`'s fact rather "
                    "than a different consequence of it. (Since Issue #332 `readiness` DOES consult "
                    "the clock, on the forward leg of `readiness_odds`; that is argued at "
                    "`_survives_to_spend` and is a different question from this one. The rule was "
                    "never *at most one family may consult a fact* — it is *at most one family may "
                    "PRICE it*, which is what `reads` records.) "
                    "Reach is one affordability filter (the Attach Budget) over two damage "
                    "ROUTES: their Active through `best_reachable_damage_vs`, the DAMAGE MODEL "
                    "against the body actually in front of me (Weakness, Resistance, prevention, my "
                    "live boosts — Issue #281); their Bench through `best_reachable_bench_damage`, "
                    "the attack's single-target snipe RIDER, which ignores Weakness and Resistance "
                    "by rule and is zeroed on the Active path (Issue #284). What the bench leg "
                    "prices is the STANDING position — chip already on their bench makes a body one "
                    "rider from dead between turns — never the conversion, which stays `attack_ev`'s. "
                    "`prize_advance` then carries the forward payoff the removal DENIES "
                    "(`TheirSide.forward_payoff`, Issue #285), on `development.evolve_marginal`'s own "
                    "`_READINESS_W` / `PRIZE_DAMAGE_RATE` / `halve(hops)` expression — the same "
                    "anchors, because forward payoff is printed damage held as POTENTIAL on either "
                    "side of the board. Not a second reading of `development`, which is MY-side only "
                    "by its own `blind_to`: this prices ONE reachable Knock Out more precisely, from "
                    "card knowledge about that body, and reads nothing about their board.",
        blind_to=(
            "SPREAD riders as a bench route — `benchSpread` is a SHARED counter budget across their "
            "whole Bench (Phantom Dive: *put 6 damage counters on your opponent's Benched Pokémon "
            "in any way you like*), so crediting its full total against each body separately would "
            "claim three Knock Outs from one 60-counter payload. The subset question has an owner "
            "— `CombatMath.spread_ko_prizes`' `best_ko_subset` knapsack — and it answers in PRIZES "
            "over a whole Bench, which does not compose into this family's per-body shape. So the "
            "bench leg reads the indivisible single-target snipe only and UNDER-reads the three "
            "spread attacks in the pool (Flutter Mane 20, Sinistcha 40, Dragapult ex 60). Under-"
            "reading my own damage is the fail-closed direction; no attack in the set prints both "
            "riders, so nothing is double-counted by the split.",
            "a multi-target snipe's COUNT — `AttackStat.benchSnipe` holds the PER-BODY damage and "
            "no multiplicity, so Kyurem's Trifrost (*110 damage to 3 of your opponent's Pokémon*) "
            "and Greninja ex's 2-target rider read as reachable against a fourth and fifth body "
            "they could not actually all fell. An over-read, and unrepresentable as a fix without a "
            "new parsed field. **It was free while the cap bound on every input; since Issue #329's "
            "scale anchor it is not.** A phantom extra target now costs `_THREAT_W` x its "
            "`opponent_target_value` — 0.0256 prizes for a 1-prize body, up to 0.0769 for a Mega ex "
            "— where it previously cost exactly 0, and the corpus carries 2 or 3 targets on 74 of "
            "614 non-empty calls. So this entry moved from harmless to priced, in the OVER-read "
            "direction, and it is the one entry here the anchor made worse rather than better.",
            "the BENCH LEG'S OWN REACH beyond the SNIPE RIDER — narrowed by Issue #284 and no "
            "longer erased by the cap. The old form of this entry recorded a ceiling that Issue "
            "#329 removed: `min(_THREAT_CAP, sum)` bound on every non-empty input, so a second "
            "reachable body added exactly 0 and a chipped bench under a reachable Active scored "
            "identically to a fresh one. **Both figures below are in `threat()` CALLS over one leaf "
            "pass (2061 calls, the leg severed to 0.0 as the control), so they are comparable**; "
            "Issue #284's own 904-ask / 338-reach / 13-move measurement is denominated in corpus "
            "FRAMES and is NOT the same denominator. Under the old equation the leg could only move "
            "the output by making an empty input non-empty, which is **278** calls. Under the "
            "anchor it moves **336**, by 0.023 to 0.077 prizes — and the extra **58** are exactly "
            "the boards where the Active leg ALREADY read something, the case the cap used to erase "
            "(commonest shape 0.0769 -> 0.1, 31 calls). What remains blind is the leg's reach "
            "itself: the route is the indivisible single-target rider, so spread payloads and "
            "un-parsed riders still contribute nothing at all.",
            "THE DENIAL CREDIT'S SIZE relative to the prize leg it rides on (Issue #285) — real, "
            "read, and small. Until Issue #329 it was not merely small but INVISIBLE: every "
            "appended target contributes `prize_advance >= 1.0` (`CombatMath.prize_value` returns "
            "1, 2 or 3 and never less), so `min(_THREAT_CAP, sum)` bound on every frame the loop "
            "touched and the credit could not move the family on ANY board. **Re-measured after the "
            "anchor** (same leaf pass, `_denied_forward_payoff` severed to 0.0 as the control, and "
            "in the same CALL denominator as the entry above): the "
            "credit changes 327 of 614 non-empty inputs and now moves `threat`'s OUTPUT on **296** "
            "of 2061 calls, by **0.000115 to 0.002192** prizes, against **0** calls under the old "
            "equation — a credit can never make an empty input non-empty, so this was the one leg "
            "the cap erased completely rather than partly. "
            "The residual 31 are where the runaway guard "
            "absorbs it — small, not zero, and no longer structural. "
            "**Two credit maxima are recorded in this module and they measure different things; do "
            "not overwrite one with the other.** 0.054 prizes is the largest SINGLE-target credit "
            "on the corrections corpus (Riolu 30 → Mega Lucario ex 270: 0.045 x 240/100 x "
            "halve(1); the doctrine's headline Staryu 20 → Mega Starmie ex 210 is smaller still at "
            "0.043). 0.0855 is the largest TOTAL across every target in ONE `threat()` call, which "
            "only became possible when Issue #284 let the loop append more than one body; at "
            "`_THREAT_W` that is the 0.002192 above. Both are correct at their own seam.",
            "THE PRIZE a denied line would have YIELDED — the credit reads `owed_damage` only, so a "
            "pre-evolution whose forward form is a 3-prize Mega ex and one whose forward form is a "
            "1-prize body of the same printed damage price IDENTICALLY. That is a real gap against "
            "the doctrine's own headline, *\"trade 1 prize for a denied 3\"* — the sentence is about "
            "PRIZES and this term answers in DAMAGE. Re-checked at Issue #329 and it SURVIVES the "
            "scale anchor unchanged, because the anchor scales the whole marginal and adds no leg: "
            "`ForwardPayoff` still carries no prize leg, and `development.evolve_marginal` still "
            "prices its my-side mirror the same way, so adding one here would give the same card "
            "two valuation bases across the board. What the anchor DID retire is the old reason "
            "given for deferring it — *\"the parked scale anchor first\"* — so this is now a plain "
            "ForwardPayoff-shape gap with no prerequisite, recorded so the damage-only reading is "
            "read as measured rather than as complete.",
            "THEIR DECKLIST, when crediting a denied forward payoff — `TheirSide.forward_payoff` "
            "reads the POOL-level forward index, so a Staryu on their board carries the Mega Starmie "
            "ex credit whether or not they run one, and the `reachable` leg is hardcoded True "
            "because their hand is a COUNT and their deck is untracked. Both are OVER-reads, both "
            "deliberate: `MySide.forward_payoff` can prove a line dead from `unseen_counts` and "
            "CANCELS the credit (`development.line_topology`), and claiming the same proof about a "
            "hidden deck would zero a denial against a threat that is perfectly real. The eventual "
            "narrowing supplier is the archetype Read (`TheirSide.read` / the matched Brief), which "
            "is a probability rather than a decklist — consuming it here would hand this family a "
            "second opinion about the Read, which the sole-supplier ruling forbids.",
            "BACKWARD topology on the denial credit — whether they can actually EVOLVE the body this "
            "turn. The credit prices what the line owes, not what they hold: an evolution card in "
            "hand, a Rare Candy skipping the Stage 1 (`data/EN_Card_Data.csv` id 1079), the "
            "played-this-turn gate (`docs/rules.md` §4) and their remaining hops are all unread, so "
            "a Dreepy they can never grow and one holding Drakloak price identically. `hand`'s "
            "mirror of this question is Issue #288's playability gate on MY side; there is no "
            "opponent-side equivalent and there cannot be one without their hand.",
            "the SCALING half of a denied payoff — the credit reads printed `maxDamage`, mirroring "
            "`MySide.forward_payoff` exactly so one card prices the same from either side. That "
            "makes it blind the way the printed forward index is blind: Alakazam's whole threat is a "
            "scaling term and its printed damage is 10, so denying an Abra credits almost nothing. "
            "`CombatMath.forward_threat_ceiling` is the board-priced instrument and is deliberately "
            "NOT substituted — using it on one side only would give the same card two valuation "
            "bases, and using it on both would retune `development.evolve_marginal`, which ADR-0070 "
            "rules.",
            "the non-Tera BENCH-IMMUNITY set — `docs/rules.md` §11's own warning: the immunity set "
            "is BROADER than Tera ex (Antique Plume Fossil, Misty's Magikarp, Poltchageist all "
            "carry unconditional prevent-all-while-Benched) and `CardStat` has no field for it "
            "(ADR-0020). `tera` is read and fails closed; the rest read as reachable and are "
            "over-credited. The residual gap, recorded rather than papered over — the fix is the "
            "same one ADR-0020 names, threading the engine's benched-immunity ability into "
            "`CardStat`.",
            "an {ex}-RESTRICTED bench rider — Zeraora's Thunder Raid (*210 damage to 1 of your "
            "opponent's Benched Pokémon {ex}*) parses to 0, so `slowking` gets no bench route from "
            "it. That is `parse_attack_bench_snipe`'s documented fail-closed doctrine (match only "
            "the clean unconditional phrasing; `tests/scouting/test_attack_riders.py` pins the "
            "restricted case at 0 by name), not a defect here — under-reading my own reach is the "
            "safe direction, and widening the parser is a card-fact change with its own blast "
            "radius over the whole pool.",
            "CONVERTING either seat's exposure into a prize — that is the attack's, and "
            "`attack_ev` prices it at the terminal action. This family prices the exposure STANDING "
            "on the board, capped at `_THREAT_CAP`, because `score(sequence) = state_value(end "
            "board) + EV(terminal)` adds the two and would otherwise pay for one Knock Out twice.",
            "their Energy denial / resource strip — removing fuel lengthens their clock without "
            "removing a body, and `opponent_target_value` prices bodies. `deny_relevance` is the "
            "instrument and is still dark (T2 / Issue #228 arms it).",
            "their hand and deck AS A RESOURCE — hand disruption (a Judge, a discard effect) still "
            "prices exactly 0 in THIS family: `opponent_target_value` prices bodies, and cards in "
            "hand are options rather than a body. Issue #280 closed the other half — `survival`'s "
            "clocks now read `theirs.hand_size` through the Damage Formula, so shrinking the hand "
            "of a scaling attacker IS priced, as the lengthened clock it buys. What remains dark is "
            "the resource reading (the Supporter they no longer hold, the search they cannot make) "
            "and `theirs.deck_count`, which still has a supplier and no reader — the Formula's "
            "hidden-deck pair is OMITTED for a side whose deck is not exactly known, and the "
            "opponent's never is (`_SideBase._deck_facts` claims `(None, None)`), so threading the "
            "context did NOT quietly give the deck count a reader the way it gave the hand size "
            "one. Narrowed, not closed; T4 must always-expand disruption plays.",
            "CHIP DAMAGE — progress toward a Knock Out I cannot yet complete. Reachability is a "
            "STEP: `_reachable_target_values` credits nothing for a body unless my Active's best "
            "reachable damage AGAINST THAT SEAT already meets its remaining HP, so a Mega "
            "Lucario chipped from 330 to 120 scores the same as one at full HP. Issue #281 made "
            "the step's height honest and Issue #284 gave their BENCH a step of its own — both "
            "legs are still steps, so bench chip that does not reach the rider still prices 0. "
            "This family is `survival`'s mirror "
            "in name and NOT in form — survival grades continuously by a clock "
            "(`halve(turns_to_ko_me - 1)`), while this family's REACHABILITY is on/off however "
            "finely Issue #329's anchor grades what a reached body yields — and that is exactly what "
            "the wave-3 ruling on `83116501|0|decision|60` objects to: *\"Our Starmie cannot KO the "
            "Lucario in under 3 turns. We can KO it with 2 Jetting Blows and a single Nebula "
            "Beam.\"* A multi-turn KO plan prices 0 every turn until the last one. Closing it needs "
            "a MY-side KO clock on the model — `CombatMath.turns_to_ko` is the shipped oracle but "
            "gates affordability on a raw energy COUNT while this family's reachability filter uses "
            "the Attach Budget, so routing to it as-is would give the family a second and weaker "
            "opinion about affordability than the one it already holds (the sole-supplier ruling "
            "forbids exactly that). The accessor is substrate, owned by T1's completeness contract "
            "(Issue #260); named here rather than derived inline, because `ceil(hp / damage)` "
            "written in this module WOULD be the second opinion.",
            "the SURVIVAL half of `opponent_target_value` — its `survival_shift` is a Δ of "
            "`turns_to_ko_me` under REMOVAL of the body, and the model exposes no removal-delta "
            "route (the live consumer at `pilot.py` bypasses to CombatMath, which the sole-supplier "
            "ruling forbids here). Passed as 0, so this family prices prize_advance only and a body "
            "whose removal buys turns without yielding prizes reads flat. T1 (Issue #260) owns the "
            "accessor; until it lands the fail-closed 0 is the honest answer, not a silent one.",
        ),
    ),
    TermFamily(
        name="readiness",
        reads=("body_payoff", "readiness_odds", "role_relevance"),
        does_not_read=("assignment_coverage", "bench_slot_price"),
        composition="Per-body payoff x readiness odds x role relevance, composed from the existing "
                    "Attach-Budget / readiness-odds / Needs machinery rather than a second opinion "
                    "about any of them. The payoff is `StateModel.attack_payoff` — the best attack the "
                    "body can pay off with ON THIS BOARD, not the printed `CardStat.maxDamage` "
                    "roll-up (ADR-0109). That makes `body_payoff` depend on MY Bench CONTENTS for a "
                    "bench-gated attack, which is not a second claim on `bench_slot_price`: "
                    "`development` prices how many slots are left, this prices what one attack can "
                    "land, and the two never read the same number. "
                    "**`readiness_odds` consults `turns_to_ko_me`, and that is not a disjointness "
                    "breach** — stated here because it is the first thing a reader of the tuples "
                    "will suspect, and because Issue #332 required the call to be argued rather "
                    "than assumed. The odds ask *does this body get to its payoff attack*, and a "
                    "body the opponent removes first does not get there; the clock is an INPUT to "
                    "that probability the way `turns_to_afford` already is, consulted on the "
                    "FORWARD leg alone (`_survives_to_spend`). `survival` prices a different "
                    "CONSEQUENCE of the same fact in a different currency — the `prize_at_risk` "
                    "handed over when the body falls, against the damage-denominated potential that "
                    "dies with it — so removing the body raises one family and lowers the other, "
                    "which is not one quantity added twice. Both families read the clock through "
                    "ONE call (`_survival_clock`), so they cannot come to disagree about it. The "
                    "registry fact stays `readiness_odds`, exactly as `survival` keeps "
                    "`predicted_loss` while consulting `prize_race`'s counts: splitting the clock "
                    "into a second fact string to make the read visible would make "
                    "`double_counted()` pass VACUOUSLY, which is the answer "
                    "`sound_rules.SCHEDULED_PAIRS` already records for the same temptation.",
        blind_to=(
            "the VALUE of the Active slot — narrowed by Issue #351, which took the legality half. "
            "`_may_attack_now` now gates the now-leg on the area and on `attack_blocked`, so a "
            "benched body no longer claims it can attack this turn; what stays unpriced is the "
            "slot's WORTH, so a retreat that puts the right body in front still moves this family "
            "only through the Attach Budget and the gate's on/off step. `promote_retreat_value` is "
            "the instrument and composes into `survival`; the retreat allowance itself is an OWED "
            "snapshot zone (T1).",
            "a board condition that is NOT a bench-partner condition — ADR-0109 routed the payoff "
            "through the damage oracle, which reads the one condition family the card-text parser "
            "extracts (`AttackStat.requiresBench`). Walking the whole set for *\"this attack does "
            "nothing\"* finds 24 attacks: 10 are coin flips (the `damageMin`/`damageMax` family, a "
            "different question), 2 are bench-partner gates and are now priced, and the remaining "
            "**12 are unread** — no Stadium in play (Fan Rotom 174), a Bench-count floor (Victini "
            "490), an exact hand size (Medicham 884), hand parity with the opponent (Iron Boulder "
            "971), a defender predicate (Sawk 602 vs {ex}, Camerupt 857 vs Burned, Basculin 577 vs "
            "an undamaged Active), their prize count (Hop's Cramorant 311), and a pay-from-hand "
            "discard (Decidueye 129, Lurantis 398, Ceruledge 797). Each still prices its PRINTED "
            "damage. **Exposure across the five shipped decks is 0** — the deck-csv walk finds only "
            "Solrock 676 — which is why Issue #278's *\"add only what the four decks need\"* leaves "
            "them here rather than in the build. This is the address, not a verdict: a deck change "
            "that adds one of the 12 makes it a live over-price, and the fix is another parser in "
            "`scouting/card_text.py` plus a context key, never a hand-enumerated condition "
            "vocabulary (ADR-0109's rejected option).",
            "Ability readiness — the incumbent leaf scored attack and Ability CO-EQUALLY "
            "(`planner._ability_readiness`, `_READINESS_ABILITY_VALUE`). Nothing in the model "
            "supplies an Ability payoff, so an evolve whose whole point is switching an engine "
            "Ability on prices only its attack payoff. The largest single regression risk in this "
            "swap, and named here so T4 reads it as a gap rather than a verdict.",
            "an Energy that EVAPORATES, on the now-leg of a body that CAN cash it — and this is now "
            "a VERDICT rather than a gap (Issue #351). `_readiness_odds` is `max(readiness_p, "
            "halve(turns_to_afford))`; the forward clock drops `discard_eot` Energy "
            "(`MySide.turns_to_afford(exclude_expiring=True)`) but `readiness_p` keeps it, and the "
            "two legs read the same attachment through the same matcher, so an Energy that FULLY "
            "arms the body zeroes the clock and pins the now-leg at 1.0 together. Issue #351 gated "
            "the now-leg on LEGALITY (`_may_attack_now` — the area plus `attack_blocked`) rather "
            "than stripping the Energy from it, and the measurement is why: over the committed "
            "corpus, 25 of 1018 of my bodies hold a `discard_eot` Energy and the clock moves on all "
            "25, but **21 of those are the Active on an unblocked turn**, where the body really can "
            "spend the Energy this turn and the 1.0 is TRUE. Masking the forward leg there is this "
            "family answering its own question correctly. What remains unpriced is only the "
            "residue: an Active that will attack with a DIFFERENT attack than its payoff, leaving "
            "the Ignition partly unspent. That is `attack_ev`'s at the terminal action (Issue #263) "
            "rather than a hole here, and it is bounded by the same 21 frames.",
            "what a DOOMED body could still do THIS turn OUTSIDE its payoff attack — the "
            "survivability discount (`_survives_to_spend`, Issue #332) zeroes the FORWARD leg on a "
            "body whose clock reads 1, which is exact for a payoff that lands on a later turn, and "
            "the now-leg is what keeps that body priced for a swing it can take right now. What "
            "nothing prices is the lesser swing: `attack_payoff` names ONE attack, so a doomed Mega "
            "Starmie ex whose Nebula Beam is unaffordable reads 0 forward while Jetting Blow is "
            "still on the menu in front of it. That swing is `attack_ev`'s at the terminal action "
            "rather than a hole in this family, and it is recorded because the zero is NEW — before "
            "Issue #332 the forward leg paid the doomed body anyway, so a reader diffing the two "
            "would otherwise read the drop as the body's whole value disappearing.",
        ),
    ),
    TermFamily(
        name="hand",
        reads=("assignment_coverage", "re_access", "hand_worth"),
        does_not_read=("body_payoff", "deploy_marginal"),
        composition="Assignment coverage of LIVE slots plus re-access, on the `set_keep_v2` spine. "
                    "Its Worth-denominated part is the one place POC_WORTH_PRIZE_RATE crosses. A "
                    "card's value once PLAYED belongs to `readiness` or `development`; this family "
                    "prices it only while it is still in hand.",
        blind_to=(
            "hand SIZE as such — a bigger hand is more options, but the assignment prices coverage "
            "of live slots and a card covering nothing contributes only its latent worth. A draw "
            "that whiffs therefore prices near 0, which is correct, and a draw that hits prices "
            "through the slots it fills, which is also correct — recorded so the near-zero is read "
            "as measured rather than missing.",
            "information already revealed — see the module header: two orderings that reveal then "
            "commit, or commit then reveal, reach the SAME end state, so no end-state function can "
            "separate them. Structural, whitelisted (`information-before-commitment`), not a gap.",
            "MY HAND on a simulated end board — the whole family prices 0 there, so on the develop "
            "rollout's leaf a card leaving my hand currently costs nothing. Not an equation gap: "
            "the engine's end observation is OPPONENT-perspective, so my hand is hidden, and the "
            "`leaf_hand_value` capture that works around it is one action stale in a per-branch way "
            "(`planner._simulate_line` carries the measurement — arming it scored a branch that SPENT "
            "a card ABOVE one that spent nothing). A snapshot at the true end of my turn is the fix "
            "and it needs substrate the sim does not have. The family is fully live wherever a REAL "
            "board is scored, which is every call Issue #263's 1-ply ordering makes. **MEASURED, no "
            "longer merely predicted** (2026-08-02, Issue #262): across all 22 gating "
            "Discrimination-Gate frames the T3 layer owns, this family read exactly 0.0000 on BOTH "
            "sides of every comparison — inert, 22 for 22. The consequence is the one the entry "
            "warned of, and it decides ten of those frames on its own: `development` credits the "
            "body a card play lands while NOTHING on the leaf path charges for the card leaving my "
            "hand, so spending is free. `_line_account`'s spend charge is the only counterweight, "
            "and on those ten frames it fires on FOUR and is out-scaled about 3:1 where it does "
            "(-0.06 prizes against a +0.20 deploy credit) — on the other six nothing charges for "
            "the card at all. That is why the leaf prefers Ultra Ball / Buddy-Buddy Poffin / "
            "Lillie's over the developer's *\"just save it for next turn\"* on every one of them.",
            "DECK THINNING as a reason to spend a card. The assignment prices what a card COVERS, so "
            "a card whose slot is already satisfied prices at its latent worth and playing it reads "
            "as a small loss. The wave-3 ruling on `83457493|1|decision|33` says otherwise on a real "
            "board: with all three Staryu/Starmie already out, Buddy-Buddy Poffin covers nothing AND "
            "is worth playing anyway, because removing a dead card raises the quality of every "
            "subsequent draw. That is a property of the DECK's composition, which no term reads — "
            "`readiness` and `development` price bodies, and this family prices the hand. Named "
            "rather than left as a silent zero, because at ordering time a 0 delta is never explored "
            "(Issue #263's blind-spot contract).",
        ),
    ),
    TermFamily(
        name="development",
        reads=("deploy_marginal", "evolve_marginal", "bench_slot_price", "line_topology"),
        does_not_read=("role_relevance", "prize_at_risk"),
        composition="Bench and line topology through the deploy (ADR-0086) and evolve (ADR-0070) "
                    "marginals, PLUS an escalating Bench-slot price: a slot's marginal cost rises as "
                    "open slots deplete, so the last slot is not spent on a non-critical support "
                    "body a second wincon should have had. That escalation replaces the flat +60 "
                    "`keep-a-bench` cliff (a spare body priced 1.96 on a non-empty Bench against "
                    "61.96 on an empty one — the entire gap was the rung). Issue #232.",
        blind_to=(
            "the STADIUM — `model.stadium` has a supplier and no reader, so playing or replacing "
            "one prices exactly 0. T4 lists stadium among the families it takes over, and this is "
            "the term that would have to grow the read.",
            "their board topology — development is MY-side only. Their bench filling up, or their "
            "line completing, moves nothing here; `threat` reads their bodies as targets, not as "
            "development. An accepted POC asymmetry (there is no opponent model).",
        ),
    ),
)

#: **The terminal registry** — terms evaluated at a sequence's TERMINAL ACTION, never on a board.
#:
#: Kept separate from :data:`REGISTRY` rather than added to it, and the separation is the point: an
#: attack has no successor state (`apply_option` raises for a terminal option), so
#: `score(sequence) = state_value(end board) + EV(terminal action)` is a SUM OF TWO KINDS of thing —
#: a function of a board and a function of an action. Folding the second into the six would make
#: `state_value(model)` answerable only for boards that came with an action attached, which is
#: exactly the provenance-dependence Issue #262 forbids.
#:
#: :func:`registry_gaps` and :func:`double_counted` walk BOTH, so the one-fact-one-family rule
#: spans the seam and `attack_ev` cannot quietly re-price what `threat` already prices.
TERMINAL_REGISTRY: tuple[TermFamily, ...] = (
    TermFamily(
        name="attack_ev",
        reads=("attack_damage", "attack_riders", "attack_economy", "next_turn_lock"),
        does_not_read=("opponent_target_value", "readiness_odds"),
        composition="EV of the attack that ENDS the turn (Issue #263 § Terminal-action valuation; "
                    "old Issue #145 amendment B made concrete). Composed from the shipped oracles, "
                    "never new math: the KO band / `predicted_damage` with coin branches entering "
                    "as an EXPECTATION rather than a printed floor, the target's prize value, "
                    "snipe/spread RIDER value priced against THEIR board, Effect-Clause economy "
                    "riders (energy recycle), and the next-turn clock cost a `nextTurnSelfLock`-"
                    "class attack imposes on ME. Readiness is deliberately absent: whether I CAN "
                    "attack is `readiness`'s question about the board, and asking it twice would "
                    "multiply the same probability into the same prize.",
        blind_to=(
            "the opponent's REPLY — this is a 1-ply expectation, so an attack that wins the "
            "exchange and an attack that wins the exchange and survives the answer score the same "
            "except through the end board's own `survival`. Depth-2 is out of the POC (Issue #150).",
            "opponent-choice riders — 'your opponent discards a card' and its relatives have no "
            "opponent model, so their value is 0. The apply-seam REFUSES the same class; the two "
            "refusals are the same gap seen from two sides.",
            "opponent ACTION-ECONOMY locks — a rider that restricts what the opponent may DO on "
            "their next turn (an Item lock, an Evolution lock, a named-attack lock) is not a body "
            "grant, so `transient_grants` (ADR-0033, homed `mine.active.grant` only) does not carry "
            "it even in principle: its vocabulary is `self_lock`/`same_lock`/`self_bonus`/"
            "`prevent_all`/`reduction` (`state_model.py`'s `grant` docstring), none of which is "
            "'opponent can't play card-type X'. Budew's Itchy Pollen (235, `item_lock`, free "
            "attack, verified at source) is the concrete case — 1 card in 1 deck, but the reason "
            "`dragapult_ex` sets `preferred_start=\"second\"` (`docs/rules.md` §2: the first player "
            "cannot attack turn 1) — a 1-of that moved a deck-level parameter. Pricing it needs a "
            "THEIR-side extension of `transient_grants`, the same OWED-zone class Issue #282 needs "
            "for damage-boost Trainers; declaring it here is free and honest now (Issue #290).",
        ),
    ),
)

#: Name -> family, for the `working` breakdown and for T3's dispatch.
FAMILIES: Mapping[str, TermFamily] = {f.name: f for f in REGISTRY}

#: Name -> terminal-action family. Separate mapping for the separate registry, so a caller cannot
#: iterate `FAMILIES` and silently pick up a term that needs an action it does not have.
TERMINAL_FAMILIES: Mapping[str, TermFamily] = {f.name: f for f in TERMINAL_REGISTRY}


def state_value(model: "StateModel", *, working: dict | None = None) -> float:
    """The board's worth **in prizes**. Higher is better for ME.

    ``model`` is a :class:`common.state_model.StateModel` — the SOLE data supplier, both sides
    (ADR-0092 standing ruling). Nothing here reads a raw observation or reaches for the Pilot.

    ``working``, when a dict is passed, is FILLED with the per-family breakdown ``{name: prizes}``.
    A caller-supplied dict rather than a second entry point or a wrapper type, for one reason: the
    Turn Planner evaluates this once per candidate sequence and must pay nothing for a diagnostic it
    is not reading, while a correction round wants the breakdown on the one frame it is disputing.
    Passing nothing costs nothing; the sum of a filled ``working`` equals the return value.

    **Deviation from the issue's literal wording, recorded rather than slipped in:** Issue #259 and
    the T0 spec both say "a ``working()`` per-term breakdown dict", which reads as a second callable.
    An out-parameter was chosen instead because a second callable either re-computes every family
    (paying twice on the planner's hot path) or forces a cache the contract would then have to
    specify. The BREAKDOWN is what the contract owes; how it is delivered is this module's choice,
    and a wave reviewer should overrule it here if they disagree.

    **Incremental evaluation** rides the StateModel's existing lazy memo (ADR-0068 amendment A) —
    the model is the unit of caching, so a family re-reading an already-derived clock pays once per
    model, not once per call. **This function memoizes on the model too**, through the same
    `_memoized` channel every parameterised derivation uses, so a second call on one model is a dict
    lookup rather than six re-evaluated families. That matters because the leaf and the wave-3
    workings dump both score the same model, and Issue #263's composer scores each candidate's model
    once for ordering and may meet it again inside a sequence.

    The memo holds the per-family dict, not the scalar, so a caller that passes ``working`` gets the
    full breakdown on a cache HIT as well as on a miss — a cache that silently stopped filling the
    diagnostic would send wave-3 triage after the wrong term. ``working.update`` copies, so a caller
    cannot reach through it and corrupt the cached dict for every later reader.

    Old Issue #145's amendment A asked for incremental leaf evaluation across boards. The POC answer
    is memo-per-model, recorded here rather than left implicit: the apply-seam hands out a FRESH
    model per hypothetical, so there is no cross-model delta to exploit, and cost control is term
    laziness plus the planner's branching caps. Revisit post-POC only if profiling demands it.

    **PROVENANCE-AGNOSTIC** (ruled 2026-08-01, Issue #262). ``model`` is a StateModel and nothing
    here may branch on how it was produced. Issue #259 §3b gives the apply-seam three fates, two of
    which yield a model — MODELLED (closed-form) and ENGINE-RESOLVED (a real-board engine readback
    for a clause-vocabulary gap) — and this function sees only the model in both cases. No provenance
    flag reaches it and none may be added: a term that behaved differently on an engine-resolved
    board than on a modelled one would be a bug in that term, not a legitimate distinction. The
    guarantee that keeps the two paths scoring identically is §3c's completeness audit
    (`snapshot_coverage`), not a branch here.

    **Sane MID-TURN, not only at end of turn** (Issue #263's ordering ruling). Uniform 1-ply
    differencing evaluates this on half-finished turns — Energy attached but no attack yet, a body
    benched but not yet evolved — so no term keys off "the turn is over" or off having attacked, and
    every term degrades continuously: a half-built attacker scores partial readiness through
    `readiness_p`, never 0 and never full. `test_state_value.py`'s monotonicity class is the guard."""
    terms = model._memoized(("state_value",), lambda: _terms(model))
    if working is not None:
        working.update(terms)
    return float(sum(terms.values()))


def _terms(model: "StateModel") -> dict:
    """The six families, evaluated once. **Insertion order is the REGISTRY's order and that is a
    contract** (Issue #262's purity amendment: *"fixed term-iteration order — never dict/set
    iteration that could reorder"*). Floating-point addition is not associative, so a reordering
    would move the last bits of the sum; `test_the_term_iteration_order_is_FIXED_...` asserts it."""
    race = model.prize_race
    return {
        "prize_race": prize_race(my_prizes_remaining=race.my_prizes_remaining,
                                 their_prizes_remaining=race.opp_prizes_remaining),
        "survival": survival(_exposed_bodies(model), predicted_loss=_predicted_loss(model)),
        "threat": threat(_reachable_target_values(model)),
        "readiness": readiness(_ready_bodies(model)),
        "hand": hand(**_hand_legs(model)),
        "development": development(**_development_legs(model)),
    }


# ── the extractors — StateModel -> the families' plain numbers ────────────────────────────────────
#
# Split out per family rather than inlined, for the reason the registry exists: each one is the
# single place a board fact enters the scalar, so "which family reads `turns_to_ko_me`" has a code
# answer and not only a docstring one. Every one of them rides the model's lazy memo (ADR-0068) —
# they read derived accessors and derive nothing themselves — which is the whole of this module's
# incremental-evaluation story. The apply-seam produces FRESH models per hypothetical, so there is
# no cross-model delta to exploit and none is attempted: cost control is term laziness plus the
# planner's branching caps. Old Issue #145's amendment A asked for incremental leaf evaluation; the
# POC answer is memo-per-hypothetical-model, revisited post-POC only if profiling demands it.


def _exposed_bodies(model: "StateModel") -> tuple:
    """MY bodies as `survival` reads them — BOTH areas, Bench-Harvest-aware.

    The harvest kwargs are the point of T0's widened `turns_to_ko_me` signature: a benched body's
    clock is a different question from the Active's (`my_benched`), and a shared rider budget is a
    fact about the whole bench that one body cannot express (`my_bench`). Passing the defaults would
    silently ask the solo-body question for six bodies.

    ``context`` is the same argument one level further out (Issue #280). The clock prices THEIR
    attacks through the Damage Formula, whose scaling attacks read their counts off a context dict —
    and a variable absent from that dict contributes 0 (`strategy/damage.py`). Passing none meant
    every scaler read 0, so an opponent holding twelve cards and one holding two produced the SAME
    clock: `docs/matchups/alakazam.md` is the second-most-played archetype in the tracked meta and
    its damage *is* its hand size (Powerful Hand, 20 per card, no floor). Measured on the 371-frame
    corrections corpus, threading it moves 20 body clocks.

    ``attacker="theirs"`` is the whole of the correctness here and is not boilerplate. The Formula's
    variables are named relative to the attacker (`atk_*`/`def_*`) and the attacker on a SURVIVAL
    read is the opponent; handing this `mine` would read my own hand as their damage scaler, which is
    silently plausible and wrong in the one direction a survival estimate may never fail in. The
    board's other half is not lost by choosing — a Mega Froslass ex scaling off `def_hand` (my hand)
    is in the same dict, on the defender's side of it, which is exactly why one dict cannot serve
    both directions.

    It is passed for BENCHED bodies too, where the oracle currently has nothing to do with it: the
    bench leg is the Bench Harvest, whose payloads are the printed snipe/spread riders, and riders
    ignore Weakness/Resistance by rule (ADR-0022) so they never route through the damage model. The
    call site states the DIRECTION of the read and leaves which leg consumes it to the oracle;
    branching here would encode the oracle's internals in `state_value` and would go stale the day a
    rider learns to scale. The cost is nil — the context is memoized per direction and
    identity-stable, so it canonicalises once into the clock's memo key."""
    return tuple(
        ExposedBody(prize_at_risk=float(b.prize_value), turns_to_ko_me=_survival_clock(model, b))
        for b in model.mine.bodies)


def _survival_clock(model: "StateModel", body) -> int:
    """**THE** clock on one of my bodies — the single call two families read (Issue #332).

    Extracted from :func:`_exposed_bodies` rather than copied into the readiness path, and the
    extraction is the correctness rather than tidiness. `survival` grades exposure by this clock and
    `readiness` now discounts a body's FORWARD potential by it (:func:`_survives_to_spend`); asking
    the oracle twice with two independently-written argument lists is precisely how the two families
    come to hold different opinions about when the same body dies. The sole-supplier ruling forbids a
    second opinion, and one call site is what makes that structural instead of hopeful.

    Every kwarg is :func:`_exposed_bodies`' own, unchanged and argued there: the Bench-Harvest pair
    (``my_benched`` / ``my_bench``), ``opp_active``, and the THEIRS-direction Damage Formula context
    (Issue #280) — the attacker on a survival read is the opponent. Cost is nil on the second
    reader: `StateModel.turns_to_ko_me` is memoized by VALUE over every argument, `bench_raws` and
    `active_raw` are `lazy` snapshot properties, and `damage_context` is a method memoized per
    DIRECTION and identity-stable — so the readiness path pays a memo hit rather than a re-derivation."""
    return int(model.theirs.turns_to_ko_me(
        body.body, my_benched=not body.is_active, my_bench=model.mine.bench_raws,
        opp_active=model.theirs.active_raw, context=model.damage_context(attacker="theirs")))


def _predicted_loss(model: "StateModel") -> bool:
    """Can the opponent WIN next turn? — the terminal-loss family (whitelisted `predicted-loss` and
    `prize-lethality`), charged at :data:`LOSS_PRIZES` inside `survival`.

    **Two cases of `docs/rules.md` §7, one clock.** Both are win conditions a next-turn Knock Out
    reaches, and both fire only when the budgeted Incoming actually Knocks the body Out:

    * **case 2** (ADR-0064) — my Bench is EMPTY under a doomed Active, so there is nothing to
      promote and the Knock Out ends the match.
    * **case 1** (ADR-0064 Amendment B, Issue #283) — a doomed body whose Knock Out yields at least
      the prizes they still need, so the Knock Out takes their LAST prize.

    **Why case 1 is here and could not be anywhere else.** *"They are at 3 prizes and my Active is a
    3-prize Mega"* is a loss; *"they are at 6"* is an exposure. The fact separating them is the
    PRODUCT of a body's prize yield and their remaining count, and the double-counting rule splits
    those across `survival` (owns `prize_at_risk`) and `prize_race` (owns the counts) — so neither
    positional family may form it, and :func:`registry_gaps` reported nothing because the fact was
    *claimed*, just by families structurally unable to combine it. This term is the one already
    licensed to price a game-ending fact outside the positional band. It reads their count as a
    win-condition TEST and never as race value; both families' `blind_to` say so.

    Case 1 spans BOTH areas, because §7 case 1 is about a BODY rather than the Active Spot: a
    chipped multi-prize body on the Bench under a live snipe rider ends the game just as finally.
    The area is declared to the clock (``my_benched=``), which confines a benched body's
    reachability to the snipe/spread riders and honours Tera bench-immunity (`docs/rules.md` §11)
    instead of crediting printed damage that cannot land there.

    ``evo_min_energy=1`` is ADR-0064's bounded-pessimism guard carried over verbatim, and shared by
    both cases — an evolution-based Knock Out counts only off a pre-evolution that ALREADY carries
    Energy, because a bare 0-Energy pre-evo is not a credible next-turn game-ender. Dropping it for
    the new case would make this rung fire on boards the incumbent leaves alone, which is a
    behaviour change disguised as a port.

    ``context`` is the THEIRS-direction Damage Formula dict (Issue #280), threaded into the clock
    both cases share. The rung this is a port OF — `planner.Planner._predicted_loss` — makes the same
    `reachable_incoming(evo_min_energy=1)` call WITH ``context=self._opp_attack_context``, the
    Pilot's own *"OPPONENT-as-attacker context"*, so the direction here is the incumbent's rather
    than a fresh judgement about which side attacks; this call site was simply the one that dropped
    it. Omitting it did not make the rung conservative, it made it BLIND: every Damage Formula
    scaler contributed 0, so a Powerful Hand at 21 cards read as 0 damage rather than 420 and a
    doomed board with an empty Bench scored as a healthy one. Measured on the corrections corpus,
    five bench-empty frames read a different Incoming once the context is threaded; on
    `82226759|64` it is 30 → 420 against a 330 HP Active. Under-reading incoming damage is the one
    direction a survival estimate may never fail in, and a terminal rung is where it costs most.

    The answer is a BOOL rather than a magnitude, which is Issue #283's explicit POC ruling made
    structural: a body whose loss hands them 2 of the 3 prizes they need is worse than the flat
    exposure `survival` prices but is not a loss, and grading that is a post-POC question."""
    mine, theirs = model.mine, model.theirs

    def _doomed(body) -> bool:
        return bool(body.hp_remaining) and theirs.reachable_incoming(
            body.body, evo_min_energy=1, my_benched=not body.is_active,
            context=model.damage_context(attacker="theirs")) >= body.hp_remaining

    # case 2 — the visible bench-empty fact gates the clock read, so a board with a Bench pays
    # nothing for this leg (a bench body soaks: recoverable, not a loss).
    active = mine.active
    if active is not None and not mine.bench and _doomed(active):
        return True

    # case 1 — the CHEAP prize comparison gates the expensive clock read, and it is false on every
    # board where they still need more prizes than my biggest body is worth (i.e. almost all of
    # them), so the extra reads are paid only where the fact can actually fire.
    #
    # `prizes_remaining` reads an ABSENT `prize` zone as 0, and 0 is falsy here, which is the fail
    # direction rather than an accident: a hand-built board that carries no zone makes no claim, and
    # a board on which they have already taken their last prize has no next turn to predict.
    left = model.prize_race.opp_prizes_remaining
    return bool(left) and any(b.prize_value >= left and _doomed(b) for b in mine.bodies)


def _reachable_target_values(model: "StateModel") -> tuple:
    """Their bodies as `threat` reads them: `needs.opponent_target_value` over the Knock Outs I can
    actually reach THIS turn — **both seats**, each through its own damage route.

    Reachability is my Active's best affordable damage against the target's remaining HP, under the
    full Attach Budget. The shipped affordability oracle, not a second opinion about it. What
    changes with the seat is the DAMAGE, because a rider is a different route rather than a wider
    read of the same one:

    * their **Active** — `best_reachable_damage_vs`, the damage model against the body actually in
      front of me (Issue #281).
    * their **Bench** — `best_reachable_bench_damage`, the attack's single-target snipe RIDER
      (Issue #284). Printed damage lands on the Active; a benched body is reachable only through a
      rider, which ignores Weakness and Resistance by rule (ADR-0022) and is zeroed on the Active
      path by `predicted_damage` itself. Bench-immune (`docs/rules.md` §11) and unreadable bodies
      contribute nothing, failing closed.

    **Against THIS defender, not in the abstract** (Issue #281). The read used to be the
    opponent-INDEPENDENT `best_reachable_damage` — the biggest *printed* number my Active could
    afford — and a printed number is wrong in both directions at once. It under-claimed every
    Weakness Knock Out (`mega_starmie`'s doctrine is *lead Jetting Blow when the Active is
    Water-weak with ≤240 HP*: printed 120, doubled 240, and the gate said unreachable), and it
    over-claimed every prevented one (`docs/matchups/crustle.md` Seam 1 — *a pure-ex deck cannot
    damage an active Crustle at all*, while the printed gate priced the Knock Out as pressure). The
    sibling applies Weakness/Resistance, the defender's prevention Ability and my live damage
    boosts, at the oracle's default ``bound="exact"`` — an offensive gate is neither the Lethal
    Solver's guarantee (``"min"``) nor a worst case (``"max"``). The incumbent is untouched, because
    it is `attach_value`'s counterfactual leg and that equation is corpus-ruled (ADR-0069 §2).

    **Their BENCH, because chip standing on it is an asset** (Issue #284). The loop returned at most
    one element, so damage already on their benched bodies was invisible: a board where six counters
    sat there from last turn's Phantom Dive scored identically to a fresh one. `dragapult_ex`'s win
    plan IS that asset — *"Phantom Dive pre-loads benched mons with softening chip you cash into
    prizes on LATER turns"*, and *"Phantom Dive is the turn-ender, so Munkidori / Boss's / Cruel
    Arrow resolve BEFORE it and convert prior-turn chip"*. What this prices is the STANDING position
    (a body of theirs is one rider from dead, and that constrains what they can afford to bench),
    exactly as the Active leg prices their Active's exposure. Converting either remains
    `attack_ev`'s at the terminal action, which is what `_THREAT_CAP` and the module header's
    two-band argument keep from being paid twice.

    **`snipe_relevance.target_relevance` is deliberately NOT called here**, though it is the other
    instrument the audit names. It answers *should I aim this turn's snipe at this body* — the
    CONVERSION decision, which is `attack_ev`'s and the Pilot's snipe rung's — and its inputs
    (`turns_to_ko_before`/`_after`, `rider_damage`, `prizes_needed`, the matched Brief priority) are
    Pilot plumbing no `StateModel` supplies. Reading it would hand this family a second opinion
    about a question another term owns, which the sole-supplier ruling forbids. What this leg needs
    from that module is its SUBJECT — that a bench route exists at all — and that comes off
    `AttackStat.benchSnipe` directly.

    ``attacker="mine"`` on the context is not boilerplate — the Damage Formula's variables are named
    relative to the attacker, so `survival`'s context and this one are different dicts and one
    cannot answer both. It is read inside the Active branch only: the bench route is a printed rider
    that no scaler reaches, so passing a context there would key a memo on a value nothing consumes.

    **The DENIAL credit, because a pre-evolution is worth what it becomes** (Issue #285). A target's
    `prize_value` is what the body yields NOW, so killing a Staryu priced exactly as much as killing
    any other 1-prize body — while the doctrine's whole point is that it erases three. *"Snipe/gust a
    Staryu before it rush-evolves … to trade 1 prize for a denied 3"*; *"prioritise sniping Snover
    pre-evolution — a 1-prize cost erases a 3-prize wincon"*; *"race the fragile pre-evos — KO Dreepy
    (70) / Drakloak (90) before they become the wall"* — **seven of the eight matchup docs** make this
    their primary or secondary lever, and it applies to a plain gust-and-Knock-Out too. So
    `prize_advance` now carries the forward payoff the removal DENIES, from
    :meth:`TheirSide.forward_payoff`.

    The credit is `development.evolve_marginal`'s expression, term for term — `_READINESS_W x
    (owed_damage / PRIZE_DAMAGE_RATE) x halve(hops)` — and reusing it rather than choosing a scale is
    the point: forward payoff is printed damage held as POTENTIAL on both sides of the board, so the
    same anchor prices it, and a re-tier moves both together. `halve(hops)` is `EvolveBody.p_arrive`'s
    shipped convention (ADR-0070 §6), which is what keeps a body three hops from its payoff from
    pricing as though it were one. **No new constant** enters here.

    Two legs of that expression are deliberately NOT mirrored. `relevance` is `MySide.role_worth` —
    the deck's own DECLARED opinion about what a body is for, which no opponent supplies — so the
    opponent leg carries none and reads at full weight. And the `line_topology` CANCELLATION cannot
    apply, because `TheirSide.forward_payoff` fails OPEN on reachability (their deck is untracked);
    the fail direction is argued at that method. Both make this an OVER-read rather than an
    under-read, which is the safe direction for a threat term and is recorded in `blind_to`.

    **This is not a read of their board TOPOLOGY**, which the epic's ledger routes to Issue #263 and
    `development.blind_to` rules out (*"their bench filling up, or their line completing, moves
    nothing here"*). Nothing here reads their bench count, their development, or what they hold: the
    credit is CARD KNOWLEDGE about one target body — its `evolvesFrom` chain and printed damage —
    exactly the class of fact `prize_value` already is. What `development` is blind to is valuing
    THEIR development as a positional term; this values one reachable Knock Out more precisely, which
    is `threat`'s own declared subject.

    ``survival_shift=0`` is the fail-closed answer to a missing supplier, named in `blind_to` rather
    than hidden: the shift is a Δ of `turns_to_ko_me` under REMOVAL of the body and the model exposes
    no removal-delta route. `phase` is still threaded honestly, so the term sharpens with the race
    exactly as `phase_scale` says it should once the shift becomes readable."""
    mine = model.mine.active
    race = model.prize_race
    phase = _needs.phase_scale(race_ahead=None,
                               opp_prizes_remaining=race.opp_prizes_remaining)
    values = []
    for target in model.theirs.bodies:
        if not target.hp_remaining:
            continue
        reach = (model.mine.best_reachable_damage_vs(
                     mine, target, context=model.damage_context(attacker="mine"))
                 if target.is_active else
                 model.mine.best_reachable_bench_damage(mine, target))
        if reach < target.hp_remaining:
            continue
        advance = float(target.prize_value) + _denied_forward_payoff(model, target)
        values.append(_needs.opponent_target_value(prize_advance=advance,
                                                   survival_shift=0, phase=phase))
    return tuple(values)


def _forward_credit(forward, *, relevance: float = 1.0) -> float:
    """What a line's UNPAID forward payoff is worth, in prizes — the ONE expression, both sides.

    `_development_legs` prices MY body's owed payoff with it and :func:`_denied_forward_payoff`
    prices the DENIAL of theirs, and they are the same quantity read from opposite ends of the
    board: printed damage held as POTENTIAL, crossed on `PRIZE_DAMAGE_RATE`, carried at the
    positional `_READINESS_W` band, hop-discounted by `EvolveBody.p_arrive`'s shipped `halve`
    convention (ADR-0070 §6). Two copies would let a re-tier land on one side and not the other,
    which is the divergence `CombatMath._forward_hop_depths` was extracted to prevent one module
    over — the same discipline, applied to the expression rather than to the walk.

    ``relevance`` is the my-side leg only: `MySide.role_worth` is the deck's DECLARED opinion about
    what a body is for, and no opponent supplies one. It defaults to 1.0 rather than to 0.0 so the
    opponent reading carries the payoff at full weight, which is an OVER-read and the safe direction
    for a threat term (`threat.blind_to`).

    **The guard is defensive, not load-bearing, and mutation testing says so** — deleting it changes
    no result, because `forward_payoff_terms` and `MySide.forward_payoff` both return owed damage 0
    exactly when hops is 0, and `_READINESS_W x 0 x halve(0)` is already 0. It is kept because that
    coupling is a property of those two oracles' current shape rather than an invariant: a future
    reading returning owed damage at 0 hops would be priced UNDISCOUNTED, since `halve(0)` is 1.0.
    Recorded rather than left to look tested.
    """
    if forward.hops <= 0 or forward.owed_damage <= 0.0:
        return 0.0
    return (_READINESS_W * (forward.owed_damage / currency.PRIZE_DAMAGE_RATE)
            * halve(forward.hops) * relevance)


def _denied_forward_payoff(model: "StateModel", target) -> float:
    """The forward payoff removing ``target`` DENIES, in prizes — `threat`'s denial credit.

    :func:`_forward_credit` against THEIR body, minus the two legs that have no opponent-side
    supplier: `relevance` (defaulted, see above) and the `line_topology` CANCELLATION, which cannot
    apply because `TheirSide.forward_payoff` fails OPEN on reachability. Both are argued at
    :func:`_reachable_target_values` and named in `threat.blind_to`.
    """
    return _forward_credit(model.theirs.forward_payoff(target.card_id))


def _ready_bodies(model: "StateModel") -> tuple:
    """MY bodies as `readiness` reads them.

    * ``payoff`` — the body's line payoff in prizes, as `StateModel.attack_payoff` reads it: the best
      attack this body can actually pay off with **on this board**, not the printed
      `CardStat.maxDamage` roll-up (Issue #287, ADR-0109). A printed number cannot carry a board
      condition, so Solrock's Cosmic Beam — *"70 … if you don't have Lunatone on your Bench, this
      attack does nothing"* — used to price 70 on a Bench that would never pay it, and benching or
      losing the Lunatone moved this term by exactly 0. The body's OWN form, deliberately: what a
      FORWARD form would achieve is evolution topology and belongs to `development`, and reading the
      forward closure here would price one fact in two families.
    * ``readiness_odds`` — `readiness_p` asked about the body's PAYOFF attack, not about "any
      attack". The distinction is load-bearing and not pedantry: pairing a max-damage payoff with
      the any-attack (famine) probability saturates the term for every real attacker, and a
      saturated term has zero derivative, so the attach that completes the payoff cost would price
      at 0 delta and never be explored. The attack id comes from the SAME `AttackPayoff` record as the
      damage, which is what keeps the pair honest once a gated maximum falls back to a lesser attack.
      Its FORWARD leg is discounted by the body's own survival clock (:func:`_survives_to_spend`,
      Issue #332): potential that lands on a later turn needs the body to still be standing on that
      turn, and `turns_to_ko_me` is the shipped answer. Read through :func:`_survival_clock`, the
      one call `survival` reads too, so neither family can hold its own opinion about the clock.
    * ``role_relevance`` — `role_value` normalised by `DEPLOY_WORTH_SCALE`, which is exactly
      `deploy_value._relevance`'s dimensionless ratio. Composed rather than re-derived so a role
      re-tier moves both instruments together."""
    out = []
    seen: set = set()
    for b in model.mine.bodies:
        if b.stat is None:
            continue                       # unknown card: make no claim (the oracle's own direction)
        paying = model.mine.attack_payoff(b)
        payoff = paying.damage / currency.PRIZE_DAMAGE_RATE
        if payoff <= 0.0:
            continue                       # nothing this body can land: a condition it cannot meet
        out.append(ReadyBody(payoff=payoff,
                             readiness_odds=_readiness_odds(model, b, paying.attack_id),
                             role_relevance=_body_relevance(model, b.card_id, seen)))
    return tuple(out)


#: A repeated UTILITY body's discount — `planner._READINESS_SATURATED`, carried at the same value.
_SATURATED = 0.1


def _saturation(model: "StateModel", card_id, seen: set) -> float:
    """1.0 for the first copy of a card in play and for any attacker; :data:`_SATURATED` for a
    SECOND in-play copy of the same utility card.

    `planner._readiness_saturation`'s ruled convention, ported: *"a 2nd Lunatone is fodder — we only
    ever need one Solrock and one Lunatone"*, keyed on card id, while an attacker always accumulates
    because *"a 2nd attacker advances the prize race"*. Without it the board terms are sums where
    they should be SETS, and two identical engine bodies price as two — the duplicate-wincon naivety
    `set_keep_v2` was built to make structurally impossible one seam over.

    The shipped rule asks the Pilot's `_is_utility_body`; the deck-agnostic reading of the same
    question is the DECLARED role, which the model supplies: a body at or above the
    `secondary_attacker` tier is an attacker. **Mutates ``seen``** — the caller's per-board set,
    exactly as the shipped helper does."""
    if card_id is None:
        return 1.0
    if model.mine.role_worth(card_id) >= ROLE_TIER["secondary_attacker"]:
        return 1.0
    if card_id in seen:
        return _SATURATED
    seen.add(card_id)
    return 1.0


def _readiness_odds(model: "StateModel", body, attack_id) -> float:
    """P(this body gets to its payoff attack) — `readiness_p` OR the forward clock, whichever is
    better, and the `or` is the part that matters.

    ``attack_id`` is the attack the payoff was PRICED from (`Payoff.attack_id`), passed in rather
    than re-derived so the two legs cannot name different attacks. They can now differ: a body whose
    biggest attack is gated by an unmet board condition falls back to its best paying attack, and
    asking these odds about the dead one would price a real payoff at a probability that belongs to
    nothing.

    `readiness_p` is a THIS-TURN probability and fails closed at 0.0, which is the right answer to
    the question it asks and the wrong shape for a positional term: once the turn's one manual attach
    is spent, every body one Energy short of its payoff reads 0, and a whole mid-turn board goes flat
    — the exact "does not degrade gracefully on partial states" failure Issue #263's ordering ruling
    names. A body one Energy from its wincon attack is not as ready as an armed one, but it is
    emphatically readier than a bare Basic.

    So the forward leg is `grading.halve(turns_to_afford)` — `EvolveBody.p_arrive`'s equation,
    reused rather than re-derived, over MY half of the Two Clocks (ADR-0070 §6). Armed now grades
    1.0, next turn 0.5, unknown 0.0 (fail closed, no claim). Taking the MAX rather than adding keeps
    the result a probability and keeps it monotone in both inputs: attaching Energy can only shorten
    the clock or raise the odds, so it can only raise this.

    **The forward leg excludes EVAPORATING Energy** (`exclude_expiring`, Issue #286): Ignition
    Energy is discarded at the end of the turn it is attached, so a clock that counts it is not
    reading the board this body will stand on next turn. The now-leg deliberately keeps it — the
    Energy genuinely is there this turn, and that is a fact, not the error. `docs/rules.md` names
    the misplay the rider causes as its worked example of a reason-only rule (*"don't attach
    Ignition T1-going-first — you can't attack, so it's discarded for nothing"*, correction
    ep81903490 f5), and `mega_starmie` runs four of them in thirteen Energy.

    It is live on a PARTIAL loan, and `mega_starmie` prints one: Ignition on a **Basic** provides
    only ``{C}``, so a Staryu holding one is still two attaches from its line's ``{C}{C}{C}`` payoff
    and `readiness_p` reads 0.0 (a colourless unit cannot pay Water Gun's ``{W}``). Measured on the
    real pilot: `readiness` 0.000750 → **0.000375**, which is exactly the bare-Staryu value. An
    Ignition on a Staryu now buys nothing forward, which is the correction.

    **The now-leg is asked only of a body that may LEGALLY attack this turn** (Issue #351,
    :func:`_may_attack_now`), and that is what un-masks the rest of Issue #286's fix. The oracle has
    no legality leg — nothing on its path reads the body's area, the turn, or the first-player attack
    ban — so a BENCHED body, or an Active on a turn with no attack step, used to read 1.0 and
    ``max`` discarded the forward clock behind it. Measured over the committed corrections corpus
    (372 frames / 1018 of my bodies, positive control 536 reading 0.0): 25 hold a `discard_eot`
    Energy and the clock moves on all 25; **21 are Active on an unblocked turn**, where the 1.0 is
    TRUE and the masking is this function answering correctly, and **4** are not — 1 benched
    (`83664991|43`) and 3 first-player-turn-1 (`81903490|8`, `81903490|10`, `81904451|9`). Those 4
    are the whole of the defect, and Issue #351's option 2 — stripping the expiring Energy from the
    now-leg too — was rejected because it would tell an armed Active attacker it cannot swing.

    **The forward leg is also discounted by the body's own SURVIVAL clock** (Issue #332,
    :func:`_survives_to_spend`), and it rides the forward leg ALONE for the same reason
    `exclude_expiring` does: the two legs answer about two different turns. The now-leg is about a
    payoff cashed on MY turn, which happens before the opponent's next one, so a body about to fall
    still swings and no discount is owed. The forward leg is about a payoff cashed on a LATER turn,
    which the body has to still be standing for — and `turns_to_ko_me` is exactly the shipped answer
    to whether it will be. Without it `readiness` prices an attach onto a body the opponent removes
    next turn identically to one onto the successor behind it, which is the measured misplay
    (`83037962|0|decision|48`: *"Placed second energy on active doomed mega starmie … therefor
    should start powering up our reserve benched staryu"*)."""
    now = model.mine.readiness_p(body, attack_id) if _may_attack_now(model, body) else 0.0
    arm = model.mine.turns_to_afford(body, exclude_expiring=True)
    forward = 0.0 if arm is None else halve(arm) * _survives_to_spend(model, body)
    return max(0.0, min(1.0, max(now, forward)))


def _may_attack_now(model: "StateModel", body) -> bool:
    """May ``body`` attack THIS turn at all — the legality leg `readiness_p` does not have.

    The now-leg asks *P(this body is READY to use the attack this turn)* and answers it from
    affordability alone. Verified at source rather than recalled: `MySide.readiness_p` →
    `CombatMath.readiness_p` → `reachable_attach_p` → `reachable_attach`, whose only
    non-affordability gates are the ADR-0033 transient `self_lock`/`same_lock`. Nothing on that
    path reads the
    body's AREA, the turn number, or the first-player attack ban — so a **BENCHED** body reads 1.0,
    and so does an Active on a turn the rules give no attack step to.

    Two facts, both already shipped and neither re-derived here:

    * :attr:`BodyView.is_active` — only the Active attacks. The Bench is where a body waits
      (`docs/rules.md` §3).
    * :attr:`MySide.attack_blocked` — the RULE leg, carrying all three of Asleep, Paralyzed and the
      first player on turn 1 (`docs/rules.md` §2, *"CANNOT attack — the starting player skips the
      attack step on turn 1"*, `[RULE: rulebook L152]`).

    **This is `active_famine`'s composition, applied to an arbitrary body rather than to the
    Active.** That property is the shipped precedent for the shape: it checks `attack_blocked`
    BEFORE calling the affordability oracle, and its docstring says why — *"only the RULE leg may
    claim a famine without one"*. The rules leg lives in the caller; this is a caller that was
    missing it. `active_famine` itself is not reusable here because it is Active-scoped by
    construction, and the body this function is asked about is usually not the Active.

    **Why the gate is HERE and not in `readiness_p`** (Issue #278's *"never retune the incumbent"*).
    The oracle is shared, and its area-blindness is CORRECT for its other caller: `promote_retreat_value`
    (ADR-0073) reads it to price bringing a benched body TO the Active spot, and a `readiness_p` that
    returned 0 for a benched body would answer that question with the very fact the promote changes.
    So the legality leg belongs to the consumer that asks about a body standing still, which is this
    one. `test_the_gate_leaves_readiness_p_ITSELF_byte_identical` pins that the oracle did not move.

    **What this does NOT do, stated because the difference is the whole design.** It does not strip
    the evaporating Energy from the now-leg (Issue #351's rejected option 2). Where the body CAN
    attack, an Ignition on it is genuinely spendable this turn and the 1.0 is true; masking Issue
    #286's forward leg there is the family answering correctly, not a defect. Measured over the
    committed corpus at the fix commit: of the 25 of my bodies holding a `discard_eot` Energy, **21
    are Active on an unblocked turn** and keep their 1.0, and **4** fail this gate — one benched
    (`83664991|43`) and three first-player-turn-1 (`81903490|8`, `81903490|10`, `81904451|9`, the
    episode `docs/rules.md` cites for exactly this misplay).

    **The ABSENT-fact direction is fail-CLOSED**, which is the safe one here: `attack_blocked` reads
    ``self.turn <= 1`` over ``self.turn = int(turn or 0)``, so a board that states no turn at all
    reads turn 0 and comes back BLOCKED — the now-leg then claims nothing and the family falls back
    to the forward clock. That is the opposite of the collapses
    `test_value_stack_integration.RULED_COLLAPSES` catalogues, where an absent fact arrives as a
    number that reads like a measurement, and it is the direction this gate wants: the failure it
    must never have is crediting a body that cannot swing.
    `test_the_legality_gate_fails_CLOSED_on_a_board_that_states_no_turn` pins it."""
    return body.is_active and not model.mine.attack_blocked


def _survives_to_spend(model: "StateModel", body) -> float:
    """How much of this body's FUTURE I still own, in [0, 1] — ``1 - halve(turns_to_ko_me - 1)``.

    The complement of `survival`'s own grade, on the same clock through the same
    :func:`_survival_clock` call, so the two families cannot come to disagree about when a body
    dies. No new curve and no new constant: `survival` grades a body's exposure by
    ``halve(turns_to_ko_me - 1)`` — undiscounted when they can Knock it Out this coming turn, an
    eighth of the worry at three turns — and this is one minus that number.

    **It reads as an exact statement rather than as a smoothing at the end that matters.** A clock
    of 1 means they Knock the body Out on their very NEXT turn, and the forward leg is a payoff that
    lands on one of MY later turns — which comes after theirs. So a forward payoff on a body with a
    clock of 1 is never spent, and `1 - halve(0) == 0.0` says so. At 2 the body survives to act once
    more and the grade is 0.5; the smoothing is in the middle of the curve, not at the end the
    measured frame turns on.

    **The zero is a priced zero, not a pruning one, and the distinction is the module's own.** A
    saturated term has no derivative and is never explored (see the constants block), so a factor
    that flattened a whole family would be a defect. This flattens ONE leg of ONE body: every play
    that arms that body THIS turn still moves the now-leg, and a play that only advances a doomed
    body's future arming genuinely buys nothing — 0 delta is the developer's ruling on that frame,
    not a term failing to notice. What the zero DOES leave unpriced is named in `readiness.blind_to`
    rather than left to be discovered.

    **Why this is not a double count against `survival`, argued rather than assumed** (Issue #332's
    first acceptance criterion). The two families price two different CONSEQUENCES of the one fact,
    in two different currencies: `survival` charges the body's ``prize_at_risk`` — the prizes handed
    over when it falls — and this discounts the body's ``payoff`` — the damage-denominated potential
    that dies with it. Removing the doomed body from the board would raise `survival` (less
    exposure) and lower `readiness` (lost potential), so the two readings are not one quantity added
    twice.

    The registry fact therefore stays `readiness_odds`, already in `readiness.reads`, and the clock
    is an INPUT to that probability exactly as `turns_to_afford` already is. This is `survival`'s own
    shipped precedent, applied to the mirror case: its `_predicted_loss` consults
    `their_prizes_remaining`, which `prize_race` owns, as a win-condition TEST rather than as race
    value, and keeps `predicted_loss` as the registry fact. **Splitting the clock into a second fact
    string to make the read visible is the move both places reject** — `sound_rules.SCHEDULED_PAIRS`
    records the same temptation and the same answer, because a fact renamed to dodge a detector makes
    the detector pass VACUOUSLY. `double_counted()` stays empty and means it."""
    return 1.0 - halve(_survival_clock(model, body) - 1)


#: The floor under an UNDECLARED body's role relevance, and it is derived rather than chosen: the
#: bottom rung of the shipped role ladder (`ROLE_TIER["tutor"]` 10.0) over
#: `currency.DEPLOY_WORTH_SCALE` (30.0). A body in play that the deck never declared a role for is
#: still a body — it soaks a Knock Out, it occupies the Active spot, it can swing — so pricing it at
#: exactly 0 would make `readiness` and `development` blind to half of a real board and would leave
#: every play onto it at 0 delta. The floor says "at least the least important declared job", which
#: is the weakest claim the shipped ladder can make rather than a new number.
_ROLE_FLOOR = ROLE_TIER["tutor"] / currency.DEPLOY_WORTH_SCALE


def _body_relevance(model: "StateModel", card_id, seen: set) -> float:
    """How much this body matters, discounted for being a repeat — :func:`_role_relevance` times
    :func:`_saturation`, in one place.

    `readiness` and `development` both need it and each keeps its OWN ``seen`` set, because they are
    independent readings of the board and sharing the bookkeeping would make the second family's
    answer depend on the first having run. What must not be duplicated is the EXPRESSION: two copies
    would let a saturation change land in one family and not the other, which is a divergence nothing
    would report."""
    return _role_relevance(model, card_id) * _saturation(model, card_id, seen)


def _role_relevance(model: "StateModel", card_id) -> float:
    """A card's role weight as a dimensionless [0, 1] ratio — `deploy_value._relevance`'s form.

    Reads `MySide.role_worth`, which is the deck's DECLARED opinion resolved once per model, so this
    and the deploy marginal cannot form different views of what a body is for. Roles are declaration,
    not card data (`card_worth.role_value`: "the Pilot supplies ``roles``"), which is why the model
    carries a resolver rather than this function reaching for a `CardStat` field that does not
    exist."""
    if currency.DEPLOY_WORTH_SCALE <= 0:
        return 0.0
    worth = model.mine.role_worth(card_id)
    return max(_ROLE_FLOOR, min(1.0, worth / currency.DEPLOY_WORTH_SCALE))


def _hand_legs(model: "StateModel") -> dict:
    """My hand as `hand` reads it — the `set_keep_v2` spine, through `MySide.needs`.

    Returns all-zero when no Needs resolution was supplied. That is a REAL zero rather than a
    hidden one: with no resolution there are no slots, so the hand covers nothing, and the
    alternative (re-resolving here) would put a second board→slots derivation in the codebase
    beside the Pilot's, which is the duplication `MySide.needs` exists to prevent."""
    resolution = model.mine.needs
    if resolution is None:
        return {"assignment_coverage": 0.0, "re_access": 0.0, "hand_worth": 0.0}
    re_access, coverage = resolution.split()
    return {"assignment_coverage": float(coverage), "re_access": float(re_access),
            "hand_worth": float(resolution.latent_worth)}


def _development_legs(model: "StateModel") -> dict:
    """My board's topology as `development` reads it, every leg already in prizes.

    * ``deploy_marginal`` — what the bodies IN PLAY are worth as development: each body's role
      relevance through `currency.deploy_relevance_to_damage`, the deploy marginal's own bridge,
      then across `PRIZE_DAMAGE_RATE`. Benching a body raises it, which is what makes a deploy
      price above zero under differencing.
    * ``evolve_marginal`` — the FORWARD payoff a line still OWES, through :func:`_forward_credit`:
      hop-discounted by `grading.halve` (the convention `EvolveBody.p_arrive` already uses) and
      crossed on :data:`_READINESS_W`, the same positional anchor `readiness` uses. That helper is
      shared with `threat`'s denial credit (Issue #285), which prices the SAME quantity from the
      other end of the board. The anchor is not decoration: forward payoff is
      printed damage held as POTENTIAL, exactly like readiness's, and pricing it at raw prize scale
      instead made this leg alone reach 0.5 prizes per Stage-2 line and saturate the family's guard
      on an ordinary board. Evolving raises it by consuming a hop; it reads the forward CLOSURE and
      `readiness` reads the CURRENT form, so the two never price one attack twice.
    * ``line_topology`` — is that forward form still ACCESSIBLE? A line whose only Stage-1 sits in
      the discard is topologically dead however well funded its base is, so this leg CANCELS the
      evolve credit for a dead line (`unseen_counts` is the sound "not provably gone" read the rest
      of the snapshot already uses) and is 0 for a live one. Expressed as a cancellation rather than
      as a bonus so that a line with nowhere to go contributes nothing at all rather than something
      slightly smaller.
    * ``bench_slot_price`` — the escalating COST of the Bench slots already consumed (Issue #232).

    Both board legs carry :func:`_saturation`, so a second copy of the same utility body prices as
    the near-duplicate it is. Sums where sets belong is the naivety `set_keep_v2` makes structurally
    impossible one seam over, and it has no business reappearing here.
    """
    mine = model.mine
    deploy = evolve = topology = 0.0
    seen: set = set()
    for b in mine.bodies:
        if b.card_id is None:
            continue
        relevance = _body_relevance(model, b.card_id, seen)
        deploy += currency.deploy_relevance_to_damage(relevance) / currency.PRIZE_DAMAGE_RATE
        forward = mine.forward_payoff(b.card_id)
        credit = _forward_credit(forward, relevance=relevance)
        if credit:
            evolve += credit
            if not forward.reachable:
                topology -= credit
    return {"deploy_marginal": deploy, "evolve_marginal": evolve, "line_topology": topology,
            "bench_slot_price": _bench_slot_price(len(mine.bench))}


def _bench_slot_price(occupied: int) -> float:
    """The escalating price of ``occupied`` Bench slots, in prizes (Issue #232).

    Slot *i* of `_BENCH_MAX` costs `_BENCH_SLOT_PRICE x halve(_BENCH_MAX - i)`, so the FIRST body
    onto an empty Bench pays a sixteenth of what the LAST one pays. That escalation is the whole
    point: the flat +60 `keep-a-bench` cliff it replaces priced a spare body at 1.96 on a non-empty
    Bench and 61.96 on an empty one, and the entire gap was the rung rather than the board.

    A CUMULATIVE price rather than a marginal one, because `state_value` scores a STATE: the board
    has already paid for every slot it occupies, and differencing recovers the marginal for free as
    the difference of two cumulative prices."""
    total = 0.0
    for i in range(1, min(int(occupied), _BENCH_MAX) + 1):
        total += _BENCH_SLOT_PRICE * halve(_BENCH_MAX - i)
    return total


# ── the term families — pure functions over RESOLVED plain numbers ────────────────────────────────
#
# The sub-seam, confirmed with the developer before this module was written. `state_value` takes the
# StateModel (so `apply_option` can feed it directly and it composes for sequences); each family
# below takes plain numbers, so the equations test the way `test_deploy_value.py` tests — no engine,
# no obs, no Pilot, no StateModel construction. The families are also exactly the `working` keys, so
# the breakdown falls out of the seam rather than being assembled beside it.


def prize_race(*, my_prizes_remaining: int, their_prizes_remaining: int) -> float:
    """The **Prize Race** leg: lead plus proximity, in prizes.

    Two facts, not one: a 2-prize lead at 5-vs-3 remaining is not the 2-prize lead at 2-vs-0, because
    proximity to zero is what converts a lead into a win. Reads the COUNTS only — what any individual
    body is worth when it falls belongs to `survival` or `threat`.

    **The lead leg has UNIT SLOPE, and that is load-bearing rather than a scaling choice.** Taking
    a prize moves this term by exactly 1.0, which is what makes the whole scalar prize-denominated
    and what preserves the incumbent leaf's dominant `KO_SCORE * prizes_taken` term across the swap.

    That unit slope is the yardstick `ko-score-band` is measured against — and the measurement is
    **not** the incumbent's. A positional family's absolute LEVEL can exceed a prize here (see the
    module header and `sound_rules.py`'s `ko-score-band` entry, which records the divergence and
    files it for a ruling); what cannot exceed a prize is a single play's positional DELTA, which is
    what the per-body bounds hold. Stated this way round because the older phrasing — "every
    positional family is capped well under 1.0" — is simply false of this implementation, and a
    docstring that asserts a retired invariant is worse than one that names the live one.

    Proximity is graded by `grading.halve`, the shipped decay convention, on prizes-still-to-take
    rather than a fresh curve: at one prize left the grade is 1.0, at six it is 1/32. It enters as
    a DIFFERENCE of the two sides' grades, so a symmetric race contributes nothing and only the
    asymmetry — the thing that actually distinguishes 5-vs-3 from 3-vs-1 — survives."""
    mine, theirs = int(my_prizes_remaining), int(their_prizes_remaining)
    lead = float(theirs - mine)
    proximity = halve(mine - 1) - halve(theirs - 1)
    return lead + _PROXIMITY_W * proximity


def survival(bodies: Iterable[ExposedBody], *, predicted_loss: bool = False) -> float:
    """My bodies' exposure, in prizes — **negative**, since it is what I stand to lose.

    ``bodies`` is one :class:`ExposedBody` per body across BOTH areas, Active and Bench.
    Each is graded by `common.grading.halve(turns_to_ko_me - 1)`: a body they can Knock Out THIS
    coming turn is undiscounted, and one they cannot reach for three turns is worth an eighth of the
    worry. `halve` is the shipped convention, reused rather than a new decay rate per equation.

    ``predicted_loss`` is the bench-empty doom (ADR-0064): my only Pokémon is a doomed Active, so the
    Knock Out ends the match (`docs/rules.md` §7 case 2). It is a TERMINAL term at -KO_SCORE scale,
    not a large positional one — the distinction `_LINE_CAP` exists to keep.

    **UNCAPPED, deliberately.** This is a forecast of real prize flow, not a positional read: a
    3-prize Mega ex they can Knock Out this turn genuinely costs three times what a 1-prize Basic
    does, and a cap set under a prize would erase exactly that distinction. The `ko-score-band`
    invariant is untouched — it says a POSITIONAL term never outbids a prize, and this term is
    denominated in prizes rather than in position.

    **The sum is RANK-GRADED, because they attack once.** `docs/rules.md` §3, verified at source:
    *"Attack — 1, and it ends the turn"* (rulebook L105-148). Each body's per-body clock is honest,
    but ADDING them at full weight claims the opponent knocks out every body whose clock reads 1 on
    the same turn, which the rules forbid. So the worst-exposed body is undiscounted, the next pays
    `halve(1)`, the third `halve(2)` — the shipped decay applied to the turn ordering the rulebook
    fixes, not a new dampening constant. Six 1-prize bodies all reachable now price 1.97 rather than
    6.0, and the bound on the whole term becomes ~2x the worst single body.

    This is a MEASURED failure, not a precaution. Ungraded, the term reached −4.5 prizes on ordinary
    corpus boards against a `development` leg of +0.4, so every deploy priced net-negative and the
    leaf preferred doing nothing on a develop turn. `planner._readiness` carries the identical fix on
    the mirror side, for the identical reason and with its own measurement: *"the rules allow ONE
    retreat per turn (rules.md §3), so only the single best benched attacker is 'nearly Active',
    never the whole bench (measured: a per-body lift multiplied across a loaded bench and overtook
    the human's attacker-in-front lines)"*.

    ``predicted_loss`` charges :data:`LOSS_PRIZES`, which is DERIVED to exceed the largest sum every
    other family can express, so it dominates by construction rather than by a transcribed −1.0 that
    two exposed ex bodies would quietly out-scale."""
    graded = sorted((float(b.prize_at_risk) * halve(int(b.turns_to_ko_me) - 1) for b in bodies),
                    reverse=True)
    exposure = sum(g * halve(rank) for rank, g in enumerate(graded))
    return -(exposure + (LOSS_PRIZES if predicted_loss else 0.0))


def threat(targets: Iterable[float]) -> float:
    """Their bodies' exposure to ME, in prizes — positive.

    ``targets`` is `needs.opponent_target_value` per opponent body over the Knock Outs I can actually
    reach. Reachability is the filter that keeps this from pricing a wish: an opponent body I have no
    line on contributes nothing, however valuable it would be.

    A plain SUM rather than a max-with-discount, matching the frozen composition. The bound that
    keeps it from becoming a wish is the reachability FILTER the caller applies, not an arithmetic
    one: their Active is reachable by printed damage, and a benched body only through the attack's
    snipe RIDER (Issue #284), so on most boards the sum has one term and it can never have more than
    six. CONVERTING any of them is still `attack_ev`'s at the terminal action; what this family
    prices is the exposure standing on the board (see its `blind_to`).

    **POSITIONAL, so SCALED then capped** — :data:`_THREAT_W` crosses the prize-denominated sum into
    the positional band, and :data:`_THREAT_CAP` (`planner._PLANNER_THREAT_CAP` 100 / `KO_SCORE`) is
    the runaway guard behind it. That band is where the my-side/their-side asymmetry described in the
    module header lives. Their exposure standing on the board is worth something — it constrains what
    they can afford to leave in front — but the PRIZE for converting it belongs to the attack that
    converts it, and `score(sequence) = state_value(end board) + EV(terminal)` would otherwise pay for
    one Knock Out twice.

    **The anchor is in FRONT of the cap and the cap is untouched** (Issue #329). Order is
    load-bearing rather than stylistic: :data:`POSITIONAL_MAX` sums the four positional caps and
    :data:`LOSS_PRIZES` is derived from that sum, so folding the anchor into `_THREAT_CAP` would move
    the predicted-loss dominance constant without anything saying so.

    The shape is ADR-0107's, CLAMP INCLUDED — that ADR's `gust_target` seam is
    `GUST_TARGET_BAND x min(1, otv / TARGET_VALUE_CEILING)`, and `min(_THREAT_CAP, _THREAT_W * sum)`
    is the same expression with the band factored out of the clamp. Worth stating because the
    fraction is written UNclamped in more than one prose record of this family.

    **The guard still bites, on 7.3% of non-empty corpus inputs, and that is not a residual defect.**
    This is a SUM over up to six targets while `_THREAT_W`'s divisor is a SINGLE target's ceiling, so
    reaching a 3-prize Mega ex and a 2-prize body at once sums to 5.0 — 1.28x the divisor. Five prizes
    of simultaneously-reachable exposure is the extreme board a runaway guard exists for. Do not write
    *"the cap never binds"* anywhere; it is measurably false."""
    return min(_THREAT_CAP, _THREAT_W * float(sum(float(t) for t in targets)))


def readiness(bodies: Iterable[ReadyBody]) -> float:
    """How close my board is to DOING something, in prizes.

    ``bodies`` is one :class:`ReadyBody` per body. Multiplicative, not additive:
    a huge payoff at zero odds is worth zero, and the shipped Attach-Budget / readiness-odds
    machinery already answers the odds question — this composes that answer rather than forming a
    second opinion about it.

    **Positional**, so the product crosses into the positional zone on :data:`_READINESS_W` — the
    shipped `planner._READINESS_ATTACK_W` carried at the same band — and is then bounded per body and
    in total by two runaway guards that do not bite in normal play. The scale is the term's meaning:
    readiness prices POTENTIAL, and the prize for actually swinging belongs to `attack_ev`.

    **Degrades gracefully on a HALF-BUILT body**, which Issue #263's ordering ruling makes a hard
    requirement: `payoff` is the body's printed line payoff and does not depend on what is attached,
    so a partly-funded attacker scores `payoff x odds x relevance` with odds strictly between 0 and
    1 — not zero, not full. A term that read "can it attack right now" instead would price every
    mid-turn board at 0 and prune every attach before the leaf could vindicate it.

    **Odds are FORWARD-LOOKING on both clocks** (Issue #332). `readiness_odds` asks whether the body
    gets to its payoff attack, and there are two ways not to: it never affords the cost
    (`turns_to_afford`), or the opponent removes it first (`turns_to_ko_me`, through
    :func:`_survives_to_spend`). Funding a body the opponent Knocks Out next turn therefore buys
    nothing forward, which is what stops this family preferring the body already in front to the
    successor being built behind it."""
    total = 0.0
    for body in bodies:
        contribution = (_READINESS_W * float(body.payoff)
                        * min(1.0, max(0.0, float(body.readiness_odds)))
                        * min(1.0, max(0.0, float(body.role_relevance))))
        total += min(_READINESS_BODY_CAP, contribution)
    return min(_READINESS_CAP, total)


def hand(*, assignment_coverage: float, re_access: float, hand_worth: float,
         worth_prize_rate: float | None = None) -> float:
    """What is still IN HAND, in prizes.

    ``assignment_coverage`` and ``re_access`` are the `set_keep_v2` spine — which live slots the hand
    can fill, and how readily the deck can hand me another. ``hand_worth`` is the Worth-denominated
    remainder, and ``worth_prize_rate`` (defaulting to :data:`POC_WORTH_PRIZE_RATE`) is the ONE place
    Worth crosses into prizes anywhere in this module.

    Pricing the hand at zero was considered and rejected: it makes every free Item strictly worth
    playing, which is the defect `_DENIAL_ITEM_COST` patched for Hammers and `common.hold_value`
    generalises (Issue #261 item 2f, discharging old Issue #212). This family is where that price
    stops being a seam-scoped constant: under differencing the card leaves `hand` and arrives in
    `readiness`/`development`, so the hold is the Worth this term loses — and
    :data:`POC_WORTH_PRIZE_RATE` is what `currency.ITEM_HOLD_WORTH_RATE` reconciles against, and
    they AGREE: composed through `PRIZE_DAMAGE_RATE` it reads 100 Worth per prize against this
    module's 120, inside the 20% an authored scaffold can honestly claim. The disagreement worth
    knowing about is a different one — `currency.GUST_TARGET_WORTH_RATE`, on the same scale pair and
    ~47x away — and it is settled by referent at :data:`POC_WORTH_PRIZE_RATE`, not by splitting.

    The three legs are `needs.assignment_split`'s two halves plus the resolver's latent remainder,
    so they are already disjoint by construction — `coverage` is what the HELD cards cover,
    `re_access` is what the closure re-supplies with no held card at all, and `latent worth` is the
    Worth of cards covering no specific slot. Summing them and crossing once is the whole equation;
    the DP that produced the first two is `set_keep_v2`'s, unchanged.

    **Bounded by a runaway guard, not by the incumbent's cap** — see :data:`_HAND_CAP` for why
    `pilot._HAND_READINESS_CAP` is deliberately not carried over: against the ratified rate it would
    bite below the Worth of one Basic Energy and price every card play at 0 delta.

    ``worth_prize_rate`` defaults to :data:`POC_WORTH_PRIZE_RATE` and is a PARAMETER rather than a
    module read so the scale-invariance test can re-point the yardstick and assert what does and does
    not move — the same discipline `test_deploy_value.py` applies to `DEPLOY_WORTH_SCALE`."""
    rate = POC_WORTH_PRIZE_RATE if worth_prize_rate is None else worth_prize_rate
    if not rate:
        return 0.0
    worth = float(assignment_coverage) + float(re_access) + float(hand_worth)
    return min(_HAND_CAP, max(0.0, worth) * float(rate))


def development(*, deploy_marginal: float, evolve_marginal: float, bench_slot_price: float,
                line_topology: float) -> float:
    """Board topology — bench and evolution lines, in prizes.

    ``bench_slot_price`` is the escalating cost of consuming an open Bench slot, and it is a COST:
    the marginal rises as slots deplete, so taking the last slot with a non-critical body is priced
    as the mistake it is rather than being flat until the Bench is full. Issue #232's spare-body
    cliff is what the flat form measured.

    All four legs arrive in PRIZES; the caller's extractor does the crossing, because each leg
    crosses on a different shipped bridge (the deploy marginal on `DEPLOY_BAND` / `DEPLOY_WORTH_SCALE`
    then `PRIZE_DAMAGE_RATE`, the evolve marginal on `PRIZE_DAMAGE_RATE` alone) and hiding two
    different conversions behind one signature is how a currency ends up with a fourth undocumented
    rate.

    :data:`_DEVELOPMENT_CAP` is a runaway guard applied to the SIGNED total, so a board that has
    over-spent its Bench can still score NEGATIVE development — a cost clipped at zero would make the
    last Bench slot free again, which is the cliff this family exists to remove."""
    return min(_DEVELOPMENT_CAP,
               float(deploy_marginal) + float(evolve_marginal) + float(line_topology)
               - float(bench_slot_price))


# ── the terminal-action term ──────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class AttackEV:
    """:func:`attack_ev`'s answer, with its sub-values named.

    A record rather than a bare float because Issue #263 shares this implementation across two
    trackers and both need the breakdown: the composer to explain why one attack beat another, and
    the wave-3 packet to show a human which leg carried a flip. Mirrors `DeployValue.working()`,
    which is the shipped shape for exactly this."""

    #: The prize value of the Knock Out, weighted by P(the damage lands it).
    knockout: float = 0.0
    #: Damage that does NOT knock out, carried at the currency rate — chip is progress, not nothing.
    chip: float = 0.0
    #: Snipe / spread rider value against THEIR board.
    riders: float = 0.0
    #: Effect-Clause economy riders (energy recycling and its relatives).
    economy: float = 0.0
    #: What a `nextTurnSelfLock`-class attack costs ME next turn. A COST: already subtracted.
    next_turn_cost: float = 0.0
    #: The sum. In prizes.
    total: float = 0.0

    def working(self) -> dict:
        return {"knockout": self.knockout, "chip": self.chip, "riders": self.riders,
                "economy": self.economy, "next_turn_cost": self.next_turn_cost}


def attack_ev(*, damage: float, target_hp: float, target_prizes: float,
              ko_probability: float = 1.0, rider_value: float = 0.0,
              economy_value: float = 0.0, next_turn_cost: float = 0.0) -> AttackEV:
    """**EV of the attack that ENDS the turn**, in prizes (Issue #263 § Terminal-action valuation).

    Attack and end-turn are TERMINAL — there is no post-attack board for the apply-seam to hand back
    — so `state_value(end board)` alone cannot tell two sequences apart when they differ only in
    their final action. The sequence score is therefore
    ``score = state_value(end board) + EV(terminal action)``, with ``EV(end-turn) = 0``, and this is
    that second summand.

    **An EXPECTATION, not a printed floor** — old Issue #145's amendment B made concrete.
    ``damage`` is the damage MODEL's answer (W/R applied, coin branches already averaged by the
    caller, self-damage and spread riders in ``rider_value``), and ``ko_probability`` carries the
    residual uncertainty a bound policy leaves. A certain printed hit is the degenerate case
    ``ko_probability=1.0``, which is why this shape absorbs a coin attack without an archetype
    branch — the point of stating attack value as a random variable in the first place.

    **Chip is credited, and strictly below the Knock Out band by construction**: damage that does not
    kill is still progress toward one, so it prices as the FRACTION of the target removed times what
    the target is worth. That is the same damage→prize crossing `PRIZE_DAMAGE_RATE` performs, taken
    against the actual body instead of against the card set's median HP-per-prize — sharper, and it
    makes "less than a Knock Out is worth less than a Knock Out" a fact about the arithmetic rather
    than a cap someone remembered to add. The median rate remains the fallback for an unreadable HP.

    ``next_turn_cost`` is a COST and is SUBTRACTED. A `nextTurnSelfLock`-class attack (Mega Lucario's
    Mega Brave — no Mega Brave next turn) buys damage now against a clock cost later, and an EV that
    omitted the second half would recommend it every time.

    Readiness is deliberately absent from the signature. Whether I can afford this attack at all is
    `readiness`'s question about the BOARD, and multiplying it in here would put the same
    probability into the same prize twice — the double-counting rule, one term over."""
    dmg, hp = max(0.0, float(damage)), max(0.0, float(target_hp))
    prizes, p_ko = max(0.0, float(target_prizes)), min(1.0, max(0.0, float(ko_probability)))
    if hp and dmg >= hp:
        knockout, chip = prizes * p_ko, 0.0
    elif hp:
        knockout = 0.0
        chip = prizes * (dmg / hp)
    else:                                   # unreadable HP: fall back to the median crossing
        knockout = 0.0
        chip = min(prizes, dmg / currency.PRIZE_DAMAGE_RATE)
    total = knockout + chip + float(rider_value) + float(economy_value) - float(next_turn_cost)
    return AttackEV(knockout=knockout, chip=chip, riders=float(rider_value),
                    economy=float(economy_value), next_turn_cost=float(next_turn_cost),
                    total=total)


# ── the coverage map, executable ──────────────────────────────────────────────────────────────────


def _all_families() -> tuple:
    """Both registries. The one-fact-one-family rule spans the state/terminal seam, so every
    coverage check below walks this rather than :data:`REGISTRY` alone — otherwise `attack_ev`
    could quietly re-price what `threat` already prices and no test would notice."""
    return REGISTRY + TERMINAL_REGISTRY


def blind_spots() -> dict:
    """``{family: (dimension — why it is uncovered, …)}`` — **the blind-spot checklist**.

    Issue #263's ordering ruling makes this a load-bearing deliverable rather than documentation.
    Under uniform 1-ply differencing a play that moves only state no family reads prices at exactly
    0 delta, and at ordering time 0 means *never explored* — not *undervalued*. So the composer needs
    to tell a genuine zero (nothing happened) from an uncovered one (something happened that nobody
    prices), and this is what it reads to do it.

    Distinct from :func:`registry_gaps`, which is bookkeeping over what families SAY about each
    other: a fact one family disclaims and another claims is fine, and a fact NOBODY has written
    down anywhere is invisible to it. These entries are the ones somebody had to notice."""
    return {f.name: f.blind_to for f in _all_families() if f.blind_to}


def registry_gaps() -> list[str]:
    """Facts some family declares it does NOT read and that NO family reads — the coverage holes.

    Empty is the contract. This is the double-counting rule's other half made executable: the rule
    forbids a fact entering twice, and this catches a fact entering zero times, which is the failure
    mode that looks like a working build (`a play that changes state no term reads prices 0`).

    **Known limitation, stated so it is not mistaken for coverage.** This is SELF-REFERENTIAL: it can
    only see facts somebody already typed into a ``does_not_read``. A board signal nobody wrote down
    anywhere is still invisible to it. The issue nominates the 2026-07-31 value-stack audit's
    Board-signal map as the real checklist, and reconciling this registry against that map is owed —
    T3 (Issue #262) does it as it implements each family, because that is the point at which a
    missing input actually bites. Until then, an empty result means "nothing DECLARED is orphaned",
    not "every board fact is priced"."""
    read = {fact for f in _all_families() for fact in f.reads}
    return sorted({fact for f in _all_families() for fact in f.does_not_read} - read)


def double_counted() -> list[str]:
    """Facts claimed by MORE than one family — the double-counting rule, executable.

    Empty is the contract (ADR-0092 §4-T0). The rule earned its enforcement: an empty Bench under a
    knock-outable Active reached the draft whitelist through THREE mechanisms at once, and nothing
    about writing that list prompted the question (ADR-0096)."""
    seen: dict[str, int] = {}
    for f in _all_families():
        for fact in f.reads:
            seen[fact] = seen.get(fact, 0) + 1
    return sorted(k for k, n in seen.items() if n > 1)


__all__: Sequence[str] = (
    "POC_WORTH_PRIZE_RATE", "LOSS_PRIZES", "WIN_PRIZES",
    "REGISTRY", "FAMILIES", "TERMINAL_REGISTRY", "TERMINAL_FAMILIES",
    "TermFamily", "ExposedBody", "ReadyBody", "AttackEV",
    "state_value", "prize_race", "survival", "threat", "readiness", "hand", "development",
    "attack_ev", "registry_gaps", "double_counted", "blind_spots",
)
