"""Matchup Brief consumer — load the hand-authored ``briefs/<slug>.json`` and match one to the Read
by ``covers`` (ADR-0027 variant routing). Pure and lib-free. It never ACTS: the γ-gated consumers
live in the Pilot's Tactical layer.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .read import Read

_DEFAULT = Path(__file__).resolve().parent / "briefs"


@dataclass
class Brief:
    """One opponent archetype's objective counterplay annotations (see docs/matchups/<slug>.md)."""
    slug: str
    label: str
    covers: list[str]                                       # member archetype strings → variant routing
    opponent_properties: dict = field(default_factory=dict)  # lever keys (opponent_properties.json, same dir)
    wincon: dict = field(default_factory=dict)                # {line: [all stages], plan: str}
    pokemon: list[dict] = field(default_factory=list)         # {card, roles: [closed doctrine roles]}
    key_cards: list[dict] = field(default_factory=list)       # {card, role, enables?}


def _brief_from(raw: dict) -> Brief | None:
    """Build a Brief from a parsed JSON dict; None if it lacks the identity fields (slug + covers)."""
    slug, covers = raw.get("slug"), raw.get("covers")
    if not slug or not isinstance(covers, list) or not covers:
        return None
    return Brief(
        slug=slug, label=raw.get("label", slug), covers=[str(c) for c in covers],
        opponent_properties=raw.get("opponent_properties") or {},
        wincon=raw.get("wincon") or {}, pokemon=raw.get("pokemon") or [],
        key_cards=raw.get("key_cards") or [],
    )


def load_briefs(path: str | Path | None = None) -> list[Brief]:
    """Load every well-formed ``briefs/*.json``. Fail-safe: a bad file is skipped, a missing dir → []."""
    d = Path(path or _DEFAULT)
    if not d.is_dir():
        return []
    out: list[Brief] = []
    for f in sorted(d.glob("*.json")):
        try:
            b = _brief_from(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            b = None
        if b is not None:
            out.append(b)
    return out


def match_brief(briefs: list[Brief], read: Read | None) -> Brief | None:
    """Plain string routing on ``candidates[0]``; γ tempers how the match is USED downstream, never
    whether it matches."""
    if not read or not read.candidates:
        return None
    top = read.candidates[0][0]
    return next((b for b in briefs if top in b.covers), None)


_TARGET_ROLE = {
    "wincon": "prize_liability", "wincon_base": "fragile_preevo",
    "wincon_stage": "fragile_preevo", "disruption_target": "disruption_target",
    "primary_attacker": "attacker", "attacker": "attacker", "support": "engine",
    "energy_accel": "engine", "draw_engine": "engine",
}
_TARGET_ROLE_ORDER = ("wincon", "wincon_base", "wincon_stage", "disruption_target",
                      "primary_attacker", "attacker", "energy_accel", "draw_engine", "support")
_THREAT_ROLES = frozenset({"threat", "wincon", "primary_attacker", "attacker", "disruption"})


def resolve_brief_cards(brief: Brief, ids_for_name) -> tuple[frozenset[int], dict[int, str]]:
    """Resolve compact Pokémon doctrine into Pilot threat ids and target roles.

    Key trainer cards document how a body becomes dangerous; they never create a target on their
    own.  The selected body roles drive snipe, gust, and energy-denial through MatchupPlan.
    """
    threat_ids: set[int] = set()
    target_roles: dict[int, str] = {}
    for entry in brief.pokemon or []:
        roles = tuple(entry.get("roles") or ())
        ids = ids_for_name(entry.get("card", "")) or ()
        if _THREAT_ROLES.intersection(roles):
            threat_ids.update(ids)
        # A body may be both support and an explicitly valuable disruption target (Fezandipiti ex).
        # Select the strongest declared target meaning, not the JSON list's incidental order.
        target_role = next((_TARGET_ROLE[r] for r in _TARGET_ROLE_ORDER if r in roles), None)
        if target_role:
            for cid in ids:
                target_roles[cid] = target_role
    return frozenset(threat_ids), target_roles
