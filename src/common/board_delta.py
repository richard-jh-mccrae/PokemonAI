"""The closed-form board delta — ONE ENGINE STEP, synthesized arithmetically (ADR-0098, Issue #382).

`apply_option` owns the contract; this owns the arithmetic, and raises :class:`Unmodellable` for
anything it cannot write in one step. The unit is the ENGINE's step, not the human notion of a play.

**Copy-on-write, never in-place and never a deep copy**: `state_value` memoizes onto the model and
nothing invalidates that key, so a mutated model returns a stale scalar in silence.

⚠️ ``energies`` is Energy UNITS, not a card list — card ids stop equalling `EnergyType` codes at the
ninth card (`board_cards.py`)."""
from __future__ import annotations

from dataclasses import dataclass

from common import snapshot_coverage
from common.board_cards import body_unit_codes
# `cg.api.AreaType` numbers, DLL-free and pinned to the engine enum by a test.
from common.option_equivalence import AREA_ACTIVE, AREA_BENCH, AREA_HAND
from common.strategy.context import _ATTACH, _EVOLVE, _PLAY, _RETREAT

#: `cg.api.SelectContext.MAIN`, the only context this module transitions at. Matters most for
#: `_ATTACH`: an attach posed inside a card's effect spends no manual allowance and never lands here.
CONTEXT_MAIN = 0

#: On `PlayerState` rather than on the body — only the Active can carry one (`docs/rules.md` §8).
CONDITION_FLAGS = ("poisoned", "burned", "asleep", "paralyzed", "confused")

#: Fallback when an observation omits the engine's own ``benchMax``; only a hand-built board reaches
#: it.
_BENCH_MAX = 5


class Unmodellable(Exception):
    """*"This option's board change is not closed-form under the current vocabulary."* `apply_option`
    turns it into a `Refusal` — never a silently-unchanged observation, which would price 0.0 delta."""


@dataclass(frozen=True)
class Delta:
    """One engine step, as a fresh observation plus what it actually wrote."""

    #: The synthesized observation. Structurally shared with the pre-state everywhere it could be.
    obs: dict
    #: `snapshot_coverage` zone ids this step ASSIGNED — assignments only, never the closure of
    #: everything downstream (a derived zone here would be a second model of the dependency graph).
    writes: frozenset[str]
    #: Their `PlayerState` and the shared Stadium are the pre-state's own objects.
    shares_opponent: bool = True


def fork(obs: dict) -> tuple[dict, dict, list]:
    """Fresh ``obs`` / ``current`` / ``players`` containers, sharing every zone below them."""
    new_obs = dict(obs or {})
    current = dict(new_obs.get("current") or {})
    players = list(current.get("players") or [])
    current["players"] = players
    new_obs["current"] = current
    return new_obs, current, players


def fork_player(players: list, index: int) -> dict:
    """Its zone lists are still SHARED — the caller forks whichever list it writes."""
    seat = dict(players[index] or {})
    players[index] = seat
    return seat


def _without(cards, index: int) -> list:
    out = list(cards or ())
    del out[index]
    return out


def _card_ref(card: dict, seat: int) -> dict:
    """A card as it appears in a *stack* — the shape the engine writes into ``preEvolution``. A body's
    state does not survive being stacked under its evolution; only the card does."""
    ref = {"id": card.get("id"), "serial": card.get("serial")}
    if card.get("playerIndex") is not None:
        ref["playerIndex"] = card["playerIndex"]
    else:
        ref["playerIndex"] = seat
    return ref


def _body_at(seat: dict, area: int, index):
    """The body an ``(inPlayArea, inPlayIndex)`` reference names, or None. None rather than a raise:
    an unresolvable option must refuse, not forfeit the grader match on an `IndexError`."""
    if not isinstance(index, int) or index < 0:
        return None
    zone = {AREA_ACTIVE: "active", AREA_BENCH: "bench"}.get(area)
    if zone is None:
        return None
    bodies = seat.get(zone) or ()
    return bodies[index] if index < len(bodies) else None


