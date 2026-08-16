"""Regression gates for the first family-ranked Bellman correction corpus."""
from pathlib import Path
import time

from bellman_helpers import runtime
from train.blunder.store import load_corrections


REPO = Path(__file__).resolve().parents[2]
STORE = REPO / "data" / "corrections" / "mega_starmie_20260813_33b43c86"
ROWS = {row.id: row for row in load_corrections(STORE)}
RUNTIME = runtime()


def test_f20_collects_pokegear_information_before_attaching():
    decision = runtime().decide(ROWS["b8de42dc17f0"].obs)

    assert decision.chosen in {(0,), (6,)}
    # The human ruling is the CHOSEN card above and it is unchanged. This second assertion only
    # records which needs that play serves, and the play now serves two: a deck search reaches a
    # card that reaches an Evolution, so `_chain_reach` credits the evolve demand as well. Both
    # entries are true of the same unchanged move.
    assert {"general.evolve_active_attacker",
            "general.low_cost_information_access_before_commitment"} <= set(
        decision.diagnostics["strategy_beam"].focused[0].path_ids)


def test_f21_does_not_spend_a_dead_setup_fetch():
    # No Staryu remain and Cinderace is a 160HP Stage 2, so the Poffin reaches nothing and is
    # pruned outright rather than losing on a value margin a deadline can erase (ADR-0140).
    assert RUNTIME.decide(ROWS["25c423bbb0ec"].obs).chosen == (0,)


def test_turn_6_collects_information_before_committing_energy():
    # Re-pinned 2026-08-16 to the human turn_plan ("pokegear > replan > attach basic energy to
    # active"): 546369c9's (1,) tracked a solver budget flip, not a ruling (ADR-0140 amendment).
    decision = runtime().decide(ROWS["810eb9a2ae5c"].obs)

    assert decision.chosen == (0,)
    assert decision.diagnostics["strategy_beam"].focused[0].path_ids == (
        "general.low_cost_information_access_before_commitment",)
    assert '"id":1122' in decision.diagnostics["production"][
        "candidate_harvest"]["completed"][0]["root_action"]


def test_turn_8_develops_or_funds_the_safe_attacker_not_the_doomed_active():
    assert RUNTIME.decide(ROWS["96f392732553"].obs).chosen in {(1,), (7,)}


def test_f56_takes_the_knockout_attack():
    assert RUNTIME.decide(ROWS["9ee6dfe9df33"].obs).chosen == (0,)


def test_turn_10_uses_low_cost_information_before_committing_energy():
    assert runtime().decide(ROWS["d31f6bfa4803"].obs).chosen in {(0,), (4,)}


def test_f34_accepts_any_symmetric_empty_staryu_for_the_first_acceleration():
    assert RUNTIME.decide(ROWS["76c643323cc4"].obs).chosen in {(0,), (1,), (2,)}


def test_f51_promotes_the_ready_accelerator():
    assert RUNTIME.decide(ROWS["ce5b54e8276d"].obs).chosen == (0,)


def test_f56_equivalent_evolution_copy_does_not_freeze():
    started = time.perf_counter()
    decision = runtime().decide(ROWS["e1e75d61175f"].obs)

    assert decision.chosen in {(0,), (1,), (2,)}
    assert time.perf_counter() - started < 60.0


def test_turn_2_uses_the_no_discard_setup_fetch_first():
    assert RUNTIME.decide(ROWS["026c27592f19"].obs).chosen == (4,)


def test_turn_2_uses_the_supporter_before_turbo_flare():
    assert RUNTIME.decide(ROWS["37a3c18f25b2"].obs).chosen == (3,)
