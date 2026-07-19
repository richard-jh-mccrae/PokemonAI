"""The DISCARD keep-cost SHADOW (shadow-equations ruling, 2026-07-19 — the first equation shipped
under it): at a real forced-discard pick the card-worth oracle's answer is computed and EMITTED
beside the decision (`Decision.discard_shadow` → the sparse `@T` key → the blunder-shell dropdown),
deciding NOTHING — the tuned `_DISCARD` ladder stays the decider. Disagreement rows are the
telemetry gold the discard convergence (seam D) swaps on.
"""
import sys
from pathlib import Path

import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

REPO = Path(__file__).resolve().parents[2]
DISCARD = 8
MEGA, SALVATORE, HILDA, WALLYS, CAPE, WATER = 1031, 1189, 1225, 1229, 1159, 3


def _setup(hand_ids):
    """The `test_discard_selection.py` fixture shape: a forced Discard-2 over ``hand_ids``."""
    stats = DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True),
        SALVATORE: CardStat(SALVATORE, name="Salvatore", cardType=3),
        HILDA: CardStat(HILDA, name="Hilda", cardType=3),
        WALLYS: CardStat(WALLYS, name="Wally's", cardType=3),
        CAPE: CardStat(CAPE, name="Hero's Cape", aceSpec=True, hpBonus=100, cardType=2),
        WATER: CardStat(WATER, name="Water", energyType=2, cardType=5),   # 5 = BASIC_ENERGY
    })
    funcs = CardFunctions({SALVATORE: ["search", "rush_evolve"], HILDA: ["search"],
                           WALLYS: ["heal", "clutch_heal"]})
    strat = Strategy(roles={MEGA: ["win_condition", "primary_attacker"], SALVATORE: ["tutor"],
                            HILDA: ["tutor"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    hand = [{"id": cid} for cid in hand_ids]
    opts = [{"type": 3, "area": 2, "index": i} for i in range(len(hand_ids))]
    obs = {"current": {"players": [{"active": [None], "bench": [], "hand": hand},
                                   {"active": [None], "bench": []}], "yourIndex": 0, "turn": 4},
           "select": {"context": DISCARD, "minCount": 2, "maxCount": 2, "option": opts}}
    return pilot, obs


@pytest.mark.req("REQ-SHADOW-0001")
def test_shadow_emits_the_full_working_and_the_agreement_bit():
    """Worth-ranked hand: the ladder pitches the redundant Salvatore + the Water; the equation ranks
    the same two cheapest (tutor 10 with the wincon leg intact, energy 8 — both below the ACE SPEC
    25, the clutch heal 20, the wincon 30). Full per-card working + agree=True on the record."""
    pilot, obs = _setup([MEGA, CAPE, WALLYS, WATER, SALVATORE])
    dec = pilot.explain(obs)
    s = dec.discard_shadow
    assert s is not None and s["agree"] is True
    assert s["picks"] == sorted(dec.chosen) and set(s["eq_pick"]) == set(dec.chosen)
    by_cid = {r["cid"]: r for r in s["eq"]}
    assert by_cid[MEGA]["worth"] == 30.0 and by_cid[MEGA]["keep"] == 30.0
    assert by_cid[CAPE]["keep"] == 25.0                        # ACE SPEC fallback
    assert by_cid[WALLYS]["keep"] == 20.0                      # clutch_heal TAG_TIER
    assert by_cid[WATER]["keep"] == 8.0 and by_cid[SALVATORE]["keep"] == 10.0


@pytest.mark.req("REQ-SHADOW-0001")
def test_shadow_disagreement_is_recorded_and_decides_nothing():
    """A duplicated wincon: the v1 per-card equation prices BOTH copies at 0 (dup-in-hand — the
    sets-not-sums naivety, deliberately emitted) so it would pitch the two Megas; the ladder keeps
    key cards and pitches the fodder. The disagreement is RECORDED — and the ladder's pick stands
    untouched (the shadow decides nothing)."""
    pilot, obs = _setup([MEGA, MEGA, CAPE, WATER, SALVATORE])
    dec = pilot.explain(obs)
    s = dec.discard_shadow
    assert s is not None and s["agree"] is False
    megas = [r for r in s["eq"] if r["cid"] == MEGA]
    assert len(megas) == 2 and all(r["dup_hand"] and r["keep"] == 0.0 for r in megas)
    assert set(s["eq_pick"]) == {0, 1}                         # the equation's naive pick: both Megas
    assert set(dec.chosen) != {0, 1}                           # the ladder still decided


@pytest.mark.req("REQ-SHADOW-0001")
def test_shadow_fuel_bit_zeroes_a_discard_source_accel_energy():
    """The zone sign's v1 (spec Round 7, Kyogre/Aura-Jab class): a Basic Energy a discard-source
    accel attack wants IN the discard is FUEL — its keep floors at 0 with the bit emitted. Verified
    on the shipped mega_lucario (Aura Jab: recoverN, recoverSource=discard)."""
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    ml = _build_pilot("mega_lucario")[0]
    fuels = ml._discard_fuel_types()
    assert fuels                                               # Aura Jab's discard-source accel
    e = next(c for c in set(ml.deck)
             if getattr(ml.stats.get(c), "is_basic_energy", False)
             and (None in fuels or getattr(ml.stats.get(c), "energyType", None) in fuels))
    hand = [{"id": e}, {"id": e}, {"id": 1121}]
    opts = [{"type": 3, "area": 2, "index": i} for i in range(3)]
    obs = {"current": {"players": [{"active": [None], "bench": [], "hand": hand},
                                   {"active": [None], "bench": []}], "yourIndex": 0, "turn": 4},
           "select": {"context": DISCARD, "minCount": 1, "maxCount": 1, "option": opts}}
    s = ml.explain(obs).discard_shadow
    assert s is not None
    row = next(r for r in s["eq"] if r["cid"] == e)
    assert row["fuel"] is True and row["keep"] == 0.0


@pytest.mark.req("REQ-SHADOW-0001")
def test_shadow_rides_telemetry_and_respects_the_midsim_guard():
    """The gamble-trace pattern (ADR-0019): the shadow rides the sparse `discard_shadow` key of the
    `@T` record; a non-discard decision carries no key; mid-sim (`self._planning`) records nothing."""
    from common.telemetry import to_record
    pilot, obs = _setup([MEGA, CAPE, WALLYS, WATER, SALVATORE])
    dec = pilot.explain(obs)
    rec = to_record(dec)
    assert rec["discard_shadow"]["agree"] is True
    sel, board = obs["select"], pilot._board(obs)
    pilot._planning = True
    try:
        assert pilot._discard_shadow(obs, sel, board, sel["option"], list(dec.chosen)) is None
    finally:
        pilot._planning = False
    # no real choice (forced full pick) -> nothing to shadow
    forced = {**sel, "minCount": 5, "maxCount": 5}
    assert pilot._discard_shadow(obs, forced, board, sel["option"], [0, 1, 2, 3, 4]) is None
