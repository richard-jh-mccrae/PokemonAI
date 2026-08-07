"""The ONE walk over a board Pokémon's cards — `common.board_cards` (Issue #297).

`energies` is ``list[EnergyType]`` — the UNITS the attached cards PROVIDE — while the cards are
``energyCards``. They coincide for the eight Basic Energies (card id == type code) and part ways
after: Ignition renders ``[0,0,0]`` and names no card; Rock Fighting renders ``[6]``, which is the
card id of Basic {F} Energy, a card it is not.

Card facts VERIFIED at source (`data/EN_Card_Data.csv` + `cg.api.EnergyType`).
"""
from collections import Counter

from common import board_cards
from common.deck_tracker import OwnCardModel
from common.strategy import combat
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider
from common.state_model import StateModel
from common.strategy import Strategy
from common.strategy.combat import CombatMath

COLORLESS, FIGHTING = 0, 6
RIOLU = 677
E_F, IGNITION, ROCK_FIGHTING = 6, 17, 20
CAPE = 1250                                    # a Tool, to prove `tools` still rides the same walk

_STATS = {
    RIOLU: CardStat(RIOLU, synthetic=True, name='Riolu', hp=80, energyType=FIGHTING, cardType=0),
    E_F: CardStat(E_F, name="Basic {F} Energy", cardType=5, energyType=FIGHTING),
    IGNITION: CardStat(IGNITION, name="Ignition Energy", cardType=6, energyType=COLORLESS),
    ROCK_FIGHTING: CardStat(ROCK_FIGHTING, name="Rock Fighting Energy", cardType=6,
                            energyType=FIGHTING),
    CAPE: CardStat(CAPE, synthetic=True, name="Hero's Cape", cardType=2),
}

#: 4x Basic {F}, 2x Ignition, 2x Rock Fighting, a Tool and the Riolu.
DECK = [E_F] * 4 + [IGNITION] * 2 + [ROCK_FIGHTING] * 2 + [CAPE, RIOLU]


def _witness_body():
    """Four Energy UNITS from TWO Energy cards, so `energies` and `energyCards` genuinely differ."""
    return {"id": RIOLU, "serial": 1, "hp": 80, "maxHp": 80,
            "energies": [COLORLESS, COLORLESS, COLORLESS, FIGHTING],
            "energyCards": [{"id": IGNITION, "serial": 2}, {"id": ROCK_FIGHTING, "serial": 3}],
            "tools": [{"id": CAPE, "serial": 4}], "preEvolution": []}


def _player(**kw):
    me = {"active": [_witness_body()], "bench": [], "hand": [], "handCount": 0,
          "discard": [], "prize": [None] * 4, "deckCount": 6,
          "poisoned": False, "burned": False, "asleep": False, "paralyzed": False,
          "confused": False}
    me.update(kw)
    return me


def _opp():
    return {"active": [], "bench": [], "hand": None, "handCount": 5, "discard": [],
            "prize": [None] * 6, "deckCount": 40,
            "poisoned": False, "burned": False, "asleep": False, "paralyzed": False,
            "confused": False}


def _mine(**kw):
    obs = {"current": {"players": [_player(**kw), _opp()], "yourIndex": 0, "turn": 5},
           "logs": []}
    combat = CombatMath(DictCardStatProvider(_STATS), functions=None, transients=None)
    return StateModel.build(obs, combat=combat, deck=DECK).mine


def test_the_walk_yields_the_card_keys_and_never_the_unit_list():
    assert board_cards.CARD_STACKS == ("energyCards", "tools", "preEvolution")
    ids = list(board_cards.body_card_ids(_witness_body()))
    assert ids == [RIOLU, IGNITION, ROCK_FIGHTING, CAPE]
    # Walking `energies` instead yields phantom card-0 entries and a card 6 not on this board.
    assert COLORLESS not in ids and E_F not in ids


def test_an_empty_or_missing_body_yields_nothing():
    assert list(board_cards.body_card_ids(None)) == []
    assert list(board_cards.body_card_ids({})) == []
    assert list(board_cards.body_card_ids({"id": RIOLU})) == [RIOLU]


def test_a_bare_int_stack_entry_resolves_like_a_card_dict():
    """Several hand-built fixtures carry bare ids rather than card dicts; both are real."""
    body = {"id": RIOLU, "energyCards": [E_F, {"id": IGNITION}], "tools": [], "preEvolution": []}
    assert list(board_cards.body_card_ids(body)) == [RIOLU, E_F, IGNITION]


def test_visible_counts_names_the_special_energy_cards_not_the_units():
    visible = _mine().visible_counts
    assert visible[IGNITION] == 1                   # was 0 — `[0,0,0]` never named card 17
    assert visible[ROCK_FIGHTING] == 1              # was 0 — `[6]` named Basic {F} instead
    assert visible[E_F] == 0                        # was 1 — a card that is not on this board
    assert visible[CAPE] == 1 and visible[RIOLU] == 1


