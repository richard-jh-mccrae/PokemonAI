from common.strategy.strategies import (
    ActivatedStrategy,
    ActivationCondition,
    DesiredFact,
    GENERAL_STRATEGIES,
    StrategyHint,
    StrategyOverride,
    StrategySnapshot,
    resolve_strategies,
    activate_strategies,
    strategy_hint_from_dict,
)
from common.strategy.strategy import Roles
from common.demand import StrategyBeamBuilder, semantic_action_key
from common.effects import CardEffects
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
        conviction="high",
        provenance="general",
        bundle_id="turn.attack",
        waypoint=1,
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
    assert resolved.as_dict()["general"][0]["conviction"] == "high"
    assert "confidence" not in resolved.as_dict()["general"][0]
    assert resolved.as_dict()["general"][0]["bundle_id"] == "turn.attack"
    assert resolved.as_dict()["general"][0]["waypoint"] == 1


def test_legacy_strategy_confidence_loads_as_authored_conviction():
    loaded = strategy_hint_from_dict({
        "identifier": "brief.legacy",
        "conditions": [],
        "desired_facts": [{"kind": "fund_attack", "recipient": "own.active"}],
        "recipient_selector": "own.active",
        "deadline": "this_turn",
        "confidence": "medium",
    }, scope="opponent", provenance="brief:test")

    assert loaded.conviction == "medium"
    assert loaded.bundle_id is None
    assert loaded.waypoint == 0


def test_strategy_bundle_metadata_reaches_the_planning_snapshot():
    snapshot = activate_strategies(
        _observation(hand=[]), resolve_strategies((_rule(),)), roles=Roles({}))

    assert snapshot.hints[0].conviction == "high"
    assert snapshot.hints[0].bundle_id == "turn.attack"
    assert snapshot.hints[0].waypoint == 1


def test_this_turn_urgency_rises_when_the_branch_reaches_closing_actions():
    hint = ActivatedStrategy(
        "deck.attack", "fund_attack", "own.active", 10, 77, (),
        "this_turn", "high", "turn.attack", 0)
    snapshot = StrategySnapshot(4, 0, "hash", "snapshot", (), (), (hint,))
    builder = StrategyBeamBuilder(snapshot)
    open_state = SimpleNamespace(obs=_observation(hand=[]), root_seat=0)
    closing = _observation(hand=[])
    closing["select"]["option"] = [{"type": 13, "attackId": 1}]
    closing_state = SimpleNamespace(obs=closing, root_seat=0)

    assert builder.urgency(open_state, hint) == "medium"
    assert builder.urgency(closing_state, hint) == "high"


def test_missing_damage_setup_recipient_is_satisfied_not_impossible():
    hint = ActivatedStrategy(
        "deck.snipe", "damage_setup", "opponent.bench.highest_role",
        20, 999, (), "this_turn", "high", "turn.attack", 2)
    snapshot = StrategySnapshot(4, 0, "hash", "snapshot", (), (), (hint,))
    state = SimpleNamespace(obs=_observation(hand=[]), root_seat=0)

    assert StrategyBeamBuilder(snapshot).outcome_statuses(state)[0]["status"] == "satisfied"


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
            recipient_selector="own.active", deadline="this_turn", conviction="high",
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


def test_heal_hint_ignores_play_actions_without_a_source_card():
    hint = SimpleNamespace(
        kind="heal", target_card_ids=(), recipient_serial=None,
        strategy_id="deck.heal", deadline="this_turn", conviction="high")
    snapshot = SimpleNamespace(hints=(hint,))
    action = SimpleNamespace(identity=SimpleNamespace(kind="play"), selection=(0,))
    state = SimpleNamespace(
        obs={"select": {"option": [{}]}, "current": {"players": [{}, {}]}},
        root_seat=0, deck_counts=())

    class Effects:
        @staticmethod
        def clauses(card_id):
            assert card_id is not None
            return ()

    beam = StrategyBeamBuilder(snapshot, effects=Effects()).build(state, [action])

    assert beam.focused == ()


def _engine_play(index):
    """A Play exactly as `cg.game` emits it — EVERY field present, unused ones ``None``. The
    hand-written `{"type": 7, "index": 0}` used elsewhere here omits `area` entirely, a shape the
    engine never produces, so it cannot exercise the source-card lookup the way a real match does."""
    return {"area": None, "attackId": None, "cardId": None, "count": None, "energyIndex": None,
            "inPlayArea": None, "inPlayIndex": None, "index": index, "number": None,
            "playerIndex": None, "serial": None, "specialConditionType": None,
            "toolIndex": None, "type": 7}


