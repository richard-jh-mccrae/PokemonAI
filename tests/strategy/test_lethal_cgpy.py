"""The multi-step lethal verification harness on the cgpy twin — DLL-free (ADR-0050 M3).

The live native-vs-py comparison is ``test_engine_agreement_engine.py``. When the decide() steering
hooks exist, ``engine_confirms_py`` on the bare fixture goes True and THAT is the fix's gate.
"""
import json
from dataclasses import asdict
from pathlib import Path

import pytest

from cgpy import alias
from lethal_helpers import engine_confirms_py

REPO = Path(__file__).resolve().parents[2]

_PETREL, _AIR_BALLOON, _PPP = 1219, 1174, 1141
_MEGA_LUCARIO_EX, _SOLROCK = 678, 676
_AURA_JAB, _COSMIC_BEAM = 982, 980


def _fixture(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / f"{name}.json")
                      .read_text(encoding="utf-8"))


def _deck(agent):
    return [int(x) for x in (REPO / "src" / "agents" / agent / "deck.csv")
            .read_text(encoding="utf-8").split("\n")[:60]]


def _pilot(deck):
    from common.cards import CardFunctions
    from common.effects import CardEffects
    from common.pilot import Pilot
    from common.scouting.provider import EngineCardStatProvider
    from common.strategy import Strategy
    from common.strategy.general_strategy import GENERAL_STRATEGY
    try:
        fns = CardFunctions.load()
    except Exception:
        fns = CardFunctions({})
    # attack facts flow through the provider (ADR-0051), lazily built off whichever engine `cg` maps
    # to — so native/cgpy parity holds without a hand-built table here.
    return Pilot(Strategy(), deck, general_strategy=GENERAL_STRATEGY,
                 stats=EngineCardStatProvider(), functions=fns, effects=CardEffects.load(),
                 lethal_verify=True, lethal_family=True, lethal_veto=True)


# ------------------------------------------------------------------ verdict pins

@pytest.mark.req("REQ-CGPY-M3-0014")
@pytest.mark.parametrize("name,agent,line,expected", [
    ("ms_lethal_recover_energy_to_win_f110", "mega_starmie", None, True),
    ("ml_lethal_recover_energy_retreat_ko_f26", "mega_lucario", None, False),
    ("ml_lethal_recover_energy_via_gong_f48", "mega_lucario", None, False),
    ("ml_lethal_retreat_boost_to_ko_f24", "mega_lucario", None, False),
    # [0] = Play Petrel, the LETHAL framing, not the retired dead-hand `correct` ([1] Lillie's, a
    # draw-6 whose verdict is draw-dependent). False = the steering hooks are unbuilt.
    ("ml_petrel_balloon_retreat_lethal_f15", "mega_lucario", [0], False),
], ids=lambda v: v if isinstance(v, str) else "")
def test_engine_confirms_py_matches_the_native_verdicts(name, agent, line, expected):
    alias.install()
    try:
        pilot = _pilot(_deck(agent))
    finally:
        alias.uninstall()
    assert engine_confirms_py(_fixture(name), pilot, line=line) is expected


@pytest.mark.req("REQ-CGPY-M3-0014")
def test_engine_confirms_py_needs_no_search_begin_input():
    """cgpy seeds from the structured state alone."""
    fx = _fixture("ms_lethal_recover_energy_to_win_f110")
    fx["obs"] = {k: v for k, v in fx["obs"].items() if k != "search_begin_input"}
    assert not fx["obs"].get("search_begin_input")
    alias.install()
    try:
        pilot = _pilot(_deck("mega_starmie"))
    finally:
        alias.uninstall()
    assert engine_confirms_py(fx, pilot) is True


# ------------------------------------------------------------------ identity drive

def _auto(sel):
    n = sel.get("minCount", 0)
    return list(range(n)) if n else []


def _drive_line(pilot, obs, choosers, *, max_selects=30):
    """Each scripted select is chosen BY IDENTITY (the chooser inspects the live obs and names its
    pick); unscripted interstitials — attack riders, prize picks — auto-answer their minimum."""
    from cg import api as cgapi

    from common.strategy.planner import _prune_none

    cur = obs["current"]
    yi = cur["yourIndex"]
    me, opp = cur["players"][yi], cur["players"][1 - yi]
    yd, yp, od_, op_, oh = pilot._seed_zones(obs, me, opp)
    st = cgapi.search_begin(cgapi.to_observation_class(obs), yd, yp, od_, op_, oh, [],
                            manual_coin=True)
    queue = list(choosers)
    try:
        for _ in range(max_selects):
            o = st.observation
            c = o.current
            if c is not None and c.result != -1:
                assert not queue, f"verdict before {len(queue)} scripted picks ran"
                return c.result == yi
            if c is None or o.select is None or c.yourIndex != yi:
                return None
            od = _prune_none(asdict(o))
            sel = od["select"]
            picks = queue[0](od, sel) if queue else None
            if picks is not None:
                queue.pop(0)
            else:
                is_main = (sel.get("type"), sel.get("context")) == (0, 0)
                assert not (queue and is_main), \
                    f"MAIN select did not match the next scripted pick: {sel.get('option')}"
                picks = _auto(sel)
            st = cgapi.search_step(st.searchId, picks)
        return None
    finally:
        cgapi.search_end()


