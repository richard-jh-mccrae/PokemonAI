"""The TOOL attach channel (Issue #423) — what a Pokémon Tool that moves a Retreat Cost is worth.

`_attach_value` used to refuse every Tool at its guard, and the composer prices one at exactly 0.0
(`board_delta._retreat` writes only the allowance, so a retreat has no consequence to score), which
left nothing able to tell the Active from a benched body. The channel differences ADR-0100's shipped
retreat verdict and clamps the answer into ADR-0069 §1's Retreat Equity band.

Style A builds boards by hand; Style B replays the corpus frames that ruled on an Air Balloon. Card
facts are VERIFIED at `data/EN_Card_Data.csv`, never recalled.
"""
import sys
from pathlib import Path

import pytest

from common.cards import CardFunctions
from common.pilot import Pilot, _ATTACH_RETREAT_EQUITY
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Line, Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY
from corpus_helpers import corpus_records, replay_agent

REPO = Path(__file__).resolve().parents[2]

ATTACH, HAND, ACTIVE, BENCH, MAIN, END = 8, 2, 4, 5, 0, 14
_TOOL, _BASIC_ENERGY = 2, 5
WATER, FIGHTING = 3, 6

MEGA, STARYU = 1031, 1030
#: NO Pokémon in this pool prints Retreat 0 (the CSV's Retreat column holds only 1-4 and n/a), so
#: the free-retreating holder MUST be synthetic — a non-pool id and a non-pool name, deliberately.
FREE_RETREATER = 9001
W_ENERGY = 3
JETTING, NEBULA, WATER_GUN, GNAW = 101, 102, 103, 107

#: Four REAL Tools, one per shape the channel must tell apart — reduction, SURCHARGE, conditional
#: grant, no-mobility. Every parsed field below is checked against `data/EN_Card_Data.csv`.
BALLOON, GEMSTONE, RESCUE_BOARD, CAPE = 1174, 1166, 1157, 1159


def _stats():
    return DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=210,
                       minCostDamage=120, minAttackCost=1, maxDamageCost=3, evolvesFrom="Staryu",
                       retreatCost=2, attacks=(JETTING, NEBULA)),
        STARYU: CardStat(STARYU, name="Staryu", hp=70, maxDamage=20, minCostDamage=20,
                         minAttackCost=1, maxDamageCost=1, retreatCost=1, attacks=(WATER_GUN,)),
        FREE_RETREATER: CardStat(FREE_RETREATER, synthetic=True, name="Free-Retreat Basic", hp=60,
                                 maxDamage=10, minCostDamage=10, minAttackCost=1, maxDamageCost=1,
                                 retreatCost=0, attacks=(GNAW,)),
        W_ENERGY: CardStat(W_ENERGY, synthetic=True, name="Water", cardType=_BASIC_ENERGY,
                           energyType=WATER),
        BALLOON: CardStat(BALLOON, name="Air Balloon", cardType=_TOOL, retreatReduction=2),
        GEMSTONE: CardStat(GEMSTONE, name="Gravity Gemstone", cardType=_TOOL, retreatReduction=-1),
        RESCUE_BOARD: CardStat(RESCUE_BOARD, name="Rescue Board", cardType=_TOOL,
                               retreatReduction=1, retreatFreeAtHp=30),
        CAPE: CardStat(CAPE, name="Hero’s Cape", cardType=_TOOL, aceSpec=True, hpBonus=100),
    }, attacks={
        JETTING: AttackStat(JETTING, damage=120, cost=1, energyTypes=(WATER,)),
        NEBULA: AttackStat(NEBULA, damage=210, cost=3, energyTypes=(0, 0, 0)),
        WATER_GUN: AttackStat(WATER_GUN, damage=20, cost=1, energyTypes=(WATER,)),
        GNAW: AttackStat(GNAW, damage=10, cost=1, energyTypes=(0,)),
    })


