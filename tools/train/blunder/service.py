"""Integration glue between the tagging shell (UI) and the data spine.

Pure functions (no HTTP) so they are unit-testable: build the labeled-decision payload
the UI dropdowns consume, and turn one posted tag into a validated, logged Correction.
``shell.py`` is a thin stdlib-HTTP wrapper over these.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from .correction import (
    Correction, build_correction, identity_key, select_min_count, subject_of,
)
from .decisions import Decision, iter_decisions
from .decode import option_label
from .seats import detect_seat
from .store import DEFAULT_PATH, append_correction, load_corrections
from .telemetry_log import (
    decision_seconds as telemetry_decision_seconds, lethal_proof_seconds, record_for,
    records_for, search_timing,
)


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
                "decision_seconds": d.decision_seconds,
            }
            for d in decisions
        ],
    }


def _film(replay: dict) -> list[dict]:
    steps = replay.get("steps") or []
    return (steps[0][0].get("visualize") or []) if steps and steps[0] else []


def _opening_frame(film: list[dict]) -> int:
    """The first frame the board viewer can actually show. The film opens before the deal — the coin
    flip's board has no cards at all, so landing there renders an empty board."""
    for idx, raw in enumerate(film):
        current = raw.get("current") or {}
        if current.get("stadium"):
            return idx
        for player in current.get("players") or []:
            if any(player.get(area) for area in ("active", "bench", "hand")):
                return idx
    return 0


def _live_on_the_wire(record: dict | None) -> dict | None:
    """Keep the large archived search trace server-side; the pane uses distilled timings."""
    return None if record is None else {k: v for k, v in record.items() if k != "diagnostics"}


def _records_by_seat(live_records, live_seat, live_records_by_seat) -> dict[int, list[dict]]:
    """Seat -> the seat's ``@T`` stream. The by-seat map wins; the single-seat stream fills in the
    seat it was loaded for."""
    by_seat = {int(seat): records
               for seat, records in (live_records_by_seat or {}).items() if records is not None}
    if live_records is not None and live_seat is not None and int(live_seat) not in by_seat:
        by_seat[int(live_seat)] = live_records
    return by_seat


def frames_payload(replay: dict, our_team: str | None = None,
                   live_records: list[dict] | None = None, live_seat: int | None = None,
                   live_records_by_seat: dict[int, list[dict]] | None = None) -> dict:
    """``step`` is 1-based like HEROZ's stepper; ``frame`` is the 0-based id a tag POSTs. ``live`` is
    the @T record the SHIPPED agent emitted at that decision (ADR-0019)."""
    info = replay.get("info") or {}
    film = _film(replay)
    decisions = iter_decisions(replay)
    by_frame: dict[int, Decision] = {d.frame: d for d in decisions}
    # The positional join walks every Decision, so run it ONCE for all seats: per-frame `record_for`
    # re-extracts (and deep-copies) the whole film each call, which is quadratic in the film length.
    live_by_frame = records_for(
        decisions, _records_by_seat(live_records, live_seat, live_records_by_seat))

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
        live = live_by_frame.get((decision.seat, idx)) if decision is not None else None
        wire = _live_on_the_wire(live)
        ledger = wire if (wire or {}).get("schema") == "ledger.telemetry" else None
        seconds = telemetry_decision_seconds(live)
        if seconds is None and decision is not None and decision.decision_seconds != 0.0:
            seconds = decision.decision_seconds
        frames.append({
            "step": idx + 1, "frame": idx,
            "turn": current.get("turn"), "seat": current.get("yourIndex"),
            "context": select.get("context"), "type": select.get("type"),
            "taggable": decision is not None,
            "chosen": chosen, "selected_label": selected_label, "options": options,
            "decision_seconds": seconds,
            "lethal_proof_seconds": lethal_proof_seconds(live),
            "search_timing": search_timing(live),
            # Read through the SAME derivation `build_correction` validates with, so the pane and
            # the validator cannot disagree; `None` keeps the pane refusing where the validator would.
            "min_count": select_min_count(decision.obs) if decision is not None else None,
            "live": None if ledger is not None else wire,
            "ledger": ledger,
        })

    return {
        "episode_id": info.get("EpisodeId"), "team_names": info.get("TeamNames"),
        "seat": detect_seat(replay, our_team) if our_team else None,
        "total": len(film), "frames": frames, "opening_frame": _opening_frame(film),
    }


def _turn_span(replay: dict, *, seat: int, turn: int, live_records) -> list[dict]:
    """No per-Decision ``current``: the Anchor carries the one board a human reads, and a full-info
    snapshot per Decision would cost ~10 KB each (ADR-0049)."""
    decisions = iter_decisions(replay)
    live_by_frame = records_for(decisions, {seat: live_records} if live_records is not None else {})
    return [
        {"frame": d.frame, "select_context": d.select_context, "select_type": d.select_type,
         "chosen": list(d.chosen), "chosen_label": _labels_for(d, d.chosen), "obs": d.obs,
         "decision_seconds": d.decision_seconds,
         "live_trace": live_by_frame.get((seat, d.frame))}
        for d in decisions if d.seat == seat and d.turn == turn
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
            "decision_seconds": c.decision.get("decision_seconds"),
            "posture_mismatch": c.posture_mismatch,   # human flagged the opponent belief wrong (ADR-0041)
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
    live_records_by_seat: dict[int, list[dict]] | None = None,
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

    seat_records = (live_records_by_seat or {}).get(decision.seat, live_records)
    live_trace = (record_for(replay, seat_records, seat=decision.seat, frame=frame)
                  if seat_records is not None else None)
    live_seconds = telemetry_decision_seconds(live_trace)
    if live_seconds is not None:
        decision = replace(decision, decision_seconds=live_seconds)
    correction = build_correction(
        decision, source=source, agent=agent, correct=list(correct),
        category=category, rationale=rationale,
        chosen_label=_labels_for(decision, decision.chosen),
        correct_label=_labels_for(decision, list(correct)),
        live_trace=live_trace,
        scope=scope,
        span=build_span(replay, decision, scope=scope, live_records=seat_records),
        **identity,
    )
    append_correction(correction, store_path)
    return correction
