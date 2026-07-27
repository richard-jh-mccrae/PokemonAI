"""The frame read-out (`train.blunder.frame_view`) — key parsing, source resolution, rendering.

The two claims worth pinning hardest are the ones a hand-written dump kept getting wrong:

* the per-turn flags belong to the **turn player**, who is NOT always the seat being asked
  (a post-KO promotion is prompted during the opponent's turn); and
* a zone the acting seat could not see is **labelled**, so a full-information deck or prize list
  can never be mistaken for something the agent knew.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for sub in ("tools", "src"):
    path = str(REPO / sub)
    if path not in sys.path:
        sys.path.insert(0, path)

from train.blunder.frame_view import (  # noqa: E402
    UNKNOWN_CARD, available_frames, dump, find_frame, parse_frame_key, render, turn_player,
)

# The frame this tool was built for: episode 82756664 frame 97 — seat 1 promoting after a KO,
# which is prompted during seat 0's turn.
KEY = "82756664-97"
EPISODE, FRAME = 82756664, 97


# --- key parsing ------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "82756664-97", " 82756664-97 ", "82756664-f97", "82756664_97", "82756664 f97",
    "ep82756664-97", "EP82756664 F97", "82756664:97",
])
def test_parse_frame_key_accepts_the_forms_that_show_up_in_chat_and_docs(text):
    assert parse_frame_key(text) == (EPISODE, FRAME)


@pytest.mark.parametrize("text", ["", "97", "abc", "82756664", "-97", "82756664-"])
def test_parse_frame_key_rejects_non_keys(text):
    with pytest.raises(ValueError):
        parse_frame_key(text)


@pytest.mark.parametrize("text", ["82756664-t9s1", "82756664-m1"])
def test_parse_frame_key_rejects_scoped_keys_with_a_pointed_hint(text):
    """A Turn- or Match-scoped Correction key names many frames, so it has no single board state."""
    with pytest.raises(ValueError, match="scoped Correction key"):
        parse_frame_key(text)


# --- turn player ------------------------------------------------------------------------------

@pytest.mark.parametrize("turn,first,expected", [
    (1, 0, 0), (2, 0, 1), (9, 0, 0), (10, 0, 1),      # firstPlayer 0 takes the odd turns
    (1, 1, 1), (2, 1, 0), (9, 1, 1),
])
def test_turn_player_gives_the_seat_whose_ply_it_is(turn, first, expected):
    assert turn_player(turn, first) == expected


@pytest.mark.parametrize("turn,first", [(0, 0), (0, 1), (None, 0), (5, None), (-1, 0)])
def test_turn_player_is_none_when_no_single_seat_owns_the_turn(turn, first):
    """Turn 0 is the shared setup phase — both seats act in it (tools/train/CONTEXT.md)."""
    assert turn_player(turn, first) is None


# --- resolving a frame from the committed stores -----------------------------------------------

def test_finds_the_real_frame_in_the_correction_tree():
    hit = find_frame(EPISODE, FRAME)
    assert (hit.episode_id, hit.frame) == (EPISODE, FRAME)
    assert hit.turn == 9
    assert hit.asked_seat == 1
    assert hit.full_info is True
    assert "corrections.jsonl" in str(hit.source_path)
    assert hit.correction is not None


def test_missing_frame_raises_and_names_where_it_looked():
    with pytest.raises(LookupError, match="not found"):
        find_frame(EPISODE, 999999)


def test_available_frames_lists_the_episodes_tagged_frames():
    keys = available_frames(EPISODE)
    assert KEY in keys
    assert all(k.startswith(f"{EPISODE}-") for k in keys)


def test_available_frames_does_not_scan_a_date_as_a_frame_key():
    """A fixture note carrying "2026-07-13" must not register as episode 2026 frame 7."""
    assert not any(k.startswith("2026-") for k in available_frames())


# --- the read-out -----------------------------------------------------------------------------

@pytest.fixture(scope="module")
def text():
    return dump(KEY)


def test_header_names_the_frame_the_source_and_the_agent(text):
    assert f"FRAME {KEY}" in text
    assert "corrections.jsonl" in text
    assert "mega_starmie" in text


def test_sections_appear_once_each_and_in_a_fixed_order(text):
    order = ["BOARD STATE — FRAME", "--- THE DECISION", "--- TURN STATE ---", "--- SEAT 1",
             "--- SEAT 0"]
    positions = [text.index(section) for section in order]
    assert positions == sorted(positions)
    for section in order:
        assert text.count(section) == 1, f"{section} rendered more than once"


def test_the_turn_flags_are_attributed_to_the_turn_player_not_the_asked_seat(text):
    """f97: seat 1 is asked to promote, but it is seat 0's turn — so the flags are seat 0's."""
    assert "turn player: seat 0" in text
    assert "the per-turn flags below are SEAT 0's" in text
    assert "OUT OF TURN" in text
    assert "The flags below are NOT yours." in text


def test_every_per_turn_allowance_is_reported_with_what_it_means(text):
    assert "energy attached from hand: YES" in text
    assert "supporter played: YES" in text
    assert "stadium played: NO" in text
    assert "retreated: NO" in text
    assert "actions taken this turn: 20" in text


def test_an_empty_active_spot_is_called_out_rather_than_silently_missing(text):
    """Seat 1's Active was just knocked out — that is the whole reason for this decision."""
    assert "ACTIVE: EMPTY" in text
    assert "must promote one" in text


