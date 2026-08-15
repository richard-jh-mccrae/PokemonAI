from common.strategy.needs import (
    ActivatedNeed,
    ActivationCondition,
    DesiredFact,
    NeedStrategy,
    StrategyOverride,
    TurnNeedSnapshot,
    resolve_need_strategies,
    activate_need_strategies,
)
from common.strategy.strategy import Roles
from common.needs import StrategyBeamBuilder, semantic_action_key
from common.options import enumerate_legal_actions
from types import SimpleNamespace


def _rule(identifier="general.fund_active"):
    return NeedStrategy(
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
    resolved = resolve_need_strategies(
        (general,), (deck,),
        (StrategyOverride("general.fund_active", enabled=False),),
    )

    assert [row.identifier for row in resolved.effective] == ["mega_starmie.evolve_active"]
    assert resolved.content_hash == resolve_need_strategies(
        (general,), (deck,),
        (StrategyOverride("general.fund_active", enabled=False),),
    ).content_hash
    assert resolved.as_dict()["overrides"][0]["strategy_id"] == "general.fund_active"


def test_strategy_rejects_conflicting_recipient_declarations():
    import pytest
    with pytest.raises(ValueError, match="recipient"):
        NeedStrategy(
            identifier="general.bad", scope="general", conditions=(),
            desired_facts=(DesiredFact("fund_attack", "own.bench", 1),),
            recipient_selector="own.active", deadline="this_turn", confidence="high",
            provenance="general",
        )


def test_strategy_resolution_rejects_silent_replacement_and_unknown_override():
    import pytest

    with pytest.raises(ValueError, match="duplicate Needs strategy"):
        resolve_need_strategies((_rule(),), (_rule(),), ())
    with pytest.raises(ValueError, match="unknown Needs strategy override"):
        resolve_need_strategies((_rule(),), (), (StrategyOverride("missing", enabled=False),))


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


def test_turn_snapshot_is_hand_independent_and_recipient_specific():
    rule = NeedStrategy(
        "deck.evolve_active", "deck",
        (ActivationCondition("own.active.evolvable", "eq", True),),
        (DesiredFact("evolve", "own.active"),),
        "own.active", "this_turn", "high", "deck",
    )
    resolved = resolve_need_strategies((), (rule,), ())
    roles = Roles({11: ["win_condition"]}, evolves={10: 11})

    left = activate_need_strategies(_observation(hand=[]), resolved, roles=roles)
    right = activate_need_strategies(_observation(hand=[{"id": 11}]), resolved, roles=roles)

    assert left.snapshot_id == right.snapshot_id
    assert left.hints[0].recipient_serial == 77
    assert left.hints[0].target_card_ids == (11,)


def test_turn_snapshot_may_abstain():
    rule = NeedStrategy(
        "deck.never", "deck",
        (ActivationCondition("own.active.energy_count", "gt", 99),),
        (DesiredFact("fund_attack", "own.active"),),
        "own.active", "this_turn", "high", "deck",
    )
    resolved = resolve_need_strategies((), (rule,), ())

    snapshot = activate_need_strategies(_observation(hand=[]), resolved, roles=Roles())

    assert snapshot.hints == ()
    assert snapshot.active_ids == ()
    assert snapshot.inactive_ids == ("deck.never",)


def test_attack_ready_condition_uses_the_deployed_attack_provider():
    rule = NeedStrategy(
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

    snapshot = activate_need_strategies(
        observation, resolve_need_strategies((rule,), (), ()),
        roles=Roles({}), stats=Stats())

    assert snapshot.hints == ()
    assert snapshot.active_ids == ()
    assert snapshot.inactive_ids == ("general.fund",)


def test_strategy_beam_targets_the_declared_recipient_without_pruning_other_actions():
    rule = NeedStrategy(
        "deck.evolve_active", "deck",
        (ActivationCondition("own.active.evolvable", "eq", True),),
        (DesiredFact("evolve", "own.active"),),
        "own.active", "this_turn", "high", "deck",
    )
    roles = Roles({11: ["win_condition"]}, evolves={10: 11})
    observation = _observation(hand=[{"id": 11, "serial": 99}])
    observation["current"]["players"][0]["bench"] = [
        {"id": 10, "serial": 78, "energies": []},
    ]
    observation["select"]["option"] = [
        {"type": 9, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
        {"type": 9, "index": 0, "inPlayArea": 5, "inPlayIndex": 0},
        {"type": 14},
    ]
    snapshot = activate_need_strategies(
        observation, resolve_need_strategies((), (rule,), ()), roles=roles)
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
    rule = NeedStrategy(
        "deck.evolve_active", "deck",
        (ActivationCondition("own.active.evolvable", "eq", True),),
        (DesiredFact("evolve", "own.active"),),
        "own.active", "this_turn", "high", "deck",
    )
    roles = Roles({11: ["win_condition"]}, evolves={10: 11})
    observation = _observation(hand=[{"id": 50, "serial": 99}])
    observation["select"]["option"] = [{"type": 7, "index": 0}, {"type": 14}]
    snapshot = activate_need_strategies(
        observation, resolve_need_strategies((), (rule,), ()), roles=roles)
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
    rule = NeedStrategy(
        "general.information", "general",
        (ActivationCondition("own.active.energy_count", "lt", 1),),
        (DesiredFact("relevant_information", "turn"),),
        "turn", "immediate", "high", "general",
    )
    observation = _observation(hand=[{"id": 50, "serial": 99}])
    observation["select"]["option"] = [{"type": 7, "index": 0}, {"type": 14}]
    snapshot = activate_need_strategies(
        observation, resolve_need_strategies((rule,), (), ()), roles=Roles({}))
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


def test_information_need_wins_a_priority_tie_with_a_commitment_need():
    observation = _observation(hand=[{"id": 50}, {"id": 3}])
    observation["select"]["option"] = [
        {"type": 7, "index": 0},
        {"type": 8, "index": 1, "inPlayArea": 4, "inPlayIndex": 0},
    ]
    snapshot = TurnNeedSnapshot(4, 0, "hash", "snapshot", (), (), (
        ActivatedNeed("general.information", "relevant_information", "turn",
                      None, None, (), "immediate", "high"),
        ActivatedNeed("deck.fund", "fund_attack", "own.active",
                      10, 77, (), "immediate", "high"),
    ))

    class Effects:
        @staticmethod
        def clauses(card_id):
            return ({"kind": "fetch", "target": "pokemon", "zone": "deck"},) \
                if card_id == 50 else ()

    class Stats:
        @staticmethod
        def get(card_id):
            return SimpleNamespace(is_supporter=False, is_energy=card_id == 3,
                                   is_pokemon=card_id == 11, stage="basic")

    actions = enumerate_legal_actions(observation)
    beam = StrategyBeamBuilder(snapshot, effects=Effects(), stats=Stats()).build(
        SimpleNamespace(obs=observation, root_seat=0, deck_counts=((11, 1),)), actions)

    assert [row.family for row in beam.focused[:2]] == ["play", "attach"]


def test_cached_need_orders_a_forced_recovery_target():
    observation = _observation(hand=[])
    observation["current"]["players"][0]["discard"] = [{"id": 1030}, {"id": 3}]
    observation["select"] = {"context": 7, "minCount": 1, "maxCount": 1, "option": [
        {"type": 3, "playerIndex": 0, "area": 3, "index": 0},
        {"type": 3, "playerIndex": 0, "area": 3, "index": 1},
    ]}
    snapshot = TurnNeedSnapshot(4, 0, "hash", "snapshot", (), (), (
        ActivatedNeed("deck.deploy", "deploy", "own.bench",
                      None, None, (1030,), "this_turn", "high"),
    ))
    actions = enumerate_legal_actions(observation)

    beam = StrategyBeamBuilder(snapshot).build(
        SimpleNamespace(obs=observation, root_seat=0, deck_counts=()), actions)

    assert [row.action_key for row in beam.focused] == [
        semantic_action_key(next(action for action in actions if action.selection == (0,)))
    ]


def test_deploy_need_targets_declared_evolution_bases_when_none_are_in_play():
    rule = NeedStrategy(
        "deck.deploy_backup", "deck",
        (ActivationCondition("own.board.evolvable_count", "eq", 0),),
        (DesiredFact("deploy", "turn"),),
        "turn", "this_turn", "high", "deck",
    )
    roles = Roles({1031: ("win_condition",)}, evolves={1030: 1031})
    observation = _observation(hand=[])

    snapshot = activate_need_strategies(
        observation, resolve_need_strategies((), (rule,), ()), roles=roles)

    assert snapshot.hints == (
        ActivatedNeed("deck.deploy_backup", "deploy", "turn",
                      None, None, (1030,), "this_turn", "high"),
    )


def test_deploy_fetch_is_not_focused_without_a_remaining_evolution_payoff():
    observation = _observation(hand=[{"id": 50}])
    observation["select"]["option"] = [{"type": 7, "index": 0}]
    snapshot = TurnNeedSnapshot(4, 0, "hash", "snapshot", (), (), (
        ActivatedNeed("deck.deploy", "deploy", "turn",
                      None, None, (1030,), "this_turn", "high"),
    ))

    class Effects:
        @staticmethod
        def clauses(_card_id):
            return ({"kind": "fetch", "target": "pokemon", "zone": "deck"},)

    class Stats:
        @staticmethod
        def get(card_id):
            return SimpleNamespace(is_supporter=False, is_pokemon=card_id == 1030,
                                   stage="basic" if card_id == 1030 else None)

    registry = SimpleNamespace(line_parents={1031: 1030})
    beam = StrategyBeamBuilder(
        snapshot, effects=Effects(), stats=Stats(), registry=registry).build(
            SimpleNamespace(obs=observation, root_seat=0, deck_counts=((1030, 1),)),
            enumerate_legal_actions(observation),
        )

    assert beam.focused == ()


def test_shuffle_refresh_supporter_is_relevant_information():
    observation = _observation(hand=[{"id": 50}])
    observation["select"]["option"] = [{"type": 7, "index": 0}]
    snapshot = TurnNeedSnapshot(4, 0, "hash", "snapshot", (), (), (
        ActivatedNeed("general.information", "relevant_information", "turn",
                      None, None, (), "immediate", "high"),
    ))

    class Effects:
        @staticmethod
        def clauses(_card_id):
            return ({"kind": "draw", "amount": 5, "rider": "shuffle_own_hand_in"},)

    class Stats:
        @staticmethod
        def get(_card_id):
            return SimpleNamespace(is_supporter=True)

    beam = StrategyBeamBuilder(snapshot, effects=Effects(), stats=Stats()).build(
        SimpleNamespace(obs=observation, root_seat=0, deck_counts=((11, 10),)),
        enumerate_legal_actions(observation),
    )

    assert len(beam.focused) == 1
