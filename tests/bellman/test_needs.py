from __future__ import annotations

import pytest

from common.effects import CardEffects
from common.needs import CoverageEdge, Need, NeedModel, NeedRoute, best_assignment
from common.scouting.provider import CardStat, DictCardStatProvider
from common.value import CardFacts, Potential, ValueRegistry


LINE_BASE = 901
LINE_TOP = 902
SUPPORTER = 903
UNRELATED = 904
BENCH_TUTOR = 905
TRAINER_TUTOR = 906
TOOL = 907


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


def test_typed_need_routes_cross_bench_ability_and_supporter_tutor_edges():
    registry = ValueRegistry(facts={
        BENCH_TUTOR: CardFacts(pokemon=True, stage="basic"),
        TRAINER_TUTOR: CardFacts(),
        TOOL: CardFacts(),
    })
    stats = DictCardStatProvider({
        BENCH_TUTOR: CardStat(BENCH_TUTOR, hp=70, stage="basic"),
        TRAINER_TUTOR: CardStat(TRAINER_TUTOR, cardType=3),
        TOOL: CardStat(TOOL, cardType=2),
    })
    effects = CardEffects({
        BENCH_TUTOR: [{"kind": "fetch", "target": "supporter", "zone": "deck",
                       "trigger": "on_bench_play"}],
        TRAINER_TUTOR: [{"kind": "fetch", "target": "trainer", "zone": "deck"}],
    })
    model = NeedModel(registry, _potential, effects=effects, stats=stats)
    need = Need("retreat", ((TOOL, 2.0),))
    available = {TRAINER_TUTOR: 1, TOOL: 1}

    route = model.best_route(
        BENCH_TUTOR, (need,), supporter_available=True, discard_capacity=0,
        bench_capacity=1, available_targets=available)

    assert route is not None
    assert route.path == (BENCH_TUTOR, TRAINER_TUTOR, TOOL)
    assert route.value == pytest.approx(2.0 * 0.75 ** 2)
    assert model.routes(
        BENCH_TUTOR, (need,), supporter_available=True, discard_capacity=0,
        bench_capacity=0, available_targets=available) == ()
    assert model.routes(
        BENCH_TUTOR, (need,), supporter_available=False, discard_capacity=0,
        bench_capacity=1, available_targets=available) == ()


def test_need_route_progress_rises_only_as_same_turn_actions_are_committed():
    route = NeedRoute(0, 2.0 * 0.75 ** 2,
                      (BENCH_TUTOR, TRAINER_TUTOR, TOOL), direct_value=2.0)

    values = (
        route.progress_value(0),
        route.progress_value(0, pending=True),
        route.progress_value(1),
        route.progress_value(1, pending=True),
        route.progress_value(2),
        route.direct_value,
    )

    assert values == tuple(sorted(values))
    assert values[0] == pytest.approx(2.0 * 0.75 ** 5)
    assert values[-1] == pytest.approx(2.0)


def test_committed_supporter_route_survives_after_its_play_is_paid():
    registry = ValueRegistry(facts={TRAINER_TUTOR: CardFacts(), TOOL: CardFacts()})
    stats = DictCardStatProvider({
        TRAINER_TUTOR: CardStat(TRAINER_TUTOR, cardType=3),
        TOOL: CardStat(TOOL, cardType=2),
    })
    model = NeedModel(registry, _potential, effects=CardEffects({
        TRAINER_TUTOR: [{"kind": "fetch", "target": "trainer", "zone": "deck"}],
    }), stats=stats)
    need = Need("retreat", ((TOOL, 2.0),))

    assert model.routes(
        TRAINER_TUTOR, (need,), supporter_available=False, discard_capacity=0,
        available_targets={TOOL: 1}) == ()
    assert model.best_route(
        TRAINER_TUTOR, (need,), supporter_available=False, discard_capacity=0,
        available_targets={TOOL: 1}, committed=True).path == (TRAINER_TUTOR, TOOL)


def test_assignment_cannot_spend_one_intermediate_tutor_copy_twice():
    signatures = (
        (CoverageEdge(0, 1.0, fetched_targets=(TRAINER_TUTOR, TOOL)),),
        (CoverageEdge(1, 1.0, fetched_targets=(TRAINER_TUTOR, LINE_TOP)),),
    )

    assignment = best_assignment(
        signatures, 2, target_counts={TRAINER_TUTOR: 1, TOOL: 1, LINE_TOP: 1})

    assert assignment.value == pytest.approx(1.0)
    assert assignment.covered_mask in (0b01, 0b10)


def test_visible_direct_out_removes_need_before_tutor_valuation():
    model = _model()
    needs = (Need("develop", ((LINE_TOP, 1.0),)),)

    assert model.uncovered_by_direct_hand(
        needs, [LINE_TOP], supporter_available=True) == ()
    assert model.uncovered_by_direct_hand(
        needs, [UNRELATED], supporter_available=True) == needs


def test_playable_supporter_in_hand_covers_its_direct_need_only_while_usable():
    model = _model()
    needs = (Need("damage", ((SUPPORTER, 1.0),)),)

    assert model.uncovered_by_hand(
        needs, [SUPPORTER], supporter_available=True, discard_capacity=0) == ()
    assert model.uncovered_by_hand(
        needs, [SUPPORTER], supporter_available=False, discard_capacity=0) == needs


@pytest.mark.parametrize("observation", (
    _observation([LINE_TOP], appeared=False),
    _observation([LINE_TOP], body=False),
))
def test_next_turn_evolution_option_disappears_when_the_enabling_clock_or_body_is_absent(observation):
    resolved = _model().next_turn_retained(observation, 0, [LINE_TOP])

    assert resolved.value == 0.0
    assert resolved.options == ()
