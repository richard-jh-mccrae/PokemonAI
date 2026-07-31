"""Attack-audit engine smokes (REQ-AUDIT-0010): the harness on the committed native engine,
offline on Windows + Linux like ``test_lethal_engine.py``.

Reproduces the ADR-0032 goldens as MEASUREMENTS: Resistance -30 (rules.md §5, project-verified),
Weakness x2, Nebula Beam 1488 = 210 through Crustle's prevent-ex ability, Jetting Blow 1487 =
0 to the Crustle Active while its 50 bench-snipe still lands, and the coin fork's min/max.

Defenders are pinned by cardId (engine-verified facts in comments) so the assertions are exact;
the only stochastic knob is bench arrival, guarded by a bounded retry.
"""
import pytest

from sim.audit_attacks import CRUSTLE, card_pool, measure_attack, plan_scenarios

OKIDOGI, GOOD_PUNCH = 116, 147          # Fighting, Good Punch printed 70, cost {F}{F}, no rider
HO_OH = 318                             # 130 HP, resists Fighting, no ability
MEGA_AUDINO = 1006                      # 270 HP, WEAK to Fighting, no ability
MEGA_ZYGARDE = 1056                     # 310 HP, weak Grass only, no resistance, no ability
MEGA_STARMIE, NEBULA_BEAM, JETTING_BLOW = 1031, 1488, 1487
EEVEE, QUICK_ATTACK = 43, 40            # printed 20; "flip a coin, if heads 20 more"


def _plan(scenario, defender, **kw):
    plan = {"scenario": scenario, "defender": defender, "extra_energy": 0, "delay_turns": 0,
            "atk_bench": None, "def_bench": None, "sweep": None}
    plan.update(kw)
    return plan


def _measure(attack_id, plan, attempts=3, need_bench=False, want_bench=None, **kw):
    """Bounded retry: bench arrival is the one stochastic knob (drawn spares get benched).

    ``want_bench=(atk, dfn)`` retries until both seats actually reached those counts. The harness
    fires anyway when bench patience runs out — deliberately, so a missed target degrades to a
    duplicate fit point rather than a wrong one — but a test asserting exact counts has to wait
    for the draw that makes them reachable.

    An unbroken streak of ERROR records is a different animal from a missed bench target: it is a
    harness fault, not a shuffle, so it fails here NAMING the underlying message. Falling through
    to ``return recs`` surfaced it downstream as a bare ``'error' not in {...}``, which hid the
    one string that says what actually went wrong.
    """
    errors = []
    for _ in range(attempts):
        recs = measure_attack(attack_id, plan, **kw)
        r = recs[0]
        if "error" in r:
            errors.append(r["error"])
            continue
        if need_bench and not r["defenderBench"]:
            continue
        if want_bench and (r["attackerBench"], r["defenderBench"]) != tuple(want_bench):
            continue
        return recs
    if len(errors) == attempts:
        raise AssertionError(f"attack {attack_id} errored on all {attempts} attempts; "
                             f"last: {errors[-1]}")
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


# --- per-seat bench control (REQ-AUDIT-0018) ---------------------------------------------
# The cap is what turns bench population from an uncontrolled confound into a swept variable.
# Skeledirge's Torcherto is the family the cap exists for: printed 60, "+20 more damage for
# each Benched Pokemon (both yours and your opponent's)" — so a verified cap doubles as a
# verification of the combined-bench model itself.

SKELEDIRGE, TORCHERTO = 203, 274


def _vanilla_plan(owner_card_id, **caps):
    cards = card_pool()
    plan = next(p for p in plan_scenarios(cards[owner_card_id], cards)
                if p["scenario"] == "vanilla")
    return {**plan, **caps}


@pytest.mark.req("REQ-AUDIT-0018")
def test_a_zero_bench_cap_empties_both_seats_and_the_scaler_contributes_nothing():
    # A cap of 0 is the one target always reachable in a single draw, so this case is exact.
    r = _measure(TORCHERTO, _vanilla_plan(SKELEDIRGE, atk_bench=0, def_bench=0),
                 coin_fork=False)[0]
    assert "error" not in r, r
    assert r["printed"] == 60
    assert (r["attackerBench"], r["defenderBench"]) == (0, 0)
    assert r["dealtActive"] == 60                     # no bench => printed only


@pytest.mark.req("REQ-AUDIT-0018")
@pytest.mark.parametrize("atk,dfn", [(1, 2), (2, 1)])
def test_bench_caps_bound_both_seats_and_the_combined_scaler_tracks_the_actual_counts(atk, dfn):
    # Two invariants, both deterministic. The CEILING: neither seat may exceed its cap. The
    # MODEL: dealt damage tracks the counts actually reached. Asserting the exact target instead
    # would be asserting the shuffle — the harness deliberately fires when bench patience runs
    # out, recording what it got, so a missed target is a duplicate fit point and not an error.
    # `want_bench` still steers the retry at the target, so the wait path is exercised in
    # practice; the assertions just don't depend on it landing.
    plan = _vanilla_plan(SKELEDIRGE, atk_bench=atk, def_bench=dfn)
    r = _measure(TORCHERTO, plan, attempts=6, want_bench=(atk, dfn), coin_fork=False)[0]
    assert "error" not in r, r
    assert r["printed"] == 60
    assert r["attackerBench"] <= atk and r["defenderBench"] <= dfn
    assert r["dealtActive"] == 60 + 20 * (r["attackerBench"] + r["defenderBench"])