def _replace_body(seat: dict, area: int, index: int, body: dict) -> None:
    """Splice ``body`` into a FRESH copy of its zone list on ``seat``."""
    zone = "active" if area == AREA_ACTIVE else "bench"
    bodies = list(seat.get(zone) or ())
    bodies[index] = body
    seat[zone] = bodies


def replace_body(seat: dict, area: int, index: int, body: dict) -> None:
    """Public body replacement primitive for effect resolvers sharing this seam's shape checks."""
    _replace_body(seat, area, index, body)


def switch_active_with_bench(seat: dict, bench_index: int) -> None:
    """Swap my Active with one occupied Bench slot; callers own allowance and condition writes."""
    active = list(seat.get("active") or ())
    if not active or not active[0]:
        raise Unmodellable(f"switch names bench index {bench_index!r}, which is not an occupied slot")
    promote_from_bench(seat, bench_index)


def promote_from_bench(seat: dict, bench_index: int) -> None:
    """Move one occupied Bench body Active; swap an existing Active or preserve its empty slot."""
    active = list(seat.get("active") or ())
    bench = list(seat.get("bench") or ())
    if not isinstance(bench_index, int) or not 0 <= bench_index < len(bench) or not bench[bench_index]:
        raise Unmodellable(f"promotion names bench index {bench_index!r}, which is not occupied")
    promoted = bench[bench_index]
    if active and active[0]:
        active[0], bench[bench_index] = promoted, active[0]
    else:
        active = [promoted]
        bench[bench_index] = None
    seat["active"], seat["bench"] = active, bench


def attach_energy_card(seat: dict, card: dict, *, area: int, index: int, combat) -> None:
    """Attach one already-sourced Energy card without consuming the manual attachment allowance."""
    target = _body_at(seat, area, index)
    stat = _stat(combat, (card or {}).get("id"))
    if target is None or stat is None or not stat.is_energy:
        raise Unmodellable("an effect Energy attachment needs a readable Energy card and own body")
    body = dict(target)
    body["energyCards"] = list(body.get("energyCards") or ()) + [card]
    body["energies"] = list(body_unit_codes(body)) + list(
        _provided_units(combat, card.get("id"), holder_stat=_stat(combat, target.get("id"))))
    _replace_body(seat, area, index, body)


def take_from_hand(seat: dict, index, what: str) -> dict:
    """Remove and return my hand card at ``index``, resyncing ``handCount``. Raises
    :class:`Unmodellable` rather than `IndexError`, which would forfeit the grader match."""
    hand = seat.get("hand") or ()
    if not isinstance(index, int) or not 0 <= index < len(hand):
        raise Unmodellable(f"{what} names hand index {index!r}, which this snapshot cannot resolve "
                           f"(hand of {len(hand)})")
    card = hand[index]
    seat["hand"] = _without(hand, index)
    if seat.get("handCount") is not None:
        seat["handCount"] = len(seat["hand"])
    return card


def clear_conditions(seat: dict) -> bool:
    """Clear the five Special-Condition flags; True when any was set, so the caller declares the
    ``special_conditions`` write only when it happened (`docs/rules.md` §8)."""
    hit = [f for f in CONDITION_FLAGS if seat.get(f)]
    for flag in hit:
        seat[flag] = False
    return bool(hit)


def _stat(combat, card_id):
    """This card's `CardStat`, or None — through the combat oracle's own accessor (ADR-0056)."""
    getter = getattr(combat, "_card_stat", None)
    return getter(card_id) if getter is not None and card_id is not None else None


