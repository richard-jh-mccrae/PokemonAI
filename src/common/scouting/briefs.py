"""Matchup Brief consumer — load the hand-authored Briefs and match one to the Read (ADR-0027).

Pure and lib-free (mirrors ``artifact.load_artifact`` + ``matchup.matchup_favorability``). A Brief is the
objective, shared counterplay profile of one opponent **Variant Cluster**, authored by ``/matchup-genie``
at ``src/common/scouting/briefs/<slug>.json``. This bridge loads them and, given the Scouting Read,
returns the Brief whose ``covers`` list contains the Read's top candidate archetype — the variant routing
of ADR-0027. It never acts; a (future, γ-gated) consumer decides what to do with the match, exactly as
the card-fact posture and ``matchup_favorability`` do.
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
    opponent_properties: dict = field(default_factory=dict)  # lever keys (assets/opponent_properties.json)
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
    """The Brief whose ``covers`` contains the Read's top candidate archetype, else None.

    Plain string routing (ADR-0027: the Read matches ``candidates[0]`` against each Brief's ``covers``);
    γ tempers how the match is USED downstream, not whether it matches. None on no Read / no candidates /
    no covering Brief.
    """
    if not read or not read.candidates:
        return None
    top = read.candidates[0][0]
    return next((b for b in briefs if top in b.covers), None)


def resolve_brief_cards(brief: Brief, ids_for_name) -> tuple[frozenset[int], dict[int, str]]:
    """Resolve a Brief's name-keyed ``threats``/``targets`` to card ids (ADR-0027 consumer substrate).

    The authored Brief names cards, but the Pilot/Board works in card ids; this bridges the two via an
    injected ``ids_for_name`` lookup (a ``name -> iterable[int]``, e.g. a provider's ``ids_for_name``),
    which keeps the resolution pure and testable without the engine.

    Args:
        brief: the matched Matchup Brief.
        ids_for_name: ``name -> iterable[int]`` — every card id printed under a card name.

    Returns:
        ``(threat_ids, target_roles)`` — ``threat_ids`` is the frozenset of ids of every
        ``threats[].card``; ``target_roles`` maps each resolved ``targets[].card`` id to its ``role``.
        A name that resolves to no id is skipped (never raises); a name mapping to several ids maps all
        of them; a card that is both a threat and a target appears in both outputs (independent surfaces).
    """
    threat_ids: set[int] = set()
    for t in brief.threats or []:
        threat_ids.update(ids_for_name(t.get("card", "")) or ())
    target_roles: dict[int, str] = {}
    for t in brief.targets or []:
        role = t.get("role")
        for cid in ids_for_name(t.get("card", "")) or ():
            target_roles[cid] = role
    return frozenset(threat_ids), target_roles
