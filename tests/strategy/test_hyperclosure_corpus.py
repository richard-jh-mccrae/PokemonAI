"""The correction-seeded acceptance corpus for the hypergeometric-fetch-closure subsystem
(spec §Round 10 §1). The ~35 recorded shuffle / fetch / discard blunders that ARE the acceptance
suite: each replays the REAL recorded state through the real `Pilot.explain()` and asserts the
human's `correct` option is the one chosen (the `tests/strategy/test_blunder_*` harness).

Two roles, one corpus (the TDD ratchet):
  * **PINS** — corrections the shipped agent ALREADY gets right. Plain assertions: they lock the
    behaviour the staged WP7 value convergences (refresh-SHED → keep-cost, fetch grab/pitch → the
    oracle) must NOT regress — the net that makes each flip provable instead of reckless (ADR-0065).
  * **TARGETS** — open blunders the convergence is meant to FIX, marked `xfail(strict=True)`. They
    are green while unfixed; when a flip makes one pass, the strict-xfail turns it into a red XPASS —
    the signal to PROMOTE it from a target to a pin. Delete the `xfail` mark, keep the id.

Provenance & filtering (spec): ids are `<episode_id>-f<frame>`, drawn verbatim from the spec's family
lists; every record is read from the committed `data/corrections/`; `reviewed.json` is joined first —
`refuted` and `covered` corrections do NOT become fixtures (`test_excluded_ids_are_provably_out` proves
each exclusion). One id (`82228640-9`) carries no `agent`/obs and is unreplayable — excluded, noted.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CORR = REPO / "data" / "corrections"

# ── The families (spec §Round 10 §1). "<ep>-<frame>": each entry is a real recorded correction. ──
#    PIN  = the shipped agent already ranks `correct` top today (a regression guard).
#    TGT  = an open blunder; the staged convergence must flip it (xfail-strict target).
PINS = {
    # discard-pair valuation (sets, not sums; role floors)
    "85045840-14": "dp: don't pitch the on-board Dragapult ex to a Budew fetch",
    # fetch-target valuation (role × gate × closure)
    "84890060-26": "ft: energy-over-body — the fetched {F} chains attach→retreat→KO",
    "84071010-53": "ft: fetch the Solrock line piece, pre-evos accounted",
    "83686860-33": "ft: fetch Munkidori over a redundant Drakloak",
    "85058051-13": "ft: fetch the Lunatone engine the wincon needs",
    "81903490-8":  "ft: Ultra Ball hunts the Mega Starmie ex wincon",
    # whether-to-play / hold the fetch (deadline + whiff)
    "83007714-8":  "hold: no need to Ultra Ball — end the turn, hold the outs",
    "85045840-12": "hold: attach the {P} to Dreepy instead of a needless Ultra Ball",
    "83967841-17": "hold: hold the Ultra Ball, end the turn",
    "83661652-29": "hold: play the Riolu base rather than Ultra Ball away held outs",
    "82525741-78": "hold: evolve Mega Starmie ex instead of a Poffin with the line set",
    "85046350-79": "hold: Boss's Orders the KO rather than a dead Poffin",
    # shuffle timing & keep-value (the refresh side)
    "83686860-13": "keep: don't refresh a live hand — end the turn",
    "83661652-40": "keep: play the Riolu, don't shuffle it into Lillie's",
    "82750161-60": "keep: attack (Jetting Blow) over Harlequin at 11-vs-2 (the ADR-0060 anchor)",
    "83457493-31": "keep: pitch dead cards BEFORE the symmetric shuffle",
    # discard-as-resource (zone-signed worth)
    "85785067-42": "res: discard the {F} as Lunar Cycle FUEL, don't attach it",
    "85785067-54": "res: Lunatone's discard-to-draw over the inert attach",
    "85058574-16": "res: Lunar Cycle fuel over the benched Solrock attach",
}
TARGETS = {
    # discard-pair valuation
    "82525101-14": "dp: kept Ignition — never Ultra-Ball it away; pitch the duplicate",
    "82749656-20": "dp: pitched the ACE SPEC Hero's Cape",
    "83686860-18": "dp: pitched BOTH Dreepy — killed a line (the pair-valuation case)",
    "82867148-48": "dp: duplicates-first pitching",
    "86091435-68": "dp: pitch order / duplicate-first at the Lillie's shuffle",
    # fetch-target valuation
    "82753746-11": "ft: role-dead Cinderace — gate closed after opening",
    "85059103-9":  "ft: fetched a duplicate of a held card",
    # whether-to-play / hold the fetch
    "86091728-19": "hold: attach the {P} to Dreepy rather than a needless Ultra Ball",
    "85163634-17": "hold: attack (Turbo Flare) instead of Ultra Ball",
    "85164605-64": "hold: attack (Jetting Blow) instead of Ultra Ball",
    "82754241-12": "hold: Ultra Ball over Poffin when the Staryu line is exhausted",
    # shuffle timing & keep-value (the refresh side — the SHED convergence's own targets)
    "83038055-51": "keep: strong hand → attack (Nebula Beam), don't refresh",
    "82752045-94": "keep: >7 good cards → attack, don't shuffle them away",
    "82749168-65": "keep: Ignition/Wally's valued by next-turn need — attack instead",
    "83969481-55": "keep: attack (Jetting Blow) over Lillie's on a live hand",
    "83037962-49": "keep: attack over Harlequin (symmetric refresh returns their board)",
}
# Provably out (spec: refuted/covered don't become fixtures; one record is unreplayable).
EXCLUDED = {
    "82524455-6":   "refuted",
    "85058574-114": "refuted",
    "82756664-9":   "refuted",
    "83661652-30":  "covered",
    "83661652-31":  "covered",
    "83967840-54":  "covered",
    "82228640-9":   "no-agent",   # record carries no `agent`/obs — unreplayable
}


def _build_index() -> dict:
    """Every committed correction keyed by (episode_id, frame). Last write wins — the same decision
    tagged across builds is one correction."""
    index = {}
    for jf in CORR.glob("*/corrections.jsonl"):
        for line in jf.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            index[(str(d.get("episode_id")), d.get("decision", {}).get("frame"))] = d
    return index


_INDEX = _build_index()
_REVIEWED = json.loads((CORR / "reviewed.json").read_text(encoding="utf-8"))
_PILOTS: dict = {}


def _record(cid: str) -> dict:
    ep, fr = cid.split("-")
    rec = _INDEX.get((ep, int(fr)))
    assert rec is not None, f"correction {cid} not found in data/corrections/"
    return rec


def _pilot(agent: str):
    if agent not in _PILOTS:
        spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _PILOTS[agent] = mod._build_pilot(agent)[0]
    return _PILOTS[agent]


def _replay_picks_correct(cid: str) -> bool:
    rec = _record(cid)
    d = _pilot(rec["agent"]).explain(rec["obs"])
    return list(d.chosen) == list(rec["correct"])


def _param(cid, reason, *, xfail):
    marks = (pytest.mark.xfail(reason=reason, strict=True),) if xfail else ()
    return pytest.param(cid, id=cid, marks=marks)


_CASES = ([_param(c, r, xfail=False) for c, r in PINS.items()]
          + [_param(c, r, xfail=True) for c, r in TARGETS.items()])


@pytest.mark.req("REQ-CORPUS-0001")
@pytest.mark.parametrize("cid", _CASES)
def test_correction_ranks_the_human_pick_top(cid):
    """Replay the recorded decision through the real Pilot: the human's `correct` option is chosen.
    PINS assert it (regression net for the staged convergences); TARGETS xfail-strict until a flip
    lands (then the XPASS says: promote this id from a target to a pin)."""
    assert _replay_picks_correct(cid), (
        f"{cid}: expected {_record(cid)['correct_label']!r}, "
        f"got {_record(cid)['chosen_label']!r}")


@pytest.mark.req("REQ-CORPUS-0001")
@pytest.mark.parametrize("cid,why", sorted(EXCLUDED.items()))
def test_excluded_ids_are_provably_out(cid, why):
    """Every excluded correction is out for a checkable reason — a `refuted`/`covered` disposition in
    reviewed.json, or a genuinely unreplayable record — never silent omission of a live target."""
    ep, fr = cid.split("-")
    if why in ("refuted", "covered"):
        disp = _REVIEWED.get(f"{ep}-{fr}", {}).get("disposition")
        assert disp == why, f"{cid}: claimed {why}, reviewed.json says {disp!r}"
    elif why == "no-agent":
        assert not _record(cid).get("agent"), f"{cid}: claimed no-agent but a record agent exists"


def test_corpus_families_are_disjoint_and_ided():
    """No id is both a pin and a target or double-listed — the audit surface stays clean."""
    assert not (set(PINS) & set(TARGETS)), "an id is both a pin and a target"
    assert not (set(PINS | TARGETS) & set(EXCLUDED)), "an id is both included and excluded"
