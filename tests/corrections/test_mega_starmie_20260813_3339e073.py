"""Regression gates for the 2026-08-13 Mega Starmie 3339e073 batch."""
from pathlib import Path

import pytest

from bellman_helpers import runtime
from train.blunder.store import load_corrections


REPO = Path(__file__).resolve().parents[2]
STORE = REPO / "data" / "corrections" / "mega_starmie_20260813_3339e073"
ROWS = {row.id: row for row in load_corrections(STORE)}
RUNTIME = runtime()


@pytest.mark.parametrize(("correction_id", "expected"), (
    ("d39f2e524f36", (6,)),  # free mulligan cards are monotonically beneficial
    ("e02e699ced1d", (0,)),  # draw access covers two missing primary-attacker slots
    ("92e27180b008", (0,)),  # free Pokegear information precedes the held deterministic evolution
    ("8c69ecaccafa", (0,)),  # equal damage concentrates toward the nearer KO
    ("dfc26070178c", (0,)),  # information action precedes the resolving attack
    ("8d91984d4430", (1,)),  # diversify acceleration across viable Basic attackers
    ("c7fd0670fb3e", (0,)),  # evolve the funded line
    ("76e7d6d7539e", (3,)),  # Nebula Beam starts the faster prize line
    ("5ee5f49312b2", (0,)),  # exact refresh value precedes its guaranteed visible attack
    ("da72e53929f0", (0,)),  # Harlequin replaces a dead visible hand
    ("c8ee8ab3e82b", (1,)),  # turn annotation's own written line starts with Hilda
    ("91cea0a2fa6d", (1,)),  # attach to the healthy attacker
    ("da39bb37b166", (1,)),  # never overcap the nearly-KO'd attacker
    ("188cceda7001", (0,)),  # Harlequin replaces a dead visible hand
    ("feafb8ef77c5", (0,)),  # information action before Turbo Flare
    ("496a7657096f", (0,)),  # dead Mega Signal must not detour the Harlequin line
    ("baede6accfac", (8,)),  # dead Mega Signal must not detour the ruled attack
    ("cb70b1405932", (4,)),  # expiring Energy is lost at End in either line
    ("79767ab416a7", (0,)),  # persistent basic Energy beats expiring Energy
    ("3c2afa3f1f28", (0,)),  # beneficial attack beats End
))
def test_adjudicated_choice(correction_id, expected):
    accepted = {expected}
    if correction_id == "c7fd0670fb3e":
        accepted.add((5,))  # retreat then evolve reaches the same ruled funded-Starmie line
    assert RUNTIME.decide(ROWS[correction_id].obs).chosen in accepted
