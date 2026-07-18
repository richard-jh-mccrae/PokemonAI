"""Tool Doctrine (ADR-0028): a Pokémon Tool equips at an ATTACH select. A +HP Tool (Hero's Cape,
+100 HP, ACE SPEC, irreplaceable) is deployed PROACTIVELY onto the body that carries the game — not
held for a breakpoint — because a deck that shuffles its own hand (Lillie's / Harlequin) would
otherwise shuffle the one-of ACE SPEC back into the deck. The target is chosen by survival-turns
board-math (`ceil(hp / incoming)`; the boost earns its slot when it adds a full turn) with the
win-condition always taking priority. Verified through the PUBLIC Pilot interface (`decide` /
`explain(...).fired`). See docs/adr/0028-tool-deploy-is-survival-turns-board-math.md.
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
@pytest.mark.req("REQ-GEN-0048")
def test_deploy_hp_tool_fires_onto_the_active_wincon():
    """A +HP Tool (Hero's Cape) in hand and the Active IS the win-condition: attaching it onto the
    Active is positively endorsed (`deploy-hp-tool`), so the equip can beat a draw Supporter in the
    develop phase. Proactive by default — no incoming threat is required (ADR-0028)."""
    stats = DictCardStatProvider({
        CAPE: CardStat(CAPE, hp=0, aceSpec=True, hpBonus=100),
        WINC: CardStat(WINC, megaEx=True, hp=330, weakness=LIGHTNING, evolvesFrom="Staryu"),
    })
    funcs = CardFunctions({CAPE: ["tool"]})
    pilot = Pilot(_wincon_strat(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
    # ATTACH Cape (hand idx 0) onto my Active win-condition (inPlay ACTIVE / 0). No opponent set
    # -> no incoming threat; deploy must still fire (proactive default).
    obs = make_select([opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)],
                      context=MAIN, current=state(active=poke(WINC, hp=330, energy=1), hand=[CAPE]))
    trace = pilot.explain(obs).options[0]
    assert "deploy-hp-tool" in _fired(trace)
    assert trace.score > 0


# --- correction #1: deploy Cape BEFORE a hand-shuffle Supporter shuffles it away ------------------
@pytest.mark.req("REQ-GEN-0048")
def test_deploy_beats_a_hand_shuffle_supporter():
    """ep82866415 f43: holding the Cape, the agent must attach it onto the Active win-condition BEFORE
    playing a hand-shuffle draw Supporter (Lillie's) that would shuffle the irreplaceable ACE SPEC into
    the deck. The positive deploy lands in tier-2 (attach) and outranks the tier-3 shuffle, so `decide`
    equips the Cape — the bug, fixed (the old protect-weights left it at ≤0, below the shuffle)."""
    stats = DictCardStatProvider({
        CAPE: CardStat(CAPE, hp=0, aceSpec=True, hpBonus=100),
        WINC: CardStat(WINC, megaEx=True, hp=330, weakness=LIGHTNING, evolvesFrom="Staryu"),
        LILLIES: CardStat(LILLIES, hp=0),
    })
    funcs = CardFunctions({CAPE: ["tool"], LILLIES: ["draw", "shuffle_hand"]})
    pilot = Pilot(_wincon_strat(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
    # play Lillie's (idx 0) OR attach Cape onto Active wincon (hand idx 1) OR End.
    obs = make_select(
        [opt(PLAY, index=0), opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0), opt(END)],
        context=MAIN, current=state(active=poke(WINC, hp=330, energy=1), hand=[LILLIES, CAPE]))
    assert pilot.decide(obs) == [1]                               # attach Cape, don't shuffle it away


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
        CAPE: CardStat(CAPE, hp=0, aceSpec=True, hpBonus=100),
        LILLIES: CardStat(LILLIES, hp=0),
        OPENER: CardStat(OPENER, hp=160),                        # off-line body (NOT the wincon)
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
    stats = DictCardStatProvider({LILLIES: CardStat(LILLIES, hp=0), OPENER: CardStat(OPENER, hp=160)})
    funcs = CardFunctions({LILLIES: ["draw", "shuffle_hand"], OPENER: ["opener"]})
    pilot = Pilot(_wincon_strat(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
    obs = make_select([opt(PLAY, index=0), opt(END)], context=MAIN,
                      current=state(active=poke(OPENER, hp=160, energy=1), hand=[LILLIES]))
    assert "hold-irreplaceable-tool-dont-shuffle" not in _fired(pilot.explain(obs).options[0])


# --- correction #2: at-risk targeting picks body where +100 buys the MOST survival turns ----------
@pytest.mark.req("REQ-GEN-0050")
def test_at_risk_deploy_prefers_the_higher_gain_bench_line_piece():
    """ep82866415 f48 (corr #2): the Cape goes onto the body where +100 buys the MOST survival turns.
    The Active wincon (330 HP vs 120 incoming) gains 1 turn; a benched Staryu line-piece (70 HP vs a
    50 bench-snipe) gains 2 — so the picker equips the BENCH Staryu (it rides up the line on evolve).
    Both are wincon-related bodies, so 'wincon priority' is intact (a wall would only get it if no
    wincon body wanted it)."""
    stats = DictCardStatProvider({
        CAPE: CardStat(CAPE, hp=0, aceSpec=True, hpBonus=100),
        WINC: CardStat(WINC, megaEx=True, hp=330, weakness=LIGHTNING, energyType=WATER, evolvesFrom="Staryu"),
        STARYU: CardStat(STARYU, hp=70, weakness=LIGHTNING, energyType=WATER),
        SNIPER: CardStat(SNIPER, energyType=WATER, maxDamage=120, benchSnipeDamage=50),
    })
    funcs = CardFunctions({CAPE: ["tool"]})
    pilot = Pilot(_line_strat(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
    # ATTACH Cape onto Active wincon (opt 0) OR onto benched Staryu line-piece (opt 1).
    obs = make_select(
        [opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0),
         opt(ATTACH, area=HAND, index=0, inPlayArea=BENCH, inPlayIndex=0)],
        context=MAIN, current=state(active=poke(WINC, hp=330, energy=1),
                                    bench=[poke(STARYU, hp=70, energy=1)],
                                    opp_active=poke(SNIPER, energy=1, hp=330), hand=[CAPE]))
    opts = pilot.explain(obs).options
    assert "deploy-hp-tool" in _fired(opts[1])           # BENCH Staryu - gains most turns
    assert "deploy-hp-tool" not in _fired(opts[0])       # not the Active (gains fewer)
    assert pilot.decide(obs) == [1]


@pytest.mark.req("REQ-GEN-0050")
def test_picker_handles_a_zero_gain_bench_line_piece_without_crashing():
    """Regression (the tuple-vs-None comparison crash): a benched wincon line-piece with NO incoming
    (gain 0 — the common real-game shape: a benched Staryu, no opponent snipe) must not crash the
    picker. It falls through to the proactive default (the active win-condition)."""
    stats = DictCardStatProvider({
        CAPE: CardStat(CAPE, hp=0, aceSpec=True, hpBonus=100),
        WINC: CardStat(WINC, megaEx=True, hp=330, weakness=LIGHTNING, energyType=WATER, evolvesFrom="Staryu"),
        STARYU: CardStat(STARYU, hp=70, weakness=LIGHTNING, energyType=WATER),
    })
    funcs = CardFunctions({CAPE: ["tool"]})
    pilot = Pilot(_line_strat(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
    obs = make_select(                                       # no opp_active -> all incoming 0 -> gain 0
        [opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0),
         opt(ATTACH, area=HAND, index=0, inPlayArea=BENCH, inPlayIndex=0)],
        context=MAIN, current=state(active=poke(WINC, hp=330, energy=1),
                                    bench=[poke(STARYU, hp=70, energy=1)], hand=[CAPE]))
    opts = pilot.explain(obs).options                       # must not raise
    assert "deploy-hp-tool" in _fired(opts[0])              # proactive default -> active wincon
    assert "deploy-hp-tool" not in _fired(opts[1])          # not the 0-gain bench line-piece


# --- Active doomed even at +100 -> redirect Cape to the promotable successor ----------------------
@pytest.mark.req("REQ-GEN-0051")
def test_doomed_active_redirects_the_cape_to_the_promotable_successor():
    """User addition: 'if our active is doomed and a cape can't protect it, we cape our next in line to
    be promoted.' When the Active wincon dies even at +100 (incoming >= hp+100), equip the benched
    successor (a 2nd win-condition) that inherits the fight — evaluated against the FULL incoming it
    will then face as the new Active, not the bench snipe."""
    stats = DictCardStatProvider({
        CAPE: CardStat(CAPE, hp=0, aceSpec=True, hpBonus=100),
        WINC: CardStat(WINC, megaEx=True, hp=330, weakness=LIGHTNING, energyType=WATER, evolvesFrom="Staryu"),
        SNIPER: CardStat(SNIPER, energyType=WATER, maxDamage=350),   # 350 >= 200+100 -> active doomed at cape
    })
    funcs = CardFunctions({CAPE: ["tool"]})
    pilot = Pilot(_line_strat(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
    obs = make_select(
        [opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0),
         opt(ATTACH, area=HAND, index=0, inPlayArea=BENCH, inPlayIndex=0)],
        context=MAIN, current=state(active=poke(WINC, hp=200, energy=1),     # doomed (350 >= 300)
                                    bench=[poke(WINC, hp=330, energy=1)],     # the successor
                                    opp_active=poke(SNIPER, energy=3, hp=330), hand=[CAPE]))
    opts = pilot.explain(obs).options
    assert "deploy-hp-tool" in _fired(opts[1])           # the benched successor
    assert "deploy-hp-tool" not in _fired(opts[0])       # not the doomed Active
    assert pilot.decide(obs) == [1]


@pytest.mark.req("REQ-GEN-0051")
def test_no_deploy_onto_a_body_that_dies_even_with_the_boost():
    """The Active wincon dies even at +100 and there is no benched successor — don't waste the
    irreplaceable Cape on a body that is lost anyway (the user: 'here it IS never'). Deploy stays
    silent, so the agent holds the Cape."""
    stats = DictCardStatProvider({
        CAPE: CardStat(CAPE, hp=0, aceSpec=True, hpBonus=100),
        WINC: CardStat(WINC, megaEx=True, hp=330, weakness=LIGHTNING, energyType=WATER, evolvesFrom="Staryu"),
        SNIPER: CardStat(SNIPER, energyType=WATER, maxDamage=350),
    })
    funcs = CardFunctions({CAPE: ["tool"]})
    pilot = Pilot(_line_strat(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
    obs = make_select([opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)],
                      context=MAIN, current=state(active=poke(WINC, hp=200, energy=1),
                                                  opp_active=poke(SNIPER, energy=3, hp=330), hand=[CAPE]))
    assert "deploy-hp-tool" not in _fired(pilot.explain(obs).options[0])    # don't cape the doomed active


# --- wall (off-line body) earns Cape ONLY when +100 buys a real survival turn ----------------------
@pytest.mark.req("REQ-GEN-0052")
def test_wall_gets_the_cape_when_it_buys_a_survival_turn():
    """User: 'never say never' on an off-line body — a re-emerged Cinderace WALL (the Active, not the
    win-condition) earns the Cape when +100 lets it survive 2 turns instead of 1 (160 HP vs 210
    incoming: 1 → 2). With no win-condition body wanting the Cape, the wall gets it (wincon priority is
    preserved — a wincon body would still outrank it)."""
    stats = DictCardStatProvider({
        CAPE: CardStat(CAPE, hp=0, aceSpec=True, hpBonus=100),
        WALL: CardStat(WALL, hp=160, energyType=FIRE),                # off-line wall, NOT the wincon
        SNIPER: CardStat(SNIPER, energyType=WATER, maxDamage=210),
    })
    funcs = CardFunctions({CAPE: ["tool"], WALL: ["opener"]})
    pilot = Pilot(_line_strat(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
    obs = make_select([opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)],
                      context=MAIN, current=state(active=poke(WALL, hp=160, energy=1),
                                                  opp_active=poke(SNIPER, energy=3, hp=330), hand=[CAPE]))
    assert "deploy-hp-tool" in _fired(pilot.explain(obs).options[0])


@pytest.mark.req("REQ-GEN-0052")
def test_wall_does_not_get_the_cape_when_it_gains_no_turn():
    """A wall the boost can't help (160 HP vs 400 incoming: dies in 1 turn either way → gain 0) gets
    nothing — don't fritter the irreplaceable Cape on an off-line body for no survival gain."""
    stats = DictCardStatProvider({
        CAPE: CardStat(CAPE, hp=0, aceSpec=True, hpBonus=100),
        WALL: CardStat(WALL, hp=160, energyType=FIRE),
        SNIPER: CardStat(SNIPER, energyType=WATER, maxDamage=400),
    })
    funcs = CardFunctions({CAPE: ["tool"], WALL: ["opener"]})
    pilot = Pilot(_line_strat(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
    obs = make_select([opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)],
                      context=MAIN, current=state(active=poke(WALL, hp=160, energy=1),
                                                  opp_active=poke(SNIPER, energy=3, hp=330), hand=[CAPE]))
    assert "deploy-hp-tool" not in _fired(pilot.explain(obs).options[0])


# --- predict-next-attacker: incoming sees opponent BENCHED promotion, not just current Active -----
@pytest.mark.req("REQ-GEN-0053")
def test_predict_next_attacker_sees_a_benched_opp_promotion():
    """Incoming generalizes beyond the opponent's CURRENT Active: a harmless Active (100) hides a big
    BENCHED attacker (350, energized & affordable). Reading the real threat, our damaged Active (200 HP)
    is doomed even at +100 (350 >= 300) -> redirect the Cape to the benched successor (330 HP, gains a
    turn vs 350). Without predicting the promotion we'd wrongly cape the 'safe-looking' Active."""
    stats = DictCardStatProvider({
        CAPE: CardStat(CAPE, hp=0, aceSpec=True, hpBonus=100),
        WINC: CardStat(WINC, megaEx=True, hp=330, weakness=LIGHTNING, energyType=WATER, evolvesFrom="Staryu"),
        WEAKOPP: CardStat(WEAKOPP, energyType=WATER, maxDamage=100),
        BIGOPP: CardStat(BIGOPP, energyType=WATER, maxDamage=350, minAttackCost=1),
    })
    funcs = CardFunctions({CAPE: ["tool"]})
    pilot = Pilot(_line_strat(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
    obs = make_select(
        [opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0),
         opt(ATTACH, area=HAND, index=0, inPlayArea=BENCH, inPlayIndex=0)],
        context=MAIN, current=state(active=poke(WINC, hp=200, energy=1),         # damaged active
                                    bench=[poke(WINC, hp=330, energy=1)],         # the successor
                                    opp_active=poke(WEAKOPP, energy=1, hp=200),
                                    opp_bench=[poke(BIGOPP, energy=1, hp=330)], hand=[CAPE]))
    opts = pilot.explain(obs).options
    assert "deploy-hp-tool" in _fired(opts[1])           # benched successor (real threat predicted)
    assert "deploy-hp-tool" not in _fired(opts[0])       # not the doomed Active
    assert pilot.decide(obs) == [1]


# --- KO invariant: a positional Cape deploy never forgoes a knockout (corr 82756664-36) ------------
@pytest.mark.req("REQ-GEN-0054")
def test_cape_deploy_never_forgoes_a_lethal_ko():
    """A positional Cape deploy never overrides a knockout. With a lethal attack AND the proactive Cape
    deploy both on the menu, the deploy is a tier-2 development and the lethal attack a tier-4
    turn-ender, so `_finish_turn_last` equips the Cape FIRST then takes the KO the same turn — the
    attack is DEFERRED (held for last), not dropped, so the Cape never costs the prize."""
    stats = DictCardStatProvider({
        CAPE: CardStat(CAPE, hp=0, aceSpec=True, hpBonus=100),
        WINC: CardStat(WINC, megaEx=True, hp=330, weakness=LIGHTNING, energyType=WATER, evolvesFrom="Staryu"),
        FRAGILE: CardStat(FRAGILE, energyType=WATER, maxDamage=100),
    }, attacks={1: AttackStat(1, damage=200)})    # attack 1 does 200 -> KOs a 60-HP Active
    funcs = CardFunctions({CAPE: ["tool"]})
    pilot = Pilot(_line_strat(), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                  stats=stats, functions=funcs)
    obs = make_select(
        [attack_opt(1), opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)],
        context=MAIN, current=state(active=poke(WINC, hp=330, energy=1),
                                    opp_active=poke(FRAGILE, energy=1, hp=60), hand=[CAPE]))
    decision = pilot.explain(obs)
    assert decision.options[0].tactical >= KO_SCORE         # attack IS a recognized lethal KO
    assert decision.options[0].deferred                     # ...but held for last, never forgone
    assert "deploy-hp-tool" in _fired(decision.options[1])  # Cape deploy endorsed (tier-2 develop)
    assert pilot.decide(obs) == [1]                         # equip Cape first, then KO on re-presented menu
