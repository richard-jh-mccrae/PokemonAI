"""S3c — the deny instrument's STRIP delta (`Pilot._strip_delta_terms`, ADR-0078 / #199).

#186 built the opponent-target marginal's **removal** Δ: the turns of survival bought by a body
leaving the board. That is the gust / snipe question. A Crushing Hammer never asks it — it discards
ONE Energy and the body stays — so deny had no slice to read.

The Δ that gives it one carries the **user's ruling of 2026-07-28** (ADR-0078 Amendments B + C): *"deny
shall not calculate energy re-attached on a following turn. It shall only ever perform a calculation
on opponent's Pokémon with energy during our own turn."* So the POLICY is `base_attach: 0` — no credit
for the Energy they re-attach next turn — while the FORM stays the shared two-term marginal, so the
one-backend claim holds.

Card facts verified at source (`data/EN_Card_Data.csv`): Mega Lucario ex (678) attacks are Aura Jab
`{F}` 130 and Mega Brave `{F}{F}` 270; Basic `{F}` Energy is card id 6. Energy entries in an
observation are card ids, not dicts — the charged affordability path reads their types.
"""
from __future__ import annotations

import types

import pytest

from common import needs

MEGA_LUCARIO, FIGHTING = 678, 6


def _pilot(*, strip=True):
    from train.tune import _build_pilot
    p = _build_pilot("mega_lucario")[0]
    p._planning = False
    p.deny_strip_delta = strip
    return p


def _obs(opp_energies, *, my_hp=200):
    """My Active at ``my_hp``; their Active a Mega Lucario ex holding ``opp_energies`` Basic {F}."""
    return {"current": {"yourIndex": 0, "players": [
        {"active": [{"id": 999999, "hp": my_hp, "energies": []}]},
        {"active": [{"id": MEGA_LUCARIO, "hp": 340, "energies": [FIGHTING] * opp_energies}]},
    ]}}


BOARD = types.SimpleNamespace(race_ahead=-1.0, opp_prizes_remaining=3)


def _active_row(pilot, obs):
    _phase, rows = pilot._opponent_target_rows(obs, BOARD)
    return next(r for r in rows if r["area"] == "active")


@pytest.mark.req("REQ-STRIP-0001")
def test_the_delta_is_instantaneous_and_never_credits_next_turns_re_attach():
    """**The user's ruling of 2026-07-28.** A body on 2 Energy that loses one is priced on what it can
    do NOW: Mega Brave (270) drops to Aura Jab (130), which takes an extra turn to KO a 200-HP Active,
    so the strip buys a turn.

    Under the forward-looking reading (`base_attach: 1`) this was **0** — the curve handed the
    opponent a replacement Energy every turn, so the body was back to 2 by the time it attacked and
    the strip bought nothing. Gate 1 measured that as `m = 0.000` on four of the five frames the
    corpus rules PLAY, including `82525101-92`, which is this exact board. This test is the regression
    guard: it fails the moment `base_attach` goes back above 0."""
    assert _pilot()._DENY_CHARGED["base_attach"] == 0
    assert _active_row(_pilot(), _obs(2))["strip_shift"] >= 1


@pytest.mark.req("REQ-STRIP-0002")
def test_disarming_a_body_outright_saturates_rather_than_running_away():
    """The user's second point, and the correction to an earlier draft of this method. Stripping the
    last Energy leaves a body that cannot attack at all on the board as it stands, so its Δ runs to
    the horizon. That is **correct, not a runaway**:

      * a Hammer cannot take a body below zero Energy, so the value SATURATES — a bare body yields 0
        (tested below), it does not keep paying;
      * `needs._SURVIVAL_CAP` bounds the term regardless, so deny stays SUB-PRIZE and can never
        out-price a real prize outcome.

    An earlier draft replaced this with a one-step damage swing on the mistaken worry that the horizon
    Δ overstates the strip. The cap already contained it, and the corpus preferred this shape."""
    row = _active_row(_pilot(), _obs(1))
    assert row["strip_shift"] >= 1
    assert row["deny_value"] <= needs._SURVIVAL_CAP          # the cap contains the horizon
    # Disarming outright is worth at least as much as downgrading an attack — you cannot buy more
    # than "they do not attack", and you cannot buy it twice.
    assert row["deny_value"] >= _active_row(_pilot(), _obs(2))["deny_value"]


