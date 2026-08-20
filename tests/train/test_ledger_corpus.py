"""The dashboard's arithmetic: agreement per deck, gaps per affected decision, regressions."""
from __future__ import annotations

from train.ledger_corpus import payload, render_markdown


def row(deck, row_id, *, agrees, graded=True, gaps=(), chosen=(0,), correct=(1,)):
    return {"deck": deck, "key": f"1-{row_id}", "id": row_id, "scope": "decision",
            "context": "Main", "category": "test", "graded": graded,
            "chosen": list(chosen), "correct": list(correct) if graded else [],
            "exact": False, "agrees": agrees if graded else None,
            "chosen_label": "a", "correct_label": "b", "rationale": "why",
            "gaps": list(gaps), "elapsed_seconds": 0.1,
            "ledger": {"value": 0.0, "backend": "ledger", "weights": "w",
                       "prices": [{"action": "x", "selection": [0], "swing": -0.2,
                                   "ends_turn": False}]}}


def test_payload_reports_per_deck_agreement_and_the_generality_floor():
    rows = [row("a_deck", "r1", agrees=True), row("a_deck", "r2", agrees=True),
            row("b_deck", "r3", agrees=True), row("b_deck", "r4", agrees=False),
            row("b_deck", "r5", agrees=None, graded=False)]
    result = payload(rows)
    assert result["decks"]["a_deck"]["agreement"] == 1.0
    assert result["decks"]["b_deck"]["agreement"] == 0.5
    assert result["decks"]["b_deck"]["ungraded"] == 1
    assert result["generality_floor"] == 0.5


def test_gap_census_counts_decisions_affected_not_mentions():
    rows = [row("a_deck", "r1", agrees=True, gaps=["unknown card 5", "unknown card 5"]),
            row("a_deck", "r2", agrees=True, gaps=["unknown card 5"])]
    result = payload(rows)
    assert result["decks"]["a_deck"]["gap_census"] == {"unknown card 5": 2}


def test_regressions_name_frames_that_used_to_agree():
    baseline = payload([row("a_deck", "r1", agrees=True), row("a_deck", "r2", agrees=False)])
    result = payload([row("a_deck", "r1", agrees=False), row("a_deck", "r2", agrees=False)],
                     baseline=baseline)
    assert result["regressions"] == ["r1"]


def test_markdown_render_carries_the_rationale_beside_the_miss():
    rendered = render_markdown(payload([row("a_deck", "r1", agrees=False)]))
    assert "rationale: why" in rendered
    assert "priced -0.2000 x" in rendered
    assert "Generality floor" in rendered