def _pilot(*, attach_value=True, promote_retreat_value=True):
    strat = Strategy(roles={MEGA: ["win_condition", "primary_attacker"], STARYU: ["starter"]},
                     lines=[Line(path=[STARYU, MEGA], payoff=MEGA)])
    return Pilot(strat, deck=[1] * 60, general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 functions=CardFunctions({}), attach_value=attach_value,
                 promote_retreat_value=promote_retreat_value)


def _poke(cid, *, energy=0, hp=None, tools=()):
    stat = _stats().get(cid)
    return {"id": cid, "hp": stat.hp if hp is None else hp, "maxHp": stat.hp,
            "energies": [WATER] * energy,
            "energyCards": [{"id": W_ENERGY} for _ in range(energy)],
            "tools": [{"id": t} for t in tools]}


def _attach(hand_idx, area, in_idx):
    return {"type": ATTACH, "area": HAND, "index": hand_idx,
            "inPlayArea": area, "inPlayIndex": in_idx}


def _obs(active, bench, hand, options, *, turn=6):
    return {"current": {"players": [{"active": [active], "bench": list(bench), "hand": hand},
                                    {"active": [_poke(STARYU, energy=1)], "bench": []}],
                        "yourIndex": 0, "turn": turn},
            "select": {"context": MAIN, "minCount": 1, "maxCount": 1, "option": options}}


def _rows(pilot, obs):
    """`{option index: row}` off the decision's own working — the wire, not a private call."""
    working = pilot.explain(obs).attach_working
    return ({r["i"]: r for r in working["eq"]}, working["abstained"]) if working else ({}, 0)


# ── Style A: the channel's own rulings ────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-TOOL-ATTACH-0001")
def test_a_tool_that_moves_no_retreat_cost_still_abstains():
    """Hero's Cape grants HP and no mobility. ADR-0028's survival-turns math has had no owner since
    Issue #386 deleted the Tool doctrine, and pricing its CARD without its CREDIT is ADR-0127's trap."""
    p = _pilot()
    obs = _obs(_poke(MEGA, energy=2), [_poke(STARYU)], [{"id": CAPE}, {"id": W_ENERGY}],
               [_attach(0, ACTIVE, 0), _attach(0, BENCH, 0), _attach(1, ACTIVE, 0)])
    rows, abstained = _rows(p, obs)
    assert abstained == 2 and set(rows) == {2}     # only the Energy earned a row


@pytest.mark.req("REQ-TOOL-ATTACH-0002")
def test_the_active_is_priced_and_every_benched_recipient_is_zero():
    """Only the Active pays a Retreat Cost, so only there does a retreat Tool buy anything now."""
    p = _pilot()
    obs = _obs(_poke(MEGA, energy=2), [_poke(STARYU, energy=1), _poke(STARYU)], [{"id": BALLOON}],
               [_attach(0, ACTIVE, 0), _attach(0, BENCH, 0), _attach(0, BENCH, 1)])
    rows, abstained = _rows(p, obs)
    assert abstained == 0, "a retreat Tool is PRICED, not abstained — 0.0 and silence differ"
    assert rows[0]["retreat_equity"] > 0.0
    assert rows[1]["retreat_equity"] == 0.0 and rows[2]["retreat_equity"] == 0.0


@pytest.mark.req("REQ-TOOL-ATTACH-0002")
def test_the_benched_zero_is_arithmetic_and_not_an_area_gate():
    """The bench zero is not "this board prices nothing": the oracle DISCRIMINATES here — equipping
    the Active moves it — and a bench recipient still differences to 0, because both its legs read A."""
    p = _pilot()
    obs = _obs(_poke(MEGA, energy=2), [_poke(MEGA, energy=3)], [{"id": BALLOON}],
               [_attach(0, ACTIVE, 0), _attach(0, BENCH, 0)])
    rows, _ = _rows(p, obs)
    active = p._my_active(obs)
    board = p._board(obs, obs["select"])
    equipped = dict(active, tools=[{"id": BALLOON}])
    bare, armed = (p._retreat_option_value(obs, board, active),
                   p._retreat_option_value(obs, board, equipped))
    assert armed != bare, "the oracle is inert on this board, so the bench 0.0 would prove nothing"
    assert rows[0]["retreat_equity"] > 0.0 and rows[1]["retreat_equity"] == 0.0


