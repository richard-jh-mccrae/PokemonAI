from pathlib import Path
import copy
from dataclasses import replace

import pytest

from common.api import ActionIdentity
from common.decision.turn import WorkerTurnSearchProvider
from common.observation.nodes import HiddenHand
from cgpy.engine import Engine
from cgpy.experiment import (ChanceBranchKind, ChanceExpansion,
                             ChanceExpansionRequest, ChanceExpansionStatus,
                             ChanceSampleKey, ChanceSuccessor, ChanceTransition,
                             ExperimentSnapshot, NodeKind, PrimitiveTransition,
                             SearchContractError, TurnSearchEnvironment)
from cgpy.rng import SeededRng
from cgpy.schema import AreaType, OptionType, SelectContext
from cgpy.state import CardInstance, PendingSelect


REPO = Path(__file__).resolve().parents[2]


def _deck(name: str) -> list[int]:
    return [int(value) for value in (
        REPO / "src" / "agents" / name / "deck.csv"
    ).read_text(encoding="utf-8").split()[:60]]


def _start_of_turn(seed: int = 603) -> Engine:
    engine, error_player, error_type = Engine.start(
        _deck("mega_starmie"), _deck("mega_starmie"), rng=SeededRng(seed))
    assert engine is not None, (error_player, error_type)
    for _ in range(40):
        pending = engine.gs.pending
        assert pending is not None
        if engine.gs.phase == "TURN" and pending.context == 0:
            return engine
        engine.step(list(range(pending.min_count)))
    raise AssertionError("setup did not reach the first turn")


def test_exact_snapshot_opens_a_hidden_safe_player_decision_root():
    snapshot = ExperimentSnapshot.capture(_start_of_turn(), seat=0)

    environment = TurnSearchEnvironment.from_snapshot(snapshot)
    root = environment.root
    fork = environment.fork(root)

    assert environment.node_kind(root) is NodeKind.PLAYER_DECISION
    assert environment.actor(root) == 0
    assert environment.observation(root).seat == 0
    assert isinstance(environment.observation(root).them.hand, HiddenHand)
    assert environment.legal_actions(root) == environment.observation(root).legal_actions
    assert environment.state_key(root) == environment.state_key(fork)
    assert environment.state_key(root).schema_version == 1
    assert not hasattr(root, "_engine")
    assert isinstance(environment, WorkerTurnSearchProvider)


def test_primitive_transition_replays_by_action_identity():
    snapshot = ExperimentSnapshot.capture(_start_of_turn(), seat=0)
    environment = TurnSearchEnvironment.from_snapshot(snapshot)
    root = environment.root
    end = next(action for action in environment.legal_actions(root)
               if action.identity.kind == "end")

    recorded = environment.transition(root, end.identity)
    persisted = PrimitiveTransition.loads(recorded.dumps())
    replayed = environment.replay(root, persisted)

    assert replayed == recorded
    assert persisted == recorded
    assert persisted.node is None
    with pytest.raises(SearchContractError, match="missing"):
        environment.transition(root, ActionIdentity("missing"))


def _relabel_serials(engine: Engine) -> None:
    gs = engine.gs
    mapping = {}
    for seat in (0, 1):
        serials = sorted(serial for serial, card in gs.cards.items()
                         if card.owner == seat)
        mapping.update(zip(serials, reversed(serials)))
    gs.cards = {
        mapping[serial]: CardInstance(mapping[serial], card.card_id, card.owner)
        for serial, card in gs.cards.items()
    }

    def relabel(values):
        return [mapping[value] for value in values]

    for board in gs.players:
        board.deck = relabel(board.deck)
        board.hand = relabel(board.hand)
        board.discard = relabel(board.discard)
        board.prize = relabel(board.prize)
        for body in ([board.active] if board.active else []) + board.bench:
            body.stack = relabel(body.stack)
            body.energy = relabel(body.energy)
            body.tools = relabel(body.tools)
    gs.stadium = relabel(gs.stadium)
    gs.looking = None if gs.looking is None else relabel(gs.looking)
    gs.attach_seq = {mapping[serial]: tick for serial, tick in gs.attach_seq.items()}
    if gs.pending is not None:
        gs.pending.deck_listing = (None if gs.pending.deck_listing is None
                                   else relabel(gs.pending.deck_listing))
        gs.pending.context_card = (None if gs.pending.context_card is None
                                   else mapping[gs.pending.context_card])
        gs.pending.effect_card = (None if gs.pending.effect_card is None
                                  else mapping[gs.pending.effect_card])


