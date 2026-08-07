"""The **provision seam** — `CombatMath.provision_codes` (Issue #418, ADR-0125).

Ignition Energy (17) is the ONLY shipped card carrying either ``discard_eot`` or ``provides_evo``,
and it carries both — so a rule keyed on the wrong predicate reads correctly on every card that
exists today. `test_the_two_cases_the_coincidence_hides` runs the two SYNTHETIC cards that separate
them, because no shipped card can.

The second half is the ``energies``-vs-``energyCards`` split (Issue #297): card 17 is not an
``EnergyType``, so `unit_colours` resolves it to the empty set — WILD, which pays every slot.
"""
from __future__ import annotations

import json
from pathlib import Path

from card_facts import ignition_tags                    # the committed Ignition Energy tags, ONE copy
from common.board_delta import Unmodellable, units_for_cards
from common.cards import CardFunctions
from common.effects import CardEffects
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy.combat import WILD_CODE, CombatMath, unit_colours

REPO = Path(__file__).resolve().parents[2]

STARYU, M_STARMIE = 1030, 1031      # Basic 70 HP / Stage 1 from Staryu, 330 HP
JETTING_BLOW, NEBULA_BEAM = 51, 52  # {W} 120 / ●●● 210 — card facts at `data/EN_Card_Data.csv` 1031
IGNITION, BOOMERANG, TELEPATH = 17, 9, 19
WATER_ENERGY = 3                    # Basic {W} Energy — the card whose id EQUALS its EnergyType
COLORLESS, WATER, PSYCHIC = 0, 3, 5

#: Two cards that do not exist, each splitting one of the predicates the shipped pool welds together:
#: `EVO_ONLY` provides 3 on an Evolution and never expires; `BURST_2` expires and provides 2, not 3.
EVO_ONLY, BURST_2 = 9001, 9002


def _combat(tags, *, stats=None):
    base = {
        STARYU: CardStat(STARYU, name="Staryu", hp=70, energyType=WATER,
                         attacks=(JETTING_BLOW,)),
        M_STARMIE: CardStat(M_STARMIE, name="Mega Starmie ex", hp=330, energyType=WATER,
                            megaEx=True, evolvesFrom="Staryu",
                            attacks=(JETTING_BLOW, NEBULA_BEAM)),
        WATER_ENERGY: CardStat(WATER_ENERGY, name="Basic {W} Energy", cardType=5, energyType=WATER),
        IGNITION: CardStat(IGNITION, name="Ignition Energy", cardType=6, energyType=COLORLESS),
        BOOMERANG: CardStat(BOOMERANG, name="Boomerang Energy", cardType=6, energyType=COLORLESS),
        TELEPATH: CardStat(TELEPATH, name="Telepath Psychic Energy", cardType=6, energyType=PSYCHIC),
        EVO_ONLY: CardStat(EVO_ONLY, synthetic=True, name="(synthetic) evo-only Energy",
                           cardType=6, energyType=COLORLESS),
        BURST_2: CardStat(BURST_2, synthetic=True, name="(synthetic) two-unit burst",
                          cardType=6, energyType=COLORLESS),
    }
    base.update(stats or {})
    attacks = {JETTING_BLOW: AttackStat(JETTING_BLOW, damage=120, cost=1, energyTypes=(WATER,)),
               NEBULA_BEAM: AttackStat(NEBULA_BEAM, damage=210, cost=3, energyTypes=(0, 0, 0))}
    return CombatMath(DictCardStatProvider(base, attacks=attacks),
                      functions=CardFunctions(tags), transients=None, effects=CardEffects({}))


#: The REAL tags, as committed; Ignition's come from `tests/card_facts.py` and are asserted against
#: the store below rather than trusted.
_REAL = {IGNITION: ignition_tags(),
         BOOMERANG: ["provides:1"], TELEPATH: ["provides:1", "search"]}


def _stat(c, cid):
    return c._card_stat(cid)


