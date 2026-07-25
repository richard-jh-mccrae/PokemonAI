"""Blunder round 2026-07-01 (mega_starmie, episode 83037962 mirror) — the Hypotheses + Pilot signals
authored by /blunder-buster for the CRITICAL cohort (ADR-0018).

Four blunders, all hinging on the Active being DOOMED (or on a game-winning attack being on the menu):
  f48  don't over-build a doomed win-condition Active — feed the benched successor (dont-overbuild-the-doomed-wincon)
  f49  don't shuffle away the hand's successor + Energy when doomed (hold-successor-when-doomed)
  f78  take a game-winning KO now; don't strip your own Energy to heal-and-stall (active_can_ko gate + winning-attack-first)
  f70  feed a firing accelerator (Turbo Flare) even when doomed — it multiplies (feed-the-firing-accelerator)

Lib-free: synthetic obs via pilot_helpers + DictCardStatProvider, so the fast suite needs no engine.
"""
import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import KO_SCORE, Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Line, Strategy
from pilot_helpers import (ACTIVE, BENCH, HAND, PLAY, attack_opt, fetch_effects, make_select,
                           opt, poke, state)

ATTACH, RETREAT = 8, 12   # engine OptionType mirrors (src/cg/api.py)
WINCON = 900        # Mega Starmie ex shape: Stage-1 Mega ex, Jetting Blow (cost 1, 120) + Nebula (CCC, 210)
PREEVO = 800        # Staryu (the Line base)
ACCEL = 666         # Cinderace shape: accel_source (Turbo Flare, cost 1, accelerates the Bench)
WATER = 3
HARLEQUIN = 1223    # shuffle_hand draw Supporter
LILLIES = 1227      # shuffle_hand draw Supporter (Lillie's Determination)
MEGA_SIGNAL = 1145  # tutor_mega — fetches ONLY a Mega Evolution ex (the wincon)
WALLYS = 1229       # clutch_heal (heals a Mega ex, bounces ALL its Energy to hand)
SALVATORE = 1189    # a plain search Supporter (dig-before-commit fodder)
NEBULA, JETTING, TURBO = 10, 11, 13   # attack ids


def _fired(o):
    return {h.id for h, _ in o.fired}


def _stats():
    return DictCardStatProvider({
        WINCON: CardStat(WINCON, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=210,
                         maxDamageCost=3, minAttackCost=1, minCostDamage=120, attacks=(NEBULA, JETTING),
                         evolvesFrom="Staryu", energyType=3),
        PREEVO: CardStat(PREEVO, name="Staryu", hp=70, maxDamage=20, maxDamageCost=1,
                         minAttackCost=1, minCostDamage=20, attacks=(12,)),
        ACCEL: CardStat(ACCEL, name="Cinderace", hp=160, maxDamage=50, maxDamageCost=1,
                        minAttackCost=1, minCostDamage=50, attacks=(TURBO,), energyType=2),
        WATER: CardStat(WATER, name="Basic {W} Energy", hp=0, energyType=3),
        678: CardStat(678, name="opp attacker", hp=180, megaEx=True, maxDamage=210, energyType=7),
    }, attacks={NEBULA: AttackStat(NEBULA, damage=210, cost=3),
                JETTING: AttackStat(JETTING, damage=120, cost=1),
                TURBO: AttackStat(TURBO, damage=50, cost=1)})


_FNS = {HARLEQUIN: ["draw", "shuffle_hand"], LILLIES: ["draw", "shuffle_hand"],
        MEGA_SIGNAL: ["search", "tutor_mega"], WALLYS: ["heal", "clutch_heal"], SALVATORE: ["search"]}