def test_search_state_key_canonicalizes_serials_and_excludes_rng():
    source = _start_of_turn()
    source.gs.outbox = [[], []]
    source.gs.outbox_god = []
    relabeled = source.fork()
    relabeled.gs.cards = copy.deepcopy(relabeled.gs.cards)
    _relabel_serials(relabeled)
    relabeled.gs.rng = SeededRng(999999)
    changed = relabeled.fork()
    changed.gs.energy_attached = not changed.gs.energy_attached

    baseline = TurnSearchEnvironment.from_engine(source, perspective_seat=0)
    equivalent = TurnSearchEnvironment.from_engine(relabeled, perspective_seat=0)
    different = TurnSearchEnvironment.from_engine(changed, perspective_seat=0)

    assert baseline.state_key(baseline.root) == equivalent.state_key(equivalent.root)
    assert baseline.state_key(baseline.root) != different.state_key(different.root)


def test_information_key_excludes_hidden_opponent_deck_permutations():
    source = _start_of_turn()
    permuted = source.fork()
    opponent = permuted.gs.players[1]
    opponent.deck[0], opponent.deck[-1] = opponent.deck[-1], opponent.deck[0]

    baseline = TurnSearchEnvironment.from_engine(source, perspective_seat=0)
    hidden = TurnSearchEnvironment.from_engine(permuted, perspective_seat=0)

    assert baseline.state_key(baseline.root) != hidden.state_key(hidden.root)
    assert baseline.information_key(baseline.state_key(baseline.root)) == \
        hidden.information_key(hidden.state_key(hidden.root))


def test_search_state_key_excludes_diagnostic_logs_and_preserves_source_logs():
    clean = _start_of_turn()
    logged = clean.fork()
    logged.gs.outbox[0].append({"type": 9, "playerIndex": 0})
    logged.gs.outbox_god.append({"type": 9, "playerIndex": 0})

    clean_environment = TurnSearchEnvironment.from_engine(clean, perspective_seat=0)
    logged_environment = TurnSearchEnvironment.from_engine(logged, perspective_seat=0)

    assert clean_environment.state_key(clean_environment.root) == logged_environment.state_key(
        logged_environment.root)
    assert logged.gs.outbox[0]
    assert logged.gs.outbox_god


def test_opponent_prompt_is_an_opaque_information_boundary():
    engine = _start_of_turn()
    opponent = engine.gs.players[1]
    engine.gs.pending = PendingSelect(
        seat=1, type=1, context=int(SelectContext.TO_HAND),
        min_count=1, max_count=1,
        options=[{"type": int(OptionType.CARD), "area": int(AreaType.DECK),
                  "index": 0, "playerIndex": 1}],
        deck_listing=list(opponent.deck),
    )

    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    root = environment.root
    observed = environment.observation(root)

    assert environment.node_kind(root) is NodeKind.INFORMATION_BOUNDARY
    assert environment.actor(root) is None
    assert root.boundary_reason.value == "opponent_decision"
    assert observed.select is None
    assert observed.legal_actions == ()
    assert isinstance(observed.them.hand, HiddenHand)


def test_engine_failure_becomes_an_unavailable_node():
    engine = _start_of_turn()
    engine.gs.pending.options = [{"type": 999}]
    engine.gs.pending.min_count = 1
    engine.gs.pending.max_count = 1
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    root = environment.root

    transition = environment.transition(
        root, environment.legal_actions(root)[0].identity)

    assert environment.node_kind(transition.node) is NodeKind.UNAVAILABLE
    assert transition.failure is not None
    assert "AssertionError" in transition.failure
    assert environment.legal_actions(transition.node) == ()
    assert environment.state_key(transition.node) != environment.state_key(root)


