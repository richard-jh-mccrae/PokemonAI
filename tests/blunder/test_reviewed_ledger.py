"""The reviewed-corrections ledger: already-assessed blunders excluded from fresh blunder-busting.

Covers the loader/partition (`tools/train/blunder/reviewed.py`) and the maintenance CLI
(`tools/train/review_correction.py`). Lib-free: Corrections are stubbed to (episode_id, frame)."""
import json

import pytest

from train.blunder.reviewed import (
    DISPOSITIONS, load_reviewed, partition_reviewed, review_key,
)
from train.review_correction import main as cli


class _Corr:
    """Minimal Correction stub — partition only reads episode_id, seat, scope, subject, frame."""
    def __init__(self, episode_id, frame, *, scope="decision", subject=None, seat=0):
        self.episode_id = episode_id
        self.decision = {"frame": frame}
        self.scope = scope
        self.subject = frame if scope == "decision" and subject is None else subject
        self.seat = seat


@pytest.mark.req("REQ-TUNE-0030")
def test_review_key_matches_the_report_id():
    assert review_key(_Corr(81904451, 37)) == "81904451-37"


@pytest.mark.req("REQ-TUNE-0034")
def test_review_key_is_scope_aware():
    """ADR-0049: a scoped Correction is ledgered by its Scope's subject, so disposing of a Turn
    Correction never retires the Decision Corrections inside that Turn (and vice versa)."""
    turn = _Corr(81904451, 37, scope="turn", subject=12, seat=1)
    match = _Corr(81904451, 37, scope="match", subject=None, seat=1)
    assert review_key(turn) == "81904451-t12s1"
    assert review_key(match) == "81904451-m1"
    assert len({review_key(turn), review_key(match), review_key(_Corr(81904451, 37))}) == 3


@pytest.mark.req("REQ-TUNE-0031")
def test_load_reviewed_drops_comment_keys_and_missing_is_empty(tmp_path):
    p = tmp_path / "reviewed.json"
    p.write_text(json.dumps({
        "_note": "a comment",
        "81904451-37": {"disposition": "refuted", "reason": "forgoes a KO"},
    }), encoding="utf-8")
    led = load_reviewed(p)
    assert set(led) == {"81904451-37"}                       # _note gone
    assert led["81904451-37"]["disposition"] == "refuted"
    assert load_reviewed(tmp_path / "nope.json") == {}        # missing -> {}


@pytest.mark.req("REQ-TUNE-0032")
def test_partition_splits_active_from_dispositioned():
    reviewed = {"81904451-37": {"disposition": "refuted", "reason": "forgoes a KO"}}
    corrs = [_Corr(81904451, 37), _Corr(81904451, 99)]       # 1 reviewed, 1 new
    active, dispositioned = partition_reviewed(corrs, reviewed)
    assert [c.episode_id for c in active] == [81904451] and active[0].decision["frame"] == 99
    assert len(dispositioned) == 1
    c, entry = dispositioned[0]
    assert review_key(c) == "81904451-37" and entry["disposition"] == "refuted"


@pytest.mark.req("REQ-TUNE-0033")
def test_cli_records_lists_and_removes(tmp_path, capsys):
    p = tmp_path / "reviewed.json"
    assert cli(["81904451-37", "refuted", "forgoes a KO", "--path", str(p)]) == 0
    saved = json.loads(p.read_text(encoding="utf-8"))
    assert saved["81904451-37"]["disposition"] == "refuted"
    assert saved["81904451-37"]["reason"] == "forgoes a KO"
    assert "round" in saved["81904451-37"]

    capsys.readouterr()
    assert cli(["--list", "--path", str(p)]) == 0
    assert "81904451-37" in capsys.readouterr().out

    assert cli(["--remove", "81904451-37", "--path", str(p)]) == 0
    assert "81904451-37" not in json.loads(p.read_text(encoding="utf-8"))


@pytest.mark.req("REQ-TUNE-0033")
def test_cli_rejects_an_unknown_disposition(tmp_path):
    with pytest.raises(SystemExit):                          # argparse choices= guard
        cli(["81904451-37", "bogus", "x", "--path", str(tmp_path / "r.json")])
    assert "refuted" in DISPOSITIONS and "deferred" in DISPOSITIONS and "covered" in DISPOSITIONS
