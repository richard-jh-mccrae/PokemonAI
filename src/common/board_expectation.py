"""The expectation node — a reveal's outcome classes, closed-form (ADR-0130, Issue #383).

Where `board_delta` returns ONE board, a draw/search has a DISTRIBUTION. `apply_option` owns the
frozen `OutcomeClass` / `Expectation` shapes; this only fills them. Never a sampled engine shuffle,
and class identity is taken AFTER the reveal (ADR-0091).

**LIVE at runtime** — `composer._one_ply` first calls :func:`closed_form_transition` for the ordered
coin/refresh registry, then :func:`expectation` for an enumerated revealing `_PLAY`. The same
closed-form registry owns supported `_ABILITY` draw routes without pretending the source is in hand."""
from __future__ import annotations

from typing import Callable, Mapping, NoReturn

from collections import Counter
from dataclasses import dataclass, replace
from itertools import product
from math import comb

from common import board_delta, deck_odds, snapshot_coverage
from common.board_delta import Unmodellable
from common.fetch_closure import WINDOW, fetch_target_matches, multiset_classes, reveal_legs
from common.option_equivalence import AREA_ACTIVE, AREA_BENCH, AREA_HAND, option_fingerprint
from common.state_model import ability_allowance_marker, ability_allowance_spent
from common.strategy.context import _ABILITY, _PLAY

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
    # How deep the look goes. `dig_from` is deliberately ABSENT beside it: the bottom-N is the same
    # distribution, but nothing shipped needs it and an unhandled key is the fail-closed answer.
    "dig",
    # how several revealing legs COMBINE — read by `fetch_closure.reveal_legs`, shared with the
    # CHOICE node.
    "choice",
    # `cost_required` needs no handling here: an unpayable cost already refuses as an illegal play.
    "cost", "cost_required",
})

#: The clause fields this seam cannot decide, each with its OWN reason — the refusal names only the
#: ones that fired, so a test can tell which, and `dig` is absent because ADR-0133 prices it.
_UNDECIDABLE_FETCH_FIELDS: dict[str, str] = {
    "trigger": "fires off some other event than this play",
    "condition": "reads board history the snapshot does not hold",
    "name_family": "needs a pool index keyed by printed name",
}

_HAMMER_COIN = {"kind": "coin", "effect": "discard_opp_energy", "amount": 1}

_SCALAR_DRAW_KEYS = frozenset({
    "kind", "amount", "amount_if", "condition", "opponent_amount", "opponent_amount_if", "rider",
    "allowance",
})
_ABILITY_DRAW_KEYS = _SCALAR_DRAW_KEYS | {"window"}


@dataclass(frozen=True)
class ClosedFormRoute:
    """One conservative closed-form owner. Key coverage only admits the semantic predicate to run."""

    name: str
    option_kinds: frozenset[int]
    clause_kind: str
    handled_keys: frozenset[str]
    accepts: Callable[[Mapping], bool]
    build: Callable


@dataclass(frozen=True)
class _Source:
    kind: int
    seat: int
    index: int
    card_id: int
    stat: object
    body_serial: object | None = None
    area: int | None = None


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
        if value in snapshot_coverage.NONDETERMINISTIC_CLAUSES and value != "coin":
            _no(card_id, name, f"clause {value!r} consults RNG — a simulated shuffle is one sample, "
                               f"not a distribution (the engine has no deal-seed)")
    if clause.get("kind") == "coin":
        if clause == _HAMMER_COIN:
            return
        _no(card_id, name, "only Crushing Hammer's exact one-Energy coin shape has a closed-form "
                            "DEALT route")
    if clause.get("kind") == "draw":
        _no(card_id, name,
            "a `draw` is an n-card window and `deck_odds` answers *P(>=1 target in the window)*, "
            "never the JOINT distribution over which n cards arrived; single-card classes would be a "
            "conditional biased toward the highest-count cards, which is worse than the search "
            "case's honest lower bound")
    # NOT `fetch_is_unconditional`: that is an ENDORSER's question and this node enumerates. A `dig`
    # is admitted because the window is PRICED (ADR-0133); the other three stay undecidable here.
    undecidable = [f for f in _UNDECIDABLE_FETCH_FIELDS if clause.get(f)]
    if undecidable:
        _no(card_id, name, "this seam cannot decide " + "; ".join(
            f"`{f}`, which {_UNDECIDABLE_FETCH_FIELDS[f]}" for f in undecidable))
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


