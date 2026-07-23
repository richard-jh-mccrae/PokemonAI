"""The doom-relax replay audit (doom-shadow grill follow-up, 2026-07-23) — REQ-DOOMAUDIT.

`doom_matched_relax` shipped on a 15-frame grill + a wide-CI gauntlet A/B; this audit turns fresh
self-play/gauntlet FILMS into ground truth for the exact boolean: on the last decision of each of a
seat's turns, the pilot-replayed `threat_shadow` says what the doom read decided, and the film's
LATER frames say what actually happened to that Active on the opponent's next turn (a KO'd body's
serial lands in its owner's discard). Cohorts:

  FALSE_RELAX  — the matched relax cleared a worst-case doom cry, the body stayed in, and it DIED:
                 the dangerous direction, each one a frame to grill.
  RELAX_OK     — relax cleared the cry and the body survived: the pessimism the relax exists to cure.
  DOOM_HIT / DOOM_PHANTOM — the doom bit stood (matched-confirmed or worst-case) and the body
                 died / survived.
  SAFE_MISS / SAFE_OK — the WORST-CASE oracle itself said safe and the body died / survived
                 (the incumbent's own blind spot — hidden burst class — as a baseline).
  DODGED       — the body at the audited decision was no longer Active when the opponent's turn
                 began (we switched/it was gusted): the counterfactual is unobservable, excluded.

Pure-logic core, engine-free tests: `audit_replay` takes an injectable `explain(obs) -> shadow`
so these tests drive synthetic films through fake shadows; the CLI wires the real per-(game, seat)
stateful Pilot (`tune._build_pilot`, fresh per game — stateful WITHIN a game is live-faithful).
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))

from train.probes.doom_audit import (  # noqa: E402
    audit_replay,
    classify,
    seat_agent,
    tally,
    turn_player,
)


# ---------------------------------------------------------------------------- synthetic films
def _body(serial, hp=70):
    return {"serial": serial, "id": 1, "hp": hp, "maxHp": hp, "energies": []}


def _frame(*, seat, turn, first_player=0, my_active, my_discard=(), select=True):
    """One visualize-shaped film frame: `seat` is the acting seat (current.yourIndex); the acting
    seat's board carries `my_active`/`my_discard`, the other seat's board a fixed opponent body."""
    players = [None, None]
    players[seat] = {"active": [my_active] if my_active else [],
                     "discard": [{"serial": s, "id": 99} for s in my_discard], "bench": []}
    players[1 - seat] = {"active": [_body(900, hp=200)], "discard": [], "bench": []}
    return {"obs": {"current": {"yourIndex": seat, "turn": turn, "firstPlayer": first_player,
                                "players": players}},
            "current": {"yourIndex": seat, "turn": turn, "firstPlayer": first_player,
                        "players": players},
            "select": {"option": [1, 2], "context": 0} if select else None,
            "selected": None}


def _film_frames(frames):
    return {"steps": [[{"visualize": frames}]],
            "rewards": [0, 0], "info": {"EpisodeId": 42, "TeamNames": ["x#0-a", "x#1-b"]}}


def _shadow(*, old=True, final=False, decided=True, matched=True, charged=0, hp=70):
    return {"doom_old": old, "doom_curve": False, "doom_incoming": 0, "my_hp": hp,
            "agree": True, "doom_charged": charged, "matched": matched, "decided": decided,
            "doom_final": final}


def _explain_with(shadows):
    """A fake `explain`: pops one shadow per call (in film order of the audited seat's frames)."""
    queue = list(shadows)

    def explain(obs):
        return queue.pop(0) if queue else None
    return explain


# ---------------------------------------------------------------------------- unit: helpers
@pytest.mark.req("REQ-DOOMAUDIT-0001")
def test_seat_agent_parses_the_recorder_team_name():
    """TeamNames are `<stem>#<seat>-<agent>` (gauntlet/selfplay recorders); the agent name is
    everything after the seat marker — underscores in agent names and dashes in stems both survive."""
    assert seat_agent("ms__dp_20260723-101010_abc1234-gauntlet#0-mega_starmie") == "mega_starmie"
    assert seat_agent("stem#1-dragapult_ex") == "dragapult_ex"
    assert seat_agent("no-marker-here") is None
    assert seat_agent(None) is None


@pytest.mark.req("REQ-DOOMAUDIT-0001")
def test_turn_player_alternates_from_first_player():
    """Turn t's player: firstPlayer takes odd turns (1-based) — seat = (firstPlayer + t - 1) % 2."""
    assert turn_player(1, first_player=0) == 0
    assert turn_player(2, first_player=0) == 1
    assert turn_player(1, first_player=1) == 1
    assert turn_player(4, first_player=1) == 0


@pytest.mark.req("REQ-DOOMAUDIT-0002")
def test_classify_covers_the_six_cohorts():
    relax = _shadow(old=True, final=False, decided=True)
    doom = _shadow(old=True, final=True, decided=True)
    safe = _shadow(old=False, final=False, decided=False)
    assert classify(relax, died=True) == "FALSE_RELAX"
    assert classify(relax, died=False) == "RELAX_OK"
    assert classify(doom, died=True) == "DOOM_HIT"
    assert classify(doom, died=False) == "DOOM_PHANTOM"
    assert classify(safe, died=True) == "SAFE_MISS"
    assert classify(safe, died=False) == "SAFE_OK"


# ---------------------------------------------------------------------------- audit_replay
def _three_turn_film(*, opp_start_serial, later_discard, end_early=False):
    """Seat 0's turn 1 (two decisions on body 5), opp's turn 2 (their board shows MY active =
    ``opp_start_serial``), then my turn 3 observation carrying ``later_discard`` — or, with
    ``end_early``, the game ends during their turn and only a terminal frame shows the discard."""
    frames = [
        _frame(seat=0, turn=1, my_active=_body(5)),                    # my decision (mid-turn)
        _frame(seat=0, turn=1, my_active=_body(5)),                    # my LAST decision this turn
        _frame(seat=1, turn=2, my_active=_body(900, hp=200)),          # opp acting; my board is
    ]
    # the opponent-side frame views MY board from players[0]:
    frames[2]["current"]["players"][0] = {"active": [_body(opp_start_serial)],
                                          "discard": [], "bench": []}
    frames[2]["obs"]["current"] = frames[2]["current"]
    if end_early:
        terminal = _frame(seat=1, turn=2, my_active=_body(900, hp=200), select=False)
        terminal["current"]["players"][0] = {"active": [], "discard": [
            {"serial": s, "id": 99} for s in later_discard], "bench": []}
        terminal["obs"]["current"] = terminal["current"]
        frames.append(terminal)
    else:
        frames.append(_frame(seat=0, turn=3, my_active=_body(6), my_discard=later_discard))
    return _film_frames(frames)


@pytest.mark.req("REQ-DOOMAUDIT-0003")
def test_relaxed_body_that_dies_next_opponent_turn_is_a_false_relax():
    """Body 5 faces the opponent after a relaxed doom read and its serial is in my discard by my
    next turn → FALSE_RELAX, keyed to the turn's LAST decision (the read closest to facing them)."""
    replay = _three_turn_film(opp_start_serial=5, later_discard=(5,))
    rows = audit_replay(replay, seat=0,
                        explain=_explain_with([_shadow(), _shadow()]))
    assert [r["cohort"] for r in rows] == ["FALSE_RELAX"]
    assert rows[0]["turn"] == 1 and rows[0]["serial"] == 5


@pytest.mark.req("REQ-DOOMAUDIT-0003")
def test_relaxed_body_that_survives_is_relax_ok():
    replay = _three_turn_film(opp_start_serial=5, later_discard=())
    rows = audit_replay(replay, seat=0, explain=_explain_with([_shadow(), _shadow()]))
    assert [r["cohort"] for r in rows] == ["RELAX_OK"]


@pytest.mark.req("REQ-DOOMAUDIT-0003")
def test_body_switched_before_the_opponents_turn_is_dodged():
    """The audited decision was about body 5, but body 6 faced the opponent — the counterfactual
    is unobservable, the row is DODGED regardless of what died later."""
    replay = _three_turn_film(opp_start_serial=6, later_discard=(5,))
    rows = audit_replay(replay, seat=0, explain=_explain_with([_shadow(), _shadow()]))
    assert [r["cohort"] for r in rows] == ["DODGED"]


@pytest.mark.req("REQ-DOOMAUDIT-0003")
def test_game_ending_ko_during_their_turn_is_caught_via_the_terminal_frame():
    """The most important false relax is the one that LOSES the game — no later my-turn frame
    exists, so the death must be read off the terminal frame's discard."""
    replay = _three_turn_film(opp_start_serial=5, later_discard=(5,), end_early=True)
    rows = audit_replay(replay, seat=0, explain=_explain_with([_shadow(), _shadow()]))
    assert [r["cohort"] for r in rows] == ["FALSE_RELAX"]


@pytest.mark.req("REQ-DOOMAUDIT-0003")
def test_worst_case_doom_and_safe_reads_classify_from_the_same_truth():
    doom_replay = _three_turn_film(opp_start_serial=5, later_discard=(5,))
    rows = audit_replay(doom_replay, seat=0, explain=_explain_with(
        [_shadow(final=True), _shadow(final=True)]))
    assert [r["cohort"] for r in rows] == ["DOOM_HIT"]
    safe_replay = _three_turn_film(opp_start_serial=5, later_discard=())
    rows = audit_replay(safe_replay, seat=0, explain=_explain_with(
        [_shadow(old=False, decided=False), _shadow(old=False, decided=False)]))
    assert [r["cohort"] for r in rows] == ["SAFE_OK"]


@pytest.mark.req("REQ-DOOMAUDIT-0003")
def test_sparse_shadow_frames_are_skipped_not_crashed():
    """A frame whose explain yields no shadow (mid-sim guard / no live actives) contributes no row."""
    replay = _three_turn_film(opp_start_serial=5, later_discard=(5,))
    rows = audit_replay(replay, seat=0, explain=_explain_with([None, None]))
    assert rows == []


@pytest.mark.req("REQ-DOOMAUDIT-0005")
def test_mid_turn_relax_marks_the_row_relax_touched():
    """The relax's live value is largely MID-turn (freeing attach/retreat decisions), so a turn
    whose LAST read re-doomed still carries `relax_touched=True` when any earlier read on the same
    body cleared a worst-case cry — the under-count the turn-end cohort alone would hide."""
    replay = _three_turn_film(opp_start_serial=5, later_discard=(5,))
    rows = audit_replay(replay, seat=0, explain=_explain_with(
        [_shadow(old=True, final=False, decided=True),      # mid-turn: relax fired
         _shadow(old=True, final=True, decided=True)]))     # last read: doom stood
    assert [r["cohort"] for r in rows] == ["DOOM_HIT"]
    assert rows[0]["relax_touched"] is True
    # and a turn never touched by a relax stays untouched
    rows = audit_replay(replay, seat=0, explain=_explain_with(
        [_shadow(old=True, final=True), _shadow(old=True, final=True)]))
    assert rows[0]["relax_touched"] is False


@pytest.mark.req("REQ-DOOMAUDIT-0004")
def test_tally_aggregates_cohorts_and_surfaces_false_relaxes():
    rows = [{"cohort": "FALSE_RELAX", "episode": 1, "turn": 3},
            {"cohort": "RELAX_OK"}, {"cohort": "RELAX_OK"},
            {"cohort": "DOOM_PHANTOM"}, {"cohort": "DODGED"}]
    t = tally(rows)
    assert t["FALSE_RELAX"] == 1 and t["RELAX_OK"] == 2
    assert t["DOOM_PHANTOM"] == 1 and t["DODGED"] == 1 and t["SAFE_MISS"] == 0
