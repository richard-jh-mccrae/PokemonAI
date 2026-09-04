from __future__ import annotations

from .knowledge import KnownOwnPrizes
from .state import ObservationState, ObservationStateBuilder


class ProviderState:
    __slots__ = ("_provider_payload", "observation", "root_seat", "provider_token",
                 "_actor_seat", "belief_token", "recycled_card_ids", "deck", "deck_counts",
                 "prize_counts", "control")

    def __init__(self, payload: dict, observation: ObservationState, *, token: str,
                 actor_seat: int | None = None, belief_token: str | None = None,
                 recycled_card_ids=(), control=None,
                 deck=(), deck_counts=(), prize_counts=()):
        self._provider_payload = payload
        self.observation = observation
        self.root_seat = observation.seat
        self.provider_token = str(token)
        self._actor_seat = observation.seat if actor_seat is None else int(actor_seat)
        self.belief_token = belief_token
        self.recycled_card_ids = tuple(int(card_id) for card_id in recycled_card_ids)
        self.deck = tuple(deck)
        self.deck_counts = tuple(deck_counts)
        self.prize_counts = tuple(prize_counts)
        self.control = control

    @property
    def actor_seat(self):
        if self.control is not None and self.control.actor_seat is not None:
            return self.control.actor_seat
        return self._actor_seat

    @property
    def legal_actions(self) -> tuple:
        return self.observation.legal_actions

    @property
    def semantic_key(self) -> str:
        return self.observation.decision_key

    def with_observation(self, payload: dict) -> "ProviderState":
        state, _delta = ObservationStateBuilder(self.observation.decklist).advance(
            self.observation, payload)
        return type(self)(payload, state, token=state.decision_key, actor_seat=self.actor_seat,
                          belief_token=self.belief_token, deck=self.deck,
                          recycled_card_ids=self.recycled_card_ids,
                          deck_counts=state.deck_counts or (),
                          prize_counts=(state.knowledge.own_prizes.cards
                                        if isinstance(state.knowledge.own_prizes,
                                                      KnownOwnPrizes) else ()))


class ProviderBinding:
    def _bind(self, state, observation):
        successor = state.with_observation(observation)
        metadata = getattr(self, "_provider_metadata", {}).pop(id(observation), {})
        control = metadata.get("control")
        if isinstance(successor, ProviderState):
            successor.control = control
        elif control is not None:
            self._legacy_controls = getattr(self, "_legacy_controls", {})
            self._legacy_controls[self._key(successor)] = control
        return successor

    def control(self, state):
        if isinstance(state, ProviderState):
            return state.control
        return getattr(self, "_legacy_controls", {}).get(self._key(state))


def provider_payload(state) -> dict:
    payload = getattr(state, "_provider_payload", None)
    if payload is not None:
        return payload
    return state.provider_payload


__all__ = ("ProviderState",)
