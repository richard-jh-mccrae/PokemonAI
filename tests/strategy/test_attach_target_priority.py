"""Attach-target priority in setup: Active vs the benched 2nd line (corpus target 86091728-19).

`prefer-active-attach-in-setup` STANDS DOWN when the Active is neither a Line member nor carries an
attacker Role while a benched Line member still needs Energy (`board.bench_line_member_needs`); the
`attach_to_needy_line` tie-break then routes the Energy to the bench.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

_ATTACH, _BENCH = 8, 5
_PSYCHIC_ENERGY, _DREEPY, _MUNKIDORI = 5, 119, 112


def _record():
    """THE Corpus Reader, via the shared test helper (ADR-0087 / ADR-0089)."""
    from corpus_helpers import corpus_record
    return corpus_record("86091728", 19)


def _pilot(agent: str):
    """A fresh pilot (the Pilot is stateful across explain() calls — corpus instrument finding)."""
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


@pytest.fixture(scope="module")
def decision():
    rec = _record()
    return rec, _pilot(rec.agent).explain(rec.obs)


def _me(rec):
    return rec.obs["current"]["players"][rec.obs["current"].get("yourIndex", 0)]


@pytest.mark.req("REQ-CORPUS-0001")
def test_the_psychic_goes_to_a_bare_benched_dreepy(decision):
    """EITHER of the two byte-identical Dreepy satisfies the human's intent."""
    rec, d = decision
    assert len(d.chosen) == 1
    opt = rec.decision["options"][d.chosen[0]]
    assert opt["type"] == "Attach", f"picked {opt} — not an attach"
    card = _me(rec)["hand"][opt["index"]]
    assert card["id"] == _PSYCHIC_ENERGY, f"attached {card['name']}, not the Basic {{P}}"
    assert opt["inPlayArea"] == _BENCH, "the {P} went to the Active, not the benched line"
    body = _me(rec)["bench"][opt["inPlayIndex"]]
    assert body["id"] == _DREEPY and not body["energies"], "target is not a bare benched Dreepy"


@pytest.mark.req("REQ-CORPUS-0001")
def test_prefer_active_stands_down_for_the_roleless_offline_active(decision):
    """The rung's other gates are live on this record (Active needs Energy, not doomed), so the
    stand-down is what silences it rather than an incidental gate."""
    rec, d = decision
    active_p = next(t for t in d.options
                    if rec.decision["options"][t.index].get("type") == "Attach"
                    and rec.decision["options"][t.index].get("inPlayArea") == 4
                    and _me(rec)["hand"][rec.decision["options"][t.index]["index"]]["id"]
                    == _PSYCHIC_ENERGY)
    fired = {h.id for h, _ in active_p.fired}
    assert "prefer-active-attach-in-setup" not in fired, (
        "the prior still fires on the role-less off-Line Active — the stand-down is not live")
    # Still PRICED: the tie-break went quiet, the option did not go dead.
    assert next(r for r in d.attach_working["eq"] if r["i"] == active_p.index)["marginal"] > 0
