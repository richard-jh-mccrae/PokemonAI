"""The unified snipe THREAT RANK (`_target_threat_rank`) and its rules (ADR-0020 follow-up)."""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from pilot_helpers import BENCH, card_opt, make_select, poke, state


def _pilot(stats, functions=None, scaled_threat_rank=True):
    # Both switches ON to match the shipped PROFILE (constructor defaults are OFF). An unarmed Pilot
    # scores every bench target 0 — ADR-0085 deleted the additive fallback — so orderings go vacuous.
    return Pilot(Strategy(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=functions, scaled_threat_rank=scaled_threat_rank, snipe_relevance=True)


def _rank(pilot, obs, index):
    """Deliberately NOT re-pointed at Snipe Relevance, which is CATEGORICAL (ADR-0085 decision 1) and
    scores 0 for every target here; the rank's live reader is `planner.py:_ko_key_threat_lines`."""
    select = obs["select"]
    pilot._board(obs, select)      # builds `_opp_attack_context`; the scaling term is 0 without it
    return pilot._target_threat_rank(obs, select, select["option"][index], None, 0.0)


_SNIPER = CardStat(700, synthetic=True, name="Sniper", maxDamage=120, attacks=(11,))
_ATTACKS = {11: AttackStat(11, damage=120, benchSnipe=50)}


@pytest.mark.req("REQ-GEN-0028")
def test_already_evolved_ex_outranks_a_low_hp_support_body():
    # Dragapult ex is TERMINAL, so the descendants-only `forward_max_damage` scores it 0 — the rank
    # must read its OWN printed 200.
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
    # Alakazam's Powerful Hand has PRINTED damage 0; its threat is entirely the Damage Formula's
    # scaling term. `functions=None` proves the rank needs no per-card tag to see it (Issue #213).
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
    # A COMBINED-BENCH scaler ("+20 for each Benched Pokemon, both yours and your opponent's") has no
    # Function Tag and a printed 20; the rank sees it through the Damage Formula, not a special case.
    attacks = dict(_ATTACKS)
    attacks[371] = AttackStat(371, damage=20, cost=2, scaleVar="both_bench", scalePerUnit=20)
    stats = DictCardStatProvider({
        700: _SNIPER,
        272: CardStat(272, synthetic=True, name="Lillie's Clefairy ex", hp=190, ex=True, maxDamage=20,
                      minAttackCost=2, attacks=(371,)),
        64: CardStat(64, synthetic=True, name='Hoothoot', hp=70, maxDamage=90),   # bigger PRINTED damage
    }, attacks=attacks)
    pilot = _pilot(stats)
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=15,
                      current=state(active=poke(700), bench=[poke(64), poke(64), poke(64)],
                                    opp_bench=[poke(272, hp=190), poke(64, hp=70)]))
    assert _rank(pilot, obs, 0) > _rank(pilot, obs, 1)             # 20 + 20*5 benched = 120 > 90


@pytest.mark.req("REQ-GEN-0018")
def test_a_benched_knockout_outranks_a_scarier_chip():
    # The 50-rider KOs the 50-HP body outright; the scarier body can only be CHIPPED.
    stats = DictCardStatProvider({
        700: _SNIPER,
        121: CardStat(121, name="Dragapult ex", hp=320, ex=True, maxDamage=200, evolvesFrom="Drakloak"),
        99: CardStat(99, synthetic=True, name="Frail", hp=50, maxDamage=10),
    }, attacks=_ATTACKS)
    pilot = _pilot(stats)
    obs = make_select([card_opt(BENCH, 0, player=1), card_opt(BENCH, 1, player=1)], context=15,
                      current=state(active=poke(700), opp_bench=[poke(121, hp=320), poke(99, hp=50)]))
    # The free prize is the STRUCTURAL `_snipe_ko_dominator` (KO_SCORE-class), so no sum of
    # positional weights can out-vote it the way it could the retired `snipe-for-the-ko` rung.
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
        743: CardStat(743, synthetic=True, name='Alakazam', hp=140, maxDamage=10, evolvesFrom="Kadabra"),
    })
    assert stats.forward_card_ids(741) == frozenset({742, 743})     # Abra -> Kadabra -> Alakazam
    assert stats.forward_card_ids(743) == frozenset()               # terminal


@pytest.mark.req("REQ-GEN-0028")
def test_the_kill_switch_off_restores_the_printed_only_read():
    # OFF is the printed-`maxDamage` read, so the scaler's hidden threat is invisible and the bigger
    # PRINTED body wins. Asserted in BOTH directions so the switch cannot quietly become a no-op.
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
    # The damage context is per-decision, so the pair must be read AFTER a decision has built it —
    # with no context the scaling term is 0 by design.
    assert on._threat_damage_pair(742, stats.get(742)) == (30.0, 140.0)   # line reaches 20x7
    assert off._threat_damage_pair(742, stats.get(742)) == (30.0, 0.0)    # printed forward index
