"""Regression gates for the 2026-08-13 Mega Starmie 3339e073 batch."""
from pathlib import Path

import pytest

from bellman_helpers import runtime
from train.blunder.store import load_corrections


REPO = Path(__file__).resolve().parents[2]
STORE = REPO / "data" / "corrections" / "mega_starmie_20260813_3339e073"
ROWS = {row.id: row for row in load_corrections(STORE)}
RUNTIME = runtime()


@pytest.mark.parametrize(("correction_id", "accepted"), (
    ("d39f2e524f36", ((6,),)),  # free mulligan cards are monotonically beneficial
    ("e02e699ced1d", ((0,),)),  # draw access covers two missing primary-attacker slots
    ("92e27180b008", ((0,),)),  # exact reveal expectation survives without heuristic deletion
    ("8c69ecaccafa", ((0,),)),  # equal damage concentrates toward the nearer KO
    ("dfc26070178c", ((0,),)),  # information action precedes the resolving attack
    ("8d91984d4430", ((1,),)),  # diversify acceleration across viable Basic attackers
    ("c7fd0670fb3e", ((0,), (3,), (5,))),  # free information/evolution/retreat prefixes
    ("76e7d6d7539e", ((4,),)),  # Wally returns all three Basics, leaving no legal attack
    ("5ee5f49312b2", ((1,),)),  # analytic refresh commitment does not plan a hidden hand
    ("da72e53929f0", ((0,),)),  # complete hidden-refresh expectation remains eligible
    ("c8ee8ab3e82b", ((1,),)),  # turn annotation's own written line starts with Hilda
    ("91cea0a2fa6d", ((1,),)),  # attach to the healthy attacker
    ("da39bb37b166", ((1,),)),  # never overcap the nearly-KO'd attacker
    ("188cceda7001", ((1,),)),  # Poffin creates a Turbo Flare recipient before attacking
    ("feafb8ef77c5", ((0,),)),  # information action before Turbo Flare
    ("496a7657096f", ((4,),)),  # dead stadium and Mega searches commute before refreshing
    ("baede6accfac", ((1,), (6,))),  # free Harlequin/search prefixes; never attach fourth Energy
    ("cb70b1405932", ((4,),)),  # expiring Energy is lost at End in either line
    ("79767ab416a7", ((0,),)),  # persistent basic Energy beats expiring Energy
    ("3c2afa3f1f28", ((0,),)),  # beneficial attack beats End
))
def test_adjudicated_choice(correction_id, accepted):
    assert RUNTIME.decide(ROWS[correction_id].obs).chosen in accepted
