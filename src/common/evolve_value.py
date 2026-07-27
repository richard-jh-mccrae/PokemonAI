"""Evolve DECIDER — ADR-0070 (grill: docs/plans/evolve-valuation-grill-spec.md, #140).

The evolve decision as ONE equation, in the DAMAGE currency #139 established (ADR-0069), replacing
the `baseline_evolution.py` rung pile and the dragapult `hold-evolution` deck rung:

    deploy(X) = max( this_turn(X), payoff_damage(X) x p_arrive(X) x p_survive(X) )
    value     = deploy(R) - deploy(B) + income_gain - income_loss

`this_turn` is IMMEDIATE, typed and certain — the #137 reachability read of what the body can swing
for right now. The forward term is the LINE PAYOFF discounted twice: by **when the line arms**
(`turns_to_afford`, whose energy and forward-hop legs run in PARALLEL, never summed) and by
**whether the body survives to use it** (`turns_to_ko_me`). `max` between them because both read one
progress on one body (ADR-0069 §1) — a body is never paid twice for the same Energy.

Because a pre-evolution and its result build toward the SAME line payoff, `payoff_damage` cancels in
the difference: **the deploy delta is driven purely by what evolving does to the two clocks.** Which
is the whole claim — attaching and evolving run in parallel, so a hop is worth a turn only when hops
OUTNUMBER the energy turns owed, and worth nothing when they do not. The old flat
`_ATTACH_PREEVO_DISCOUNT` charged a 4x penalty either way; this measures it (ADR-0070 §2, §6).

Three doctrines that used to be rungs, now DERIVED — the Dragapult line makes them one arithmetic
fact, because Drakloak's Dragon Headbutt and Dragapult ex's Phantom Dive have the IDENTICAL {R}{P}
cost (verified at source):

  * **can pay {R}{P}** -> `this_turn` 70 vs 200, and the evolved form owes no hop -> evolve and swing.
  * **cannot pay it**  -> neither body attacks, both clocks read alike, deploy is ZERO, and the
    persistent Recon stream is the only term left -> hold and keep digging. `hold-evolution` DELETED.
  * **body armed**     -> the engine buys no readiness, `ready_loss` is 0, and the hold pressure
    vanishes on its own. Ruling 1's collapse, with no `turns_to_ready` gate.

There is no exposure term (refuted twice at source — evolving usually makes the body STURDIER) and
no doom override: "this body is about to die" is a statement about what its banked Energy is worth,
so it lives INSIDE the comparison as the survival weighting, not stapled outside it (ADR-0070 §4,
§5). The decider is PRIZE-BLIND: the race arrives once, in #145's scalar (ADR-0069 §6).

A pure function of its inputs — the Pilot reads the board into `EvolveInputs`, so the equation stays
testable at the seam and cannot reach for state it was not handed.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# The grading convention lives in `common.grading` now that the promote/retreat equation reads it
# too (ADR-0073 §4) — one halving rule and one horizon, so a re-tune on either equation cannot
# silently re-open the other. Aliased at module scope because this file's prose names them.
from common.grading import HORIZON as _HORIZON
from common.grading import halve as _halve


@dataclass
class EvolveBody:
    """The damage-currency reading of ONE body — the pre-evolution B, or the result R it becomes.

    Filled by the Pilot from the StateModel; every field is a measurement, never a tier."""
    #: Best damage this body can reach THIS turn under its own Attach Budget (#137). Typed and
    #: sound: an attack whose colours are unpayable is not reachable.
    this_turn: float = 0.0
    #: The LINE PAYOFF's damage — the attack this body's Energy is ultimately building toward. The
    #: same number for a pre-evolution and its result (both read `_line_payoff_stat`), which is why
    #: it cancels in the deploy difference.
    payoff_damage: float = 0.0
    #: `turns_to_afford` — the hop-aware armed clock: MAX of the energy deficit and the forward-hop
    #: depth, never the sum. 0 = armed now. None = unreadable, and the forward term then makes NO
    #: claim (fail-closed, ADR-0067).
    arm: int | None = None
    #: `turns_to_ko_me` — turns until the opponent's board can fell this body in one swing, read at
    #: its AREA-AT-DAMAGE-TIME (a benched body is reachable only by snipe/spread riders, and a Tera
    #: body not at all). Large = safe.
    ko: int = _HORIZON

    def p_arrive(self) -> float:
        """P(the line arms) — the armed clock, halved per turn out. Fail-CLOSED at 0.0 on an
        unreadable clock: an unknown is worth nothing, never its optimistic reading."""
        return 0.0 if self.arm is None else _halve(self.arm)

    def p_survive(self) -> float:
        """P(the body lives to use the payoff) — the race between the two clocks. Whole while it
        arms strictly before it can be felled; graded by the same halving once the KO clock catches
        up, so the boundary is continuous rather than a cliff."""
        if self.arm is None:
            return 0.0
        return 1.0 if self.arm < self.ko else _halve(self.arm - self.ko + 1)

    def deploy(self) -> float:
        """What having this body on the board is worth, in damage. `max` because the immediate and
        forward terms re-read ONE progress on ONE body (ADR-0069 §1)."""
        return max(self.this_turn, self.payoff_damage * self.p_arrive() * self.p_survive())


@dataclass
class EvolveInputs:
    """The board facts an evolve option's value reads, so the equation stays a pure function."""
    body: EvolveBody = field(default_factory=EvolveBody)      # B — the pre-evolution, as it stands
    result: EvolveBody = field(default_factory=EvolveBody)    # R — the form it becomes

    # -- income: an ODDS read, never a tier (ADR-0070 §3) ---------------------------------------
    #: Δ`readiness_p` the RESULT's draw/dig Ability buys — the exact hypergeometric that its dig
    #: depth finds the enabler the payoff still lacks. 0 on a body that already reaches, which is
    #: what makes a redundant engine worth exactly nothing without a saturation rule.
    ready_gain: float = 0.0
    #: Δ`readiness_p` the BODY's Ability buys — the stream evolving forfeits.
    ready_loss: float = 0.0
    #: R's Ability is usable THIS turn (evolve -> use it is one legal turn: Abilities fire "per the
    #: ability's own text", rules.md:91, and the engine re-presents the menu after each non-ending
    #: action). The gain is then undiscounted.
    result_ability_now: bool = False
    #: B's Ability is STILL on the menu — i.e. not yet used this turn. Read off the menu, never
    #: inferred from an assumed ordering: the sequencer usually fires it at tier 0 before the evolve,
    #: in which case evolving forfeits no use THIS turn and the loss is purely future (ADR-0070 §7).
    body_ability_on_menu: bool = False
    #: B's Ability self-shuffles (Run Away Draw) — a single deadline-0 burst rather than a stream, so
    #: there is no future to lose. The recycle card-fact splits the HORIZON, not the magnitude.
    body_ability_oneshot: bool = False
    #: Turns B would remain un-ready, i.e. how long a persistent engine would keep paying. Sourced
    #: from B's own armed clock; 0 once the body is armed, which collapses the hold to nothing.
    hold_turns: int = 0


