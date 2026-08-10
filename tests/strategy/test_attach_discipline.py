"""Attach DISCIPLINE: concentrate Energy on one win-condition, prefer a reusable Basic over a burst.

Both are consequences of the decider's axes, not rungs (ADR-0069), so these assert the DECISION and
the axes that produced it.
"""
import pytest

from card_facts import ignition_tags
from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
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
    mega_attack, staryu_attack = 990_301, 990_302
    return DictCardStatProvider({
        MEGA: CardStat(MEGA, synthetic=True, name="Synthetic Mega attacker", hp=330, megaEx=True, maxDamage=210,
                       minAttackCost=3, maxDamageCost=3, evolvesFrom="Staryu",
                       attacks=(mega_attack,)),
        STARYU: CardStat(STARYU, name="Staryu", hp=70, minAttackCost=1, maxDamageCost=1,
                         attacks=(staryu_attack,)),
        WATER: CardStat(WATER, synthetic=True, name="Water", cardType=5, energyType=3),
        IGNITION: CardStat(IGNITION, synthetic=True, name="Ignition", cardType=6, energyType=0),
    }, attacks={
        mega_attack: AttackStat(mega_attack, damage=210, cost=3, energyTypes=(3, 3, 3)),
        staryu_attack: AttackStat(staryu_attack, damage=20, cost=1, energyTypes=(3,)),
    })


def _pilot():
    funcs = CardFunctions({IGNITION: ignition_tags()})
    strat = Strategy(roles={MEGA: ["win_condition", "primary_attacker"], STARYU: ["starter"]})
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 functions=funcs)


def _obs(bench, hand, options):
    me = {"active": [None], "bench": bench, "hand": hand}
    return {"current": {"players": [me, {"active": [None], "bench": []}], "yourIndex": 0, "turn": 6},
            "select": {"context": MAIN, "minCount": 1, "maxCount": 1, "option": options}}


@pytest.mark.req("REQ-GEN-0016")
def test_concentrate_loads_the_most_built_wincon_over_a_bare_body():
    p = _pilot()
    bench = [{"id": MEGA, "energies": [WATER, WATER], "hp": 330}, {"id": STARYU, "energies": [], "hp": 70}]
    hand = [{"id": WATER}]
    opts = [_attach(0, BENCH, 0), _attach(0, BENCH, 1)]               # -> the 2e Mega, -> the bare Staryu
    obs = _obs(bench, hand, opts)
    assert p._board(obs, obs["select"]).priority_wincon_slot == (BENCH, 0)
    dec = p.explain(obs)
    rows = {r["i"]: r for r in dec.attach_working["eq"]}
    assert rows[0]["build"] > rows[1]["build"]                        # convexity, not a rung
    assert max(rows, key=lambda i: rows[i]["tactical"]) == 0         # root ranks the built Mega


@pytest.mark.req("REQ-GEN-0016")
def test_prefer_reusable_basic_over_ignition_onto_the_wincon():
    p = _pilot()
    bench = []
    me_active = {"id": MEGA, "energies": [WATER, WATER], "hp": 330}
    hand = [{"id": IGNITION}, {"id": WATER}]
    obs = {"current": {"players": [{"active": [me_active], "bench": [], "hand": hand},
                                   {"active": [None], "bench": []}], "yourIndex": 0, "turn": 6},
           "select": {"context": MAIN, "minCount": 1, "maxCount": 1,
                      "option": [_attach(0, ACTIVE, 0), _attach(1, ACTIVE, 0)]}}   # Ignition vs Water
    dec = p.explain(obs)
    rows = {r["i"]: r for r in dec.attach_working["eq"]}
    assert rows[0]["tactical"] < rows[1]["tactical"]                  # the burst is the dearer spend
    assert p.decide(obs) == [1]                                       # attach the reusable Water


