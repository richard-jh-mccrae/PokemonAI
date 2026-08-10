"""Evolve DECIDER — ADR-0070 (grill: ADR-0070, #140).

    deploy(X) = max( this_turn(X), payoff_damage(X) x p_arrive(X) x p_survive(X) )
    value     = deploy(R) - deploy(B) + income_gain - income_loss

`max`, never a sum: both terms read ONE progress on ONE body (ADR-0069 §1). Because B and R build
toward the SAME line payoff, `payoff_damage` CANCELS in the difference — so the deploy delta is
driven purely by what evolving does to the two clocks.

No exposure term (refuted twice at source: evolving usually makes a body sturdier) and no doom
override — survival is a WEIGHTING inside the comparison, not a gate outside it. PRIZE-BLIND: the
race arrives once, in ADR-0069 §6's scalar. Pure over `EvolveInputs`; the Pilot reads the board.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ONE halving rule and ONE horizon, shared with the promote/retreat equation (ADR-0100 §4), so a
# re-tune on either cannot silently re-open the other.
from common.grading import HORIZON as _HORIZON
from common.grading import halve as _halve


@dataclass
class EvolveBody:
    """The damage-currency reading of ONE body — the pre-evolution B, or the result R it becomes.
    Every field is a measurement, never a tier."""
    #: Best damage reachable THIS turn under this body's own Attach Budget. Typed and sound.
    this_turn: float = 0.0
    #: The LINE PAYOFF's damage — the SAME number for B and R, which is why it cancels in the delta.
    payoff_damage: float = 0.0
    #: `turns_to_afford` — MAX of the energy deficit and the forward-hop depth, never the sum. 0 =
    #: armed now. None = unreadable, and the forward term then makes NO claim (ADR-0067).
    arm: int | None = None
    #: `turns_to_ko_me`, read at this body's AREA-AT-DAMAGE-TIME. Large = safe.
    ko: int = _HORIZON
    #: Canonical shared realization in damage currency. None preserves the legacy pure-call adapter.
    realization_damage: float | None = None

    def p_arrive(self) -> float:
        """P(the line arms) — the armed clock, halved per turn out. Fail-CLOSED at 0.0 on an
        unreadable clock: an unknown is worth nothing, never its optimistic reading."""
        return 0.0 if self.arm is None else _halve(self.arm)

    def p_survive(self) -> float:
        """P(the body lives to use the payoff) — the race between the two clocks, graded by the same
        halving once the KO clock catches up, so the boundary is continuous rather than a cliff."""
        if self.arm is None:
            return 0.0
        return 1.0 if self.arm < self.ko else _halve(self.arm - self.ko + 1)

    def deploy(self) -> float:
        """What having this body on the board is worth, in damage. `max` because the immediate and
        forward terms re-read ONE progress on ONE body (ADR-0069 §1)."""
        if self.realization_damage is not None:
            return max(0.0, float(self.realization_damage))
        return max(self.this_turn, self.payoff_damage * self.p_arrive() * self.p_survive())


@dataclass
class EvolveInputs:
    """The board facts an evolve option's value reads, so the equation stays a pure function."""
    body: EvolveBody = field(default_factory=EvolveBody)      # B — the pre-evolution, as it stands
    result: EvolveBody = field(default_factory=EvolveBody)    # R — the form it becomes

    # -- income: an ODDS read, never a tier (ADR-0070 §3) ---------------------------------------

    #: Δ`readiness_p` the RESULT's dig Ability buys. 0 on a body that already reaches, which is what
    #: makes a redundant engine worth nothing without a saturation rule.
    ready_gain: float = 0.0
    #: Δ`readiness_p` the BODY's Ability buys — the stream evolving forfeits.
    ready_loss: float = 0.0
    #: R's Ability is usable THIS turn, so the gain is undiscounted.
    result_ability_now: bool = False
    #: B's Ability is STILL on the menu. Read off the MENU, never inferred from an assumed ordering
    #: (ADR-0070 §7): fired first, evolving forfeits nothing this turn and the loss is purely future.
    body_ability_on_menu: bool = False
    #: B's Ability self-shuffles — a single burst, so there is no future stream to lose.
    body_ability_oneshot: bool = False
    #: Turns B would remain un-ready; 0 once armed, which collapses the hold to nothing.
    hold_turns: int = 0
    #: Direct shared readiness marginals; None keeps the legacy odds adapter for pure callers.
    income_gain_damage: float | None = None
    income_loss_damage: float | None = None


@dataclass
class EvolveValue:
    """The evolve value with its terms — the decider's legible working (ADR-0008/0019)."""
    deploy: float = 0.0
    income_gain: float = 0.0
    income_loss: float = 0.0
    total: float = 0.0


def evolve_value(inp: EvolveInputs) -> EvolveValue:
    """The value of an EVOLVE option, in damage (see module docstring)."""
    deploy = inp.result.deploy() - inp.body.deploy()

    # Income GAIN — immediate when R's Ability fires this turn, else one turn out.
    gain = (float(inp.income_gain_damage) if inp.income_gain_damage is not None
            else inp.result.payoff_damage * inp.ready_gain)
    if not inp.result_ability_now:
        gain *= _halve(1)

    # Income LOSS — a SPLIT horizon: this turn's use, forfeit only while still on the menu, plus the
    # future stream as the geometric sum of the halving (sum_{t=1..n} 2^-t == 1 - 2^-n).
    per_use = (float(inp.income_loss_damage) if inp.income_loss_damage is not None
               else inp.body.payoff_damage * inp.ready_loss)
    loss = per_use if inp.body_ability_on_menu else 0.0
    if not inp.body_ability_oneshot:
        loss += per_use * (1.0 - _halve(max(0, int(inp.hold_turns))))

    return EvolveValue(deploy=deploy, income_gain=gain, income_loss=loss,
                       total=deploy + gain - loss)
