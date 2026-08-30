import pytest

from common.api import ActionIdentity
from cgpy.experiment import (BoundaryReason, ChanceSampleKey, NodeKind,
                             PrimitiveTransition, TurnSearchEnvironment)
from cgpy.rng import SeededRng
from cgpy.schema import SelectContext

from real_engine_helpers import (
    BodySpec, lock_main_allowances, option_card_id, scenario,
)


def test_ultra_ball_play_is_one_primitive_transition_to_a_forced_discard_node():
    engine, _agent = scenario(
        "dragapult_ex", me_active=BodySpec((119,)), me_hand=(1121, 2, 5, 121),
        me_top=(121,), them_active=BodySpec((119, 120, 121), energies=(2, 5)))
    lock_main_allowances(engine)
    direct = engine.fork()
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    root = environment.root
    play = next(
        action for action in environment.legal_actions(root)
        if action.identity.kind == "play"
        and engine.gs.card_id(engine.gs.players[0].hand[
            engine.gs.pending.options[action.selection[0]]["index"]]) == 1121)

    direct.step(list(play.selection))
    transition = environment.transition(root, play.identity)
    direct_environment = TurnSearchEnvironment.from_engine(direct, perspective_seat=0)

    assert isinstance(transition, PrimitiveTransition)
    assert transition.schema_version == 1
    assert transition.action == play.identity
    assert environment.node_kind(transition.node) is NodeKind.FORCED_DECISION
    assert environment.observation(transition.node).select.context == int(
        SelectContext.DISCARD)
    assert environment.state_key(transition.node) == direct_environment.state_key(
        direct_environment.root)
    assert environment.node_kind(root) is NodeKind.PLAYER_DECISION
    assert engine.gs.pending.context == int(SelectContext.MAIN)
    direct.observation(viewer=0, sbi_token=None)

    discard = next(
        action for action in environment.legal_actions(transition.node)
        if len(action.selection) == 2
        and {option_card_id(direct, direct.gs.pending.options[index])
             for index in action.selection} == {5, 121})
    direct.step(list(discard.selection))
    fetched = environment.transition(transition.node, discard.identity).node
    assert environment.node_kind(fetched) is NodeKind.FORCED_DECISION
    assert environment.observation(fetched).select.context == int(SelectContext.TO_HAND)
    direct_fetch = TurnSearchEnvironment.from_engine(direct, perspective_seat=0)
    assert environment.state_key(fetched) == direct_fetch.state_key(direct_fetch.root)

    fetch = next(
        action for action in environment.legal_actions(fetched)
        if option_card_id(direct, direct.gs.pending.options[action.selection[0]]) == 120)
    boundary = environment.transition(fetched, fetch.identity).node
    assert environment.node_kind(boundary) is NodeKind.INFORMATION_BOUNDARY
    assert boundary.boundary_reason is BoundaryReason.SHUFFLE_DRAW
    assert environment.observation(boundary).me.hand.count(120) == 1


def test_pokegear_hidden_reveal_stops_at_an_information_boundary():
    engine, _agent = scenario(
        "mega_starmie", me_active=BodySpec((1030,)), me_hand=(1122,),
        me_top=(1227, 3, 1223, 3, 1030, 3),
        them_active=BodySpec((1030, 1031), energies=(3, 17)))
    lock_main_allowances(engine)
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    root = environment.root
    play = next(action for action in environment.legal_actions(root)
                if action.identity.kind == "play")

    transition = environment.transition(root, play.identity)

    assert environment.node_kind(transition.node) is NodeKind.INFORMATION_BOUNDARY
    assert transition.boundary_reason is BoundaryReason.RANDOM_REVEAL
    assert environment.is_information_boundary(transition.node)
    assert environment.legal_actions(transition.node) == ()
    assert environment.state_key(transition.node) != environment.state_key(root)
    assert engine.gs.pending.context == int(SelectContext.MAIN)


