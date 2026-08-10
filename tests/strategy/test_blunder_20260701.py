"""Blunder round 2026-07-01 (mega_starmie) — four blunders, all hinging on the Active being DOOMED or
on a game-winning attack being on the menu.

Lib-free: synthetic obs via pilot_helpers + DictCardStatProvider, so no engine.
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
WINCON = 900        # Mega Starmie ex shape: Jetting Blow (cost 1, 120) + Nebula (CCC, 210)
PREEVO = 800        # Staryu (the Line base)
ACCEL = 666         # Cinderace shape: accel_source (Turbo Flare, cost 1)
WATER = 3
HARLEQUIN = 1223    # shuffle_hand draw Supporter
LILLIES = 1227      # shuffle_hand draw Supporter
MEGA_SIGNAL = 1145  # tutor_mega — fetches ONLY a Mega Evolution ex
WALLYS = 1229       # clutch_heal (heals a Mega ex, bounces ALL its Energy to hand)
SALVATORE = 1189    # a plain search Supporter
NEBULA, JETTING, TURBO = 10, 11, 13   # attack ids


def _fired(o):
    return {h.id for h, _ in o.fired}

def _ranked(pilot, obs):
    """``[(index, score), ...]`` best-first. The composer owns the MAIN pick (Issue #386), so on a
    HAND-BUILT board the ranking is the fact these tests own."""
    return [(o.index, o.score) for o in sorted(pilot.explain(obs).options, key=lambda o: -o.score)]


def _sequenced(pilot, obs):
    """The ladder's own final ORDER — `_finish_turn_last` applied to its score order."""
    select = obs["select"]
    dec = pilot.explain(obs)
    board = pilot._board(obs, select)
    options = select["option"]
    traces = list(dec.options)
    by_score = pilot._score_order(obs, options, traces)
    return pilot._finish_turn_last(obs, board, options, traces, by_score,
                                   select.get("maxCount", 0), select.get("context"))


def _stats():
    return DictCardStatProvider({
        WINCON: CardStat(WINCON, synthetic=True, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=210,
                         maxDamageCost=3, minAttackCost=1, minCostDamage=120, attacks=(NEBULA, JETTING),
                         evolvesFrom="Staryu", energyType=3),
        PREEVO: CardStat(PREEVO, synthetic=True, name="Staryu", hp=70, maxDamage=20, maxDamageCost=1,
                         minAttackCost=1, minCostDamage=20, attacks=(12,)),
        ACCEL: CardStat(ACCEL, name="Cinderace", hp=160, maxDamage=50, maxDamageCost=1,
                        minAttackCost=1, minCostDamage=50, attacks=(TURBO,), energyType=2),
        WATER: CardStat(WATER, name="Basic {W} Energy", hp=0, energyType=3),
        678: CardStat(678, synthetic=True, name="opp attacker", hp=180, megaEx=True, maxDamage=210, energyType=7),
    }, attacks={NEBULA: AttackStat(NEBULA, damage=210, cost=3),
                JETTING: AttackStat(JETTING, damage=120, cost=1),
                TURBO: AttackStat(TURBO, damage=50, cost=1)})


_FNS = {HARLEQUIN: ["draw", "shuffle_hand"], LILLIES: ["draw", "shuffle_hand"],
        MEGA_SIGNAL: ["search", "tutor_mega"], WALLYS: ["heal", "clutch_heal"], SALVATORE: ["search"]}


def _pilot(deck=None, **kw):
    """The Staryu -> Mega Starmie line, with Cinderace as the accel_source."""
    strat = Strategy(roles={WINCON: ["win_condition", "primary_attacker"], ACCEL: ["accel_source"]},
                     lines=[Line(path=[PREEVO, WINCON], payoff=WINCON)])
    return Pilot(strat, deck=deck if deck is not None else [1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=_stats(), functions=CardFunctions(_FNS), effects=fetch_effects(_FNS), **kw)


@pytest.mark.req("REQ-GEN-0034")
def test_dont_overbuild_the_doomed_wincon_feeds_the_bench_successor():
    """A doomed Active must not soak Energy toward an attack it won't live to fire."""
    pilot = _pilot()
    to_active = opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)
    to_bench = opt(ATTACH, area=HAND, index=0, inPlayArea=BENCH, inPlayIndex=0)
    doomed = state(active=poke(WINCON, energy=1, hp=210), bench=[poke(PREEVO, energy=0, hp=70)],
                   opp_active=poke(678, hp=210), hand=[WATER])
    obs = make_select([to_active, to_bench], current=doomed)
    assert pilot._board(obs).active_doomed                                  # the premise
    # `dont-overbuild-the-doomed-wincon` is DELETED (ADR-0069): the SURVIVAL gate zeroes the build.
    assert next(r for r in pilot.explain(obs).attach_working["eq"]
                if r["i"] == 0)["build"] == 0.0
    assert pilot.decide(obs) == [1]

    # Control — a HEALTHY wincon Active still builds toward Nebula.
    healthy = state(active=poke(WINCON, energy=1, hp=330), bench=[poke(PREEVO, energy=0, hp=70)],
                    opp_active=poke(678, hp=210), hand=[WATER])
    obs_h = make_select([to_active, to_bench], current=healthy)
    assert not pilot._board(obs_h).active_doomed
    assert "dont-overbuild-the-doomed-wincon" not in _fired(pilot.explain(obs_h).options[0])
    assert pilot.decide(obs_h) == [1]  # no Active-slot privilege in the shared profile


@pytest.mark.req("REQ-GEN-0035")
def test_pressure_gate_holds_the_successor_when_doomed():
    """Under doom the successor's re-access credit zeroes (`gate_library.closing_gate_reaccess`), so the
    graded SHED charges its FULL role worth — the hold rides the keep-cost equation, no rung."""
    pilot = _pilot()
    play_harlequin = opt(PLAY, area=HAND, index=0)
    attack = attack_opt(JETTING)                                # available: 1 W attached
    # `appearThisTurn` makes the Staryu an ineligible base this turn, isolating PRESSURE from the
    # separate DEPLOY-NOW spike while `line_preevo_in_play` still holds.
    just_benched = {**poke(PREEVO, energy=0, hp=70), "appearThisTurn": True}
    doomed = state(active=poke(WINCON, energy=1, hp=100), bench=[just_benched],
                   opp_active=poke(678, hp=210), hand=[HARLEQUIN, WINCON])
    obs = make_select([play_harlequin, attack], current=doomed)
    b = pilot._board(obs)
    assert b.active_doomed and b.wincon_in_hand and b.line_preevo_in_play  # the premise
    assert pilot._gate_closing(WINCON, b)                       # the successor's gate is CLOSING
    assert WINCON not in b.deploy_now_ids                       # …via pressure, not deploy-now
    assert pilot.decide(obs) == [1]

    # Control — HEALTHY Active: no doom and no deploy-now, so the hand copy keeps its discount.
    healthy = state(active=poke(WINCON, energy=1, hp=330), bench=[just_benched],
                    opp_active=poke(678, hp=210), hand=[HARLEQUIN, WINCON])
    obs_h = make_select([play_harlequin, attack], current=healthy)
    b_h = pilot._board(obs_h)
    assert not b_h.active_doomed and not pilot._gate_closing(WINCON, b_h)
    counts = {WINCON: 1}
    assert (pilot._keep_cost(WINCON, counts, 40, 6, b_h)
            < pilot._keep_cost(WINCON, counts, 40, 6, b))       # doom charges strictly more


@pytest.mark.req("REQ-GEN-0036")
def test_active_can_ko_sees_the_big_affordable_attack_not_just_the_cheapest():
    pilot = _pilot()
    loaded = state(active=poke(WINCON, energy=3, hp=70), opp_active=poke(678, hp=180))
    b = pilot._board(make_select([opt(14)], current=loaded))
    assert b.active_can_ko                                       # Nebula (210) KOs the 180-HP Active
    assert not b.active_cheap_attack_kos                         # Jetting Blow (120) alone doesn't


@pytest.mark.req("REQ-GEN-0036")
def test_clutch_heal_stands_down_and_the_game_winning_attack_is_taken_now():
    """The clutch heal BOUNCES the Energy the winning attack needs, so it must not out-rank it."""
    pilot = _pilot()
    play_salvatore = opt(PLAY, area=HAND, index=0)              # a dig
    play_wallys = opt(PLAY, area=HAND, index=1)                 # clutch_heal
    nebula = attack_opt(NEBULA)                                 # the game-winning KO
    won = state(active=poke(WINCON, energy=3, hp=70), bench=[poke(PREEVO, hp=70)],
                opp_active=poke(678, hp=180), hand=[SALVATORE, WALLYS], prizes=3)
    obs = make_select([play_salvatore, play_wallys, nebula, opt(14)], current=won)
    traces = pilot.explain(obs)
    assert traces.options[2].tactical >= KO_SCORE
    assert not traces.options[2].deferred                       # winning attack is NOT held back
    assert _ranked(pilot, obs)[0][0] == 2
    # `hold-clutch-heal` is DELETED (Issue #386), so the CLAIM is asserted as the comparison it was.
    assert traces.options[2].score > traces.options[1].score, (
        "the clutch heal out-scores a WINNING attack; the survival term is not standing down")

    # Control — SAME doomed Active but CANNOT KO.
    cant = state(active=poke(WINCON, energy=3, hp=70), bench=[poke(PREEVO, hp=70)],
                 opp_active=poke(678, hp=330), hand=[SALVATORE, WALLYS], prizes=3)
    obs_c = make_select([play_salvatore, play_wallys, nebula, opt(14)], current=cant)
    assert not pilot._board(obs_c).active_can_ko
    # The heal now prices 0.0 on BOTH boards, so the stand-down above is not the gate working — see
    # `test_the_clutch_heal_gate_is_still_conditional`, which holds that loss as a live tripwire.


@pytest.mark.req("REQ-GEN-0036")
@pytest.mark.xfail(strict=True, reason=(
    "POC-T4/5 CAPABILITY LOSS (Issue #386): `hold-clutch-heal` was deleted with `baseline_heal.py`, "
    "and it was CONDITIONAL — hold the save while a KO is on the board, fire it when none is. "
    "Measured on the pair of boards above, the clutch heal now prices 0.0 whether or not a KO is "
    "available, so nothing separates them. A survival heal priced by the survival delta it buys is "
    "the swap's premise and may well be right, but 'the same on both boards' is not that premise "
    "working — it is the option being invisible. Strict, so it turns RED the day a survival term "
    "reaches this decision"))
def test_the_clutch_heal_gate_is_still_conditional():
    """The half of the pair above that did NOT survive the deletion, kept as a live tripwire."""
    pilot = _pilot()
    play_salvatore, play_wallys = opt(PLAY, area=HAND, index=0), opt(PLAY, area=HAND, index=1)
    nebula = attack_opt(NEBULA)
    lethal = state(active=poke(WINCON, energy=3, hp=70), bench=[poke(PREEVO, hp=70)],
                   opp_active=poke(678, hp=180), hand=[SALVATORE, WALLYS], prizes=3)
    cant = state(active=poke(WINCON, energy=3, hp=70), bench=[poke(PREEVO, hp=70)],
                 opp_active=poke(678, hp=330), hand=[SALVATORE, WALLYS], prizes=3)
    menu = [play_salvatore, play_wallys, nebula, opt(14)]
    heal_when_lethal = pilot.explain(make_select(menu, current=lethal)).options[1].score
    heal_when_not = pilot.explain(make_select(menu, current=cant)).options[1].score
    assert heal_when_not > heal_when_lethal, (
        f"the clutch heal prices identically ({heal_when_not}) with and without a KO on the board")


@pytest.mark.req("REQ-GEN-0037")
def test_feed_the_firing_accelerator_over_a_bench_body_even_when_doomed():
    """Feeding the doomed accelerator 1 Water routes 3 Energy onto the Bench, so it beats dribbling 1."""
    pilot = _pilot()
    to_accel = opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)
    to_bench = opt(ATTACH, area=HAND, index=0, inPlayArea=BENCH, inPlayIndex=0)
    doomed = state(active=poke(ACCEL, energy=0, hp=210),
                   bench=[poke(WINCON, energy=0, hp=180), poke(WINCON, energy=0, hp=330)],
                   opp_active=poke(678, hp=190), hand=[WATER])
    obs = make_select([to_accel, to_bench], current=doomed)
    b = pilot._board(obs)
    assert b.active_doomed and not b.bench_wincon_ready and not b.accel_recipient_missing
    active_ctx = pilot.explain(obs).options[0]
    # `feed-the-firing-accelerator` is DELETED (ADR-0069); the credit is `this_turn`, because this
    # synthetic's Turbo Flare carries no `recoverN` rider and the accel-ROUTING term is silent.
    rows = {r["i"]: r for r in pilot.explain(obs).attach_working["eq"]}
    assert rows[0]["this_turn"] > 0 and rows[0]["marginal"] > rows[1]["marginal"]
    assert "dont-feed-the-doomed" not in _fired(active_ctx)
    assert pilot.decide(obs) == [0]

    # Control — a READY benched wincon to retreat into: the feed stands down.
    ready = state(active=poke(ACCEL, energy=0, hp=210),
                  bench=[poke(WINCON, energy=1, hp=330)],           # ready: 1 W = Jetting Blow
                  opp_active=poke(678, hp=190), hand=[WATER])
    # The menu must OFFER the retreat — the survival gate stands the tonight-credit down only when
    # the pivot is legally available NOW.
    obs_r = make_select([to_accel, to_bench, opt(RETREAT)], current=ready)
    assert pilot._board(obs_r).bench_wincon_ready
    rows = {r["i"]: r for r in pilot.explain(obs_r).attach_working["eq"]}
    assert rows[0]["this_turn"] == 0.0, "the doomed Active is still bought a swing in front of the pivot"
    assert rows[0]["marginal"] == 0.0
    assert rows[1]["build"] > rows[1]["resource_cost"], (
        "the safe Mega's stronger-attack progress remains a positive alternative")


@pytest.mark.req("REQ-GEN-0038")
def test_energy_placeable_is_false_when_every_body_is_maxed():
    """A fully-powered Active with an EMPTY Bench leaves a held Energy no home."""
    pilot = _pilot()
    maxed = pilot._board(make_select([opt(14)], current=state(active=poke(WINCON, energy=3, hp=170))))
    assert not maxed.energy_placeable
    building = pilot._board(make_select([opt(14)], current=state(active=poke(WINCON, energy=1, hp=170))))
    assert building.energy_placeable                            # 1 E < Nebula's 3
