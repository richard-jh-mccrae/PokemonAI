from __future__ import annotations

from types import SimpleNamespace

import pytest

from common import DecisionState, Refresh
from common.effects import CardEffects
from common.native_engine import NativeCgTransitionProvider, _NativeWorld
from common.options import enumerate_legal_actions
from common.refresh import RefreshEvaluator
from common.scouting.provider import CardStat, DictCardStatProvider
from common.value import KNOWN_CARD_FLOOR, CardFacts, Potential, ValueRegistry


REFRESH_CARD = 900
LINE_BASE = 901
LINE_TOP = 902
POKEMON_TUTOR = 903
FILLER = 904
PLAY_OPTION_TYPE = 7
MAIN_CONTEXT = 0


def _potential(observation):
    players = ((observation.get("current") or {}).get("players") or ())
    mine = players[0] if players else {}
    evolved = any(body and int(body.get("id", 0)) == LINE_TOP
                  for body in tuple(mine.get("active") or ()) + tuple(mine.get("bench") or ()))
    hand_value = sum(0.2 for card in (mine.get("hand") or ())
                     if card and int(card.get("id", 0)) == LINE_TOP)
    families = (("board", 1.0 if evolved else 0.0), ("hand", hand_value))
    return Potential(sum(value for _name, value in families), families)


def _observation(hand, *, deck_count=10):
    return {
        "current": {
            "yourIndex": 0, "turn": 2, "supporterPlayed": False,
            "energyAttached": True, "retreated": False, "stadiumPlayed": False,
            "players": [
                {"hand": [{"id": card_id, "serial": 10 + index, "playerIndex": 0}
                          for index, card_id in enumerate(hand)],
                 "handCount": len(hand), "discard": [], "active": [],
                 "bench": [{"id": LINE_BASE, "serial": 20, "playerIndex": 0,
                            "hp": 60, "maxHp": 60, "appearThisTurn": False,
                            "preEvolution": [], "energies": [], "energyCards": [], "tools": []}],
                 "benchMax": 5, "prize": [None] * 6, "deckCount": deck_count},
                {"hand": None, "handCount": 0, "discard": [], "active": [], "bench": [],
                 "prize": [None] * 6, "deckCount": 10},
            ],
        },
        "select": {"context": MAIN_CONTEXT, "minCount": 1, "maxCount": 1,
                   "option": [{"type": PLAY_OPTION_TYPE, "index": 0, "playerIndex": None}]},
    }


def _registry(deck):
    return ValueRegistry(
        roles={LINE_BASE: ("primary_attacker",), LINE_TOP: ("primary_attacker",)},
        functions={REFRESH_CARD: ("draw", "shuffle_hand"),
                   POKEMON_TUTOR: ("search", "tutor_pokemon")},
        facts={card_id: CardFacts(pokemon=card_id in (LINE_BASE, LINE_TOP),
                                  stage=("basic" if card_id == LINE_BASE else
                                         "stage1" if card_id == LINE_TOP else None))
               for card_id in set(deck)},
        lines=((LINE_BASE, LINE_TOP),), line_pairs=((LINE_BASE, LINE_TOP),),
    )


def _stats():
    return DictCardStatProvider({
        REFRESH_CARD: CardStat(REFRESH_CARD, cardType=3),
        LINE_BASE: CardStat(LINE_BASE, hp=60, stage="basic"),
        LINE_TOP: CardStat(LINE_TOP, hp=330, stage="stage1", evolvesFrom="Base"),
        POKEMON_TUTOR: CardStat(POKEMON_TUTOR, cardType=1),
        FILLER: CardStat(FILLER, cardType=1),
    })


def _state(deck, hand=(REFRESH_CARD,)):
    registry = _registry(deck)
    return DecisionState.from_observation(
        _observation(hand), deck=deck, deck_name="test",
        value_registry_identity=registry.identity), registry


def test_native_refresh_transition_never_steps_a_hypothetical_draw_world():
    deck = (REFRESH_CARD, LINE_BASE, *(FILLER for _ in range(10)))
    state, registry = _state(deck)
    action = enumerate_legal_actions(state.obs)[0]

    class Api:
        calls = 0

        @classmethod
        def search_step(cls, *_args, **_kwargs):
            cls.calls += 1
            raise AssertionError("refresh valuation must not step the native engine")

    provider = object.__new__(NativeCgTransitionProvider)
    provider.effects = CardEffects({REFRESH_CARD: [{
        "kind": "draw", "amount": 6, "rider": "shuffle_own_hand_in",
    }]})
    provider._worlds = {state.semantic_key: (_NativeWorld(1.0, 77),)}
    provider._api = Api

    result = provider.transition(state, action)

    assert isinstance(result, Refresh)
    assert result.draws == ((6, 0),)
    assert Api.calls == 0
    assert not hasattr(result, "state")


