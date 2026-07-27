"""Attach DISCIPLINE: concentrate Energy on one win-condition, and prefer a reusable Basic over a
discard-EOT burst (the b7e483a misattachment blunders).

Both behaviours OUTLIVED the rungs that used to carry them (#139, ADR-0069): concentrate is now a
consequence of the CONVEX typed build (finishing a started carrier is worth more than starting a
fresh one, because the marginal of the k-th Energy rises with k), and reusable-over-burst is the
decider's resource tie-break plus its evaporation loss. So these pins assert the DECISION and the
axes that produced it, not which rung fired.
"""
import pytest

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
    # Mega Starmie ex: cheapest attack 1, biggest attack CCC=3 -> "under max" until 3 Energy
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
                 functions=funcs)


def _obs(bench, hand, options):
    me = {"active": [None], "bench": bench, "hand": hand}
    return {"current": {"players": [me, {"active": [None], "bench": []}], "yourIndex": 0, "turn": 6},
            "select": {"context": MAIN, "minCount": 1, "maxCount": 1, "option": options}}


@pytest.mark.req("REQ-GEN-0016")
def test_concentrate_loads_the_most_built_wincon_over_a_bare_body():
    # Bench: a Mega on 2 Energy (closest to its CCC payoff), a bare Staryu. 3rd Energy tops up
    # the Mega — concentrate, don't spread onto the Staryu
    p = _pilot()
    bench = [{"id": MEGA, "energies": [WATER, WATER], "hp": 330}, {"id": STARYU, "energies": [], "hp": 70}]
    hand = [{"id": WATER}]
    opts = [_attach(0, BENCH, 0), _attach(0, BENCH, 1)]               # -> the 2e Mega, -> the bare Staryu
    obs = _obs(bench, hand, opts)
    assert p._board(obs, obs["select"]).priority_wincon_slot == (BENCH, 0)
    dec = p.explain(obs)
    rows = {r["i"]: r for r in dec.attach_working["eq"]}
    assert rows[0]["build"] > rows[1]["build"]                        # convexity, not a rung
    assert p.decide(obs) == [0]                                       # load the most-built Mega


@pytest.mark.req("REQ-GEN-0016")
def test_prefer_reusable_basic_over_ignition_onto_the_wincon():
    # A Water and an Ignition both top up the Active Mega; prefer reusable Water, save the burst
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
    p = Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=stats, functions=funcs)
    # bench: off-line Cinderace at LOWER index, Line base Staryu after — both bare/needy
    bench = [{"id": CINDERACE, "energies": [], "hp": 160}, {"id": STARYU, "energies": [], "hp": 70}]
    obs = _obs(bench, [{"id": WATER}], [_attach(0, BENCH, 0), _attach(0, BENCH, 1)])   # ->Cinderace, ->Staryu
    t0, t1 = p.explain(obs).options
    assert t0.score == t1.score                                      # genuinely a SCORE tie...
    assert t1.attach_to_needy_line and not t0.attach_to_needy_line   # ...broken by the Line-base flag
    assert p.decide(obs) == [1]                                      # so Staryu (Line base) fed, not Cinderace


NEBULA_BEAM, JETTING_BLOW = 9001, 9002


def _arm_pilot():
    """A pilot whose Mega Starmie ex carries REAL attack records. The retired count matcher needed
    only `maxDamageCost`; the oracle that replaced it (#142) matches typed slots, so the boundary
    probe now has to state the attacks it is a boundary of. Own builder — `_stats()` is shared by
    the rest of this file and adding attacks there would move other scores."""
    stats = DictCardStatProvider(
        {MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=210,
                        minAttackCost=1, maxDamageCost=3, evolvesFrom="Staryu",
                        attacks=(JETTING_BLOW, NEBULA_BEAM)),
         WATER: CardStat(WATER, name="Water", energyType=2, cardType=5),
         IGNITION: CardStat(IGNITION, name="Ignition", energyType=0, cardType=6)},
        attacks={NEBULA_BEAM: AttackStat(NEBULA_BEAM, damage=210, cost=3, energyTypes=(0, 0, 0)),
                 JETTING_BLOW: AttackStat(JETTING_BLOW, damage=60, cost=1, energyTypes=(0,))})
    return Pilot(Strategy(roles={MEGA: ["win_condition", "primary_attacker"]}), deck=[1] * 60,
                 general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({IGNITION: ["discard_eot"]}))


def _arm_board(p, energies, hand=()):
    me = {"active": [{"id": MEGA, "energies": list(energies), "hp": 330}], "bench": [],
          "hand": [{"id": c} for c in hand], "prize": [None] * 4}
    obs = {"current": {"players": [me, {"active": [None], "bench": [], "prize": [None] * 6}],
                       "yourIndex": 0, "turn": 6},
           "select": {"context": MAIN, "minCount": 1, "maxCount": 1, "option": []}}
    return p._board(obs, obs["select"], carried=p.carried())


@pytest.mark.req("REQ-GEN-0016")
def test_go_down_swinging_turns_on_only_at_the_biggest_attacks_boundary():
    """`Board.active_arm_available` — the go-down-swinging read the decider's survival gate and the
    Lunar-Cycle famine share (ms 85163079 f51). Restated at the BOARD seam: the private count
    matcher it used to call is deleted (#142), and a pin on a deleted predicate is no pin at all.
    Guards the un-fixtured counter-case ep83037962 f48 (1W->2W, still short of Nebula Beam CCC=3) —
    a synthetic boundary probe, no real replay frame."""
    p = _arm_pilot()
    # f51 shape: 2 Water attached, a third in hand -> the Budget completes CCC -> arm and swing.
    assert _arm_board(p, [WATER, WATER], hand=[WATER]).active_arm_available is True
    # f48 shape: 1 Water attached, one in hand -> 2 < CCC=3 -> don't overbuild for a turn that won't come.
    assert _arm_board(p, [WATER], hand=[WATER]).active_arm_available is False
    # already armed: CCC is payable with what is ATTACHED -> nothing left for an attach to complete.
    assert _arm_board(p, [WATER, WATER, WATER], hand=[WATER]).active_arm_available is False
    # nothing to attach: the boundary is the BUDGET's, not the body's -> no arm without one.
    assert _arm_board(p, [WATER, WATER], hand=[]).active_arm_available is False


@pytest.mark.req("REQ-GEN-0016")
def test_a_hand_special_energy_does_not_arm_the_active():
    """A NARROWING taken knowingly (#142). The retired matcher hardcoded "a `discard_eot` burst onto
    an Evolution provides 3", so an Ignition in hand armed a bare Mega. The Attach Budget's manual
    leg reads TYPED BASIC Energy only, so a Special Energy contributes zero — fail-closed per
    ADR-0067, and the honest fix is an Effect-Clause row for its provision, not a second matcher.
    INERT on every shipped deck: none of the five agent decklists runs a Special Energy (verified
    against `data/EN_Card_Data.csv` card types), so this asserts the boundary rather than a loss."""
    p = _arm_pilot()
    assert _arm_board(p, [], hand=[IGNITION]).active_arm_available is False
