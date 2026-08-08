"""Extract taggable Decisions from a cabt replay's full-information film.

A Decision is one engine ``select`` (a choice among options) at one frame of the
``visualize`` film, paired with the choice that was made (``chosen``) and the
full-information board state (``current``). The film is full-info -- both players'
hands are visible -- unlike the per-seat agent Observation, which hides the opponent.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    episode_id: int | None
    frame: int            # index into the visualize film
    seat: int             # current.yourIndex -- the acting player
    turn: int
    select_context: str   # e.g. "Main", "Switch", "Mulligan"
    select_type: str      # e.g. "Main", "Card", "YesNo"
    options: list[dict]   # legal option list (select.option)
    chosen: list[int]     # positional indices into options (recorded selection)
    current: dict         # full-information board snapshot at this Decision
    obs: dict | None = None  # agent observation (int enums) for the Tuner -- aligned to options

    def snapshot(self) -> dict:
        """The embedded state a Correction stores -- already decoupled from the
        source replay (options/current are deep copies made at extraction)."""
        return {
            "frame": self.frame,
            "turn": self.turn,
            "select_context": self.select_context,
            "select_type": self.select_type,
            "options": self.options,
            "current": self.current,
        }


def _film(replay: dict) -> list[dict]:
    """The full-information per-frame film (the engine attaches it to steps[0][0])."""
    steps = replay.get("steps") or []
    if not steps or not steps[0]:
        return []
    return steps[0][0].get("visualize") or []


def iter_decisions(replay: dict) -> list[Decision]:
    """Every option-choice with a recorded selection, in film order. The selection for frame ``i``
    lives in ``film[i+1].selected`` — the film offsets selection by +1."""
    episode_id = (replay.get("info") or {}).get("EpisodeId")
    film = _film(replay)
    out: list[Decision] = []
    for i, frame in enumerate(film):
        select = frame.get("select")
        if not isinstance(select, dict) or not select.get("option"):
            continue
        nxt = film[i + 1] if i + 1 < len(film) else None
        chosen = nxt.get("selected") if nxt else None
        if chosen is None:
            continue
        current = frame.get("current") or {}
        out.append(
            Decision(
                episode_id=episode_id,
                frame=i,
                seat=current.get("yourIndex"),
                turn=current.get("turn"),
                select_context=select.get("context"),
                select_type=select.get("type"),
                # deep-copy so Decision is a self-contained snapshot, decoupled
                # from source replay (survives replay mutation/deletion).
                options=copy.deepcopy(select.get("option")),
                chosen=list(chosen),
                current=copy.deepcopy(current),
                # agent obs (int enums) recorded one frame after the prompt, same as
                # `selected` -- so it aligns option-for-option with this Decision (verified).
                obs=copy.deepcopy(nxt.get("obs")),
            )
        )
    return out