def test_both_sides_report_prizes_hand_deck_and_discard(text):
    for seat in (0, 1):
        block = _seat_block(text, seat)
        assert "prizes remaining:" in block
        assert "HAND:" in block
        assert "DECK:" in block
        assert "DISCARD:" in block
        assert "BENCH:" in block
        assert "special conditions on the Active:" in block


def test_prize_and_deck_contents_are_listed_but_labelled_hidden(text):
    """The point of the labels: full-information contents must never read as agent knowledge."""
    seat1 = _seat_block(text, 1)
    assert "prize cards, face down [hidden from you]:" in seat1
    assert "Mega Starmie ex" in seat1.split("prize cards")[1].split("ACTIVE")[0]
    assert "DECK: 25 cards left" in seat1
    assert "hidden from you" in seat1.split("DECK:")[1].split("\n")[0]


def test_the_opponents_hand_is_shown_with_its_count_public_and_contents_not(text):
    seat0 = _seat_block(text, 0)
    hand_line = [ln for ln in seat0.splitlines() if ln.startswith("HAND:")][0]
    assert "7 cards" in hand_line
    assert "hidden from you" in hand_line
    assert "the count is public" in hand_line


def test_discard_is_labelled_public_on_both_sides(text):
    for seat in (0, 1):
        discard = [ln for ln in _seat_block(text, seat).splitlines()
                   if ln.startswith("DISCARD:")][0]
        assert "[public" in discard


def test_the_asked_seat_is_rendered_first(text):
    assert text.index("--- SEAT 1") < text.index("--- SEAT 0")


def test_options_resolve_to_the_cards_they_name(text):
    assert "[0] Card · seat 1 BENCH index 0 = Cinderace" in text
    assert "[1] Card · seat 1 BENCH index 1 = Mega Starmie ex" in text
    assert "[2] Card · seat 1 BENCH index 2 = Staryu" in text


def test_the_ruling_and_the_agents_own_choice_are_both_shown(text):
    assert "the agent chose: [1]" in text
    assert "the correct choice was: [0]" in text
    assert "blunder category: missed_disruption" in text
    assert "rationale:" in text
    assert "agent trace at this frame:" in text


def test_card_facts_come_from_the_committed_tables(text):
    """Verified against src/cgpy/defs: Mega Starmie ex is 330 HP, weak to {L}, retreat 2, and a
    Mega Evolution Pokémon ex is worth 3 prizes (docs/rules.md §6)."""
    assert "weakness {L} (takes x2)" in text
    assert "retreat cost 2" in text
    assert "KO here gives the opponent 3 (Mega Evolution Pokémon ex)" in text
    assert "Jetting Blow" in text


def test_an_effect_modified_max_hp_is_flagged_against_the_printed_value(text):
    """Cinderace prints 160 HP but has maxHp 130 here — Gravity Mountain is in play."""
    assert "max HP is 130, printed HP is 160 (-30 from effects in play" in text


def test_the_stadium_in_play_is_reported_with_its_owner(text):
    assert "stadium in play: Gravity Mountain (played by seat 0)" in text


def test_the_match_result_field_is_translated(text):
    assert "match result: not decided yet" in text


def test_deck_order_is_withheld_by_default_and_labelled_when_asked():
    assert "deck order as recorded in the film" not in dump(KEY)
    with_order = dump(KEY, deck_order=True)
    assert "deck order as recorded in the film" in with_order
    assert "NOT a legitimate top-of-deck read" in with_order


def test_the_read_out_is_plain_text_with_no_table_markup(text):
    assert "|" not in text
    assert "---|" not in text


def test_the_render_is_deterministic(text):
    assert dump(KEY) == text


# --- the per-seat Observation shape ------------------------------------------------------------

def test_an_observation_snapshot_renders_the_same_sections(tmp_path):
    """A fixture pins the agent's own Observation: ints for enums, no `name` on cards, absent
    opponent hand, and face-down prizes as bare nulls. Same section order out."""
    text = dump("82756664-37", corrections=None, replays=None)
    assert "per-seat agent Observation" in text
    assert "--- TURN STATE ---" in text
    assert "--- SEAT 1" in text and "--- SEAT 0" in text
    # enums arrive as ints here and must still read as names
    assert "select context: Main" in text
    assert "select type: Main" in text
    # cards carry only an id, so the name comes from the committed card tables
    assert "Cinderace" in text


def test_face_down_cards_are_named_as_unknown_not_dropped():
    """An Observation's prize pile is six nulls — say so instead of listing six phantom cards."""
    text = dump("82756664-37", corrections=None, replays=None)
    assert "prizes remaining: 6 of 6" in text
    assert "face down, identities not in this snapshot" in text


