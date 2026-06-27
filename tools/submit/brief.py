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


def render_brief(manifest: dict, *, prev_deck: dict | None = None,
                 prev_build_id: int | None = None, prev_hyps: dict | None = None) -> str:
    """Render the Manifest into a self-contained Agent Brief (HTML) that also embeds it.

    The machine-readable Manifest is inlined in a `<script type="application/json">` (with `<`
    escaped so it cannot break out), so the single file is both human- and machine-readable.
    `prev_deck` (the previous build's deck) drives a highlighted **deck-change** callout, and
    `prev_hyps` (`{"strategy": [...], "general": [...]}` — the previous build's Hypothesis rows) a
    **strategy-change** callout (weights/rules/status changed since build `prev_build_id`). Omit
    both for the first build.
    """
    payload = json.dumps(manifest, ensure_ascii=False).replace("<", "\\u003c")
    p, caps = manifest["provenance"], manifest["capabilities"]
    flags = (f"Tier-{caps['tier']} · card_functions:{'✓' if caps['card_functions']['present'] else '✗'}"
             f" · posture:{'on' if caps['posture']['enabled'] else 'off'}"
             f" · overrides:{caps['overrides']['count']}")
    added, removed, changed, badges = _deck_diff(prev_deck, manifest["deck"])
    w_chg, h_add, h_rem, st_chg, hyp_marks = _hyp_diff(
        prev_hyps, manifest["strategy"]["hypotheses"], manifest["general_strategy"]["hypotheses"])
    return (
        "<!doctype html>\n<html lang='en'><head><meta charset='utf-8'>\n"
        f"<title>Agent Brief — {html.escape(p['agent'])}</title>\n"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;max-width:60rem}"
        "code,pre{background:#f3f3f3;padding:.1rem .3rem;border-radius:3px}pre{white-space:pre-wrap}"
        "details{margin:.25rem 0}summary{cursor:pointer}h2{margin-top:1.5rem}"
        ".deckdiff{background:#fff8e1;border-left:4px solid #f5a623;padding:.4rem .8rem;"
        "margin:.5rem 0;border-radius:4px}.deckdiff li.add{color:#1a7f37}.deckdiff li.rem{color:#b42318}"
        ".deckdiff li.chg{color:#9a6700}li.changed{background:#fff8e1;border-radius:3px;padding:0 .2rem}"
        ".tag{font-weight:600;color:#9a6700}</style></head>\n<body>\n"
        f"<h1>{html.escape(p['agent'])}</h1>\n"
        f"<p>built {p['built_at']} · commit <code>{html.escape(p['git_hash'])}</code> · {flags}</p>\n"
        f"<h2>Deck — {manifest['deck']['size']} cards</h2>\n"
        f"{_deck_diff_html(prev_build_id, added, removed, changed)}\n"
        f"{_deck_html(manifest['deck'], badges)}\n"
        f"<h2>Deck Strategy — {html.escape(manifest['strategy']['name'])}</h2>\n"
        f"{_hyp_diff_html(prev_build_id, w_chg, h_add, h_rem, st_chg)}\n"
        f"{_hyp_details(manifest['strategy']['hypotheses'], hyp_marks)}\n"
        "<h2>General Strategy</h2>\n"
        f"{_hyp_details(manifest['general_strategy']['hypotheses'], hyp_marks)}\n"
        f'<script type="application/json" id="manifest">{payload}</script>\n'
        "</body></html>\n"
    )