def test_unavailable_state_key_excludes_exception_wording(monkeypatch):
    source = _start_of_turn()
    first = TurnSearchEnvironment.from_engine(source, perspective_seat=0)
    second = TurnSearchEnvironment.from_engine(source, perspective_seat=0)
    action = first.legal_actions(first.root)[0].identity
    messages = iter(("first diagnostic", "second diagnostic"))

    def fail(_engine, _selection):
        raise RuntimeError(next(messages))

    monkeypatch.setattr(Engine, "step", fail)
    first_result = first.transition(first.root, action)
    second_result = second.transition(second.root, action)

    assert first_result.failure != second_result.failure
    assert first_result.result_state_key == second_result.result_state_key


def test_end_stops_at_the_turn_boundary_after_the_hidden_next_draw():
    environment = TurnSearchEnvironment.from_snapshot(
        ExperimentSnapshot.capture(_start_of_turn(), seat=0))
    root = environment.root
    end = next(action for action in environment.legal_actions(root)
               if action.identity.kind == "end")

    transition = environment.transition(root, end.identity)

    assert environment.node_kind(transition.node) is NodeKind.TURN_BOUNDARY
    assert transition.boundary_reason.value == "turn_transition"
    assert environment.is_turn_boundary(transition.node)
    assert environment.actor(transition.node) is None
    assert environment.legal_actions(transition.node) == ()
    before = environment.observation(root)
    after = environment.observation(transition.node)
    assert after.turn.number == before.turn.number + 1
    assert after.them.deck_count == before.them.deck_count - 1
    assert after.them.hand.count == before.them.hand.count + 1
    assert isinstance(after.them.hand, HiddenHand)


def test_opponent_draw_identity_cannot_change_the_turn_boundary_key():
    first_engine = _start_of_turn()
    second_engine = first_engine.fork()
    opponent = 1 - first_engine.select_seat
    second_engine.gs.players[opponent].deck[-2:] = reversed(
        second_engine.gs.players[opponent].deck[-2:])
    environments = [
        TurnSearchEnvironment.from_engine(engine, perspective_seat=engine.select_seat)
        for engine in (first_engine, second_engine)]

    boundaries = []
    for environment in environments:
        end = next(action for action in environment.legal_actions(environment.root)
                   if action.identity.kind == "end")
        boundaries.append(environment.transition(environment.root, end.identity).node)

    assert boundaries[0].state_key == boundaries[1].state_key
    assert boundaries[0].observation == boundaries[1].observation


def test_nondecision_node_kinds_have_no_strategic_actor():
    chance_engine = _start_of_turn()
    chance_engine.gs.pending = PendingSelect(
        seat=0, type=9, context=int(SelectContext.COIN_HEAD),
        min_count=1, max_count=1,
        options=[{"type": int(OptionType.YES)}, {"type": int(OptionType.NO)}],
    )
    terminal_engine = _start_of_turn()
    terminal_engine.gs.set_result(0, 0)
    unavailable_engine = _start_of_turn()
    unavailable_engine.gs.pending = None

    chance = TurnSearchEnvironment.from_engine(chance_engine, perspective_seat=0)
    terminal = TurnSearchEnvironment.from_engine(terminal_engine, perspective_seat=0)
    unavailable = TurnSearchEnvironment.from_engine(unavailable_engine, perspective_seat=0)

    assert chance.node_kind(chance.root) is NodeKind.CHANCE
    assert terminal.node_kind(terminal.root) is NodeKind.TERMINAL
    assert unavailable.node_kind(unavailable.root) is NodeKind.UNAVAILABLE
    assert chance.actor(chance.root) is None
    assert terminal.actor(terminal.root) is None
    assert unavailable.actor(unavailable.root) is None
    assert chance.legal_actions(chance.root) == ()
    assert terminal.is_terminal(terminal.root)

    sample = ChanceSampleKey(
        603, chance.state_key(chance.root).digest,
        chance.state_key(chance.root).digest, ActionIdentity("coin"), 0)
    first = chance.sample(chance.root, sample)
    replayed = chance.replay_chance(chance.root, ChanceTransition.loads(first.dumps()))
    assert first == replayed
    assert first.sample == sample
    assert first.outcome.kind in ("yes", "no")
    assert first.node is not None


