"""The persisted Battle Result record (tools/sim/result): per-Match source of truth +
recomputable aggregate header, appended to a committed JSONL log (ADR-0021 amendment)."""
import pytest

from sim.battle import BattleMatch
from sim.result import append_battle, build_battle_result, next_battle_id, read_battles

ROWS = [
    {"submission_id": 1, "agent": "mega_starmie", "artifact": "ms_a", "label": "base", "git_hash": "aaaaaaa"},
    {"submission_id": 3, "agent": "mega_starmie", "artifact": "ms_c", "label": "tuned", "git_hash": "ccccccc"},
]


def _result(records, **kw):
    return build_battle_result(
        battle_id=kw.pop("battle_id", 1),
        ran_at="2026-06-29T00:00:00Z", run_git_hash="abc1234", mode="pre-filter",
        contestants=[
            {"row": ROWS[1], "deck_ids": [3] * 60, "overlay": {"overrides": {"x": 5}}},
            {"row": ROWS[0], "deck_ids": [3] * 60, "overlay": None},
        ],
        records=records, params={"n_requested": 4, "jobs": 2, "seat_balanced": True}, **kw)


@pytest.mark.req("REQ-SIM-0006")
def test_aggregate_header_recomputes_from_matches_and_keeps_a_seat():
    records = [BattleMatch(0, 0), BattleMatch(1, 0), BattleMatch(0, 1), BattleMatch(1, None)]
    r = _result(records)
    assert (r["tally"]["n"], r["tally"]["a_wins"], r["tally"]["draws"]) == (4, 2, 1)
    assert r["win_rate"] == pytest.approx(2 / 4)            # derived from the same matches
    assert [m["a_seat"] for m in r["matches"]] == [0, 1, 0, 1]   # per-Match source of truth, a_seat kept
    assert "verdict" not in r                               # interpretation is derived on read, never stored


@pytest.mark.req("REQ-SIM-0006")
def test_battle_result_round_trips_through_the_committed_log(tmp_path):
    log = tmp_path / "battles.jsonl"
    r1 = _result([BattleMatch(0, 0)])
    append_battle(log, r1)
    r2 = _result([BattleMatch(1, 1)], battle_id=next_battle_id(log))
    append_battle(log, r2)
    assert read_battles(log) == [r1, r2]   # immutable append, faithfully reloaded
    assert r2["battle_id"] == 2            # monotonic battle_id derived from the log


@pytest.mark.req("REQ-SIM-0006")
def test_contestants_carry_provenance_overlay_and_deck_hash():
    a, b = _result([BattleMatch(0, 0)])["contestants"]
    assert (a["side"], b["side"]) == ("A", "B")
    assert a["submission_id"] == 3 and a["agent"] == "mega_starmie" and a["git_hash"] == "ccccccc"
    assert a["kind"] == "build"                          # has an artifact -> a Build (not working-tree)
    assert a["overlay"] == {"overrides": {"x": 5}} and b["overlay"] is None   # the config under test
    assert a["deck_hash"] == b["deck_hash"]              # same 60-card deck (same-deck self)