def _hyp_details(hyps: list[dict], marks: dict | None = None) -> str:
    """Each Hypothesis as an expandable `<details>` row carrying all of its info.

    `marks` (id -> badge, e.g. `30→2` or `new`) highlights rows that changed since the last build."""
    marks = marks or {}
    rows = []
    for h in hyps:
        tuned = " <em>(tuned)</em>" if h.get("overridden") else ""
        mark = marks.get(h["id"])
        chg = f" <span class='tag'>{html.escape(mark)}</span>" if mark else ""
        cls = " class='changed'" if mark else ""
        rows.append(
            f"<details{cls}><summary><b>{html.escape(h['id'])}</b> — w={h['effective']}{tuned}"
            f" · {html.escape(h['status'])}{chg}</summary>"
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


def _card_index() -> dict:
    """`{card_id: metadata}` from the local card cache — best-effort (empty if unavailable)."""
    try:
        from meta_tracker.cards import load_cards
        return load_cards()
    except Exception:
        return {}      # no card db at build time -> brief falls back to the bare count


def _deck(agent_dir: Path, cards: dict | None = None) -> dict:
    """The decklist as `{size, cards:[{id, count, name, category}]}` — duplicates collapsed,
    each id resolved to its name + category from the card cache so the Brief can show real cards."""
    path = agent_dir / "deck.csv"
    if not path.exists():
        return {"size": 0, "cards": []}
    ids = [int(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    cards = _card_index() if cards is None else cards
    rows = []
    for cid, n in sorted(Counter(ids).items()):
        meta = cards.get(cid, {})
        rows.append({"id": cid, "count": n, "name": meta.get("name"), "category": meta.get("category")})
    return {"size": len(ids), "cards": rows}


def _card_label(card: dict) -> str:
    """A card's name, falling back to `#<id>` when the cache couldn't resolve it."""
    return card.get("name") or f"#{card['id']}"


# Standard decklist sections: (heading, the card categories it gathers).
_DECK_SECTIONS = [
    ("Pokémon", {"pokemon"}),
    ("Trainer", {"item", "tool", "supporter", "stadium"}),
    ("Energy", {"basic_energy", "special_energy"}),
]


def _deck_html(deck: dict, badges: dict | None = None) -> str:
    """The decklist grouped into Pokémon / Trainer / Energy, counts first — like a real list.

    `badges` maps a card id to a change marker (`new` / `+1` / `-2`); marked rows are highlighted.
    Returns "" when no names resolved (no card db at build time); the size line still shows."""
    cards = deck.get("cards", [])
    if not any(c.get("name") for c in cards):
        return ""
    badges = badges or {}
    known = {cat for _, cats in _DECK_SECTIONS for cat in cats}
    blocks = []
    for title, cats in [*_DECK_SECTIONS, ("Other", None)]:
        section = [c for c in cards if (c.get("category") in cats if cats else c.get("category") not in known)]
        if not section:
            continue
        section.sort(key=lambda c: (-c["count"], (c.get("name") or "").lower()))
        n = sum(c["count"] for c in section)
        items = "".join(_deck_li(c, badges.get(c["id"])) for c in section)
        blocks.append(f"<details open><summary><b>{html.escape(title)}</b> ({n})</summary>"
                      f"<ul>{items}</ul></details>")
    return "\n".join(blocks)


def _deck_li(card: dict, badge: str | None) -> str:
    """One decklist row, highlighted with its change badge when the card changed since last build."""
    mark = f" <span class='tag'>{html.escape(badge)}</span>" if badge else ""
    cls = " class='changed'" if badge else ""
    return f"<li{cls}>{card['count']}× {html.escape(_card_label(card))}{mark}</li>"


def _deck_diff(prev_deck: dict | None, cur_deck: dict) -> tuple[list, list, list, dict]:
    """The deck delta vs a baseline -> (added, removed, changed, badges).

    `added`/`removed` are whole cards; `changed` carries `from`/`to` counts; `badges` maps a
    *current* card id to its inline marker. Empty across the board when nothing changed (or no
    baseline) — the brief then shows no callout."""
    if not (prev_deck or {}).get("cards"):
        return [], [], [], {}      # no previous build to diff against (e.g. the first build)
    prev = {c["id"]: c for c in prev_deck["cards"]}
    cur = {c["id"]: c for c in cur_deck.get("cards", [])}
    added, changed, badges = [], [], {}
    for cid, c in cur.items():
        if cid not in prev:
            added.append(c)
            badges[cid] = "new"
        elif c["count"] != prev[cid]["count"]:
            changed.append({**c, "from": prev[cid]["count"], "to": c["count"]})
            badges[cid] = f"{c['count'] - prev[cid]['count']:+d}"
    removed = [c for cid, c in prev.items() if cid not in cur]
    return added, removed, changed, badges


def _deck_diff_html(prev_build_id, added: list, removed: list, changed: list) -> str:
    """A highlighted callout of every deck change since the previous build (empty when none)."""
    if not (added or removed or changed):
        return ""
    rows = [f"<li class='add'>+{c['count']}× {html.escape(_card_label(c))} <em>(new)</em></li>"
            for c in added]
    rows += [f"<li class='chg'>{html.escape(_card_label(c))}: {c['from']} → {c['to']}</li>"
             for c in changed]
    rows += [f"<li class='rem'>−{c['count']}× {html.escape(_card_label(c))} <em>(removed)</em></li>"
             for c in removed]
    since = f" since build #{prev_build_id}" if prev_build_id is not None else ""
    return f"<div class='deckdiff'><b>⚠ Deck changed{since}</b><ul>{''.join(rows)}</ul></div>"


def _hyp_diff(prev_hyps: dict | None, cur_strategy: list, cur_general: list):
    """The Hypothesis delta vs a baseline -> (weights, added, removed, status, marks).

    Compares **effective** weight (authored merged with `tuned.json`) and `status` across both the
    deck and general Strategies. `marks` maps a *current* Hypothesis id to its inline badge. All
    empty when there's no prior hypothesis baseline (the first build after this field exists)."""
    prev = {h["id"]: h for h in ((prev_hyps or {}).get("strategy", []) + (prev_hyps or {}).get("general", []))}
    if not prev:
        return [], [], [], [], {}
    cur = {h["id"]: h for h in (cur_strategy + cur_general)}
    weights, status, added, marks = [], [], [], {}
    for hid, h in cur.items():
        if hid not in prev:
            added.append(h)
            marks[hid] = "new rule"
            continue
        old = prev[hid]
        wc = h["effective"] != old.get("effective")
        sc = h.get("status") != old.get("status")
        if wc:
            weights.append({"id": hid, "from": old.get("effective"), "to": h["effective"]})
        if sc:
            status.append({"id": hid, "from": old.get("status"), "to": h.get("status")})
        if wc and sc:
            marks[hid] = f"w {old.get('effective')}→{h['effective']}, {old.get('status')}→{h.get('status')}"
        elif wc:
            marks[hid] = f"w {old.get('effective')}→{h['effective']}"
        elif sc:
            marks[hid] = f"{old.get('status')}→{h.get('status')}"
    removed = [h for hid, h in prev.items() if hid not in cur]
    return weights, added, removed, status, marks


def _hyp_diff_html(prev_build_id, weights: list, added: list, removed: list, status: list) -> str:
    """A highlighted callout of every Strategy change (weights / rules / status) since the previous
    build — so you can see at a glance what tuning changed between iterations (empty when none)."""
    if not (weights or added or removed or status):
        return ""
    rows = [f"<li class='add'>+ <code>{html.escape(h['id'])}</code> "
            f"<em>(new rule, w={h['effective']})</em></li>" for h in added]
    rows += [f"<li class='chg'><code>{html.escape(w['id'])}</code>: weight {w['from']} → {w['to']}</li>"
             for w in weights]
    rows += [f"<li class='chg'><code>{html.escape(s['id'])}</code>: status {html.escape(str(s['from']))} "
             f"→ {html.escape(str(s['to']))}</li>" for s in status]
    rows += [f"<li class='rem'>− <code>{html.escape(h['id'])}</code> <em>(removed)</em></li>"
             for h in removed]
    since = f" since build #{prev_build_id}" if prev_build_id is not None else ""
    return f"<div class='deckdiff'><b>⚠ Strategy changed{since}</b><ul>{''.join(rows)}</ul></div>"


def build_manifest(agent_dir, *, general_strategy=None, when=None, git_hash=None,
                   agent_name=None, cards=None) -> dict:
    """The agent's decision-steering Manifest (ADR-0019).

    `general_strategy` defaults to the shared `GENERAL_STRATEGY` shipped in `common/`;
    `when` / `git_hash` / `agent_name` default to now / `HEAD` / the dir name — pass them to
    stamp deterministically in tests. `cards` (the card cache) defaults to the local `cards.json`
    and resolves the decklist's names; inject it in tests.
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
        "deck": _deck(agent_dir, cards),
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
