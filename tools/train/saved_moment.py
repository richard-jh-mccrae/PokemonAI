"""Resolve one saved replay moment without binding consumers to a storage layout."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from meta_tracker.parse import load_replay
from train.blunder.store import jsonl_files


REPO = Path(__file__).resolve().parents[2]
DEFAULT_CORRECTIONS = REPO / "data" / "corrections"
DEFAULT_REPLAYS = REPO / "data" / "replays"
DEFAULT_FIXTURES = REPO / "tests" / "fixtures" / "corrections"

_KEY = re.compile(r"^\s*(?:ep)?(\d+)\s*[-_:\s]\s*f?(\d+)\s*$", re.IGNORECASE)
_KEY_IN_TEXT = re.compile(r"(?:ep)?(\d{6,})\s*[-_:\s]\s*f?(\d+)", re.IGNORECASE)


def _note_keys(note) -> set[tuple[int, int]]:
    return {(int(a), int(b)) for a, b in _KEY_IN_TEXT.findall(str(note or ""))}


def parse_frame_key(key: str) -> tuple[int, int]:
    text = str(key).strip()
    match = _KEY.match(text)
    if not match:
        hint = ""
        if re.search(r"-\s*[tm]\d", text, re.IGNORECASE):
            hint = (" — that looks like a scoped Correction key (a Turn or a Match, not one "
                    "frame); pass the Anchor frame instead")
        raise ValueError(f"not an <episode>-<frame> key: {key!r}{hint}")
    return int(match.group(1)), int(match.group(2))


@dataclass
class SavedMoment:
    episode_id: int
    frame: int
    current: dict
    source: str
    source_path: Path | None = None
    full_info: bool = True
    select_context: int | str | None = None
    select_type: int | str | None = None
    options: list | None = None
    turn: int | None = None
    asked_seat: int | None = None
    chosen: list | None = None
    correction: dict | None = None
    obs_recorded: bool = False


def _film(replay: dict) -> list:
    steps = replay.get("steps") or []
    if not steps or not steps[0]:
        return []
    return steps[0][0].get("visualize") or []


def _corrections_in(path: Path):
    from train.blunder.correction import Correction

    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            if line.strip():
                yield Correction.from_dict(json.loads(line))
        except (ValueError, TypeError):
            continue


def _from_correction(record: dict, path: Path) -> SavedMoment:
    decision = record.get("decision") or {}
    current = decision.get("current") or {}
    return SavedMoment(
        episode_id=record.get("episode_id"), frame=decision.get("frame"), current=current,
        source="Correction log — its embedded full-information snapshot", source_path=path,
        turn=decision.get("turn"), asked_seat=current.get("yourIndex", record.get("seat")),
        chosen=record.get("chosen"), correction=record, obs_recorded=bool(record.get("obs")),
        select_context=decision.get("select_context"), select_type=decision.get("select_type"),
        options=decision.get("options") or [],
    )


def _from_film(replay: dict, path: Path, episode_id: int, frame: int) -> SavedMoment | None:
    film = _film(replay)
    if not 0 <= frame < len(film):
        return None
    entry = film[frame] or {}
    current = entry.get("current") or {}
    select = entry.get("select") if isinstance(entry.get("select"), dict) else {}
    following = film[frame + 1] if frame + 1 < len(film) else None
    return SavedMoment(
        episode_id=episode_id, frame=frame, current=current,
        source=f"Replay film, frame {frame} of {len(film)} — full information",
        source_path=path, turn=current.get("turn"), asked_seat=current.get("yourIndex"),
        chosen=(following or {}).get("selected"), obs_recorded=bool((following or {}).get("obs")),
        select_context=select.get("context"), select_type=select.get("type"),
        options=select.get("option") or [],
    )


def _from_fixture(record: dict, path: Path, episode_id: int, frame: int) -> SavedMoment:
    obs = record.get("obs") or {}
    current = obs.get("current") or {}
    select = obs.get("select") if isinstance(obs.get("select"), dict) else {}
    correction = ({"correct": record.get("correct"), "rationale": record.get("note")}
                  if record.get("correct") is not None or record.get("note") else None)
    return SavedMoment(
        episode_id=episode_id, frame=frame, current=current,
        source="Test fixture — the per-seat agent Observation", source_path=path, full_info=False,
        turn=current.get("turn"), asked_seat=current.get("yourIndex"), correction=correction,
        obs_recorded=True, select_context=select.get("context"), select_type=select.get("type"),
        options=select.get("option") or [],
    )


def resolve_saved_moment(episode_id: int, frame: int, *, replays=DEFAULT_REPLAYS,
                         corrections=DEFAULT_CORRECTIONS, fixtures=DEFAULT_FIXTURES,
                         replay_path: Path | None = None) -> SavedMoment:
    searched: list[str] = []
    if replay_path is not None:
        replay_path = Path(replay_path)
        hit = _from_film(load_replay(replay_path), replay_path, episode_id, frame)
        if hit is None:
            raise LookupError(f"{replay_path} has no frame {frame}")
        return hit

    corrections = Path(corrections) if corrections else None
    if corrections and corrections.exists():
        searched.append(f"{corrections}/**/corrections.jsonl")
        for path in jsonl_files(corrections):
            for correction in _corrections_in(path):
                if (correction.episode_id == episode_id
                        and (correction.decision or {}).get("frame") == frame):
                    return _from_correction(correction.to_dict(), path)

    replays = Path(replays) if replays else None
    if replays and replays.is_dir():
        searched.append(f"{replays}/**/*.json[.gz]")
        candidates = (sorted(replays.rglob(f"episode-{episode_id}-*.json"))
                      + sorted(replays.rglob(f"episode-{episode_id}-*.json.gz")))
        if not candidates:
            candidates = sorted(replays.rglob("*.json")) + sorted(replays.rglob("*.json.gz"))
        for path in candidates:
            if path.name.endswith("-logs.json"):
                continue
            if path.name.startswith("episode-") and f"episode-{episode_id}-" not in path.name:
                continue
            try:
                replay = load_replay(path)
            except (OSError, ValueError):
                continue
            replay_episode = ((replay.get("info") or {}).get("EpisodeId")
                              if isinstance(replay, dict) else None)
            if isinstance(replay, dict) and replay_episode == episode_id:
                hit = _from_film(replay, path, episode_id, frame)
                if hit is not None:
                    return hit
    elif replays:
        searched.append(f"{replays} (absent — raw replays are not committed, ADR-0002)")

    fixtures = Path(fixtures) if fixtures else None
    if fixtures and fixtures.is_dir():
        searched.append(f"{fixtures}/*.json")
        for path in sorted(fixtures.glob("*.json")):
            try:
                record = load_replay(path)
            except (OSError, ValueError):
                continue
            if record.get("obs") and (episode_id, frame) in _note_keys(record.get("note")):
                return _from_fixture(record, path, episode_id, frame)

    places = "; ".join(searched or ["nothing"])
    raise LookupError(
        f"frame {episode_id}-{frame} not found. Searched: {places}. A replay makes any frame "
        "resolvable — pass --replay <file> if you have the episode's film (raw replays are not "
        "committed).")


find_frame = resolve_saved_moment
FrameHit = SavedMoment
