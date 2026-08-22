"""Build the shipped-agent manifest and its human-readable brief."""
from __future__ import annotations

import csv
import html
import importlib.util
import io
import json
import sys
from collections import Counter
from datetime import datetime
from dataclasses import asdict
from pathlib import Path

from submit.package import REPO, _git_hash, artifact_stem
from common.ledger import ComputeConfiguration, DeckOverlay, ValuationConfiguration


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


def _strategy(strategy, deck) -> dict:
    resolved_roles = strategy.roles.resolve(deck)
    roles = {str(card_id): list(names) for card_id, names in sorted(resolved_roles.items())}
    prize_plan = {
        "protect": list(strategy.prize_plan.protect),
        "offer": list(strategy.prize_plan.offer),
    }
    return {
        "name": strategy.name,
        "roles": roles,
        "starter_priority": list(strategy.starter_priority),
        "prize_plan": prize_plan,
        "params": dict(strategy.params),
    }


def _ledger_configuration(strategy) -> dict:
    overlay = dict(strategy.ledger_overlay)
    resolved = ValuationConfiguration.general().resolve(DeckOverlay(overlay))
    return {
        "identity": resolved.identity,
        "schema_version": resolved.schema_version,
        "deck_overlay": {str(name): float(value) for name, value in sorted(overlay.items())},
        "values": dict(resolved),
    }


def build_manifest(agent_dir, *, when=None, git_hash=None, agent_name=None, cards=None,
                   **_ignored) -> dict:
    """Describe the exact shipped bundle without importing the engine."""
    agent_dir = Path(agent_dir)
    when = when or datetime.now()
    git_hash = _git_hash(REPO) if git_hash is None else git_hash
    agent_name = agent_name or agent_dir.name
    strategy = _load_strategy(agent_dir)
    cards = _card_index() if cards is None else cards
    deck = _deck(agent_dir, cards)
    deck_ids = tuple(card["id"] for card in deck["cards"] for _ in range(card["count"]))
    compute = ComputeConfiguration()
    return {
        "schema_version": 9,
        "provenance": {
            "agent": agent_name,
            "built_at": when.isoformat(timespec="seconds"),
            "git_hash": git_hash,
            "artifact": artifact_stem(agent_name, when=when, git_hash=git_hash),
        },
        "system": "ledger",
        "deck": deck,
        "strategy": _strategy(strategy, deck_ids),
        "valuation_configuration": _ledger_configuration(strategy),
        "compute_configuration": {
            "identity": compute.identity,
            "schema_version": compute.schema_version,
            "search": {"identity": compute.search.identity, **asdict(compute.search)},
            "policy": {"identity": compute.policy.identity, **asdict(compute.policy)},
        },
        "safety_bounds": {
            "callback_watchdog_seconds": {
                "value": 120.0, "units": "seconds", "adjustable": False,
                "provenance": "mirror_gate",
            },
        },
        "capabilities": {
            "ledger": True,
            "card_store": (agent_dir / "common" / "cards" / "card_facts.py").exists(),
            "scouting": (agent_dir / "common" / "scouting" / "artifact.json").exists(),
            "native_engine": (agent_dir / "cg").exists(),
        },
    }


def render_brief_csv(manifest: dict) -> str:
    fields_ = ("schema_version", "agent", "artifact", "system", "record_type", "card_id",
               "value", "name", "provenance")
    provenance = manifest["provenance"]
    common = {"schema_version": manifest["schema_version"], "agent": provenance["agent"],
              "artifact": provenance["artifact"], "system": manifest["system"]}
    rows = [{**common, "record_type": "role", "card_id": card_id,
             "value": json.dumps(roles)}
            for card_id, roles in manifest["strategy"]["roles"].items()]
    rows.extend({**common, "record_type": "starter", "card_id": card_id,
                 "value": position}
                for position, card_id in enumerate(manifest["strategy"]["starter_priority"]))
    configuration = manifest["valuation_configuration"]
    rows.extend({**common, "record_type": "valuation_coefficient", "name": name,
                 "value": value, "provenance": configuration["identity"]}
                for name, value in configuration["values"].items())
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields_)
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
    configuration = manifest["valuation_configuration"]
    overridden = set(configuration["deck_overlay"])

    def weight_table(group: str, prefix: str = "") -> str:
        rendered = "".join(
            ("<tr class='custom'>" if f"{prefix}{name}" in overridden or name in overridden
             else "<tr>")
            + f"<td>{html.escape(str(name))}</td><td>{value}</td></tr>"
            for name, value in configuration[group].items())
        return (f"<details><summary>{html.escape(group)} ({len(configuration[group])})</summary>"
                "<table><thead><tr><th>Name</th><th>Value</th></tr></thead>"
                f"<tbody>{rendered}</tbody></table></details>")

    weight_sections = weight_table("values")
    override_rows = "".join(
        f"<li><code>{html.escape(name)}</code>: {value}</li>"
        for name, value in configuration["deck_overlay"].items()) or "<li>none</li>"
    safety_rows = "".join(
        f"<li><code>{html.escape(name)}</code>: {row['value']} {html.escape(row['units'])}</li>"
        for name, row in manifest["safety_bounds"].items())
    return (
        "<!doctype html>\n<html lang='en'><head><meta charset='utf-8'>"
        f"<title>Agent Brief — {html.escape(provenance['agent'])}</title>"
        "<style>body{font-family:system-ui,sans-serif;margin:2rem;max-width:60rem}"
        "code{background:#f3f3f3;padding:.1rem .3rem}table{border-collapse:collapse;width:100%}"
        "th,td{border:1px solid #ddd;padding:.35rem;text-align:left}.custom{background:#fff3bf}"
        "details{margin:.6rem 0}</style></head><body>"
        f"<h1>{html.escape(provenance['agent'])}</h1>"
        f"<p>Ledger · {manifest['deck']['size']} cards · "
        f"<code>{html.escape(provenance['git_hash'])}</code></p>"
        f"<h2>Deck roles</h2><ul>{role_rows}</ul>"
        f"<h2>Starter priority</h2><p>{html.escape(str(strategy['starter_priority']))}</p>"
        f"<h2>Valuation configuration</h2><p><code>{configuration['identity']}</code> · "
        f"{len(configuration['deck_overlay'])} deck residuals</p>"
        f"<ul>{override_rows}</ul>{weight_sections}"
        f"<details><summary>Read-only safety bounds</summary><ul>{safety_rows}</ul></details>"
        f"<script type='application/json' id='manifest'>{payload}</script>"
        "</body></html>\n"
    )


__all__ = ["build_manifest", "render_brief", "render_brief_csv"]
