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


# --- tracer: +HP Tool deploys proactively onto the Active win-condition --------------------------
# ── the Tool Doctrine — DELETED (POC-T4/5, Issue #386) ───────────────────────────────────────────
#
# `src/common/strategy/doctrines/doctrine_tool.py` is GONE — all five of its rungs are on Issue
# #386's list (`deploy-hp-tool` +40, `save-tool-for-the-attacker` −15,
# `equip-the-retreat-tool-on-the-active` +8, `hold-the-retreat-tool-with-no-retreat` −12,
# `protect-ace-spec-tool` −10), and those rungs WERE the module. Ten tests died with it, including
# the survival-turns target picker, because `_predicted_next_attacker` and the rest of ADR-0028's
# board-math helpers lived inside the deleted rungs and have no definition anywhere now.
#
# Two of the ten were already passing VACUOUSLY before deletion, and they are the reason this note
# is long. `test_no_deploy_onto_a_body_that_dies_even_with_the_boost` and
# `test_wall_does_not_get_the_cape_when_it_gains_no_turn` each asserted only
# `"deploy-hp-tool" not in _fired(...)`. Once the rung is deleted that is true of every board in the
# game, so both went green while checking nothing — and no failure count anywhere would ever have
# shown it. A negative assertion about a deleted mechanism is not a weakened test, it is dead text.
#
# WHERE THE FACTS WENT:
#
#   "a Tool goes on the body that carries the game" .... `deploy_value` (ADR-0086) prices a deploy,
#       and under differencing a Tool that buys a survival turn shows up as `survival` on the end
#       board rather than as a +40 endorsement. Corpus evidence: `test_tool_holder_facts.py`.
#   "a Cape deploy NEVER forgoes a lethal KO" .......... structural, and stronger than the rung was.
#       The win rung and the closed-form KO pool sit ABOVE the composer in `plan_turn`'s ladder
#       (Issue #386 §3), so a positional play cannot outrank a lethal by construction rather than by
#       weight. Asserted on real captured boards by `tests/strategy/test_lethal_recover.py` (four
#       frames, green) and on live engine drives by `test_lethal_engine.py`.
#   "don't shuffle away an irreplaceable Tool" ......... NOT deleted. `hold-irreplaceable-tool-dont-shuffle`
#       survives and its two tests remain below — which is why this file still exists.
# --- correction #1: deploy Cape BEFORE a hand-shuffle Supporter shuffles it away ------------------
# --- anti-shuffle belt: no good carrier -> HOLD Cape, don't shuffle it away -----------------------
@pytest.mark.req("REQ-GEN-0049")
def test_hold_irreplaceable_tool_dont_shuffle_with_no_good_target():
    """The belt for the case the positive deploy can't reach: holding the irreplaceable Cape with NO
    win-condition body to equip (only an off-line opener Active), a hand-shuffle Supporter would shuffle
    the ACE SPEC into the deck. The graded SHED (ADR-0065) prices the held ACE SPEC at its
    ACE_SPEC_TIER worth × how UN-recoverable it is (a one-per-deck, discard-irretrievable Tool ⇒ near
    its full worth), so the refresh scores NEGATIVE — the fold of the retired
    `hold-irreplaceable-tool-dont-shuffle` guard — and the agent holds the Cape (ends)."""
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


# --- correction #2: at-risk targeting picks body where +100 buys the MOST survival turns ----------
# --- Active doomed even at +100 -> redirect Cape to the promotable successor ----------------------
# --- wall (off-line body) earns Cape ONLY when +100 buys a real survival turn ----------------------
# --- predict-next-attacker: incoming sees opponent BENCHED promotion, not just current Active -----
# --- KO invariant: a positional Cape deploy never forgoes a knockout (corr 82756664-36) ------------
