"""Aggregate Corrections into trend summaries and a self-contained HTML report.

The "my agents over time" view is the ``own`` pile, bucketed by Category and grouped
by the submission timeline (see ``tools/train/CONTEXT.md`` Source/Category). ``peer``
Corrections are counted separately (expertise injection, not our agent's blunders).
"""
from __future__ import annotations

import html as _html
import json
from collections import Counter
from pathlib import Path
from typing import Iterable

from .correction import Correction, is_critical
from .reviewed import load_reviewed, review_key
from .store import load_corrections


def _bucket(items: list[Correction]) -> dict:
    return {"total": len(items), "by_category": dict(Counter(c.category for c in items))}


def _group(items, keyfn, extra=None) -> dict:
    """Group corrections by ``keyfn(c)`` into {key: {total, by_category, **extra(c)}}."""
    out: dict = {}
    for c in items:
        key = keyfn(c)
        slot = out.get(key)
        if slot is None:
            slot = {"total": 0, "by_category": {}}
            if extra:
                slot.update(extra(c))
            out[key] = slot
        slot["total"] += 1
        slot["by_category"][c.category] = slot["by_category"].get(c.category, 0) + 1
    return out


def summarize(corrections: Iterable[Correction]) -> dict:
    """Counts for the trend report: own (by category, by submission) and peer (by category)."""
    corrections = list(corrections)
    own = [c for c in corrections if c.source == "own"]
    peer = [c for c in corrections if c.source == "peer"]

    result = {"own": _bucket(own), "peer": _bucket(peer)}
    result["own"]["by_submission"] = _group(own, lambda c: c.submission_id)
    result["own"]["by_build"] = _group(own, lambda c: c.agent_build,
                                       extra=lambda c: {"built_at": c.built_at})
    return result


def avg_blunders_per_game(corrections) -> dict:
    """Per agent build: own blunder count, the distinct tagged games, and their ratio.

    A "game" here is a **distinct tagged episode** — the games that surfaced ≥1 blunder. A reviewed
    game with no blunder leaves no row in the log, so this is blunders per *blundered* game (an upper
    bound on the true per-game-played rate), computed entirely from the Correction log. Returns
    ``{agent_build: {"blunders", "games", "avg", "built_at"}}``."""
    out: dict = {}
    for c in corrections:
        if c.source != "own":
            continue
        slot = out.setdefault(c.agent_build, {"blunders": 0, "episodes": set(), "built_at": c.built_at})
        slot["blunders"] += 1
        slot["episodes"].add(c.episode_id)
    for slot in out.values():
        slot["games"] = len(slot["episodes"])
        slot["avg"] = slot["blunders"] / slot["games"] if slot["games"] else 0.0
    return out


# --- Resolution view: tag each blunder with its /blunder-buster terminal outcome ----------------
# `fixed` implicit — auto-reconciliation (ADR-0018) dropped it from `open[]` since a committed
# rule now satisfies it; `covered`/`refuted`/`deferred` come from reviewed ledger; `open` still
# needs a rule; `skipped` = tactical / no-obs pile the tuner can't route.
_RESOLVED = ("fixed", "covered", "refuted", "deferred")
_DISP_ORDER = ("fixed", "covered", "refuted", "deferred", "open", "skipped")