def _play(cid):
    def f(od, sel):
        if (sel.get("type"), sel.get("context")) != (0, 0):
            return None
        hand = od["current"]["players"][od["current"]["yourIndex"]]["hand"]
        for i, o in enumerate(sel["option"]):
            if o.get("type") == 7 and hand[o["index"]]["id"] == cid:
                return [i]
        return None
    return f


def _attach_to_active(cid):
    def f(od, sel):
        if (sel.get("type"), sel.get("context")) != (0, 0):
            return None
        hand = od["current"]["players"][od["current"]["yourIndex"]]["hand"]
        for i, o in enumerate(sel["option"]):
            if (o.get("type") == 8 and o.get("inPlayArea") == 4
                    and hand[o["index"]]["id"] == cid):
                return [i]
        return None
    return f


def _retreat():
    def f(od, sel):
        for i, o in enumerate(sel["option"]):
            if o.get("type") == 12:
                return [i]
        return None
    return f


def _pay_energy():
    def f(od, sel):
        return [0] if sel.get("context") == 30 else None
    return f


def _promote(cid, *, energized=None):
    def f(od, sel):
        if sel.get("context") != 3:
            return None
        bench = od["current"]["players"][od["current"]["yourIndex"]]["bench"]
        for i, o in enumerate(sel["option"]):
            p = bench[o["index"]]
            if p["id"] == cid and (energized is None or bool(p["energyCards"]) == energized):
                return [i]
        return None
    return f


def _attack(attack_id):
    def f(od, sel):
        for i, o in enumerate(sel["option"]):
            if o.get("type") == 13 and o.get("attackId") == attack_id:
                return [i]
        return None
    return f


def _deck_pick(cid):
    def f(od, sel):
        if sel.get("context") != 7 or not sel.get("deck"):
            return None
        listing = sel["deck"]
        for i, o in enumerate(sel["option"]):
            if listing[o["index"]]["id"] == cid:
                return [i]
        return None
    return f


@pytest.mark.req("REQ-CGPY-M3-0015")
def test_f15_retreat_enabler_win_line_is_real_on_cgpy():
    """Petrel -> tutor Air Balloon -> Tool onto Makuhita -> free retreat -> promote Mega Lucario ex
    -> Aura Jab 130 vs Riolu 80 with an empty bench -> the ENGINE declares the win."""
    fx = _fixture("ml_petrel_balloon_retreat_lethal_f15")
    obs = dict(fx["obs"], search_begin_input="cgpy")
    alias.install()
    try:
        pilot = _pilot(_deck("mega_lucario"))
        verdict = _drive_line(pilot, obs, [
            _play(_PETREL),
            _deck_pick(_AIR_BALLOON),
            _attach_to_active(_AIR_BALLOON),
            _retreat(),
            _promote(_MEGA_LUCARIO_EX),
            _attack(_AURA_JAB),
        ])
    finally:
        alias.uninstall()
    assert verdict is True


@pytest.mark.req("REQ-CGPY-M3-0015")
def test_f24_boost_to_ko_win_line_is_real_on_cgpy():
    """Attach {F} to the benched Solrock, 2x Premium Power Pro (+30 {F} each), retreat Lunatone,
    promote the energized Solrock, Cosmic Beam 130 OHKOs Duraludon with an empty bench."""
    fx = _fixture("ml_lethal_retreat_boost_to_ko_f24")
    obs = dict(fx["obs"], search_begin_input="cgpy")
    alias.install()
    try:
        pilot = _pilot(_deck("mega_lucario"))
        verdict = _drive_line(pilot, obs, [
            lambda od, sel: list(fx["correct"])
            if (sel.get("type"), sel.get("context")) == (0, 0) else None,
            _play(_PPP),
            _play(_PPP),
            _retreat(),
            _pay_energy(),
            _promote(_SOLROCK, energized=True),
            _attack(_COSMIC_BEAM),
        ])
    finally:
        alias.uninstall()
    assert verdict is True
