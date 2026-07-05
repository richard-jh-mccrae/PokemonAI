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
    """REQ-GEN-0072: on each captured ep83661652 state the shipped Pilot benches Riolu — the wincon
    Line pre-evolution — rather than an off-line support Basic (Solrock / Makuhita) or the chip attack.
    The develop rides tier 0 (ahead of the tier-4 attack) and `develop-the-wincon-base-first` breaks
    the develop tie toward the wincon base."""
    fx = _fixture(name)
    dec = _shipped_pilot().explain(fx["obs"])
    assert dec.chosen == fx["correct"]                          # Play Riolu
    riolu = fx["correct"][0]
    assert "develop-the-wincon-base-first" in _fired_ids(dec.options[riolu])


def test_offline_basic_does_not_get_the_wincon_edge():
    """REQ-GEN-0072: the boost fires ONLY on the Line pre-evolution — an off-line Basic (Solrock at
    f40) still scores at the bare `develop-a-basic-in-setup` +12, so it is Riolu's edge, not a blanket
    develop bump."""
    fx = _fixture("ml0703_develop_riolu_not_shuffle_f40")
    dec = _shipped_pilot().explain(fx["obs"])
    solrock = 2                                                 # opt[2] = Play Solrock (off-line engine base)
    assert "develop-the-wincon-base-first" not in _fired_ids(dec.options[solrock])
