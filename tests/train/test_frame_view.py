"""The frame read-out (`train.blunder.frame_view`) — key parsing, source resolution, rendering.

The claims worth pinning hardest are the ones a hand-written dump kept getting wrong:

* the per-turn flags belong to the **turn player**, who is NOT always the seat being asked
  (a post-KO promotion is prompted during the opponent's turn);
* a zone the acting seat could not see is **labelled**, so a full-information deck or prize list
  can never be mistaken for something the agent knew; and
* **no line exceeds the column width** — the read-out is read on a phone, so a layout regression
  that overflows is a real defect, not cosmetics.

Assertions on prose go through `flat()`, which collapses the wrapping. Wrap points move whenever a
label is reworded; the *content* is what these tests are about.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for sub in ("tools", "src"):
    path = str(REPO / sub)
    if path not in sys.path:
        sys.path.insert(0, path)

from train.blunder.frame_view import (  # noqa: E402
    UNKNOWN_CARD, WIDTH, available_frames, dump, find_frame, parse_frame_key, render, turn_player,
)

# The frame this tool was built for: episode 82756664 frame 97 — seat 1 promoting after a KO,
# which is prompted during seat 0's turn.
KEY = "82756664-97"
EPISODE, FRAME = 82756664, 97


def flat(text: str) -> str:
    """The read-out with its wrapping collapsed, for assertions about content not line breaks."""
    return re.sub(r"\s+", " ", text)


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


# --- the column width (the phone contract) -----------------------------------------------------

@pytest.fixture(scope="module")
def text():
    return dump(KEY)


def test_no_line_exceeds_the_default_width(text):
    """The read-out is read on a phone. An overflowing line is a defect, not a nitpick."""
    over = [(i, len(ln), ln) for i, ln in enumerate(text.splitlines(), 1) if len(ln) > WIDTH]
    assert over == [], f"{len(over)} line(s) over {WIDTH} chars: {over[:3]}"


def test_the_default_width_is_phone_sized():
    assert WIDTH == 38


@pytest.mark.parametrize("width", [30, 38, 60, 100])
def test_no_line_exceeds_an_explicit_width(width):
    rendered = dump(KEY, width=width)
    over = [ln for ln in rendered.splitlines() if len(ln) > width]
    assert over == [], f"over {width}: {over[:3]}"


def test_a_wider_column_yields_fewer_lines_with_the_same_content():
    narrow, wide = dump(KEY, width=38), dump(KEY, width=100)
    assert len(wide.splitlines()) < len(narrow.splitlines())
    for probe in ("Mega Starmie ex", "Gravity Mountain", "missed_disruption", "Turbo Flare"):
        assert probe in flat(narrow) and probe in flat(wide)


def test_a_deck_zone_is_grouped_not_one_card_per_line(text):
    """25 cards listed one per line is four phone screens; grouped it is a handful of lines."""
    deck_block = _after(_seat_block(text, 1), "DECK ", stop=("DISCARD ",))
    assert "Basic {W} Energy x3" in flat(deck_block)
    assert len(deck_block.splitlines()) < 14


def test_brief_drops_card_rule_text_but_keeps_every_zone():
    brief = dump(KEY, effects=False)
    assert "Search your deck for up to 3 Basic Energy" not in flat(brief)  # rule text gone
    assert "Turbo Flare" in flat(brief)                                    # the attack itself stays
    for zone in ("PRIZES", "ACTIVE", "BENCH", "HAND", "DECK", "DISCARD"):
        assert zone in brief
    assert len(brief.splitlines()) < len(dump(KEY).splitlines())


def test_the_source_path_breaks_at_slashes_not_mid_segment(text):
    """A path hard-wrapped mid-segment reads as a typo."""
    assert "data/corrections/" in text
    assert "mega_starmie_20260630_b7e483a/" in text


# --- the read-out -----------------------------------------------------------------------------

def test_header_names_the_frame_the_source_and_the_agent(text):
    assert f"BOARD STATE {KEY}" in text
    assert "corrections.jsonl" in text
    assert "mega_starmie" in text
    assert "ep 82756664 · frame 97 · turn 9" in text


def test_sections_appear_once_each_and_in_a_fixed_order(text):
    order = ["BOARD STATE", "-- DECISION", "-- TURN ", "-- SEAT 1", "-- SEAT 0"]
    positions = [text.index(section) for section in order]
    assert positions == sorted(positions)
    for section in order:
        assert text.count(section) == 1, f"{section} rendered more than once"


def test_the_turn_flags_are_attributed_to_the_turn_player_not_the_asked_seat(text):
    """f97: seat 1 is asked to promote, but it is seat 0's turn — so the flags are seat 0's."""
    body = flat(text)
    assert "turn player s0" in body
    assert "OUT OF TURN" in body
    assert "The flags below are s0's, NOT yours." in body
    assert "where s0 is in the turn:" in body


def test_every_per_turn_allowance_is_reported_with_what_it_means(text):
    body = flat(text)
    assert "energy attached from hand: YES" in body
    assert "no manual attach left" in body
    assert "supporter played: YES" in body
    assert "stadium played: NO" in body
    assert "retreated: NO" in body
    assert "the 1 manual retreat is available" in body
    assert "actions taken: 20" in body
    assert "ENDS the turn" in body


def test_an_empty_active_spot_is_called_out_rather_than_silently_missing(text):
    """Seat 1's Active was just knocked out — that is the whole reason for this decision."""
    assert "ACTIVE: EMPTY" in text
    assert "must promote one" in flat(text)


