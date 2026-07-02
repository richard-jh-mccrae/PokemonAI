"""Card-popularity ranking from meta episodes (``meta_tracker.meta_usage``). Lib-free."""
import pytest

from meta_tracker.meta_usage import rank_card_usage


@pytest.mark.req("REQ-FUNC-0014")
def test_rank_weights_by_band_sums_both_decks_and_excludes():
    eps = [
        {"band": "Elite", "deck0": [100, 100, 3], "deck1": [200]},
        {"band": "Mid",   "deck0": [100], "deck1": [3]},
    ]
    counts = rank_card_usage(eps, band_weights={"Elite": 3, "Mid": 1}, exclude_ids={3})
    assert counts[100] == 3 * 2 + 1 * 1   # Elite (x2 copies *3) + Mid (x1 *1)
    assert counts[200] == 3               # Elite (x1 *3)
    assert 3 not in counts                # basic Energy excluded


@pytest.mark.req("REQ-FUNC-0014")
def test_rank_unweighted_defaults_to_one_per_band():
    eps = [{"band": "High", "deck0": [7], "deck1": [7, 9]}]
    counts = rank_card_usage(eps)          # no weights → every copy counts 1
    assert counts[7] == 2 and counts[9] == 1


@pytest.mark.req("REQ-FUNC-0014")
def test_rank_tolerates_missing_fields():
    assert rank_card_usage([{"band": "Mid"}, {}]) == {}   # no decks → empty, never raises