def _source(model, option) -> _Source | None:
    """Kind/context gates precede every source-zone read; malformed owned sources refuse."""
    kind = (option or {}).get("type")
    if kind not in (_PLAY, _ABILITY):
        return None
    obs = getattr(model, "source_obs", None) or {}
    if (obs.get("select") or {}).get("context") != board_delta.CONTEXT_MAIN:
        return None
    seat = int(getattr(model, "my_index", 0))
    players = (obs.get("current") or {}).get("players") or ()
    me = players[seat] if 0 <= seat < len(players) else {}
    if kind == _ABILITY:
        area, index = (option or {}).get("area"), (option or {}).get("index")
        zone = "active" if area == AREA_ACTIVE else "bench" if area == AREA_BENCH else None
        cards = me.get(zone) or () if zone is not None else ()
        if (zone is None or not isinstance(index, int) or isinstance(index, bool)
                or not 0 <= index < len(cards) or not cards[index]):
            raise Unmodellable(
                f"closed-form MAIN `_ABILITY` source area/index {area!r}/{index!r} "
                "does not name an occupied in-play body")
        body = cards[index]
        card_id = body.get("id")
        stat = model.card_stat(card_id)
        if stat is None or not getattr(stat, "is_pokemon", False):
            return None
        serial = body.get("serial")
        if serial is None:
            raise Unmodellable(
                f"closed-form MAIN `_ABILITY` source {card_id} has no body serial for its allowance")
        return _Source(kind=_ABILITY, seat=seat, index=index, card_id=int(card_id), stat=stat,
                       body_serial=serial, area=area)
    hand = me.get("hand") or ()
    index = (option or {}).get("index")
    if not isinstance(index, int) or isinstance(index, bool) or not 0 <= index < len(hand):
        raise Unmodellable(
            f"closed-form MAIN `_PLAY` source index {index!r} is not an occupied hand slot")
    card = hand[index] or {}
    card_id = card.get("id")
    stat = model.card_stat(card_id)
    if stat is None or not (getattr(stat, "is_item", False) or getattr(stat, "is_supporter", False)):
        return None
    return _Source(kind=_PLAY, seat=seat, index=index, card_id=int(card_id), stat=stat)


def _spent_trainer(model, source: _Source):
    """The certain half of a gated Trainer route. Never re-resolves the option source."""
    obs = getattr(model, "source_obs", None) or {}
    new_obs, current, players = board_delta.fork(obs)
    me = board_delta.fork_player(players, source.seat)
    hand_count = int(me.get("handCount")) if me.get("handCount") is not None else len(
        me.get("hand") or ())
    card = board_delta.take_from_hand(me, source.index, "closed-form play")
    # ``take_from_hand`` normally resyncs to the visible list. A hypothetical blind draw may leave
    # identities unknown, so preserve the authoritative count and spend exactly one source card.
    me["handCount"] = max(0, hand_count - 1)
    me["discard"] = list(me.get("discard") or ()) + [card]
    if getattr(source.stat, "is_supporter", False):
        current["supporterPlayed"] = True
    return new_obs, players


