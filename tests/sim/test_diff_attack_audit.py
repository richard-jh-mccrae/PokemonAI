"""The audit DIFF (ADR-0032 item 5, join half): measurements vs the damage oracle. Every mismatch
is a discovered gap — the closed form predicted one number, the engine dealt another. Pure core
(`diff_records`) tested lib-free; the CLI wires engine tables.

Requirements: REQ-AUDIT-0011 (each panel measurement diffs against `compute_active_damage`; a
coin-fork record diffs against its own bound, a sweep record against the attacker-side scaling
context — match iff equal), REQ-AUDIT-0012 (error-ledger / live-coin / unknown-attack records are
classified skips, never silent), REQ-AUDIT-0013 (gaps carry enough to act: ids, scenario,
printed/dealt/predicted, a coarse class — `scaler` when printed 0 dealt >0, `over_prediction` when
dealt 0 predicted >0, else `modifier`).
"""
import pytest

from common.cards import CardFunctions
from common.scouting.provider import AttackStat, CardStat
from sim.diff_attack_audit import diff_records

STATS = {
    1031: CardStat(cardId=1031, name="Mega Starmie ex", hp=300, megaEx=True, energyType=3),
    345: CardStat(cardId=345, name="Crustle", hp=140, energyType=1),
    9: CardStat(cardId=9, name="Vanilla", hp=200, energyType=2),
}
ATTACKS = {
    1488: AttackStat(attackId=1488, damage=210, cost=3,
                     ignoresWeakness=True, ignoresResistance=True, ignoresEffects=True),
    1487: AttackStat(attackId=1487, damage=120, cost=1, benchSnipe=50),
    # Powerful Hand: `handSizeDamage` is DERIVED from the scaling term now (Issue #213), so the
    # fixture states the underlying fact rather than the roll-up.
    1072: AttackStat(attackId=1072, damage=0, cost=1, scaleVar="atk_hand", scalePerUnit=20),
    142: AttackStat(attackId=142, damage=40, cost=1, damageMin=0, damageMax=40),
    123: AttackStat(attackId=123, damage=0, cost=3, scaleVar="atk_hand", scalePerUnit=30),
}
FUNCS = CardFunctions({345: ["prevent_ex_damage"]})


def _rec(aid, attacker, scenario, defender, dealt, *, printed=None, coin=None, sweep=None,
         koed=False, error=None):
    r = {"attackId": aid, "attackerCardId": attacker, "scenario": scenario,
         "defenderCardId": defender, "printed": printed if printed is not None
         else getattr(ATTACKS.get(aid), "damage", 0), "dealtActive": dealt,
         "coin": coin, "sweep": sweep, "koed": koed}
    if error:
        r["error"] = error
    return r


@pytest.mark.req("REQ-AUDIT-0011")
def test_matching_measurements_confirm_the_oracle():
    recs = [_rec(1488, 1031, "prevent_ex", 345, 210),   # Nebula pierces — engine agrees
            _rec(1487, 1031, "prevent_ex", 345, 0)]     # Jetting prevented, engine agrees
    out = diff_records(recs, ATTACKS, STATS, FUNCS)
    assert len(out["matched"]) == 2 and not out["gaps"]


@pytest.mark.req("REQ-AUDIT-0011")
def test_a_mismatch_is_a_gap_with_both_numbers():
    recs = [_rec(1488, 1031, "prevent_ex", 345, 0)]     # hypothetical: engine says prevented
    out = diff_records(recs, ATTACKS, STATS, FUNCS)
    (gap,) = out["gaps"]
    assert (gap["predicted"], gap["dealtActive"]) == (210, 0)
    assert gap["class"] == "over_prediction"


@pytest.mark.req("REQ-AUDIT-0013")
def test_scaler_gap_classified_for_formula_tier():
    recs = [_rec(1072, 743, "vanilla", 9, 280)]         # Powerful Hand: printed 0, dealt 20/card
    out = diff_records(recs, ATTACKS, STATS, FUNCS)
    (gap,) = out["gaps"]
    assert gap["class"] == "scaler"


@pytest.mark.req("REQ-AUDIT-0011")
def test_conditional_outcome_within_modeled_bounds_is_a_bounded_match():
    # Best Punch dealt 0 this game (tails). Exact (printed 40) disagrees — but 0 lies within
    # modeled [0, 40]: Lethal reads the floor, Incoming the ceiling. Bounded-correct, no gap.
    out = diff_records([_rec(142, 50, "vanilla", 9, 0)], ATTACKS, STATS, FUNCS)
    assert not out["gaps"] and out["matched"][0].get("bounded") is True
    # dealt OUTSIDE bounds is still a real gap
    bad = diff_records([_rec(142, 50, "vanilla", 9, 90)], ATTACKS, STATS, FUNCS)
    assert len(bad["gaps"]) == 1


@pytest.mark.req("REQ-AUDIT-0011")
def test_coin_fork_records_diff_against_their_bound():
    recs = [_rec(142, 50, "vanilla", 9, 0, coin="min"),     # tails: does nothing — floor agrees
            _rec(142, 50, "vanilla", 9, 40, coin="max")]    # heads: printed — ceiling agrees
    out = diff_records(recs, ATTACKS, STATS, FUNCS)
    assert len(out["matched"]) == 2 and not out["gaps"]
    bad = diff_records([_rec(142, 50, "vanilla", 9, 60, coin="max")], ATTACKS, STATS, FUNCS)
    assert bad["gaps"][0]["coin"] == "max"                  # wrong ceiling is a visible gap


@pytest.mark.req("REQ-AUDIT-0011")
def test_sweep_records_diff_with_attacker_side_context():
    rec = _rec(123, 50, "vanilla", 9, 210, sweep={"var": "hand", "step": 2})
    rec["myHandSize"] = 7                                    # 30 x 7 = 210 — formula agrees
    out = diff_records([rec], ATTACKS, STATS, FUNCS)
    assert len(out["matched"]) == 1 and not out["gaps"]


@pytest.mark.req("REQ-AUDIT-0012")
def test_errors_live_coins_and_unknown_attacks_are_classified_skips():
    live_coin = _rec(1487, 1031, "vanilla", 9, 140)     # live battle flipped a coin (random outcome)
    live_coin["coinLogs"] = 1
    recs = [_rec(5, 9, "vanilla", None, 0, error="no basic-first chain"),
            live_coin,
            _rec(999, 9, "vanilla", 9, 40)]             # unknown attack id -> skip, no crash
    out = diff_records(recs, ATTACKS, STATS, FUNCS)
    reasons = sorted(s["reason"] for s in out["skipped"])
    assert reasons == ["coin_rng_live", "error_ledger", "no_attack_record"]
    assert not out["gaps"]
