"""The expectation node — a reveal's outcome classes, closed-form (ADR-0130, Issue #383).

Where `board_delta` returns ONE board, a draw/search has a DISTRIBUTION. `apply_option` owns the
frozen `OutcomeClass` / `Expectation` shapes; this only fills them. Never a sampled engine shuffle,
and class identity is taken AFTER the reveal (ADR-0091).

**LIVE at runtime** — `composer._one_ply` calls :func:`expectation` for a revealing `_PLAY`."""
from __future__ import annotations

from typing import NoReturn

from collections import Counter
from itertools import product

from common import board_delta, deck_odds, snapshot_coverage
from common.board_delta import Unmodellable
from common.fetch_closure import (fetch_is_unconditional, fetch_target_matches,
                                  multiset_classes, reveal_legs)
from common.option_equivalence import AREA_BENCH, AREA_HAND, option_fingerprint
from common.strategy.context import _PLAY

#: `dest` values this seam can PLACE. `in_play` is deliberately ABSENT: it puts an EVOLUTION onto a
#: body the effect CHOOSES, which is `board_choice`'s node rather than a deploy.
_PLACED_DESTS: frozenset[str] = frozenset({"bench"})

#: Max outcome classes one Expectation enumerates — the measured post-Option-Equivalence menu-width
#: P95 (ADR-0130), never a tuned weight. Truncation past it is ALWAYS reported.
BRANCH_CAP = 12

#: Clause keys this module honours; anything else refuses, fail-closed against vocabulary drift. Every
#: member is a `snapshot_coverage.CLAUSE_PARAMETERS` key, so this set can only narrow that registry.
_HANDLED_FETCH_KEYS = frozenset({
    "kind", "target", "zone", "amount", "dest",
    "energy_type", "hp_max", "no_rule_box", "no_ability",
    # how several revealing legs COMBINE — read by `fetch_closure.reveal_legs`, shared with the
    # CHOICE node.
    "choice",
    # `cost_required` needs no handling here: an unpayable cost already refuses as an illegal play.
    "cost", "cost_required",
})


def revealing_clauses(combat, card_id) -> tuple:
    """**An empty tuple is never evidence that a card reveals nothing** — it is evidence that nothing
    is DECLARED, the blind spot `apply_option.footprints_writing_unhomed` names by card."""
    return tuple(c for c in board_delta.card_clauses(combat, card_id)
                 if c.get("kind") in snapshot_coverage.REVEALING_CLAUSES)


def _legs_of(combat, card_id, stat):
    """This card's revealing legs and how they COMBINE, or :class:`Unmodellable`. The relation is
    `fetch_closure.reveal_legs` — ONE reader, shared with `board_choice`'s CHOICE node."""
    every = board_delta.card_clauses(combat, card_id)
    name = getattr(stat, "name", "?")
    try:
        legs = reveal_legs(every)
    except ValueError as gap:
        _no(card_id, name, str(gap))
    if len(every) > len(legs.legs):
        _no(card_id, name, "it carries a non-revealing clause as well, whose leg would "
                                  "difference to exactly 0 in every enumerated class")
    return legs


def _no(card_id, name, why) -> NoReturn:
    """The seam's one refusal convention — the modelling backlog groups by exactly this string."""
    raise Unmodellable(f"{card_id} {name}: {why}")


