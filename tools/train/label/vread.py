"""The shared per-decision P(win) reader (S3a §D5).

``iter_values`` reads the value net on the **aligned obs** (``film[i+1].obs``) — byte-for-byte the
path `train.value.extract` trains on, so labeler, AIVAT and training can never see different V(s).

**Null-model rule, the inverse of the runtime.** The runtime is fail-open (absent artifact -> 0.5);
offline that would emit ``v=0.5`` for every frame, so this **raises**. Offline tools fail loud.

The record shape is a cross-track contract with S2b: additive fields are non-breaking, renames are not.
"""
from __future__ import annotations

from common.value.features import features_from_board
from train.blunder.decisions import _film


def agent_name_for_seat(replay: dict, seat: int) -> str | None:
    """The **bare** agent name for ``seat`` from ``info.TeamNames``. Corpus films name seats
    ``{stem}#<seat>-<agent>``; a ladder film's plain name passes through. Out-of-range -> None."""
    names = (replay.get("info") or {}).get("TeamNames") or []
    if not (0 <= seat < len(names)):
        return None
    name = names[seat]
    if "#" in name:                                    # corpus: "{stem}#{seat}-{agent}"
        after_hash = name.split("#", 1)[1]             # "{seat}-{agent}"
        if "-" in after_hash:
            return after_hash.split("-", 1)[1]
    return name


def iter_values(pilot, replay: dict, model):
    """One value record per own decision frame, in film order. A null ``model`` raises — see above."""
    if not getattr(model, "present", False):
        raise ValueError(
            "vread requires a present value model — a null/absent model would emit v=0.5 for every "
            "frame (offline tools fail loud, unlike the fail-open runtime). Pass a trained "
            "value_model.json via --model.")
    episode_id = (replay.get("info") or {}).get("EpisodeId")
    film = _film(replay)
    for i, frame in enumerate(film):
        select = frame.get("select")
        if not isinstance(select, dict) or not select.get("option"):
            continue
        nxt = film[i + 1] if i + 1 < len(film) else None
        obs = nxt.get("obs") if nxt else None
        if not obs:
            continue
        cur = obs.get("current") or {}
        seat = cur.get("yourIndex")
        if seat is None:
            continue
        try:
            board = pilot._board(obs, obs.get("select"))
        except Exception:
            continue                                   # a malformed frame never kills the walk
        yield {
            "episode_id": episode_id,
            "frame": i,
            "seat": seat,
            "turn": cur.get("turn"),
            "agent": agent_name_for_seat(replay, seat),
            "v": model.predict(features_from_board(board)),
            "context": select.get("context"),          # additive: lets triage/detect filter contexts
        }
