import json
from collections import Counter

import pytest

from common.api import ActionIdentity
from common.ledger import EvaluationModel
from common.observation import KnownDeckTop, KnownOwnPrizes, LegalKnowledge, UnknownDeckTop
from cgpy.experiment import (BoundaryReason, ChanceExpansionRequest,
                             ChanceExpansionStatus, ChanceSampleKey, NodeKind,
                             PrimitiveTransition, TeacherCoverage,
                             TeacherSearchConfiguration, TurnSearchEnvironment,
                             WithinHorizonTeacher)
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
    main = environment.transition(fetched, fetch.identity).node
    assert environment.node_kind(main) is NodeKind.PLAYER_DECISION
    assert main.boundary_reason is None
    assert environment.observation(main).me.hand.count(120) == 1


def test_pokegear_hidden_reveal_stops_at_a_chance_node():
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

    assert environment.node_kind(transition.node) is NodeKind.CHANCE
    assert transition.boundary_reason is BoundaryReason.RANDOM_REVEAL
    assert not environment.is_information_boundary(transition.node)
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
    expansion = environment.expand(
        chance, ChanceExpansionRequest(experiment_seed=604))

    assert environment.node_kind(chance) is NodeKind.CHANCE
    assert first == second
    assert first.node is not None
    assert first.result_kind in (NodeKind.PLAYER_DECISION, NodeKind.FORCED_DECISION)
    assert expansion.status is ChanceExpansionStatus.COMPLETE
    assert expansion.support_size == 2
    assert [transition.probability for transition in expansion.transitions] == [0.5, 0.5]
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


def test_poffin_multi_select_returns_to_main_without_a_shuffle_branch():
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
    main = environment.transition(choose_bench, both.identity).node

    assert environment.node_kind(main) is NodeKind.PLAYER_DECISION
    assert main.boundary_reason is None


def test_lillies_expands_to_reproducible_whole_hand_main_successors():
    engine, _agent = scenario(
        "mega_starmie", me_active=BodySpec((1030,)),
        me_hand=(1227, 3), me_top=(1223, 1121, 3, 1030, 1031, 17, 1225, 1086),
        them_active=BodySpec((1030, 1031), energies=(3, 17)))
    lock_main_allowances(engine, supporter=False)
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    root = environment.root
    play = next(
        action for action in environment.legal_actions(root)
        if action.identity.kind == "play"
        and engine.gs.card_id(engine.gs.players[0].hand[
            engine.gs.pending.options[action.selection[0]]["index"]]) == 1227)
    played_serial = engine.gs.players[0].hand[
        engine.gs.pending.options[play.selection[0]]["index"]]
    original_hand = set(engine.gs.players[0].hand)
    chance = environment.transition(root, play.identity).node

    first = environment.expand(
        chance, ChanceExpansionRequest(
            experiment_seed=604, exact_outcome_limit=1, sample_count=4))
    extended = environment.expand(
        chance, ChanceExpansionRequest(
            experiment_seed=604, exact_outcome_limit=1, sample_count=6))

    assert environment.node_kind(chance) is NodeKind.CHANCE
    assert chance.boundary_reason is BoundaryReason.SHUFFLE_DRAW
    assert first.status is ChanceExpansionStatus.ESTIMATED
    assert first.requested_count == first.produced_count == 4
    assert first.probability_mass == pytest.approx(1.0)
    assert tuple(item.branch_key for item in first.transitions) == tuple(
        item.branch_key for item in extended.transitions[:4])
    assert tuple(item.result_state_key for item in first.transitions) == tuple(
        item.result_state_key for item in extended.transitions[:4])
    for successor in first.successors:
        observation = environment.observation(successor.node)
        assert environment.node_kind(successor.node) is NodeKind.PLAYER_DECISION
        assert observation.turn.supporter_played
        assert len(observation.me.hand) == 8
        assert observation.me.deck_count == root.observation.me.deck_count - 7
        assert any(card.serial not in original_hand for card in observation.me.hand)
        assert all(card.serial != played_serial for card in observation.me.hand)
        assert any(card.serial == played_serial for card in observation.me.discard)
        assert environment.legal_actions(successor.node)