def _check_clause(clause: dict, card_id, name) -> None:
    """Every fail-closed gate on the clause. **Ordered most-specific-first, and the order is
    load-bearing**: the unknown-KEY catch-all runs LAST so refusals name the actionable reason."""
    for value in snapshot_coverage.clause_values(clause):
        if value in snapshot_coverage.NONDETERMINISTIC_CLAUSES:
            _no(card_id, name, f"clause {value!r} consults RNG — a simulated shuffle is one sample, "
                               f"not a distribution (the engine has no deal-seed)")
    if clause.get("kind") == "draw":
        _no(card_id, name,
            "a `draw` is an n-card window and `deck_odds` answers *P(>=1 target in the window)*, "
            "never the JOINT distribution over which n cards arrived; single-card classes would be a "
            "conditional biased toward the highest-count cards, which is worse than the search "
            "case's honest lower bound")
    if not fetch_is_unconditional(clause):
        _no(card_id, name, "not the unconditional, decidable whole-deck search "
                           "`fetch_closure.fetch_is_unconditional` defines — it carries a `trigger`, "
                           "a `dig`, a `condition` or a `name_family`, none of which this seam can "
                           "decide")
    if clause.get("zone") != "deck":
        _no(card_id, name, f"a {clause.get('zone')!r}-zone search carries NO chance — that zone is "
                           f"visible — so it is a pure CHOICE node, not an expectation")
    cost = clause.get("cost")
    if cost is not None:
        if cost not in snapshot_coverage.COST_CARDS:
            _no(card_id, name, f"cost {cost!r} is not in `snapshot_coverage.COST_CARDS` — fail "
                               f"closed against vocabulary drift, exactly as this module's "
                               f"unknown-key gate does")
        if snapshot_coverage.COST_CARDS[cost] is None:
            _no(card_id, name, f"cost {cost!r} names no fixed card count. `discard_hand` pays the "
                               f"whole hand, whose size is not a constant; `bottom_2` returns cards "
                               f"to the DECK, which moves `unseen_counts` and would invalidate the "
                               f"pool this node enumerates over")
    amount = clause.get("amount")
    if amount is not None and not (isinstance(amount, int) and not isinstance(amount, bool)
                                   and amount >= 1):
        _no(card_id, name, f"`amount` {amount!r} names no number the enumerator can range over — "
                           f"only `\"all\"` reaches here, and resolving it needs a pool to count "
                           f"against plus the Bench cap its carriers deliver into (Issue #410)")
    dest = clause.get("dest")
    if dest is not None and dest not in _PLACED_DESTS:
        _no(card_id, name, f"`dest` {dest!r}: the found body arrives on a body this seam does not "
                           f"choose, which is a CHOICE node (`board_choice`) rather than the deploy "
                           f"transition {sorted(_PLACED_DESTS)} composes with")
    unknown = sorted(set(clause) - _HANDLED_FETCH_KEYS)
    if unknown:
        _no(card_id, name, f"clause key(s) {unknown} are not in this module's handled set — fail "
                           f"closed against vocabulary drift, exactly as `board_delta._clause_writes` "
                           f"refuses an undeclared clause VALUE")


def outcome_pool(model, clause: dict) -> dict:
    """``{card id: unseen copies}`` — the deck cards this search can deliver. The filter is the
    SHIPPED `fetch_target_matches`, never a second matcher (ADR-0087)."""
    return {cid: n for cid, n in (model.mine.unseen_counts or {}).items()
            if n > 0 and fetch_target_matches(clause, model.card_stat(cid))}


def _class_weight(model, delivered: tuple) -> float:
    """An AVAILABILITY weight (ADR-0029's hypergeometric split at the class's multiplicity), NOT a
    joint draw probability. Not normalised here — the caller normalises over the FULL class set."""
    hidden, left = model.mine.prizes_hidden, model.mine.deck_count
    unseen = model.mine.unseen_counts or {}
    weight = 1.0
    for cid, need in Counter(delivered).items():
        weight *= deck_odds.p_contains_at_least(unseen.get(cid, 0), hidden, left, need)
    return weight


