from __future__ import annotations

import pytest

from common.effects import CardEffects
from common.needs import Need, NeedModel, best_assignment
from common.scouting.provider import CardStat, DictCardStatProvider
from common.value import CardFacts, Potential, ValueRegistry


LINE_BASE = 901
LINE_TOP = 902
SUPPORTER = 903
UNRELATED = 904


def _potential(observation):
    mine = observation["current"]["players"][0]
    hand = 0.2 * len(mine.get("hand") or ())
    body = next((body for body in mine.get("bench") or () if body), None)
    board = 0.0
    if body and int(body.get("id", 0)) == LINE_TOP:
        board = 1.0
        if int(body.get("hp", 0)) == int(body.get("maxHp", 0)):
            board += 0.3
    families = (("board", board), ("hand", hand))
    return Potential(sum(value for _name, value in families), families)


def _observation(hand, *, appeared=True, body=True):
    bench = []
    if body:
        bench.append({
            "id": LINE_BASE, "hp": 30, "maxHp": 60, "appearThisTurn": appeared,
            "preEvolution": [], "energies": [], "energyCards": [], "tools": [],
        })
    return {
        "current": {
            "yourIndex": 0, "turn": 2, "supporterPlayed": True,
            "energyAttached": True, "retreated": False, "stadiumPlayed": False,
            "players": [
                {"hand": [{"id": card_id} for card_id in hand], "handCount": len(hand),
                 "active": [], "bench": bench, "discard": [], "prize": [None] * 6},
                {"hand": None, "handCount": 0, "active": [], "bench": [],
                 "discard": [], "prize": [None] * 6},
            ],
        },
    }


def _model():
    registry = ValueRegistry(
        roles={LINE_TOP: ("win_condition",)},
        facts={
            LINE_BASE: CardFacts(pokemon=True, stage="basic"),
            LINE_TOP: CardFacts(pokemon=True, stage="stage1"),
            SUPPORTER: CardFacts(),
            UNRELATED: CardFacts(),
        },
        lines=((LINE_BASE, LINE_TOP),), line_pairs=((LINE_BASE, LINE_TOP),),
    )
    stats = DictCardStatProvider({
        LINE_BASE: CardStat(LINE_BASE, hp=60, stage="basic"),
        LINE_TOP: CardStat(LINE_TOP, hp=330, stage="stage1", megaEx=True),
        SUPPORTER: CardStat(SUPPORTER, cardType=3),
        UNRELATED: CardStat(UNRELATED, cardType=1),
    })
    return NeedModel(registry, _potential, effects=CardEffects({}), stats=stats)


def test_assignment_never_uses_one_card_or_need_twice():
    assignment = best_assignment((((0, 1.0), (1, 0.8)), ((0, 0.9),)), 2)

    assert assignment.value == pytest.approx(1.7)
    assert assignment.covered_mask == 0b11
    assert assignment.used_card_mask == 0b11


def test_next_turn_evolution_has_situational_value_beyond_equal_static_hand_worth():
    model = _model()

    useful = model.next_turn_retained(
        _observation([LINE_TOP, UNRELATED]), 0, [LINE_TOP, UNRELATED])
    unrelated = model.next_turn_retained(
        _observation([UNRELATED]), 0, [UNRELATED])

    assert useful.value == pytest.approx(0.6)
    assert useful.options[0].description.startswith("evolve:")
    assert unrelated.value == 0.0


def test_multi_target_fetch_provides_one_assignment_token_per_printed_target():
    model = _model()
    needs = (
        Need("setup:one", ((LINE_BASE, 0.5),)),
        Need("setup:two", ((LINE_BASE, 0.5),)),
    )
    effects = CardEffects({SUPPORTER: [{
        "kind": "fetch", "target": "pokemon", "zone": "deck", "amount": 2,
    }]})
    model = NeedModel(model.registry, _potential, effects=effects, stats=model.stats)

    tokens = model.coverage_slots(
        SUPPORTER, needs, supporter_available=True, discard_capacity=0,
        available_targets={LINE_BASE: 2})
    assignment = best_assignment(tokens, len(needs), target_counts={LINE_BASE: 2})

    assert len(tokens) == 2
    assert assignment.value == pytest.approx(1.0)


def test_fetch_without_a_remaining_target_is_not_an_out():
    model = _model()
    need = Need("develop", ((LINE_TOP, 1.0),))
    effects = CardEffects({SUPPORTER: [{
        "kind": "fetch", "target": "pokemon", "zone": "deck",
    }]})
    model = NeedModel(model.registry, _potential, effects=effects, stats=model.stats)

    assert model.coverage_slots(
        SUPPORTER, (need,), supporter_available=True, discard_capacity=0,
        available_targets={LINE_TOP: 0}) == ()


@pytest.mark.parametrize("observation", (
    _observation([LINE_TOP], appeared=False),
    _observation([LINE_TOP], body=False),
))
def test_next_turn_evolution_option_disappears_when_the_enabling_clock_or_body_is_absent(observation):
    resolved = _model().next_turn_retained(observation, 0, [LINE_TOP])

    assert resolved.value == 0.0
    assert resolved.options == ()
