"""The unified snipe THREAT RANK (`_target_threat_rank`) + its rules (ADR-0020 follow-up).

Covers what the retired flat priorities (weakest / evolving / strongest-evolving) could not: an
already-evolved ex attacker seen by its PRINTED damage (the descendants-only forward signal scores it
0), a line that CERTAINLY reaches a hand-size attacker (a card-fact Posture read, not a meta guess),
and a benched knockout valued as the prize it is. The b7e483a bad-target blunders.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from pilot_helpers import BENCH, card_opt, make_select, poke, state


def _fired(trace):
    return {h.id for h, _ in trace.fired}


def _pilot(stats, functions=None):
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=functions)


_SNIPER = CardStat(700, name="Sniper", maxDamage=120, attacks=(11,))   # my Active: a 50-snipe rider
_ATTACKS = {11: AttackStat(11, damage=120, benchSnipe=50)}             # its attack record


@pytest.mark.req("REQ-GEN-0028")
def test_already_evolved_ex_outranks_a_low_hp_support_body():
    # Dragapult ex is opponent's main attacker but TERMINAL, so forward_max_damage scores it 0 —
    # rank must read its OWN printed 200 so it's top threat over a 70-HP support benchsitter.
    stats = DictCardStatProvider({
        700: _SNIPER,
        121: CardStat(121, name="Dragapult ex", hp=320, ex=True, maxDamage=200, evolvesFrom="Drakloak"),
        64: CardStat(64, name="Hoothoot", hp=70, maxDamage=20),     # support; lower HP
    }, attacks=_ATTACKS)
    pilot = _pilot(stats)
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=15,  # DAMAGE
                      current=state(active=poke(700), opp_bench=[poke(121, hp=320), poke(64, hp=70)]))
    dragapult, hoothoot = pilot.explain(obs).options
    assert "snipe-the-top-threat" in _fired(dragapult)
    assert "snipe-the-top-threat" not in _fired(hoothoot)
    assert pilot.decide(obs) == [0]                                 # big ex, not the low-HP support


@pytest.mark.req("REQ-GEN-0028")
def test_a_line_that_reaches_a_hand_size_attacker_outranks_a_bigger_raw_damage_line():
    # Kadabra's printed damage is 30 and Alakazam's is 10 — but its line CERTAINLY reaches Alakazam, a
    # hand-size attacker (Powerful Hand). Dunsparce's line reaches a bigger raw-damage body, yet
    # card-fact boost makes latent Alakazam the priority snipe (the ep82753102 f85 blunder).
    stats = DictCardStatProvider({
        700: _SNIPER,
        742: CardStat(742, name="Kadabra", hp=80, maxDamage=30, evolvesFrom="Abra"),
        743: CardStat(743, name="Alakazam", hp=140, maxDamage=10, evolvesFrom="Kadabra"),
        305: CardStat(305, name="Dunsparce", hp=70, maxDamage=20),
        66: CardStat(66, name="Dudunsparce", hp=140, maxDamage=90, evolvesFrom="Dunsparce"),
    }, attacks=_ATTACKS)
    funcs = CardFunctions({743: ["hand_size_attacker"]})
    pilot = _pilot(stats, functions=funcs)
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=15,
                      current=state(active=poke(700), opp_bench=[poke(742, hp=80), poke(305, hp=70)]))
    kadabra, dunsparce = pilot.explain(obs).options
    assert "snipe-the-top-threat" in _fired(kadabra)
    assert "snipe-the-top-threat" not in _fired(dunsparce)
    assert pilot.decide(obs) == [0]                                 # latent hand-size attacker line


@pytest.mark.req("REQ-GEN-0018")
def test_a_benched_knockout_outranks_a_scarier_chip():
    # 50-rider KOs a 50-HP body (a prize). Even a far scarier body that can only be CHIPPED is
    # passed over for the free knockout — snipe-for-the-ko dominates snipe-the-top-threat.
    stats = DictCardStatProvider({
        700: _SNIPER,
        121: CardStat(121, name="Dragapult ex", hp=320, ex=True, maxDamage=200, evolvesFrom="Drakloak"),
        99: CardStat(99, name="Frail", hp=50, maxDamage=10),
    }, attacks=_ATTACKS)
    pilot = _pilot(stats)
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=15,
                      current=state(active=poke(700), opp_bench=[poke(121, hp=320), poke(99, hp=50)]))
    dragapult, frail = pilot.explain(obs).options
    assert "snipe-for-the-ko" in _fired(frail) and "snipe-for-the-ko" not in _fired(dragapult)
    assert pilot.decide(obs) == [1]                                 # take prize, not chip


@pytest.mark.req("REQ-0020")
def test_forward_card_ids_collects_the_whole_descendant_line():
    stats = DictCardStatProvider({
        741: CardStat(741, name="Abra", hp=50, maxDamage=10),
        742: CardStat(742, name="Kadabra", hp=80, maxDamage=30, evolvesFrom="Abra"),
        743: CardStat(743, name="Alakazam", hp=140, maxDamage=10, evolvesFrom="Kadabra"),
    })
    assert stats.forward_card_ids(741) == frozenset({742, 743})     # Abra -> Kadabra -> Alakazam
    assert stats.forward_card_ids(743) == frozenset()               # terminal