def _cost_indices(model, option, legs, *, seat_index, card_id, name, shed) -> tuple:
    """The HAND INDICES this play's cost takes, ``()`` when free, or a refusal. WHICH cards is the
    live decider's answer, so it is passed IN; with no oracle it REFUSES rather than pricing it free."""
    costs = {leg.get("cost") for leg in legs.legs if leg.get("cost") is not None}
    if not costs:
        return ()
    if len(costs) > 1:
        _no(card_id, name, f"its legs declare DIFFERENT costs {sorted(costs)} — a play has one "
                           f"price, so this is either a compendium defect or a shape with no single "
                           f"payment to charge; refusing rather than picking one")
    cost = costs.pop()
    picks = snapshot_coverage.COST_CARDS[cost]          # `_check_clause` proved it is a real count
    if shed is None:
        _no(card_id, name, f"its cost {cost!r} takes {picks} card(s) from my hand and no `shed` "
                           f"oracle was supplied — WHICH cards is the live decider's answer "
                           f"(`needs.cheapest_removal`), so the caller must pass it in rather than "
                           f"have this node invent a second one")
    hand = ((model.source_obs.get("current") or {}).get("players") or [{}])[seat_index].get("hand")
    played = option.get("index")
    taken = tuple(dict.fromkeys(int(i) for i in (shed(model, option, picks) or ())))
    legal = tuple(i for i in taken if 0 <= i < len(hand or ()) and i != played)
    if len(legal) != picks:
        _no(card_id, name, f"its cost takes {picks} card(s) and the `shed` oracle named {len(legal)} "
                           f"usable hand index(es) — the play is not legal on this board (the "
                           f"engine's own `handOthers` gate), so there is nothing to enumerate")
    return legal


def _found_serial(card_id: int, ordinal: int) -> int:
    """A found card's synthesized `serial`. NEGATIVE so a dump tells it from an observed one, and
    ordinal-keyed because `-card_id` alone collides when one class delivers two of the same card."""
    return -(card_id * 100 + ordinal)


def _dest_of(legs, *, card_id, name):
    """The ONE place this card's delivery lands, or None for a hand write. Mirrors `_cost_indices`'
    single-value discipline: a card whose legs disagree has no single destination to compose with."""
    dests = {leg.get("dest") for leg in legs.legs}
    if len(dests) > 1:
        _no(card_id, name, f"its legs declare DIFFERENT destinations {sorted(d or 'hand' for d in dests)} "
                           f"— one play delivers to one zone, so this is either a compendium defect "
                           f"or a shape with no single placement; refusing rather than picking one")
    return dests.pop() if dests else None


def _bench_room(model, seat_index: int) -> int:
    """Open Bench slots on my side. The cap comes from `board_delta.bench_max`, so "is there room"
    cannot disagree with `_play`, which fills the Bench through the same reader."""
    me = ((model.source_obs.get("current") or {}).get("players") or [{}])[seat_index] or {}
    return max(0, board_delta.bench_max(model.source_obs, seat_index) - len(me.get("bench") or ()))


def _place_on_bench(model, me, current, delivered: tuple, *, seat_index, card_id, name) -> tuple:
    """Deploy each delivered body, MUTATING ``me``; returns the bench indices they landed on. Built
    from `board_delta`'s own primitives so an arriving body is taxed exactly as a hand-played one."""
    bench = list(me.get("bench") or ())
    at = []
    for ordinal, cid in enumerate(delivered):
        dstat = model.card_stat(cid)
        if dstat is None or not getattr(dstat, "hp", None):
            _no(card_id, name, f"it delivers {cid} onto the Bench and that card has no `CardStat` HP, "
                               f"so the arriving body's maximum is unknown")
        clauses = board_delta.stadium_clauses_for(current, model.combat, event="bench_play",
                                                  stat=dstat)
        body = board_delta.bench_body(cid, dstat, seat_index=seat_index,
                                      serial=_found_serial(cid, ordinal))
        board_delta.apply_bench_arrival(body, clauses, dstat)
        bench.append(body)
        at.append(len(bench) - 1)
    me["bench"] = bench
    return tuple(at)


