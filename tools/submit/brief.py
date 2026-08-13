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
from common.pilot_profile import PilotProfile


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


def _strategy(strategy) -> dict:
    roles = {str(card_id): list(names) for card_id, names in sorted(strategy.roles.items())}
    lines = [{"path": list(line.path), "payoff": line.payoff, "role": line.role,
              "ready": {"energy": line.ready.energy}}
             for line in strategy.lines]
    prize_plan = None if strategy.prize_plan is None else {
        "routes": [list(route) for route in strategy.prize_plan.routes],
        "prizes_to_win": strategy.prize_plan.prizes_to_win,
    }
    return {
        "name": strategy.name,
        "roles": roles,
        "lines": lines,
        "starter_priority": list(strategy.starter_priority),
        "partners": {str(card_id): list(partners)
                     for card_id, partners in sorted(strategy.partners.items())},
        "worth_overrides": {str(card_id): value
                            for card_id, value in sorted(strategy.worth_overrides.items())},
        "pilot_adjustments": dict(strategy.pilot_adjustments),
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
    pilot_profile = PilotProfile.resolve(
        authored_deck=strategy.pilot_adjustments, provenance=f"strategy:{strategy.name}")
    return {
        "schema_version": 4,
        "provenance": {
            "agent": agent_name,
            "built_at": when.isoformat(timespec="seconds"),
            "git_hash": git_hash,
            "artifact": artifact_stem(agent_name, when=when, git_hash=git_hash),
        },
        "system": "bellman",
        "deck": _deck(agent_dir, cards),
        "strategy": _strategy(strategy),
        "pilot_profile": pilot_profile.as_dict(),
        "safety_bounds": {
            "callback_watchdog_seconds": {
                "value": 120.0, "units": "seconds", "adjustable": False,
                "provenance": "mirror_gate",
            },
        },
        "capabilities": {
            "bellman": True,
            "card_functions": (agent_dir / "common" / "card_functions.json").exists(),
            "scouting": (agent_dir / "common" / "scouting" / "artifact.json").exists(),
            "native_engine": (agent_dir / "cg").exists(),
        },
    }


def render_brief_csv(manifest: dict) -> str:
    fields = ("schema_version", "agent", "artifact", "system", "record_type", "card_id",
              "value", "name", "group", "family", "global", "deck_learned_adjustment",
              "authored_deck_adjustment", "effective", "minimum", "maximum", "units",
              "learnable", "provenance")
    provenance = manifest["provenance"]
    common = {"schema_version": manifest["schema_version"], "agent": provenance["agent"],
              "artifact": provenance["artifact"], "system": manifest["system"]}
    rows = [{**common, "record_type": "role", "card_id": card_id,
             "value": json.dumps(roles)}
            for card_id, roles in manifest["strategy"]["roles"].items()]
    rows.extend({**common, "record_type": "starter", "card_id": card_id,
                 "value": position}
                for position, card_id in enumerate(manifest["strategy"]["starter_priority"]))
    for group_rows in manifest["pilot_profile"]["groups"].values():
        rows.extend({**common, "record_type": "pilot_parameter", **row,
                     "provenance": manifest["pilot_profile"]["provenance"]}
                    for row in group_rows)
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
    customized = sum(
        row["deck_learned_adjustment"] != 0 or row["authored_deck_adjustment"] != 0
        for rows in manifest["pilot_profile"]["groups"].values() for row in rows)
    profile_sections = []
    for group, rows in manifest["pilot_profile"]["groups"].items():
        rendered = "".join(
            ("<tr class='custom' >" if (row["deck_learned_adjustment"] != 0
                                        or row["authored_deck_adjustment"] != 0) else "<tr>")
            + "".join(f"<td>{html.escape(str(row[key]))}</td>" for key in (
                "name", "family", "global", "deck_learned_adjustment",
                "authored_deck_adjustment", "effective", "minimum", "maximum", "units"))
            + "</tr>" for row in rows)
        profile_sections.append(
            f"<details><summary>{html.escape(group)} ({len(rows)})</summary>"
            "<table><thead><tr><th>Name</th><th>Family</th><th>Global</th>"
            "<th>Deck learned</th><th>Deck authored</th><th>Effective</th>"
            "<th>Min</th><th>Max</th><th>Units</th></tr></thead>"
            f"<tbody>{rendered}</tbody></table></details>")
    safety_rows = "".join(
        f"<li><code>{html.escape(name)}</code>: {row['value']} {html.escape(row['units'])}</li>"
        for name, row in manifest["safety_bounds"].items())
    return (
        "<!doctype html>\n<html lang='en'><head><meta charset='utf-8'>"
        f"<title>Bellman Agent Brief — {html.escape(provenance['agent'])}</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;max-width:60rem}"
        "code{background:#f3f3f3;padding:.1rem .3rem}table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #ddd;padding:.35rem;text-align:left}.custom{background:#fff3bf}"
        "details{margin:.6rem 0}</style></head><body>"
        f"<h1>{html.escape(provenance['agent'])}</h1>"
        f"<p>Bellman · {manifest['deck']['size']} cards · "
        f"<code>{html.escape(provenance['git_hash'])}</code></p>"
        f"<h2>Deck roles</h2><ul>{role_rows}</ul>"
        f"<h2>Starter priority</h2><p>{html.escape(str(strategy['starter_priority']))}</p>"
        f"<h2>Pilot profile</h2><p><code>{manifest['pilot_profile']['hash']}</code> · "
        f"{customized} deck-customized parameters</p>{''.join(profile_sections)}"
        f"<details><summary>Read-only safety bounds</summary><ul>{safety_rows}</ul></details>"
        f"<script type='application/json' id='manifest'>{payload}</script>"
        "</body></html>\n"
    )


__all__ = ["build_manifest", "render_brief", "render_brief_csv"]