def test_harlequin_resolves_both_hidden_hands_then_allows_later_traversal():
    engine, _agent = scenario(
        "mega_starmie", me_active=BodySpec((1030,)), me_hand=(1223, 3),
        them_active=BodySpec((1030, 1031), energies=(3, 17)))
    lock_main_allowances(engine, supporter=False)
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    root = environment.root
    play = next(
        action for action in environment.legal_actions(root)
        if action.identity.kind == "play"
        and engine.gs.card_id(engine.gs.players[0].hand[
            engine.gs.pending.options[action.selection[0]]["index"]]) == 1223)
    chance = environment.transition(root, play.identity).node

    expansion = environment.expand(
        chance, ChanceExpansionRequest(
            experiment_seed=604, exact_outcome_limit=1, sample_count=8))

    assert expansion.status is ChanceExpansionStatus.ESTIMATED
    assert expansion.requested_count == expansion.produced_count == 8
    assert expansion.probability_mass == pytest.approx(1.0)
    encoded = expansion.dumps()
    trace = json.loads(encoded)
    assert trace["schema"] == "cgpy-chance-expansion"
    assert trace["status"] == "estimated"
    assert trace["exact_outcome_limit"] == 1
    assert trace["sample_count"] == 8
    assert trace["requested_count"] == trace["produced_count"] == 8
    assert len(trace["branches"]) == 8
    assert all({"branch_key", "probability", "result_state_key", "result_kind",
                "boundary_reason", "failure"} <= branch.keys()
               for branch in trace["branches"])
    assert "card_id" not in encoded
    assert "deck_order" not in encoded
    assert "rng" not in encoded
    for successor in expansion.successors:
        observation = environment.observation(successor.node)
        assert isinstance(observation.them.hand, type(root.observation.them.hand))
        assert (len(observation.me.hand), observation.them.hand.count) in {
            (5, 3), (3, 5)}
        end = next(action for action in environment.legal_actions(successor.node)
                   if action.identity.kind == "end")
        later = environment.transition(successor.node, end.identity)
        assert later.result_kind is NodeKind.TURN_BOUNDARY
    assert engine.gs.pending.context == int(SelectContext.MAIN)
    assert not engine.gs.supporter_played


def test_pure_shuffle_canonicalizes_private_deck_order_without_a_chance_node():
    engine, _agent = scenario(
        "dragapult_ex", me_active=BodySpec((119,)),
        me_hand=(1121, 2, 5, 121),
        them_active=BodySpec((119, 120, 121), energies=(2, 5)))
    board = engine.gs.players[0]
    kept = []
    for card_id in (120, 1086, 1086):
        serial = next(serial for serial in board.deck
                      if engine.gs.card_id(serial) == card_id)
        board.deck.remove(serial)
        kept.append(serial)
    board.discard.extend(board.deck)
    board.deck = kept
    lock_main_allowances(engine)
    prize_counts = Counter(engine.gs.card_id(serial) for serial in board.prize)
    reverse = engine.fork()
    reverse.gs.players[0].deck.reverse()
    knowledge = LegalKnowledge(
        own_prizes=KnownOwnPrizes(tuple(prize_counts.items())),
        known_top=KnownDeckTop(((kept[-1], 1086),)))

    def fetch_then_shuffle(source):
        environment = TurnSearchEnvironment.from_engine(
            source, perspective_seat=0, knowledge=knowledge)
        root = environment.root
        play = next(
            action for action in environment.legal_actions(root)
            if action.identity.kind == "play"
            and source.gs.card_id(source.gs.players[0].hand[
                source.gs.pending.options[action.selection[0]]["index"]]) == 1121)
        discard = environment.transition(root, play.identity).node
        paid = next(action for action in environment.legal_actions(discard)
                    if len(action.selection) == 2)
        fetch_node = environment.transition(discard, paid.identity).node
        fetch = next(
            action for action in environment.legal_actions(fetch_node)
            if action.selection and environment.observation(fetch_node).select.deck[
                environment.observation(fetch_node).select.options[
                    action.selection[0]].index].card_id == 120)
        return environment, environment.transition(fetch_node, fetch.identity).node

    first_environment, first = fetch_then_shuffle(engine)
    second_environment, second = fetch_then_shuffle(reverse)

    assert first_environment.node_kind(first) is NodeKind.PLAYER_DECISION
    assert second_environment.node_kind(second) is NodeKind.PLAYER_DECISION
    assert first.state_key == second.state_key
    assert first.observation.decision_key == second.observation.decision_key
    assert isinstance(first.observation.knowledge.known_top, UnknownDeckTop)