def test_unseen_counts_leaves_the_attached_copies_out_of_the_deck():
    unseen = _mine().unseen_counts
    assert unseen[IGNITION] == 1                    # 2 in the decklist, 1 attached
    assert unseen[ROCK_FIGHTING] == 1               # 2 in the decklist, 1 attached
    assert unseen[E_F] == 4                         # all 4 still unseen — none is on the board
    assert RIOLU not in unseen and CAPE not in unseen


def test_the_attach_budget_input_is_not_eroded_by_a_special_energy():
    """Miscounting an attached Special as a Basic {F} takes a real {F} out of the deck's supply — a
    manufactured famine one card deep, read by the Attach Budget's deck-fetch leg."""
    mine = _mine(prize=[None])                      # one hidden prize, so the ceiling is not slot-capped
    assert mine.deck_energy_counts[FIGHTING].ceiling == 4
    assert FIGHTING in mine.deck_energy_types


def test_every_visible_counter_agrees_on_the_same_board():
    """Three consumers of ONE walk, so they cannot drift apart card-for-card."""
    me = _player()
    model_counts = _mine()
    pilot_counts = Pilot(Strategy({}, {}), deck=DECK)._visible_card_counts(me)
    tracker_counts = OwnCardModel(DECK)._visible(me, {"effect": None, "contextCard": None})

    expected = Counter({RIOLU: 1, IGNITION: 1, ROCK_FIGHTING: 1, CAPE: 1})
    assert +model_counts.visible_counts == expected
    assert +pilot_counts == expected
    assert +tracker_counts == expected


def test_the_pilot_and_the_model_derive_the_same_deck():
    """Asserted under an ANCHORED prize split, the only case where both may make an exact claim."""
    prizes = {E_F: 1, IGNITION: 1}
    me = _player(prize=[None])
    obs = {"current": {"players": [me, _opp()], "yourIndex": 0, "turn": 5},
           "logs": [], "own_prizes": prizes}
    combat = CombatMath(DictCardStatProvider(_STATS), functions=None, transients=None)
    mine = StateModel.build(obs, combat=combat, deck=DECK).mine
    pilot_known = Pilot(Strategy({}, {}), deck=DECK)._deck_known_counts(me, prizes)

    assert mine.unseen_counts == pilot_known
    deck_count, by_type = mine._deck_facts()
    assert deck_count == sum(pilot_known.values())
    assert by_type == {FIGHTING: 3}                 # 4 Basic {F} − 1 prized; the Specials aren't Basic


def test_an_unanchored_side_still_claims_no_deck_facts():
    """No positive deck claim while an unseen copy could be sitting in a face-down prize."""
    assert _mine()._deck_facts() == (None, None)


# ── the other half of the same distinction: `energies` read as UNITS ───────────────────────────
# Feeding an `energies` entry to `_card_stat` as a card id is right for codes 1-8 and wrong after.

RAINBOW, TEAM_ROCKET, PSYCHIC, DARKNESS = 10, 11, 5, 7
JETTING = 11                                    # {W}{C}{C} — one typed slot, two colourless


def _combat():
    from common.scouting.provider import AttackStat
    return CombatMath(
        DictCardStatProvider(_STATS, attacks={JETTING: AttackStat(JETTING, damage=120, cost=3,
                                                                  energyTypes=(3, 0, 0))}),
        functions=None, transients=None)


def test_a_unit_pays_the_colours_its_code_names():
    assert combat.unit_colours(FIGHTING) == frozenset({FIGHTING})
    assert combat.unit_colours(COLORLESS) == frozenset({COLORLESS})   # was wild
    assert combat.unit_colours(RAINBOW) == frozenset()                # "Every Types" — really wild
    assert combat.unit_colours(TEAM_ROCKET) == frozenset({PSYCHIC, DARKNESS})
    assert combat.unit_colours(99) == frozenset()                     # a later set's code: fail-open


def test_attached_type_counts_reads_the_units_not_the_card_table():
    """Colourless is not a colour any typed cost slot can be paid from, so it enters no histogram."""
    c = _combat()
    assert c.attached_type_counts(_witness_body()) == {FIGHTING: 1}   # the Rock Fighting's {F} only
    assert c.attached_type_counts({"energies": [COLORLESS] * 3}) == {}
    assert c.attached_type_counts({"energies": [RAINBOW]}) == {}      # cannot name ONE colour


def test_a_colourless_unit_no_longer_funds_a_typed_slot():
    """Colourless units meet an attack's COUNT but cannot pay its TYPED slot."""
    c = _combat()
    assert not c.attack_type_payable(JETTING, {"energies": [COLORLESS] * 3})
    assert c.attack_type_payable(JETTING, {"energies": [3, COLORLESS, COLORLESS]})
    assert c.attack_type_payable(JETTING, {"energies": [RAINBOW] * 3})     # wild — fail-open stands


def test_the_attached_and_in_hand_readings_of_one_energy_agree():
    """`AttachUnit` and `_special_energy_groups` must give one Energy the same colour in hand and
    once attached."""
    units = _combat()._attached_units({"energies": [COLORLESS, FIGHTING]})
    assert [u.types for u in units] == [frozenset({COLORLESS}), frozenset({FIGHTING})]