# ───────────────────────────────────────────────────────────── the ground truth, re-measured
def test_the_shipped_pool_welds_discard_eot_to_provides_evo():
    """Asserted off the committed store so a new card breaks THIS file instead of the Pilot: a card
    carrying one predicate without the other ends the coincidence this module's premise rests on."""
    table = json.loads((REPO / "src" / "common" / "card_functions.json").read_text(encoding="utf-8"))
    provides, evo, burst = set(), set(), set()
    for cid, tags in table.items():
        for tag in tags:
            if str(tag).startswith("provides:"):
                provides.add(int(cid))
            if str(tag).startswith("provides_evo:"):
                evo.add(int(cid))
            if tag == "discard_eot":
                burst.add(int(cid))
    assert provides == {BOOMERANG, IGNITION, TELEPATH}
    assert evo == burst == {IGNITION}, (
        "the pool's provides_evo / discard_eot populations no longer coincide — re-read the new "
        "card; the seam handles it, but this file's premise has changed")


def test_the_committed_tags_are_what_the_shared_fixture_claims():
    """`tests/card_facts.IGNITION_TAGS` is a LITERAL, not a read of the store — a constant that
    loaded the store could only ever agree with it, so the literal is checked here instead."""
    real = CardFunctions.load()
    for cid, tags in _REAL.items():
        assert sorted(real.tags(cid)) == sorted(tags)


# ──────────────────────────────────────────────────────────────────── the seam's three answers
def test_a_basic_energy_is_one_unit_of_its_own_colour():
    c = _combat(_REAL)
    assert c.provision_codes(WATER_ENERGY, _stat(c, STARYU)) == (WATER,)
    assert c.provision_codes(WATER_ENERGY, _stat(c, M_STARMIE)) == (WATER,)


def test_ignition_is_one_colourless_on_a_basic_and_three_on_an_evolution():
    """Card 17 prints *"provides {C}… if attached to an Evolution Pokémon, {C}{C}{C} instead"*, so
    the HOLDER is the argument: the provision is a property of the holder as much as of the card."""
    c = _combat(_REAL)
    assert c.provision_codes(IGNITION, _stat(c, STARYU)) == (COLORLESS,)
    assert c.provision_codes(IGNITION, _stat(c, M_STARMIE)) == (COLORLESS,) * 3


def test_a_tool_claims_zero_units_rather_than_making_no_claim():
    """A Pokémon Tool rides ``OptionType.ATTACH`` as an Energy does. ``()`` is a CLAIM (provides
    nothing); ``None`` is *"I cannot read this"*."""
    tool = {8001: CardStat(8001, synthetic=True, name="Air Balloon", cardType=2, retreatReduction=2)}
    c = _combat(_REAL, stats=tool)
    assert c.provision_codes(8001, _stat(c, M_STARMIE)) == ()
    assert c.provision_codes_or_floor(8001, _stat(c, M_STARMIE)) == ()


def test_an_untagged_special_energy_is_unreadable_not_zero():
    """Fail-CLOSED (ADR-0067): ``None`` and ``()`` must not be confused — zero units is a real,
    plausible board that under-reports the attach, so the apply seam refuses rather than writing it."""
    c = _combat({IGNITION: ["discard_eot"]})
    assert c.provision_codes(IGNITION, _stat(c, M_STARMIE)) is None


def test_the_floor_is_one_unit_and_never_the_hardcodes_guess_at_three():
    """The DECIDER's degradation: ``None`` becomes ONE unit, of the card's own colour or WILD. Never
    three — an unreadable card must not inherit the ``discard_eot``-shaped guess."""
    c = _combat({IGNITION: ["discard_eot"]})
    assert c.provision_codes_or_floor(IGNITION, _stat(c, M_STARMIE)) == (COLORLESS,)
    assert c.provision_codes_or_floor(None, _stat(c, M_STARMIE)) == (WILD_CODE,)
    assert unit_colours(WILD_CODE) == frozenset(), "the unknown-colour floor must read WILD"


