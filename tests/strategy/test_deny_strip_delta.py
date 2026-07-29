"""S3c — the deny instrument's STRIP delta (`Pilot._strip_delta_terms`, ADR-0077 / #199).

#186 built the opponent-target marginal's **removal** Δ: the turns of survival bought by a body
leaving the board. That is the gust / snipe question. A Crushing Hammer never asks it — it discards
ONE Energy and the body stays — so deny had no slice to read. These tests pin the Δ that gives it
one, the POLICY choice without which it is identically zero, and the two properties that make it safe
to compute (OFF by default, decides nothing).

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
def test_off_is_byte_identical_and_on_adds_only_new_keys():
    """The switch is COMPUTE-ONLY. OFF, the rows are exactly what #186 shipped; ON, every incumbent
    field is unchanged and only the two new keys appear. Nothing reads them yet — #187 is the
    consumer and is itself blocked on #199 — so ON can change no decision."""
    obs = _obs(1)
    off_phase, off_rows = _pilot(strip=False)._opponent_target_rows(obs, BOARD)
    on_phase, on_rows = _pilot(strip=True)._opponent_target_rows(obs, BOARD)

    assert off_phase == on_phase
    assert not any({"strip_shift", "deny_value"} & set(r) for r in off_rows)
    for off, on in zip(off_rows, on_rows):
        assert {"strip_shift", "deny_value"} <= set(on)
        for k in ("area", "bi", "id", "prize", "survival_shift", "value"):
            assert off[k] == on[k], k                     # the incumbent marginal is untouched


@pytest.mark.req("REQ-STRIP-0002")
def test_a_strip_that_turns_off_the_nuke_buys_a_survival_turn():
    """The case where a Hammer earns its keep. Mega Lucario ex on 1 Energy reaches Mega Brave (270)
    next turn off its one attach and one-shots a 200-HP Active; strip that Energy and one attach only
    reaches Aura Jab (130), which needs a second turn to accumulate the KO. So the strip buys a turn
    — a positive Δ, converted to prize-equivalents by the phase scale."""
    row = _active_row(_pilot(), _obs(1, my_hp=200))
    assert row["strip_shift"] == 1
    assert row["deny_value"] > 0.0


@pytest.mark.req("REQ-STRIP-0003")
def test_the_next_attach_cancels_a_strip_the_body_can_afford_to_lose():
    """The load-bearing surprise, and the reason #199's gate 1 is not a formality: the marginal is
    forward-looking, so it credits the opponent their one attach per turn (rules.md §3). A body on 2
    Energy that loses one is back to 2 by the time it attacks, so the strip buys NOTHING and the Δ is
    0 — even though ADR-0062's oracle prices exactly this case at 140 damage denied (270 → 130),
    because that oracle measures the strip INSTANTANEOUSLY and never credits the re-attach.

    Both readings are internally coherent; they answer different questions. Which one deny should be
    denominated in is what gate 1 measures, so this test pins the disagreement rather than papering
    over it. ADR-0062 already knew the re-attach was real — it is half the derivation of
    `_DENIAL_BENCH = 0.25` (*"they get a turn in between to simply re-attach"*)."""
    assert _active_row(_pilot(), _obs(2, my_hp=200))["strip_shift"] == 0


@pytest.mark.req("REQ-STRIP-0004")
def test_the_slow_policy_is_load_bearing_not_a_refinement():
    """Design doc ruling 2 (per-consumer conservatism, never collapsed) with teeth. Under the CEILING
    policy the removal Δ uses, the strip Δ is identically 0 for every board — `incoming` checks a
    form's affordability against its CHEAPEST attack and then credits its BIGGEST regardless, so
    Energy count cannot move it. Deny is fail-slow, not fail-scared, and only the charged read prices
    the per-attack typed affordability a strip actually attacks."""
    p = _pilot()
    obs = _obs(1, my_hp=200)
    assert _active_row(p, obs)["strip_shift"] == 1        # slow policy: the strip lands

    ma = {"id": 999999, "hp": 200}
    bodies = [{"id": MEGA_LUCARIO, "hp": 340, "energies": [FIGHTING]}]
    stripped = [{"id": MEGA_LUCARIO, "hp": 340, "energies": []}]
    ceiling = (p.combat.turns_to_ko_me(ma, stripped, opp_active=stripped[0])
               - p.combat.turns_to_ko_me(ma, bodies, opp_active=bodies[0]))
    assert ceiling == 0                                   # ceiling policy: the strip is invisible


@pytest.mark.req("REQ-STRIP-0005")
def test_a_bare_body_denies_nothing_and_the_caller_s_dict_is_never_mutated():
    """Two properties in one board. A body holding NO Energy yields 0 — the ADR-0062 whiff arriving
    structurally rather than as a separate gate. And the Δ models the strip on a COPY (the S2 recur
    shadow's mechanism, inverted), so the observation the caller handed in is unchanged afterwards —
    the guard that keeps a compute-only read from leaking into live state."""
    obs = _obs(0)
    before = [dict(p) for p in obs["current"]["players"][1]["active"]]
    row = _active_row(_pilot(), obs)
    assert row["strip_shift"] == 0 and row["deny_value"] == 0.0
    assert obs["current"]["players"][1]["active"] == before

    obs2 = _obs(2)
    _pilot()._opponent_target_rows(obs2, BOARD)
    assert obs2["current"]["players"][1]["active"][0]["energies"] == [FIGHTING, FIGHTING]


@pytest.mark.req("REQ-STRIP-0006")
def test_deny_is_pure_tempo_so_its_marginal_is_sub_prize_and_never_exceeds_removal():
    """ADR-0077 decision 1: `prize_advance` is 0 for deny because a strip takes no Prizes, so the
    marginal is bounded by `needs._SURVIVAL_CAP` (< 1 Prize) where the removal value of the same
    3-prize body reaches 3.9. That asymmetry is not a bug — it is what gate 1 exists to measure, and
    the reason deny cannot simply read gust's slice.

    A strip can also never buy more survival than removing the body outright, which is the ordering
    the two Δs must respect to live in one currency."""
    row = _active_row(_pilot(), _obs(1, my_hp=200))
    assert row["deny_value"] <= needs._SURVIVAL_CAP
    assert row["deny_value"] <= row["value"]              # strip ≤ removal, same body
    assert row["prize"] == 3                              # Mega ex — and deny earns none of it