def _heal_beam(option):
    rule = StrategyHint(
        "general.heal_damaged_active_attacker", "general",
        (ActivationCondition("own.active.role", "contains", "primary_attacker"),
         ActivationCondition("own.active.hp_fraction", "lt", 0.70)),
        (DesiredFact("heal", "own.active"),),
        "own.active", "immediate", "high", "general",
    )
    observation = _observation(hand=[{"id": 50, "serial": 99}])
    observation["current"]["players"][0]["active"] = [
        {"id": 10, "serial": 77, "energies": [], "hp": 30, "maxHp": 100}]
    observation["select"]["option"] = [option, {"type": 14}]
    snapshot = activate_strategies(
        observation, resolve_strategies((rule,), (), ()), roles=Roles({10: ["primary_attacker"]}))
    # The REAL CardEffects, not a stub: its `int(card_id)` lookup is the thing that raised.
    effects = CardEffects({"50": [{"kind": "heal", "amount": 30}]})

    actions = enumerate_legal_actions(observation)
    beam = StrategyBeamBuilder(snapshot, effects=effects).build(
        SimpleNamespace(obs=observation, root_seat=0, deck_counts=()), actions)
    return beam, next(action for action in actions if action.identity.kind == "play")


def test_heal_hint_reads_an_engine_shaped_play_and_survives_an_unresolvable_one():
    beam, play = _heal_beam(_engine_play(0))
    assert semantic_action_key(play) in {row.action_key for row in beam.focused}

    # An index past the hand names no card. Score it zero — never hand `None` to a clause lookup,
    # which raised TypeError and killed the whole agent process mid-Match.
    beam, play = _heal_beam(_engine_play(9))
    assert semantic_action_key(play) in {row.action_key for row in beam.inactive}


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


def test_cached_strategy_orders_a_forced_recovery_target():
    observation = _observation(hand=[])
    observation["current"]["players"][0]["discard"] = [{"id": 1030}, {"id": 3}]
    observation["select"] = {"context": 7, "minCount": 1, "maxCount": 1, "option": [
        {"type": 3, "playerIndex": 0, "area": 3, "index": 0},
        {"type": 3, "playerIndex": 0, "area": 3, "index": 1},
    ]}
    snapshot = StrategySnapshot(4, 0, "hash", "snapshot", (), (), (
        ActivatedStrategy("deck.deploy", "deploy", "own.bench",
                          None, None, (1030,), "this_turn", "high"),
    ))
    actions = enumerate_legal_actions(observation)

    beam = StrategyBeamBuilder(snapshot).build(
        SimpleNamespace(obs=observation, root_seat=0, deck_counts=()), actions)

    assert [row.action_key for row in beam.focused] == [
        semantic_action_key(next(action for action in actions if action.selection == (0,)))
    ]


