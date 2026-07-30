"""The override GENERATOR (ADR-0032 D1: the audit's measurements populate the shipped table).
Pure derivation rules over measurement records -> `attack_overrides.json` entries; conservative by
construction — only engine-agreed, exactly-fitting facts are emitted, everything else stays on the
gap ledger for the formula tier / hand review.

Requirements: REQ-AUDIT-0014 (coin-fork pairs on the vanilla panel -> measured damageMin/damageMax),
REQ-AUDIT-0015 (a printed-0 attack dealing one CONSTANT across >=2 modifier scenarios -> a fixed
`damage` override; any cross-scenario disagreement rejects), REQ-AUDIT-0016 (sweep points fitting
dealt = base + k x var EXACTLY (integer residuals 0, k>0) -> scaleVar/scalePerUnit; noisy fits
reject), REQ-AUDIT-0017 (never emit a field the parser already got right — overrides are deltas),
REQ-AUDIT-0019 (the bench family is named by JOINING two single-variable sweeps; one axis alone,
a drifted pinned seat, a noisy axis, or unequal positive slopes all emit nothing).
"""
import pytest

from common.scouting.provider import AttackStat
from sim.generate_attack_overrides import derive_overrides


def _m(aid, scenario, dealt, *, printed=0, coin=None, sweep=None, energies=1, hand=6,
       atk_bench=1, def_bench=1, error=None):
    r = {"attackId": aid, "attackerCardId": 1, "scenario": scenario, "printed": printed,
         "dealtActive": dealt, "coin": coin, "sweep": sweep, "attackerEnergies": energies,
         "myHandSize": hand, "attackerBench": atk_bench, "defenderBench": def_bench,
         "koed": False}
    if error:
        r["error"] = error
    return r


def _bench_axis(aid, printed, per_atk, per_def, *, base=None, pinned=1):
    """Both bench sweeps for one attack: dealt = base + per_atk*atkBench + per_def*defBench.

    Mirrors what the harness produces — each axis moves one seat 0/1/2 and pins the other at
    ``pinned`` — so a test states the TRUTH about a card and lets the join rule name it.
    """
    base = printed if base is None else base
    recs = [_m(aid, "vanilla", base + per_atk * pinned + per_def * pinned, printed=printed,
               atk_bench=pinned, def_bench=pinned)]                      # the panel point
    for n in (0, 1, 2):
        recs.append(_m(aid, "vanilla", base + per_atk * n + per_def * pinned, printed=printed,
                       atk_bench=n, def_bench=pinned,
                       sweep={"var": "atk_bench", "step": n}))
        recs.append(_m(aid, "vanilla", base + per_atk * pinned + per_def * n, printed=printed,
                       atk_bench=pinned, def_bench=n,
                       sweep={"var": "def_bench", "step": n}))
    return recs


@pytest.mark.req("REQ-AUDIT-0014")
def test_coin_fork_pair_yields_measured_bounds():
    recs = [_m(142, "vanilla", 40, printed=40),
            _m(142, "vanilla", 0, printed=40, coin="min"),
            _m(142, "vanilla", 40, printed=40, coin="max")]
    parsed = {142: AttackStat(attackId=142, damage=40)}          # parser saw no bounds
    out = derive_overrides(recs, parsed)
    assert out[142] == {"damageMin": 0, "damageMax": 40}


@pytest.mark.req("REQ-AUDIT-0017")
def test_no_override_when_parser_already_agrees():
    recs = [_m(142, "vanilla", 0, printed=40, coin="min"),
            _m(142, "vanilla", 40, printed=40, coin="max")]
    parsed = {142: AttackStat(attackId=142, damage=40, damageMin=0, damageMax=40)}
    assert 142 not in derive_overrides(recs, parsed)


