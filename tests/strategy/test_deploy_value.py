"""The DEPLOY decider's equation (`common/deploy_value.py`, ADR-0086 / Issue #197).

Pure arithmetic over resolved board facts — no engine, no obs, no Pilot. The load-bearing one is
`test_the_worth_legs_are_dimensionless`: amendment B's whole currency argument rests on the Worth
points CANCELLING in a ratio, and a regression to a raw magnitude would be silent everywhere else.
"""
from __future__ import annotations

import pytest

from common import currency
from common.deploy_value import DeployInputs, deploy_value


def _inp(**kw) -> DeployInputs:
    """A deploy that is worth exactly nothing, so each test moves ONE leg off zero."""
    base = dict(assignment_marginal=0.0, ability_marginal=0.0, ability_odds=0.0,
                ability_can_fire=False, supporter_quota_spent=False,
                accel_unlock=0.0, exposure_prizes=0.0, phase=1.0)
    base.update(kw)
    return DeployInputs(**base)


# ── composition ──────────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-DEPLOY-0001")
def test_a_deploy_that_buys_nothing_is_worth_nothing():
    """`_finish_turn_last` sequences above End only on a POSITIVE score, so this must be EXACTLY 0.0
    rather than a small positive drift."""
    assert deploy_value(_inp()).total == 0.0


@pytest.mark.req("REQ-DEPLOY-0001")
def test_the_band_scales_only_the_worth_legs_and_never_the_damage_native_ones():
    """The accel unlock and the exposure are ALREADY damage, so multiplying them by the band would
    price them twice in two different currencies (ADR-0086 amendment C)."""
    v = deploy_value(_inp(assignment_marginal=currency.DEPLOY_WORTH_SCALE,   # relevance 1.0
                          accel_unlock=40.0, exposure_prizes=0.0))
    assert v.assignment_relevance == pytest.approx(1.0)
    assert v.total == pytest.approx(currency.DEPLOY_BAND + 40.0)


@pytest.mark.req("REQ-DEPLOY-0001")
def test_exposure_is_prize_denominated_and_converts_through_the_prize_rate():
    """Decision 5: the exposure leg is a PRIZE-Path delta, so it crosses into the damage score through
    `PRIZE_DAMAGE_RATE` — the one legitimate prize->damage bridge — and never through the deploy band."""
    v = deploy_value(_inp(exposure_prizes=0.5, phase=1.0))
    assert v.exposure == pytest.approx(0.5 * currency.PRIZE_DAMAGE_RATE)
    assert v.total == pytest.approx(-0.5 * currency.PRIZE_DAMAGE_RATE)


@pytest.mark.req("REQ-DEPLOY-0001")
def test_exposure_is_phase_scaled_so_the_same_body_is_cheap_early_and_dear_late():
    """`needs.phase_scale` sharpens every prize-denominated term as the opponent nears their last
    Prize. A gift that costs little on turn 2 costs a great deal at 2 prizes left."""
    early = deploy_value(_inp(exposure_prizes=1.0, phase=0.3)).exposure
    late = deploy_value(_inp(exposure_prizes=1.0, phase=1.0)).exposure
    assert early == pytest.approx(0.3 * currency.PRIZE_DAMAGE_RATE)
    assert late > early


# ── the currency property the whole design rests on ──────────────────────────────────────────────


@pytest.mark.req("REQ-DEPLOY-0002")
def test_the_worth_legs_are_dimensionless(monkeypatch):
    """The Worth POINTS must CANCEL, so re-banding every tier by a constant factor leaves the score
    untouched. Simplify the ratio to a raw magnitude and only this test fails (ADR-0086 amendment B)."""
    v1 = deploy_value(_inp(assignment_marginal=15.0, ability_marginal=6.0,
                           ability_odds=1.0, ability_can_fire=True))
    monkeypatch.setattr(currency, "DEPLOY_WORTH_SCALE", currency.DEPLOY_WORTH_SCALE * 7.0)
    v2 = deploy_value(_inp(assignment_marginal=15.0 * 7.0, ability_marginal=6.0 * 7.0,
                           ability_odds=1.0, ability_can_fire=True))
    assert v2.total == pytest.approx(v1.total)
    assert v2.assignment_relevance == pytest.approx(v1.assignment_relevance)


@pytest.mark.req("REQ-DEPLOY-0002")
def test_relevance_is_signed_unlike_denys_and_saturates_at_the_yardstick():
    """A DEPLOY can be actively bad where a strip cannot, so relevance is SIGNED — that is how the
    take-fewer decline and the turn-ender floor come to refuse one. Magnitude still saturates."""
    assert deploy_value(_inp(assignment_marginal=-currency.DEPLOY_WORTH_SCALE)).total < 0
    huge = deploy_value(_inp(assignment_marginal=currency.DEPLOY_WORTH_SCALE * 50))
    assert huge.assignment_relevance == pytest.approx(1.0)
    assert huge.total == pytest.approx(currency.DEPLOY_BAND)
    assert deploy_value(_inp(assignment_marginal=-currency.DEPLOY_WORTH_SCALE * 50)
                        ).assignment_relevance == pytest.approx(-1.0)


