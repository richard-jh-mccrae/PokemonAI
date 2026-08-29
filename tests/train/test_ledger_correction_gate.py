from train.ledger_correction_gate import correction_gate_findings, ledger_correction_sources
from train.blunder.correction import correction_selection_error
from train.blunder.store import load_corrections
from train.ledger_corpus import _replay_one


def test_one_ply_gate_selects_every_round_at_or_after_its_first_production_run(tmp_path):
    names = (
        "20260828-111914_ad58ab7d_mega_starmie",
        "20260828-221100_a39dfc83_mega_starmie",
        "20260829-072514_635d215b_mega_lucario",
        "mega_starmie_20260813_c9991b12",
    )
    for name in names:
        directory = tmp_path / name
        directory.mkdir()
        (directory / "corrections.jsonl").touch()

    assert ledger_correction_sources(tmp_path) == (
        tmp_path / names[0] / "corrections.jsonl",
        tmp_path / names[1] / "corrections.jsonl",
        tmp_path / names[2] / "corrections.jsonl",
    )


def test_gate_fails_any_unreplayed_record_or_violated_preference():
    report = {
        "rows": [{"id": "a", "grading_exclusion": None},
                 {"id": "b", "grading_exclusion": "search_incomplete"}],
        "retired": [],
    }
    audit = {
        "summary": {"incomplete": 1, "violated_preferences": 2,
                    "conflict_sets": 0},
        "audits": [
            {"gradeable": True, "satisfied_by_committed": False,
             "margin": {"atomic": -1.0}, "current_selection": [2],
             "acceptable_selections": [[1]]},
            {"gradeable": True, "satisfied_by_committed": False,
             "margin": {"atomic": -0.5}, "current_selection": [3],
             "acceptable_selections": [[1]]},
        ],
    }

    assert correction_gate_findings(report, audit, correction_count=3) == (
        "replayed 2 of 3 corrections",
        "1 correction replays are structurally incomplete",
        "1 pairwise value audits are incomplete",
        "2 correction preferences are violated",
    )


def test_gate_fails_closed_when_no_corrections_are_selected():
    report = {"rows": [], "retired": []}
    audit = {"summary": {"incomplete": 0, "violated_preferences": 0,
                         "conflict_sets": 0}, "audits": []}

    assert correction_gate_findings(report, audit, correction_count=0) == (
        "no one-ply Ledger corrections selected",)


def test_first_one_ply_round_has_valid_single_choice_rulings():
    first = ledger_correction_sources()[0]

    assert [(correction.id, correction_selection_error(correction))
            for correction in load_corrections(first)
            if correction_selection_error(correction)] == []


def test_gate_accepts_a_ruled_current_choice_despite_its_raw_pairwise_margin():
    report = {"rows": [{"id": "a", "grading_exclusion": None}], "retired": []}
    audit = {
        "summary": {"incomplete": 0, "violated_preferences": 1,
                    "conflict_sets": 0},
        "audits": [{"gradeable": True, "satisfied_by_committed": False,
                    "margin": {"atomic": -1.0}, "current_selection": [1],
                    "acceptable_selections": [[1], [3]]}],
    }

    assert correction_gate_findings(report, audit, correction_count=1) == ()


def test_refresh_supporter_does_not_shuffle_away_usable_items():
    correction = next(
        correction for correction in load_corrections(ledger_correction_sources()[0])
        if correction.id == "061e8f4e6878")

    row = _replay_one(correction.agent, correction)

    assert row["chosen"] in row["acceptable"]