def test_deploy_fetch_is_not_focused_without_a_remaining_evolution_payoff():
    observation = _observation(hand=[{"id": 50}])
    observation["select"]["option"] = [{"type": 7, "index": 0}]
    snapshot = StrategySnapshot(4, 0, "hash", "snapshot", (), (), (
        ActivatedStrategy("deck.deploy", "deploy", "own.bench",
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


def test_accelerator_clauses_earn_funding_access_odds():
    # An accel card is an OUT for a fund_attack demand: Crispin-class clauses previously scored
    # access odds 0.0 and never entered the focused beam.
    hint = SimpleNamespace(
        kind="fund_attack", target_card_ids=(), recipient_serial=77,
        strategy_id="general.fund_active_attacker", deadline="this_turn", conviction="high")
    snapshot = SimpleNamespace(hints=(hint,))
    observation = _observation(hand=[{"id": 1198, "serial": 5, "playerIndex": 0}])
    observation["select"]["option"] = [{"type": 7, "index": 0}, {"type": 14}]

    class Effects:
        @staticmethod
        def clauses(card_id):
            return (({"kind": "accel", "amount": 1, "source": "deck", "energy": "basic"},)
                    if card_id == 1198 else ())

    class Stats:
        @staticmethod
        def get(card_id):
            return SimpleNamespace(is_supporter=card_id == 1198, is_pokemon=False,
                                   is_energy=card_id == 906, is_basic_energy=card_id == 906,
                                   energyType=3)

    actions = enumerate_legal_actions(observation)
    beam = StrategyBeamBuilder(snapshot, effects=Effects(), stats=Stats()).build(
        SimpleNamespace(obs=observation, root_seat=0, deck_counts=((906, 4),)), actions)

    play = next(action for action in actions if action.identity.kind == "play")
    assert semantic_action_key(play) in {row.action_key for row in beam.focused}


def test_damage_boost_hint_prioritizes_the_boost_play():
    hint = SimpleNamespace(
        kind="damage_boost", target_card_ids=(), recipient_serial=None,
        strategy_id="general.boost_the_committed_attack", deadline="this_turn",
        conviction="medium")
    snapshot = SimpleNamespace(hints=(hint,))
    observation = _observation(hand=[{"id": 1141, "serial": 5, "playerIndex": 0}])
    observation["select"]["option"] = [{"type": 7, "index": 0}, {"type": 14}]

    class Effects:
        @staticmethod
        def clauses(card_id):
            return ({"kind": "damage_boost"},) if card_id == 1141 else ()

    class Stats:
        @staticmethod
        def get(_card_id):
            return SimpleNamespace(is_supporter=False, is_pokemon=False)

    actions = enumerate_legal_actions(observation)
    beam = StrategyBeamBuilder(snapshot, effects=Effects(), stats=Stats()).build(
        SimpleNamespace(obs=observation, root_seat=0, deck_counts=()), actions)

    play = next(action for action in actions if action.identity.kind == "play")
    assert semantic_action_key(play) in {row.action_key for row in beam.focused}


def test_boost_general_strategy_is_declared():
    assert "general.boost_the_committed_attack" in {
        hint.identifier for hint in GENERAL_STRATEGIES}


def test_boost_hint_survives_the_committed_attack_it_names():
    """PR #533 review: after the manual attach, a boost Trainer can still pay onto the offered
    attack — the old commitment_available gate turned the hint off in exactly that spot."""
    observation = _observation(hand=[])
    observation["current"]["energyAttached"] = True     # attach committed, Active not evolvable
    observation["select"]["option"] = [{"type": 13, "attackId": 1}, {"type": 14}]

    snapshot = activate_strategies(
        observation, resolve_strategies(GENERAL_STRATEGIES), roles=Roles({}))

    assert "general.boost_the_committed_attack" in snapshot.active_ids


def test_boost_hint_rests_with_no_commitment_and_no_offered_attack():
    observation = _observation(hand=[])
    observation["current"]["energyAttached"] = True
    observation["select"]["option"] = [{"type": 14}]    # End only: nothing to boost

    snapshot = activate_strategies(
        observation, resolve_strategies(GENERAL_STRATEGIES), roles=Roles({}))

    assert "general.boost_the_committed_attack" not in snapshot.active_ids


def test_damage_setup_hint_matches_a_spread_attacker():
    hint = SimpleNamespace(
        kind="damage_setup", target_card_ids=(), recipient_serial=88,
        strategy_id="deck.setup", deadline="this_turn", conviction="high")
    snapshot = SimpleNamespace(hints=(hint,))
    observation = _observation(hand=[])
    observation["current"]["players"][1]["bench"] = [{"id": 30, "serial": 88}]
    observation["select"]["option"] = [{"type": 13, "attackId": 500}, {"type": 14}]

    class Stats:
        @staticmethod
        def get(_card_id):
            return SimpleNamespace(is_supporter=False, is_pokemon=True)

        @staticmethod
        def attack(_attack_id):
            return SimpleNamespace(benchSnipe=0, benchSpread=60)

    actions = enumerate_legal_actions(observation)
    beam = StrategyBeamBuilder(snapshot, effects=None, stats=Stats()).build(
        SimpleNamespace(obs=observation, root_seat=0, deck_counts=()), actions)

    attack = next(action for action in actions if action.identity.kind == "attack")
    assert semantic_action_key(attack) in {row.action_key for row in beam.focused}



def _coverage_observation(hand_ids, *, bench_ids=()):
    observation = _observation(hand=[
        {"id": card_id, "serial": 90 + index, "playerIndex": 0}
        for index, card_id in enumerate(hand_ids)])
    observation["current"]["players"][0]["bench"] = [
        {"id": card_id, "serial": 60 + index, "energies": []}
        for index, card_id in enumerate(bench_ids)]
    observation["select"]["option"] = [
        *({"type": 7, "index": index} for index in range(len(hand_ids))),
        {"type": 14},
    ]
    return observation


def _deploy_hint(strategy_id, targets, *, deadline="immediate", conviction="high",
                 waypoint=0):
    return ActivatedStrategy(
        strategy_id, "deploy", "own.bench", None, None, tuple(targets),
        deadline, conviction, None, waypoint)


class _BasicStats:
    @staticmethod
    def get(_card_id):
        return SimpleNamespace(is_pokemon=True, stage="basic", is_supporter=False,
                               is_energy=False)


def _coverage_beam(hints, hand_ids, *, bench_ids=(), sequence_coverage=True,
                   prefix_outcomes=()):
    observation = _coverage_observation(hand_ids, bench_ids=bench_ids)
    snapshot = StrategySnapshot(4, 0, "hash", "snapshot", (), (), tuple(hints))
    builder = StrategyBeamBuilder(
        snapshot, stats=_BasicStats(), sequence_coverage=sequence_coverage)
    builder.prefix_outcomes = tuple(prefix_outcomes)
    actions = enumerate_legal_actions(observation)
    beam = builder.build(
        SimpleNamespace(obs=observation, root_seat=0, deck_counts=()), actions)
    plays = {action.selection[0]: semantic_action_key(action)
             for action in actions if action.identity.kind == "play"}
    return beam, plays, builder


def test_one_high_need_outranks_any_number_of_weaker_needs():
    hints = (
        _deploy_hint("deck.primary", (101,)),
        *(_deploy_hint(f"deck.minor_{index}", (102, 200 + index),
                       deadline="next_turn", conviction="low")
          for index in range(5)),
    )

    beam, plays, _builder = _coverage_beam(hints, (101, 102))

    assert [row.action_key for row in beam.focused] == [plays[0], plays[1]]


def test_equal_primary_tier_prefers_the_line_with_more_distinct_outcomes():
    hints = (
        _deploy_hint("deck.alpha", (101,)),
        _deploy_hint("deck.beta", (102,)),
        _deploy_hint("deck.beta_extra", (102, 300),
                     deadline="next_turn", conviction="low"),
    )

    beam, plays, _builder = _coverage_beam(hints, (101, 102))

    assert [row.action_key for row in beam.focused] == [plays[1], plays[0]]
    by_key = {row.action_key: row for row in beam.focused}
    assert len(by_key[plays[1]].coverage) == 2
    assert len(by_key[plays[0]].coverage) == 1


def test_duplicate_desired_outcomes_count_once():
    duplicated = (
        _deploy_hint("deck.alpha", (101,)),
        _deploy_hint("deck.beta_one", (102,)),
        _deploy_hint("deck.beta_two", (102,)),
    )
    single = (
        _deploy_hint("deck.alpha", (101,)),
        _deploy_hint("deck.beta_one", (102,)),
    )

    left, plays, _builder = _coverage_beam(duplicated, (101, 102))
    right, _plays, _builder = _coverage_beam(single, (101, 102))

    assert [row.action_key for row in left.focused] == [
        row.action_key for row in right.focused]
    assert all(len(row.coverage) == 1 for row in left.focused)


def test_renaming_and_reordering_strategy_identifiers_keeps_search_order():
    hints = (
        _deploy_hint("deck.alpha", (101,)),
        _deploy_hint("deck.beta", (102,)),
        _deploy_hint("deck.beta_extra", (102, 300),
                     deadline="next_turn", conviction="low"),
    )
    renamed = tuple(reversed((
        _deploy_hint("zzz.renamed_1", (101,)),
        _deploy_hint("aaa.renamed_2", (102,)),
        _deploy_hint("mmm.renamed_3", (102, 300),
                     deadline="next_turn", conviction="low"),
    )))

    left, _plays, _builder = _coverage_beam(hints, (101, 102))
    right, _plays, _builder = _coverage_beam(renamed, (101, 102))

    assert [row.action_key for row in left.focused] == [
        row.action_key for row in right.focused]


def test_general_and_deck_scope_share_one_need_set_without_precedence():
    def resolved_beam(general_targets, deck_targets):
        general = StrategyHint(
            "general.deploy", "general", (),
            (DesiredFact("deploy", "own.bench", target_card_ids=general_targets),),
            "own.bench", "immediate", "high", "general")
        deck = StrategyHint(
            "deck.deploy", "deck", (),
            (DesiredFact("deploy", "own.bench", target_card_ids=deck_targets),),
            "own.bench", "immediate", "high", "deck")
        observation = _coverage_observation((101, 102))
        snapshot = activate_strategies(
            observation, resolve_strategies((general,), (deck,)), roles=Roles({}))
        actions = enumerate_legal_actions(observation)
        beam = StrategyBeamBuilder(
            snapshot, stats=_BasicStats(), sequence_coverage=True).build(
            SimpleNamespace(obs=observation, root_seat=0, deck_counts=()), actions)
        return [row.action_key for row in beam.focused]

    assert resolved_beam((101,), (102,)) == resolved_beam((102,), (101,))


def test_satisfied_and_impossible_outcomes_stop_contributing_coverage():
    hints = (
        _deploy_hint("deck.alpha", (101,)),
        _deploy_hint("deck.beta", (102,)),
        _deploy_hint("deck.beta_satisfied", (102, 400)),
    )

    beam, plays, _builder = _coverage_beam(hints, (101, 102), bench_ids=(400,))
    by_key = {row.action_key: row for row in beam.focused}
    assert len(by_key[plays[1]].coverage) == 1

    observation = _coverage_observation((101, 102))
    snapshot = StrategySnapshot(4, 0, "hash", "snapshot", (), (), (
        _deploy_hint("deck.alpha", (101,)),
        _deploy_hint("deck.beta", (102,)),
        _deploy_hint("deck.beta_dead", (102, 500)),
    ))
    builder = StrategyBeamBuilder(
        snapshot, stats=_BasicStats(), sequence_coverage=True)
    builder.last_reachability["deck.beta_dead"] = "impossible"
    actions = enumerate_legal_actions(observation)
    beam = builder.build(
        SimpleNamespace(obs=observation, root_seat=0, deck_counts=()), actions)
    by_key = {row.action_key: row for row in beam.focused}
    plays = {action.selection[0]: semantic_action_key(action)
             for action in actions if action.identity.kind == "play"}
    assert len(by_key[plays[1]].coverage) == 1


def test_unknown_reachability_fails_open_and_never_prunes():
    hints = (_deploy_hint("deck.alpha", (101,)),)

    beam, plays, _builder = _coverage_beam(hints, (101, 102))

    statuses = {row["strategy_id"]: row["status"] for row in beam.paths}
    assert statuses["deck.alpha"] in {"unknown", "guaranteed"}
    assert plays[1] in {row.action_key for row in beam.inactive}
    assert plays[0] in {row.action_key for row in beam.focused}


def test_extra_coverage_beyond_the_cap_cannot_reorder():
    def order(first_extras, second_extras):
        hints = (
            _deploy_hint("deck.alpha", (101,)),
            _deploy_hint("deck.beta", (102,)),
            *(_deploy_hint(f"deck.a_extra_{index}", (101, 600 + index),
                           deadline="next_turn", conviction="low")
              for index in range(first_extras)),
            *(_deploy_hint(f"deck.b_extra_{index}", (102, 700 + index),
                           deadline="next_turn", conviction="low")
              for index in range(second_extras)),
        )
        beam, _plays, _builder = _coverage_beam(hints, (101, 102))
        return [row.action_key for row in beam.focused]

    assert order(5, 8) == order(8, 5)


def test_prefix_outcomes_stop_recounting_already_advanced_outcomes():
    hints = (
        _deploy_hint("deck.alpha", (101,)),
        _deploy_hint("deck.beta", (102,)),
        _deploy_hint("deck.beta_extra", (102, 300),
                     deadline="next_turn", conviction="low"),
    )
    reference, plays, _builder = _coverage_beam(hints, (101, 102))
    extra_key = next(
        key for key in
        {row.action_key: row for row in reference.focused}[plays[1]].coverage
        if "300" in key)

    beam, plays, _builder = _coverage_beam(
        hints, (101, 102), prefix_outcomes=(extra_key,))

    by_key = {row.action_key: row for row in beam.focused}
    assert len(by_key[plays[1]].coverage) == 1
    assert len(by_key[plays[0]].coverage) == 1


def test_sequence_coverage_off_keeps_the_legacy_scalar_order():
    hints = (
        _deploy_hint("deck.alpha", (101,)),
        _deploy_hint("deck.beta", (102,)),
        _deploy_hint("deck.beta_extra", (102, 300),
                     deadline="next_turn", conviction="low"),
    )

    beam, plays, _builder = _coverage_beam(hints, (101, 102), sequence_coverage=False)

    assert {row.action_key for row in beam.focused} == {plays[0], plays[1]}
    assert all(row.coverage == () for row in beam.focused)
    assert sorted(row.action_key for row in beam.focused) == [
        row.action_key for row in beam.focused]


def test_combined_coverage_reports_best_tier_and_ordered_distinct_outcomes():
    from common.demand import SequenceCoverage, combined_coverage

    merged = combined_coverage((
        SequenceCoverage((1.0, 2.0), ("deploy|a", "deploy|b")),
        SequenceCoverage((3.0, 1.0), ("deploy|b", "evolve|c")),
        SequenceCoverage(),
    ))

    assert merged.tier == (3.0, 1.0)
    assert merged.outcomes == ("deploy|a", "deploy|b", "evolve|c")
    assert combined_coverage(()).tier == (0.0, 0.0)


def test_riolu_primary_line_with_lunatone_coverage_searches_first():
    from common.demand import combined_coverage

    riolu, riolu_evolution, lunatone = 333, 678, 500
    hints = (
        ActivatedStrategy(
            "mega_lucario.develop_riolu", "evolve", "own.active", riolu, 77,
            (riolu_evolution,), "immediate", "high", "lucario.turn", 0),
        ActivatedStrategy(
            "mega_lucario.establish_lunatone", "deploy", "own.bench", None, None,
            (lunatone,), "this_turn", "medium", "lucario.engine", 0),
    )
    observation = _observation(hand=[
        {"id": riolu_evolution, "serial": 90, "playerIndex": 0},
        {"id": lunatone, "serial": 91, "playerIndex": 0},
    ])
    observation["current"]["players"][0]["active"] = [
        {"id": riolu, "serial": 77, "energies": []}]
    observation["select"]["option"] = [
        {"type": 9, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
        {"type": 7, "index": 1},
        {"type": 14},
    ]
    snapshot = StrategySnapshot(4, 0, "hash", "snapshot", (), (), hints)

    class Stats:
        @staticmethod
        def get(card_id):
            return SimpleNamespace(
                is_pokemon=True, is_energy=False, is_supporter=False,
                stage="basic" if card_id == lunatone else "stage1",
                evolvesFrom=None if card_id == lunatone else "Riolu")

    state = SimpleNamespace(obs=observation, root_seat=0, deck_counts=())
    actions = enumerate_legal_actions(observation)
    builder = StrategyBeamBuilder(snapshot, stats=Stats(), sequence_coverage=True)
    beam = builder.build(state, actions)

    evolve = next(action for action in actions if action.selection == (0,))
    deploy = next(action for action in actions if action.selection == (1,))
    # The contextual primary need is Riolu development: its line searches first.
    assert [row.action_key for row in beam.focused] == [
        semantic_action_key(evolve), semantic_action_key(deploy)]

    # At the same primary tier, the line that also establishes Lunatone carries more
    # distinct coverage than the line that only develops Riolu.
    riolu_only = combined_coverage((builder.action_coverage(state, evolve),))
    riolu_and_lunatone = combined_coverage((
        builder.action_coverage(state, evolve),
        builder.action_coverage(state, deploy),
    ))
    assert riolu_and_lunatone.tier == riolu_only.tier
    assert len(riolu_and_lunatone.outcomes) == 2
    assert len(riolu_only.outcomes) == 1


_PEEK, _EVOLUTION = 50, 200


def _partition_beam(peek_clauses, *, deck_counts=((11, 1), (12, 8)),
                    information_partition=True, extra_hand=(), extra_hints=()):
    hints = (
        ActivatedStrategy("deck.develop_active", "evolve", "own.active", 10, 77,
                          (_EVOLUTION,), "immediate", "high", None, 0),
        ActivatedStrategy("general.information", "low_cost_information_access", "turn",
                          None, None, (), "immediate", "high", None, 0),
        *extra_hints,
    )
    hand = [{"id": _EVOLUTION, "serial": 90, "playerIndex": 0},
            {"id": _PEEK, "serial": 91, "playerIndex": 0},
            *({"id": card_id, "serial": 92 + index, "playerIndex": 0}
              for index, card_id in enumerate(extra_hand))]
    observation = _observation(hand=hand)
    observation["select"]["option"] = [
        {"type": 9, "index": 0, "inPlayArea": 4, "inPlayIndex": 0},
        *({"type": 7, "index": index} for index in range(1, len(hand))),
        {"type": 14},
    ]
    snapshot = StrategySnapshot(4, 0, "hash", "snapshot", (), (), hints)

    class Effects:
        @staticmethod
        def clauses(card_id):
            return tuple(peek_clauses) if card_id == _PEEK else ()

    class Stats:
        @staticmethod
        def get(card_id):
            return SimpleNamespace(
                is_pokemon=card_id in {_EVOLUTION, 11, 101, 102}, is_energy=False,
                is_supporter=False,
                stage="basic" if card_id in {11, 101, 102} else "stage1")

    builder = StrategyBeamBuilder(
        snapshot, effects=Effects(), stats=Stats(), sequence_coverage=True,
        information_partition=information_partition)
    state = SimpleNamespace(obs=observation, root_seat=0,
                            deck_counts=tuple(deck_counts))
    actions = enumerate_legal_actions(observation)
    beam = builder.build(state, actions)
    return beam, actions, builder, state


def test_a_live_free_peek_leads_the_beam_by_rule_not_by_score():
    dig = ({"kind": "fetch", "target": "pokemon", "zone": "deck", "dig": 3},)

    beam, actions, builder, _state = _partition_beam(dig)
    evolve = next(action for action in actions if action.identity.kind == "evolve")
    peek = next(action for action in actions if action.identity.kind == "play")
    assert [row.action_key for row in beam.focused] == [
        semantic_action_key(peek), semantic_action_key(evolve)]
    assert 0.0 < builder.last_odds[semantic_action_key(peek)] < 1.0

    legacy, actions, _builder, _state = _partition_beam(
        dig, information_partition=False)
    evolve = next(action for action in actions if action.identity.kind == "evolve")
    peek = next(action for action in actions if action.identity.kind == "play")
    assert [row.action_key for row in legacy.focused] == [
        semantic_action_key(evolve), semantic_action_key(peek)]


def test_a_dead_peek_does_not_lead_the_beam():
    dig = ({"kind": "fetch", "target": "pokemon", "zone": "deck", "dig": 3},)

    beam, actions, _builder, _state = _partition_beam(dig, deck_counts=((12, 8),))

    evolve = next(action for action in actions if action.identity.kind == "evolve")
    peek = next(action for action in actions if action.identity.kind == "play")
    assert [row.action_key for row in beam.focused] == [semantic_action_key(evolve)]
    assert semantic_action_key(peek) in {row.action_key for row in beam.inactive}


def test_a_costed_search_does_not_lead_the_beam():
    costed = ({"kind": "fetch", "target": "pokemon", "zone": "deck", "dig": 3,
               "cost": "discard_2", "cost_required": True},)

    beam, actions, _builder, _state = _partition_beam(costed)

    evolve = next(action for action in actions if action.identity.kind == "evolve")
    peek = next(action for action in actions if action.identity.kind == "play")
    assert [row.action_key for row in beam.focused] == [semantic_action_key(evolve)]
    assert semantic_action_key(peek) in {row.action_key for row in beam.inactive}


def test_partition_keeps_the_coverage_order_inside_each_class():
    dig = ({"kind": "fetch", "target": "pokemon", "zone": "deck", "dig": 3},)
    extras = (
        _deploy_hint("deck.alpha", (101,)),
        _deploy_hint("deck.beta", (102,)),
        _deploy_hint("deck.beta_extra", (102, 300),
                     deadline="next_turn", conviction="low"),
    )

    on, actions, _builder, _state = _partition_beam(
        dig, extra_hand=(101, 102), extra_hints=extras)
    peek_key = semantic_action_key(
        next(action for action in actions if action.selection == (1,)))
    off, _actions, _builder, _state = _partition_beam(
        dig, extra_hand=(101, 102), extra_hints=extras,
        information_partition=False)

    off_order = [row.action_key for row in off.focused]
    assert [row.action_key for row in on.focused] == [
        peek_key, *(key for key in off_order if key != peek_key)]


def test_rank_legal_returns_the_live_peek_first_with_the_partition_on():
    dig = ({"kind": "fetch", "target": "pokemon", "zone": "deck", "dig": 3},)

    _beam, actions, builder, state = _partition_beam(dig)

    ranked = builder.rank_legal(state, actions)
    peek = next(action for action in actions if action.identity.kind == "play")
    assert ranked[0] is peek
