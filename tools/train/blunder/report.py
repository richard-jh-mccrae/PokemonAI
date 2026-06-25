"""Aggregate Corrections into trend summaries and a self-contained HTML report.

The "my agents over time" view is the ``own`` pile, bucketed by Category and grouped
by the submission timeline (see ``tools/train/CONTEXT.md`` Source/Category). ``peer``
Corrections are counted separately (expertise injection, not our agent's blunders).
"""
from __future__ import annotations

import html as _html
from collections import Counter
from pathlib import Path
from typing import Iterable

from .correction import Correction
from .store import load_corrections


def _bucket(items: list[Correction]) -> dict:
    return {"total": len(items), "by_category": dict(Counter(c.category for c in items))}


def summarize(corrections: Iterable[Correction]) -> dict:
    """Counts for the trend report: own (by category, by submission) and peer (by category)."""
    corrections = list(corrections)
    own = [c for c in corrections if c.source == "own"]
    peer = [c for c in corrections if c.source == "peer"]

    by_submission: dict = {}
    for c in own:
        slot = by_submission.setdefault(c.submission_id, {"total": 0, "by_category": {}})
        slot["total"] += 1
        slot["by_category"][c.category] = slot["by_category"].get(c.category, 0) + 1

    result = {"own": _bucket(own), "peer": _bucket(peer)}
    result["own"]["by_submission"] = by_submission
    return result


_STYLE = (
    "body{font:14px system-ui,sans-serif;margin:24px;color:#1a1a1a}"
    "h1{font-size:20px}h2{font-size:16px;margin-top:24px;border-bottom:1px solid #ddd}"
    "table{border-collapse:collapse;margin:8px 0}td,th{padding:2px 10px;text-align:left}"
    ".bar{display:inline-block;height:12px;background:#3b6db3;vertical-align:middle}"
    ".muted{color:#777}details{margin:3px 0}summary{cursor:pointer}"
    "code{background:#f2f2f2;padding:1px 4px;border-radius:3px}"
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


def build_report(corrections_path: Path | str, out_path: Path | str) -> Path:
    """Render a self-contained, offline HTML trend report (no external resources)."""
    out_path = Path(out_path)
    corrections = load_corrections(corrections_path)
    if not corrections:
        out_path.write_text(
            "<!doctype html><html><head><meta charset='utf-8'><title>Blunder trends</title>"
            "</head><body><h1>Blunder trends</h1><p>No corrections logged yet.</p></body></html>",
            encoding="utf-8",
        )
        return out_path

    summary = summarize(corrections)
    own, peer = summary["own"], summary["peer"]
    parts = [
        "<!doctype html><html><head><meta charset='utf-8'><title>Blunder trends</title>",
        f"<style>{_STYLE}</style></head><body>",
        "<h1>Blunder trends</h1>",
        f"<p>{own['total']} own-agent blunders &middot; {peer['total']} peer blunders</p>",
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

    parts.append("<h2>My agents &mdash; details</h2>")
    for c in corrections:
        if c.source != "own":
            continue
        chosen = _esc(c.chosen_label or c.chosen)
        correct = _esc(c.correct_label or c.correct)
        head = (
            f"{_esc(c.category)} &middot; ep {_esc(c.episode_id)} &middot; "
            f"turn {_esc(c.decision.get('turn'))} &middot; <code>{chosen}</code> &rarr; <code>{correct}</code>"
        )
        parts.append(f"<details><summary>{head}</summary><p>{_esc(c.rationale)}</p></details>")

    parts.append("<h2>Peer (expertise injection)</h2>")
    parts.append(_category_table(peer["by_category"]))
    parts.append("</body></html>")

    out_path.write_text("".join(parts), encoding="utf-8")
    return out_path

