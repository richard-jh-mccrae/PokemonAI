"""Lethal Solver (ADR-0030): the eager, sound, this-turn win-detector.

Behaviour through the Pilot's PUBLIC interface (``decide`` / ``explain``): when a guaranteed win
exists THIS turn, ``explain(obs).lethal`` names the line and ``decide`` takes its next step. Lib-free
(the closed-form layer); the engine-verified slices live in the engine-backed suite.
"""
import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import KO_SCORE, Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.telemetry import to_record
from pilot_helpers import ACTIVE, ATTACH, HAND, PLAY, attack_opt, make_select, opt, poke, state

END = 14  # OptionType.END (not exported by pilot_helpers)

WINCON = 900   # my Active attacker / win-condition (Mega Starmie ex shape)
PREEVO = 800   # Staryu — the Line base (evolves into WINCON), a weak attacker on its own
OPP = 678      # opponent's Active
JETTING = 11   # attack id: cost 1, 120 damage
NEBULA = 10    # attack id: cost 3, 210 damage (the big attack an extra Energy unlocks)
STARYU = 12    # Staryu's own attack: cost 1, 20 damage (can't KO)
SNIPE = 15     # a snipe attack: cost 1, 50 to the Active + a 100 bench-snipe rider
WATER = 3      # a Basic {W} Energy card in hand
WALLYS = 1229  # Wally's Compassion — clutch_heal (heals a Mega ex, BOUNCES all its Energy to hand)
BOSS = 1182    # Boss's Orders — a gust Supporter (drags a benched Pokémon to the Active Spot)
EVOLVE = 9     # OptionType.EVOLVE (not exported by pilot_helpers)
RETREAT = 12   # OptionType.RETREAT (not exported by pilot_helpers)
EXOPP = 679    # opponent's Active: a Pokémon ex (2 prizes)
BENCHIE = 700  # opponent's benched body (1 prize), KO-able by the snipe rider


def _stats():
    return DictCardStatProvider({
        WINCON: CardStat(WINCON, name="Mega Starmie ex", hp=330, energyType=3, minAttackCost=1,
                         minCostDamage=120, maxDamage=210, maxDamageCost=3,
                         attacks=(JETTING, NEBULA, SNIPE), evolvesFrom="Staryu"),
        PREEVO: CardStat(PREEVO, name="Staryu", hp=70, energyType=3, minAttackCost=1,
                         minCostDamage=20, maxDamage=20, attacks=(STARYU,)),
        OPP: CardStat(OPP, name="opp active", hp=120, energyType=7),
        EXOPP: CardStat(EXOPP, name="opp ex", hp=330, energyType=7, ex=True),
        BENCHIE: CardStat(BENCHIE, name="opp benchie", hp=100, energyType=7),
        WATER: CardStat(WATER, name="Basic {W} Energy", hp=0, energyType=3),
    })


def _pilot(**kw):
    strat = Strategy(roles={WINCON: ["win_condition", "primary_attacker"]})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=_stats(), functions=CardFunctions({WALLYS: ["heal", "clutch_heal"], BOSS: ["gust"]}),
                 attacks={JETTING: 120, NEBULA: 210, STARYU: 20, SNIPE: 50},
                 attack_costs={JETTING: 1, NEBULA: 3, STARYU: 1, SNIPE: 1},
                 bench_snipe={SNIPE: 100}, **kw)


@pytest.mark.req("REQ-LETHAL-0001")
def test_immediate_prize_out_ko_is_a_locked_lethal_line_taken_now():
    """Tracer bullet: my Active can KO the opponent's Active (Jetting Blow 120 vs 120 HP) and it takes
    my LAST prize -> a guaranteed win THIS turn. The Solver locks the 1-step line and the Pilot takes
    the attack; ``explain(obs).lethal`` surfaces the line."""
    pilot = _pilot()
    # Active powered for Jetting Blow (1 W); opp Active at 120 HP (a KO); my last prize (1 remaining).
    won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(OPP, hp=120),
                prizes=1, opp_prizes=2)
    obs = make_select([attack_opt(JETTING), opt(END)], current=won)

    d = pilot.explain(obs)
    assert d.lethal is not None                    # a guaranteed winning line was found and locked
    assert d.lethal.next_step == [0]               # its next step is the finishing attack
    assert pilot.decide(obs) == [0]                # ... and the Pilot takes it


