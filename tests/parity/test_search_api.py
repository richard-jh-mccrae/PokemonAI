"""M3 verification API (ADR-0050): seeding, sessions, manual coin, compat — DLL-free.

The committed native traces double as the seeding oracle: every recorded frame carries the
live obs (what `state_from_obs` gets) AND the god frame (the true hidden zones, standing in
for a caller's predictions), so a seeded engine can be checked for an EXACT re-render of the
recorded select+current and then stepped with the recorded choice.
"""
import json
from pathlib import Path

import pytest

from cgpy.engine import Engine
from cgpy.rng import SeededRng
from cgpy.search import (export_token, parse_token, session_begin, session_end,
                         session_step, state_from_obs, state_from_visualize)
from cgpy.verify.differ import first_divergence
from cgpy.verify.trace import Trace

FIXDIR = Path(__file__).resolve().parents[1] / "fixtures" / "parity"
TRACES = sorted(FIXDIR.glob("*.trace.json.gz"))
_CRUSHING_HAMMER = 1120
_SETUP_CTX = (1, 2, 38, 41, 42)     # setup machine selects: not a seeding target


def _god_predictions(fr):
    yi = fr["obs"]["current"]["yourIndex"]
    god = fr["god"]
    gme, gopp = god["players"][yi], god["players"][1 - yi]
    return ([c["id"] for c in gme["deck"]], [c["id"] for c in gme["prize"]],
            [c["id"] for c in gopp["deck"]], [c["id"] for c in gopp["prize"]],
            [c["id"] for c in gopp["hand"]])


def _seed(fr, **kw):
    yd, yp, od, op_, oh = _god_predictions(fr)
    return state_from_obs(dict(fr["obs"]), yd, yp, od, op_, oh, [], **kw)


def _select_current(obs):
    return {"select": obs["select"], "current": obs["current"]}


@pytest.mark.req("REQ-CGPY-M3-0001")
@pytest.mark.parametrize("path", TRACES, ids=lambda p: p.name.split(".")[0])
def test_seeded_states_rerender_the_recorded_obs_and_step(path):
    """Every seedable recorded select re-renders select+current byte-exactly and accepts
    the recorded choice. Non-seedable frames must be rejected with a diagnosable error,
    never mis-seeded (the fail-loud contract)."""
    tr = Trace.load(path)
    seeded = 0
    for k, fr in enumerate(tr.frames):
        sel = fr["obs"].get("select") or {}
        if fr.get("god") is None or fr.get("choice") is None:
            continue
        if sel.get("context") in _SETUP_CTX:
            continue
        yi = fr["obs"]["current"]["yourIndex"]
        try:
            eng = _seed(fr)
        except ValueError:
            continue                      # documented non-seedable class (fail-loud)
        ours = eng.observation(viewer=yi, sbi_token=None)
        d = first_divergence(_select_current(fr["obs"]), _select_current(ours))
        assert d is None, f"{path.name} f{k}: seeded render diverged\n{d}"
        eng.step(list(fr["choice"]))
        assert eng.gs.pending is not None or eng.result != -1, f"{path.name} f{k}: dead state"
        seeded += 1
    assert seeded >= 5, f"{path.name}: only {seeded} frames seeded — oracle too thin"


@pytest.mark.req("REQ-CGPY-M3-0001")
def test_state_from_obs_validation_matches_native_messages():
    tr = Trace.load(TRACES[0])
    fr = next(f for f in tr.frames
              if (f["obs"].get("select") or {}).get("context") == 0 and f.get("god"))
    yd, yp, od, op_, oh = _god_predictions(fr)
    obs = dict(fr["obs"])

    with pytest.raises(ValueError, match="your_deck does not match"):
        state_from_obs(obs, yd[:-1], yp, od, op_, oh, [])
    with pytest.raises(ValueError, match="your_prize does not match"):
        state_from_obs(obs, yd, yp[:-1], od, op_, oh, [])
    with pytest.raises(ValueError, match="opponent_deck does not match"):
        state_from_obs(obs, yd, yp, od[:-1], op_, oh, [])
    with pytest.raises(ValueError, match="opponent_prize does not match"):
        state_from_obs(obs, yd, yp, od, op_[:-1], oh, [])
    with pytest.raises(ValueError, match="opponent_hand does not match"):
        state_from_obs(obs, yd, yp, od, op_, oh[:-1], [])
    with pytest.raises(ValueError, match="Invalid Card ID."):
        state_from_obs(obs, [999999] + yd[1:], yp, od, op_, oh, [])
    with pytest.raises(ValueError, match="Not agent observation."):
        state_from_obs({"select": None, "current": None, "logs": []}, yd, yp, od, op_, oh, [])