def _discarded_energy_models(model, spent_obs: dict, *, seat: int) -> tuple:
    """Every legal heads target after a Crushing Hammer has been spent."""
    other = 1 - seat
    players = (spent_obs.get("current") or {}).get("players") or []
    opponent = players[other] if 0 <= other < len(players) else {}
    out = []
    for area in ("active", "bench"):
        for body_index, raw in enumerate(opponent.get(area) or ()):
            cards = list((raw or {}).get("energyCards") or ())
            for energy_index, dropped in enumerate(cards):
                after_obs, _current, after_players = board_delta.fork(spent_obs)
                theirs = board_delta.fork_player(after_players, other)
                bodies = list(theirs.get(area) or ())
                body = dict(bodies[body_index])
                kept = cards[:energy_index] + cards[energy_index + 1:]
                body["energyCards"] = kept
                body["energies"] = board_delta.units_for_cards(
                    model.combat, kept, holder_stat=model.card_stat(body.get("id")))
                bodies[body_index] = body
                theirs[area] = bodies
                theirs["discard"] = list(theirs.get("discard") or ()) + [dropped]
                out.append((area, body_index, energy_index, after_obs))
    return tuple(out)


def _coin_expectation(model, source: _Source, _clause, *, score: Callable[[object], float],
                      shed=None):
    """Crushing Hammer's two DEALT outcomes, with the heads target chosen after the flip."""
    spent_obs, _players = _spent_trainer(model, source)
    seat = source.seat
    tail = model.rebuilt(spent_obs, reuse_their_side=True)
    heads = _discarded_energy_models(model, spent_obs, seat=seat)
    if heads:
        chosen = max(heads, key=lambda row: (float(score(model.rebuilt(row[3], reuse_their_side=False))),
                                             row[:3]))
        head = model.rebuilt(chosen[3], reuse_their_side=False)
        fingerprint = ("coin", "heads", *chosen[:3])
    else:
        head, fingerprint = tail, ("coin", "heads", "whiff")
    from common.apply_option import DEALT, Expectation, OutcomeClass
    return Expectation(classes=(OutcomeClass(0.5, tail, ("coin", "tails")),
                                OutcomeClass(0.5, head, fingerprint)), resolution=DEALT)


def _ability_allowance(model, source: _Source, clause):
    """Metadata, not a generic condition, decides whether same-name copies share currency."""
    allowance = clause.get("allowance")
    if source.kind != _ABILITY:
        if allowance is not None:
            _no(source.card_id, getattr(source.stat, "name", "?"),
                "an Ability allowance appeared on a played Trainer")
        return None
    marker = ability_allowance_marker(
        allowance, card_id=source.card_id, body_serial=source.body_serial)
    if marker is None:
        _no(source.card_id, getattr(source.stat, "name", "?"),
            f"activated Ability allowance {allowance!r} is not `body` or `card`")
    if ability_allowance_spent(model, marker):
        scope = "per-body" if allowance == "body" else "once-per-card/global"
        _no(source.card_id, getattr(source.stat, "name", "?"),
            f"{scope} Ability allowance for {marker[1]!r} is already spent")
    return marker


def _spent_source(model, source: _Source, clause):
    """Spend the source without conflating a hand Trainer with an in-play Ability body."""
    if source.kind == _PLAY:
        return _spent_trainer(model, source)
    key, value = _ability_allowance(model, source, clause)
    new_obs, current, players = board_delta.fork(model.source_obs)
    used = list(current.get(key) or ())
    if value not in used:
        used.append(value)
    current[key] = used
    return new_obs, players


