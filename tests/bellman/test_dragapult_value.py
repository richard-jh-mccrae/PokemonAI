from copy import deepcopy

from common import CardFacts, ValueRegistry
from common.options import enumerate_legal_actions, recycled_card_ids
from agents.dragapult_ex.potential import DragapultPotential
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider


MUNKIDORI, DRAGAPULT, TARGET, ENERGY = 112, 121, 900, 7
MIND_BEND, PHANTOM_DIVE, SNIPE = 141, 154, 901
ORDINARY = 904


def _body(card_id, *, hp=100, maximum=100, energies=()):
    return {
        "id": card_id,
        "hp": hp,
        "maxHp": maximum,
        "energies": list(energies),
        "energyCards": [{"id": ENERGY} for _ in energies],
        "preEvolution": [],
        "tools": [],
    }


def _observation(*, mine, opponent, marker=None):
    observation = {
        "current": {
            "yourIndex": 0,
            "result": -1,
            "players": [mine, opponent],
        },
        "select": {"context": 0, "option": []},
    }
    if marker is not None:
        observation["bellmanTransient"] = marker
    return observation


def _player(active, bench=()):
    return {
        "active": [active] if active else [],
        "bench": list(bench),
        "hand": [],
        "prize": [None] * 6,
    }


def test_darkness_energy_fuels_munkidori_ability_value():
    stats = DictCardStatProvider({
        MUNKIDORI: CardStat(MUNKIDORI, hp=110, abilityEnergyTypes=(7,)),
        TARGET: CardStat(TARGET, hp=100),
        ENERGY: CardStat(ENERGY, cardType=5, energyType=7),
    })
    registry = ValueRegistry(
        roles={MUNKIDORI: ("counter_mover",)},
        facts={MUNKIDORI: CardFacts(pokemon=True), TARGET: CardFacts(pokemon=True),
               ENERGY: CardFacts(typed_basic_energy=True)},
    )
    potential = DragapultPotential(stats, registry=registry, root_seat=0)
    opponent = _player(_body(TARGET))
    unfunded = _observation(
        mine=_player(_body(TARGET), (_body(MUNKIDORI, maximum=110, hp=110),)),
        opponent=opponent,
    )
    funded = deepcopy(unfunded)
    funded["current"]["players"][0]["bench"][0]["energies"] = [7]
    funded["current"]["players"][0]["bench"][0]["energyCards"] = [{"id": ENERGY}]

    before = dict(potential(unfunded).families)
    after = dict(potential(funded).families)

    assert after["ability_fuel"] > before["ability_fuel"]
    assert potential(funded).total > potential(unfunded).total


def test_confusion_has_bellman_value():
    stats = DictCardStatProvider({
        MUNKIDORI: CardStat(MUNKIDORI, hp=110, attacks=(MIND_BEND,)),
        TARGET: CardStat(TARGET, hp=100),
    }, attacks={MIND_BEND: AttackStat(MIND_BEND, damage=60, energyTypes=(5, 0))})
    registry = ValueRegistry(functions={MUNKIDORI: ("confuse",)}, facts={
        MUNKIDORI: CardFacts(pokemon=True), TARGET: CardFacts(pokemon=True),
    })
    potential = DragapultPotential(stats, registry=registry, root_seat=0)
    clear = _observation(
        mine=_player(_body(MUNKIDORI, maximum=110, hp=110, energies=(5, 7))),
        opponent=_player(_body(TARGET)),
    )
    confused = deepcopy(clear)
    confused["current"]["players"][1]["confused"] = True

    assert dict(potential(confused).families)["special_conditions"] > 0.0
    assert potential(confused).total > potential(clear).total


def test_item_lock_marker_has_bellman_value():
    stats = DictCardStatProvider({TARGET: CardStat(TARGET, hp=100)})
    registry = ValueRegistry(functions={235: ("item_lock",)},
                             facts={TARGET: CardFacts(pokemon=True)})
    potential = DragapultPotential(stats, registry=registry, root_seat=0)
    clear = _observation(mine=_player(_body(TARGET)), opponent=_player(_body(TARGET)))
    locked = deepcopy(clear)
    locked["bellmanActor"] = 1
    locked["current"]["players"][0]["active"] = [_body(235)]
    clear["current"]["players"][0]["active"] = [_body(235)]

    assert dict(potential(locked).families)["item_lock"] > 0.0
    assert potential(locked).total > potential(clear).total


def test_benched_tera_is_not_exposed_to_direct_snipe():
    stats = DictCardStatProvider({
        TARGET: CardStat(TARGET, hp=100),
        DRAGAPULT: CardStat(DRAGAPULT, hp=320, tera=True),
        ORDINARY: CardStat(ORDINARY, hp=320),
        902: CardStat(902, hp=100, attacks=(SNIPE,)),
    }, attacks={SNIPE: AttackStat(SNIPE, damage=10, benchSnipe=100)})
    registry = ValueRegistry(functions={DRAGAPULT: ("spread",)}, facts={
        TARGET: CardFacts(pokemon=True),
        DRAGAPULT: CardFacts(pokemon=True, prize_value=2),
        ORDINARY: CardFacts(pokemon=True, prize_value=2),
        902: CardFacts(pokemon=True),
    })
    potential = DragapultPotential(stats, registry=registry, root_seat=0)
    tera = _observation(
        mine=_player(_body(TARGET, hp=50), (_body(DRAGAPULT, hp=80, maximum=320),)),
        opponent=_player(_body(902)),
    )
    ordinary = deepcopy(tera)
    ordinary["current"]["players"][0]["bench"][0]["id"] = ORDINARY

    assert potential(tera).total > potential(ordinary).total