def _revealed(model, option, delivered: tuple, *, seat_index, stat, paid: tuple = (), dest=None,
              card_id=None, name="?"):
    """The observation after the search RESOLVES. ``paid`` is applied BEFORE the search, matching the
    engine's own order — charging after would let a delivered card pay for its own search."""
    new_obs, current, players = board_delta.fork(model.source_obs)
    me = board_delta.fork_player(players, seat_index)
    index = option.get("index")
    if paid:
        hand = list(me.get("hand") or ())
        spent = [hand[i] for i in sorted(paid, reverse=True)]
        for i in sorted(paid, reverse=True):
            hand.pop(i)
        me["hand"] = hand
        if me.get("handCount") is not None:
            me["handCount"] = len(hand)
        me["discard"] = list(me.get("discard") or ()) + list(reversed(spent))
        index = index - sum(1 for i in paid if i < index)      # the play's own index shifts down
    played = board_delta.take_from_hand(me, index, "reveal")
    # `docs/rulebook.txt` L78 — the card that performed the search is out of play once it resolves.
    me["discard"] = list(me.get("discard") or ()) + [played]
    if dest == "bench":
        at = _place_on_bench(model, me, current, delivered, seat_index=seat_index,
                             card_id=card_id, name=name)
    else:
        hand = list(me.get("hand") or ())
        at = []
        for ordinal, found in enumerate(delivered):
            hand.append({"id": found, "serial": _found_serial(found, ordinal),
                         "playerIndex": seat_index})
            at.append(len(hand) - 1)
        me["hand"] = hand
        if me.get("handCount") is not None:
            me["handCount"] = len(hand)
    if me.get("deckCount") is not None:
        me["deckCount"] = max(0, int(me["deckCount"]) - len(delivered))
    if getattr(stat, "is_supporter", False):
        current["supporterPlayed"] = True          # `docs/rules.md` §3 — one Supporter per turn
    return new_obs, tuple(at)


def _fingerprint(obs, indices: tuple, seat_index, dest=None) -> tuple:
    """Per-card fingerprints on the POST-reveal board; the pre-reveal reference is unfingerprintable.
    A benched delivery keys on the BODY it became — a hand index would name a card that never arrived."""
    if dest == "bench":
        return tuple(option_fingerprint({"type": _PLAY, "inPlayArea": AREA_BENCH,
                                         "inPlayIndex": index, "playerIndex": seat_index}, obs)
                     for index in indices)
    return tuple(option_fingerprint({"type": _PLAY, "area": AREA_HAND, "index": index,
                                     "playerIndex": seat_index}, obs)
                 for index in indices)


def _classes_for(legs, pools: tuple) -> list:
    """Outcome classes as sorted tuples of card ids; ``[]`` when the legs deliver nothing. For a
    conjunction an empty leg SKIPS — the engine's own behaviour — so refuse only when EVERY leg is."""
    if legs.relation == "conjunction":
        live = [sorted(p) for p in pools if p]
        if not live:
            return []
        return sorted({tuple(sorted(combo)) for combo in product(*live)})
    union: dict = {}
    for pool in pools:
        union.update(pool)
    return multiset_classes(union, legs.cap)