@pytest.mark.req("REQ-AUDIT-0015")
def test_constant_effect_damage_needs_cross_scenario_agreement():
    parsed = {850: AttackStat(attackId=850, damage=0, ignoresWeakness=True, ignoresResistance=True)}
    # Telekinesis: printed 0, dealt 70 on vanilla AND weak -> fixed damage 70
    recs = [_m(850, "vanilla", 70), _m(850, "weak", 70)]
    assert derive_overrides(recs, parsed)[850] == {"damage": 70}
    # disagreement (weak doubled: plain scaling/W-affected, not constant) -> reject
    recs2 = [_m(850, "vanilla", 70), _m(850, "weak", 140)]
    assert 850 not in derive_overrides(recs2, parsed)
    # single scenario isn't agreement -> reject
    assert 850 not in derive_overrides([_m(850, "vanilla", 70)], parsed)


@pytest.mark.req("REQ-AUDIT-0016")
def test_sweep_points_fit_an_exact_linear_scaler():
    parsed = {1072: AttackStat(attackId=1072, damage=0)}         # pretend parser missed it
    recs = [_m(1072, "vanilla", 120, hand=6),
            _m(1072, "vanilla", 160, hand=8, sweep={"var": "hand", "step": 2}),
            _m(1072, "vanilla", 200, hand=10, sweep={"var": "hand", "step": 4})]
    assert derive_overrides(recs, parsed)[1072] == {"scaleVar": "atk_hand", "scalePerUnit": 20}
    # noisy point breaks the exact fit -> reject (stays on ledger)
    recs[2]["dealtActive"] = 210
    assert 1072 not in derive_overrides(recs, parsed)


@pytest.mark.req("REQ-AUDIT-0016")
def test_energy_sweeps_fit_the_attacker_energy_var():
    parsed = {201: AttackStat(attackId=201, damage=0)}
    recs = [_m(201, "vanilla", 120, energies=3),
            _m(201, "vanilla", 160, energies=4, sweep={"var": "energy", "step": 1}),
            _m(201, "vanilla", 200, energies=5, sweep={"var": "energy", "step": 2})]
    assert derive_overrides(recs, parsed)[201] == {"scaleVar": "atk_active_energy",
                                                   "scalePerUnit": 40}


@pytest.mark.req("REQ-AUDIT-0014")
def test_copy_attacks_are_excluded_from_generation():
    # copy-attack's measured damage is the COPIED attack's - defender-dependent, non-transferable
    recs = [_m(528, "vanilla", 0, coin="min"), _m(528, "vanilla", 200, coin="max")]
    parsed = {528: AttackStat(attackId=528, damage=0)}
    texts = {528: "Flip a coin. If heads, choose 1 of your opponent's Active Pokémon's attacks "
                  "and use it as this attack."}
    assert derive_overrides(recs, parsed, texts=texts) == {}
    assert 528 in derive_overrides(recs, parsed)          # without texts guard can't fire


@pytest.mark.req("REQ-AUDIT-0014")
def test_errors_and_foreign_scenarios_never_contribute():
    recs = [_m(5, "vanilla", 0, error="undrivable"),
            _m(142, "weak", 0, printed=40, coin="min"),          # non-vanilla fork: W/R baked in
            _m(142, "weak", 80, printed=40, coin="max")]
    assert derive_overrides(recs, {142: AttackStat(attackId=142, damage=40)}) == {}


# --- the bench family: two sweeps, joined (REQ-AUDIT-0019) --------------------------------
# A SINGLE bench sweep cannot name the family: sweeping the attacker's bench yields the same
# slope for `atk_bench` and `both_bench`, and `def_bench` yields none. So the variable is named
# by JOINING two single-variable sweeps. Getting this wrong is not hypothetical — 274 Torcherto
# (a combined-bench scaler) shipped an exact-looking `atk_hand`/5 fit because bench was the one
# variable the harness neither controlled nor recorded.


@pytest.mark.req("REQ-AUDIT-0019")
def test_equal_slopes_on_both_axes_name_the_combined_bench_family():
    # 274 Torcherto / 371 Full Moon Rondo: "+20 for each Benched Pokemon (both yours and your
    # opponent's)" — engine-confirmed 60 + 20*(atk+def).
    parsed = {274: AttackStat(attackId=274, damage=60)}
    recs = _bench_axis(274, 60, per_atk=20, per_def=20)
    assert derive_overrides(recs, parsed)[274] == {"scaleVar": "both_bench", "scalePerUnit": 20}