def _draw_transition(model, source: _Source, clause, *, score=None, shed=None):
    """Known scalar draw writes plus composition Worth; never sample a shuffled deck."""
    from common.apply_option import DEALT, Expectation, OutcomeClass, ScalarTransition
    from common.deck_value import deck_draw_worth
    from common.state_value import worth_to_prizes
    from common.strategy import refresh

    card_id = source.card_id
    problem = refresh.draw_shape_problem(clause)
    if problem is not None:
        _no(card_id, getattr(source.stat, "name", "?"), f"draw route refuses: {problem}")
    if clause.get("condition") == "pokemon_ko_last_turn" and not model.my_pokemon_koed_last_turn:
        _no(card_id, getattr(source.stat, "name", "?"),
            "draw route condition `pokemon_ko_last_turn` does not hold")
    prizes = model.prize_race
    branches = refresh.draw_branches(clause, prizes.my_prizes_remaining,
                                     prizes.opp_prizes_remaining,
                                     my_hand_size=model.mine.hand_size)
    if branches is None:
        _no(card_id, getattr(source.stat, "name", "?"),
            "draw route has no decidable count branches")
    spent_obs, _players = _spent_source(model, source, clause)
    seat = source.seat
    rider = clause.get("rider")
    shuffled_own = rider in {"shuffle_own_hand_in", "shuffle_both_hands"}
    own_available = model.mine.deck_count + (max(0, model.mine.hand_size - 1) if shuffled_own else 0)
    other = 1 - seat
    opponent_shuffles = rider == "shuffle_both_hands"

    def transition(my_draw: int, opp_draw: int):
        branch_obs, _current, players = board_delta.fork(spent_obs)
        mine = board_delta.fork_player(players, seat)
        actual_my = min(own_available, my_draw)
        if shuffled_own:
            mine["hand"] = []
            mine["handCount"] = actual_my
        else:
            mine["handCount"] = int(mine.get("handCount") or 0) + actual_my
        actual_opp = opp_draw
        theirs = board_delta.fork_player(players, other)
        if opponent_shuffles:
            hand_count = int(theirs.get("handCount") or 0)
            deck_count = int(theirs.get("deckCount") or 0)
            actual_opp = min(deck_count + hand_count, opp_draw)
            theirs["handCount"] = actual_opp
            if theirs.get("deckCount") is not None:
                theirs["deckCount"] = deck_count + hand_count - actual_opp
        after = model.rebuilt(branch_obs, reuse_their_side=not opponent_shuffles)
        scalar = worth_to_prizes(deck_draw_worth(model, actual_my))
        return ScalarTransition(model=after, scalar=float(scalar)), actual_my, actual_opp

    outcomes = tuple(transition(my_draw, opp_draw) for my_draw, opp_draw in branches)
    if len(outcomes) == 1:
        return outcomes[0][0]
    probability = 1.0 / len(outcomes)
    return Expectation(
        classes=tuple(OutcomeClass(probability, result.model,
                                   ("draw", branch, actual_my, actual_opp), result.scalar)
                      for branch, (result, actual_my, actual_opp) in enumerate(outcomes)),
        resolution=DEALT)


def _ability_draw_transition(model, source: _Source, clause, *, score=None, shed=None):
    """The three supported activated draws; Dudunsparce's body mutation stays an explicit gap."""
    name = getattr(source.stat, "name", "?")
    rider = clause.get("rider")
    if rider == "shuffle_self_in":
        _no(source.card_id, name,
            "draw route refuses `shuffle_self_in`: shuffling the source body/stack may require "
            "promotion, and no body transition models that write")
    if clause.get("window") is not None:
        return _draw_window_expectation(model, source, clause, score=score)
    if rider != "discard_basic_f_energy":
        return _draw_transition(model, source, clause, score=score)

    _ability_allowance(model, source, clause)
    if clause.get("condition") != "solrock_in_play" or "Solrock" not in model.mine.in_play_names:
        _no(source.card_id, name, "draw route condition `solrock_in_play` does not hold")
    mine_obs = ((model.source_obs.get("current") or {}).get("players") or [])[source.seat]
    candidates = []
    for i, card in enumerate(mine_obs.get("hand") or ()):
        cid = (card or {}).get("id")
        stat = model.card_stat(cid) if cid is not None else None
        if (stat is not None and getattr(stat, "is_typed_basic_energy", False)
                and int(getattr(stat, "energyType", -1)) == 6):
            candidates.append(i)
    candidates = tuple(candidates)
    if not candidates:
        _no(source.card_id, name,
            "Lunar Cycle needs one Basic {F} Energy in hand; the offered Ability has no legal fuel")
    if shed is None:
        _no(source.card_id, name,
            "Lunar Cycle needs the caller's `shed` oracle to rank its legal Basic {F} Energy fuel")
    paid_option = {"type": _ABILITY, "area": source.area, "index": source.index}
    picked = tuple(dict.fromkeys(int(i) for i in (shed(model, paid_option, 1, candidates) or ())))
    if len(picked) != 1 or picked[0] not in candidates:
        _no(source.card_id, name,
            "Lunar Cycle's `shed` oracle did not name exactly one legal Basic {F} Energy")
    paid_obs, _current, players = board_delta.fork(model.source_obs)
    mine = board_delta.fork_player(players, source.seat)
    hand = list(mine.get("hand") or ())
    fuel = hand.pop(picked[0])
    mine["hand"] = hand
    if mine.get("handCount") is not None:
        mine["handCount"] = max(0, int(mine["handCount"]) - 1)
    mine["discard"] = list(mine.get("discard") or ()) + [fuel]
    paid_model = model.rebuilt(paid_obs, reuse_their_side=True)
    scalar_clause = {k: v for k, v in clause.items()
                     if k not in {"condition", "rider"}}
    return _draw_transition(paid_model, source, scalar_clause, score=score)


