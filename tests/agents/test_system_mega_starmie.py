"""System test: the mega_starmie deck (tests/fixtures) driven through a scripted mock match.

Verifies end-to-end that the deck's DECLARATIONS (Roles / Lines / params — the deck carries zero
Hypotheses since the 2026-07-02 fold) drive the role-keyed General Strategy rules, that the
tag-keyed rules fire alongside them, and that Function Tags + engine card stats (weakness) are
used and have an effect. Lib-free: the fixture Strategy imports only common.strategy, and
observations are built by hand.
"""
import importlib.util
from pathlib import Path

import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import KO_SCORE, Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from pilot_helpers import (
    ATTACH, HAND, MAIN, MULLIGAN, NO, PLAY, SETUP_ACTIVE, YES,
    attack_opt, card_opt, make_select, opt, poke, state,
)

# Load deck's real Strategy from test fixture (lib-free; imports only common.strategy).
_FIX = Path(__file__).parents[1] / "fixtures" / "agents" / "mega_starmie" / "strategy.py"
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
}, attacks={JETTING: AttackStat(JETTING, damage=120)})
_TAGS = CardFunctions({BUDDY_POFFIN: ["search"], MEGA_SIGNAL: ["search"], CINDERACE: ["opener"]})


def _pilot(functions=_TAGS, stats=_STATS):
    return Pilot(STRATEGY, deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=stats, functions=functions)


# --- the scripted match ---------------------------------------------------
def _open_active():   # SETUP: choose opening Active (Staryu vs Cinderace)
    return make_select([card_opt(HAND, 0), card_opt(HAND, 1)], context=SETUP_ACTIVE,
                       current=state(hand=[STARYU, CINDERACE]))


def _play_search():   # SETUP: PLAY a tutor/search card (Buddy Poffin) vs basic (Staryu)
    return make_select([opt(PLAY, area=HAND, index=0), opt(PLAY, area=HAND, index=1)],
                       current=state(hand=[BUDDY_POFFIN, STARYU]))


def _attack():        # RACE: Mega Starmie ex (Water) attacks Cinderace (Fire, Weak to Water)
    return make_select([attack_opt(JETTING)], context=MAIN,
                       current=state(active=poke(MEGA_STARMIE, energy=3),
                                     opp_active=poke(CINDERACE, hp=160)))


def _fired(pilot, obs):
    return {h.id for o in pilot.explain(obs).options for h, _ in o.fired}


@pytest.mark.req("REQ-SYS-0001")
def test_deck_declarations_drive_role_keyed_general_rules_over_a_match():
    # Deck ships ZERO Hypotheses; its Roles/params opt in to role-keyed General Strategy.
    p = _pilot()
    fired = set().union(*(_fired(p, o) for o in (_open_active(), _play_search(), _attack())))
    role_keyed = {"open-the-accelerator", "advance-the-accel-pieces",
                  "play-a-tutor-for-the-unfound-wincon"}       # fire only via this deck's Roles
    general = {h.id for h in GENERAL_STRATEGY.hypotheses}
    assert fired & role_keyed, f"no role-keyed rule fired off the declarations: {fired}"
    assert fired & (general - role_keyed), f"no other General Strategy rule fired: {fired}"


@pytest.mark.req("REQ-SYS-0002")
def test_a_role_keyed_and_a_tag_keyed_general_rule_fire_on_the_same_card():
    # Buddy Poffin (opt0): deck Role 'tutor' AND Function Tag 'search' -> both signals fire on one option.
    fired0 = {h.id for h, _ in _pilot().explain(_play_search()).options[0].fired}
    assert "play-a-tutor-for-the-unfound-wincon" in fired0   # role-keyed (deck's declaration)
    assert "dig-before-commit" in fired0                     # tag-keyed (universal Function Tag)


@pytest.mark.req("REQ-SYS-0003")
def test_function_tags_have_an_effect():
    obs = _play_search()
    with_tags = {h.id for h, _ in _pilot().explain(obs).options[0].fired}
    without = {h.id for h, _ in _pilot(functions=None).explain(obs).options[0].fired}
    assert "dig-before-commit" in with_tags     # tag drives the tag-keyed rule
    assert "dig-before-commit" not in without   # remove card_functions -> rule can't fire
    assert "play-a-tutor-for-the-unfound-wincon" in without  # role-keyed rule unaffected


@pytest.mark.req("REQ-SYS-0004")
def test_weakness_has_an_effect_on_the_knockout():
    p = _pilot()
    assert p.explain(_attack()).options[0].score >= KO_SCORE   # 120 x2 = 240 >= 160 -> KO

    # counterfactual: same attack into a non-weak defender is not a knockout
    nonweak = make_select([attack_opt(JETTING)], context=MAIN,
                          current=state(active=poke(MEGA_STARMIE, energy=3),
                                        opp_active=poke(9999, hp=160)))
    assert p.explain(nonweak).options[0].score < KO_SCORE      # 120 < 160 -> no KO


@pytest.mark.req("REQ-SYS-0005")
def test_agent_keeps_a_startable_cinderace_hand_rather_than_mulliganing():
    # Blunder #2: hand has Cinderace but no Basic -> engine offers Mulligan [Yes=redraw, No=keep].
    # Cinderace's Explosiveness (opener tag + starter role) makes it keepable: keep, don't redraw.
    p = _pilot()
    mull = make_select([opt(YES), opt(NO)], context=MULLIGAN, current=state(hand=[CINDERACE]))
    assert p.decide(mull) == [1]   # No = keep hand
    assert "keep-a-startable-hand" in {h.id for h, _ in p.explain(mull).options[0].fired}


@pytest.mark.req("REQ-SYS-0006")
def test_agent_attaches_energy_during_setup_rather_than_passing():
    # Blunder #1: in SETUP, attaching Energy must beat doing nothing (power-up-attacker), so
    # agent powers up its attacker instead of only ever playing the special accel energy.
    p = _pilot()
    obs = make_select([opt(ATTACH), opt(PLAY)], current=state(active=poke(STARYU, energy=0)))
    assert p.decide(obs) == [0]    # attach the Energy
    assert "power-up-attacker" in {h.id for h, _ in p.explain(obs).options[0].fired}
