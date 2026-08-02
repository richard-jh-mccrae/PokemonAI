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
a drifted pinned seat, a noisy axis, or unequal positive slopes all emit nothing),
REQ-PROV-0002 (a derivation carries the measurement rows that establish it, the rejected/flat axes
included), REQ-PROV-0006 (table and sidecar are emitted in ONE pass, so they cannot desync),
REQ-PROV-0007 (the generator may retract what it authored; never what a human ruled).
"""
import json
from pathlib import Path

import pytest

from common.scouting.provider import AttackStat
from sim.generate_attack_overrides import (METHOD_ENGINE_FIT, METHOD_TEXT_VERIFIED,
                                           METHOD_UNAUDITED, Derivation, derive_entries,
                                           derive_overrides, main, measured_attacks,
                                           merge_provenance)

REPO = Path(__file__).resolve().parents[2]


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


# --- provenance: the evidence rides the derivation (REQ-PROV-0002) -------------------------
# `reports/attack_audit/` is gitignored, so a shipped override used to be uncheckable against its
# own evidence — which is how 274's `atk_hand` fit sat wrong and unseen. The fix is that deriving a
# value and recording what established it are ONE operation, not two descriptions that can drift.


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
    """The load-bearing half. A flat hand axis is what PROVES hand size was measured and does not
    move the damage; keeping only the fitted bench points would preserve the conclusion and throw
    away the evidence that makes it sound — reintroducing 274's blind spot one level down."""
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
    """Dedup collapses identical rows, never disagreeing ones. Two measurements that agree on every
    controlled variable and disagree on the damage are the single most informative thing a reader
    can find in this file — silently keeping whichever came last would discard exactly the evidence
    that says a fact is not what it claims."""
    # A disagreement that stops every rule firing ships nothing, so there is nothing to document.
    parsed = {909: AttackStat(attackId=909, damage=0)}
    recs = [_m(909, "vanilla", 70), _m(909, "weak", 70), _m(909, "weak", 140)]
    assert 909 not in derive_entries(recs, parsed)
    # ...but where a rule DOES fire, the disagreeing rows survive into the record
    recs = [_m(910, "vanilla", 70), _m(910, "weak", 70),
            _m(910, "vanilla", 0, coin="min"), _m(910, "vanilla", 70, coin="max"),
            _m(910, "vanilla", 90, coin="max")]              # same identity, different damage
    entry = derive_entries(recs, {910: AttackStat(attackId=910, damage=0)})[910]
    assert sorted(r["dealt"] for r in entry.evidence if r["coin"] == "max") == [70, 90]


# --- provenance: the merge rule (REQ-PROV-0007) --------------------------------------------
# The generator may retract what it AUTHORED; it may not retract what a human RULED. A partial
# recapture must never silently un-price an attack it did not measure.


def _prov(method, fields, **extra):
    return {"method": method, "fields": fields, "evidence": [], **extra}


@pytest.mark.req("REQ-PROV-0007")
def test_a_fit_the_fresh_measurements_no_longer_support_is_dropped():
    """Exactly the 274 outcome: a stale `atk_hand` fit today's fitter would not emit. The generator
    authored it, so the generator may take it back."""
    existing = {274: _prov(METHOD_ENGINE_FIT, {"scaleVar": "atk_hand", "scalePerUnit": 5})}
    entries, notes = merge_provenance({}, existing, measured={274})
    assert 274 not in entries
    assert any("DROPPED" in n for n in notes)


@pytest.mark.req("REQ-PROV-0007")
def test_an_attack_this_run_never_measured_keeps_its_entry():
    """A per-attack recapture is the intended workflow, so a run that measured one attack must not
    blow away the other 116."""
    existing = {6: _prov(METHOD_UNAUDITED, {"damageMin": 0, "damageMax": 120}),
                274: _prov(METHOD_ENGINE_FIT, {"scaleVar": "atk_hand", "scalePerUnit": 5})}
    entries, _ = merge_provenance({}, existing, measured={274})
    assert entries[6] == existing[6] and 274 not in entries