def _provided_units(combat, card_id, *, holder_stat) -> tuple:
    """The `EnergyType` UNIT codes attaching this Energy CARD puts on ``energies``, or a REFUSAL.
    Keyed on the HOLDER — Ignition provides {C} on a Basic and {C}{C}{C} on an Evolution."""
    codes = combat.provision_codes(card_id, holder_stat)
    if codes is not None:
        return tuple(codes)
    stat = _stat(combat, card_id)
    if getattr(stat, "energyType", None) is None:
        raise Unmodellable(
            f"{card_id} {getattr(stat, 'name', '?')}: attached Energy with no `energyType` — the "
            f"unit colour is unknown, and a guessed colour funds attacks it cannot pay for")
    raise Unmodellable(
        f"{card_id} {getattr(stat, 'name', '?')}: Special Energy with no `provides:N` Function "
        f"Tag — how many units it provides is unknown, and 0 would under-report the attach")


def units_for_cards(combat, cards, *, holder_stat) -> list:
    """``holder_stat`` is the stage to read AGAINST — on an evolve, the EVOLUTION's stat."""
    out: list = []
    for card in cards or ():
        card_id = (card or {}).get("id")
        if _stat(combat, card_id) is None:
            raise Unmodellable(f"{card_id}: no `CardStat` for an attached Energy card, so its "
                               f"provision cannot be re-derived")
        out.extend(_provided_units(combat, card_id, holder_stat=holder_stat))
    return out


def card_clauses(combat, card_id) -> tuple:
    """This card's Effect Clauses off the combat oracle's own `CardEffects`, or ``()``. ⚠️ ``()`` is
    *undeclared*, never *writes nothing* — a card the compendium never heard of returns the same."""
    effects = getattr(combat, "effects", None)
    return tuple(effects.clauses(card_id) if effects is not None else ())


def _one_clause_writes(combat, card_id, clause) -> frozenset:
    """Every `snapshot_coverage` zone ONE clause writes, unioned over all four vocabulary axes. An
    undeclared value is *unknown* and refuses, so it cannot quietly union to nothing."""
    out: set = set()
    for value in snapshot_coverage.clause_values(clause):
        if value not in snapshot_coverage.CLAUSE_WRITES:
            raise Unmodellable(
                f"{card_id}: clause value {value!r} is not in `snapshot_coverage.CLAUSE_WRITES` "
                f"— the vocabulary moved underneath the seam")
        if value in snapshot_coverage.NONDETERMINISTIC_CLAUSES:
            raise Unmodellable(
                f"{card_id}: clause {value!r} consults RNG — a simulated shuffle is one sample, "
                f"not a distribution (the engine has no deal-seed)")
        if value in snapshot_coverage.REVEALING_CLAUSES:
            raise Unmodellable(
                f"{card_id}: clause {value!r} REVEALS information — it belongs to an Expectation "
                f"node over outcome classes (POC-T4/2, Issue #383), not to a point transition")
        out |= snapshot_coverage.CLAUSE_WRITES[value]
    return frozenset(out)


def _clause_writes(combat, card_id) -> frozenset:
    """Every `snapshot_coverage` zone this card's Effect Clauses write. ⚠️ **An empty union is not
    proof the card writes nothing**, so callers never treat it as a licence on its own."""
    out: set = set()
    for clause in card_clauses(combat, card_id):
        out |= _one_clause_writes(combat, card_id, clause)
    return frozenset(out)


#: Damage per damage COUNTER. The compendium prints a Stadium trigger's tax in COUNTERS and the
#: engine in DAMAGE, so one has to be converted; the two spellings cross-check (2 x 10 == 20).
_COUNTER = 10

#: `cg.api.EnergyType.DARKNESS`, spelled out because this module is DLL-free by contract. ⚠️
#: `TEAM_ROCKET` (11) is deliberately NOT here: a Team Rocket's {D} body IS taxed by Risky Ruins.
_DARKNESS = 7

#: :func:`stadium_clauses_for`'s ``event`` vocabulary, NOT the compendium's namespace. ``static`` is
#: not a transition at all — it is the FLOATING modifier read, with no board event in flight.
STADIUM_EVENTS: frozenset = frozenset({"bench_play", "stage_change", "displace", "static"})

#: NAMED so the one consumer outside this module spells it by import rather than by literal.
STADIUM_STATIC: str = "static"

