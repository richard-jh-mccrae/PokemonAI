"""Eval harness (tools/sim/eval_strata, ADR-0053 WP2 design D5): skill-sensitivity stratification.
The value-swing proxy runs against a stub model — the committed seed model may be null here."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

FIXTURE_AGENTS = REPO / "tests" / "fixtures" / "agents"
SRC = [REPO / "src"]


@pytest.mark.req("REQ-SIM-0021")
def test_sensitivity_split_is_strict_median_and_degenerate_safe():
    from sim.eval_strata import sensitivity_split
    thr, labels = sensitivity_split([0.1, 0.2, 0.8, 0.9])
    assert labels == ["low-swing", "low-swing", "high-swing", "high-swing"]
    thr0, labels0 = sensitivity_split([0.0, 0.0, 0.0])
    assert labels0 == ["low-swing", "low-swing", "low-swing"]      # degenerate -> all low
    assert sensitivity_split([]) == (0.0, [])


@pytest.mark.req("REQ-SIM-0021")
def test_strata_cells_compute_paired_delta_within_each_stratum():
    from sim.eval_strata import strata_cells

    def games(sens, cand_wins, base_wins, total):
        out = []
        for k in range(total):
            out.append({"sensitivity": sens, "opponent": "o", "seat": 0,
                        "arm": "candidate", "won": k < cand_wins})
            out.append({"sensitivity": sens, "opponent": "o", "seat": 0,
                        "arm": "baseline", "won": k < base_wins})
        return out

    gs = games(0.9, 70, 50, 100) + games(0.1, 50, 50, 100)          # high-swing: +20pts; low: flat
    cells = {c["name"]: c for c in strata_cells(gs)}
    assert cells["high-swing"]["n"] == 200 and cells["low-swing"]["n"] == 200
    assert cells["high-swing"]["win_delta"] > 0.15
    assert abs(cells["low-swing"]["win_delta"]) < 1e-9
    assert strata_cells([]) == []


@pytest.mark.req("REQ-SIM-0021")
def test_strata_cell_with_only_one_arm_reports_null_delta():
    """Zero-width interval, not a crash."""
    from sim.eval_strata import strata_cells
    solo = [{"sensitivity": 0.5, "opponent": "o", "seat": 0, "arm": "candidate", "won": True}]
    cells = {c["name"]: c for c in strata_cells(solo)}
    assert cells["low-swing"]["win_delta"] == 0.0 and cells["low-swing"]["ci_low"] == 0.0


class _RampModel:
    """P(win) ramps with the prize lead, so a real game's trajectory spans a real range."""

    def predict(self, features) -> float:
        prize_diff = features[6]                                    # opp_prizes − my_prizes
        return max(0.0, min(1.0, 0.5 + prize_diff / 12.0))


# Films are fresh random games (unseedable engine RNG); ~1 in 8 is short enough to score swing 0.0,
# so the positive-swing claim below must be an EXISTENCE claim over several films, not one.
_STRATA_FILMS = 5


@pytest.fixture(scope="module")
def films(tmp_path_factory):
    from sim.corpus import generate_corpus_run
    from meta_tracker.parse import load_replay
    out = tmp_path_factory.mktemp("strata")
    run_dir = generate_corpus_run(
        run_id="strata", created_at="2026-07-19T00:00:00", git_rev="x", agents=["mega_starmie"],
        agents_root=FIXTURE_AGENTS, out_root=out, agent_versions={"mega_starmie": "x"},
        per_pairing=_STRATA_FILMS, extra_syspath=SRC)
    loaded = [load_replay(p) for p in sorted(run_dir.rglob("*.json.gz"))]
    assert loaded, "corpus generation produced no films"
    return loaded


@pytest.mark.req("REQ-SIM-0021")
def test_game_sensitivity_is_a_real_swing_over_a_real_film(films):
    """Only the arm's OWN seat frames are scored (D5), never the opponent's."""
    from sim.eval_strata import game_sensitivity, own_winprob
    from train.tune import _build_pilot
    pilot, _ = _build_pilot("mega_starmie")
    trajs = [own_winprob(pilot, _RampModel(), f, arm_seat=0) for f in films]
    swings = [game_sensitivity(pilot, _RampModel(), f, arm_seat=0) for f in films]

    for traj, swing in zip(trajs, swings):                         # must hold of EVERY real game
        assert all(not isinstance(p, complex) for p in traj)
        assert swing is not None and 0.0 <= swing <= 1.0

    assert any(len(t) > 5 for t in trajs), (
        f"no film produced a scorable trajectory: lengths {[len(t) for t in trajs]}")
    assert any(s > 0.0 for s in swings), (                         # the trajectory is live, not constant
        f"every one of {len(films)} real films scored a flat swing ({swings}) — the proxy is "
        f"reading a constant, not the arm's own-decision value trajectory")


@pytest.mark.req("REQ-SIM-0021")
def test_game_sensitivity_none_when_no_scorable_frame():
    """None = excluded from stratification, not a zero-swing blowout."""
    from sim.eval_strata import game_sensitivity
    from train.tune import _build_pilot
    pilot, _ = _build_pilot("mega_starmie")
    assert game_sensitivity(pilot, _RampModel(), {"steps": []}, arm_seat=0) is None
