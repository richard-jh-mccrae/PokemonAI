"""The override GENERATOR (ADR-0032 D1): pure derivation rules over measurement records ->
`attack_overrides.json` entries.

Conservative by construction — only engine-agreed, EXACTLY-fitting facts are emitted, everything
else stays on the gap ledger. Each test carries its own REQ id; the rules they encode are in
ADR-0083 (bounds are board-scoped, a scaler family is named by JOINING two single-variable sweeps,
a defender-bench slope needs a matched non-{ex} control) and ADR-0108 (evidence rides the
derivation, table and sidecar emit in one pass, a fit may retract what the generator authored but
never what a human ruled).
"""
import json
from pathlib import Path

import pytest

from common.scouting.provider import AttackStat
from sim.generate_attack_overrides import (METHOD_ENGINE_FIT, METHOD_TEXT_VERIFIED,
                                           METHOD_UNAUDITED, Derivation, _evidence,
                                           derive_entries, derive_overrides, main,
                                           measured_attacks, merge_provenance)

REPO = Path(__file__).resolve().parents[2]


def _m(aid, scenario, dealt, *, printed=0, coin=None, sweep=None, energies=1, hand=6,
       atk_bench=1, def_bench=1, error=None, def_energies=None, def_ex=None, atk_stage2=None):
    """The three defender-side fields default to None, a REAL state: it is what a measurement taken
    before Issue #275's axes existed looks like, and several tests turn on that difference."""
    r = {"attackId": aid, "attackerCardId": 1, "scenario": scenario, "printed": printed,
         "dealtActive": dealt, "coin": coin, "sweep": sweep, "attackerEnergies": energies,
         "myHandSize": hand, "attackerBench": atk_bench, "defenderBench": def_bench,
         "defenderEnergies": def_energies, "defenderExInPlay": def_ex,
         "attackerBenchStage2": atk_stage2, "koed": False}
    if error:
        r["error"] = error
    return r


def _energy_axes(aid, printed, per_atk, per_def, *, cost=3):
    """dealt = printed + per_atk*atkEnergy + per_def*defEnergy, laid out as the harness lays it out:
    each axis moves one seat and pins the other, and the un-swept panel point is the shared origin."""
    def dealt(atk_e, def_e):
        return printed + per_atk * atk_e + per_def * def_e

    recs = [_m(aid, "vanilla", dealt(cost, 0), printed=printed, energies=cost, def_energies=0)]
    for n in (1, 2):
        recs.append(_m(aid, "vanilla", dealt(cost + n, 0), printed=printed, energies=cost + n,
                       def_energies=0, sweep={"var": "energy", "step": n}))
        recs.append(_m(aid, "vanilla", dealt(cost, n), printed=printed, energies=cost,
                       def_energies=n, sweep={"var": "def_energy", "step": n}))
    return recs


def _rulebox_axes(aid, printed, per_ex, per_bench, *, control=True):
    """The default panel is {ex}-SATURATED, so `defenderExInPlay` is always ``defenderBench + 1``.
    ``control=False`` is the pre-Issue-#275 set, where the two variables are indistinguishable."""
    def dealt(ex, bench):
        return printed + per_ex * ex + per_bench * bench

    recs = [_m(aid, "vanilla", dealt(2, 1), printed=printed, def_bench=1, def_ex=2)]
    for n in (0, 1, 2):
        recs.append(_m(aid, "vanilla", dealt(n + 1, n), printed=printed, def_bench=n,
                       def_ex=n + 1, sweep={"var": "def_bench", "step": n}))
        recs.append(_m(aid, "vanilla", dealt(2, 1), printed=printed, atk_bench=n, def_bench=1,
                       def_ex=2, sweep={"var": "atk_bench", "step": n}))
        if control:
            recs.append(_m(aid, "vanilla_plain", dealt(0, n), printed=printed, def_bench=n,
                           def_ex=0, sweep={"var": "def_bench", "step": n}))
    return recs


def _bench_axis(aid, printed, per_atk, per_def, *, base=None, pinned=1):
    """dealt = base + per_atk*atkBench + per_def*defBench, laid out as the harness lays it out, so a
    test states the TRUTH about a card and lets the join rule name it."""
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


# --- the bound is BOARD-SCOPED (REQ-AUDIT-0014, ADR-0083 Amendment A) ----------------------
# `--sweep` leaves one `coin="max"` record per BOARD, so a `{coin: ...}` collapse ships one.


def _fork(aid, lo, hi, *, printed=0, sweep=None, energies=1, hand=6, atk_bench=1, def_bench=1):
    """A min/max fork pair measured on ONE board — what `_coin_fork` produces from one position."""
    at = dict(printed=printed, sweep=sweep, energies=energies, hand=hand,
              atk_bench=atk_bench, def_bench=def_bench)
    return [_m(aid, "vanilla", lo, coin="min", **at), _m(aid, "vanilla", hi, coin="max", **at)]


