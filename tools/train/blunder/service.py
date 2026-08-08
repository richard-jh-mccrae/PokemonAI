"""Integration glue between the tagging shell (UI) and the data spine.

Pure functions (no HTTP) so they are unit-testable: build the labeled-decision payload
the UI dropdowns consume, and turn one posted tag into a validated, logged Correction.
``shell.py`` is a thin stdlib-HTTP wrapper over these.
"""
from __future__ import annotations

from pathlib import Path

from .correction import (
    Correction, build_correction, identity_key, select_min_count, subject_of,
)
from .decisions import Decision, iter_decisions
from .decode import option_label
from .seats import detect_seat
from .store import DEFAULT_PATH, append_correction, load_corrections
from .telemetry_log import record_for


def _labeled_options(decision: Decision) -> list[dict]:
    return [{"pos": i, "label": option_label(opt, decision.current)}
            for i, opt in enumerate(decision.options)]


def _labels_for(decision: Decision, positions: list[int]) -> str:
    # Film's `selected` isn't always a clean option-position (engine quirk; e.g.
    # Count/Card selects) -> label only in-range positions, skip the rest.
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


def frames_payload(replay: dict, our_team: str | None = None,
                   live_records: list[dict] | None = None, live_seat: int | None = None) -> dict:
    """``step`` is 1-based like HEROZ's stepper; ``frame`` is the 0-based id a tag POSTs. ``live`` is
    the @T record the SHIPPED agent emitted at that decision (ADR-0019)."""
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
        live = None
        if live_records is not None and decision is not None and decision.seat == live_seat:
            live = record_for(replay, live_records, seat=live_seat, frame=idx)
        frames.append({
            "step": idx + 1, "frame": idx,
            "turn": current.get("turn"), "seat": current.get("yourIndex"),
            "context": select.get("context"), "type": select.get("type"),
            "taggable": decision is not None,
            "chosen": chosen, "selected_label": selected_label, "options": options,
            # Read through the SAME derivation `build_correction` validates with, so the pane and
            # the validator cannot disagree; `None` keeps the pane refusing where the validator would.
            "min_count": select_min_count(decision.obs) if decision is not None else None,
            "live": live,
        })

    return {
        "episode_id": info.get("EpisodeId"), "team_names": info.get("TeamNames"),
        "seat": detect_seat(replay, our_team) if our_team else None,
        "total": len(film), "frames": frames,
    }


def _live_for(replay, live_records, *, seat, frame):
    return record_for(replay, live_records, seat=seat, frame=frame) if live_records is not None else None


def _turn_span(replay: dict, *, seat: int, turn: int, live_records) -> list[dict]:
    """No per-Decision ``current``: the Anchor carries the one board a human reads, and a full-info
    snapshot per Decision would cost ~10 KB each (ADR-0049)."""
    return [
        {"frame": d.frame, "select_context": d.select_context, "select_type": d.select_type,
         "chosen": list(d.chosen), "chosen_label": _labels_for(d, d.chosen), "obs": d.obs,
         "live_trace": _live_for(replay, live_records, seat=seat, frame=d.frame)}
        for d in iter_decisions(replay) if d.seat == seat and d.turn == turn
    ]


def build_span(replay: dict, decision: Decision, *, scope: str, live_records) -> list[dict] | None:
    """The Span a Correction of ``scope`` embeds, anchored at ``decision`` (ADR-0049)."""
    if scope == "turn":
        return _turn_span(replay, seat=decision.seat, turn=decision.turn, live_records=live_records)
    return None


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
            "posture_mismatch": c.posture_mismatch,   # human flagged the opponent Read wrong (ADR-0041)
            "scope": c.scope, "subject": c.subject,   # what the tag is ABOUT (ADR-0049) — a Turn
            "span_len": len(c.span or []),            # Correction and the Decision Corrections inside
            "turn_plan": c.turn_plan,                 # the human's ideal-line note (edit-restore)
        })                                            # it share a step, so the list must distinguish them
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
    live_records: list[dict] | None = None,
    replace_id: str | None = None,
    scope: str = "decision",
    **identity,
) -> Correction:
    """``frame`` is always the Anchor (a real Decision), but off ``decision`` scope the record is
    keyed by the Scope subject; ONE Correction per subject, else ``ValueError`` (ADR-0015/ADR-0049)."""
    decision = next((d for d in iter_decisions(replay) if d.frame == frame), None)
    if decision is None:
        raise ValueError(f"no Decision at frame {frame}")

    subject = subject_of(scope, decision.snapshot())
    key = (decision.episode_id, decision.seat, scope, subject)
    existing = [c for c in load_corrections(store_path)
                if identity_key(c) == key and c.id != replace_id]
    if existing:
        where = {"decision": f"frame {frame}", "turn": f"turn {subject}"}.get(scope, "unknown scope")
        raise ValueError(
            f"a correction already exists at this {scope} (episode {decision.episode_id}, "
            f"seat {decision.seat}, {where}) - edit or remove it first")

    live_trace = (record_for(replay, live_records, seat=decision.seat, frame=frame)
                  if live_records is not None else None)
    correction = build_correction(
        decision, source=source, agent=agent, correct=list(correct),
        category=category, rationale=rationale,
        chosen_label=_labels_for(decision, decision.chosen),
        correct_label=_labels_for(decision, list(correct)),
        live_trace=live_trace,
        scope=scope,
        span=build_span(replay, decision, scope=scope, live_records=live_records),
        **identity,
    )
    append_correction(correction, store_path)
    return correction