def _draw_window_expectation(model, source: _Source, clause, *, score=None):
    """Drakloak's top-two/take-one distribution under Issue #440's best-shown-card policy."""
    from common.apply_option import DEALT, SCORE_PLACES, Expectation, OutcomeClass
    name = getattr(source.stat, "name", "?")
    if (source.kind != _ABILITY or clause.get("amount") != 1 or clause.get("window") != 2
            or clause.get("rider") != "other_to_bottom"):
        _no(source.card_id, name, f"unsupported draw-window shape {dict(clause)!r}")
    if score is None:
        _no(source.card_id, name, "a draw-window needs the value oracle that chooses its best card")
    spent_obs, _players = _spent_source(model, source, clause)

    def delivered(card_id=None):
        after_obs, _current, players = board_delta.fork(spent_obs)
        mine = board_delta.fork_player(players, source.seat)
        if card_id is not None:
            hand = list(mine.get("hand") or ())
            hand.append({"id": card_id, "serial": _found_serial(card_id, 0),
                         "playerIndex": source.seat})
            mine["hand"] = hand
            if mine.get("handCount") is not None:
                mine["handCount"] = int(mine["handCount"]) + 1
            if mine.get("deckCount") is not None:
                mine["deckCount"] = max(0, int(mine["deckCount"]) - 1)
        return model.rebuilt(after_obs, reuse_their_side=True)

    copies = dict(model.mine.unseen_counts)
    singles = {cid: delivered(cid) for cid in copies}
    order = tuple(sorted(singles, key=lambda cid: (-round(float(score(singles[cid])),
                                                          SCORE_PLACES), cid)))
    left, hidden = int(model.mine.deck_count), int(model.mine.hidden_outside_deck)
    weights = window_classes(order, copies, left + hidden, min(2, left), 1)
    ranked = sorted(weights, key=lambda klass: (-weights[klass], klass))
    kept, dropped = ranked[:BRANCH_CAP], ranked[BRANCH_CAP:]
    classes = tuple(OutcomeClass(weights[klass],
                                 delivered(None) if not klass else singles[klass[0]],
                                 ("draw-window", *klass)) for klass in kept)
    return Expectation(classes=classes, resolution=DEALT, truncated=len(dropped))


