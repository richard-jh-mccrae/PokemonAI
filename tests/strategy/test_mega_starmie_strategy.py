"""Executable claims about the shipped Mega Starmie declarations, read against real card data."""
from types import SimpleNamespace

from agents.mega_starmie.strategy import (
    CINDERACE, IGNITION_ENERGY, MEGA_STARMIE_EX, STARYU, STRATEGY,
)
from common.cards import CardFunctions
from common.cards.functions.damage import bench_reach
from common.demand import StrategyBeamBuilder, semantic_action_key
from common.effects import CardEffects
from common.options import enumerate_legal_actions
from common.scouting.provider import EngineCardStatProvider
from common.strategy.strategies import (
    GENERAL_STRATEGIES, activate_strategies, resolve_strategies,
)


JETTING_BLOW, NEBULA_BEAM = 1487, 1488
POFFIN = 1086

STATS = EngineCardStatProvider()
FUNCTIONS = CardFunctions.load()
EFFECTS = CardEffects.load()
ROLES = STRATEGY.roles.resolve((STARYU, MEGA_STARMIE_EX, CINDERACE), STATS, FUNCTIONS)
RESOLVED = resolve_strategies(GENERAL_STRATEGIES, STRATEGY.strategies)


def _body(card_id, serial, energies=(), pre=(), hp=None):
    maximum = int(getattr(STATS.get(card_id), "hp", 100) or 100)
    return {"id": card_id, "serial": serial, "energies": list(energies), "energyCards": [],
            "hp": maximum if hp is None else hp, "maxHp": maximum,
            "preEvolution": list(pre), "tools": []}


def _observation(active, bench=(), *, hand=(), options=(), opponent_bench=(), turn=1):
    return {
        "current": {
            "turn": turn, "yourIndex": 0, "energyAttached": False, "supporterPlayed": False,
            "players": [
                {"active": [active], "bench": list(bench), "hand": list(hand),
                 "handCount": len(hand), "benchMax": 5, "discard": []},
                {"active": [_body(STARYU, 900)], "bench": list(opponent_bench), "benchMax": 5},
            ],
        },
        "select": {"context": 0, "minCount": 1, "maxCount": 1, "option": list(options)},
    }


def _activate(observation):
    return activate_strategies(observation, RESOLVED, roles=ROLES, stats=STATS,
                               opponent_role_worth={MEGA_STARMIE_EX: 3.0})


def _focused(observation, snapshot):
    actions = enumerate_legal_actions(observation)
    state = SimpleNamespace(obs=observation, root_seat=0,
                            deck_counts=((STARYU, 3), (MEGA_STARMIE_EX, 3)))
    beam = StrategyBeamBuilder(
        snapshot, effects=EFFECTS, stats=STATS, registry=None, width=8).build(state, actions)
    keys = {row.action_key for row in beam.focused}
    return actions, {action for action in actions if semantic_action_key(action) in keys}


def _selections_carrying(observation, snapshot, strategy_id):
    """Which offered selections the named hint itself put in the beam, ignoring every other."""
    actions = enumerate_legal_actions(observation)
    state = SimpleNamespace(obs=observation, root_seat=0,
                            deck_counts=((STARYU, 3), (MEGA_STARMIE_EX, 3)))
    beam = StrategyBeamBuilder(
        snapshot, effects=EFFECTS, stats=STATS, registry=None, width=8).build(state, actions)
    by_key = {semantic_action_key(action): action for action in actions}
    return {by_key[row.action_key].selection for row in beam.focused
            if strategy_id in row.path_ids}


def test_bench_hint_fires_before_the_energy_is_committed():
    """Turbo Flare attaches only to BENCHED Pokemon, so the Bench must hold Staryu before
    Cinderace is funded — the old attack_ready gate switched the hint off exactly then."""
    snapshot = _activate(_observation(_body(CINDERACE, 1)))

    assert "mega_starmie.bench_staryu_before_turbo_flare" in snapshot.active_ids