def test_intercepted_coin_resumes_from_a_reproducible_chance_sample():
    engine, _agent = scenario(
        "mega_starmie", me_active=BodySpec((1030,)), me_hand=(1120,),
        them_active=BodySpec((1030, 1031), energies=(3,)))
    lock_main_allowances(engine)
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    root = environment.root
    play = next(action for action in environment.legal_actions(root)
                if action.identity.kind == "play")
    chance = environment.transition(root, play.identity).node
    sample_key = ChanceSampleKey(
        603, root.state_key.digest, chance.state_key.digest, play.identity, 0)

    first = environment.sample(chance, sample_key)
    second = environment.sample(chance, sample_key)

    assert environment.node_kind(chance) is NodeKind.CHANCE
    assert first == second
    assert first.node is not None
    assert first.result_kind in (NodeKind.PLAYER_DECISION, NodeKind.FORCED_DECISION)
    forged = ChanceSampleKey(
        603, root.state_key.digest, chance.state_key.digest,
        ActionIdentity("forged"), 0)
    with pytest.raises(ValueError, match="action does not match"):
        environment.sample(chance, forged)


def test_non_frame_confusion_coin_replays_the_whole_attack():
    engine, _agent = scenario(
        "mega_lucario", me_active=BodySpec((677, 678), energies=(6,)),
        me_bench=(BodySpec((673, 674)),),
        them_active=BodySpec((677, 678), energies=(6, 6)))
    lock_main_allowances(engine)
    engine.gs.players[0].confused = True
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    root = environment.root
    attack = next(action for action in environment.legal_actions(root)
                  if action.identity.kind == "attack")
    chance = environment.transition(root, attack.identity).node
    sample_key = ChanceSampleKey(
        603, root.state_key.digest, chance.state_key.digest, attack.identity, 0)

    result = environment.sample(chance, sample_key)

    assert environment.node_kind(chance) is NodeKind.CHANCE
    assert result.result_kind is not NodeKind.UNAVAILABLE
    assert result.failure is None


def test_looped_coin_effect_replays_prior_outcomes_without_reapplying_damage():
    engine, _agent = scenario(
        "mega_lucario", me_active=BodySpec((677, 678), energies=(6, 6, 6, 6, 6)),
        them_active=BodySpec((677, 678), energies=(6, 6)),
        them_bench=(BodySpec((673, 674)),))
    engine.gs.cards[engine.gs.players[0].active.top].card_id = 1056
    lock_main_allowances(engine)
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    root = environment.root
    attack = next(
        action for action in environment.legal_actions(root)
        if action.identity.kind == "attack" and dict(action.options[0])["attackId"] == 1526)
    first_chance = environment.transition(root, attack.identity).node
    first_sample = None
    for index in range(20):
        candidate = ChanceSampleKey(
            603, root.state_key.digest, first_chance.state_key.digest,
            attack.identity, index)
        if not SeededRng(candidate.seed).coin():
            first_sample = candidate
            break
    assert first_sample is not None
    second_chance = environment.sample(first_chance, first_sample).node
    second_sample = ChanceSampleKey(
        603, root.state_key.digest, second_chance.state_key.digest, attack.identity, 1)

    result = environment.sample(second_chance, second_sample)

    assert environment.node_kind(first_chance) is NodeKind.CHANCE
    assert environment.node_kind(second_chance) is NodeKind.CHANCE
    assert environment.state_key(first_chance) != environment.state_key(second_chance)
    assert result.result_kind not in (NodeKind.CHANCE, NodeKind.UNAVAILABLE)
    assert result.failure is None


