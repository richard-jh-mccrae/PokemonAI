"""The dashboard's arithmetic: agreement per deck, gaps per affected decision, regressions."""
from __future__ import annotations

from types import SimpleNamespace

from train.ledger_corpus import _satisfies_human, payload, render_markdown


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
    rows = [row("a_deck", "r1", agrees=True, gaps=["unknown card 5", "no formula for x"]),
            row("a_deck", "r2", agrees=True, gaps=["unknown card 5"]),
            row("a_deck", "r3", agrees=True)]
    result = payload(rows)
    assert result["decks"]["a_deck"]["gap_census"] == {"unknown card 5": 2,
                                                       "no formula for x": 1}
    # One decision with two gap kinds is ONE affected decision, not two.
    assert result["decks"]["a_deck"]["gap_decisions"] == 2


def test_any_recorded_alternative_ruling_satisfies():
    """Frames like 6154988eb489 rule several picks equally correct; grading only the primary
    `correct` list was mis-reporting the alternatives as misses."""
    from common.option_equivalence import option_equivalence

    correction = SimpleNamespace(correct=[0], correct_alternatives=[[1], [6]])
    options = [{"type": 7, "index": index} for index in range(8)]
    equivalence = option_equivalence(options, {"current": {"players": []}})
    assert _satisfies_human([0], correction, equivalence)
    assert _satisfies_human([6], correction, equivalence)
    assert not _satisfies_human([3], correction, equivalence)


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


def test_the_real_producer_feeds_the_dashboard_shape():
    """Every other test here builds rows with the `row()` fixture, a hand-maintained mirror of
    `_replay_one`'s output — the check-the-serializer trap. This replays ONE real correction
    frame through the real producer (fresh runtime, live Ledger brain, cgpy previews) and runs
    the result through payload + render_markdown, so a shape drift between the producer and
    the consumers fails here instead of shipping silently."""
    from pathlib import Path

    from train.blunder.store import load_corrections
    from train.ledger_corpus import _replay_one

    store = (Path(__file__).resolve().parents[2] / "data" / "corrections"
             / "mega_starmie_20260813_c9991b12")
    frame = next(record for record in load_corrections(store)
                 if record.obs is not None
                 and (record.obs.get("select") or {}).get("context") == 0
                 and int((record.obs.get("current") or {}).get("turn", 0)) > 0)
    produced = _replay_one("mega_starmie", frame)

    assert produced["backend"] == "ledger"      # the live brain answered, not a fallback
    fixture_keys = set(row("a_deck", "r1", agrees=True)) - {"ledger"}
    assert fixture_keys <= set(produced), fixture_keys - set(produced)
    if "ledger" in produced:                    # misses carry the price breakdown
        assert set(row("a_deck", "r1", agrees=True)["ledger"]) <= set(produced["ledger"])

    rendered = render_markdown(payload([produced]))
    assert "Generality floor" in rendered


def test_a_crashed_decision_is_surfaced_even_when_it_agrees():
    """A dead brain that happened to pick the ruled action must show as a CRASH in the
    human-facing dashboard, never as a quiet success."""
    crashed = row("a_deck", "r1", agrees=True)
    crashed["backend"] = "strategy-fallback"
    crashed["fallback"] = {"cause": "exception:ValueError",
                           "error": {"type": "ValueError", "message": "boom"}}
    result = payload([crashed, row("a_deck", "r2", agrees=True)])
    assert result["decks"]["a_deck"]["fallbacks"] == 1
    rendered = render_markdown(result)
    assert "Crashed decisions (1)" in rendered
    assert "exception:ValueError" in rendered and "boom" in rendered