def test_both_sides_report_prizes_hand_deck_and_discard(text):
    for seat in (0, 1):
        block = _seat_block(text, seat)
        assert "PRIZES" in block
        assert "HAND " in block
        assert "DECK " in block
        assert "DISCARD " in block
        assert "BENCH " in block
        assert "conditions:" in block


def test_prizes_report_remaining_taken_and_the_win_condition(text):
    seat1 = flat(_seat_block(text, 1))
    assert "PRIZES 5 of 6 left · 1 taken" in seat1
    assert "the 6th taken wins" in seat1


def test_prize_and_deck_contents_are_listed_but_labelled_hidden(text):
    """The point of the labels: full-information contents must never read as agent knowledge."""
    seat1 = _seat_block(text, 1)
    assert "contents [hid]:" in seat1
    assert "Mega Starmie ex" in flat(_after(seat1, "contents [hid]:", stop=("ACTIVE",)))
    assert "DECK 25 left [pub count · hid contents]" in flat(seat1)
    assert "derivable by deck-tracking" in flat(seat1)


def test_the_opponents_hand_is_shown_with_its_count_public_and_contents_not(text):
    seat0 = flat(_seat_block(text, 0))
    assert "HAND 7 [hid] count is pub, contents are not" in seat0


def test_our_own_hand_is_labelled_as_seen(text):
    assert "HAND 10 [you]" in _seat_block(text, 1)


def test_discard_is_labelled_public_on_both_sides(text):
    for seat in (0, 1):
        assert "[pub — both may look]" in flat(_seat_block(text, seat))


def test_the_asked_seat_is_rendered_first(text):
    assert text.index("-- SEAT 1") < text.index("-- SEAT 0")


def test_options_resolve_to_the_cards_they_name(text):
    body = flat(text)
    assert "[0] Card s1 BENCH0 = Cinderace" in body
    assert "[1] Card s1 BENCH1 = Mega Starmie ex" in body
    assert "[2] Card s1 BENCH2 = Staryu" in body


def test_the_ruling_and_the_agents_own_choice_are_both_shown(text):
    body = flat(text)
    assert "AGENT CHOSE [1] s1 BENCH1 = Mega Starmie ex" in body
    assert "RULED CORRECT [0] s1 BENCH0 = Cinderace" in body
    assert "category missed_disruption" in body
    assert "rationale:" in body
    assert "agent trace:" in body


def test_card_facts_come_from_the_committed_tables(text):
    """Verified against src/cgpy/defs: Mega Starmie ex is 330 HP, weak to {L}, retreat 2, and a
    Mega Evolution Pokémon ex is worth 3 prizes (docs/rules.md §6)."""
    body = flat(text)
    assert "weak {L} x2 · retreat 2" in body
    assert "KO gives 3 prizes (Mega ex)" in body
    assert "KO gives 1 prize" in body
    assert "atk Jetting Blow · {W} · 120 dmg" in body


def test_attached_energy_is_grouped_with_its_provided_types(text):
    """Five identical energies are one item, and the provided types are spelled out."""
    body = flat(text)
    assert "energy 5: {F}{F}{F}{F}{F} Basic {F} Energy x5" in body


def test_an_effect_modified_max_hp_is_flagged_against_the_printed_value(text):
    """Cinderace prints 160 HP but has maxHp 130 here — Gravity Mountain is in play."""
    assert "max 130 vs printed 160 (-30 from effects in play)" in flat(text)


def test_the_stadium_in_play_is_reported_with_its_owner(text):
    assert "stadium: Gravity Mountain (s0) [pub, affects both]" in flat(text)