@pytest.mark.req("REQ-CGPY-M3-0002")
def test_manual_coin_poses_coin_head_and_resumes():
    """manual_coin=True: a Crushing Hammer play suspends at a COIN_HEAD YesNo (ctx 46)
    instead of consuming rng; answering resumes the program (the Solver's soundness hook)."""
    checked = 0
    for path in TRACES:
        tr = Trace.load(path)
        for fr in tr.frames:
            sel = fr["obs"].get("select") or {}
            if (sel.get("type"), sel.get("context")) != (0, 0) or fr.get("god") is None:
                continue
            yi = fr["obs"]["current"]["yourIndex"]
            hand = fr["obs"]["current"]["players"][yi].get("hand") or []
            play_i = next((i for i, o in enumerate(sel.get("option") or [])
                           if o.get("type") == 7
                           and hand[o["index"]]["id"] == _CRUSHING_HAMMER), None)
            if play_i is None:
                continue
            eng = _seed(fr, manual_coin=True)
            eng.step([play_i])
            p = eng.gs.pending
            assert p is not None and p.context == 46, f"expected COIN_HEAD, got {p}"
            assert [o["type"] for o in p.options] == [1, 2]      # YES / NO
            eng.step([0])                                        # choose heads -> resumes
            assert eng.gs.pending is not None or eng.result != -1
            checked += 1
            break
        if checked:
            break
    assert checked, "no trace offered a Crushing Hammer play at MAIN"


@pytest.mark.req("REQ-CGPY-M3-0003")
def test_state_token_reseeds_a_live_game_exactly():
    """Observations from a live cgpy engine carry the state token; reseeding from them
    reproduces select+current exactly at every MAIN select of a full self-played game."""
    import random
    tr = Trace.load(FIXDIR / "vanilla2_4000.trace.json.gz")
    deck0, deck1 = tr.decks
    eng, _, _ = Engine.start(deck0, deck1, rng=SeededRng(7))
    rng = random.Random(7)
    seeded = 0
    for _ in range(300):
        if eng.result != -1:
            break
        seat = eng.select_seat
        obs = eng.observation(viewer=seat, sbi_token=export_token(eng.gs))
        p = eng.gs.pending
        if (obs["select"]["type"], obs["select"]["context"]) == (0, 0):
            gs = eng.gs
            me, opp = gs.players[seat], gs.players[1 - seat]
            twin = state_from_obs(obs, [gs.card_id(s) for s in me.deck],
                                  [gs.card_id(s) for s in me.prize],
                                  [gs.card_id(s) for s in opp.deck],
                                  [gs.card_id(s) for s in opp.prize],
                                  [gs.card_id(s) for s in opp.hand], [])
            o2 = twin.observation(viewer=seat, sbi_token=None)
            d = first_divergence(_select_current(obs), _select_current(o2))
            assert d is None, f"token reseed diverged: {d}"
            assert parse_token(export_token(twin.gs))["phase"] == "TURN"
            seeded += 1
        k = rng.randint(p.min_count, p.max_count)
        eng.step(rng.sample(range(len(p.options)), k) if k else [])
    assert seeded >= 3


@pytest.mark.req("REQ-CGPY-M3-0004")
def test_sessions_clone_per_step_and_native_error_strings():
    tr = Trace.load(TRACES[0])
    fr = next(f for f in tr.frames
              if (f["obs"].get("select") or {}).get("context") == 0
              and f.get("god") and f.get("choice"))
    eng = _seed(fr)
    yi = fr["obs"]["current"]["yourIndex"]
    sid = session_begin(eng)
    before = _select_current(eng.observation(viewer=yi, sbi_token=None))

    sid2, stepped = session_step(sid, list(fr["choice"]))
    assert sid2 != sid and stepped is not eng
    after = _select_current(eng.observation(viewer=yi, sbi_token=None))
    assert first_divergence(before, after) is None, "clone-per-step mutated the parent"

    sid3, again = session_step(sid, list(fr["choice"]))          # old id still steppable
    assert sid3 not in (sid, sid2)

    with pytest.raises(ValueError,
                       match="There is no element with the specified search_id."):
        session_step(987654, [0])
    p = eng.gs.pending
    with pytest.raises(ValueError, match="minCount"):
        session_step(sid, list(range(p.max_count + 1)) if p.max_count else [0, 1])
    if p.max_count >= 2 and len(p.options) >= 1:
        with pytest.raises(ValueError, match="Duplicate select elements."):
            session_step(sid, [0, 0])
    with pytest.raises(ValueError, match="0 <= select elements"):
        session_step(sid, [len(p.options)])

    from cgpy.search import session_release
    session_release(sid3)
    with pytest.raises(ValueError, match="Released item."):
        session_step(sid3, [0])
    session_end()
    with pytest.raises(ValueError, match="There is no element"):
        session_step(sid2, [0])


