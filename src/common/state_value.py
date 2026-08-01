"""**State Value** — the ONE prize-denominated scalar for a board (POC-T3, contract frozen by
POC-T0 / Issue #259, ADR-0092).

`state_value(model)` answers *what is this position worth, in prizes?* Every play is then priced by
**differencing** it — `value(play) = state_value(after) − state_value(before)` — with `after`
produced closed-form by `common.apply_option`. One mechanism replaces ~60 hypothesis rungs.

**IMPLEMENTED by T3 (Issue #262).** T0 (Issue #259) shipped the registry, the signatures and the
docstrings; this module now carries the equations. Nothing here invents math: every family is a
composition of an already-FIRING equation (survival off `turns_to_ko_me` + Bench Harvest, threat off
`needs.opponent_target_value`, readiness off the Attach-Budget / `readiness_p` machinery, hand off
`needs.set_keep_v2`, development off the deploy/evolve marginals, prize_race off `PrizeRace`), and
where a coverage gap remains it is NAMED in :attr:`TermFamily.blind_to` rather than priced at a
silent zero.

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
construction instead of by a hopeful constant.

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
#: the three incumbents rather than dropped in beside them:
#:
#:     deploy    DEPLOY_BAND / DEPLOY_WORTH_SCALE = 25/30   0.833 dmg/worth   <- ANCHOR
#:     trainer   TAG_TIER["gust"] 10.0 vs _DENIAL_ITEM_COST 10   1.0          agrees within 20%
#:     energy    ENERGY_TIER 8.0 vs ENERGY_RECOVER 160/3         6.67         DISAGREES ~8x
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
_THREAT_CAP = 0.1

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
                    "VALUES of individual bodies are deliberately absent here.",
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
                    "Bench-Harvest-aware. `_predicted_loss` (-KO_SCORE bench-empty doom, ADR-0064) "
                    "survives here as a TERMINAL term, outside the positional band by construction. "
                    "The band is the SUM of the positional caps (readiness 300 + survival 50 + "
                    "threat 100 + value 40 + line 100 = 590) against KO_SCORE 1000, of which "
                    "`_LINE_CAP` is the line term's 100 (`strategy/planner.py`) — a loss-avoidance "
                    "value cannot be both bounded under that band AND un-outbiddable, so it is "
                    "neither.",
        blind_to=(
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
        reads=("opponent_target_value", "my_reachable_kos"),
        does_not_read=("turns_to_ko_me", "their_prizes_remaining"),
        composition="Their exposure to ME: per-body `needs.opponent_target_value` over the Knock "
                    "Outs I can reach. The mirror of `survival`, and the reason the two must not "
                    "both read a clock — `turns_to_ko_me` is THEIR clock on MY bodies.",
        blind_to=(
            "bench-reachable Knock Outs (snipe / spread riders) — reachability here is my Active's "
            "best reachable damage against a body's remaining HP, which only ever reaches their "
            "ACTIVE. A snipe line onto their benched wincon prices 0 in this family BY DESIGN: it "
            "is an ATTACK's rider, and `attack_ev` prices it at the terminal action.",
            "their Energy denial / resource strip — removing fuel lengthens their clock without "
            "removing a body, and `opponent_target_value` prices bodies. `deny_relevance` is the "
            "instrument and is still dark (T2 / Issue #228 arms it).",
            "their hand and deck — `theirs.hand_size` and `theirs.deck_count` have suppliers and "
            "no reader, so hand disruption (a Judge, a discard effect) prices exactly 0. This is "
            "the single largest uncovered family; T4 must always-expand disruption plays.",
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
                    "about any of them.",
        blind_to=(
            "who is ACTIVE — `readiness_p` is per body and area-aware through the Attach Budget, "
            "but nothing here prices the Active SLOT itself, so a retreat that puts the right body "
            "in front moves this family only through the Budget. `promote_retreat_value` is the "
            "instrument and composes into `survival`; the retreat allowance itself is an OWED "
            "snapshot zone (T1).",
            "Ability readiness — the incumbent leaf scored attack and Ability CO-EQUALLY "
            "(`planner._ability_readiness`, `_READINESS_ABILITY_VALUE`). Nothing in the model "
            "supplies an Ability payoff, so an evolve whose whole point is switching an engine "
            "Ability on prices only its attack payoff. The largest single regression risk in this "
            "swap, and named here so T4 reads it as a gap rather than a verdict.",
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
            "board is scored, which is every call Issue #263's 1-ply ordering makes.",
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
    model, not once per call.

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
    mine, theirs = model.mine, model.theirs
    race = model.prize_race
    terms = {
        "prize_race": prize_race(my_prizes_remaining=race.my_prizes_remaining,
                                 their_prizes_remaining=race.opp_prizes_remaining),
        "survival": survival(_exposed_bodies(model), predicted_loss=_predicted_loss(model)),
        "threat": threat(_reachable_target_values(model)),
        "readiness": readiness(_ready_bodies(model)),
        "hand": hand(**_hand_legs(model)),
        "development": development(**_development_legs(model)),
    }
    if working is not None:
        working.update(terms)
    return float(sum(terms.values()))


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
    silently ask the solo-body question for six bodies."""
    bench_raws = model.mine.bench_raws
    opp_active = model.theirs.active_raw
    return tuple(
        ExposedBody(prize_at_risk=float(b.prize_value),
                    turns_to_ko_me=int(model.theirs.turns_to_ko_me(
                        b.body, my_benched=not b.is_active, my_bench=bench_raws,
                        opp_active=opp_active)))
        for b in model.mine.bodies)


