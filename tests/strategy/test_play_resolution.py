"""Play-from-hand option resolution (the bug that disabled every roles/tags Hypothesis on plays) +
the win-condition development rules it unblocked.

Both of those rules are now GONE with the evolve-decider swap (#140, ADR-0070 §10) and this module
keeps only the option-resolution claim it was named for. Where their referents went:
  * `evolve-into-wincon` -> the decider's deploy term (`test_evolve_decider.py` for the algebra,
    `test_evolve_value.py` for real frames).
  * `prefer-rush-evolve-tutor` -> `pilot._rush_evolve_tutor_tactical`, the same equation over the
    hypothetical result; its three premises survive there as structural gates. Pinned behaviourally
    at the Pilot seam (`test_blunder_20260629.py`'s Salvatore frames), which is the better seam for
    them than a predicate unit test."""
from common.pilot import Pilot
from common.strategy import Plan, Strategy

_PLAY, _ATTACH, _EVOLVE = 7, 8, 9


def test_play_from_hand_option_resolves_its_card_id():
    """REQ-PILOT-0022: a play option is a bare hand index with no `area` (`{"index":N,"type":7}`);
    it must resolve to `hand[N]` — otherwise card_id is None and every roles/tags/stat Hypothesis is
    silently dead on plays (why Salvatore was never played)."""
    p = Pilot(Strategy(), deck=[])
    obs = {"current": {"yourIndex": 0, "players": [{"hand": [{"id": 111}, {"id": 1189}]}]}}
    assert p._option_card_id(obs, {}, {"index": 1, "type": _PLAY}) == 1189
    assert p._option_card_id(obs, {}, {"index": 0, "type": _PLAY}) == 111
    assert p._option_card_id(obs, {}, {"index": 9, "type": _PLAY}) is None   # out of range -> None, no crash


def _ctx(**kw):
    base = dict(plan=Plan.SETUP, select_context=None, option_type=_PLAY, card_id=1,
                tags=[], roles=[], board=Board())
    base.update(kw)
    return Context(**base)
