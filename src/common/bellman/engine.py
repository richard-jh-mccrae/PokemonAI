"""Neutral cgpy transition provider for Bellman search."""
from __future__ import annotations

from collections import Counter
from dataclasses import replace

from .algebra import Actor, Deterministic, Terminal, Unknown
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

    def __init__(self, root: DecisionState):
        self.root = root
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
            child = engine.fork()
            child.step(list(action.selection))
            observation = child.observation(viewer=state.root_seat, sbi_token="cgpy")
            observation["own_prizes"] = _own_prize_export(child, state.root_seat)
            successor = state.with_observation(observation)
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


__all__ = ("CgpyTransitionProvider",)
