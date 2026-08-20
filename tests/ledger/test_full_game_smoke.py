"""One whole cgpy game through the LIVE runtime: the Ledger answers, BoardState agrees.

The deployment shell (common.runtime) catches every exception into a strategy-fallback answer,
so a completely dead Ledger still finishes matches and every other full-game harness stays
green. This smoke is the liveness assertion the rest of the tree cannot supply:

- every post-pregame decision must come back `backend == "ledger"` (or the trivial
  forced-selection shortcut) — one strategy-fallback anywhere fails the game;
- both seats' BoardState advance chains are cross-checked against the ENGINE'S OWN state —
  god truth, not a rendered reprint — every step: zone counts, hand and discard contents,
  actives, bench, statuses, stadium;
- the game must reach a real result, the terminal frame is digested (the one frame shape no
  fixture ever carried), and the evaluator reads the win/loss/draw off it."""
from __future__ import annotations

import importlib.util
from collections import Counter
from pathlib import Path

from cgpy.engine import Engine
from cgpy.render import observation
from cgpy.rng import SeededRng

from common.board import BoardState
from common.deck_tracker import OwnCardModel
from common.engine import CgpyTransitionProvider
from common.ledger import LedgerContext, evaluate
from common.runtime import build_runtime

REPO = Path(__file__).resolve().parents[2]
MAX_STEPS = 2000


def _runtime(deck):
    path = REPO / "src" / "agents" / "mega_starmie" / "strategy.py"
    spec = importlib.util.spec_from_file_location("_smoke_strategy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return build_runtime(module.STRATEGY, deck, provider_factory=CgpyTransitionProvider)


def _deck():
    path = REPO / "src" / "agents" / "mega_starmie" / "deck.csv"
    return [int(value) for value in path.read_text(encoding="utf-8").split()[:60]]


def _ids(gs, serials):
    return Counter(gs.cards[serial].card_id for serial in serials)


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
        if side.hand is not None:
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


def test_a_full_cgpy_mirror_game_runs_on_the_ledger_start_to_finish():
    deck = _deck()
    # Seed chosen by scan: 16 turns, every prize taken — knockouts, promotions, prize flips.
    engine, err_player, err_type = Engine.start(deck, deck, rng=SeededRng(424242))
    assert engine is not None, f"deck rejected: seat {err_player} errorType {err_type}"
    runtimes = {seat: _runtime(deck) for seat in (0, 1)}
    own_cards = {seat: OwnCardModel(runtimes[seat].deck, effects=runtimes[seat].effects)
                 for seat in (0, 1)}
    chains = {seat: BoardState.root(observation(engine.gs, seat), decklist=deck)
              for seat in (0, 1)}
    backends: Counter = Counter()
    steps = 0
    while engine.gs.result == -1 and steps < MAX_STEPS:
        seat = engine.gs.pending.seat
        obs = observation(engine.gs, seat)
        own_cards[seat].observe(obs)
        obs["own_prizes"] = own_cards[seat].prize_export()
        obs["known_top"] = own_cards[seat].known_top_export()
        turn = int((obs.get("current") or {}).get("turn", 0))
        decision = runtimes[seat].decide(obs)
        backend = decision.diagnostics.get("backend")
        backends[backend] += 1
        if turn <= 0:
            assert backend == "declarative-pregame", (steps, backend)
        else:
            # The whole point: the LEDGER answered, not the exception fallback.
            assert backend in ("ledger", "forced-selection"), \
                (steps, backend, decision.diagnostics)
        engine.step(list(decision.chosen))
        steps += 1
        for view in (0, 1):
            chains[view] = chains[view].advance(observation(engine.gs, view))
            if engine.gs.turn >= 1:        # setup facedowns are legitimately masked
                _assert_board_matches_engine(chains[view], engine.gs, view, steps)

    assert engine.gs.result != -1, f"no result after {MAX_STEPS} steps; backends {backends}"
    assert backends["ledger"] >= 20, backends
    assert backends.get("strategy-fallback", 0) == 0, backends

    # The terminal frame digests, and the evaluator reads the outcome straight off the board.
    ctx = LedgerContext.build()
    finals = {view: evaluate(chains[view].advance(observation(engine.gs, view)), ctx)
              for view in (0, 1)}
    for view in (0, 1):
        assert chains[view].turn.result == engine.gs.result
    if engine.gs.result == 2:              # simultaneous outcome: a draw for both seats
        assert finals[0].part("result") == finals[1].part("result") == 0.0
    else:
        winner = int(engine.gs.result)
        assert finals[winner].total > 50.0
        assert finals[1 - winner].total < -50.0
