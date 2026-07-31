"""Blunder round 2026-07-05 (mega_lucario, ep83661652 replays) — the develop-tiebreak fix.

The whole turn 5-7 cascade of ep83661652 has ONE root: `develop-a-basic-in-setup` (+12) is
INDIFFERENT among Basics, so which Basic got benched fell to `_finish_turn_last`'s option-index
tiebreak — the Pilot benched whichever Basic sat lowest in the menu (Solrock / Makuhita ahead of
Riolu by pure array position). The wincon Line base (Riolu → Mega Lucario ex) never got down, so the
deck 'played terribly' (feeding Meowth / just attacking / shuffling Riolu away).

`develop-the-wincon-base-first` (+6) gives the win-condition Line pre-evolution (`card_is_line_preevo`
— Riolu here, Staryu on Starmie, Dreepy on Dragapult; NEVER an off-line support Basic) a faint edge
so it leads the develop tiebreak (18 vs the other Basics' 12). Like the two 20260705 siblings this is
a `_finish_turn_last` sequencing THRESHOLD, not a ranking margin — the wincon base still scores BELOW
the turn-ending attack (tier 4), but rides tier 0, so it gates here on the real `explain()` rather
than via the W-route weight fit (which compares raw scores across tiers and is blind to it).
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
    """REQ-GEN-0072: on each captured ep83661652 state the shipped Pilot develops the board rather
    than feeding Meowth / attacking / shuffling Riolu away.

    Since ADR-0086 the pick is the Deploy Marginal's, not `develop-the-wincon-base-first` (+6,
    deleted), so the assertion moved from "which rung fired" to "which option was chosen" plus the
    priced leg behind it. Two rulings are honoured rather than re-litigated:

    * an ACCEPTED SET (`correct_alternatives`) — f33's rationale names both basics and bench drops
      COMMUTE (rulebook L120-122), so Solrock and Riolu are equally correct there;
    * a HELD-OUT frame (`claims.decision.owner`) — f44 is #165's, the Turn Planner's: the attach and
      the Supporter were already spent before this decision, so no per-option price can fix it."""
    fx = _fixture(name)
    held = ((fx.get("claims") or {}).get("decision") or {}).get("owner")
    if held:
        pytest.skip(f"held out to {held}: {((fx['claims']['decision']).get('why') or '')[:160]}")
    dec = _shipped_pilot().explain(fx["obs"])
    accepted = [list(a) for a in (fx.get("correct_alternatives") or [fx["correct"]])]
    assert dec.chosen in accepted, f"chose {dec.chosen}, accepted {accepted}"
    assert dec.options[dec.chosen[0]].deploy_working["total"] > 0   # the develop is PRICED, not tied


def test_offline_basic_does_not_get_the_wincon_edge():
    """REQ-GEN-0072: the wincon base's edge over an off-line Basic is REAL, not a tie broken by menu
    position — the failure mode this round was built to kill.

    `develop-the-wincon-base-first` (+6) is deleted, so the assertion is now on the equation: at f40
    Riolu (the Riolu → Mega Lucario ex pre-evolution) must out-price Solrock (an off-line engine base)
    on the Deploy Marginal itself. Asserting the deleted rung no longer fires would pass vacuously."""
    fx = _fixture("ml0703_develop_riolu_not_shuffle_f40")
    dec = _shipped_pilot().explain(fx["obs"])
    riolu, solrock = 3, 2                       # opt[3] = Play Riolu, opt[2] = Play Solrock
    assert (dec.options[riolu].deploy_working["total"]
            > dec.options[solrock].deploy_working["total"])
