"""Consumer helper: artifact matchup table -> posterior-weighted favorability."""
import pytest

from common.scouting.artifact import Artifact
from common.scouting.matchup import matchup_favorability


def _art() -> Artifact:
    return Artifact(
        priors={}, card_inclusion={}, background={},
        dossiers={"Mine": {"matchups": {
            "Foe":   {"win_rate": 0.8, "n": 10.0},
            "Other": {"win_rate": 0.3, "n": 5.0},
        }}},
    )


@pytest.mark.req("REQ-SCOUT-0009")
def test_favorability_is_posterior_weighted():
    fav, cov = matchup_favorability(_art(), "Mine", [("Foe", 0.75), ("Other", 0.25)])
    assert fav == pytest.approx(0.75 * 0.8 + 0.25 * 0.3)   # 0.675
    assert cov == pytest.approx(1.0)                        # both cells present


@pytest.mark.req("REQ-SCOUT-0009")
def test_unknown_candidate_is_neutral_and_uncovered():
    fav, cov = matchup_favorability(_art(), "Mine", [("Stranger", 1.0)])
    assert fav == pytest.approx(0.5)   # no cell → neutral contribution
    assert cov == pytest.approx(0.0)   # nothing actually covered


@pytest.mark.req("REQ-SCOUT-0009")
def test_partial_coverage_blends_default():
    fav, cov = matchup_favorability(_art(), "Mine", [("Foe", 0.5), ("Stranger", 0.5)])
    assert fav == pytest.approx(0.5 * 0.8 + 0.5 * 0.5)   # 0.65
    assert cov == pytest.approx(0.5)


@pytest.mark.req("REQ-SCOUT-0009")
def test_empty_or_unknown_degrades_to_neutral():
    assert matchup_favorability(Artifact({}, {}, {}, {}), "X", [("Y", 1.0)]) == (0.5, 0.0)
    assert matchup_favorability(_art(), "Mine", []) == (0.5, 0.0)
    assert matchup_favorability(_art(), "Ghost", [("Foe", 1.0)]) == (0.5, 0.0)
