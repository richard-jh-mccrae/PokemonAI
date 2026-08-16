"""Regression gates for the exhaustive 2026-08-14 Mega Starmie self-play corrections."""
from pathlib import Path

from bellman_helpers import runtime
from train.blunder.store import load_corrections


REPO = Path(__file__).resolve().parents[2]
STORE = (REPO / "data" / "corrections"
         / "mega_starmie_20260814-024054_418c362f-dirty-selfplay-b9480288")
ROWS = {row.id: row for row in load_corrections(STORE)}
RUNTIME = runtime()


def test_f13_takes_the_attack_or_information_before_it():
    decision = RUNTIME.decide(ROWS["86d154ac4158"].obs)

    if decision.chosen != (2,):
        assert decision.chosen in {(0,), (1,)}
        assert decision.diagnostics["ledger"]["continuation"] > 0.0


def test_f38_returns_a_legal_equivalent_evolution_copy():
    assert RUNTIME.decide(ROWS["1e23f38484f3"].obs).chosen == (0,)


def test_f41_does_not_spend_the_heal_supporter_on_twenty_damage():
    assert RUNTIME.decide(ROWS["ccd4c495d767"].obs).chosen != (1,)


def test_f64_searches_supporter_information_then_bellman_attaches():
    decision = runtime().decide(ROWS["e99b5c183656"].obs)

    assert decision.chosen in {(1,), (3,), (6,)}
    # Info leads and is credited; later deck hints co-sign the same look via access odds.
    assert "general.low_cost_information_access_before_commitment" in (
        decision.diagnostics["strategy_beam"].focused[0].path_ids)
    assert decision.diagnostics["production"]["candidate_harvest"]["completed"][0][
        "root_action"].startswith("ActionIdentity(kind='play'")


def test_f68_promotes_the_next_turn_attacker():
    assert RUNTIME.decide(ROWS["4cfe37b76592"].obs).chosen == (1,)


def test_f72_accelerates_to_the_developed_attacker():
    assert RUNTIME.decide(ROWS["b0a3658b2f5f"].obs).chosen == (0,)
