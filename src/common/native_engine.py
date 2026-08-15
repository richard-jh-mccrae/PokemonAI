"""Native ``cg`` transition provider for production Bellman search."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, fields, is_dataclass
import hashlib

from .algebra import Actor, Chance, Deterministic, Terminal, Unknown, WeightedEdge
from .options import LegalAction, enumerate_legal_actions
from .commutativity import action_footprint
from .refresh import refresh_transition
from .refresh import played_card_id
from .transition_value import end_has_forced_value_change
from .state import DecisionState
from .terminal import terminal_effects_supported
from common.strategy.context import _ACTIVE, _BENCH, _MAIN, _NO, _YES


# One authoritative native world is the deployed latency budget.  Additional worlds are an
# injectable offline diagnostic seam; multiplying complete full-turn searches in a live agent
# turns one legal decision into minutes of native search and prevents a match from completing.
NATIVE_BELIEF_WORLD_COUNT = 1
MANUAL_COIN_CONTEXT = 46
COIN_BRANCH_PROBABILITY = 0.5
PROBABILITY_TOTAL = 1.0
MINIMUM_CARD_ID = 1
PHASE_DIGEST_BYTES = 8
PHASE_DENOMINATOR = float(1 << (PHASE_DIGEST_BYTES * 8))
HIDDEN_SIGNATURE_DIGEST_BYTES = 16


@dataclass(frozen=True)
class _NativeWorld:
    probability: float
    search_id: int
    attack_committed: bool = False


def _expand(counts) -> tuple[int, ...]:
    return tuple(int(card_id) for card_id, count in counts for _ in range(int(count)))


def _fill(cards, count: int, fallback) -> tuple[int, ...]:
    count = max(0, int(count))
    values = tuple(int(card_id) for card_id in cards if int(card_id) >= MINIMUM_CARD_ID)
    reserve = tuple(int(card_id) for card_id in fallback if int(card_id) >= MINIMUM_CARD_ID)
    if not values:
        values = reserve
    if not values or count == 0:
        return ()
    repeated = list(values)
    while len(repeated) < count:
        repeated.extend(reserve or values)
    return tuple(repeated[:count])


def _plain_native(value):
    """Convert cg dataclasses without ``dataclasses.asdict``'s recursive deep copies."""
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _plain_native(getattr(value, field.name)) for field in fields(value)}
    value_type = type(value)
    if value_type is list:
        return [_plain_native(child) for child in value]
    if value_type is tuple:
        return tuple(_plain_native(child) for child in value)
    if value_type is dict:
        return {key: _plain_native(child) for key, child in value.items()}
    return value


def _hidden_card_identity(card):
    if isinstance(card, dict):
        return card.get("id", card.get("cardId"))
    return card


def _hidden_signature(observation: dict, root_seat: int) -> str:
    """Identity of the determinized hidden state, independent of the action path used to reach it."""
    players = ((observation.get("current") or {}).get("players") or ())
    zones = []
    for seat, player in enumerate(players):
        player = player or {}
        names = ("deck", "prize") if seat == root_seat else ("deck", "prize", "hand")
        zones.append(tuple(
            (name, tuple(_hidden_card_identity(card) for card in (player.get(name) or ())))
            for name in names
        ))
    payload = repr(tuple(zones)).encode("utf-8")
    return hashlib.blake2b(
        payload, digest_size=HIDDEN_SIGNATURE_DIGEST_BYTES, person=b"bellman-hidden",
    ).hexdigest()


def _stratified_order(cards: tuple[int, ...], world_index: int, world_count: int) -> list[int]:
    """Low-discrepancy hidden-zone order, then one midpoint from each world stratum.

    A grouped-by-id order makes a one-world deployment treat arbitrary numeric ids as draw
    probability.  Space every identity's physical copies across the unit interval with a stable
    phase, then rotate worlds through equal-mass strata.  No Worth, role, function, effect, or card
    name enters the construction.
    """
    if not cards:
        return []
    counts = Counter(int(card_id) for card_id in cards)
    positioned = []
    for card_id, count in counts.items():
        digest = hashlib.blake2b(
            str(card_id).encode("ascii"), digest_size=PHASE_DIGEST_BYTES,
            person=b"bellman-zone",
        ).digest()
        phase = int.from_bytes(digest, "big") / PHASE_DENOMINATOR
        positioned.extend(
            ((copy_index + phase) / count, phase, card_id)
            for copy_index in range(count)
        )
    balanced = tuple(card_id for _position, _phase, card_id in sorted(positioned))
    worlds = max(1, int(world_count))
    index = int(world_index) % worlds
    offset = ((2 * index + 1) * len(balanced)) // (2 * worlds)
    return list(balanced[offset:] + balanced[:offset])