def _load_proposals(proposals_dir) -> tuple[set, set, set]:
    """Scan ``data/corrections/tuner/*.json`` → (open_keys, skipped_keys, decks_with_proposals), keyed
    ``"<episode_id>-<frame>"`` like the ledger. Best-effort: a missing/unreadable dir yields empty
    sets (every blunder then falls back to ``open`` — never wrongly claimed ``fixed``)."""
    open_keys, skipped_keys, decks = set(), set(), set()
    p = Path(proposals_dir)
    if not p.exists():
        return open_keys, skipped_keys, decks
    for f in sorted(p.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        decks.add(data.get("deck") or f.stem)
        open_keys.update(f"{e.get('episode_id')}-{e.get('frame')}" for e in data.get("open", []))
        skipped_keys.update(f"{e.get('episode_id')}-{e.get('frame')}" for e in data.get("skipped", []))
    return open_keys, skipped_keys, decks


def _disposition(c, reviewed: dict, open_keys: set, skipped_keys: set, decks: set) -> str:
    """One Correction's terminal outcome (the /blunder-buster vocabulary): ledger disposition
    (covered/refuted/deferred) > still-``open`` > ``skipped`` > ``fixed`` (its deck was tuned and the
    blunder is no longer open, so a rule satisfies it). A deck with no proposals snapshot stays
    ``open`` — we never claim ``fixed`` without the evidence that reconciliation dropped it."""
    key = review_key(c)
    entry = reviewed.get(key)
    if entry:
        return entry.get("disposition", "covered")
    if key in open_keys:
        return "open"
    if key in skipped_keys:
        return "skipped"
    if c.agent in decks:
        return "fixed"
    return "open"


_STYLE = (
    "body{font:14px system-ui,sans-serif;margin:24px;color:#1a1a1a}"
    "h1{font-size:20px}h2{font-size:16px;margin-top:24px;border-bottom:1px solid #ddd}"
    "table{border-collapse:collapse;margin:8px 0}td,th{padding:2px 10px;text-align:left}"
    ".bar{display:inline-block;height:12px;background:#3b6db3;vertical-align:middle}"
    ".muted{color:#777}details{margin:3px 0}summary{cursor:pointer}"
    "code{background:#f2f2f2;padding:1px 4px;border-radius:3px}"
    ".pill{display:inline-block;font-size:11px;font-weight:600;padding:0 6px;border-radius:8px;"
    "color:#fff;margin-right:6px}"
    ".fixed{background:#2e7d32}.covered{background:#3b6db3}.refuted{background:#8a8a8a}"
    ".deferred{background:#b3873b}.open{background:#c0392b}.skipped{background:#cccccc;color:#333}"
    ".critical{background:#d32f2f;outline:2px solid #000}"   # must-fix-first; orthogonal to disposition
)


def _esc(value) -> str:
    return _html.escape(str(value))


def _category_table(by_category: dict) -> str:
    if not by_category:
        return "<p class='muted'>none</p>"
    top = max(by_category.values())
    rows = []
    for category, count in sorted(by_category.items(), key=lambda kv: -kv[1]):
        width = int(220 * count / top) if top else 0
        rows.append(
            f"<tr><td>{_esc(category)}</td><td>{count}</td>"
            f"<td><div class='bar' style='width:{width}px'></div></td></tr>"
        )
    return "<table>" + "".join(rows) + "</table>"


def _per_game_table(stats: dict) -> str:
    """Avg blunders-per-game by build, chronological — the over-time blunder-density trend."""
    if not stats:
        return "<p class='muted'>none</p>"
    rows_data = sorted(  # chronological: built_at, then build id
        ((slot.get("built_at") or "", build, slot["games"], slot["blunders"], slot["avg"])
         for build, slot in stats.items()),
        key=lambda r: (r[0], str(r[1])),
    )
    top = max((avg for *_, avg in rows_data), default=0) or 1
    rows = ["<tr><th>built</th><th>build</th><th>games</th><th>blunders</th>"
            "<th>avg/game</th><th></th></tr>"]
    for built, build, games, blunders, avg in rows_data:
        width = int(220 * avg / top)
        rows.append(
            f"<tr><td>{_esc(built or '?')}</td><td>{_esc(build)}</td><td>{games}</td>"
            f"<td>{blunders}</td><td><b>{avg:.1f}</b></td>"
            f"<td><div class='bar' style='width:{width}px'></div></td></tr>"
        )
    return "<table>" + "".join(rows) + "</table>"


def _resolution_table(counts: dict) -> str:
    """Disposition pills with counts + bars, in a stable fixed→open→skipped order."""
    present = [(d, counts[d]) for d in _DISP_ORDER if counts.get(d)]
    if not present:
        return "<p class='muted'>none</p>"
    top = max(n for _, n in present)
    rows = []
    for disp, count in present:
        width = int(220 * count / top) if top else 0
        rows.append(
            f"<tr><td><span class='pill {disp}'>{disp}</span></td><td>{count}</td>"
            f"<td><div class='bar' style='width:{width}px'></div></td></tr>"
        )
    return "<table>" + "".join(rows) + "</table>"


def build_report(corrections_path: Path | str, out_path: Path | str, *,
                 reviewed_path: Path | str | None = None,
                 proposals_dir: Path | str | None = None) -> Path:
    """Render a self-contained, offline HTML trend report (no external resources).

    When ``reviewed_path`` (the reviewed ledger) and/or ``proposals_dir`` (``data/corrections/tuner``) are
    supplied, each own blunder is also tagged with its terminal outcome — fixed / covered / refuted /
    deferred / open / skipped — the header splits resolved vs open, and a *by resolution* section is
    added. Omit both for the plain tag-trend view (unchanged legacy output)."""
    out_path = Path(out_path)
    corrections = load_corrections(corrections_path)
    if not corrections:
        out_path.write_text(
            "<!doctype html><html><head><meta charset='utf-8'><title>Blunder trends</title>"
            "</head><body><h1>Blunder trends</h1><p>No corrections logged yet.</p></body></html>",
            encoding="utf-8",
        )
        return out_path

    enrich = reviewed_path is not None or proposals_dir is not None
    reviewed = load_reviewed(reviewed_path) if reviewed_path is not None else {}
    open_keys, skipped_keys, decks = (
        _load_proposals(proposals_dir) if proposals_dir is not None else (set(), set(), set()))
    disp = ({id(c): _disposition(c, reviewed, open_keys, skipped_keys, decks)
             for c in corrections if c.source == "own"} if enrich else {})

    summary = summarize(corrections)
    own, peer = summary["own"], summary["peer"]

    head_counts = ""
    if enrich:
        counts = Counter(disp.values())
        resolved_n = sum(counts.get(d, 0) for d in _RESOLVED)
        head_counts = f" ({resolved_n} resolved &middot; {counts.get('open', 0)} open"
        head_counts += f" &middot; {counts['skipped']} skipped)" if counts.get("skipped") else ")"

    n_critical = sum(1 for c in corrections if c.source == "own" and is_critical(c.rationale))
    crit_note = (f" &middot; <span class='pill critical'>&#9888; {n_critical} CRITICAL</span>"
                 if n_critical else "")
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'><title>Blunder trends</title>",
        f"<style>{_STYLE}</style></head><body>",
        "<h1>Blunder trends</h1>",
        f"<p>{own['total']} own-agent blunders{head_counts}{crit_note} "
        f"&middot; {peer['total']} peer blunders</p>",
    ]
    if enrich:
        parts.append("<h2>My agents &mdash; by resolution</h2>")
        parts.append(_resolution_table(counts))
    parts.append("<h2>My agents &mdash; avg blunders per game (by build, over time)</h2>")
    parts.append("<p class='muted'>avg = own blunders &divide; distinct tagged games "
                 "(games that surfaced &ge;1 blunder)</p>")
    parts.append(_per_game_table(avg_blunders_per_game(corrections)))
    parts += [
        "<h2>My agents &mdash; by category</h2>",
        _category_table(own["by_category"]),
        "<h2>My agents &mdash; by submission (timeline)</h2>",
    ]

    subs = own.get("by_submission", {})
    if subs:
        rows = ["<tr><th>submission</th><th>total</th><th>categories</th></tr>"]
        for sid in sorted(subs, key=lambda k: (k is None, k)):
            slot = subs[sid]
            cats = ", ".join(f"{_esc(c)}&times;{n}" for c, n in sorted(slot["by_category"].items()))
            rows.append(f"<tr><td>{_esc(sid)}</td><td>{slot['total']}</td><td>{cats}</td></tr>")
        parts.append("<table>" + "".join(rows) + "</table>")
    else:
        parts.append("<p class='muted'>none</p>")

    parts.append("<h2>My agents &mdash; by build (over time)</h2>")
    builds = own.get("by_build", {})
    if builds:
        rows = ["<tr><th>built</th><th>build</th><th>total</th><th>categories</th></tr>"]
        for b in sorted(builds, key=lambda k: (builds[k].get("built_at") or "", str(k))):
            slot = builds[b]
            cats = ", ".join(f"{_esc(c)}&times;{n}" for c, n in sorted(slot["by_category"].items()))
            rows.append(f"<tr><td>{_esc(slot.get('built_at') or '?')}</td><td>{_esc(b)}</td>"
                        f"<td>{slot['total']}</td><td>{cats}</td></tr>")
        parts.append("<table>" + "".join(rows) + "</table>")
    else:
        parts.append("<p class='muted'>none</p>")

    parts.append("<h2>My agents &mdash; details</h2>")
    for c in corrections:
        if c.source != "own":
            continue
        chosen = _esc(c.chosen_label or c.chosen)
        correct = _esc(c.correct_label or c.correct)
        badge = f"<span class='pill {disp[id(c)]}'>{disp[id(c)]}</span>" if enrich else ""
        crit = "<span class='pill critical'>&#9888; CRITICAL</span>" if is_critical(c.rationale) else ""
        head = (
            f"{crit}{badge}{_esc(c.category)} &middot; ep {_esc(c.episode_id)} &middot; "
            f"turn {_esc(c.decision.get('turn'))} &middot; <code>{chosen}</code> &rarr; <code>{correct}</code>"
        )
        parts.append(f"<details><summary>{head}</summary><p>{_esc(c.rationale)}</p></details>")

    parts.append("<h2>Peer (expertise injection)</h2>")
    parts.append(_category_table(peer["by_category"]))
    parts.append("</body></html>")

    out_path.write_text("".join(parts), encoding="utf-8")
    return out_path