@pytest.mark.req("REQ-PROV-0007")
def test_a_human_ruling_survives_a_measurement_that_establishes_nothing():
    """425 Tenacious Tail is the case. The harness pins both benches at 1 and fills them with
    whatever basics the drive drew, so `def_ex_in_play` measures 0 and a fit concludes "no scaler"
    from data that could not have shown one — and dropping the entry reverts the attack to computing
    ZERO damage, a blind spot rather than an under-read. Kept, and REPORTED."""
    existing = {425: _prov(METHOD_TEXT_VERIFIED, {"scaleVar": "def_ex_in_play",
                                                  "scalePerUnit": 60}, owner="#275")}
    entries, notes = merge_provenance({}, existing, measured={425})
    assert entries[425] == existing[425]
    assert any("KEPT" in n and "--prune" in n for n in notes)
    # ...unless the operator explicitly opts in
    pruned, notes = merge_provenance({}, existing, measured={425}, prune=True)
    assert pruned == {} and any("PRUNED" in n for n in notes)


@pytest.mark.req("REQ-PROV-0007")
def test_a_recapture_backfills_an_unaudited_entry_into_a_fit():
    """The intended way the 111-entry debt is paid down: measure it, and the row stops saying
    "nobody knows where this came from" without anyone editing it by hand."""
    fields = {"scaleVar": "both_bench", "scalePerUnit": 20}
    evidence = [{"scenario": "vanilla", "sweep": "atk_bench", "step": 0, "coin": None,
                 "atkBench": 0, "defBench": 1, "energies": 1, "hand": 6, "dealt": 80}]
    existing = {274: _prov(METHOD_UNAUDITED, fields)}
    entries, notes = merge_provenance({274: Derivation(fields, evidence)}, existing, measured={274})
    assert entries[274]["method"] == METHOD_ENGINE_FIT
    assert entries[274]["evidence"] == evidence
    assert any("now measured" in n for n in notes)


@pytest.mark.req("REQ-PROV-0007")
def test_measured_attacks_ignores_a_run_that_only_ledgered_errors():
    """An undrivable attack measured nothing, so its shipped fact must not be retracted on the
    strength of the failure to measure it."""
    assert measured_attacks([_m(5, "vanilla", 0, error="undrivable")]) == set()
    assert measured_attacks([_m(5, "vanilla", 0, error="undrivable"),
                             _m(6, "vanilla", 40)]) == {6}


# --- provenance: one pass, two files (REQ-PROV-0006) ---------------------------------------


@pytest.mark.req("REQ-PROV-0006")
def test_a_regenerate_with_nothing_measured_reproduces_both_committed_files_byte_for_byte(tmp_path):
    """The strongest statement of the whole rule, end-to-end: run the real generator over an EMPTY
    measurement set and both shipped stores come back unchanged, to the byte. That pins three things
    at once — the merge never regresses an unmeasured fact, the table is emitted from the sidecar's
    own `fields` so the two cannot desync, and the writer's format (CRLF, indent, key order) is
    exactly what is committed, on whichever OS runs this."""
    committed_table = REPO / "src" / "common" / "attack_overrides.json"
    committed_prov = REPO / "src" / "common" / "attack_overrides.provenance.json"
    empty = tmp_path / "measurements.json"
    empty.write_text(json.dumps({"measurements": []}), encoding="utf-8")
    # Everything under tmp_path — a test that can write over a committed store is a test that
    # eventually does.
    out, prov = tmp_path / "table.json", tmp_path / "prov.json"
    prov.write_bytes(committed_prov.read_bytes())
    assert main(["--measurements", str(empty), "--out", str(out), "--provenance", str(prov)]) == 0
    assert out.read_bytes() == committed_table.read_bytes()
    assert prov.read_bytes() == committed_prov.read_bytes()
