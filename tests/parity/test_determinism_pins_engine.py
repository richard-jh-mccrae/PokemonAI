"""Engine pins for the native-engine determinism facts cgpy relies on (ADR-0059, M0).

Each test re-verifies one empirical fact from docs/pyeng/determinism.md against the live native
lib. If a future engine build changes one, THIS suite fails (a named fact), rather than the
parity corpus failing obscurely. Skips cleanly when the native lib can't load. REQ-CGPY-0001.
"""
from __future__ import annotations

import importlib.util
import json
import random
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

pytest.importorskip("cg.sim", reason="native engine unavailable")

# NATIVE-ONLY: these pin empirical facts about the DLL. Under `CG_ENGINE=py` the module reaches
# past the alias with its own `from cg import api` and ABORTS THE INTERPRETER, so it skips instead.
try:
    from cgpy.alias import installed as _alias_installed
except Exception:                                            # cgpy absent: nothing to guard
    def _alias_installed() -> bool:
        return False

if _alias_installed():
    pytest.skip("native-engine pins: meaningless (and fatal) on the cgpy twin",
                allow_module_level=True)

from cg.game import battle_finish, battle_select, battle_start, visualize_data  # noqa: E402

DEFS = REPO / "src" / "cgpy" / "defs"
_CARDS = json.loads((DEFS / "card_data.json").read_text(encoding="utf-8"))


def _agent_deck(name: str = "mega_starmie") -> list[int]:
    p = REPO / "src" / "agents" / name / "deck.csv"
    return [int(x) for x in p.read_text(encoding="utf-8").split()[:60]]


def _distinct_name_deck(skip: set[int] = frozenset()) -> list[int]:
    seen, deck = set(), []
    for c in _CARDS:
        if c.get("basic") and c["cardType"] == 0 and c["cardId"] not in skip and c["name"] not in seen:
            deck.append(c["cardId"])
            seen.add(c["name"])
        if len(deck) >= 8:
            break
    for c in _CARDS:
        if len(deck) >= 60:
            break
        if c["cardId"] in skip or c["name"] in seen or c["cardType"] == 5 or c.get("aceSpec"):
            continue
        deck.append(c["cardId"])
        seen.add(c["name"])
    return deck


def _drive(obs, rng, steps, until=None):
    """Random-legal driver; stops at result/no-select or when `until(obs)` is truthy."""
    for _ in range(steps):
        if until is not None and until(obs):
            return obs
        cur = obs.get("current") or {}
        if cur.get("result", -1) not in (-1, None):
            return obs
        sel = obs.get("select")
        if sel is None:
            return obs
        k = sel["minCount"] if sel["minCount"] > 0 else (1 if sel["maxCount"] >= 1 else 0)
        pick = rng.sample(range(len(sel["option"])), min(k, len(sel["option"]))) if sel["option"] else []
        obs = battle_select([int(i) for i in pick])
    return obs


def test_serials_are_positional_and_stable():
    """Seat 0 position i -> serial 3+i; seat 1 -> 63+i; frame-0 deck already shuffled."""
    deck0 = _distinct_name_deck()
    deck1 = _distinct_name_deck(skip=set(deck0))
    obs, start = battle_start(deck0, deck1)
    try:
        assert start.errorPlayer == -1
        players = json.loads(visualize_data())[0]["current"]["players"]
        for seat, (deck, base) in enumerate(((deck0, 3), (deck1, 63))):
            pos = {cid: i for i, cid in enumerate(deck)}
            zone = players[seat]["deck"]
            assert [c["id"] for c in zone] != deck, "frame-0 deck should be shuffled"
            for c in zone:
                assert c["serial"] == base + pos[c["id"]], (seat, c)
    finally:
        battle_finish()


def test_is_first_asked_of_seat0_before_deal():
    deck = _agent_deck()
    obs, _ = battle_start(deck, deck)
    try:
        assert obs["current"]["yourIndex"] == 0
        assert obs["current"]["firstPlayer"] == -1
        assert obs["select"]["context"] == 41  # SelectContext.IS_FIRST
        assert obs["current"]["players"][0]["handCount"] == 0  # pre-deal
    finally:
        battle_finish()