@pytest.mark.req("REQ-STRIP-0003")
def test_off_is_byte_identical_and_on_adds_only_new_keys():
    """The switch is COMPUTE-ONLY. OFF, the rows are exactly what #186 shipped; ON, every incumbent
    field is unchanged and only the two new keys appear. Nothing reads them yet — #187 is the
    consumer and is itself blocked on #199 — so ON can change no decision."""
    obs = _obs(2)
    off_phase, off_rows = _pilot(strip=False)._opponent_target_rows(obs, BOARD)
    on_phase, on_rows = _pilot(strip=True)._opponent_target_rows(obs, BOARD)

    assert off_phase == on_phase
    assert not any({"strip_shift", "deny_value"} & set(r) for r in off_rows)
    for off, on in zip(off_rows, on_rows):
        assert {"strip_shift", "deny_value"} <= set(on)
        for k in ("area", "bi", "id", "prize", "survival_shift", "value"):
            assert off[k] == on[k], k                     # the incumbent marginal is untouched


@pytest.mark.req("REQ-STRIP-0004")
def test_the_policy_is_load_bearing_not_a_refinement():
    """Design doc ruling 2 (per-consumer conservatism, never collapsed) with teeth. Under the CEILING
    policy the removal Δ uses, the strip Δ is identically 0 for every board — `incoming` checks a
    form's affordability against its CHEAPEST attack and then credits its BIGGEST regardless, so
    Energy count cannot move it. Only a charged policy prices the per-attack typed affordability a
    strip actually attacks."""
    p = _pilot()
    assert _active_row(p, _obs(1))["strip_shift"] >= 1    # ruled policy: the strip lands

    ma = {"id": 999999, "hp": 200}
    bodies = [{"id": MEGA_LUCARIO, "hp": 340, "energies": [FIGHTING]}]
    stripped = [{"id": MEGA_LUCARIO, "hp": 340, "energies": []}]
    ceiling = (p.combat.turns_to_ko_me(ma, stripped, opp_active=stripped[0])
               - p.combat.turns_to_ko_me(ma, bodies, opp_active=bodies[0]))
    assert ceiling == 0                                   # ceiling policy: the strip is invisible


@pytest.mark.req("REQ-STRIP-0005")
def test_a_bare_body_denies_nothing_and_the_caller_s_dict_is_never_mutated():
    """The saturation floor, and the no-leak guard. A body holding NO Energy yields 0 — you cannot
    hammer it to negative Energy, which is the second half of the ruling (*"only ... Pokémon with
    energy"*) arriving structurally rather than as a gate. And the Δ models the strip on a COPY (the
    S2 recur shadow's mechanism, inverted), so the observation the caller handed in is unchanged."""
    obs = _obs(0)
    before = [dict(p) for p in obs["current"]["players"][1]["active"]]
    row = _active_row(_pilot(), obs)
    assert row["strip_shift"] == 0 and row["deny_value"] == 0.0
    assert obs["current"]["players"][1]["active"] == before

    obs2 = _obs(2)
    _pilot()._opponent_target_rows(obs2, BOARD)
    assert obs2["current"]["players"][1]["active"][0]["energies"] == [FIGHTING, FIGHTING]


@pytest.mark.req("REQ-STRIP-0006")
def test_deny_uses_the_shared_two_term_form_and_stays_sub_prize():
    """What Amendment C bought back. Deny's Δ goes through `needs.opponent_target_value` — the SAME
    function gust and snipe read — so decision 1's one-backend claim holds rather than being weakened
    to "shares the currency but not the form". `prize_advance` is 0 (a strip takes no Prizes), so the
    marginal is the phase-scaled survival term alone and stays under `_SURVIVAL_CAP`, where the
    removal value of the same 3-prize body reaches 3.9."""
    row = _active_row(_pilot(), _obs(2))
    expected = needs.opponent_target_value(
        prize_advance=0.0, survival_shift=row["strip_shift"],
        phase=needs.phase_scale(race_ahead=BOARD.race_ahead,
                                opp_prizes_remaining=BOARD.opp_prizes_remaining))
    assert row["deny_value"] == pytest.approx(expected)
    assert row["deny_value"] <= needs._SURVIVAL_CAP
    assert row["deny_value"] <= row["value"]              # strip ≤ removal, same body
    assert row["prize"] == 3                              # Mega ex — and deny earns none of it
