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
CINDERACE, FILLER, IGNITION = 666, 999, 17


def _setup(hand_ids, *, minc=2, powered=False):
    """The `test_discard_selection.py` fixture shape: a forced Discard over ``hand_ids``.
    ``powered`` gives my Active its full attack cost (so ``active_fully_powered``)."""
    stats = DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, maxDamageCost=3),
        SALVATORE: CardStat(SALVATORE, name="Salvatore", cardType=3),
        HILDA: CardStat(HILDA, name="Hilda", cardType=3),
        WALLYS: CardStat(WALLYS, name="Wally's", cardType=3),
        CAPE: CardStat(CAPE, name="Hero's Cape", aceSpec=True, hpBonus=100, cardType=2),
        WATER: CardStat(WATER, name="Water", energyType=2, cardType=5),   # 5 = BASIC_ENERGY
        CINDERACE: CardStat(CINDERACE, name="Cinderace", hp=160, cardType=0),   # a dead opener
        FILLER: CardStat(FILLER, name="Filler", cardType=1),              # a role-less Item spare
        IGNITION: CardStat(IGNITION, name="Ignition Energy", cardType=6, energyType=0),  # a burst
    })
    funcs = CardFunctions({SALVATORE: ["search", "rush_evolve"], HILDA: ["search"],
                           WALLYS: ["heal", "clutch_heal"], CINDERACE: ["opener"],
                           IGNITION: ["discard_eot"]})
    strat = Strategy(roles={MEGA: ["win_condition", "primary_attacker"], SALVATORE: ["tutor"],
                            HILDA: ["tutor"]})
    pilot = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    hand = [{"id": cid} for cid in hand_ids]
    opts = [{"type": 3, "area": 2, "index": i} for i in range(len(hand_ids))]
    active = [{"id": MEGA, "hp": 330, "energies": [0] * 3}] if powered else [None]
    obs = {"current": {"players": [{"active": active, "bench": [], "hand": hand},
                                   {"active": [None], "bench": []}], "yourIndex": 0, "turn": 4},
           "select": {"context": DISCARD, "minCount": minc, "maxCount": minc, "option": opts}}
    return pilot, obs


@pytest.mark.req("REQ-SHADOW-0002")
def test_pitch_term_ranks_dead_weight_ahead_of_a_live_spare_among_zero_keep():
    """Finding 3 (the seam-D grill): keep-cost alone can't RANK a discard — a dreg, a duplicate, and a
    dead card all correctly price keep 0, so `eq_pick` fell to raw hand index. The PITCH-PREFERENCE
    term (the `P(met | pitch) − P(met | keep)` sign the ladder's positive rungs carry) breaks those
    ties by DEADNESS: a spent `opener` (Cinderace, its role expired — `discard-the-dead-opener`) is
    actively best gone, so it out-pitches a merely role-less spare that still prices keep 0. The
    filler sits at index 0 so the OLD index tie-break would wrongly pitch it."""
    pilot, obs = _setup([FILLER, CINDERACE], minc=1)               # both worth 0 -> both keep 0
    s = pilot.explain(obs).discard_shadow
    assert s is not None
    by_cid = {r["cid"]: r for r in s["eq"]}
    assert by_cid[FILLER]["keep"] == 0.0 and by_cid[CINDERACE]["keep"] == 0.0     # keep can't separate
    assert by_cid[CINDERACE].get("dead_opener") is True
    assert by_cid[CINDERACE]["pitch"] > by_cid[FILLER]["pitch"]     # deadness discriminates
    assert s["eq_pick"] == [1]                                      # pitch the dead opener, not idx-0 filler


