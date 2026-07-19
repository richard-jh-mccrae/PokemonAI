"""Eval harness (tools/sim/eval_strata, ADR-0053 WP2 design D5): skill-sensitivity stratification.
The pure statistics (median split, per-stratum paired delta) are unit-tested directly; the
value-swing proxy is exercised on a real generated film with a deterministic stub model so the
swing is non-degenerate (the committed seed model may be null in the test tree)."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

FIXTURE_AGENTS = REPO / "tests" / "fixtures" / "agents"
SRC = [REPO / "src"]


# ---- pure statistics -------------------------------------------------------------------------

@pytest.mark.req("REQ-SIM-0021")
def test_sensitivity_split_is_strict_median_and_degenerate_safe():
    """A strict median split puts wide-swinging games in high-swing; a run where every game scores
    the same (the null model → swing 0) collapses entirely to low-swing rather than splitting noise."""
    from sim.eval_strata import sensitivity_split
    thr, labels = sensitivity_split([0.1, 0.2, 0.8, 0.9])
    assert labels == ["low-swing", "low-swing", "high-swing", "high-swing"]
    thr0, labels0 = sensitivity_split([0.0, 0.0, 0.0])
    assert labels0 == ["low-swing", "low-swing", "low-swing"]      # degenerate -> all low
    assert sensitivity_split([]) == (0.0, [])


@pytest.mark.req("REQ-SIM-0021")
def test_strata_cells_compute_paired_delta_within_each_stratum():
    """Within a stratum the delta is the SAME paired candidate−baseline contrast as the headline,
    restricted to that stratum's games; high-swing here favours the candidate, low-swing is flat."""
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
    assert cells["high-swing"]["win_delta"] > 0.15                  # candidate clearly better on sensitive games
    assert abs(cells["low-swing"]["win_delta"]) < 1e-9             # dead flat where decisions didn't matter
    assert strata_cells([]) == []


@pytest.mark.req("REQ-SIM-0021")
def test_strata_cell_with_only_one_arm_reports_null_delta():
    """A stratum whose games never pair (one arm only) carries no candidate−baseline signal ->
    null-delta zero-width interval, not a crash."""
    from sim.eval_strata import strata_cells
    solo = [{"sensitivity": 0.5, "opponent": "o", "seat": 0, "arm": "candidate", "won": True}]
    cells = {c["name"]: c for c in strata_cells(solo)}
    assert cells["low-swing"]["win_delta"] == 0.0 and cells["low-swing"]["ci_low"] == 0.0


# ---- value-swing proxy on a real film --------------------------------------------------------

class _RampModel:
    """A deterministic stub value model: P(win) ramps with the prize lead (feature 6 = opp−my
    prizes), so a real game's trajectory spans a real range — unlike the possibly-null seed model."""

    def predict(self, features) -> float:
        prize_diff = features[6]                                    # opp_prizes − my_prizes
        return max(0.0, min(1.0, 0.5 + prize_diff / 12.0))


@pytest.fixture(scope="module")
def one_film(tmp_path_factory):
    """One real mega_starmie mirror film (same live path as test_corpus)."""
    from sim.corpus import generate_corpus_run
    from meta_tracker.parse import load_replay
    out = tmp_path_factory.mktemp("strata")
    run_dir = generate_corpus_run(
        run_id="strata", created_at="2026-07-19T00:00:00", git_rev="x", agents=["mega_starmie"],
        agents_root=FIXTURE_AGENTS, out_root=out, agent_versions={"mega_starmie": "x"},
        per_pairing=1, extra_syspath=SRC)
    films = sorted(run_dir.rglob("*.json.gz"))
    return load_replay(films[0])


@pytest.mark.req("REQ-SIM-0021")
def test_game_sensitivity_is_a_real_swing_over_a_real_film(one_film):
    """The proxy runs the shipped Pilot's _board over a real film through a value model and returns
    a bounded, positive swing — the seat-0 trajectory spans a real range as prizes are taken."""
    from sim.eval_strata import game_sensitivity, seat0_winprob
    from train.tune import _build_pilot
    pilot, _ = _build_pilot("mega_starmie")
    traj = seat0_winprob(pilot, _RampModel(), one_film)
    assert len(traj) > 10                                          # a real game -> many decision frames
    swing = game_sensitivity(pilot, _RampModel(), one_film)
    assert swing is not None and 0.0 < swing <= 1.0


@pytest.mark.req("REQ-SIM-0021")
def test_game_sensitivity_none_when_no_scorable_frame(one_film):
    """A film with no scorable decision (empty steps) yields None — excluded from stratification,
    not counted as a zero-swing blowout."""
    from sim.eval_strata import game_sensitivity
    from train.tune import _build_pilot
    pilot, _ = _build_pilot("mega_starmie")
    assert game_sensitivity(pilot, _RampModel(), {"steps": []}) is None