@dataclass
class EvolveValue:
    """The evolve value with its terms — the decider's legible working (ADR-0008/0019), carried on
    the decision record as the per-option rows #146/#148 consume. ``total`` is the sum."""
    deploy: float = 0.0
    income_gain: float = 0.0
    income_loss: float = 0.0
    total: float = 0.0


def evolve_value(inp: EvolveInputs) -> EvolveValue:
    """The value of an EVOLVE option, in damage (see module docstring)."""
    deploy = inp.result.deploy() - inp.body.deploy()

    # Income GAIN — immediate when R's Ability fires this turn, else one turn out.
    gain = inp.result.payoff_damage * inp.ready_gain
    if not inp.result_ability_now:
        gain *= _halve(1)

    # Income LOSS — the SPLIT horizon. This turn's use is forfeit only while it is still on the menu;
    # the future stream is the geometric sum of the halving over the turns B would stay un-ready
    # (sum_{t=1..n} 2^-t == 1 - 2^-n), and a one-shot has no future to lose.
    per_use = inp.body.payoff_damage * inp.ready_loss
    loss = per_use if inp.body_ability_on_menu else 0.0
    if not inp.body_ability_oneshot:
        loss += per_use * (1.0 - _halve(max(0, int(inp.hold_turns))))

    return EvolveValue(deploy=deploy, income_gain=gain, income_loss=loss,
                       total=deploy + gain - loss)
