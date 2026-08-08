"""Deny Relevance — the read that replaced deny's magnitude (`deny_relevance`, ADR-0080 / Issue #199).

Three gates: LIVENESS (any Energy attached at all?), REDUNDANCY (do we KO that body this turn?) and
RELEVANCE (is the Energy on their wincon, is it the right type, or is it on support we want gone?).

Asserted at the SEAM a consumer reads (`Pilot._opponent_target_rows`), because the failure that bit
Issue #199 twice was correct arithmetic answering the wrong question on a real board. Assertions are
RANKINGS, not magnitudes (ADR-0080 decision 3) — the scale was deliberately left free to re-shape.

Card facts below are verified at `data/EN_Card_Data.csv` and `src/cg/api.py` EnergyType.
"""
from __future__ import annotations

import csv
import re
import types
from pathlib import Path

import pytest

from common import deny_relevance as dr

REPO = Path(__file__).resolve().parents[2]

RIOLU, MEGA_LUCARIO, SOLROCK = 677, 678, 676
MUNKIDORI, DRAGAPULT_EX, MEOWTH_EX = 112, 121, 1071
MAKUHITA, HARIYAMA = 673, 674
FIRE, PSYCHIC, FIGHTING, DARKNESS = 2, 5, 6, 7
IGNITION = 17

BOARD = types.SimpleNamespace(race_ahead=-1.0, opp_prizes_remaining=3, active_can_ko=False)


def _pilot(deck="mega_lucario", *, on=True):
    from train.tune import _build_pilot
    p = _build_pilot(deck)[0]
    p._planning = False
    p.deny_relevance = on
    return p


def _obs(bench=(), *, active=None, my_energies=()):
    """My Active (a harmless 200-HP body unless overridden) against an opponent board. ``active`` /
    ``bench`` entries are ``(card_id, energies)``, energies as CARD IDS — the shape an obs carries."""
    def body(spec):
        cid, es = spec
        return {"id": cid, "hp": 200, "maxHp": 200, "energies": list(es)}
    return {"current": {"yourIndex": 0, "players": [
        {"active": [{"id": 999999, "hp": 200, "maxHp": 200, "energies": list(my_energies)}]},
        {"active": [body(active)] if active else [],
         "bench": [body(b) for b in bench]},
    ]}}


def _rows(pilot, obs, board=BOARD):
    pilot._snapshot(obs)              # the per-decision StateModel these rows now read (POC-T1)
    result = pilot._opponent_target_rows(obs, board)
    assert result is not None, "expected opponent-target rows for this board"
    return result[1]


def _rel(pilot, obs, board=BOARD):
    """{card_id: relevance} over every emitted row."""
    return {r["id"]: r["relevance"] for r in _rows(pilot, obs, board)}


