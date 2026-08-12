"""Dashboard: the over-time view joining Agent History and the Performance Log (ADR-0019).

Self-contained HTML: one row per Submission, its declared state beside its collected
performance (score, record, per-Archetype matchup dropdown) — the growth-and-development
picture and the Strategy-Writeup evidence.
"""
from __future__ import annotations

import html
import json
from pathlib import Path

from submit.build import DEFAULT_HISTORY
from submit.collect import DEFAULT_PERF
from submit.history import read_history


def _latest_by_submission(performance: list[dict]) -> dict:
    """The newest Performance sample per submission_id (score drifts; keep the latest)."""
    latest: dict[int, dict] = {}
    for s in performance:
        sid = s["submission_id"]
        if sid not in latest or s.get("sampled_at", "") > latest[sid].get("sampled_at", ""):
            latest[sid] = s
    return latest


def _matchups(sample: dict) -> str:
    items = "".join(
        f"<li>{html.escape(m['archetype'])}: {m['wins']}-{m['losses']}</li>"
        for m in sample.get("matchups", []))
    return f"<details><summary>matchups</summary><ul>{items}</ul></details>" if items else ""


def render_dashboard(history: list[dict], performance: list[dict]) -> str:
    """Render the over-time dashboard (no external dependencies)."""
    latest = _latest_by_submission(performance)
    rows = []
    for h in sorted(history, key=lambda r: r["submission_id"]):
        s, p = h["summary"], latest.get(h["submission_id"], {})
        rec = p.get("record", {})
        record = f"{rec['wins']}-{rec['losses']}" if rec else "—"
        rows.append(
            f"<tr><td>{h['submission_id']}</td><td>{html.escape(str(h.get('label') or ''))}</td>"
            f"<td>{html.escape(str(h.get('built_at', ''))[:10])}</td>"
            f"<td><code>{html.escape(str(h.get('git_hash', '')))}</code></td>"
            f"<td>{html.escape(s.get('system', 'legacy'))}</td><td>{s.get('roles', '—')}</td>"
            f"<td>{p.get('public_score', '—')}</td><td>{record}</td><td>{_matchups(p)}</td></tr>")
    head = ("<tr><th>#</th><th>label</th><th>built</th><th>commit</th><th>system</th>"
            "<th>roles</th><th>score</th><th>W-L</th><th>matchups</th></tr>")
    return (
        "<!doctype html>\n<html lang='en'><head><meta charset='utf-8'>\n"
        "<title>Agent Dashboard</title>\n"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem}table{border-collapse:collapse}"
        "td,th{border:1px solid #ddd;padding:.3rem .6rem;text-align:left}"
        "summary{cursor:pointer}code{background:#f3f3f3;padding:0 .2rem}</style></head>\n<body>\n"
        "<h1>Agent Dashboard</h1>\n"
        f"<table>\n{head}\n" + "\n".join(rows) + "\n</table>\n</body></html>\n"
    )


def build_dashboard(*, history=DEFAULT_HISTORY, performance=DEFAULT_PERF, out: Path | str) -> Path:
    """Read the two committed logs and write the dashboard HTML to `out`."""
    perf = [json.loads(ln) for ln in Path(performance).read_text(encoding="utf-8").splitlines()
            if ln.strip()] if Path(performance).exists() else []
    out = Path(out)
    out.write_text(render_dashboard(read_history(history), perf), encoding="utf-8")
    return out
