"""Discard SELECTION at a forced cost-discard (the b7e483a wasted_resource blunders).

Pitch the dead weight — a redundant tutor (its win-condition already in hand) and a setup-only opener
you can no longer play — while protecting the ACE SPEC and keeping the reliable engine Supporters over
filler / a situational hand-disruption card.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

DISCARD = 8
MEGA, STARYU, CINDERACE, SALVATORE, HILDA, LILLIES, HARLEQUIN, WALLYS, CAPE, WATER = (
    1031, 1030, 666, 1189, 1225, 1227, 1223, 1229, 1159, 3)


def _setup(hand_ids):
    stats = DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True),
        CINDERACE: CardStat(CINDERACE, name="Cinderace", hp=160, cardType=0),
        SALVATORE: CardStat(SALVATORE, name="Salvatore", cardType=3),
        HILDA: CardStat(HILDA, name="Hilda", cardType=3),
        LILLIES: CardStat(LILLIES, name="Lillie's", cardType=3),
        HARLEQUIN: CardStat(HARLEQUIN, name="Harlequin", cardType=3),
        WALLYS: CardStat(WALLYS, name="Wally's", cardType=3),
        CAPE: CardStat(CAPE, name="Hero's Cape", aceSpec=True, hpBonus=100, cardType=2),
        WATER: CardStat(WATER, name="Water", energyType=2),
    })
    funcs = CardFunctions({SALVATORE: ["search", "rush_evolve"], HILDA: ["search"],
                           LILLIES: ["draw", "shuffle_hand"], WALLYS: ["heal", "clutch_heal"],
                           HARLEQUIN: ["draw", "hand_disruption", "shuffle_hand"], CINDERACE: ["opener"]})
    strat = Strategy(roles={MEGA: ["win_condition", "primary_attacker"], SALVATORE: ["tutor"],
                            HILDA: ["tutor"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    hand = [{"id": cid} for cid in hand_ids]
    opts = [{"type": 3, "area": 2, "index": i} for i in range(len(hand_ids))]
    obs = {"current": {"players": [{"active": [None], "bench": [], "hand": hand},
                                   {"active": [None], "bench": []}], "yourIndex": 0, "turn": 4},
           "select": {"context": DISCARD, "minCount": 2, "maxCount": 2, "option": opts}}
    return pilot, obs


@pytest.mark.req("REQ-GEN-0023")
def test_discards_the_redundant_tutor_and_protects_the_ace_spec_and_engine():
    # Mega in hand -> Salvatore's job is DONE (job-done gate, was `discard-the-redundant-tutor`);
    # the spare Water cycles free. Keep the ACE SPEC + clutch heal + wincon (their worth floors).
    pilot, obs = _setup([MEGA, CAPE, WALLYS, WATER, SALVATORE])           # idx: 0..4
    dec = pilot.explain(obs)
    assert dec.options[4].score == 0                                      # Salvatore: job done, free
    assert dec.options[1].score < 0                                       # Hero's Cape: ACE-SPEC floor
    assert set(pilot.decide(obs)) == {4, 3}                               # Salvatore + Water, not Cape/Wally's


@pytest.mark.req("REQ-GEN-0023")
def test_discards_the_dead_opener_and_the_disruption_card_over_the_engine():
    # Post-opening: Cinderace dead in hand (job-done gate); Harlequin claims no worth (the draw band
    # excludes hand_disruption). Keep Lillie's + Hilda (draw band / tutor floor).
    pilot, obs = _setup([LILLIES, HILDA, HARLEQUIN, CINDERACE])           # idx: 0..3
    dec = pilot.explain(obs)
    assert dec.options[3].score == 0 and dec.options[2].score == 0        # dead opener + disruptor: free
    assert dec.options[0].score < 0 and dec.options[1].score < 0          # the engine: floored
    assert set(pilot.decide(obs)) == {3, 2}                               # Cinderace + Harlequin


IGNITION = 17


def _powered_setup(hand_ids, *, active_energy):
    """f36 shape: my Mega Starmie ACTIVE at ``active_energy`` (3 = Nebula's cost — fully powered),
    a forced Discard-2 over ``hand_ids``."""
    pilot, obs = _setup(hand_ids)
    pilot.stats._stats[MEGA] = CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True,
                                        maxDamage=210, maxDamageCost=3, minAttackCost=1,
                                        attacks=(10, 11))
    pilot.stats._stats[IGNITION] = CardStat(IGNITION, name="Ignition Energy", hp=0, energyType=0)
    pilot.functions = CardFunctions({**{k: list(v) for k, v in pilot.functions._table.items()},
                                     IGNITION: ["discard_eot"]})
    me = obs["current"]["players"][0]
    me["active"] = [{"id": MEGA, "hp": 330, "maxHp": 330, "energies": [0] * active_energy,
                     "energyCards": [], "tools": [], "preEvolution": []}]
    return pilot, obs


@pytest.mark.req("REQ-GEN-0067")
def test_burst_energy_keep_decays_once_the_active_is_fully_powered():
    """ep83454549 f36: the Active Mega already carries Nebula Beam's cost — Ignition's burst has no
    urgent job, so the keep-key premise is void and the hand-refresh engine Supporter (Lillie's)
    outkeeps it: pitch [dead opener, Ignition], keep Lillie's."""
    pilot, obs = _powered_setup([CINDERACE, LILLIES, IGNITION], active_energy=3)
    dec = pilot.explain(obs)
    assert dec.options[2].score == 0                                      # job done: the burst is free
    assert set(pilot.decide(obs)) == {0, 2}                               # pitch opener + Ignition


@pytest.mark.req("REQ-GEN-0067")
def test_burst_energy_stays_protected_while_the_active_still_needs_it():
    """Control: the same hand with the Active at 1 Energy — the burst is still the route to the big
    attack, so `keep-key-cards-at-discard` protects Ignition and the pitch falls elsewhere."""
    pilot, obs = _powered_setup([CINDERACE, LILLIES, IGNITION], active_energy=1)
    dec = pilot.explain(obs)
    assert dec.options[2].score < 0                                       # still protected (key band)
    assert IGNITION not in {[CINDERACE, LILLIES, IGNITION][i] for i in pilot.decide(obs)}
