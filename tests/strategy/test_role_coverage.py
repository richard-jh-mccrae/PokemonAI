"""WP7 — role-coverage lint for the shipped agents (hypergeometric-fetch-closure §Round 9 §5, ADR-0065).

The Scouting-gate pattern applied to the worth oracle: NO card is silently priced at zero by a typo.
Every role string a deck DECLARES must resolve to a known vocabulary term — a `card_worth.ROLE_TIER`
WORTH tier or a documented BEHAVIOURAL role (gust / retreat_tool / … drive tag-rungs, not worth) —
and every declaration must key a real deck card. A misspelled ``win_condition`` would otherwise price
the wincon at 0 with no error; this test is that error.

The FULL Round-9 gate ("every deck.csv card resolves to a role, derived or declared") rides with the
Role-Sheet pipeline (deck-genie declares / the deriver derives — the WP7 skill-loop half, staged): most
Trainers/Energy are legitimately un-Roled today and priced by tag/CardStat rules, not the worth oracle.
This lint pins what is soundly checkable NOW: the declared vocabulary is well-formed and wired.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

AGENTS = ["mega_lucario", "mega_starmie", "dragapult_ex"]

# Behavioural (NON-worth) roles: they route tag/context rungs (the gust doctrine, retreat-tool
# selection, disruption/recovery/starter reads), NOT the worth oracle, so `role_value` prices them 0
# by design. Listed here so a NEW role string that is really a TYPO of a worth tier fails the lint.
BEHAVIOURAL_ROLES = frozenset({"gust", "retreat_tool", "disruption", "recovery", "starter"})


def _shipped_pilot(agent):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot(agent)[0]


@pytest.mark.req("REQ-WORTH-0003")
@pytest.mark.parametrize("agent", AGENTS)
def test_every_declared_role_is_known_vocabulary(agent):
    """No card silently priced at zero from a typo: every declared role (the compiled
    `pilot.strategy.roles`) is either a `card_worth.ROLE_TIER` worth tier or a documented behavioural
    role. Reads the roles through the built Pilot — NOT a bare ``import agents.<x>.strategy``, which
    collides with `kaggle_environments`' own top-level ``agents`` module in the CI env."""
    from common.card_worth import ROLE_TIER
    known = set(ROLE_TIER) | BEHAVIOURAL_ROLES
    roles_map = _shipped_pilot(agent).strategy.roles
    unknown = {r for roles in roles_map.values() for r in roles if r not in known}
    assert not unknown, f"{agent}: unknown role string(s) {sorted(unknown)} — a typo prices the card 0"


@pytest.mark.req("REQ-WORTH-0003")
@pytest.mark.parametrize("agent", AGENTS)
def test_every_roled_card_is_in_the_deck(agent):
    """A ROLES key that names no deck card is dead (or a stale id): the declaration prices nothing."""
    pilot = _shipped_pilot(agent)
    deck = set(pilot.deck)
    orphan = {cid for cid in pilot.strategy.roles if cid not in deck}
    assert not orphan, f"{agent}: ROLES declares non-deck card id(s) {sorted(orphan)}"


@pytest.mark.req("REQ-WORTH-0003")
@pytest.mark.parametrize("agent", AGENTS)
def test_every_worth_roled_card_prices_positive(agent):
    """The wiring holds end-to-end: every card that declares a WORTH role resolves to a positive
    `role_value` through the Pilot delegator — the worth oracle actually reaches the deck's plan pieces."""
    from common.card_worth import ROLE_TIER
    pilot = _shipped_pilot(agent)
    for cid, roles in pilot.strategy.roles.items():
        if any(r in ROLE_TIER for r in roles):
            assert pilot._role_value(cid) > 0, f"{agent}: card {cid} declares {roles} but prices 0"
