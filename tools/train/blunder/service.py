"""Integration glue between the tagging shell (UI) and the data spine.

Pure functions (no HTTP) so they are unit-testable: build the labeled-decision payload
the UI dropdowns consume, and turn one posted tag into a validated, logged Correction.
``shell.py`` is a thin stdlib-HTTP wrapper over these.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from .correction import (
    Correction, build_correction, identity_key, select_min_count, subject_of,
)
from .decisions import Decision, iter_decisions
from .decode import _known_card_name, option_label
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


def _viewer_card(card) -> dict:
    card = card if isinstance(card, dict) else {}
    if card.get("name") is None:
        card["name"] = _known_card_name(card.get("id")) or "Hidden"
    if not isinstance(card.get("energies"), list):
        card["energies"] = []
    return card


def _player_at(raw: dict, seat: int) -> dict | None:
    players = ((raw.get("current") or {}).get("players") or [])
    return players[seat] if seat < len(players) and isinstance(players[seat], dict) else None


def _card_key(card: dict) -> tuple[str, int] | None:
    if isinstance(card.get("serial"), int):
        return "serial", card["serial"]
    if isinstance(card.get("id"), int):
        return "id", card["id"]
    return None


def _zone_card_keys(value) -> set[tuple[str, int]]:
    found = set()
    if isinstance(value, list):
        for item in value:
            found.update(_zone_card_keys(item))
    elif isinstance(value, dict):
        key = _card_key(value)
        if key is not None:
            found.add(key)
        for nested in value.values():
            if isinstance(nested, (dict, list)):
                found.update(_zone_card_keys(nested))
    return found


def _repair_hands(film: list[dict]) -> None:
    seats = max((len(((raw.get("current") or {}).get("players") or [])) for raw in film), default=0)
    exact: list[list[list[dict] | None]] = [[None] * len(film) for _ in range(seats)]
    for frame, raw in enumerate(film):
        for seat in range(seats):
            player = _player_at(raw, seat)
            if player is None:
                continue
            hand = player.get("hand")
            count = int(player.get("handCount") or (len(hand) if isinstance(hand, list) else 0))
            cards = [card for card in (hand or []) if isinstance(card, dict)]
            if isinstance(hand, list) and len(cards) == count:
                exact[seat][frame] = cards

    for seat in range(seats):
        next_exact: list[list[dict] | None] = [None] * len(film)
        upcoming = None
        for frame in range(len(film) - 1, -1, -1):
            if exact[seat][frame] is not None:
                upcoming = exact[seat][frame]
            next_exact[frame] = upcoming
        known: list[dict] = []
        for frame, raw in enumerate(film):
            player = _player_at(raw, seat)
            if player is None:
                continue
            hand = player.get("hand")
            count = int(player.get("handCount") or (len(hand) if isinstance(hand, list) else 0))
            if exact[seat][frame] is not None:
                known = exact[seat][frame] or []
            else:
                outside = set()
                for area, value in player.items():
                    if area not in {"hand", "handCount"}:
                        outside.update(_zone_card_keys(value))
                current = raw.get("current") or {}
                outside.update(_zone_card_keys([
                    card for card in (current.get("stadium") or [])
                    if isinstance(card, dict) and card.get("playerIndex") == seat
                ]))
                select = raw.get("select") or {}
                outside.update(_zone_card_keys([select.get("effect"), select.get("contextCard")]))
                known = [card for card in known if _card_key(card) not in outside]
                if len(known) > count:
                    future = {_card_key(card) for card in (next_exact[frame] or [])}
                    known = [card for card in known if _card_key(card) in future]
                partial = [card for card in (hand or []) if isinstance(card, dict)]
                if partial:
                    by_key = {_card_key(card): card for card in known}
                    by_key.update({_card_key(card): card for card in partial})
                    known = list(by_key.values())
            visible = known[:count]
            player["hand"] = visible + [None] * (count - len(visible))


def _read_agent_deck(team_name: str) -> list[int] | None:
    root = Path(__file__).resolve().parents[3] / "src" / "agents"
    name = team_name.partition("#")[0]
    path = (root / name / "deck.csv").resolve()
    try:
        path.relative_to(root.resolve())
        deck = [int(card_id) for card_id in path.read_text(encoding="utf-8").split()]
    except (OSError, ValueError):
        return None
    return deck if len(deck) == 60 else None


def _viewer_decklists(replay: dict, supplied) -> list[list[int] | None]:
    names = (replay.get("info") or {}).get("TeamNames") or []
    seats = max(len(names), len(supplied or []), 2)
    decks: list[list[int] | None] = []
    for seat in range(seats):
        given = supplied[seat] if supplied is not None and seat < len(supplied) else None
        decks.append([int(card_id) for card_id in given] if given is not None else
                     _read_agent_deck(str(names[seat])) if seat < len(names) else None)
    return decks


def _visible_cards(raw: dict, seat: int) -> Counter:
    current = raw.get("current") or {}
    player = _player_at(raw, seat) or {}
    cards = Counter()
    seen = set()

    def add(card) -> None:
        if not isinstance(card, dict) or not isinstance(card.get("id"), int):
            return
        serial = card.get("serial")
        if serial is not None and serial in seen:
            return
        if serial is not None:
            seen.add(serial)
        cards[card["id"]] += 1

    for card in (player.get("hand") or []) + (player.get("discard") or []):
        add(card)
    for area in ("active", "bench"):
        for body in player.get(area) or []:
            add(body)
            if isinstance(body, dict):
                for nested in ("energyCards", "tools", "preEvolution"):
                    for card in body.get(nested) or []:
                        add(card)
    for card in current.get("stadium") or []:
        if isinstance(card, dict) and card.get("playerIndex") == seat:
            add(card)
    select = raw.get("select") or {}
    add(select.get("effect"))
    add(select.get("contextCard"))
    return cards


def _prize_anchors(film: list[dict], decks: list[list[int] | None]) -> list[list[tuple[int, Counter]]]:
    anchors: list[list[tuple[int, Counter]]] = [[] for _ in decks]
    for frame, raw in enumerate(film):
        current = raw.get("current") or {}
        seat = current.get("yourIndex")
        if not isinstance(seat, int) or seat >= len(decks) or decks[seat] is None:
            continue
        player = _player_at(raw, seat) or {}
        revealed = (raw.get("select") or {}).get("deck")
        if not isinstance(revealed, list) or not revealed or len(revealed) != player.get("deckCount"):
            continue
        prizes = Counter(decks[seat])
        prizes.subtract(card["id"] for card in revealed
                        if isinstance(card, dict) and isinstance(card.get("id"), int))
        prizes.subtract(_visible_cards(raw, seat))
        remaining = len(player.get("prize") or [])
        if sum(prizes.values()) == remaining and all(count >= 0 for count in prizes.values()):
            anchors[seat].append((frame, prizes))
    return anchors


def _repair_prizes(film: list[dict], decks: list[list[int] | None]) -> None:
    anchors = _prize_anchors(film, decks)
    for frame, raw in enumerate(film):
        players = ((raw.get("current") or {}).get("players") or [])
        for seat, player in enumerate(players):
            prize = player.get("prize")
            if not isinstance(prize, list):
                player["prize"] = []
                continue
            actual = [card for card in prize if isinstance(card, dict)]
            if len(actual) == len(prize):
                continue
            count = len(prize)
            same = [(at, cards) for at, cards in anchors[seat] if sum(cards.values()) == count]
            if same:
                known = min(same, key=lambda item: abs(item[0] - frame))[1]
            else:
                future = [(at, cards) for at, cards in anchors[seat]
                          if at >= frame and sum(cards.values()) < count]
                known = max(future, key=lambda item: sum(item[1].values()))[1] if future else Counter()
            cards = [{"id": card_id, "playerIndex": seat}
                     for card_id, copies in sorted(known.items()) for _ in range(copies)]
            player["prize"] = cards + [None] * (count - len(cards))


def _repair_transition_metadata(film: list[dict], decks: list[list[int] | None]) -> None:
    for frame, raw in enumerate(film):
        if not isinstance(raw.get("logs"), list):
            logs = (raw.get("obs") or {}).get("logs")
            raw["logs"] = logs if isinstance(logs, list) else []
        if not isinstance(raw.get("action"), list):
            if frame == 0:
                raw["action"] = [list(deck) if deck is not None else None for deck in decks[:2]]
                continue
            actor = ((film[frame - 1].get("current") or {}).get("yourIndex"))
            action = [None, None]
            if actor in (0, 1):
                action[actor] = raw.get("selected")
            raw["action"] = action


def viewer_replay_payload(replay: dict, *, decklists=None) -> dict:
    """Return a viewer-safe copy without changing the replay kept as Correction evidence."""
    payload = deepcopy(replay)
    film = _film(payload)
    decks = _viewer_decklists(payload, decklists)
    _repair_transition_metadata(film, decks)
    _repair_hands(film)
    _repair_prizes(film, decks)
    preload_cards: list[dict[int, dict]] = []
    for raw in film:
        raw["logs"] = raw.get("logs") if isinstance(raw.get("logs"), list) else []
        current = raw.get("current") or {}
        current["stadium"] = [_viewer_card(card) for card in (current.get("stadium") or [])
                              if isinstance(card, dict)]
        for seat, player in enumerate(current.get("players") or []):
            while len(preload_cards) <= seat:
                preload_cards.append({})
            for area in ("active", "bench", "discard", "deck"):
                player[area] = [_viewer_card(card) for card in (player.get(area) or [])
                                if isinstance(card, dict)]
            hand = player.get("hand")
            if not isinstance(hand, list):
                hand = [None] * int(player.get("handCount") or 0)
            player["hand"] = [_viewer_card(card) for card in hand]
            prize = player.get("prize")
            player["prize"] = ([_viewer_card(card) if isinstance(card, dict) else None
                                for card in prize]
                               if isinstance(prize, list) else [])
            for area in ("active", "bench", "hand", "discard", "prize", "deck"):
                for card in player[area]:
                    if isinstance(card, dict) and isinstance(card.get("id"), int):
                        preload_cards[seat].setdefault(card["id"], card)
        if preload_cards:
            for card in current["stadium"]:
                if isinstance(card.get("id"), int):
                    preload_cards[0].setdefault(card["id"], card)
    if film:
        for seat, player in enumerate((film[0].get("current") or {}).get("players") or []):
            present = {card.get("id") for card in player["deck"]}
            player["deck"].extend(card for card_id, card in preload_cards[seat].items()
                                  if card_id not in present)
    steps = payload.get("steps") or []
    if steps:
        while len(steps[0]) < 2:
            steps[0].append({})
        if len(steps) < len(film):
            steps.extend([[{}, {}] for _ in range(len(film) - len(steps))])
        elif len(steps) > len(film):
            del steps[len(film):]
    payload["viewerOpeningFrame"] = _opening_frame(film)
    return payload


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


def frames_index_payload(payload: dict) -> dict:
    """Return the initial page payload; per-Decision telemetry stays lazy."""
    indexed = []
    for frame in payload["frames"]:
        row = {key: value for key, value in frame.items() if key not in {"live", "ledger"}}
        row["has_details"] = frame.get("live") is not None or frame.get("ledger") is not None
        indexed.append(row)
    return {**payload, "frames": indexed}


def frame_details_payload(payload: dict, *, frame: int) -> dict:
    """Return the telemetry pane data for one film frame."""
    selected = next((item for item in payload["frames"] if item["frame"] == frame), None)
    if selected is None:
        raise ValueError(f"unknown frame {frame}")
    ledger = deepcopy(selected.get("ledger"))
    if ledger:
        for candidate in ledger.get("candidates") or []:
            candidate["gaps"] = list(dict.fromkeys(candidate.get("gaps") or []))
    return {"frame": frame, "live": selected.get("live"), "ledger": ledger}


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
