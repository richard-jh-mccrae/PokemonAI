"""Mine labelled states from replays for the Automatic Value Model (ADR-0042).

For each of MY decision frames in a replay, build the Tier-3/Tier-4 feature vector by running the
shipped Pilot's ``_board`` on the recorded agent ``obs`` (the same obs the tuner replays on), and
label it with the eventual winner (did the seat that owned this decision win?). One row per decision
frame — thousands of labelled states per match, so the noisy one-bit-per-match W/L becomes calibrated
supervision (the ADR-0007 "state-level label" argument).
"""
from __future__ import annotations

from common.value.features import features_from_board
from meta_tracker.parse import winner_index
from train.blunder.decisions import _film


def rows_from_replay(pilot, replay: dict):
    """``won`` is 1.0 if the seat owning the decision won. A DRAW carries no win label, so those
    replays are skipped. `pilot._board` is pure on the obs: this never touches the live engine."""
    winner = winner_index(replay)
    if winner is None:
        return
    film = _film(replay)
    for i, frame in enumerate(film):
        select = frame.get("select")
        if not isinstance(select, dict) or not select.get("option"):
            continue
        nxt = film[i + 1] if i + 1 < len(film) else None
        obs = nxt.get("obs") if nxt else None
        if not obs:
            continue
        seat = (obs.get("current") or {}).get("yourIndex")
        if seat is None:
            continue
        try:
            board = pilot._board(obs, obs.get("select"))
        except Exception:
            continue                                   # a malformed frame never kills the extraction
        yield features_from_board(board), (1.0 if seat == winner else 0.0)


def extract_dataset(pilot, replays):
    """Accumulate ``(rows, labels)`` across ``replays`` (an iterable of loaded replay dicts)."""
    rows, labels = [], []
    for replay in replays:
        for feats, won in rows_from_replay(pilot, replay):
            rows.append(feats)
            labels.append(won)
    return rows, labels
