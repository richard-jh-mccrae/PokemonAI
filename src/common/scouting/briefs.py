"""Matchup Brief consumer — load the hand-authored ``briefs/<slug>.json`` and match one to the Read
by ``covers`` (ADR-0027 variant routing). Pure and lib-free. It never ACTS: the γ-gated consumers
enter the Bellman board potential as opponent-role facts.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from common.card_worth import role_value
from .pokemon_roles import general_pokemon_roles

from .read import Read

_DEFAULT = Path(__file__).resolve().parent / "briefs"


@dataclass
class Brief:
    """One opponent archetype's compact counterplay annotations."""
    slug: str
    label: str
    covers: list[str]                                       # member archetype strings → variant routing
    opponent_properties: dict = field(default_factory=dict)  # lever keys (opponent_properties.json, same dir)
    pokemon: list[dict] = field(default_factory=list)         # {card, roles: [compact doctrine roles]}
    key_cards: list[dict] = field(default_factory=list)       # {card, role}
    #: Ledger weight overrides scoped to THIS archetype's side of the board — same dotted-key
    #: format as a deck's `Strategy.ledger_overrides`; validated at use, so a typo fails loud.
    ledger_overrides: dict = field(default_factory=dict)


def _brief_from(raw: dict) -> Brief | None:
    """Build a Brief from a parsed JSON dict; None if it lacks the identity fields (slug + covers)."""
    slug, covers = raw.get("slug"), raw.get("covers")
    if not slug or not isinstance(covers, list) or not covers:
        return None
    return Brief(
        slug=slug, label=raw.get("label", slug), covers=[str(c) for c in covers],
        opponent_properties=raw.get("opponent_properties") or {},
        pokemon=raw.get("pokemon") or [],
        key_cards=raw.get("key_cards") or [],
        ledger_overrides=raw.get("ledger_overrides") or {},
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


def _covers_key(label: str) -> str:
    """Archetype labels arrive with mixed straight/curly apostrophes (the artifact's own
    spellings drift per set); routing must not hinge on typography."""
    return label.replace("’", "'")


def match_brief(briefs: list[Brief], read: Read | None) -> Brief | None:
    """Plain string routing on ``candidates[0]``; γ tempers how the match is USED downstream, never
    whether it matches."""
    if not read or not read.candidates:
        return None
    top = _covers_key(read.candidates[0][0])
    return next((b for b in briefs
                 if any(top == _covers_key(cover) for cover in b.covers)), None)


_TARGET_ROLE = {
    "primary_attacker": "primary_attacker", "backup_attacker": "backup_attacker",
    "disruption_target": "disruption_target", "support_pokemon": "support_pokemon",
    "accel_source": "accel_source", "engine": "engine", "counter_mover": "counter_mover",
}
_TARGET_ROLE_ORDER = ("primary_attacker", "disruption_target", "backup_attacker",
                      "accel_source", "counter_mover", "engine", "support_pokemon")
_THREAT_ROLES = frozenset({
    "primary_attacker", "backup_attacker", "disruption_target",
})


def _evolution_line(card_ids, ids_for_name, stat_for_id, forward_ids) -> frozenset[int]:
    """Return every known printing in the declared attacker's evolution line."""
    line = {int(card_id) for card_id in card_ids}
    if stat_for_id is None:
        return frozenset(line)
    if forward_ids is not None:
        for card_id in tuple(line):
            line.update(int(descendant) for descendant in forward_ids(card_id) or ())
    pending = list(line)
    while pending:
        card_id = pending.pop()
        stat = stat_for_id(card_id)
        parent_name = getattr(stat, "evolvesFrom", None) if stat is not None else None
        for ancestor in ids_for_name(parent_name) if parent_name else ():
            if int(ancestor) not in line:
                line.add(int(ancestor))
                pending.append(int(ancestor))
    return frozenset(line)


def resolve_brief_cards(brief: Brief, ids_for_name, *, stat_for_id=None,
                        forward_ids=None, functions=None) -> tuple[frozenset[int], dict[int, str]]:
    """Resolve compact Pokémon doctrine into Bellman threat ids and target roles.

    Key trainer cards document how a body becomes dangerous; they never create a target on their
    own.  The selected body roles drive snipe, gust, and energy-denial through MatchupPlan.
    """
    threat_ids: set[int] = set()
    role_claims: dict[int, set[str]] = {}
    primary_ids: set[int] = set()
    for entry in brief.pokemon or []:
        roles = tuple(entry.get("roles") or ())
        ids = {int(card_id) for card_id in ids_for_name(entry.get("card", "")) or ()}
        if stat_for_id is not None:
            generic = general_pokemon_roles(ids, _StatLookup(stat_for_id, forward_ids), functions)
            for card_id, card_roles in generic.items():
                role_claims.setdefault(card_id, set()).update(card_roles)
        if _THREAT_ROLES.intersection(roles):
            threat_ids.update(ids)
        for card_id in ids:
            role_claims.setdefault(card_id, set()).update(roles)
        if "primary_attacker" in roles:
            primary_ids.update(ids)

    # A primary attacker means its whole evolution line. This lets generic card evolution data
    # identify the Basic and intermediate bodies even when the Brief only names the final attacker.
    primary_line = _evolution_line(primary_ids, ids_for_name, stat_for_id, forward_ids)
    threat_ids.update(primary_line)
    for card_id in primary_line:
        role_claims.setdefault(card_id, set()).add("primary_attacker")

    target_roles: dict[int, str] = {}
    for card_id, roles in role_claims.items():
        # A body may be both support and an explicitly valuable disruption target (Fezandipiti ex).
        # Select the strongest declared target meaning, not the JSON list's incidental order.
        target_role = next((_TARGET_ROLE[role] for role in _TARGET_ROLE_ORDER if role in roles), None)
        if target_role:
            target_roles[card_id] = target_role
    return frozenset(threat_ids), target_roles


def scouted_ledger_roles(read: Read | None, brief: Brief | None, stats,
                         functions=None) -> dict[int, tuple[str, ...]]:
    """Recognition role claims by card id (matched Brief declarations + Read intel) for the
    Ledger's opponent worth read; the caller blends them by the Read's gamma (ADR-0148)."""
    claims: dict[int, tuple[str, ...]] = {}

    def add(card_id, roles):
        if roles:
            claims[int(card_id)] = tuple(dict.fromkeys(
                (*claims.get(int(card_id), ()), *roles)))

    for intel in (*(read.threats if read else ()), *(read.targets if read else ())):
        add(intel.cardId, (intel.role,) if intel.role else ())
    ids_for_name = getattr(stats, "ids_for_name", None)
    if brief is not None and ids_for_name is not None:
        _threat_ids, target_roles = resolve_brief_cards(
            brief, ids_for_name, stat_for_id=getattr(stats, "get", None),
            forward_ids=getattr(stats, "forward_card_ids", None), functions=functions)
        for card_id, role in target_roles.items():
            add(card_id, (role,))
    return claims


class _StatLookup:
    def __init__(self, get, forward_card_ids=None):
        self.get = get
        self.forward_card_ids = forward_card_ids or (lambda _card_id: ())


_STAGE_RANK = {"basic": 0, "stage1": 1, "stage2": 2}


def _stage_rank(stats, card_id: int) -> int:
    stat = stats.get(card_id) if stats is not None else None
    return _STAGE_RANK.get(str(getattr(stat, "stage", "") or "").lower(), 0)


def resolve_scouted_role_worth(read: Read | None, artifact, stats, *, briefs=(), functions=None,
                               line_decay: float = 1.0) -> dict[int, float]:
    """Posterior expected role Worth from authored Briefs, with dossier targets as fallback.

    ``line_decay`` discounts a primary attacker's line per evolution step still owed before the
    payoff; 1.0 keeps the flat stamp that values a Basic exactly like the body about to become
    the win condition.
    """
    expected: dict[int, float] = {}
    dossiers = getattr(artifact, "dossiers", {}) if artifact is not None else {}
    for candidate, probability in (read.candidates if read is not None else ()):
        brief = next((item for item in briefs if candidate in item.covers), None)
        ids_for_name = getattr(stats, "ids_for_name", None)
        if brief is not None and ids_for_name is not None:
            _threat_ids, target_roles = resolve_brief_cards(
                brief, ids_for_name, stat_for_id=getattr(stats, "get", None),
                forward_ids=getattr(stats, "forward_card_ids", None), functions=functions)
            candidate_worth: dict[int, float] = {}
            for row in brief.pokemon or ():
                roles = tuple(row.get("roles") or ())
                row_ids = {int(card_id) for card_id in ids_for_name(row.get("card", "")) or ()}
                generic = general_pokemon_roles(row_ids, stats, functions)
                for card_id in row_ids:
                    combined = tuple(dict.fromkeys((*generic.get(card_id, ()), *roles)))
                    worth = role_value(combined)
                    candidate_worth[int(card_id)] = max(
                        candidate_worth.get(int(card_id), 0.0), worth)
                if "primary_attacker" in roles:
                    line_ids = _evolution_line(
                        row_ids, ids_for_name, getattr(stats, "get", None),
                        getattr(stats, "forward_card_ids", None))
                    payoff_prizes = max(
                        (int(getattr(stats.get(card_id), "prize_value", 1) or 1)
                         for card_id in line_ids), default=1)
                    # Each step still owed costs the opponent a turn and a card, so the body one
                    # evolution short of the win condition outranks the Basic two behind it.
                    payoff_rank = max(
                        (_stage_rank(stats, card_id) for card_id in line_ids), default=0)
                    for card_id in line_ids:
                        owed = max(0, payoff_rank - _stage_rank(stats, card_id))
                        candidate_worth[card_id] = max(
                            candidate_worth.get(card_id, 0.0),
                            worth * payoff_prizes * (line_decay ** owed))
            primary_worth = role_value(("primary_attacker",))
            for card_id, role in target_roles.items():
                if role == "primary_attacker":
                    candidate_worth[int(card_id)] = max(
                        candidate_worth.get(int(card_id), 0.0), primary_worth)
            for card_id, worth in candidate_worth.items():
                expected[card_id] = expected.get(card_id, 0.0) + float(probability) * worth
            continue
        dossier = dossiers.get(candidate) or {}
        roles_by_card: dict[int, set[str]] = {}
        for row in dossier.get("targets") or ():
            roles_by_card.setdefault(int(row["cardId"]), set()).add(str(row["role"]))
        for card_id, roles in roles_by_card.items():
            stat = stats.get(card_id) if stats is not None else None
            if "fragile_preevo" in roles and getattr(stat, "stage", None) not in (None, "basic"):
                roles = {*roles, "primary_attacker"}
            expected[card_id] = expected.get(card_id, 0.0) + float(probability) * role_value(roles)
    return expected
