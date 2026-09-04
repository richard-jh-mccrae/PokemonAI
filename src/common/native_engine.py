"""Native ``cg`` transition provider: fork the engine, enumerate, apply — never rank."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, fields, is_dataclass
import hashlib

from .algebra import Actor, Chance, Deterministic, Terminal, Unknown, WeightedEdge
from .cards import card_store
from .options import LegalAction, recycled_card_ids
from .refresh import refresh_transition
from .observation.provider import provider_payload as _payload
from common.strategy.context import _MAIN, _NO, _YES


# Deployment budgets one authoritative native world. Extra injectable diagnostic worlds would
# multiply a full-turn search into minutes per decision.
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


def _known_prize_cards(parent, remaining_prizes, count: int) -> list[dict]:
    known = Counter({int(card_id): int(copies)
                     for card_id, copies in getattr(parent, "prize_counts", ())})
    remaining = Counter(
        int(card_id) for card in remaining_prizes
        if (card_id := _hidden_card_identity(card)) is not None)
    taken = known - remaining
    return [{"id": card_id} for card_id in sorted(taken.elements())[:count]]


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
    """Build a low-discrepancy hidden-zone order and select one midpoint per world stratum.
    Stable phases spread physical copies without using Worth, roles, effects, or card names."""
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


def _seeded_order(cards: tuple[int, ...], token: str, world_index: int) -> tuple[int, ...]:
    """Permute physical positions reproducibly without reading their card identities."""
    ranked = sorted(
        range(len(cards)),
        key=lambda index: hashlib.blake2b(
            f"{token}:{world_index}:{index}".encode("utf-8"),
            digest_size=PHASE_DIGEST_BYTES, person=b"puct-draw",
        ).digest())
    return tuple(cards[index] for index in ranked)


def _own_hidden_zones(root, player: dict, *, world_index: int,
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

    def __init__(self, root, *, registry=None, effects=None, stats=None,
                 api_module=None, world_count: int = NATIVE_BELIEF_WORLD_COUNT, cards=None,
                 analytic_refresh: bool = True, hidden_order_token: str | None = None):
        self.root = root
        self.registry = registry
        self.effects = effects
        self.stats = stats
        #: Card records by id — the unified store unless a test injects its own records.
        self.cards = card_store() if cards is None else cards
        self.world_count = max(1, int(world_count))
        self.analytic_refresh = bool(analytic_refresh)
        self.hidden_order_token = hidden_order_token
        self._worlds: dict[str, tuple[_NativeWorld, ...]] = {}
        self._provider_metadata: dict[int, dict] = {}
        self._root_turn = int((_payload(root).get("current") or {}).get("turn") or 0)
        self._error = ""
        self._api = api_module
        self._search_open = False
        try:
            if self._api is None:
                from cg import api
                self._api = api
            self._worlds[self._key(root)] = self._begin_worlds(root)
        except Exception as exc:  # noqa: BLE001 - adapter failure is first-class
            self._error = f"{type(exc).__name__}: {exc}"

    @property
    def available(self) -> bool:
        return not self._error and bool(self._worlds.get(self._key(self.root)))

    @property
    def retained_states(self) -> int:
        return sum(len(worlds) for worlds in self._worlds.values())

    def close(self) -> None:
        if self._api is not None and self._search_open:
            self._api.search_end()
            self._search_open = False

    def _bind(self, state, observation):
        """Successor state construction — the Ledger preview seam overrides this to skip the
        DecisionState build per node (ADR-0146)."""
        return state.with_observation(observation)

    def _key(self, state) -> str:
        """The world-map key for a state; the preview seam substitutes identity tokens."""
        return state.semantic_key

    def actions(self, state) -> tuple[LegalAction, ...]:
        if self._key(state) not in self._worlds:
            return ()
        return state.legal_actions

    def actor(self, state) -> Actor:
        seat = int(getattr(state, "actor_seat", state.root_seat))
        return Actor.OURS if seat == state.root_seat else Actor.OPPONENT

    def transition(self, state, action: LegalAction):
        worlds = self._worlds.get(self._key(state))
        if not worlds:
            return Unknown("native search state unavailable", self._key(state))
        refresh = refresh_transition(state, action, self.cards) if self.analytic_refresh else None
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
                recycled = recycled_card_ids(
                    _payload(state), action, self.registry, state.root_seat,
                    carried=getattr(state, "recycled_card_ids", ()),
                    actor_seat=getattr(state, "actor_seat", state.root_seat))
                self._provider_metadata.setdefault(id(observation), {})[
                    "recycled_card_ids"] = recycled
                if int(((observation.get("select") or {}).get("context", -1))) == MANUAL_COIN_CONTEXT:
                    children.extend(self._coin_children(
                        stepped.searchId, world.probability, committed, state, observation,
                        actor_seat=forced_next_actor))
                else:
                    children.append((world.probability, stepped.searchId, committed, observation))
            return self._group_children(state, action, children)
        except Exception as exc:  # noqa: BLE001 - engine gap remains explicit
            return Unknown("native cg transition failed", f"{type(exc).__name__}: {exc}")

    def _begin_worlds(self, root) -> tuple[_NativeWorld, ...]:
        observation = _payload(root)
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
            if self.hidden_order_token is not None:
                own_deck = _seeded_order(own_deck, self.hidden_order_token, index)
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

    def _observation(self, native_observation, parent, *, actor_seat=None) -> dict:
        observation = _plain_native(native_observation)
        actor = (_actor_seat(observation, parent.root_seat)
                 if actor_seat is None else int(actor_seat))
        if not hasattr(self, "_provider_metadata"):
            self._provider_metadata = {}
        self._provider_metadata[id(observation)] = {
            "belief_token": _hidden_signature(observation, parent.root_seat),
            "actor_seat": actor,
        }
        current = observation.get("current") or {}
        current["yourIndex"] = parent.root_seat
        players = current.get("players") or ()
        parent_players = (_payload(parent).get("current") or {}).get("players") or ()
        if 0 <= parent.root_seat < len(players) and 0 <= parent.root_seat < len(parent_players):
            root_player = players[parent.root_seat] or {}
            parent_player = parent_players[parent.root_seat] or {}
            known_hand = parent_player.get("hand")
            hand_count = int(root_player.get("handCount", -1))
            native_hand = root_player.get("hand")
            hidden_hand = native_hand is None or (
                isinstance(native_hand, list) and not native_hand and hand_count > 0)
            if hidden_hand and isinstance(known_hand, list) and len(known_hand) <= hand_count:
                restored = _plain_native(known_hand)
                missing = hand_count - len(restored)
                if missing:
                    restored.extend(_known_prize_cards(
                        parent, root_player.get("prize") or (), missing))
                if len(restored) == hand_count:
                    root_player["hand"] = restored
        for seat, player in enumerate(players):
            if not player:
                continue
            player["prize"] = [None] * len(player.get("prize") or ())
            if seat != parent.root_seat:
                player["hand"] = None
        return observation

    def _coin_children(self, search_id: int, probability: float, committed: bool,
                       parent, observation: dict, *, actor_seat=None):
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

    def _group_children(self, parent, action: LegalAction, children):
        if len(children) == 1:
            probability, search_id, committed, observation = children[0]
            successor = self._bind(parent, observation)
            successor_key = self._key(successor)
            self._worlds[successor_key] = (
                _NativeWorld(PROBABILITY_TOTAL, int(search_id), bool(committed)),
            )
            return self._node(
                parent, successor,
                ((float(probability), int(search_id), bool(committed), observation),),
            )

        # Grouping merges worlds whose PUBLIC successor is identical. Under the preview seam's
        # identity keys nothing merges — each world keeps its own edge, same expected value.
        grouped: dict[str, list[tuple[float, int, bool, dict, object]]] = {}
        for probability, search_id, committed, observation in children:
            public = self._bind(parent, observation)
            group_key = self._key(public)
            grouped.setdefault(group_key, []).append(
                (float(probability), int(search_id), bool(committed), observation, public))
        if not grouped:
            return Unknown("native cg returned no successor", str(action.identity))

        edges = []
        for index, (group_key, rows) in enumerate(sorted(grouped.items())):
            mass = sum(row[0] for row in rows)
            successor = rows[0][4]
            successor_key = self._key(successor)
            self._worlds[successor_key] = tuple(
                _NativeWorld(probability / mass, search_id, committed)
                for probability, search_id, committed, _observation, _successor in rows
            )
            node = self._node(parent, successor, rows)
            edges.append(WeightedEdge(mass, f"native outcome {index + 1}", node))

        total = sum(edge.probability for edge in edges)
        if total <= 0.0:
            return Unknown("native cg returned zero probability mass", str(action.identity))
        normalized = tuple(WeightedEdge(edge.probability / total, edge.label, edge.node)
                           for edge in edges)
        return normalized[0].node if len(normalized) == 1 else Chance(normalized)

    def _node(self, parent, successor, rows):
        current = _payload(successor).get("current") or {}
        result = int(current.get("result", -1))
        if result != -1:
            return Terminal(successor, "win" if result == parent.root_seat else "loss")
        select = _payload(successor).get("select") or {}
        committed = any(row[2] for row in rows)
        passed_turn = (committed
                       and int(current.get("turn", self._root_turn)) != self._root_turn
                       and int(select.get("context", -1)) == _MAIN)
        if passed_turn:
            return Terminal(successor, "attack resolved")
        return Deterministic(successor)


__all__ = ("NativeCgTransitionProvider",)
