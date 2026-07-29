"""**Deny Relevance** — the read that replaced deny's magnitude (`deny_relevance`, ADR-0080 / Issue #199).

Issue #199's grill measured the Worth Damage Rate **underivable**: the corpus-wide DISCARD sweep found 12
`Discard`-context frames, exactly one holding a Hammer (`86091435-68`), and on that board the strip
prices 0.000 under BOTH the ADR-0078 marginal and the incumbent ADR-0062 oracle — so the rate divides
out of `m × PRIZE_DAMAGE_RATE / WORTH_DAMAGE_RATE` and no Δ policy rescues it. The user's doctrine
then reframed deny entirely, as a liveness gate, a redundancy gate and a **relevance** read:

    1. does my opponent have any energy attached to any of its pokemon? if no, hold the hammer
    2. do we KO that pokemon this turn (the active by attack, or a benched one we can reach)? no
       hammer on that specific pokemon
    3. for any pokemon with energy we don't KO — is the energy on their wincon? is it the correct
       energy type? or is it energy on a supporting pokemon we want gone?

Asserted here at the SEAM a consumer reads (`Pilot._opponent_target_rows`), not against the pure
scorer — the failure mode that bit Issue #199 twice was never bad arithmetic, it was correct arithmetic
answering the wrong question on a real board, which a pure-function test passes and a row-level test
does not.

Assertions are **rankings, not magnitudes** (ADR-0080 decision 3): the doctrine is a set of orderings
and the scale was deliberately left free to re-shape, so pinning scalars would make an honest
recalibration look like a regression.

**Card facts verified at source** (`data/EN_Card_Data.csv`, `src/cg/api.py` EnergyType) at authoring:
  * Riolu 677 (Basic, `{F}`) → **Mega Lucario ex** 678 (Stage 1, a SINGLE hop — no intermediate
    Lucario in this set), Aura Jab `{F}` 130 / Mega Brave `{F}{F}` 270.
  * Solrock 676 (Basic, `{F}`) — Cosmic Beam `{F}` 70, *"If you don't have Lunatone on your Bench,
    this attack does nothing"*; no forward form.
  * Munkidori 112 — Adrena-Brain, *"if this Pokémon has any {D} Energy attached"*; Mind Bend `{P}●` 60.
  * Dragapult ex 121 — Phantom Dive `{R}{P}` 200; Jet Headbutt `●` 70 (all-colourless).
  * Meowth ex 1071 — Last-Ditch Catch needs no Energy; Tuck Tail `●●●` 60 (all-colourless).
  * Makuhita 673 → Hariyama 674, Wild Press `{F}{F}{F}` 210.
  * Basic Energy card ids COINCIDE with their EnergyType code — `{F}` 6, `{P}` 5, `{D}` 7, `{R}` 2,
    `{M}` 8 — but that is a coincidence in the data, NOT an identity: Ignition Energy is card **17**,
    a Special Energy (`provides:1` / `provides_evo:3`).
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
    """My Active (a harmless 200-HP body unless overridden) against an opponent board.

    ``active`` / ``bench`` entries are ``(card_id, energies)`` — energies as CARD IDS, the shape a
    real observation carries."""
    def body(spec):
        cid, es = spec
        return {"id": cid, "hp": 200, "maxHp": 200, "energies": list(es)}
    return {"current": {"yourIndex": 0, "players": [
        {"active": [{"id": 999999, "hp": 200, "maxHp": 200, "energies": list(my_energies)}]},
        {"active": [body(active)] if active else [],
         "bench": [body(b) for b in bench]},
    ]}}


def _rows(pilot, obs, board=BOARD):
    result = pilot._opponent_target_rows(obs, board)
    assert result is not None, "expected opponent-target rows for this board"
    return result[1]


def _rel(pilot, obs, board=BOARD):
    """{card_id: relevance} over every emitted row."""
    return {r["id"]: r["relevance"] for r in _rows(pilot, obs, board)}


# ── the derived normalizer ───────────────────────────────────────────────────────────────────────
@pytest.mark.req("REQ-DENYREL-0001")
def test_the_normalizer_recomputes_from_the_card_set():
    """`MAX_ATTACK_DAMAGE` is DERIVED, in the same spirit as `currency.PRIZE_DAMAGE_RATE`: the
    largest attack damage printed in the set. This test IS that recomputation — pinning the literal
    instead would make it tuned-by-another-name (ADR-0065)."""
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
    """Doctrine step 1 — *"does my opponent have any energy attached to any of its pokemon? if yes,
    continue, if no, stop, hold hammer."* Also ADR-0062's whiff, arriving structurally: there is
    nothing to strip, so no gate has to say so."""
    p = _pilot()
    rel = _rel(p, _obs(active=(MEGA_LUCARIO, [])))
    assert rel[MEGA_LUCARIO] == 0.0


# ── gate 2: redundancy ───────────────────────────────────────────────────────────────────────────
@pytest.mark.req("REQ-DENYREL-0003")
def test_an_active_we_are_about_to_ko_denies_nothing():
    """Doctrine step 2 — *"does the opponents active have energy and we KO that active at end of our
    turn? if KO, dont hammer on that specific pokemon."* This is ADR-0063's `active_can_ko` drop,
    which ADR-0078's re-audit ruled NOT subsumed and required to survive the swap: `turns_to_ko_me`
    cannot see that we are about to Knock Out their Active, so without it the read prices a corpse."""
    p = _pilot()
    obs = _obs(active=(MEGA_LUCARIO, [FIGHTING]))
    live = _rel(p, obs, BOARD)
    doomed = _rel(p, obs, types.SimpleNamespace(race_ahead=-1.0, opp_prizes_remaining=3,
                                                active_can_ko=True))
    assert live[MEGA_LUCARIO] > 0.0, "a charged Mega Lucario ex is a real target"
    assert doomed[MEGA_LUCARIO] == 0.0, "we are KOing it — the strip buys nothing"


@pytest.mark.req("REQ-DENYREL-0004")
def test_a_benched_body_we_can_snipe_ko_denies_nothing():
    """Doctrine step 2's bench clause — *"or maybe its a benched pokemon that we can snipe and KO.
    same thing, no hammer on that specific pokemon."* Needs the identity of the sniped body, which
    the aggregate prize read cannot give, hence `combat.bench_ko_indices` (Issue #199).

    My Active is Dragapult ex holding `{R}{P}`: Phantom Dive is affordable and puts 6 damage counters
    (60) on the bench, which finishes a 50-HP body but not a 200-HP one.

    Phantom Dive is a DISTRIBUTABLE spread, not a single-target snipe rider — *"in any way you like"*
    — so all 60 may land on one body. Reading only the snipe rider left this gate blind here, i.e.
    blind on one of our own three decks, which is why the reach is the max of the two."""
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
    """The user's worked ruling — *"if we KO opponents active Lucario with energy, and they have a
    benched riolu and solrock, each with an energy, we hammer the Riolu."*

    Raw current-form damage orders these BACKWARDS (Riolu's Accelerating Stab is 30, Solrock's Cosmic
    Beam is 70), which is exactly why the read scans the whole LINE: attached Energy carries through
    an evolution, and Riolu's `{F}` is banking toward Mega Lucario ex's Mega Brave 270 while Solrock
    evolves into nothing and needs a benched Lunatone to deal anything at all."""
    p = _pilot()
    rel = _rel(p, _obs(bench=[(RIOLU, [FIGHTING]), (SOLROCK, [FIGHTING])]))
    assert rel[RIOLU] > rel[SOLROCK]
    assert rel[SOLROCK] > 0.0, "Solrock is a weaker target, not a dead one"


@pytest.mark.req("REQ-DENYREL-0006")
def test_the_type_that_advances_their_attack_outranks_the_stray_one():
    """The user's worked ruling — *"if opponent has a dragapult with a darkness energy (mistakes
    happen) + a fire energy, hammer against fire only, ignore the darkness."*

    Phantom Dive costs `{R}{P}` for 200; the `{D}` advances neither slot. Note the read is NOT gated
    on current affordability — this body cannot pay Phantom Dive yet (no `{P}`), and the `{R}` is
    still the Energy worth taking, because relevance asks what is on the plan's critical path."""
    p = _pilot("dragapult_ex")
    rows = _rows(p, _obs(active=(DRAGAPULT_EX, [DARKNESS, FIRE])))
    row = next(r for r in rows if r["id"] == DRAGAPULT_EX)
    assert row["relevance"] > 0.0
    assert row["relevance_energy"] == 1, "the {R} at index 1, not the {D} at index 0"


