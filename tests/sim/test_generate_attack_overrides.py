"""The override GENERATOR (ADR-0032 D1: the audit's measurements populate the shipped table).
Pure derivation rules over measurement records -> `attack_overrides.json` entries; conservative by
construction — only engine-agreed, exactly-fitting facts are emitted, everything else stays on the
gap ledger for the formula tier / hand review.

Requirements: REQ-AUDIT-0014 (coin-fork pairs on the vanilla panel -> measured damageMin/damageMax,
BOARD-SCOPED per ADR-0083 Amendment A: one board or several AGREEING boards emit, disagreeing boards
emit nothing, one board answering twice emits nothing — and a bound never ships for an attack that
HAS a scaler, parser-named or fitted, because the bound replaces the base term the scaler adds to),
REQ-AUDIT-0015 (a printed-0 attack dealing one CONSTANT across >=2 modifier scenarios -> a fixed
`damage` override; any cross-scenario disagreement rejects, and a printed-0 attack whose own
sentence says "for each" is refused outright — the panel is one board, so its agreement measures
that board's COUNT, not the attack), REQ-AUDIT-0016 (sweep points fitting
dealt = base + k x var EXACTLY (integer residuals 0, k>0) -> scaleVar/scalePerUnit; noisy fits
reject), REQ-AUDIT-0017 (never emit a field the parser already got right — overrides are deltas),
REQ-AUDIT-0019 (the bench family is named by JOINING two single-variable sweeps; one axis alone,
a drifted pinned seat, a noisy axis, or unequal positive slopes all emit nothing),
REQ-AUDIT-0020 (the active-Energy family joins the SAME way — attacker slope with the defender flat
-> `atk_active_energy`, flat with the defender moving -> `def_active_energy`, equal positive slopes
-> `both_active_energy`; and once a record set carries `defenderEnergies` at all, the one-sided
attacker fit is retired because the join is available),
REQ-AUDIT-0021 (a defender-bench slope is separated from the bench's RULE-BOX composition by a
matched non-{ex} control at the same bench counts; without the control both readings fit and the
bench count wins by accident, with it the rule-box fit must hold AND the bench fit must fail),
REQ-PROV-0002 (a derivation carries the measurement rows that establish it, the rejected/flat axes
included), REQ-PROV-0006 (table and sidecar are emitted in ONE pass, so they cannot desync),
REQ-PROV-0007 (the generator may retract what it authored; never what a human ruled),
REQ-PROV-0008 (a fit CONTRADICTING a text_verified ruling is not written: the ruling is kept, both
readings are named, the run exits non-zero; `--rule` opts in — and the same halt covers an existing
engine_fit that a NARROWER run, one covering fewer (scenario, axis) points, would overwrite).
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
    """One measurement record.

    The three defender-side fields default to **None**, which is a real state and not a shortcut:
    it is what every measurement taken before Issue #275's axes existed looks like, and several
    tests below turn on exactly that difference — `_records_defender_energy` retires the one-sided
    energy fit only once the harness actually records the field.
    """
    r = {"attackId": aid, "attackerCardId": 1, "scenario": scenario, "printed": printed,
         "dealtActive": dealt, "coin": coin, "sweep": sweep, "attackerEnergies": energies,
         "myHandSize": hand, "attackerBench": atk_bench, "defenderBench": def_bench,
         "defenderEnergies": def_energies, "defenderExInPlay": def_ex,
         "attackerBenchStage2": atk_stage2, "koed": False}
    if error:
        r["error"] = error
    return r


def _energy_axes(aid, printed, per_atk, per_def, *, cost=3):
    """Both energy sweeps for one attack: dealt = printed + per_atk*atkEnergy + per_def*defEnergy.

    Mirrors the harness exactly (REQ-AUDIT-0020): the attacker's axis walks ``cost``..``cost+2``
    with the defender pinned at 0, the defender's walks 0..2 with the attacker pinned at ``cost``,
    and the un-swept panel point is the shared origin of both.
    """
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
    """The defender-bench sweep AND its matched non-{ex} control (REQ-AUDIT-0021).

    The {ex} half is the harness's default panel, which is {ex}-SATURATED: the defender's Active
    and every fodder body it benches are Mega Pokemon ex, so `defenderExInPlay` is always
    ``defenderBench + 1``. The control re-runs the same bench counts against an all-non-{ex}
    defender, where it is always 0. ``control=False`` reproduces the pre-Issue-#275 measurement
    set, in which the two variables are indistinguishable.
    """
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


# --- the bound is BOARD-SCOPED (REQ-AUDIT-0014, ADR-0083 Amendment A) ----------------------
# `merge_records` keys a measurement on its sweep point, so `--sweep` leaves SEVERAL vanilla
# `coin="max"` records — one per board. Collapsing them into `{coin: record}` shipped whichever the
# dict landed on: the 274 defect one field over, attributing variation to the one variable that was
# recorded while another that was not controlled had also moved.


def _fork(aid, lo, hi, *, printed=0, sweep=None, energies=1, hand=6, atk_bench=1, def_bench=1):
    """A min/max fork pair measured on ONE board — what `_coin_fork` produces from one position."""
    at = dict(printed=printed, sweep=sweep, energies=energies, hand=hand,
              atk_bench=atk_bench, def_bench=def_bench)
    return [_m(aid, "vanilla", lo, coin="min", **at), _m(aid, "vanilla", hi, coin="max", **at)]


@pytest.mark.req("REQ-AUDIT-0014")
def test_boards_that_disagree_on_the_bound_emit_NOTHING():
    """879 "flip a coin for each {D} Pokémon you have in play" is the shape: the bound is a function
    of the board, and the override table has no form that says so. Naming one board's number as the
    attack's own is the arbitrary survivor with a tidier implementation."""
    parsed = {920: AttackStat(attackId=920, damage=0)}
    recs = (_fork(920, 0, 60, atk_bench=1, sweep={"var": "atk_bench", "step": 1})
            + _fork(920, 0, 120, atk_bench=2, sweep={"var": "atk_bench", "step": 2}))
    assert 920 not in derive_entries(recs, parsed)