def _own_hidden_zones(root: DecisionState, player: dict, *, world_index: int,
                      world_count: int) -> tuple[tuple[int, ...], tuple[int, ...]]:
    deck_count = max(0, int(player.get("deckCount", 0)))
    prize_count = len(player.get("prize") or ())
    known_prizes = _expand(root.prize_counts)
    unknown_prize_count = max(0, prize_count - len(known_prizes))
    required = deck_count + unknown_prize_count
    remaining = tuple(_stratified_order(
        _expand(root.deck_counts), world_index, world_count))
    if len(remaining) < required:
        fallback = tuple(_stratified_order(root.deck, world_index, world_count))
        remaining = _fill(remaining, required, fallback)
    hidden_prizes = remaining[:unknown_prize_count]
    deck = _fill(remaining[unknown_prize_count:], deck_count, root.deck)
    prizes = _fill((*known_prizes, *hidden_prizes), prize_count, root.deck)
    return deck, prizes


def _actor_seat(observation: dict, root_seat: int) -> int:
    select = observation.get("select") or {}
    if int(select.get("context", -1)) == _MAIN:
        return root_seat
    seats = {int(option["playerIndex"]) for option in (select.get("option") or ())
             if option.get("playerIndex") is not None}
    if len(seats) == 1:
        return next(iter(seats))
    current = observation.get("current") or {}
    return int(current.get("yourIndex", root_seat))


