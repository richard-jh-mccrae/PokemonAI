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
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CORR = REPO / "data" / "corrections"

BOSS = 1182   # Boss's Orders card id (the gust Supporter every case turns on)

PINS = {
    "85163079-30": "loaded-equal-KO: Boss's the 4-Energy Staryu (their loading Mega Starmie "
                   "pre-evo) over the equal-prize Cinderace attack — gust-for-the-loaded-equal-ko",
}
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


def _record(cid: str) -> dict:
    ep, fr = cid.split("-")
    for jf in CORR.glob("*/corrections.jsonl"):
        rec = None
        for line in jf.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if str(d.get("episode_id")) == ep and d.get("decision", {}).get("frame") == int(fr):
                rec = d                              # last write wins, like the hyperclosure harness
        if rec is not None:
            return rec
    raise AssertionError(f"correction {cid} not found in data/corrections/")


def _pilot(agent: str):
    """A FRESH pilot per replay (statefulness lesson — see test_hyperclosure_corpus._pilot)."""
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


def _explain(cid: str):
    rec = _record(cid)
    # ep82224509 f46 predates the agent field — the episode is a mega_starmie game (Round-0 grep).
    return rec, _pilot(rec["agent"] or "mega_starmie").explain(rec["obs"])


def _boss_options(decision):
    return [o for o in decision.options if o.card_id == BOSS]


@pytest.mark.req("REQ-CORPUS-0002")
@pytest.mark.parametrize("cid", [pytest.param(c, id=c) for c in PINS])
def test_round0_correction_ranks_the_human_pick_top(cid):
    rec, d = _explain(cid)
    assert set(d.chosen) == set(rec["correct"]), (
        f"{cid}: expected {rec['correct_label']!r}, got options {sorted(d.chosen)}")


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


@pytest.mark.req("REQ-CORPUS-0002")
@pytest.mark.parametrize("cid", [pytest.param(c, id=c) for c in REFUTED_GUARDS])
def test_round0_refuted_board_keeps_the_gate_shut(cid):
    """On the refuted board the loaded-equal tie-break must NOT fire — the human correction was
    wrong to gust, and the swing gate is what keeps the agent right."""
    _rec, d = _explain(cid)
    for o in _boss_options(d):
        assert "gust-for-the-loaded-equal-ko" not in {h.id for h, _ in o.fired}


@pytest.mark.req("REQ-CORPUS-0002")
@pytest.mark.parametrize("cid", [pytest.param(c, id=c) for c in ADJUDICATED])
def test_round0_adjudicated_line_is_taken(cid):
    """The human-adjudicated agent line: Boss's Orders is ENDORSED by gust-for-the-ko (the 2-prize
    drag-and-finish beats the 1-prize menu rider) and chosen at the frame."""
    _rec, d = _explain(cid)
    boss = _boss_options(d)
    assert boss, f"{cid}: no Boss's Orders option on the menu"
    assert any("gust-for-the-ko" in {h.id for h, _ in o.fired} for o in boss)
    assert any(o.index in d.chosen for o in boss)
