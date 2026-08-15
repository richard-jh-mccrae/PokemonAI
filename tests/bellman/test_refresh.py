from __future__ import annotations

from types import SimpleNamespace

import pytest

from common import DecisionState, Refresh
from common.effects import CardEffects
from common.native_engine import NativeCgTransitionProvider, _NativeWorld
from common.needs import Need
from common.options import enumerate_legal_actions
from common.refresh import RefreshEvaluator
from common.scouting.provider import CardStat, DictCardStatProvider
from common.value import CardFacts, Potential, ValueRegistry


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
        roles={LINE_BASE: ("win_condition_base",), LINE_TOP: ("win_condition",)},
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


def test_refresh_uses_exact_need_class_odds_for_direct_cards_and_fetchers():
    # Four semantic outs in ten cards, drawing two: 1 - C(6,2)/C(10,2) = 2/3.
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

    assert dict(ledger.benefits)["refresh_immediate_needs"] == pytest.approx(2 / 3)
    assert branches[0]["needs"] == (f"evolve:20:{LINE_TOP}",)


def test_drawn_tutor_cannot_reuse_the_last_matching_target_drawn_beside_it():
    deck = (REFRESH_CARD, LINE_BASE, LINE_TOP, POKEMON_TUTOR)
    state, registry = _state(deck)
    evaluator = RefreshEvaluator(
        registry, _potential,
        effects=CardEffects({POKEMON_TUTOR: [{
            "kind": "fetch", "target": "pokemon", "zone": "deck",
        }]}),
        stats=_stats(),
    )
    needs = (Need("first", ((LINE_TOP, 1.0),)), Need("second", ((LINE_TOP, 1.0),)))

    value = evaluator._expected_need_value(
        state, needs, (), 2, supporter_available=True)

    assert value == pytest.approx(1.0)


def test_future_need_odds_use_one_root_value_for_every_covering_out():
    evaluator = RefreshEvaluator(
        _registry((REFRESH_CARD, LINE_TOP, FILLER)), _potential,
        effects=CardEffects({}), stats=_stats())
    needs = (Need("future", ((LINE_TOP, 0.2), (FILLER, 1.0))),)

    normalized = evaluator._root_value(needs)

    assert normalized[0].direct == ((LINE_TOP, 1.0), (FILLER, 1.0))


def test_future_need_normalization_preserves_recipient_and_attack_exclusivity():
    evaluator = RefreshEvaluator(
        _registry((REFRESH_CARD, LINE_TOP, FILLER)), _potential,
        effects=CardEffects({}), stats=_stats())
    need = Need(
        "future", ((LINE_TOP, 0.2), (FILLER, 1.0)), timing="next_turn",
        recipient="active:7", capability="fund_attack", slot="1:3",
        ceiling=1.0, alternative="1487")

    normalized = evaluator._root_value((need,))[0]

    assert normalized.recipient == "active:7"
    assert normalized.capability == "fund_attack"
    assert normalized.slot == "1:3"
    assert normalized.alternative == "1487"
    assert normalized.ceiling == pytest.approx(1.0)


def test_refresh_does_not_claim_a_need_already_held_and_playable_first():
    hidden = (LINE_TOP, LINE_TOP, *(FILLER for _ in range(8)))
    deck = (REFRESH_CARD, LINE_BASE, LINE_TOP, *hidden)
    state, registry = _state(deck, hand=(REFRESH_CARD, LINE_TOP))
    evaluator = RefreshEvaluator(
        registry, _potential, effects=CardEffects({}), stats=_stats())

    ledger, branches = evaluator.evaluate(state, Refresh(REFRESH_CARD, ((6, 0),), False))

    assert "refresh_immediate_needs" not in dict(ledger.benefits)
    assert dict(ledger.costs)["refresh_held_options"] == pytest.approx(0.2)
    assert branches[0]["needs"] == ()


def test_refresh_does_not_charge_the_played_card_as_a_surrendered_option():
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

    assert dict(ledger.costs)["refresh_held_options"] == pytest.approx(0.2)


def test_harlequin_style_coin_branches_are_averaged_without_draw_hands():
    hidden = (LINE_TOP, *(FILLER for _ in range(9)))
    deck = (REFRESH_CARD, LINE_BASE, *hidden)
    state, registry = _state(deck)
    evaluator = RefreshEvaluator(
        registry, _potential, effects=CardEffects({}), stats=_stats())

    _ledger, branches = evaluator.evaluate(
        state, Refresh(REFRESH_CARD, ((5, 3), (3, 5)), True))

    assert tuple((row["own_draw"], row["opponent_draw"]) for row in branches) == (
        (5, 3), (3, 5))
    assert all("need_value" in row for row in branches)


def test_refresh_charges_a_deterministic_next_turn_evolution_option():
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

    assert dict(ledger.costs)["refresh_next_turn_options"] == pytest.approx(0.8)
    assert dict(ledger.benefits)["refresh_next_turn_needs"] > 0.0
    assert branches[0]["retained_options"][0].startswith("evolve:")
    assert branches[0]["next_turn_needs"] == (f"evolve:20:{LINE_TOP}",)
