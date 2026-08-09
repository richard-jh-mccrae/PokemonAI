"""The GRAB-side refresh value (`_grab_refresh_value`, ADR-0122 amendment).

A grabbed refresh is priced at the SWING playing it produces — `_refresh_swing`, the identical
quantity `_refresh_swing_tactical` scores at the PLAY seam — so the grab reads magnitude AND the
GIFT a symmetric refill hands the opponent, which `own_draw_count` alone cannot see:

    Lillie's   CYCLE 20 − shed 0 (empty hand) − gift 0     = +20
    Judge      CYCLE 20 − shed 0              − gift 8×2   = +4

The flat `grab-a-draw-supporter-in-setup` (+10) is RETIRED in the same change (ADR-0069 §7).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

PETREL, JUDGE, LILLIES = 1219, 1213, 1227


def _record(episode: str, frame: int):
    """THE Corpus Reader, via the shared test helper (ADR-0087 / ADR-0089)."""
    from corpus_helpers import corpus_record
    return corpus_record(episode, frame)


def _pilot():
    """A FRESH pilot per test — the Pilot is stateful across `explain()` calls (corpus discipline)."""
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot("mega_lucario")[0]


def _by_card(dec):
    out = {}
    for t in dec.options:
        out.setdefault(t.card_id, t)
    return out


@pytest.mark.req("REQ-DISRUPT-0001")
def test_lillies_outranks_judge_by_the_swing_not_by_a_tiebreak():
    """The MARGIN is the point: the swing prices the 8-vs-4 draw AND the cards Judge hands the
    opponent, so any flat category credit collapses the gap."""
    dec = _pilot().explain(_record("86088989", 29).obs)
    by_card = _by_card(dec)
    judge, lillies = by_card[JUDGE], by_card[LILLIES]
    assert lillies.score > judge.score
    assert lillies.score - judge.score == pytest.approx(16.0)




@pytest.mark.req("REQ-DISRUPT-0001")
def test_the_category_rung_is_retired_so_the_swing_cannot_double_count():
    """ADR-0069 §7: a category credit for the very thing the swing measures is DELETED, not left
    underneath, or the two stack into an exact tie the option index then breaks."""
    from common.strategy.general_strategy import GENERAL_STRATEGY
    assert not any(h.id == "grab-a-draw-supporter-in-setup" for h in GENERAL_STRATEGY.hypotheses)