@pytest.mark.req("REQ-AUDIT-0014")
def test_boards_that_disagree_on_the_bound_emit_NOTHING():
    """"Flip a coin for each {D} Pokémon you have in play" is the shape: the bound is a function of
    the BOARD, and the override table has no form that says so."""
    parsed = {920: AttackStat(attackId=920, damage=0)}
    recs = (_fork(920, 0, 60, atk_bench=1, sweep={"var": "atk_bench", "step": 1})
            + _fork(920, 0, 120, atk_bench=2, sweep={"var": "atk_bench", "step": 2}))
    assert 920 not in derive_entries(recs, parsed)


@pytest.mark.req("REQ-AUDIT-0014")
def test_boards_that_AGREE_corroborate_the_bound_rather_than_disqualifying_it():
    """ADR-0083 §3's flat-axis argument applied to the bound: the board was varied and provably does
    not move it."""
    parsed = {921: AttackStat(attackId=921, damage=40)}
    recs = (_fork(921, 0, 40, printed=40, sweep={"var": "atk_bench", "step": 1})
            + _fork(921, 0, 40, printed=40, atk_bench=2, sweep={"var": "atk_bench", "step": 2})
            + _fork(921, 0, 40, printed=40, hand=9, sweep={"var": "hand", "step": 2}))
    assert derive_entries(recs, parsed)[921].fields == {"damageMin": 0, "damageMax": 40}


@pytest.mark.req("REQ-AUDIT-0014")
def test_one_board_measured_twice_with_two_answers_is_not_a_fact():
    """The board key excludes `sweep`/`step`: those are LABELS, and two plans reach the same board by
    design, so keying on the label lets a self-contradiction read as board sensitivity."""
    parsed = {922: AttackStat(attackId=922, damage=0)}
    recs = _fork(922, 0, 70) + _fork(922, 0, 90, sweep={"var": "atk_bench", "step": 1})
    assert 922 not in derive_entries(recs, parsed)


@pytest.mark.req("REQ-AUDIT-0014")
def test_the_same_board_reached_by_two_plans_is_ONE_board():
    """One measurement repeated, not two boards corroborating — and it still emits."""
    parsed = {925: AttackStat(attackId=925, damage=40)}
    recs = (_fork(925, 0, 40, printed=40)
            + _fork(925, 0, 40, printed=40, sweep={"var": "atk_bench", "step": 1}))
    assert derive_entries(recs, parsed)[925].fields == {"damageMin": 0, "damageMax": 40}


@pytest.mark.req("REQ-AUDIT-0014")
def test_a_measured_bound_never_ships_beside_a_FITTED_scaler():
    """The legacy evaluator REPLACES the base with the bound, then adds `scalePerUnit x count` —
    so a bound measured where the scaler contributes adds that contribution twice."""
    parsed = {923: AttackStat(attackId=923, damage=60)}
    recs = _bench_axis(923, 60, per_atk=20, per_def=20)
    # a fork pair on the reference board, agreeing with itself — on its own it would ship
    recs += _fork(923, 0, 100, printed=60)
    fields = derive_entries(recs, parsed)[923].fields
    assert fields == {"scaleVar": "both_bench", "scalePerUnit": 20}
    assert "damageMin" not in fields and "damageMax" not in fields
    # ...and without the scaler to displace it, the very same fork pair DOES ship
    plain = {924: AttackStat(attackId=924, damage=60)}
    assert derive_entries(_fork(924, 0, 100, printed=60), plain)[924].fields == {
        "damageMin": 0, "damageMax": 100}


@pytest.mark.req("REQ-AUDIT-0014")
def test_a_measured_bound_never_ships_beside_a_PARSER_NAMED_scaler_either():
    """The oracle does not care WHO named `scaleVar` — it scales whenever the field is set — so the
    guard has to test the EFFECTIVE scaler, not just the fit."""
    parsed = {926: AttackStat(attackId=926, damage=60, scaleVar="atk_hand", scalePerUnit=20)}
    assert 926 not in derive_entries(_fork(926, 0, 100, printed=60), parsed)


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


@pytest.mark.req("REQ-AUDIT-0015")
def test_a_printed_0_PER_UNIT_attack_is_never_frozen_at_one_boards_constant():
    """The modifier panel is ONE board, so "the same number in every scenario" measures that board's
    count. "for each" is the whole per-unit vocabulary in this pool, verified at source."""
    parsed = {425: AttackStat(attackId=425, damage=0)}
    texts = {425: "This attack does 60 damage for each of your opponent’s Pokémon {ex} in play."}
    agreeing = [_m(425, "vanilla", 120), _m(425, "prevent_ex", 120)]
    assert 425 not in derive_overrides(agreeing, parsed, texts)
    # ...and the guard is TEXT-shaped, not attack-shaped: a printed-0 constant naming no count still
    # ships, so a guard refusing every printed-0 attack cannot pass here.
    plain = {850: AttackStat(attackId=850, damage=0)}
    recs = [_m(850, "vanilla", 70), _m(850, "weak", 70)]
    flat = {850: "This attack does 70 damage."}
    assert derive_overrides(recs, plain, flat)[850] == {"damage": 70}


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
# A SINGLE sweep cannot name it: `atk_bench` and `both_bench` slope the same on one axis.