#: The ``on`` values a `stadium_trigger` may name. One today (Risky Ruins), and an ``on`` outside
#: this set is UNKNOWN rather than non-matching -- see :func:`stadium_clauses_for`.
_TRIGGER_EVENTS: frozenset = frozenset({"bench_play"})


def _is_basic(stat) -> bool:
    """A Basic Pokemon, off `CardStat.stage` — the ONE derivation (Issue #408). Deliberately NOT
    ``evolvesFrom is None and not stage2``, which is exact on today's pool and drifts."""
    return getattr(stat, "stage", None) == "basic"


def _admits_stage2(stat):
    """Gravity Mountain (1252): *"Each Stage 2 Pokemon in play"*."""
    return bool(getattr(stat, "stage2", False))


def _admits_basic(stat):
    """Lively Stadium (1251): *"Each Basic Pokemon in play"*. Never answers *unknown* — ``stage``
    alone decides it, unlike :func:`_admits_basic_non_dark`."""
    return _is_basic(stat)


def _admits_basic_non_dark(stat):
    """Risky Ruins (1260): *"a Basic non-{D} Pokemon"*. None — *unknown*, which refuses — when the
    body has no ``energyType``, since guessing would tax or spare a body the engine does not."""
    if getattr(stat, "energyType", None) is None:
        return None
    return _is_basic(stat) and int(stat.energyType) != _DARKNESS


#: `applies_to` resolvers. The other three values are absent on purpose — they ride clauses whose
#: write-set is EMPTY, so they never survive the filter, and a MISSING key refuses (Issue #433).
_APPLIES_TO = {
    "stage2": _admits_stage2,
    "basic": _admits_basic,
    "basic_non_dark": _admits_basic_non_dark,
}


def _admits(clause: dict, stats: tuple):
    """Does ``clause``'s ``applies_to`` admit any of these body classes? True / False / None, where
    None is *unknown* and every caller treats it as refuse — `undeclared_clauses` cannot see drift."""
    key = clause.get("applies_to")
    if key is None:
        # No body scope named: the clause is about the board rather than about a class of body.
        return True
    resolver = _APPLIES_TO.get(key)
    if resolver is None:
        return None
    verdicts = [resolver(stat) for stat in stats if stat is not None]
    if not verdicts or None in verdicts:
        return None
    return any(verdicts)


def stadium_clauses_for(current: dict, combat, *, event: str, stat=None) -> tuple:
    """The in-play Stadium's clauses that AFFECT this event/body — ``()`` when it cannot reach it.
    ``stat`` is a tuple for ``stage_change``, where the delta may START or STOP applying (ADR-0130)."""
    if event not in STADIUM_EVENTS:
        raise Unmodellable(f"stadium_clauses_for: {event!r} is not one of {sorted(STADIUM_EVENTS)}")
    card = (current.get("stadium") or [None])[0]
    if not card:
        return ()
    return stadium_clauses_of(combat, card.get("id"), event=event, stat=stat)


def stadium_clauses_of(combat, card_id, *, event: str, stat=None) -> tuple:
    """The clauses of the Stadium **card** ``card_id`` that affect this event/body. A `stadium_static`
    has NO event filter; anything unrecognised comes back so the CALLER refuses (ADR-0130)."""
    if event not in STADIUM_EVENTS:
        raise Unmodellable(f"stadium_clauses_of: {event!r} is not one of {sorted(STADIUM_EVENTS)}")
    if card_id is None:
        return ()
    stats = tuple(stat) if isinstance(stat, (tuple, list)) else (stat,)
    out = []
    try:
        for clause in card_clauses(combat, card_id):
            if not _one_clause_writes(combat, card_id, clause):
                continue
            if event == "displace":
                out.append(clause)
                continue
            kind = clause.get("kind")
            if kind == "stadium_trigger":
                on = clause.get("on")
                if on not in _TRIGGER_EVENTS:
                    out.append(clause)              # unknown `on` -- fail closed
                    continue
                if on != event:                     # incl. every known trigger under `static`, which
                    continue                        # names no event at all
            elif kind != "stadium_static":
                out.append(clause)                  # unknown clause kind -- fail closed
                continue
            if _admits(clause, stats) is not False:
                out.append(clause)                  # True, or unknown -- fail closed
    except Unmodellable as gap:
        raise Unmodellable(f"a Stadium whose effect the seam cannot model -- {gap}")
    return tuple(out)


