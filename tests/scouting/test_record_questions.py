"""The records answer single-card interpretation questions (Stat Provider seam, ADR-0051).

``CardStat``/``AttackStat`` carry the interpretation the retired decider derived from raw
fields at 60+ call sites (the ex/megaEx prize ladder, ``cardType`` comparisons, the
``(minAttackCost or 99)`` affordability idiom). Both provider adapters hand out the same
record classes, so a hand-built record in a test answers exactly like the engine path.
Expected values are pinned from the sites being retired — ports, not redesigns.
"""
import pytest

from common.scouting.provider import AttackStat, CardStat


# --- prize ladder / ex-rule body (retires the `stat.ex or stat.megaEx` idiom) -----------

@pytest.mark.req("REQ-STAT-0001")
def test_prize_value_ladder_mega_ex_plain():
    # The _prize_value ladder (pilot): Mega ex -> 3, ex -> 2, else 1. The engine reports a
    # Mega ex with BOTH flags set (build_cache: ex=True, megaEx=True) — megaEx wins.
    assert CardStat(678, ex=True, megaEx=True).prize_value == 3
    assert CardStat(666, synthetic=True, ex=True).prize_value == 2
    assert CardStat(333).prize_value == 1


@pytest.mark.req("REQ-STAT-0001")
def test_is_ex_body_covers_ex_and_mega_ex():
    # The ex-rule body predicate behind damage-boost/prevention gates and bench liability.
    assert CardStat(666, synthetic=True, ex=True).is_ex_body
    assert CardStat(678, megaEx=True).is_ex_body
    assert not CardStat(333).is_ex_body


# --- card kind (retires the raw `cardType == N` comparisons) ----------------------------

@pytest.mark.req("REQ-STAT-0001")
def test_is_pokemon_reads_hp():
    # Trainers/Energy report hp 0 (the deploy path's is-a-Pokemon fact).
    assert CardStat(333, hp=70).is_pokemon
    assert not CardStat(1086, hp=0).is_pokemon


@pytest.mark.req("REQ-STAT-0001")
def test_card_kind_predicates_key_on_the_cardtype_enum():
    # CardType: ITEM=1, TOOL=2, SUPPORTER=3, BASIC_ENERGY=5, SPECIAL_ENERGY=6 (cg.api).
    assert CardStat(1, synthetic=True, cardType=1).is_item
    assert CardStat(2, synthetic=True, cardType=2).is_tool
    assert CardStat(3, synthetic=True, cardType=3).is_supporter
    assert CardStat(5, cardType=5).is_basic_energy
    assert not CardStat(6, synthetic=True, cardType=6).is_basic_energy
    assert CardStat(5, cardType=5).is_energy
    assert CardStat(6, synthetic=True, cardType=6).is_energy       # Special Energy is still an Energy
    assert not CardStat(3, synthetic=True, cardType=3).is_energy


@pytest.mark.req("REQ-STAT-0001")
def test_unknown_cardtype_fails_open_to_false():
    # cardType None (unknown card) answers False to every kind question — never asserts.
    st = CardStat(999)
    assert not (st.is_item or st.is_tool or st.is_supporter
                or st.is_energy or st.is_basic_energy or st.is_typed_basic_energy)


@pytest.mark.req("REQ-STAT-0001")
def test_is_typed_basic_energy_needs_both_kind_and_type():
    # The attach-type family reads `cardType == 5 and energyType is not None` (pilot _hand_basic_energy).
    assert CardStat(3, cardType=5, energyType=3).is_typed_basic_energy
    assert not CardStat(3, synthetic=True, cardType=5, energyType=None).is_typed_basic_energy
    assert not CardStat(3, synthetic=True, cardType=6, energyType=3).is_typed_basic_energy   # Special never counts


# --- cheapest-attack affordability (retires `(minAttackCost or 99) <= e`) ---------------

@pytest.mark.req("REQ-STAT-0001")
def test_can_pay_cheapest_is_the_fail_closed_affordability_idiom():
    assert CardStat(678, synthetic=True, minAttackCost=2).can_pay_cheapest(2)
    assert not CardStat(678, synthetic=True, minAttackCost=2).can_pay_cheapest(1)
    # Unknown cheapest cost fails CLOSED — a my-side affordability claim is never assumed.
    assert not CardStat(678, synthetic=True, minAttackCost=None).can_pay_cheapest(4)
    # Pinned port quirk: `or 99` maps a 0-cost attack to 99 too — kept byte-faithful to the
    # retired sites (doctrine_gust/doctrine_tool/planner); a free attack reads unaffordable.
    assert not CardStat(678, synthetic=True, minAttackCost=0).can_pay_cheapest(4)


# --- AttackStat determinism (ports the retired decider's interpretation) ----------------

@pytest.mark.req("REQ-STAT-0001")
def test_attack_is_deterministic_requires_fixed_bounds_and_no_scaling():
    assert AttackStat(10, damage=120, damageMax=120).is_deterministic
    # A coin fork lifts the ceiling: not deterministic.
    assert not AttackStat(10, damage=120, damageMax=240).is_deterministic
    # damageMax None does NOT read deterministic (pinned comparison: damageMax == damage).
    assert not AttackStat(10, damage=120).is_deterministic
    # Any scaling term disqualifies, even with matching bounds.
    assert not AttackStat(10, damage=120, damageMax=120, scaleVar="atk_hand",
                          scalePerUnit=20).is_deterministic
    assert not AttackStat(10, damage=120, damageMax=120, hiddenPerUnit=20).is_deterministic
