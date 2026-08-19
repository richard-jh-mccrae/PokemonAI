"""Deck-neutral terminal utility for full-turn Bellman search.

The evaluator contains no action policy and no card-specific behavior. It maps observable state
facts to prize-equivalent utility; the engine and Bellman recursion determine how actions change
those facts.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .cards import card_store
from .cards.card_facts import BASIC_ENERGY, EnergyCard, PokemonCard, STAGE2
from .cards.functions.attack_lock import locked_attack_ids
from .card_worth import KNOWN_CARD_FLOOR, function_role
from .cards.functions.energy import ENERGY_COLORLESS, payment_fraction, provision_units
from .information import BellmanDeckProfile
from .cards.functions.damage import bench_reach, compute_active_damage
from .cards.functions.damage_context import SideFacts, damage_context
from .strategy.context import _DAMAGE, _TO_ACTIVE
from .value import Potential, ValueRegistry, worth_to_prizes


MINIMUM_HP = 1
KNOCKED_OUT_HP = 0
TERMINAL_GAME_UTILITY = 100.0
DAMAGE_COUNTERS_PER_PRIZE = 200.0
DAMAGE_COUNTER_SIZE = 10
STANDARD_PRIZE_COUNT = 6
FUTURE_HAND_ACCESS_DISCOUNT = 0.75
OPPONENT_ROLE_PRESENCE_SHARE = 0.90
OPPONENT_ROLE_HEALTH_SHARE = 0.10
SAFE_DAMAGE_RESERVE_SHARE = 0.10
OPPONENT_ROLE_THREAT_SHARE = 0.20
OPPONENT_ROLE_WORTH_NORMALIZER = 30.0
BENCH_ATTACK_ACCESS_SHARE = 0.50
EVOLVED_BODY_PRIZE_SHARE = 0.040
DEPLOYED_BASIC_LINE_PRIZE_SHARE = 0.020
KO_PRESSURE_SHARE = 0.000001
#: ADR-0060's strip/gift currency: one hidden opponent card = the known-card floor.
OPPONENT_HAND_CARD_WORTH = KNOWN_CARD_FLOOR
#: Checkup facts (docs/rules.md L161): poison places 1 counter; burn places 2 UNCONDITIONALLY —
#: the coin only decides whether the burn then cures, never whether the damage lands.
POISON_CHECKUP_DAMAGE = 10
BURN_CHECKUP_DAMAGE = 20.0
#: Forecast share of a statused Active's attack: wake/attack coins and the paralysis turn-skip
#: (docs/rules.md L156-166); our own sleep sees two checkups before our next attack window.
INCOMING_CONDITION_SHARE = {"asleep": 0.5, "paralyzed": 0.0, "confused": 0.5}
OWN_CONDITION_SHARE = {"asleep": 0.75, "confused": 0.5}

_UNSET = object()


@dataclass(frozen=True)
class UtilityScale:
    """Only the lexicographic game result needs a scale above prize-equivalent state utility."""

    game: float = TERMINAL_GAME_UTILITY


def _bodies(player):
    return tuple(body for body in (
        tuple(player.get("active") or ()) + tuple(player.get("bench") or ())) if body)


def _energy_codes(body):
    codes = body.get("energies")
    if codes is not None:
        return [int(code) for code in codes]
    return [int(card.get("energyType", ENERGY_COLORLESS))
            for card in body.get("energyCards") or ()]


def _pay_fraction(codes, required) -> float:
    return payment_fraction(codes, required)


def _hand_count(player) -> int:
    hand = player.get("hand")
    return len(hand) if hand is not None else int(player.get("handCount", 0) or 0)


def board_parity(board: float, role_pressure: float) -> float:
    """Our board Worth over the opponent's role-pressure magnitude, in ``[0, 1]`` (ADR-0141).
    No resolved pressure means nothing to be behind of, so parity stays whole."""
    if role_pressure <= 0.0:
        return 1.0
    return min(1.0, max(0.0, board) / role_pressure)


def own_stadium(current, seat: int) -> tuple:
    return tuple(card for card in (current.get("stadium") or ())
                 if card and card.get("playerIndex") is not None
                 and int(card["playerIndex"]) == seat)


def _active_condition_share(player, table) -> float:
    """Special conditions ride the player payload and apply to that side's Active only."""
    share = 1.0
    for name, factor in table.items():
        if player.get(name):
            share *= factor
    return share


