"""Blunder round 2026-07-05 (mega_lucario) — the develop-tiebreak fix.

A develop rung indifferent among Basics left the pick to menu order, so the wincon Line base never
got benched. Since ADR-0086 the Deploy Marginal prices it, and these gate on the real `explain()`.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _shipped_pilot():
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot("mega_lucario")
    return pilot


def _fixture(name):
    p = REPO / "tests" / "fixtures" / "corrections" / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _fired_ids(option):
    return {h.id for h, _w in option.fired}


@pytest.mark.req("REQ-GEN-0072")
@pytest.mark.parametrize("name", [
    "ml0703_develop_riolu_over_solrock_f33",     # CRITICAL: don't feed Meowth / just attack — bench Riolu
    "ml0703_develop_riolu_not_shuffle_f40",      # CRITICAL: don't shuffle Riolu away with Lillie's — bench it
    "ml0703_develop_riolu_over_makuhita_f44",    # CRITICAL: stop resisting basics — bench the wincon base
])
def test_critical_develops_the_wincon_base_over_an_offline_basic(name):
    """Two rulings are honoured rather than re-litigated: an ACCEPTED SET (`correct_alternatives`),
    because bench drops COMMUTE (rulebook L120-122); and a HELD-OUT frame (`claims.decision.owner`)."""
    fx = _fixture(name)
    held = ((fx.get("claims") or {}).get("decision") or {}).get("owner")
    if held:
        pytest.skip(f"held out to {held}: {((fx['claims']['decision']).get('why') or '')[:160]}")
    dec = _shipped_pilot().explain(fx["obs"])
    accepted = [list(a) for a in (fx.get("correct_alternatives") or [fx["correct"]])]
    assert dec.chosen in accepted, f"chose {dec.chosen}, accepted {accepted}"
    assert dec.options[dec.chosen[0]].deploy_working["total"] > 0   # the develop is PRICED, not tied


def test_offline_basic_does_not_get_the_wincon_edge():
    """Asserted on the Deploy Marginal: `develop-the-wincon-base-first` is deleted, so asserting the
    rung no longer fires would pass vacuously."""
    fx = _fixture("ml0703_develop_riolu_not_shuffle_f40")
    dec = _shipped_pilot().explain(fx["obs"])
    riolu, solrock = 3, 2                       # opt[3] = Play Riolu, opt[2] = Play Solrock
    assert (dec.options[riolu].deploy_working["total"]
            > dec.options[solrock].deploy_working["total"])
