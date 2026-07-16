"""The executable Tier Map (``src/common/tiers.py``): every runtime kill-switch is placed on
exactly one tier, and ``resolve`` reports the deployed enabled/disabled state — the contract the
Agent Brief renders."""
import pytest

from common import tiers
from common.runtime import PROFILE


@pytest.mark.req("REQ-TIERS-0001")
def test_every_profile_flag_is_placed_on_exactly_one_tier_node():
    """The drift guard: no shipped kill-switch may be missing from the map (else the Brief would
    silently omit a capability), and the map may not reference a non-existent switch."""
    owner = tiers.flag_owner()                       # raises if any flag is double-claimed
    missing = set(PROFILE) - set(owner)
    assert not missing, f"PROFILE flags absent from the tier map: {sorted(missing)}"
    stray = set(owner) - set(PROFILE)
    assert not stray, f"tier map references non-PROFILE flags: {sorted(stray)}"


@pytest.mark.req("REQ-TIERS-0002")
def test_resolve_reflects_the_default_deployment_profile():
    by_id = {t["id"]: t for t in tiers.resolve(tiers.effective_flags({}, PROFILE))}
    assert by_id["T0"]["state"] == "on"              # structural — the always-on fallback
    assert by_id["T5"]["state"] == "off"             # value_model ships gated off (ADR-0042)


@pytest.mark.req("REQ-TIERS-0002")
def test_a_deck_param_override_flips_its_tier_state():
    on = {t["id"]: t for t in tiers.resolve(tiers.effective_flags({"value_model": True}, PROFILE))}
    assert on["T5"]["state"] == "on"                 # a deck that arms the gate flips T5 enabled
    off = {t["id"]: t for t in tiers.resolve(tiers.effective_flags({"objectives_race": False}, PROFILE))}
    t3_sub = {s["id"]: s for s in off["T3"]["sub"]}
    assert t3_sub["T3.2"]["state"] == "off"          # forcing a sub-tier's switch off shows it off


@pytest.mark.req("REQ-TIERS-0002")
def test_unbuilt_subtiers_report_unbuilt_not_a_toggle():
    by_id = {t["id"]: t for t in tiers.resolve(tiers.effective_flags({}, PROFILE))}
    t4_sub = {s["id"]: s for s in by_id["T4"]["sub"]}
    assert t4_sub["T4.4"]["state"] == "unbuilt"      # Learned Matchup Weights — grilled, unbuilt
    t6_sub = {s["id"]: s for s in by_id["T6"]["sub"]}
    assert t6_sub["T6.2"]["state"] == "unbuilt"      # Sampled-Belief Search — unbuilt (research)


@pytest.mark.req("REQ-TIERS-0001")
def test_search_budget_is_a_budget_switch_on_only_when_positive():
    off = {t["id"]: t for t in tiers.resolve(tiers.effective_flags({}, PROFILE))}
    assert {s["id"]: s for s in off["T6"]["sub"]}["T6.1"]["state"] == "off"   # budget 0, escalation off
    on = tiers.effective_flags({"escalation": True, "search_budget": 2}, PROFILE)
    on_sub = {s["id"]: s for s in {t["id"]: t for t in tiers.resolve(on)}["T6"]["sub"]}
    assert on_sub["T6.1"]["state"] == "on"           # escalation on AND budget>0