def test_retreat_chain_reaches_main_then_turn_boundary_without_greedy_policy(monkeypatch):
    monkeypatch.setattr(
        "common.ledger.search.GreedyDecisionPolicy.choose",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Greedy Decision Policy was invoked")))
    engine, _agent = scenario(
        "dragapult_ex", me_active=BodySpec((119,), energies=(2,), hp=20),
        me_bench=(BodySpec((119, 120, 121), energies=(2, 5)), BodySpec((119,))),
        them_active=BodySpec((119, 120, 121), energies=(2, 5)))
    lock_main_allowances(engine)
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)

    root = environment.root
    retreat = next(action for action in environment.legal_actions(root)
                   if action.identity.kind == "retreat")
    payment = environment.transition(root, retreat.identity).node
    assert environment.observation(payment).select.context == int(
        SelectContext.DISCARD_ENERGY)

    paid = environment.transition(
        payment, environment.legal_actions(payment)[0].identity).node
    assert environment.observation(paid).select.context == int(SelectContext.SWITCH)
    promote = next(
        action for action in environment.legal_actions(paid)
        if environment.observation(paid).me.bench[
            dict(action.options[0])["index"]].card.card_id == 121)
    main = environment.transition(paid, promote.identity).node

    assert environment.node_kind(main) is NodeKind.PLAYER_DECISION
    assert environment.actor(main) == 0
    end = next(action for action in environment.legal_actions(main)
               if action.identity.kind == "end")
    boundary = environment.transition(main, end.identity).node
    assert environment.node_kind(boundary) is NodeKind.TURN_BOUNDARY


def test_poffin_multi_select_is_atomic_before_its_shuffle_boundary():
    engine, _agent = scenario(
        "dragapult_ex", me_active=BodySpec((119,)), me_hand=(1086,),
        me_top=(119, 119), them_active=BodySpec((119, 120, 121), energies=(2, 5)))
    lock_main_allowances(engine)
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    root = environment.root
    play = next(action for action in environment.legal_actions(root)
                if action.identity.kind == "play")

    choose_bench = environment.transition(root, play.identity).node
    assert environment.observation(choose_bench).select.context == int(
        SelectContext.TO_BENCH)
    both = next(action for action in environment.legal_actions(choose_bench)
                if len(action.selection) == 2)
    boundary = environment.transition(choose_bench, both.identity).node

    assert environment.node_kind(boundary) is NodeKind.INFORMATION_BOUNDARY
    assert boundary.boundary_reason is BoundaryReason.SHUFFLE_DRAW


@pytest.mark.parametrize(
    "agent,scenario_args,attack_id,context",
    (
        (
            "mega_lucario",
            {
                "me_active": BodySpec((677, 678), energies=(6,)),
                "me_bench": (
                    BodySpec((673, 674)), BodySpec((673, 674)), BodySpec((677,))),
                "me_discard": (6, 6, 6),
                "them_active": BodySpec((677, 678), energies=(6, 6)),
                "them_prizes": 5,
            },
            982,
            SelectContext.ATTACH_TO,
        ),
        (
            "mega_starmie",
            {
                "me_active": BodySpec((1030, 1031), energies=(3,)),
                "them_active": BodySpec((1030, 1031)),
                "them_bench": (
                    BodySpec((1030,), hp=40), BodySpec((1030, 1031), hp=200)),
            },
            1487,
            SelectContext.DAMAGE,
        ),
        (
            "dragapult_ex",
            {
                "me_active": BodySpec((119, 120, 121), energies=(2, 5)),
                "them_active": BodySpec((119, 120, 121), energies=(2, 5)),
                "them_bench": (
                    BodySpec((119, 120, 121), hp=20), BodySpec((119,), hp=10),
                    BodySpec((119,), hp=70)),
            },
            154,
            SelectContext.DAMAGE_COUNTER_ANY,
        ),
    ),
)
def test_representative_attacks_expose_their_forced_target_menu(
        agent, scenario_args, attack_id, context):
    engine, _agent = scenario(agent, **scenario_args)
    lock_main_allowances(engine)
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    root = environment.root
    attack = next(
        action for action in environment.legal_actions(root)
        if action.identity.kind == "attack"
        and dict(action.options[0]).get("attackId") == attack_id)

    forced = environment.transition(root, attack.identity).node

    assert environment.node_kind(forced) is NodeKind.FORCED_DECISION
    assert environment.observation(forced).select.context == int(context)
    assert environment.actor(forced) == 0
    assert environment.legal_actions(forced)
