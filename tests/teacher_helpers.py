from pathlib import Path

from cgpy.engine import Engine
from cgpy.experiment import ExperimentSnapshot
from cgpy.rng import SeededRng


REPO = Path(__file__).resolve().parents[1]


def deck(name):
    return [int(value) for value in (
        REPO / "src" / "agents" / name / "deck.csv"
    ).read_text(encoding="utf-8").split()[:60]]


def end_only_snapshot(name, path=None):
    cards = deck(name)
    engine, error_player, error_type = Engine.start(
        cards, cards, rng=SeededRng(605))
    assert engine is not None, (error_player, error_type)
    for _ in range(40):
        pending = engine.gs.pending
        assert pending is not None
        if engine.gs.phase == "TURN" and pending.context == 0:
            pending.options = [next(option for option in pending.options
                                    if option["type"] == 14)]
            snapshot = ExperimentSnapshot.capture(engine, seat=engine.select_seat)
            return snapshot if path is None else snapshot.save(path)
        engine.step(list(range(pending.min_count)))
    raise AssertionError("setup did not reach the first turn")


__all__ = ("deck", "end_only_snapshot")
