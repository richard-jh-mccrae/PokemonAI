"""Held-card risk — fetch-early vs fetch-late (hypergeometric-fetch-closure §Round 8 §5;
built 2026-07-19, its `seam-held-card-risk.md` plan doc retired — git history).

Fetching a key card the turn BEFORE it can be played buys nothing this turn (the fetch succeeds
identically next turn — a whole-deck search cares only that the target remains in deck) while it
pays the discard cost a turn early and holds the fetched key across the opponent's turn, exposed to
their symmetric refreshes (Judge / Harlequin). Two rungs price the two legs of the one closed form:

* ``dont-fetch-before-the-deadline`` — the fetch-EARLY leg: a fetch whose every needed target is
  provably unplayable this turn (`Context.fetch_target_deferred`, the rules.md §4 evolution-timing
  read) stands down when it pays a discard cost now (always wasted) or the matched Read prices a
  live hand-strip (`Board.opp_hand_strip_odds`, fail-open 0.0).
* ``dont-shuffle-away-the-deferred-fetch`` — the fetch-LATE leg's re-access risk realised by OUR OWN
  refresh: while a held fetch's needed grab is deferred to next turn, a self-shuffle destroys the
  deferred plan exactly like the opponent's Judge would — hold the hand, attack instead.

Acceptance: the recorded mega_starmie blunder ep85163634 f17 (Ultra Ball one turn early; the human:
"we dont need the Starmie now … there is no cost to just wait a turn") — the corpus target promoted
to a PIN by this build.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

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
        BASE: CardStat(BASE, name="Basep", hp=70),
        WINC: CardStat(WINC, name="Wincmon", megaEx=True, hp=330, evolvesFrom="Basep"),
        VAN1: CardStat(VAN1, name="Van1", hp=90),
        VAN2: CardStat(VAN2, name="Van2", hp=90),
        REFRESH: CardStat(REFRESH, name="Refresh", cardType=3),
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
def test_fetch_one_turn_early_stands_down_and_the_attack_fires_f17():
    """ms 85163634 f17: turn 2 (our first turn), both Staryu benched THIS turn, Mega Starmie ex the
    only needed Ultra Ball target — unplayable until next turn (rules.md §4). The human: attack with
    Turbo Flare; fetch next turn. The fetch-early rung drives Ultra Ball ≤ 0 and the deferred-fetch
    hold drives the Lillie's/Harlequin refreshes ≤ 0, so the +266.9 attack is chosen."""
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

@pytest.mark.req("REQ-GEN-0059")
def test_costly_fetch_stands_down_when_the_target_cannot_land_this_turn():
    """A cost-discard tutor whose only needed target is an evolution with no eligible base (the base
    was benched THIS turn) nets ≤ 0 — the fetch succeeds identically next turn, the cost is paid now."""
    pilot = _pilot_for(cost_discard=True)
    bench = [dict(poke(BASE), appearThisTurn=True), poke(VAN1)]
    obs = _menu([FETCH, VAN1, VAN2], bench=bench)
    t = pilot.explain(obs).options[0]
    assert "dont-fetch-before-the-deadline" in _fired(t)
    assert t.score <= 0


@pytest.mark.req("REQ-GEN-0059")
def test_costly_fetch_plays_when_the_target_can_evolve_this_turn():
    """Same board with the base ELIGIBLE (in play since last turn): the fetched evolution lands this
    turn, so the deadline rung is silent and the endorsed fetch stays positive."""
    pilot = _pilot_for(cost_discard=True)
    bench = [poke(BASE), poke(VAN1)]                       # appearThisTurn absent -> eligible
    obs = _menu([FETCH, VAN1, VAN2], bench=bench)
    t = pilot.explain(obs).options[0]
    assert "dont-fetch-before-the-deadline" not in _fired(t)
    assert t.score > 0