def test_sampled_draw_honors_legal_known_top_over_private_deck_order():
    engine, _agent = scenario(
        "mega_starmie", me_active=BodySpec((1030,)), me_hand=(3,),
        them_active=BodySpec((1030, 1031), energies=(3, 17)))
    board = engine.gs.players[0]
    enriching_energy = board.hand[0]
    engine.gs.cards[enriching_energy].card_id = 13
    known_serial = board.deck[0]
    assert known_serial != board.deck[-1]
    lock_main_allowances(engine, energy=False)
    environment = TurnSearchEnvironment.from_engine(
        engine, perspective_seat=0,
        knowledge=LegalKnowledge(known_top=KnownDeckTop((
            (known_serial, engine.gs.card_id(known_serial)),))))
    blind = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    assert environment.root.state_key != blind.root.state_key
    attach = next(action for action in environment.legal_actions(environment.root)
                  if action.identity.kind == "attach")
    chance = environment.transition(environment.root, attach.identity).node

    expansion = environment.expand(
        chance, ChanceExpansionRequest(
            experiment_seed=604, exact_outcome_limit=1, sample_count=6))
    blind_chance = blind.transition(blind.root, attach.identity).node
    blind_expansion = blind.expand(
        blind_chance, ChanceExpansionRequest(
            experiment_seed=604, exact_outcome_limit=1, sample_count=6))

    assert expansion.status is ChanceExpansionStatus.ESTIMATED
    assert all(any(card.serial == known_serial
                   for card in environment.observation(successor.node).me.hand)
               for successor in expansion.successors)
    private_top = board.deck[-1]
    assert any(all(card.serial != private_top
                   for card in blind.observation(successor.node).me.hand)
               for successor in blind_expansion.successors)


def test_sampled_draw_is_invariant_to_unseen_deck_order():
    engine, _agent = scenario(
        "mega_starmie", me_active=BodySpec((1030,)), me_hand=(3,),
        them_active=BodySpec((1030, 1031), energies=(3, 17)))
    enriching_energy = engine.gs.players[0].hand[0]
    engine.gs.cards[enriching_energy].card_id = 13
    permuted = engine.fork()
    deck = permuted.gs.players[0].deck
    left = next(index for index, serial in enumerate(deck)
                if permuted.gs.card_id(serial) != permuted.gs.card_id(deck[-1]))
    deck[left], deck[-1] = deck[-1], deck[left]
    lock_main_allowances(engine, energy=False)
    lock_main_allowances(permuted, energy=False)

    def expansion(source):
        environment = TurnSearchEnvironment.from_engine(source, perspective_seat=0)
        attach = next(action for action in environment.legal_actions(environment.root)
                      if action.identity.kind == "attach")
        chance = environment.transition(environment.root, attach.identity).node
        result = environment.expand(
            chance, ChanceExpansionRequest(
                experiment_seed=604, exact_outcome_limit=1, sample_count=6))
        visible = tuple(sorted(
            (successor.probability, environment.observation(successor.node).decision_key)
            for successor in result.successors))
        return environment, result, visible

    baseline, first, first_visible = expansion(engine)
    hidden, second, second_visible = expansion(permuted)

    assert baseline.root.observation.decision_key == hidden.root.observation.decision_key
    assert baseline.root.state_key != hidden.root.state_key
    assert tuple(item.branch_key for item in first.transitions) == \
        tuple(item.branch_key for item in second.transitions)
    assert first_visible == second_visible


