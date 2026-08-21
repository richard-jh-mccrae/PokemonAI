from __future__ import annotations

from .knowledge import KnownOwnPrizes
from .state import ObservationState, ObservationStateBuilder


class ProviderState:
    __slots__ = ("_provider_payload", "observation", "root_seat", "provider_token",
                 "actor_seat", "belief_token", "recycled_card_ids", "deck", "deck_counts",
                 "prize_counts")

    def __init__(self, payload: dict, observation: ObservationState, *, token: str,
                 actor_seat: int | None = None, belief_token: str | None = None,
                 recycled_card_ids=(),
                 deck=(), deck_counts=(), prize_counts=()):
        self._provider_payload = payload
        self.observation = observation
        self.root_seat = observation.seat
        self.provider_token = str(token)
        self.actor_seat = observation.seat if actor_seat is None else int(actor_seat)
        self.belief_token = belief_token
        self.recycled_card_ids = tuple(int(card_id) for card_id in recycled_card_ids)
        self.deck = tuple(deck)
        self.deck_counts = tuple(deck_counts)
        self.prize_counts = tuple(prize_counts)

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


def provider_payload(state) -> dict:
    payload = getattr(state, "_provider_payload", None)
    if payload is not None:
        return payload
    return state.provider_payload


__all__ = ("ProviderState",)