@pytest.mark.req("REQ-AUDIT-0019")
def test_equal_slopes_on_both_axes_name_the_combined_bench_family():
    # 274 Torcherto: "+20 for each Benched Pokemon (both yours and your opponent's)".
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
    # With only the attacker axis, a combined scaler is indistinguishable from an attacker one.
    parsed = {903: AttackStat(attackId=903, damage=60)}
    recs = [r for r in _bench_axis(903, 60, per_atk=20, per_def=20)
            if (r.get("sweep") or {}).get("var") != "def_bench"]
    assert 903 not in derive_overrides(recs, parsed)


@pytest.mark.req("REQ-AUDIT-0019")
def test_an_axis_whose_pinned_seat_drifted_is_rejected_as_uncontrolled():
    # The pin must be read off the RECORDS, not trusted from the plan — patience can run out.
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
    # With bench pinned across the hand sweep a bench scaler is CONSTANT there, so it cannot win.
    parsed = {906: AttackStat(attackId=906, damage=60)}
    recs = _bench_axis(906, 60, per_atk=20, per_def=20)
    recs += [_m(906, "vanilla", 100, printed=60, hand=8, sweep={"var": "hand", "step": 2}),
             _m(906, "vanilla", 100, printed=60, hand=10, sweep={"var": "hand", "step": 4})]
    assert derive_overrides(recs, parsed)[906] == {"scaleVar": "both_bench", "scalePerUnit": 20}


# --- provenance: the evidence rides the derivation (REQ-PROV-0002) -------------------------
# Deriving a value and recording what established it are ONE operation, not two descriptions.


@pytest.mark.req("REQ-PROV-0002")
def test_the_delta_and_its_evidence_come_out_of_one_derivation():
    parsed = {142: AttackStat(attackId=142, damage=40)}
    recs = [_m(142, "vanilla", 40, printed=40),
            _m(142, "vanilla", 0, printed=40, coin="min"),
            _m(142, "vanilla", 40, printed=40, coin="max")]
    entry = derive_entries(recs, parsed)[142]
    assert entry.fields == {"damageMin": 0, "damageMax": 40}
    # the fork PAIR is the claim, so both halves are the record
    assert sorted(r["coin"] for r in entry.evidence) == ["max", "min"]
    assert sorted(r["dealt"] for r in entry.evidence) == [0, 40]
    # `derive_overrides` is the same derivation with the evidence dropped
    assert derive_overrides(recs, parsed) == {142: entry.fields}


@pytest.mark.req("REQ-PROV-0002")
def test_a_scaler_keeps_the_REJECTED_axes_not_just_the_winning_one():
    """A flat axis is what PROVES a variable was measured and ruled out; keeping only the fitted
    points preserves the conclusion and discards what makes it sound."""
    parsed = {907: AttackStat(attackId=907, damage=60)}
    recs = _bench_axis(907, 60, per_atk=20, per_def=20)
    recs += [_m(907, "vanilla", 100, printed=60, hand=8, sweep={"var": "hand", "step": 2}),
             _m(907, "vanilla", 100, printed=60, energies=3, sweep={"var": "energy", "step": 2})]
    entry = derive_entries(recs, parsed)[907]
    assert entry.fields == {"scaleVar": "both_bench", "scalePerUnit": 20}
    axes = {r["sweep"] for r in entry.evidence}
    assert axes == {None, "atk_bench", "def_bench", "hand", "energy"}
    assert {r["dealt"] for r in entry.evidence if r["sweep"] in ("hand", "energy")} == {100}


@pytest.mark.req("REQ-PROV-0002")
def test_evidence_is_deduplicated_and_ordered_so_a_regenerate_is_stable():
    """Two rules can consult the same record, and a sidecar that differed only in row ORDER would
    read as a real change in every review."""
    parsed = {908: AttackStat(attackId=908, damage=0)}
    recs = [_m(908, "vanilla", 70), _m(908, "weak", 70)] * 3          # same three records, thrice
    entry = derive_entries(recs, parsed)[908]
    assert entry.fields == {"damage": 70}
    assert len(entry.evidence) == 2                                   # deduped by row identity
    assert entry.evidence == derive_entries(list(reversed(recs)), parsed)[908].evidence


