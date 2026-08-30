from types import SimpleNamespace

from train.ledger_correction_gate import (
    correction_gate_findings,
    is_one_ply_ledger_correction,
    ledger_correction_sources,
)
from train.blunder.correction import correction_selection_error
from train.blunder.reviewed import load_reviewed, review_key
from train.blunder.store import load_corrections


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


def test_one_ply_gate_routes_puct_attribution_out_of_ledger_replay():
    assert is_one_ply_ledger_correction(SimpleNamespace(attribution=None))
    assert not is_one_ply_ledger_correction(
        SimpleNamespace(attribution="puct_search"))


def test_new_round_routing_is_pinned_to_atomic_vs_ordered_work():
    sources = {
        path.parent.name: path for path in ledger_correction_sources()
        if path.parent.name in {
            "20260829-181337_db2e41bd_mega_starmie",
            "20260829-184447_db2e41bd_mega_lucario",
        }}
    corrections = [
        correction for source in sources.values()
        for correction in load_corrections(source, dedup=False)]
    reviewed = load_reviewed()

    puct = {correction.id for correction in corrections
            if not is_one_ply_ledger_correction(correction)
            or reviewed.get(review_key(correction), {}).get("disposition")
            == "deferred-multi-turn"}
    retired = {correction.id for correction in corrections
               if review_key(correction) in reviewed and correction.id not in puct}
    active = {correction.id for correction in corrections
              if is_one_ply_ledger_correction(correction)
              and review_key(correction) not in reviewed}

    assert puct == {
        "0583a2df47ee", "16d8f143c500", "23ab3ad8add1",
        "17a0280c2b26", "27269b208744", "439acf9eebf0", "bad3f5423491",
    }
    assert retired == {
        "39270eede285",
    }
    assert active == {
        "024d2b10765c", "1fff89399198",
        "2109d00a2f31", "61ab038cc160", "86ff10e9f2ef",
        "974a2484f8ee", "9e56f5f95b91", "c7cb00f2f8e7",
        "fcd365f4e685", "feaaa877cebe",
    }


