"""Promote/retreat DECIDER (ADR-0100): the damage-currency **Sub-lethal Residual** beside the
shared exact post-board position projection.

    promote_value(B) = my_yield(B) + closure(B) + tempo_denied(B) - fatal(B) - resource_cost(A)
    pick_option(B)   = promote_value(B)

ONE evaluator serves pick and whether sites. Body position belongs to the shared projection; this
residual owns immediate yield, closure, denied tempo, fatality, and non-position resource cost.

Pure over measurements: the Pilot fills :class:`PromoteBody` / :class:`RetreatSide`; this equation
makes no oracle calls, so each ruling remains testable without constructing a board.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from common.currency import PRIZE_DAMAGE_RATE as _PRIZE_DAMAGE_RATE
from common.grading import HORIZON
from common.strategy.context import ENERGY_RECOVER, KO_SCORE

#: Re-exported from `common.currency`, which owns the derivation and its recomputing test (ADR-0078).
PRIZE_DAMAGE_RATE = _PRIZE_DAMAGE_RATE


@dataclass
class PromoteBody:
    """The damage-currency reading of ONE body — a promote candidate B, or the Active A being
    retreated. Filled by the Pilot from the StateModel snapshot; every field a measurement."""

    # -- my_yield: what B earns as the new Active (§3, §3a, §3b) --------------------------------
    #: Best damage reachable THIS turn under its OWN Attach Budget — typed, so unpayable colours out.
    reach: float = 0.0
    #: ADR-0040 KO-Race per-turn wall progress (`hp / t_star`) when no affordable attack KOs this
    #: turn — else None, and `reach` stands. Vs a standing wall the single hit is fake value.
    wall_progress: float | None = None
    #: Energy this body's accel rider would attach AND a recipient can USE (`_recover_units`).
    #: FRACTIONAL — an EXPECTED count (ADR-0077); `my_yield` must not `int()` it.
    accel_units: float = 0.0
    #: Canonical exhaustive build marginal in damage. None preserves legacy pure callers.
    accel_value: float | None = None

    # -- closure: the probabilistic middle (§5) -------------------------------------------------
    #: PER-ATTACK ``max`` of ``damage(a) x Δreadiness_p``; the draw window is ZERO at a forced promote.
    closure: float = 0.0

    # -- exposure / preservation: the prize side (§4) --------------------------------------------
    #: Prizes a Knock Out of this body yields — Mega ex 3, ex 2, else 1 (rules.md §6).
    prizes: int = 1
    #: `turns_to_ko_me` at the ACTIVE area — where a promoted body ARRIVES and a retreating one STANDS.
    ko_active: int = HORIZON

    # -- tempo_denied: the Threat-Clock delta (§6) -----------------------------------------------
    #: ``incoming(t=2) - incoming(t=1)`` — ONE development step's threat growth off the live curve.
    tempo_step: float = 0.0
    #: This body item-locks AND the opponent PROVABLY still holds live Item copies. Fails CLOSED (no
    #: matched Read -> no credit): the term ENDORSES a play, and ADR-0067 is fail-closed on yield.
    denies_items: bool = False

    # -- fatal: the endgame dominance band (§7a) --------------------------------------------------
    #: Prizes the opponent still needs.
    opp_prizes_remaining: int = 6
    #: This body takes a Knock Out on arrival — ruling 5's stand-down, so `fatal` does not fire on a
    #: trade we are happy to make. The KO's own magnitude is the tactical layer's (§1, §11).
    takes_ko: bool = False

    # ---- the terms ------------------------------------------------------------------------------

    def my_yield(self) -> float:
        """The two legs ADD rather than `max`: independent card features, so `max` WITHIN an axis
        and sum ACROSS (ADR-0069 §1)."""
        attack = self.reach if self.wall_progress is None else float(self.wall_progress)
        accel = (ENERGY_RECOVER * max(0.0, float(self.accel_units))
                 if self.accel_value is None else max(0.0, float(self.accel_value)))
        return max(0.0, attack) + accel

    def tempo_denied(self) -> float:
        """A CEILING, not an identity: the lock denies ITEMS while the curve delta measures a WHOLE
        development step. The live-Items gate is what bounds the over-credit."""
        return max(0.0, float(self.tempo_step)) if self.denies_items else 0.0

    def fatal(self) -> float:
        """A finite dominance BAND, not a veto: when every option is fatal the residual still orders
        them. The near-goal escalation is EMERGENT from `prizes >= opp_prizes_remaining` (§7b)."""
        if self.takes_ko or self.ko_active > 1:
            return 0.0
        return KO_SCORE if self.prizes >= self.opp_prizes_remaining >= 2 else 0.0


@dataclass
class RetreatSide:
    """Stable Pilot/equation wire for non-position costs of leaving Active."""

    #: ADR-0069 §5c resource premium: worth ABOVE a reusable Basic, so only a one-shot is charged.
    resource_premium: float = 0.0
    #: A switch-class ITEM pays a CARD and no Energy (§11).
    card_worth: float = 0.0

    def retreat_cost(self) -> float:
        """Only non-position resource cost; destroyed build is already present in the post-board."""
        return max(0.0, self.resource_premium) + max(0.0, self.card_worth)


@dataclass
class PromoteRetreatInputs:
    """The board facts a promote/retreat option's value reads, so the equation stays pure."""
    #: B — the body being brought to the Active Spot.
    body: PromoteBody = field(default_factory=PromoteBody)
    #: Non-position resource cost; None at a body PICK and at a forced promote (§9).
    retreat: RetreatSide | None = None


@dataclass
class PromoteRetreatValue:
    """The value with its inner terms — the decider's legible working, so a wrong answer is
    diagnosable term by term rather than as one number."""
    my_yield: float = 0.0
    closure: float = 0.0
    # Stable working-schema fields. Position owns them, so this residual always reports zero.
    exposure: float = 0.0
    tempo_denied: float = 0.0
    fatal: float = 0.0
    preservation: float = 0.0
    retreat_cost: float = 0.0
    total: float = 0.0


def promote_value(inp: PromoteRetreatInputs) -> PromoteRetreatValue:
    """Pure specialized residual; exposure/preservation remain zero wire fields owned by position."""
    b = inp.body
    my, clos = b.my_yield(), max(0.0, float(b.closure))
    tempo, fatal = b.tempo_denied(), b.fatal()

    cost = inp.retreat.retreat_cost() if inp.retreat is not None else 0.0

    total = my + clos + tempo - fatal - cost
    return PromoteRetreatValue(my_yield=my, closure=clos, exposure=0.0, tempo_denied=tempo,
                               fatal=fatal, preservation=0.0, retreat_cost=cost,
                               total=total)