def _stadium_ref(current: dict, combat) -> str:
    """``"<id> <name>"`` for the in-play Stadium."""
    card_id = ((current.get("stadium") or [{}])[0] or {}).get("id")
    return f"{card_id} {getattr(_stat(combat, card_id), 'name', '?')}"


def bench_max(obs: dict, seat_index: int) -> int:
    """A seat's Bench CAP — the engine's own ``benchMax``, or this module's fallback. One reader, so
    the seam that fills the Bench and the seam that asks whether it is full cannot disagree."""
    players = ((obs or {}).get("current") or {}).get("players") or []
    me = players[seat_index] if 0 <= seat_index < len(players) and players[seat_index] else {}
    return int(me.get("benchMax") or _BENCH_MAX)


def bench_body(card_id, stat, *, seat_index: int, serial) -> dict:
    """One freshly benched body at the PRINTED maximum, nothing attached — field-for-field the
    engine's own renderer. The Stadium's arrival tax is :func:`apply_bench_arrival`'s, not this."""
    return {
        "id": card_id,
        "serial": serial,
        "playerIndex": seat_index,
        "hp": int(stat.hp),
        "maxHp": int(stat.hp),
        "appearThisTurn": True,
        "energies": [], "energyCards": [], "tools": [], "preEvolution": [],
    }


def apply_bench_arrival(body: dict, clauses, stat) -> frozenset:
    """Apply the Stadium's bench-play clauses to a just-arrived body, MUTATING it. A trigger's damage
    is STORED, so ``hp`` moves and ``maxHp`` does NOT; anything else — incl. a static — REFUSES."""
    writes: set = set()
    for clause in clauses:
        admits = _admits(clause, (stat,))
        if (clause.get("kind") == "stadium_trigger" and clause.get("on") == "bench_play"
                and clause.get("effect") == "damage_counters" and admits is True):
            damage = int(clause.get("amount") or 0) * _COUNTER
            if damage:
                body["hp"] = max(0, int(body.get("hp") or 0) - damage)
                writes.add("damage_counters")
            continue
        raise Unmodellable(
            f"a Stadium clause {clause!r} reaches a body arriving on the Bench and the seam has no "
            f"applier for it (`applies_to` admits: {admits!r}) -- a half-applied Stadium is the "
            f"three-quarters-of-a-card modelling Issue #300's `_covers` verdict exists to refuse")
    return frozenset(writes)


def stadium_hp_delta(clauses, stat) -> int:
    """The in-play Stadium's FLOATING HP modifier for a body of this class (0 when none reaches it).
    ``stat`` is RE-tested here: only the body that ends up on the board earns the delta."""
    delta = 0
    for clause in clauses:
        admits = _admits(clause, (stat,))
        if (clause.get("kind") == "stadium_static"
                and clause.get("effect") == "hp_delta" and admits is not None):
            delta += int(clause.get("amount") or 0) if admits else 0
            continue
        raise Unmodellable(
            f"a Stadium clause {clause!r} reaches a body this transition re-classes and the seam has "
            f"no applier for it (`applies_to` admits: {admits!r}) -- the transition would produce a "
            f"board the engine does not")
    return delta


