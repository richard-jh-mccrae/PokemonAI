"""Scouting recognition scorer: presence-only Naive Bayes posterior (docs/scouting.md)."""
import pytest

from common.scouting.scorer import posterior

# Card ids from the Mega Lucario ex demo; opponents are illustrative.
SOLROCK, RIOLU, MEGA_LUCARIO = 676, 677, 678
KIRLIA, GARDEVOIR = 100, 101


@pytest.mark.req("REQ-SCOUT-0001")
def test_signature_card_spikes_its_archetype():
    # Solrock is near-exclusive to Mega Lucario ex; seeing it settles the read.
    priors = {"Mega Lucario ex": 0.5, "Gardevoir ex": 0.5}
    card_inclusion = {
        "Mega Lucario ex": {SOLROCK: 0.95, MEGA_LUCARIO: 1.0},
        "Gardevoir ex": {GARDEVOIR: 1.0, KIRLIA: 0.9},
    }
    background = {SOLROCK: 0.05, MEGA_LUCARIO: 0.05, GARDEVOIR: 0.05, KIRLIA: 0.05}

    candidates, unknown_mass = posterior(priors, card_inclusion, background, {SOLROCK})

    assert candidates[0][0] == "Mega Lucario ex"
    assert candidates[0][1] > 0.8


@pytest.mark.req("REQ-SCOUT-0003")
def test_unrecognized_cards_raise_unknown_mass():
    # A common card belonging to no tracked archetype should look "off-meta".
    priors = {"Mega Lucario ex": 0.5, "Gardevoir ex": 0.5}
    card_inclusion = {"Mega Lucario ex": {SOLROCK: 0.95}, "Gardevoir ex": {GARDEVOIR: 1.0}}
    ROGUE = 9999
    background = {ROGUE: 0.5}

    candidates, unknown_mass = posterior(priors, card_inclusion, background, {ROGUE})

    assert unknown_mass > candidates[0][1]


@pytest.mark.req("REQ-SCOUT-0002")
def test_corroborating_evidence_sharpens_posterior():
    # Seeing more of an archetype's cards only increases its posterior.
    priors = {"Mega Lucario ex": 0.5, "Gardevoir ex": 0.5}
    card_inclusion = {
        "Mega Lucario ex": {SOLROCK: 0.6, MEGA_LUCARIO: 0.9, RIOLU: 0.9},
        "Gardevoir ex": {SOLROCK: 0.3, GARDEVOIR: 1.0},
    }
    background = {SOLROCK: 0.2, MEGA_LUCARIO: 0.05, RIOLU: 0.1, GARDEVOIR: 0.05}

    one, _ = posterior(priors, card_inclusion, background, {SOLROCK})
    many, _ = posterior(priors, card_inclusion, background, {SOLROCK, MEGA_LUCARIO, RIOLU})

    assert dict(many)["Mega Lucario ex"] > dict(one)["Mega Lucario ex"]