@pytest.mark.req("REQ-TOOL-ATTACH-0003")
def test_a_holder_that_already_retreats_free_gains_nothing():
    """A holder printing Retreat 0 gives the Tool no cost to move — the emergent form of the deleted
    `hold-the-retreat-tool-with-no-retreat` rung, by arithmetic rather than by a rung."""
    p = _pilot()
    obs = _obs(_poke(FREE_RETREATER), [_poke(STARYU, energy=1)], [{"id": BALLOON}],
               [_attach(0, ACTIVE, 0)])
    rows, _ = _rows(p, obs)
    assert rows[0]["retreat_equity"] == 0.0


@pytest.mark.req("REQ-TOOL-ATTACH-0004")
def test_a_surcharge_tool_prices_negative():
    """`retreatReduction` is SIGNED since Issue #306 — Gravity Gemstone makes retreating DEARER, and
    the decider is allowed to say 'attach nothing' and mean it."""
    p = _pilot()
    # A destination worth retreating INTO, so the without-Gemstone leg is positive and there is
    # something for the surcharge to take away: Retreat 2 payable now, 3 once the Gemstone lands.
    obs = _obs(_poke(MEGA, energy=2), [_poke(MEGA, energy=3)], [{"id": GEMSTONE}],
               [_attach(0, ACTIVE, 0)])
    rows, _ = _rows(p, obs)
    assert rows[0]["retreat_equity"] < 0.0 and rows[0]["tactical"] < 0.0
    assert rows[0]["retreat_equity"] >= -_ATTACH_RETREAT_EQUITY     # signed, and inside the band


@pytest.mark.req("REQ-TOOL-ATTACH-0005")
def test_rescue_boards_conditional_grant_is_read_on_the_real_body():
    """Rescue Board's −1 alone leaves Mega Starmie ex at Retreat 1 with no Energy to pay it; its
    `retreatFreeAtHp` clause is what makes the retreat legal, and only the REAL HP can say so."""
    p = _pilot()
    healthy = _obs(_poke(MEGA), [_poke(STARYU, energy=1)], [{"id": RESCUE_BOARD}],
                   [_attach(0, ACTIVE, 0)])
    damaged = _obs(_poke(MEGA, hp=30), [_poke(STARYU, energy=1)], [{"id": RESCUE_BOARD}],
                   [_attach(0, ACTIVE, 0)])
    assert _rows(p, healthy)[0][0]["retreat_equity"] == 0.0        # still cannot pay the last {C}
    assert _rows(_pilot(), damaged)[0][0]["retreat_equity"] > 0.0  # the clause grants a free retreat


@pytest.mark.req("REQ-TOOL-ATTACH-0006")
def test_the_value_is_clamped_into_the_retreat_equity_band():
    """ADR-0100's verdict says WHETHER; ADR-0069 §1's band says WHAT IT IS WORTH. Uncapped, an
    unlocked retreat outbids a ruled Energy attach — the measurement is ADR-0135's."""
    p = _pilot()
    obs = _obs(_poke(MEGA, energy=2), [_poke(MEGA, energy=3)], [{"id": BALLOON}],
               [_attach(0, ACTIVE, 0)])
    rows, _ = _rows(p, obs)
    assert 0.0 < rows[0]["retreat_equity"] <= _ATTACH_RETREAT_EQUITY


@pytest.mark.req("REQ-TOOL-ATTACH-0007")
def test_both_kill_switches_reach_the_channel():
    """`attach_value` gates the decider; `promote_retreat_value` gates the equation it CONSUMES — a
    decider flag does not gate a shared-oracle swap, so the retreat decider's own flag must reach here."""
    obs = _obs(_poke(MEGA, energy=2), [_poke(MEGA, energy=3)], [{"id": BALLOON}],
               [_attach(0, ACTIVE, 0), {"type": END}])

    def _tactical(pilot):
        return pilot.explain(obs).options[0].tactical

    assert _tactical(_pilot()) > 0.0                               # the channel is live by default
    assert _tactical(_pilot(attach_value=False)) == 0.0            # the decider's own flag
    assert _tactical(_pilot(promote_retreat_value=False)) == 0.0   # the equation it CONSUMES


