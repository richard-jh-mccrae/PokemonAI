"""Neutral cgpy transition provider for Bellman search."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace

from .algebra import Actor, Chance, Deterministic, Terminal, Unknown, WeightedEdge
from .information import CausalNeeds, Need, OutcomeRng, hypergeometric_classes
from .options import LegalAction, enumerate_legal_actions
from .state import DecisionState


def _expand(counts) -> list[int]:
    return [int(card_id) for card_id, count in counts for _ in range(int(count))]


def _take(cards: tuple[int, ...], count: int) -> list[int]:
    if not cards:
        return []
    copies = list(cards)
    while len(copies) < count:
        copies.extend(cards)
    return copies[:count]


def _own_prize_export(engine, seat: int) -> dict[int, int]:
    board = engine.gs.players[seat]
    return dict(Counter(engine.gs.card_id(serial) for serial in board.prize))


class CgpyTransitionProvider:
    """Forkable full-rules engine adapter.  It enumerates and applies; it never ranks."""

    def __init__(self, root: DecisionState, *, registry=None, needs: CausalNeeds | None = None):
        self.root = root
        self.registry = registry
        self.needs = needs or CausalNeeds()
        self._engines: dict[str, object] = {}
        self._attack_committed: dict[str, bool] = {}
        self._root_turn = int((root.obs.get("current") or {}).get("turn", 0))
        self._error = ""
        try:
            from cgpy.rng import SeededRng
            from cgpy.search import state_from_obs

            obs = root.obs
            current = obs.get("current") or {}
            players = current.get("players") or ()
            me = players[root.root_seat] if len(players) > root.root_seat else {}
            opp = players[1 - root.root_seat] if len(players) > 1 else {}
            own_deck = _expand(root.deck_counts)
            own_prize = _expand(root.prize_counts)
            if len(own_prize) < len(me.get("prize") or ()):
                pool = _take(root.deck, len(me.get("prize") or ()) + int(me.get("deckCount", 0)))
                own_prize = pool[:len(me.get("prize") or ())]
                own_deck = pool[len(own_prize):]
            own_deck = _take(tuple(own_deck or root.deck), int(me.get("deckCount", 0)))
            filler = tuple(root.deck)
            engine = state_from_obs(
                obs, own_deck, own_prize,
                _take(filler, int(opp.get("deckCount", 0))),
                _take(filler, len(opp.get("prize") or ())),
                _take(filler, int(opp.get("handCount", 0))), [],
                manual_coin=True, rng=SeededRng(0),
            )
            self._engines[root.semantic_key] = engine
            self._attack_committed[root.semantic_key] = False
        except Exception as exc:  # noqa: BLE001 - becomes first-class Unknown
            self._error = f"{type(exc).__name__}: {exc}"

    @property
    def available(self) -> bool:
        return not self._error

    def actions(self, state: DecisionState) -> tuple[LegalAction, ...]:
        if state.semantic_key not in self._engines:
            return ()
        return enumerate_legal_actions(state.obs)

    def actor(self, state: DecisionState) -> Actor:
        engine = self._engines.get(state.semantic_key)
        if engine is None:
            return Actor.OURS
        return Actor.OURS if engine.select_seat == state.root_seat else Actor.OPPONENT

    def transition(self, state: DecisionState, action: LegalAction):
        engine = self._engines.get(state.semantic_key)
        if engine is None:
            return Unknown("engine state unavailable", self._error or state.semantic_key)
        try:
            information = self._information_transition(state, engine, action)
            if information is not None:
                return information
            child = engine.fork()
            child.step(list(action.selection))
            if child.gs.pending is not None and int(child.gs.pending.context) == 46:
                return self._coin_transition(state, child, action)
            return self._register_successor(state, child, action)
        except Exception as exc:  # noqa: BLE001 - an engine gap is explicit
            return Unknown("cgpy transition failed", f"{type(exc).__name__}: {exc}")

    def _state_from_engine(self, state, child, *, adjustments=()):
        observation = child.observation(viewer=state.root_seat, sbi_token="cgpy")
        observation["own_prizes"] = _own_prize_export(child, state.root_seat)
        return state.with_observation(observation).with_adjustments(adjustments)

    def _register_successor(self, state, child, action, *, adjustments=()):
        try:
            successor = self._state_from_engine(state, child, adjustments=adjustments)
            committed = self._attack_committed.get(state.semantic_key, False) or \
                action.identity.kind == "attack"
            self._engines[successor.semantic_key] = child
            self._attack_committed[successor.semantic_key] = committed
            if child.result != -1:
                result = "win" if child.result == state.root_seat else "loss"
                return Terminal(successor, result)
            pending = child.gs.pending
            passed_turn = (pending is not None and pending.seat != state.root_seat
                           and int(child.gs.turn) != self._root_turn
                           and int(pending.context) == 0)
            if committed and passed_turn:
                return Terminal(successor, "attack resolved")
            return Deterministic(successor)
        except Exception as exc:  # noqa: BLE001 - an engine gap is explicit
            return Unknown("cgpy transition failed", f"{type(exc).__name__}: {exc}")

    def _coin_transition(self, state, child, action):
        source_id = None
        if child.gs.frames:
            source_id = child.gs.card_id(child.gs.frames[-1].source)
        if source_id == 1223:
            return self._harlequin_coin_transition(state, child, action)
        edges = []
        for index, option in enumerate(child.gs.pending.options):
            if int(option.get("type", -1)) not in (1, 2):
                continue
            branch = child.fork()
            branch.step([index])
            node = self._register_successor(state, branch, action)
            label = "heads" if int(option.get("type")) == 1 else "tails"
            edges.append(WeightedEdge(0.5, label, node))
        if len(edges) != 2:
            return Unknown("manual coin menu malformed", repr(child.gs.pending.options))
        return Chance(tuple(edges))

    @staticmethod
    def _force_top_ids(engine, seat, draw_ids):
        deck = engine.gs.players[seat].deck
        remaining, chosen = list(deck), []
        for card_id in draw_ids:
            serial = next((serial for serial in remaining
                           if engine.gs.card_id(serial) == card_id), None)
            if serial is None:
                raise ValueError(f"requested unavailable top card {card_id}")
            remaining.remove(serial)
            chosen.append(serial)
        deck[:] = remaining + list(reversed(chosen))

    def _harlequin_coin_transition(self, state, child, action):
        pool_ids = [child.gs.card_id(serial)
                    for serial in child.gs.players[state.root_seat].deck]
        counts = Counter(pool_ids)
        needs = self.needs.derive(state.obs, deck_counts=counts)
        edges = []
        for index, option in enumerate(child.gs.pending.options):
            option_type = int(option.get("type", -1))
            if option_type not in (1, 2):
                continue
            draws = 5 if option_type == 1 else 3
            for outcome in hypergeometric_classes(pool_ids, draws, needs):
                draw_ids, adjustment = self._representative_ids(
                    pool_ids, needs, outcome, self.registry)
                branch = child.fork()
                self._force_top_ids(branch, state.root_seat, draw_ids)
                branch.step([index])
                node = self._register_successor(
                    state, branch, action, adjustments=(("chance.hand", adjustment),))
                label = ("heads" if option_type == 1 else "tails") + ":" + outcome.label
                edges.append(WeightedEdge(0.5 * outcome.probability, label, node))
        if not edges:
            return Unknown("Harlequin coin menu malformed", repr(child.gs.pending.options))
        return Chance(tuple(edges))

    def _played_card_id(self, engine, action):
        if action.identity.kind != "play" or len(action.selection) != 1:
            return None, None
        option = engine.gs.pending.options[action.selection[0]]
        index = option.get("index")
        hand = engine.gs.players[self.root.root_seat].hand
        if not isinstance(index, int) or not 0 <= index < len(hand):
            return None, None
        serial = hand[index]
        return engine.gs.card_id(serial), serial

    @staticmethod
    def _representative_ids(pool, needs, outcome, registry):
        remaining = list(pool)
        selected = []
        claimed = set()
        expected_worth = 0.0
        for need, count in zip(needs, outcome.counts):
            eligible = [card_id for card_id in remaining
                        if card_id in need.card_ids and card_id not in claimed]
            claimed.update(need.card_ids)
            if count:
                chosen = eligible[:count]
                for card_id in chosen:
                    remaining.remove(card_id)
                selected.extend(chosen)
                mean = (sum(registry.worth(card_id) for card_id in eligible) / len(eligible)
                        if registry and eligible else 0.0)
                expected_worth += mean * count
        complement = [card_id for card_id in remaining if card_id not in claimed]
        mean = (sum(registry.worth(card_id) for card_id in complement) / len(complement)
                if registry and complement else 0.0)
        if registry:
            ordered = sorted(complement, key=lambda card_id: (abs(registry.worth(card_id) - mean),
                                                               card_id))
        else:
            ordered = sorted(complement)
        chosen_other = ordered[:outcome.remainder]
        selected.extend(chosen_other)
        expected_worth += mean * outcome.remainder
        actual = sum(registry.worth(card_id) for card_id in selected) if registry else 0.0
        return selected, (expected_worth - actual) / 120.0

    def _information_transition(self, state, engine, action):
        card_id, source = self._played_card_id(engine, action)
        if card_id == 1122:
            return self._pokegear_transition(state, engine, action)
        if card_id != 1227:
            return None
        board = engine.gs.players[state.root_seat]
        pool_serials = list(board.deck) + [serial for serial in board.hand if serial != source]
        pool_ids = [engine.gs.card_id(serial) for serial in pool_serials]
        draws = 8 if len(board.prize) == 6 else 6
        counts = Counter(pool_ids)
        needs = self.needs.derive(state.obs, deck_counts=counts)
        outcomes = hypergeometric_classes(pool_ids, draws, needs)
        edges = []
        serial_to_card = {serial: engine.gs.card_id(serial) for serial in engine.gs.cards}
        for outcome in outcomes:
            draw_ids, adjustment = self._representative_ids(pool_ids, needs, outcome, self.registry)
            branch = engine.fork()
            branch.gs.rng = OutcomeRng(seat=state.root_seat, serial_to_card=serial_to_card,
                                       draw_ids=draw_ids)
            branch.step(list(action.selection))
            node = self._register_successor(
                state, branch, action, adjustments=(("chance.hand", adjustment),))
            edges.append(WeightedEdge(outcome.probability, outcome.label, node))
        return Chance(tuple(edges))

    def _pokegear_transition(self, state, engine, action):
        board = engine.gs.players[state.root_seat]
        pool_ids = [engine.gs.card_id(serial) for serial in board.deck]
        supporter_ids = sorted({engine.gs.card_id(serial) for serial in board.deck
                                if int(engine.gs.stat(serial).cardType) == 3})
        needs = tuple(Need(f"supporter:{card_id}", (card_id,),
                           self.registry.worth(card_id) if self.registry else 0.0,
                           "Pokégear reveal identity changes the reachable Supporter continuation")
                      for card_id in supporter_ids)
        outcomes = hypergeometric_classes(pool_ids, min(7, len(pool_ids)), needs)
        edges = []
        for outcome in outcomes:
            top_ids, _adjustment = self._representative_ids(pool_ids, needs, outcome, self.registry)
            branch = engine.fork()
            self._force_top_ids(branch, state.root_seat, top_ids)
            branch.step(list(action.selection))
            node = self._register_successor(state, branch, action)
            edges.append(WeightedEdge(outcome.probability, outcome.label, node))
        return Chance(tuple(edges))


__all__ = ("CgpyTransitionProvider",)
