"""Closed-form chance-node boundaries for Issues #456 and #466."""
from __future__ import annotations

from dataclasses import replace

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


HAMMER, STAMP, JUDGE, HARLEQUIN, DETERMINATION, BASIC, ENERGY = (
    1120, 1080, 1213, 1223, 1227, 90001, 6)


def _body(card_id, *, energy=False):
    cards = ([{"id": ENERGY, "serial": 31, "playerIndex": 1}] if energy else [])
    return {"id": card_id, "serial": card_id, "playerIndex": 1, "hp": 100, "maxHp": 100,
            "appearThisTurn": False, "energies": [6] if energy else [], "energyCards": cards,
            "tools": [], "preEvolution": []}


def _model(card_id, clauses, *, opp_hand=0, opp_deck=16, covers="full", context=0):
    stats = DictCardStatProvider({
        HAMMER: CardStat(HAMMER, name="Crushing Hammer", cardType=1),
        STAMP: CardStat(STAMP, name="Unfair Stamp", cardType=1),
        JUDGE: CardStat(JUDGE, name="Judge", cardType=3),
        HARLEQUIN: CardStat(HARLEQUIN, name="Harlequin", cardType=3),
        DETERMINATION: CardStat(DETERMINATION, name="Lillie's Determination", cardType=3),
        BASIC: CardStat(BASIC, synthetic=True, name="Basic", hp=100, cardType=0),
        ENERGY: CardStat(ENERGY, name="Basic {F} Energy", cardType=5, energyType=6),
    })
    table = {card_id: clauses}
    if covers is not None:
        table["_covers"] = {str(card_id): {"covers": covers, "reason": "test verdict"}}
    combat = CombatMath(stats, functions=CardFunctions({}), transients=None,
                        effects=CardEffects(table))
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
           "select": {"context": context, "option": []}}
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
    result = be.closed_form_transition(
        model, {"type": _PLAY, "index": 0},
        score=lambda after: after.theirs.active.energy_count)
    assert result is not None and result.resolution == "dealt"
    assert [c.probability for c in result.classes] == [0.5, 0.5]
    assert result.best(lambda after: after.theirs.active.energy_count) == 1.0
    assert result.ordering(lambda after: after.theirs.active.energy_count) == pytest.approx(0.5)


def test_judge_is_a_scalar_transition_not_a_draw_class_enumeration():
    model = _model(JUDGE, [{"kind": "draw", "amount": 4, "rider": "shuffle_both_hands"}],
                   opp_hand=8, opp_deck=16)
    result = be.closed_form_transition(model, {"type": _PLAY, "index": 0}, score=lambda _m: 0.0)
    assert result is not None
    assert result.scalar == pytest.approx(3.0 / 120.0)
    assert result.model.theirs.hand_size == 4
    assert result.model.theirs.deck_count == 20
    assert result.model.mine.hand_size == 4


@pytest.mark.parametrize(("card_id", "clause", "my_hand", "their_hand", "scalar"), [
    (JUDGE, {"kind": "draw", "amount": 4, "rider": "shuffle_both_hands"}, 4, 4, 3 / 120),
    (HARLEQUIN, {"kind": "draw", "amount": 5,
                 "amount_if": {"condition": "coin_tails", "amount": 3},
                 "rider": "shuffle_both_hands"}, 4, 4, 3 / 120),
    (DETERMINATION, {"kind": "draw", "amount": 6,
                     "amount_if": {"condition": "exactly_6_prizes_remaining", "amount": 8},
                     "rider": "shuffle_own_hand_in"}, 6, 8, 5 / 120),
])
def test_structural_refresh_routes_preserve_the_three_pre_registry_results(
        card_id, clause, my_hand, their_hand, scalar):
    result = be.closed_form_transition(
        _model(card_id, [clause], opp_hand=8), {"type": _PLAY, "index": 0},
        score=lambda _m: 0.0)
    assert result.model.mine.hand_size == my_hand
    assert result.model.theirs.hand_size == their_hand
    assert result.scalar == pytest.approx(scalar)