@pytest.mark.req("REQ-AUDIT-0014")
def test_boards_that_AGREE_corroborate_the_bound_rather_than_disqualifying_it():
    """Refusing on "more than one board" would throw away the strongest evidence the harness can
    produce. Several boards agreeing is ADR-0083 §3's flat-axis argument applied to the bound: the
    board was varied and provably does not move it."""
    parsed = {921: AttackStat(attackId=921, damage=40)}
    recs = (_fork(921, 0, 40, printed=40, sweep={"var": "atk_bench", "step": 1})
            + _fork(921, 0, 40, printed=40, atk_bench=2, sweep={"var": "atk_bench", "step": 2})
            + _fork(921, 0, 40, printed=40, hand=9, sweep={"var": "hand", "step": 2}))
    assert derive_entries(recs, parsed)[921].fields == {"damageMin": 0, "damageMax": 40}


@pytest.mark.req("REQ-AUDIT-0014")
def test_one_board_measured_twice_with_two_answers_is_not_a_fact():
    """Same physical board, two different `max` values — the measurement does not reproduce, so it
    establishes nothing.

    REACHABLE through a real measurements file, which is why the board key excludes `sweep`/`step`.
    Those are labels, and two plans land on the same board by design: the panel point pins both
    benches at `_BENCH_REF = 1` and so does the `atk_bench` step-1 sweep point. `merge_records` keys
    on the sweep point, so both survive the merge — and keying the board on the label would file
    them as two boards, letting one board's self-contradiction read as ordinary board sensitivity.
    """
    parsed = {922: AttackStat(attackId=922, damage=0)}
    recs = _fork(922, 0, 70) + _fork(922, 0, 90, sweep={"var": "atk_bench", "step": 1})
    assert 922 not in derive_entries(recs, parsed)


@pytest.mark.req("REQ-AUDIT-0014")
def test_the_same_board_reached_by_two_plans_is_ONE_board():
    """The other half of that rule: agreeing on one board through two plans is not two boards
    corroborating each other, it is one measurement repeated — and it still emits."""
    parsed = {925: AttackStat(attackId=925, damage=40)}
    recs = (_fork(925, 0, 40, printed=40)
            + _fork(925, 0, 40, printed=40, sweep={"var": "atk_bench", "step": 1}))
    assert derive_entries(recs, parsed)[925].fields == {"damageMin": 0, "damageMax": 40}


