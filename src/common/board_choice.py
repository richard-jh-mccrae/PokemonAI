"""**The choice node** — the boards a Deferred-Target Option can reach (Issue #392). Ruling: ADR-0121.

Three modules answer *"what board does this option produce?"*: `board_delta` for a deterministic node,
`board_expectation` for a reveal's distribution, this one for an option whose TARGET is deferred.

**LIVE at runtime** — `composer._one_ply` opts in unconditionally, so this module prices every retreat
the MAIN menu offers. The Target Rankers only prefilter: `state_value` decides."""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import NamedTuple, NoReturn

from common import (board_delta, board_expectation, currency, needs, retreat_cost,
                    snapshot_coverage)
from common.board_delta import Unmodellable
from common.fetch_closure import fetch_target_matches, multiset_classes, reveal_legs
from common.option_equivalence import AREA_ACTIVE, AREA_BENCH, AREA_HAND, option_fingerprint
from common.promote_retreat_value import PromoteBody, PromoteRetreatInputs, promote_value
from common.scouting.matchup_plan import ROLE_REGISTRY
from common.strategy.context import _PLAY, _RETREAT

#: Kinds whose target is STRUCTURALLY deferred: `_RETREAT` carries no card, so no clause either.
CHOICE_KINDS: frozenset[int] = frozenset({_RETREAT})

#: Clause kinds with a deferred target — the CLASS vocabulary. :data:`CHOICE_REGISTRY` says which
#: members have a resolver and which have a board synthesis; a member with neither is a census entry.
CHOICE_CLAUSES: frozenset[str] = frozenset({"gust", "heal", "accel", "self_switch"})

#: A search of a VISIBLE zone. NOT a `CHOICE_CLAUSES` member, and the ZONE is the distinction: a DECK
#: fetch is the chance node's (hidden zone, `deck_odds`), a DISCARD fetch is this node's (no chance).
FETCH_DISCARD: str = "fetch_discard"

#: A deck fetch whose destination is an existing body. Unlike a hand fetch it reveals no usable
#: intermediate card: the player chooses both the Evolution and the body it replaces.
FETCH_IN_PLAY: str = "fetch_in_play"

#: The clause keys a `FETCH_DISCARD` leg may carry — deliberately NARROWER than
#: `board_expectation._HANDLED_FETCH_KEYS`: this applier would silently ignore `cost` / `dest` / `trigger`.
_HANDLED_DISCARD_KEYS: frozenset[str] = frozenset({
    "kind", "target", "zone", "amount", "choice", "energy_type", "no_rule_box", "no_ability",
})

#: **Every key :data:`CHOICE_REGISTRY` may carry.** Three families, keyed differently because they ARE
#: different: an option kind (int), a clause kind (str), and a zone-qualified clause family.
CHOICE_KEYS: frozenset = (frozenset(CHOICE_KINDS) | CHOICE_CLAUSES |
                           frozenset({FETCH_DISCARD, FETCH_IN_PLAY}))

@dataclass(frozen=True)
class ChoiceKind:
    """One deferred-target key's legs. ``space``/``canonical``/``apply`` take ``(model, x, *,
    seat_index)``; ``rank`` is ``(model, candidate) -> float``, DESC; ``fingerprint`` is post-choice."""

    space: object
    canonical: object
    rank: object = None
    apply: object = None
    fingerprint: object = None
    #: `False` when this choice changes their materialised side (a gust), forbidding reuse.
    shares_opponent: bool = True
    no_applier: str = ""

    def __post_init__(self):
        if (self.apply is None) != (self.fingerprint is None):
            raise ValueError("`apply` and `fingerprint` are one capability in two halves — a board "
                             "nothing can fingerprint joins no class, and a fingerprint over a board "
                             "nothing writes has nothing to take")
        if self.apply is None and not self.no_applier.strip():
            raise ValueError("a key with no board synthesis must say WHY — the message is destined "
                             "for the telemetry line and the modelling backlog, which groups by it")


#: `needs.opponent_target_value`'s ceiling — the yardstick that reads a prize-denominated marginal as
#: the dimensionless `[0, 1]` relevance `currency.tiebreak_bonus` requires. Read, never restated.
TARGET_VALUE_CEILING = needs.TARGET_VALUE_CEILING


# ── the D7 combination: `value` and `role_priority`, on one sort key ───────────────────────────────