def _attach(obs, option, *, seat_index, combat) -> Delta:
    """Energy or Tool from hand onto a body in play. Both arrive as `OptionType.ATTACH` and write
    different zones, hence the branch on `CardStat.cardType`. Only the Energy leg spends allowance."""
    new_obs, current, players = fork(obs)
    me = fork_player(players, seat_index)
    card = take_from_hand(me, option.get("index"), "attach")
    stat = _stat(combat, card.get("id"))
    if stat is None:
        raise Unmodellable(f"{card.get('id')}: no `CardStat` for the attached card")

    area, index = option.get("inPlayArea"), option.get("inPlayIndex")
    target = _body_at(me, area, index)
    if target is None:
        raise Unmodellable(f"attach names ({area!r}, {index!r}), which is not a body on my board")

    body = dict(target)
    writes = {"my_hand_ids"}
    if stat.is_tool:
        body["tools"] = list(body.get("tools") or ()) + [card]
        writes.add("attached_tools")
        # A Tool's flat HP grant lands on BOTH current and maximum, gated through
        # `applies_to_holder` — the ONE place every holder condition is evaluated.
        bonus = int(getattr(stat, "hpBonus", 0) or 0)
        if bonus and stat.applies_to_holder(_stat(combat, target.get("id"))):
            body["hp"] = int(body.get("hp") or 0) + bonus
            body["maxHp"] = int(body.get("maxHp") or 0) + bonus
            writes.add("damage_counters")
    elif stat.is_energy:
        units = _provided_units(combat, card.get("id"),
                                holder_stat=_stat(combat, target.get("id")))
        body["energyCards"] = list(body.get("energyCards") or ()) + [card]
        body["energies"] = list(body_unit_codes(body)) + list(units)
        # Unconditional because :func:`transition` already refuses anything off the MAIN menu.
        current["energyAttached"] = True
        writes.update({"attached_energy", "allowance_energy_attached"})
    else:
        raise Unmodellable(
            f"{card.get('id')} {stat.name}: an ATTACH of a card that is neither Energy nor a Tool — "
            f"the seam has no structural transition for it")
    _replace_body(me, area, index, body)
    return Delta(obs=new_obs, writes=frozenset(writes))


def evolve_body(current: dict, seat: dict, card: dict, *, area: int, index: int, seat_index: int,
                combat) -> frozenset[str]:
    """Replace an own body with an already-sourced Evolution card, returning exact writes."""
    stat = _stat(combat, card.get("id"))
    if stat is None or not stat.hp:
        raise Unmodellable(f"{card.get('id')}: no `CardStat` HP for the Evolution card, so the "
                           f"evolved body's maximum is unknown")

    target = _body_at(seat, area, index)
    if target is None:
        raise Unmodellable(f"evolve names ({area!r}, {index!r}), which is not a body on my board")

    tools = list(target.get("tools") or ())
    energy_cards = list(target.get("energyCards") or ())
    target_stat = _stat(combat, target.get("id"))

    # BOTH stats: the static delta may START or STOP applying, so the seam must engage either way.
    stadium_clauses = stadium_clauses_for(current, combat, event="stage_change",
                                          stat=(target_stat, stat))

    # Carried cards carry their EFFECTS too: a Tool's grant and a Special Energy's provision re-read
    # the NEW stage, and the Stadium delta floats on top of both — never folded into the stored sum.
    stadium_delta = stadium_hp_delta(stadium_clauses, stat)
    max_hp = int(stat.hp) + sum(
        int(getattr(t_stat, "hpBonus", 0) or 0)
        for t_stat in (_stat(combat, (t or {}).get("id")) for t in tools)
        if t_stat is not None and t_stat.applies_to_holder(stat)) + stadium_delta
    units_before = tuple(units_for_cards(combat, energy_cards, holder_stat=target_stat))
    if units_before != tuple(body_unit_codes(target)):
        # A SELF-CHECK: a provision model already wrong about the body as it stands cannot be
        # trusted to re-derive it post-evolution.
        raise Unmodellable(
            f"the attached-Energy provision model disagrees with this board before the evolution "
            f"even happens (seam {units_before}, engine {tuple(body_unit_codes(target))}), so the "
            f"re-derived post-evolution units cannot be trusted")
    # Invariant to a floating Stadium modifier: rendered `hp` and `maxHp` both carry it, so it
    # cancels in the subtraction.
    taken = max(0, int(target.get("maxHp") or 0) - int(target.get("hp") or 0))
    body = {
        "id": card.get("id"),
        "serial": card.get("serial"),
        "playerIndex": card.get("playerIndex", seat_index),
        "hp": max(0, max_hp - taken),
        "maxHp": max_hp,
        "appearThisTurn": True,
        "energies": units_for_cards(combat, energy_cards, holder_stat=stat),
        "energyCards": energy_cards,
        "tools": tools,
        "preEvolution": list(target.get("preEvolution") or ()) + [_card_ref(target, seat_index)],
    }
    _replace_body(seat, area, index, body)
    # `new_in_play` unconditionally: §4 forbids evolving a body the turn it was played, so the bit
    # necessarily flips.
    writes = {"my_hand_ids", "bodies_in_play", "new_in_play"}
    if stadium_delta:
        # `damage_counters` homes the HP read. NON-ZERO only: a clause priced at 0 assigned nothing.
        writes.add("damage_counters")
    if area == AREA_ACTIVE and clear_conditions(seat):
        writes.add("special_conditions")
    return frozenset(writes)


