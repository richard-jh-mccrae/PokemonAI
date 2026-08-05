"""MatchupPlan — the unified opponent target-priority spine (ADR-0051).

Assigns every opponent body one ``(role, priority)``, so a single object answers "who do I
target / who do I leave alone" for the snipe and gust decisions (and, later, proactive plays).
The role is composed from tiers of decreasing generality:

  * **general** card-fact (matchup-AGNOSTIC, always applies): what is true of a card in *every*
    deck, derived by :func:`derive_general_roles` from facts the Pilot supplies (γ-independent).
  * **matchup** (γ-gated): the curated Matchup Brief (matchup-genie) and, below it, the Read's
    own probabilistic Intel — precise when recognized, silent when not.

**The sheet is an ORDINAL PRIORITY, not a worth** (Issue #395 D1), and that was forced rather than
chosen: `tests/strategy/test_needs.py` asserts every `card_worth.ROLE_TIER` role names a slot kind it
can supply, and every `needs.SLOT_KINDS` member is a hand-or-board need **of ours**. An opponent role
in that table turns CI red with no honest slot to name. Two independent supports: the two
vocabularies already collide on the word `engine` (`ROLE_TIER` 12.0, *a plan piece worth keeping*,
against :data:`ROLE_REGISTRY`'s 0, *neutral, do not boost*), so reusing either as the other's sheet
would make that disagreement silent; and Issue #398 measured that at this seam the ordering is
decided by WHICH bodies carry a signal rather than by how much (an arm carrying ~20× another's
magnitude bought 1.26× the movement). Nothing here enters the prize-denominated
`needs.opponent_target_value` currency, and `needs.TARGET_VALUE_CEILING` with the two rates derived
from it are untouched.

**The vocabulary is CLOSED** (Issue #395 D2). It was not, and the cost was measured: the shipped
`artifact.json` assigns `attacker` to **530** opponent bodies — the largest role population in the
artifact — and `attacker` was not in the consumed table, so every one of them resolved to 0 through
`_ROLE_PRIORITY.get(role or "", 0)` with no error, no log and no test. `Scout._target_role` emitted
two more (`support`, `unknown`) that were equally absent. :func:`undeclared_roles` is the teeth and
:func:`roles_in_dossiers` / :func:`roles_in_brief` are the walks, paired with it by
`tests/scouting/test_scouting_matchup_plan.py` over the REAL shipped artifacts — the walks live here
rather than in the test for the reason `snapshot_coverage` states one store over: *a vocabulary the
audit forgets to visit is an audit that passes by not looking.*

Pure and lib-free (mirrors ``briefs.py``): the Pilot resolves the raw inputs (card facts →
:class:`BodyFacts`, ``resolve_brief_cards`` → Brief roles, ``Read.targets`` → Intel roles) and the
consumers read :meth:`MatchupPlan.priority`. It never acts. See docs/adr/0051.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

# Provenance of a role assignment — decides whether the Read confidence scales it.
_GENERAL = "general"     # a card fact: true in every matchup, applies at γ=0
_MATCHUP = "matchup"     # a Read/Brief claim: only as strong as the recognition (× γ)
PROVENANCES = (_GENERAL, _MATCHUP)


@dataclass(frozen=True)
class Role:
    """One legal opponent role: its ordinal priority, why it sits there, and which provenance tiers
    are allowed to assign it.

    ``tiers`` is a claim about the shipped stores, and
    `tests/scouting/test_scouting_matchup_plan.py` checks it against them — a role only a curated
    human may assert (`disruption_target`) must not appear in a derivation, and a role only a
    derivation produces must not appear in a hand-authored Brief."""

    priority: int
    reason: str
    tiers: tuple[str, ...]


#: **The closed role vocabulary** — role -> ordinal priority. Positive = target sooner, negative =
#: leave alone. Magnitudes sit ABOVE the generic snipe/gust rungs (~20-60) but well BELOW KO_SCORE,
#: so this steers WHICH non-KO target to hit — never over a real Knock Out.
#:
#: The ORDER is the load-bearing part (D1's ordinal finding); the magnitudes are authored and a
#: measurement may re-rule them without re-ruling the order.
ROLE_REGISTRY: dict[str, Role] = {
    "prize_liability": Role(
        100, "the wincon body itself — KO/gust it", (_GENERAL, _MATCHUP)),
    "fragile_preevo": Role(
        90, "its pre-evolution — deny the wincon before it comes online", (_GENERAL, _MATCHUP)),
    "disruption_target": Role(
        60, "their key supporter/enabler the Brief says to REMOVE (the 'hunt an engine' role). "
            "Curated ONLY: an explicit human claim about this matchup outranks a derived one, and "
            "nothing derives it — that is what the role means.", (_MATCHUP,)),
    "attacker": Role(
        50, "a body whose line actually attacks. **530 shipped assignments resolved to 0 before "
            "Issue #395** — the largest role population in the artifact, inert. Sits BELOW the "
            "wincon and its pre-evo deliberately: a body that attacks is a real steer but not "
            "automatically a better removal target than the wincon itself. The worked example is "
            "Crustle, which is the Crustle / Mega Kangaskhan ex deck's main attacker *because* it "
            "cannot be damaged by an ex attacker in an ex-dominated format.",
        (_GENERAL, _MATCHUP)),
    "enabler": Role(
        40, "a body that assists the key Pokémon in HOW it attacks — damage boosts, a free-retreat "
            "grant, ability fuel (the Solrock/Lunatone shape). Below `attacker` because removing "
            "the attacker is the more direct answer. Needs no new Function Tag: every input is "
            "already a parsed `CardStat` field.", (_GENERAL, _MATCHUP)),
    "engine": Role(
        0, "a plain accelerant/enabler (Cinderace class) — NEUTRAL: a poor snipe target, so do not "
           "boost it. `disruption_target` is how a Brief opts one in, and `avoid` is how the "
           "general tier de-prioritizes the 1-prize utility class.", (_GENERAL, _MATCHUP)),
    "support": Role(
        0, "emitted by `Scout._target_role` for an in-play body with no printed damage. No claim — "
           "but it must be DECLARED or the vocabulary lint fails, which is the whole point of a "
           "closed vocabulary: silence is a ruling, not an omission.", (_MATCHUP,)),
    "unknown": Role(
        0, "emitted by `Scout._target_role` when there is no CardStat at all, and by "
           "`Scout._dossier_intel` for a dossier entry with no role. Same reading as `support`.",
        (_MATCHUP,)),
    "avoid": Role(
        -80, "decoy / self-shuffler — never spend removal here. **Gated on `prize_value == 1`** "
             "(D4): a 1-prize utility body (Dudunsparce / Budew class) is a poor place to spend "
             "removal, but a 2- or 3-prize engine is a PRIME one and the prizes are the reason. "
             "Before the gate this fired on Mega Kangaskhan ex (3 prizes) and Fezandipiti ex (2), "
             "unscaled by γ and written AFTER Read-Intel, so it overwrote the `prize_liability` the "
             "dossier had correctly assigned.", (_GENERAL, _MATCHUP)),
}

#: Role -> base priority. Kept as a name because `sound_rules.py`'s `firing-equation-constants`
#: whitelist names it: these are authored magnitudes inside an equation whose shape is right.
#: DERIVED from :data:`ROLE_REGISTRY` rather than written twice — a second table is the drift
#: `undeclared_roles` exists to prevent.
_ROLE_PRIORITY: dict[str, int] = {name: r.priority for name, r in ROLE_REGISTRY.items()}


def role_priority(role: str | None) -> int:
    """Base priority for a role name; 0 for an unroled / unknown body (falls through to the
    Pilot's generic threat rank).

    Still `.get(..., 0)`, and that is now SAFE rather than silent: an undeclared role cannot reach
    here without :func:`undeclared_roles` going red over the shipped artifacts first. The fallback
    is for a body with NO role, which is a real state; it is no longer also the fallback for a role
    the table forgot."""
    return _ROLE_PRIORITY.get(role or "", 0)


def undeclared_roles(roles: Sequence[str]) -> list[str]:
    """Role strings with no :data:`ROLE_REGISTRY` entry. Empty is the contract.

    **The teeth.** `attacker` sat outside the table across 530 shipped assignments and resolved to 0
    in silence; this is what makes the next such string fail loudly instead. Takes the values rather
    than an artifact so it can be bitten by a fabricated one — pair it with :func:`roles_in_dossiers`
    and :func:`roles_in_brief` to walk the real stores."""
    return sorted(r for r in set(roles) if r not in ROLE_REGISTRY)


def roles_in_dossiers(dossiers: Mapping) -> list[str]:
    """Every role string in a scouting artifact's ``dossiers`` block, sorted.

    Walks the shipped artifact rather than a hand-kept list, because *a hand-kept list is precisely
    what a new role string would not be added to*. Takes the already-parsed block so this module
    stays lib-free and the walk stays bitable by a fabricated payload."""
    out: set[str] = set()
    for sections in (dossiers or {}).values():
        for entries in (sections or {}).values():
            if not isinstance(entries, list):
                continue                       # `card_inclusion` and friends are not role-bearing
            out.update(e["role"] for e in entries
                       if isinstance(e, dict) and isinstance(e.get("role"), str) and e["role"])
    return sorted(out)


def roles_in_brief(brief: Mapping) -> list[str]:
    """Every role string in ONE curated Matchup Brief payload, sorted.

    The Brief's own `brief.schema.json` declares a role enum and **nothing in `src/` or `tests/`
    loaded it**, while `.claude/skills/matchup-genie/scripts/validate_brief.py` enforces it and has
    no automated caller — so a hand-edited Brief with a typo'd role shipped green. This walk is what
    the test pairs with :func:`undeclared_roles` to close that."""
    out: set[str] = set()
    for entry in (brief or {}).get("targets") or ():
        role = (entry or {}).get("role") if isinstance(entry, dict) else None
        if isinstance(role, str) and role:
            out.add(role)
    return sorted(out)


@dataclass(frozen=True)
class BodyFacts:
    """The deck-agnostic card facts :func:`derive_general_roles` reads about ONE opponent body.

    A record rather than a bag of kwargs, and supplied by the Pilot rather than looked up here: this
    module is pure, and `build_matchup_plan`'s existing contract is already *"the Pilot supplies the
    facts"*. Making the derivation pure is also what keeps the `avoid` prize gate testable at the
    scouting seam instead of stranding it at the Pilot level."""

    tags: frozenset = frozenset()
    prize_value: int = 1


def derive_general_roles(facts: Mapping[int, BodyFacts]) -> dict[int, str]:
    """``{card id: role}`` for the **general**, γ-independent tier — what is true of these cards in
    every deck.

    Today one rule, and it is the one Issue #395 D4 corrects. A body carrying the `draw` Function
    Tag is `avoid` **only when it is worth one prize**. The gate is read off `prize_value`, which
    `CombatMath.prize_value` already ships, so no new constant is authored.

    Why the gate is the fix rather than a refinement: the ungated rule fired on Mega Kangaskhan ex
    (300 HP, 3 prizes) and Fezandipiti ex (210 HP, 2 prizes) exactly as it fired on Dudunsparce
    (140 HP, 1 prize), its `_GENERAL` provenance meant it applied at FULL strength against an
    opponent we had not recognised, and `build_matchup_plan` writes it after Read-Intel so it
    overwrote the `prize_liability` the dossier had already assigned. The developer's ruling is that
    prize math stays in the equation: *"if they have a wall and draw engine like Mega Kangaskhan,
    and we can KO it, that's 3 prize cards"*, and the Dragapult line — chip Fezandipiti ex to 200,
    gust it next turn for the KO and the match — was being steered against by a rule written for the
    Dudunsparce/Budew class."""
    out: dict[int, str] = {}
    for cid, f in (facts or {}).items():
        if "draw" in (f.tags or ()) and f.prize_value == 1:
            out[cid] = "avoid"
    return out


@dataclass(frozen=True)
class _Assignment:
    role: str
    provenance: str      # _GENERAL | _MATCHUP


@dataclass
class MatchupPlan:
    """Per-opponent-body target priority (ADR-0051). ``assignments`` maps a body's card id to
    its resolved ``(role, provenance)``; ``gamma`` is the Read confidence that scales the
    matchup tier (the general card-fact tier is γ-independent)."""
    assignments: dict[int, _Assignment] = field(default_factory=dict)
    gamma: float = 0.0

    def role(self, body_id: int | None) -> str | None:
        """The resolved role for ``body_id`` (None if unroled / unknown)."""
        a = self.assignments.get(body_id) if body_id is not None else None
        return a.role if a else None

    def priority(self, body_id: int | None) -> float:
        """Target priority for ``body_id`` — higher = target sooner, negative = avoid, 0 =
        unroled. A general card fact applies in full (γ-independent); a matchup claim is scaled
        by the Read confidence, so it fades to silent against an unrecognized opponent."""
        a = self.assignments.get(body_id) if body_id is not None else None
        if a is None:
            return 0.0
        base = float(role_priority(a.role))
        return base if a.provenance == _GENERAL else base * self.gamma


def build_matchup_plan(*, brief_roles: dict[int, str] | None = None,
                       read_roles: dict[int, str] | None = None,
                       general_roles: dict[int, str] | None = None,
                       gamma: float = 0.0) -> MatchupPlan:
    """Compose a :class:`MatchupPlan` from its tiers, most-general first so the more specific
    tier overwrites per body (last write wins):

      1. **Read-Intel** (``read_roles``, matchup): the Read's observed/dossier roles — weakest.
      2. **general** card-fact (``general_roles``, from :func:`derive_general_roles`) — the
         deck-agnostic truth, applied at any confidence.
      3. **curated Brief** (``brief_roles``, matchup): the hand-authored intent — most specific.

    ``read_roles`` come from ``Read.targets`` Intel and ``brief_roles`` from ``resolve_brief_cards``.
    ``general_roles`` replaced the old ``draw_engine_ids`` id-set (Issue #395 D4/D5): the tier now
    carries a ROLE per body rather than one hard-coded `avoid`, which is what lets the derivation
    both gate `avoid` on prize value and, later, name the other deck-agnostic roles. Pure — the
    Pilot resolves the facts; the plan composes and scales."""
    assignments: dict[int, _Assignment] = {}
    for cid, role in (read_roles or {}).items():
        assignments[cid] = _Assignment(role, _MATCHUP)
    for cid, role in (general_roles or {}).items():        # general card fact overrides Read-Intel
        assignments[cid] = _Assignment(role, _GENERAL)
    for cid, role in (brief_roles or {}).items():          # curated Brief overrides all
        assignments[cid] = _Assignment(role, _MATCHUP)
    return MatchupPlan(assignments=assignments, gamma=gamma)


__all__: Sequence[str] = (
    "Role", "ROLE_REGISTRY", "PROVENANCES", "BodyFacts", "MatchupPlan",
    "role_priority", "undeclared_roles", "roles_in_dossiers", "roles_in_brief",
    "derive_general_roles", "build_matchup_plan",
)