def role_span(registry: dict | None = None) -> float:
    """``max(abs(priority))`` over `matchup_plan.ROLE_REGISTRY` — the normaliser mapping an ordinal
    role priority into ``[-1, 1]``. DERIVED per call; 1.0 on an empty or all-zero sheet, so it is total."""
    sheet = ({name: role.priority for name, role in ROLE_REGISTRY.items()}
             if registry is None else registry)
    return max((abs(float(p)) for p in sheet.values()), default=0.0) or 1.0


def gust_rank_key(rows, *, registry: dict | None = None):
    """One sort key for a whole opponent-target MENU (not one row): `value`, tie-broken by `role_priority`,
    sorted DESC. `currency.tiebreak_bonus` sizes the quantum, so a role orders ONLY exact ties (Issue #395)."""
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
    raise Unmodellable(f"{what}: {why}")


def _my_active(obs: dict, seat_index: int) -> dict | None:
    return next((b for b in (_my_side(obs, seat_index).get("active") or ()) if b), None)


def _after_discard(model, body: dict, discard_idx) -> tuple:
    """``(the body minus the discarded Energy cards, the cards that went)`` — ONE derivation, shared by
    the ranker and the applier. ``energies`` is RE-DERIVED: provision depends on the HOLDER too."""
    cards = list(body.get("energyCards") or ())
    drop = {int(i) for i in discard_idx}
    kept = [c for i, c in enumerate(cards) if i not in drop]
    after = dict(body, energyCards=kept, energies=board_delta.units_for_cards(
        model.combat, kept, holder_stat=model.card_stat(body.get("id"))))
    return after, [c for i, c in enumerate(cards) if i in drop]


def _my_side(obs: dict, seat_index: int) -> dict:
    players = ((obs.get("current") or {}).get("players")) or []
    if not 0 <= seat_index < len(players) or not players[seat_index]:
        _no(f"seat {seat_index}", "this snapshot carries no player at that seat")
    return players[seat_index]


# ── the choice key: which registry entry an option routes to ──────────────────────────────────────


def choice_key(model, option: dict, *, seat_index: int):
    """The registry key this option's deferred target routes under — an option KIND (int) or a clause
    KIND (str). Refuses anything with no deferred target, so a point transition cannot land here."""
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
    # A search of a VISIBLE zone is this node's. Asked BEFORE the `CHOICE_CLAUSES` test because `fetch`
    # is deliberately not a member, and it must be a discard search AND NOTHING ELSE to route here.
    fetches = tuple(c for c in every if c.get("kind") == "fetch")
    if (len(fetches) == 1 and len(fetches) == len(every)
            and fetches[0].get("zone") == "deck" and fetches[0].get("dest") == "in_play"):
        return FETCH_IN_PLAY
    if fetches and len(fetches) == len(every) and all(c.get("zone") == "discard" for c in fetches):
        try:
            reveal_legs(every)              # the ONE relation reader, shared with the chance node
        except ValueError as gap:
            _no(f"{card_id} {name}", str(gap))
        # The same rule the chance node keeps: this applier writes a plain hand delivery, so a discard
        # fetch that grew a `cost`, `dest` or `trigger` would be applied as though it had none.
        for leg in reveal_legs(every).legs:
            unknown = sorted(set(leg) - _HANDLED_DISCARD_KEYS)
            if unknown:
                _no(f"{card_id} {name}",
                    f"clause key(s) {unknown} are not in this node's handled set — fail closed "
                    f"against vocabulary drift, exactly as `board_expectation._check_clause` does "
                    f"for the deck half")
        return FETCH_DISCARD
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
    clause = deferred[0]
    key = clause.get("kind")
    # A clause kind is a family, not a promise every carrier has this exact card shape.
    # Other carriers keep their point-seam refusal rather than becoming Wally/Crispin by accident.
    supported = {
        "gust": set(clause) == {"kind", "target"},
        "heal": (clause.get("amount"), clause.get("restriction"), clause.get("rider"))
                == ("all", "mega_only", "bounce_energy_to_hand"),
        "accel": (clause.get("amount"), clause.get("source"), clause.get("target"),
                  clause.get("energy"), clause.get("to_hand"), clause.get("distinct_types"))
                 == (1, "deck", "any_pokemon", "basic", 1, True),
        "self_switch": set(clause) == {"kind"},
    }
    if not supported.get(key, False):
        _no(f"{card_id} {name}",
            f"the deferred {key!r} clause is not this issue's closed card shape — its target family "
            "remains a point-seam refusal until its own full synthesis is built")
    return key


def has_deferred_target(model, option: dict, *, seat_index: int) -> bool:
    """Does this option defer its target — the ROUTING question, as a boolean, because `apply_option`'s
    dispatch must not raise. Nothing is swallowed: `board_delta._play` refuses the same cards by name."""
    try:
        choice_key(model, option, seat_index=seat_index)
    except Unmodellable:
        return False
    return True