def _evolve(obs, option, *, seat_index, combat) -> Delta:
    """The Evolution card from hand REPLACES the body in play, keeping attached cards and damage and
    clearing conditions (`docs/rules.md` §4). Damage carries as a DELTA — the maximum changed."""
    new_obs, current, players = fork(obs)
    me = fork_player(players, seat_index)
    card = take_from_hand(me, option.get("index"), "evolve")
    writes = evolve_body(current, me, card, area=option.get("inPlayArea"),
                          index=option.get("inPlayIndex"), seat_index=seat_index, combat=combat)
    return Delta(obs=new_obs, writes=writes)


def _retreat(obs, option, *, seat_index, combat) -> Delta:
    """The whole step. The option is bare ``{"type": 12}`` in 5807 of 5807 parity and 146 of 146
    corrections occurrences — cost and promotion are separate selects, so beam admission is Issue #385's."""
    new_obs, current, _players = fork(obs)
    current["retreated"] = True
    return Delta(obs=new_obs, writes=frozenset({"allowance_retreat_used"}))


def _play(obs, option, *, seat_index, combat) -> Delta:
    """Play a card from hand — the structural half. A Basic deploy and a Stadium settle in one engine
    step; everything else refuses, because the EFFECT is the play. This module applies NO clauses."""
    new_obs, current, players = fork(obs)
    me = fork_player(players, seat_index)
    card = take_from_hand(me, option.get("index"), "play")
    card_id = card.get("id")
    stat = _stat(combat, card_id)
    if stat is None:
        raise Unmodellable(f"{card_id}: no `CardStat` for the played card")

    extra = _clause_writes(combat, card_id)
    if extra:
        raise Unmodellable(
            f"{card_id} {stat.name}: its Effect Clauses write {sorted(extra)} — the structural floor "
            f"is not the whole play, and modelling three quarters of a card is what Issue #300's "
            f"`_covers` verdict exists to prevent")

    if stat.is_pokemon:
        if getattr(stat, "evolvesFrom", None) is not None:
            raise Unmodellable(f"{card_id} {stat.name}: an Evolution has no `_PLAY` route — it "
                               f"reaches the board by evolving")
        if not stat.hp:
            raise Unmodellable(f"{card_id} {stat.name}: no `CardStat` HP, so the deployed body's "
                               f"maximum is unknown")
        # Asked BEFORE the Bench cap, so an unreadable Stadium refuses on the vocabulary rather than
        # on whichever check happens to run first.
        stadium_clauses = stadium_clauses_for(current, combat, event="bench_play", stat=stat)
        bench = list(me.get("bench") or ())
        if len(bench) >= int(me.get("benchMax") or _BENCH_MAX):
            raise Unmodellable(f"{card_id} {stat.name}: the Bench is full, so this deploy is not a "
                               f"legal play on this board")
        body = bench_body(card_id, stat, seat_index=card.get("playerIndex", seat_index),
                          serial=card.get("serial"))
        writes = {"my_hand_ids", "bodies_in_play", "bench_occupancy", "new_in_play"}
        writes |= apply_bench_arrival(body, stadium_clauses, stat)
        bench.append(body)
        me["bench"] = bench
        return Delta(obs=new_obs, writes=frozenset(writes))

    if stat.is_stadium:
        old = (current.get("stadium") or [None])[0]
        if old and old.get("id") == card_id:
            raise Unmodellable(f"{card_id} {stat.name}: a Stadium of the same name is already in "
                               f"play, so this is not a legal play (`docs/rulebook.txt` L137)")
        # DISPLACEMENT ends the old Stadium's effect on every body on BOTH sides, so there is no
        # per-body question to narrow to — this site deliberately keeps REFUSING (ADR-0130).
        displaced = stadium_clauses_for(current, combat, event="displace")
        if displaced:
            raise Unmodellable(
                f"{_stadium_ref(current, combat)} is in play and DISPLACING it ends its effect on "
                f"every body it was modifying, on both sides — {len(displaced)} writing clause(s) "
                f"the transition would have to un-apply board-wide (measured: Gravity Mountain's "
                f"-30 coming BACK, `ml_dx_2001` f172 290/290 vs f181 320/320)")
        writes = {"my_hand_ids", "stadium", "allowance_stadium_played"}
        if old is not None:
            owner = old.get("playerIndex")
            owner = seat_index if owner is None else int(owner)
            side = fork_player(players, owner)
            side["discard"] = list(side.get("discard") or ()) + [old]
            writes.add("my_discard_contents" if owner == seat_index
                       else "their_discard_contents")
        played = dict(card)
        played["playerIndex"] = card.get("playerIndex", seat_index)
        current["stadium"] = [played]
        current["stadiumPlayed"] = True
        # `shares_opponent=False` UNCONDITIONALLY: the Stadium is a SHARED zone their side's
        # derivations read, so a reused `TheirSide` would carry a stale one.
        return Delta(obs=new_obs, writes=frozenset(writes), shares_opponent=False)

    raise Unmodellable(
        f"{card_id} {stat.name}: a Trainer play is its EFFECT, and the effect is what a differencing "
        f"composer is asking about — the structural floor alone would be a delta the engine does not "
        f"produce (the card does not even reach the discard on the same step when the effect opens a "
        f"select). Expectation / choice nodes are POC-T4/2 (Issue #383)")


