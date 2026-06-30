"""Attach DISCIPLINE: concentrate Energy on one win-condition, and prefer a reusable Basic over a
discard-EOT burst (the b7e483a misattachment blunders).

`concentrate-energy-on-wincon` reads `board.priority_wincon_slot` — the win-condition carrying the
most Energy while still short of its biggest attack — so the deck loads ONE attacker instead of
dribbling Energy across the Bench. `prefer-reusable-over-burst` breaks the Basic-vs-Ignition tie.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.strategy import Line, Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

ATTACH, HAND, ACTIVE, BENCH, MAIN = 8, 2, 4, 5, 0
MEGA, STARYU, WATER, IGNITION = 1031, 1030, 3, 17
CINDERACE = 666       # an off-line opener/accelerator — NOT on the win-condition Line


def _fired(trace):
    return {h.id for h, _ in trace.fired}


def _attach(hand_idx, area, in_idx):
    return {"type": ATTACH, "area": HAND, "index": hand_idx, "inPlayArea": area, "inPlayIndex": in_idx}


def _stats():
    # Mega Starmie ex: cheapest attack 1, biggest attack CCC=3 -> "under max" until 3 Energy.
    return DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=210,
                       minAttackCost=1, maxDamageCost=3, evolvesFrom="Staryu"),
        STARYU: CardStat(STARYU, name="Staryu", hp=70, minAttackCost=1, maxDamageCost=1),
        WATER: CardStat(WATER, name="Water", energyType=2),
        IGNITION: CardStat(IGNITION, name="Ignition", energyType=0),
    })


def _pilot():
    funcs = CardFunctions({IGNITION: ["discard_eot"]})
    strat = Strategy(roles={MEGA: ["win_condition", "primary_attacker"], STARYU: ["starter"]})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 functions=funcs, attacks={}, attack_costs={})


def _obs(bench, hand, options):
    me = {"active": [None], "bench": bench, "hand": hand}
    return {"current": {"players": [me, {"active": [None], "bench": []}], "yourIndex": 0, "turn": 6},
            "select": {"context": MAIN, "minCount": 1, "maxCount": 1, "option": options}}


@pytest.mark.req("REQ-GEN-0016")
def test_concentrate_loads_the_most_built_wincon_over_a_bare_body():
    # Bench: a Mega on 2 Energy (closest to its CCC payoff) and a bare Staryu. The third Energy tops up
    # the Mega — concentrate, don't spread it onto the Staryu.
    p = _pilot()
    bench = [{"id": MEGA, "energies": [WATER, WATER], "hp": 330}, {"id": STARYU, "energies": [], "hp": 70}]
    hand = [{"id": WATER}]
    opts = [_attach(0, BENCH, 0), _attach(0, BENCH, 1)]               # -> the 2e Mega, -> the bare Staryu
    obs = _obs(bench, hand, opts)
    assert p._board(obs, obs["select"]).priority_wincon_slot == (BENCH, 0)
    dec = p.explain(obs)
    assert "concentrate-energy-on-wincon" in _fired(dec.options[0])
    assert "concentrate-energy-on-wincon" not in _fired(dec.options[1])
    assert p.decide(obs) == [0]                                       # load the most-built Mega


@pytest.mark.req("REQ-GEN-0016")
def test_prefer_reusable_basic_over_ignition_onto_the_wincon():
    # A Water and an Ignition both top up the Active Mega; prefer the reusable Water and save the burst.
    p = _pilot()
    bench = []
    me_active = {"id": MEGA, "energies": [WATER, WATER], "hp": 330}
    hand = [{"id": IGNITION}, {"id": WATER}]
    obs = {"current": {"players": [{"active": [me_active], "bench": [], "hand": hand},
                                   {"active": [None], "bench": []}], "yourIndex": 0, "turn": 6},
           "select": {"context": MAIN, "minCount": 1, "maxCount": 1,
                      "option": [_attach(0, ACTIVE, 0), _attach(1, ACTIVE, 0)]}}   # Ignition vs Water
    dec = p.explain(obs)
    assert "prefer-reusable-over-burst" in _fired(dec.options[0])     # the Ignition attach: penalised
    assert "prefer-reusable-over-burst" not in _fired(dec.options[1])  # the Water attach: clean
    assert p.decide(obs) == [1]                                       # attach the reusable Water


@pytest.mark.req("REQ-GEN-0016")
def test_attach_tiebreak_prefers_the_line_base_over_an_off_line_body():
    """Among EQUAL-score needy bench attaches, the decide()-ordering tie-break feeds a win-condition
    LINE base (a Staryu) before an off-line body (a benched Cinderace) — build the line, don't dribble
    onto a spent opener. A W-route-invisible nicety (no score changes). ep82867148 f87."""
    funcs = CardFunctions({IGNITION: ["discard_eot"]})
    stats = DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, minAttackCost=1,
                       maxDamageCost=3, evolvesFrom="Staryu"),
        STARYU: CardStat(STARYU, name="Staryu", hp=70, minAttackCost=1, maxDamageCost=1),
        CINDERACE: CardStat(CINDERACE, name="Cinderace", hp=160, minAttackCost=1, maxDamageCost=1),
        WATER: CardStat(WATER, name="Water", energyType=2)})
    strat = Strategy(roles={MEGA: ["win_condition", "primary_attacker"], CINDERACE: ["accel_source"]},
                     lines=[Line(path=[STARYU, MEGA], payoff=MEGA)])
    p = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs,
              attacks={}, attack_costs={})
    # bench: the off-line Cinderace at the LOWER index, the Line base Staryu after — both bare/needy.
    bench = [{"id": CINDERACE, "energies": [], "hp": 160}, {"id": STARYU, "energies": [], "hp": 70}]
    obs = _obs(bench, [{"id": WATER}], [_attach(0, BENCH, 0), _attach(0, BENCH, 1)])   # ->Cinderace, ->Staryu
    t0, t1 = p.explain(obs).options
    assert t0.score == t1.score                                      # genuinely a SCORE tie ...
    assert t1.attach_to_needy_line and not t0.attach_to_needy_line   # ... broken by the Line-base flag
    assert p.decide(obs) == [1]                                      # so the Staryu (Line base) is fed, not Cinderace
