"""The strategy activation engine and doctrine catalog for the Bellman search beam."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, replace
import hashlib
import json

from common.cards.functions.damage import compute_active_damage
from common.cards.functions.energy import payment_fraction, unmet_cost_slots
from common.strategy.strategies import (
    _BENCH_CARD, ActivationCondition, DesiredFact, StrategyHint, StrategyOverride,
)

from .state import _visible_own_ids

@dataclass(frozen=True)
class ResolvedStrategies:
    general: tuple[StrategyHint, ...]
    deck: tuple[StrategyHint, ...]
    opponent: tuple[StrategyHint, ...]
    overrides: tuple[StrategyOverride, ...]
    effective: tuple[StrategyHint, ...]
    content_hash: str

    def as_dict(self) -> dict:
        return {
            "general": [row.as_dict() for row in self.general],
            "deck": [row.as_dict() for row in self.deck],
            "opponent": [row.as_dict() for row in self.opponent],
            "overrides": [row.as_dict() for row in self.overrides],
            "effective": [row.as_dict() for row in self.effective],
            "content_hash": self.content_hash,
        }


@dataclass(frozen=True)
class ActivatedStrategy:
    strategy_id: str
    kind: str
    recipient: str
    recipient_card_id: int | None
    recipient_serial: int | None
    target_card_ids: tuple[int, ...]
    deadline: str
    conviction: str
    bundle_id: str | None = None
    waypoint: int = 0
    amount: int = 1


@dataclass(frozen=True)
class StrategySnapshot:
    turn: int
    seat: int
    strategy_hash: str
    snapshot_id: str
    active_ids: tuple[str, ...]
    inactive_ids: tuple[str, ...]
    hints: tuple[ActivatedStrategy, ...]


def _player(observation: dict, seat: int) -> dict:
    players = ((observation.get("current") or {}).get("players") or ())
    return players[seat] if 0 <= seat < len(players) and players[seat] else {}


def _active_body(player: dict) -> dict:
    active = player.get("active") or ()
    return active[0] if active and active[0] else {}


def _attack_ready(body: dict, cards) -> bool:
    if not body or body.get("id") is None:
        return False
    from common.cards.functions.energy import unmet_cost_slots

    card = cards.get(int(body["id"]))
    attacks = getattr(card, "attacks", ()) or ()
    if not attacks:
        return False
    provisions = body.get("energies") or ()
    maximum = max(len(attack.cost) for attack in attacks)
    return any(len(attack.cost) == maximum and not unmet_cost_slots(provisions, attack.cost)
               for attack in attacks)


def _knocks_out(attacker_body: dict, defender_body: dict, cards) -> bool:
    """Whether a cost the attacker can already pay reaches the defender's remaining HP.

    Card facts only: printed damage against printed HP. Whether taking the knockout is the
    right play is Bellman's to weigh -- this only makes sure the option is searched.
    """
    if not attacker_body or not defender_body:
        return False
    attacker = cards.get(int(attacker_body["id"])) \
        if attacker_body.get("id") is not None else None
    defender = cards.get(int(defender_body["id"])) \
        if defender_body.get("id") is not None else None
    remaining = int(defender_body.get("hp", 0) or 0)
    if attacker is None or defender is None or remaining <= 0:
        return False
    provisions = tuple(attacker_body.get("energies") or ())
    for attack in getattr(attacker, "attacks", ()) or ():
        if unmet_cost_slots(provisions, attack.cost):
            continue
        if compute_active_damage(attack, attacker, defender) >= remaining:
            return True
    return False


def _zone_card_ids(zone) -> tuple[int, ...]:
    return tuple(int(card["id"]) for card in zone or () if card and card.get("id") is not None)


def _side_bodies(player: dict) -> tuple[dict, ...]:
    return tuple(body for body in (
        tuple(player.get("active") or ()) + tuple(player.get("bench") or ())) if body)


def _hand_count(player: dict) -> int:
    hand = player.get("hand")
    if isinstance(hand, (list, tuple)):
        return len(hand)
    return int(player.get("handCount", 0) or 0)


def _special_energy_ids(bodies, stats) -> tuple[int, ...]:
    """Attached Energy cards beyond Basic — the hint names the id; the engine prices the text."""
    if stats is None:
        return ()
    ids = []
    for body in bodies:
        for card in body.get("energyCards") or ():
            if not card or card.get("id") is None:
                continue
            stat = stats.get(int(card["id"]))
            name = str(getattr(stat, "name", "") or "")
            if stat is not None and getattr(stat, "is_energy", False) \
                    and not name.startswith("Basic"):
                ids.append(int(card["id"]))
    return tuple(sorted(set(ids)))


def _tool_ids(bodies) -> tuple[int, ...]:
    return tuple(sorted(set(
        int(card["id"]) for body in bodies for card in body.get("tools") or ()
        if card and card.get("id") is not None)))


def _visible_facts(observation: dict, *, roles, stats=None, effects=None,
                   opponent_role_worth=None, deck=None, cards=None) -> dict:
    from common.cards import card_store

    cards = card_store() if cards is None else cards
    current = observation.get("current") or {}
    seat = int(current.get("yourIndex", 0))
    player = _player(observation, seat)
    active = _active_body(player)
    card_id = int(active["id"]) if active.get("id") is not None else None
    card_roles = tuple(roles.get(card_id, ())) if card_id is not None else ()
    bench = tuple(body for body in player.get("bench") or () if body)
    opponent = _player(observation, 1 - seat)
    opponent_bench = tuple(body for body in opponent.get("bench") or () if body)
    opponent_role_worth = opponent_role_worth or {}
    options = tuple((observation.get("select") or {}).get("option") or ())
    can_attack = any(int(option.get("type", -1)) == 13 for option in options)
    commitment_available = (not bool(current.get("energyAttached"))
                            or (card_id in roles.evolves if card_id is not None else False))
    facts = {
        "own.active.card_id": card_id,
        "own.active.role": card_roles,
        "own.active.is_attacker": bool(
            {"primary_attacker", "backup_attacker"}.intersection(card_roles)),
        "own.active.energy_count": len(active.get("energies") or ()),
        "own.active.hp_fraction": (
            int(active.get("hp", 0)) / max(1, int(active.get("maxHp", active.get("hp", 1))))
            if active else 0.0),
        "own.active.attack_ready": _attack_ready(active, cards),
        "own.active.can_attack": can_attack,
        "own.active.evolvable": card_id in roles.evolves if card_id is not None else False,
        "own.bench.evolvable_count": sum(
            1 for body in bench if body.get("id") in roles.evolves),
        "own.bench.card_ids": tuple(int(body.get("id", 0)) for body in bench),
        "own.bench.space": max(0, int(player.get("benchMax", 5)) - len(bench)),
        "opponent.bench.card_ids": tuple(
            int(body.get("id", 0)) for body in opponent_bench),
        "opponent.bench.role_target_count": sum(
            float(opponent_role_worth.get(int(body.get("id", 0)), 0.0)) > 0.0
            for body in opponent_bench),
        "opponent.bench.highest_role.hp": int(_recipient_body(
            observation, seat, "opponent.bench.highest_role", roles,
            opponent_role_worth).get("hp", 0)),
        "own.active.knocks_out_defender": _knocks_out(
            active, _active_body(opponent), cards),
        "turn.commitment_available": commitment_available,
        # The condition language has no OR; a boost pays off while a commitment can still create
        # an attack OR one is already offered (PR #533 review: the post-attach committed case).
        "turn.boostable_attack_available": commitment_available or can_attack,
    }
    ability_ids = []
    for option in options:
        if int(option.get("type", -1)) != 10:
            continue
        area, index = option.get("inPlayArea", option.get("area")), option.get(
            "inPlayIndex", option.get("index"))
        bodies = ((player.get("active") or ()) if area == 4 else
                  (player.get("bench") or ()) if area == 5 else ())
        if isinstance(index, int) and 0 <= index < len(bodies) and bodies[index]:
            ability_ids.append(int(bodies[index].get("id", 0)))
    facts["turn.ability.card_ids"] = tuple(ability_ids)
    facts["own.damaged_count"] = 0
    for body in (active, *bench):
        if not body:
            continue
        body_id = int(body.get("id", 0))
        prefix = f"own.card.{body_id}"
        facts[prefix + ".in_play"] = True
        facts[prefix + ".energy_count"] = max(
            int(facts.get(prefix + ".energy_count", 0)), len(body.get("energies") or ()))
        # The MOST threatened copy, not whichever the loop reached last. A deck running four
        # Drakloak asks "is a Drakloak in danger", and a last-wins reading answers about an
        # arbitrary one.
        facts[prefix + ".hp_fraction"] = min(
            float(facts.get(prefix + ".hp_fraction", 1.0)),
            int(body.get("hp", 0)) / max(1, int(body.get("maxHp", body.get("hp", 1)))))
        if int(body.get("hp", 0)) < int(body.get("maxHp", body.get("hp", 0))):
            facts["own.damaged_count"] += 1
        stat = stats.get(body_id) if stats is not None else None
        required = tuple(getattr(stat, "abilityEnergyTypes", ()) or ())
        if required:
            facts[prefix + ".ability_ready"] = payment_fraction(
                tuple(int(code) for code in body.get("energies") or ()), required) >= 1.0
    facts["opponent.bench.softened_multi_prize_count"] = sum(
        int(body.get("hp", 0)) <= 200
        and int(getattr(stats.get(int(body.get("id", 0))), "prize_value", 1)) > 1
        for body in opponent_bench
    ) if stats is not None else 0
    # --- The public census: counts and contents on both sides, so a condition can read the
    # --- same board Bellman prices. Opponent per-card facts mirror the own.card family.
    opponent_active = _active_body(opponent)
    opponent_active_id = (int(opponent_active["id"])
                          if opponent_active.get("id") is not None else None)
    own_bodies = _side_bodies(player)
    opponent_bodies = _side_bodies(opponent)
    facts.update({
        "own.deck.count": int(player.get("deckCount", 0) or 0),
        "opponent.deck.count": int(opponent.get("deckCount", 0) or 0),
        "own.hand.count": _hand_count(player),
        "opponent.hand.count": _hand_count(opponent),
        "own.prizes.remaining": len(player.get("prize") or ()),
        "opponent.prizes.remaining": len(opponent.get("prize") or ()),
        "own.discard.card_ids": _zone_card_ids(player.get("discard")),
        "opponent.discard.card_ids": _zone_card_ids(opponent.get("discard")),
        "own.discard.basic_energy_count": (sum(
            1 for card_id in _zone_card_ids(player.get("discard"))
            if getattr(stats.get(card_id), "is_energy", False)
            and str(getattr(stats.get(card_id), "name", "") or "").startswith("Basic")
        ) if stats is not None else 0),
        # Behind on prizes, as the cards gate it: MORE prize cards remaining than the opponent.
        "own.prizes.more_remaining_than_opponent": (
            len(player.get("prize") or ()) > len(opponent.get("prize") or ())),
        "opponent.active.card_id": opponent_active_id,
        "opponent.active.energy_count": len(opponent_active.get("energies") or ()),
        "opponent.active.hp": int(opponent_active.get("hp", 0) or 0),
        "opponent.active.is_role_target": (
            float(opponent_role_worth.get(opponent_active_id, 0.0)) > 0.0
            if opponent_active_id is not None else False),
        "own.energy_in_play": sum(len(body.get("energies") or ()) for body in own_bodies),
        "opponent.energy_in_play": sum(
            len(body.get("energies") or ()) for body in opponent_bodies),
        "own.active.energy_card_ids": _zone_card_ids(active.get("energyCards")),
        "opponent.active.energy_card_ids": _zone_card_ids(
            opponent_active.get("energyCards")),
        "own.active.tool_card_ids": _zone_card_ids(active.get("tools")),
        "opponent.active.tool_card_ids": _zone_card_ids(opponent_active.get("tools")),
        "own.tools.in_play": _tool_ids(own_bodies),
        "opponent.tools.in_play": _tool_ids(opponent_bodies),
        "own.special_energy_in_play": _special_energy_ids(own_bodies, stats),
        "opponent.special_energy_in_play": _special_energy_ids(opponent_bodies, stats),
    })
    for body in opponent_bodies:
        prefix = f"opponent.card.{int(body.get('id', 0))}"
        facts[prefix + ".in_play"] = True
        facts[prefix + ".energy_count"] = max(
            int(facts.get(prefix + ".energy_count", 0)), len(body.get("energies") or ()))
    # Our own hidden zones, exact once own_prizes records the first search's split. Absent
    # without a decklist, so a condition distinguishes "empty" from "unknown" via `missing`.
    if deck:
        remaining = Counter(int(value) for value in deck)
        remaining.subtract(_visible_own_ids(observation, seat))
        prizes = Counter({int(card_id): int(count) for card_id, count in
                          (observation.get("own_prizes") or {}).items()})
        remaining.subtract(prizes)
        facts["own.deck.card_ids"] = tuple(sorted(
            card_id for card_id, count in remaining.items() if count > 0))
        facts["own.prizes.card_ids"] = tuple(sorted(
            card_id for card_id, count in prizes.items() if count > 0))
    ko_window = bool(observation.get("strategyPokemonKoWindow"))
    if not ko_window:
        try:
            token = observation.get("search_begin_input")
            payload = token.split(":", 1)[1] if isinstance(token, str) and ":" in token else ""
            internals = json.loads(payload) if payload else None
        except (ValueError, TypeError):
            internals = None
        if internals is not None:
            ko_turn = tuple(internals.get("ko_turn") or ())
            ko_window = (seat < len(ko_turn)
                         and int(ko_turn[seat]) == int(current.get("turn", 0)) - 1)
    ko_window = ko_window or any(
        body and int(body.get("hp", 1)) <= 0
        for body in player.get("active") or ())
    if effects is not None and stats is not None:
        hand = tuple(player.get("hand") or ())
        for option in options:
            if int(option.get("type", -1)) != 7:
                continue
            index = option.get("index")
            card = hand[index] if isinstance(index, int) and 0 <= index < len(hand) else None
            card_id = int(card.get("id", 0)) if card else 0
            stat = stats.get(card_id)
            if bool(getattr(stat, "is_pokemon", False)):
                continue
            if any(clause.get("condition") == "pokemon_ko_last_turn"
                   for clause in effects.clauses(card_id)):
                ko_window = True
                break
    facts["turn.pokemon_ko_window"] = ko_window
    return facts


def _recipient_body(observation: dict, seat: int, selector: str, roles,
                    opponent_role_worth=None) -> dict:
    player = _player(observation, seat)
    if selector == "own.active":
        return _active_body(player)
    if selector == "own.bench.evolvable:first":
        return next((body for body in player.get("bench") or ()
                     if body and body.get("id") in roles.evolves), {})
    if selector.startswith(_BENCH_CARD):
        # `evolvable:first` binds whichever Basic sits earliest, which is the wrong body as soon
        # as a deck Benches two evolving Basics. This names the one the declaration meant.
        card_id = int(selector[len(_BENCH_CARD):])
        return next((body for body in player.get("bench") or ()
                     if body and int(body.get("id", -1)) == card_id), {})
    if (selector.startswith("own.body.card:")
            and selector.split(":")[-1] in {"first", "readiest", "weakest"}):
        try:
            card_id = int(selector.split(":")[1])
        except (IndexError, ValueError):
            return {}
        copies = tuple(body for body in (
            tuple(player.get("active") or ()) + tuple(player.get("bench") or ()))
            if body and int(body.get("id", 0)) == card_id)
        def readiness(body):
            return (
                len(body.get("energies") or ()),
                int(body.get("hp", 0)) / max(1, int(body.get("maxHp", body.get("hp", 1)))),
            )

        if selector.endswith(":readiest"):
            # The copy in the best shape to attack: most Energy, then least hurt. A deck running
            # four of a card must be able to name the one worth promoting, not the first listed.
            return max(copies, key=lambda body: (*readiness(body), -int(body.get("serial", 0))),
                       default={})
        if selector.endswith(":weakest"):
            # The mirror, and NOT interchangeable with it: a need to protect a body is about the
            # copy in the worst shape, and pointing it at the readiest one saves the wrong body
            # while the threatened one still dies.
            return min(copies, key=lambda body: (*readiness(body), int(body.get("serial", 0))),
                       default={})
        return copies[0] if copies else {}
    if selector == "opponent.bench.highest_role":
        opponent = _player(observation, 1 - seat)
        worth = opponent_role_worth or {}
        return max(
            (body for body in opponent.get("bench") or () if body),
            key=lambda body: (
                float(worth.get(int(body.get("id", 0)), 0.0)),
                -int(body.get("hp", 0)),
                -int(body.get("serial", body.get("id", 0))),
            ),
            default={},
        )
    return {}


def _condition_matches(condition: ActivationCondition, facts: dict) -> bool:
    present = condition.fact in facts
    actual = facts.get(condition.fact)
    expected = condition.value
    operations = {
        "eq": lambda: actual == expected,
        "ne": lambda: actual != expected,
        "lt": lambda: present and actual < expected,
        "le": lambda: present and actual <= expected,
        "gt": lambda: present and actual > expected,
        "ge": lambda: present and actual >= expected,
        "contains": lambda: present and expected in actual,
        "not_contains": lambda: present and expected not in actual,
        "missing": lambda: not present,
    }
    try:
        return bool(operations[condition.operator]())
    except (TypeError, ValueError):
        return False


def activate_strategies(observation: dict, resolved: ResolvedStrategies, *, roles,
                        stats=None, effects=None, opponent_role_worth=None,
                        deck=None, cards=None) -> StrategySnapshot:
    current = observation.get("current") or {}
    turn = int(current.get("turn", 0))
    seat = int(current.get("yourIndex", 0))
    facts = _visible_facts(
        observation, roles=roles, stats=stats, effects=effects,
        opponent_role_worth=opponent_role_worth, deck=deck, cards=cards)
    active_rows = tuple(
        row for row in resolved.effective
        if all(_condition_matches(condition, facts) for condition in row.conditions)
    )
    active_ids = tuple(row.identifier for row in active_rows)
    inactive_ids = tuple(
        row.identifier for row in resolved.effective if row.identifier not in active_ids)
    hints = []
    for row in active_rows:
        for desired in row.desired_facts:
            recipient_body = _recipient_body(
                observation, seat, desired.recipient, roles, opponent_role_worth)
            recipient_card_id = (int(recipient_body["id"])
                                 if recipient_body.get("id") is not None else None)
            recipient_serial = (int(recipient_body["serial"])
                                if recipient_body.get("serial") is not None else None)
            targets = desired.target_card_ids
            if (not targets and desired.kind == "evolve"
                    and recipient_card_id in roles.evolves):
                targets = (int(roles.evolves[recipient_card_id]),)
            hints.append(ActivatedStrategy(
                row.identifier, desired.kind, desired.recipient,
                recipient_card_id, recipient_serial,
                targets, row.deadline, row.conviction, row.bundle_id, row.waypoint,
                int(desired.amount),
            ))
    payload = {
        "turn": turn,
        "seat": seat,
        "strategy_hash": resolved.content_hash,
        "active_ids": active_ids,
        "inactive_ids": inactive_ids,
        "hints": [asdict(row) for row in hints],
    }
    snapshot_id = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return StrategySnapshot(
        turn, seat, resolved.content_hash, snapshot_id,
        active_ids, inactive_ids, tuple(hints),
    )


def resolve_strategies(general, deck=(), opponent=(), overrides=()) -> ResolvedStrategies:
    general = tuple(general)
    deck = tuple(deck)
    opponent = tuple(opponent)
    overrides = tuple(overrides)
    declared = (*general, *deck, *opponent)
    by_id = {row.identifier: row for row in declared}
    if len(by_id) != len(declared):
        raise ValueError("duplicate strategy identifier")
    unknown = {row.strategy_id for row in overrides} - set(by_id)
    if unknown:
        raise ValueError(f"unknown strategy override: {sorted(unknown)}")
    override_by_id = {row.strategy_id: row for row in overrides}
    if len(override_by_id) != len(overrides):
        raise ValueError("duplicate strategy override")
    effective = []
    for row in declared:
        override = override_by_id.get(row.identifier)
        if override is not None:
            row = replace(
                row,
                enabled=row.enabled if override.enabled is None else override.enabled,
                conditions=(*row.conditions, *override.additional_conditions),
            )
        if row.enabled:
            effective.append(row)
    effective = tuple(sorted(effective, key=lambda row: row.identifier))
    payload = {
        "general": [row.as_dict() for row in general],
        "deck": [row.as_dict() for row in deck],
        "opponent": [row.as_dict() for row in opponent],
        "overrides": [row.as_dict() for row in overrides],
        "effective": [row.as_dict() for row in effective],
    }
    content_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ResolvedStrategies(general, deck, opponent, overrides, effective, content_hash)


GENERAL_STRATEGIES = (
    StrategyHint(
        "general.fund_active_attacker",
        "general",
        (
            ActivationCondition("own.active.is_attacker", "eq", True),
            # Below half health the body is a heal-or-replace question; above it funding
            # stays live — exact viability of the recipient is Bellman's call.
            ActivationCondition("own.active.hp_fraction", "ge", 0.5),
            ActivationCondition("own.active.attack_ready", "eq", False),
        ),
        (DesiredFact("fund_attack", "own.active"),),
        "own.active",
        "this_turn",
        "high",
        "shared-general",
    ),
    StrategyHint(
        "general.evolve_active_attacker",
        "general",
        (
            ActivationCondition("own.active.evolvable", "eq", True),
        ),
        (DesiredFact("evolve", "own.active"),),
        "own.active",
        "this_turn",
        "high",
        "shared-general",
    ),
    StrategyHint(
        "general.heal_damaged_active_attacker",
        "general",
        (
            ActivationCondition("own.active.role", "contains", "primary_attacker"),
            ActivationCondition("own.active.hp_fraction", "lt", 0.70),
        ),
        (DesiredFact("heal", "own.active"),),
        "own.active",
        "immediate",
        "high",
        "shared-general",
    ),
    StrategyHint(
        "general.low_cost_information_access_before_commitment",
        "general",
        (ActivationCondition("turn.commitment_available", "eq", True),),
        (DesiredFact("low_cost_information_access", "turn"),),
        "turn",
        "immediate",
        "high",
        "shared-general",
    ),
    StrategyHint(
        # Surfacing the knockout, not choosing it: an attack that takes a prize must at least be
        # searched. Whether it beats developing instead is Bellman's comparison to make.
        #
        # this_turn and medium, NOT immediate/high: the knockout is still there after the bench
        # is filled and the Energy is down, so it is not lost by developing first, and taking it
        # is usually -- not always -- better than developing. Authored at immediate/high it
        # displaced the Poffin-two-Staryu setup that the Mega Starmie correction rules first.
        "general.take_the_knockout_in_front_of_you",
        "general",
        (ActivationCondition("own.active.knocks_out_defender", "eq", True),),
        (DesiredFact("knock_out", "own.active"),),
        "own.active",
        "this_turn",
        "medium",
        "shared-general",
    ),
    StrategyHint(
        # The Read's role worth marks which Benched opponent body the matchup turns on. Only
        # attacks that actually reach the Bench are credited, so a deck with no bench reach
        # carries this hint inert.
        "general.press_the_scouted_role_target",
        "general",
        (ActivationCondition("opponent.bench.role_target_count", "gt", 0),),
        (DesiredFact("damage_setup", "opponent.bench.highest_role"),),
        "opponent.bench.highest_role",
        "this_turn",
        "medium",
        "shared-general",
    ),
    StrategyHint(
        # A this-turn damage boost pays off only if the boosted attack is still ahead of it in
        # the same epoch; schedule it early so search reaches that attack before the caps.
        "general.boost_the_committed_attack",
        "general",
        (ActivationCondition("turn.boostable_attack_available", "eq", True),),
        (DesiredFact("damage_boost", "turn"),),
        "turn",
        "this_turn",
        "medium",
        "shared-general",
    ),
)


def general_card_strategies(deck, roles, functions, stats,
                            effects=None) -> tuple[StrategyHint, ...]:
    hints = []
    for card_id in sorted(set(int(value) for value in deck)):
        card_roles = frozenset(roles.get(card_id, ()))
        tags = frozenset(functions.tags(card_id)) if functions is not None else frozenset()
        recipient = f"own.body.card:{card_id}:first"
        stat = stats.get(card_id) if stats is not None else None
        clauses = tuple(effects.clauses(card_id)) if effects is not None else ()
        is_trainer = (stat is not None and not getattr(stat, "is_pokemon", False)
                      and not getattr(stat, "is_energy", False))
        if is_trainer:
            # A gust converts only while the scouted Bench holds a body worth dragging out.
            if any(clause.get("kind") == "gust" for clause in clauses):
                hints.append(StrategyHint(
                    f"general.card.{card_id}.gust_the_role_target", "general",
                    (ActivationCondition("opponent.bench.role_target_count", "gt", 0),),
                    (DesiredFact("play_card", "opponent.bench.highest_role",
                                 target_card_ids=(card_id,)),),
                    "opponent.bench.highest_role", "this_turn", "medium",
                    "shared-card-role"))
            # A card usable only in the turn after a loss (Unfair Stamp) is taken now or lost.
            if any(clause.get("condition") == "pokemon_ko_last_turn" for clause in clauses):
                hints.append(StrategyHint(
                    f"general.card.{card_id}.play_in_the_ko_window", "general",
                    (ActivationCondition("turn.pokemon_ko_window", "eq", True),),
                    (DesiredFact("play_card", "own.active", target_card_ids=(card_id,)),),
                    "own.active", "immediate", "medium", "shared-card-role"))
            # An acceleration trainer fires under the conditions its own clause declares:
            # Rosa's Encouragement wants the prize deficit AND Basic Energy in the discard.
            # WHICH body receives the Energy stays Bellman's pick.
            accel = next((clause for clause in clauses
                          if clause.get("kind") == "accel"), None)
            if accel is not None:
                conditions = []
                if accel.get("source") == "discard":
                    conditions.append(ActivationCondition(
                        "own.discard.basic_energy_count", "gt", 0))
                if accel.get("condition") == "more_prizes_remaining_than_opp":
                    conditions.append(ActivationCondition(
                        "own.prizes.more_remaining_than_opponent", "eq", True))
                hints.append(StrategyHint(
                    f"general.card.{card_id}.accelerate_energy", "general",
                    tuple(conditions),
                    (DesiredFact("play_card", "own.active", target_card_ids=(card_id,)),),
                    "own.active", "this_turn", "medium", "shared-card-role"))
            # Denial is live only while their board holds Energy to take. WHICH body loses
            # it stays Bellman's pick — this only puts the card in the searched set.
            if "energy_denial" in tags:
                hints.append(StrategyHint(
                    f"general.card.{card_id}.deny_the_energy", "general",
                    (ActivationCondition("opponent.energy_in_play", "gt", 0),),
                    (DesiredFact("play_card", "own.active", target_card_ids=(card_id,)),),
                    "own.active", "this_turn", "medium", "shared-card-role"))
            continue
        if "item_locker" in card_roles:
            hints.append(StrategyHint(
                f"general.card.{card_id}.item_lock", "general",
                (ActivationCondition("own.active.card_id", "eq", card_id),),
                (DesiredFact("item_lock", "own.active", target_card_ids=(card_id,)),),
                "own.active", "immediate", "high", "shared-card-role"))
        if "counter_mover" in card_roles:
            stat = stats.get(card_id) if stats is not None else None
            required = frozenset(getattr(stat, "abilityEnergyTypes", ()) or ())
            # energyType alone also matches a Pokemon OF that type -- Fezandipiti ex is a
            # Darkness Pokemon, not Darkness Energy -- which credited any search that could
            # find it as funding the Ability.
            energy_ids = tuple(sorted(set(
                int(energy_id) for energy_id in deck
                if bool(getattr(stats.get(int(energy_id)), "is_energy", False))
                and getattr(stats.get(int(energy_id)), "energyType", None) in required
            ))) if stats is not None else ()
            hints.extend((
                StrategyHint(
                    f"general.card.{card_id}.fund_ability", "general",
                    (ActivationCondition(f"own.card.{card_id}.in_play", "eq", True),),
                    (DesiredFact("fund_ability", recipient, target_card_ids=energy_ids),),
                    recipient, "immediate", "high", "shared-card-role"),
                StrategyHint(
                    f"general.card.{card_id}.use_ability", "general", (
                        ActivationCondition("turn.ability.card_ids", "contains", card_id),
                        ActivationCondition("own.damaged_count", "gt", 0),
                    ), (DesiredFact("use_ability", recipient, target_card_ids=(card_id,)),),
                    recipient, "immediate", "high", "shared-card-role"),
            ))
            if "confuse" in tags:
                hints.append(StrategyHint(
                    f"general.card.{card_id}.confusion_attack", "general", (),
                    (DesiredFact("status_setup", "opponent.bench.highest_role",
                                 target_card_ids=(card_id,)),),
                    "opponent.bench.highest_role", "this_turn", "medium",
                    "shared-card-role"))
        if "draw_engine" in card_roles:
            conditional_draw = bool(effects is not None and any(
                clause.get("kind") == "draw"
                and clause.get("condition") == "pokemon_ko_last_turn"
                for clause in effects.clauses(card_id)))
            if conditional_draw:
                hints.append(StrategyHint(
                    f"general.card.{card_id}.deploy_after_ko", "general", (
                        ActivationCondition("turn.pokemon_ko_window", "eq", True),
                        ActivationCondition("own.bench.card_ids", "not_contains", card_id),
                        ActivationCondition("own.bench.space", "gt", 0),
                    ), (DesiredFact("deploy", "own.bench", target_card_ids=(card_id,)),),
                    "own.bench", "immediate", "high", "shared-card-role"))
            hints.append(StrategyHint(
                f"general.card.{card_id}.draw_ability", "general",
                (ActivationCondition("turn.ability.card_ids", "contains", card_id),),
                (DesiredFact("use_ability", recipient, target_card_ids=(card_id,)),),
                recipient, "immediate", "high", "shared-card-role"))
    return tuple(hints)


__all__ = (
    "ActivatedStrategy", "GENERAL_STRATEGIES", "ResolvedStrategies", "StrategySnapshot",
    "activate_strategies", "general_card_strategies", "resolve_strategies",
)
