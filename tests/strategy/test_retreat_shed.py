"""The retreat shed is chosen over CARDS, not units (ADR-0100 §8; Issue #297's misread, one layer over).

`_retreat_discard_choice` used to walk a body's ``energies`` one entry at a time. That field is
``list[EnergyType]`` — the UNITS the attached cards provide (`cg/api.py` `Pokemon`) — while a
retreat discards CARDS. The engine settles the shape and this file pins it:
`_pose_retreat_energy` poses one `DISCARD_ENERGY` option **per attached Energy card**, carrying that
card's yield as ``count``, then removes that one card and subtracts its units from what remains.

Verified on recorded NATIVE traces, not from the reimplementation
(`tests/fixtures/parity/v2_ms_mirror_5001.trace.json.gz`, 3339 `DISCARD_ENERGY` frames across the
store):

    frame 128  remainEnergyCost=2   energies [3,0,0,0] (4 units)   energyCards [3,17] (2 cards)
               opt energyIndex=0 count=1      <- Basic {W} Energy
               opt energyIndex=1 count=3      <- Ignition Energy
    frame 129  remainEnergyCost=1   energies [0,0,0]   (3 units)   energyCards [17]   (1 card)
               opt energyIndex=0 count=3      <- pay 1, shed 3: overpay, and forced

Card facts VERIFIED at source (`data/EN_Card_Data.csv` + `src/common/card_functions.json`) — never
recalled:
  * card 3 = Basic {W} Energy, one {W} unit. `EnergyType.WATER` is also 3.
  * card 17 = Ignition Energy, Special: "provides {C} Energy… If this card is attached to an
    Evolution Pokémon, it provides {C}{C}{C} Energy instead" — tags `provides:1`, `provides_evo:3`.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Line, Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

COLORLESS, WATER = 0, 3
WINCON, BENCHED = 900, 901
WATER_E, IGNITION, MYSTERY_E = 3, 17, 199
JETTING = 11                                    # {W}{W}{W} — a fully typed 3-cost payoff

_STATS = {
    WINCON: CardStat(WINCON, name="Wincon", hp=330, megaEx=True, evolvesFrom="Staryu",
                     energyType=WATER, minAttackCost=3, maxDamage=210, maxDamageCost=3,
                     attacks=(JETTING,), retreatCost=1, cardType=0),
    BENCHED: CardStat(BENCHED, name="Benched", hp=90, cardType=0),
    WATER_E: CardStat(WATER_E, name="Basic {W} Energy", cardType=5, energyType=WATER),
    IGNITION: CardStat(IGNITION, name="Ignition Energy", cardType=6, energyType=COLORLESS),
    MYSTERY_E: CardStat(MYSTERY_E, name="Untagged Special Energy", cardType=6,
                        energyType=COLORLESS),
}
_ATTACKS = {JETTING: AttackStat(JETTING, damage=210, cost=3, energyTypes=(WATER, WATER, WATER))}
#: The shipped tags for card 17, copied from `src/common/card_functions.json`. MYSTERY_E carries
#: none — the untagged-Special case the reconciliation must refuse.
_TAGS = {IGNITION: ["discard_eot", "provides:1", "provides_evo:3"]}


#: The same payoff with COLOURLESS slots, so an attached Ignition actually fills something. Both
#: shapes are real and they answer differently, which is the point: a colourless unit is worth
#: nothing to a fully typed cost and worth a slot to a partly colourless one.
_ATTACKS_COLOURLESS = {JETTING: AttackStat(JETTING, damage=210, cost=3,
                                           energyTypes=(WATER, COLORLESS, COLORLESS))}


def _pilot(*, colourless_payoff: bool = False):
    return Pilot(Strategy(roles={WINCON: ["win_condition", "primary_attacker"]},
                          lines=[Line(path=[WINCON], payoff=WINCON, role="win_condition")]),
                 deck=[WATER_E] * 8 + [IGNITION] * 4 + [WINCON] * 4,
                 general_strategy=GENERAL_STRATEGY,
                 stats=DictCardStatProvider(
                     _STATS, attacks=_ATTACKS_COLOURLESS if colourless_payoff else _ATTACKS),
                 functions=CardFunctions(_TAGS))


def _active(*cards):
    """My Active carrying ``cards``, in the engine's real two-field shape. Ignition is on an
    EVOLUTION here (Wincon has `evolvesFrom`), so it provides {C}{C}{C} — three units."""
    provides = {WATER_E: (WATER,), IGNITION: (COLORLESS,) * 3, MYSTERY_E: (COLORLESS,) * 2}
    return {"id": WINCON, "serial": 1, "hp": 330, "maxHp": 330,
            "energies": [u for c in cards for u in provides[c]],
            "energyCards": [{"id": c, "serial": 10 + i} for i, c in enumerate(cards)],
            "tools": [], "preEvolution": []}


# ── the card/unit attribution ──────────────────────────────────────────────────────────────────

def test_yields_pair_each_card_with_what_it_provides():
    p = _pilot()
    assert p._attached_energy_yields(_active(WATER_E, IGNITION)) == ((WATER_E, 1), (IGNITION, 3))


def test_an_untagged_special_refuses_the_attribution():
    """Fail-CLOSED: no `provides:N` tag, no card-level claim — the caller falls back and charges no
    resource premium rather than guessing which card left."""
    assert _pilot()._attached_energy_yields(_active(MYSTERY_E)) is None


def test_an_attribution_that_does_not_reconcile_is_refused():
    """The per-card yields must sum to what the engine reported in `energies`. A body claiming one
    Ignition but only one unit is a shape we cannot read, so we make no claim about it."""
    body = _active(IGNITION)
    body["energies"] = [COLORLESS]                  # 1 unit, but the card provides 3
    assert _pilot()._attached_energy_yields(body) is None


# ── the shed itself ────────────────────────────────────────────────────────────────────────────

def test_a_card_is_indivisible_and_overpay_is_visible():
    """Frame 129's board: only an Ignition attached, retreat cost 1. The engine's one option sheds
    all three units. The old per-unit search took exactly one and priced the retreat at one."""
    p = _pilot()
    after, discarded = p._retreat_discard_choice(_active(IGNITION), 1)
    assert discarded == (IGNITION,)
    assert after["energies"] == []                  # all 3 units go — not 1
    assert [c["id"] for c in after["energyCards"]] == []


def test_the_shed_prefers_the_single_card_that_pays_alone():
    """Frame 128's board — Basic {W} + Ignition — against a cost of 3. Shedding the Ignition ALONE
    is legal (3 >= 3) and keeps the {W} that the payoff's `{W}{W}{W}` actually needs. Greedy
    cheapest-first would take the {W} and then still need the Ignition, shedding everything."""
    p = _pilot()
    after, discarded = p._retreat_discard_choice(_active(WATER_E, IGNITION), 3)
    assert discarded == (IGNITION,)
    assert after["energies"] == [WATER]
    assert [c["id"] for c in after["energyCards"]] == [WATER_E]


def test_an_unreachable_set_is_never_chosen():
    """`sum(S) - max(S) < cost` is the engine's own stopping rule: it stops posing the moment the
    remaining cost hits zero. Three single-unit Energy therefore cannot all be dumped on a cost of
    2 — the third option is never offered."""
    p = _pilot()
    after, discarded = p._retreat_discard_choice(_active(WATER_E, WATER_E, WATER_E), 2)
    assert len(discarded) == 2 and set(discarded) == {WATER_E}
    assert after["energies"] == [WATER]             # exactly one survives


def test_a_zero_cost_retreat_sheds_nothing():
    p = _pilot()
    after, discarded = p._retreat_discard_choice(_active(WATER_E, IGNITION), 0)
    assert discarded == () and after["energies"] == _active(WATER_E, IGNITION)["energies"]


def test_a_cost_beyond_the_board_sheds_everything():
    p = _pilot()
    after, discarded = p._retreat_discard_choice(_active(WATER_E), 5)
    assert discarded == (WATER_E,) and after["energies"] == []


def test_an_unreadable_body_falls_back_and_claims_no_cards():
    """No attribution -> the per-unit fallback still prices the right NUMBER of units leaving, but
    names no card, so the resource premium below makes no claim it cannot support."""
    p = _pilot()
    after, discarded = p._retreat_discard_choice(_active(MYSTERY_E), 1)
    assert discarded == ()
    assert len(after["energies"]) == 1              # 2 units, one unit paid


# ── the resource premium reads CARD ids ────────────────────────────────────────────────────────

def _obs(active):
    return {"current": {"players": [
        {"active": [active], "bench": [{"id": BENCHED, "serial": 2, "hp": 90, "maxHp": 90,
                                        "energies": [], "energyCards": [], "tools": [],
                                        "preEvolution": []}],
         "hand": [], "handCount": 0, "discard": [], "prize": [None] * 4, "deckCount": 30,
         "poisoned": False, "burned": False, "asleep": False, "paralyzed": False,
         "confused": False},
        {"active": [], "bench": [], "hand": None, "handCount": 5, "discard": [],
         "prize": [None] * 6, "deckCount": 40,
         "poisoned": False, "burned": False, "asleep": False, "paralyzed": False,
         "confused": False}],
        "yourIndex": 0, "turn": 5}, "logs": []}


def test_the_premium_prices_the_card_that_left_not_a_unit_code():
    """ADR-0069 §5c charges worth ABOVE a reusable Basic, so only a one-shot is nudged. Shedding an
    Ignition must consult card 17. It used to consult the UNIT codes `[0, 0, 0]` — card 0, which
    does not exist — so the one-shot this premium exists to charge for cost exactly nothing."""
    p = _pilot()
    legs = p._retreat_cost_legs(_obs(_active(IGNITION)))
    assert legs["resource_premium"] == pytest.approx(
        0.05 * max(0.0, p._role_value(IGNITION) - _energy_tier()))
    assert legs["resource_premium"] > 0.0


def test_a_plain_basic_still_pays_no_premium():
    """The premium is worth ABOVE a reusable Basic — a Basic Energy is exactly the floor."""
    legs = _pilot()._retreat_cost_legs(_obs(_active(WATER_E)))
    assert legs["resource_premium"] == pytest.approx(0.0)


def test_the_build_legs_see_the_whole_card_leave():
    """`build_after` is read off the body the shed really produces, so an Ignition paying a ONE-cost
    retreat shows all three units gone — the overpay, priced.

    Needs a payoff with colourless slots, or the Ignition fills nothing and losing it is free
    whichever model you use (that is exactly what the `{W}{W}{W}` pilot above shows, and why the
    shed picks the Ignition there). On `{W}{C}{C}` its three units fill two real slots, so the whole
    card leaving is a build cliff: 2/3 matched -> nothing. The old per-unit shed took ONE unit, left
    two colourless behind, and reported the same 2/3 — a retreat priced at zero build."""
    p = _pilot(colourless_payoff=True)
    legs = p._retreat_cost_legs(_obs(_active(IGNITION)))
    assert legs["build_before"] == pytest.approx((2 / 3) ** 2 * 210)
    assert legs["build_after"] == 0.0


def _energy_tier():
    from common.card_worth import ENERGY_TIER
    return ENERGY_TIER