@pytest.mark.req("REQ-LETHAL-0002")
def test_empty_bench_ko_is_lethal_even_when_prizes_are_not_last():
    """A KO of the opponent's Active while their Bench is EMPTY wins the game (they have no Pokémon
    left to promote) — a win even though it does NOT take my last prize. The Solver locks it."""
    pilot = _pilot()
    # 3 prizes left (NOT a prize-out), but the opponent's Bench is empty: KO their Active = they lose.
    won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(OPP, hp=120),
                opp_bench=[], prizes=3, opp_prizes=2)
    obs = make_select([attack_opt(JETTING), opt(END)], current=won)
    d = pilot.explain(obs)
    assert d.lethal is not None and d.lethal.next_step == [0]   # empty-bench win detected + taken
    assert pilot.decide(obs) == [0]

    # Control — the opponent has a benched Pokémon, so the KO is NOT a win (they promote); with prizes
    # not last there is no lethal to lock.
    not_won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(OPP, hp=120),
                    opp_bench=[poke(OPP, hp=120)], prizes=3, opp_prizes=2)
    obs_c = make_select([attack_opt(JETTING), opt(END)], current=not_won)
    assert pilot.explain(obs_c).lethal is None


@pytest.mark.req("REQ-LETHAL-0003")
def test_enabling_attach_is_locked_and_the_breaker_is_vetoed():
    """CRITICAL 040c shape: the Active needs ONE more Energy to KO for the win. Attaching it unlocks
    Nebula Beam (210 vs 180); the Solver locks the 2-step line (attach -> KO), takes the attach, and
    VETOES Wally's Compassion (clutch_heal) — which would BOUNCE the Energy the KO needs and blow the
    win. The enabling step, not the finishing attack, is this decision's next step."""
    pilot = _pilot()
    play_wallys = opt(PLAY, area=HAND, index=0)                              # the breaker
    attach_water = opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0)
    # Active at 2 Energy (Jetting 120 can't KO 180); attaching the 3rd unlocks Nebula 210 = the win.
    won = state(active=poke(WINCON, energy=2, hp=330), opp_active=poke(OPP, hp=180),
                opp_bench=[poke(OPP, hp=180)], hand=[WALLYS, WATER], prizes=1, opp_prizes=2)
    obs = make_select([play_wallys, attach_water, attack_opt(JETTING), opt(END)], current=won)
    d = pilot.explain(obs)
    assert d.lethal is not None and d.lethal.next_step == [1]   # lock the enabling attach
    assert pilot.decide(obs) == [1]                             # take it, NOT Wally's (index 0)

    # Control — the opponent's Active is too healthy (330): attaching does NOT unlock a KO, so there is
    # no line to lock and the Solver stands down.
    safe = state(active=poke(WINCON, energy=2, hp=330), opp_active=poke(OPP, hp=330),
                 opp_bench=[poke(OPP, hp=180)], hand=[WALLYS, WATER], prizes=1, opp_prizes=2)
    obs_c = make_select([play_wallys, attach_water, attack_opt(JETTING), opt(END)], current=safe)
    assert pilot.explain(obs_c).lethal is None


@pytest.mark.req("REQ-LETHAL-0004")
def test_evolve_that_unlocks_the_ko_is_a_locked_lethal_line():
    """a211/aae4 shape: my Active is a Staryu (its own 20-damage attack can't KO). Evolving it to Mega
    Starmie ex — the Energy carries through — lets Jetting Blow (120) KO for the win. No existing hook
    sees an evolve-unlock, so the Solver does its own lookahead: it locks `evolve -> KO` and takes the
    evolve."""
    pilot = _pilot()
    evolve = opt(EVOLVE, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)  # Staryu -> Mega (hand[0])
    staryu_attack = attack_opt(STARYU)                                          # 20 dmg — no KO
    won = state(active=poke(PREEVO, energy=1, hp=70), opp_active=poke(OPP, hp=120),
                opp_bench=[poke(OPP, hp=120)], hand=[WINCON], prizes=1, opp_prizes=2)
    obs = make_select([evolve, staryu_attack, opt(END)], current=won)
    d = pilot.explain(obs)
    assert d.lethal is not None and d.lethal.next_step == [0]   # lock the evolve that unlocks the KO
    assert pilot.decide(obs) == [0]

    # Control — evolving still doesn't reach the KO (opp Active at 330 > Jetting's 120): no lethal.
    safe = state(active=poke(PREEVO, energy=1, hp=70), opp_active=poke(OPP, hp=330),
                 opp_bench=[poke(OPP, hp=120)], hand=[WINCON], prizes=1, opp_prizes=2)
    obs_c = make_select([evolve, staryu_attack, opt(END)], current=safe)
    assert pilot.explain(obs_c).lethal is None