@pytest.mark.req("REQ-GEN-0059")
def test_deadline_holds_on_my_first_turn_even_with_an_eligible_base():
    """Neither player may evolve on their own first turn (rulebook L128): an eligible-looking base
    (benched at setup) still cannot receive the evolution on turn 2 for the second player."""
    pilot = _pilot_for(cost_discard=True)
    bench = [poke(BASE), poke(VAN1)]
    obs = _menu([FETCH, VAN1, VAN2], bench=bench, turn=2, first_player=1)
    obs["current"]["yourIndex"] = 0                        # first_player=1, we are 0 -> our first turn is 2
    t = pilot.explain(obs).options[0]
    assert "dont-fetch-before-the-deadline" in _fired(t)
    assert t.score <= 0


@pytest.mark.req("REQ-GEN-0059")
def test_free_fetch_holds_only_under_a_live_strip_read():
    """The exposure leg (Round 8 §5): a FREE tutor before the deadline is silent with no Read
    (fail-open — no rep → no exposure claimed → no veto) and stands down once the matched Read
    prices a live symmetric refresh (`opp_hand_strip_odds` from `copies_left_odds`)."""
    bench = [dict(poke(BASE), appearThisTurn=True), poke(VAN1)]
    # no Read: the free early fetch is NOT vetoed (waiting costs nothing, but neither does fetching)
    pilot = _pilot_for(cost_discard=False)
    obs = _menu([FREEFETCH, VAN1, VAN2], bench=bench)
    assert "dont-fetch-before-the-deadline" not in _fired(pilot.explain(obs).options[0])
    # a confident Read holding Judge copies: the held key would sit exposed -> fetch-late wins
    pilot = _pilot_for(cost_discard=False, hand_disruption_judge=True)
    om = OpponentModel()
    om.copies_left_odds = lambda card_id=None: ({JUDGE: 0.9} if card_id is None else 0.9)
    pilot.opponent = om
    t = pilot.explain(obs).options[0]
    assert "dont-fetch-before-the-deadline" in _fired(t)
    assert t.score <= 0


@pytest.mark.req("REQ-GEN-0059")
def test_deadline_rung_leaves_the_starved_and_developed_board_to_its_own_rung():
    """The currency-zone rule (replace, not stack): on the starved-and-developed board that
    `dont-costly-tutor-when-starved-and-developed` (−30) already prices, the deadline rung stays
    silent — one rung per jurisdiction, never both."""
    pilot = _pilot_for(cost_discard=True)
    bench = [dict(poke(BASE), appearThisTurn=True), poke(VAN1), poke(VAN2)]
    obs = _menu([FETCH, VAN1, VAN2], bench=bench, active=poke(900, energy=0))
    fired = _fired(pilot.explain(obs).options[0])
    assert "dont-costly-tutor-when-starved-and-developed" in fired
    assert "dont-fetch-before-the-deadline" not in fired


# ── fetch-LATE leg: dont-shuffle-away-the-deferred-fetch ─────────────────────────────────────────

@pytest.mark.req("REQ-GEN-0060")
def test_refresh_stands_down_while_a_held_fetch_is_deferred():
    """Holding a live tutor whose needed grab is deferred to next turn, a self-refresh (Lillie's)
    would shuffle the plan's vehicle away — the very strip the deferral is guarding against. The
    hold cancels the speculative draw credit; the refresh nets ≤ 0."""
    pilot = _pilot_for(cost_discard=True)
    bench = [dict(poke(BASE), appearThisTurn=True), poke(VAN1)]
    obs = _menu([REFRESH, FETCH, VAN1, VAN2], bench=bench)
    t = pilot.explain(obs).options[0]
    assert "dont-shuffle-away-the-deferred-fetch" in _fired(t)
    assert t.score <= 0


@pytest.mark.req("REQ-GEN-0060")
def test_refresh_cycles_freely_once_the_held_fetch_can_land_its_target():
    """Same hand with the base ELIGIBLE: the fetch is playable this turn (no deferral), so the
    refresh hold is silent — a healthy board still cycles."""
    pilot = _pilot_for(cost_discard=True)
    bench = [poke(BASE), poke(VAN1)]
    obs = _menu([REFRESH, FETCH, VAN1, VAN2], bench=bench)
    assert "dont-shuffle-away-the-deferred-fetch" not in _fired(pilot.explain(obs).options[0])
