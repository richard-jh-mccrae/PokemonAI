"""M3 drop-in engine (ADR-0059): the ``cg.game`` twin + alias, DLL-free.

Runs whole games through the aliased ``cg`` surface exactly as the battle harness does —
vanilla decks only (every card union-covered), seeded chaos policy.
"""
import json
import random
from pathlib import Path

import pytest

from cgpy import alias
from cgpy.verify.trace import Trace

FIXDIR = Path(__file__).resolve().parents[1] / "fixtures" / "parity"


@pytest.fixture
def aliased(monkeypatch):
    """Install the cg->cgpy alias for the test, restoring displaced modules after."""
    monkeypatch.setenv("CGPY_SEED", "11")
    alias.install()
    try:
        yield
    finally:
        alias.uninstall()


def _play_one(rng: random.Random):
    from cg.game import battle_finish, battle_select, battle_start, visualize_data

    tr = Trace.load(FIXDIR / "vanilla2_4000.trace.json.gz")
    deck0, deck1 = tr.decks
    obs, start = battle_start(deck0, deck1)
    assert (start.errorPlayer, start.errorType) == (-1, 0) and start.battlePtr
    choices = []
    for _ in range(2000):
        cur = obs.get("current") or {}
        if cur.get("result", -1) != -1:
            break
        sel = obs["select"]
        assert obs["search_begin_input"].startswith("cgpy/1:")
        k = rng.randint(sel["minCount"], sel["maxCount"])
        choice = rng.sample(range(len(sel["option"])), k) if k else []
        choices.append(choice)
        obs = battle_select(choice)
    viz = json.loads(visualize_data())
    battle_finish()
    return obs, choices, viz


@pytest.mark.req("REQ-CGPY-M3-0008")
def test_self_play_to_result_with_visualize_alignment(aliased):
    obs, choices, viz = _play_one(random.Random(5))
    assert obs["current"]["result"] != -1
    assert len(viz) == len(choices) + 1
    for k, choice in enumerate(choices):
        assert viz[k + 1]["selected"] == choice          # the +1-offset convention
    assert viz[0]["selected"] is None
    names = {l["type"] for f in viz for l in f["logs"]}
    assert {"Draw", "MoveCard", "Shuffle"} <= names      # god logs: CamelCase name-strings
    assert viz[-1]["current"]["players"][0]["deck"], "god frame must reveal decks"


@pytest.mark.req("REQ-CGPY-M3-0008")
def test_seeded_self_play_is_reproducible(aliased):
    a = _play_one(random.Random(9))
    b = _play_one(random.Random(9))
    assert a[0]["current"]["result"] == b[0]["current"]["result"]
    assert a[1] == b[1]


@pytest.mark.req("REQ-CGPY-M3-0009")
def test_battle_start_deck_validation_parity(aliased):
    from cg.game import battle_start

    tr = Trace.load(FIXDIR / "vanilla2_4000.trace.json.gz")
    deck0, deck1 = tr.decks
    with pytest.raises(ValueError, match="The deck must contain 60 cards."):
        battle_start(deck0[:59], deck1)
    bad = [deck0[0]] * 60                                # >4 copies of one name
    obs, start = battle_start(bad, deck1)
    assert obs is None and start.errorPlayer == 0 and start.errorType == 2
    assert not start.battlePtr


@pytest.mark.req("REQ-CGPY-M3-0009")
def test_battle_select_exception_classes(aliased):
    from cg.game import battle_finish, battle_select, battle_start

    tr = Trace.load(FIXDIR / "vanilla2_4000.trace.json.gz")
    deck0, deck1 = tr.decks
    obs, _ = battle_start(deck0, deck1)
    with pytest.raises(ValueError, match="select_list is not list"):
        battle_select("0")
    with pytest.raises(IndexError):
        battle_select([len(obs["select"]["option"])])    # out of range, native class
    battle_finish()
    with pytest.raises(ValueError, match="battle_ptr broken."):
        battle_select([0])


@pytest.mark.req("REQ-CGPY-M3-0010")
def test_alias_restores_displaced_modules():
    import sys
    sentinel = object()
    saved = sys.modules.get("cg")
    sys.modules["cg"] = sentinel
    try:
        alias.install()
        import cgpy.compat
        assert sys.modules["cg"] is cgpy.compat
        alias.uninstall()
        assert sys.modules["cg"] is sentinel
    finally:
        if saved is not None:
            sys.modules["cg"] = saved
        else:
            sys.modules.pop("cg", None)