def _predicted_loss(model: "StateModel") -> bool:
    """The bench-empty doom (ADR-0064, whitelisted `predicted-loss`): my only Pokémon is a doomed
    Active, so the Knock Out ends the match (`docs/rules.md` §7 case 2).

    ``evo_min_energy=1`` is ADR-0064's bounded-pessimism guard carried over verbatim — an
    evolution-based Knock Out counts only off a pre-evolution that ALREADY carries Energy, because a
    bare 0-Energy pre-evo is not a credible next-turn game-ender. Dropping it would make this rung
    fire on boards the incumbent leaves alone, which is a behaviour change disguised as a port."""
    active = model.mine.active
    if active is None or not active.hp_remaining or model.mine.bench:
        return False
    return model.theirs.reachable_incoming(active.body, evo_min_energy=1) >= active.hp_remaining


def _reachable_target_values(model: "StateModel") -> tuple:
    """Their bodies as `threat` reads them: `needs.opponent_target_value` over the Knock Outs I can
    actually reach THIS turn.

    Reachability is `best_reachable_damage` (my Active, under its full Attach Budget) against the
    target's remaining HP — the shipped affordability oracle, not a second opinion about it. Only
    their ACTIVE is reachable by damage at all; a benched body needs a snipe rider, which is an
    attack's property and belongs to `attack_ev` (see `threat`'s `blind_to`).

    ``survival_shift=0`` is the fail-closed answer to a missing supplier, named in `blind_to` rather
    than hidden: the shift is a Δ of `turns_to_ko_me` under REMOVAL of the body and the model exposes
    no removal-delta route. `phase` is still threaded honestly, so the term sharpens with the race
    exactly as `phase_scale` says it should once the shift becomes readable."""
    target = model.theirs.active
    if target is None or not target.hp_remaining:
        return ()
    if model.mine.best_reachable_damage(model.mine.active) < target.hp_remaining:
        return ()
    race = model.prize_race
    phase = _needs.phase_scale(race_ahead=None,
                               opp_prizes_remaining=race.opp_prizes_remaining)
    return (_needs.opponent_target_value(prize_advance=float(target.prize_value),
                                         survival_shift=0, phase=phase),)