def test_sampled_draw_is_invariant_to_unseen_deck_prize_allocation():
    engine, _agent = scenario(
        "mega_starmie", me_active=BodySpec((1030,)), me_hand=(3,),
        them_active=BodySpec((1030, 1031), energies=(3, 17)))
    enriching_energy = engine.gs.players[0].hand[0]
    engine.gs.cards[enriching_energy].card_id = 13
    permuted = engine.fork()
    board = permuted.gs.players[0]
    deck_index, prize_index = next(
        (deck_index, prize_index)
        for deck_index, deck_serial in enumerate(board.deck)
        for prize_index, prize_serial in enumerate(board.prize)
        if permuted.gs.card_id(deck_serial) != permuted.gs.card_id(prize_serial))
    board.deck[deck_index], board.prize[prize_index] = (
        board.prize[prize_index], board.deck[deck_index])
    lock_main_allowances(engine, energy=False)
    lock_main_allowances(permuted, energy=False)

    def expansion(source):
        environment = TurnSearchEnvironment.from_engine(source, perspective_seat=0)
        attach = next(action for action in environment.legal_actions(environment.root)
                      if action.identity.kind == "attach")
        chance = environment.transition(environment.root, attach.identity).node
        result = environment.expand(
            chance, ChanceExpansionRequest(
                experiment_seed=604, exact_outcome_limit=16, sample_count=6))
        visible = tuple(sorted(
            (successor.probability, environment.observation(successor.node).decision_key)
            for successor in result.successors))
        return environment, result, visible

    baseline, first, first_visible = expansion(engine)
    hidden, second, second_visible = expansion(permuted)

    assert baseline.root.observation.decision_key == hidden.root.observation.decision_key
    assert baseline.root.state_key != hidden.root.state_key
    assert tuple(item.branch_key for item in first.transitions) == \
        tuple(item.branch_key for item in second.transitions)
    assert first_visible == second_visible


def test_bottom_look_reserves_known_top_across_deck_prize_allocations():
    engine, _agent = scenario(
        "mega_starmie", me_active=BodySpec((1030,)), me_hand=(3,),
        them_active=BodySpec((1030, 1031), energies=(3, 17)))
    dusk_ball = engine.gs.players[0].hand[0]
    engine.gs.cards[dusk_ball].card_id = 1102
    board = engine.gs.players[0]
    known_serial = board.deck[-1]
    knowledge = LegalKnowledge(known_top=KnownDeckTop((
        (known_serial, engine.gs.card_id(known_serial)),)))
    permuted = engine.fork()
    hidden = permuted.gs.players[0]
    prize_index = next(
        index for index, serial in enumerate(hidden.prize)
        if permuted.gs.card_id(serial) != permuted.gs.card_id(known_serial))
    hidden.deck[hidden.deck.index(known_serial)], hidden.prize[prize_index] = (
        hidden.prize[prize_index], known_serial)
    lock_main_allowances(engine)
    lock_main_allowances(permuted)

    def expansion(source):
        environment = TurnSearchEnvironment.from_engine(
            source, perspective_seat=0, knowledge=knowledge)
        play = next(action for action in environment.legal_actions(environment.root)
                    if action.identity.kind == "play")
        chance = environment.transition(environment.root, play.identity).node
        result = environment.expand(
            chance, ChanceExpansionRequest(
                experiment_seed=604, exact_outcome_limit=1, sample_count=6))
        visible = tuple(sorted(
            (successor.probability, environment.observation(successor.node).decision_key)
            for successor in result.successors))
        assert any(successor.node.kind is NodeKind.FORCED_DECISION
                   for successor in result.successors)
        for successor in result.successors:
            observation = environment.observation(successor.node)
            if successor.node.kind is NodeKind.FORCED_DECISION:
                assert known_serial not in {
                    card.serial for card in observation.looking.cards}
                assert observation.knowledge.known_top == knowledge.known_top
        return environment, result, visible

    baseline, first, first_visible = expansion(engine)
    hidden_environment, second, second_visible = expansion(permuted)

    assert baseline.root.observation.decision_key == \
        hidden_environment.root.observation.decision_key
    assert baseline.root.state_key != hidden_environment.root.state_key
    assert tuple(item.branch_key for item in first.transitions) == \
        tuple(item.branch_key for item in second.transitions)
    assert first_visible == second_visible