def test_the_match_result_field_is_translated(text):
    assert "result: not decided yet" in text


def test_deck_order_is_withheld_by_default_and_labelled_when_asked():
    # "recorded order" also appears in the LABELS legend, so probe the order block's own heading
    assert "recorded order —" not in flat(dump(KEY))
    with_order = flat(dump(KEY, deck_order=True))
    assert "recorded order — engine-internal, NOT a legitimate top-of-deck read:" in with_order


def test_the_read_out_is_plain_text_with_no_table_markup(text):
    assert "|" not in text
    assert "---|" not in text


def test_the_render_is_deterministic(text):
    assert dump(KEY) == text


# --- the per-seat Observation shape ------------------------------------------------------------

def test_an_observation_snapshot_renders_the_same_sections():
    """A fixture pins the agent's own Observation: ints for enums, no `name` on cards, absent
    opponent hand, and face-down prizes as bare nulls. Same section order out."""
    text = dump("82756664-37", corrections=None, replays=None)
    assert "per-seat agent Observation" in flat(text)
    assert "-- TURN " in text
    assert "-- SEAT 1" in text and "-- SEAT 0" in text
    # enums arrive as ints here and must still read as names
    assert "context Main" in text
    assert "type Main" in text
    # cards carry only an id, so the name comes from the committed card tables
    assert "Cinderace" in text
    assert not [ln for ln in text.splitlines() if len(ln) > WIDTH]


def test_face_down_cards_are_named_as_unknown_not_dropped():
    """An Observation's prize pile is six nulls — say so instead of listing six phantom cards."""
    text = flat(dump("82756664-37", corrections=None, replays=None))
    assert "PRIZES 6 of 6 left · 0 taken" in text
    assert "contents: face down, not in this snapshot" in text


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
    assert "[0] Ability the STADIUM = Gravity Mountain" in flat(render(hit))


def test_an_option_on_a_non_zone_area_keeps_the_area_name():
    """ENERGY / TOOL / PRE_EVOLUTION hang off a Pokémon, so there is no zone list to index — say
    which area it was rather than printing a bare index."""
    from train.blunder.frame_view import FrameHit
    hit = FrameHit(episode_id=1, frame=0, current={
        "turn": 3, "firstPlayer": 0, "yourIndex": 0, "result": -1,
        "players": [{"active": [], "bench": [], "prize": 6, "handCount": 0, "deckCount": 40,
                     "discard": []}] * 2,
    }, source="synthetic", options=[{"type": 5, "area": 8, "index": 1}])
    assert "s0 ENERGY1" in render(hit)


def test_a_null_pokemon_slot_renders_as_unknown():
    from train.blunder.frame_view import FrameHit
    hit = FrameHit(episode_id=1, frame=0, current={
        "turn": 3, "firstPlayer": 0, "yourIndex": 0, "result": -1,
        "players": [{"active": [None], "bench": [], "prize": 6, "handCount": 3, "deckCount": 40,
                     "discard": []},
                    {"active": [], "bench": [], "prize": 6, "handCount": 3, "deckCount": 40,
                     "discard": []}],
    }, source="synthetic")
    assert flat(UNKNOWN_CARD) in flat(render(hit))


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

    body = flat(render(hit))
    assert "turn player s1" in body                # turn 2, firstPlayer 0 -> seat 1
    assert "s1 is the turn player" in body
    assert "the 1 manual attach is still available" in body
    assert "stadium: none" in body
    assert "AGENT CHOSE [0] End" in body           # a target-less option keeps its type


def test_a_frame_past_the_end_of_a_film_is_a_clean_lookup_error(tmp_path):
    replay = {"info": {"EpisodeId": 4242}, "steps": [[{"visualize": [{"current": {}}]}]]}
    path = tmp_path / "replay.json"
    path.write_text(json.dumps(replay), encoding="utf-8")
    with pytest.raises(LookupError, match="no frame 7"):
        find_frame(4242, 7, replay_path=path)


# --- helpers ----------------------------------------------------------------------------------

def _seat_block(text: str, seat: int) -> str:
    """Everything the read-out says about one seat."""
    marker = f"-- SEAT {seat}"
    start = text.index(marker)
    rest = text[start + len(marker):]
    end = rest.find("-- SEAT ")
    return rest if end == -1 else rest[:end]


def _after(block: str, marker: str, *, stop=()) -> str:
    """The slice of ``block`` from ``marker`` up to the first of ``stop``."""
    rest = block[block.index(marker):]
    cuts = [rest.index(s) for s in stop if s in rest]
    return rest[:min(cuts)] if cuts else rest
