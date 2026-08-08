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
    tempo: str = ""
    summary: str = ""
    opponent_properties: dict = field(default_factory=dict)  # lever keys (opponent_properties.json, same dir)
    threats: list[dict] = field(default_factory=list)        # attackers to respect ({card, why})
    targets: list[dict] = field(default_factory=list)        # disrupt/snipe ({card, role, why})


def _brief_from(raw: dict) -> Brief | None:
    """Build a Brief from a parsed JSON dict; None if it lacks the identity fields (slug + covers)."""
    slug, covers = raw.get("slug"), raw.get("covers")
    if not slug or not isinstance(covers, list) or not covers:
        return None
    return Brief(
        slug=slug, label=raw.get("label", slug), covers=[str(c) for c in covers],
        tempo=raw.get("tempo", ""), summary=raw.get("summary", ""),
        opponent_properties=raw.get("opponent_properties") or {},
        threats=raw.get("threats") or [], targets=raw.get("targets") or [],
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


def resolve_brief_cards(brief: Brief, ids_for_name) -> tuple[frozenset[int], dict[int, str]]:
    """``(threat_ids, target_roles)``. A name resolving to no id is skipped; one mapping to several
    ids maps all of them; a card that is both threat and target appears in both (independent)."""
    threat_ids: set[int] = set()
    for t in brief.threats or []:
        threat_ids.update(ids_for_name(t.get("card", "")) or ())
    target_roles: dict[int, str] = {}
    for t in brief.targets or []:
        role = t.get("role")
        for cid in ids_for_name(t.get("card", "")) or ():
            target_roles[cid] = role
    return frozenset(threat_ids), target_roles