def test_prize_take_reserves_known_top_across_deck_prize_allocations():
    engine, _agent = scenario(
        "mega_starmie",
        me_active=BodySpec((1030, 1031), energies=(3, 17)),
        them_active=BodySpec((1030,), hp=10),
        them_bench=(BodySpec((1030,)),))
    board = engine.gs.players[0]
    known_serial = board.deck[-1]
    knowledge = LegalKnowledge(known_top=KnownDeckTop((
        (known_serial, engine.gs.card_id(known_serial)),)))
    permuted = engine.fork()
    hidden = permuted.gs.players[0]
    prize_index = next(
        index for index, serial in enumerate(hidden.prize)
        if permuted.gs.card_id(serial) != permuted.gs.card_id(known_serial))
    hidden.deck[hidden.deck.index(known_serial)], hidden.prize[prize_index] = (
        hidden.prize[prize_index], known_serial)
    lock_main_allowances(engine)
    lock_main_allowances(permuted)

    def expansion(source):
        environment = TurnSearchEnvironment.from_engine(
            source, perspective_seat=0, knowledge=knowledge)
        attack = next(action for action in environment.legal_actions(environment.root)
                      if action.identity.kind == "attack")
        target_node = environment.transition(environment.root, attack.identity).node
        target = environment.legal_actions(target_node)[0]
        prize_node = environment.transition(target_node, target.identity).node
        assert prize_node.kind is NodeKind.FORCED_DECISION
        choose = environment.legal_actions(prize_node)[0]
        chance = environment.transition(prize_node, choose.identity).node
        result = environment.expand(
            chance, ChanceExpansionRequest(
                experiment_seed=604, exact_outcome_limit=16, sample_count=6))
        visible = tuple(sorted(
            (successor.probability, environment.observation(successor.node).decision_key)
            for successor in result.successors))
        assert all(known_serial not in {
            card.serial for card in environment.observation(successor.node).me.hand}
                   for successor in result.successors)
        assert all(environment.observation(successor.node).knowledge.known_top
                   == knowledge.known_top for successor in result.successors)
        return environment, result, visible

    baseline, first, first_visible = expansion(engine)
    hidden_environment, second, second_visible = expansion(permuted)

    assert baseline.root.observation.decision_key == \
        hidden_environment.root.observation.decision_key
    assert baseline.root.state_key != hidden_environment.root.state_key
    assert tuple(item.branch_key for item in first.transitions) == \
        tuple(item.branch_key for item in second.transitions)
    assert first_visible == second_visible


def test_refresh_is_invariant_to_opponent_deck_hand_allocation():
    engine, _agent = scenario(
        "mega_starmie", me_active=BodySpec((1030,)), me_hand=(1223, 3),
        them_active=BodySpec((1030, 1031), energies=(3, 17)))
    opponent = engine.gs.players[1]
    opponent.hand.append(opponent.deck.pop())
    permuted = engine.fork()
    board = permuted.gs.players[1]
    deck_index, hand_index = next(
        (deck_index, hand_index)
        for deck_index, deck_serial in enumerate(board.deck)
        for hand_index, hand_serial in enumerate(board.hand)
        if permuted.gs.card_id(deck_serial) != permuted.gs.card_id(hand_serial))
    board.deck[deck_index], board.hand[hand_index] = (
        board.hand[hand_index], board.deck[deck_index])
    lock_main_allowances(engine, supporter=False)
    lock_main_allowances(permuted, supporter=False)

    def expansion(source):
        environment = TurnSearchEnvironment.from_engine(source, perspective_seat=0)
        play = next(
            action for action in environment.legal_actions(environment.root)
            if action.identity.kind == "play"
            and source.gs.card_id(source.gs.players[0].hand[
                source.gs.pending.options[action.selection[0]]["index"]]) == 1223)
        chance = environment.transition(environment.root, play.identity).node
        result = environment.expand(
            chance, ChanceExpansionRequest(
                experiment_seed=604, exact_outcome_limit=16, sample_count=8))
        visible = tuple(sorted(
            (successor.probability, environment.observation(successor.node).decision_key)
            for successor in result.successors))
        return environment, result, visible

    baseline, first, first_visible = expansion(engine)
    hidden, second, second_visible = expansion(permuted)

    assert baseline.root.observation.decision_key == hidden.root.observation.decision_key
    assert baseline.root.state_key != hidden.root.state_key
    assert tuple(item.branch_key for item in first.transitions) == \
        tuple(item.branch_key for item in second.transitions)
    assert first_visible == second_visible


