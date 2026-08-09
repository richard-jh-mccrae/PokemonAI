"""Closed-form chance-node boundaries for Issue #456."""
from __future__ import annotations

import pytest

from common import board_expectation as be
from common import state_value as sv
from common.board_delta import Unmodellable
from common.cards import CardFunctions
from common.composer import compose
from common.effects import CardEffects
from common.scouting.provider import CardStat, DictCardStatProvider
from common.state_model import StateModel
from common.strategy.combat import CombatMath
from common.strategy.context import _PLAY


HAMMER, STAMP, JUDGE, BASIC, ENERGY = 1120, 1080, 1213, 90001, 6


def _body(card_id, *, energy=False):
    cards = ([{"id": ENERGY, "serial": 31, "playerIndex": 1}] if energy else [])
    return {"id": card_id, "serial": card_id, "playerIndex": 1, "hp": 100, "maxHp": 100,
            "appearThisTurn": False, "energies": [6] if energy else [], "energyCards": cards,
            "tools": [], "preEvolution": []}


def _model(card_id, clauses, *, opp_hand=0, opp_deck=16):
    stats = DictCardStatProvider({
        HAMMER: CardStat(HAMMER, name="Crushing Hammer", cardType=1),
        STAMP: CardStat(STAMP, name="Unfair Stamp", cardType=1),
        JUDGE: CardStat(JUDGE, name="Judge", cardType=3),
        BASIC: CardStat(BASIC, synthetic=True, name="Basic", hp=100, cardType=0),
        ENERGY: CardStat(ENERGY, name="Basic {F} Energy", cardType=5, energyType=6),
    })
    combat = CombatMath(stats, functions=CardFunctions({}), transients=None,
                        effects=CardEffects({card_id: clauses}))
    mine = {"active": [_body(BASIC)], "bench": [], "benchMax": 5,
            "hand": [{"id": card_id, "serial": 11, "playerIndex": 0}], "handCount": 1,
            "discard": [], "prize": [None] * 4,
            "poisoned": False, "burned": False, "asleep": False, "paralyzed": False,
            "confused": False}
    theirs = {"active": [_body(BASIC, energy=True)], "bench": [], "benchMax": 5,
              "hand": [], "handCount": opp_hand, "deckCount": opp_deck, "discard": [],
              "prize": [None] * 4,
              "poisoned": False, "burned": False, "asleep": False, "paralyzed": False,
              "confused": False}
    obs = {"current": {"players": [mine, theirs], "yourIndex": 0, "turn": 3,
                       "energyAttached": False, "supporterPlayed": False, "retreated": False,
                       "stadiumPlayed": False, "stadium": []}, "logs": [],
           "select": {"context": 0, "option": []}}
    return StateModel.build(obs, combat=combat, deck=[BASIC] * 59 + [card_id])


def test_a_coin_is_not_rejected_by_the_shuffle_rng_guard():
    """A 50/50 flip has two known branches; deck-order RNG remains the refused shape."""
    be._check_clause({"kind": "coin", "effect": "discard_opp_energy", "amount": 1},
                     1120, "Crushing Hammer")
    with pytest.raises(Unmodellable, match="RNG"):
        be._check_clause({"kind": "fetch", "target": "pokemon", "zone": "deck",
                          "rider": "shuffle_both_hands"}, 1, "shuffle control")
    with pytest.raises(Unmodellable, match="exact one-Energy"):
        be._check_clause({"kind": "coin", "effect": "discard_opp_energy", "amount": 2},
                         1120, "coin control")


def test_threat_prices_an_opponents_hand_as_a_resource_once():
    """A held opponent card is a liability for me; the same read must not create a new family."""
    assert sv.threat([1.0], opponent_hand_resource=4.0) < sv.threat([1.0])
    threat = sv.FAMILIES["threat"]
    assert "opponent_hand_resource" in threat.reads
    assert sv.registry_gaps() == sv.double_counted() == []
    assert sv.threat([], opponent_hand_resource=sv._needs.TARGET_VALUE_CEILING ** 2) == pytest.approx(
        -sv._THREAT_CAP)


def test_crushing_hammer_orders_the_mean_of_its_dealt_branches_not_heads():
    model = _model(HAMMER, [{"kind": "coin", "effect": "discard_opp_energy", "amount": 1}])
    result = be.coin_expectation(model, {"type": _PLAY, "index": 0},
                                 score=lambda after: after.theirs.active.energy_count)
    assert result is not None and result.resolution == "dealt"
    assert [c.probability for c in result.classes] == [0.5, 0.5]
    assert result.best(lambda after: after.theirs.active.energy_count) == 1.0
    assert result.ordering(lambda after: after.theirs.active.energy_count) == pytest.approx(0.5)


def test_judge_is_a_scalar_transition_not_a_draw_class_enumeration():
    model = _model(JUDGE, [{"kind": "draw", "amount": 4, "rider": "shuffle_both_hands"}],
                   opp_hand=8, opp_deck=16)
    result = be.refresh_transition(model, {"type": _PLAY, "index": 0})
    assert result is not None
    assert result.scalar == pytest.approx(3.0 / 120.0)
    assert result.model.theirs.hand_size == 4
    assert result.model.theirs.deck_count == 20
    assert result.model.mine.hand_size == 4


def test_judge_strips_a_fresh_opponent_hand_more_than_it_refills_an_empty_one():
    clauses = [{"kind": "draw", "amount": 4, "rider": "shuffle_both_hands"}]
    empty = compose(_model(JUDGE, clauses, opp_hand=0), [{"type": _PLAY, "index": 0}],
                    clauses_cover=True)
    fresh = compose(_model(JUDGE, clauses, opp_hand=8), [{"type": _PLAY, "index": 0}],
                    clauses_cover=True)
    assert fresh.fanned[0] > empty.fanned[0]


def test_a_partial_refresh_stays_on_the_generic_fail_closed_path():
    result = compose(_model(STAMP, [{"kind": "draw", "amount": 5,
                                    "rider": "shuffle_both_hands"}], opp_hand=8),
                     [{"type": _PLAY, "index": 0}], clauses_cover=False)
    assert result.fanned == (None,)
    assert result.gaps and "shuffle_both_hands" in result.gaps[0]


@pytest.mark.parametrize(("card_id", "clauses"), [
    (HAMMER, [{"kind": "coin", "effect": "discard_opp_energy", "amount": 1}]),
    (JUDGE, [{"kind": "draw", "amount": 4, "rider": "shuffle_both_hands"}]),
])
def test_the_composer_prices_each_closed_form_chance_route(card_id, clauses):
    result = compose(_model(card_id, clauses, opp_hand=8), [{"type": _PLAY, "index": 0}],
                     clauses_cover=True)
    assert result.fanned[0] is not None
    assert result.gaps == ()