# ── the Ability leg: decision 3, the Meowth ex case ──────────────────────────────────────────────


@pytest.mark.req("REQ-DEPLOY-0003")
def test_the_ability_leg_is_zero_when_the_trigger_cannot_fire():
    """ADR-0086 decision 3's three zeroes are the SAME fact — the trigger cannot fire — so one flag
    carries all three and the Pilot owns deciding which."""
    assert deploy_value(_inp(ability_marginal=30.0, ability_odds=1.0,
                             ability_can_fire=False)).ability_relevance == 0.0


@pytest.mark.req("REQ-DEPLOY-0003")
def test_the_ability_leg_is_odds_weighted_so_a_probably_absent_supporter_is_not_a_promise():
    """A ranked consumer WEIGHTS by probability rather than gating on it (ADR-0074)."""
    full = deploy_value(_inp(ability_marginal=30.0, ability_odds=1.0, ability_can_fire=True))
    thin = deploy_value(_inp(ability_marginal=30.0, ability_odds=0.2, ability_can_fire=True))
    assert thin.ability_relevance == pytest.approx(full.ability_relevance * 0.2)


@pytest.mark.req("REQ-DEPLOY-0003")
def test_a_fetch_that_cannot_be_cashed_this_turn_takes_the_one_turn_discount():
    """One Supporter per turn, so a fetch after the quota is spent banks for NEXT turn — a precision
    `board.no_supporter_in_hand` cannot express, since ANY Supporter in hand silences it."""
    from common.grading import halve
    now = deploy_value(_inp(ability_marginal=30.0, ability_odds=1.0, ability_can_fire=True,
                            supporter_quota_spent=False))
    banked = deploy_value(_inp(ability_marginal=30.0, ability_odds=1.0, ability_can_fire=True,
                               supporter_quota_spent=True))
    assert banked.ability_relevance == pytest.approx(now.ability_relevance * halve(1))
    assert 0 < banked.ability_relevance < now.ability_relevance


@pytest.mark.req("REQ-DEPLOY-0003")
def test_a_needless_fetch_prices_at_zero_however_reachable_the_supporter():
    """The leg is the marginal of the need the fetched Supporter fills, so a met need prices the drop
    at nothing however certainly the deck holds one."""
    assert deploy_value(_inp(ability_marginal=0.0, ability_odds=1.0,
                             ability_can_fire=True)).ability_relevance == 0.0


# ── the working breakdown ────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-DEPLOY-0004")
def test_the_result_reports_every_leg_so_a_disagreement_is_diagnosable():
    """The decider sweep prints the term breakdown on BOTH sides of a flip, and the Decision Gate is
    ruled by a human reading it — so a bare total would make the gate unrulable."""
    v = deploy_value(_inp(assignment_marginal=15.0, ability_marginal=6.0, ability_odds=0.5,
                          ability_can_fire=True, accel_unlock=12.0, exposure_prizes=0.25))
    assert set(v.working()) == {"assignment_relevance", "ability_relevance", "accel_unlock",
                                "exposure", "total"}
    assert v.working()["total"] == pytest.approx(v.total)
    assert v.total == pytest.approx(
        currency.DEPLOY_BAND * (v.assignment_relevance + v.ability_relevance)
        + v.accel_unlock - v.exposure)


# ── the accel-unlock leg (decision 8) — Pilot-side, so it needs a Pilot ──────────────────────────


@pytest.mark.req("REQ-DEPLOY-0005")
def test_accel_unlock_credits_the_energy_a_landing_spot_realises():
    """ADR-0086 decision 8: benching an Acceleration Recipient is worth the Energy the accelerator can
    now ACTUALLY place, priced at the derived `ENERGY_RECOVER` — not a flat bonus for being a piece."""
    from common.strategy.context import ENERGY_RECOVER
    from _accel_fixture import accel_pilot, accel_obs   # noqa: F401

    pilot, obs, option = accel_pilot()
    board = pilot._board(obs, obs["select"])
    assert board.accel_recipient_missing is True
    riolu = pilot._option_card_id(obs, obs["select"], option)
    unlocked = pilot._deploy_accel_unlock(obs, board, riolu)
    assert unlocked > 0
    # Exact shared build: two Fighting units complete Mega Brave's 270-damage, one-hop profile.
    assert unlocked == pytest.approx(135.0)


@pytest.mark.req("REQ-DEPLOY-0005")
def test_accel_unlock_is_zero_without_a_stranded_accelerator():
    """The two stand-downs the flat +20 rung wrote by hand, both derived here: no accelerator Active
    means nothing is stranded, and a recipient already benched means the Energy already lands."""
    from _accel_fixture import accel_pilot

    pilot, obs, option = accel_pilot(recipient_benched=True)
    board = pilot._board(obs, obs["select"])
    assert board.accel_recipient_missing is False
    assert pilot._deploy_accel_unlock(obs, board,
                                      pilot._option_card_id(obs, obs["select"], option)) == 0.0
