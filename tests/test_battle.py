"""Battle (tools/sim): a local head-to-head between two Builds. Pure-core + engine driver."""
from pathlib import Path

import pytest

from sim.battle import (AgentServer, MatchResult, format_report, play_match, read_deck,
                        resolve, resolve_contestant, run_battle, tally, wilson_ci)

REPO = Path(__file__).resolve().parents[1]
FIXTURE_AGENTS = REPO / "tests" / "fixtures" / "agents"
MEGA = FIXTURE_AGENTS / "mega_starmie"          # a complete, legal, self-playing source agent
SRC = [REPO / "src"]                            # the source fixture isn't self-contained; cg/common live in src

ROWS = [
    {"submission_id": 1, "agent": "mega_starmie", "artifact": "ms_a", "label": "base", "git_hash": "aaaaaaa"},
    {"submission_id": 2, "agent": "slowking", "artifact": "sk_b", "label": None, "git_hash": "bbbbbbb"},
    {"submission_id": 3, "agent": "mega_starmie", "artifact": "ms_c", "label": "tuned", "git_hash": "ccccccc"},
]


@pytest.mark.req("REQ-SIM-0006")
def test_resolve_by_build_id():
    assert resolve_contestant("3", ROWS)["artifact"] == "ms_c"


@pytest.mark.req("REQ-SIM-0006")
def test_resolve_by_name_picks_the_latest_build():
    # two mega_starmie builds (#1, #3) -> the newer wins
    assert resolve_contestant("mega_starmie", ROWS)["submission_id"] == 3


@pytest.mark.req("REQ-SIM-0006")
def test_resolve_unknown_id_or_name_raises_naming_the_miss():
    with pytest.raises(ValueError, match="99"):
        resolve_contestant("99", ROWS)
    with pytest.raises(ValueError, match="zzz"):
        resolve_contestant("zzz", ROWS)


@pytest.mark.req("REQ-SIM-0006")
def test_resolve_name_is_the_working_tree_source_not_a_build(tmp_path):
    # a bare agent name resolves to the live src/agents/<name> dir, not the Build Ledger
    row, bundle = resolve("mega_starmie", [], agents_root=FIXTURE_AGENTS,
                          out=tmp_path, into=tmp_path)
    assert bundle == FIXTURE_AGENTS / "mega_starmie"
    assert row["label"] == "working-tree" and row["submission_id"] == "src"


@pytest.mark.req("REQ-SIM-0006")
def test_resolve_unknown_working_tree_name_errors(tmp_path):
    with pytest.raises(ValueError, match="nope"):
        resolve("nope", [], agents_root=FIXTURE_AGENTS, out=tmp_path, into=tmp_path)


@pytest.mark.req("REQ-SIM-0006")
def test_wilson_ci_is_wide_at_low_n_and_tight_at_high_n():
    lo_small, hi_small = wilson_ci(6, 10)
    lo_big, hi_big = wilson_ci(600, 1000)
    assert (hi_small - lo_small) > (hi_big - lo_big)        # n=10 far less certain than n=1000
    assert lo_big < 0.6 < hi_big                            # the point estimate sits inside
    assert wilson_ci(0, 0) == (0.0, 0.0)                    # empty Battle, no divide-by-zero


@pytest.mark.req("REQ-SIM-0006")
def test_tally_counts_wins_draws_and_crashes():
    results = [
        MatchResult(winner=0),
        MatchResult(winner=0),
        MatchResult(winner=1),
        MatchResult(winner=None),                            # a draw, owned by neither
        MatchResult(winner=1, crashed=(0,)),                 # A crashed -> B won + A flagged
    ]
    t = tally(results)
    assert (t["n"], t["a_wins"], t["b_wins"], t["draws"]) == (5, 2, 2, 1)
    assert (t["a_crashes"], t["b_crashes"]) == (1, 0)        # crash both loses *and* is surfaced


@pytest.mark.req("REQ-SIM-0006")
def test_report_states_both_contestants_the_score_and_the_ci():
    t = tally([MatchResult(winner=0)] * 31 + [MatchResult(winner=1)] * 17 + [MatchResult(winner=None)] * 2)
    report = format_report(ROWS[2], ROWS[0], t, elapsed=8.3, jobs=10, mode="curiosity")
    assert "#3 mega_starmie (tuned, ccccccc)" in report     # provenance, short hash
    assert "#3 wins 31" in report and "#1 wins 17" in report and "draws 2" in report
    assert "win-rate 62%" in report and "95% CI" in report   # 31/50 = 62%, with honesty interval
    assert "crashes 0" in report


@pytest.mark.req("REQ-SIM-0006")
def test_report_keeps_the_dirty_flag_on_a_working_tree_contestant():
    src_row = {"submission_id": "src", "agent": "mega_starmie", "label": "working-tree",
               "git_hash": "f1cd9bf-dirty"}
    t = tally([MatchResult(winner=0)] * 3)
    report = format_report(src_row, ROWS[0], t, elapsed=1.0, jobs=2, mode="curiosity")
    assert "#src mega_starmie (working-tree, f1cd9bf-dirty)" in report   # -dirty not truncated away


@pytest.mark.req("REQ-SIM-0006")
def test_report_surfaces_crashes_when_present():
    t = tally([MatchResult(winner=1, crashed=(0,))] * 3 + [MatchResult(winner=0)] * 2)
    report = format_report(ROWS[2], ROWS[0], t, elapsed=1.0, jobs=2, mode="curiosity")
    assert "crashes 3" in report and "#3: 3" in report       # the crashing build, called out


# --- engine driver: real Matches on the committed native engine (offline; no cabt/ke) ---


@pytest.mark.req("REQ-SIM-0007")
def test_play_match_runs_a_full_game_and_names_a_winner():
    deck = read_deck(MEGA)
    a, b = AgentServer(MEGA, SRC), AgentServer(MEGA, SRC)
    try:
        result = play_match(a, b, deck, deck)
    finally:
        a.close()
        b.close()
    assert result.winner in (0, 1, None)        # the engine resolved the game to a verdict
    assert result.crashed == ()                 # a clean mirror crashes neither seat


@pytest.mark.req("REQ-SIM-0007")
def test_play_match_scores_a_crashing_seat_as_a_loss():
    crasher = FIXTURE_AGENTS / "crasher"        # main.py raises when asked to act
    a, b = AgentServer(crasher, SRC), AgentServer(MEGA, SRC)
    try:
        result = play_match(a, b, read_deck(MEGA), read_deck(MEGA))
    finally:
        a.close()
        b.close()
    assert result.winner == 1 and result.crashed == (0,)   # seat 0 crashed -> seat 1 wins, flagged


@pytest.mark.req("REQ-SIM-0007")
def test_run_battle_parallel_tallies_every_match():
    deck = read_deck(MEGA)
    results = run_battle(MEGA, MEGA, deck, deck, n=4, jobs=2, extra_syspath=SRC)
    t = tally(results)
    assert t["n"] == 4                          # every fanned-out Match came back
    assert t["a_wins"] + t["b_wins"] + t["draws"] == 4