# ── the target CLASS resolver ─────────────────────────────────────────────────────────────────────
# ADR-0121 decision 2: expansion is data-driven off the compendium's target vocabulary, never per-card.


def _stage(stat) -> str:
    """``CardStat.stage`` normalised, or ``""``. The `.lower()` is a coercion across a provider seam."""
    return (getattr(stat, "stage", None) or "").lower()


class _BodyPlace(NamedTuple):
    active: bool
    mine: bool


#: Declared `target` values evaluable against a body in play — a SUBSET of `CLAUSE_SELECTORS["target"]`
#: by construction. FAIL-CLOSED on a missing `stage`: an unreadable body matches no stage class.
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

#: Declared `target` values naming a CARD class, not a body. Listed rather than merely absent so the
#: refusal says *category error* instead of *unimplemented* — that is work which does not exist.
_CARD_CLASS_TARGETS = frozenset({
    "basic_energy", "energy", "item", "own_line", "own_type", "stadium", "supporter", "tool",
    "trainer", "future",
})

#: Clause keys the class resolver honours; anything else refuses, fail-closed against vocabulary drift.
#: `zone` and `source` are absent because they select a CARD ZONE, and a body in play is in none.
_HANDLED_TARGET_KEYS = frozenset({"kind", "target", "target_type", "restriction"})

_RESTRICTIONS = {
    "mega_only":   lambda stat, place: bool(getattr(stat, "megaEx", False)),
    "active_only": lambda stat, place: place.active,
}


def target_predicate(clause: dict):
    """``(CardStat, _BodyPlace) -> bool`` for one clause's declared target class, or a refusal. Three
    ways to fail get three DIFFERENT sentences — drift, category error, scoped gap — being three jobs."""
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
        # Fail CLOSED on an unreadable body: a class we cannot evaluate must not widen to *every* body.
        return stat is not None and all(leg(stat, place) for leg in legs)
    return match


# ── target spaces ─────────────────────────────────────────────────────────────────────────────────


def _retreat_space(model, option: dict, *, seat_index: int) -> tuple:
    """A retreat's product space: ``((discarded energy-card indices), promoted bench index)`` (ADR-0121
    §5). Identical Energy cards collapse on id HERE, because `option_fingerprint` compares BY ORDER."""
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
    """A gust's space: the opponent in-play bodies its clause's declared target CLASS names — the KIND
    gives the scope, the `target` selector narrows through :data:`BODY_PREDICATES`, never per-card."""
    obs = model.source_obs
    players = ((obs.get("current") or {}).get("players")) or []
    them = players[1 - seat_index] if len(players) > 1 else None
    if not them:
        _no("gust", "this snapshot carries no opponent side to reach across to")
    clause = _clause_of(model, option, seat_index=seat_index)
    match = target_predicate(clause)
    return tuple(i for i, b in enumerate(them.get("bench") or ())
                 if b and match(model.card_stat(b.get("id")), _BodyPlace(active=False, mine=False)))


def _body_clause(clause: dict) -> dict:
    """The body-selector portion of a multi-leg clause, kept closed over target vocabulary."""
    return {key: clause[key] for key in ("kind", "target", "target_type", "restriction")
            if key in clause}


def _own_body_space(model, clause: dict, *, seat_index: int) -> tuple:
    """Own target coordinates as ``(area, index)`` for a clause that names a body class."""
    match = target_predicate(_body_clause(clause))
    me = _my_side(model.source_obs, seat_index)
    out = []
    for area, zone in ((AREA_ACTIVE, "active"), (AREA_BENCH, "bench")):
        for index, body in enumerate(me.get(zone) or ()):
            if body and match(model.card_stat(body.get("id")),
                              _BodyPlace(active=area == AREA_ACTIVE, mine=True)):
                out.append((area, index))
    return tuple(out)


def _heal_space(model, option: dict, *, seat_index: int) -> tuple:
    return _own_body_space(model, _clause_of(model, option, seat_index=seat_index),
                           seat_index=seat_index)


def _self_switch_space(model, option: dict, *, seat_index: int) -> tuple:
    """Switch-like effects choose one occupied own Bench slot; they are not manual retreats."""
    return tuple(i for i, body in enumerate(_my_side(model.source_obs, seat_index).get("bench") or ())
                 if body)