def _pilot(deck=None, **kw):
    """A Pilot over the Staryu -> Mega Starmie line, with Cinderace as the accel_source (mirrors the deck)."""
    strat = Strategy(roles={WINCON: ["win_condition", "primary_attacker"], ACCEL: ["accel_source"]},
                     lines=[Line(path=[PREEVO, WINCON], payoff=WINCON)])
    return Pilot(strat, deck=deck if deck is not None else [1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=_stats(), functions=CardFunctions(_FNS), effects=fetch_effects(_FNS), **kw)


# ---------------------------------------------------------- f48: dont-overbuild-the-doomed-wincon
@pytest.mark.req("REQ-GEN-0034")
def test_dont_overbuild_the_doomed_wincon_feeds_the_bench_successor():
    """A doomed Mega Starmie Active that can ALREADY attack (1 W = Jetting Blow) must not soak the 2nd
    Energy toward its Nebula Beam it won't live to fire — build the benched Staryu successor (ep83037962
    f48). Cancels the concentrate+build stack (−45) so the Bench attach (`power-up-attacker` +15) wins."""
    pilot = _pilot()
    to_active = opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)
    to_bench = opt(ATTACH, area=HAND, index=0, inPlayArea=BENCH, inPlayIndex=0)
    # Active wincon at 1 W (Jetting-Blow-ready already), doomed (opp 210 >= my 210 HP); a benched Staryu.
    doomed = state(active=poke(WINCON, energy=1, hp=210), bench=[poke(PREEVO, energy=0, hp=70)],
                   opp_active=poke(678, hp=210), hand=[WATER])
    obs = make_select([to_active, to_bench], current=doomed)
    assert pilot._board(obs).active_doomed                                  # the premise
    # `dont-overbuild-the-doomed-wincon` is DELETED (#139, ADR-0069): the SURVIVAL gate zeroes a doomed
    # Active's forward build outright, so there is no overbuild left to penalise.
    assert next(r for r in pilot.explain(obs).attach_working["eq"]
                if r["i"] == 0)["build"] == 0.0
    assert pilot.decide(obs) == [1]                                         # feed the Bench successor

    # Control — a HEALTHY wincon Active (not doomed) still builds toward Nebula (rule stands down).
    healthy = state(active=poke(WINCON, energy=1, hp=330), bench=[poke(PREEVO, energy=0, hp=70)],
                    opp_active=poke(678, hp=210), hand=[WATER])
    obs_h = make_select([to_active, to_bench], current=healthy)
    assert not pilot._board(obs_h).active_doomed
    assert "dont-overbuild-the-doomed-wincon" not in _fired(pilot.explain(obs_h).options[0])
    assert pilot.decide(obs_h) == [0]                                       # keep building Active


# ------------------------------------- f49: the pressure gate (fold of hold-successor-when-doomed)
@pytest.mark.req("REQ-GEN-0035")
def test_pressure_gate_holds_the_successor_when_doomed():
    """The Active wincon is doomed, the hand holds the successor Mega + a benched Staryu to evolve it
    onto — refuse the Harlequin shuffle (it would gamble the rebuild away) and attack instead (f49).
    The flat `hold-successor-when-doomed` (−35) is RETIRED into the PRESSURE GATE (2026-07-19): under
    doom the successor's re-access credit zeroes (`gate_library.closing_gate_reaccess`), so the graded
    SHED charges its FULL role worth — the hold rides the one keep-cost equation, no rung."""
    pilot = _pilot()
    play_harlequin = opt(PLAY, area=HAND, index=0)
    attack = attack_opt(JETTING)                                # Jetting Blow available (1 W attached)
    # The benched Staryu is JUST-benched (`appearThisTurn`) so it is NOT an eligible base this turn —
    # isolating the PRESSURE gate from the separate DEPLOY-NOW spike (a deployable hand wincon, tested
    # in test_gate_library). `line_preevo_in_play` still holds (a preevo IS in play, appearThisTurn
    # aside), which is the pressure premise.
    just_benched = {**poke(PREEVO, energy=0, hp=70), "appearThisTurn": True}
    doomed = state(active=poke(WINCON, energy=1, hp=100), bench=[just_benched],
                   opp_active=poke(678, hp=210), hand=[HARLEQUIN, WINCON])
    obs = make_select([play_harlequin, attack], current=doomed)
    b = pilot._board(obs)
    assert b.active_doomed and b.wincon_in_hand and b.line_preevo_in_play  # the premise
    assert pilot._gate_closing(WINCON, b)                       # the successor's gate is CLOSING (pressure)
    assert WINCON not in b.deploy_now_ids                       # …via pressure, not deploy-now (isolated)
    assert pilot.decide(obs) == [1]                             # attack; don't shuffle successor away

    # Control — HEALTHY Active, base just-benched: no doom AND no deploy-now, so no spike — the hand
    # copy keeps its closure discount, shuffle's fine.
    healthy = state(active=poke(WINCON, energy=1, hp=330), bench=[just_benched],
                    opp_active=poke(678, hp=210), hand=[HARLEQUIN, WINCON])
    obs_h = make_select([play_harlequin, attack], current=healthy)
    b_h = pilot._board(obs_h)
    assert not b_h.active_doomed and not pilot._gate_closing(WINCON, b_h)
    counts = {WINCON: 1}
    assert (pilot._keep_cost(WINCON, counts, 40, 6, b_h)
            < pilot._keep_cost(WINCON, counts, 40, 6, b))       # doom charges strictly more


