"""S3c — the deny instrument's STRIP delta (`Pilot._strip_delta_terms`, ADR-0077 / #199).

#186 built the opponent-target marginal's **removal** Δ: the turns of survival bought by a body
leaving the board. That is the gust / snipe question. A Crushing Hammer never asks it — it discards
ONE Energy and the body stays — so deny had no slice to read.

The Δ that gives it one carries the **user's ruling of 2026-07-28** (ADR-0077 Amendment B): *"deny
shall not calculate energy re-attached on a following turn. It shall only ever perform a calculation
on opponent's Pokémon with energy during our own turn."* So it is a ONE-STEP damage swing against the
board as it stands, converted to prize-equivalents by `PRIZE_DAMAGE_RATE` — not a `turns_to_ko_me`
projection. The first test is the payoff: it reproduces ADR-0062's own worked table exactly.

Card facts verified at source (`data/EN_Card_Data.csv`): Mega Lucario ex (678) attacks are Aura Jab
`{F}` 130 and Mega Brave `{F}{F}` 270; Basic `{F}` Energy is card id 6. Energy entries in an
observation are card ids, not dicts — the charged affordability path reads their types.
"""
from __future__ import annotations

import types

import pytest

from common.currency import PRIZE_DAMAGE_RATE

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
@pytest.mark.parametrize("energy, denies", [(1, 130), (2, 140), (3, 0), (4, 0)])
def test_the_delta_reproduces_adr_0062s_worked_table(energy, denies):
    """The validation that the user's ruling is the right shape. ADR-0062 worked Mega Lucario ex out
    by hand and published the table:

        their Energy | best now | after the strip | denies
                   1 |      130 |               0 |    130   — the attacker goes off
                   2 |      270 |             130 |    140   — the nuke goes off
                   3 |      270 |             270 |      0   — SURPLUS, the Hammer is wasted

    The shared marginal now returns exactly those numbers, in prize-equivalents. The surplus row is
    the ADR-0062 whiff arriving structurally — no separate gate asserts it."""
    row = _active_row(_pilot(), _obs(energy))
    assert row["strip_damage"] == denies
    assert row["deny_value"] == pytest.approx(denies / PRIZE_DAMAGE_RATE)


@pytest.mark.req("REQ-STRIP-0002")
def test_off_is_byte_identical_and_on_adds_only_new_keys():
    """The switch is COMPUTE-ONLY. OFF, the rows are exactly what #186 shipped; ON, every incumbent
    field is unchanged and only the two new keys appear. Nothing reads them yet — #187 is the
    consumer and is itself blocked on #199 — so ON can change no decision."""
    obs = _obs(2)
    off_phase, off_rows = _pilot(strip=False)._opponent_target_rows(obs, BOARD)
    on_phase, on_rows = _pilot(strip=True)._opponent_target_rows(obs, BOARD)

    assert off_phase == on_phase
    assert not any({"strip_damage", "deny_value"} & set(r) for r in off_rows)
    for off, on in zip(off_rows, on_rows):
        assert {"strip_damage", "deny_value"} <= set(on)
        for k in ("area", "bi", "id", "prize", "survival_shift", "value"):
            assert off[k] == on[k], k                     # the incumbent marginal is untouched


@pytest.mark.req("REQ-STRIP-0003")
def test_the_delta_is_instantaneous_and_never_credits_next_turns_re_attach():
    """**The user's ruling of 2026-07-28**, and the fix for gate 1's first failure. A body on 2 Energy
    that loses one is priced at what it loses NOW (270 → 130 = 140).

    Under the forward-looking reading this was **0**: the curve handed the opponent a replacement
    Energy every turn, so the body was back to 2 by the time it attacked and the strip bought nothing.
    That reading is what gate 1 measured as broken — `m = 0.000` on four of the five frames the corpus
    rules PLAY, including `82525101-92`, which is this exact board. This test is the regression guard
    for the ruling: it fails the moment `base_attach` goes back above 0."""
    assert _pilot()._DENY_CHARGED["base_attach"] == 0
    assert _active_row(_pilot(), _obs(2))["strip_damage"] == 140


@pytest.mark.req("REQ-STRIP-0004")
def test_the_delta_is_a_snapshot_not_a_multi_turn_projection():
    """The other half of the ruling — *"only ever perform a calculation on opponent's Pokémon with
    energy during our own turn"* — and the trap found while implementing it.

    Differencing `turns_to_ko_me` (the shape the REMOVAL Δ uses) with no attaches modelled reports a
    fully-stripped body as never attacking again — Δ = the whole horizon, wildly overstating a strip
    the opponent simply re-attaches past. That is a multi-turn projection wearing a snapshot's
    clothes. The shipped Δ is a one-step `incoming(t=1)` difference instead, so a strip is never worth
    more than the damage it actually takes off the board this turn."""
    row = _active_row(_pilot(), _obs(1))
    assert row["strip_damage"] == 130                    # Aura Jab, the whole of what it can do now
    ma = {"id": 999999, "hp": 200}
    bodies = [{"id": MEGA_LUCARIO, "hp": 340, "energies": [FIGHTING]}]
    ceiling_damage = _pilot().combat.incoming(ma, bodies, 1, opp_active=bodies[0])
    assert row["strip_damage"] <= ceiling_damage         # never more than the board's own reach


@pytest.mark.req("REQ-STRIP-0005")
def test_a_bare_body_denies_nothing_and_the_caller_s_dict_is_never_mutated():
    """Two properties in one board. A body holding NO Energy yields 0 — there is nothing to strip,
    which is the second half of the ruling (*"only ... Pokémon with energy"*) arriving structurally.
    And the Δ models the strip on a COPY (the S2 recur shadow's mechanism, inverted), so the
    observation the caller handed in is unchanged afterwards — the guard that keeps a compute-only
    read from leaking into live state."""
    obs = _obs(0)
    before = [dict(p) for p in obs["current"]["players"][1]["active"]]
    row = _active_row(_pilot(), obs)
    assert row["strip_damage"] == 0 and row["deny_value"] == 0.0
    assert obs["current"]["players"][1]["active"] == before

    obs2 = _obs(2)
    _pilot()._opponent_target_rows(obs2, BOARD)
    assert obs2["current"]["players"][1]["active"][0]["energies"] == [FIGHTING, FIGHTING]


@pytest.mark.req("REQ-STRIP-0006")
def test_deny_shares_the_currency_but_not_the_two_term_form():
    """ADR-0077 Amendment B's honest cost. Deny's Δ is denominated in prize-equivalents like every
    other instrument's — that is what lets one exchange rate serve them all — but it is a DAMAGE
    quantity divided by `PRIZE_DAMAGE_RATE`, not `prize_advance + phase × survival_shift`. The ruling
    buys correctness on deny's own question at the price of the shared two-term form, and that
    trade-off should be visible in a test rather than buried in a docstring.

    `prize_advance` is 0 either way: a strip takes no Prizes."""
    row = _active_row(_pilot(), _obs(2))
    assert row["deny_value"] * PRIZE_DAMAGE_RATE == pytest.approx(row["strip_damage"])
    assert row["prize"] == 3                             # Mega ex — and deny earns none of it
    assert row["deny_value"] != row["value"]             # a different question from removal