def expectation(model, option, *, seat_index=None, context=None, cap: int = BRANCH_CAP,
                shed=None):
    """The :class:`~common.apply_option.Expectation` over ``option``'s reveal, or
    :class:`~common.board_delta.Unmodellable`. A class's ``probability`` is an AVAILABILITY weight."""
    from common.apply_option import Expectation, OutcomeClass          # contract, imported lazily

    if int(cap) < 1:
        raise ValueError(
            f"cap={cap!r}: an Expectation must enumerate at least one class — a zero-class one is an "
            f"un-enumerated effect whose `expected()` raises, which is the shape the empty-pool "
            f"refusal exists to prevent. Caller error, so it raises where a modelling gap refuses.")
    obs = getattr(model, "source_obs", None)
    if not obs:
        raise Unmodellable("the model carries no source observation to reveal from — it was "
                           "constructed directly rather than through `StateModel.build`")
    seat_index = int(getattr(model, "my_index", 0) if seat_index is None else seat_index)
    if context is None:
        context = (obs.get("select") or {}).get("context")
    if context != board_delta.CONTEXT_MAIN:
        raise Unmodellable(
            f"select context {context!r} is not the MAIN menu — this option is one leg of a card's "
            f"effect resolving, and that card's other writes ride the same engine step")
    kind = int((option or {}).get("type", -1))
    if kind != _PLAY:
        raise Unmodellable(
            f"option kind {kind} is not a `_PLAY` — a reveal riding another kind does not put its "
            f"source card in my discard, so this module's structural floor does not hold for it")

    hand = ((obs.get("current") or {}).get("players") or [{}])[seat_index].get("hand") or ()
    index = option.get("index")
    if not isinstance(index, int) or not 0 <= index < len(hand):
        raise Unmodellable(f"reveal names hand index {index!r}, which this snapshot cannot resolve "
                           f"(hand of {len(hand)})")
    card_id = (hand[index] or {}).get("id")
    stat = model.card_stat(card_id)
    if stat is None:
        raise Unmodellable(f"{card_id}: no `CardStat` for the played card")
    name = getattr(stat, "name", "?")
    # Gate ORDER is load-bearing (ADR-0130): "does this reveal at all?" first, then the ABILITY gate,
    # then the clause gates, and the card-type floor LAST — so each refusal names an actionable reason.
    legs = _legs_of(model.combat, card_id, stat)
    # An Ability does not fire because the body was PLAYED; only `on_bench_play` rides the `_PLAY`.
    if not (getattr(stat, "is_item", False) or getattr(stat, "is_supporter", False)):
        triggers = {leg.get("trigger") for leg in legs.legs}
        if triggers != {"on_bench_play"}:
            named = sorted(t for t in triggers if t)
            carried = f"trigger(s) {named}" if named else "no `trigger` at all"
            _no(card_id, name, f"its revealing clause is an ABILITY, not this play — it carries "
                               f"{carried}, and only `on_bench_play` fires because the body was "
                               f"PLAYED (an Ability is a separate `_ABILITY` option). So deploying "
                               f"it reveals nothing, and modelling a reveal here would be WRONG "
                               f"rather than under-scoped")
    for leg in legs.legs:
        _check_clause(leg, card_id, name)
    if not (getattr(stat, "is_item", False) or getattr(stat, "is_supporter", False)):
        _no(card_id, name, "only an Item or a Supporter resolves to my discard on a search; this "
                           "card's structural floor is a different one")

    paid = _cost_indices(model, option, legs, seat_index=seat_index, card_id=card_id, name=name, shed=shed)
    dest = _dest_of(legs, card_id=card_id, name=name)
    if dest == "bench":
        # TRUNCATES, never filters: every carrier searches for "up to" N, so one slot delivers one
        # body — dropping the oversized class would refuse a legal play.
        room = _bench_room(model, seat_index)
        if room <= 0:
            _no(card_id, name, "my Bench is full, so there is no open Bench slot for it to deliver "
                               "into — the play is unreachable on this board, and enumerating a "
                               "zero-body delivery would rank a dead Item beside a live one")
        legs = legs._replace(cap=min(int(legs.cap), room))
    pools = tuple(outcome_pool(model, leg) for leg in legs.legs)
    candidates = _classes_for(legs, pools)
    if not candidates:
        _no(card_id, name, "no target it can reach is still unseen in my deck — a provably-whiffing "
                           "search is a fact to refuse on, not a zero-class Expectation")
    weights = {klass: _class_weight(model, klass) for klass in candidates}
    mass = sum(weights.values())
    if mass <= 0.0:
        _no(card_id, name, "no target it can reach has any availability left (`deck_odds` puts every "
                           "matching copy outside the deck), so there is nothing to enumerate")

    # Descending weight, then ascending class: the ordering must be a pure function of the board or
    # two processes enumerate different sets.
    ranked = sorted(candidates, key=lambda klass: (-weights[klass], klass))
    kept, dropped = ranked[:int(cap)], ranked[int(cap):]
    classes = []
    for klass in kept:
        after_obs, at = _revealed(model, option, klass, seat_index=seat_index, stat=stat,
                                  paid=paid, dest=dest, card_id=card_id, name=name)
        classes.append(OutcomeClass(
            probability=weights[klass] / mass,
            # The reveal never reaches across the table, so their built side is reusable.
            model=model.rebuilt(after_obs, reuse_their_side=True),
            fingerprint=_fingerprint(after_obs, at, seat_index, dest)))
    return Expectation(classes=tuple(classes), truncated=len(dropped))


__all__ = ("BRANCH_CAP", "revealing_clauses", "outcome_pool", "expectation")
