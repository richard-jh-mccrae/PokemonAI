"""Prize-economy FETCH term (ADR-0048) — develop the cheap 1-prize attacker line over a redundant
high-prize line once the multi-prize win-condition is in play.

`develop-the-cheap-prize-wall-line` (+3, doctrine_fetch) is a small POSITIVE tie-break, enabled by
broadening line recognition: a secondary-attacker `Line` (role="secondary_attacker") is recognized so its
base (Makuhita) earns the same `prefer-wincon-line-piece` +18 as the wincon base (Riolu), then the tie-break
tips the cheaper-forward one. It fires only when the wincon base is REDUNDANT (already deployable, so
`fetch-base-before-stranded-payoff` stands down) — when a base is genuinely NEEDED it defers, and it is
inert with the kill-switch off / for decks without a secondary Line (behavior-neutral, ADR-0034).

Card facts (engine ground truth): mega_lucario runs Riolu(677)→Mega Lucario ex(678, 3-prize) and the
secondary Makuhita(673)→Hariyama(674, 1-prize) line.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

RIOLU, MEGA, MAKUHITA, HARIYAMA, OPP_BASIC = 677, 678, 673, 674, 379


def _pilot(deck="mega_lucario"):
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot(deck)[0]


def _fetch_obs(riolu_in_hand: bool):
    """Mega Lucario ex online; a _TO_HAND search offering a 2nd Riolu vs a Makuhita. A Riolu in hand makes
    the wincon base already deployable (the 2nd Riolu redundant)."""
    hand = [{"id": RIOLU}] if riolu_in_hand else []
    me = {"active": [{"id": MEGA, "energies": [6, 6], "hp": 340, "maxHp": 340}],
          "bench": [], "hand": hand, "discard": [], "prize": [None] * 6}
    opp = {"active": [{"id": OPP_BASIC, "energies": [], "hp": 80, "maxHp": 80}],
           "bench": [], "discard": [], "prize": [None] * 6}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": 6},
            "select": {"context": 7, "deck": [{"id": RIOLU, "playerIndex": 0}, {"id": MAKUHITA, "playerIndex": 0}],
                       "option": [{"area": 1, "index": 0, "type": 3, "playerIndex": 0},
                                  {"area": 1, "index": 1, "type": 3, "playerIndex": 0}],
                       "minCount": 0, "maxCount": 1}, "logs": []}


def _fired(option):
    return {h.id for h, _w in option.fired}






@pytest.mark.req("REQ-GEN-0075")
def test_kill_switch_off_is_inert_the_secondary_line_is_not_recognized():
    """With the ADR-0048 kill-switch off, `_recognized_line_preevo_set` narrows to the win-condition line,
    so the secondary Makuhita earns NO line-piece credit and the tie-break never fires."""
    p = _pilot()
    p.prize_economy_fetch = False
    dec = p.explain(_fetch_obs(riolu_in_hand=True))
    assert "develop-the-cheap-prize-wall-line" not in _fired(dec.options[1])
    assert "prefer-wincon-line-piece" not in _fired(dec.options[1])
    assert dec.chosen == [0]                                   # reverts to preferring the wincon base


@pytest.mark.req("REQ-GEN-0075")
@pytest.mark.parametrize("deck", ["mega_starmie", "dragapult_ex"])
def test_neutral_for_decks_without_a_secondary_attacker_line(deck):
    """A deck that declares only win-condition Lines has recognized == narrow line-preevo set, so the
    broadening and the tie-break are wholly inert (Score-Diff-neutral, ADR-0034)."""
    p = _pilot(deck)
    assert p._recognized_line_preevo_set() == p._line_preevo_set()
