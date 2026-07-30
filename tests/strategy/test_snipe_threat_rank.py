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


def _pilot(stats, functions=None, scaled_threat_rank=True):
    # Both switches ON to match the shipped PROFILE; the constructor defaults are OFF because each is
    # an incident lever, and a bare Pilot() would silently exercise a retired read.
    # `scaled_threat_rank` is Issue #213's; `snipe_relevance` is ADR-0084's, and since that ADR's
    # deletion pass removed the six DAMAGE target rungs there is no additive path left to fall back
    # on — an unarmed Pilot scores every bench target 0 and the argmax degenerates to option index,
    # which would make every ordering assertion below pass vacuously.
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=functions, scaled_threat_rank=scaled_threat_rank, snipe_relevance=True)


def _rank(pilot, obs, index):
    """One option's THREAT RANK — the instrument these tests are actually about.

    They used to read it off a FIRED hypothesis id (`snipe-the-top-threat`), and ADR-0084 deleted
    that rung with the other five. The rank itself SURVIVES: `planner.py:_ko_key_threat_lines` ranks
    the opponent bench with `_body_threat_rank` for the ADR-0031 `ko_key_threat` Goal-Ladder rung
    (`planner_key_threat`, shipped ON). So the requirement is unchanged and still live — only its
    reader moved from a snipe rung to the Planner.

    These assertions were deliberately NOT re-pointed at Snipe Relevance. The scalar is CATEGORICAL
    (ADR-0084 decision 1) and asks *does this body matter to their plan and my route*, not *how big
    is it*; on these fixtures the opponent bodies carry no Energy, so `their_plan` is 0 for every
    target and the conjunctive product is 0 for all of them. Asserting a magnitude ordering on an
    instrument that deliberately does not price magnitude would be testing the wrong thing — this is
    ADR-0062's wall, which is why the two instruments coexist rather than one subsuming the other.
    """
    select = obs["select"]
    pilot._board(obs, select)      # builds `_opp_attack_context`; the scaling term is 0 without it
    return pilot._target_threat_rank(obs, select, select["option"][index], None, 0.0)


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
    assert _rank(pilot, obs, 0) > _rank(pilot, obs, 1)             # 200-damage ex over low-HP support


@pytest.mark.req("REQ-GEN-0028")
def test_a_line_that_reaches_a_hand_size_attacker_outranks_a_bigger_raw_damage_line():
    # The ep82753102 f85 blunder. Alakazam's Powerful Hand has PRINTED damage 0 — its whole threat
    # lives in the Damage Formula's scaling term (2 counters per card in hand = 20/card), so at a
    # 7-card hand its line is worth 140 and outranks Dunsparce's line at a printed 90.
    #
    # Issue #213 changed the MECHANISM, not the requirement. This used to pass on a flat +500
    # boost keyed off the `hand_size_attacker` Function Tag, and the fixture stated Alakazam's
    # damage as a printed 10 with no scaling attack at all — a card fact that is simply false, and
    # which only went unnoticed because the boost swamped it. The fixture now states the real card,
    # and `functions=None` proves the rank no longer needs a per-card tag to see the threat.
    attacks = dict(_ATTACKS)
    attacks[1072] = AttackStat(1072, damage=0, cost=1, scaleVar="atk_hand", scalePerUnit=20)
    stats = DictCardStatProvider({
        700: _SNIPER,
        742: CardStat(742, name="Kadabra", hp=80, maxDamage=30, evolvesFrom="Abra"),
        743: CardStat(743, name="Alakazam", hp=140, maxDamage=0, minAttackCost=1,
                      evolvesFrom="Kadabra", attacks=(1072,)),
        305: CardStat(305, name="Dunsparce", hp=70, maxDamage=20),
        66: CardStat(66, name="Dudunsparce", hp=140, maxDamage=90, evolvesFrom="Dunsparce"),
    }, attacks=attacks)
    pilot = _pilot(stats)
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=15,
                      current=state(active=poke(700), opp_bench=[poke(742, hp=80), poke(305, hp=70)],
                                    opp_hand_count=7))
    assert _rank(pilot, obs, 0) > _rank(pilot, obs, 1)             # 20x7 latent line > printed 90