@pytest.mark.req("REQ-CGPY-M3-0005")
def test_state_from_visualize_god_seeding():
    """God-view seeding: with the paired select, the render matches the recorded obs
    exactly; without one, the engine REBUILDS the MAIN menu and it must equal the recorded
    option list (the option builder is the parity-owned surface)."""
    tr = Trace.load(FIXDIR / "ms_mirror_1000.trace.json.gz")
    decks = tr.decks
    checked = 0
    for k, fr in enumerate(tr.frames):
        sel = fr["obs"].get("select") or {}
        if (sel.get("type"), sel.get("context")) != (0, 0) or fr.get("god") is None:
            continue
        yi = fr["obs"]["current"]["yourIndex"]
        eng = state_from_visualize(fr["god"], decks, seat=yi, select=sel)
        ours = eng.observation(viewer=yi, sbi_token=None)
        d = first_divergence(_select_current(fr["obs"]), _select_current(ours))
        assert d is None, f"f{k}: god-seeded render diverged\n{d}"

        rebuilt = state_from_visualize(fr["god"], decks, seat=yi)
        menu = rebuilt.observation(viewer=yi, sbi_token=None)
        d = first_divergence(fr["obs"]["select"], menu["select"])
        assert d is None, f"f{k}: rebuilt MAIN menu diverged from the recorded one\n{d}"
        checked += 1
    assert checked >= 5


@pytest.mark.req("REQ-CGPY-M3-0006")
def test_compat_api_search_flow():
    """The ``cg.api``-shaped surface: dataclass round-trip, search_begin/step/end, root
    observation carrying search_begin_input=None, table functions matching the snapshot."""
    from cgpy.compat import api

    cards = api.all_card_data()
    attacks = api.all_attack()
    assert len(cards) > 1000 and len(attacks) > 1000
    assert isinstance(cards[0].skills, list) and isinstance(cards[0].cardId, int)

    tr = Trace.load(TRACES[0])
    fr = next(f for f in tr.frames
              if (f["obs"].get("select") or {}).get("context") == 0
              and f.get("god") and f.get("choice"))
    obs = dict(fr["obs"])
    obs["search_begin_input"] = "native-blob-stand-in"
    ob = api.to_observation_class(obs)
    assert ob.current.yourIndex == fr["obs"]["current"]["yourIndex"]

    yd, yp, od, op_, oh = _god_predictions(fr)
    st = api.search_begin(ob, yd, yp, od, op_, oh, [], manual_coin=True)
    assert st.observation.search_begin_input is None
    assert st.observation.select is not None
    st2 = api.search_step(st.searchId, list(fr["choice"]))
    assert st2.searchId != st.searchId
    st3 = api.search_step(st.searchId, list(fr["choice"]))   # clone-per-step: old id lives
    assert st3.searchId != st2.searchId
    api.search_end()
    with pytest.raises(ValueError, match="There is no element"):
        api.search_step(st2.searchId, [0])

    with pytest.raises(ValueError, match="Not agent observation."):
        api.search_begin(api.to_observation_class(dict(fr["obs"],
                                                       search_begin_input=None)),
                         yd, yp, od, op_, oh, [])


@pytest.mark.req("REQ-CGPY-M3-0007")
def test_mid_effect_trainer_seeding():
    """A select posed by a trainer's own program (the fetch class correction fixtures
    capture) seeds without a token: the frame is reconstructed from the effect card and
    the recorded pick applies. Ambiguous/unsupported mid-effect states raise."""
    seeded = 0
    for path in TRACES:
        tr = Trace.load(path)
        for k, fr in enumerate(tr.frames):
            sel = fr["obs"].get("select") or {}
            if fr.get("god") is None or fr.get("choice") is None:
                continue
            if sel.get("context") not in (5, 7, 8):   # TO_BENCH / TO_HAND / DISCARD
                continue
            if not sel.get("effect"):
                continue
            try:
                eng = _seed(fr)
            except ValueError:
                continue
            yi = fr["obs"]["current"]["yourIndex"]
            ours = eng.observation(viewer=yi, sbi_token=None)
            d = first_divergence(_select_current(fr["obs"]), _select_current(ours))
            assert d is None, f"{path.name} f{k}: mid-effect render diverged\n{d}"
            assert eng.gs.frames, "no EffectFrame reconstructed"
            eng.step(list(fr["choice"]))
            assert eng.gs.pending is not None or eng.result != -1
            seeded += 1
    assert seeded >= 10, f"only {seeded} mid-effect frames seeded"