# Ordered for deterministic diagnostics only. Acceptance still requires exactly one match.
CLOSED_FORM_ROUTES = (
    ClosedFormRoute(
        name="coin", option_kinds=frozenset({_PLAY}), clause_kind="coin",
        handled_keys=frozenset(_HAMMER_COIN),
        accepts=lambda clause: dict(clause) == _HAMMER_COIN, build=_coin_expectation),
    ClosedFormRoute(
        name="draw", option_kinds=frozenset({_PLAY}), clause_kind="draw",
        handled_keys=_SCALAR_DRAW_KEYS,
        accepts=lambda clause: clause.get("kind") == "draw", build=_draw_transition),
    ClosedFormRoute(
        name="ability-draw", option_kinds=frozenset({_ABILITY}), clause_kind="draw",
        handled_keys=_ABILITY_DRAW_KEYS,
        accepts=lambda clause: clause.get("kind") == "draw", build=_ability_draw_transition),
)


def closed_form_transition(model, option, *, score: Callable[[object], float],
                           clauses_cover: bool | None = None, shed=None):
    """An owned clause fails closed before its unique registered builder can run."""
    source = _source(model, option)
    if source is None:
        return None
    routes = tuple(route for route in CLOSED_FORM_ROUTES if source.kind in route.option_kinds)
    clauses = board_delta.card_clauses(model.combat, source.card_id)
    owned_kinds = frozenset(route.clause_kind for route in routes)
    owned = tuple(clause for clause in clauses if clause.get("kind") in owned_kinds)
    if not owned:
        return None

    cover = clauses_cover
    if cover is None:
        effects = getattr(getattr(model, "combat", None), "effects", None)
        cover = effects.clauses_cover(source.card_id) if effects is not None else None
    name = getattr(source.stat, "name", "?")
    if cover is not True:
        state = "partial" if cover is False else "unruled"
        _no(source.card_id, name,
            f"clause coverage is {state}; a closed-form route requires the whole printed effect")
    if len(owned) != 1:
        _no(source.card_id, name,
            f"ambiguous closed-form ownership: {len(owned)} owned clauses match; exactly one is "
            "required")
    if len(clauses) != 1:
        _no(source.card_id, name,
            f"a sibling clause would be dropped by the closed-form route ({len(clauses)} total)")

    clause = owned[0]
    candidates = tuple(route for route in routes if route.clause_kind == clause.get("kind"))
    handled = frozenset().union(*(route.handled_keys for route in candidates))
    unknown = sorted(set(clause) - handled)
    if unknown:
        _no(source.card_id, name, f"unhandled key(s) {unknown} in closed-form clause")
    matches = tuple(route for route in candidates
                    if set(clause) <= route.handled_keys and route.accepts(clause))
    if not matches:
        _no(source.card_id, name,
            f"no closed-form route accepts clause shape {dict(clause)!r}")
    if len(matches) != 1:
        route_names = [route.name for route in matches]
        _no(source.card_id, name, f"ambiguous closed-form routes {route_names}")
    return matches[0].build(model, source, clause, score=score, shed=shed)


def outcome_pool(model, clause: dict) -> dict:
    """``{card id: unseen copies}`` — the deck cards this search can deliver. The filter is the
    SHIPPED `fetch_target_matches` at its WINDOW reading, never a second matcher (ADR-0087)."""
    return {cid: n for cid, n in (model.mine.unseen_counts or {}).items()
            if n > 0 and fetch_target_matches(clause, model.card_stat(cid), reading=WINDOW)}


def _class_weight(model, delivered: tuple) -> float:
    """An AVAILABILITY weight (ADR-0029's hypergeometric split at the class's multiplicity), NOT a
    joint draw probability. Not normalised here — the caller normalises over the FULL class set."""
    hidden, left = model.mine.hidden_outside_deck, model.mine.deck_count
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


def _dig_depth(legs, *, card_id, name):
    """The ONE window this play looks at, or None when no leg digs. A union shares a single look, so
    two depths name two windows and there is no distribution over both."""
    depths = {int(leg["dig"]) for leg in legs.legs if leg.get("dig")}
    if not depths:
        return None
    if len(depths) > 1:
        _no(card_id, name, f"its legs declare DIFFERENT dig depths {sorted(depths)} — one play takes "
                           f"ONE look at the top of the deck, so there is no single window to "
                           f"enumerate over; refusing rather than picking one")
    if legs.relation == "conjunction":
        _no(card_id, name, "a dig on CONJUNCTION legs — each leg carries its own budget but they "
                           "share one window, so the per-leg picks are NOT independent and the "
                           "product this seam enumerates would count the same cards twice")
    return depths.pop()