def test_refresh_reports_exact_draw_odds_without_adding_them_to_bellman_utility():
    hidden = (LINE_TOP, LINE_TOP, POKEMON_TUTOR, POKEMON_TUTOR, *(FILLER for _ in range(6)))
    deck = (REFRESH_CARD, LINE_BASE, *hidden)
    state, registry = _state(deck)
    evaluator = RefreshEvaluator(
        registry, _potential,
        effects=CardEffects({POKEMON_TUTOR: [{
            "kind": "fetch", "target": "pokemon", "zone": "deck",
        }]}),
        stats=_stats(),
    )

    ledger, branches = evaluator.evaluate(state, Refresh(REFRESH_CARD, ((2, 0),), False))

    assert dict(ledger.benefits)["refresh_expected_hand"] == pytest.approx(0.08)
    assert "refresh_board_access" not in dict(ledger.benefits)
    assert branches[0]["board_access_value"] > 0.0
    assert branches[0]["expected_hand_value"] == pytest.approx(0.08)
    assert branches[0]["hand_value_deviation"] > 0.08
    assert not any("demand" in key for key in (*dict(ledger.benefits), *dict(ledger.costs)))


def test_returned_cards_join_the_exact_refresh_draw_pool():
    deck = (REFRESH_CARD, LINE_BASE, FILLER)
    state, registry = _state(deck)
    evaluator = RefreshEvaluator(registry, _potential, effects=CardEffects({}), stats=_stats())

    value, deviation = evaluator._draw_value_moments(state, (LINE_TOP,), 1)

    assert value == pytest.approx(0.1)
    assert deviation == pytest.approx(0.1)


def test_refresh_reports_a_guaranteed_held_demand_without_charging_bellman_utility():
    hidden = (LINE_TOP, LINE_TOP, *(FILLER for _ in range(8)))
    deck = (REFRESH_CARD, LINE_BASE, LINE_TOP, *hidden)
    state, registry = _state(deck, hand=(REFRESH_CARD, LINE_TOP))
    evaluator = RefreshEvaluator(
        registry, _potential, effects=CardEffects({}), stats=_stats())

    ledger, branches = evaluator.evaluate(state, Refresh(REFRESH_CARD, ((6, 0),), False))

    assert "refresh_held_demand" not in dict(ledger.costs)
    assert dict(ledger.costs)["refresh_held_options"] == pytest.approx(0.2)
    assert "expected_hand_value" in branches[0]


def test_refresh_charges_every_consumed_hand_card_including_the_played_card():
    deck = (REFRESH_CARD, FILLER, *(FILLER for _ in range(10)))
    state, registry = _state(deck, hand=(REFRESH_CARD, FILLER))

    def hand_potential(observation):
        hand = observation["current"]["players"][0].get("hand") or ()
        value = 0.2 * len(hand)
        return Potential(value, (("hand", value),))

    evaluator = RefreshEvaluator(
        registry, hand_potential, effects=CardEffects({}), stats=_stats())

    ledger, _branches = evaluator.evaluate(
        state, Refresh(REFRESH_CARD, ((6, 0),), False))

    assert dict(ledger.costs)["refresh_held_options"] == pytest.approx(0.4)


def test_refresh_charges_a_dead_fetch_only_as_known_discard_fodder():
    deck = (REFRESH_CARD, POKEMON_TUTOR, *(FILLER for _ in range(10)))
    state, registry = _state(deck, hand=(REFRESH_CARD, POKEMON_TUTOR))

    def hand_potential(observation):
        hand = observation["current"]["players"][0].get("hand") or ()
        value = 0.2 * len(hand)
        return Potential(value, (("hand", value),))

    evaluator = RefreshEvaluator(
        registry, hand_potential,
        effects=CardEffects({POKEMON_TUTOR: [{
            "kind": "fetch", "target": "pokemon", "zone": "deck",
        }]}),
        stats=_stats(),
    )

    ledger, _branches = evaluator.evaluate(
        state, Refresh(REFRESH_CARD, ((6, 0),), False))

    assert dict(ledger.costs)["refresh_held_options"] == pytest.approx(
        0.2 + KNOWN_CARD_FLOOR / 120.0)


