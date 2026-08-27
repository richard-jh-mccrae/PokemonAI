"""One whole cgpy game through the live runtime: the Ledger answers, ObservationState agrees.

This smoke is the liveness assertion the rest of the tree cannot supply:

- every post-pregame decision enters the coordinator exactly once and returns as Ledger;
- both seats' ObservationState advance chains are cross-checked against the ENGINE'S OWN state —
  god truth, not a rendered reprint — every step: zone counts, hand and discard contents,
  actives, bench, statuses, stadium;
- the game must reach a real result, the terminal frame is digested (the one frame shape no
  fixture ever carried), and the evaluator reads the win/loss/draw off it."""
from __future__ import annotations

from observation_builders import build_observation, advance_observation

import importlib.util
from collections import Counter
from pathlib import Path
import pytest

from cgpy.engine import Engine
from cgpy.render import observation
from cgpy.rng import SeededRng
from cgpy.search import export_token

from common.observation import HiddenHand, ObservationState, ObservationStateBuilder
from common.deck_tracker import OwnCardModel
from common.engine import CgpyTransitionProvider
from common.ledger import EvaluationModel, evaluate
from common.runtime import build_runtime

REPO = Path(__file__).resolve().parents[2]
MAX_STEPS = 2000


def _runtime(deck, agent):
    path = REPO / "src" / "agents" / agent / "strategy.py"
    spec = importlib.util.spec_from_file_location("_smoke_strategy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return build_runtime(module.STRATEGY, deck, provider_factory=CgpyTransitionProvider)


def _deck(agent):
    path = REPO / "src" / "agents" / agent / "deck.csv"
    return [int(value) for value in path.read_text(encoding="utf-8").split()[:60]]


def _ids(gs, serials):
    return Counter(gs.cards[serial].card_id for serial in serials)


def _observation(engine, seat):
    return observation(engine.gs, seat, sbi_token=export_token(engine.gs))


def _assert_board_matches_engine(board, gs, seat, step):
    """The board's beliefs against the engine's internal state — not against a render of it."""
    for label, side, engine_side in (("me", board.me, gs.players[seat]),
                                     ("them", board.them, gs.players[1 - seat])):
        note = f"step {step} seat {seat} {label}"
        assert side.deck_count == len(engine_side.deck), note
        assert side.hand_count == len(engine_side.hand), note
        assert side.prize_count == len(engine_side.prize), note
        assert Counter(card.card_id for card in side.discard) \
            == _ids(gs, engine_side.discard), note
        if not isinstance(side.hand, HiddenHand):
            assert Counter(card.card_id for card in side.hand) \
                == _ids(gs, engine_side.hand), note
        assert (side.active is None) == (engine_side.active is None), note
        if side.active is not None:
            assert side.active.card.card_id \
                == gs.cards[engine_side.active.top].card_id, note
            assert side.active.hp == engine_side.active.hp, note
        assert Counter(body.card.card_id for body in side.bench) \
            == Counter(gs.cards[bench_body.top].card_id
                       for bench_body in engine_side.bench), note
        for condition in ("poisoned", "burned", "asleep", "paralyzed", "confused"):
            assert getattr(side, condition) == getattr(engine_side, condition), \
                f"{note} {condition}"
    assert Counter(card.card_id for card in board.stadium) == _ids(gs, gs.stadium), \
        f"step {step} stadium"
    assert board.turn.number == gs.turn, f"step {step} turn"


@pytest.mark.parametrize("agent", ("dragapult_ex", "mega_lucario", "mega_starmie"))
def test_a_full_cgpy_mirror_game_runs_on_the_ledger_start_to_finish(monkeypatch, agent):
    monkeypatch.setenv("AGENT_BRAIN_STRICT", "1")
    deck = _deck(agent)
    # Seed chosen by scan: 16 turns, every prize taken — knockouts, promotions, prize flips.
    engine, err_player, err_type = Engine.start(deck, deck, rng=SeededRng(424242))
    assert engine is not None, f"deck rejected: seat {err_player} errorType {err_type}"
    runtimes = {seat: _runtime(deck, agent) for seat in (0, 1)}
    coordinator_entries: Counter = Counter()
    for seat, runtime in runtimes.items():
        real = runtime.ledger.coordinator

        class RecordingCoordinator:
            def decide(self, *args, _seat=seat, _real=real, **kwargs):
                coordinator_entries[_seat] += 1
                return _real.decide(*args, **kwargs)

        runtime.ledger.coordinator = RecordingCoordinator()
    own_cards = {seat: OwnCardModel(runtimes[seat].deck)
                 for seat in (0, 1)}
    chains = {seat: build_observation(_observation(engine, seat), decklist=deck)
              for seat in (0, 1)}
    backends: Counter = Counter()
    steps = 0
    while engine.gs.result == -1 and steps < MAX_STEPS:
        seat = engine.gs.pending.seat
        obs = _observation(engine, seat)
        own_cards[seat].observe(ObservationStateBuilder(deck).root(obs))
        obs["own_prizes"] = own_cards[seat].prize_export()
        obs["known_top"] = own_cards[seat].known_top_export()
        turn = int((obs.get("current") or {}).get("turn", 0))
        entries_before = coordinator_entries[seat]
        decision = runtimes[seat].decide(obs)
        backend = decision.diagnostics.get("backend")
        backends[backend] += 1
        if turn <= 0:
            assert backend == "declarative-pregame", (steps, backend)
            assert coordinator_entries[seat] == entries_before
        else:
            assert backend == "ledger", (steps, backend, decision.diagnostics)
            assert coordinator_entries[seat] == entries_before + 1
        engine.step(list(decision.chosen))
        steps += 1
        for view in (0, 1):
            chains[view] = advance_observation(chains[view], _observation(engine, view))
            if engine.gs.turn >= 1:        # setup facedowns are legitimately masked
                _assert_board_matches_engine(chains[view], engine.gs, view, steps)

    assert engine.gs.result != -1, f"no result after {MAX_STEPS} steps; backends {backends}"
    assert backends["ledger"] > 0, backends
    assert set(backends) <= {"declarative-pregame", "ledger"}, backends

    # The terminal frame digests, and the evaluator reads the outcome straight off the board.
    ctx = EvaluationModel.build()
    finals = {view: evaluate(advance_observation(chains[view], _observation(engine, view)), ctx)
              for view in (0, 1)}
    for view in (0, 1):
        assert chains[view].turn.result == engine.gs.result
    if engine.gs.result == 2:              # simultaneous outcome: a draw for both seats
        assert finals[0].part("result") == finals[1].part("result") == 0.0
    else:
        winner = int(engine.gs.result)
        assert finals[winner].part("result") == 100.0
        assert finals[1 - winner].part("result") == -100.0
