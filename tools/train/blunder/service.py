"""Integration glue between the tagging shell (UI) and the data spine.

Pure functions (no HTTP) so they are unit-testable: build the labeled-decision payload
the UI dropdowns consume, and turn one posted tag into a validated, logged Correction.
``shell.py`` is a thin stdlib-HTTP wrapper over these.
"""
from __future__ import annotations

from pathlib import Path

from .correction import Correction, build_correction
from .decisions import Decision, iter_decisions
from .decode import option_label
from .seats import detect_seat
from .store import DEFAULT_PATH, append_correction, load_corrections


def _labeled_options(decision: Decision) -> list[dict]:
    return [{"pos": i, "label": option_label(opt, decision.current)}
            for i, opt in enumerate(decision.options)]


def _labels_for(decision: Decision, positions: list[int]) -> str:
    # The film's `selected` is not always a clean option-position (engine quirk; e.g.
    # Count/Card selects), so label only the in-range positions and skip the rest.
    n = len(decision.options)
    return ", ".join(option_label(decision.options[i], decision.current)
                     for i in positions if isinstance(i, int) and 0 <= i < n)


def decisions_payload(replay: dict, our_team: str | None = None) -> dict:
    """A JSON-able view of every Decision (frame, seat, turn, context, labeled options,
    chosen positions) plus the detected seat -- what the tagging UI renders."""
    info = replay.get("info") or {}
    decisions = iter_decisions(replay)
    return {
        "episode_id": info.get("EpisodeId"),
        "team_names": info.get("TeamNames"),
        "seat": detect_seat(replay, our_team) if our_team else None,
        "decisions": [
            {
                "frame": d.frame, "seat": d.seat, "turn": d.turn,
                "context": d.select_context, "type": d.select_type,
                "chosen": d.chosen, "options": _labeled_options(d),
            }
            for d in decisions
        ],
    }


def _film(replay: dict) -> list[dict]:
    steps = replay.get("steps") or []
    return (steps[0][0].get("visualize") or []) if steps and steps[0] else []


def frames_payload(replay: dict, our_team: str | None = None) -> dict:
    """Every film frame, numbered like HEROZ's stepper (1-based ``step`` of ``total``).

    Each frame carries its 0-based ``frame`` (used when POSTing a tag), ``turn``,
    ``context``, a ``selected_label`` (mirrors the viewer's "Selected Action"), and --
    for taggable frames (those that are real Decisions) -- the labeled ``options``.
    """
    info = replay.get("info") or {}
    film = _film(replay)
    by_frame: dict[int, Decision] = {d.frame: d for d in iter_decisions(replay)}

    frames = []
    for idx, raw in enumerate(film):
        select = raw.get("select") or {}
        current = raw.get("current") or {}
        decision = by_frame.get(idx)
        if decision is not None:
            options = _labeled_options(decision)
            chosen = decision.chosen
            selected_label = _labels_for(decision, decision.chosen)
        else:
            options, chosen, selected_label = [], (raw.get("selected") or []), ""
        frames.append({
            "step": idx + 1, "frame": idx,
            "turn": current.get("turn"), "seat": current.get("yourIndex"),
            "context": select.get("context"), "type": select.get("type"),
            "taggable": decision is not None,
            "chosen": chosen, "selected_label": selected_label, "options": options,
        })

    return {
        "episode_id": info.get("EpisodeId"), "team_names": info.get("TeamNames"),
        "seat": detect_seat(replay, our_team) if our_team else None,
        "total": len(film), "frames": frames,
    }


def list_corrections(replay: dict, store_path: Path | str = DEFAULT_PATH) -> list[dict]:
    """The Corrections already logged for THIS replay's episode -- the review list."""
    episode_id = (replay.get("info") or {}).get("EpisodeId")
    out = []
    for c in load_corrections(store_path):
        if c.episode_id != episode_id:
            continue
        frame = c.decision.get("frame")
        out.append({
            "id": c.id, "frame": frame, "step": (frame or 0) + 1, "turn": c.decision.get("turn"),
            "seat": c.seat, "source": c.source, "category": c.category,
            "correct": c.correct, "correct_label": c.correct_label, "rationale": c.rationale,
        })
    return out


def record_correction(
    replay: dict,
    *,
    frame: int,
    correct: list[int],
    category: str,
    rationale: str,
    source: str,
    agent: str,
    store_path: Path | str = DEFAULT_PATH,
    **identity,
) -> Correction:
    """Build, validate (ADR-0015) and append a Correction for the Decision at ``frame``.

    ``chosen``/``correct`` are auto-labeled via the decoder. ``identity`` forwards
    optional keys (submission_id, agent_version, episode_time, tagged_at, attribution).
    """
    decision = next((d for d in iter_decisions(replay) if d.frame == frame), None)
    if decision is None:
        raise ValueError(f"no Decision at frame {frame}")

    correction = build_correction(
        decision, source=source, agent=agent, correct=list(correct),
        category=category, rationale=rationale,
        chosen_label=_labels_for(decision, decision.chosen),
        correct_label=_labels_for(decision, list(correct)),
        **identity,
    )
    append_correction(correction, store_path)
    return correction
