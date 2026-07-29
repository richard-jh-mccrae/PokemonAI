"""The DEPLOY decider's equation (`common/deploy_value.py`, ADR-0081 / Issue #197).

Pure arithmetic over resolved board facts — no engine, no obs, no Pilot — which is the seam the ADR
picked so the whole equation is testable with plain numbers. Prior art for the style:
`test_evolve_value.py` (ADR-0070) and `test_promote_retreat_value.py` (ADR-0073).

The property test that matters most here is `test_the_worth_legs_are_dimensionless`: the entire
currency argument of amendment B rests on the Worth points CANCELLING in a ratio, and a regression
that reintroduced a raw magnitude would be silent — the numbers would still look plausible. Nothing
else in the suite would catch it.
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
    """The floor matters as much as the ceiling: `_finish_turn_last` sequences an option above End
    only on a POSITIVE score, so a body that covers no need, fires no Ability, unlocks no Energy and
    hands the opponent nothing must land at exactly 0.0 rather than a small positive drift."""
    assert deploy_value(_inp()).total == 0.0


@pytest.mark.req("REQ-DEPLOY-0001")
def test_the_band_scales_only_the_worth_legs_and_never_the_damage_native_ones():
    """Amendment C's shape: the two Worth legs are dimensionless and enter through `DEPLOY_BAND`;
    the accel unlock and the exposure are ALREADY damage, so multiplying them by the band would
    price them twice in two different currencies."""
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
    """**The load-bearing property of amendment B.** The Worth legs are `marginal / DEPLOY_WORTH_SCALE`,
    so the Worth POINTS CANCEL — re-banding every tier by a constant factor must leave the deploy
    score untouched, because both the marginal and the yardstick move together.

    If someone later "simplifies" the ratio into a raw magnitude the numbers still look plausible and
    every other test still passes; this is the only thing that fails. That is why the yardstick is
    read from `currency` at call time rather than bound at import."""
    v1 = deploy_value(_inp(assignment_marginal=15.0, ability_marginal=6.0,
                           ability_odds=1.0, ability_can_fire=True))
    monkeypatch.setattr(currency, "DEPLOY_WORTH_SCALE", currency.DEPLOY_WORTH_SCALE * 7.0)
    v2 = deploy_value(_inp(assignment_marginal=15.0 * 7.0, ability_marginal=6.0 * 7.0,
                           ability_odds=1.0, ability_can_fire=True))
    assert v2.total == pytest.approx(v1.total)
    assert v2.assignment_relevance == pytest.approx(v1.assignment_relevance)


@pytest.mark.req("REQ-DEPLOY-0002")
def test_relevance_is_signed_unlike_denys_and_saturates_at_the_yardstick():
    """Deny's relevance is [0,1] because a strip is never actively bad. A DEPLOY can be: a body worth
    less than what it displaces is a mistake, and the equation has to be able to say so — that is how
    the optional-select take-fewer decline and the turn-ender floor come to refuse it.

    Magnitude still saturates at the yardstick, so one freakishly large marginal cannot swamp the
    damage-native legs or breach the positional band `_LINE_CAP` protects."""
    assert deploy_value(_inp(assignment_marginal=-currency.DEPLOY_WORTH_SCALE)).total < 0
    huge = deploy_value(_inp(assignment_marginal=currency.DEPLOY_WORTH_SCALE * 50))
    assert huge.assignment_relevance == pytest.approx(1.0)
    assert huge.total == pytest.approx(currency.DEPLOY_BAND)
    assert deploy_value(_inp(assignment_marginal=-currency.DEPLOY_WORTH_SCALE * 50)
                        ).assignment_relevance == pytest.approx(-1.0)


# ── the Ability leg: decision 3, the Meowth ex case ──────────────────────────────────────────────


@pytest.mark.req("REQ-DEPLOY-0003")
def test_the_ability_leg_is_zero_when_the_trigger_cannot_fire():
    """Decision 3's three zeroes, all DERIVED rather than vetoed: Set Up precedes the first turn so
    "once during your turn" is unsatisfiable; a second same-turn Last-Ditch is barred by the card's
    own text; and a body with no bench-drop Ability has nothing to fire. One flag carries all three
    because they are the same fact — the trigger cannot fire — and the Pilot owns deciding which."""
    assert deploy_value(_inp(ability_marginal=30.0, ability_odds=1.0,
                             ability_can_fire=False)).ability_relevance == 0.0


@pytest.mark.req("REQ-DEPLOY-0003")
def test_the_ability_leg_is_odds_weighted_so_a_probably_absent_supporter_is_not_a_promise():
    """A ranked consumer WEIGHTS by probability rather than gating on it (ADR-0074): benching a
    2-prize body to search for a Supporter already drawn or discarded should price near zero, not
    full."""
    full = deploy_value(_inp(ability_marginal=30.0, ability_odds=1.0, ability_can_fire=True))
    thin = deploy_value(_inp(ability_marginal=30.0, ability_odds=0.2, ability_can_fire=True))
    assert thin.ability_relevance == pytest.approx(full.ability_relevance * 0.2)


@pytest.mark.req("REQ-DEPLOY-0003")
def test_a_fetch_that_cannot_be_cashed_this_turn_takes_the_one_turn_discount():
    """One Supporter per turn (`rulebook.txt` L133), so a fetch made after the Supporter is spent
    banks for NEXT turn. This is the precision `board.no_supporter_in_hand` structurally cannot
    express — that signal is silenced by ANY Supporter in hand, which is why the agent can never dig
    for the SPECIFIC one it needs. Graded by the shared halving convention, not a fresh constant."""
    from common.grading import halve
    now = deploy_value(_inp(ability_marginal=30.0, ability_odds=1.0, ability_can_fire=True,
                            supporter_quota_spent=False))
    banked = deploy_value(_inp(ability_marginal=30.0, ability_odds=1.0, ability_can_fire=True,
                               supporter_quota_spent=True))
    assert banked.ability_relevance == pytest.approx(now.ability_relevance * halve(1))
    assert 0 < banked.ability_relevance < now.ability_relevance


@pytest.mark.req("REQ-DEPLOY-0003")
def test_a_needless_fetch_prices_at_zero_however_reachable_the_supporter():
    """"Only bench it when we need a SPECIFIC Supporter" as arithmetic: the leg is the marginal of the
    need the fetched Supporter fills, so a position whose draw/engine need is already met prices the
    drop at nothing no matter how certainly the deck holds one."""
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
    """ADR-0081 decision 8, and the leg's whole point: benching an Acceleration Recipient is worth
    the Energy the accelerator can now ACTUALLY place — not a flat bonus for being a line piece.

    The rider is Aura Jab ("attach up to 3 Basic {F} Energy from your discard pile to your Benched
    Pokémon"). With no Line member benched it fires blanks (`accel_recipient_missing`), so the
    counterfactual is exactly what the deploy buys: `_recover_units` on the board WITH the candidate
    benched. Priced at the shipped, DERIVED `ENERGY_RECOVER` (median damage-per-Energy over every
    attack costing >= 2, `160/3`) rather than a constant invented for this leg.

    Zero when the accelerator is not Active or a recipient already exists — the rule's hand-written
    stand-down conditions, now derived."""
    from common.strategy.context import ENERGY_RECOVER
    from tests.strategy._accel_fixture import accel_pilot, accel_obs   # noqa: F401

    pilot, obs, option = accel_pilot()
    board = pilot._board(obs, obs["select"])
    assert board.accel_recipient_missing is True
    riolu = pilot._option_card_id(obs, obs["select"], option)
    unlocked = pilot._deploy_accel_unlock(obs, board, riolu)
    assert unlocked > 0
    assert unlocked == pytest.approx(2 * ENERGY_RECOVER)     # Riolu->Mega Brave {F}{F}, 3 in discard


@pytest.mark.req("REQ-DEPLOY-0005")
def test_accel_unlock_is_zero_without_a_stranded_accelerator():
    """The two stand-downs the flat +20 rung wrote by hand, both derived here: no accelerator Active
    means nothing is stranded, and a recipient already benched means the Energy already lands."""
    from tests.strategy._accel_fixture import accel_pilot

    pilot, obs, option = accel_pilot(recipient_benched=True)
    board = pilot._board(obs, obs["select"])
    assert board.accel_recipient_missing is False
    assert pilot._deploy_accel_unlock(obs, board,
                                      pilot._option_card_id(obs, obs["select"], option)) == 0.0