def _accel_space(model, option: dict, *, seat_index: int) -> tuple:
    """Crispin's product: one basic Energy to attach, a distinct-type one to hand, and a body."""
    clause = _clause_of(model, option, seat_index=seat_index)
    if (clause.get("source"), clause.get("energy"), clause.get("amount"), clause.get("to_hand"),
            clause.get("distinct_types")) != ("deck", "basic", 1, 1, True):
        _no("accel", "only the declared Crispin shape (deck basic 1 + to_hand 1, distinct types) "
                     "has a product resolver")
    energies = tuple(cid for cid, count in model.mine.unseen_counts.items() if count > 0
                     and bool(getattr(model.card_stat(cid), "is_typed_basic_energy", False)))
    targets = _own_body_space(model, clause, seat_index=seat_index)
    return tuple((attached, delivered, area, index)
                 for attached in energies for delivered in energies
                 if getattr(model.card_stat(attached), "energyType", None)
                 != getattr(model.card_stat(delivered), "energyType", None)
                 for area, index in targets)


def _in_play_fetch_space(model, option: dict, *, seat_index: int) -> tuple:
    """Salvatore's deck Evolution paired with the own body it actually evolves from."""
    clause = next(c for c in board_delta.card_clauses(
        model.combat, _played_id(model, option, seat_index=seat_index)) if c.get("kind") == "fetch")
    if clause.get("zone") != "deck" or clause.get("dest") != "in_play":
        _no("fetch", "this resolver is only for a deck fetch whose destination is in_play")
    out = []
    me = _my_side(model.source_obs, seat_index)
    for cid, count in model.mine.unseen_counts.items():
        stat = model.card_stat(cid)
        if not count or stat is None or not fetch_target_matches(clause, stat):
            continue
        for area, zone in ((AREA_ACTIVE, "active"), (AREA_BENCH, "bench")):
            for index, body in enumerate(me.get(zone) or ()):
                base = model.card_stat((body or {}).get("id"))
                if body and getattr(stat, "evolvesFrom", None) == getattr(base, "name", None):
                    out.append((cid, area, index))
    return tuple(out)


def _clause_of(model, option: dict, *, seat_index: int) -> dict:
    obs = model.source_obs
    hand = _my_side(obs, seat_index).get("hand") or ()
    card_id = (hand[option.get("index")] or {}).get("id")
    return next(c for c in board_delta.card_clauses(model.combat, card_id)
                if c.get("kind") in CHOICE_CLAUSES)


def _discard_matches(model, option: dict, *, seat_index: int) -> tuple:
    """``(legs, {card id: copies in my discard this search can take})``. The zone is face-up, so the
    counts are what the discard HOLDS and there is no availability question — no `deck_odds` call."""
    legs = reveal_legs(board_delta.card_clauses(model.combat, _played_id(model, option, seat_index=seat_index)))
    discard = _my_side(model.source_obs, seat_index).get("discard") or ()
    pool: dict = {}
    for card in discard:
        cid = (card or {}).get("id")
        stat = model.card_stat(cid)
        if stat is None:
            continue
        if any(fetch_target_matches(leg, stat) for leg in legs.legs):
            pool[cid] = pool.get(cid, 0) + 1
    return legs, pool


def _discard_space(model, option: dict, *, seat_index: int) -> tuple:
    """The distinct deliveries a discard search can make, as ``(hand index, (card id, …))`` — over CARD
    IDS, the collapse `option_fingerprint` performs anyway. The index rides along: ``apply`` gets no option."""
    legs, pool = _discard_matches(model, option, seat_index=seat_index)
    index = int(option.get("index"))
    return tuple((index, klass) for klass in multiset_classes(pool, legs.cap))


def _apply_discard_fetch(model, candidate, *, seat_index: int, option=None) -> tuple:
    """``(post-choice observation, the zones it wrote)`` for one discard-search delivery. The source
    card is discarded AFTER the search resolves, so it can never be one of the cards taken (L78)."""
    hand_index, delivered = candidate
    new_obs, current, players = board_delta.fork(model.source_obs)
    me = board_delta.fork_player(players, seat_index)
    played = board_delta.take_from_hand(me, hand_index, "discard search")
    discard = list(me.get("discard") or ())
    hand = list(me.get("hand") or ())
    for cid in delivered:
        at = next(i for i, c in enumerate(discard) if (c or {}).get("id") == cid)
        hand.append(discard.pop(at))
    me["discard"] = discard + [played]
    me["hand"] = hand
    if me.get("handCount") is not None:
        me["handCount"] = len(hand)
    stat = model.card_stat((played or {}).get("id"))
    if getattr(stat, "is_supporter", False):
        current["supporterPlayed"] = True          # `docs/rules.md` §3 — one Supporter per turn
    return new_obs, frozenset({"my_hand_ids", "my_discard_contents"})


