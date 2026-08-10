"""Blunder round 2026-06-30 (mega_starmie) — the rules + signals authored by /blunder-buster.

Lib-free: synthetic obs dicts via pilot_helpers + DictCardStatProvider, so no native engine.
"""
import pytest

from card_facts import ignition_tags
from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import KO_SCORE, Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Line, Strategy
from pilot_helpers import (
    ACTIVE, ATTACH_FROM, BENCH, HAND, attack_opt, card_opt, make_select, opt, poke, state)

ATTACH = 8
RETREAT = 12
END = 14
WINCON = 900        # Mega Starmie ex shape: Jetting Blow {W} 120 (+50 snipe), Nebula CCC 210
PREEVO = 800        # Staryu shape
CINDER = 666        # Cinderace shape: Stage-2 Evolution, 1-cost 50-dmg attack
WATER = 3
IGNITION = 17
OPP = 678


def _fired(o):
    return {h.id for h, _ in o.fired}

def _ranked(pilot, obs):
    """``[(index, score), ...]`` best-first. The composer owns the MAIN pick (Issue #386), so on a
    HAND-BUILT board the ranking is the fact these tests own."""
    return [(o.index, o.score) for o in sorted(pilot.explain(obs).options, key=lambda o: -o.score)]


def _stats():
    return DictCardStatProvider({
        WINCON: CardStat(WINCON, synthetic=True, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=210,
                         maxDamageCost=3, minAttackCost=1, minCostDamage=120, attacks=(10, 11),
                         evolvesFrom="Staryu", energyType=3),
        PREEVO: CardStat(PREEVO, synthetic=True, name="Staryu", hp=70, maxDamage=20, maxDamageCost=1,
                         minAttackCost=1, minCostDamage=20, attacks=(12,)),
        CINDER: CardStat(CINDER, name="Cinderace", hp=160, maxDamage=50, maxDamageCost=1,
                         minAttackCost=1, minCostDamage=50, attacks=(20,), evolvesFrom="Raboot",
                         energyType=2),                      # {R} — the turn-1 weakness test needs it
        WATER: CardStat(WATER, name="Basic {W} Energy", hp=0, energyType=3),
        IGNITION: CardStat(IGNITION, name="Ignition Energy", hp=0, energyType=0),
        OPP: CardStat(OPP, synthetic=True, name="opp", hp=60, weakness=2),  # weak to {R}
    }, attacks={
        10: AttackStat(10, damage=210, cost=3),
        11: AttackStat(11, damage=120, cost=1, benchSnipe=50),
        12: AttackStat(12, damage=20, cost=1),
        20: AttackStat(20, damage=50, cost=1),
    })


def _pilot(**kw):
    return Pilot(Strategy(roles={WINCON: ["win_condition", "primary_attacker"]},
                          lines=[Line(path=[PREEVO, WINCON], payoff=WINCON)]),
                 deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 functions=CardFunctions({IGNITION: ignition_tags()}), **kw)


@pytest.mark.req("REQ-GEN-0048")
def test_dont_waste_ignition_on_an_already_powered_cinderace():
    """The Active already holds a {W} for its 1-cost attack, so the Ignition evaporates uncashed."""
    pilot = _pilot()
    attach_ign = opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)   # Ignition
    attack = attack_opt(20)                                                          # Turbo Flare, 50
    obs = make_select([attach_ign, attack, opt(END)],
                      current=state(active=poke(CINDER, energy=1, hp=160),
                                    opp_active=poke(OPP, hp=60), hand=[IGNITION]))
    traces = pilot.explain(obs)
    assert next(r for r in traces.attach_working["eq"] if r["i"] == 0)["evaporates"] is True
    assert traces.options[0].tactical < 0
    assert traces.options[0].score <= 0                               # sunk -> sequenced last
    assert pilot.decide(obs) == [1]


@pytest.mark.req("REQ-GEN-0049")
def test_lethal_attach_stands_down_on_turn_one_going_first():
    """On turn 1 the first player CANNOT attack (rules.md §first-turn), so the unlocked KO is illusory."""
    pilot = _pilot()
    attach_ign = opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)
    # Cinderace 0 Energy; opp 60 HP weak to {R} -> +Ignition lets Turbo Flare (50x2=100) KO.
    cur = state(active=poke(CINDER, energy=0, hp=160), opp_active=poke(OPP, hp=60), hand=[IGNITION], turn=1)
    obs = make_select([attach_ign, opt(END)], current=cur)
    assert pilot.explain(obs).options[0].tactical < 0
    assert pilot.decide(obs) == [1]

    # Control: same board, later turn -> lethal attach is real -> KO-class.
    later = state(active=poke(CINDER, energy=0, hp=160), opp_active=poke(OPP, hp=60), hand=[IGNITION], turn=3)
    assert pilot.explain(make_select([attach_ign, opt(END)], current=later)).options[0].tactical >= KO_SCORE


