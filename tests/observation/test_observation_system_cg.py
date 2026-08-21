"""ObservationState over the deployed engine's own recorded games (system level).

Every frame in a parity trace is the cg engine's verbatim board printout plus the decision taken,
so replaying one through the advance chain verifies board state before and after every decision
of a real game — no Decision subsystem needed, the decisions are already on the tape. The extras
piece is exempt from the fresh-build comparison: a chain legitimately carries lock knowledge a
from-scratch build of one frame cannot have."""
from __future__ import annotations

from observation_builders import build_observation, advance_observation

import gzip
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "parity"))

from from_cabt import convert  # noqa: E402

from common.observation import HiddenHand, ObservationState, VisibleHand  # noqa: E402

EPISODES = ["match-replay.json", "episode-82749168-replay.json.gz"]


def _trace(name):
    path = REPO / "tests" / "fixtures" / name
    if name.endswith(".gz"):
        return convert(json.loads(gzip.decompress(path.read_bytes())))
    return convert(json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("name", EPISODES)
@pytest.mark.parametrize("seat", [0, 1])
def test_a_real_engine_game_replays_through_the_advance_chain(name, seat):
    trace = _trace(name)
    deck = tuple(trace.decks[seat])
    frames = [frame["obs"] for frame in trace.frames
              if (frame["obs"].get("current") or {}).get("yourIndex") == seat]
    assert len(frames) > 10, "the episode barely shows this seat"
    board = build_observation(frames[0], decklist=deck)
    last_turn, prizes_seen = 0, 0
    for index, obs in enumerate(frames[1:], start=1):
        board = advance_observation(board, obs)
        fresh = build_observation(obs, decklist=deck)
        assert board == fresh and board.position_key == fresh.position_key, \
            f"{name} seat {seat} frame {index}: observation diverged"
        # The boundary and the ledger hold on every real frame.
        assert isinstance(board.them.hand, HiddenHand)
        assert isinstance(board.me.hand, VisibleHand) and len(board.me.hand) == board.me.hand_count
        # Time only moves forward; prizes only shrink once setup has laid them.
        assert board.turn.number >= last_turn
        if prizes_seen:
            assert board.me.prize_count <= prizes_seen
        last_turn, prizes_seen = board.turn.number, board.me.prize_count
        # The unseen pool is exactly deck plus prizes at REST (the main menu): during any other
        # select a played card can legitimately be in no zone while the engine asks about it.
        if (board.select is not None and board.select.context == 0
                and board.looking is None and not board.me.active_hidden):
            assert sum(count for _cid, count in board.deck_counts) \
                == board.me.deck_count + board.me.prize_count, \
                f"{name} seat {seat} frame {index}: unseen pool drifted"