def test_a_stadium_targeted_option_names_the_stadium_not_a_bare_index():
    """An ABILITY on the Stadium is `{type: Ability, area: STADIUM, index: 0}` — and the Stadium
    hangs off the top-level state, not off a player (`cgpy.options`)."""
    from train.blunder.frame_view import FrameHit
    hit = FrameHit(episode_id=1, frame=0, current={
        "turn": 3, "firstPlayer": 0, "yourIndex": 0, "result": -1,
        "stadium": [{"id": 1252, "name": "Gravity Mountain", "playerIndex": 0}],
        "players": [{"active": [], "bench": [], "prize": 6, "handCount": 0, "deckCount": 40,
                     "discard": []}] * 2,
    }, source="synthetic", options=[{"type": 10, "area": 7, "index": 0}])
    text = render(hit)
    assert "[0] Ability · the STADIUM = Gravity Mountain" in text


def test_an_option_on_a_non_zone_area_keeps_the_area_name():
    """ENERGY / TOOL / PRE_EVOLUTION hang off a Pokémon, so there is no zone list to index — say
    which area it was rather than printing a bare index."""
    from train.blunder.frame_view import FrameHit
    hit = FrameHit(episode_id=1, frame=0, current={
        "turn": 3, "firstPlayer": 0, "yourIndex": 0, "result": -1,
        "players": [{"active": [], "bench": [], "prize": 6, "handCount": 0, "deckCount": 40,
                     "discard": []}] * 2,
    }, source="synthetic", options=[{"type": 5, "area": 8, "index": 1}])
    assert "seat 0 ENERGY index 1" in render(hit)


def test_a_null_pokemon_slot_renders_as_unknown():
    from train.blunder.frame_view import FrameHit
    hit = FrameHit(episode_id=1, frame=0, current={
        "turn": 3, "firstPlayer": 0, "yourIndex": 0, "result": -1,
        "players": [{"active": [None], "bench": [], "prize": 6, "handCount": 3, "deckCount": 40,
                     "discard": []},
                    {"active": [], "bench": [], "prize": 6, "handCount": 3, "deckCount": 40,
                     "discard": []}],
    }, source="synthetic")
    assert UNKNOWN_CARD in render(hit)


# --- reading a frame straight out of a replay film ---------------------------------------------

def test_a_replay_film_resolves_any_frame_not_only_tagged_ones(tmp_path):
    """Raw replays are not committed (ADR-0002), so build a minimal film to pin the path."""
    current = {
        "turn": 2, "firstPlayer": 0, "yourIndex": 1, "result": -1, "energyAttached": False,
        "supporterPlayed": False, "stadiumPlayed": False, "retreated": False,
        "turnActionCount": 0, "stadium": [],
        "players": [
            {"active": [{"id": 676, "name": "Solrock", "hp": 110, "maxHp": 110, "energies": []}],
             "bench": [], "benchMax": 5, "deck": [], "deckCount": 40, "discard": [],
             "hand": [], "handCount": 0, "prize": 6},
            {"active": [{"id": 1030, "name": "Staryu", "hp": 70, "maxHp": 70, "energies": [3]}],
             "bench": [], "benchMax": 5, "deck": [], "deckCount": 39, "discard": [],
             "hand": [], "handCount": 1, "prize": 6},
        ],
    }
    film = [
        {"current": current, "select": {"context": "Main", "type": "Main",
                                        "option": [{"type": "End"}]}},
        {"selected": [0], "obs": {"current": current}},
    ]
    replay = {"info": {"EpisodeId": 4242}, "steps": [[{"visualize": film}]]}
    path = tmp_path / "replay.json"
    path.write_text(json.dumps(replay), encoding="utf-8")

    hit = find_frame(4242, 0, replay_path=path)
    assert hit.full_info is True
    assert hit.chosen == [0]
    assert "Replay film, frame 0 of 2" in hit.source

    text = render(hit)
    assert "turn player: seat 1" in text          # turn 2, firstPlayer 0 -> seat 1
    assert "seat 1 is the turn player" in text
    assert "the 1 manual attach is still available" in text
    assert "stadium in play: none" in text


def test_a_frame_past_the_end_of_a_film_is_a_clean_lookup_error(tmp_path):
    replay = {"info": {"EpisodeId": 4242}, "steps": [[{"visualize": [{"current": {}}]}]]}
    path = tmp_path / "replay.json"
    path.write_text(json.dumps(replay), encoding="utf-8")
    with pytest.raises(LookupError, match="no frame 7"):
        find_frame(4242, 7, replay_path=path)


# --- helpers ----------------------------------------------------------------------------------

def _seat_block(text: str, seat: int) -> str:
    """Everything the read-out says about one seat."""
    marker = f"--- SEAT {seat}"
    start = text.index(marker)
    rest = text[start + len(marker):]
    end = rest.find("--- SEAT ")
    return rest if end == -1 else rest[:end]