@pytest.mark.req("REQ-LETHAL-0005")
def test_snipe_that_does_not_take_enough_prizes_is_not_lethal():
    """SOUNDNESS: I need 2 prizes. My attack snipes a benched 1-prize body (a KO) but does NOT KO the
    2-prize ex Active — so it takes only ONE prize, not the win. The Solver must NOT lock it: a false
    lethal that committed the turn is the one catastrophic direction."""
    pilot = _pilot()
    snipe = attack_opt(SNIPE)                                    # 50 to Active (survives) + 100 snipe KO
    looks_won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(EXOPP, hp=330),
                      opp_bench=[poke(BENCHIE, hp=100)], prizes=2, opp_prizes=2)
    obs = make_select([snipe, opt(END)], current=looks_won)
    assert pilot.explain(obs).lethal is None                    # only 1 prize taken -> not a win

    # Control — I need only 1 prize: the same snipe-KO now takes my last, so it IS lethal and locks.
    won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(EXOPP, hp=330),
                opp_bench=[poke(BENCHIE, hp=100)], prizes=1, opp_prizes=2)
    obs_c = make_select([snipe, opt(END)], current=won)
    assert pilot.explain(obs_c).lethal is not None and pilot.decide(obs_c) == [0]


@pytest.mark.req("REQ-LETHAL-0006")
def test_simultaneous_double_ko_is_a_draw_not_a_locked_win():
    """SOUNDNESS: my KO takes my last prize, but its recoil also KOs my Active and hands the opponent
    their last prize at the same Checkup — the competition scores that a DRAW, not a win (ADR-0022 #2).
    The Solver must NOT lock it. Dedicated fixtures so the recoil attack can't perturb other slices."""
    RECOILER, ROPP, RECOIL_ATK = 950, 951, 20
    stats = DictCardStatProvider({
        RECOILER: CardStat(RECOILER, name="recoiler", hp=70, energyType=3, minAttackCost=1,
                           minCostDamage=210, maxDamage=210, attacks=(RECOIL_ATK,)),
        ROPP: CardStat(ROPP, name="ropp", hp=200, energyType=7),
    })
    pilot = Pilot(Strategy(roles={RECOILER: ["win_condition"]}), deck=[1] * 60,
                  general_strategy=GENERAL_STRATEGY, stats=stats, functions=CardFunctions({}),
                  attacks={RECOIL_ATK: 210}, attack_costs={RECOIL_ATK: 1}, recoil={RECOIL_ATK: 400})
    # recoil 400 self-KOs my 70-HP Active; both players take their last prize at once -> a draw.
    draw = state(active=poke(RECOILER, energy=1, hp=70), opp_active=poke(ROPP, hp=200),
                 opp_bench=[poke(ROPP, hp=200)], prizes=1, opp_prizes=1)
    obs = make_select([attack_opt(RECOIL_ATK), opt(END)], current=draw)
    assert pilot.explain(obs).lethal is None                    # a draw is not a win

    # Control — my Active survives the recoil (500 HP > 400): the KO is a clean win and locks.
    win = state(active=poke(RECOILER, energy=1, hp=500), opp_active=poke(ROPP, hp=200),
                opp_bench=[poke(ROPP, hp=200)], prizes=1, opp_prizes=1)
    obs_c = make_select([attack_opt(RECOIL_ATK), opt(END)], current=win)
    assert pilot.explain(obs_c).lethal is not None


# ----------------------------------------------------------------- the in-scope CRITICAL gate (ADR-0030)
@pytest.mark.req("REQ-LETHAL-0007")
def test_critical_c1e0_winning_attack_vetoes_the_gust_breaker():
    """CRITICAL c1e0 ('must never happen again'): the current Active can KO the opponent's Active for
    the win, but the agent played Boss's Orders — gusting up a body it could no longer KO — and threw
    the game. The Solver locks the winning attack and vetoes the gust."""
    pilot = _pilot()
    boss = opt(PLAY, area=HAND, index=0)                         # the breaker (gust)
    won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(OPP, hp=120),
                opp_bench=[poke(BENCHIE, hp=100)], hand=[BOSS], prizes=1, opp_prizes=2)
    obs = make_select([boss, attack_opt(JETTING), opt(END)], current=won)
    d = pilot.explain(obs)
    assert d.lethal is not None and d.lethal.next_step == [1]
    assert pilot.decide(obs) == [1]                             # attack for the win, NOT Boss's (index 0)


