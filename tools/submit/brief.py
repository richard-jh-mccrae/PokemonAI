"""Build the Bellman agent manifest and its human-readable brief."""
from __future__ import annotations

import csv
import html
import importlib.util
import io
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from submit.package import REPO, _git_hash, artifact_stem


def _load_strategy(agent_dir: Path):
    spec = importlib.util.spec_from_file_location("_brief_strategy", agent_dir / "strategy.py")
    module = importlib.util.module_from_spec(spec)
    previous = sys.dont_write_bytecode
    sys.dont_write_bytecode = True
    try:
        spec.loader.exec_module(module)
    finally:
        sys.dont_write_bytecode = previous
    return module.STRATEGY


def _card_index() -> dict:
    try:
        from meta_tracker.cards import load_cards
        return load_cards()
    except Exception:
        return {}


def _deck(agent_dir: Path, cards: dict | None = None) -> dict:
    path = agent_dir / "deck.csv"
    ids = [int(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    cards = _card_index() if cards is None else cards
    rows = []
    for card_id, count in sorted(Counter(ids).items()):
        card = cards.get(card_id, {})
        rows.append({"id": card_id, "count": count, "name": card.get("name"),
                     "category": card.get("category")})
    return {"size": len(ids), "cards": rows}


def _shared_partners(agent_dir: Path, card_ids) -> dict[int, tuple[int, ...]]:
    """Read printed partner tags from the staged bundle, or source when briefing in place."""
    source = agent_dir / "common" / "card_functions.json"
    if not source.exists():
        source = REPO / "src" / "common" / "card_functions.json"
    try:
        tags = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    deck = {int(card_id) for card_id in card_ids}
    partners: dict[int, tuple[int, ...]] = {}
    for card_id in sorted(deck):
        values = set()
        for tag in tags.get(str(card_id), ()):
            if not isinstance(tag, str) or not tag.startswith("partner:"):
                continue
            try:
                partner = int(tag.removeprefix("partner:"))
            except ValueError:
                continue
            if partner in deck and partner != card_id:
                values.add(partner)
        if values:
            partners[card_id] = tuple(sorted(values))
    return partners


def _shared_roles(agent_dir: Path, card_ids) -> dict[int, tuple[str, ...]]:
    source = agent_dir / "common" / "card_functions.json"
    if not source.exists():
        source = REPO / "src" / "common" / "card_functions.json"
    try:
        tags = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {
        int(card_id): tuple(tag.removeprefix("role:") for tag in tags.get(str(card_id), ())
                            if isinstance(tag, str) and tag.startswith("role:")
                            and tag.removeprefix("role:"))
        for card_id in card_ids
        if any(isinstance(tag, str) and tag.startswith("role:") and tag.removeprefix("role:")
               for tag in tags.get(str(card_id), ()))
    }


def _shared_lines(agent_dir: Path, card_ids) -> tuple[tuple[int, ...], ...]:
    source = agent_dir / "common" / "card_functions.json"
    if not source.exists():
        source = REPO / "src" / "common" / "card_functions.json"
    try:
        tags = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    deck, edges = {int(card_id) for card_id in card_ids}, {}
    for card_id in deck:
        targets = []
        for tag in tags.get(str(card_id), ()):
            if not isinstance(tag, str) or not tag.startswith("evolves:"):
                continue
            try:
                target = int(tag.removeprefix("evolves:"))
            except ValueError:
                continue
            if target in deck and target != card_id:
                targets.append(target)
        if len(set(targets)) == 1:
            edges[card_id] = targets[0]
    roots = sorted(set(edges) - set(edges.values()))
    lines = []
    for root in roots:
        path, seen = [root], {root}
        while path[-1] in edges and edges[path[-1]] not in seen:
            path.append(edges[path[-1]])
            seen.add(path[-1])
        if len(path) > 1:
            lines.append(tuple(path))
    return tuple(lines)


def _strategy(strategy, *, shared_roles=None, shared_partners=None, shared_lines=()) -> dict:
    merged_roles = {int(card_id): tuple(names) for card_id, names in strategy.roles.items()}
    for card_id, values in (shared_roles or {}).items():
        merged_roles[card_id] = tuple(dict.fromkeys((*values, *merged_roles.get(card_id, ()))))
    roles = {str(card_id): list(names) for card_id, names in sorted(merged_roles.items())}
    lines = [{"path": list(line.path), "payoff": line.payoff, "role": line.role,
              "ready": {"energy": line.ready.energy}}
             for line in strategy.lines]
    declared_paths = {tuple(line["path"]) for line in lines}
    for path in shared_lines:
        if path in declared_paths:
            continue
        payoff_roles = set(merged_roles.get(path[-1], ()))
        role = ("win_condition" if "primary_attacker" in payoff_roles else
                next((name for name in ("win_condition", "secondary_attacker")
                      if name in payoff_roles), "evolution_base"))
        lines.append({"path": list(path), "payoff": path[-1], "role": role,
                      "ready": {"energy": None}})
    prize_plan = None if strategy.prize_plan is None else {
        "routes": [list(route) for route in strategy.prize_plan.routes],
        "prizes_to_win": strategy.prize_plan.prizes_to_win,
    }
    partners = {}
    for source in (shared_partners or {}, getattr(strategy, "partners", {}) or {}):
        for card_id, values in source.items():
            merged = tuple(dict.fromkeys((*partners.get(int(card_id), ()),
                                          *(int(value) for value in values))))
            if merged:
                partners[int(card_id)] = merged
    return {
        "name": strategy.name,
        "roles": roles,
        "lines": lines,
        "starter_priority": list(strategy.starter_priority),
        "partners": {str(card_id): list(values)
                     for card_id, values in sorted(partners.items())},
        "worth_overrides": {str(card_id): value
                            for card_id, value in sorted(strategy.worth_overrides.items())},
        "prize_plan": prize_plan,
        "params": dict(strategy.params),
    }


def build_manifest(agent_dir, *, when=None, git_hash=None, agent_name=None, cards=None,
                   **_ignored) -> dict:
    """Describe the exact Bellman bundle without importing the engine."""
    agent_dir = Path(agent_dir)
    when = when or datetime.now()
    git_hash = _git_hash(REPO) if git_hash is None else git_hash
    agent_name = agent_name or agent_dir.name
    strategy = _load_strategy(agent_dir)
    deck = _deck(agent_dir, cards)
    return {
        "schema_version": 3,
        "provenance": {
            "agent": agent_name,
            "built_at": when.isoformat(timespec="seconds"),
            "git_hash": git_hash,
            "artifact": artifact_stem(agent_name, when=when, git_hash=git_hash),
        },
        "system": "bellman",
        "deck": deck,
        "strategy": _strategy(
            strategy,
            shared_roles=_shared_roles(agent_dir, (row["id"] for row in deck["cards"])),
            shared_partners=_shared_partners(agent_dir, (row["id"] for row in deck["cards"])),
            shared_lines=_shared_lines(agent_dir, (row["id"] for row in deck["cards"]))),
        "capabilities": {
            "bellman": True,
            "card_functions": (agent_dir / "common" / "card_functions.json").exists(),
            "scouting": (agent_dir / "common" / "scouting" / "artifact.json").exists(),
            "native_engine": (agent_dir / "cg").exists(),
        },
    }


def render_brief_csv(manifest: dict) -> str:
    fields = ("schema_version", "agent", "artifact", "system", "record_type", "card_id", "value")
    provenance = manifest["provenance"]
    common = {"schema_version": manifest["schema_version"], "agent": provenance["agent"],
              "artifact": provenance["artifact"], "system": manifest["system"]}
    rows = [{**common, "record_type": "role", "card_id": card_id,
             "value": json.dumps(roles)}
            for card_id, roles in manifest["strategy"]["roles"].items()]
    rows.extend({**common, "record_type": "starter", "card_id": card_id,
                 "value": position}
                for position, card_id in enumerate(manifest["strategy"]["starter_priority"]))
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def render_brief(manifest: dict, **_ignored) -> str:
    provenance = manifest["provenance"]
    strategy = manifest["strategy"]
    payload = json.dumps(manifest, ensure_ascii=False).replace("<", "\\u003c")
    role_rows = "".join(
        f"<li><code>{html.escape(card_id)}</code>: {html.escape(', '.join(roles))}</li>"
        for card_id, roles in strategy["roles"].items())
    return (
        "<!doctype html>\n<html lang='en'><head><meta charset='utf-8'>"
        f"<title>Bellman Agent Brief — {html.escape(provenance['agent'])}</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;max-width:60rem}"
        "code{background:#f3f3f3;padding:.1rem .3rem}</style></head><body>"
        f"<h1>{html.escape(provenance['agent'])}</h1>"
        f"<p>Bellman · {manifest['deck']['size']} cards · "
        f"<code>{html.escape(provenance['git_hash'])}</code></p>"
        f"<h2>Deck roles</h2><ul>{role_rows}</ul>"
        f"<h2>Starter priority</h2><p>{html.escape(str(strategy['starter_priority']))}</p>"
        f"<script type='application/json' id='manifest'>{payload}</script>"
        "</body></html>\n"
    )


__all__ = ["build_manifest", "render_brief", "render_brief_csv"]