def test_unresolvable_exact_coin_expansion_is_replayable_and_unavailable():
    engine = _start_of_turn()
    engine.gs.pending = PendingSelect(
        seat=0, type=9, context=int(SelectContext.COIN_HEAD),
        min_count=1, max_count=1,
        options=[{"type": int(OptionType.YES)}, {"type": int(OptionType.NO)}],
    )
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)

    expansion = environment.expand(
        environment.root, ChanceExpansionRequest(experiment_seed=604))

    assert expansion.status is ChanceExpansionStatus.UNAVAILABLE
    assert expansion.support_size == 2
    assert expansion.requested_count == 2
    assert expansion.produced_count == 0
    assert expansion.probability_mass == pytest.approx(0.0)
    assert len(expansion.transitions) == 2
    assert len(expansion.successors) == 0
    assert {transition.probability for transition in expansion.transitions} == {0.5}
    assert {transition.method for transition in expansion.transitions} == {"coin"}
    assert {transition.branch_key.kind for transition in expansion.transitions} == {
        ChanceBranchKind.EXACT}
    for transition in expansion.transitions:
        persisted = ChanceTransition.loads(transition.dumps())
        assert persisted == transition
        assert environment.replay_chance(environment.root, persisted) == transition
        assert '"schema_version":2' in transition.dumps()
        assert '"sample"' not in transition.dumps()


def test_chance_expansion_request_defaults_are_bounded():
    request = ChanceExpansionRequest(experiment_seed=604)

    assert request.exact_outcome_limit == 16
    assert request.sample_count == 12


def test_schema_v1_chance_transition_still_loads_and_replays():
    engine = _start_of_turn()
    engine.gs.pending = PendingSelect(
        seat=0, type=9, context=int(SelectContext.COIN_HEAD),
        min_count=1, max_count=1,
        options=[{"type": int(OptionType.YES)}, {"type": int(OptionType.NO)}],
    )
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    sample = ChanceSampleKey(
        603, environment.root.state_key.digest,
        environment.root.state_key.digest, ActionIdentity("coin"), 0)
    current = environment.sample(environment.root, sample)
    legacy = ChanceTransition(
        current.parent_state_key, current.sample, current.outcome,
        current.result_state_key, current.result_kind, current.boundary_reason,
        current.failure, current.node, schema_version=1)

    persisted = ChanceTransition.loads(legacy.dumps())
    replayed = environment.replay_chance(environment.root, persisted)

    assert persisted == legacy
    assert replayed == legacy
    assert persisted.schema_version == 1
    assert '"sample"' in persisted.dumps()


def test_incomplete_expansion_preserves_missing_probability_mass():
    engine = _start_of_turn()
    engine.gs.pending = PendingSelect(
        seat=0, type=9, context=int(SelectContext.COIN_HEAD),
        min_count=1, max_count=1,
        options=[{"type": int(OptionType.YES)}, {"type": int(OptionType.NO)}],
    )
    environment = TurnSearchEnvironment.from_engine(engine, perspective_seat=0)
    failed = environment.expand(
        environment.root, ChanceExpansionRequest(experiment_seed=604))
    resolved = replace(
        failed.transitions[0], result_state_key=environment.root.state_key,
        result_kind=NodeKind.CHANCE, failure=None, node=environment.root)

    incomplete = ChanceExpansion(
        environment.root.state_key, "coin", ChanceExpansionStatus.INCOMPLETE,
        (resolved, failed.transitions[1]),
        (ChanceSuccessor(
            0.5, (resolved.branch_key,), environment.root),),
        16, 12, 2, 2, 1)

    assert incomplete.probability_mass == pytest.approx(0.5)
    assert '"probability_mass":0.5' in incomplete.dumps()


def test_environment_rejects_a_root_without_an_exact_randomness_epoch():
    engine = _start_of_turn()
    engine.gs.rng = object()

    with pytest.raises(ValueError, match="SeededRng"):
        TurnSearchEnvironment.from_engine(
            engine, perspective_seat=0)