class BoardPotential:
    """Absolute observable-state utility used at every Bellman transition.

    Card identities enter only through the supplied card facts, declared deck relationships, and
    printed attacks. No action kind, named card, matchup, or tactical sequence is preferred here.
    """

    def __init__(self, cards=None, *, registry: ValueRegistry,
                 profile: BellmanDeckProfile | None = None,
                 scale: UtilityScale = UtilityScale(), root_seat: int | None = None,
                 opponent_role_worth=None, isolated_selection: bool = False,
                 opponent_hand_share: float = 0.0, root_observation=None):
        #: Card records by id — the unified store unless a test injects its own records.
        self.cards = card_store() if cards is None else cards
        self.registry = registry
        self.profile = profile or BellmanDeckProfile.from_registry(registry)
        self.scale = scale
        self.root_seat = None if root_seat is None else int(root_seat)
        self.opponent_role_worth = {int(card_id): max(0.0, float(worth))
                                    for card_id, worth in (opponent_role_worth or {}).items()}
        self.isolated_selection = bool(isolated_selection)
        # Every consumer of the opponent-hand term must read THIS share, or the paths disagree.
        self.opponent_hand_share = max(0.0, float(opponent_hand_share))
        # Pinned to the deciding position, never per successor: ADR-0141 amendment, or the scaling
        # leaks into the damage and development families.
        self.board_parity = 1.0
        self._resource_job_cache = {}
        self._prize_job_capacities_cache = None
        self._cost_cap_cache = {}
        self._forward_cache = {}
        # Facts, energy codes, and damage contexts recur ~17x within one evaluation over the same
        # player/body dicts.  The observation is immutable for the duration of one ``__call__``, so
        # results are keyed by object identity and the cache lives only for that call.
        self._call_cache = None
        # Per-observation scratch, refreshed at the top of every `_evaluate`. A self-locked attack
        # is board state the observation does not carry, so it arrives beside it under
        # `attack_locks` and has to reach `_attack_value` somehow. Defaulted BEFORE the root-parity
        # read below, which walks the same attack valuations.
        self._attack_locks: dict = {}
        self._turn = 0
        if root_observation is not None:
            self.board_parity = self._root_board_parity(root_observation)

    def _sides(self, current):
        seat = int(current.get("yourIndex", 0)) if self.root_seat is None else self.root_seat
        players = current.get("players") or ()

        def side(index):
            return players[index] if 0 <= index < len(players) and players[index] else {}

        return seat, side(seat), side(1 - seat)

    def _root_board_parity(self, observation) -> float:
        current = observation.get("current") or {}
        seat, me, opponent = self._sides(current)
        role_pressure = -self._opponent_role_pressure(opponent)
        return board_parity(self._own_board_resources(me, stadium=own_stadium(current, seat)),
                            role_pressure)

    def _card(self, card_id):
        return self.cards.get(int(card_id)) if card_id is not None else None

    def _forward_ids(self, card_id) -> tuple[int, ...]:
        """Store Pokemon that evolve onto this card — the WHOLE line above it, name-matched,
        because a Basic's threat and cost ceiling live at the top of its line, not one hop up."""
        card_id = int(card_id)
        found = self._forward_cache.get(card_id)
        if found is None:
            forwards: list[int] = []
            frontier = [getattr(self._card(card_id), "name", None)]
            while frontier:
                name = frontier.pop()
                for other_id, other in self.cards.items():
                    if (name is not None and isinstance(other, PokemonCard)
                            and other.evolves_from == name and other_id not in forwards):
                        forwards.append(other_id)
                        frontier.append(other.name)
            found = self._forward_cache[card_id] = tuple(sorted(forwards))
        return found

    def _usable_attacks(self, body, card):
        """This body's printed attacks minus the ones a self-lock bars at the current turn."""
        barred = locked_attack_ids(self._attack_locks, body, self._turn)
        for attack in getattr(card, "attacks", ()) or ():
            if attack.attack_id not in barred:
                yield attack

    def _prizes(self, body) -> int:
        card = self._card(body.get("id"))
        return int(getattr(card, "prize_value", 1) if card is not None else 1)

    def _card_prizes(self, card_id: int) -> int:
        card = self._card(card_id)
        return int(getattr(card, "prize_value", 1) if card is not None else 1)

    def _codes(self, body):
        cache = self._call_cache
        if cache is None:
            return _energy_codes(body)
        key = ("codes", id(body))
        found = cache.get(key)
        if found is None:
            found = cache[key] = _energy_codes(body)
        return found

    def _context(self, attacker_facts: SideFacts, defender_facts: SideFacts) -> dict:
        cache = self._call_cache
        if cache is None:
            return damage_context(attacker_facts, defender_facts)
        key = ("ctx", id(attacker_facts), id(defender_facts))
        found = cache.get(key)
        if found is None:
            found = cache[key] = damage_context(attacker_facts, defender_facts)
        return found

    def _side_facts(self, player, *, attacking_body=None) -> SideFacts:
        cache = self._call_cache
        if cache is None:
            return self._build_side_facts(player, attacking_body=attacking_body)
        key = ("sf", id(player), id(attacking_body))
        found = cache.get(key)
        if found is None:
            found = cache[key] = self._build_side_facts(player, attacking_body=attacking_body)
        return found

    def _build_side_facts(self, player, *, attacking_body=None) -> SideFacts:
        bodies = _bodies(player)
        active = attacking_body or next(
            (body for body in (player.get("active") or ()) if body), None)
        bench = tuple(body for body in (player.get("bench") or ()) if body)

        def record_for(card):
            return self._card(card.get("id")) if card else None

        def is_basic_energy(record) -> bool:
            return isinstance(record, EnergyCard) and record.kind == BASIC_ENERGY

        def counters(body):
            maximum = int(body.get("maxHp", body.get("hp", 0)) or 0)
            return max(0, maximum - int(body.get("hp", maximum) or 0)) // DAMAGE_COUNTER_SIZE

        discard_records = tuple(record_for(card) for card in (player.get("discard") or ()))
        basic_by_type: dict[int, int] = {}
        for record in discard_records:
            if not is_basic_energy(record):
                continue
            provides = int(record.provides)
            basic_by_type[provides] = basic_by_type.get(provides, 0) + 1

        def card_name(body):
            return str(getattr(record_for(body), "name", "") or "")

        def attack_names(body):
            record = record_for(body)
            return tuple(attack.name for attack in getattr(record, "attacks", ()) or ())

        boosts = []
        for tool in (active.get("tools") or ()) if active else ():
            record = record_for(tool)
            clause = record.clause("damage_boost") if record is not None \
                and hasattr(record, "clause") else None
            if clause is not None and clause.amount:
                boosts.append((int(clause.amount), clause.attacker_type,
                               bool(clause.vs_ex)))

        deck_cards = tuple(player.get("deck") or ())
        deck_basic_by_type: dict[int, int] | None = {} if deck_cards else None
        if deck_basic_by_type is not None:
            for card in deck_cards:
                record = record_for(card)
                if not is_basic_energy(record):
                    continue
                provides = int(record.provides)
                deck_basic_by_type[provides] = deck_basic_by_type.get(provides, 0) + 1

        prize = player.get("prize")
        prizes_taken = STANDARD_PRIZE_COUNT - len(prize) if prize is not None else 0
        hand = player.get("hand")
        hand_size = len(hand) if hand is not None else int(player.get("handCount", 0) or 0)
        return SideFacts(
            hand_size=hand_size,
            active_energy=len(self._codes(active)) if active else 0,
            bench_count=len(bench),
            prizes_taken=prizes_taken,
            active_counters=counters(active) if active else 0,
            counters_in_play=sum(counters(body) for body in bodies),
            bench_stage2=sum(getattr(record_for(body), "stage", None) == STAGE2
                             for body in bench),
            ex_in_play=sum(bool(getattr(record_for(body), "is_rule_box", False))
                           for body in bodies),
            discard_energy_total=sum(isinstance(record, EnergyCard)
                                     for record in discard_records),
            discard_basic_by_type=basic_by_type,
            bench_names=tuple(card_name(body) for body in bench),
            in_play_names=tuple(card_name(body) for body in bodies),
            in_play_attack_names=tuple(attack_names(body) for body in bodies),
            damage_boosts=tuple(boosts),
            deck_count=(len(deck_cards) if deck_cards else None),
            deck_basic_by_type=deck_basic_by_type,
        )

    def _defender_tool_transient(self, defender) -> dict | None:
        """Attached-tool damage reduction on the defending BODY — without it the forecast reads
        only the Pokémon card's own printed defenses and overestimates every KO."""
        cache = self._call_cache
        if cache is not None:
            key = ("tool", id(defender))
            found = cache.get(key, _UNSET)
            if found is not _UNSET:
                return found
        holder = self._card(defender.get("id"))
        holder_type = getattr(holder, "energy_type", None)
        reduction, typed = 0, []
        for tool in (defender.get("tools") or ()):
            record = self._card(tool.get("id") if isinstance(tool, dict) else tool)
            clause = record.clause("damage_reduction") if record is not None \
                and hasattr(record, "clause") else None
            amount = int(clause.amount or 0) if clause is not None else 0
            if not amount:
                continue
            if (clause.holder_types is not None
                    and holder_type not in clause.holder_types):
                continue                               # Thick Scale on a non-{N} holder is inert
            types = clause.attacker_types
            needs_ability = bool(clause.requires_ability)
            if types is None and not needs_ability:
                reduction += amount
            else:                                      # attacker-gated: resolved per attack
                typed.append((amount, types, needs_ability))
        result = {}
        if reduction:
            result["reduction"] = reduction
        if typed:
            result["typed"] = tuple(typed)
        result = result or None
        if cache is not None:
            cache[key] = result
        return result

    def _condition_share(self, player, table) -> float:
        cache = self._call_cache
        if cache is None:
            return _active_condition_share(player, table)
        key = ("cond", id(player), id(table))
        found = cache.get(key)
        if found is None:
            found = cache[key] = _active_condition_share(player, table)
        return found

    def _attack_value(self, body, codes, defender, attacker_facts, defender_facts, *,
                      require_ready: bool = False) -> float:
        card = self._card(body.get("id"))
        defender_card = self._card(defender.get("id")) if defender else None
        if card is None or defender is None or defender_card is None:
            return 0.0
        hp = max(MINIMUM_HP, int(defender.get("hp", MINIMUM_HP)))
        prizes = self._prizes(defender)
        context = self._context(attacker_facts, defender_facts)
        transient = self._defender_tool_transient(defender)
        defender_tags = getattr(defender_card, "tags", frozenset())
        best = 0.0
        for attack in self._usable_attacks(body, card):
            readiness = _pay_fraction(codes, attack.cost)
            if require_ready and readiness < 1.0:
                continue
            damage = max(float(compute_active_damage(
                             attack, card, defender_card, defender_tags, context=context,
                             defender_transient=transient)),
                         float(bench_reach(attack)))
            best = max(best, prizes * min(1.0, damage / hp) * readiness)
        return best

    def _replacement_risk(self, me, opponent, exposed, *, can_bench: bool) -> float:
        """An Active knocked out with nothing to promote ends the game (``docs/rules.md`` 7.2), so
        holding no replacement costs the whole remaining prize race, not one Active's prizes."""
        if any(body for body in (me.get("bench") or ())):
            return 0.0
        hand = me.get("hand")
        if hand is None:                       # a hidden hand cannot be shown to hold no Basic
            return 0.0
        # Only while the turn is still ours: a Basic held past End cannot reach the Bench before
        # the opponent's knockout, so it must not discharge a liability it can no longer answer.
        for card in hand if can_bench else ():
            record = self._card(card.get("id")) if card else None
            if isinstance(record, PokemonCard) and not record.evolves_from:
                return 0.0
        # Reachable now it is the live liability; otherwise the board is merely one unanswered
        # knockout from losing, which is held in reserve exactly as unreachable damage is.
        reserve = 1.0 if 0 in exposed else SAFE_DAMAGE_RESERVE_SHARE
        return -reserve * float(len(opponent.get("prize") or ()))

    def _damage_progress(self, player, *, exposed=None) -> float:
        total = 0.0
        body_ids = Counter(int(body.get("id", 0)) for body in _bodies(player))
        for position, body in enumerate(_bodies(player)):
            maximum = max(MINIMUM_HP, int(body.get("maxHp", body.get("hp", MINIMUM_HP))))
            health = max(KNOCKED_OUT_HP, int(body.get("hp", maximum)))
            damage = maximum - health
            # Damage only converts into prizes on a body the opponent can actually reach, so a
            # body no printed attack knocks out next turn holds its counters in reserve.
            reserve = (1.0 if exposed is None or position in exposed
                       else SAFE_DAMAGE_RESERVE_SHARE)
            # Linear progress prices every damage counter.  Convex KO pressure additionally
            # prices concentration: the same new damage is more useful on an already injured
            # target because it is closer to converting into prizes.
            total += reserve * (
                damage / DAMAGE_COUNTERS_PER_PRIZE
                + (self._prizes(body) * KO_PRESSURE_SHARE * (damage / maximum) ** 2
                   if (self.isolated_selection
                       and body_ids[int(body.get("id", 0))] > 1) else 0.0))
        active = next((body for body in (player.get("active") or ()) if body), None)
        if active is not None:
            # Checkup damage lands whether or not any attack reaches, so it carries no reserve.
            pending = ((POISON_CHECKUP_DAMAGE if player.get("poisoned") else 0.0)
                       + (BURN_CHECKUP_DAMAGE if player.get("burned") else 0.0))
            if pending:
                remaining = max(KNOCKED_OUT_HP, int(active.get("hp", MINIMUM_HP)))
                total += min(pending, remaining) / DAMAGE_COUNTERS_PER_PRIZE
        return total

    def _reachable_defenders(self, body, *, opponent_moves_next: bool):
        variants = [body]
        if not opponent_moves_next:
            return tuple(variants)
        maximum = max(MINIMUM_HP, int(body.get("maxHp", body.get("hp", MINIMUM_HP))))
        damage = max(KNOCKED_OUT_HP, maximum - int(body.get("hp", maximum)))
        for card_id in self._forward_ids(int(body.get("id", 0))):
            if card_id not in self.opponent_role_worth:
                continue
            card = self._card(card_id)
            if card is None:
                continue
            evolved = dict(body)
            evolved["id"] = int(card_id)
            evolved["maxHp"] = int(getattr(card, "hp", maximum) or maximum)
            evolved["hp"] = max(MINIMUM_HP, evolved["maxHp"] - damage)
            variants.append(evolved)
        return tuple(variants)

    def _readiness(self, me, opponent, *, opponent_moves_next: bool = False,
                   include_incoming: bool = True) -> float:
        mine = next((body for body in (me.get("active") or ()) if body), None)
        theirs = next((body for body in (opponent.get("active") or ()) if body), None)
        defenders = (self._reachable_defenders(
            theirs, opponent_moves_next=opponent_moves_next) if theirs is not None else ())
        opponent_facts = self._side_facts(opponent)
        me_facts = self._side_facts(me)
        active_values = []
        bench_values = []
        if theirs is not None:
            for bodies, values in (((me.get("active") or ()), active_values),
                                   ((me.get("bench") or ()), bench_values)):
                for body in (body for body in bodies if body):
                    attacker_facts = self._side_facts(me, attacking_body=body)
                    values.append(min((self._attack_value(
                        body, self._codes(body), defender, attacker_facts, opponent_facts)
                        for defender in defenders), default=0.0))
        own = max(max(active_values, default=0.0)
                  * self._condition_share(me, OWN_CONDITION_SHARE),
                  BENCH_ATTACK_ACCESS_SHARE * max(bench_values, default=0.0))
        incoming_values = []
        if include_incoming and mine is not None:
            incoming_active_share = self._condition_share(opponent, INCOMING_CONDITION_SHARE)
            for body in _bodies(opponent):
                attacker_facts = self._side_facts(opponent, attacking_body=body)
                incoming_values.append(self._attack_value(
                    body, self._codes(body), mine, attacker_facts, me_facts)
                    * (incoming_active_share if body is theirs else 1.0)
                    * (1.0 + OPPONENT_ROLE_THREAT_SHARE
                       * self.opponent_role_worth.get(int(body.get("id", 0)), 0.0)
                       / OPPONENT_ROLE_WORTH_NORMALIZER))
        incoming = max(incoming_values, default=0.0)
        return own - incoming

    def _attack_coverage(self, body, codes, me, opponent, *, require_ready=False) -> float:
        active = next((target for target in (opponent.get("active") or ()) if target), None)
        bench = tuple(target for target in (opponent.get("bench") or ()) if target)
        if active is None and not bench:
            return 0.0
        attacker_facts = self._side_facts(me, attacking_body=body)
        defender_facts = self._side_facts(opponent)
        active_value = (self._attack_value(
            body, codes, active, attacker_facts, defender_facts,
            require_ready=require_ready) if active else 0.0)
        next_value = max((self._attack_value(
            body, codes, defender, attacker_facts, defender_facts,
            require_ready=require_ready)
                          for defender in bench), default=0.0)
        return active_value + next_value

    def _next_attachment_coverage(self, me, opponent) -> float:
        active = next((body for body in (me.get("active") or ()) if body), None)
        if active is None:
            return 0.0
        energy_provisions = []
        for card in me.get("hand") or ():
            record = self._card(card.get("id")) if card else None
            if not isinstance(record, EnergyCard):
                continue
            units = provision_units(record, evolved=bool(active.get("preEvolution")))
            energy_provisions.append((int(record.provides), max(1, units)))
        codes = self._codes(active)
        return max((self._attack_ko_coverage(
            active, [*codes, *([energy_type] * units)], me, opponent)
                    for energy_type, units in energy_provisions), default=0.0)

    def _attack_ko_coverage(self, body, codes, me, opponent) -> float:
        defender = next((target for target in (opponent.get("active") or ()) if target), None)
        if defender is None:
            return 0.0
        card = self._card(body.get("id"))
        defender_card = self._card(defender.get("id"))
        if card is None or defender_card is None:
            return 0.0
        attacker_facts = self._side_facts(me, attacking_body=body)
        defender_facts = self._side_facts(opponent)
        defender_tags = getattr(defender_card, "tags", frozenset())
        transient = self._defender_tool_transient(defender)
        best = 0.0
        for attack in self._usable_attacks(body, card):
            if _pay_fraction(codes, attack.cost) < 1.0:
                continue
            damage = compute_active_damage(
                attack, card, defender_card, defender_tags,
                context=self._context(attacker_facts, defender_facts),
                defender_transient=transient)
            if damage < int(defender.get("hp", MINIMUM_HP)):
                continue
            bench_prizes = self._bench_ko_prizes(attack, opponent.get("bench") or ())
            best = max(best, float(self._prizes(defender) + bench_prizes))
        return best

    def _multi_target_ko_ready(self, me, opponent) -> float:
        """Prize value of a currently ready attack that can KO Active and Bench together."""
        defender = next((body for body in (opponent.get("active") or ()) if body), None)
        bench = tuple(body for body in (opponent.get("bench") or ()) if body)
        if defender is None or not bench:
            return 0.0
        defender_card = self._card(defender.get("id"))
        if defender_card is None:
            return 0.0
        defender_facts = self._side_facts(opponent)
        defender_tags = getattr(defender_card, "tags", frozenset())
        transient = self._defender_tool_transient(defender)
        best = 0.0
        for body in _bodies(me):
            card = self._card(body.get("id"))
            if card is None:
                continue
            context = self._context(
                self._side_facts(me, attacking_body=body), defender_facts)
            codes = self._codes(body)
            for attack in self._usable_attacks(body, card):
                if _pay_fraction(codes, attack.cost) < 1.0:
                    continue
                active_damage = compute_active_damage(
                    attack, card, defender_card, defender_tags, context=context,
                    defender_transient=transient)
                if active_damage < int(defender.get("hp", MINIMUM_HP)):
                    continue
                target_prizes = self._bench_ko_prizes(attack, bench)
                if target_prizes:
                    best = max(best, float(self._prizes(defender) + target_prizes))
        return best

    def _lethal_exposure(self, defender_side, attacker_side) -> tuple[float, frozenset[int]]:
        """The (negative) worst prize liability an opposing printed attack reaches next turn, plus
        the ``_bodies`` positions it can knock out so damage elsewhere is not priced as reachable."""
        actives = tuple(body for body in (defender_side.get("active") or ()) if body)
        active = actives[0] if actives else None
        bench = tuple(body for body in (defender_side.get("bench") or ()) if body)
        bench_offset = len(actives)
        if active is None:
            return 0.0, frozenset()
        active_card = self._card(active.get("id"))
        if active_card is None:
            return 0.0, frozenset()
        active_tags = getattr(active_card, "tags", frozenset())
        defender_facts = self._side_facts(defender_side)
        attacker_active = next(
            (body for body in (attacker_side.get("active") or ()) if body), None)
        attacker_active_share = self._condition_share(
            attacker_side, INCOMING_CONDITION_SHARE)
        active_transient = self._defender_tool_transient(active)
        worst = 0.0
        reachable: set[int] = set()
        for body in _bodies(attacker_side):
            card = self._card(body.get("id"))
            if card is None:
                continue
            context = self._context(
                self._side_facts(attacker_side, attacking_body=body), defender_facts)
            # The ledger records BOTH seats, so an opponent's spent one-shot is already in it:
            # fearing a hit they cannot land is as wrong as crediting our own (ADR-0142).
            for attack in self._usable_attacks(body, card):
                exposed = 0.0
                lethal_active = False
                active_damage = compute_active_damage(
                    attack, card, active_card, active_tags, context=context,
                    defender_transient=active_transient)
                if active_damage >= int(active.get("hp", MINIMUM_HP)):
                    exposed += self._prizes(active)
                    lethal_active = True
                sniped = self._bench_ko_indices(attack, bench)
                exposed += self._bench_ko_prizes(attack, bench)
                share = attacker_active_share if body is attacker_active else 1.0
                exposed *= share
                # A body that cannot attack next turn reaches nothing, so it marks nothing.
                if share > 0.0:
                    reachable.update(index + bench_offset for index in sniped)
                    if lethal_active:
                        reachable.add(0)
                worst = max(worst, exposed)
        return -worst, frozenset(reachable)

    def _bench_ko_indices(self, attack, bench) -> tuple[int, ...]:
        """Bench positions this attack can knock out on its own. A Tera body takes no damage from
        attacks while benched, so neither snipe nor concentrated spread reaches it."""
        reach = bench_reach(attack)
        return tuple(index for index, target in enumerate(bench)
                     if not bool(getattr(self._card(target.get("id")), "tera", False))
                     and reach >= int(target.get("hp", MINIMUM_HP)))

    def _bench_ko_prizes(self, attack, bench) -> float:
        return float(max((self._prizes(bench[index])
                          for index in self._bench_ko_indices(attack, bench)), default=0))

    @staticmethod
    def _stack_ids(body):
        rows = [body]
        rows.extend(body.get("preEvolution") or ())
        rows.extend(body.get("energyCards") or ())
        rows.extend(body.get("tools") or ())
        return tuple(int(card.get("id") if isinstance(card, dict) else card)
                     for card in rows
                     if card is not None and (not isinstance(card, dict) or card.get("id") is not None))

    def _resource_job(self, card_id: int):
        card_id = int(card_id)
        if card_id in self._resource_job_cache:
            return self._resource_job_cache[card_id]
        roles = tuple(sorted(self.registry.roles.get(card_id, ())))
        functions = tuple(sorted(tag for tag in self.registry.functions.get(card_id, ())
                                 if not str(tag).startswith("provides:")))
        facts = self.registry.facts.get(card_id)
        category = "pokemon" if facts is not None and facts.pokemon else "card"
        intrinsic_role = function_role(functions)
        result = (("role", roles[0], category) if roles else
                  ("role", intrinsic_role, category) if intrinsic_role else
                  ("function", functions[0], category) if functions else
                  ("card", card_id, category))
        self._resource_job_cache[card_id] = result
        return result

    def _prize_job_capacities(self):
        if self._prize_job_capacities_cache is not None:
            return self._prize_job_capacities_cache
        capacities = {}
        for route in self.profile.prize_routes:
            counts = Counter(self._resource_job(int(card_id)) for card_id in route)
            for card_job, count in counts.items():
                capacities[card_job] = max(capacities.get(card_job, 1), count)
        self._prize_job_capacities_cache = capacities
        return capacities

    def _own_board_resources(self, me, stadium=()) -> float:
        """OUR side only: registry Worth reads 0.0 for cards outside our deck, not "no board"."""
        capacities = self._prize_job_capacities()
        body_ids = {int(body.get("id", 0)) for body in _bodies(me)}
        required_partners = dict(self.profile.partners)
        jobs: dict[tuple, list[float]] = {}
        for body in _bodies(me):
            for card_id in self._stack_ids(body):
                if isinstance(self._card(card_id), EnergyCard):
                    continue
                partners = required_partners.get(card_id, ())
                if partners and not set(partners).issubset(body_ids):
                    continue
                jobs.setdefault(self._resource_job(card_id), []).append(
                    self.registry.worth(card_id))
        # Our Stadium in play is a board resource like any attached card; without this a Stadium
        # play was a pure hand loss and the agent was structurally disincentivised from it.
        for card in stadium:
            if card and card.get("id") is not None:
                jobs.setdefault(self._resource_job(int(card["id"])), []).append(
                    self.registry.worth(int(card["id"])))
        worth = sum(sum(sorted(values, reverse=True)[:capacities.get(card_job, len(values))])
                    for card_job, values in jobs.items())
        return float(worth_to_prizes(worth))

    def _held_card_usable(self, me, card_id: int) -> bool:
        card = self._card(card_id)
        if card is None:
            return True
        bodies = _bodies(me)
        if isinstance(card, EnergyCard):
            return self.isolated_selection or any(
                len(self._codes(body)) < self._energy_cost_cap(int(body.get("id", 0)))
                for body in bodies)
        evolves_from = getattr(card, "evolves_from", None)
        if not evolves_from:
            return True
        parent = self.registry.line_parents.get(int(card_id))
        return any(
            (parent is not None and int(body.get("id", 0)) == int(parent))
            or getattr(self._card(body.get("id")), "name", None) == evolves_from
            for body in bodies
        )

    def _energy_cost_cap(self, card_id: int) -> int:
        card_id = int(card_id)
        found = self._cost_cap_cache.get(card_id)
        if found is not None:
            return found
        found = self._cost_cap_cache[card_id] = self._build_energy_cost_cap(card_id)
        return found

    def _build_energy_cost_cap(self, card_id: int) -> int:
        candidates = [int(card_id), *self._forward_ids(card_id)]
        cap = 0
        for candidate in candidates:
            card = self._card(candidate)
            for attack in (getattr(card, "attacks", ()) or ()):
                cap = max(cap, len(attack.cost))
        return cap

    def _active_ko_ready(self, me, opponent) -> bool:
        attacker = next((body for body in (me.get("active") or ()) if body), None)
        defender = next((body for body in (opponent.get("active") or ()) if body), None)
        if attacker is None or defender is None:
            return False
        return self._attack_value(
            attacker, self._codes(attacker), defender,
            self._side_facts(me, attacking_body=attacker), self._side_facts(opponent),
        ) >= self._prizes(defender)

    def _energy_position(self, me, opponent, *, historical_context=None) -> float:
        """Usable attached-resource value, shaped by deployment urgency and survival.

        Energy on an identical full-health backup is exposure while the Active's largest attack
        remains unfunded; the Active's prize liability prices that delay.
        """
        total = 0.0
        active_ko_ready = self._active_ko_ready(me, opponent)
        for body in _bodies(me):
            cap = self._energy_cost_cap(int(body.get("id", 0)))
            if cap <= 0:
                continue
            maximum = max(MINIMUM_HP, int(body.get("maxHp", body.get("hp", MINIMUM_HP))))
            survival = max(0.0, min(1.0, int(body.get("hp", maximum)) / maximum))
            cards = tuple(card for card in (body.get("energyCards") or ()) if card)
            remaining = cap
            values = []
            overcap = 0.0
            for card in cards:
                record = self._card(card.get("id"))
                supplied = provision_units(
                    record if isinstance(record, EnergyCard) else None,
                    evolved=bool(body.get("preEvolution")))
                units = min(remaining, supplied)
                unit_value = worth_to_prizes(
                    self.registry.worth(int(card.get("id", 0)))) / supplied
                values.extend(
                    unit_value
                    for _ in range(units))
                overcap += max(0, supplied - units) * unit_value
                remaining -= units
            if not values:
                values = [worth_to_prizes(self.registry.seeds.energy)] * min(
                    cap, len(self._codes(body)))
            diversify = (not self.isolated_selection or active_ko_ready
                          or bool(body.get("preEvolution")))
            shaped = sum(value / (index + 1) if diversify else value * (index + 1)
                         for index, value in enumerate(values))
            if not self.isolated_selection or historical_context != _DAMAGE:
                shaped *= self._attack_coverage(body, self._codes(body), me, opponent)
            total += survival * shaped - overcap
        active = next((body for body in (me.get("active") or ()) if body), None)
        if active is not None and not self.isolated_selection:
            cap = self._energy_cost_cap(int(active.get("id", 0)))
            missing = max(0, cap - len(self._codes(active)))
            active_maximum = max(
                MINIMUM_HP, int(active.get("maxHp", active.get("hp", MINIMUM_HP))))
            active_full = int(active.get("hp", 0)) >= active_maximum
            if missing and active_full:
                backups = tuple(body for body in (me.get("bench") or ()) if body
                                and int(body.get("id", 0)) == int(active.get("id", 0))
                                and int(body.get("hp", 0)) >= max(
                                    MINIMUM_HP,
                                    int(body.get("maxHp", body.get("hp", MINIMUM_HP)))))
                stranded_units = sum(len(self._codes(body)) for body in backups)
                total -= (self._prizes(active) * missing
                          * min(1.0, stranded_units / max(1, cap)))
        return total

    def _development(self, me) -> float:
        """Value deployed and evolved pieces of declared evolution lines."""
        evolved = sum(self._prizes(body) * EVOLVED_BODY_PRIZE_SHARE
                      for body in _bodies(me) if body.get("preEvolution"))
        line_payoff = {
            int(line[0]): self._card_prizes(int(line[-1]))
            for line in self.registry.lines if len(line) > 1
        }
        deployed = sum(
            line_payoff.get(int(body.get("id", 0)), 0) * DEPLOYED_BASIC_LINE_PRIZE_SHARE
            for body in _bodies(me) if not body.get("preEvolution")
        )
        return evolved + deployed

    def _occupied_jobs(self, me, *, skip_energy: bool = False) -> Counter:
        """Board jobs already staffed, counted in cards: ``_prize_job_capacities`` counts the cards
        along a prize route, so a stack supplies its pre-evolution's slot as well as its own."""
        occupied = Counter()
        for body in _bodies(me):
            for card_id in self._stack_ids(body):
                if skip_energy and isinstance(self._card(card_id), EnergyCard):
                    continue
                occupied[self._resource_job(card_id)] += 1
        return occupied

    def _hand_resources(self, me, *, setup_complete: bool) -> float:
        capacities = self._prize_job_capacities()
        occupied = self._occupied_jobs(me, skip_energy=self.isolated_selection)
        candidates: dict[tuple, list[float]] = {}
        for card in (me.get("hand") or ()):
            if not card or card.get("id") is None:
                continue
            card_id = int(card["id"])
            if not self._held_card_usable(me, card_id):
                continue
            facts = self.registry.facts.get(card_id)
            tags = self.registry.functions.get(card_id, ())
            if (setup_complete and "opener" in tags
                    and facts is not None and facts.stage != "basic"):
                continue
            card_job = self._resource_job(card_id)
            held_worth = self.registry.worth(card_id)
            if self.isolated_selection and "discard_eot" in tags:
                held_worth *= 0.20
            candidates.setdefault(card_job, []).append(held_worth)
        worth = 0.0
        for card_job, values in candidates.items():
            remaining = max(0, capacities.get(card_job, 1) - occupied.get(card_job, 0))
            worth += sum(sorted(values, reverse=True)[:remaining])
        return FUTURE_HAND_ACCESS_DISCOUNT * float(worth_to_prizes(worth))

    def _hand_demand(self, me) -> float:
        """Value visible cards and general access by presently missing board jobs."""
        occupied = self._occupied_jobs(me)
        capacities = self._prize_job_capacities()
        missing_slots = sum(max(0, capacity - occupied[job])
                            for job, capacity in capacities.items())
        value = 0.0
        access = 0.0
        seen = Counter()
        for card in (me.get("hand") or ()):
            if not card or card.get("id") is None:
                continue
            card_id = int(card["id"])
            if not self._held_card_usable(me, card_id):
                continue
            job = self._resource_job(card_id)
            capacity = capacities.get(job, 1)
            if occupied[job] + seen[job] < capacity:
                seen[job] += 1
                value += worth_to_prizes(self.registry.worth(card_id))
            tags = frozenset(self.registry.functions.get(card_id, ()))
            if (self.isolated_selection and missing_slots
                    and {"draw", "dig", "tutor_energy"}.intersection(tags)):
                access += missing_slots * worth_to_prizes(self.registry.worth(card_id))
        return 0.01 * value + FUTURE_HAND_ACCESS_DISCOUNT * access

    def _opponent_role_pressure(self, opponent) -> float:
        """Remaining existence plus health Worth of roles declared by the matched scouting Brief."""
        total = 0.0
        for body in _bodies(opponent):
            worth = self.opponent_role_worth.get(int(body.get("id", 0)), 0.0)
            if not worth:
                continue
            health = max(KNOCKED_OUT_HP, int(body.get("hp", MINIMUM_HP)))
            total += worth_to_prizes(worth) * (
                OPPONENT_ROLE_PRESENCE_SHARE
                + OPPONENT_ROLE_HEALTH_SHARE * health / DAMAGE_COUNTERS_PER_PRIZE)
        return -total

    def _route_suffix(self, route, prizes_taken: int):
        cumulative = 0
        for index, card_id in enumerate(route):
            if cumulative == prizes_taken:
                return route[index:]
            cumulative += self._card_prizes(card_id)
        return () if cumulative == prizes_taken else None

    def _can_develop_into(self, card_id: int, payoff_id: int) -> bool:
        return card_id == payoff_id or any(
            card_id in line[:-1] and line[-1] == payoff_id for line in self.profile.lines)

    def _prize_plan(self, me, opponent) -> float:
        if not self.profile.prize_routes or not self.profile.prizes_to_win:
            return 0.0
        prizes_taken = self.profile.prizes_to_win - len(opponent.get("prize") or ())
        if prizes_taken < 0:
            return 0.0
        active = next((body for body in (me.get("active") or ()) if body), None)
        board_ids = [int(body.get("id", 0)) for body in _bodies(me)]
        hand_ids = [int(card["id"]) for card in (me.get("hand") or ())
                    if card and card.get("id") is not None]
        values = []
        for route in self.profile.prize_routes:
            route_prizes = sum(self._card_prizes(card_id) for card_id in route)
            excess = route_prizes - self.profile.prizes_to_win
            if excess <= 0:
                continue
            suffix = self._route_suffix(route, prizes_taken)
            if not suffix:
                continue
            bodies = list(board_ids)
            held = list(hand_ids)
            covered = 0
            for desired in suffix:
                index = next((index for index, card_id in enumerate(bodies)
                              if card_id == desired), None)
                if index is not None:
                    bodies.pop(index)
                    covered += 1
                    continue
                base_index = next((index for index, card_id in enumerate(bodies)
                                   if self._can_develop_into(card_id, desired)), None)
                payoff_index = next((index for index, card_id in enumerate(held)
                                     if card_id == desired), None)
                if base_index is None or payoff_index is None:
                    break
                bodies.pop(base_index)
                held.pop(payoff_index)
                covered += 1
            if (active is not None and suffix
                    and not self._can_develop_into(int(active.get("id", 0)), suffix[0])):
                covered = 0
            # The declared route makes the opponent take `excess` additional
            # prizes. Its utility is therefore measured in those prize units,
            # attenuated only by the fraction of the remaining route presently
            # available on board or directly in hand.
            values.append(float(excess) * (covered / len(suffix)))
        return max(values, default=0.0)

    def __call__(self, observation) -> Potential:
        self._call_cache = {}
        try:
            return self._evaluate(observation)
        finally:
            self._call_cache = None

    def _evaluate(self, observation) -> Potential:
        current = observation.get("current") or {}
        self._attack_locks = observation.get("attack_locks") or {}
        self._turn = int(current.get("turn", 0))
        seat, me, opponent = self._sides(current)
        result = int(current.get("result", -1))
        if result != -1:
            game = self.scale.game if result == seat else -self.scale.game
            return Potential(game, (("game", game),))
        _liability, exposed_bodies = self._lethal_exposure(me, opponent)
        historical_context = observation.get("bellmanHistoricalContext")
        selection_context = (historical_context if historical_context is not None
                             else (observation.get("select") or {}).get("context"))
        promoted_after_attack = (self.isolated_selection
                                 and historical_context == _TO_ACTIVE)
        opponent_moves_next = int(observation.get("bellmanActor", seat)) != seat
        readiness = self._readiness(
            me, opponent, opponent_moves_next=opponent_moves_next,
            include_incoming=not promoted_after_attack)
        if promoted_after_attack:
            readiness = self._next_attachment_coverage(me, opponent)
        board = self._own_board_resources(me, stadium=own_stadium(current, seat))
        opponent_roles = self._opponent_role_pressure(opponent)
        families = {
            "game": self._replacement_risk(me, opponent, exposed_bodies,
                                           can_bench=not opponent_moves_next),
            "prize_race": float(len(opponent.get("prize") or ()) - len(me.get("prize") or ())),
            "damage": (self._damage_progress(opponent)
                       - self._damage_progress(me, exposed=exposed_bodies)),
            "readiness": readiness,
            "multi_target_ko": (0.0 if observation.get("bellmanHistoricalMain")
                                else self._multi_target_ko_ready(me, opponent)),
            # Historical isolated effect menus lack the parent attack continuation. Do not infer a
            # future multi-target line from that deliberately partial state.
            "board": board,
            "energy_position": self._energy_position(
                me, opponent, historical_context=selection_context),
            "development": self._development(me),
            "hand": self._hand_resources(me, setup_complete=int(current.get("turn", 0)) > 0),
            "hand_demand": self._hand_demand(me),
            "opponent_roles": opponent_roles,
            "opponent_hand": (-self.board_parity
                              * self.opponent_hand_share
                              * worth_to_prizes(OPPONENT_HAND_CARD_WORTH)
                              * _hand_count(opponent)),
            "prize_plan": self._prize_plan(me, opponent),
        }
        return Potential(sum(families.values()), tuple(sorted(families.items())))

    def optimistic_ceiling(self, _observation, **_context) -> float:
        return self.scale.game


__all__ = ("BoardPotential", "UtilityScale")
