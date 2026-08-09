"""Play-from-hand option resolution."""
from common.pilot import Pilot
from common.strategy import Strategy

_PLAY = 7


def test_play_from_hand_option_resolves_its_card_id():
    """A bare play hand index resolves to its card rather than disabling every play-side reader."""
    p = Pilot(Strategy(), deck=[])
    obs = {"current": {"yourIndex": 0, "players": [{"hand": [{"id": 111}, {"id": 1189}]}]}}
    assert p._option_card_id(obs, {}, {"index": 1, "type": _PLAY}) == 1189
    assert p._option_card_id(obs, {}, {"index": 0, "type": _PLAY}) == 111
    assert p._option_card_id(obs, {}, {"index": 9, "type": _PLAY}) is None
