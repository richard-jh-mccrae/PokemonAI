"""The shared per-decision P(win) reader (S3a design §D5).

``iter_values`` walks a replay's decision frames and, for each one a seat owns, computes the value
net's ``P(win)`` on the **aligned obs** (``film[i+1].obs``) via ``features_from_board(pilot._board(...))``
— byte-for-byte the path ``train.value.extract`` trains on, so the labeler, S2b's AIVAT plug-in, and
value-net training can never see different V(s) for the same frame.

**Null-model rule (the inverse of the runtime).** ``common.value.model.ValueModel`` is fail-open at
runtime: absent artifact → 0.5, so a missing model degrades to the heuristic instead of crashing the
agent mid-match. Offline, that same politeness would emit ``v=0.5`` for every frame — zero signal
presented as data, silently poisoning triage and the θ review. So ``iter_values`` **raises** on a
null model. Offline tools fail loud.

The record shape ``{episode_id, frame, seat, turn, agent, v}`` (plus additive ``context``) is a
cross-track contract with S2b (§D5 / contracts C4 if reconciled) — additive fields are non-breaking;
renames/removals are a breaking change.
"""
from __future__ import annotations

from common.value.features import features_from_board
from train.blunder.decisions import _film


def agent_name_for_seat(replay: dict, seat: int) -> str | None:
    """The **bare** agent name for ``seat`` from ``info.TeamNames``. Corpus films name seats
    ``{stem}#<seat>-<agent>`` (``sim.corpus``), so the bare name is everything after the first
    ``-`` that follows the ``#`` marker — a name with underscores (``mega_lucario``) survives intact.
    A ladder film's plain name (``"SkiChu"``, no ``#``) passes through unchanged. Out-of-range seat
    → None (never raises)."""
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
    """Yield one value record per own decision frame of ``replay``, in film order.

    ``model`` must be a present (non-null) ``ValueModel`` — a null model raises ``ValueError`` (see
    the module docstring). ``pilot._board`` is pure on the obs, so nothing here touches the live
    engine; the yielded ``v`` is ``model.predict`` on that board's feature vector.
    """
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