def window_classes(order: tuple, copies: dict, pool: int, window: int, take: int) -> dict:
    """``{delivered class: probability}`` for taking the best ``take`` of ``order`` that a ``window``-card
    look at ``pool`` reveals. EXACT, sums to 1.0, and ``()`` is the whiff (ADR-0133)."""
    pool, window, take = int(pool), min(int(window), int(pool)), int(take)
    counts = [int(copies.get(cid, 0)) for cid in order]
    cum, running = [0], 0      # `cum[i]` = copies ranked ABOVE group `i`; `cum[-1]` = every match
    for c in counts:
        running += c
        cum.append(running)
    total = comb(pool, window) if 0 <= window <= pool else 0
    if total <= 0 or take < 1:
        return {(): 1.0}
    # ONE definition of the whiff — the shared bracket, not this enumerator's all-zero branch, which
    # is why `emit` will not write `()` and why a zero-mass whiff is absent rather than present at 0.
    whiff = deck_odds.window_miss_probability(cum[-1], pool, window)
    out: dict = {(): whiff} if whiff > 0.0 else {}

    def emit(prefix: tuple, ways: float) -> None:
        klass = tuple(sorted(cid for cid, a in zip(order, prefix) for _ in range(a)))
        if klass:
            out[klass] = out.get(klass, 0.0) + ways / total

    def walk(i: int, slots: int, prefix: tuple, ways: int) -> None:
        if i == len(order):        # every group ranged over: the look held fewer than `take` matches
            rest = window - sum(prefix)
            if 0 <= rest <= pool - cum[i]:
                emit(prefix, ways * comb(pool - cum[i], rest))
            return
        for a in range(min(counts[i], slots) + 1):
            if a < slots:          # group not the cutoff, so EXACTLY `a` of it showed up
                walk(i + 1, slots - a, prefix + (a,), ways * comb(counts[i], a))
                continue
            # `a == slots` fills the delivery HERE, so any b >= a of this group leaves the same class
            # and everything ranked below is free: it was never reached.
            mass = sum(ways * comb(counts[i], b) * comb(pool - cum[i + 1], window - sum(prefix) - b)
                       for b in range(a, counts[i] + 1)
                       if 0 <= window - sum(prefix) - b <= pool - cum[i + 1])
            if mass:
                emit(prefix + (a,), mass)

    walk(0, take, (), 1)
    return out


