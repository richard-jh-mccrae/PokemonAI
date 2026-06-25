"""Build an agent's Manifest and render its Agent Brief (ADR-0019).

The Manifest is the decision-steering fingerprint: read *declaratively* from the agent's
Strategy + General Strategy and its shipped data files — never by running the agent.
"""
from __future__ import annotations

import html
import importlib.util
import inspect
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from submit.package import REPO, _git_hash, artifact_stem  # reuse the build-stamp helpers


def render_brief(manifest: dict) -> str:
    """Render the Manifest into a self-contained Agent Brief (HTML) that also embeds it.

    The machine-readable Manifest is inlined in a `<script type="application/json">` (with `<`
    escaped so it cannot break out), so the single file is both human- and machine-readable.
    """
    payload = json.dumps(manifest, ensure_ascii=False).replace("<", "\\u003c")
    p, caps = manifest["provenance"], manifest["capabilities"]
    badges = (f"Tier-{caps['tier']} · card_functions:{'✓' if caps['card_functions']['present'] else '✗'}"
              f" · posture:{'on' if caps['posture']['enabled'] else 'off'}"
              f" · overrides:{caps['overrides']['count']}")
    return (
        "<!doctype html>\n<html lang='en'><head><meta charset='utf-8'>\n"
        f"<title>Agent Brief — {html.escape(p['agent'])}</title>\n"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;max-width:60rem}"
        "code,pre{background:#f3f3f3;padding:.1rem .3rem;border-radius:3px}pre{white-space:pre-wrap}"
        "details{margin:.25rem 0}summary{cursor:pointer}h2{margin-top:1.5rem}</style></head>\n<body>\n"
        f"<h1>{html.escape(p['agent'])}</h1>\n"
        f"<p>built {p['built_at']} · commit <code>{html.escape(p['git_hash'])}</code> · {badges}</p>\n"
        f"<p>deck: {manifest['deck']['size']} cards</p>\n"
        f"<h2>Deck Strategy — {html.escape(manifest['strategy']['name'])}</h2>\n"
        f"{_hyp_details(manifest['strategy']['hypotheses'])}\n"
        "<h2>General Strategy</h2>\n"
        f"{_hyp_details(manifest['general_strategy']['hypotheses'])}\n"
        f'<script type="application/json" id="manifest">{payload}</script>\n'
        "</body></html>\n"
    )


def _hyp_details(hyps: list[dict]) -> str:
    """Each Hypothesis as an expandable `<details>` row carrying all of its info."""
    rows = []
    for h in hyps:
        tuned = " <em>(tuned)</em>" if h.get("overridden") else ""
        rows.append(
            f"<details><summary><b>{html.escape(h['id'])}</b> — w={h['effective']}{tuned}"
            f" · {html.escape(h['status'])}</summary>"
            f"<p>{html.escape(h.get('rationale', ''))}</p>"
            f"<pre>{html.escape(h.get('trigger', ''))}</pre>"
            f"<small>authored {h['authored']} → effective {h['effective']}</small></details>"
        )
    return "\n".join(rows)


def _load_strategy(agent_dir: Path):
    """Load the deck's declarative STRATEGY from `agent_dir/strategy.py` (no engine, no `.pyc`)."""
    spec = importlib.util.spec_from_file_location("_brief_strategy", Path(agent_dir) / "strategy.py")
    mod = importlib.util.module_from_spec(spec)
    prev = sys.dont_write_bytecode
    sys.dont_write_bytecode = True   # don't drop a __pycache__ into the staged bundle (it would ship)
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.dont_write_bytecode = prev
    return mod.STRATEGY


def _trigger_src(fn) -> str:
    """The `when` trigger's source (the lambda expression), best-effort."""
    try:
        src = inspect.getsource(fn).strip()
    except (OSError, TypeError):
        return ""
    i = src.find("lambda")
    return (src[i:] if i >= 0 else src).rstrip().rstrip(",")


def _hyp_row(h, tuned: dict) -> dict:
    """One Hypothesis as a manifest row — all of its decision-steering info."""
    effective = tuned.get(h.id, h.weight)
    return {
        "id": h.id,
        "rationale": h.rationale,
        "authored": h.weight,
        "effective": effective,
        "overridden": h.id in tuned and tuned[h.id] != h.weight,
        "status": h.status,
        "trigger": _trigger_src(h.when),
    }


def _deck(agent_dir: Path) -> dict:
    """The decklist as `{size, cards:[{id, count}]}` — duplicates collapsed."""
    path = agent_dir / "deck.csv"
    if not path.exists():
        return {"size": 0, "cards": []}
    ids = [int(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    counts = Counter(ids)
    return {"size": len(ids), "cards": [{"id": cid, "count": n} for cid, n in sorted(counts.items())]}


def build_manifest(agent_dir, *, general_strategy=None, when=None, git_hash=None,
                   agent_name=None) -> dict:
    """The agent's decision-steering Manifest (ADR-0019).

    `general_strategy` defaults to the shared `GENERAL_STRATEGY` shipped in `common/`;
    `when` / `git_hash` / `agent_name` default to now / `HEAD` / the dir name — pass them to
    stamp deterministically in tests.
    """
    agent_dir = Path(agent_dir)
    if general_strategy is None:
        from common.general_strategy import GENERAL_STRATEGY
        general_strategy = GENERAL_STRATEGY
    when = when or datetime.now()
    git_hash = _git_hash(REPO) if git_hash is None else git_hash
    agent_name = agent_name or agent_dir.name
    strategy = _load_strategy(agent_dir)
    tuned_path = agent_dir / "tuned.json"
    tuned = json.loads(tuned_path.read_text(encoding="utf-8")) if tuned_path.exists() else {}
    meta_path = agent_dir / "tuned.meta.json"          # provenance sidecar (ADR-0019)
    training = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    search_budget = strategy.params.get("search_budget", 0)
    return {
        "schema_version": 1,
        "provenance": {
            "agent": agent_name,
            "built_at": when.isoformat(timespec="seconds"),
            "git_hash": git_hash,
            "artifact": artifact_stem(agent_name, when=when, git_hash=git_hash),
        },
        "deck": _deck(agent_dir),
        "training": training,
        "capabilities": {
            "search_budget": search_budget,
            "tier": 1 if search_budget > 0 else 0,    # >0 => Tier-1 Search; else Tier-0 closed-form
            "card_functions": {"present": (agent_dir / "common" / "card_functions.json").exists()},
            "posture": {"enabled": (agent_dir / "common" / "scouting" / "artifact.json").exists()},
            "overrides": {"present": bool(tuned), "count": len(tuned)},
        },
        "strategy": {
            "name": strategy.name,
            "hypotheses": [_hyp_row(h, tuned) for h in strategy.hypotheses],
        },
        "general_strategy": {
            "hypotheses": [_hyp_row(h, tuned) for h in general_strategy.hypotheses],
        },
    }