@pytest.mark.req("REQ-AUDIT-0019")
def test_a_flat_defender_axis_names_the_attacker_bench_family():
    parsed = {900: AttackStat(attackId=900, damage=30)}
    recs = _bench_axis(900, 30, per_atk=30, per_def=0)
    assert derive_overrides(recs, parsed)[900] == {"scaleVar": "atk_bench", "scalePerUnit": 30}


@pytest.mark.req("REQ-AUDIT-0019")
def test_a_flat_attacker_axis_names_the_defender_bench_family():
    parsed = {901: AttackStat(attackId=901, damage=30)}
    recs = _bench_axis(901, 30, per_atk=0, per_def=10)
    assert derive_overrides(recs, parsed)[901] == {"scaleVar": "def_bench", "scalePerUnit": 10}


@pytest.mark.req("REQ-AUDIT-0019")
def test_unequal_positive_slopes_emit_nothing_and_stay_on_the_ledger():
    # Not a family the closed vocabulary can express — never guess which side to name.
    parsed = {902: AttackStat(attackId=902, damage=30)}
    recs = _bench_axis(902, 30, per_atk=20, per_def=10)
    assert 902 not in derive_overrides(recs, parsed)


@pytest.mark.req("REQ-AUDIT-0019")
def test_one_measured_axis_is_never_enough_to_name_a_bench_family():
    # THE failure this rule exists to prevent: with only the attacker axis measured, a combined
    # scaler is indistinguishable from an attacker-bench scaler. Emit nothing, not a guess.
    parsed = {903: AttackStat(attackId=903, damage=60)}
    recs = [r for r in _bench_axis(903, 60, per_atk=20, per_def=20)
            if (r.get("sweep") or {}).get("var") != "def_bench"]
    assert 903 not in derive_overrides(recs, parsed)


@pytest.mark.req("REQ-AUDIT-0019")
def test_an_axis_whose_pinned_seat_drifted_is_rejected_as_uncontrolled():
    # Patience can run out and a seat can miss its target. The pinned seat must be provably
    # constant across the axis, read off the records — not trusted from the plan.
    parsed = {904: AttackStat(attackId=904, damage=60)}
    recs = _bench_axis(904, 60, per_atk=20, per_def=20)
    drifted = next(r for r in recs if (r.get("sweep") or {}).get("var") == "atk_bench")
    drifted["defenderBench"] = 3                       # the pinned seat moved
    assert 904 not in derive_overrides(recs, parsed)


@pytest.mark.req("REQ-AUDIT-0019")
def test_a_noisy_bench_axis_rejects_like_any_other_sweep():
    parsed = {905: AttackStat(attackId=905, damage=60)}
    recs = _bench_axis(905, 60, per_atk=20, per_def=20)
    next(r for r in recs if (r.get("sweep") or {}).get("var") == "atk_bench"
         and r["attackerBench"] == 2)["dealtActive"] += 5
    assert 905 not in derive_overrides(recs, parsed)


@pytest.mark.req("REQ-AUDIT-0017")
def test_a_bench_family_the_parser_already_named_is_not_re_stated():
    parsed = {274: AttackStat(attackId=274, damage=60, scaleVar="both_bench", scalePerUnit=20)}
    assert 274 not in derive_overrides(_bench_axis(274, 60, per_atk=20, per_def=20), parsed)


@pytest.mark.req("REQ-AUDIT-0019")
def test_a_pinned_bench_keeps_a_bench_scaler_from_fitting_the_hand_axis():
    # The root cause of the 274 defect: with bench pinned across the hand sweep, a bench scaler
    # is CONSTANT there, so the hand fit is flat and never wins.
    parsed = {906: AttackStat(attackId=906, damage=60)}
    recs = _bench_axis(906, 60, per_atk=20, per_def=20)
    recs += [_m(906, "vanilla", 100, printed=60, hand=8, sweep={"var": "hand", "step": 2}),
             _m(906, "vanilla", 100, printed=60, hand=10, sweep={"var": "hand", "step": 4})]
    assert derive_overrides(recs, parsed)[906] == {"scaleVar": "both_bench", "scalePerUnit": 20}