def test_gate_fails_any_unreplayed_record_or_violated_preference():
    report = {
        "rows": [{"id": "a", "grading_exclusion": None,
                  "agent_build": "20260830-082433_d00f93d6_mega_starmie"},
                 {"id": "b", "grading_exclusion": "search_incomplete",
                  "agent_build": "20260830-082433_d00f93d6_mega_starmie"}],
        "retired": [],
    }
    audit = {
        "summary": {"incomplete": 1, "violated_preferences": 2,
                    "conflict_sets": 0},
        "audits": [
            {"correction_id": "a", "gradeable": True,
             "satisfied_by_committed": False,
             "margin": {"atomic": -1.0}, "current_selection": [2],
             "acceptable_selections": [[1]]},
            {"correction_id": "a", "gradeable": True,
             "satisfied_by_committed": False,
             "margin": {"atomic": -0.5}, "current_selection": [3],
             "acceptable_selections": [[1]]},
            {"correction_id": "b", "gradeable": False,
             "satisfied_by_committed": False,
             "margin": {"atomic": None}, "current_selection": None,
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
    report = {"rows": [{
        "id": "a", "grading_exclusion": None,
        "agent_build": "20260830-082433_d00f93d6_mega_starmie",
    }], "retired": []}
    audit = {
        "summary": {"incomplete": 0, "violated_preferences": 1,
                    "conflict_sets": 0},
        "audits": [{"correction_id": "a", "gradeable": True,
                    "satisfied_by_committed": True,
                    "margin": {"atomic": 1.0}, "current_selection": [1],
                    "acceptable_selections": [[1], [3]]}],
    }

    assert correction_gate_findings(report, audit, correction_count=1) == ()


def test_gate_rejects_repeating_the_recorded_blunder_even_with_positive_margin():
    report = {
        "rows": [{
            "id": "a", "grading_exclusion": None, "graded": True,
            "agrees": False, "chosen": [0], "recorded_chosen": [0],
            "agent_build": "20260830-082433_d00f93d6_mega_starmie",
        }],
        "retired": [],
    }
    audit = {
        "summary": {"incomplete": 0, "violated_preferences": 0,
                    "conflict_sets": 0},
        "audits": [{"gradeable": True, "satisfied_by_committed": True,
                    "margin": {"atomic": 1.0}, "current_selection": [0],
                    "acceptable_selections": [[2]]}],
    }

    assert correction_gate_findings(report, audit, correction_count=1) == (
        "1 correction replays repeat the recorded blunder",)


def test_gate_rejects_a_different_wrong_choice_despite_positive_pairwise_margin():
    report = {
        "rows": [{
            "id": "a", "grading_exclusion": None, "graded": True,
            "agrees": False, "chosen": [1], "recorded_chosen": [0],
            "agent_build": "20260830-082433_d00f93d6_mega_starmie",
        }],
        "retired": [],
    }
    audit = {
        "summary": {"incomplete": 0, "violated_preferences": 0,
                    "conflict_sets": 0},
        "audits": [{"correction_id": "a", "gradeable": True,
                    "satisfied_by_committed": True,
                    "margin": {"atomic": 1.0}, "current_selection": [1],
                    "acceptable_selections": [[2]]}],
    }

    assert correction_gate_findings(report, audit, correction_count=1) == (
        "1 correction replays choose outside the ruling",)


def test_exact_selection_gate_does_not_reinterpret_legacy_pairwise_corrections():
    report = {
        "rows": [{
            "id": "a", "grading_exclusion": None, "graded": True,
            "agrees": False, "chosen": [1], "recorded_chosen": [0],
            "agent_build": "20260829-235959_old_mega_starmie",
        }],
        "retired": [],
    }
    audit = {
        "summary": {"incomplete": 0, "violated_preferences": 0,
                    "conflict_sets": 0},
        "audits": [{"correction_id": "a", "gradeable": True,
                    "satisfied_by_committed": False,
                    "margin": {"atomic": -1.0}, "current_selection": [1],
                    "acceptable_selections": [[2]]}],
    }

    assert correction_gate_findings(report, audit, correction_count=1) == ()


def test_exact_selection_gate_keeps_legacy_replay_failures_informational():
    report = {"rows": [{
        "id": "a", "grading_exclusion": "search_incomplete", "fallback": True,
        "agent_build": "20260829-235959_old_mega_starmie",
    }], "retired": []}
    audit = {
        "summary": {"incomplete": 1, "violated_preferences": 0,
                    "conflict_sets": 1},
        "minimal_conflict_sets": [["a", "legacy-peer"]],
        "audits": [{"correction_id": "a", "gradeable": False,
                    "satisfied_by_committed": False,
                    "margin": {"atomic": None}, "current_selection": None,
                    "acceptable_selections": [[2]]}],
    }

    assert correction_gate_findings(report, audit, correction_count=1) == ()


def test_exact_selection_gate_rejects_a_new_correction_without_a_ruling():
    report = {"rows": [{
        "id": "a", "grading_exclusion": "no_ruling", "graded": False,
        "agent_build": "20260830-082433_d00f93d6_mega_starmie",
    }], "retired": []}
    audit = {"summary": {"incomplete": 0, "violated_preferences": 0,
                         "conflict_sets": 0}, "audits": []}

    assert correction_gate_findings(report, audit, correction_count=1) == (
        "1 correction replays are structurally incomplete",)


def test_gate_requires_every_ruled_alternative_to_beat_the_recorded_choice():
    report = {"rows": [{
        "id": "a", "grading_exclusion": None,
        "agent_build": "20260830-082433_d00f93d6_mega_starmie",
    }], "retired": []}
    audit = {
        "summary": {"incomplete": 0, "violated_preferences": 1,
                    "conflict_sets": 0},
        "audits": [{"correction_id": "a", "gradeable": True,
                    "satisfied_by_committed": False,
                    "margin": {"atomic": -1.0}, "current_selection": [3],
                    "acceptable_selections": [[1], [2]],
                    "acceptable_preferences": [
                        {"selection": [1], "margin": -1.0},
                        {"selection": [2], "margin": 0.25},
                    ]}],
    }

    assert correction_gate_findings(report, audit, correction_count=1) == (
        "1 correction preferences are violated",)


def test_refresh_supporter_ordering_is_deferred_to_full_turn_search():
    correction = next(
        correction for correction in load_corrections(ledger_correction_sources()[0])
        if correction.id == "061e8f4e6878")

    review = load_reviewed()[review_key(correction)]

    assert review["disposition"] == "deferred-multi-turn"
    assert "PUCT" in review["reason"]
