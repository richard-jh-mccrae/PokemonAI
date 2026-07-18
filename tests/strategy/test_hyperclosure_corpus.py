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
    # These five record a SINGLE flagged discard for a 2-card forced pitch (correct ⊆ chosen, the
    # partial-discard semantics above). The shipped keep-value ladder ALREADY discards the flagged
    # card in each — role-floor + duplicate-first work; they pin that (they were misfiled as targets
    # because a 1-index `correct` can never equal a 2-index pick).
    "82525101-14": "dp: never Ultra-Ball away the Ignition burst — pitch the duplicate Wally's (⊆)",
    "82749656-20": "dp: keep the ACE SPEC Hero's Cape — give back the redundant Salvatore (⊆)",
    "83686860-18": "dp: don't pitch BOTH Dreepy — one line survives; Judge goes instead (⊆)",
    "82867148-48": "dp: keep the lone Boss's/Harlequin disruptors — pitch a duplicate Lillie's (⊆)",
    "82753746-11": "ft: pitch the role-dead Cinderace after the opening — keep the draw Supporters (⊆)",
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
    "85164605-64": "hold: attack (Jetting Blow KO) — the graded refresh shed drops the costly-hand "
                   "Lillie's below tier-0, freeing the lethal (promoted from a TARGET by ADR-0065)",
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
    # The two grab/pitch targets that survive as GENUINE gaps (the other five discard-pair records
    # were malformed single-index fixtures now pinned above). Both need the DEADLINE/gate library, NOT
    # the keep_cost oracle — the shipped ladder already prices roles + redundancy (ADR-0065 §grab/pitch):
    "86091435-68": "dp: don't pitch a Drakloak that can EVOLVE the active Dreepy this turn — a "
                   "deployability deadline (a benched-Drakloak board pitches it correctly, ep83686860 "
                   "f18), which a flat keep_cost floor can't tell apart. Gate library, not keep_cost.",
    "85059103-9":  "ft: fetch Petrel (→ Fighting Gong → Solrock chain) over a redundant draw Supporter "
                   "— the duplicate Lillie's is already avoided (`dont-grab-a-card-already-in-hand`); "
                   "the gap is tutor-chain fetch-priority, not redundancy.",
    # whether-to-play / hold the fetch
    "86091728-19": "attach: the {P} belongs on the benched Dreepy (2nd line), not the Active — the "
                   "Ultra Ball substance is FIXED; the residue is attach-target priority "
                   "(`prefer-active-attach-in-setup` +8 tips it Active). A minor separate axis.",
    "85163634-17": "hold: fetch one turn early = Judge exposure — the held-card-risk tier-2 seam "
                   "(spec §Round 8 §5, explicitly deferred): fetch-late beats fetch-early when "
                   "disruption is live. Not keep-value, not the gate library.",
    # worth-coverage: the refresh SHED under-prices situational Trainers/special Energy — their
    # keep-value lives in the DISCARD ladder (keep-key −30 covers `discard_eot`; dont-waste-clutch-
    # heal) but `role_value` prices them 0 (no ROLE, no tag fallback), so the graded shed lets the
    # refresh stay positive and it plays (tier 3) before the deferred attack. The identified fix:
    # tag-derived worth fallbacks (Round 9 'engine from Function Tags'), measured before flipping.
    "82749168-65": "worth: Lillie's (+) shuffles back the Ignition burst before a KO attack — "
                   "Ignition (`discard_eot`) prices 0 in role_value, so hand_keep can't see it",
    "83969481-55": "worth: Lillie's (+10) shuffles back Wally's Compassion (clutch_heal, role 0) "
                   "that answers next-turn Nebula Beam — same coverage gap + a pressure deadline",
}
# The tagged blunder is DEAD (scores ≤ 0, not chosen) but strict `correct`-equality can't hold —
# the residue is a DIFFERENT, adjudicated or deliberately-designed line. Assert the substance: the
# recorded blunder pick is not made and its option prices ≤ 0.
SUBSTANCE_PINS = {
    "83038055-51": "Lillie's dead (−34); agent attacks. Residue: Jetting-vs-Nebula, ALREADY "
                   "adjudicated in the agent's favour (reviewed.json ep83661649 f30 / ep83116501 "
                   "f60; the f94 precedent test declines to pin Nebula over Jetting).",
    "82752045-94": "Lillie's dead (−10); agent attacks. Same Jetting-vs-Nebula residue, same "
                   "adjudication.",
    "83037962-49": "Harlequin dead (−11, the SHED convergence); agent plays Night Stretcher first — "
                   "`recover-to-refill-bench`'s DESIGNED refill-THEN-attack sequencing (its own "
                   "rationale), the attack follows.",
    "82754241-12": "Poffin dead (−25, `dont-search-an-empty-deck`); the pick is now a PRICED "
                   "refresh-first gamble (52%, EV 525 > det 8 + keep 16) the human never evaluated "
                   "— a line adopted after the correction, not the tagged blunder.",
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


def _record(cid: str) -> dict:
    ep, fr = cid.split("-")
    rec = _INDEX.get((ep, int(fr)))
    assert rec is not None, f"correction {cid} not found in data/corrections/"
    return rec


def _pilot(agent: str):
    """A FRESH pilot per replay — the Pilot is stateful across `explain()` calls (the deck tracker
    accumulates observations of ONE game), so sharing a pilot across corrections from different
    games makes each verdict depend on which replays ran before it (measured: the same option scored
    +8.1 polluted vs −6.9 clean). Slower, sound."""
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


def _replay_picks_correct(cid: str) -> bool:
    """Did the shipped Pilot make the human's pick? Set-valued (order-independent).

    A forced DISCARD select takes ``minCount`` cards, but a human often records only the ONE
    load-bearing card their correction is about ("pitch the duplicate Wally's, not the Ignition") —
    a `correct` shorter than the pick count. Such a partial correction is satisfied iff every card it
    names IS discarded (`correct ⊆ chosen`): the flagged mistake is not made, whatever fills the
    remaining forced slot. A fully-specified correction (as many picks as the select forces) still
    demands set equality."""
    rec = _record(cid)
    d = _pilot(rec["agent"]).explain(rec["obs"])
    chosen, correct = set(d.chosen), set(rec["correct"])
    sel = rec["obs"].get("select") or {}
    picks = sel.get("minCount") or sel.get("maxCount") or len(correct) or 1
    if 0 < len(correct) < picks:                 # a partial discard correction: the flagged card(s) only
        return correct <= chosen
    return chosen == correct


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
@pytest.mark.parametrize("cid", [pytest.param(c, id=c) for c in SUBSTANCE_PINS])
def test_substance_pin_the_tagged_blunder_is_dead(cid):
    """The recorded blunder pick is not made AND its option prices ≤ 0 — the correction's substance,
    without pinning the alternative line (which is separately adjudicated / designed; see
    SUBSTANCE_PINS notes)."""
    rec = _record(cid)
    d = _pilot(rec["agent"]).explain(rec["obs"])
    blunder = set(rec["chosen"])
    assert not (blunder & set(d.chosen)), f"{cid}: still makes the tagged pick {rec['chosen_label']!r}"
    for t in d.options:
        if t.index in blunder:
            assert t.score <= 0, (f"{cid}: the tagged blunder option [{t.index}] still prices "
                                  f"{t.score:+.1f} — the fix is an accident of ordering, not a floor")


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
    """No id is double-listed across categories — the audit surface stays clean."""
    cats = [set(PINS), set(TARGETS), set(SUBSTANCE_PINS), set(EXCLUDED)]
    for i, a in enumerate(cats):
        for b in cats[i + 1:]:
            assert not (a & b), f"an id is listed in two categories: {sorted(a & b)}"
