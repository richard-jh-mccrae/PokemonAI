"""**The choice node** — the boards a Deferred-Target Option can reach (POC-T4/5, Issue #392, under
the seam contract ADR-0098 froze at POC-T0; ruling: ADR-0121).

Three modules now answer *"what board does this option produce?"*, and they differ by the KIND of node
the option is:

======================================  ====================================================  ========
module                                  question                                              node
======================================  ====================================================  ========
`common.board_delta`                    what would the board be if I did this?                point
`common.board_expectation`              what distribution does this reveal produce?           chance
**`common.board_choice`** (this)        what boards can this option's deferred target reach?  choice
======================================  ====================================================  ========

`common.apply_option` still owns the CONTRACT — the frozen :class:`~common.apply_option.OutcomeClass`
/ :class:`~common.apply_option.Expectation` shapes are REUSED here, not re-invented — and this module
owns the ARITHMETIC, exactly as its two siblings do.

**Still INERT at runtime.** `runtime.PROFILE["deferred_target_expansion"]` ships **False**; Issue
#385's composer arms it. `board_expectation` shipped on the same principle, and for the same reason:
the parity lane and both ADR-0072 gates must see the seam they saw at Issue #382 until the consumer
that changes decisions actually exists.

## The defect this exists to delete

Issue #263 § *The ordering heuristic* rules that the sequence composer prices **every** option
identically: *"apply the single option through the seam, evaluate `state_value` on the result, rank by
that delta."* One scorer at 1 ply and n ply alike. It cannot price a retreat.

A `_RETREAT` option is the bare ``{"type": 12}`` — **5807 of 5807** offered options across the
committed parity corpus, **146 of 146** in the corrections corpus both ADR-0072 gates replay
(`board_delta._retreat`, measured 2026-08-04). The engine spends ``current.retreated`` and poses the
rest as separate selects: `_DISCARD_ENERGY` (context 30) for the cost, then `_SWITCH` (context 3) for
the promotion. So `board_delta._retreat` writes ``frozenset({"allowance_retreat_used"})`` — the only
allowance-ONLY write-set in that module — and a retreat's 1-ply delta is the allowance bit alone,
which against a board-reading leaf is a near-zero. Issue #263's own amendment rules what a near-zero
at ordering time means: *"a 0 delta at ordering time means **never explored**, not undervalued."*

**Retreat is one member of a measured class, and the census is what turned a fix into an
architecture.** `board_delta.py`'s `_play` records **63** further `_PLAY` steps whose write's target
*"is chosen at a follow-up select, so the `_PLAY` option does not determine it — structurally the same
case as `_RETREAT`"*: Boss's Orders ×30 (poses `_SWITCH` ctx 3), Crispin ×16 (`_TO_HAND` ctx 7),
Wally's Compassion ×14 (ctx 17), Rosa's Encouragement ×2 (ctx 22).

**This is NOT a clause-coverage gap, and the distinction is load-bearing.** All four cards are
`covers: "full"`, and `snapshot_coverage.CLAUSE_SELECTORS["target"]` already records the target
**class** (`any`, `any_pokemon`, `basic`, `benched`, `stage2`, …). What is absent is the target
**instance**, which only the board supplies. Issue #300's `covers: partial` is the orthogonal failure
— *we do not know the whole card*; this one is *we know the whole card and not which body*. The class
had two incoherent fates for one shape: a `_PLAY` REFUSED *loudly* (Issue #263: *"a one-action
terminal candidate flagged as a coverage gap … never silently dropped"*), while a `_RETREAT` priced
~0.0 and was pruned **silently**. That asymmetry, not the retreat, is the defect.

A structural beam whitelist was the cheaper route and was REJECTED: it buys *presence* without
*comparability* — the retreat's 1-ply score stays wrong and the composer ranks on it, which breaks
*"the SAME scorer runs at 1 ply and n ply"* for one kind. Expansion dissolves the bug instead: there
is no ~0-scored retreat left to admit.

## Choice semantics, and why the container is reused rather than re-invented

:func:`deferred_target` returns an `Expectation`. Every `OutcomeClass.probability` is
``1 / len(the FULL enumeration)`` — the denominator is the class count BEFORE the cap, exactly as
`board_expectation` normalises its availability weights over the full pool before capping. Two
consequences, and both are the point:

* ``total_probability`` is **1.0 on a complete enumeration** and falls below it by exactly the
  truncated share otherwise, so a capped enumeration cannot read as a complete one. A denominator
  taken over the KEPT classes would sum to 1.0 while classes were being dropped, which is the "no
  silent caps" failure.
* **The composer takes the `max` over ``classes``, never** :meth:`~common.apply_option.Expectation.expected`.
  This is not a new rule. `Expectation.expected`'s own docstring already states it: *"For a **choice**
  node the true value is the **max**, so this is a strict LOWER bound"* and *"The composer (Issue
  #385) takes the max over `classes`."* A chance node's probabilities are what nature does; a choice
  node's are a uniform prior over decisions the PLAYER makes, and averaging over decisions one gets
  to pick would price a menu at its mean.

`board_delta._retreat` **does not change.** It stays allowance-only and parity-honest, because
modelling a swap the engine did not perform diverges from the recorded native trace on the very next
frame and the trace is the reference (ADR-0098). `board_delta.transition`'s MAIN-menu gate (`context
!= CONTEXT_MAIN` refuses; measured at 14 580 of 14 581 modelled steps) is precisely why this is a
separate module and not a widening of that one.

## Both of a retreat's deferred dimensions, because there are two

`docs/rulebook.txt` L142: *"you must discard 1 Energy from your Active Pokémon for each [C] listed in
its Retreat Cost"* — **no type restriction**. L143: the retreating body keeps *"all damage counters
and all attached cards"* on reaching the Bench. So when attached Energy exceeds the Retreat Cost,
**which** Energy to shed is a real choice deciding the benched body's future readiness, and the engine
poses it as `_DISCARD_ENERGY` ctx 30. The target space is therefore a PRODUCT — ``(discard set ×
promoted body)`` — and it collapses to one class whenever ``attached == cost`` or the Retreat Cost is
0, structurally rather than by a special case: ``C(n, n)`` and ``C(n, 0)`` are both 1.

`promote_retreat_value.RetreatSide.build_after` already resolved that dimension — *"the greedy
cheapest-to-lose typed choice, retreat slots being colourless so the set is genuinely ours to pick"* —
a criterion chosen when A's future was not being searched. **It is DEMOTED here from answer to
ranker** (ADR-0100 amendment, ADR-0121 decision 5), so expansion leads with the greedy set and
simply does not stop there.

## What the engine actually does, read off the traces rather than recalled

Verified on the committed parity corpus (`alakazam_9000` f10→f14, `alakazam_9001` f7→f10,
`alakazam_9002` f10→f13), by walking each `_RETREAT` past its ctx-30/ctx-3 selects to the first frame
back at MAIN for the same seat:

* the retreating body and the promoted body **SWAP IN PLACE** — A lands on exactly the Bench index the
  promoted body vacated (`alakazam_9001`: bench[2] was promoted, and A is bench[2] afterwards);
* A keeps its ``hp``, its ``tools`` and its ``preEvolution`` (L143), and loses ONLY the discarded
  Energy cards, which are appended to my discard;
* ``current.retreated`` flips True.

The remaining ``energies`` are RE-DERIVED from the Energy cards that survive, through
`board_delta.units_for_cards`, never by subtracting units: the provision is a property of the HOLDER
as well as of the card (Ignition Energy is {C} on a Basic and {C}{C}{C} on an Evolution), so a
hand-kept subtraction would be a second model of that derivation.

Special Conditions are cleared, because `docs/rulebook.txt` L143 says so in the same breath — *"When
your Active Pokémon goes to your Bench (whether it retreated or got there some other way), some things
do go away—Special Conditions and any effects from attacks."* That leg is `board_delta.clear_conditions`,
the same function the evolve transition already uses, so the two cannot disagree about the clause.

## The class identity, and why it is a PAIR of fingerprints

`option_equivalence.option_fingerprint` on the POST-choice observation, over **both** bodies the
choice moved: the promoted body now in the Active Spot, and the retreated body at its new Bench index.
A fingerprint over the Active alone would call two candidates that promote the same body but discard
DIFFERENT Energy one class, which is precisely the dimension this module exists to open.

Reading `option_fingerprint`'s own shape is what makes the pair sufficient rather than merely
plausible: it emits ``(type, seat, [(area, card-state-minus-serial)])`` and the *index* is deliberately
absent, so two identical benched Riolu promoted from slots 0 and 1 yield the identical pair — one
class, which is right, because the resulting boards are the same multiset. `serial` is the only field
it ignores (ADR-0091), so hp, attached Energy, tools, `preEvolution` and `appearThisTurn` all split.

## The Target Rankers prefilter; `state_value` decides

Target spaces are products. Enumerate, rank with closed-form math, expand only the top-*m* through the
leaf. This is the role Issue #263 § *Consequence* sanctions for the retiring deciders — *"optionally
as pruning approximations"*, never an independent source of truth — and a kind with no registered
ranker falls back to expand-all in a deterministic order under the same cap.

``m`` is :data:`~common.board_expectation.BRANCH_CAP` (12), **reused, not a second constant**. A choice
node and a chance node cost the same thing — leaf evaluations on one option — so they take the same
cap, and the `composer-budget-caps` whitelist entry Issue #385 owes covers both. That entry does
**not exist yet**; stated as owed rather than implied, so a reader grepping `sound_rules.py` for the
name and finding nothing knows why. Truncation is REPORTED via `Expectation.truncated`, never silent.

## Parent-slot beam accounting (the consumer's half, recorded here because it sizes this module)

An expanded family holds **ONE** beam slot, taken by its best child. Expansion is an evaluation-time
fan-out, not a candidate-generation fan-out: the composer scores every class, takes `argmax`, and
emits one candidate carrying ``(parent_option, chosen_target, score)``. Beam width `k` therefore keeps
its pre-expansion meaning, so Issue #263 § *Beam-quality package*'s epsilon band and item-3 margin
telemetry keep meaning what that issue says they mean and `k` needs no re-derivation. Flat competition
was rejected for silently redefining `k`; a per-family quota `q` for adding a width parameter the
required telemetry cannot report on. The accepted loss — the *second*-best target is unreachable at
this node — is bounded by the follow-up select's REPLAN rather than silent.

## One evaluator at both sites: the follow-up select REPLANS

*(ADR-0100 amendment, ADR-0121 decision 6.)* When the engine poses the `_SWITCH` /
`_DISCARD_ENERGY` / `_TO_HAND`, the composer re-decides through this identical ranker + `state_value`
machinery, over the real board. ADR-0100's three call sites collapse to one evaluator at a different
layer than that ADR describes.

**The honest reason, because the obvious one is false.** For a retreat, **nothing changes** between the
option and the `_SWITCH`: the discard touches only A, every ``promote_value(B)`` term reads B (ADR-0100
§9 — the A-side terms are *"CONSTANT across destinations"*), nothing is revealed, and the opponent
cannot act during our turn. A commitment would provably agree. The argument is that **Crispin already
breaks commitment today** — *"Search your deck for up to 2 Basic Energy cards of different types,
**reveal them**"* — and Issue #263 § *Commutative-block collapse* names a revealing play a block
boundary. Census: retreat, Boss's Orders, Wally's Compassion and Rosa's Encouragement reveal nothing
(Rosa's attaches from the public discard); Crispin reveals. Commitment makes coherence a **standing
per-member proof obligation** over a vocabulary that will grow, failing as a legal, plausible, wrong
pick with no error anywhere. Replanning makes it **structural**, and `tools/train/choice_parity.py` is
what proves the two sites agree rather than asserting it.

## What is buildable now, and what is registered-but-refused

**`_RETREAT`, both dimensions** — it is already a MODELLED kind (`board_delta.TRANSITIONS[_RETREAT]`),
so there is a real transition to build on.

**The four `_PLAY` members are not.** `board_delta._play` refuses any card whose `_clause_writes` union
is non-empty, and all three clause kinds write::

    CLAUSE_WRITES["gust"]  = {bodies_in_play, special_conditions, transient_grants}
    CLAUSE_WRITES["heal"]  = {damage_counters}
    CLAUSE_WRITES["accel"] = {attached_energy, my_discard_contents, my_deck_count, deck_odds}

**No issue currently owns applying them, and that is worth stating plainly rather than papering over.**
`board_delta._play`'s docstring forward-references *"Expectation / choice nodes in POC-T4/2 (Issue
#383)"* — but #383 shipped only **chance** nodes over `deck_odds`, gated by
`snapshot_coverage.REVEALING_CLAUSES = {"draw", "fetch"}`, so `gust`/`heal`/`accel` never reach it.
Issue #303 minted the `gust` clause KIND in the compendium, never the apply-seam transition. Walking
all seven POC-T4 sub-issues (#382-#388) plus the side issues (#392, #394, #400) finds none that scopes
it. **This is a real, unfiled gap between what that docstring promises and what exists.**

So `gust` carries a REGISTERED target space here — its class resolver runs, its Target Ranker
(:func:`gust_rank_key`) is built and graded — and :func:`deferred_target` refuses at the apply step
with that gap named. **The registry is built to accept the clause application once some future issue
lands it**, and `tests/strategy/test_board_choice.py` asserts the unreachability AND its cause, so a
reader cannot mistake a missing consumer for a missing decision.

**Note for whoever builds `accel`:** Crispin searches the deck but its clause kind is `accel`, and
`REVEALING_CLAUSES` is `{"draw", "fetch"}` only — so Crispin is **not** currently routed as a reveal
despite revealing. It is simultaneously a chance node and a choice node. Out of scope here; recorded
so it is tripped over rather than discovered.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import NamedTuple, NoReturn

from common import (board_delta, board_expectation, currency, needs, retreat_cost,
                    snapshot_coverage)
from common.board_delta import Unmodellable
from common.option_equivalence import AREA_ACTIVE, AREA_BENCH, option_fingerprint
from common.promote_retreat_value import PromoteBody, PromoteRetreatInputs, promote_value
from common.scouting.matchup_plan import ROLE_REGISTRY
from common.strategy.context import _PLAY, _RETREAT

#: Option kinds whose target is STRUCTURALLY deferred — the engine's own resolution poses it at a
#: follow-up select, with no clause involved. `_RETREAT` is the one such member: it carries no card
#: and therefore no Effect Clause, so it is keyed by option kind rather than by clause kind.
CHOICE_KINDS: frozenset[int] = frozenset({_RETREAT})

#: Clause kinds whose write has a deferred target — the 63-step census `board_delta._play` records.
#: Declared as the CLASS vocabulary; :data:`CHOICE_REGISTRY` is what says which members have a
#: resolver built and which have a board synthesis. A member declared here with neither is a
#: recorded census entry, not a silent omission — see this module's header.
CHOICE_CLAUSES: frozenset[str] = frozenset({"gust", "heal", "accel"})

@dataclass(frozen=True)
class ChoiceKind:
    """Every leg of ONE deferred-target key, declared together (see :data:`CHOICE_REGISTRY`).

    ``space``       — ``(model, option, *, seat_index) -> tuple`` of legal target instances.
    ``canonical``   — ``(model, candidate, *, seat_index) -> hashable``: the equivalence ``space``
                      enumerates one representative of. NOT the class fingerprint; see
                      :func:`_retreat_space` for why the two vocabularies both exist.
    ``rank``        — ``(model, candidate) -> float``, sorted DESCENDING, or None to enumerate in the
                      space resolver's own deterministic order under the same cap.
    ``apply``       — ``(model, candidate, *, seat_index) -> (observation, written zones)``, or None
                      when no board synthesis exists for this key.
    ``fingerprint`` — ``(observation, candidate, *, seat_index, kind) -> tuple``, the ADR-0091 class
                      identity taken on the POST-choice board.
    ``no_applier``  — why ``apply`` is None, for the telemetry line. Required whenever it is."""

    space: object
    canonical: object
    rank: object = None
    apply: object = None
    fingerprint: object = None
    no_applier: str = ""

    def __post_init__(self):
        if (self.apply is None) != (self.fingerprint is None):
            raise ValueError("`apply` and `fingerprint` are one capability in two halves — a board "
                             "nothing can fingerprint joins no class, and a fingerprint over a board "
                             "nothing writes has nothing to take")
        if self.apply is None and not self.no_applier.strip():
            raise ValueError("a key with no board synthesis must say WHY — the message is destined "
                             "for the telemetry line and the modelling backlog, which groups by it")


#: The `needs.opponent_target_value` ceiling — `MAX_PRIZE_VALUE` (3) + `_SURVIVAL_CAP` (0.9). The
#: yardstick that lets a prize-denominated marginal be read as a dimensionless `[0, 1]` relevance,
#: which is what `currency.tiebreak_bonus` requires of its input. Read from `needs`, never restated:
#: it is a fact about that module's own equation and moves with it.
TARGET_VALUE_CEILING = needs.TARGET_VALUE_CEILING


# ── the D7 combination: `value` and `role_priority`, on one sort key ───────────────────────────────


def role_span(registry: dict | None = None) -> float:
    """``max(abs(priority))`` over the CLOSED role registry — the normaliser that maps an ordinal role
    priority into ``[-1, 1]``.

    DERIVED from `matchup_plan.ROLE_REGISTRY` on every call, never transcribed — the CLOSED role
    vocabulary Issue #395 D2 shipped, a ``{role: Role}`` map whose ordinal is ``Role.priority``.
    1.0 on an empty or all-zero registry, so the division is total and a degenerate sheet contributes
    exactly nothing rather than raising inside an ordering loop.

    **Deriving it rather than transcribing it is the whole point, and the rebase proved it.** Issue
    #395 merged to `main` while this work was in flight and did exactly what a transcribed constant
    could not survive: it moved the table from a private ``_ROLE_PRIORITY`` to this public registry,
    added `attacker` (50) and `enabler` (40), and gated `avoid` on prize value. A hardcoded 100 would
    have been silently stale; the derivation absorbed the change with no edit to the arithmetic and no
    change to the D7 guarantee, because that guarantee is stated over ``max(abs(·))`` rather than over
    any particular row.

    ``registry`` overrides the shipped sheet with a plain ``{role: priority}`` mapping. It exists so
    the property that matters — *a sheet gaining a LARGER magnitude widens the span, or the
    ``|role / span| <= 1`` bound the D7 proof rests on stops holding* — can be asserted against a
    hypothetical FUTURE sheet without reaching across a module boundary into `matchup_plan`'s
    internals."""
    sheet = ({name: role.priority for name, role in ROLE_REGISTRY.items()}
             if registry is None else registry)
    return max((abs(float(p)) for p in sheet.values()), default=0.0) or 1.0


def gust_rank_key(rows, *, registry: dict | None = None):
    """One sort key for a whole opponent-target MENU: `value`, tie-broken by `role_priority`.

    ``rows`` is `pilot._opponent_target_rows`' full candidate list — the menu, not one row — because
    the quantum is a property of the menu rather than of any row on it. Returns
    ``Callable[[dict], float]``; sort **descending**.

    ## The mechanism, reused rather than invented

    `currency.tiebreak_bonus(relevances, k)` is *"half the finest distinction a menu of `[0,1]`
    relevance values actually draws, in SCORE units… the shared arithmetic behind **BOTH** relevance
    instruments' lexicographic tiebreaks — deny's (ADR-0084) and snipe's (ADR-0085 Amendment H)"*. Its
    contract requires ``k × relevance`` to BE the instrument's score. Here the score **is** ``value``,
    so ``relevance = value / CEIL`` and ``k = CEIL`` gives ``k × relevance = value`` exactly, and the
    quantum comes back in the same prize-equivalent units: ``0.5 × (smallest real gap in value)``, or
    ``0.5 × CEIL × (1/CEIL) = 0.5`` prize-equivalents when the menu is perfectly flat.

    **No rate is invented**, which is `pilot.py`'s governing rule for mixing a MatchupPlan priority
    into a differently-denominated score (*"Only the SIGN travels … so no rate is invented to map a
    damage-scale MatchupPlan priority into the `[0,1]` band (ADR-0065's no-fudge rule)"*) and
    ADR-0065's no-fudge rule generally.

    ## The guarantee, and why it is the right semantics rather than a convenient one

    Let ``g`` be the smallest real gap in ``value`` on the menu, so ``quantum = 0.5g``. Because
    :func:`role_span` is ``max(abs(·))``, ``|role_priority / span| <= 1`` for every declared role and
    any future one. Take rows A and B with ``value_B = value_A + g`` (the tightest real difference),
    worst case A taking the largest positive role leg ``a`` and B the largest negative one ``b``::

        key(B) - key(A) >= g - 0.5g(a + b) > 0    for any a, b <= 1 with a + b < 2

    **A role can never reorder two rows whose `value` differs.** It orders *only* exact ties. Issue
    #395 D1 rules the sheet an **ordinal priority, never a worth**, on the strength of a shipped test
    (`tests/strategy/test_needs.py`'s `ROLE_TIER` ⊆ `SUPPLIES` lint); a formula that let a role flip a
    real `value` difference would be treating the ordinal as a worth, which is exactly what D1 forbids.
    It also targets the measured population: Issue #398 closed leaving **139 of 343 equal-prize groups
    perfectly flat** — *exact* ties, which is what a tiebreak breaks — because `incoming` is a per-turn
    maximum, so a non-leading body's removal Δ is a **Structural Zero** at any resolution. And when
    every value on the menu is identical the ``1/k`` fallback fires and ordering becomes **purely** the
    role ladder, which is the bench case `_opponent_target_rows`' own comment says *"still ranks almost
    nothing."*

    ``role_priority`` is `pilot._opponent_target_rows`' own leg — `MatchupPlan.priority(cid)` attached
    beside `prize_advance` / `survival_shift` / `value`, deliberately UNFUSED so that each consumer
    combines. **Issue #395 D7 shipped it to `main` while this work was in flight**, and this is that
    combination, its first composer consumer.

    The ``0.0`` default is kept and is not a placeholder: it is exactly what an UNROLED body
    contributes on a live row (`role_priority` resolves through the closed vocabulary's own
    `.get(role, 0)`), so one key orders a menu whose rows carry the field and a menu whose rows
    predate it, identically. That is what let this ranker be written and graded before Issue #395
    merged, and absorb its arrival with no edit. `MatchupPlan.priority` is already γ-scaled for
    matchup provenance and γ-independent for general card facts, so an unrecognised opponent (γ=0)
    silently contributes only the derived tier. Nothing extra to handle."""
    ceil = float(TARGET_VALUE_CEILING)
    values = [float((r or {}).get("value", 0.0)) for r in (rows or ())]
    quantum = currency.tiebreak_bonus([v / ceil for v in values], k=ceil) if values else 0.0
    span = role_span(registry)

    def key(row: dict) -> float:
        return float((row or {}).get("value", 0.0)) \
            + quantum * (float((row or {}).get("role_priority", 0.0)) / span)
    return key


# ── refusals ──────────────────────────────────────────────────────────────────────────────────────


def _no(what, why) -> NoReturn:
    """Raise the seam's one refusal, in the seam's one convention — ``"<subject>: <what is missing>"``
    (`apply_option.EngineResolved.clause_gap`). The message is destined for the telemetry line and the
    modelling backlog, which is grouped by exactly this string."""
    raise Unmodellable(f"{what}: {why}")


def _my_active(obs: dict, seat_index: int) -> dict | None:
    """My Active body on ``obs``, or None. One spelling, because three call sites wanted it and a
    fourth would have grown a fourth `next(...)` walk."""
    return next((b for b in (_my_side(obs, seat_index).get("active") or ()) if b), None)


def _after_discard(model, body: dict, discard_idx) -> tuple:
    """``(the body minus the discarded Energy cards, the cards that went)``.

    **ONE derivation, because two callers need it and they must not disagree**: the RANKER prices the
    Build Standing A keeps, and the APPLIER writes the board A lands on — and if those two computed
    the surviving Energy differently, the prefilter would be ordering boards the synthesis never
    produces. Spelling it twice is the drift `board_delta.units_for_cards`' own docstring says that
    function exists to prevent, one level up.

    The surviving ``energies`` are RE-DERIVED from the cards that remain rather than subtracted,
    because the provision is a property of the HOLDER as well as of the card (Ignition Energy is {C}
    on a Basic and {C}{C}{C} on an Evolution)."""
    cards = list(body.get("energyCards") or ())
    drop = {int(i) for i in discard_idx}
    kept = [c for i, c in enumerate(cards) if i not in drop]
    stat = model.card_stat(body.get("id"))
    after = dict(body, energyCards=kept, energies=board_delta.units_for_cards(
        model.combat, kept, onto_evolution=getattr(stat, "evolvesFrom", None) is not None))
    return after, [c for i, c in enumerate(cards) if i in drop]


def _my_side(obs: dict, seat_index: int) -> dict:
    """My `PlayerState` on ``obs``, or a refusal. None rather than an IndexError anywhere near the
    ordering hot path — a raise there is a forfeited grader match over an option we merely could not
    resolve."""
    players = ((obs.get("current") or {}).get("players")) or []
    if not 0 <= seat_index < len(players) or not players[seat_index]:
        _no(f"seat {seat_index}", "this snapshot carries no player at that seat")
    return players[seat_index]


# ── the choice key: which registry entry an option routes to ──────────────────────────────────────


def choice_key(model, option: dict, *, seat_index: int):
    """The registry key this option's deferred target routes under — an option KIND (int) for a
    structural deferral, or a clause KIND (str) for a card's.

    Refuses anything with no deferred target at all, so a caller cannot silently get an
    expand-everything answer for a point transition. The clause branch keeps `board_expectation`'s
    two symmetrical refusals for the same reason it does: a card with several deferred-target clauses
    is a CONJUNCTION the vocabulary cannot distinguish from a disjunction, and a card carrying a
    non-deferred clause as well has writes this node does not place."""
    kind = int((option or {}).get("type", -1))
    if kind in CHOICE_KINDS:
        return kind
    if kind != _PLAY:
        _no(f"option kind {kind}",
            "no deferred target — its whole effect is determined by the option itself, so it is a "
            "point transition (`board_delta`) or a chance node (`board_expectation`), not a choice")
    obs = model.source_obs
    hand = _my_side(obs, seat_index).get("hand") or ()
    index = (option or {}).get("index")
    if not isinstance(index, int) or not 0 <= index < len(hand):
        _no(f"play of hand index {index!r}", f"this snapshot cannot resolve it (hand of {len(hand)})")
    card_id = (hand[index] or {}).get("id")
    stat = model.card_stat(card_id)
    name = getattr(stat, "name", "?")
    every = board_delta.card_clauses(model.combat, card_id)
    deferred = tuple(c for c in every if c.get("kind") in CHOICE_CLAUSES)
    if not deferred:
        _no(f"{card_id} {name}",
            "no clause with a deferred target — the compendium either determines this card's targets "
            "or has never heard of the card, and `()` is *undeclared*, never *writes nothing*")
    if len(deferred) > 1:
        _no(f"{card_id} {name}",
            f"{len(deferred)} deferred-target clauses — printed as a CONJUNCTION, and nothing in the "
            f"clause vocabulary distinguishes AND from OR, so a product over them would be a guess "
            f"about the card")
    if len(every) > len(deferred):
        _no(f"{card_id} {name}",
            "it carries a non-deferred clause as well, whose writes this node does not place — "
            "modelling three quarters of a card is what Issue #300's `_covers` verdict exists to "
            "prevent")
    return deferred[0].get("kind")


def has_deferred_target(model, option: dict, *, seat_index: int) -> bool:
    """Does this option defer its target to a follow-up select — the ROUTING question, as a boolean.

    `apply_option`'s dispatch has to ask before it commits to a shape, and it must not raise doing so:
    *"a raise on the ordering hot path is a forfeited grader match over an option we merely could not
    price"*. So :func:`choice_key`'s refusal is caught here.

    ⚠️ **Nothing is swallowed, and the reason is a property of where the refusals live rather than of
    this function.** `choice_key` refuses on three things — an unresolvable hand index, a CONJUNCTION
    of deferred-target clauses, a non-deferred companion clause — and each is a card whose `_PLAY`
    `board_delta._play` ALSO refuses, with its own sentence, because its `_clause_writes` union is
    non-empty. So a False here routes the option to a seam that then names the same gap on the
    telemetry line; it never prices the option at a silent 0.0. What would break that property is a
    deferred-target clause kind whose card `board_delta` can write — which is exactly the
    apply-seam gap this module's header records as unowned, and `tests/strategy/test_board_choice.py`
    asserts the non-empty write-set that keeps the property true today."""
    try:
        choice_key(model, option, seat_index=seat_index)
    except Unmodellable:
        return False
    return True


# ── the target CLASS resolver, driven by the compendium's declared vocabulary ─────────────────────
#
# ADR-0121 decision 2: *"Expansion is data-driven off the compendium's target vocabulary, never
# per-card. The class resolver reads `CLAUSE_SELECTORS["target"]` and its neighbours (`restriction`,
# `zone`, `source`); a hand-written expander per card hardcodes what is already data."*
#
# So the VOCABULARY is `snapshot_coverage`'s and this module declares only which of its members it can
# evaluate against a BOARD. That split is what keeps the two failure modes apart, and they are
# different work: a value the compendium never declared is vocabulary DRIFT (someone minted a selector
# nobody registered), while a declared value with no predicate here is a scoped GAP with a name.


def _stage(stat) -> str:
    """``CardStat.stage`` normalised — ``"basic"`` / ``"stage1"`` / ``"stage2"``, or ``""``.

    The `.lower()` is redundant against the real provider (`stage_from_card` already returns the
    canonical string) and is kept for the reason `Pilot._retreat_free_granted` keeps its own: the
    field crosses a provider boundary, and a cheap coercion beats a silent miss on an injected row."""
    return (getattr(stat, "stage", None) or "").lower()


class _BodyPlace(NamedTuple):
    """Where a candidate body sits — the facts a target class needs that its `CardStat` cannot say."""
    active: bool
    mine: bool


#: Declared `target` values this module can evaluate against a body in play, as
#: ``(CardStat, _BodyPlace) -> bool``. **A subset of `CLAUSE_SELECTORS["target"]` by construction**,
#: and `tests/strategy/test_board_choice.py` asserts the containment with a vacuity guard — a
#: predicate keyed by a value the compendium does not declare is dead code nothing else could catch.
#:
#: The stage legs read `CardStat.stage` — **the canonical field, not a second reading of it.**
#: `provider.stage_from_card` is *"the ONE derivation (Issue #408)"* and folds the engine's own
#: `CardData.basic` / `.stage1` / `.stage2` booleans into one string; its docstring rules out exactly
#: what an earlier draft of this table did: *"Not derived from `evolvesFrom`: that is exact on today's
#: pool but it is a second READING — inferring a printed stage from an evolution name — where the
#: booleans are the engine's answer."* Measured before switching: the two agreed on **every** Pokémon
#: in the pool, so this is a provenance fix rather than a behaviour change.
#:
#: FAIL-CLOSED on a missing `stage`: a body whose stage cannot be read matches no stage class, which
#: narrows a target space rather than widening it. That direction matters — an unknown narrowing read
#: as *no* narrowing is the one failure that silently hands a clause every body on the board.
BODY_PREDICATES = {
    "any":             lambda stat, place: True,
    "pokemon":         lambda stat, place: bool(getattr(stat, "is_pokemon", False)),
    "any_pokemon":     lambda stat, place: bool(getattr(stat, "is_pokemon", False)),
    "basic":           lambda stat, place: _stage(stat) == "basic",
    "basic_pokemon":   lambda stat, place: _stage(stat) == "basic",
    "evolution":       lambda stat, place: _stage(stat) in ("stage1", "stage2"),
    "stage1":          lambda stat, place: _stage(stat) == "stage1",
    "stage2":          lambda stat, place: _stage(stat) == "stage2",
    "mega":            lambda stat, place: bool(getattr(stat, "megaEx", False)),
    "pokemon_ex":      lambda stat, place: bool(getattr(stat, "is_ex_body", False)),
    "tera":            lambda stat, place: bool(getattr(stat, "tera", False)),
    "benched":         lambda stat, place: not place.active,
    "bench_only":      lambda stat, place: not place.active,
    "opponent_active": lambda stat, place: place.active and not place.mine,
}

#: Declared `target` values that name a CARD class rather than a body in play — `basic_energy`,
#: `item`, `supporter` and friends. Listed rather than merely absent from :data:`BODY_PREDICATES`, so
#: the refusal can say *"that class is not a body"* instead of *"unimplemented"*: they are not work
#: owed here, they are a category error for a space over bodies, and a backlog that conflated the two
#: would size work that does not exist.
_CARD_CLASS_TARGETS = frozenset({
    "basic_energy", "energy", "item", "own_line", "own_type", "stadium", "supporter", "tool",
    "trainer", "future",
})

#: Clause keys the class resolver honours. Anything else refuses, fail-closed against vocabulary
#: drift — the same discipline `board_expectation._HANDLED_FETCH_KEYS` keeps for its own node. The
#: neighbours ADR-0121 decision 2 names are here; `zone` and `source` are absent because they
#: select a CARD ZONE, and a body already in play is in no such zone.
_HANDLED_TARGET_KEYS = frozenset({"kind", "target", "target_type", "restriction"})

#: `restriction` values this resolver can evaluate. `mega_only` is Wally's Compassion's.
_RESTRICTIONS = {
    "mega_only":   lambda stat, place: bool(getattr(stat, "megaEx", False)),
    "active_only": lambda stat, place: place.active,
}


def target_predicate(clause: dict):
    """``(CardStat, _BodyPlace) -> bool`` for one clause's declared target class, or a refusal.

    The whole of ADR-0121 decision 2 in one function: the vocabulary is the compendium's, the
    evaluation is this module's, and the three ways it can fail are three DIFFERENT sentences —
    vocabulary drift, a category error, and a scoped gap — because they are three different pieces of
    work and a backlog grouped by one message could not tell them apart."""
    unknown = sorted(set(clause) - _HANDLED_TARGET_KEYS)
    if unknown:
        _no(f"clause {clause.get('kind')!r}",
            f"key(s) {unknown} are not in this resolver's handled set — fail closed against "
            f"vocabulary drift, exactly as `board_expectation._check_clause` does for its own")
    declared = snapshot_coverage.CLAUSE_SELECTORS["target"]
    target = clause.get("target")
    if target is not None and target not in declared:
        _no(f"target {target!r}",
            "not a value `snapshot_coverage.CLAUSE_SELECTORS['target']` declares — the compendium "
            "grew a selector nobody registered, so nothing here can know what it means")
    if target in _CARD_CLASS_TARGETS:
        _no(f"target {target!r}",
            "names a CARD class, not a body in play — a target space over bodies cannot evaluate it, "
            "and that is a category error rather than an unbuilt predicate")
    if target is not None and target not in BODY_PREDICATES:
        _no(f"target {target!r}",
            "is declared vocabulary this resolver has no board predicate for yet — a scoped gap, not "
            "drift and not a category error")
    legs = [BODY_PREDICATES[target]] if target is not None else [lambda stat, place: True]
    restriction = clause.get("restriction")
    if restriction is not None:
        if restriction not in snapshot_coverage.CLAUSE_SELECTORS.get("restriction", ()):
            _no(f"restriction {restriction!r}", "not a declared `restriction` selector value")
        if restriction not in _RESTRICTIONS:
            _no(f"restriction {restriction!r}",
                "is declared vocabulary this resolver has no board predicate for yet")
        legs.append(_RESTRICTIONS[restriction])
    energy_type = clause.get("target_type")
    if energy_type is not None:
        legs.append(lambda stat, place: getattr(stat, "energyType", None) == energy_type)

    def match(stat, place) -> bool:
        # Fail CLOSED on an unreadable body: a class we cannot evaluate must not silently widen to
        # *every* body, which is the direction `combat._accel_target_ok` also refuses.
        return stat is not None and all(leg(stat, place) for leg in legs)
    return match


# ── target spaces ─────────────────────────────────────────────────────────────────────────────────


def _retreat_space(model, option: dict, *, seat_index: int) -> tuple:
    """A retreat's product space: ``((discarded energy-card indices), promoted bench index)``.

    Both dimensions, per ADR-0121 decision 5. The Energy leg collapses to ONE member whenever
    ``attached == cost`` or the Retreat Cost is 0 — structurally, because ``C(n, n)`` and ``C(n, 0)``
    are both 1, rather than by a special case that could drift from the claim.

    Identical Energy CARDS are collapsed here, on their ids — an ``energyCards`` entry is
    ``{id, serial, playerIndex}`` and `serial` is the one field ADR-0091's fingerprint ignores, so two
    copies of the same Energy card ARE one choice, and this bounds the product at the number of
    DISTINCT attached Energy cards rather than at ``C(attached, cost)``.

    ⚠️ **It is not merely an optimisation — the post-synthesis fingerprint provably cannot do this
    one, and the measurement is why.** `option_fingerprint` compares a body's card lists by VALUE
    including their ORDER. Removing entries 0 and 1 versus entries 0 and 6 from
    ``[P, P, {other}, P, P, P, P, P]`` leaves the same multiset in a different order, so the two
    fingerprint differently while being the same game state — measured at `boomer_9001` f39, Mega
    Zygarde ex holding eight Energy at Retreat Cost 2. No canonical removal fixes it either: the
    ENGINE's own pick among identical cards is arbitrary and lands in that same order, so a
    canonicalised synthesis would then disagree with the recorded board.

    So the two collapses coexist and answer different questions, which is why neither subsumes the
    other: **this one** asks *"is discarding this card or that identical one the same CHOICE?"*, in the
    option's own coordinates, where the answer is a card fact; **the fingerprint** asks *"do these two
    choices reach the same BOARD?"*, which is ADR-0091's declared class identity and is what collapses
    two indistinguishable benched bodies. `tools/train/choice_parity.py` checks enumeration in the
    first vocabulary (:func:`candidate_class`) and the arithmetic in the second."""
    obs = model.source_obs
    me = _my_side(obs, seat_index)
    active = _my_active(obs, seat_index)
    if active is None:
        _no("retreat", "no readable Active body on my side, so nothing is leaving the Active Spot")
    bench = list(me.get("bench") or ())
    slots = tuple(i for i, b in enumerate(bench) if b)
    if not slots:
        _no("retreat", "my Bench is empty, so the engine's `_SWITCH` poses no choice — and a retreat "
                       "with nowhere to promote to is not a legal play (`docs/rulebook.txt` L142)")
    cost = retreat_cost.effective_retreat_cost(
        active, stat_of=model.card_stat, my_bodies=[b for b in ([active] + bench) if b],
        combat=model.combat)
    cards = list(active.get("energyCards") or ())
    if cost > len(cards):
        _no(f"retreat of {active.get('id')}",
            f"its Retreat Cost reads {cost} but only {len(cards)} Energy cards are attached, so the "
            f"engine that OFFERED this option is applying a free-retreat grant `common.retreat_cost` "
            f"cannot see (measured: Ethan's Magcargo 356, *'If this Pokémon has no Energy attached, "
            f"it has no Retreat Cost'* — a self-Ability shape nothing parses). Refuse rather than "
            f"enumerate a space that cannot be paid")
    seen, discards = set(), []
    for combo in itertools.combinations(range(len(cards)), cost):
        ids = tuple(sorted((cards[i] or {}).get("id") for i in combo))
        if ids in seen:
            continue
        seen.add(ids)
        discards.append(combo)
    return tuple((d, j) for d in discards for j in slots)


def _gust_space(model, option: dict, *, seat_index: int) -> tuple:
    """A gust's space: the opponent in-play bodies its clause's declared target CLASS names.

    *"Switch in 1 of your opponent's Benched Pokémon to the Active Spot"* — Boss's Orders (1182),
    quoted from `data/EN_Card_Data.csv`. The clause KIND supplies the SCOPE (a gust reaches across the
    table, and switching in a body already Active is not a move); the `target` SELECTOR narrows within
    it, through :data:`BODY_PREDICATES` — never a per-card branch, which is what ADR-0121 decision
    2 rules out.

    Registered and exercised even though :func:`deferred_target` cannot synthesize the resulting board
    (see the header): the class resolver and :func:`gust_rank_key` are the two halves that ARE
    buildable, and proving them now is what makes the future clause application a wiring change."""
    obs = model.source_obs
    players = ((obs.get("current") or {}).get("players")) or []
    them = players[1 - seat_index] if len(players) > 1 else None
    if not them:
        _no("gust", "this snapshot carries no opponent side to reach across to")
    clause = _clause_of(model, option, seat_index=seat_index)
    match = target_predicate(clause)
    return tuple(i for i, b in enumerate(them.get("bench") or ())
                 if b and match(model.card_stat(b.get("id")), _BodyPlace(active=False, mine=False)))


def _clause_of(model, option: dict, *, seat_index: int) -> dict:
    """The single deferred-target clause a `_PLAY` option carries. Re-resolved rather than threaded,
    because :func:`choice_key` already proved there is exactly one and this keeps each space resolver
    callable on its own."""
    obs = model.source_obs
    hand = _my_side(obs, seat_index).get("hand") or ()
    card_id = (hand[option.get("index")] or {}).get("id")
    return next(c for c in board_delta.card_clauses(model.combat, card_id)
                if c.get("kind") in CHOICE_CLAUSES)


def target_space(model, option: dict, *, seat_index: int) -> tuple:
    """The legal target INSTANCES, resolved from the declared target CLASS against the board.

    A product space returns tuples — for a retreat, ``(discard set, promoted bench index)``. Empty is
    never returned: a resolver that finds no instance refuses, because a zero-class Expectation is an
    un-enumerated effect whose ``expected()`` raises inside the ordering loop."""
    entry = CHOICE_REGISTRY.get(choice_key(model, option, seat_index=seat_index))
    if entry is None:
        _no(f"choice key {choice_key(model, option, seat_index=seat_index)!r}",
            "declared in `CHOICE_CLAUSES` as a member of the deferred-target census, but no target "
            "SPACE resolver is built for it (Issue #392 § Scope: `_RETREAT` is buildable now, the "
            "`_PLAY` members are not)")
    space = entry.space(model, option, seat_index=seat_index)
    if not space:
        _no(f"choice key {key!r}", "its target class resolves to no legal instance on this board")
    return tuple(space)


# ── Target Rankers ────────────────────────────────────────────────────────────────────────────────


def _build_standing(model, body: dict, payoff_id, damage: float) -> float:
    """``(matched / slots)^2 × damage`` — the convex TYPED build credit of ``body`` against a FIXED
    payoff attack (ADR-0070 §2's Build Standing).

    Through `CombatMath.matched_slots`, which is the matcher `reachable_attach` uses, so "fits" and
    "reaches" can never disagree: an Energy filling no slot earns ZERO build (off-type waste is
    emergent, never a separate colourless-blind boolean) and a colourless slot absorbs any type.

    The attack is fixed by the CALLER, on the pre-discard body, for `_attach_build_delta`'s own reason
    — *"the branch is chosen by the payoff attack's cost record, which no attach changes, so both legs
    always read the same way and the difference is exact."* Re-choosing it per candidate would let a
    discard silently re-target the attack it is being scored against.

    **0.0 when no cost record resolves**, deliberately: the Pilot's `_build_standing` falls back to a
    COUNT reading there, and a count is not damage. This value is summed with `promote_value`, which is
    damage, so a count fallback would mix scales inside one sort key. Making no typed claim leaves the
    discard dimension unordered and lets the promotion dimension rank alone — the fail-closed
    direction for a prefilter whose whole contract is that the leaf decides."""
    if payoff_id is None or damage <= 0:
        return 0.0
    matched, slots = model.combat.matched_slots(body, payoff_id)
    if not slots:
        return 0.0
    return ((float(matched) / float(slots)) ** 2) * float(damage)


def _promote_body(model, raw: dict) -> PromoteBody:
    """B's damage-currency reading, from the measurements a `StateModel` supplies.

    ADR-0100's equation is pure over measurements and the PILOT fills them; a choice node holds only
    the model, so it fills the terms the model owns and leaves the rest at their dataclass defaults.
    **Which ones, named rather than left to be discovered:**

    * filled — ``reach`` (`MySide.best_reachable_damage`), ``prizes`` (`BodyView.prize_value`),
      ``ko_active`` (`TheirSide.turns_to_ko_me`, the ACTIVE-area clock, which is where a promoted body
      arrives), ``opp_prizes_remaining`` (`TheirSide.prizes_remaining`);
    * left at defaults — ``wall_progress``, ``accel_units``, ``closure``, ``tempo_step``,
      ``denies_items``, ``takes_ko``, every one of which is a Board/objectives derivation the Pilot
      owns and the model does not expose.

    So this prices ``reach − exposure − fatal``: how hard B hits against how many prizes promoting it
    hands over, clock-graded. That is the load-bearing half of ADR-0100 and it is a **prefilter**, the
    role Issue #263 § *Consequence* sanctions — *"optionally as pruning approximations"*. ``ko_bench``
    is deliberately absent because it feeds only `preservation()`, an A-side term, and this call passes
    ``retreat=None`` per ADR-0100 §9.

    ``reach`` is read on B where it stands, on the BENCH. Its Attach Budget once Active is not modelled
    — an approximation, stated: `attach_budget` reads the body's area, and synthesizing the post-swap
    board to re-read it would cost exactly the leaf evaluation this prefilter exists to avoid."""
    view = model.mine.view_of(raw)
    return PromoteBody(
        reach=float(model.mine.best_reachable_damage(view)),
        prizes=int(getattr(view, "prize_value", 1) or 1),
        ko_active=int(model.theirs.turns_to_ko_me(raw)),
        opp_prizes_remaining=int(getattr(model.theirs, "prizes_remaining", 6) or 6),
    )


def rank_retreat(model, candidate) -> float:
    """A retreat candidate's prefilter score — **ADR-0100's own retreat equation, minus its constants**.

        retreat_option = max over bench B of promote_value(B) + preservation(A) − retreat_cost(A)

    ``retreat_cost(A)`` is ``build_before(A) − build_after(A)`` plus a resource premium, and
    ``preservation(A)`` and ``build_before(A)`` are CONSTANT across every member of this space — the
    first by ADR-0100 §9 (*"the A-side terms are constant across destinations"*), the second because A
    is the same body whatever it discards. A constant cannot change an ordering, so the score reduces
    to ``promote_value(B) + build_after(A | discard set)`` exactly. **No rate is invented and no term
    is re-weighted**: this is the shipped equation read as a ranking rather than as a value.

    That is also precisely what ADR-0121 decision 5's demotion means in code — `build_after` stops
    being the ANSWER to *which Energy goes* and becomes the KEY the discard dimension is ordered by, so
    the greedy cheapest-to-lose set still ranks first and expansion simply does not stop there.

    The resource premium (ADR-0069 §5c, charged on Worth above a reusable Basic) is NOT included: it is
    a sub-band tie-break scaled by a Pilot constant, and importing a decider's band into a common
    prefilter to order equals would buy nothing the leaf does not then settle."""
    discard_idx, promote_idx = candidate
    obs, seat = model.source_obs, int(model.my_index)
    active = _my_active(obs, seat)
    bench = list(_my_side(obs, seat).get("bench") or ())
    promo = promote_value(PromoteRetreatInputs(body=_promote_body(model, bench[promote_idx]))).total
    payoff = model.mine.attack_payoff(model.mine.view_of(active))
    after, _went = _after_discard(model, active, discard_idx)
    return float(promo) + _build_standing(model, after, payoff.attack_id, payoff.damage)


#: The prefilters, keyed by :func:`choice_key`'s answer: ``Callable[[model, candidate], float]``,
#: sorted DESCENDING. A key with no entry falls back to the space resolver's own deterministic order,
#: under the same cap — never to an unranked truncation.
#:
#: **`gust` is deliberately ABSENT rather than listed-and-empty.** Its ranker exists and is graded
#: (:func:`gust_rank_key`), but it takes a MENU of `pilot._opponent_target_rows` rows — `value`,
#: `prize_advance`, `survival_shift`, and the `role_priority` Issue #395 D7 shipped — and those rows are a
#: PILOT derivation over the Read, the Brief and the KO clock, none of which a `StateModel` exposes. So
#: the composer passes it in through ``ranker=`` at the call site that holds the rows; storing a
#: menu-shaped callable in a per-candidate registry would make every reader check which shape they got.
#: (Built from :data:`CHOICE_REGISTRY` below — one declaration, two names.)
TARGET_RANKERS: dict = {}


# ── board synthesis ───────────────────────────────────────────────────────────────────────────────


def _apply_retreat(model, candidate, *, seat_index: int) -> tuple:
    """``(post-choice observation, the zones it wrote)`` for one retreat candidate.

    Composed entirely from `board_delta`'s already-parity-verified public copy-on-write primitives —
    public since POC-T4/2 for exactly this reason — so the arithmetic inherits their guarantee and
    `tools/train/choice_parity.py` is left to check the COMPOSITION, which is where the risk is.

    The move is a SWAP IN PLACE, read off the traces (this module's header names the three frames): A
    lands on the Bench index the promoted body vacated, keeping its hp, tools and `preEvolution`
    (`docs/rulebook.txt` L143), and loses only the discarded Energy cards, which are appended to my
    discard (L78 — *"cards taken out of play go to the discard pile"*)."""
    discard_idx, promote_idx = candidate
    new_obs, current, players = board_delta.fork(model.source_obs)
    me = board_delta.fork_player(players, seat_index)
    actives = list(me.get("active") or ())
    bench = list(me.get("bench") or ())
    a = dict(actives[0])
    writes = {"allowance_retreat_used", "bodies_in_play"}

    if discard_idx:
        # The SAME derivation the ranker prices, so the prefilter cannot order a board this never
        # writes (`_after_discard`). `docs/rulebook.txt` L78 — the paid cards leave play.
        a, went = _after_discard(model, a, discard_idx)
        me["discard"] = list(me.get("discard") or ()) + went
        writes.update({"attached_energy", "my_discard_contents"})

    actives[0], bench[promote_idx] = bench[promote_idx], a
    me["active"], me["bench"] = actives, bench
    current["retreated"] = True                      # `docs/rules.md` §3 — one manual retreat a turn
    # `docs/rulebook.txt` L143 — a body reaching the Bench recovers from every Special Condition. The
    # same function the evolve transition uses, so the two cannot disagree about the clause.
    if board_delta.clear_conditions(me):
        writes.add("special_conditions")
    return new_obs, frozenset(writes)


def _fingerprint_retreat(after_obs: dict, candidate, *, seat_index: int, kind: int) -> tuple:
    """The class identity — `option_fingerprint` over BOTH bodies the choice moved.

    A pair rather than one string, and the header says why: the Active alone would call two candidates
    that promote the same body but discard different Energy one class, which is the dimension this
    module exists to open. `OutcomeClass.fingerprint` is declared a tuple for exactly this shape."""
    _discard_idx, promote_idx = candidate
    return tuple(option_fingerprint({"type": kind, "inPlayArea": area, "inPlayIndex": index,
                                     "playerIndex": seat_index}, after_obs)
                 for area, index in ((AREA_ACTIVE, 0), (AREA_BENCH, promote_idx)))


def _canonical_retreat(model, candidate, *, seat_index: int) -> tuple:
    """A retreat candidate's equivalence key — ``(sorted discarded card ids, promoted bench index)``.

    The coordinates :func:`_retreat_space` dedupes in, so two index tuples naming the same Energy
    cards key alike whichever copies the picker happened to name."""
    discard_idx, promote_idx = candidate
    cards = list((_my_active(model.source_obs, seat_index) or {}).get("energyCards") or ())
    return (tuple(sorted((cards[i] or {}).get("id") for i in discard_idx
                         if 0 <= int(i) < len(cards))), promote_idx)


def _canonical_identity(model, candidate, *, seat_index: int):
    """The candidate IS its own equivalence key — for a space whose members are already the distinct
    choices (a gust names one opposing body; there is no picker freedom to collapse)."""
    return candidate


#: **ONE registry entry per deferred-target key** — every leg of a key declared together.
#:
#: It was five parallel maps (space / ranker / apply / fingerprint / canonical / refusal-reason) kept
#: in sync by prose, which is the shape where a key gains a space and silently never gains a canonical
#: form. One record makes the sync obligation STRUCTURAL: adding a member is one literal, and a leg
#: nobody filled is a `None` a reader can see rather than an absence in a map they did not think to
#: check. The sibling modules each carry one dispatch table for the same reason
#: (`board_delta.TRANSITIONS`).
#:
#: ``apply``/``fingerprint`` are ``None`` for a key whose board synthesis does not exist, and
#: ``no_applier`` is why — spelled per key so the modelling backlog groups by an actionable sentence
#: rather than by "not implemented".
CHOICE_REGISTRY: dict = {
    _RETREAT: ChoiceKind(
        space=_retreat_space, canonical=_canonical_retreat, rank=rank_retreat,
        apply=_apply_retreat, fingerprint=_fingerprint_retreat),
    "gust": ChoiceKind(
        space=_gust_space, canonical=_canonical_identity,
        no_applier="`CLAUSE_WRITES['gust']` is non-empty ({bodies_in_play, special_conditions, "
                   "transient_grants}), so `board_delta._play` refuses the play and no apply-seam "
                   "transition writes those zones. The target SPACE and the Target Ranker are built "
                   "and graded; only the clause application is missing, and NO ISSUE CURRENTLY OWNS "
                   "IT (Issue #392 § Scope — Issue #383 shipped chance nodes gated on "
                   "REVEALING_CLAUSES, Issue #303 minted the clause kind)"),
}

TARGET_RANKERS.update({key: k.rank for key, k in CHOICE_REGISTRY.items() if k.rank is not None})


# ── the node ────────────────────────────────────────────────────────────────────────────────────────


def candidate_class(model, option: dict, candidate, *, seat_index: int) -> tuple:
    """The equivalence key ``candidate`` reduces to in :func:`target_space`'s own coordinates.

    Public for `tools/train/choice_parity.py`, which reads the target a trace records as TAKEN in raw
    index coordinates and must ask whether the enumeration REACHES it. Asking that on the raw tuple is
    wrong — the space enumerates one representative per equivalence, so the engine naming an equivalent
    other representative would read as an enumeration hole that is not one. See :func:`_retreat_space`
    for why this vocabulary exists beside the fingerprint rather than instead of it."""
    return CHOICE_REGISTRY[choice_key(model, option, seat_index=seat_index)].canonical(
        model, candidate, seat_index=seat_index)


def realise(model, option: dict, candidate, *, seat_index: int) -> tuple:
    """``(post-choice observation, class fingerprint)`` for ONE candidate — the per-candidate half of
    :func:`deferred_target`, exposed because two callers need it separately.

    `tools/train/choice_parity.py` is the reason it is public rather than an implementation detail:
    that lane holds the target a trace records as TAKEN and needs the board that instance produces, to
    diff against the recorded one. Reaching into `CHOICE_REGISTRY` for it would be the cross-module private
    reach `board_delta`'s own promotions exist to avoid.

    The candidate is realised **verbatim**, in its own coordinates — not through
    :func:`candidate_class` first. That matters for the lane: the engine's pick among identical Energy
    cards is arbitrary and shows up in the surviving ``energyCards`` order, so synthesizing the
    canonical representative instead would disagree with the recorded board on a difference the game
    does not make. Enumeration is checked in the equivalence vocabulary; arithmetic is checked here,
    on exactly what happened."""
    entry = CHOICE_REGISTRY[choice_key(model, option, seat_index=seat_index)]
    after_obs, _writes = entry.apply(model, candidate, seat_index=seat_index)
    return after_obs, entry.fingerprint(after_obs, candidate, seat_index=seat_index,
                                        kind=int((option or {}).get("type", -1)))


def deferred_target(model, option: dict, *, seat_index=None, context=None,
                    cap: int = board_expectation.BRANCH_CAP, ranker=None):
    """The boards this option's deferred target can reach — a CHOICE node, as an
    :class:`~common.apply_option.Expectation`.

    Mirrors `board_expectation.expectation`'s signature and contract: ``context`` defaults to the live
    select context on the model's own observation, ``seat_index`` to the model's seat, and ``cap`` to
    :data:`~common.board_expectation.BRANCH_CAP` — a parameter because the composer's budget is
    per-decision rather than global, and because truncation is otherwise untestable without a
    pathological board. It must be **>= 1**: a cap of 0 would return a zero-class Expectation, the
    shape the empty-space refusal exists to prevent, so it raises rather than manufacturing one.

    Every `OutcomeClass.probability` is ``1 / len(the full enumeration)`` and the composer takes the
    **max** over ``classes``, never ``.expected()`` — the header carries the epistemics. Classes are
    collapsed by `option_equivalence.option_fingerprint` on the POST-choice observation, so two
    identical benched bodies yield one class.

    Raises :class:`~common.board_delta.Unmodellable` for the caller to turn into a `Refusal` — the
    always-expand path, never a silently unchanged board.

    **Never mutates ``model``.** Every write lands on a fork; the planner holds the pre-state while it
    evaluates alternatives, and a node that edited in place would corrupt every sibling branch — the
    property the whole differencing scheme rests on."""
    from common.apply_option import Expectation, OutcomeClass          # contract, imported lazily

    if int(cap) < 1:
        raise ValueError(
            f"cap={cap!r}: a choice node must enumerate at least one class — a zero-class one is an "
            f"un-enumerated effect whose `expected()` raises, which is the shape the empty-space "
            f"refusal exists to prevent. Caller error, so it raises where a modelling gap refuses.")
    obs = getattr(model, "source_obs", None)
    if not obs:
        raise Unmodellable("the model carries no source observation to choose from — it was "
                           "constructed directly rather than through `StateModel.build`")
    my_seat = int(getattr(model, "my_index", 0))
    seat_index = my_seat if seat_index is None else int(seat_index)
    if context is None:
        context = (obs.get("select") or {}).get("context")
    if context != board_delta.CONTEXT_MAIN:
        raise Unmodellable(
            f"select context {context!r} is not the MAIN menu — this option is one leg of a card's "
            f"effect resolving, and that card's other writes ride the same engine step")
    kind = int((option or {}).get("type", -1))
    if seat_index != my_seat:
        raise Unmodellable(
            f"seat {seat_index} is not the model's own ({my_seat}) — a deferred-target option is one "
            f"*I* am taking, and the rankers price my board, so a foreign seat would rank the wrong "
            f"side's future")

    key = choice_key(model, option, seat_index=seat_index)
    entry = CHOICE_REGISTRY.get(key)
    if entry is None or entry.apply is None:
        _no(f"choice key {key!r}",
            (entry.no_applier if entry is not None and entry.no_applier else
             "no board synthesis is registered for it, so the resulting board cannot be written"))

    space = target_space(model, option, seat_index=seat_index)
    rank = ranker if ranker is not None else entry.rank
    # Descending rank, then the candidate itself: the ordering must be a pure function of the board or
    # two processes enumerate different sets, which is the reproducibility guarantee
    # `option_equivalence.class_representatives` keeps for exactly the same reason.
    ordered = tuple(space) if rank is None else tuple(
        sorted(space, key=lambda c: (-float(rank(model, c)), c)))

    # Synthesize the OBSERVATION for every candidate and collapse on its fingerprint, THEN cap. Doing
    # it in this order is what makes the cap a bound on distinct DECISIONS rather than on candidates:
    # capping first could keep two indistinguishable boards and drop a third that differs. The
    # observation is dict/list copy-on-write and cheap; the `StateModel` wrapper is what costs, and it
    # is built only for the classes that survive.
    distinct: dict = {}
    for candidate in ordered:
        after_obs, _writes = entry.apply(model, candidate, seat_index=seat_index)
        fingerprint = entry.fingerprint(after_obs, candidate, seat_index=seat_index, kind=kind)
        distinct.setdefault(fingerprint, after_obs)
    total = len(distinct)
    kept = list(distinct.items())[:int(cap)]
    return Expectation(
        classes=tuple(OutcomeClass(
            probability=1.0 / float(total),
            # A choice node on my own board never reaches across the table nor touches the shared
            # Stadium, so their already-built side is reusable — `board_delta.Delta.shares_opponent`'s
            # guarantee, held here by construction and mirrored from `_retreat`'s own True.
            model=model.rebuilt(after_obs, reuse_their_side=True),
            fingerprint=fingerprint) for fingerprint, after_obs in kept),
        truncated=total - len(kept))


__all__ = ("CHOICE_KINDS", "CHOICE_CLAUSES", "TARGET_VALUE_CEILING", "ChoiceKind",
           "CHOICE_REGISTRY", "TARGET_RANKERS", "role_span", "gust_rank_key", "choice_key", "target_space",
           "rank_retreat", "has_deferred_target", "candidate_class", "realise",
           "deferred_target")
