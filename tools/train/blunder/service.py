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
from .store import DEFAULT_PATH, append_correction


def _labeled_options(decision: Decision) -> list[dict]:
    return [{"pos": i, "label": option_label(opt, decision.current)}
            for i, opt in enumerate(decision.options)]


def _labels_for(decision: Decision, positions: list[int]) -> str:
    return ", ".join(option_label(decision.options[i], decision.current) for i in positions)


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