def _fingerprint_discard(after_obs: dict, candidate, *, seat_index: int, kind) -> tuple:
    _hand_index, delivered = candidate
    hand = ((after_obs.get("current") or {}).get("players") or [{}])[seat_index].get("hand") or ()
    first = len(hand) - len(delivered)
    return tuple(option_fingerprint({"type": _PLAY, "area": AREA_HAND, "index": i,
                                     "playerIndex": seat_index}, after_obs)
                 for i in range(first, len(hand)))


def _rank_discard(model, candidate) -> float:
    """The delivery's declared Role Worth — **ordering only**: it enters no score and adds to no delta,
    it only decides which classes survive the cap. A magnitude would be a rung; a sort key is not."""
    _hand_index, delivered = candidate
    return float(sum(model.mine.role_worth(cid) for cid in delivered))


def _played_id(model, option: dict, *, seat_index: int):
    hand = _my_side(model.source_obs, seat_index).get("hand") or ()
    return (hand[int(option.get("index"))] or {}).get("id")


def target_space(model, option: dict, *, seat_index: int) -> tuple:
    """The legal target INSTANCES, from the declared target CLASS against the board. Empty is never
    returned: a zero-class Expectation is an un-enumerated effect whose ``expected()`` raises."""
    key = choice_key(model, option, seat_index=seat_index)
    entry = CHOICE_REGISTRY.get(key)
    if entry is None:
        _no(f"choice key {key!r}",
            "declared in `CHOICE_CLAUSES` as a member of the deferred-target census, but no target "
            "SPACE resolver is built for it (Issue #392 § Scope: `_RETREAT` is buildable now, the "
            "`_PLAY` members are not)")
    space = entry.space(model, option, seat_index=seat_index)
    if not space:
        _no(f"choice key {key!r}", "its target class resolves to no legal instance on this board")
    return tuple(space)


# ── Target Rankers ────────────────────────────────────────────────────────────────────────────────


def _build_standing(model, body: dict) -> float:
    """Damage-currency projection of the canonical multi-attack build profile."""
    from common.state_value import combat_build_profile
    return combat_build_profile(model, body).value_damage if body else 0.0


def _promote_body(model, raw: dict) -> PromoteBody:
    """B's damage-currency reading from what a `StateModel` supplies — the Pilot-owned ADR-0100 terms
    stay at their dataclass defaults, so this prices ``reach − exposure − fatal`` as a PREFILTER."""
    view = model.mine.view_of(raw)
    return PromoteBody(
        reach=float(model.mine.best_reachable_damage(view)),
        prizes=int(getattr(view, "prize_value", 1) or 1),
        ko_active=int(model.theirs.turns_to_ko_me(raw)),
        opp_prizes_remaining=int(getattr(model.theirs, "prizes_remaining", 6) or 6),
    )


def rank_retreat(model, candidate) -> float:
    """A retreat candidate's prefilter score — ADR-0100's retreat equation with its A-side constants
    dropped, which cannot change an ordering: ``promote_value(B) + build_after(A | discard set)``."""
    discard_idx, promote_idx = candidate
    obs, seat = model.source_obs, int(model.my_index)
    active = _my_active(obs, seat)
    bench = list(_my_side(obs, seat).get("bench") or ())
    promo = promote_value(PromoteRetreatInputs(body=_promote_body(model, bench[promote_idx]))).total
    after, _went = _after_discard(model, active, discard_idx)
    return float(promo) + _build_standing(model, after)


#: The prefilters, keyed by :func:`choice_key`'s answer; sorted DESCENDING, and built from
#: :data:`CHOICE_REGISTRY`. `gust` is ABSENT: its ranker takes a MENU, so it arrives via ``ranker=``.
TARGET_RANKERS: dict = {}


# ── board synthesis ───────────────────────────────────────────────────────────────────────────────