def test_teacher_choice_is_invariant_to_unseen_deck_order():
    engine, _agent = scenario(
        "mega_starmie", me_active=BodySpec((1030,)), me_hand=(3,),
        them_active=BodySpec((1030, 1031), energies=(3, 17)))
    enriching_energy = engine.gs.players[0].hand[0]
    engine.gs.cards[enriching_energy].card_id = 13
    for index, serial in enumerate(engine.gs.players[0].deck):
        engine.gs.cards[serial].card_id = 3 if index % 2 else 17
    permuted = engine.fork()
    permuted.gs.players[0].deck.reverse()
    lock_main_allowances(engine, energy=False)
    lock_main_allowances(permuted, energy=False)
    configuration = TeacherSearchConfiguration(
        node_cap=1_000, path_node_cap=64, chance_branch_cap=1_000,
        exact_outcome_limit=1, chance_sample_count=6, time_cap_seconds=10)

    def search(source):
        environment = TurnSearchEnvironment.from_engine(source, perspective_seat=0)
        result = WithinHorizonTeacher().search_environment(
            environment, evaluation_model=EvaluationModel.build(),
            experiment_seed=654, configuration=configuration,
            baseline_identity="hidden-order-test")
        return environment, result

    baseline, first = search(engine)
    hidden, second = search(permuted)

    assert baseline.root.observation.decision_key == hidden.root.observation.decision_key
    assert baseline.root.state_key != hidden.root.state_key
    assert first.coverage is second.coverage is TeacherCoverage.COMPLETE
    assert first.preferred_action == second.preferred_action
    assert tuple((item.action, item.expected_value) for item in first.root_actions) == \
        tuple((item.action, item.expected_value) for item in second.root_actions)


def test_known_top_is_consumed_when_drakloak_moves_it_into_looking():
    engine, _agent = scenario(
        "dragapult_ex", me_active=BodySpec((119,)),
        me_bench=(BodySpec((119, 120)),),
        them_active=BodySpec((119, 120, 121), energies=(2, 5)))
    lock_main_allowances(engine)
    board = engine.gs.players[0]
    known_serial = board.deck[0]
    known = KnownDeckTop(((known_serial, engine.gs.card_id(known_serial)),))
    environment = TurnSearchEnvironment.from_engine(
        engine, perspective_seat=0,
        knowledge=LegalKnowledge(known_top=known))
    ability = next(action for action in environment.legal_actions(environment.root)
                   if action.identity.kind == "ability")
    chance = environment.transition(environment.root, ability.identity).node

    expansion = environment.expand(
        chance, ChanceExpansionRequest(
            experiment_seed=604, exact_outcome_limit=1, sample_count=2))

    for successor in expansion.successors:
        observation = environment.observation(successor.node)
        assert successor.node.kind is NodeKind.FORCED_DECISION
        assert known_serial in {card.serial for card in observation.looking.cards}
        assert observation.knowledge.known_top != known


def test_expansion_fold_can_reverse_single_hit_ranking_for_a_whole_hand_combo():
    engine, _agent = scenario(
        "mega_starmie", me_active=BodySpec((1030,)),
        me_hand=(1227, 1223, 3),
        me_top=(1121, 3, 1030, 1031, 17, 1225, 1086),
        them_active=BodySpec((1030, 1031), energies=(3, 17)))
    lock_main_allowances(engine, supporter=False)
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    root = environment.root
    plays = {
        engine.gs.card_id(engine.gs.players[0].hand[
            engine.gs.pending.options[action.selection[0]]["index"]]): action
        for action in environment.legal_actions(root)
        if action.identity.kind == "play"
    }
    request = ChanceExpansionRequest(
        experiment_seed=35, exact_outcome_limit=1, sample_count=12)
    expansions = {
        card_id: environment.expand(
            environment.transition(root, plays[card_id].identity).node, request)
        for card_id in (1227, 1223)
    }

    def hand(successor):
        return tuple(card.card_id
                     for card in environment.observation(successor.node).me.hand)

    hit_rate = {
        card_id: sum(successor.probability
                     for successor in expansion.successors
                     if 1121 in hand(successor))
        for card_id, expansion in expansions.items()
    }
    expected_combo_value = {
        card_id: sum(successor.probability
                     for successor in expansion.successors
                     if hand(successor).count(1145) >= 2)
        for card_id, expansion in expansions.items()
    }

    assert hit_rate[1227] > hit_rate[1223]
    assert expected_combo_value[1223] > expected_combo_value[1227]


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