def _ready_bodies(model: "StateModel") -> tuple:
    """MY bodies as `readiness` reads them.

    * ``payoff`` — the body's PRINTED line payoff (`CardStat.maxDamage`) in prizes. The body's own
      form, deliberately: what a FORWARD form would achieve is evolution topology and belongs to
      `development`, and reading the forward closure here would price one fact in two families.
    * ``readiness_odds`` — `readiness_p` asked about the body's PAYOFF attack, not about "any
      attack". The distinction is load-bearing and not pedantry: pairing a max-damage payoff with
      the any-attack (famine) probability saturates the term for every real attacker, and a
      saturated term has zero derivative, so the attach that completes the payoff cost would price
      at 0 delta and never be explored. See `BodyView.payoff_attack`.
    * ``role_relevance`` — `role_value` normalised by `DEPLOY_WORTH_SCALE`, which is exactly
      `deploy_value._relevance`'s dimensionless ratio. Composed rather than re-derived so a role
      re-tier moves both instruments together."""
    out = []
    seen: set = set()
    for b in model.mine.bodies:
        stat = b.stat
        if stat is None:
            continue                       # unknown card: make no claim (the oracle's own direction)
        payoff = float(getattr(stat, "maxDamage", 0) or 0) / currency.PRIZE_DAMAGE_RATE
        if payoff <= 0.0:
            continue
        out.append(ReadyBody(payoff=payoff,
                             readiness_odds=_readiness_odds(model, b),
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


def _readiness_odds(model: "StateModel", body) -> float:
    """P(this body gets to its payoff attack) — `readiness_p` OR the forward clock, whichever is
    better, and the `or` is the part that matters.

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
    the clock or raise the odds, so it can only raise this."""
    now = model.mine.readiness_p(body, body.payoff_attack)
    arm = model.mine.turns_to_afford(body)
    forward = 0.0 if arm is None else halve(arm)
    return max(0.0, min(1.0, max(now, forward)))


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
    * ``evolve_marginal`` — the FORWARD payoff a line still OWES, hop-discounted by `grading.halve`
      (the convention `EvolveBody.p_arrive` already uses) and crossed on :data:`_READINESS_W`, the
      same positional anchor `readiness` uses. The anchor is not decoration: forward payoff is
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
        if forward.hops > 0 and forward.owed_damage > 0.0:
            credit = (_READINESS_W * (forward.owed_damage / currency.PRIZE_DAMAGE_RATE)
                      * halve(forward.hops) * relevance)
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
    one: in practice only their Active is reachable by damage at all, so the sum has one or two
    terms — a benched body is reachable only through a snipe rider, which `attack_ev` prices at the
    terminal action and this family deliberately does not (see its `blind_to`).

    **POSITIONAL, so capped** at :data:`_THREAT_CAP` (`planner._PLANNER_THREAT_CAP` 100 /
    `KO_SCORE`), which is where the my-side/their-side asymmetry described in the module header
    lives. Their exposure standing on the board is worth something — it constrains what they can
    afford to leave in front — but the PRIZE for converting it belongs to the attack that converts
    it, and `score(sequence) = state_value(end board) + EV(terminal)` would otherwise pay for one
    Knock Out twice."""
    return min(_THREAT_CAP, float(sum(float(t) for t in targets)))


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
    mid-turn board at 0 and prune every attach before the leaf could vindicate it."""
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
    :data:`POC_WORTH_PRIZE_RATE` is what `currency.ITEM_HOLD_WORTH_RATE` reconciles against.
    ⚠️ **They do not reconcile yet:** `ITEM_HOLD_WORTH_RATE / currency.PRIZE_DAMAGE_RATE`
    is `1.0 / 100.0`, against this module's authored `1/120` — a 20% gap, recorded at
    :data:`POC_WORTH_PRIZE_RATE` rather than silently split.

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
    "POC_WORTH_PRIZE_RATE", "LOSS_PRIZES",
    "REGISTRY", "FAMILIES", "TERMINAL_REGISTRY", "TERMINAL_FAMILIES",
    "TermFamily", "ExposedBody", "ReadyBody", "AttackEV",
    "state_value", "prize_race", "survival", "threat", "readiness", "hand", "development",
    "attack_ev", "registry_gaps", "double_counted", "blind_spots",
)