class NativeCgTransitionProvider:
    """Fork the authoritative engine; enumerate and apply actions without ranking them."""

    backend = "native-cg-bellman"

    def __init__(self, root: DecisionState, *, registry=None, effects=None, stats=None,
                 api_module=None, world_count: int = NATIVE_BELIEF_WORLD_COUNT):
        self.root = root
        self.registry = registry
        self.effects = effects
        self.stats = stats
        self.world_count = max(1, int(world_count))
        self._worlds: dict[str, tuple[_NativeWorld, ...]] = {}
        self._root_turn = int((root.obs.get("current") or {}).get("turn", 0))
        self._error = ""
        self._api = api_module
        self._search_open = False
        try:
            if self._api is None:
                from cg import api
                self._api = api
            self._worlds[root.semantic_key] = self._begin_worlds(root)
        except Exception as exc:  # noqa: BLE001 - adapter failure is first-class
            self._error = f"{type(exc).__name__}: {exc}"

    @property
    def available(self) -> bool:
        return not self._error and bool(self._worlds.get(self.root.semantic_key))

    def close(self) -> None:
        if self._api is not None and self._search_open:
            self._api.search_end()
            self._search_open = False

    def actions(self, state: DecisionState) -> tuple[LegalAction, ...]:
        if state.semantic_key not in self._worlds:
            return ()
        return enumerate_legal_actions(state.obs)

    def actor(self, state: DecisionState) -> Actor:
        seat = int(state.obs.get("bellmanActor", state.root_seat))
        return Actor.OURS if seat == state.root_seat else Actor.OPPONENT

    def footprint(self, state: DecisionState, action: LegalAction):
        return action_footprint(state, action, effects=self.effects, stats=self.stats)

    def terminal_action_supported(self, state: DecisionState, action: LegalAction) -> bool:
        kind = action.identity.kind
        options = tuple((state.obs.get("select") or {}).get("option") or ())
        option_index = action.selection[0] if len(action.selection) == 1 else -1
        option = options[option_index] if 0 <= option_index < len(options) else {}
        current = state.obs.get("current") or {}
        players = current.get("players") or ()
        mine = players[state.root_seat] if state.root_seat < len(players) else {}
        card_id = played_card_id(state, action)
        if card_id is None and kind in {"attach", "evolve"}:
            hand_index = option.get("index")
            hand = mine.get("hand") or ()
            if isinstance(hand_index, int) and 0 <= hand_index < len(hand) and hand[hand_index]:
                card_id = int(hand[hand_index]["id"])
        if card_id is None and kind in {"ability", "skill"}:
            area = option.get("inPlayArea", option.get("area"))
            index = option.get("inPlayIndex", option.get("index"))
            cards = (mine.get("active") if area == _ACTIVE else
                     mine.get("bench") if area == _BENCH else
                     current.get("stadium") if area == 7 else ()) or ()
            if isinstance(index, int) and 0 <= index < len(cards) and cards[index]:
                card_id = int(cards[index]["id"])
        recipient_id = None
        if kind == "attach":
            area = option.get("inPlayArea")
            index = option.get("inPlayIndex")
            bodies = (mine.get("active") if area == _ACTIVE else
                      mine.get("bench") if area == _BENCH else ()) or ()
            body = bodies[index] if isinstance(index, int) and 0 <= index < len(bodies) else None
            recipient_id = int(body["id"]) if body and body.get("id") is not None else None
        return terminal_effects_supported(
            state, action, card_id=card_id, recipient_id=recipient_id,
            effects=self.effects, stats=self.stats)

    def transition(self, state: DecisionState, action: LegalAction):
        worlds = self._worlds.get(state.semantic_key)
        if not worlds:
            return Unknown("native search state unavailable", state.semantic_key)
        refresh = refresh_transition(state, action, self.effects)
        if refresh is not None:
            return refresh
        children = []
        forced_next_actor = 1 - state.root_seat if action.identity.kind == "end" else None
        try:
            for world in worlds:
                stepped = self._api.search_step(world.search_id, list(action.selection))
                committed = world.attack_committed or action.identity.kind == "attack"
                observation = self._observation(
                    stepped.observation, state, actor_seat=forced_next_actor)
                if int(((observation.get("select") or {}).get("context", -1))) == MANUAL_COIN_CONTEXT:
                    children.extend(self._coin_children(
                        stepped.searchId, world.probability, committed, state, observation,
                        actor_seat=forced_next_actor))
                else:
                    children.append((world.probability, stepped.searchId, committed, observation))
            return self._group_children(state, action, children)
        except Exception as exc:  # noqa: BLE001 - engine gap remains explicit
            return Unknown("native cg transition failed", f"{type(exc).__name__}: {exc}")

    def resolve_end(self, state: DecisionState, action: LegalAction):
        return self.transition(state, action) if end_has_forced_value_change(state, self.registry) else None

    def _begin_worlds(self, root: DecisionState) -> tuple[_NativeWorld, ...]:
        observation = root.obs
        current = observation.get("current") or {}
        players = current.get("players") or ()
        mine = players[root.root_seat] if len(players) > root.root_seat else {}
        opponent = players[1 - root.root_seat] if len(players) > 1 else {}
        opponent_deck = _fill((), int(opponent.get("deckCount", 0)), root.deck)
        opponent_prize = _fill((), len(opponent.get("prize") or ()), root.deck)
        opponent_hand = _fill((), int(opponent.get("handCount", 0)), root.deck)
        native_observation = self._api.to_observation_class(observation)
        worlds = []
        probability = PROBABILITY_TOTAL / self.world_count
        for index in range(self.world_count):
            own_deck, own_prize = _own_hidden_zones(
                root, mine, world_index=index, world_count=self.world_count)
            state = self._api.search_begin(
                native_observation,
                list(own_deck),
                list(own_prize),
                _stratified_order(opponent_deck, index, self.world_count),
                _stratified_order(opponent_prize, index, self.world_count),
                _stratified_order(opponent_hand, index, self.world_count),
                [], manual_coin=True,
            )
            self._search_open = True
            worlds.append(_NativeWorld(probability, int(state.searchId)))
        return tuple(worlds)

    def _observation(self, native_observation, parent: DecisionState, *, actor_seat=None) -> dict:
        observation = _plain_native(native_observation)
        observation["bellmanBeliefKey"] = _hidden_signature(observation, parent.root_seat)
        observation["bellmanActor"] = (_actor_seat(observation, parent.root_seat)
                                       if actor_seat is None else int(actor_seat))
        current = observation.get("current") or {}
        current["yourIndex"] = parent.root_seat
        players = current.get("players") or ()
        parent_players = (parent.obs.get("current") or {}).get("players") or ()
        if 0 <= parent.root_seat < len(players) and 0 <= parent.root_seat < len(parent_players):
            root_player = players[parent.root_seat] or {}
            parent_player = parent_players[parent.root_seat] or {}
            known_hand = parent_player.get("hand")
            if (root_player.get("hand") is None and isinstance(known_hand, list)
                    and len(known_hand) == int(root_player.get("handCount", -1))):
                root_player["hand"] = _plain_native(known_hand)
        for seat, player in enumerate(players):
            if not player:
                continue
            player["prize"] = [None] * len(player.get("prize") or ())
            if seat != parent.root_seat:
                player["hand"] = None
        if "own_prizes" in parent.obs:
            observation["own_prizes"] = parent.obs["own_prizes"]
        if "known_top" in parent.obs:
            observation["known_top"] = parent.obs["known_top"]
        return observation

    def _coin_children(self, search_id: int, probability: float, committed: bool,
                       parent: DecisionState, observation: dict, *, actor_seat=None):
        options = tuple((observation.get("select") or {}).get("option") or ())
        by_type = {int(option.get("type", -1)): index for index, option in enumerate(options)}
        if _YES not in by_type or _NO not in by_type:
            raise ValueError("manual coin menu lacks heads/tails choices")
        children = []
        for option_type in (_YES, _NO):
            stepped = self._api.search_step(search_id, [by_type[option_type]])
            observation = self._observation(
                stepped.observation, parent, actor_seat=actor_seat)
            children.append((probability * COIN_BRANCH_PROBABILITY,
                             int(stepped.searchId), committed, observation))
        return children

    def _group_children(self, parent: DecisionState, action: LegalAction, children):
        if len(children) == 1:
            probability, search_id, committed, observation = children[0]
            observation = dict(observation)
            successor = parent.with_observation(observation)
            successor_key = successor.semantic_key
            self._worlds[successor_key] = (
                _NativeWorld(PROBABILITY_TOTAL, int(search_id), bool(committed)),
            )
            return self._node(
                parent, successor,
                ((float(probability), int(search_id), bool(committed), observation),),
            )

        grouped: dict[str, list[tuple[float, int, bool, dict]]] = {}
        for probability, search_id, committed, observation in children:
            public = parent.with_observation(observation)
            group_key = public.semantic_key
            grouped.setdefault(group_key, []).append(
                (float(probability), int(search_id), bool(committed), observation))
        if not grouped:
            return Unknown("native cg returned no successor", str(action.identity))

        edges = []
        for index, (group_key, rows) in enumerate(sorted(grouped.items())):
            mass = sum(row[0] for row in rows)
            observation = dict(rows[0][3])
            successor = parent.with_observation(observation)
            successor_key = successor.semantic_key
            self._worlds[successor_key] = tuple(
                _NativeWorld(probability / mass, search_id, committed)
                for probability, search_id, committed, _observation in rows
            )
            node = self._node(parent, successor, rows)
            edges.append(WeightedEdge(mass, f"native outcome {index + 1}", node))

        total = sum(edge.probability for edge in edges)
        if total <= 0.0:
            return Unknown("native cg returned zero probability mass", str(action.identity))
        normalized = tuple(WeightedEdge(edge.probability / total, edge.label, edge.node)
                           for edge in edges)
        return normalized[0].node if len(normalized) == 1 else Chance(normalized)

    def _node(self, parent: DecisionState, successor: DecisionState, rows):
        current = successor.obs.get("current") or {}
        result = int(current.get("result", -1))
        if result != -1:
            return Terminal(successor, "win" if result == parent.root_seat else "loss")
        select = successor.obs.get("select") or {}
        committed = any(row[2] for row in rows)
        passed_turn = (committed
                       and int(current.get("turn", self._root_turn)) != self._root_turn
                       and int(select.get("context", -1)) == _MAIN)
        if passed_turn:
            return Terminal(successor, "attack resolved")
        return Deterministic(successor)


__all__ = ("NativeCgTransitionProvider",)
