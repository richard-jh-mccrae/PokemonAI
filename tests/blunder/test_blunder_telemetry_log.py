"""Reading live Decision Telemetry (ADR-0019) and joining it to a Correction's frame."""
from conftest import FIXTURES

from meta_tracker.parse import load_replay
from train.blunder.decisions import iter_decisions
from train.blunder.service import frames_payload, record_correction
from train.blunder.store import load_corrections
from train.blunder.telemetry_log import find_log, load_log, record_for

TELE = FIXTURES / "replays" / "mega_starmie_20260625_bde590c"
LOG = TELE / "episode-81903490-agent-0-logs.json"
REPLAY = TELE / "episode-81903490-replay.json.gz"


def _seat0_taggable(replay):
    return next(d for d in iter_decisions(replay) if d.seat == 0 and len(d.options) >= 2
                and all(0 <= c < len(d.options) for c in d.chosen))


def test_load_log_parses_the_at_records():
    """REQ-TELE-0001: the per-seat agent log parses into ordered @T decision records."""
    records = load_log(LOG)
    assert len(records) == 66                      # one per seat-0 decision, handshake skipped
    first = records[0]
    assert set(first) >= {"plan", "tier", "chosen", "opts", "margin"}
    assert all("fired" in o and "score" in o for o in first["opts"])


def test_record_for_joins_every_seat_frame_with_integrity_check():
    """REQ-TELE-0001: every seat-0 Decision frame joins to a live record whose option count and
    chosen positions match the film (the join's built-in integrity guard)."""
    replay = load_replay(REPLAY)
    records = load_log(LOG)
    joined = 0
    for d in iter_decisions(replay):
        if d.seat != 0:
            continue
        rec = record_for(replay, records, seat=0, frame=d.frame)
        assert rec is not None, f"frame {d.frame} did not join"
        assert len(rec["opts"]) == len(d.options)
        assert rec["chosen"] == d.chosen
        joined += 1
    assert joined == 66


def test_record_for_returns_none_for_an_unknown_frame():
    """REQ-TELE-0001: a frame that is not a seat decision yields no record (no false join)."""
    replay = load_replay(REPLAY)
    records = load_log(LOG)
    assert record_for(replay, records, seat=0, frame=99999) is None


def test_find_log_resolves_the_sibling_agent_log():
    """REQ-TELE-0001: the agent log is located next to a collected replay by episode id + seat."""
    assert find_log(REPLAY, 0) == LOG
    assert find_log(REPLAY, 1) is None             # no seat-1 log in fixture


def test_record_correction_embeds_the_live_trace(tmp_path):
    """REQ-TELE-0002: tagging with the agent log embeds the live @T record (how it actually
    decided) on the Correction, and it round-trips through the store."""
    replay = load_replay(REPLAY)
    records = load_log(LOG)
    for record in records:
        record["decision_seconds"] = 0.125
    d = _seat0_taggable(replay)
    correct = [next(i for i in range(len(d.options)) if i not in d.chosen)]
    store = tmp_path / "c.jsonl"

    rec = record_correction(replay, frame=d.frame, correct=correct, category="bad_target",
                            rationale="note", source="own", agent="mega_starmie",
                            store_path=store, live_records=records)

    assert rec.live_trace is not None
    assert rec.live_trace["chosen"] == d.chosen          # live record for this exact decision
    assert rec.decision["decision_seconds"] == 0.125
    assert "fired" in rec.live_trace["opts"][0]
    [loaded] = load_corrections(store)
    assert loaded.live_trace == rec.live_trace           # survives the JSONL round-trip


def test_record_correction_persists_the_posture_mismatch_flag(tmp_path):
    """ADR-0041: the tagging shell's 'opponent read was wrong' checkbox rides through
    record_correction (via **identity) onto the Correction and survives the store round-trip."""
    replay = load_replay(REPLAY)
    records = load_log(LOG)
    d = _seat0_taggable(replay)
    correct = [next(i for i in range(len(d.options)) if i not in d.chosen)]
    store = tmp_path / "c.jsonl"

    rec = record_correction(replay, frame=d.frame, correct=correct, category="bad_target",
                            rationale="vs Mega Lucario ex, snipe Riolu", source="own",
                            agent="mega_starmie", store_path=store, live_records=records,
                            posture_mismatch=True)

    assert rec.posture_mismatch is True
    [loaded] = load_corrections(store)
    assert loaded.posture_mismatch is True               # survives the JSONL round-trip


def test_frames_payload_attaches_live_trace_for_the_analyzed_seat():
    """REQ-TELE-0002: the inspector payload carries the live trace for the analyzed seat's
    taggable frames (so the tagger sees real scores/fired), and none for the other seat."""
    replay = load_replay(REPLAY)
    records = load_log(LOG)
    payload = frames_payload(replay, live_records=records, live_seat=0)

    seat0 = [f for f in payload["frames"] if f["taggable"] and f["seat"] == 0]
    assert seat0 and all(f["live"] is not None for f in seat0)
    seat1 = [f for f in payload["frames"] if f["taggable"] and f["seat"] == 1]
    assert all(f["live"] is None for f in seat1)         # only seat 0's log was supplied