# ── the derived normalizer ───────────────────────────────────────────────────────────────────────
@pytest.mark.req("REQ-DENYREL-0001")
def test_the_normalizer_recomputes_from_the_card_set():
    """`MAX_ATTACK_DAMAGE` is DERIVED — the largest attack damage printed in the set — and this test
    IS that recomputation; pinning the literal would tune by another name (ADR-0065)."""
    best = 0
    with open(REPO / "data" / "EN_Card_Data.csv", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            m = re.match(r"^(\d+)", (row.get("Damage") or "").strip())
            if m:
                best = max(best, int(m.group(1)))
    assert best == dr.MAX_ATTACK_DAMAGE


# ── gate 1: liveness ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.req("REQ-DENYREL-0002")
def test_a_body_holding_no_energy_is_irrelevant():
    """Doctrine step 1. Also ADR-0062's whiff, arriving STRUCTURALLY: there is nothing to strip, so
    no gate has to say so."""
    p = _pilot()
    rel = _rel(p, _obs(active=(MEGA_LUCARIO, [])))
    assert rel[MEGA_LUCARIO] == 0.0


# ── gate 2: redundancy ───────────────────────────────────────────────────────────────────────────
@pytest.mark.req("REQ-DENYREL-0003")
def test_an_active_we_are_about_to_ko_denies_nothing():
    """Doctrine step 2, and ADR-0063's `active_can_ko` drop that ADR-0078 ruled NOT subsumed:
    `turns_to_ko_me` cannot see we are about to KO their Active, so the read prices a corpse."""
    p = _pilot()
    obs = _obs(active=(MEGA_LUCARIO, [FIGHTING]))
    live = _rel(p, obs, BOARD)
    doomed = _rel(p, obs, types.SimpleNamespace(race_ahead=-1.0, opp_prizes_remaining=3,
                                                active_can_ko=True))
    assert live[MEGA_LUCARIO] > 0.0, "a charged Mega Lucario ex is a real target"
    assert doomed[MEGA_LUCARIO] == 0.0, "we are KOing it — the strip buys nothing"


@pytest.mark.req("REQ-DENYREL-0004")
def test_a_benched_body_we_can_snipe_ko_denies_nothing():
    """Doctrine step 2's bench clause, which needs the IDENTITY of the sniped body. Phantom Dive is a
    DISTRIBUTABLE spread, not a single-target rider, so the reach is the MAX of the two."""
    p = _pilot("dragapult_ex")
    obs = _obs(bench=[(SOLROCK, [FIGHTING]), (RIOLU, [FIGHTING])],
               active=(MEGA_LUCARIO, []), my_energies=[FIRE, PSYCHIC])
    obs["current"]["players"][0]["active"][0]["id"] = DRAGAPULT_EX
    obs["current"]["players"][1]["bench"][0]["hp"] = 50        # dies to the spread
    rows = _rows(p, obs)
    by_area = {(r["area"], r["bi"]): r for r in rows}
    sniped, safe = by_area[("bench", 0)], by_area[("bench", 1)]
    assert sniped["relevance"] == 0.0, "we snipe-KO it this turn — no hammer on that body"
    assert safe["relevance"] > 0.0, "the body we do NOT kill is still a live target"


# ── the doctrine's five worked rulings ───────────────────────────────────────────────────────────
@pytest.mark.req("REQ-DENYREL-0005")
def test_the_energy_on_the_wincon_line_outranks_the_one_on_support():
    """Raw current-form damage orders these BACKWARDS, which is why the read scans the whole LINE:
    attached Energy carries through an evolution, and Solrock evolves into nothing."""
    p = _pilot()
    rel = _rel(p, _obs(bench=[(RIOLU, [FIGHTING]), (SOLROCK, [FIGHTING])]))
    assert rel[RIOLU] > rel[SOLROCK]
    assert rel[SOLROCK] > 0.0, "Solrock is a weaker target, not a dead one"


@pytest.mark.req("REQ-DENYREL-0006")
def test_the_type_that_advances_their_attack_outranks_the_stray_one():
    """Phantom Dive costs `{R}{P}`, so the `{D}` advances neither slot. NOT gated on current
    affordability — relevance asks what is on the plan's critical path, not what is payable now."""
    p = _pilot("dragapult_ex")
    rows = _rows(p, _obs(active=(DRAGAPULT_EX, [DARKNESS, FIRE])))
    row = next(r for r in rows if r["id"] == DRAGAPULT_EX)
    assert row["relevance"] > 0.0
    assert row["relevance_energy"] == 1, "the {R} at index 1, not the {D} at index 0"


@pytest.mark.req("REQ-DENYREL-0007")
def test_the_ability_fuel_outranks_the_attack_cost_on_the_same_body():
    """The `{P}` pays a real attack slot and the `{D}` pays none, yet the `{D}` is the strip because
    muting the Ability is the larger loss. A WITHIN-body ruling, so the mute leg goes no further."""
    p = _pilot("dragapult_ex")
    rows = _rows(p, _obs(bench=[(MUNKIDORI, [DARKNESS, PSYCHIC])], active=(DRAGAPULT_EX, [FIRE])))
    row = next(r for r in rows if r["id"] == MUNKIDORI)
    assert row["relevance_energy"] == 0, "the {D} at index 0, not the {P} at index 1"
    assert row["relevance_ability_leg"] > row["relevance_attack_leg"]


@pytest.mark.req("REQ-DENYREL-0008")
def test_a_second_copy_of_the_gated_type_means_the_strip_mutes_nothing():
    """Adrena-Brain needs *"any {D}"*, so two `{D}` survive a strip — derived from the card text."""
    p = _pilot("dragapult_ex")
    rows = _rows(p, _obs(bench=[(MUNKIDORI, [DARKNESS, DARKNESS])], active=(DRAGAPULT_EX, [FIRE])))
    row = next(r for r in rows if r["id"] == MUNKIDORI)
    assert row["relevance_ability_leg"] == 0.0


@pytest.mark.req("REQ-DENYREL-0009")
def test_an_energy_on_a_body_that_does_nothing_with_it_is_ignored():
    """Meowth ex's attacks are all-colourless, so no attached Energy is ever on a specific-type slot.
    The 0 falls out of the cost, with no card-level special case."""
    p = _pilot("dragapult_ex")
    rel = _rel(p, _obs(bench=[(MEOWTH_EX, [DARKNESS])], active=(DRAGAPULT_EX, [FIRE])))
    assert rel[MEOWTH_EX] == 0.0


@pytest.mark.req("REQ-DENYREL-0010")
def test_the_marginal_target_lands_between_dead_and_critical():
    """A genuine maybe: Makuhita's own attacks are 10 and 30 but Hariyama's Wild Press is 210. The
    case a boolean gate cannot express, and the reason relevance is a scalar."""
    p = _pilot()
    rel = _rel(p, _obs(bench=[(MAKUHITA, [FIGHTING]), (RIOLU, [FIGHTING]), (MEOWTH_EX, [FIGHTING])]))
    assert rel[MEOWTH_EX] < rel[MAKUHITA] < rel[RIOLU]


# ── surplus, and the Energy-identity trap ────────────────────────────────────────────────────────
@pytest.mark.req("REQ-DENYREL-0011")
def test_surplus_energy_prices_zero_the_way_adr_0062_says_it_should():
    """ADR-0062's table prices three `{F}` at 0 — both attacks stay payable after a strip. Arrives
    STRUCTURALLY from the surplus clause here, rather than from a separate whiff gate."""
    p = _pilot()
    at = lambda n: _rel(p, _obs(active=(MEGA_LUCARIO, [FIGHTING] * n)))[MEGA_LUCARIO]
    assert at(1) > 0.0 and at(2) > 0.0
    assert at(3) == 0.0, "surplus in the type — the strip takes nothing it still needs"


@pytest.mark.req("REQ-DENYREL-0012")
def test_a_special_energy_is_resolved_by_type_not_by_card_id():
    """Attached Energy is a list of CARD IDS, and a Basic Energy's id COINCIDES with its `EnergyType`
    code — a coincidence in the data, not an identity. Ignition (17) is a colourless Special."""
    p = _pilot()
    row = next(r for r in _rows(p, _obs(active=(MEGA_LUCARIO, [IGNITION, PSYCHIC])))
               if r["id"] == MEGA_LUCARIO)
    assert row["relevance"] == 0.0, "neither a colourless Special nor an off-type {P} is on the path"
    row = next(r for r in _rows(p, _obs(active=(MEGA_LUCARIO, [IGNITION, PSYCHIC, FIGHTING])))
               if r["id"] == MEGA_LUCARIO)
    assert row["relevance"] > 0.0 and row["relevance_energy"] == 2, \
        "the {F} at index 2 — not the Ignition at 0, not the {P} at 1"


@pytest.mark.req("REQ-DENYREL-0016")
def test_the_binding_count_catches_a_typed_attack_the_body_is_exactly_paying_for():
    """The second way a strip sets an attack back: every typed slot covered and the body exactly on
    the total cost. A body still MISSING a colour is bound by the TYPE, not the count."""
    p = _pilot("dragapult_ex")
    row = next(r for r in _rows(p, _obs(active=(DRAGAPULT_EX, [DARKNESS, FIRE])))
               if r["id"] == DRAGAPULT_EX)
    assert row["relevance_energy"] == 1, "exactly on total cost, but the {P} is missing — type binds"


@pytest.mark.req("REQ-DENYREL-0017")
def test_a_brief_named_threat_is_sharpened_but_a_whiff_is_never_promoted():
    """ADR-0080 decision 2: a Brief's `threats` MULTIPLY the derived rank, never source it, so it can
    never promote a whiff — the same discipline as *"a booster must scale, never add"* (ADR-0063)."""
    p = _pilot()
    obs = _obs(bench=[(SOLROCK, [FIGHTING]), (MEOWTH_EX, [FIGHTING])])
    plain = _rel(p, obs)
    boosted = _rel(p, obs, types.SimpleNamespace(race_ahead=-1.0, opp_prizes_remaining=3,
                                                 active_can_ko=False,
                                                 brief_threat_ids=frozenset({SOLROCK, MEOWTH_EX})))
    assert boosted[SOLROCK] > plain[SOLROCK], "the Brief sharpens a body that already reads"
    assert boosted[MEOWTH_EX] == plain[MEOWTH_EX] == 0.0, "a Brief cannot promote a whiff"


@pytest.mark.req("REQ-DENYREL-0018")
def test_the_forward_contribution_is_reported_separately():
    """The forward leg is the scan's SCOPE, not a separate addend, so it stays inspectable via
    `relevance_forward` — otherwise a surprising ranking needs a debugger to diagnose."""
    p = _pilot()
    rows = {r["id"]: r for r in _rows(p, _obs(bench=[(RIOLU, [FIGHTING]), (SOLROCK, [FIGHTING])]))}
    assert rows[RIOLU]["relevance_forward"] > 0, "Riolu's claim is Mega Lucario ex's Mega Brave"
    assert rows[SOLROCK]["relevance_forward"] == 0, "Solrock evolves into nothing"


# ── the kill-switch ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.req("REQ-DENYREL-0013")
def test_the_switch_off_path_emits_nothing_at_all():
    """Ships OFF and byte-identical (ADR-0080 decision 4): no field emitted and the redundancy gate
    not even computed. Nothing reads these yet, so ON must change no decision either."""
    off = _rows(_pilot(on=False), _obs(active=(MEGA_LUCARIO, [FIGHTING])))
    assert all("relevance" not in r for r in off)
    on = _rows(_pilot(on=True), _obs(active=(MEGA_LUCARIO, [FIGHTING])))
    assert all("relevance" in r for r in on)
    # the shared terms are untouched by the switch — the read is additive, not a repricing
    for a, b in zip(off, on):
        assert (a["value"], a["prize"], a["survival_shift"]) == \
               (b["value"], b["prize"], b["survival_shift"])


@pytest.mark.req("REQ-DENYREL-0014")
def test_the_read_is_resolved_once_per_decision_not_once_per_option():
    """ADR-0076 Amendment C: the per-body simulation runs ONCE, shared via `_opponent_target_cache`."""
    p = _pilot()
    obs = _obs(active=(MEGA_LUCARIO, [FIGHTING]))
    calls = []
    original = p._relevance_terms
    p._relevance_terms = lambda *a, **k: (calls.append(1), original(*a, **k))[1]
    p._board(obs)
    assert len(calls) == 1, f"one energized body, one relevance resolution (got {len(calls)})"


@pytest.mark.req("REQ-DENYREL-0015")
def test_an_unknown_card_degrades_to_zero_rather_than_raising():
    """Fail toward NOT spending the Hammer: an unknown body is not evidence its Energy is valuable."""
    p = _pilot()
    rel = _rel(p, _obs(active=(123456789, [FIGHTING])))
    assert rel[123456789] == 0.0
