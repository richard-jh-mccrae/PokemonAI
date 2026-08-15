from common.strategy.strategies import (
    ActivationCondition,
    DesiredFact,
    GENERAL_STRATEGIES,
    StrategyHint,
    StrategyOverride,
    resolve_strategies,
    activate_strategies,
)
from common.strategy.strategy import Roles
from common.demand import StrategyBeamBuilder, semantic_action_key
from common.options import enumerate_legal_actions
from types import SimpleNamespace


def test_shipped_deck_roles_name_only_pokemon():
    from agents.dragapult_ex.strategy import ROLES as dragapult_roles
    from agents.mega_lucario.strategy import ROLES as lucario_roles
    from agents.mega_starmie.strategy import ROLES as starmie_roles
    from common.scouting.provider import EngineCardStatProvider

    stats = EngineCardStatProvider()

    assert all(stats.get(card_id).is_pokemon
               for roles in (dragapult_roles, lucario_roles, starmie_roles)
               for card_id in roles)


def _rule(identifier="general.fund_active"):
    return StrategyHint(
        identifier=identifier,
        scope="general",
        conditions=(ActivationCondition("own.active.energy_count", "lt", 1),),
        desired_facts=(DesiredFact("fund_attack", "own.active", 1),),
        recipient_selector="own.active",
        deadline="this_turn",
        confidence="high",
        provenance="general",
    )


def test_strategy_resolution_is_serializable_stable_and_explicit():
    general = _rule()
    deck = _rule("mega_starmie.evolve_active")
    resolved = resolve_strategies(
        (general,), (deck,),
        overrides=(StrategyOverride("general.fund_active", enabled=False),),
    )

    assert [row.identifier for row in resolved.effective] == ["mega_starmie.evolve_active"]
    assert resolved.content_hash == resolve_strategies(
        (general,), (deck,),
        overrides=(StrategyOverride("general.fund_active", enabled=False),),
    ).content_hash
    assert resolved.as_dict()["overrides"][0]["strategy_id"] == "general.fund_active"


def test_strategy_resolution_combines_general_deck_and_opponent_layers():
    general = _rule()
    deck = _rule("deck.setup")
    opponent = StrategyHint(
        "opponent.pressure_engine", "opponent", (),
        (DesiredFact("damage_setup", "opponent.bench.highest_role"),),
        "opponent.bench.highest_role", "this_turn", "medium", "brief:test")

    resolved = resolve_strategies((general,), (deck,), (opponent,))

    assert resolved.general == (general,)
    assert resolved.deck == (deck,)
    assert resolved.opponent == (opponent,)
    assert {row.identifier for row in resolved.effective} == {
        "general.fund_active", "deck.setup", "opponent.pressure_engine"}


def test_strategy_rejects_conflicting_recipient_declarations():
    import pytest
    with pytest.raises(ValueError, match="recipient"):
        StrategyHint(
            identifier="general.bad", scope="general", conditions=(),
            desired_facts=(DesiredFact("fund_attack", "own.bench", 1),),
            recipient_selector="own.active", deadline="this_turn", confidence="high",
            provenance="general",
        )


def test_strategy_resolution_rejects_silent_replacement_and_unknown_override():
    import pytest

    with pytest.raises(ValueError, match="duplicate strategy"):
        resolve_strategies((_rule(),), (_rule(),), ())
    with pytest.raises(ValueError, match="unknown strategy override"):
        resolve_strategies(
            (_rule(),), overrides=(StrategyOverride("missing", enabled=False),))


def _observation(*, hand):
    return {
        "current": {
            "turn": 4,
            "yourIndex": 0,
            "energyAttached": False,
            "players": [
                {"active": [{"id": 10, "serial": 77, "energies": []}],
                 "bench": [], "hand": hand},
                {"active": [{"id": 20, "serial": 88, "energies": []}], "bench": []},
            ],
        },
        "select": {"context": 0, "option": []},
    }


