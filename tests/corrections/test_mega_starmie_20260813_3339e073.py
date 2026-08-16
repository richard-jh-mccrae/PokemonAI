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
    ("79767ab416a7", (0,)),  # persistent basic Energy beats expiring Energy
    ("3c2afa3f1f28", (0,)),  # beneficial attack beats End
))
def test_adjudicated_choice(correction_id, expected):
    assert RUNTIME.decide(ROWS[correction_id].obs).chosen == expected


def test_c7fd_searches_cheap_information_then_bellman_attacks():
    decision = runtime().decide(ROWS["c7fd0670fb3e"].obs)

    assert decision.chosen in {(3,), (4,)}
    assert decision.diagnostics["strategy_beam"].focused[0].path_ids == (
        "general.low_cost_information_access_before_commitment",)
    assert decision.diagnostics["production"]["candidate_harvest"]["completed"][0][
        "root_action"].startswith("ActionIdentity(kind='play'")


def test_cb70_retreat_keeps_the_three_prize_body():
    # PR #523 ruling stands; reviewed.json refutes the [3] label. The Mega Signal that used to
    # order this node away from retreat is a whole-deck tutor, not a free peek (ADR-0140).
    assert RUNTIME.decide(ROWS["cb70b1405932"].obs).chosen == (4,)
