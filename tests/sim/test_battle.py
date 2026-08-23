"""Battle (tools/sim): a local head-to-head between two Builds. Pure-core + engine driver."""
from pathlib import Path
from time import monotonic
from types import SimpleNamespace

import pytest
import sim.battle as battle

from sim.battle import (AgentServer, BattleMatch, MatchResult, balanced_tally, format_report,
                        parse_spec, play_match, read_deck, resolve, resolve_contestant, run_battle,
                        seat_plan, tally, to_battle_match, wilson_ci)

REPO = Path(__file__).resolve().parents[2]
FIXTURE_AGENTS = REPO / "tests" / "fixtures" / "agents"
MEGA = FIXTURE_AGENTS / "mega_starmie"          # complete, legal, self-playing source agent
SRC = [REPO / "src"]                            # source fixture isn't self-contained; cg/common live in src

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
    # two mega_starmie builds (#1, #3) -> newer wins
    assert resolve_contestant("mega_starmie", ROWS)["submission_id"] == 3


@pytest.mark.req("REQ-SIM-0006")
def test_resolve_unknown_id_or_name_raises_naming_the_miss():
    with pytest.raises(ValueError, match="99"):
        resolve_contestant("99", ROWS)
    with pytest.raises(ValueError, match="zzz"):
        resolve_contestant("zzz", ROWS)


@pytest.mark.req("REQ-SIM-0006")
def test_resolve_name_is_the_working_tree_source_not_a_build(tmp_path):
    # bare agent name resolves to live src/agents/<name> dir, not the Build Ledger
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
    assert lo_big < 0.6 < hi_big                            # point estimate sits inside
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
    assert (t["a_crashes"], t["b_crashes"]) == (1, 0)        # crash both loses AND surfaces


@pytest.mark.req("REQ-SIM-0006")
def test_parse_spec_splits_off_an_optional_experiment_overlay():
    assert parse_spec("mega_starmie@exp/cand.json") == ("mega_starmie", "exp/cand.json")
    assert parse_spec("3") == ("3", None)                  # bare build id, no overlay
    assert parse_spec("mega_starmie") == ("mega_starmie", None)


@pytest.mark.req("REQ-SIM-0006")
def test_to_battle_match_maps_engine_seat_to_contestant():
    # A in seat 0: engine outcome already A/B-relative (identity)
    assert to_battle_match(0, MatchResult(winner=0)) == BattleMatch(a_seat=0, winner=0)
    # A in seat 1: engine seat 1 winning means A (contestant 0) won
    assert to_battle_match(1, MatchResult(winner=1)) == BattleMatch(a_seat=1, winner=0)
    # A in seat 1, engine seat 0 won+crashed -> that's B (contestant 1) winning + crashing
    assert to_battle_match(1, MatchResult(winner=0, crashed=(0,))) == BattleMatch(a_seat=1, winner=1, crashed=(1,))
    # draw stays a draw regardless of seat
    assert to_battle_match(1, MatchResult(winner=None)).winner is None


@pytest.mark.req("REQ-SIM-0006")
def test_seat_plan_splits_n_evenly_and_is_deterministic():
    plan = seat_plan(4)
    assert len(plan) == 4 and plan.count(0) == 2 and plan.count(1) == 2   # even split
    odd = seat_plan(5)
    assert len(odd) == 5 and abs(odd.count(0) - odd.count(1)) == 1        # odd: differ by one
    assert seat_plan(5) == odd                                            # deterministic (no RNG)


@pytest.mark.req("REQ-SIM-0006")
def test_balanced_tally_counts_A_wins_in_both_seats_and_splits_by_seat():
    # A won once from each seat; B won once from each seat (perfectly balanced sample).
    records = [
        BattleMatch(a_seat=0, winner=0),        # A sat seat 0 and won
        BattleMatch(a_seat=1, winner=0),        # A sat seat 1 and won
        BattleMatch(a_seat=0, winner=1),        # A sat seat 0, B won
        BattleMatch(a_seat=1, winner=1),        # A sat seat 1, B won
    ]
    t = balanced_tally(records)
    assert (t["n"], t["a_wins"], t["b_wins"]) == (4, 2, 2)   # A's wins counted regardless of seat
    # per-seat split is the ADR-0021 audit: seat effect must stay visible
    assert t["by_seat"][0] == {"n": 2, "a_wins": 1}
    assert t["by_seat"][1] == {"n": 2, "a_wins": 1}


