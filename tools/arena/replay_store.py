"""Persist PvC replays under data/replays/PvC/ (ADR-0058).

Same shape as the Self-play Corpus — a tagged `env.toJSON()` written uncompressed —
so the blunder inspector and Tuner ingest PvC games unchanged. The Arena's own
metadata (Visitor, Forfeit, the Rating) rides in `info.pvc`; downstream tools ignore
unknown info keys, and the file stays one self-contained artifact for the SSH pull.
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1]
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from sim.selfplay import episode_id, tag_replay  # noqa: E402

REPLAY_DIR = _TOOLS.parent / "data" / "replays" / "PvC"


def save_replay(replay: dict, dest_dir: Path, *, agent: str, visitor: str | None,
                human_seat: int, forfeit: str | None = None,
                stamp: str | None = None) -> Path:
    """Tag + write one PvC replay; returns the file path. `forfeit` is None (played out), "concede"
    or "timeout"; only a timeout counts as abandoned — a concede is a deliberate finish."""
    stamp = stamp or time.strftime("%Y%m%d-%H%M%S")
    # the random tail keeps concurrent same-second finishes (and their EpisodeIds)
    # from silently overwriting each other
    stem = f"pvc_{agent}_{stamp}_{uuid.uuid4().hex[:6]}"
    names = [visitor or "Visitor", agent] if human_seat == 0 else [agent, visitor or "Visitor"]
    tagged = tag_replay(replay, episode_id=episode_id(stem, 0), team_names=names)
    tagged["info"]["pvc"] = {
        "visitor": visitor,
        "agent": agent,
        "human_seat": human_seat,
        "forfeit": forfeit,
        "abandoned": forfeit == "timeout",
        "rating": None,
    }
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / f"{stem}.json"
    path.write_text(json.dumps(tagged, ensure_ascii=False), encoding="utf-8")
    return path


def patch_rating(path: Path, rating: dict) -> None:
    """Embed the post-game Rating into an already-saved replay's info.pvc."""
    path = Path(path)
    replay = json.loads(path.read_text(encoding="utf-8"))
    replay.setdefault("info", {}).setdefault("pvc", {})["rating"] = rating
    path.write_text(json.dumps(replay, ensure_ascii=False), encoding="utf-8")
