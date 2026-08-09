"""Held-card risk — fetch-early vs fetch-late, the two legs of one closed form.

Fetching a key card the turn BEFORE it can be played buys nothing (a whole-deck search only needs
the target to stay in deck), pays the discard cost a turn early, and holds the key across the
opponent's turn exposed to their symmetric refreshes:

* ``dont-fetch-before-the-deadline`` — the fetch-EARLY leg.
* ``dont-shuffle-away-the-deferred-fetch`` — the same re-access risk realised by OUR OWN refresh.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from poc_t4_flips import marks

from common.cards import CardFunctions
from common.opponent_model import OpponentModel
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Line, Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from pilot_helpers import MAIN, PLAY, fetch_effects, make_select, opt, poke, state

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "corrections"

FETCH = 2001          # a synthetic cost-discard Pokémon tutor (the Ultra Ball shape)
FREEFETCH = 2002      # the same tutor without the discard cost (the Mega Signal shape)
REFRESH = 1227        # Lillie's Determination — a real shuffle_hand refresh (verified draw facts)
JUDGE = 1213          # the opponent-side symmetric refresh the Read prices
BASE, WINC = 1030, 1031
VAN1, VAN2 = 901, 902


def _fired(option_trace):
    return {h.id for h, _ in option_trace.fired}


def _pilot_for(*, cost_discard: bool = True, hand_disruption_judge: bool = False):
    """A Pilot whose deck runs the BASE→WINC line plus a Pokémon tutor; the WINC is the declared
    win-condition so its grab value is positive (`fetch-the-wincon`)."""
    fetch_tags = (["cost_discard", "search", "tutor_pokemon"] if cost_discard
                  else ["search", "tutor_pokemon"])
    fid = FETCH if cost_discard else FREEFETCH
    funcs_map = {fid: fetch_tags, REFRESH: ["draw", "shuffle_hand"]}
    if hand_disruption_judge:
        funcs_map[JUDGE] = ["draw", "hand_disruption", "shuffle_hand"]
    stats = DictCardStatProvider({
        BASE: CardStat(BASE, synthetic=True, name="Basep", hp=70),
        WINC: CardStat(WINC, synthetic=True, name="Wincmon", megaEx=True, hp=330, evolvesFrom="Basep"),
        VAN1: CardStat(VAN1, synthetic=True, name="Van1", hp=90),
        VAN2: CardStat(VAN2, synthetic=True, name="Van2", hp=90),
        REFRESH: CardStat(REFRESH, synthetic=True, name="Refresh", cardType=3),
        fid: CardStat(fid, name="Fetch", cardType=1),
    })
    strat = Strategy(lines=[Line(path=[BASE, WINC], payoff=WINC, role="win_condition")])
    deck = [BASE] * 3 + [WINC] * 2 + [fid] * 2 + [REFRESH] * 2 + [1] * 51
    return Pilot(strat, deck=deck, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions(funcs_map), effects=fetch_effects(funcs_map))


def _menu(hand, *, bench, active=None, turn=3, first_player=None):
    """An open MAIN menu: one PLAY per hand card, plus End. `bench` entries are board poke dicts."""
    options = [opt(PLAY, index=i) for i in range(len(hand))] + [opt(type=14)]
    cur = state(active=active or poke(900, energy=2), bench=bench, hand=hand, turn=turn)
    if first_player is not None:
        cur["firstPlayer"] = first_player
    return make_select(options, context=MAIN, current=cur)


# ── the recorded blunder: ep85163634 f17 (the corpus target this seam promotes) ──────────────────

def _real_pilot(agent: str):
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_pilot(agent)[0]


@pytest.mark.req("REQ-CORPUS-0001")
@pytest.mark.xfail(strict=True, reason=marks("ms_fetch_one_turn_early_judge_exposure_f17")[0].kwargs["reason"])
def test_fetch_one_turn_early_stands_down_and_the_attack_fires_f17():
    """Both Staryu benched THIS turn, so the only needed Ultra Ball target is unplayable until next
    turn (rules.md §4): fetch-early drives the Ball <= 0 and the deferred hold drives the refreshes down."""
    fx = json.loads((FIXTURES / "ms_fetch_one_turn_early_judge_exposure_f17.json")
                    .read_text(encoding="utf-8"))
    d = _real_pilot("mega_starmie").explain(fx["obs"])
    assert d.chosen == fx["correct"], f"expected {fx['correct_label']!r}"
    ball = d.options[2]                      # [2] Play Ultra Ball — the tagged blunder
    assert ball.score <= 0, f"the early fetch must price ≤ 0 (tier 4), got {ball.score:+.1f}"
    assert "dont-fetch-before-the-deadline" in _fired(ball)
    lillies = d.options[0]                   # [0] Play Lillie's Determination — the next-best trap
    assert lillies.score <= 0, f"the self-refresh must price ≤ 0, got {lillies.score:+.1f}"
    assert "dont-shuffle-away-the-deferred-fetch" in _fired(lillies)


# ── fetch-EARLY leg: dont-fetch-before-the-deadline ───────────────────────────────────────────────











# ── fetch-LATE leg: dont-shuffle-away-the-deferred-fetch ─────────────────────────────────────────



@pytest.mark.req("REQ-GEN-0060")
def test_refresh_cycles_freely_once_the_held_fetch_can_land_its_target():
    """Same hand with the base ELIGIBLE: the fetch is playable this turn (no deferral), so the
    refresh hold is silent — a healthy board still cycles."""
    pilot = _pilot_for(cost_discard=True)
    bench = [poke(BASE), poke(VAN1)]
    obs = _menu([REFRESH, FETCH, VAN1, VAN2], bench=bench)
    assert "dont-shuffle-away-the-deferred-fetch" not in _fired(pilot.explain(obs).options[0])
