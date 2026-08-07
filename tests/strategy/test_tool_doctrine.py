"""The irreplaceable-Tool HOLD — what is left of the Tool Doctrine after POC-T4/5 (Issue #386).

ADR-0028's doctrine had two halves. The DEPLOY half — a +HP Tool (Hero's Cape, +100 HP, ACE SPEC)
placed proactively onto the body that carries the game, its target chosen by survival-turns
board-math (`ceil(hp / incoming)`) — was five tuned rungs in `doctrines/doctrine_tool.py`, and Issue
#386 deletes all five. The rungs were the whole module, so the module is gone; the audit note below
records where each fact went.

The HOLD half survives, and it is the reason this file does. `hold-irreplaceable-tool-dont-shuffle`
(−30) is not on the deletion list: it prices playing a hand-SHUFFLE card while an irreplaceable
one-of Tool sits in hand, which is a fact about a card leaving your hand rather than a preference
about where a Tool should go. Verified through the PUBLIC Pilot interface
(`explain(...).options[].fired`). See docs/adr/0028-tool-deploy-is-survival-turns-board-math.md.
"""
import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Line, Strategy
from pilot_helpers import (ACTIVE, ATTACH, BENCH, HAND, MAIN, PLAY, attack_opt, make_select, opt,
                           poke, state)

CAPE = 1159          # Hero's Cape - ACE SPEC Pokemon Tool, +100 HP
WINC = 1031          # win-condition payoff (a Mega ex)
STARYU = 1030        # win-condition's pre-evolution (a Line piece)
LILLIES = 1227       # hand-shuffle draw Supporter (shuffle hand into deck, draw) - `shuffle_hand`
OPENER = 900         # off-line opener body (not the win-condition) - bad Cape carrier
WALL = 901           # off-line wall (re-emerged Cinderace) - earns Cape only if it gains a turn
SNIPER = 8000        # opponent attacker that bench-snipes (Jetting-Blow-like: 120 + 50 snipe)
WEAKOPP = 8001       # opponent Active that barely hits (current attacker isn't the threat)
BIGOPP = 8002        # opponent BENCHED attacker that hits hard once promoted (the real threat)
FRAGILE = 8003       # low-HP opponent Active my attack KOs this turn (lethal-KO setup)
KO_SCORE = 1000      # option that knocks out scores >= this (common/strategy/context.py)
WATER = 3
FIRE = 2
LIGHTNING = 4
END = 14             # OptionType.END


def _line_strat():
    return Strategy(roles={WINC: ["win_condition", "primary_attacker"]},
                    lines=[Line(path=[STARYU, WINC], payoff=WINC)])


def _fired(option_trace):
    return {h.id for h, _ in option_trace.fired}


def _wincon_strat():
    return Strategy(roles={WINC: ["win_condition", "primary_attacker"]},
                    lines=[])


# The Tool Doctrine module was DELETED (Issue #386) along with its five rungs and ten tests; only
# the anti-shuffle belt below survives, which is why this file still exists.
@pytest.mark.req("REQ-GEN-0049")
def test_hold_irreplaceable_tool_dont_shuffle_with_no_good_target():
    """Holding the irreplaceable Cape with NO win-condition body to equip: the graded SHED (ADR-0065)
    prices the held ACE SPEC so the hand-shuffle refresh scores NEGATIVE and the agent holds."""
    stats = DictCardStatProvider({
        CAPE: CardStat(CAPE, synthetic=True, hp=0, aceSpec=True, hpBonus=100),
        LILLIES: CardStat(LILLIES, hp=0),
        OPENER: CardStat(OPENER, synthetic=True, hp=160),                        # off-line body (NOT the wincon)
    })
    funcs = CardFunctions({CAPE: ["tool"], LILLIES: ["draw", "shuffle_hand"], OPENER: ["opener"]})
    pilot = Pilot(_wincon_strat(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,
                      current=state(active=poke(OPENER, hp=160, energy=1), hand=[LILLIES, CAPE]))
    trace = pilot.explain(obs).options[0]                        # the Lillie's (shuffle) option
    assert trace.score < 0, f"held ACE SPEC must make the refresh reluctant, scored {trace.score:+.1f}"
    assert pilot.decide(obs) == [1]                              # hold (End), don't shuffle Cape away


@pytest.mark.req("REQ-GEN-0049")
def test_hold_irreplaceable_tool_silent_without_an_irreplaceable_tool():
    """No ACE SPEC Tool in hand -> nothing irreplaceable to protect -> the belt stays silent (the
    refresh is judged on its own merits)."""
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, synthetic=True, hp=0), OPENER: CardStat(OPENER, synthetic=True, hp=160)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"], OPENER: ["opener"]})
    pilot = Pilot(_wincon_strat(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,
                      current=state(active=poke(OPENER, hp=160, energy=1), hand=[LILLIES]))
    assert "hold-irreplaceable-tool-dont-shuffle" not in _fired(pilot.explain(obs).options[0])


