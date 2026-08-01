"""**State Value** — the ONE prize-denominated scalar for a board (POC-T3, contract frozen by
POC-T0 / Issue #259, ADR-0092).

`state_value(model)` answers *what is this position worth, in prizes?* Every play is then priced by
**differencing** it — `value(play) = state_value(after) − state_value(before)` — with `after`
produced closed-form by `common.apply_option`. One mechanism replaces ~60 hypothesis rungs.

**INERT.** This module is a frozen contract, not an implementation: T0 (Issue #259) ships the
registry, the signatures and the docstrings; T3 (Issue #262) fills the equations in. Every scoring
entry point raises `NotImplementedError` rather than returning a plausible zero, because an
unimplemented term that quietly prices 0 is indistinguishable from a term that correctly prices 0 —
and telling those apart is the entire job of the coverage map below.

## Unit basis

Prizes. Damage crosses on `currency.PRIZE_DAMAGE_RATE` (DERIVED — the median HP-per-prize over the
card set, recomputed from the CSV by `test_currency.py`). Worth crosses ONLY on
:data:`POC_WORTH_PRIZE_RATE`, the authored scaffold below.

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
`apply_option`'s own note and ADR-TEMP-259b decision 3. Information-first sequencing therefore stays
a structural rule on the whitelist (`_finish_turn_last`'s information-before-commitment boundary),
and is not a gap in this registry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

# Read through the MODULE, never by binding the names: `currency` is the one source for the derived
# bridges, and a `from currency import ...` would defeat the scale-invariance test that re-points the
# yardstick to prove the ratios are dimensionless (`deploy_value` makes the same argument).
from common import currency  # noqa: F401  (the contract's unit basis; consumed by T3)

#: **The Worth -> prize scaffold** (ADR-TEMP-259d, ratified wave 1). Damage-per-worth-point is the
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
#: **Reconciliation, recorded rather than hidden** (ADR-TEMP-259d decision 1). Converted to
#: damage-per-worth-point this must be stated against the three rates already catalogued in
#: `currency.py`, which disagree by ~6.7x among themselves:
#:
#:     trainer   TAG_TIER["gust"] 10.0  vs  _DENIAL_ITEM_COST 10       ~1.0
#:     energy    ENERGY_TIER      8.0   vs  ENERGY_RECOVER  160/3      ~6.7
#:     deploy    DEPLOY_BAND / DEPLOY_WORTH_SCALE = 25/30              ~0.83
#:
#: A value landing far outside that spread is evidence about the INCUMBENTS as much as about this
#: constant — ADR-0078's own rule. Whitelisted `authored-scaffold`; retires when a post-POC fit
#: against ruled spend-vs-hold frames converges.
#:
#: **The value itself is T3's** (Issue #262), authored with its reasoning recorded. `None` here is
#: the contract saying so: T0 approves the mechanism and its bindings, not a number.
POC_WORTH_PRIZE_RATE: float | None = None


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
    ),
    TermFamily(
        name="survival",
        reads=("prize_at_risk", "turns_to_ko_me", "bench_harvest", "predicted_loss"),
        does_not_read=("my_prizes_remaining", "readiness_odds"),
        composition="Sum over MY bodies, both areas, of prize_at_risk x halve(turns_to_ko_me - 1), "
                    "Bench-Harvest-aware. `_predicted_loss` (-KO_SCORE bench-empty doom, ADR-0064) "
                    "survives here as a TERMINAL term, outside the positional band by construction "
                    "— `_LINE_CAP` caps positional at 590 against KO_SCORE 1000, so a loss-avoidance "
                    "value cannot be both bounded under that band and un-outbiddable.",
    ),
    TermFamily(
        name="threat",
        reads=("opponent_target_value", "my_reachable_kos"),
        does_not_read=("turns_to_ko_me", "their_prizes_remaining"),
        composition="Their exposure to ME: per-body `needs.opponent_target_value` over the Knock "
                    "Outs I can reach. The mirror of `survival`, and the reason the two must not "
                    "both read a clock — `turns_to_ko_me` is THEIR clock on MY bodies.",
    ),
    TermFamily(
        name="readiness",
        reads=("body_payoff", "readiness_odds", "role_relevance"),
        does_not_read=("assignment_coverage", "bench_slot_price"),
        composition="Per-body payoff x readiness odds x role relevance, composed from the existing "
                    "Attach-Budget / readiness-odds / Needs machinery rather than a second opinion "
                    "about any of them.",
    ),
    TermFamily(
        name="hand",
        reads=("assignment_coverage", "re_access", "hand_worth"),
        does_not_read=("body_payoff", "deploy_marginal"),
        composition="Assignment coverage of LIVE slots plus re-access, on the `set_keep_v2` spine. "
                    "Its Worth-denominated part is the one place POC_WORTH_PRIZE_RATE crosses. A "
                    "card's value once PLAYED belongs to `readiness` or `development`; this family "
                    "prices it only while it is still in hand.",
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
    ),
)

#: Name -> family, for the `working` breakdown and for T3's dispatch.
FAMILIES: Mapping[str, TermFamily] = {f.name: f for f in REGISTRY}


def state_value(model, *, working: dict | None = None) -> float:
    """The board's worth **in prizes**. Higher is better for ME.

    ``model`` is a :class:`common.state_model.StateModel` — the SOLE data supplier, both sides
    (ADR-0092 standing ruling). Nothing here reads a raw observation or reaches for the Pilot.

    ``working``, when a dict is passed, is FILLED with the per-family breakdown ``{name: prizes}``.
    A caller-supplied dict rather than a second entry point or a wrapper type, for one reason: the
    Turn Planner evaluates this once per candidate sequence and must pay nothing for a diagnostic it
    is not reading, while a correction round wants the breakdown on the one frame it is disputing.
    Passing nothing costs nothing; the sum of a filled ``working`` equals the return value, asserted
    by test.

    **Incremental evaluation** rides the StateModel's existing lazy memo (ADR-0068 amendment A) —
    the model is the unit of caching, so a family re-reading an already-derived clock pays once per
    model, not once per call.

    Raises `NotImplementedError` until T3 (Issue #262). Returning 0.0 would be the worse stub: it is
    exactly what a correct-but-neutral position scores, so an unimplemented build would read as a
    working one right up until the ladder disagreed."""
    raise NotImplementedError("state_value is POC-T3 (Issue #262); T0 freezes the contract only")


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
    body is worth when it falls belongs to `survival` or `threat`."""
    raise NotImplementedError("prize_race is POC-T3 (Issue #262)")


def survival(bodies: Iterable[tuple[float, int]], *, predicted_loss: bool = False) -> float:
    """My bodies' exposure, in prizes — **negative**, since it is what I stand to lose.

    ``bodies`` is ``(prize_at_risk, turns_to_ko_me)`` per body across BOTH areas, Active and Bench.
    Each is graded by `common.grading.halve(turns_to_ko_me - 1)`: a body they can Knock Out THIS
    coming turn is undiscounted, and one they cannot reach for three turns is worth an eighth of the
    worry. `halve` is the shipped convention, reused rather than a new decay rate per equation.

    ``predicted_loss`` is the bench-empty doom (ADR-0064): my only Pokémon is a doomed Active, so the
    Knock Out ends the match (`docs/rules.md` §7 case 2). It is a TERMINAL term at -KO_SCORE scale,
    not a large positional one — the distinction `_LINE_CAP` exists to keep."""
    raise NotImplementedError("survival is POC-T3 (Issue #262)")


def threat(targets: Iterable[float]) -> float:
    """Their bodies' exposure to ME, in prizes — positive.

    ``targets`` is `needs.opponent_target_value` per opponent body over the Knock Outs I can actually
    reach. Reachability is the filter that keeps this from pricing a wish: an opponent body I have no
    line on contributes nothing, however valuable it would be."""
    raise NotImplementedError("threat is POC-T3 (Issue #262)")


def readiness(bodies: Iterable[tuple[float, float, float]]) -> float:
    """How close my board is to DOING something, in prizes.

    ``bodies`` is ``(payoff, readiness_odds, role_relevance)`` per body. Multiplicative, not additive:
    a huge payoff at zero odds is worth zero, and the shipped Attach-Budget / readiness-odds
    machinery already answers the odds question — this composes that answer rather than forming a
    second opinion about it."""
    raise NotImplementedError("readiness is POC-T3 (Issue #262)")


def hand(*, assignment_coverage: float, re_access: float, hand_worth: float,
         worth_prize_rate: float | None = None) -> float:
    """What is still IN HAND, in prizes.

    ``assignment_coverage`` and ``re_access`` are the `set_keep_v2` spine — which live slots the hand
    can fill, and how readily the deck can hand me another. ``hand_worth`` is the Worth-denominated
    remainder, and ``worth_prize_rate`` (defaulting to :data:`POC_WORTH_PRIZE_RATE`) is the ONE place
    Worth crosses into prizes anywhere in this module.

    Pricing the hand at zero was considered and rejected: it makes every free Item strictly worth
    playing, which is the defect `_DENIAL_ITEM_COST` patches for Hammers and Issue #212 generalises."""
    raise NotImplementedError("hand is POC-T3 (Issue #262)")


def development(*, deploy_marginal: float, evolve_marginal: float, bench_slot_price: float,
                line_topology: float) -> float:
    """Board topology — bench and evolution lines, in prizes.

    ``bench_slot_price`` is the escalating cost of consuming an open Bench slot, and it is a COST:
    the marginal rises as slots deplete, so taking the last slot with a non-critical body is priced
    as the mistake it is rather than being flat until the Bench is full. Issue #232's spare-body
    cliff is what the flat form measured."""
    raise NotImplementedError("development is POC-T3 (Issue #262)")


def registry_gaps() -> list[str]:
    """Facts some family declares it does NOT read and that NO family reads — the coverage holes.

    Empty is the contract. This is the double-counting rule's other half made executable: the rule
    forbids a fact entering twice, and this catches a fact entering zero times, which is the failure
    mode that looks like a working build (`a play that changes state no term reads prices 0`)."""
    read = {fact for f in REGISTRY for fact in f.reads}
    return sorted({fact for f in REGISTRY for fact in f.does_not_read} - read)


def double_counted() -> list[str]:
    """Facts claimed by MORE than one family — the double-counting rule, executable.

    Empty is the contract (ADR-0092 §4-T0). The rule earned its enforcement: an empty Bench under a
    knock-outable Active reached the draft whitelist through THREE mechanisms at once, and nothing
    about writing that list prompted the question (ADR-TEMP-259c)."""
    seen: dict[str, int] = {}
    for f in REGISTRY:
        for fact in f.reads:
            seen[fact] = seen.get(fact, 0) + 1
    return sorted(k for k, n in seen.items() if n > 1)


__all__: Sequence[str] = (
    "POC_WORTH_PRIZE_RATE", "REGISTRY", "FAMILIES", "TermFamily", "state_value",
    "prize_race", "survival", "threat", "readiness", "hand", "development",
    "registry_gaps", "double_counted",
)