#: Keyed by the engine `OptionType` this seam declares MODELLED; `test_apply_transitions` asserts
#: this agrees with `apply_option.TRANSITION_KINDS`.
TRANSITIONS = {
    _ATTACH: _attach,
    _EVOLVE: _evolve,
    _RETREAT: _retreat,
    _PLAY: _play,
}


def transition(obs: dict, option: dict, *, seat_index: int, combat, context=None) -> Delta:
    """The observation after ``option``, or :class:`Unmodellable`. **MAIN-menu options only**: an
    option posed inside a card's effect carries writes belonging to the CARD, not to its own kind."""
    if context != CONTEXT_MAIN:
        raise Unmodellable(
            f"select context {context!r} is not the MAIN menu — this option is one leg of a card's "
            f"effect resolving, and that card's other writes ride the same engine step (measured: "
            f"Rare Candy's `_EVOLVE` at context 37 also discards the Rare Candy)")
    kind = int((option or {}).get("type", -1))
    fn = TRANSITIONS.get(kind)
    if fn is None:
        raise Unmodellable(f"option kind {kind} has no closed-form transition in this module")
    return fn(obs or {}, option or {}, seat_index=int(seat_index), combat=combat)


__all__ = ("CONTEXT_MAIN", "CONDITION_FLAGS", "Unmodellable", "Delta", "TRANSITIONS", "transition",
           "fork", "fork_player", "take_from_hand", "card_clauses",
           "clear_conditions", "units_for_cards", "replace_body", "switch_active_with_bench",
           "promote_from_bench", "attach_energy_card",
           "evolve_body")