# ─────────────────────────────────────── acceptance 5: the two cases the shipped pool cannot show
def test_the_two_cases_the_coincidence_hides():
    """Two SYNTHETIC cards, each splitting one half of the weld the shipped pool enforces. Neither
    exists, which is the whole argument for the seam: no test over the shipped pool can catch this."""
    c = _combat({**_REAL,
                 EVO_ONLY: ["provides:1", "provides_evo:3"],          # no expiry rider
                 BURST_2: ["discard_eot", "provides:1", "provides_evo:2"]})
    basic, evolution = _stat(c, STARYU), _stat(c, M_STARMIE)

    assert c.provision_codes(EVO_ONLY, basic) == (COLORLESS,)
    assert c.provision_codes(EVO_ONLY, evolution) == (COLORLESS,) * 3, (
        "a provides_evo card that does not expire still provides its printed 3 on an Evolution; "
        "the retired hardcode keyed the 3 off `discard_eot` and would read 1 here")

    assert c.provision_codes(BURST_2, basic) == (COLORLESS,)
    assert c.provision_codes(BURST_2, evolution) == (COLORLESS,) * 2, (
        "a discard_eot card is worth what it PRINTS on an Evolution; the retired hardcode read a "
        "flat 3 for every burst and would over-credit this one by a full unit")


# ─────────────────────────────────── acceptance 3: card ids and unit codes are NOT interchangeable
def test_an_ignition_cannot_pay_a_water_slot_and_a_card_id_says_otherwise():
    """``[0]`` is what the engine renders for one Ignition on a Basic; ``[17]`` is the card id, which
    reads WILD. Written as the INEQUALITY, because the defect was precisely that they agreed."""
    c = _combat(_REAL)
    assert unit_colours(COLORLESS) == frozenset({COLORLESS})
    assert unit_colours(IGNITION) == frozenset(), "card 17 is not an EnergyType — it reads WILD"

    def payable(energies):
        body = {"id": STARYU, "energies": list(energies)}
        return c.attack_type_payable(JETTING_BLOW, body)

    assert payable([COLORLESS]) is False, "one colourless unit cannot pay a {W} slot"
    assert payable([IGNITION]) is True, "…but the CARD ID reads wild, which is the whole defect"
    assert payable([COLORLESS]) != payable([IGNITION]), (
        "`[0]` and `[17]` must never be interchangeable: the first is what the engine renders and "
        "the second manufactures reachable damage")
    # The seam answers in the engine's vocabulary by construction, so a caller cannot reach the
    # wrong list by accident.
    assert c.provision_codes(IGNITION, _stat(c, STARYU)) == (COLORLESS,)


def test_a_typed_special_energy_is_the_same_trap_one_card_over():
    """Not an Ignition-only quirk: Telepath Psychic Energy is card 19 with ``energyType`` {P}, so the
    id resolves to no colour at all while the code it renders pays {P} slots."""
    c = _combat(_REAL)
    assert c.provision_codes(TELEPATH, _stat(c, M_STARMIE)) == (PSYCHIC,)
    assert unit_colours(PSYCHIC) == frozenset({PSYCHIC})
    assert unit_colours(TELEPATH) == frozenset()


# ──────────────────────────────────────────────────── acceptance 1: ONE composition, two contracts
def test_the_apply_seam_refuses_exactly_where_the_seam_cannot_read():
    """`board_delta.units_for_cards` is the seam's OTHER arity: the two contracts differ only in what
    they do with an unreadable card — never in what they compute."""
    c = _combat({IGNITION: ["discard_eot"]})
    cards = [{"id": IGNITION}]
    try:
        units_for_cards(c, cards, holder_stat=_stat(c, M_STARMIE))
    except Unmodellable as gap:
        assert "provides:N" in str(gap)
    else:                                              # pragma: no cover - the failure is the point
        raise AssertionError("an untagged Special Energy must refuse, not attach zero units")
    # …and with real tags both arities give the same answer — one reader rather than two.
    real = _combat(_REAL)
    assert units_for_cards(real, cards, holder_stat=_stat(real, M_STARMIE)) == [COLORLESS] * 3
    assert (tuple(units_for_cards(real, cards, holder_stat=_stat(real, M_STARMIE)))
            == real.provision_codes(IGNITION, _stat(real, M_STARMIE)))