@pytest.mark.req("REQ-LETHAL-0008")
def test_critical_fd5c_retreat_into_the_powered_wincon_is_locked():
    """CRITICAL fd5c: retreating was right — but into the powered Mega Starmie that KOs for the win, not
    the unpowered opener. My spent Active can't KO; a benched Mega (1 W = Jetting Blow 120) KOs the
    opponent's 120-HP Active. The Solver locks the retreat that brings the winning attacker Active."""
    pilot = _pilot()
    retreat = opt(RETREAT)
    won = state(active=poke(PREEVO, energy=1, hp=70),                 # a spent opener that can't KO
                bench=[poke(WINCON, energy=1, hp=330)],               # the powered wincon that can
                opp_active=poke(OPP, hp=120), opp_bench=[poke(BENCHIE, hp=100)], prizes=1, opp_prizes=2)
    obs = make_select([retreat, attack_opt(STARYU), opt(END)], current=won)
    d = pilot.explain(obs)
    assert d.lethal is not None and d.lethal.next_step == [0]   # lock the retreat-to-lethal
    assert pilot.decide(obs) == [0]


@pytest.mark.req("REQ-LETHAL-0010")
def test_strict_execute_only_holds_across_the_turns_two_decisions():
    """Across the many per-decision calls of ONE turn, the Solver re-derives the same line and takes its
    next step each time — the enabling attach first (Wally's vetoed), then the finishing KO (Wally's
    vetoed again) once the engine re-opens the menu. Strict execute-only, no explicit turn state."""
    pilot = _pilot()
    play_wallys = opt(PLAY, area=HAND, index=0)
    attach_water = opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0)
    # Decision 1: Active at 2 E (Jetting can't KO 180); attaching the 3rd unlocks Nebula 210 = the win.
    before = state(active=poke(WINCON, energy=2, hp=330), opp_active=poke(OPP, hp=180),
                   opp_bench=[poke(OPP, hp=180)], hand=[WALLYS, WATER], prizes=1, opp_prizes=2)
    obs1 = make_select([play_wallys, attach_water, attack_opt(JETTING), opt(END)], current=before)
    assert pilot.decide(obs1) == [1]                            # the enabling attach, NOT Wally's

    # Decision 2: the engine re-opened the menu after the attach — Active now at 3 E, Nebula available.
    after = state(active=poke(WINCON, energy=3, hp=330), opp_active=poke(OPP, hp=180),
                  opp_bench=[poke(OPP, hp=180)], hand=[WALLYS], prizes=1, opp_prizes=2)
    obs2 = make_select([play_wallys, attack_opt(NEBULA), opt(END)], current=after)
    assert pilot.explain(obs2).lethal is not None
    assert pilot.decide(obs2) == [1]                            # the finishing KO, NOT Wally's


# ------------------------------------------------------- telemetry: the verdict rides in the @T record
@pytest.mark.req("REQ-LETHAL-0011")
def test_lethal_verdict_is_emitted_in_decision_telemetry():
    """The Solver's verdict must ride in the @T Decision Telemetry (ADR-0019) — the SAME `to_record`
    feeds the live stderr line, the correction's `live_trace`, and the tuner's retest — so a blunder
    correction on a lethal decision carries the solver's data for the blunder-buster to analyze. A
    locked line surfaces its step + kind + rationale; a non-lethal decision surfaces `lethal: None`
    (the key is always present so corrections can filter on it)."""
    pilot = _pilot()
    won = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(OPP, hp=120),
                prizes=1, opp_prizes=2)
    rec = to_record(pilot.explain(make_select([attack_opt(JETTING), opt(END)], current=won)))
    assert rec["lethal"] == {"step": [0], "kind": "direct", "why": "lethal: this KO wins the match"}

    safe = state(active=poke(WINCON, energy=1, hp=330), opp_active=poke(OPP, hp=330),
                 opp_bench=[poke(OPP, hp=120)], prizes=3, opp_prizes=2)
    rec_none = to_record(pilot.explain(make_select([attack_opt(JETTING), opt(END)], current=safe)))
    assert "lethal" in rec_none and rec_none["lethal"] is None

    # an enabling-step lock carries its own kind, so a correction can tell a develop-unlock apart.
    unlock = state(active=poke(WINCON, energy=2, hp=330), opp_active=poke(OPP, hp=180),
                   opp_bench=[poke(OPP, hp=180)], hand=[WALLYS, WATER], prizes=1, opp_prizes=2)
    obs_u = make_select([opt(PLAY, area=HAND, index=0),
                         opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0),
                         attack_opt(JETTING), opt(END)], current=unlock)
    assert to_record(pilot.explain(obs_u))["lethal"]["kind"] == "unlock"