def test_strategy_snapshot_is_hand_independent_and_recipient_specific():
    rule = StrategyHint(
        "deck.evolve_active", "deck",
        (ActivationCondition("own.active.evolvable", "eq", True),),
        (DesiredFact("evolve", "own.active"),),
        "own.active", "this_turn", "high", "deck",
    )
    resolved = resolve_strategies((), (rule,), ())
    roles = Roles({11: ["primary_attacker"]}, evolves={10: 11})

    left = activate_strategies(_observation(hand=[]), resolved, roles=roles)
    right = activate_strategies(_observation(hand=[{"id": 11}]), resolved, roles=roles)

    assert left.snapshot_id == right.snapshot_id
    assert left.hints[0].recipient_serial == 77
    assert left.hints[0].target_card_ids == (11,)


def test_strategy_relevant_new_information_creates_a_new_snapshot():
    rule = StrategyHint(
        "deck.deploy", "deck",
        (ActivationCondition("own.bench.card_ids", "not_contains", 11),),
        (DesiredFact("deploy", "own.bench", target_card_ids=(11,)),),
        "own.bench", "this_turn", "high", "deck")
    resolved = resolve_strategies((), (rule,))
    before = _observation(hand=[])
    after = _observation(hand=[])
    after["current"]["players"][0]["bench"] = [
        {"id": 11, "serial": 78, "energies": []}]

    left = activate_strategies(before, resolved, roles=Roles({}))
    right = activate_strategies(after, resolved, roles=Roles({}))

    assert left.snapshot_id != right.snapshot_id
    assert left.active_ids == ("deck.deploy",)
    assert right.inactive_ids == ("deck.deploy",)


def test_turn_snapshot_may_abstain():
    rule = StrategyHint(
        "deck.never", "deck",
        (ActivationCondition("own.active.energy_count", "gt", 99),),
        (DesiredFact("fund_attack", "own.active"),),
        "own.active", "this_turn", "high", "deck",
    )
    resolved = resolve_strategies((), (rule,), ())

    snapshot = activate_strategies(_observation(hand=[]), resolved, roles=Roles())

    assert snapshot.hints == ()
    assert snapshot.active_ids == ()
    assert snapshot.inactive_ids == ("deck.never",)


def test_attack_ready_condition_uses_the_deployed_attack_provider():
    rule = StrategyHint(
        "general.fund", "general",
        (ActivationCondition("own.active.attack_ready", "eq", False),),
        (DesiredFact("fund_attack", "own.active"),),
        "own.active", "this_turn", "high", "general",
    )
    observation = _observation(hand=[])
    observation["current"]["players"][0]["active"][0]["energies"] = [3, 3]

    class Stats:
        @staticmethod
        def get(_card_id):
            return SimpleNamespace(attacks=(90, 91))

        @staticmethod
        def attack(attack_id):
            return SimpleNamespace(energyTypes=(3,) if attack_id == 90 else (3, 3))

    snapshot = activate_strategies(
        observation, resolve_strategies((rule,), (), ()),
        roles=Roles({}), stats=Stats())

    assert snapshot.hints == ()
    assert snapshot.active_ids == ()
    assert snapshot.inactive_ids == ("general.fund",)


def test_general_funding_strategy_accepts_primary_and_backup_attackers():
    class Stats:
        @staticmethod
        def get(_card_id):
            return SimpleNamespace(attacks=(90,))

        @staticmethod
        def attack(_attack_id):
            return SimpleNamespace(energyTypes=(3,))

    for role in ("primary_attacker", "backup_attacker"):
        snapshot = activate_strategies(
            _observation(hand=[]), resolve_strategies(GENERAL_STRATEGIES),
            roles=Roles({10: [role]}), stats=Stats())
        assert "general.fund_active_attacker" in snapshot.active_ids


