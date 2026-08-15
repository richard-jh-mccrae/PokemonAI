"""Regression gates for the 2026-08-13 Mega Starmie correction batch."""
from __future__ import annotations

from pathlib import Path
import time

import pytest

from bellman_helpers import runtime
from train.blunder.store import load_corrections


REPO = Path(__file__).resolve().parents[2]
STORE = REPO / "data" / "corrections" / "mega_starmie_20260813_c9991b12"
ROWS = {row.id: row for row in load_corrections(STORE)}
RUNTIME = runtime()
MAX_CORRECTION_DECISION_SECONDS = 60.0


@pytest.mark.parametrize(("correction_id", "expected"), (
    ("c7cec0b0d266", (1,)),  # setup-only opener is a legal starting Pokemon
    ("55574333c63b", (3,)),  # safe chip damage does not justify spending the Supporter
    ("f1571e558ae0", (1,)),  # same setup-only opener through the opposite seat
    ("c8ebc06190d5", (0,)),  # beneficial attack beats ending the turn
    ("0395fcb0da0f", (2,)),  # recorded evolution commutes; attach/item still precede Lillie
    ("ab708777810c", (0,)),  # free denial before the resolving attack
    ("231db774b45e", (1,)),  # Water recovery outranks a redundant fourth Staryu
    ("26007ba948e7", (0,)),  # urgent Wally and Night Stretcher are exact-value commutative prefixes
    ("79789ec5d19e", (1,)),  # simultaneous Active/Bench KO readiness is preserved
    ("6a0242d3e39a", (1,)),  # energy goes to the empty healthy attacker
))
def test_corrected_choice(correction_id, expected):
    assert RUNTIME.decide(ROWS[correction_id].obs).chosen == expected


def test_free_information_forms_the_first_strategy_line():
    decision = runtime().decide(ROWS["8db4265d078d"].obs)

    assert decision.chosen == (1,)
    assert decision.diagnostics["strategy_beam"].focused[0].path_ids == (
        "general.low_cost_information_access_before_commitment",)
    assert decision.diagnostics["production"]["candidate_harvest"]["completed"][0][
        "root_action"].startswith("ActionIdentity(kind='play'")


def test_information_first_label_starts_with_one_of_the_two_information_actions():
    # The annotation contains two Main-menu indices although maxCount is one. Pokégear is the
    # intended first action; Buddy-Buddy Poffin can only be a later continuation (or vice versa).
    assert RUNTIME.decide(ROWS["47126201206d"].obs).chosen in {(3,), (5,)}


@pytest.mark.parametrize("correction_id", ("1fe0da3d8b94", "854d18378289"))
def test_freeze_reports_finish_with_a_legal_choice(correction_id):
    row = ROWS[correction_id]
    started = time.perf_counter()
    decision = RUNTIME.decide(row.obs)
    elapsed = time.perf_counter() - started
    option_count = len((row.obs.get("select") or {}).get("option") or ())
    assert decision.chosen
    assert all(0 <= index < option_count for index in decision.chosen)
    assert elapsed < MAX_CORRECTION_DECISION_SECONDS
