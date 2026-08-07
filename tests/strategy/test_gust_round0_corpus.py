"""The correction-seeded acceptance corpus for the gusting Round-0 build (ADR-0066;
docs/plans/gusting-round0-measurement.md). Mirror of `test_hyperclosure_corpus.py`: each case
replays the REAL recorded state through the real `Pilot.explain()` (fresh pilot per replay — the
statefulness lesson) and asserts the Round-0 verdict.

Three roles here:
  * **PINS** — the human's `correct` is now chosen (the three-fix build flipped ep85163079 f30).
  * **SUBSTANCE pins** — the tagged Boss's-Orders blunder is DEAD (the gust rules stay silent and
    the option is not chosen) but strict `correct`-equality can't hold because the residue is a
    different, out-of-gust-scope line (sequencing / attack choice).
  * **REFUTED guards** — reviewed.json-refuted corrections whose boards prove a gate HOLDS (the
    loaded-equal tie-break must not fire on a bare pre-evo, ep82224509 f46).

ep86091435 f119 was ADJUDICATED 2026-07-19 (reviewed.json: refuted-by-better-line): the widened
bench KO oracle finds a 2-prize drag-and-spread line (gust a 130-HP Duraludon, Phantom Dive KOs it
AND the 40-HP Relicanth) that supersedes the human's 1-prize development line — banks 2 of the 4
needed prizes and kills a future Assemble-Alloy accel body, needing no future draws. The ADJUDICATED
pin below locks that line in.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from poc_t4_flips import record_reason

REPO = Path(__file__).resolve().parents[2]
CORR = REPO / "data" / "corrections"

BOSS = 1182   # Boss's Orders card id (the gust Supporter every case turns on)

# 85163079-30 MOVED to `poc_t4_flips.CORPUS_RECORD_FLIPS` (POC-T4/5, Issue #386) — the seam cannot
# model a gust, so the pin cannot hold and pretending it can would make this file dishonest about
# what it covers. `GUST_REFUSALS` there names all five affected frames together.
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
    """THE Corpus Reader, via the shared test helper (ADR-0087 / ADR-0089). `load_corrections`
    dedups, so the old "last write wins" walk and this agree — measured, all 372 committed records
    carry a unique (episode, frame)."""
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
    # `replay_agent` is the shared fallback, and it is no longer papering over a missing `agent`:
    # `Correction.from_dict` backfills it from `agent_build`, so ep82224509 f46 — one of the 40
    # records the raw walk dropped — now reads `mega_starmie` on its own (ADR-0087, Issue #241). The
    # fallback survives for the corpus's one `SkiChu` record, which has no agent directory.
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
        assert o.index not in d.chosen


# A test whose ONLY assertion was `"<deleted-rung>" not in _fired(...)` is DELETED here (POC-T4/5,
# Issue #386). Once the rung is gone that assertion is true of every board in the game, so the test
# went GREEN while checking nothing — a hole no failure count can show. Deleted rather than left
# passing, because dead text that looks like a guard is worse than no guard.
#
# Doubly so here: the test directly above asserts the STRONGER, non-vacuous form of the same fact on
# the same board -- `not o.fired`, `o.score <= 0` and `o.index not in d.chosen`. Nothing is lost.
@pytest.mark.req("REQ-CORPUS-0002")
@pytest.mark.xfail(strict=True, reason=record_reason("86091435", 119))
@pytest.mark.parametrize("cid", [pytest.param(c, id=c) for c in ADJUDICATED])
def test_round0_adjudicated_line_is_taken(cid):
    """The human-adjudicated agent line: Boss's Orders is chosen at the frame — the 2-prize
    drag-and-finish that was ruled better than the correction's 1-prize development line.

    The `gust-for-the-ko` half of this assertion is GONE with the rung (POC-T4/5, Issue #386) and is
    not carried over: it named which rung endorsed the play. What is asserted is the ACTION. It
    currently fails, and `poc_t4_flips.GUST_REFUSALS` says why in one place: the seam cannot model a
    gust at all (`CLAUSE_WRITES['gust']` is non-empty, so `_covers` refuses), so no weighting reaches
    this or the four sibling frames."""
    _rec, d = _explain(cid)
    boss = _boss_options(d)
    assert boss, f"{cid}: no Boss's Orders option on the menu"
    assert any(o.index in d.chosen for o in boss)