@pytest.mark.req("REQ-AUDIT-0014")
def test_a_measured_bound_never_ships_beside_a_FITTED_scaler():
    """`compute_active_damage` sets `dmg = damageMin/Max` — the bound REPLACES the base — then adds
    `scalePerUnit x count` on top. A bound measured where the scaler contributes already holds that
    contribution, so shipping both adds it twice: an over-prediction, the one class the CI audit gate
    exists to fail. The scaler survives (base-relative, sound); the bound falls back to the parser's,
    which is read off the printed sentence and is base-relative too."""
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
    """The commoner case, and the one the first version of this guard missed by construction.

    `_scaler` returns nothing when the parser already named the variable, so testing only the FIT
    let a parser-named scaler plus a fork pair straight through. The oracle does not care who named
    `scaleVar` — it adds the scaling term whenever the field is set — so the test has to be the
    EFFECTIVE scaler. Measured on a probe before this test was written: the entry shipped
    `damageMax 100` from a fork measured at hand 6, and `compute_active_damage` then read 160 at
    hand 3."""
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
    """Issue #355's adjacent hazard, on the same write path as the merge defect.

    A printed-0 attack whose own printed sentence says "for each" deals a COUNT times a per-unit
    number, and the modifier panel is one board — so "the same number in every scenario" measures
    that board's count, not the attack. Freezing it as a flat `damage` ships an over-prediction
    the moment the count is lower, which is the soundness class `ci_audit_gate.py` exists to fail.

    425 Tenacious Tail is the live case and it is averted only by ACCIDENT. Its attacker is
    colourless, so `pick_panel` finds no weakness or resistance body and the whole panel is
    {vanilla, prevent_ex} — two points. `prevent_ex` zeroes the attack (measured vanilla 120,
    `prevent_ex` 0), so those two disagree and the constant rule rejects on its own. Take that one
    accident away — the two-point panel below agrees at 120 — and the pre-guard generator shipped
    `{"damage": 120}` for an attack that deals 60 x (opponent's Pokemon ex in play).

    The refusal reads the printed text, the idiom `derive_entries` already uses to exclude a
    copy-attack. "for each" is the WHOLE per-unit vocabulary in this pool, verified at source: of
    381 printed-0 attacks carrying text, 124 announce a per-unit count and every one of them says
    "for each" — no "for every", no "times the number".
    """
    parsed = {425: AttackStat(attackId=425, damage=0)}
    texts = {425: "This attack does 60 damage for each of your opponent’s Pokémon {ex} in play."}
    agreeing = [_m(425, "vanilla", 120), _m(425, "prevent_ex", 120)]
    assert 425 not in derive_overrides(agreeing, parsed, texts)
    # ...and the guard is TEXT-shaped, not attack-shaped: Telekinesis's printed-0 constant, whose
    # sentence names no count, still ships. A guard that refused every printed-0 attack would pass
    # the assertion above while deleting the rule it is guarding.
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
    # ...and asserted on the distiller itself, because every rule that COULD hand it a contradicting
    # pair now rejects that pair upstream. The property still has to hold: the day a rule stops
    # rejecting, the record must show the disagreement rather than a survivor of it.
    same = dict(attackId=911, scenario="vanilla", coin=None, sweep=None, attackerBench=1,
                defenderBench=1, attackerEnergies=1, myHandSize=6)
    rows = _evidence([{**same, "dealtActive": 70}, {**same, "dealtActive": 140},
                      {**same, "dealtActive": 70}])
    assert sorted(r["dealt"] for r in rows) == [70, 140]      # identical collapse, contradicting stay


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
    """425 Tenacious Tail is the case. The harness pins both benches at 1 and fills them with
    whatever basics the drive drew, so `def_ex_in_play` measures 0 and a fit concludes "no scaler"
    from data that could not have shown one — and dropping the entry reverts the attack to computing
    ZERO damage, a blind spot rather than an under-read. Kept, and REPORTED."""
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
    """The sibling above's blind spot, and the whole of Issue #355.

    `..._establishes_nothing` covers `derived == {}`. It structurally CANNOT cover `derived != {}`:
    the `KEPT`/`--prune` branch that protects a ruling lives in the second loop, which opens
    `if aid in entries: continue`, and a derived attack is always already in `entries`. So the one
    case where a measurement actively DISAGREES with a human ruling ran straight past the guard —
    the fit was written unconditionally and the disagreement was demoted to a line of stdout.

    Not hypothetical: driven against the committed engine during the Issue #275 verification pass,
    the fitter names `def_bench` for 425. `pick_panel` gives that attacker (306 Dudunsparce ex) card
    1056 Mega Zygarde ex as its vanilla defender — `megaEx=True`, and a Mega Evolution Pokemon ex IS
    a Pokemon ex (`docs/rulebook.txt` L337, why `cgpy/damage.py:56-58` counts `ex or megaEx`) — so
    `def_ex_in_play` and `def_bench` move together at every point the sweep can reach. Against a
    bench of plain Basics that invents 60 damage per body, straight into `state_value`'s `threat`
    and `survival` terms.
    """
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

    # ...unless the operator explicitly opts in, exactly as `--prune` works one branch down.
    ruled, notes, contradicted = merge_provenance(derived, existing, measured={425}, rule=True)
    assert ruled[425]["fields"] == fit and ruled[425]["method"] == METHOD_ENGINE_FIT
    assert ruled[425]["evidence"] == evidence and contradicted == []
    assert any("RULING" in n and "--rule" in n for n in notes), \
        "accepting a ruling-overwrite must still be logged — that is the only durable trace of it"


