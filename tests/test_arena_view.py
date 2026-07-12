"""Arena view-model: raw seat obs -> the phone-renderable board + labeled options.

The one place obs decoding for the Visitor lives. Uses pilot_helpers' lib-free obs
builders with real pool ids, so labels are checked against real card names.
Engine-backed only for name lookups (provider), same as CI's engine-load guarantee.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import pilot_helpers as ph  # noqa: E402
from deck_convert import _indexes  # noqa: E402
from arena import view  # noqa: E402

req = pytest.mark.req("REQ-ARENA-0003")

BY_NORM = _indexes()[0]
STARYU = BY_NORM["staryu"][0]
ULTRA = BY_NORM["ultra ball"][0]


@req
def test_main_menu_labels_options_and_hides_opponent_hand():
    from common.scouting.provider import EngineCardStatProvider
    atk = EngineCardStatProvider().get(STARYU).attacks[0]
    cur = ph.state(
        active=ph.poke(STARYU, energy=1, hp=60, max_hp=70), hand=(ULTRA,),
        opp_active=ph.poke(STARYU, hp=70, max_hp=70), opp_hand_count=5,
        prizes=3, opp_prizes=4)
    obs = ph.make_select(
        [ph.opt(ph.PLAY, index=0), ph.attack_opt(atk), ph.opt(14)], current=cur)

    v = view.build_view(obs)

    assert v["phase"] == "play"
    assert [c["name"] for c in v["you"]["hand"]] == ["Ultra Ball"]
    assert v["you"]["active"]["name"] == "Staryu"
    assert v["you"]["active"]["hp"] == 60 and v["you"]["active"]["max_hp"] == 70
    assert v["you"]["prizes"] == 3 and v["opp"]["prizes"] == 4
    assert v["opp"]["hand_count"] == 5 and "hand" not in v["opp"]   # hidden info stays hidden
    labels = [o["label"] for o in v["select"]["options"]]
    assert labels[0] == "Play Ultra Ball"
    assert labels[1].startswith("Attack: ") and len(labels[1]) > len("Attack: ")
    assert labels[2] == "End turn"
    assert [o["i"] for o in v["select"]["options"]] == [0, 1, 2]    # engine indices preserved


@req
def test_attach_and_evolve_carry_tap_coordinates():
    WATER_E = BY_NORM["basic {w} energy"][0]
    MEGA = BY_NORM["mega starmie ex"][0]
    cur = ph.state(
        active=ph.poke(STARYU, hp=70, max_hp=70),
        bench=(ph.poke(STARYU, hp=70, max_hp=70),),
        hand=(WATER_E, MEGA))
    obs = ph.make_select([
        {"type": ph.ATTACH, "area": ph.HAND, "index": 0, "inPlayArea": ph.ACTIVE, "inPlayIndex": 0},
        {"type": ph.ATTACH, "area": ph.HAND, "index": 0, "inPlayArea": ph.BENCH, "inPlayIndex": 0},
        {"type": 9, "area": ph.HAND, "index": 1, "inPlayArea": ph.ACTIVE, "inPlayIndex": 0},
    ], current=cur)

    opts = view.build_view(obs)["select"]["options"]

    assert opts[0]["label"].startswith("Attach Basic {W} Energy")
    assert "Staryu" in opts[0]["label"]
    assert opts[0]["source"] == {"zone": "hand", "index": 0}
    assert opts[0]["target"] == {"zone": "active", "index": 0, "opp": False}
    assert opts[1]["target"] == {"zone": "bench", "index": 0, "opp": False}
    assert opts[2]["label"].startswith("Evolve Staryu")
    assert "Mega Starmie ex" in opts[2]["label"]


@req
def test_board_card_options_label_their_zone_and_owner():
    cur = ph.state(
        active=ph.poke(STARYU, hp=70, max_hp=70),
        opp_active=ph.poke(STARYU, hp=50, max_hp=70),
        opp_bench=(ph.poke(STARYU, hp=70, max_hp=70),))
    obs = ph.make_select([
        ph.card_opt(ph.ACTIVE, 0, player=1),                 # snipe target: opp active
        ph.card_opt(ph.BENCH, 0, player=1),                  # snipe target: opp bench
    ], context=ph.DAMAGE, current=cur)

    v = view.build_view(obs)
    opts = v["select"]["options"]

    assert opts[0]["target"] == {"zone": "active", "index": 0, "opp": True}
    assert "Staryu" in opts[0]["label"]
    assert opts[1]["target"] == {"zone": "bench", "index": 0, "opp": True}
    assert v["select"]["prompt"]                             # a human sentence for the pick


@req
def test_search_pick_labels_come_from_the_revealed_deck():
    deck = [{"id": ULTRA, "serial": 9, "playerIndex": 0},
            {"id": STARYU, "serial": 10, "playerIndex": 0}]
    obs = ph.make_select([
        {"type": ph.CARD, "area": ph.DECK, "index": 0, "playerIndex": 0},
        {"type": ph.CARD, "area": ph.DECK, "index": 1, "playerIndex": 0},
    ], context=ph.TO_HAND, deck=deck, current=ph.state())

    v = view.build_view(obs)

    assert [o["label"] for o in v["select"]["options"]] == ["Ultra Ball", "Staryu"]
    assert v["select"]["prompt"] == "Choose a card to take"
    # revealed picks carry the card + pile, so the browser can show the actual scans
    assert [(o["card"], o["pile"]) for o in v["select"]["options"]] == \
        [(ULTRA, "deck"), (STARYU, "deck")]


@req
def test_discard_pile_picks_are_labeled_from_the_discard():
    cur = ph.state(discard=(ULTRA, STARYU))
    obs = ph.make_select([
        {"type": ph.CARD, "area": ph.DISCARD, "index": 0, "playerIndex": 0},
        {"type": ph.CARD, "area": ph.DISCARD, "index": 1, "playerIndex": 0},
    ], context=ph.TO_HAND, current=cur)

    opts = view.build_view(obs)["select"]["options"]

    assert "Ultra Ball" in opts[0]["label"] and "Staryu" in opts[1]["label"]
    assert [(o["card"], o["pile"]) for o in opts] == \
        [(ULTRA, "discard"), (STARYU, "discard")]


@req
def test_looking_reveals_carry_the_card_but_board_picks_do_not():
    cur = ph.state(active=ph.poke(STARYU, hp=70, max_hp=70))
    cur["looking"] = [{"id": ULTRA, "serial": 1, "playerIndex": 0}]
    obs = ph.make_select([
        {"type": ph.CARD, "area": 12, "index": 0, "playerIndex": 0},   # LOOKING
        ph.card_opt(ph.ACTIVE, 0, player=0),                           # a board pick
    ], current=cur)

    opts = view.build_view(obs)["select"]["options"]

    assert opts[0]["label"] == "Ultra Ball"
    assert opts[0]["card"] == ULTRA and opts[0]["pile"] == "looking"
    assert "pile" not in opts[1]                     # board targets keep the board flow


@req
def test_attached_card_picks_name_the_card_and_its_pokemon():
    WATER_E = BY_NORM["basic {w} energy"][0]
    CAPE = BY_NORM["hero's cape"][0]
    mon = ph.poke(STARYU, hp=70, max_hp=70)
    mon["energyCards"] = [{"id": WATER_E, "serial": 1, "playerIndex": 0}]
    mon["tools"] = [{"id": CAPE, "serial": 2, "playerIndex": 0}]
    mon["energies"] = [3]                                # EnergyType.WATER
    cur = ph.state(active=mon)
    obs = ph.make_select([
        {"type": 5, "area": ph.ACTIVE, "index": 0, "playerIndex": 0, "energyIndex": 0},
        {"type": 4, "area": ph.ACTIVE, "index": 0, "playerIndex": 0, "toolIndex": 0},
        {"type": 6, "area": ph.ACTIVE, "index": 0, "playerIndex": 0,
         "energyIndex": 0, "count": 1},
    ], context=26, current=cur)                          # DISCARD_ENERGY_CARD

    labels = [o["label"] for o in view.build_view(obs)["select"]["options"]]

    assert "Basic {W} Energy" in labels[0] and "Staryu" in labels[0]
    assert "Hero" in labels[1] and "Staryu" in labels[1]
    assert "Water" in labels[2] and "Staryu" in labels[2]
    assert "Select" not in labels                        # nothing left blind


@req
def test_mon_energies_are_typed_not_a_bare_count():
    mine = ph.poke(STARYU, hp=70, max_hp=70)
    mine["energies"] = [3, 3]                            # two Water units
    theirs = ph.poke(STARYU, hp=70, max_hp=70)
    theirs["energies"] = [2]                             # one Fire unit — public info
    cur = ph.state(active=mine, opp_active=theirs)

    v = view.build_view(ph.make_select([ph.opt(14)], current=cur))

    assert v["you"]["active"]["energies"] == [3, 3]      # EnergyType ints, order kept
    assert v["opp"]["active"]["energies"] == [2]


@req
def test_discards_are_public_while_hands_and_decks_stay_counts():
    cur = ph.state(discard=(ULTRA,), opp_discard=(STARYU, ULTRA),
                   opp_hand_count=5, deck_count=30)

    v = view.build_view(ph.make_select([ph.opt(14)], current=cur))

    assert [c["name"] for c in v["you"]["discard"]] == ["Ultra Ball"]
    assert [c["name"] for c in v["opp"]["discard"]] == ["Staryu", "Ultra Ball"]
    for side in (v["you"], v["opp"]):                    # hidden zones: counts only
        assert "deck" not in side
        assert isinstance(side["deck_count"], int)
    assert "hand" not in v["opp"] and v["opp"]["hand_count"] == 5


@req
def test_bot_actions_render_as_events_for_the_ticker():
    from common.scouting.provider import EngineCardStatProvider
    atk = EngineCardStatProvider().get(STARYU).attacks[0]
    obs = ph.make_select([ph.opt(14)], current=ph.state(your_index=0))
    obs["logs"] = [
        {"type": 10, "playerIndex": 1, "cardId": ULTRA, "serial": 3},          # PLAY
        {"type": 15, "playerIndex": 1, "cardId": STARYU, "serial": 4, "attackId": atk},
        {"type": 16, "playerIndex": 0, "cardId": STARYU, "serial": 5, "value": -30},
        {"type": 4, "playerIndex": 0, "cardId": ULTRA, "serial": 6},           # my DRAW
        {"type": 5, "playerIndex": 1},                                         # opp DRAW_REVERSE
    ]

    events = view.build_view(obs)["events"]

    assert any("Opponent played Ultra Ball" in e for e in events)
    assert any(e.startswith("Opponent's Staryu used ") for e in events)
    assert any("Staryu" in e and "30" in e for e in events)
    assert any("You drew Ultra Ball" in e for e in events)
    assert any(e == "Opponent drew a card" for e in events)


@req
def test_finished_game_reports_result_from_your_seat():
    cur = ph.state(your_index=1)
    cur["result"] = 1
    obs = {"select": None, "logs": [], "current": cur}

    v = view.build_view(obs)

    assert v["phase"] == "over"
    assert v["result"] == {"winner_seat": 1, "you_won": True, "draw": False}


@req
def test_draw_is_neither_win_nor_loss():
    cur = ph.state(your_index=0)
    cur["result"] = 2                                    # simulator delta: a draw
    v = view.build_view({"select": None, "logs": [], "current": cur})
    assert v["phase"] == "over"
    assert v["result"] == {"winner_seat": None, "you_won": False, "draw": True}
