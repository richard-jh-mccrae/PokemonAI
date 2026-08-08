"""The correction-seeded acceptance corpus for the hypergeometric-fetch-closure subsystem.

Each case replays the REAL recorded state through the real `Pilot.explain()` and asserts the human's
`correct` option is chosen. PINS assert it outright; TARGETS are open blunders under
`xfail(strict=True)`, so a flip turns red and forces the promotion. `refuted`/`covered` in
reviewed.json are the ONLY grounds for exclusion.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
CORR = REPO / "data" / "corrections"

# "<ep>-<frame>" -> what the human ruled. PIN = the shipped agent already ranks `correct` top.
PINS = {
    "86091728-19": "attach: the {P} goes to the benched 2nd-line Dreepy, not the role-less off-Line "
                   "Active Munkidori — `prefer-active-attach-in-setup` stands down when a benched "
                   "Line member sits un-powered and the Active isn't a deck attacker; the "
                   "`attach_to_needy_line` tie-break develops the line (promoted from a TARGET by "
                   "the attach-target-priority seam build; either identical Dreepy satisfies it — "
                   "`_matches_up_to_interchangeability`)",
    "83661652-29": "hold: play the Riolu base rather than Ultra Ball away held outs",
    "83661652-40": "keep: play the Riolu, don't shuffle it into Lillie's",
    "85058574-16": "res: Lunar Cycle fuel over the benched Solrock attach",
    "82228640-9": "recovered from the 40 dropped records — the agent already makes the human pick",
    # discard-pair valuation (sets, not sums; role floors)
    "85045840-14": "dp: don't pitch the on-board Dragapult ex to a Budew fetch",
    # These five record a SINGLE flagged discard for a 2-card forced pitch, so they are `correct ⊆
    # chosen` cases — a 1-index `correct` can never equal a 2-index pick.
    "82525101-14": "dp: never Ultra-Ball away the Ignition burst — pitch the duplicate Wally's (⊆)",
    "82749656-20": "dp: keep the ACE SPEC Hero's Cape — give back the redundant Salvatore (⊆)",
    "83686860-18": "dp: don't pitch BOTH Dreepy — one line survives; Judge goes instead (⊆)",
    "82867148-48": "dp: keep the lone Boss's/Harlequin disruptors — pitch a duplicate Lillie's (⊆)",
    "82753746-11": "ft: pitch the role-dead Cinderace after the opening — keep the draw Supporters (⊆)",
    # fetch-target valuation (role × gate × closure)
    "84890060-26": "ft: energy-over-body — the fetched {F} chains attach→retreat→KO",
    "84071010-53": "ft: fetch the Solrock line piece, pre-evos accounted",
    "85059103-9":  "ft: fetch Petrel (→ Fighting Gong → Solrock chain) over a redundant draw "
                   "Supporter — `grab-the-chain-opener` (+15, seam C: a tutor is worth the "
                   "discounted closure it reaches) out-ranks the flat draw band (promoted from a "
                   "TARGET by the tutor-chain grab-value build)",
    "83686860-33": "ft: fetch Munkidori over a redundant Drakloak",
    "85058051-13": "ft: fetch the Lunatone engine the wincon needs",
    "81903490-8":  "ft: Ultra Ball hunts the Mega Starmie ex wincon",
    # whether-to-play / hold the fetch (deadline + whiff)
    "85045840-12": "hold: attach the {P} to Dreepy instead of a needless Ultra Ball",
    # Costed-search POC: 83967841-17/85163634-17 moved; composer plays Ultra Ball on both.
    # shuffle timing & keep-value (the refresh side)
    "82749168-65": "worth: Lillie's stands down (−) holding the Ignition burst before a KO attack "
                   "— `discard_eot` worth 30 (the ladder keep-key band), promoted from a TARGET",
    "82750161-60": "keep: attack (Jetting Blow) over Harlequin at 11-vs-2 (the ADR-0060 anchor)",
    # discard-as-resource (zone-signed worth). No option-level valuation ranks these; what does is
    # scoring the whole TURN.
    "82525741-78": "poffin: don't play a fetch whose target class is exhausted",
    "85058574-114": "hold: don't play Poke Pad when not fetching a Pokemon; keep it as "
                   "Ultra Ball fodder",
    "83457493-31": "keep: pitch dead cards BEFORE the symmetric shuffle (promoted by Issue #455)",
}
TARGETS = {
    # `86091435-68` was REFUTED-AS-LABELED (reviewed.json); its surviving substance rides as
    # `test_deploy_now_drakloak_is_not_pitched` below.
    "83661652-31": "discard/fetch: Ultra Ball discarded Riolu, then fetched Riolu — the sequence is "
                   "the blunder, reopened by Issue #347 ruling",
}
READJUDICATED = {
    "85164605-64": (1, 1182, {742, 65, 741}, "Boss's Orders: deferred board synthesis outranks the "
                                          "former Jetting Blow correction by a positive composer delta"),
}
# A THIRD category, deliberately NOT folded into TARGETS: behaviour that CHANGED under the swap and
# that nobody has ruled on yet. Each keeps its ORIGINAL pin text verbatim.
POC_T4_FLIPS = {
    "83686860-13": "keep: don't refresh a live hand — end the turn (moved by Issue #456's scalar "
                   "refresh valuation; pending human re-adjudication)",
    "83007714-8":  "hold: no need to Ultra Ball — end the turn, hold the outs",
    "85046350-79": "hold: Boss's Orders the KO rather than a dead Poffin",
    "83969481-55": "keep: preserve the healer insuring the LAST wincon — a held `clutch_heal` "
                   "covering an irreplaceable Active takes an insurance slot at its full tier "
                   "instead of the 0.45 latency haircut, so Lillie's prices -8.8 and the agent "
                   "attacks (ADR-0101 amendment; wave-2 ruling, Issue #261)",
    "85785067-42": "res: discard the {F} as Lunar Cycle FUEL, don't attach it",
    "85785067-54": "res: Lunatone's discard-to-draw over the inert attach",
    # Filed by the `shed` WIRING, not the swap: before it, every costed search REFUSED unpriced and
    # the composer had no opinion about an Ultra Ball.
    "83967841-17": "the composer plays Ultra Ball where the human ruled End turn; the costed "
                   "search is priced for the first time",
    "85163634-17": "the composer plays Ultra Ball where the human ruled Attack with Turbo Flare; "
                   "same cause as 83967841-17",
}
# The tagged blunder is DEAD but strict `correct`-equality cannot hold: the residue is a DIFFERENT,
# separately adjudicated line. Assert only the substance.
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
    "82756664-9":   "refuted",
    "86091435-68":  "refuted",    # 2026-07-19 user re-review: the label's 2nd slot was wrong (keep the
                                  # Hammer for the opponent's Active); the equation's pick endorsed. The
                                  # surviving substance = `test_deploy_now_drakloak_is_not_pitched`.
    "83661652-30":  "refuted",
    "83967840-54":  "covered",
}


_REVIEWED = json.loads((CORR / "reviewed.json").read_text(encoding="utf-8"))


def _record(cid: str):
    """THE Corpus Reader, via the shared test helper (ADR-0087 / ADR-0089)."""
    from corpus_helpers import corpus_record
    ep, fr = cid.split("-")
    return corpus_record(ep, int(fr))


def _pilot(agent: str):
    """A FRESH pilot per replay: the Pilot is stateful across `explain()` calls (its deck tracker
    accumulates ONE game), so sharing one FLIPS verdicts — an option scored +8.1 polluted, −6.9 clean."""
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


_ATTACH_TYPES = frozenset({8, "Attach"})    # option "type": engine enum (raw obs) / label (record mirror)
_AREA_ZONE = {4: "active", 5: "bench"}      # engine area code → the obs player zone


def _attach_fingerprint(obs: dict, opt: dict):
    """(hand card, byte-identical target body) — everything but the engine `serial`. None for a
    non-attach option or an unresolvable target; those keep exact-index matching."""
    if opt.get("type") not in _ATTACH_TYPES:
        return None
    cur = obs.get("current") or {}
    players = cur.get("players") or []
    yi = cur.get("yourIndex", 0)
    me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
    bodies = me.get(_AREA_ZONE.get(opt.get("inPlayArea"), ""), []) or []
    i = opt.get("inPlayIndex")
    if not (isinstance(i, int) and 0 <= i < len(bodies)) or not isinstance(bodies[i], dict):
        return None
    body = {k: v for k, v in sorted(bodies[i].items()) if k != "serial"}
    return json.dumps({"card": opt.get("index"), "body": body}, sort_keys=True, default=str)


def _matches_up_to_interchangeability(obs: dict, chosen: set, correct: set) -> bool:
    """Set equality, except that attach picks are compared by `_attach_fingerprint`."""
    if chosen == correct:
        return True
    if len(chosen) != len(correct):
        return False
    opts = (obs.get("select") or {}).get("option") or []

    def _keys(idxs):
        return sorted((_attach_fingerprint(obs, opts[i]) or f"exact:{i}")
                      if 0 <= i < len(opts) else f"exact:{i}" for i in idxs)
    return _keys(chosen) == _keys(correct)


def _replay_picks_correct(cid: str) -> bool:
    """Did the shipped Pilot make the human's pick? A `correct` SHORTER than the forced pick count is
    a partial correction, satisfied by `correct ⊆ chosen`; a full one demands set equality."""
    rec = _record(cid)
    d = _pilot(rec.agent).explain(rec.obs)
    chosen, correct = set(d.chosen), set(rec.correct)
    sel = rec.obs.get("select") or {}
    picks = sel.get("minCount") or sel.get("maxCount") or len(correct) or 1
    if 0 < len(correct) < picks:                 # a partial discard correction: the flagged card(s) only
        return correct <= chosen
    return _matches_up_to_interchangeability(rec.obs, chosen, correct)


def _expanded_deferred(rec, index):
    from common import apply_option as ao
    pilot = _pilot(rec.agent)
    my_index = int((rec.obs.get("current") or {}).get("yourIndex") or 0)
    model = pilot._leaf_state_model(rec.obs, my_index)
    return ao.apply_option(model, rec.obs["select"]["option"][index],
                           expand_deferred_targets=True,
                           search_api=getattr(pilot, "_search_api", None))


def _param(cid, reason, *, xfail):
    marks = (pytest.mark.xfail(reason=reason, strict=True),) if xfail else ()
    return pytest.param(cid, id=cid, marks=marks)


_CASES = ([_param(c, r, xfail=False) for c, r in PINS.items()]
          + [_param(c, r, xfail=True) for c, r in TARGETS.items()]
          + [_param(c, r, xfail=True) for c, r in POC_T4_FLIPS.items()])


@pytest.mark.req("REQ-CORPUS-0001")
@pytest.mark.parametrize("cid", _CASES)
def test_correction_ranks_the_human_pick_top(cid):
    """TARGETS are xfail-strict, so a flip becomes an XPASS that says: promote this id to a pin."""
    assert _replay_picks_correct(cid), (
        f"{cid}: expected {_record(cid).correct_label!r}, "
        f"got {_record(cid).chosen_label!r}")


@pytest.mark.req("REQ-CORPUS-0001")
@pytest.mark.parametrize("cid,expected_index,expected_card,expected_targets,_why", [
    pytest.param(cid, index, card, targets, why, id=cid)
    for cid, (index, card, targets, why) in READJUDICATED.items()
])
def test_re_adjudicated_deferred_choice_has_a_positive_composer_reason(
        cid, expected_index, expected_card, expected_targets, _why):
    """A legal deferred Supporter replaces the old correction only through positive leaf value."""
    rec = _record(cid)
    d = _pilot(rec.agent).explain(rec.obs)
    assert rec.correct == [5], "the original Jetting Blow correction is retained as audit history"
    choice = _expanded_deferred(rec, expected_index)
    from common import apply_option as ao
    from corpus_helpers import opponent_active_ids
    assert isinstance(choice, ao.Expectation)
    assert len(choice.classes) == len(expected_targets)
    assert opponent_active_ids(choice) == expected_targets
    assert d.chosen == [expected_index]
    assert d.options[expected_index].card_id == expected_card
    assert d.composer and d.composer["first_index"] == expected_index
    assert d.composer["margin"]["chosen_delta"] > 0.0


@pytest.mark.req("REQ-CORPUS-0001")
@pytest.mark.parametrize("cid", [pytest.param(c, id=c) for c in SUBSTANCE_PINS])
def test_substance_pin_the_tagged_blunder_is_dead(cid):
    """The blunder is not made AND prices <= 0, without pinning the alternative line."""
    rec = _record(cid)
    d = _pilot(rec.agent).explain(rec.obs)
    blunder = set(rec.chosen)
    assert not (blunder & set(d.chosen)), f"{cid}: still makes the tagged pick {rec.chosen_label!r}"
    for t in d.options:
        if t.index in blunder:
            assert t.score <= 0, (f"{cid}: the tagged blunder option [{t.index}] still prices "
                                  f"{t.score:+.1f} — the fix is an accident of ordering, not a floor")


@pytest.mark.req("REQ-CORPUS-0001")
def test_deploy_now_drakloak_is_not_pitched():
    """The surviving substance of the refuted `86091435-68`: whatever fills the other Ultra-Ball
    slot, the hand Drakloak — the only card that can evolve the active Dreepy — must not be pitched."""
    rec = _record("86091435-68")
    p = _pilot(rec.agent)
    d = p.explain(rec.obs)
    sel = rec.obs["select"]
    drakloak = [i for i, o in enumerate(sel.get("option") or [])
                if p._option_card_id(rec.obs, sel, o) == 120]
    assert drakloak, "fixture drift: no Drakloak option in the recorded select"
    assert not (set(drakloak) & set(d.chosen)), \
        f"the deploy-now Drakloak {drakloak} was pitched: chosen={d.chosen}"


@pytest.mark.req("REQ-CORPUS-0001")
@pytest.mark.parametrize("cid,why", sorted(EXCLUDED.items()))
def test_excluded_ids_are_provably_out(cid, why):
    """Every excluded correction is out for a checkable reason — a `refuted`/`covered` disposition in
    reviewed.json, or a genuinely unreplayable record — never silent omission of a live target."""
    ep, fr = cid.split("-")
    if why in ("refuted", "covered"):
        disp = _REVIEWED.get(f"{ep}-{fr}", {}).get("disposition")
        assert disp == why, f"{cid}: claimed {why}, reviewed.json says {disp!r}"
    else:                                       # no third ground survives — see the 82228640-9 note
        raise AssertionError(f"{cid}: unrecognised exclusion ground {why!r}")


def test_corpus_families_are_disjoint_and_ided():
    """No id is double-listed across categories — the audit surface stays clean."""
    cats = [set(PINS), set(TARGETS), set(POC_T4_FLIPS), set(SUBSTANCE_PINS), set(EXCLUDED)]
    for i, a in enumerate(cats):
        for b in cats[i + 1:]:
            assert not (a & b), f"an id is listed in two categories: {sorted(a & b)}"
