import pytest

from sim.mirror_gate import assert_within_limit, summarize


def test_mirror_summary_reports_per_match_average_minimum_and_maximum():
    assert summarize([1.0, 2.0, 6.0]) == {"avg": 3.0, "min": 1.0, "max": 6.0}


def test_mirror_gate_rejects_the_slowest_match_not_the_average():
    with pytest.raises(RuntimeError, match="max match time 301.0s exceeds 300.0s"):
        assert_within_limit([1.0, 2.0, 301.0], 300.0)
