from sim.strategy_bench import decision_metrics, format_report, summarize_decisions


def _telemetry():
    return [{
        "engine_seat": 1,
        "decision_index": 4,
        "action": {"kind": "card", "card_id": 7},
        "value": 12.5,
        "complete": True,
        "decision_seconds": 60.0,
        "decision_limit_seconds": 60.0,
        "deadline_hit": True,
        "diagnostics": {
            "strategy_snapshot": {"turn": 3},
            "production": {
                "final_incumbent": {
                    "first_found_seconds": 4.0,
                    "stabilized_seconds": 5.0,
                    "strategy_wave": "first",
                    "strategy_focus_position": 3,
                    "strategy_focus_count": 8,
                },
                "incumbent_timeline": [{"elapsed_seconds": 4.0}],
            },
        },
    }]


def test_metrics_preserve_final_incumbent_timing_and_friendly_focus_coordinates():
    rows = decision_metrics(_telemetry(), match_index=2, contestants=("a", "b"))
    assert rows[0]["agent"] == "b"
    assert rows[0]["first_found_seconds"] == 4.0
    assert rows[0]["stabilized_seconds"] == 5.0
    assert rows[0]["strategy_wave"] == "first"
    assert rows[0]["strategy_focus_position"] == 3
    assert rows[0]["strategy_focus_count"] == 8


def test_report_uses_strategy_wave_and_focus_position_language():
    decisions = decision_metrics(_telemetry(), match_index=2, contestants=("a", "b"))
    payload = {
        "config": {"mode": "versus", "decision_timeout": 60.0, "match_timeout": 600.0},
        "matches": [{"winner_seat": 1, "timed_out": (), "match_deadline_hit": False}],
        "decisions": decisions,
        "summary": summarize_decisions(decisions),
    }
    report = format_report(payload)
    assert "Final incumbent first found avg 4.00s" in report
    assert "Strategy wave: first" in report
    assert "Strategy focus position: 3 of 8" in report