def test_strategy_beam_targets_the_declared_recipient_without_pruning_other_actions():
    rule = StrategyHint(
        "deck.evolve_active", "deck",
        (ActivationCondition("own.active.evolvable", "eq", True),),
        (DesiredFact("evolve", "own.active"),),
        "own.active", "this_turn", "high", "deck",
    )
    roles = Roles({11: ["primary_attacker"]}, evolves={10: 11})
    observation = _observation(hand=[{"id": 11, "serial": 99}])
    observation["current"]["players"][0]["bench"] = [
        {"id": 10, "serial": 78, "energies": []},
    ]
    observation["select"]["option"] = [
        {"type": 9, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
        {"type": 9, "index": 0, "inPlayArea": 5, "inPlayIndex": 0},
        {"type": 14},
    ]
    snapshot = activate_strategies(
        observation, resolve_strategies((), (rule,), ()), roles=roles)
    actions = enumerate_legal_actions(observation)

    beam = StrategyBeamBuilder(snapshot).build(
        SimpleNamespace(obs=observation, root_seat=0, deck_counts=((11, 1),)), actions)

    active = next(action for action in actions if action.selection == (0,))
    bench = next(action for action in actions if action.selection == (1,))
    end = next(action for action in actions if action.selection == (2,))
    assert [row.action_key for row in beam.focused] == [semantic_action_key(active)]
    assert semantic_action_key(bench) in {row.action_key for row in beam.inactive}
    assert semantic_action_key(end) in {row.action_key for row in beam.safety}


def test_live_odds_refresh_against_the_cached_turn_snapshot():
    rule = StrategyHint(
        "deck.evolve_active", "deck",
        (ActivationCondition("own.active.evolvable", "eq", True),),
        (DesiredFact("evolve", "own.active"),),
        "own.active", "this_turn", "high", "deck",
    )
    roles = Roles({11: ["primary_attacker"]}, evolves={10: 11})
    observation = _observation(hand=[{"id": 50, "serial": 99}])
    observation["select"]["option"] = [{"type": 7, "index": 0}, {"type": 14}]
    snapshot = activate_strategies(
        observation, resolve_strategies((), (rule,), ()), roles=roles)
    actions = enumerate_legal_actions(observation)

    class Effects:
        @staticmethod
        def clauses(card_id):
            return ({"kind": "draw", "amount": 1},) if card_id == 50 else ()

    reachable = StrategyBeamBuilder(snapshot, effects=Effects()).build(
        SimpleNamespace(obs=observation, root_seat=0, deck_counts=((11, 1), (12, 9))),
        actions,
    )
    unreachable = StrategyBeamBuilder(snapshot, effects=Effects()).build(
        SimpleNamespace(obs=observation, root_seat=0, deck_counts=((12, 10),)), actions)

    assert snapshot.snapshot_id
    assert {row.family for row in reachable.focused} == {"play"}
    assert unreachable.focused == ()


def test_information_hint_includes_free_search_but_excludes_discard_commitments():
    rule = StrategyHint(
        "general.information", "general",
        (ActivationCondition("own.active.energy_count", "lt", 1),),
        (DesiredFact("low_cost_information_access", "turn"),),
        "turn", "immediate", "high", "general",
    )
    observation = _observation(hand=[{"id": 50, "serial": 99}])
    observation["select"]["option"] = [{"type": 7, "index": 0}, {"type": 14}]
    snapshot = activate_strategies(
        observation, resolve_strategies((rule,), (), ()), roles=Roles({}))
    actions = enumerate_legal_actions(observation)

    class Effects:
        @staticmethod
        def clauses(_card_id):
            return ({"kind": "fetch", "target": "pokemon", "zone": "deck",
                     "cost": "discard_2", "cost_required": True},)

    class Stats:
        @staticmethod
        def get(card_id):
            return SimpleNamespace(is_supporter=False, is_pokemon=card_id == 11,
                                   stage="basic" if card_id == 11 else None)

    beam = StrategyBeamBuilder(snapshot, effects=Effects(), stats=Stats()).build(
        SimpleNamespace(obs=observation, root_seat=0, deck_counts=((11, 1),)), actions)

    assert beam.focused == ()

    class FreeSearch:
        @staticmethod
        def clauses(_card_id):
            return ({"kind": "fetch", "target": "pokemon", "zone": "deck"},)

    free_beam = StrategyBeamBuilder(
        snapshot, effects=FreeSearch(), stats=Stats()).build(
            SimpleNamespace(obs=observation, root_seat=0, deck_counts=((11, 1),)), actions)

    assert len(free_beam.focused) == 1
    assert free_beam.focused[0].path_ids == ("general.information",)


def test_low_cost_information_strategy_focuses_a_draw_ability():
    rule = StrategyHint(
        "general.information", "general", (),
        (DesiredFact("low_cost_information_access", "turn"),),
        "turn", "immediate", "high", "general")
    observation = _observation(hand=[])
    observation["select"]["option"] = [
        {"type": 10, "area": 4, "index": 0}, {"type": 14}]
    snapshot = activate_strategies(
        observation, resolve_strategies((rule,)), roles=Roles({}))
    actions = enumerate_legal_actions(observation)

    class Effects:
        @staticmethod
        def clauses(card_id):
            return ({"kind": "draw", "amount": 1},) if card_id == 10 else ()

    class Stats:
        @staticmethod
        def get(_card_id):
            return SimpleNamespace(is_supporter=False)

    beam = StrategyBeamBuilder(snapshot, effects=Effects(), stats=Stats()).build(
        SimpleNamespace(obs=observation, root_seat=0, deck_counts=((11, 1),)), actions)

    assert [row.family for row in beam.focused] == ["ability"]


def test_deploy_strategy_focuses_the_declared_basic():
    rule = StrategyHint(
        "deck.deploy_staryu", "deck", (),
        (DesiredFact("deploy", "own.bench", target_card_ids=(1030,)),),
        "own.bench", "immediate", "high", "deck")
    observation = _observation(hand=[{"id": 1030, "serial": 99}])
    observation["select"]["option"] = [{"type": 7, "index": 0}, {"type": 14}]
    snapshot = activate_strategies(
        observation, resolve_strategies((), (rule,)), roles=Roles({}))
    actions = enumerate_legal_actions(observation)

    class Stats:
        @staticmethod
        def get(card_id):
            return SimpleNamespace(is_pokemon=card_id == 1030, stage="basic")

    beam = StrategyBeamBuilder(snapshot, stats=Stats()).build(
        SimpleNamespace(obs=observation, root_seat=0, deck_counts=()), actions)

    assert [row.family for row in beam.focused] == ["play"]


def test_damage_setup_strategy_focuses_a_bench_snipe_attack():
    rule = StrategyHint(
        "deck.soften_role_target", "deck",
        (ActivationCondition("opponent.bench.role_target_count", "gt", 0),),
        (DesiredFact("damage_setup", "opponent.bench.highest_role"),),
        "opponent.bench.highest_role", "this_turn", "medium", "deck")
    observation = _observation(hand=[])
    observation["current"]["players"][1]["bench"] = [
        {"id": 20, "serial": 89, "hp": 100, "energies": []}]
    observation["select"]["option"] = [{"type": 13, "attackId": 90}, {"type": 14}]

    class Stats:
        @staticmethod
        def attack(_attack_id):
            return SimpleNamespace(benchSnipe=30)

    snapshot = activate_strategies(
        observation, resolve_strategies((), (rule,)), roles=Roles({}),
        opponent_role_worth={20: 30.0})
    actions = enumerate_legal_actions(observation)
    beam = StrategyBeamBuilder(snapshot, stats=Stats()).build(
        SimpleNamespace(obs=observation, root_seat=0, deck_counts=()), actions)

    assert [row.family for row in beam.focused] == ["attack"]
    assert [row.family for row in beam.safety] == ["attack", "end"]