# ---------------------------------------------------------- f78: active_can_ko + winning-attack-first
@pytest.mark.req("REQ-GEN-0036")
def test_active_can_ko_sees_the_big_affordable_attack_not_just_the_cheapest():
    """The new board signal: a loaded Active whose BIG attack KOs (Nebula 210 at CCC) though its cheap
    attack (Jetting 120) doesn't — active_cheap_attack_kos misses it, active_can_ko catches it."""
    pilot = _pilot()
    loaded = state(active=poke(WINCON, energy=3, hp=70), opp_active=poke(678, hp=180))
    b = pilot._board(make_select([opt(14)], current=loaded))
    assert b.active_can_ko                                       # Nebula (210) KOs the 180-HP Active
    assert not b.active_cheap_attack_kos                         # Jetting Blow (120) alone doesn't


@pytest.mark.req("REQ-GEN-0036")
def test_clutch_heal_stands_down_and_the_game_winning_attack_is_taken_now():
    """f78 missed win: a lethal Nebula (KO of a Mega ex = 3 prizes = my last 3) is on the menu, yet the
    agent played Wally's Compassion (clutch_heal, +60) — which BOUNCES the Energy the attack needs — and
    a dig Supporter (dig-before-commit, +20) sequenced ahead of the deferred attack. hold-clutch-heal
    now stands down (active_can_ko), and a game-winning attack is tier-0 (taken over the dig)."""
    pilot = _pilot()
    play_salvatore = opt(PLAY, area=HAND, index=0)              # a +20 dig (would sequence tier 1)
    play_wallys = opt(PLAY, area=HAND, index=1)                 # clutch_heal (+60 when ungated)
    nebula = attack_opt(NEBULA)                                 # the game-winning KO
    won = state(active=poke(WINCON, energy=3, hp=70), bench=[poke(PREEVO, hp=70)],
                opp_active=poke(678, hp=180), hand=[SALVATORE, WALLYS], prizes=3)
    obs = make_select([play_salvatore, play_wallys, nebula, opt(14)], current=won)
    traces = pilot.explain(obs)
    assert traces.options[2].tactical >= KO_SCORE               # Nebula is lethal
    assert "hold-clutch-heal" not in _fired(traces.options[1])  # the survival heal stands down
    assert not traces.options[2].deferred                       # winning attack is NOT held back
    assert pilot.decide(obs) == [2]                             # take the win now

    # Control — SAME doomed Active but CANNOT KO (opp too healthy): clutch heal still fires.
    cant = state(active=poke(WINCON, energy=3, hp=70), bench=[poke(PREEVO, hp=70)],
                 opp_active=poke(678, hp=330), hand=[SALVATORE, WALLYS], prizes=3)
    obs_c = make_select([play_salvatore, play_wallys, nebula, opt(14)], current=cant)
    assert not pilot._board(obs_c).active_can_ko
    assert "hold-clutch-heal" in _fired(pilot.explain(obs_c).options[1])


# ---------------------------------------------------------- f70: feed-the-firing-accelerator
@pytest.mark.req("REQ-GEN-0037")
def test_feed_the_firing_accelerator_over_a_bench_body_even_when_doomed():
    """f70 (peer mirror): the doomed Active is Cinderace (accel_source). Feeding it 1 Water lets Turbo
    Flare accelerate 3 Energy onto the Bench — worth far more than dribbling 1 onto a benched Mega. The
    accelerator isn't a spent opener, so dont-feed-the-doomed stands down and the feed wins."""
    pilot = _pilot()
    to_accel = opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)
    to_bench = opt(ATTACH, area=HAND, index=0, inPlayArea=BENCH, inPlayIndex=0)
    # Active accelerator (0 E, needs 1 for Turbo Flare), doomed; two benched Mega successors at 0 E.
    doomed = state(active=poke(ACCEL, energy=0, hp=210),
                   bench=[poke(WINCON, energy=0, hp=180), poke(WINCON, energy=0, hp=330)],
                   opp_active=poke(678, hp=190), hand=[WATER])
    obs = make_select([to_accel, to_bench], current=doomed)
    b = pilot._board(obs)
    assert b.active_doomed and not b.bench_wincon_ready and not b.accel_recipient_missing
    active_ctx = pilot.explain(obs).options[0]
    # `feed-the-firing-accelerator` is DELETED (#139, ADR-0069). The feed still wins on arithmetic:
    # arming the doomed accelerator unlocks its attack TONIGHT, which out-values one Energy of forward
    # build on a bench body. (This synthetic's Turbo Flare carries no `recoverN` rider, so the
    # accel-ROUTING term is silent here by construction — the credit is `this_turn`.)
    rows = {r["i"]: r for r in pilot.explain(obs).attach_working["eq"]}
    assert rows[0]["this_turn"] > 0 and rows[0]["marginal"] > rows[1]["marginal"]
    assert "dont-feed-the-doomed" not in _fired(active_ctx)     # firing accelerator is exempt
    assert pilot.decide(obs) == [0]                             # feed the accelerator

    # Control — READY benched wincon exists (retreat into it instead): feed stands down,
    # dont-feed-the-doomed fires again (ep83007714 f65 shape, cleanly split by bench_wincon_ready).
    ready = state(active=poke(ACCEL, energy=0, hp=210),
                  bench=[poke(WINCON, energy=1, hp=330)],           # a ready Mega (1 W = Jetting Blow)
                  opp_active=poke(678, hp=190), hand=[WATER])
    # The menu must OFFER the retreat: the survival gate's this-turn half stands the doomed Active's
    # tonight-credit down only when the pivot is legally available now, which is the fact that
    # separates this frame from 82525101-69 (a "ready" bench body too poor to pay its own retreat).
    obs_r = make_select([to_accel, to_bench, opt(RETREAT)], current=ready)
    assert pilot._board(obs_r).bench_wincon_ready
    rows = {r["i"]: r for r in pilot.explain(obs_r).attach_working["eq"]}
    assert rows[0]["this_turn"] == 0.0, "the doomed Active is still bought a swing in front of the pivot"
    assert rows[0]["marginal"] < rows[1]["marginal"], "feed the bench successor, not the doomed body"