def _dig_expectation(model, legs, pools: tuple, dig: int, *, class_of, score, cap, card_id, name):
    """A dig's classes: the WINDOW deals, and inside it I take the best-scoring match. The probabilities
    are exact under exactly that policy, so the ranking is part of the model rather than a display order."""
    from common.apply_option import DEALT, SCORE_PLACES, Expectation

    if score is None:
        _no(card_id, name, "a dig's classes are ordered by what each delivery is WORTH and no `score` "
                           "oracle was supplied — the window deals and I take the best match in it, "
                           "so the caller passes the value it ranks by, exactly as `_cost_indices` "
                           "makes it pass `shed`")
    union: dict = {}
    for pool in pools:
        union.update(pool)
    left, hidden = int(model.mine.deck_count), int(model.mine.hidden_outside_deck)
    singles = {cid: class_of((cid,), 0.0) for cid in union}
    # ADR-0128's noise floor, then the id: this ranking IS the policy priced, so two processes reading
    # one board must reach the same one or they enumerate different distributions.
    order = tuple(sorted(singles, key=lambda cid: (-round(float(score(singles[cid].model)),
                                                          SCORE_PLACES), cid)))
    # The look is at the top of the DECK, so it is that deep; the pool it is drawn from is every unseen
    # card, because deck-then-window composes to one uniform subset of deck+prizes (ADR-0133).
    weights = window_classes(order, union, left + hidden, min(int(dig), left), int(legs.cap))
    whiff = weights.pop((), 0.0)
    ranked = sorted(weights, key=lambda klass: (-weights[klass], klass))
    # The whiff is PINNED — under a greedy ranking the cap drops the WORST outcomes, which on a DEALT
    # node biases `expected()` upward. It never takes the only slot, or a live dig prices as dead.
    pinned = whiff > 0.0 and int(cap) >= 2
    kept, dropped = ranked[:int(cap) - pinned], ranked[int(cap) - pinned:]
    classes = [replace(singles[klass[0]], probability=weights[klass]) if len(klass) == 1
               else class_of(klass, weights[klass]) for klass in kept]
    if pinned:
        classes.append(class_of((), whiff))
    return Expectation(classes=tuple(classes), resolution=DEALT,
                       truncated=len(dropped) + (whiff > 0.0 and not pinned))


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
                shed=None, score=None):
    """``option``'s reveal as an :class:`~common.apply_option.Expectation`, or an ``Unmodellable``. A
    whole-deck search weights by AVAILABILITY and is CHOSEN; a dig by its window, and is DEALT (ADR-0133)."""
    from common.apply_option import CHOSEN, Expectation, OutcomeClass  # contract, imported lazily

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
    dig = _dig_depth(legs, card_id=card_id, name=name)

    def _class_of(delivered: tuple, probability: float):
        """One enumerated outcome. The reveal never reaches across the table, so their side is reusable."""
        after_obs, at = _revealed(model, option, delivered, seat_index=seat_index, stat=stat,
                                  paid=paid, dest=dest, card_id=card_id, name=name)
        return OutcomeClass(probability=probability,
                            model=model.rebuilt(after_obs, reuse_their_side=True),
                            fingerprint=_fingerprint(after_obs, at, seat_index, dest))

    def _whiff():
        """The known no-delivery transition — search still pays its normal play cost."""
        return Expectation(classes=(_class_of((), 1.0),), resolution=CHOSEN)

    if dest == "bench":
        # TRUNCATES, never filters: every carrier searches for "up to" N, so one slot delivers one
        # body — dropping the oversized class would refuse a legal play.
        room = _bench_room(model, seat_index)
        if room <= 0:
            _no(card_id, name, "my Bench is full, so there is no open Bench slot for it to deliver "
                               "into — the play is unreachable on this board, and enumerating a "
                               "zero-body delivery would rank a dead Item beside a live one")
        legs = legs._replace(cap=min(int(legs.cap), room))
    # A single/union search says “up to” its cap, so the known deck size keeps its reachable partial class.
    # This avoids an impossible full delivery with zero mass; conjunctions have separate per-leg budgets.
    if legs.relation != "conjunction":
        legs = legs._replace(cap=min(int(legs.cap), int(model.mine.deck_count)))
    pools = tuple(outcome_pool(model, leg) for leg in legs.legs)
    if dig is not None:
        return _dig_expectation(model, legs, pools, dig, class_of=_class_of, score=score, cap=cap,
                                card_id=card_id, name=name)
    candidates = _classes_for(legs, pools)
    if not candidates:
        return _whiff()
    weights = {klass: _class_weight(model, klass) for klass in candidates}
    mass = sum(weights.values())
    if mass <= 0.0:
        if int(model.mine.deck_count) == 0:
            return _whiff()
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
    return Expectation(classes=tuple(classes), truncated=len(dropped), resolution=CHOSEN)


__all__ = ("BRANCH_CAP", "ClosedFormRoute", "CLOSED_FORM_ROUTES", "closed_form_transition",
           "revealing_clauses", "outcome_pool", "window_classes", "expectation")