def test_the_hand_leg_and_the_attached_leg_agree_about_one_ignition():
    """Both legs run through the seam, so the Budget's hypothetical attach and the board it becomes
    carry identical colours (Issue #142, Issue #297)."""
    c = _combat(_REAL)
    hand_group, = c._special_energy_groups([IGNITION], _stat(c, M_STARMIE))
    attached = c._attached_units({"id": M_STARMIE, "energies": [COLORLESS] * 3})
    assert hand_group == attached
    assert [u.types for u in hand_group] == [frozenset({COLORLESS})] * 3


def test_a_rainbow_special_energy_is_wild_on_both_legs():
    """No shipped deck reaches this: the hand leg spelled its pool ``frozenset({etype})``, so
    ``RAINBOW`` paid a non-existent slot in hand while paying anything once attached (Issue #418)."""
    rainbow = {9003: CardStat(9003, synthetic=True, name="(synthetic) rainbow Energy",
                              cardType=6, energyType=WILD_CODE)}
    c = _combat({**_REAL, 9003: ["provides:1"]}, stats=rainbow)
    hand_group, = c._special_energy_groups([9003], _stat(c, M_STARMIE))
    attached = c._attached_units({"id": M_STARMIE, "energies": [WILD_CODE]})
    assert hand_group == attached
    assert [u.types for u in hand_group] == [frozenset()], "RAINBOW pays any one slot, in hand too"


# ─────────────────────────────────────────────────────────── the evolve hypothetical (D3's seam)
def test_restage_energy_re_reads_the_cards_against_the_new_stage():
    """`restage_energy` asks *what do the same cards provide once this body is an Evolution* —
    `without_expiring_energy`'s sibling."""
    c = _combat(_REAL)
    body = {"id": STARYU, "energies": [COLORLESS], "energyCards": [{"id": IGNITION}]}
    after = c.restage_energy(body, _stat(c, M_STARMIE))
    assert after["energies"] == [COLORLESS] * 3
    assert after["energyCards"] == body["energyCards"], "the CARDS carry through an evolve unchanged"
    assert body["energies"] == [COLORLESS], "the input must not be mutated"


def test_restage_energy_declines_rather_than_compounding_a_disagreement():
    """A decider cannot refuse, so `board_delta._evolve`'s self-check lands here as a DECLINE: the
    body comes back by identity, reading exactly as it did before."""
    c = _combat(_REAL)
    # Engine says two units, model says one: re-deriving would compound a visible error.
    lying = {"id": STARYU, "energies": [COLORLESS, COLORLESS], "energyCards": [{"id": IGNITION}]}
    assert c.restage_energy(lying, _stat(c, M_STARMIE)) is lying

    unreadable = _combat({IGNITION: ["discard_eot"]})
    body = {"id": STARYU, "energies": [COLORLESS], "energyCards": [{"id": IGNITION}]}
    assert unreadable.restage_energy(body, _stat(unreadable, M_STARMIE)) is body

    # No `energyCards` at all — a hand-built board. Nothing to re-derive FROM, so nothing is claimed.
    bare = {"id": STARYU, "energies": [COLORLESS]}
    assert c.restage_energy(bare, _stat(c, M_STARMIE)) is bare


def test_restage_energy_returns_the_body_by_identity_when_nothing_moves():
    """A Basic Energy provides the same unit on either stage, so the common board costs one walk and
    no allocation — the same contract `without_expiring_energy` declares."""
    c = _combat(_REAL)
    body = {"id": STARYU, "energies": [WATER], "energyCards": [{"id": WATER_ENERGY}]}
    assert c.restage_energy(body, _stat(c, M_STARMIE)) is body