def test_judge_strips_a_fresh_opponent_hand_more_than_it_refills_an_empty_one():
    clauses = [{"kind": "draw", "amount": 4, "rider": "shuffle_both_hands"}]
    empty = compose(_model(JUDGE, clauses, opp_hand=0), [{"type": _PLAY, "index": 0}])
    fresh = compose(_model(JUDGE, clauses, opp_hand=8), [{"type": _PLAY, "index": 0}])
    assert fresh.fanned[0] > empty.fanned[0]


def test_a_partial_refresh_stays_on_the_generic_fail_closed_path():
    result = compose(_model(STAMP, [{"kind": "draw", "amount": 5,
                                    "rider": "shuffle_both_hands"}], opp_hand=8,
                            covers="partial"),
                     [{"type": _PLAY, "index": 0}])
    assert result.fanned == (None,)
    assert result.gaps and "clause coverage is partial" in result.gaps[0]


@pytest.mark.parametrize(("card_id", "clauses"), [
    (HAMMER, [{"kind": "coin", "effect": "discard_opp_energy", "amount": 1}]),
    (JUDGE, [{"kind": "draw", "amount": 4, "rider": "shuffle_both_hands"}]),
])
def test_the_composer_prices_each_closed_form_chance_route(card_id, clauses):
    result = compose(_model(card_id, clauses, opp_hand=8), [{"type": _PLAY, "index": 0}])
    assert result.fanned[0] is not None
    assert result.gaps == ()


def test_closed_form_dispatch_checks_kind_and_source_before_hand_indexing():
    model = _model(JUDGE, [{"kind": "draw", "amount": 4,
                            "rider": "shuffle_both_hands"}])
    for wrong_kind in (999, None, "ability", {}, []):
        assert be.closed_form_transition(
            model, {"type": wrong_kind, "index": 999}, score=lambda _m: 0.0) is None
    with pytest.raises(Unmodellable, match="source index"):
        be.closed_form_transition(
            model, {"type": _PLAY, "index": 999}, score=lambda _m: 0.0)
    off_context = _model(JUDGE, [{"kind": "draw", "amount": 4,
                                 "rider": "shuffle_both_hands"}], context=1)
    assert be.closed_form_transition(
        off_context, {"type": _PLAY, "index": 999}, score=lambda _m: 0.0) is None


@pytest.mark.parametrize(("clauses", "covers", "message"), [
    ([{"kind": "coin", "effect": "discard_opp_energy", "amount": 1}], "partial",
     "clause coverage"),
    ([{"kind": "coin", "effect": "discard_opp_energy", "amount": 1, "mystery": True}],
     "full", "unhandled key"),
    ([{"kind": "coin", "effect": "discard_opp_energy", "amount": 2}], "full",
     "accepts clause shape"),
    ([{"kind": "coin", "effect": "discard_opp_energy", "amount": 1},
      {"kind": "heal", "amount": 20}], "full", "sibling clause"),
])
def test_closed_form_dispatch_refuses_every_incomplete_or_ambiguous_effect(
        clauses, covers, message):
    model = _model(HAMMER, clauses, covers=covers)
    before = model.source_obs
    with pytest.raises(Unmodellable, match=message):
        be.closed_form_transition(
            model, {"type": _PLAY, "index": 0}, score=lambda _m: 0.0)
    assert model.source_obs is before
    assert model.mine.hand_ids == (HAMMER,)


def test_closed_form_registry_order_cannot_hide_two_matching_routes(monkeypatch):
    model = _model(HAMMER, [{"kind": "coin", "effect": "discard_opp_energy", "amount": 1}])
    duplicate = replace(be.CLOSED_FORM_ROUTES[0], name="duplicate-coin")
    monkeypatch.setattr(be, "CLOSED_FORM_ROUTES", be.CLOSED_FORM_ROUTES + (duplicate,))
    with pytest.raises(Unmodellable, match="ambiguous.*coin.*duplicate-coin"):
        be.closed_form_transition(
            model, {"type": _PLAY, "index": 0}, score=lambda _m: 0.0)