@pytest.mark.req("REQ-GEN-0050")
def test_retreat_into_ready_wincon_to_take_the_ko():
    """Both take the KO, but the benched wincon also snipes — same prize, better board."""
    pilot = _pilot()
    attack = attack_opt(20)                                          # Turbo Flare 50 -> KO (opp 10)
    cur = state(active=poke(CINDER, energy=1, hp=160),
                bench=[poke(WINCON, energy=3, hp=330)],             # ready wincon
                opp_active=poke(OPP, hp=10), opp_bench=[poke(PREEVO, hp=60)])  # a snipe target
    obs = make_select([attack, opt(RETREAT), opt(END)], context=0, current=cur)
    traces = pilot.explain(obs)
    assert traces.options[0].tactical >= KO_SCORE
    assert traces.options[1].tactical >= KO_SCORE
    assert traces.options[1].tactical > traces.options[0].tactical   # wincon's KO (snipe) is better
    assert _ranked(pilot, obs)[0][0] == 1


def _lethal_only(trace) -> float:
    """`OptionTrace.tactical` SUMS across layers, and a RETREAT also carries ADR-0100's Sub-lethal
    Residual — netted out here so these frames assert only whether the LETHAL lookahead fires."""
    row = trace.promote_retreat_working
    return trace.tactical - (row["tactical"] if row is not None else 0.0)

@pytest.mark.req("REQ-GEN-0050")
def test_retreat_lethal_stands_down_when_no_benched_wincon_can_ko():
    """The lookahead never forfeits a KO."""
    pilot = _pilot()
    attack = attack_opt(20)
    cur = state(active=poke(CINDER, energy=1, hp=160),
                bench=[poke(WINCON, energy=0, hp=330)],             # NOT ready
                opp_active=poke(OPP, hp=10))
    obs = make_select([attack, opt(RETREAT), opt(END)], context=0, current=cur)
    traces = pilot.explain(obs)
    assert _lethal_only(traces.options[1]) == 0                      # retreat carries no lethal value
    assert pilot.decide(obs) == [0]


@pytest.mark.req("REQ-GEN-0050")
def test_retreat_lethal_does_not_fire_when_the_active_is_the_wincon():
    """Don't retreat the win-condition itself — the lookahead is for swapping a SPENT opener in."""
    pilot = _pilot()
    cur = state(active=poke(WINCON, energy=3, hp=330),
                bench=[poke(WINCON, energy=3, hp=330)], opp_active=poke(OPP, hp=10))
    obs = make_select([attack_opt(11), opt(RETREAT), opt(END)], context=0, current=cur)
    assert _lethal_only(pilot.explain(obs).options[1]) == 0


@pytest.mark.req("REQ-GEN-0050")
def test_retreat_lethal_stands_down_when_the_active_already_takes_an_equal_ko():
    """Retreat-to-lethal fires ONLY for a STRICTLY BETTER KO, not an equal one."""
    pilot = _pilot()
    attack = attack_opt(20)                                          # Turbo Flare 50 -> KO (opp 10)
    cur = state(active=poke(CINDER, energy=1, hp=160),
                bench=[poke(PREEVO, energy=4, hp=70)],               # also KOs, but no snipe edge
                opp_active=poke(OPP, hp=10))
    obs = make_select([attack, opt(RETREAT), opt(END)], context=0, current=cur)
    traces = pilot.explain(obs)
    assert traces.options[0].tactical >= KO_SCORE
    assert _lethal_only(traces.options[1]) == 0                      # no EXTRA value -> stand down
    assert pilot.decide(obs) == [0]


