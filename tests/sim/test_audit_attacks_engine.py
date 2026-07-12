"""Attack-audit engine smokes (REQ-AUDIT-0010): the harness on the committed native engine,
offline on Windows + Linux like ``test_lethal_engine.py``.

Reproduces the ADR-0032 goldens as MEASUREMENTS: Resistance -30 (rules.md §5, project-verified),
Weakness x2, Nebula Beam 1488 = 210 through Crustle's prevent-ex ability, Jetting Blow 1487 =
0 to the Crustle Active while its 50 bench-snipe still lands, and the coin fork's min/max.

Defenders are pinned by cardId (engine-verified facts in comments) so the assertions are exact;
the only stochastic knob is bench arrival, guarded by a bounded retry.
"""
import pytest

from sim.audit_attacks import CRUSTLE, measure_attack

OKIDOGI, GOOD_PUNCH = 116, 147          # Fighting, Good Punch printed 70, cost {F}{F}, no rider
HO_OH = 318                             # 130 HP, resists Fighting, no ability
MEGA_AUDINO = 1006                      # 270 HP, WEAK to Fighting, no ability
MEGA_ZYGARDE = 1056                     # 310 HP, weak Grass only, no resistance, no ability
MEGA_STARMIE, NEBULA_BEAM, JETTING_BLOW = 1031, 1488, 1487
EEVEE, QUICK_ATTACK = 43, 40            # printed 20; "flip a coin, if heads 20 more"


def _plan(scenario, defender):
    return {"scenario": scenario, "defender": defender, "extra_energy": 0, "delay_turns": 0,
            "sweep": None}


def _measure(attack_id, plan, attempts=3, need_bench=False, **kw):
    """Bounded retry: bench arrival is the one stochastic knob (drawn spares get benched)."""
    for _ in range(attempts):
        recs = measure_attack(attack_id, plan, **kw)
        if "error" not in recs[0] and (not need_bench or recs[0]["defenderBench"] > 0):
            return recs
    return recs


@pytest.mark.req("REQ-AUDIT-0010")
def test_resistance_matchup_measures_the_known_minus_30():
    recs = _measure(GOOD_PUNCH, _plan("resist", HO_OH), coin_fork=False)
    r = recs[0]
    assert "error" not in r, r
    assert r["printed"] == 70
    assert r["dealtActive"] == 40                     # 70 - 30: uniform set-wide Resistance
    assert r["koed"] is False


@pytest.mark.req("REQ-AUDIT-0010")
def test_weakness_matchup_measures_double_damage():
    recs = _measure(GOOD_PUNCH, _plan("weak", MEGA_AUDINO), coin_fork=False)
    r = recs[0]
    assert "error" not in r, r
    assert r["dealtActive"] == 140                    # 70 x2; 270 HP body survives (no censoring)
    assert r["koed"] is False


@pytest.mark.req("REQ-AUDIT-0010")
def test_nebula_beam_ignores_crustles_prevent_ex_ability():
    recs = _measure(NEBULA_BEAM, _plan("prevent_ex", CRUSTLE), coin_fork=False)
    r = recs[0]
    assert "error" not in r, r
    assert r["attackerCardId"] == MEGA_STARMIE
    assert r["dealtActive"] == 210                    # "isn't affected ... by any effects" lands


@pytest.mark.req("REQ-AUDIT-0010")
def test_jetting_blow_is_zeroed_by_crustle_but_the_bench_snipe_lands():
    recs = _measure(JETTING_BLOW, _plan("prevent_ex", CRUSTLE), need_bench=True, coin_fork=False)
    r = recs[0]
    assert "error" not in r, r
    assert r["dealtActive"] == 0                      # Mysterious Rock Inn blanks the ex hit
    assert r["defenderBench"] > 0                     # a target existed (retry-guarded)
    assert r["dealtBench"] == [50]                    # ... and the rider still snipes it


@pytest.mark.req("REQ-AUDIT-0009")
def test_coin_fork_measures_min_and_max_over_both_outcomes():
    recs = _measure(QUICK_ATTACK, _plan("vanilla", MEGA_ZYGARDE))
    assert "error" not in recs[0], recs[0]
    by_coin = {r["coin"]: r for r in recs}
    assert by_coin[None]["attackerCardId"] == EEVEE
    assert by_coin["min"]["dealtActive"] == 20        # tails: printed only
    assert by_coin["max"]["dealtActive"] == 40        # heads: +20