@pytest.mark.req("REQ-DENYREL-0007")
def test_the_ability_fuel_outranks_the_attack_cost_on_the_same_body():
    """The user's worked ruling — *"if opponent have a benched or active Munkidori that we cannot KO
    that has a darkness and a psychic energy, we hammer against the darkness to mute the ability."*

    Adrena-Brain fires *"if this Pokémon has any {D} Energy attached"*; Mind Bend costs `{P}●`. So
    the `{P}` pays a real 60-damage attack slot and the `{D}` pays none — yet the `{D}` is the strip,
    because muting the Ability is the larger loss. This is a WITHIN-body ruling, which is why the
    mute leg is scored to dominate its own body and no further (ADR-0080; valuing it at a flat 1.0
    would rank this Munkidori above a nuke-ready attacker, which the doctrine never claimed)."""
    p = _pilot("dragapult_ex")
    rows = _rows(p, _obs(bench=[(MUNKIDORI, [DARKNESS, PSYCHIC])], active=(DRAGAPULT_EX, [FIRE])))
    row = next(r for r in rows if r["id"] == MUNKIDORI)
    assert row["relevance_energy"] == 0, "the {D} at index 0, not the {P} at index 1"
    assert row["relevance_ability_leg"] > row["relevance_attack_leg"]


