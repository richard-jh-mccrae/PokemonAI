"""Regression gate for the information-before-commitment correction."""
from pathlib import Path

from bellman_helpers import runtime
from train.blunder.store import load_corrections


REPO = Path(__file__).resolve().parents[2]
STORE = REPO / "data" / "corrections" / "mega_starmie_20260813_33b43c86"


def test_f20_collects_pokegear_information_before_attaching():
    row = next(correction for correction in load_corrections(STORE)
               if correction.id == "b8de42dc17f0")
    decision = runtime().decide(row.obs)

    assert decision.chosen == (0,)
    assert decision.diagnostics["production"]["information_first_permutations_pruned"] > 0
