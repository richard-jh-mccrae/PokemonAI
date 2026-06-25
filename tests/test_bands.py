"""Rating -> band assignment (dataset path)."""
from meta_tracker.bands import band_of_rating, rating_cutoffs

BANDS3 = [("Elite", 0.0, 2.0), ("High", 2.0, 10.0), ("Mid", 10.0, 50.0)]  # contiguous, drop bottom 50%


def test_rating_cutoffs_and_band_of_rating():
    lb = [{"rank": i, "teamId": i, "teamName": f"t{i}", "score": float(1000 - i)} for i in range(1, 101)]
    cuts = rating_cutoffs(lb, BANDS3)            # scores 999..900 desc
    assert band_of_rating(999, cuts) == "Elite"  # >= score@2%
    assert band_of_rating(990, cuts) == "High"   # >= score@10%, below Elite
    assert band_of_rating(960, cuts) == "Mid"    # >= score@50%, below High
    assert band_of_rating(800, cuts) is None     # below 50th percentile -> dropped


def test_empty_leaderboard_is_safe():
    cuts = rating_cutoffs([], BANDS3)
    assert band_of_rating(1000, cuts) == "Elite"  # all cutoffs 0 -> everything qualifies
