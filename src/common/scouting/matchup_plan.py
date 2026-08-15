"""MatchupPlan — the unified opponent target-priority spine (ADR-0051).

Every opponent body gets one ``(role, priority)`` from tiers of decreasing generality: the
γ-independent **general** card fact, then the γ-gated **matchup** tier (curated Brief over Intel).

**An ORDINAL PRIORITY, not a worth** (D1): nothing here may enter the prize-denominated
the Bellman card-Worth currency. **The vocabulary is CLOSED** (D2) — an undeclared role
resolves to 0 silently, so the audit and its two walks live HERE rather than in the test."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

# `_UTILITY_TAGS` (a body that never attacks) is the `avoid` trigger, deliberately NARROWER than
# `_ENGINE_TAGS`, which would force `avoid` onto a 1-prize `energy_accel` body — a deck's ATTACKER.
from common.strategy.context import _ENGINE_TAGS, _UTILITY_TAGS

_GENERAL = "general"     # a card fact — applies at γ=0
_MATCHUP = "matchup"     # a Read/Brief claim — scaled × γ
PROVENANCES = (_GENERAL, _MATCHUP)


#: Who may ASSIGN a role — deliberately NOT the two γ provenances above. Provenance answers *does γ
#: scale it?*; this answers *may this store say it?*, which is what keeps `unknown` out of a Brief.
DERIVED_BY = "derived"   # `derive_general_roles` — a deck-agnostic card fact
READ_BY = "read"         # `Scout` Intel / the artifact's dossiers
BRIEF_BY = "brief"       # a hand-authored Matchup Brief (`briefs/*.json`)
ASSIGNERS = (DERIVED_BY, READ_BY, BRIEF_BY)


@dataclass(frozen=True)
class Role:
    """``assigners`` is a claim about the SHIPPED stores, checked against them by the audit test."""

    priority: int
    reason: str
    assigners: tuple[str, ...]


#: **The closed role vocabulary.** Positive = target sooner, negative = leave alone. Magnitudes sit
#: above the snipe/gust rungs but well below KO_SCORE, and the ORDER is the load-bearing part.
ROLE_REGISTRY: dict[str, Role] = {
    "primary_attacker": Role(
        100, "a primary attacker or multi-prize liability — KO/gust it", (DERIVED_BY, READ_BY, BRIEF_BY)),
    "fragile_preevo": Role(
        90, "a pre-evolution with a threatening forward line — deny it before it comes online",
        (DERIVED_BY, READ_BY)),
    "disruption_target": Role(
        60, "their key supporter/enabler the Brief says to REMOVE (the 'hunt an engine' role). "
            "Curated ONLY: an explicit human claim about this matchup outranks a derived one, and "
            "nothing derives it — that is what the role means.", (BRIEF_BY,)),
    "backup_attacker": Role(
        50, "a body whose line actually attacks. **530 shipped dossier assignments resolved to 0 "
            "before Issue #395** — the largest role population in the artifact, inert. Stated "
            "precisely, because the headline is easy to over-read: what changed is that the STRING "
            "now resolves to a real priority instead of falling through `.get(role, 0)`. For a body "
            "IN PLAY the derived tier usually names it too and, being γ-independent, supersedes the "
            "dossier's claim; the dossier's own 530 remain the live reading for the predicted "
            "entries the derivation cannot see. Both are corrections of the same defect. Sits BELOW "
            "a primary attacker deliberately: a backup attacker is a real steer but not "
            "automatically a better removal target than the primary attacker. The worked example is "
            "Crustle, the Crustle / Mega Kangaskhan ex deck's main attacker *because* it cannot be "
            "damaged by an ex attacker in an ex-dominated format.",
        (DERIVED_BY, READ_BY, BRIEF_BY)),
    "enabler": Role(
        40, "a body that assists the key Pokémon in HOW it attacks — damage boosts, a free-retreat "
            "grant, ability fuel (the Solrock/Lunatone shape). Below `backup_attacker` because removing "
            "the attacker is the more direct answer. Requires no new Function Tag: every input is "
            "already a parsed `CardStat` field. The Read does not emit it — no dossier does the "
            "derivation — so it is derived-or-curated.", (DERIVED_BY, BRIEF_BY)),
    "engine": Role(
        0, "a plain accelerant/enabler (Cinderace class) — NEUTRAL: a poor snipe target, so do not "
           "boost it. `disruption_target` is how a Brief opts one in, and `avoid` is how the "
           "general tier de-prioritizes the 1-prize utility class.",
        (DERIVED_BY, READ_BY, BRIEF_BY)),
    "support_pokemon": Role(
        0, "a generally useful support body; prize yield still contributes independently",
        (READ_BY, BRIEF_BY)),
    "accel_source": Role(
        0, "a body that accelerates resources; a Brief may separately mark it for disruption",
        (BRIEF_BY,)),
    "counter_mover": Role(
        0, "a support body that relocates damage counters", (BRIEF_BY,)),
    "unknown": Role(
        0, "emitted by `Scout._target_role` when there is no CardStat at all, and by "
           "`Scout._dossier_intel` for a dossier entry with no role. READ-ONLY because it makes no "
           "strategic claim.", (READ_BY,)),
    "avoid": Role(
        -80, "decoy / self-shuffler — never spend removal here. **Gated on `prize_value == 1`** "
             "(D4): a 1-prize utility body (Dudunsparce / Budew class) is a poor place to spend "
             "removal, but a 2- or 3-prize engine is a PRIME one and the prizes are the reason. "
             "Before the gate this fired on Mega Kangaskhan ex (3 prizes) and Fezandipiti ex (2), "
             "unscaled by γ and written AFTER Read-Intel, so it overwrote the `primary_attacker` the "
             "dossier had correctly assigned. The Read does not emit it; `Scout._target_role` has "
             "no such branch.", (DERIVED_BY, BRIEF_BY)),
}

#: DERIVED from :data:`ROLE_REGISTRY`, never written twice. Kept as a name because `sound_rules.py`'s
#: `firing-equation-constants` whitelist names it.
_ROLE_PRIORITY: dict[str, int] = {name: r.priority for name, r in ROLE_REGISTRY.items()}


def role_priority(role: str | None) -> int:
    """0 for an unroled body, a real state: :func:`undeclared_roles` reddens before an unknown one."""
    return _ROLE_PRIORITY.get(role or "", 0)


def undeclared_roles(roles: Sequence[str]) -> list[str]:
    """Empty is the contract. Takes the values, not an artifact, so a fabricated one can bite it."""
    return sorted(r for r in set(roles) if r not in ROLE_REGISTRY)


def roles_in_dossiers(dossiers: Mapping) -> list[str]:
    """Walks the SHIPPED artifact, because a hand-kept list is what a new role would not join."""
    out: set[str] = set()
    for sections in (dossiers or {}).values():
        for entries in (sections or {}).values():
            if not isinstance(entries, list):
                continue                       # `card_inclusion` and friends are not role-bearing
            out.update(e["role"] for e in entries
                       if isinstance(e, dict) and isinstance(e.get("role"), str) and e["role"])
    return sorted(out)


def roles_in_brief(brief: Mapping) -> list[str]:
    """Every authored Brief Role string; the registry audit rejects unknown vocabulary."""
    out: set[str] = set()
    for entry in (brief or {}).get("pokemon") or ():
        for role in (entry or {}).get("roles") or ():
            if isinstance(role, str):
                out.add(role)
    return sorted(out)


@dataclass(frozen=True)
class BodyFacts:
    """Supplied by the runtime, which keeps this module pure."""

    tags: frozenset = frozenset()
    prize_value: int = 1
    own_damage: float = 0.0          # this body's own biggest priced hit
    forward_damage: float = 0.0      # the biggest its line evolves INTO (0 = dead end)
    damage_boost: int = 0            # `CardStat.damageBoost`
    grants_free_retreat: bool = False  # `CardStat.retreatFreeGrant` — a board-level Ability
    ability_fuel: bool = False       # `CardStat.abilityEnergyTypes`


def derive_general_roles(facts: Mapping[int, BodyFacts]) -> dict[int, str]:
    """The γ-independent tier: FIRST MATCH WINS and the order is the ruling; an underived body
    keeps whatever the Read or a Brief gave it."""
    out: dict[int, str] = {}
    for cid, f in (facts or {}).items():
        tags = f.tags or frozenset()
        if (_UTILITY_TAGS & tags) and f.prize_value == 1:
            out[cid] = "avoid"
        elif f.prize_value >= 2:
            out[cid] = "primary_attacker"
        elif f.forward_damage > 0:
            out[cid] = "fragile_preevo"
        elif f.own_damage > 0:
            out[cid] = "backup_attacker"
        elif f.damage_boost or f.grants_free_retreat or f.ability_fuel:
            out[cid] = "enabler"
        elif _ENGINE_TAGS & tags:
            out[cid] = "engine"
    return out


def observed_body_facts(player: Mapping, *, stats=None, functions=None) -> dict[int, BodyFacts]:
    """Resolve neutral in-play card facts without importing a strategic chooser."""

    facts: dict[int, BodyFacts] = {}
    bodies = tuple((player or {}).get("active") or ()) + tuple((player or {}).get("bench") or ())
    for body in bodies:
        card_id = (body or {}).get("id")
        if card_id is None or int(card_id) in facts:
            continue
        card_id = int(card_id)
        stat = stats.get(card_id) if stats is not None else None
        forward = stats.forward_max_damage(card_id) if stats is not None else 0
        tags = frozenset(functions.tags(card_id)) if functions is not None else frozenset()
        facts[card_id] = BodyFacts(
            tags=tags,
            prize_value=int(getattr(stat, "prize_value", 1) if stat is not None else 1),
            own_damage=float(getattr(stat, "maxDamage", 0) or 0),
            forward_damage=float(forward or 0),
            damage_boost=int(getattr(stat, "damageBoost", 0) or 0),
            grants_free_retreat=bool(getattr(stat, "retreatFreeGrant", None)),
            ability_fuel=bool(getattr(stat, "abilityEnergyTypes", ()) or ()),
        )
    return facts


@dataclass(frozen=True)
class _Assignment:
    role: str
    provenance: str      # _GENERAL | _MATCHUP


@dataclass
class MatchupPlan:
    """``gamma`` is the Read confidence scaling the matchup tier; the general tier is γ-independent."""
    assignments: dict[int, _Assignment] = field(default_factory=dict)
    gamma: float = 0.0

    def role(self, body_id: int | None) -> str | None:
        a = self.assignments.get(body_id) if body_id is not None else None
        return a.role if a else None

    def priority(self, body_id: int | None) -> float:
        """Higher = target sooner, negative = avoid, 0 = unroled. A matchup claim is scaled by γ."""
        a = self.assignments.get(body_id) if body_id is not None else None
        if a is None:
            return 0.0
        base = float(role_priority(a.role))
        return base if a.provenance == _GENERAL else base * self.gamma


def build_matchup_plan(*, brief_roles: dict[int, str] | None = None,
                       read_roles: dict[int, str] | None = None,
                       general_roles: dict[int, str] | None = None,
                       gamma: float = 0.0) -> MatchupPlan:
    """Most-general first, so the more specific tier overwrites per body."""
    assignments: dict[int, _Assignment] = {}
    for cid, role in (read_roles or {}).items():
        assignments[cid] = _Assignment(role, _MATCHUP)
    for cid, role in (general_roles or {}).items():        # general card fact overrides Read-Intel
        assignments[cid] = _Assignment(role, _GENERAL)
    for cid, role in (brief_roles or {}).items():          # curated Brief overrides all
        assignments[cid] = _Assignment(role, _MATCHUP)
    return MatchupPlan(assignments=assignments, gamma=gamma)


__all__: Sequence[str] = (
    "Role", "ROLE_REGISTRY", "PROVENANCES", "ASSIGNERS", "DERIVED_BY", "READ_BY", "BRIEF_BY",
    "BodyFacts", "MatchupPlan",
    "role_priority", "undeclared_roles", "roles_in_dossiers", "roles_in_brief",
    "derive_general_roles", "observed_body_facts", "build_matchup_plan",
)
