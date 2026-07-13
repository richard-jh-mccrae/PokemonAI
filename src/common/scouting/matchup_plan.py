"""MatchupPlan — the unified opponent target-priority spine (ADR-0051).

Assigns every opponent body one ``(role, priority)``, so a single object answers "who do I
target / who do I leave alone" for the snipe and gust decisions (and, later, proactive plays).
The role is composed from tiers of decreasing generality:

  * **general** card-fact (Function Tags — matchup-AGNOSTIC, always applies): a draw ENGINE
    (Dudunsparce / Budew class) is a poor target in *every* deck, so this tier de-prioritizes it
    with NO Read required (γ-independent).
  * **matchup** (γ-gated): the curated Matchup Brief (matchup-genie) and, below it, the Read's
    own probabilistic Intel — precise when recognized, silent when not.

Pure and lib-free (mirrors ``briefs.py``): the Pilot resolves the raw inputs (its Function Tags
→ draw-engine ids, ``resolve_brief_cards`` → Brief roles, ``Read.targets`` → Intel roles) and the
consumers read :meth:`MatchupPlan.priority`. It never acts. See docs/adr/0051.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Canonical role -> base priority (ADR-0051 seed; ladder-tuned). Positive = target sooner,
# negative = leave alone. Magnitudes sit ABOVE the generic snipe/gust rungs (~20-60) but well
# BELOW KO_SCORE, so this steers WHICH non-KO target to hit — never over a real Knock Out.
_ROLE_PRIORITY: dict[str, int] = {
    "prize_liability": 100,     # the wincon body itself — KO/gust it
    "fragile_preevo": 90,       # its pre-evolution — deny the wincon before it comes online
    "disruption_target": 60,    # their key supporter/enabler the Brief says to REMOVE (the "hunt an
                                # engine" role — explicit and curated, not inferred)
    "engine": 0,                # a plain accelerant/enabler (Cinderace / Solrock class) — NEUTRAL: a
                                # poor snipe target, so don't boost it; `disruption_target` is how a
                                # Brief opts one in, and the general `draw` tier avoids draw engines
    "avoid": -80,               # decoy / self-shuffler — never spend removal here
}


def role_priority(role: str | None) -> int:
    """Base priority for a role name; 0 for an unroled / unknown body (falls through to the
    Pilot's generic threat rank)."""
    return _ROLE_PRIORITY.get(role or "", 0)


# Provenance of a role assignment — decides whether the Read confidence scales it.
_GENERAL = "general"     # a card fact (draw engine): true in every matchup, applies at γ=0
_MATCHUP = "matchup"     # a Read/Brief claim: only as strong as the recognition (× γ)


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
                       draw_engine_ids=None, gamma: float = 0.0) -> MatchupPlan:
    """Compose a :class:`MatchupPlan` from its tiers, most-general first so the more specific
    tier overwrites per body (last write wins):

      1. **Read-Intel** (``read_roles``, matchup): the Read's observed/dossier roles — weakest.
      2. **general** card-fact (``draw_engine_ids``): a draw ENGINE is ``avoid`` in every deck.
      3. **curated Brief** (``brief_roles``, matchup): the hand-authored intent — most specific.

    ``read_roles`` come from ``Read.targets`` Intel, ``brief_roles`` from ``resolve_brief_cards``,
    and ``draw_engine_ids`` from the Pilot's Function Tags (the ``draw`` tag). Pure — the Pilot
    resolves these; the plan just composes and scales them."""
    assignments: dict[int, _Assignment] = {}
    for cid, role in (read_roles or {}).items():
        assignments[cid] = _Assignment(role, _MATCHUP)
    for cid in (draw_engine_ids or ()):                    # general card fact overrides Read-Intel
        assignments[cid] = _Assignment("avoid", _GENERAL)
    for cid, role in (brief_roles or {}).items():          # curated Brief overrides all
        assignments[cid] = _Assignment(role, _MATCHUP)
    return MatchupPlan(assignments=assignments, gamma=gamma)
