"""Regression gates for the critical 2026-08-14 Mega Starmie corrections."""
from pathlib import Path

from bellman_helpers import runtime
from train.blunder.store import load_corrections


REPO = Path(__file__).resolve().parents[2]
STORE = (REPO / "data" / "corrections"
         / "mega_starmie_20260814-201423_3ea4245a-dirty-selfplay")
ROWS = {row.id: row for row in load_corrections(STORE)}


def test_f11_takes_the_available_attack():
    assert runtime().decide(ROWS["80a43e46936f"].obs).chosen == (1,)


def test_f22_selects_the_supporter_that_completes_the_second_attacker():
    assert runtime().decide(ROWS["bf62dfec37d5"].obs).chosen == (0,)


def test_f32_refreshes_for_the_next_attack_energy():
    assert runtime().decide(ROWS["50a7f923549e"].obs).chosen == (1,)


def test_f72_concentrates_energy_on_the_active_attacker():
    assert runtime().decide(ROWS["dace30bdf47f"].obs).chosen == (5,)


def test_f16_takes_the_available_attack():
    assert runtime().decide(ROWS["89514ba8ce7e"].obs).chosen == (1,)
