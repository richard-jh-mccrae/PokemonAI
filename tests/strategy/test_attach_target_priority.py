"""Attach-target priority in setup: Active vs the benched 2nd line (corpus target 86091728-19).

The seam (grilled 2026-07-19; its plan doc `seam-attach-target-priority.md` retired after the
build — git history): at a setup attach,
`prefer-active-attach-in-setup` (+8) tipped the {P} onto the Active Munkidori — a body the deck never
declared as an attacker (no Role, off-Line; its Adrena-Brain wants {D}) — while two bare Dreepy
(the declared win-condition Line base) sat benched. The human wants the line developed.

The grilled ruling: the +8's charter is "prefer the ACTIVE **attacker**" (ep83007714 f7: bare Active
Cinderace, an `accel_source`, over benched Staryu). It STANDS DOWN when the Active is neither a Line
member nor carries any attacker Role (declared or derived) while a benched Line member still needs
Energy (`board.bench_line_member_needs`). Active and bench then tie and the existing decide()-only
`attach_to_needy_line` tie-break (ep82867148 f87) routes the Energy to the benched line — no new
currency. The rejected framing "the Active's next-attack cost is already covered" is pinned OUT here:
the Active in the acceptance record is BARE, so that predicate is false and could never flip it.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

_ATTACH, _BENCH = 8, 5
_PSYCHIC_ENERGY, _DREEPY, _MUNKIDORI = 5, 119, 112


def _record():
    corr = REPO / "data" / "corrections" / "dragapult_ex_20260715_32530b9" / "corrections.jsonl"
    for line in corr.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if str(d.get("episode_id")) == "86091728" and d.get("decision", {}).get("frame") == 19:
            return d
    raise AssertionError("correction 86091728-19 not found in data/corrections/")


def _pilot(agent: str):
    """A fresh pilot (the Pilot is stateful across explain() calls — corpus instrument finding)."""
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


@pytest.fixture(scope="module")
def decision():
    rec = _record()
    return rec, _pilot(rec["agent"]).explain(rec["obs"])


def _me(rec):
    return rec["obs"]["current"]["players"][rec["obs"]["current"].get("yourIndex", 0)]


@pytest.mark.req("REQ-CORPUS-0001")
def test_the_psychic_goes_to_a_bare_benched_dreepy(decision):
    """The turn's {P} lands on a bare benched Dreepy (the declared Line base), not the role-less
    off-Line Active Munkidori. EITHER of the two byte-identical Dreepy satisfies the human's intent
    (the 074df7c interchangeability precedent)."""
    rec, d = decision
    assert len(d.chosen) == 1
    opt = rec["decision"]["options"][d.chosen[0]]
    assert opt["type"] == "Attach", f"picked {opt} — not an attach"
    card = _me(rec)["hand"][opt["index"]]
    assert card["id"] == _PSYCHIC_ENERGY, f"attached {card['name']}, not the Basic {{P}}"
    assert opt["inPlayArea"] == _BENCH, "the {P} went to the Active, not the benched line"
    body = _me(rec)["bench"][opt["inPlayIndex"]]
    assert body["id"] == _DREEPY and not body["energies"], "target is not a bare benched Dreepy"


@pytest.mark.req("REQ-CORPUS-0001")
def test_prefer_active_stands_down_for_the_roleless_offline_active(decision):
    """`prefer-active-attach-in-setup` does NOT fire on the {P}→Active-Munkidori option: the Active
    carries no attacker Role and is off-Line while a benched Line member still needs Energy. The
    charter's other gates are live on this record (Active needs Energy, not doomed) — the stand-down
    is what silences it, not an incidental gate."""
    rec, d = decision
    active_p = next(t for t in d.options
                    if rec["decision"]["options"][t.index].get("type") == "Attach"
                    and rec["decision"]["options"][t.index].get("inPlayArea") == 4
                    and _me(rec)["hand"][rec["decision"]["options"][t.index]["index"]]["id"]
                    == _PSYCHIC_ENERGY)
    fired = {h.id for h, _ in active_p.fired}
    assert "prefer-active-attach-in-setup" not in fired, (
        "the +8 still fires on the role-less off-Line Active — the stand-down is not live")
    assert "power-up-attacker" in fired, (
        "the Active attach lost more than the tie-break — power-up-attacker should still price it")
