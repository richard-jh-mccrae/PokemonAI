"""Horizon-2 lock oracle (ADR-0061) through the SHIPPED Pilot — real captured boards.

The follow-up arithmetic itself is pinned in test_lock_sequence.py against the printed card text;
these two pin that the Pilot reads the board when it applies it.
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
    """Mega Brave locks only ITSELF, so it forfeits the difference to the lock-free pick, discounted;
    neither charge is a constant — swap the Pokemon's other attack and both move."""
    pilot = _shipped_pilot()
    board, attacks = _attacks(pilot, _fx("ml_dont_wake_the_giant_with_the_locking_ko_f88.json"))
    assert not board.active_doomed                       # the follow-up is real here
    assert attacks[MEGA_BRAVE_DMG][1] == pytest.approx(0.5 * (MEGA_BRAVE_DMG - AURA_JAB_DMG))
    assert attacks[AURA_JAB_DMG][1] == 0                 # lock-free: nothing forfeited


def test_a_doomed_active_pays_no_cooldown_charge():
    pilot = _shipped_pilot()
    board, attacks = _attacks(pilot, _fx("ml_dont_judge_away_the_bigger_hand_f111.json"))
    assert board.active_doomed
    assert attacks[MEGA_BRAVE_DMG][1] == 0