@pytest.mark.req("REQ-DENYREL-0008")
def test_a_second_copy_of_the_gated_type_means_the_strip_mutes_nothing():
    """Adrena-Brain needs *"any {D}"*, so a Munkidori holding two `{D}` keeps its Ability through a
    strip — the mute leg must not fire. Derived from the card text, not a special case."""
    p = _pilot("dragapult_ex")
    rows = _rows(p, _obs(bench=[(MUNKIDORI, [DARKNESS, DARKNESS])], active=(DRAGAPULT_EX, [FIRE])))
    row = next(r for r in rows if r["id"] == MUNKIDORI)
    assert row["relevance_ability_leg"] == 0.0


@pytest.mark.req("REQ-DENYREL-0009")
def test_an_energy_on_a_body_that_does_nothing_with_it_is_ignored():
    """The user's worked ruling — *"does opponent has a meowth with an energy, ignore it."*

    Meowth ex's Last-Ditch Catch needs no Energy and Tuck Tail costs `●●●` — ALL colourless, so no
    attached Energy is ever on a specific-type slot. The 0 falls out of the cost, with no card-level
    special case."""
    p = _pilot("dragapult_ex")
    rel = _rel(p, _obs(bench=[(MEOWTH_EX, [DARKNESS])], active=(DRAGAPULT_EX, [FIRE])))
    assert rel[MEOWTH_EX] == 0.0


@pytest.mark.req("REQ-DENYREL-0010")
def test_the_marginal_target_lands_between_dead_and_critical():
    """The user's worked ruling — *"if opponent has makuhuta with single energy, hammer? maybe."*

    A genuine maybe: Makuhita's own attacks are 10 and 30, but it evolves into Hariyama whose Wild
    Press is `{F}{F}{F}` 210. So it must be neither ignorable like the Meowth nor as urgent as the
    Riolu — which is the case a boolean gate cannot express and is why relevance is a scalar."""
    p = _pilot()
    rel = _rel(p, _obs(bench=[(MAKUHITA, [FIGHTING]), (RIOLU, [FIGHTING]), (MEOWTH_EX, [FIGHTING])]))
    assert rel[MEOWTH_EX] < rel[MAKUHITA] < rel[RIOLU]


# ── surplus, and the Energy-identity trap ────────────────────────────────────────────────────────
@pytest.mark.req("REQ-DENYREL-0011")
def test_surplus_energy_prices_zero_the_way_adr_0062_says_it_should():
    """ADR-0062's worked table records that a Mega Lucario ex holding THREE `{F}` denies **0** — it
    can still pay Aura Jab `{F}` and Mega Brave `{F}{F}` after losing one. Here that arrives
    STRUCTURALLY from the surplus clause rather than from a separate whiff gate, and the 1- and
    2-Energy rows (which its table prices 130 and 140) stay live."""
    p = _pilot()
    at = lambda n: _rel(p, _obs(active=(MEGA_LUCARIO, [FIGHTING] * n)))[MEGA_LUCARIO]
    assert at(1) > 0.0 and at(2) > 0.0
    assert at(3) == 0.0, "surplus in the type — the strip takes nothing it still needs"


