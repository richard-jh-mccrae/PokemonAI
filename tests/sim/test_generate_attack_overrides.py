"""The override GENERATOR (ADR-0032 D1: the audit's measurements populate the shipped table).
Pure derivation rules over measurement records -> `attack_overrides.json` entries; conservative by
construction — only engine-agreed, exactly-fitting facts are emitted, everything else stays on the
gap ledger for the formula tier / hand review.

Requirements: REQ-AUDIT-0014 (coin-fork pairs on the vanilla panel -> measured damageMin/damageMax),
REQ-AUDIT-0015 (a printed-0 attack dealing one CONSTANT across >=2 modifier scenarios -> a fixed
`damage` override; any cross-scenario disagreement rejects), REQ-AUDIT-0016 (sweep points fitting
dealt = base + k x var EXACTLY (integer residuals 0, k>0) -> scaleVar/scalePerUnit; noisy fits
reject), REQ-AUDIT-0017 (never emit a field the parser already got right — overrides are deltas).
"""
import pytest

from common.scouting.provider import AttackStat
from sim.generate_attack_overrides import derive_overrides


def _m(aid, scenario, dealt, *, printed=0, coin=None, sweep=None, energies=1, hand=6, error=None):
    r = {"attackId": aid, "attackerCardId": 1, "scenario": scenario, "printed": printed,
         "dealtActive": dealt, "coin": coin, "sweep": sweep, "attackerEnergies": energies,
         "myHandSize": hand, "koed": False}
    if error:
        r["error"] = error
    return r


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