@pytest.mark.req("REQ-SIM-0006")
def test_report_shows_the_per_seat_split_for_a_balanced_run():
    # A won 1 of 2 as seat 0, 2 of 2 as seat 1 — seat effect report must keep visible
    records = [BattleMatch(0, 0), BattleMatch(0, 1), BattleMatch(1, 0), BattleMatch(1, 0)]
    report = format_report(ROWS[2], ROWS[0], balanced_tally(records), elapsed=1.0, jobs=2, mode="pre-filter")
    assert "seat 0" in report and "seat 1" in report      # both seats surfaced (ADR-0021 audit)
    assert "1/2" in report and "2/2" in report            # A's per-seat win counts


@pytest.mark.req("REQ-SIM-0006")
def test_report_states_both_contestants_the_score_and_the_ci():
    t = tally([MatchResult(winner=0)] * 31 + [MatchResult(winner=1)] * 17 + [MatchResult(winner=None)] * 2)
    report = format_report(ROWS[2], ROWS[0], t, elapsed=8.3, jobs=10, mode="curiosity")
    assert "#3 mega_starmie (tuned, ccccccc)" in report     # provenance, short hash
    assert "#3 wins 31" in report and "#1 wins 17" in report and "draws 2" in report
    assert "win-rate 62%" in report and "95% CI" in report   # 31/50 = 62%, honesty interval
    assert "crashes 0" in report


@pytest.mark.req("REQ-SIM-0006")
def test_report_keeps_the_dirty_flag_on_a_working_tree_contestant():
    src_row = {"submission_id": "src", "agent": "mega_starmie", "label": "working-tree",
               "git_hash": "f1cd9bf-dirty"}
    t = tally([MatchResult(winner=0)] * 3)
    report = format_report(src_row, ROWS[0], t, elapsed=1.0, jobs=2, mode="curiosity")
    assert "#src mega_starmie (working-tree, f1cd9bf-dirty)" in report   # -dirty not truncated


@pytest.mark.req("REQ-SIM-0006")
def test_report_surfaces_crashes_when_present():
    t = tally([MatchResult(winner=1, crashed=(0,))] * 3 + [MatchResult(winner=0)] * 2)
    report = format_report(ROWS[2], ROWS[0], t, elapsed=1.0, jobs=2, mode="curiosity")
    assert "crashes 3" in report and "#3: 3" in report       # crashing build, called out


# --- engine driver: real Matches on committed native engine (offline; no cabt/ke) ---


@pytest.mark.req("REQ-SIM-0007")
def test_play_match_runs_a_full_game_and_names_a_winner():
    deck = read_deck(MEGA)
    a = AgentServer(MEGA, SRC, capture_telemetry=True)
    b = AgentServer(MEGA, SRC, capture_telemetry=True)
    telemetry = []
    try:
        result = play_match(a, b, deck, deck, telemetry=telemetry,
                            episode_key="native-full-game")
    finally:
        a.close()
        b.close()
    assert result.winner in (0, 1, None)        # engine resolved the game to a verdict
    assert result.crashed == ()                 # clean mirror crashes neither seat
    decisions = [record for record in telemetry if record["record_type"] == "decision"]
    outcomes = [record for record in telemetry if record["record_type"] == "outcome"]
    assert len(outcomes) == 1
    assert outcomes[0]["decision_ids"] == [record["record_id"] for record in decisions]


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
    assert "RuntimeError: intentional crash" in result.failure


@pytest.mark.req("REQ-SIM-0007")
def test_play_match_attributes_an_expired_shorter_wait_to_the_match_deadline(monkeypatch):
    obs = {"current": {"result": -1, "yourIndex": 0}, "select": {"context": 0}}
    monkeypatch.setattr("cg.game.battle_start", lambda _a, _b: (
        obs, SimpleNamespace(errorPlayer=-1)))
    monkeypatch.setattr("cg.game.battle_finish", lambda: None)
    clock = iter((0.0, 0.0, 0.0, 2.0))
    monkeypatch.setattr(battle, "monotonic", lambda: next(clock))

    class TimedServer:
        last_timeout = True
        last_telemetry = []

        def act(self, _obs, timeout=None):
            assert timeout == 1.0
            return None

    result = play_match(TimedServer(), TimedServer(), [], [],
                        decision_timeout=5.0, match_timeout=1.0)
    assert result.winner is None
    assert result.timed_out == ()
    assert result.match_deadline_hit


