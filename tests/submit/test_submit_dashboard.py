"""Dashboard: state vs. performance over time across all Submissions (ADR-0019)."""
import pytest

from submit.dashboard import render_dashboard


@pytest.mark.req("REQ-SUB-0012")
def test_dashboard_joins_state_and_performance_with_a_matchup_dropdown():
    history = [{"submission_id": 1, "built_at": "2026-06-25T08:00:00", "git_hash": "abc1234",
                "summary": {"tier": 0, "general_hyps": 10, "deck_hyps": 3}}]
    performance = [{"submission_id": 1, "sampled_at": "2026-06-26T08:00:00", "public_score": 1200.0,
                    "record": {"wins": 5, "losses": 2},
                    "matchups": [{"archetype": "Dragapult ex", "wins": 3, "losses": 1}]}]

    html = render_dashboard(history, performance)

    assert "http://" not in html and "https://" not in html      # self-contained
    assert "1200" in html and "5-2" in html                       # score + record joined by id
    assert "Dragapult ex" in html and "<details" in html          # per-archetype matchup dropdown
