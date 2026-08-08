"""The correction-seeded acceptance corpus for the gusting Round-0 build (ADR-0066).

Each case replays the REAL recorded state through the real `Pilot.explain()`, fresh pilot per replay.
Four roles: PINS (the human's `correct` is chosen), SUBSTANCE (the blunder is dead but the residue
is off-axis), REFUTED_GUARDS (a board proving a gate holds), ADJUDICATED (the AGENT's line was ruled
better).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from poc_t4_flips import record_reason

REPO = Path(__file__).resolve().parents[2]
CORR = REPO / "data" / "corrections"

BOSS = 1182   # Boss's Orders card id (the gust Supporter every case turns on)

# 85163079-30 MOVED to `poc_t4_flips.CORPUS_RECORD_FLIPS` (Issue #386): the seam cannot model a gust,
# so the pin cannot hold. `GUST_REFUSALS` there names all five affected frames together.
PINS = {}
# The Boss's blunder is dead (no gust rule fires, the option is not chosen); the residue is a
# different axis (f109: which KO attack after the dig; f13: retreat-vs-fetch under famine).
SUBSTANCE = {
    "82753102-109": "threat-forfeit premium: the 2-prize gust+snipe stands down when the menu KO "
                    "removes the hand-size Alakazam dooming my Active",
    "86091435-13":  "marginal stall: wall-for-equal-wall famine gust stands down (Duraludon for "
                    "Duraludon denies nothing)",
}
# reviewed.json-refuted boards that prove a gate holds its ground.
REFUTED_GUARDS = {
    "82224509-46": "equal-prize gust of a BARE Riolu pre-evo: gust-for-the-loaded-equal-ko must "
                   "stay silent (energy swing −1 < 2) — the refutation that sized the swing gate",
}
# Human-adjudicated divergences (reviewed.json refuted-by-better-line): pin the AGENT's line.
ADJUDICATED = {
    "86091435-119": "gust-for-the-ko endorses Boss's and it is chosen — the 2-prize "
                    "drag-and-spread line (gust Duraludon, Phantom Dive KOs it AND Relicanth), "
                    "adjudicated over the correction's 1-prize development line 2026-07-19",
}


def _record(cid: str):
    """THE Corpus Reader, via the shared test helper (ADR-0087 / ADR-0089)."""
    from corpus_helpers import corpus_record
    ep, fr = cid.split("-")
    return corpus_record(ep, int(fr))


def _pilot(agent: str):
    """A FRESH pilot per replay (statefulness lesson — see test_hyperclosure_corpus._pilot)."""
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


def _explain(cid: str):
    rec = _record(cid)
    # `replay_agent` is the shared fallback; it survives for the corpus's one `SkiChu` record, which
    # has no agent directory.
    from corpus_helpers import replay_agent
    return rec, _pilot(replay_agent(rec)).explain(rec.obs)


def _boss_options(decision):
    return [o for o in decision.options if o.card_id == BOSS]


@pytest.mark.req("REQ-CORPUS-0002")
@pytest.mark.parametrize("cid", [pytest.param(c, id=c) for c in PINS])
def test_round0_correction_ranks_the_human_pick_top(cid):
    rec, d = _explain(cid)
    assert set(d.chosen) == set(rec.correct), (
        f"{cid}: expected {rec.correct_label!r}, got options {sorted(d.chosen)}")


@pytest.mark.req("REQ-CORPUS-0002")
@pytest.mark.parametrize("cid", [pytest.param(c, id=c) for c in SUBSTANCE])
def test_round0_boss_blunder_is_dead(cid):
    """The tagged Boss's play must be silent (no gust hypothesis endorses it, score ≤ 0) and not
    chosen — the substance of the correction, whatever fills the frame instead."""
    rec, d = _explain(cid)
    boss = _boss_options(d)
    assert boss, f"{cid}: no Boss's Orders option on the menu"
    for o in boss:
        assert not o.fired, f"{cid}: {[h.id for h, _ in o.fired]} endorsed the refuted gust"
        assert o.score <= 0


@pytest.mark.req("REQ-CORPUS-0002")
@pytest.mark.parametrize("cid", [pytest.param(c, id=c) for c in ADJUDICATED])
def test_round0_adjudicated_line_is_taken(cid):
    """The ACTION, not which rung endorsed it, after the gust synthesis is available."""
    _rec, d = _explain(cid)
    boss = _boss_options(d)
    assert boss, f"{cid}: no Boss's Orders option on the menu"
    assert any(o.index in d.chosen for o in boss)
