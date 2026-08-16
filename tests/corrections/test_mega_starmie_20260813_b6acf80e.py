"""Regression gates for the second 2026-08-13 Mega Starmie correction batch."""
from pathlib import Path

import pytest

from bellman_helpers import runtime
from train.blunder.store import load_corrections


REPO = Path(__file__).resolve().parents[2]
STORE = REPO / "data" / "corrections" / "mega_starmie_20260813_b6acf80e"
ROWS = {row.id: row for row in load_corrections(STORE)}
RUNTIME = runtime()


@pytest.mark.parametrize(("correction_id", "expected"), (
    ("d11d625a6db3", (0,)),  # expiring Energy must be converted into damage before End
    ("c070b8acd261", (3,)),  # same expiring-Energy attack from the damaged Active
    # Wally's heals 50 off a benched Mega no attack reaches, which per-body doom pricing now values
    # at a tenth of a fully exposed heal; the ruled Salvatore wins on supporter opportunity cost.
    ("dbf1ff1d6fef", (0,)),
    ("8dfa2f8ef65d", (0,)),  # promote the fully powered attacker, not the empty pre-evolution
    ("9fb08842a8df", ()),  # prior Salvatore spend is sunk; do not encode intent as a decline rule
    ("670360dc929a", (0,)),  # snipe the developed attacker, not its empty pre-evolution
    ("3e893829feb9", (1,)),  # use denial before shuffling away the live item
))
def test_corrected_choice(correction_id, expected):
    assert RUNTIME.decide(ROWS[correction_id].obs).chosen == expected
