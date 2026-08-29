from train.ledger_correction_gate import correction_gate_findings, ledger_correction_sources


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
        tmp_path / names[1] / "corrections.jsonl",
        tmp_path / names[2] / "corrections.jsonl",
    )


def test_gate_fails_any_unreplayed_record_or_violated_preference():
    report = {
        "rows": [{"id": "a", "grading_exclusion": None},
                 {"id": "b", "grading_exclusion": "search_incomplete"}],
        "retired": [],
    }
    audit = {"summary": {"incomplete": 1, "violated_preferences": 2,
                         "conflict_sets": 0}}

    assert correction_gate_findings(report, audit, correction_count=3) == (
        "replayed 2 of 3 corrections",
        "1 correction replays are structurally incomplete",
        "1 pairwise value audits are incomplete",
        "2 correction preferences are violated",
    )


def test_gate_fails_closed_when_no_corrections_are_selected():
    report = {"rows": [], "retired": []}
    audit = {"summary": {"incomplete": 0, "violated_preferences": 0,
                         "conflict_sets": 0}}

    assert correction_gate_findings(report, audit, correction_count=0) == (
        "no one-ply Ledger corrections selected",)
