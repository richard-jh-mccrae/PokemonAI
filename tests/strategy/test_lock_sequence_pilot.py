"""Horizon-2 lock oracle (ADR-0061) through the SHIPPED Pilot — real captured boards.

The two lock branches, each on a real correction:

  ml f88   Active alive, Mega Brave (270, SAME-ATTACK lock) is a KO and Aura Jab (130, lock-free)
           is not. The lock charge is now DERIVED -- 0.5 x (270 - 130) = 70, the damage the lock
           actually forfeits next turn -- rather than the flat 40 that was charged whatever the
           Pokemon's other attack happened to be.

  ml f111  Active is `active_doomed`. There IS no next turn for it, so a cooldown costs nothing and
           we front-load: the lock charge collapses to 0. The flat 40 charged it anyway, docking a
           lethal Mega Brave for a flexibility it was never going to get to use.

The arithmetic of the follow-up itself is pinned in test_lock_sequence.py against the printed card
text; these two pin that the Pilot reads the board when it applies it.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

AURA_JAB_DMG, MEGA_BRAVE_DMG = 130, 270


def _shipped_pilot(agent="mega_lucario"):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot(agent)[0]


def _fx(name):
    return json.loads((REPO / "tests" / "fixtures" / "corrections" / name).read_text(encoding="utf-8"))


def _attacks(pilot, fx):
    """{damage: (option index, lock charge)} over the attack options on the captured menu."""
    board = pilot._board(fx["obs"], fx["obs"]["select"])
    out = {}
    for i, o in enumerate(fx["obs"]["select"]["option"]):
        aid = o.get("attackId")
        if aid:
            out[pilot._attack_stat(aid).damage] = (i, pilot._lock_sequence_cost(aid, board))
    return board, out


def test_a_same_attack_lock_is_charged_the_damage_it_actually_forfeits():
    """f88: Mega Brave locks only ITSELF, so next turn Aura Jab (130) remains. It forfeits the
    difference to a lock-free pick (270 - 130 = 140), discounted -> 70. Aura Jab locks nothing and is
    charged 0. Neither number is 40, and neither is a constant: swap the Pokemon's other attack and
    both move."""
    pilot = _shipped_pilot()
    board, attacks = _attacks(pilot, _fx("ml_dont_wake_the_giant_with_the_locking_ko_f88.json"))
    assert not board.active_doomed                       # the follow-up is real here
    assert attacks[MEGA_BRAVE_DMG][1] == pytest.approx(0.5 * (MEGA_BRAVE_DMG - AURA_JAB_DMG))
    assert attacks[AURA_JAB_DMG][1] == 0                 # lock-free: nothing forfeited


def test_a_doomed_active_pays_no_cooldown_charge():
    """f111: our Active dies to their next attack, so it will never USE the turn Mega Brave's lock
    takes away. Charging it is charging for a flexibility that does not exist -- front-load instead."""
    pilot = _shipped_pilot()
    board, attacks = _attacks(pilot, _fx("ml_dont_judge_away_the_bigger_hand_f111.json"))
    assert board.active_doomed
    assert attacks[MEGA_BRAVE_DMG][1] == 0


def test_the_locking_ko_is_still_declined_when_the_line_is_better():
    """The behavioural gate the charge exists to serve: f88's human correction is Aura Jab over the
    locking Mega Brave KO. Re-derived through the full shipped menu, not a hand-built probe."""
    fx = _fx("ml_dont_wake_the_giant_with_the_locking_ko_f88.json")
    chosen = _shipped_pilot().explain(fx["obs"]).chosen
    assert all(c in chosen for c in fx["correct"]), (
        f"chose {chosen}, want {fx['correct']} ({fx['correct_label']})")
