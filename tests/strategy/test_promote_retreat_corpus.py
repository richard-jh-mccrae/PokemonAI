"""Promote/retreat DECIDER — LIVE-PILOT seam on corpus frames (ADR-0100, #141).

Seam 2 of the phase's three (pure function · live Pilot · gates): the same claims the pure seam pins
over stated measurements, now made end-to-end through the real Pilot on real recorded boards. What
this proves that the pure seam cannot is that the Pilot FILLS the measurements correctly — the
clocks, the Budgets, the areas — so a term that is right in the abstract is also right on a board.

Every assertion is a DECISION claim (which option the agent takes) or a TERM-PRESENCE claim (this
site priced it at all), never a raw score: 1c is a ~10x re-banding of the family, and ADR-0072's
rewrite of f29 from a score claim to a decision claim is the prior art for why a magnitude target
would be re-tuned into meaninglessness by the next phase.

Fixtures are the frames walked in the grill; card facts verified at source.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from poc_t4_flips import marks

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "corrections"

_PICK_CTX = (3, 4)      # _SWITCH / _TO_ACTIVE — every option is a promote/retreat body
_RETREAT = 12


def _pilot(agent: str):
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


def _frame(agent: str, fixture: str):
    fx = json.loads((FIXTURES / f"{fixture}.json").read_text(encoding="utf-8"))
    return fx, _pilot(agent).explain(fx["obs"])


def _rows(dec):
    return {i: t.promote_retreat_working for i, t in enumerate(dec.options)
            if t.promote_retreat_working is not None}


# ---- the body PICK site (a forced promote, and a retreat destination) ---------------------------

def test_pick_promotes_the_accelerator_f120():
    """The 1-prize accelerator that CAN act out-ranks the empty line piece — a damage fact under
    `my_yield`, where the rung asserted it as a `+50` on a role tag."""
    fx, dec = _frame("mega_starmie", "pr_promote_accelerator_f120")
    assert fx["obs"]["select"]["context"] in _PICK_CTX
    assert dec.chosen == fx["correct"]


def test_pick_promotes_the_most_built_copy_f104():
    """Three copies of the SAME 3-prize body, so exposure cannot separate them and only `my_yield`
    can: the ready copy out-ranks the empty one (ADR-0100 §3, retiring `is_best_promote_target`)."""
    fx, dec = _frame("mega_starmie", "pr_promote_ready_wincon_f104")
    rows = _rows(dec)
    assert dec.chosen == fx["correct"]
    picked = rows[fx["correct"][0]]
    assert picked["my_yield"] > 0
    assert all(r["my_yield"] <= picked["my_yield"] for r in rows.values())


def test_pick_at_a_switch_uses_the_same_evaluator_f92():
    """ADR-0100 §9: a SWITCH destination is priced by the SAME evaluator as a forced promote, and the
    A-side terms are absent because they are constant across destinations."""
    fx, dec = _frame("mega_starmie", "pr_retreat_into_ready_wincon_f92")
    rows = _rows(dec)
    assert dec.chosen == fx["correct"]
    assert all(r["site"] == "pick" for r in rows.values())
    assert all(r["preservation"] == 0.0 and r["retreat_cost"] == 0.0 for r in rows.values())


# ---- the WHETHER-to-retreat site (a MAIN menu carrying a native RETREAT) ------------------------

def _whether_row(dec, obs):
    options = obs["select"]["option"]
    idx = next(i for i, o in enumerate(options) if o.get("type") == _RETREAT)
    return idx, dec.options[idx].promote_retreat_working


@pytest.mark.xfail(strict=True, reason=marks("pr_whether_dont_retreat_f9")[0].kwargs["reason"])
def test_whether_declines_the_needless_retreat_f9():
    """`stay_forgone` is DELETED (ADR-0100 §2) — the Active's attack is its OWN option, so the
    comparison IS the differential — and the retreat now pays the build its discard destroys (§8)."""
    fx, dec = _frame("mega_starmie", "pr_whether_dont_retreat_f9")
    idx, row = _whether_row(dec, fx["obs"])
    assert row is not None and row["site"] == "whether"
    assert row["total"] < 0                              # not worth it
    assert idx not in dec.chosen and dec.chosen == fx["correct"]


@pytest.mark.xfail(strict=True, reason=marks("pr_whether_should_retreat_f37")[0].kwargs["reason"])
def test_whether_takes_the_retreat_into_the_finisher_f37():
    """82756664-37 (MAIN, bad_retreat): "should retreat to Mega Starmie for the KO and snipe". The
    benched finisher out-earns staying, so the retreat prices POSITIVE and is taken."""
    fx, dec = _frame("mega_starmie", "pr_whether_should_retreat_f37")
    _idx, row = _whether_row(dec, fx["obs"])
    assert row["total"] > 0
    assert dec.chosen == fx["correct"]


def test_whether_no_longer_recuses_when_the_active_can_ko_f59():
    """ADR-0100 §1 deletes the recusal: layers SUM, and a layer that cannot see a fact prices it 0
    rather than abstaining. The residual must stay strictly sub-lethal for that sum to be honest."""
    from common.strategy.context import KO_SCORE
    fx = json.loads((FIXTURES / "pr_whether_active_can_ko_f59.json").read_text(encoding="utf-8"))
    dec = _pilot("mega_starmie").explain(fx["obs"])
    _idx, row = _whether_row(dec, fx["obs"])
    assert row is not None                               # priced, not recused
    assert abs(row["total"]) < KO_SCORE                  # …and still sub-lethal


# ---- the CLAIMS each pick-site fixture declares (ADR-0072 decision 3, ADR-0100 §12) ------------

@pytest.mark.parametrize("agent,fixture", [
    ("mega_starmie", "pr_promote_accelerator_f120"),
    ("mega_starmie", "pr_promote_ready_wincon_f104"),
    ("mega_starmie", "pr_retreat_into_ready_wincon_f92"),
    ("dragapult_ex", "dragapult_promote_over_fragile_base_f31"),
])
def test_the_pick_site_axis_claims(agent, fixture):
    """ADR-0100 §12: Axis Claims are added ONLY to pick-site frames. An ORDERING within `PROMOTE_LANE`
    survives a re-banding where a score would not, and a non-promote option out-scoring it is irrelevant."""
    from train.gates import PROMOTE_LANE, evaluate_axis_claim, parse_claims
    fx = json.loads((FIXTURES / f"{fixture}.json").read_text(encoding="utf-8"))
    claims = parse_claims(fx)
    assert claims.axis, f"{fixture} declares no Axis Claim"
    dec = _pilot(agent).explain(fx["obs"])
    sel = fx["obs"].get("select") or {}
    options, ctx = sel.get("option") or [], sel.get("context")
    scores = [None] * len(options)
    for o in dec.options:
        scores[o.index] = o.score
    for c in claims.axis:
        assert c.lane == PROMOTE_LANE, f"{fixture}: axis claim is not in the promote lane"
        assert evaluate_axis_claim(c, options=options, scores=scores, select_context=ctx) is True, (
            f"{fixture} axis claim {c.prefer} over {c.over}: scores={scores}")


@pytest.mark.parametrize("agent,fixture", [
    ("mega_starmie", "pr_promote_accelerator_f120"),
    ("mega_starmie", "pr_promote_ready_wincon_f104"),
    ("mega_starmie", "pr_retreat_into_ready_wincon_f92"),
])
def test_the_whether_argmax_equals_the_pick_argmax(agent, fixture):
    """ADR-0100 §9: the body the whether-site would retreat INTO must be the body the pick-site
    promotes. The A-side terms are a CONSTANT offset across destinations, so they cannot reorder."""
    fx, dec = _frame(agent, fixture)
    rows = _rows(dec)
    assert rows, "the decider priced nothing on a promote/retreat select"
    best = max(rows, key=lambda i: rows[i]["total"])
    assert best == fx["correct"][0]