@pytest.mark.req("REQ-PROV-0002")
def test_two_measurements_that_CONTRADICT_are_both_kept():
    """Dedup collapses identical rows, never disagreeing ones — keeping whichever came last would
    discard exactly the evidence that says a fact is not what it claims."""
    parsed = {909: AttackStat(attackId=909, damage=0)}
    recs = [_m(909, "vanilla", 70), _m(909, "weak", 70), _m(909, "weak", 140)]
    assert 909 not in derive_entries(recs, parsed)
    # asserted on the DISTILLER, because every rule that could hand it a contradicting pair now
    # rejects upstream — the property must still hold the day one stops rejecting
    same = dict(attackId=911, scenario="vanilla", coin=None, sweep=None, attackerBench=1,
                defenderBench=1, attackerEnergies=1, myHandSize=6)
    rows = _evidence([{**same, "dealtActive": 70}, {**same, "dealtActive": 140},
                      {**same, "dealtActive": 70}])
    assert sorted(r["dealt"] for r in rows) == [70, 140]      # identical collapse, contradicting stay


# --- provenance: the merge rule (REQ-PROV-0007) --------------------------------------------
# The generator may retract what it AUTHORED, never what a human RULED.


def _prov(method, fields, **extra):
    return {"method": method, "fields": fields, "evidence": [], **extra}


@pytest.mark.req("REQ-PROV-0007")
def test_a_fit_the_fresh_measurements_no_longer_support_is_dropped():
    """Exactly the 274 outcome: a stale `atk_hand` fit today's fitter would not emit. The generator
    authored it, so the generator may take it back."""
    existing = {274: _prov(METHOD_ENGINE_FIT, {"scaleVar": "atk_hand", "scalePerUnit": 5})}
    entries, notes, _ = merge_provenance({}, existing, measured={274})
    assert 274 not in entries
    assert any("DROPPED" in n for n in notes)


@pytest.mark.req("REQ-PROV-0007")
def test_an_attack_this_run_never_measured_keeps_its_entry():
    """A per-attack recapture is the intended workflow, so a run that measured one attack must not
    blow away the other 116."""
    existing = {6: _prov(METHOD_UNAUDITED, {"damageMin": 0, "damageMax": 120}),
                274: _prov(METHOD_ENGINE_FIT, {"scaleVar": "atk_hand", "scalePerUnit": 5})}
    entries, _, _ = merge_provenance({}, existing, measured={274})
    assert entries[6] == existing[6] and 274 not in entries


@pytest.mark.req("REQ-PROV-0007")
def test_a_human_ruling_survives_a_measurement_that_establishes_nothing():
    """A fit can conclude "no scaler" from data that could not have shown one, and dropping the entry
    then reverts the attack to computing ZERO damage. Kept, and REPORTED."""
    existing = {425: _prov(METHOD_TEXT_VERIFIED, {"scaleVar": "def_ex_in_play",
                                                  "scalePerUnit": 60}, owner="#275")}
    entries, notes, _ = merge_provenance({}, existing, measured={425})
    assert entries[425] == existing[425]
    assert any("KEPT" in n and "--prune" in n for n in notes)
    # ...unless the operator explicitly opts in
    pruned, notes, _ = merge_provenance({}, existing, measured={425}, prune=True)
    assert pruned == {} and any("PRUNED" in n for n in notes)


@pytest.mark.req("REQ-PROV-0008")
def test_a_human_ruling_survives_a_CONTRADICTING_engine_fit():
    """The sibling above covers `derived == {}` and structurally CANNOT cover `derived != {}` — the
    `KEPT`/`--prune` branch sits behind `if aid in entries: continue` (Issue #355)."""
    ruling = {"scaleVar": "def_ex_in_play", "scalePerUnit": 60}
    fit = {"scaleVar": "def_bench", "scalePerUnit": 60}
    evidence = [{"scenario": "vanilla", "sweep": "def_bench", "step": 2, "coin": None,
                 "atkBench": 1, "defBench": 2, "energies": 1, "hand": 6, "dealt": 180}]
    existing = {425: _prov(METHOD_TEXT_VERIFIED, ruling, owner="#275")}
    derived = {425: Derivation(fit, evidence)}

    entries, notes, contradicted = merge_provenance(derived, existing, measured={425})
    assert entries[425] == existing[425], "the RULING must survive, evidence and owner intact"
    assert contradicted == [425]
    named = [n for n in notes if "CONTRADICTION" in n and "def_ex_in_play" in n and "def_bench" in n]
    assert named, "the note must name BOTH readings, or a reader cannot tell which to go and check"

    # ...unless the operator explicitly opts in, as `--prune` works one branch down.
    ruled, notes, contradicted = merge_provenance(derived, existing, measured={425}, rule=True)
    assert ruled[425]["fields"] == fit and ruled[425]["method"] == METHOD_ENGINE_FIT
    assert ruled[425]["evidence"] == evidence and contradicted == []
    assert any("RULING" in n and "--rule" in n for n in notes), \
        "accepting a ruling-overwrite must still be logged — that is the only durable trace of it"