def test_select_deck_listing_preserves_true_order():
    """A search select's `deck` listing equals the god-view deck order (not a sort)."""
    deck = _agent_deck()
    rng = random.Random(9)
    for _ in range(20):
        obs, _ = battle_start(deck, deck)
        try:
            obs = _drive(obs, rng, 400, until=lambda o: (o.get("select") or {}).get("deck"))
            sel = obs.get("select") or {}
            if sel.get("deck"):
                seat = obs["current"]["yourIndex"]
                god = json.loads(visualize_data())[-1]["current"]["players"][seat]["deck"]
                assert [(c["id"], c["serial"]) for c in sel["deck"]] == \
                       [(c["id"], c["serial"]) for c in god]
                return
        finally:
            battle_finish()
    pytest.fail("no deck-revealing select reached in 20 chaos games — the pin measured NOTHING. "
                "Measured 25/25 alignment on 2026-07-27, so this is a harness regression (the "
                "chaos driver stopped reaching searches), not bad luck. A skip here would have "
                "retired the pin silently.")


def test_validation_error_codes():
    """BattleStart errorType codes: 1 unknown id, 2 name copies, 3 no basic, 4 ACE SPEC."""
    basics = [c["cardId"] for c in _CARDS if c.get("basic") and c["cardType"] == 0]
    energy = next(c["cardId"] for c in _CARDS if c["cardType"] == 5)
    aces = [c["cardId"] for c in _CARDS if c.get("aceSpec")]
    legal = [basics[0]] * 4 + [basics[1]] * 4 + [energy] * 52

    def verdict(deck0):
        obs, start = battle_start(list(deck0), list(legal))
        battle_finish()
        return start.errorPlayer, start.errorType

    assert verdict(legal) == (-1, 0)
    assert verdict([999999] + [basics[0]] * 4 + [energy] * 55) == (0, 1)
    assert verdict([basics[0]] * 5 + [basics[1]] * 4 + [energy] * 51) == (0, 2)
    assert verdict([energy] * 60) == (0, 3)
    assert verdict(aces[:2] + [basics[0]] * 4 + [energy] * 54) == (0, 4)


def test_fork_reshuffles_but_is_deterministic():
    """search_begin ignores the provided deck order yet is reproducible call-to-call — for forks
    from a plain MAIN select ONLY (determinism.md §4), so chaos games retry until one lands."""
    from cg import api

    deck = _agent_deck()
    rng = random.Random(3)
    for _ in range(20):
        obs, _ = battle_start(deck, deck)
        try:
            obs = _drive(obs, rng, 12)
            if obs.get("select") is None or (obs.get("current") or {}).get("result", -1) not in (-1, None):
                continue  # game ended during setup (stochastic)
            sel = obs["select"]
            if (sel.get("type"), sel.get("context")) != (0, 0):
                continue  # mid-effect select: the fork legitimately varies there
            v = json.loads(visualize_data())
            seat = obs["current"]["yourIndex"]
            me, opp = v[-1]["current"]["players"][seat], v[-1]["current"]["players"][1 - seat]
            given = list(reversed([c["id"] for c in me["deck"]]))
            o = api.to_observation_class(obs)

            def run():
                st = api.search_begin(o, given, [c["id"] for c in me["prize"]],
                                      [c["id"] for c in opp["deck"]], [c["id"] for c in opp["prize"]],
                                      [c["id"] for c in opp["hand"]], [], manual_coin=True)
                drawn = []
                for _ in range(30):
                    ob = st.observation
                    if ob.current and ob.current.result != -1:
                        break
                    if ob.select is None:
                        break
                    drawn += [l.cardId for l in ob.logs
                              if l.type == api.LogType.DRAW and l.playerIndex == seat and l.cardId]
                    end_i = next((i for i, op in enumerate(ob.select.option)
                                  if op.type == api.OptionType.END), None)
                    st = api.search_step(st.searchId, [end_i if end_i is not None else 0])
                api.search_end()
                return drawn

            d1, d2 = run(), run()
            assert d1 == d2, "fork must be deterministic across identical calls"
            if len(d1) >= 4:
                assert d1 != given[: len(d1)], "fork reshuffles (given order not preserved)"
            return
        finally:
            battle_finish()
    pytest.fail("no plain-MAIN post-drive state reached in 20 chaos games — the pin measured "
                "NOTHING. Measured 25/25 alignment on 2026-07-27, so this is a harness regression, "
                "not bad luck. A skip here would have retired the pin silently.")