# ---------------------------------------------------------- f40: benchless refresh over a redundant tutor
@pytest.mark.req("REQ-GEN-0038")
def test_energy_placeable_is_false_when_every_body_is_maxed():
    """The gate signal: a fully-powered Active (3 E = its Nebula cost) with an EMPTY Bench has no home
    for a held Energy, so `energy_placeable` is False; a body still short of its big attack flips it."""
    pilot = _pilot()
    maxed = pilot._board(make_select([opt(14)], current=state(active=poke(WINCON, energy=3, hp=170))))
    assert not maxed.energy_placeable
    building = pilot._board(make_select([opt(14)], current=state(active=poke(WINCON, energy=1, hp=170))))
    assert building.energy_placeable                            # 1 E < Nebula's 3 -> still can build


@pytest.mark.req("REQ-GEN-0038")
def test_benchless_agent_refreshes_over_a_redundant_wincon_tutor():
    """f40: benchless, the wincon Active fully powered, a Mega already in play with NO base to deploy a
    second — Mega Signal (tutor_mega) would dig a dead copy, and attach-before-hand-shuffle must not veto
    the bench-finding Lillie's (the held Water has no home). Refresh beats the redundant tutor."""
    # Deck holds a Staryu to draw into (deck_holds_a_need) + Megas Mega Signal could (uselessly) fetch.
    pilot = _pilot(deck=[WINCON] * 2 + [PREEVO] * 4 + [1] * 54)
    play_lillies = opt(PLAY, area=HAND, index=0)
    attach_water = opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0)
    play_signal = opt(PLAY, area=HAND, index=2)
    # Empty MY Bench, Active Mega fully powered (3 E), a held Water, Mega Signal, Lillie's. No base
    # anywhere. Opp keeps a benched body, so KO'ing their Active is NOT lethal (setup decision,
    # not win-this-turn — ADR-0030); prizes not last, so no Lethal Line locks.
    benchless = state(active=poke(WINCON, energy=3, hp=170), bench=[], opp_bench=[poke(678, hp=330)],
                      opp_active=poke(678, hp=180), hand=[LILLIES, WATER, MEGA_SIGNAL], prizes=5)
    obs = make_select([play_lillies, attach_water, play_signal, attack_opt(NEBULA), opt(14)],
                      current=benchless)
    b = pilot._board(obs)
    assert not b.energy_placeable and not b.wincon_base_deployable and b.wincon_in_play
    traces = pilot.explain(obs).options
    assert "attach-before-hand-shuffle" not in _fired(traces[0])   # held Water has no home -> no veto
    assert "dont-tutor-the-held-wincon" in _fired(traces[2])       # Mega Signal digs a dead 2nd Mega
    assert pilot.decide(obs) == [0]                                # play Lillie's to find a Bench

    # Control — benched Staryu (a base to deploy a 2nd Mega): Mega Signal NOT redundant, held
    # Energy IS placeable (Staryu needs it) -> both guards behave as before.
    with_base = state(active=poke(WINCON, energy=3, hp=170), bench=[poke(PREEVO, energy=0, hp=70)],
                      opp_active=poke(678, hp=180), hand=[LILLIES, WATER, MEGA_SIGNAL], prizes=5)
    obs_b = make_select([play_lillies, attach_water, play_signal, attack_opt(NEBULA), opt(14)],
                        current=with_base)
    bb = pilot._board(obs_b)
    assert bb.energy_placeable and bb.wincon_base_deployable
    assert "dont-tutor-the-held-wincon" not in _fired(pilot.explain(obs_b).options[2])