@pytest.mark.req("REQ-PROV-0008")
def test_a_measurement_that_CONFIRMS_a_ruling_is_not_a_contradiction():
    """Why the guard tests `fields` and not `method`: halting on every fit over a ruling makes the
    debt unpayable without `--rule`, which then becomes the routine flag, i.e. no guard at all."""
    fields = {"scaleVar": "def_ex_in_play", "scalePerUnit": 60}
    evidence = [{"scenario": "vanilla", "sweep": "def_bench", "step": 2, "coin": None,
                 "atkBench": 1, "defBench": 2, "energies": 1, "hand": 6, "dealt": 180}]
    existing = {425: _prov(METHOD_TEXT_VERIFIED, fields, owner="#275")}
    entries, notes, contradicted = merge_provenance({425: Derivation(fields, evidence)},
                                                    existing, measured={425})
    assert contradicted == []
    assert entries[425]["method"] == METHOD_ENGINE_FIT and entries[425]["evidence"] == evidence
    assert any("now measured" in n for n in notes)


@pytest.mark.req("REQ-PROV-0007")
def test_a_recapture_backfills_an_unaudited_entry_into_a_fit():
    """How the unaudited debt is paid down: measure it, no hand edit."""
    fields = {"scaleVar": "both_bench", "scalePerUnit": 20}
    evidence = [{"scenario": "vanilla", "sweep": "atk_bench", "step": 0, "coin": None,
                 "atkBench": 0, "defBench": 1, "energies": 1, "hand": 6, "dealt": 80}]
    existing = {274: _prov(METHOD_UNAUDITED, fields)}
    entries, notes, _ = merge_provenance({274: Derivation(fields, evidence)}, existing,
                                         measured={274})
    assert entries[274]["method"] == METHOD_ENGINE_FIT
    assert entries[274]["evidence"] == evidence
    assert any("now measured" in n for n in notes)


@pytest.mark.req("REQ-PROV-0007")
def test_measured_attacks_ignores_a_run_that_only_ledgered_errors():
    """A failure to measure must not retract the shipped fact."""
    assert measured_attacks([_m(5, "vanilla", 0, error="undrivable")]) == set()
    assert measured_attacks([_m(5, "vanilla", 0, error="undrivable"),
                             _m(6, "vanilla", 40)]) == {6}


# --- provenance: one pass, two files (REQ-PROV-0006) ---------------------------------------


@pytest.mark.req("REQ-PROV-0006")
def test_a_regenerate_with_nothing_measured_reproduces_both_committed_files_byte_for_byte(tmp_path):
    """Three claims at once: the merge never regresses an unmeasured fact, the table is emitted from
    the sidecar's own `fields`, and the writer's format matches what is committed on either OS."""
    committed_table = REPO / "tools" / "meta_tracker" / "attack_overrides.json"
    committed_prov = REPO / "tools" / "meta_tracker" / "attack_overrides.provenance.json"
    empty = tmp_path / "measurements.json"
    empty.write_text(json.dumps({"measurements": []}), encoding="utf-8")
    # everything under tmp_path: a test that CAN write over a committed store eventually does
    out, prov = tmp_path / "table.json", tmp_path / "prov.json"
    prov.write_bytes(committed_prov.read_bytes())
    assert main(["--measurements", str(empty), "--out", str(out), "--provenance", str(prov)]) == 0
    assert out.read_bytes() == committed_table.read_bytes()
    assert prov.read_bytes() == committed_prov.read_bytes()


def _measured_120_and_425() -> list[dict]:
    """A measurement pass RECONSTRUCTED from its recorded rows — driving the engine costs ~20 min and
    establishes nothing the merge needs. Faithfulness is proved by the fits it reproduces."""
    recs = [_m(425, "vanilla", 120), _m(425, "prevent_ex", 0)]
    for n, dealt in ((0, 120), (1, 120), (2, 120)):                  # attacker bench: FLAT
        recs.append(_m(425, "vanilla", dealt, atk_bench=n, sweep={"var": "atk_bench", "step": n}))
    for n, dealt in ((0, 60), (1, 120), (2, 180)):                   # defender bench: 60 per body
        recs.append(_m(425, "vanilla", dealt, def_bench=n, sweep={"var": "def_bench", "step": n}))
    recs += [_m(120, "vanilla", 60, printed=30)]
    for n, dealt in ((1, 60), (2, 90), (3, 120)):
        recs.append(_m(120, "vanilla", dealt, printed=30, energies=n,
                       sweep={"var": "energy", "step": n}))
    return recs