@pytest.mark.req("REQ-SHADOW-0003")
def test_shadow_spent_burst_is_fodder_when_the_active_is_fully_powered():
    """Ladder-win case `83454549-36`: a `discard_eot` burst (Ignition) is precious UNTIL the Active is
    fully powered — then it is SPENT and self-discards at end of turn anyway, so it is dead weight the
    human pitches. Discard-context (at a refresh it is a future attach — this is NOT a general worth
    gate): the shadow zeros its keep and flags `spent_burst` as a pitch signal only when the Active
    already carries its attack cost. FILLER at index 0 so the old ranking would mis-pitch it."""
    unpowered, obs_u = _setup([FILLER, IGNITION], minc=1, powered=False)
    ru = {r["cid"]: r for r in unpowered.explain(obs_u).discard_shadow["eq"]}
    assert ru[IGNITION]["keep"] == 30.0 and not ru[IGNITION].get("spent_burst")   # protected
    powered, obs_p = _setup([FILLER, IGNITION], minc=1, powered=True)
    s = powered.explain(obs_p).discard_shadow
    rp = {r["cid"]: r for r in s["eq"]}
    assert rp[IGNITION]["keep"] == 0.0 and rp[IGNITION]["spent_burst"] is True     # spent -> fodder
    assert rp[IGNITION]["pitch"] > rp[FILLER]["pitch"]
    assert s["eq_pick"] == [1]                                                     # pitch the spent burst


@pytest.mark.req("REQ-SHADOW-0003")
def test_shadow_pitches_the_lower_worth_duplicate_first():
    """Ladder-win case `83967840-54` (sets-not-sums): two hand-DUPLICATE cards both price keep 0 (a
    sibling copies each), but a worth-10 tutor's redundancy is worth preserving over a worth-0 draw
    Supporter's — so among equal (keep, pitch) the LOWER underlying worth sheds first. Salvatore
    (worth 10) sits at index 0 so the old index tie-break would wrongly pitch it over the worth-0
    Lillie's at index 1."""
    # two copies each of Salvatore (tutor, worth 10) and a worth-0 filler -> all keep 0 via the dup
    pilot, obs = _setup([SALVATORE, FILLER, SALVATORE, FILLER], minc=1)
    s = pilot.explain(obs).discard_shadow
    by = {r["i"]: r for r in s["eq"]}
    assert by[0]["cid"] == SALVATORE and by[0]["keep"] == 0.0 and by[0]["worth"] == 10.0
    assert by[1]["cid"] == FILLER and by[1]["keep"] == 0.0 and by[1]["worth"] == 0.0
    assert s["eq_pick"] == [1]                       # the worth-0 filler, not the worth-10 tutor at idx 0


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
    # Salvatore is a rush_evolve wincon-tutor and the Mega (wincon) is in hand -> the NEED-MET gate
    # zeros its keep (worth 10 gated to 0), and it carries the redundant_tutor pitch flag.
    assert by_cid[WATER]["keep"] == 8.0
    assert by_cid[SALVATORE]["worth"] == 10.0 and by_cid[SALVATORE]["keep"] == 0.0
    assert by_cid[SALVATORE].get("redundant_tutor") is True


@pytest.mark.req("REQ-SHADOW-0001")
def test_shadow_disagreement_is_recorded_and_decides_nothing():
    """The RESIDUAL set-naivety (deliberately emitted): a duplicated wincon still prices BOTH copies
    at keep 0 (dup-in-hand — each points at the other as re-access), so a key Mega is still WRONGLY
    pitchable. The worth tie-break softens it (the redundant Salvatore sheds first, then the LOWER-
    worth of the remaining), but with two Megas in a forced discard-2 one still gets pitched — the
    open prerequisite for the true joint-pair (sets-not-sums) fix. The disagreement is RECORDED and
    the ladder's pick stands untouched (the shadow decides nothing)."""
    pilot, obs = _setup([MEGA, MEGA, CAPE, WATER, SALVATORE])
    dec = pilot.explain(obs)
    s = dec.discard_shadow
    assert s is not None and s["agree"] is False
    megas = [r for r in s["eq"] if r["cid"] == MEGA]
    assert len(megas) == 2 and all(r["dup_hand"] and r["keep"] == 0.0 for r in megas)
    assert 0 in s["eq_pick"]                                   # a key Mega is STILL (wrongly) pitched
    assert set(s["eq_pick"]) != set(dec.chosen)               # …and the ladder disagrees, deciding it


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
