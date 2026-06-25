"""System test: the mega_starmie deck (tests/fixtures) driven through a scripted mock match.

Verifies end-to-end that the General Strategy AND the deck's own Strategy hypotheses fire, and
that Function Tags + engine card stats (weakness) are used and have an effect. Lib-free: the
fixture Strategy imports only common.strategy, and observations are built by hand.
"""
import importlib.util
from pathlib import Path

import pytest

from common.cards import CardFunctions
from common.general_strategy import GENERAL_STRATEGY
from common.pilot import KO_SCORE, Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from pilot_helpers import HAND, MAIN, SETUP_ACTIVE, attack_opt, card_opt, make_select, poke, state

# Load the deck's real Strategy from the test fixture (lib-free; imports only common.strategy).
_FIX = Path(__file__).parent / "fixtures" / "agents" / "mega_starmie" / "strategy.py"
_spec = importlib.util.spec_from_file_location("ms_fixture_strategy", _FIX)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
STRATEGY = _mod.STRATEGY

STARYU, MEGA_STARMIE, CINDERACE = 1030, 1031, 666
BUDDY_POFFIN, MEGA_SIGNAL = 1086, 1145
WATER, FIRE, LIGHTNING = 3, 2, 4
JETTING = 11  # placeholder attackId; Jetting Blow prints 120

_STATS = DictCardStatProvider({
    STARYU: CardStat(STARYU, energyType=WATER, weakness=LIGHTNING, hp=70),
    MEGA_STARMIE: CardStat(MEGA_STARMIE, energyType=WATER, weakness=LIGHTNING, megaEx=True, hp=330),
    CINDERACE: CardStat(CINDERACE, energyType=FIRE, weakness=WATER, hp=160),
    BUDDY_POFFIN: CardStat(BUDDY_POFFIN, hp=0),
    MEGA_SIGNAL: CardStat(MEGA_SIGNAL, hp=0),
})
_TAGS = CardFunctions({BUDDY_POFFIN: ["search"], MEGA_SIGNAL: ["search"]})


def _pilot(functions=_TAGS, stats=_STATS):
    return Pilot(STRATEGY, deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=stats, functions=functions, attacks={JETTING: 120})


# --- the scripted match ---------------------------------------------------
def _open_active():   # SETUP: choose the opening Active (Staryu vs Cinderace)
    return make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=SETUP_ACTIVE,
                       current=state(hand=[STARYU, CINDERACE]))


def _play_search():   # SETUP: a tutor/search card (Buddy Poffin) vs a basic (Staryu)
    return make_select([card_opt(HAND, 0), card_opt(HAND, 1)],
                       current=state(hand=[BUDDY_POFFIN, STARYU]))


def _attack():        # RACE: Mega Starmie ex (Water) attacks Cinderace (Fire, Weak to Water)
    return make_select([attack_opt(JETTING)], context=MAIN,
                       current=state(active=poke(MEGA_STARMIE, energy=3),
                                     opp_active=poke(CINDERACE, hp=160)))


def _fired(pilot, obs):
    return {h.id for o in pilot.explain(obs).options for h, _ in o.fired}


@pytest.mark.req("REQ-SYS-0001")
def test_general_and_deck_hypotheses_both_fire_over_a_match():
    p = _pilot()
    fired = set().union(*(_fired(p, o) for o in (_open_active(), _play_search(), _attack())))
    deck = {"open-cinderace", "accel-into-main", "tutor-the-wincon"}
    general = {h.id for h in GENERAL_STRATEGY.hypotheses}
    assert fired & deck, f"no deck hypothesis fired across the match: {fired}"
    assert fired & general, f"no General Strategy hypothesis fired across the match: {fired}"


@pytest.mark.req("REQ-SYS-0002")
def test_a_deck_role_and_a_general_tag_rule_fire_on_the_same_card():
    # Buddy Poffin (opt0): deck Role 'tutor' AND Function Tag 'search' -> both layers fire on one option.
    fired0 = {h.id for h, _ in _pilot().explain(_play_search()).options[0].fired}
    assert "tutor-the-wincon" in fired0    # deck hypothesis (role)
    assert "dig-before-commit" in fired0   # General Strategy hypothesis (tag)


@pytest.mark.req("REQ-SYS-0003")
def test_function_tags_have_an_effect():
    obs = _play_search()
    with_tags = {h.id for h, _ in _pilot().explain(obs).options[0].fired}
    without = {h.id for h, _ in _pilot(functions=None).explain(obs).options[0].fired}
    assert "dig-before-commit" in with_tags     # the tag drives the General Strategy rule
    assert "dig-before-commit" not in without   # remove card_functions -> the rule can't fire
    assert "tutor-the-wincon" in without        # the deck's role-based rule is unaffected


@pytest.mark.req("REQ-SYS-0004")
def test_weakness_has_an_effect_on_the_knockout():
    p = _pilot()
    assert p.explain(_attack()).options[0].score >= KO_SCORE   # 120 x2 = 240 >= 160 -> KO

    # counterfactual: the same attack into a non-weak defender is not a knockout
    nonweak = make_select([attack_opt(JETTING)], context=MAIN,
                          current=state(active=poke(MEGA_STARMIE, energy=3),
                                        opp_active=poke(9999, hp=160)))
    assert p.explain(nonweak).options[0].score < KO_SCORE      # 120 < 160 -> no KO
