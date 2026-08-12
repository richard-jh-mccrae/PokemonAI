import pytest

from sim.mirror_gate import assert_within_limit, run_mirror, summarize


def test_mirror_summary_reports_per_match_average_minimum_and_maximum():
    assert summarize([1.0, 2.0, 6.0]) == {"avg": 3.0, "min": 1.0, "max": 6.0}


def test_mirror_gate_rejects_the_slowest_match_not_the_average():
    with pytest.raises(RuntimeError, match="max match time 301.0s exceeds 300.0s"):
        assert_within_limit([1.0, 2.0, 301.0], 300.0)


def test_mirror_gate_rejects_nonpositive_worker_counts(tmp_path):
    with pytest.raises(ValueError, match="workers must be positive"):
        run_mirror("missing", games=1, max_match_seconds=1, agents_root=tmp_path, workers=0)