@pytest.mark.req("REQ-GEN-0028")
def test_the_rank_generalises_to_a_scaler_no_function_tag_covers():
    # The generalisation the flat boost could never reach: a COMBINED-BENCH attacker (Lillie's
    # Clefairy ex / Skeledirge, "+20 for each Benched Pokemon (both yours and your opponent's)")
    # has no Function Tag and a printed 20. On a populated board it is the real threat, and the
    # rank sees it for the same reason it sees Alakazam — the Damage Formula, not a special case.
    attacks = dict(_ATTACKS)
    attacks[371] = AttackStat(371, damage=20, cost=2, scaleVar="both_bench", scalePerUnit=20)
    stats = DictCardStatProvider({
        700: _SNIPER,
        272: CardStat(272, name="Lillie's Clefairy ex", hp=190, ex=True, maxDamage=20,
                      minAttackCost=2, attacks=(371,)),
        64: CardStat(64, name="Hoothoot", hp=70, maxDamage=90),   # bigger PRINTED damage
    }, attacks=attacks)
    pilot = _pilot(stats)
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=15,
                      current=state(active=poke(700), bench=[poke(64), poke(64), poke(64)],
                                    opp_bench=[poke(272, hp=190), poke(64, hp=70)]))
    assert _rank(pilot, obs, 0) > _rank(pilot, obs, 1)             # 20 + 20*5 benched = 120 > 90


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
    # `snipe-for-the-ko` (+60) is gone with the rest; the free prize is now the STRUCTURAL
    # `_snipe_ko_dominator` (KO_SCORE-class), which is why it cannot be out-summed by positional
    # weights the way the +60 rung could (ms 82754241 f45).
    from common.strategy.context import KO_SCORE
    board = pilot._board(obs, obs["select"])
    ko_ctx = pilot._context(obs, obs["select"], board, obs["select"]["option"][1])
    chip_ctx = pilot._context(obs, obs["select"], board, obs["select"]["option"][0])
    assert pilot._snipe_ko_dominator(ko_ctx) == KO_SCORE
    assert pilot._snipe_ko_dominator(chip_ctx) == 0.0
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


@pytest.mark.req("REQ-GEN-0028")
def test_the_kill_switch_off_restores_the_printed_only_read():
    # The incident lever's contract: OFF is the historical printed-`maxDamage` read, so a scaling
    # attacker's hidden threat is invisible again and the bigger PRINTED body wins. Pinned in both
    # directions so the switch can't quietly become a no-op.
    attacks = dict(_ATTACKS)
    attacks[1072] = AttackStat(1072, damage=0, cost=1, scaleVar="atk_hand", scalePerUnit=20)
    stats = DictCardStatProvider({
        700: _SNIPER,
        742: CardStat(742, name="Kadabra", hp=80, maxDamage=30, evolvesFrom="Abra"),
        743: CardStat(743, name="Alakazam", hp=140, maxDamage=0, minAttackCost=1,
                      evolvesFrom="Kadabra", attacks=(1072,)),
        305: CardStat(305, name="Dunsparce", hp=70, maxDamage=20),
        66: CardStat(66, name="Dudunsparce", hp=140, maxDamage=90, evolvesFrom="Dunsparce"),
    }, attacks=attacks)
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=15,
                      current=state(active=poke(700), opp_bench=[poke(742, hp=80), poke(305, hp=70)],
                                    opp_hand_count=7))
    on = _pilot(stats)
    off = _pilot(stats, scaled_threat_rank=False)
    assert _rank(on, obs, 0) > _rank(on, obs, 1)                          # Kadabra: latent threat seen
    assert _rank(off, obs, 0) < _rank(off, obs, 1)                        # OFF: bigger printed wins
    # ...and the pair each read to get there (the damage context is per-decision, so this must be
    # read AFTER a decision has built it — with no context the scaling term is 0 by design).
    assert on._threat_damage_pair(742, stats.get(742)) == (30.0, 140.0)   # line reaches 20x7
    assert off._threat_damage_pair(742, stats.get(742)) == (30.0, 0.0)    # printed forward index
