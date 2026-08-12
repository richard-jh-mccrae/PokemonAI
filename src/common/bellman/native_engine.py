"""Native ``cg`` transition provider for the production Bellman planner."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from enum import IntEnum
from math import comb

from .algebra import Actor, Chance, Deterministic, Terminal, Unknown, WeightedEdge
from .information import BellmanDeckProfile, CausalNeeds, hypergeometric_classes
from .options import enumerate_legal_actions
from .value import WORTH_PER_PRIZE
from common.strategy.context import (
    _HEAL, _MAIN, _MOVE_CARD, _NO, _SUPPORTER, _YES,
)


MANUAL_COIN_CONTEXT = 46
HEAL_PREVIEW_BUDGET = 80
SEARCH_PREVIEW_BUDGET = 96
SEARCH_SEQUENCE_TAGS = frozenset({"search", "bench_fill"})
FULL_PRIZE_COUNT = 6
REFRESH_DRAW_WITH_FULL_PRIZES = 8
REFRESH_DRAW_AFTER_PRIZE = 6
COIN_HEADS_DRAW = 5
COIN_TAILS_DRAW = 3
COIN_BRANCH_PROBABILITY = 0.5
REVEAL_DEPTH = 7
AREA_PRIZE = 6
DRAW_RESULT_CODE = 2


def _expand(counts) -> list[int]:
    return [int(card_id) for card_id, count in counts for _ in range(int(count))]


def _take(cards, count: int) -> list[int]:
    cards = tuple(int(card_id) for card_id in cards)
    if not cards or count <= 0:
        return []
    copies = list(cards)
    while len(copies) < count:
        copies.extend(cards)
    return copies[:count]


def _plain(value):
    """Dataclass/enum observation -> the dict shape consumed everywhere else."""
    if isinstance(value, IntEnum):
        return int(value)
    if isinstance(value, dict):
        return {key: _plain(child) for key, child in value.items() if child is not None}
    if isinstance(value, list):
        return [_plain(child) for child in value]
    return value


class NativeTransitionProvider:
    """Fork the authoritative native engine; probability math only classifies hidden outcomes."""

    def __init__(self, root, *, registry=None, needs: CausalNeeds | None = None,
                 search_api=None, production_chance: bool = True):
        self.root = root
        self.registry = registry
        self.profile = BellmanDeckProfile.from_registry(registry) if registry else BellmanDeckProfile()
        self.needs = needs or CausalNeeds(profile=self.profile)
        self.production_chance = bool(production_chance)
        self._states = {}
        self._attack_committed = {}
        self._prizes = {}
        self._root_turn = int((root.obs.get("current") or {}).get("turn", 0))
        self._error = ""
        self._closed = False
        self._search_started = False
        self._card_types = None
        self._api = search_api
        try:
            if self._api is None:
                from cg import api
                self._api = api
            obs = root.obs
            current = obs.get("current") or {}
            players = current.get("players") or ()
            me = players[root.root_seat] if len(players) > root.root_seat else {}
            opp = players[1 - root.root_seat] if len(players) > 1 else {}
            own_deck = _expand(root.deck_counts)
            own_prize = _expand(root.prize_counts)
            prize_count = len(me.get("prize") or ())
            if len(own_prize) < prize_count:
                pool = _take(root.deck, prize_count + int(me.get("deckCount", 0)))
                own_prize = pool[:prize_count]
                own_deck = pool[prize_count:]
            own_deck = _take(own_deck or root.deck, int(me.get("deckCount", 0)))
            filler = tuple(root.deck)
            native = self._api.search_begin(
                self._api.to_observation_class(obs), own_deck, own_prize,
                _take(filler, int(opp.get("deckCount", 0))),
                _take(filler, len(opp.get("prize") or ())),
                _take(filler, int(opp.get("handCount", 0))), [], manual_coin=True,
            )
            self._search_started = True
            self._states[root.semantic_key] = native
            self._attack_committed[root.semantic_key] = False
            self._prizes[root.semantic_key] = Counter(own_prize)
        except Exception as exc:  # noqa: BLE001 - adapter gaps are first-class
            self._error = f"{type(exc).__name__}: {exc}"

    @property
    def available(self) -> bool:
        return not self._error

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._search_started:
            try:
                self._api.search_end()
            except Exception:  # noqa: BLE001 - cleanup must not hide the decision/result
                pass
        self._states.clear()
        self._attack_committed.clear()
        self._prizes.clear()

    def actions(self, state):
        if state.semantic_key not in self._states:
            return ()
        return enumerate_legal_actions(state.obs)

    def actor(self, state) -> Actor:
        seat = int((state.obs.get("current") or {}).get("yourIndex", state.root_seat))
        return Actor.OURS if seat == state.root_seat else Actor.OPPONENT

    def preview_checkpoint(self):
        return frozenset(self._states), frozenset(self._attack_committed), frozenset(self._prizes)

    def preview_restore(self, checkpoint) -> None:
        state_keys, attack_keys, prize_keys = checkpoint
        for key in tuple(self._states):
            if key in state_keys:
                continue
            native = self._states.pop(key)
            try:
                self._api.search_release(native.searchId)
            except Exception:  # noqa: BLE001 - the containing search remains valid
                pass
        for key in tuple(self._attack_committed):
            if key not in attack_keys:
                del self._attack_committed[key]
        for key in tuple(self._prizes):
            if key not in prize_keys:
                del self._prizes[key]

    @staticmethod
    def _played_card_id(state, action):
        if action.identity.kind != "play" or len(action.selection) != 1:
            return None
        select = state.obs.get("select") or {}
        options = select.get("option") or ()
        option_index = action.selection[0]
        if not 0 <= option_index < len(options):
            return None
        hand_index = options[option_index].get("index")
        players = (state.obs.get("current") or {}).get("players") or ()
        mine = players[state.root_seat] if len(players) > state.root_seat else {}
        hand = mine.get("hand") or ()
        if not isinstance(hand_index, int) or not 0 <= hand_index < len(hand):
            return None
        return int(hand[hand_index]["id"])

    def _tags(self, card_id) -> frozenset[str]:
        return frozenset((self.registry.functions.get(int(card_id), ())
                          if self.registry is not None and card_id is not None else ()))

    def _played_tags(self, state, action) -> frozenset[str]:
        return self._tags(self._played_card_id(state, action))

    def preview_node_budget(self, state, action, default: int) -> int:
        context = int(((state.obs.get("select") or {}).get("context", -1)))
        tags = self._played_tags(state, action)
        if context == _HEAL or "heal" in tags:
            return max(default, HEAL_PREVIEW_BUDGET)
        return max(default, SEARCH_PREVIEW_BUDGET) if tags.intersection(
            SEARCH_SEQUENCE_TAGS) else default

    def transition(self, state, action):
        native = self._states.get(state.semantic_key)
        if native is None:
            return Unknown("native engine state unavailable", self._error or state.semantic_key)
        try:
            card_id = self._played_card_id(state, action)
            child = self._api.search_step(native.searchId, list(action.selection))
            context = int(getattr(child.observation.select, "context", -1)
                          if child.observation.select is not None else -1)
            if context == MANUAL_COIN_CONTEXT:
                return self._coin_transition(state, child, action, card_id)
            node = self._register_successor(state, child, action)
            tags = self._tags(card_id)
            if ("shuffle_hand" in tags and "hand_disruption" not in tags
                    and isinstance(node, Deterministic)):
                players = (state.obs.get("current") or {}).get("players") or ()
                mine = players[state.root_seat] if len(players) > state.root_seat else {}
                hand = [int(card["id"]) for card in (mine.get("hand") or ())]
                hand.remove(card_id)
                pool = _expand(state.deck_counts) + hand
                draws = (REFRESH_DRAW_WITH_FULL_PRIZES
                         if len(mine.get("prize") or ()) == FULL_PRIZE_COUNT
                         else REFRESH_DRAW_AFTER_PRIZE)
                return Chance(self._draw_edges(state, node.state, pool, draws, "lillie"))
            if "dig" in tags and isinstance(node, Deterministic):
                return Chance(self._pokegear_edges(node.state, _expand(state.deck_counts)))
            return node
        except Exception as exc:  # noqa: BLE001 - engine gaps are explicit, never zero
            return Unknown("native cg transition failed", f"{type(exc).__name__}: {exc}")

    def _observation(self, state, child):
        observation = _plain(asdict(child.observation))
        prizes = Counter(self._prizes.get(state.semantic_key, ()))
        for log in observation.get("logs") or ():
            if (int(log.get("type", -1)) == _MOVE_CARD
                    and int(log.get("playerIndex", -1)) == state.root_seat
                    and int(log.get("fromArea", -1)) == AREA_PRIZE):
                card_id = int(log.get("cardId", 0))
                if prizes[card_id] > 0:
                    prizes[card_id] -= 1
                    if prizes[card_id] <= 0:
                        del prizes[card_id]
        observation["own_prizes"] = dict(prizes)
        return observation, prizes

    def _register_successor(self, state, child, action):
        observation, prizes = self._observation(state, child)
        successor = state.with_observation(observation)
        committed = (self._attack_committed.get(state.semantic_key, False)
                     or action.identity.kind == "attack")
        existing = self._states.get(successor.semantic_key)
        if existing is None:
            self._states[successor.semantic_key] = child
            self._attack_committed[successor.semantic_key] = committed
            self._prizes[successor.semantic_key] = prizes
        else:
            self._api.search_release(child.searchId)
        current = observation.get("current") or {}
        result = int(current.get("result", -1))
        if result != -1:
            label = "draw" if result == DRAW_RESULT_CODE else "win" if result == state.root_seat else "loss"
            return Terminal(successor, label)
        passed_turn = (committed and int(current.get("turn", self._root_turn)) != self._root_turn
                       and int(current.get("yourIndex", state.root_seat)) != state.root_seat
                       and int(((observation.get("select") or {}).get("context", -1))) == _MAIN)
        return Terminal(successor, "attack resolved") if passed_turn else Deterministic(successor)

    def _coin_transition(self, state, coin_state, action, card_id):
        options = coin_state.observation.select.option if coin_state.observation.select else ()
        edges = []
        for index, option in enumerate(options):
            option_type = int(option.type)
            if option_type not in (_YES, _NO):
                continue
            branch = self._api.search_step(coin_state.searchId, [index])
            node = self._register_successor(state, branch, action)
            label = "heads" if option_type == _YES else "tails"
            if "hand_disruption" in self._tags(card_id) and isinstance(node, Deterministic):
                players = (state.obs.get("current") or {}).get("players") or ()
                mine = players[state.root_seat] if len(players) > state.root_seat else {}
                hand = [int(card["id"]) for card in (mine.get("hand") or ())]
                hand.remove(card_id)
                pool = _expand(state.deck_counts) + hand
                draws = COIN_HEADS_DRAW if option_type == _YES else COIN_TAILS_DRAW
                for outcome in self._draw_edges(state, node.state, pool, draws, label):
                    edges.append(WeightedEdge(COIN_BRANCH_PROBABILITY * outcome.probability,
                                              outcome.label, outcome.node))
            else:
                edges.append(WeightedEdge(COIN_BRANCH_PROBABILITY, label, node))
        try:
            self._api.search_release(coin_state.searchId)
        except Exception:  # noqa: BLE001
            pass
        if not edges:
            return Unknown("manual coin menu malformed", repr(options))
        return Chance(tuple(edges))

    def _grouped_draws(self, state, pool, draws):
        counts = Counter(pool)
        needs = self.needs.derive(state.obs, deck_counts=counts)
        exact = hypergeometric_classes(pool, draws, needs)
        groups = {}
        for outcome in exact:
            key = tuple(bool(count) for count in outcome.counts)
            groups.setdefault(key, []).append(outcome)
        claimed = {card_id for need in needs for card_id in need.card_ids}
        means = []
        for need in needs:
            cards = [card_id for card_id in pool if card_id in need.card_ids]
            means.append(sum(self.registry.worth(card_id) for card_id in cards) / len(cards)
                         if self.registry and cards else 0.0)
        other = [card_id for card_id in pool if card_id not in claimed]
        other_mean = (sum(self.registry.worth(card_id) for card_id in other) / len(other)
                      if self.registry and other else 0.0)
        for presence, members in sorted(groups.items()):
            probability = sum(row.probability for row in members)
            expected_counts = [sum(row.probability * row.counts[i] for row in members) / probability
                               for i in range(len(needs))]
            expected_other = sum(row.probability * row.remainder for row in members) / probability
            portable = sum(mean * count for mean, count in zip(means, expected_counts))
            portable += other_mean * expected_other
            causal = sum(need.value_worth for need, present in zip(needs, presence) if present)
            label = ",".join(f"{need.key}={'present' if present else 'absent'}"
                             for need, present in zip(needs, presence)) or "draw"
            yield probability, label, portable + causal

    def _draw_edges(self, state, successor, pool, draws, prefix):
        rows = []
        for probability, label, benefit_worth in self._grouped_draws(state, pool, draws):
            adjusted = successor.with_adjustments(
                (("chance.hand", float(benefit_worth) / WORTH_PER_PRIZE),))
            rows.append(WeightedEdge(probability, f"{prefix}:{label}",
                                     Terminal(adjusted, "actual-state replan")))
        return tuple(rows)

    def _pokegear_edges(self, successor, pool):
        if not pool:
            return (WeightedEdge(1.0, "no-supporter", Terminal(
                successor.with_adjustments((("chance.hand", 0.0),)),
                "actual-state replan")),)
        if self._card_types is None:
            self._card_types = {
                int(card.cardId): int(card.cardType) for card in self._api.all_card_data()
            }
        supporter_ids = sorted({card_id for card_id in pool
                                if self._card_types.get(card_id) == _SUPPORTER},
                               key=lambda card_id: (self.registry.worth(card_id)
                                                    if self.registry else 0.0, -card_id),
                               reverse=True)
        draws, total = min(REVEAL_DEPTH, len(pool)), len(pool)
        denominator = comb(total, draws)
        counts, preceding, edges = Counter(pool), 0, []
        for card_id in supporter_ids:
            copies = counts[card_id]
            without_prior = comb(total - preceding, draws) if total - preceding >= draws else 0
            without_current = (comb(total - preceding - copies, draws)
                               if total - preceding - copies >= draws else 0)
            probability = (without_prior - without_current) / denominator
            preceding += copies
            if probability <= 0.0:
                continue
            benefit = (self.registry.worth(card_id) / WORTH_PER_PRIZE) if self.registry else 0.0
            adjusted = successor.with_adjustments((("chance.hand", benefit),))
            edges.append(WeightedEdge(probability, f"best-supporter:{card_id}",
                                      Terminal(adjusted, "actual-state replan")))
        non_supporters = [card_id for card_id in pool if card_id not in supporter_ids]
        none_probability = (comb(len(non_supporters), draws) / denominator
                            if len(non_supporters) >= draws else 0.0)
        if none_probability > 0.0:
            adjusted = successor.with_adjustments((("chance.hand", 0.0),))
            edges.append(WeightedEdge(none_probability, "no-supporter",
                                      Terminal(adjusted, "actual-state replan")))
        return tuple(edges)


__all__ = ("NativeTransitionProvider",)