def test_bench_hint_rests_once_staryu_is_benched():
    snapshot = _activate(_observation(_body(CINDERACE, 1), [_body(STARYU, 2)]))

    assert "mega_starmie.bench_staryu_before_turbo_flare" in snapshot.inactive_ids


def test_bench_hint_rests_behind_an_attacker_that_cannot_turbo_flare():
    snapshot = _activate(_observation(_body(MEGA_STARMIE_EX, 2, pre=[{"id": STARYU}]), turn=5))

    assert "mega_starmie.bench_staryu_before_turbo_flare" in snapshot.inactive_ids


def test_bench_hint_focuses_the_basic_pokemon_tutor():
    observation = _observation(
        _body(CINDERACE, 1), hand=[{"id": POFFIN}], options=[{"type": 7, "index": 0}])
    actions, focused = _focused(observation, _activate(observation))

    assert focused == set(actions)


def test_only_jetting_blow_can_do_the_softening_nebula_beam_cashes_in():
    """Nebula Beam cannot reach the Bench, so the damage_setup matcher — which only ever accepted
    a bench-reaching attack — can only ever mean Jetting Blow's rider."""
    assert bench_reach(STATS.attack(JETTING_BLOW)) > 0
    assert bench_reach(STATS.attack(NEBULA_BEAM)) == 0


def test_one_softening_pass_covers_a_bench_body_but_not_a_mega_sized_one():
    """One rider then one gusted Nebula Beam reaches this far; a Mega-sized body needs more
    softening passes than that, and the hint keeps asking until the target leaves the board."""
    reach = int(STATS.attack(NEBULA_BEAM).damage) + bench_reach(STATS.attack(JETTING_BLOW))

    assert reach == 260
    assert reach < int(STATS.get(MEGA_STARMIE_EX).hp)


def test_the_snipe_hint_focuses_jetting_blow_and_not_nebula_beam():
    observation = _observation(
        _body(MEGA_STARMIE_EX, 2, energies=[0, 0, 0], pre=[{"id": STARYU}]),
        opponent_bench=[_body(MEGA_STARMIE_EX, 901)], turn=5,
        options=[{"type": 13, "attackId": JETTING_BLOW},
                 {"type": 13, "attackId": NEBULA_BEAM}, {"type": 14}])
    carried = _selections_carrying(
        observation, _activate(observation),
        "mega_starmie.soften_role_target_into_nebula_beam_range")

    assert carried == {(0,)}


def test_the_reload_waits_for_the_heal_that_creates_its_opening():
    """Correction 83116081-76 rules the Wally's play, not the attach. general healing already
    asks for the heal, so this hint declares only the repayment and rests until it lands."""
    damaged = _observation(
        _body(MEGA_STARMIE_EX, 2, energies=[3, 3], pre=[{"id": STARYU}], hp=60), turn=5)
    healed = _observation(_body(MEGA_STARMIE_EX, 2, pre=[{"id": STARYU}]), turn=5)

    assert ("mega_starmie.reload_the_healed_mega_with_ignition"
            in _activate(damaged).inactive_ids)
    assert ("mega_starmie.reload_the_healed_mega_with_ignition"
            in _activate(healed).active_ids)


def test_the_reload_names_the_energy_that_repays_a_full_bounce_in_one_attach():
    from common.cards.functions.energy import provision_units

    tags = {IGNITION_ENERGY: tuple(FUNCTIONS.tags(IGNITION_ENERGY))}
    reload_hint = next(hint for hint in STRATEGY.strategies
                       if hint.identifier == "mega_starmie.reload_the_healed_mega_with_ignition")

    assert reload_hint.desired_facts[0].target_card_ids == (IGNITION_ENERGY,)
    assert provision_units(tags, IGNITION_ENERGY, evolved=True) == len(
        STATS.attack(NEBULA_BEAM).energyTypes)