@pytest.mark.req("REQ-GEN-0016")
def test_attach_tiebreak_prefers_the_line_base_over_an_off_line_body():
    """Among EQUAL-score needy bench attaches the tie-break feeds a Line base before an off-line body."""
    funcs = CardFunctions({IGNITION: ignition_tags()})
    stats = DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, minAttackCost=1,
                       maxDamageCost=3, evolvesFrom="Staryu"),
        STARYU: CardStat(STARYU, name="Staryu", hp=70, minAttackCost=1, maxDamageCost=1),
        CINDERACE: CardStat(CINDERACE, name="Cinderace", hp=160, minAttackCost=1, maxDamageCost=1),
        WATER: CardStat(WATER, synthetic=True, name="Water", energyType=2)})
    strat = Strategy(roles={MEGA: ["win_condition", "primary_attacker"], CINDERACE: ["accel_source"]},
                     lines=[Line(path=[STARYU, MEGA], payoff=MEGA)])
    p = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    bench = [{"id": CINDERACE, "energies": [], "hp": 160}, {"id": STARYU, "energies": [], "hp": 70}]
    obs = _obs(bench, [{"id": WATER}], [_attach(0, BENCH, 0), _attach(0, BENCH, 1)])   # ->Cinderace, ->Staryu
    t0, t1 = p.explain(obs).options
    assert t0.score == t1.score                                      # genuinely a SCORE tie...
    assert t1.attach_to_needy_line and not t0.attach_to_needy_line   # ...broken by the Line-base flag
    assert p.decide(obs) == [1]                                      # so Staryu (Line base) fed, not Cinderace


NEBULA_BEAM, JETTING_BLOW = 9001, 9002


def _arm_pilot():
    """Real attack records, needed for typed-slot matching. Own builder: adding attacks to the shared
    `_stats()` would move other scores in this file."""
    stats = DictCardStatProvider(
        {MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=210,
                        minAttackCost=1, maxDamageCost=3, evolvesFrom="Staryu",
                        attacks=(JETTING_BLOW, NEBULA_BEAM)),
         WATER: CardStat(WATER, synthetic=True, name="Water", energyType=2, cardType=5),
         IGNITION: CardStat(IGNITION, synthetic=True, name="Ignition", energyType=0, cardType=6)},
        attacks={NEBULA_BEAM: AttackStat(NEBULA_BEAM, damage=210, cost=3, energyTypes=(0, 0, 0)),
                 JETTING_BLOW: AttackStat(JETTING_BLOW, damage=60, cost=1, energyTypes=(0,))})
    return Pilot(Strategy(roles={MEGA: ["win_condition", "primary_attacker"]}), deck=[1] * 60,
                 general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({IGNITION: ignition_tags()}))


def _arm_board(p, energies, hand=()):
    me = {"active": [{"id": MEGA, "energies": list(energies), "hp": 330}], "bench": [],
          "hand": [{"id": c} for c in hand], "prize": [None] * 4}
    obs = {"current": {"players": [me, {"active": [None], "bench": [], "prize": [None] * 6}],
                       "yourIndex": 0, "turn": 6},
           "select": {"context": MAIN, "minCount": 1, "maxCount": 1, "option": []}}
    return p._board(obs, obs["select"], carried=p.carried())


@pytest.mark.req("REQ-GEN-0016")
def test_go_down_swinging_turns_on_only_at_the_biggest_attacks_boundary():
    """`Board.active_arm_available`: a synthetic boundary probe on Nebula Beam's CCC=3."""
    p = _arm_pilot()
    assert _arm_board(p, [WATER, WATER], hand=[WATER]).active_arm_available is True
    assert _arm_board(p, [WATER], hand=[WATER]).active_arm_available is False
    # already armed: CCC is payable with what is ATTACHED -> nothing left for an attach to complete.
    assert _arm_board(p, [WATER, WATER, WATER], hand=[WATER]).active_arm_available is False
    # the boundary is the BUDGET's, not the body's -> no arm without something to attach.
    assert _arm_board(p, [WATER, WATER], hand=[]).active_arm_available is False


@pytest.mark.req("REQ-GEN-0016")
def test_a_hand_ignition_arms_an_evolution_from_zero():
    """Ignition (id 17) "provides {C}{C}{C}" on an Evolution, so ONE attach arms a bare Mega Starmie ex
    for Nebula Beam. The provision is a `provides:N` Function Tag, not a constant in the affordability code."""
    p = _arm_pilot()
    assert _arm_board(p, [], hand=[IGNITION]).active_arm_available is True
    assert _arm_board(p, [], hand=[]).active_arm_available is False   # nothing in hand, nothing armed