def _apply_retreat(model, candidate, *, seat_index: int, option=None) -> tuple:
    """``(post-choice observation, the zones it wrote)`` for one retreat candidate, composed from
    `board_delta`'s parity-verified primitives. A SWAP IN PLACE: A lands on the vacated bench index."""
    discard_idx, promote_idx = candidate
    new_obs, current, players = board_delta.fork(model.source_obs)
    me = board_delta.fork_player(players, seat_index)
    actives = list(me.get("active") or ())
    a = dict(actives[0])
    writes = {"allowance_retreat_used", "bodies_in_play"}

    if discard_idx:
        # The SAME derivation the ranker prices, so it cannot order a board this never writes.
        a, went = _after_discard(model, a, discard_idx)
        me["discard"] = list(me.get("discard") or ()) + went
        writes.update({"attached_energy", "my_discard_contents"})

    me["active"] = [a] + actives[1:]
    board_delta.switch_active_with_bench(me, promote_idx)
    current["retreated"] = True                      # `docs/rules.md` §3 — one manual retreat a turn
    # `docs/rulebook.txt` L143 — a body reaching the Bench recovers from every Special Condition.
    if board_delta.clear_conditions(me):
        writes.add("special_conditions")
    return new_obs, frozenset(writes)


def _spent_trainer(model, option: dict, *, seat_index: int) -> tuple[dict, dict, dict, dict, set]:
    """Fork, spend the source card, and place a Trainer into discard at its settled board."""
    new_obs, current, players = board_delta.fork(model.source_obs)
    me = board_delta.fork_player(players, seat_index)
    played = board_delta.take_from_hand(me, option.get("index"), "choice play")
    me["discard"] = list(me.get("discard") or ()) + [played]
    writes = {"my_hand_ids", "my_discard_contents"}
    stat = model.card_stat(played.get("id"))
    if getattr(stat, "is_supporter", False):
        current["supporterPlayed"] = True
        writes.add("allowance_supporter_played")
    return new_obs, current, players, me, writes


def _found_card(card_id: int, seat_index: int) -> dict:
    """A stable synthetic identity for one card selected from a hidden deck by id."""
    return {"id": int(card_id), "serial": -10_000_000 - int(card_id), "playerIndex": seat_index}


def _decrease_deck(seat: dict, amount: int) -> None:
    if seat.get("deckCount") is not None:
        seat["deckCount"] = max(0, int(seat.get("deckCount") or 0) - int(amount))


def _apply_gust(model, candidate, *, seat_index: int, option: dict) -> tuple:
    new_obs, _current, players, _me, writes = _spent_trainer(model, option, seat_index=seat_index)
    them = board_delta.fork_player(players, 1 - seat_index)
    board_delta.switch_active_with_bench(them, candidate)
    # Moving an Active also changes which one-body transient grants apply.
    writes.update({"bodies_in_play", "transient_grants"})
    if board_delta.clear_conditions(them):
        writes.add("special_conditions")
    return new_obs, frozenset(writes)


def _target_body(seat: dict, area: int, index: int) -> dict:
    zone = "active" if area == AREA_ACTIVE else "bench" if area == AREA_BENCH else None
    bodies = seat.get(zone) or () if zone else ()
    if not isinstance(index, int) or not 0 <= index < len(bodies) or not bodies[index]:
        _no("choice target", f"({area!r}, {index!r}) is not an occupied own body")
    return bodies[index]


def _apply_heal(model, candidate, *, seat_index: int, option: dict) -> tuple:
    area, index = candidate
    new_obs, _current, _players, me, writes = _spent_trainer(model, option, seat_index=seat_index)
    target = _target_body(me, area, index)
    if int(target.get("hp") or 0) >= int(target.get("maxHp") or 0):
        return new_obs, frozenset(writes)
    body = dict(target, hp=int(target.get("maxHp") or 0))
    cards = list(body.get("energyCards") or ())
    body["energyCards"], body["energies"] = [], []
    board_delta.replace_body(me, area, index, body)
    if cards:
        me["hand"] = list(me.get("hand") or ()) + cards
        if me.get("handCount") is not None:
            me["handCount"] = len(me["hand"])
        writes.update({"attached_energy", "my_hand_ids"})
    writes.add("damage_counters")
    return new_obs, frozenset(writes)


def _apply_self_switch(model, candidate, *, seat_index: int, option: dict) -> tuple:
    new_obs, _current, _players, me, writes = _spent_trainer(model, option, seat_index=seat_index)
    board_delta.switch_active_with_bench(me, candidate)
    # Unlike retreat this leaves the manual-retreat allowance alone, but it still moves grants.
    writes.update({"bodies_in_play", "transient_grants"})
    if board_delta.clear_conditions(me):
        writes.add("special_conditions")
    return new_obs, frozenset(writes)