@pytest.mark.req("REQ-PROV-0008")
def test_the_generator_HALTS_on_the_pool_as_it_stands_today(tmp_path):
    """Against the REAL table and sidecar: the derivation must really contradict both rulings, both
    stores must come back byte-identical, and the run must exit NON-ZERO (Issue #355)."""
    from cg.api import all_attack
    from common.scouting.provider import build_attack_stats

    attacks = all_attack()
    records = _measured_120_and_425()
    fits = derive_overrides(records, build_attack_stats(attacks),
                            texts={a.attackId: a.text or "" for a in attacks})
    assert fits == {120: {"scaleVar": "atk_active_energy", "scalePerUnit": 30},
                    425: {"scaleVar": "def_bench", "scalePerUnit": 60}}

    committed_table = REPO / "tools" / "meta_tracker" / "attack_overrides.json"
    committed_prov = REPO / "tools" / "meta_tracker" / "attack_overrides.provenance.json"
    src = tmp_path / "measurements.json"
    src.write_text(json.dumps({"measurements": records}), encoding="utf-8")
    out, prov = tmp_path / "table.json", tmp_path / "prov.json"
    prov.write_bytes(committed_prov.read_bytes())
    rc = main(["--measurements", str(src), "--out", str(out), "--provenance", str(prov)])
    assert rc != 0, "an un-opted-in contradiction must fail a scripted regeneration loudly"
    assert out.read_bytes() == committed_table.read_bytes()
    assert prov.read_bytes() == committed_prov.read_bytes()

    # The files are still WRITTEN: suppressing the write would make `--rule`, the dangerous flag,
    # the only way to get any output at all.
    assert out.exists() and prov.exists()

    # `--rule` is the explicit opt-in a wrong number needs to land in the diff.
    assert main(["--measurements", str(src), "--out", str(out), "--provenance", str(prov),
                 "--rule"]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["425"] == {"scaleVar": "def_bench",
                                                                 "scalePerUnit": 60}


# --- the ENERGY family is joined, never named off one side (REQ-AUDIT-0020, Issue #275) ----
# On a defender with no Energy, the attacker-only and both-sides readings coincide everywhere.


@pytest.mark.req("REQ-AUDIT-0020")
def test_equal_slopes_on_BOTH_actives_name_the_both_variable():
    """Without the defender's axis the same records name `atk_active_energy`, and the two differ by
    30 damage per Energy the OPPONENT has attached — straight into `threat` and `survival`."""
    parsed = {120: AttackStat(attackId=120, damage=30)}
    recs = _energy_axes(120, 30, per_atk=30, per_def=30)
    assert derive_overrides(recs, parsed)[120] == {"scaleVar": "both_active_energy",
                                                  "scalePerUnit": 30}


@pytest.mark.req("REQ-AUDIT-0020")
def test_a_flat_defender_axis_names_the_attacker_variable():
    parsed = {201: AttackStat(attackId=201, damage=0)}
    recs = _energy_axes(201, 0, per_atk=40, per_def=0)
    assert derive_overrides(recs, parsed)[201] == {"scaleVar": "atk_active_energy",
                                                  "scalePerUnit": 40}


@pytest.mark.req("REQ-AUDIT-0020")
def test_a_flat_attacker_axis_names_the_defender_variable():
    """Unreachable before the defender attached anything: the count was always zero, so a scaler on
    the opponent's Energy read as a constant."""
    parsed = {202: AttackStat(attackId=202, damage=20)}
    recs = _energy_axes(202, 20, per_atk=0, per_def=50)
    assert derive_overrides(recs, parsed)[202] == {"scaleVar": "def_active_energy",
                                                  "scalePerUnit": 50}


@pytest.mark.req("REQ-AUDIT-0020")
def test_unequal_positive_energy_slopes_name_nothing():
    """`both_` is a SUM of two EQUAL halves; two per-unit numbers name no expressible family."""
    parsed = {203: AttackStat(attackId=203, damage=0)}
    assert 203 not in derive_overrides(_energy_axes(203, 0, per_atk=30, per_def=10), parsed)


@pytest.mark.req("REQ-AUDIT-0020")
def test_a_noisy_defender_axis_names_nothing_rather_than_falling_back_to_one_side():
    parsed = {204: AttackStat(attackId=204, damage=0)}
    recs = _energy_axes(204, 0, per_atk=30, per_def=30)
    noisy = next(r for r in recs if (r["sweep"] or {}).get("var") == "def_energy")
    noisy["dealtActive"] += 7                       # neither flat nor an exact fit
    assert 204 not in derive_overrides(recs, parsed)


@pytest.mark.req("REQ-AUDIT-0020")
def test_the_one_sided_energy_fit_survives_only_for_measurements_that_predate_the_axis():
    """A record set with no `defenderEnergies` can name only `atk_active_energy`, so refusing it
    would retract facts rather than measure them. Once the field IS recorded, one side is a guess."""
    parsed = {205: AttackStat(attackId=205, damage=0)}
    legacy = [_m(205, "vanilla", 120, energies=3),
              _m(205, "vanilla", 160, energies=4, sweep={"var": "energy", "step": 1}),
              _m(205, "vanilla", 200, energies=5, sweep={"var": "energy", "step": 2})]
    assert derive_overrides(legacy, parsed)[205] == {"scaleVar": "atk_active_energy",
                                                     "scalePerUnit": 40}
    # same three points, now RECORDED as defender-zero, with the defender axis simply not run
    recorded = [dict(r, defenderEnergies=0) for r in legacy]
    assert 205 not in derive_overrides(recorded, parsed)


# --- the RULE-BOX family needs a MATCHED control (REQ-AUDIT-0021, Issue #275) ---------------
# The panel ranks by HP and the top basics are all Mega ex, so the two variables are collinear.


@pytest.mark.req("REQ-AUDIT-0021")
def test_the_matched_control_names_def_ex_in_play_instead_of_the_collinear_bench_count():
    """60 per {ex} reads as 60 per BENCHED BODY to anything that never saw a plain body, and
    `def_bench`/60 then invents 60 damage per ordinary Basic."""
    parsed = {425: AttackStat(attackId=425, damage=0)}
    recs = _rulebox_axes(425, 0, per_ex=60, per_bench=0)
    assert derive_overrides(recs, parsed)[425] == {"scaleVar": "def_ex_in_play",
                                                  "scalePerUnit": 60}


@pytest.mark.req("REQ-AUDIT-0021")
def test_without_the_control_the_same_records_still_name_the_bench_count():
    """The positive control: drop ONLY the paired non-{ex} plans and the fit flips to `def_bench`."""
    parsed = {425: AttackStat(attackId=425, damage=0)}
    recs = _rulebox_axes(425, 0, per_ex=60, per_bench=0, control=False)
    assert derive_overrides(recs, parsed)[425] == {"scaleVar": "def_bench", "scalePerUnit": 60}


@pytest.mark.req("REQ-AUDIT-0021")
def test_a_GENUINE_defender_bench_scaler_still_names_the_bench_with_the_control_present():
    """The control SEPARATES two variables; it does not veto one of them."""
    parsed = {206: AttackStat(attackId=206, damage=20)}
    recs = _rulebox_axes(206, 20, per_ex=0, per_bench=30)
    assert derive_overrides(recs, parsed)[206] == {"scaleVar": "def_bench", "scalePerUnit": 30}


@pytest.mark.req("REQ-AUDIT-0021")
def test_a_control_that_neither_reading_fits_names_nothing():
    """Two readings, neither exact — the gap ledger, not the tidier of the two."""
    parsed = {207: AttackStat(attackId=207, damage=0)}
    recs = _rulebox_axes(207, 0, per_ex=60, per_bench=0)
    plain = next(r for r in recs if r["scenario"] == "vanilla_plain")
    plain["dealtActive"] = 25                       # the control moved, but on no shared slope
    assert 207 not in derive_overrides(recs, parsed)


@pytest.mark.req("REQ-PROV-0002")
def test_the_matched_control_rows_are_kept_as_evidence_for_the_fit_they_justify():
    """Evidence holding only the {ex} axis reads EXACTLY like the row it was written to rule out."""
    parsed = {425: AttackStat(attackId=425, damage=0)}
    entry = derive_entries(_rulebox_axes(425, 0, per_ex=60, per_bench=0), parsed)[425]
    assert entry.fields == {"scaleVar": "def_ex_in_play", "scalePerUnit": 60}
    plain = [r for r in entry.evidence if r["scenario"] == "vanilla_plain"]
    assert {r["defBench"] for r in plain} == {0, 1, 2}
    assert {r["defEx"] for r in plain} == {0}
    assert {r["dealt"] for r in plain} == {0}       # the bench filled and nothing happened


@pytest.mark.req("REQ-PROV-0002")
def test_the_evidence_row_carries_the_defender_state_the_new_axes_control():
    """ADR-0083 §2 wants controls AND records, and with `reports/attack_audit/` gitignored the
    sidecar is the only place a reader can check a fit against."""
    parsed = {425: AttackStat(attackId=425, damage=0)}
    entry = derive_entries(_rulebox_axes(425, 0, per_ex=60, per_bench=0), parsed)[425]
    for row in entry.evidence:
        assert {"defEx", "defEnergies", "atkBenchStage2"} <= set(row)


@pytest.mark.req("REQ-AUDIT-0021")
def test_the_widened_axes_reproduce_BOTH_shipped_rulings_against_the_real_parsed_table(tmp_path):
    """The two axes turn the fits that CONTRADICTED their rulings into fits that CONFIRM them, so
    the debt is paid rather than overwritten. Card text read at source."""
    from cg.api import all_attack
    from common.scouting.provider import build_attack_stats

    attacks = all_attack()
    records = (_rulebox_axes(425, 0, per_ex=60, per_bench=0)
               + [_m(425, "prevent_ex", 0, def_bench=1, def_ex=2)]
               + _energy_axes(120, 30, per_atk=30, per_def=30, cost=3))
    parsed = build_attack_stats(attacks)
    fits = derive_overrides(records, parsed, texts={a.attackId: a.text or "" for a in attacks})
    assert fits == {425: {"scaleVar": "def_ex_in_play", "scalePerUnit": 60},
                    120: {"scaleVar": "both_active_energy", "scalePerUnit": 30}}

    committed_prov = REPO / "tools" / "meta_tracker" / "attack_overrides.provenance.json"
    committed_table = REPO / "tools" / "meta_tracker" / "attack_overrides.json"
    src = tmp_path / "measurements.json"
    src.write_text(json.dumps({"measurements": records}), encoding="utf-8")
    out, prov = tmp_path / "table.json", tmp_path / "prov.json"
    prov.write_bytes(committed_prov.read_bytes())
    rc = main(["--measurements", str(src), "--out", str(out), "--provenance", str(prov)])
    assert rc == 0, "a fit that REPRODUCES the ruling is the debt paid, not a contradiction"
    assert out.read_bytes() == committed_table.read_bytes()
    entries = json.loads(prov.read_text(encoding="utf-8"))["entries"]
    for aid in ("120", "425"):
        assert entries[aid]["method"] == METHOD_ENGINE_FIT
        assert entries[aid]["evidence"], "a fit with no evidence is the pre-Issue-#224 state"
    for still_owed in ("292", "390"):
        assert entries[still_owed]["method"] == METHOD_TEXT_VERIFIED


@pytest.mark.req("REQ-AUDIT-0021")
def test_the_rulebox_join_refuses_when_the_control_is_still_collinear_with_the_bench():
    """Asserted directly, since the bench family answers first on the records reaching `_scaler`. A
    "control" that is itself {ex}-saturated separates nothing — both readings fit those rows."""
    from sim.generate_attack_overrides import _rulebox_family

    good = _rulebox_axes(425, 0, per_ex=60, per_bench=0)
    assert _rulebox_family(good) == ("def_ex_in_play", 60)
    leaky = [dict(r, defenderExInPlay=r["defenderBench"] + 1) if r["scenario"] == "vanilla_plain"
             else r for r in good]
    leaky = [dict(r, dealtActive=60 * (r["defenderBench"] + 1))
             if r["scenario"] == "vanilla_plain" else r for r in leaky]
    assert _rulebox_family(leaky) is None


@pytest.mark.req("REQ-PROV-0008")
def test_a_NARROWER_run_may_not_overwrite_a_wider_measured_fit():
    """The test is COVERAGE, not method: a narrow run that never measured the `vanilla_plain` control
    cannot have learned the bench count is not the variable. It measured LESS, not more."""
    wide = [{"scenario": "vanilla", "sweep": "def_bench"},
            {"scenario": "vanilla_plain", "sweep": "def_bench"},
            {"scenario": "vanilla", "sweep": "atk_bench"}]
    narrow = [r for r in wide if r["scenario"] != "vanilla_plain"]
    existing = {425: {"method": METHOD_ENGINE_FIT,
                      "fields": {"scaleVar": "def_ex_in_play", "scalePerUnit": 60},
                      "evidence": wide}}
    derived = {425: Derivation({"scaleVar": "def_bench", "scalePerUnit": 60}, narrow)}

    entries, notes, contradicted = merge_provenance(derived, existing, measured={425})
    assert entries[425] == existing[425] and contradicted == [425]
    assert any("CONTRADICTION" in n and "vanilla_plain" in n for n in notes), (
        "the note must name the coverage the run is MISSING, or a reader cannot tell what to rerun")
    # ...and `--rule` is still the one explicit way through, exactly as for a human ruling
    ruled, _, contradicted = merge_provenance(derived, existing, measured={425}, rule=True)
    assert ruled[425]["fields"] == {"scaleVar": "def_bench", "scalePerUnit": 60}
    assert contradicted == []


@pytest.mark.req("REQ-PROV-0007")
def test_an_EQUALLY_WIDE_re_measurement_still_overwrites_a_fit_without_a_halt():
    """The generator may still correct what it authored: a halt here would freeze every engine fit
    and make `--rule` the routine flag."""
    cover = [{"scenario": "vanilla", "sweep": "def_bench"},
             {"scenario": "vanilla_plain", "sweep": "def_bench"}]
    existing = {425: {"method": METHOD_ENGINE_FIT,
                      "fields": {"scaleVar": "def_bench", "scalePerUnit": 60}, "evidence": cover}}
    wider = cover + [{"scenario": "vanilla", "sweep": "def_energy"}]
    derived = {425: Derivation({"scaleVar": "def_ex_in_play", "scalePerUnit": 60}, wider)}
    entries, notes, contradicted = merge_provenance(derived, existing, measured={425})
    assert contradicted == []
    assert entries[425]["fields"] == {"scaleVar": "def_ex_in_play", "scalePerUnit": 60}
    assert any("-> engine_fit" in n for n in notes)


@pytest.mark.req("REQ-PROV-0007")
def test_RETRACTION_is_untouched_by_the_narrowing_guard():
    """The guard is about a narrow run OVERWRITING with a different value, not one deriving nothing."""
    existing = {274: {"method": METHOD_ENGINE_FIT,
                      "fields": {"scaleVar": "atk_hand", "scalePerUnit": 5},
                      "evidence": [{"scenario": "vanilla", "sweep": "hand"}]}}
    entries, notes, contradicted = merge_provenance({}, existing, measured={274})
    assert 274 not in entries and contradicted == []
    assert any("DROPPED" in n for n in notes)