@pytest.mark.req("REQ-PROV-0008")
def test_a_measurement_that_CONFIRMS_a_ruling_is_not_a_contradiction():
    """The guard's other edge, and the reason it tests `fields` rather than `method`: paying a
    `text_verified` debt off by measuring it is the INTENDED outcome (REQ-PROV-0004), and a guard
    that halted on every fit over a ruling would make the debt unpayable without `--rule` — which
    would then be the routine flag, i.e. no guard at all."""
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
    """The intended way the 111-entry debt is paid down: measure it, and the row stops saying
    "nobody knows where this came from" without anyone editing it by hand."""
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
    """An undrivable attack measured nothing, so its shipped fact must not be retracted on the
    strength of the failure to measure it."""
    assert measured_attacks([_m(5, "vanilla", 0, error="undrivable")]) == set()
    assert measured_attacks([_m(5, "vanilla", 0, error="undrivable"),
                             _m(6, "vanilla", 40)]) == {6}


# --- provenance: one pass, two files (REQ-PROV-0006) ---------------------------------------


@pytest.mark.req("REQ-PROV-0006")
def test_a_regenerate_with_nothing_measured_reproduces_both_committed_files_byte_for_byte(tmp_path):
    """The strongest statement of the whole rule, end-to-end: run the real generator over an EMPTY
    measurement set and both shipped stores come back unchanged, to the byte. Three claims fall out
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


def _measured_120_and_425() -> list[dict]:
    """The Issue #355 measurement pass, RECONSTRUCTED from its recorded rows.

    Driving the native engine costs ~20 min for these two attacks and establishes nothing this test
    needs: the defect is in the merge, and what the merge sees is the derived fields. So the rows
    below are the shapes `audit_attacks` emits, carrying the damage numbers the verification pass
    recorded, and the assertion that they are faithful is that `derive_entries` reproduces the two
    fits the issue quotes EXACTLY — a wrong reconstruction cannot do that by accident.

    * 425 Tenacious Tail (printed 0, "60 damage for each of your opponent's Pokemon {ex} in play").
      Its attacker is colourless, so `pick_panel` finds no weakness or resistance body and the panel
      is {vanilla, prevent_ex} — the two points below, not four. The recorded vanilla number is 120,
      i.e. two {ex} in play with both benches pinned at 1; `prevent_ex` reads 0. Moving the
      DEFENDER's bench moves the {ex} count with it (60/120/180) while the attacker's bench axis
      stays flat -> `def_bench`/60, the collinear wrong variable.
    * 120 Myriad Leaf Shower (printed 30, "30 more damage for each Energy attached to BOTH Active
      Pokemon"). The defender holds no Energy, so every point is the attacker's alone: 60/90/120
      over 1/2/3 -> `atk_active_energy`/30, indistinguishable from the ruled variable on this panel.
    """
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
    """Issue #355's end-to-end acceptance, against the REAL parsed table and the REAL committed
    sidecar: a run that measures attacks 120 and 425 must halt on both rather than rewrite them.

    Three things are asserted at once, and all three are the issue:
      * the derivation really does contradict both rulings (so the guard is not guarding nothing);
      * both committed stores come back BYTE-IDENTICAL — the guard ships a halt, not a number;
      * the run exits NON-ZERO, so a scripted regeneration stops instead of committing the diff.
    """
    from cg.api import all_attack
    from common.scouting.provider import build_attack_stats

    attacks = all_attack()
    records = _measured_120_and_425()
    fits = derive_overrides(records, build_attack_stats(attacks),
                            texts={a.attackId: a.text or "" for a in attacks})
    assert fits == {120: {"scaleVar": "atk_active_energy", "scalePerUnit": 30},
                    425: {"scaleVar": "def_bench", "scalePerUnit": 60}}

    committed_table = REPO / "src" / "common" / "attack_overrides.json"
    committed_prov = REPO / "src" / "common" / "attack_overrides.provenance.json"
    src = tmp_path / "measurements.json"
    src.write_text(json.dumps({"measurements": records}), encoding="utf-8")
    out, prov = tmp_path / "table.json", tmp_path / "prov.json"
    prov.write_bytes(committed_prov.read_bytes())
    rc = main(["--measurements", str(src), "--out", str(out), "--provenance", str(prov)])
    assert rc != 0, "an un-opted-in contradiction must fail a scripted regeneration loudly"
    assert out.read_bytes() == committed_table.read_bytes()
    assert prov.read_bytes() == committed_prov.read_bytes()

    # The files are still WRITTEN — the ruling is protected, so the write is safe by construction,
    # and every other attack's legitimate re-measurement survives the run. Suppressing the write
    # would make `--rule` (the dangerous flag) the only way to get any output at all.
    assert out.exists() and prov.exists()

    # `--rule` is the explicit opt-in, and it is what a wrong number needs in the diff to land.
    assert main(["--measurements", str(src), "--out", str(out), "--provenance", str(prov),
                 "--rule"]) == 0
    assert json.loads(out.read_text(encoding="utf-8"))["425"] == {"scaleVar": "def_bench",
                                                                 "scalePerUnit": 60}


# --- the ENERGY family is joined, never named off one side (REQ-AUDIT-0020, Issue #275) ----
# With the defender holding no Energy, `atk_active_energy` and `both_active_energy` predict the
# SAME number at every point the harness could produce. Attack 120's vanilla point measured 120 at
# three attacker Energy — 30 + 30x3 — which both readings reproduce exactly. The defender-attach
# axis is what makes them different measurements rather than one measurement with two names.


@pytest.mark.req("REQ-AUDIT-0020")
def test_equal_slopes_on_BOTH_actives_name_the_both_variable():
    """Attack 120's real shape. This is the assertion the whole axis exists for: without the
    defender's axis the same records name `atk_active_energy`, and the two differ by 30 damage per
    Energy the OPPONENT has attached — straight into `threat` and `survival`."""
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
    """The reading the harness could not produce AT ALL before the defender attached anything: a
    scaler on the opponent's own Energy read as a constant, because the count was always zero."""
    parsed = {202: AttackStat(attackId=202, damage=20)}
    recs = _energy_axes(202, 20, per_atk=0, per_def=50)
    assert derive_overrides(recs, parsed)[202] == {"scaleVar": "def_active_energy",
                                                  "scalePerUnit": 50}


@pytest.mark.req("REQ-AUDIT-0020")
def test_unequal_positive_energy_slopes_name_nothing():
    """`both_` is a SUM of two equal halves. Two different per-unit numbers are not a family the
    override table can express, and the conservative answer is the gap ledger."""
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
    """The switch, both ways. A pre-Issue-#275 record set carries no `defenderEnergies` at all, and
    `atk_active_energy` is genuinely the only reading it can name — that is the era the seven
    shipped `unaudited` energy overrides come from, and retroactively refusing it would retract
    facts rather than measure them. The moment the field IS recorded, one side names a guess."""
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
# The audit panel is not {ex}-BLIND, it is {ex}-SATURATED: `_panel_body` and `bench_fodder` rank by
# HP and the eight highest-HP eligible basics in the pool are all Mega Pokemon ex, which ARE Pokemon
# ex (docs/rulebook.txt Appendix 1). So `def_ex_in_play` and `def_bench` were the same measurement
# wearing two names, and a fit picked whichever the code tried first — with full confidence.


@pytest.mark.req("REQ-AUDIT-0021")
def test_the_matched_control_names_def_ex_in_play_instead_of_the_collinear_bench_count():
    """Attack 425's real shape. 60 per {ex} in play against an {ex}-saturated bench is 60 per
    BENCHED BODY to any reading that never saw a plain body — and `def_bench`/60 invents 60 damage
    per ordinary Basic on the opponent's bench."""
    parsed = {425: AttackStat(attackId=425, damage=0)}
    recs = _rulebox_axes(425, 0, per_ex=60, per_bench=0)
    assert derive_overrides(recs, parsed)[425] == {"scaleVar": "def_ex_in_play",
                                                  "scalePerUnit": 60}


@pytest.mark.req("REQ-AUDIT-0021")
def test_without_the_control_the_same_records_still_name_the_bench_count():
    """The positive control for the test above: drop ONLY the paired non-{ex} plans and the fit
    flips to `def_bench`. That is what the harness shipped before this axis, so if this stopped
    reproducing it the axis would be proving nothing."""
    parsed = {425: AttackStat(attackId=425, damage=0)}
    recs = _rulebox_axes(425, 0, per_ex=60, per_bench=0, control=False)
    assert derive_overrides(recs, parsed)[425] == {"scaleVar": "def_bench", "scalePerUnit": 60}


@pytest.mark.req("REQ-AUDIT-0021")
def test_a_GENUINE_defender_bench_scaler_still_names_the_bench_with_the_control_present():
    """The guard must not simply refuse every defender-bench fit. When the damage really does track
    the bench SIZE, the non-{ex} control moves with it and the bench reading survives the pooling
    — the control separates two variables, it does not veto one of them."""
    parsed = {206: AttackStat(attackId=206, damage=20)}
    recs = _rulebox_axes(206, 20, per_ex=0, per_bench=30)
    assert derive_overrides(recs, parsed)[206] == {"scaleVar": "def_bench", "scalePerUnit": 30}


@pytest.mark.req("REQ-AUDIT-0021")
def test_a_control_that_neither_reading_fits_names_nothing():
    """Composition and count both move, and not by one consistent rule. Two readings, neither
    exact — the gap ledger, not the tidier of the two."""
    parsed = {207: AttackStat(attackId=207, damage=0)}
    recs = _rulebox_axes(207, 0, per_ex=60, per_bench=0)
    plain = next(r for r in recs if r["scenario"] == "vanilla_plain")
    plain["dealtActive"] = 25                       # the control moved, but on no shared slope
    assert 207 not in derive_overrides(recs, parsed)


@pytest.mark.req("REQ-PROV-0002")
def test_the_matched_control_rows_are_kept_as_evidence_for_the_fit_they_justify():
    """A `def_ex_in_play` row whose evidence held only the {ex} axis would read EXACTLY like the
    `def_bench` row it was written to rule out. The pair is the argument, so the pair is the
    record."""
    parsed = {425: AttackStat(attackId=425, damage=0)}
    entry = derive_entries(_rulebox_axes(425, 0, per_ex=60, per_bench=0), parsed)[425]
    assert entry.fields == {"scaleVar": "def_ex_in_play", "scalePerUnit": 60}
    plain = [r for r in entry.evidence if r["scenario"] == "vanilla_plain"]
    assert {r["defBench"] for r in plain} == {0, 1, 2}
    assert {r["defEx"] for r in plain} == {0}
    assert {r["dealt"] for r in plain} == {0}       # the bench filled and nothing happened


@pytest.mark.req("REQ-PROV-0002")
def test_the_evidence_row_carries_the_defender_state_the_new_axes_control():
    """ADR-0083 §2 wants controls AND records. The sidecar is where the record has to land: a
    reader with `reports/attack_audit/` gitignored has nothing else to check a fit against."""
    parsed = {425: AttackStat(attackId=425, damage=0)}
    entry = derive_entries(_rulebox_axes(425, 0, per_ex=60, per_bench=0), parsed)[425]
    for row in entry.evidence:
        assert {"defEx", "defEnergies", "atkBenchStage2"} <= set(row)


@pytest.mark.req("REQ-AUDIT-0021")
def test_the_widened_axes_reproduce_BOTH_shipped_rulings_against_the_real_parsed_table(tmp_path):
    """The acceptance, end to end and against the REAL table: the two axes turn the two fits that
    contradicted their rulings into fits that CONFIRM them, so `merge_provenance` has nothing to
    halt on and the debt is paid rather than overwritten.

    The reconstruction is the one Issue #355's own halt test uses, widened by the two axes:
    425 Tenacious Tail is "60 damage for each of your opponent's Pokemon {ex} in play" and 120
    Myriad Leaf Shower is "30 more damage for each Energy attached to both Active Pokemon"
    (printed 30). Both are read off the cards, and the assertion that the reconstruction is faithful
    is that it reproduces the RULED variables exactly — a wrong reconstruction cannot do that by
    accident.
    """
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

    committed_prov = REPO / "src" / "common" / "attack_overrides.provenance.json"
    committed_table = REPO / "src" / "common" / "attack_overrides.json"
    src = tmp_path / "measurements.json"
    src.write_text(json.dumps({"measurements": records}), encoding="utf-8")
    out, prov = tmp_path / "table.json", tmp_path / "prov.json"
    prov.write_bytes(committed_prov.read_bytes())
    rc = main(["--measurements", str(src), "--out", str(out), "--provenance", str(prov)])
    assert rc == 0, "a fit that REPRODUCES the ruling is the debt paid, not a contradiction"
    # the shipped values do not move: the axes measured what the human read off the card
    assert out.read_bytes() == committed_table.read_bytes()
    entries = json.loads(prov.read_text(encoding="utf-8"))["entries"]
    for aid in ("120", "425"):
        assert entries[aid]["method"] == METHOD_ENGINE_FIT
        assert entries[aid]["evidence"], "a fit with no evidence is the pre-Issue-#224 state"
    for still_owed in ("292", "390"):
        assert entries[still_owed]["method"] == METHOD_TEXT_VERIFIED


@pytest.mark.req("REQ-AUDIT-0021")
def test_the_rulebox_join_refuses_when_the_control_is_still_collinear_with_the_bench():
    """The join's second, defensive half — asserted directly, because the bench family answers
    first on the records that reach `_scaler`.

    A "control" that is itself {ex}-saturated separates nothing: this is what a predicate testing
    only `ex` and letting Mega Pokemon ex through would produce, and every default fodder body in
    the real pool is a Mega ex rather than a plain one. Both readings fit those rows exactly, so
    naming either is the 274 defect with a different variable in it.
    """
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
    """Issue #275's own consequence, guarded.

    Paying the debt on 120 and 425 flipped both rows from `text_verified` to `engine_fit` — the
    right outcome, and it removed them from the reach of the guard directly above, which tests the
    METHOD. Re-running the pre-#275 sweep would then have replaced `def_ex_in_play` with the
    collinear `def_bench` in silence: the very overwrite Issue #355 was written to stop, one method
    later.

    The test is COVERAGE, not method: the narrow run never measured the `vanilla_plain` control, so
    it cannot have learned that the bench count is not the variable. It has measured less, not more.
    """
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
    """The other half, and the half that keeps REQ-PROV-0007 intact: the generator may still correct
    what it authored. A halt here would freeze every engine fit forever and make `--rule` the
    routine flag — which is no guard at all, and is exactly how the old Decision Gate died."""
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
    """Dropping a fit the fresh measurements no longer support is the 274 outcome and stays free:
    the guard is about a narrow run OVERWRITING with a different value, not about a run that
    derived nothing at all."""
    existing = {274: {"method": METHOD_ENGINE_FIT,
                      "fields": {"scaleVar": "atk_hand", "scalePerUnit": 5},
                      "evidence": [{"scenario": "vanilla", "sweep": "hand"}]}}
    entries, notes, contradicted = merge_provenance({}, existing, measured={274})
    assert 274 not in entries and contradicted == []
    assert any("DROPPED" in n for n in notes)