@pytest.mark.req("REQ-SIM-0007")
def test_play_match_times_every_decision_even_with_the_contestants_telemetry_off(monkeypatch):
    live = {"current": {"result": -1, "yourIndex": 0}, "select": {"context": 0}}
    over = {"current": {"result": 0, "yourIndex": 0}, "select": None}
    monkeypatch.setattr("cg.game.battle_start", lambda _a, _b: (
        live, SimpleNamespace(errorPlayer=-1)))
    monkeypatch.setattr("cg.game.battle_select", lambda _choice: over)
    monkeypatch.setattr("cg.game.battle_finish", lambda: None)

    class SilentServer:                            # AGENT_NO_TELEMETRY=1 -> nothing comes back
        last_timeout = False
        last_telemetry = []
        last_seconds = 0.75

        def act(self, _obs, timeout=None):
            return [0]

    metrics = []
    play_match(SilentServer(), SilentServer(), [], [], metrics=metrics)

    assert metrics == [{"engine_seat": 0, "decision_index": 0,
                        "round_trip_seconds": 0.75, "telemetry_seconds": 0.0}]


@pytest.mark.req("REQ-SIM-0007")
def test_play_match_owner_appends_one_outcome_with_the_exact_decision_set(monkeypatch):
    live = {"current": {"result": -1, "yourIndex": 0, "players": [
        {"prize": [None, None]}, {"prize": [None]},
    ]}, "select": {"context": 0}}
    over = {"current": {"result": 1, "yourIndex": 0, "players": [
        {"prize": [None, None]}, {"prize": []},
    ]}, "select": None}
    monkeypatch.setattr("cg.game.battle_start", lambda _a, _b: (
        live, SimpleNamespace(errorPlayer=-1)))
    monkeypatch.setattr("cg.game.battle_select", lambda _choice: over)
    monkeypatch.setattr("cg.game.battle_finish", lambda: None)

    class CapturingServer:
        last_timeout = False
        last_seconds = 0.01

        def begin_episode(self, episode_key):
            self.episode_key = episode_key

        def act(self, _obs, timeout=None):
            self.last_telemetry = [{
                "record_type": "decision",
                "record_id": "seat-0-decision-0",
                "episode": {"key": self.episode_key},
            }]
            return [0]

    records = []
    play_match(CapturingServer(), CapturingServer(), [], [], telemetry=records)

    assert [record["record_type"] for record in records] == ["decision", "outcome"]
    outcome = records[-1]
    assert outcome["decision_ids"] == ["seat-0-decision-0"]
    assert outcome["result"]["winner"] == 1
    assert outcome["result"]["public_prizes"] == {"0": 2, "1": 0}


def test_illegal_deck_still_gets_exactly_one_owner_outcome(monkeypatch):
    obs = {"current": {"players": [{"prize": []}, {"prize": []}]}, "select": None}
    monkeypatch.setattr("cg.game.battle_start", lambda _a, _b: (
        obs, SimpleNamespace(errorPlayer=0)))
    monkeypatch.setattr("cg.game.battle_finish", lambda: None)

    records = []
    result = play_match(SimpleNamespace(), SimpleNamespace(), [], [], telemetry=records)

    assert result.winner == 1
    assert len(records) == 1
    assert records[0]["record_type"] == "outcome"
    assert records[0]["result"]["terminal_reason"] == "illegal_deck"


@pytest.mark.req("REQ-SIM-0007")
def test_run_battle_parallel_tallies_every_match():
    deck = read_deck(MEGA)
    results = run_battle(MEGA, MEGA, deck, deck, n=4, jobs=2, extra_syspath=SRC)
    t = tally(results)
    assert t["n"] == 4                          # every fanned-out Match came back
    assert t["a_wins"] + t["b_wins"] + t["draws"] == 4


@pytest.mark.req("REQ-SIM-0007")
def test_run_battle_is_seat_balanced_and_records_a_seat():
    deck = read_deck(MEGA)
    results = run_battle(MEGA, MEGA, deck, deck, n=4, jobs=1, extra_syspath=SRC)
    assert len(results) == 4 and all(isinstance(r, BattleMatch) for r in results)
    assert {r.a_seat for r in results} == {0, 1}             # contestant A plays both seats
    assert sum(1 for r in results if r.a_seat == 0) == 2     # N/2 each way (ADR-0021)


@pytest.mark.req("REQ-SIM-0007")
def test_run_battle_parallel_is_globally_seat_balanced():
    # odd per-worker shares (12/4 -> 3 each) must not all tilt same way; split is global
    deck = read_deck(MEGA)
    results = run_battle(MEGA, MEGA, deck, deck, n=12, jobs=4, extra_syspath=SRC)
    assert len(results) == 12
    assert sum(1 for r in results if r.a_seat == 0) == 6     # exact N/2, not 8/4 (ADR-0021)