@pytest.mark.req("REQ-TOOL-ATTACH-0001")
def test_a_misspelled_leg_raises_rather_than_reading_as_its_zero():
    """Both channels build through one row, so a typo would add a junk key and leave the real leg at
    0.0 — an assertion reading it would pass on the zero. The contract has to bite at the boundary."""
    from common.deciders.attach import _attach_row
    assert _attach_row(retreat_equity=1.0)["retreat_equity"] == 1.0
    with pytest.raises(KeyError):
        _attach_row(retreat_equty=1.0)


# ── Style B: the corpus frames that ruled on an Air Balloon ───────────────────────────────────────

#: Every ruled MAIN frame offering an Air Balloon attach. The first three rule it ONTO THE ACTIVE;
#: `ml f64` rules an Energy attach instead, and is the guard the UNCAPPED channel failed.
_BALLOON_FRAMES = [("85058574", 87), ("85709280", 42), ("85709280", 55), ("84071010", 64)]


@pytest.fixture(scope="module")
def _corpus_pilot():
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    return _build_pilot("mega_lucario")[0]


@pytest.mark.req("REQ-TOOL-ATTACH-0008")
@pytest.mark.parametrize("episode,frame", _BALLOON_FRAMES)
def test_the_ruled_balloon_frames_decide_the_way_the_human_ruled(_corpus_pilot, episode, frame):
    """The whole point, end to end — the channel's reason for existing, over the corpus."""
    rec = corpus_records([(episode, frame)])[0]
    assert replay_agent(rec) == "mega_lucario"
    decision = _corpus_pilot.explain(rec.obs)
    assert decision.chosen[0] in rec.correct


#: The Balloon frames whose ruling is a DIFFERENT play. A channel that pays for mobility nobody wants
#: would take these over, and `wasted_resource` is the human's own name for that blunder.
_NON_BALLOON_FRAMES = [("86090147", 22), ("85058051", 4), ("86090666", 9)]


@pytest.mark.req("REQ-TOOL-ATTACH-0009")
@pytest.mark.parametrize("episode,frame", _NON_BALLOON_FRAMES)
def test_the_channel_does_not_take_over_a_frame_that_wants_another_play(_corpus_pilot, episode, frame):
    """`86090147-22` rules a RETREAT and `85058051-4` an Ultra Ball; on both, the Balloon buys a
    retreat worth nothing, so the mobility difference is 0 and the pick stays where it was."""
    rec = corpus_records([(episode, frame)])[0]
    rows = {r["i"]: r for r in ((_corpus_pilot.explain(rec.obs).attach_working or {}).get("eq") or ())}
    balloons = [i for i, r in rows.items() if r["energy"] == BALLOON]
    assert balloons, f"{episode}-{frame} no longer offers a Balloon — the guard has stopped guarding"
    assert all(rows[i]["retreat_equity"] == 0.0 for i in balloons)
    assert _corpus_pilot.explain(rec.obs).chosen[0] not in balloons


@pytest.mark.req("REQ-TOOL-ATTACH-0008")
def test_the_active_outscores_every_benched_recipient_on_the_ruled_frames(_corpus_pilot):
    """The target-selection claim, stated over the corpus rather than a hand-built board."""
    for episode, frame in _BALLOON_FRAMES[:3]:
        rec = corpus_records([(episode, frame)])[0]
        rows = {r["i"]: r for r in (_corpus_pilot.explain(rec.obs).attach_working or {})["eq"]}
        balloons = {i: r for i, r in rows.items() if r["energy"] == BALLOON}
        assert len(balloons) > 1, f"{episode}-{frame} poses only one Balloon recipient"
        on_active = [r for i, r in balloons.items() if i in rec.correct]
        assert len(on_active) == 1, f"{episode}-{frame}: the ruled option is not a Balloon"
        assert all(r["tactical"] < on_active[0]["tactical"]
                   for i, r in balloons.items() if i not in rec.correct)
