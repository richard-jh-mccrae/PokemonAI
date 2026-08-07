"""Play-from-hand option resolution (the bug that disabled every roles/tags Hypothesis on plays) +
the win-condition development rule it unblocked (`prefer-rush-evolve-tutor`).

`evolve-into-wincon` was the module's other subject and is DELETED with the evolve-decider swap
(Issue #140, ADR-0070 §10) — its referent is the decider's deploy term, pinned at
`test_evolve_decider.py` (the algebra) and `test_evolve_value.py` (real frames)."""
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import Board, Context, Pilot
from common.strategy import Plan, Strategy

_PLAY, _ATTACH, _EVOLVE = 7, 8, 9
_rush = next(h for h in GENERAL_STRATEGY.hypotheses if h.id == "prefer-rush-evolve-tutor")


def test_play_from_hand_option_resolves_its_card_id():
    """REQ-PILOT-0022: a play option is a bare hand index with no `area` (`{"index":N,"type":7}`), so
    it resolves to `hand[N]`; otherwise card_id is None and every rung is silently dead on plays."""
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

def test_prefer_rush_evolve_tutor_fires_on_a_setup_rush_evolve_play():
    have_preevo = Board(line_preevo_in_play=True)                       # a pre-evolution to evolve
    assert bool(_rush.when(_ctx(tags=["rush_evolve"], board=have_preevo)))
    assert not _rush.when(_ctx(tags=["rush_evolve"],                    # payoff already online →
                               board=Board(line_preevo_in_play=True,    # stands down (ADR-0040
                                           line_ready=True)))           # migration: was plan==SETUP)
    assert not _rush.when(_ctx(tags=["search"], board=have_preevo))     # plain tutor, not rush_evolve
    assert not _rush.when(_ctx(tags=["rush_evolve"]))                   # no pre-evo in play -> stands down
    # payoff already in hand -> evolve directly; don't waste tutor (mirrors tutor-the-wincon's gate)
    assert not _rush.when(_ctx(tags=["rush_evolve"],
                               board=Board(line_preevo_in_play=True, wincon_in_hand=True)))