@pytest.mark.req("REQ-DENYREL-0012")
def test_a_special_energy_is_resolved_by_type_not_by_card_id():
    """The trap this must not fall into. Attached Energy is a list of CARD IDS, and for Basic Energy
    the id coincides with the `EnergyType` code (Basic `{F}` is card 6, FIGHTING is 6) — a
    coincidence in the data, not an identity. **Ignition Energy is card id 17**, a Special Energy
    that pays colourless slots only, so it is never on a specific-type critical path.

    The discriminating case is `[IGNITION, PSYCHIC]` on a Mega Lucario ex, whose costs are `{F}` and
    `{F}{F}`. A card-id-as-type reading would treat Ignition's id 17 as a type and the `{P}` card 5
    as PSYCHIC — neither matching FIGHTING — and land on 0 by luck. The Provider-resolved reading
    reaches the same 0 for a REASON, and the two separate the moment a real `{F}` is added: only a
    correct reading picks index 2. Both halves are asserted, since a test that its own bug would
    pass is not a test."""
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
    """The second way a strip sets an attack back: every specific-type slot is already covered and
    the body sits exactly on the total cost, so losing ANY Energy drops it under.

    Hariyama's Wild Press is `{F}{F}{F}` — three specific slots — so a Makuhita line holding two
    `{F}` is short on the type and the typed clause already fires. The clause that needs its own
    test is the guard on it: a body still MISSING a colour is bound by the type, not the count, so
    the off-type Energy stays irrelevant. Dragapult ex holding `{D}` + `{R}` against Phantom Dive
    `{R}{P}` sits exactly on the 2-Energy total, and the `{D}` must still score 0 — the user's
    *"ignore the darkness"*. Without the type-ready guard a plain total-count rule flags both."""
    p = _pilot("dragapult_ex")
    row = next(r for r in _rows(p, _obs(active=(DRAGAPULT_EX, [DARKNESS, FIRE])))
               if r["id"] == DRAGAPULT_EX)
    assert row["relevance_energy"] == 1, "exactly on total cost, but the {P} is missing — type binds"


@pytest.mark.req("REQ-DENYREL-0017")
def test_a_brief_named_threat_is_sharpened_but_a_whiff_is_never_promoted():
    """ADR-0080 decision 2: a matched Brief's `threats` MULTIPLY the derived rank, never source it.
    So a named body outranks the same body unnamed — and, because the boost is a multiplier, it can
    never make an irrelevant Energy worth taking (`0 x anything == 0`). That is the same discipline
    `_DENIAL_UNFAVORED` follows: *"a booster must scale the oracle, never add to it"* (ADR-0063)."""
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
    """The forward-potential leg is the scan's SCOPE rather than a separate addend, so it stays
    inspectable via `relevance_forward` — otherwise a surprising ranking could not be diagnosed
    without a debugger. A Riolu's whole claim comes from Mega Lucario ex, which it is not yet; a
    Solrock has no forward form at all, so its claim is entirely its own."""
    p = _pilot()
    rows = {r["id"]: r for r in _rows(p, _obs(bench=[(RIOLU, [FIGHTING]), (SOLROCK, [FIGHTING])]))}
    assert rows[RIOLU]["relevance_forward"] > 0, "Riolu's claim is Mega Lucario ex's Mega Brave"
    assert rows[SOLROCK]["relevance_forward"] == 0, "Solrock evolves into nothing"


# ── the kill-switch ──────────────────────────────────────────────────────────────────────────────
@pytest.mark.req("REQ-DENYREL-0013")
def test_the_switch_off_path_emits_nothing_at_all():
    """Ships OFF and byte-identical (ADR-0080 decision 4 / the `deny_strip_delta` precedent): no
    field emitted, and the redundancy gate not even computed. Nothing reads these yet — Issue #187 is the
    consumer — so ON must change no decision either."""
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
    """ADR-0076 Amendment C's caching promise, which this must not break: a real decision computes
    the per-body simulation ONCE and shares it through `_opponent_target_cache`."""
    p = _pilot()
    obs = _obs(active=(MEGA_LUCARIO, [FIGHTING]))
    calls = []
    original = p._relevance_terms
    p._relevance_terms = lambda *a, **k: (calls.append(1), original(*a, **k))[1]
    p._board(obs)
    assert len(calls) == 1, f"one energized body, one relevance resolution (got {len(calls)})"


@pytest.mark.req("REQ-DENYREL-0015")
def test_an_unknown_card_degrades_to_zero_rather_than_raising():
    """Fail toward NOT spending the Hammer: an unknown body is not evidence that its Energy is
    valuable, and a missing card fact must never crash a decision."""
    p = _pilot()
    rel = _rel(p, _obs(active=(123456789, [FIGHTING])))
    assert rel[123456789] == 0.0
