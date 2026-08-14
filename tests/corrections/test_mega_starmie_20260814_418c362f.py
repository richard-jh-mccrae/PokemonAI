"""Regression gates for the exhaustive 2026-08-14 Mega Starmie self-play corrections."""
from pathlib import Path

from bellman_helpers import runtime
from train.blunder.store import load_corrections


REPO = Path(__file__).resolve().parents[2]
STORE = (REPO / "data" / "corrections"
         / "mega_starmie_20260814-024054_418c362f-dirty-selfplay-b9480288")
ROWS = {row.id: row for row in load_corrections(STORE)}
RUNTIME = runtime()


def test_f13_takes_the_available_attack():
    assert RUNTIME.decide(ROWS["86d154ac4158"].obs).chosen == (2,)


def test_f38_returns_a_legal_equivalent_evolution_copy():
    assert RUNTIME.decide(ROWS["1e23f38484f3"].obs).chosen == (0,)


def test_f41_does_not_spend_the_heal_supporter_on_twenty_damage():
    assert RUNTIME.decide(ROWS["ccd4c495d767"].obs).chosen != (1,)


def test_f64_collects_supporter_information_before_attaching():
    assert RUNTIME.decide(ROWS["e99b5c183656"].obs).chosen in {(6,), (7,)}


def test_f68_promotes_the_next_turn_attacker():
    assert RUNTIME.decide(ROWS["4cfe37b76592"].obs).chosen == (1,)


def test_f72_accelerates_to_the_developed_attacker():
    assert RUNTIME.decide(ROWS["b0a3658b2f5f"].obs).chosen == (0,)