def test_harlequin_style_coin_branches_are_averaged_without_draw_hands():
    hidden = (LINE_TOP, *(FILLER for _ in range(9)))
    deck = (REFRESH_CARD, LINE_BASE, *hidden)
    state, registry = _state(deck)
    evaluator = RefreshEvaluator(
        registry, _potential, effects=CardEffects({}), stats=_stats())

    ledger, branches = evaluator.evaluate(
        state, Refresh(REFRESH_CARD, ((5, 3), (3, 5)), True))

    assert tuple((row["own_draw"], row["opponent_draw"]) for row in branches) == (
        (5, 3), (3, 5))
    assert all("expected_hand_value" in row for row in branches)
    # Dark by default: the opponent swing stays a diagnostics row until the share is armed.
    assert "refresh_opponent_hand" not in dict(ledger.benefits)
    assert "refresh_opponent_hand" not in dict(ledger.costs)
    assert "refresh_hand_size_tactical" not in dict(ledger.costs)
    assert all("opponent_hand" in row and "hand_size_tactical" in row for row in branches)


def test_the_opponent_strip_reaches_the_refresh_ledger():
    # ADR-0060: cards stripped from the opponent are certain value. The rewrite computed this
    # per branch and dropped it into diagnostics only, so Judge/Unfair Stamp/Harlequin priced
    # as pure self-harm exactly when they are strongest.
    hidden = (LINE_TOP, *(FILLER for _ in range(9)))
    deck = (REFRESH_CARD, LINE_BASE, *hidden)
    observation = _observation((REFRESH_CARD,))
    observation["current"]["players"][1]["handCount"] = 8
    registry = _registry(deck)
    state = DecisionState.from_observation(
        observation, deck=deck, deck_name="test", value_registry_identity=registry.identity)
    evaluator = RefreshEvaluator(
        registry, _potential, effects=CardEffects({}), stats=_stats(),
        opponent_hand_share=1.0)

    ledger, branches = evaluator.evaluate(state, Refresh(REFRESH_CARD, ((5, 2),), True))

    assert dict(ledger.benefits)["refresh_opponent_hand"] == pytest.approx(
        (8 - 2) * KNOWN_CARD_FLOOR / 120.0)
    assert branches[0]["opponent_hand"] == pytest.approx((8 - 2) * KNOWN_CARD_FLOOR / 120.0)


def test_a_symmetric_refresh_against_a_small_hand_is_priced_as_the_gift_it_is():
    hidden = (LINE_TOP, *(FILLER for _ in range(9)))
    deck = (REFRESH_CARD, LINE_BASE, *hidden)
    observation = _observation((REFRESH_CARD,))
    observation["current"]["players"][1]["handCount"] = 1
    registry = _registry(deck)
    state = DecisionState.from_observation(
        observation, deck=deck, deck_name="test", value_registry_identity=registry.identity)
    evaluator = RefreshEvaluator(
        registry, _potential, effects=CardEffects({}), stats=_stats(),
        opponent_hand_share=1.0)

    ledger, _branches = evaluator.evaluate(state, Refresh(REFRESH_CARD, ((5, 4),), True))

    assert dict(ledger.costs)["refresh_opponent_hand"] == pytest.approx(
        (4 - 1) * KNOWN_CARD_FLOOR / 120.0)


def test_refresh_does_not_create_next_turn_demand_rewards_or_costs():
    hidden = (LINE_TOP, *(FILLER for _ in range(9)))
    deck = (REFRESH_CARD, LINE_BASE, LINE_TOP, *hidden)
    observation = _observation((REFRESH_CARD, LINE_TOP))
    observation["current"]["players"][0]["bench"][0]["appearThisTurn"] = True
    registry = _registry(deck)
    state = DecisionState.from_observation(
        observation, deck=deck, deck_name="test", value_registry_identity=registry.identity)
    evaluator = RefreshEvaluator(
        registry, _potential, effects=CardEffects({}), stats=_stats())

    ledger, branches = evaluator.evaluate(state, Refresh(REFRESH_CARD, ((6, 0),), False))

    assert not any("demand" in key for key in (*dict(ledger.benefits), *dict(ledger.costs)))
    assert "expected_hand_value" in branches[0]