@pytest.mark.req("REQ-GEN-0051")
def test_spread_attach_to_the_needy_at_attach_from():
    pilot = _pilot()
    powered = card_opt(BENCH, 0)        # Mega Starmie ex, 3 Energy
    bare = card_opt(BENCH, 1)           # Staryu, 0 Energy
    cur = state(active=poke(CINDER, energy=1, hp=160),
                bench=[poke(WINCON, energy=3, hp=330), poke(PREEVO, energy=0, hp=70)])
    obs = make_select([powered, bare], context=ATTACH_FROM, current=cur)
    traces = pilot.explain(obs)
    assert "spread-attach-to-the-needy" not in _fired(traces.options[0])
    assert next(r for r in traces.attach_working["eq"] if r["i"] == 1)["build"] > 0
    assert pilot.decide(obs) == [1]


@pytest.mark.req("REQ-GEN-0051")
def test_attach_from_target_needs_signal_is_off_outside_attach_from():
    pilot = _pilot()
    bare = card_opt(BENCH, 1)
    cur = state(active=poke(CINDER, energy=1, hp=160),
                bench=[poke(WINCON, energy=3, hp=330), poke(PREEVO, energy=0, hp=70)])
    obs = make_select([bare], context=0, current=cur)        # MAIN, not ATTACH_FROM
    assert "spread-attach-to-the-needy" not in _fired(pilot.explain(obs).options[0])


@pytest.mark.req("REQ-GEN-0051")
def test_concentrate_accel_on_one_line_body_at_attach_from():
    """The 1-Energy Staryu clears its OWN 1-cost attack but the deck's payoff is the 3-Energy Mega, so
    the accelerated Energy concentrates on the started body."""
    pilot = _pilot()
    started = card_opt(BENCH, 0)     # Staryu, 1 Energy
    bare = card_opt(BENCH, 1)        # Staryu, 0 Energy
    cur = state(active=poke(CINDER, energy=1, hp=160),
                bench=[poke(PREEVO, energy=1, hp=70), poke(PREEVO, energy=0, hp=70)])
    obs = make_select([started, bare], context=ATTACH_FROM, current=cur)
    traces = pilot.explain(obs)
    rows = {r["i"]: r for r in traces.attach_working["eq"]}
    assert rows[1]["build"] > rows[0]["build"]  # bare Staryu crosses its exact cheap-attack envelope
    assert "concentrate-accel-on-one-line-body" not in _fired(traces.options[1])   # bare body
    assert pilot.decide(obs) == [1]

    # An EVOLVED wincon beats a MORE-energised pre-evo: no evolution step left, so it is the attacker.
    cur2 = state(active=poke(CINDER, energy=1, hp=160),
                 bench=[poke(WINCON, energy=1, hp=330), poke(PREEVO, energy=2, hp=70)])
    obs2 = make_select([card_opt(BENCH, 0), card_opt(BENCH, 1)], context=ATTACH_FROM, current=cur2)
    rows2 = {r["i"]: r for r in pilot.explain(obs2).attach_working["eq"]}
    assert rows2[0]["tactical"] > rows2[0]["resource_cost"]
    assert rows2[1]["tactical"] == rows2[1]["resource_cost"] == 0.0
    assert pilot.decide(obs2) == [0]


@pytest.mark.req("REQ-GEN-0051")
def test_conserve_burst_when_the_opponent_cannot_be_koed_even_maxed():
    """Even fully powered, Nebula Beam 210 < 300 HP, so the one-shot buys nothing worth spending."""
    pilot = _pilot()
    ign = opt(ATTACH, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)     # Ignition -> Active
    water = opt(ATTACH, area=HAND, index=1, inPlayArea=ACTIVE, inPlayIndex=0)   # Basic {W} -> Active
    cur = state(active=poke(WINCON, energy=0, hp=330), opp_active=poke(OPP, hp=300),
                hand=[IGNITION, WATER])
    obs = make_select([ign, water, opt(END)], context=0, current=cur)
    traces = pilot.explain(obs)
    rows = {r["i"]: r for r in traces.attach_working["eq"]}
    assert rows[0]["tactical"] < rows[1]["tactical"]     # the burst is capped + costs the tie-break
    assert "conserve-burst-when-no-ko" not in _fired(traces.options[1])   # not the reusable Basic
    assert _ranked(pilot, obs)[0][0] == 1

    # Control: a KO-able Active (60 HP < 210 maxed) — the burst DOES buy the KO.
    cur2 = state(active=poke(WINCON, energy=0, hp=330), opp_active=poke(OPP, hp=60), hand=[IGNITION, WATER])
    obs2 = make_select([ign, water, opt(END)], context=0, current=cur2)
    assert "conserve-burst-when-no-ko" not in _fired(pilot.explain(obs2).options[0])
