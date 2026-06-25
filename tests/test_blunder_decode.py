"""Rendering engine option dicts into human-readable dropdown labels."""
from conftest import FIXTURES

from meta_tracker.parse import load_replay
from train.blunder.decisions import iter_decisions
from train.blunder.decode import option_label

FIXTURE = FIXTURES / "episode-81364540-replay.json.gz"


def _frame(ctx):
    return next(d for d in iter_decisions(load_replay(FIXTURE)) if d.select_context == ctx)


def test_main_option_labels_resolve_against_board():
    """REQ-BLUNDER-0008: Main options render readable labels (Play/Attach/End),
    resolving cards by (area, index) position in the full-info board."""
    d = _frame("Main")              # options: Play, Play, Play, Attach, End
    labels = [option_label(o, d.current) for o in d.options]
    assert labels[-1] == "End turn"
    assert labels[3] == "Attach Basic {D} Energy → Munkidori"
    assert labels[0].startswith("Play ")


def test_card_select_labels_resolve_card_names():
    """REQ-BLUNDER-0008: Card-select options resolve to the referenced card name,
    including the top-level `looking` zone."""
    bench = _frame("ToBench")
    assert option_label(bench.options[0], bench.current) == "Budew"
    hand = _frame("ToHand")         # area 12 = looking
    assert option_label(hand.options[0], hand.current) == "Lillie's Determination"