def test_phantom_dive_spread_counts_a_ready_multi_target_ko():
    stats = DictCardStatProvider({
        DRAGAPULT: CardStat(DRAGAPULT, hp=320, attacks=(PHANTOM_DIVE,)),
        TARGET: CardStat(TARGET, hp=200),
    }, attacks={
        PHANTOM_DIVE: AttackStat(
            PHANTOM_DIVE, damage=200, energyTypes=(2, 5), benchSpread=60),
    })
    registry = ValueRegistry(functions={DRAGAPULT: ("spread",)}, facts={
        DRAGAPULT: CardFacts(pokemon=True, prize_value=2),
        TARGET: CardFacts(pokemon=True),
    })
    potential = DragapultPotential(stats, registry=registry, root_seat=0)
    observation = _observation(
        mine=_player(_body(DRAGAPULT, hp=320, maximum=320, energies=(2, 5))),
        opponent=_player(_body(TARGET, hp=200, maximum=200),
                         (_body(TARGET, hp=40, maximum=200),)),
    )

    assert dict(potential(observation).families)["multi_target_ko"] == 2.0


def test_phantom_dive_splits_six_counters_across_multiple_knockouts():
    stats = DictCardStatProvider({
        DRAGAPULT: CardStat(DRAGAPULT, hp=320, attacks=(PHANTOM_DIVE,)),
        TARGET: CardStat(TARGET, hp=200),
    }, attacks={PHANTOM_DIVE: AttackStat(
        PHANTOM_DIVE, damage=200, energyTypes=(2, 5), benchSpread=60)})
    registry = ValueRegistry(functions={DRAGAPULT: ("spread",)}, facts={
        DRAGAPULT: CardFacts(pokemon=True, prize_value=2),
        TARGET: CardFacts(pokemon=True),
    })
    potential = DragapultPotential(stats, registry=registry, root_seat=0)
    observation = _observation(
        mine=_player(_body(DRAGAPULT, hp=320, maximum=320, energies=(2, 5))),
        opponent=_player(_body(TARGET, hp=200, maximum=200), (
            _body(TARGET, hp=30, maximum=200),
            _body(TARGET, hp=30, maximum=200),
        )),
    )

    assert dict(potential(observation).families)["multi_target_ko"] == 3.0


def test_extra_counter_on_knocked_out_body_is_negative_value():
    stats = DictCardStatProvider({TARGET: CardStat(TARGET, hp=100)})
    registry = ValueRegistry(functions={TARGET: ("spread",)},
                             facts={TARGET: CardFacts(pokemon=True)})
    potential = DragapultPotential(stats, registry=registry, root_seat=0)
    knocked_out = _observation(
        mine=_player(_body(TARGET)),
        opponent=_player(None, (_body(TARGET, hp=0),)),
    )
    overkilled = deepcopy(knocked_out)
    overkilled["current"]["players"][1]["bench"][0]["hp"] = -10

    assert potential(overkilled).total < potential(knocked_out).total


def test_run_away_draw_credits_the_recycled_line_and_freed_pivot():
    dunsparce, dudunsparce = 305, 66
    stats = DictCardStatProvider({
        dunsparce: CardStat(dunsparce, hp=70),
        dudunsparce: CardStat(dudunsparce, hp=140),
        TARGET: CardStat(TARGET, hp=100),
        ORDINARY: CardStat(ORDINARY, hp=100),
        902: CardStat(902, hp=100),
    })
    registry = ValueRegistry(
        functions={dunsparce: ("recycle_line",), dudunsparce: ("recycle_line", "draw")},
        facts={card_id: CardFacts(pokemon=True)
               for card_id in (dunsparce, dudunsparce, TARGET, ORDINARY, 902)},
        overrides={dunsparce: 12, dudunsparce: 12, TARGET: 30, ORDINARY: 30, 902: 30},
    )
    potential = DragapultPotential(stats, registry=registry, root_seat=0)
    pivot = _body(dudunsparce, hp=140, maximum=140)
    pivot["preEvolution"] = [{"id": dunsparce}]
    before = _observation(
        mine=_player(_body(TARGET), (pivot,)), opponent=_player(_body(TARGET)))
    after = _observation(
        mine=_player(_body(TARGET)), opponent=_player(_body(TARGET)))
    after["current"]["players"][0]["deck"] = [{"id": dunsparce}, {"id": dudunsparce}]
    after["current"]["players"][0]["hand"] = [
        {"id": TARGET}, {"id": ORDINARY}, {"id": 902}]
    before["select"]["option"] = [
        {"type": 10, "inPlayArea": 5, "inPlayIndex": 0}]
    action = next(action for action in enumerate_legal_actions(before)
                  if action.identity.kind == "ability")
    after["bellmanRecycledCardIds"] = recycled_card_ids(before, action, registry, 0)

    assert dict(potential(after).families)["reusable_draw_line"] == 0.2
    assert potential(after).total > potential(before).total