def _apply_accel(model, candidate, *, seat_index: int, option: dict) -> tuple:
    attached, delivered, area, index = candidate
    new_obs, _current, _players, me, writes = _spent_trainer(model, option, seat_index=seat_index)
    board_delta.attach_energy_card(me, _found_card(attached, seat_index), area=area, index=index,
                                   combat=model.combat)
    me["hand"] = list(me.get("hand") or ()) + [_found_card(delivered, seat_index)]
    if me.get("handCount") is not None:
        me["handCount"] = len(me["hand"])
    _decrease_deck(me, 2)
    writes.update({"attached_energy", "my_hand_ids", "my_deck_count", "deck_odds"})
    return new_obs, frozenset(writes)


def _apply_in_play_fetch(model, candidate, *, seat_index: int, option: dict) -> tuple:
    card_id, area, index = candidate
    new_obs, current, _players, me, writes = _spent_trainer(model, option, seat_index=seat_index)
    writes.update(board_delta.evolve_body(current, me, _found_card(card_id, seat_index), area=area,
                                          index=index, seat_index=seat_index, combat=model.combat))
    _decrease_deck(me, 1)
    writes.update({"my_deck_count", "deck_odds"})
    return new_obs, frozenset(writes)


def _fingerprint_retreat(after_obs: dict, candidate, *, seat_index: int, kind: int) -> tuple:
    """The class identity — `option_fingerprint` over BOTH bodies the choice moved. A pair, or two
    candidates promoting the same body while discarding different Energy would be one class."""
    _discard_idx, promote_idx = candidate
    return tuple(option_fingerprint({"type": kind, "inPlayArea": area, "inPlayIndex": index,
                                     "playerIndex": seat_index}, after_obs)
                 for area, index in ((AREA_ACTIVE, 0), (AREA_BENCH, promote_idx)))


def _fingerprint_body(after_obs: dict, candidate, *, seat_index: int, kind: int) -> tuple:
    """A target body's post-effect identity; `candidate` ends in its own ``(area, index)`` pair."""
    area, index = candidate[-2:]
    return (option_fingerprint({"type": kind, "inPlayArea": area, "inPlayIndex": index,
                               "playerIndex": seat_index}, after_obs),)


def _fingerprint_switch(after_obs: dict, candidate, *, seat_index: int, kind: int) -> tuple:
    return tuple(option_fingerprint({"type": kind, "inPlayArea": area, "inPlayIndex": index,
                                     "playerIndex": seat_index}, after_obs)
                 for area, index in ((AREA_ACTIVE, 0), (AREA_BENCH, candidate)))


def _fingerprint_gust(after_obs: dict, candidate, *, seat_index: int, kind: int) -> tuple:
    opponent = 1 - seat_index
    return tuple(option_fingerprint({"type": kind, "inPlayArea": area, "inPlayIndex": index,
                                     "playerIndex": opponent}, after_obs)
                 for area, index in ((AREA_ACTIVE, 0), (AREA_BENCH, candidate)))


def _fingerprint_accel(after_obs: dict, candidate, *, seat_index: int, kind: int) -> tuple:
    attached, delivered, area, index = candidate
    body = option_fingerprint({"type": kind, "inPlayArea": area, "inPlayIndex": index,
                               "playerIndex": seat_index}, after_obs)
    hand = ((after_obs.get("current") or {}).get("players") or [{}])[seat_index].get("hand") or ()
    return body, tuple((card or {}).get("id") for card in hand[-1:]), attached, delivered


def _canonical_retreat(model, candidate, *, seat_index: int) -> tuple:
    discard_idx, promote_idx = candidate
    cards = list((_my_active(model.source_obs, seat_index) or {}).get("energyCards") or ())
    return (tuple(sorted((cards[i] or {}).get("id") for i in discard_idx
                         if 0 <= int(i) < len(cards))), promote_idx)


def _canonical_identity(model, candidate, *, seat_index: int):
    """The candidate IS its own equivalence key — its space's members are already the distinct choices."""
    return candidate


#: **ONE registry entry per deferred-target key**, so the sync obligation is STRUCTURAL rather than
#: kept by prose. ``apply``/``fingerprint`` are None where no synthesis exists; ``no_applier`` says why.
CHOICE_REGISTRY: dict = {
    _RETREAT: ChoiceKind(
        space=_retreat_space, canonical=_canonical_retreat, rank=rank_retreat,
        apply=_apply_retreat, fingerprint=_fingerprint_retreat),
    "gust": ChoiceKind(
        space=_gust_space, canonical=_canonical_identity, apply=_apply_gust,
        fingerprint=_fingerprint_gust, shares_opponent=False),
    "heal": ChoiceKind(space=_heal_space, canonical=_canonical_identity, apply=_apply_heal,
                       fingerprint=_fingerprint_body),
    "accel": ChoiceKind(space=_accel_space, canonical=_canonical_identity, apply=_apply_accel,
                        fingerprint=_fingerprint_accel),
    "self_switch": ChoiceKind(space=_self_switch_space, canonical=_canonical_identity,
                              apply=_apply_self_switch, fingerprint=_fingerprint_switch),
    FETCH_IN_PLAY: ChoiceKind(space=_in_play_fetch_space, canonical=_canonical_identity,
                              apply=_apply_in_play_fetch, fingerprint=_fingerprint_body),
    FETCH_DISCARD: ChoiceKind(
        space=_discard_space, canonical=_canonical_identity, rank=_rank_discard,
        apply=_apply_discard_fetch, fingerprint=_fingerprint_discard),
}

assert set(CHOICE_REGISTRY) <= CHOICE_KEYS, sorted(set(CHOICE_REGISTRY) - CHOICE_KEYS)

TARGET_RANKERS.update({key: k.rank for key, k in CHOICE_REGISTRY.items() if k.rank is not None})


# ── the node ────────────────────────────────────────────────────────────────────────────────────────


def candidate_class(model, option: dict, candidate, *, seat_index: int) -> tuple:
    """The equivalence key ``candidate`` reduces to in :func:`target_space`'s coordinates. Public for
    `tools/train/choice_parity.py`: on a raw tuple an equivalent representative reads as a hole."""
    return CHOICE_REGISTRY[choice_key(model, option, seat_index=seat_index)].canonical(
        model, candidate, seat_index=seat_index)


_OPTION_BOUND_KEYS = frozenset({"gust", "heal", "accel", "self_switch", FETCH_IN_PLAY})


def _apply_entry(entry, key, model, option, candidate, *, seat_index: int):
    """Keep the pre-existing candidate-carried applier protocol intact for its parity controls."""
    if key in _OPTION_BOUND_KEYS:
        return entry.apply(model, candidate, seat_index=seat_index, option=option)
    return entry.apply(model, candidate, seat_index=seat_index)


def realise(model, option: dict, candidate, *, seat_index: int) -> tuple:
    """``(post-choice observation, class fingerprint)`` for ONE candidate, realised **verbatim** — never
    canonicalised, or it would disagree with the board `tools/train/choice_parity.py` diffs against."""
    key = choice_key(model, option, seat_index=seat_index)
    entry = CHOICE_REGISTRY[key]
    after_obs, _writes = _apply_entry(entry, key, model, option, candidate, seat_index=seat_index)
    return after_obs, entry.fingerprint(after_obs, candidate, seat_index=seat_index,
                                        kind=int((option or {}).get("type", -1)))


def deferred_target(model, option: dict, *, seat_index=None, context=None,
                    cap: int = board_expectation.BRANCH_CAP, ranker=None):
    """The boards this option's deferred target can reach, as an `apply_option.Expectation`. The
    composer takes the **max** over ``classes``, never ``.expected()``. Never mutates ``model``."""
    from common.apply_option import CHOSEN, Expectation, OutcomeClass  # contract, imported lazily

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
    # Descending rank, then the candidate itself: the ordering must be a pure function of the board.
    ordered = tuple(space) if rank is None else tuple(
        sorted(space, key=lambda c: (-float(rank(model, c)), c)))

    # Collapse on the fingerprint THEN cap, so the cap bounds distinct DECISIONS, not candidates. The
    # observation is cheap copy-on-write; the `StateModel` wrapper is built only for survivors.
    distinct: dict = {}
    for candidate in ordered:
        after_obs, _writes = _apply_entry(entry, key, model, option, candidate, seat_index=seat_index)
        fingerprint = entry.fingerprint(after_obs, candidate, seat_index=seat_index, kind=kind)
        distinct.setdefault(fingerprint, after_obs)
    total = len(distinct)
    kept = list(distinct.items())[:int(cap)]
    return Expectation(
        classes=tuple(OutcomeClass(
            probability=1.0 / float(total),
            model=model.rebuilt(after_obs, reuse_their_side=entry.shares_opponent),
            fingerprint=fingerprint) for fingerprint, after_obs in kept),
        truncated=total - len(kept), resolution=CHOSEN)


__all__ = ("CHOICE_KINDS", "CHOICE_CLAUSES", "FETCH_DISCARD", "FETCH_IN_PLAY", "CHOICE_KEYS",
           "TARGET_VALUE_CEILING", "ChoiceKind",
           "CHOICE_REGISTRY", "TARGET_RANKERS", "role_span", "gust_rank_key", "choice_key", "target_space",
           "rank_retreat", "has_deferred_target", "candidate_class", "realise",
           "deferred_target")
