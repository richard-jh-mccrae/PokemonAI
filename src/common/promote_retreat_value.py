"""Promote/retreat DECIDER — ADR-0073 (grill: issue #141, Phase 1c of the Value System).

The promote/retreat decision as ONE equation, in the DAMAGE currency #139 established (ADR-0069)
and #140 reused (ADR-0070), replacing eleven of the twelve `baseline_promote` / `baseline_retreat`
rungs. What it prices is the **Sub-lethal Residual**: what remains once the Knock-Outs available on
both sides of the swap have cancelled.

    promote_value(B) = my_yield(B) + closure(B) - exposure(B) + tempo_denied(B) - fatal(B)
    retreat_option   = max over bench B of promote_value(B)  +  preservation(A) - retreat_cost(A)
    pick_option(B)   = promote_value(B)

**One evaluator, three call sites** (ADR-0073 §9). The whether-to-retreat question at MAIN carries
the A-side terms; the body PICK at a SWITCH/TO_ACTIVE select does not, because `preservation(A)` and
`retreat_cost(A)` are CONSTANT across destinations and could change no ordering there. The forced
promote is `promote_value(B)` with no A-side terms at all. That the two sites run the same evaluator
is what makes the old divergence — retreat BECAUSE Cinderace is worth promoting, then promote Budew
— structurally impossible rather than merely fixed.

**The layers SUM; nothing recuses** (§1). Retreat and promote are a three-part decision (whether ·
why · who) and no single layer sees all of it, so each prices what it can on the SAME option: the
Knock-Out **delta** is the tactical lookahead's (`_retreat_to_lethal_tactical` /
`_promote_ko_tactical`), dependent step-chains are #165's, and this residual is the rest. The sum
cannot double-pay because the residual is strictly sub-lethal by construction — there is no win or
lethal input to pass, so a KO magnitude is unrepresentable here. The shipped `active_can_ko` recusal
is DELETED: a layer that cannot see a fact prices it 0, it does not withdraw and leave the option
unranked.

**One currency, at a DERIVED rate** (§3). The shipped equation spoke three units at once — band
constants, a `_PRIZE_UNIT = 12` prize unit and card Worth — and was internally incoherent (a ready
win-condition priced at 3.3 prizes). After §2 deleted `stay_forgone` the option competes head-on
with attack options priced in damage on the same `score`, so ADR-0070 decision 1 applies verbatim.
Every term is now damage, and the one exchange rate is :data:`PRIZE_DAMAGE_RATE`, DERIVED from the
card set rather than tuned.

A pure function over MEASUREMENTS — the Pilot reads the board into :class:`PromoteBody` /
:class:`RetreatSide` (ADR-0070's `EvolveBody` pattern verbatim: every field a measurement, never a
tier), so the equation makes no oracle calls, cannot reach for state it was not handed, and every
ADR-0073 ruling is assertable without constructing a board.

Card facts behind the worked frames, verified at source (`data/EN_Card_Data.csv`, `docs/rules.md`):
prize value is Mega ex **3**, ex **2**, else **1** (rules.md §6); a Retreat Cost slot is colourless,
so the discarded set is ours to choose (rulebook.txt L142, and the engine poses a `DISCARD_ENERGY`
select over every attached Energy — `cgpy/turn.py:_pose_retreat_energy`); a Tera body takes no
attack damage while Benched (rules.md §11), which the Bench Harvest already honours
(`combat._harvest_items`), so its bench leg reads the full horizon.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from common.grading import HORIZON, halve
from common.strategy.context import ENERGY_RECOVER, KO_SCORE

#: The **Prize Damage Rate** — damage per prize, the ONE exchange rate that lets prize Exposure be
#: denominated in the damage currency the attach and evolve marginals already speak.
#:
#: DERIVED, not tuned: the MEDIAN HP-per-prize over every body in the set — 1061 bodies in
#: `data/EN_Card_Data.csv` at the `docs/rules.md` §6 prize values, median **100.0** (mean 101.5; per
#: band 90 / 130 / 110). Recomputable and falsifiable, which is the whole point — a test recomputes
#: it from the CSV rather than pinning the literal, so a future set re-derives it instead of
#: inheriting it. The superseded `_PRIZE_UNIT = 12` asserted roughly an eighth of this, which is why
#: the shipped equation endorsed feeding a 3-prize body to save a 40-point band.
PRIZE_DAMAGE_RATE = 100.0


@dataclass
class PromoteBody:
    """The damage-currency reading of ONE body — a promote candidate B, or the Active A being
    retreated (both need the same measurements; only which terms are read differs).

    Filled by the Pilot from the StateModel snapshot (ADR-0068, so a memoized clock cannot shift
    under a hypothetical build); every field is a measurement, never a tier."""

    # -- my_yield: what B earns as the new Active (§3, §3a, §3b) --------------------------------
    #: Best damage this body can reach THIS turn under its OWN Attach Budget (#137) — typed and
    #: sound, so an attack whose colours are unpayable is not reachable. The `best_reachable_damage`
    #: read `_evolve_side` already makes, retiring the `_READY`/`_ACT`/`_BEST_BONUS` bands: which
    #: body is the better promote is now a damage fact, so f104's best-target fix is EMERGENT
    #: rather than a `+5` tie-break bonus.
    reach: float = 0.0
    #: ADR-0040's KO-Race per-turn wall progress (`hp / t_star`) when a standing wall means no
    #: affordable attack Knocks Out this turn — else None, and `reach` stands. §3a: "vs a standing
    #: wall the single hit is fake value — price the SEQUENCE". Drakloak's 70 into a 320 HP wall is
    #: a five-turn race; crediting face-value chip would lose the retreat-to-Budew frame.
    wall_progress: float | None = None
    #: Energy this body's accel rider would actually attach AND a recipient can actually USE — the
    #: `_recover_units` count, need-gated. §3b: the dividend re-anchors on `ENERGY_RECOVER`, because
    #: retreating INTO Cinderace must credit what attacking WITH Cinderace credits (the shipped
    #: `_DIVIDEND = 5` was ~45x short of the 75-per-Energy the SAME rider earns on the attack).
    accel_units: int = 0

    # -- closure: the probabilistic middle (§5) -------------------------------------------------
    #: `max` over attacks of ``damage(a) x [readiness_p(a | enabler) - readiness_p(a)]`` — the
    #: Δ`readiness_p` this turn's dig buys, the shape ADR-0070 decision 3 shipped. PER ATTACK
    #: (never `attack_id=None`, which asks the famine question across all attacks — right for a
    #: boolean, wrong for a magnitude), one Budget per target body, and the draw window is ZERO at a
    #: forced promote: the replacement Active is chosen right after the KO'ing attack resolves or at
    #: Checkup and attacking ends the turn, so NO play window remains (rulebook.txt L173-176/L183).
    #: `Δ <= 1` bounds this below `damage(a)` by construction, so "closure can never beat actually
    #: being ready" is structural rather than the shipped interim clamp.
    closure: float = 0.0

    # -- exposure / preservation: the prize side (§4) --------------------------------------------
    #: Prizes a Knock Out of this body yields — Mega ex 3, ex 2, else 1 (rules.md §6).
    prizes: int = 1
    #: `turns_to_ko_me` read at the ACTIVE area — the ADR-0071 decision-4 accumulating clock. This
    #: is where a promoted body ARRIVES, and where a retreating body currently STANDS.
    ko_active: int = HORIZON
    #: `turns_to_ko_me` read at the BENCH area, at the `HARVEST_UNAVOIDABLE` (RESCUE) reading — a
    #: benched knockout the opponent can simply redirect onto another body in range denies nothing,
    #: and crediting it would inflate every bench rescue (`_evolve_side`'s own argument). The 35
    #: bench-immune Tera bodies in this set read the full HORIZON here: benched, they can only be
    #: reached by a gust.
    ko_bench: int = HORIZON

    # -- tempo_denied: the Threat-Clock delta (§6) -----------------------------------------------
    #: ``incoming(t=2) - incoming(t=1)`` against my next Active — ONE development step's threat
    #: growth off the live Threat-Clock curve (whose `t` moves only the ENERGY budget, evolution
    #: reach being maximal at `t=1`, so the delta IS one step).
    tempo_step: float = 0.0
    #: This body item-locks AND the opponent PROVABLY still holds live Item copies. Fails CLOSED
    #: (no matched Read → no credit), because the term ENDORSES a play and ADR-0067's rule is
    #: fail-closed on yield. Both halves matter: `_STALL` and `_ITEM_LOCK_TEMPO` were previously set
    #: from ONE card feature through ONE gate, paying 32 points for one Budew.
    denies_items: bool = False

    # -- fatal: the endgame dominance band (§7a) --------------------------------------------------
    #: Prizes the opponent still needs. Knocking this body out ENDS the match when its own prize
    #: value covers that count.
    opp_prizes_remaining: int = 6
    #: This body itself takes a Knock Out on arrival — ruling 5's provable-KO stand-down, which
    #: keeps the fatal step from firing on a trade we are happy to make. The KO's own magnitude is
    #: NOT priced here; it is the tactical layer's, summed on the same option (§1, §11).
    takes_ko: bool = False

    # ---- the terms ------------------------------------------------------------------------------

    def my_yield(self) -> float:
        """What this body earns as the new Active — its real reachable damage, race-discounted
        against a standing wall, plus the accel dividend its rider banks.

        The two legs ADD rather than `max`: they are independent card features (an attack's damage
        and its accel rider), which is the same axes discipline ADR-0069 §1 applies to the attach
        marginal — `max` WITHIN an axis, sum ACROSS."""
        attack = self.reach if self.wall_progress is None else float(self.wall_progress)
        return max(0.0, attack) + ENERGY_RECOVER * max(0, int(self.accel_units))

    def exposure(self) -> float:
        """The prizes promoting this body HANDS the opponent — continuous, per-body and
        clock-graded, never the boolean cliff `opp_can_punish` was.

        Graded by the ACTIVE-area clock because that is the area a promoted body occupies. A body
        one point short of being killable does not price identically to one that dies next turn,
        and against an unrecognised opponent the clock still speaks, where the retired matched-Read
        boolean made every body pay full exposure."""
        return self.prizes * PRIZE_DAMAGE_RATE * halve(self.ko_active - 1)

    def preservation(self) -> float:
        """The prizes retreating this body SAVES — the difference between its exposure standing in
        the Active Spot and its exposure sitting on the Bench.

        The clock DIFFERENCE is the whole term, which is what makes the doomed-Mega-Starmie frame
        need no new machinery: retreating a doomed 3-prize attacker into a fresh copy of itself
        takes the identical Knock Out either way, so the KO cancels and the 3 prizes preserved ARE
        the decision. Floored at 0 — retreating cannot make a body's own prizes *more* exposed, and
        a bench clock that reads shorter than the Active one is a redirect artefact, not a cost of
        retreating."""
        return max(0.0, self.prizes * PRIZE_DAMAGE_RATE
                   * (halve(self.ko_active - 1) - halve(self.ko_bench - 1)))

    def tempo_denied(self) -> float:
        """The development step an Item lock denies the opponent, off the Threat-Clock curve.

        Stated honestly, this is the equation's one term that is not an identity: an Item lock
        denies ITEMS while the curve delta measures a WHOLE development step, so it is a CEILING.
        The over-credit direction is exactly the over-fire an earlier sweep measured, and the
        live-Items gate is what bounds it."""
        return max(0.0, float(self.tempo_step)) if self.denies_items else 0.0

    def fatal(self) -> float:
        """`KO_SCORE` when Knocking this body out would END the match and the clock says they can
        take it next turn — the constant that already means "dominates any sub-lethal quantity" on
        the positive side, used here on the negative one.

        A finite dominance BAND, not a veto: when every option is fatal the residual still orders
        them, which a veto cannot. Stands down on a Knock-Out trade (ruling 5) — trading while
        ahead on the exchange is fine.

        The escalation near their goal needs no separate `_NEAR_GOAL`/`_GOAL_BAND` weighting: the
        condition is `prizes >= opp_prizes_remaining`, so as their count falls progressively more
        of our bodies become fatal automatically (§7b — the effect is emergent, and modelling it
        twice would be two mechanisms for one thing)."""
        if self.takes_ko or self.ko_active > 1:
            return 0.0
        return KO_SCORE if self.prizes >= self.opp_prizes_remaining >= 2 else 0.0


@dataclass
class RetreatSide:
    """The A-side of a VOLUNTARY swap — the body leaving the Active Spot, and what leaving costs.

    Present only at the whether-to-retreat question; absent at a body pick (where these terms are
    constant across destinations) and at a forced promote (where nothing is being paid)."""

    #: A itself, for :meth:`PromoteBody.preservation`.
    body: PromoteBody = field(default_factory=PromoteBody)
    #: **Build Standing** of A as it stands — `(matched/slots)^2 x maxDamage` against its line
    #: payoff attack.
    build_before: float = 0.0
    #: Build Standing of A after the retreat discards its N Energy — the greedy cheapest-to-lose
    #: typed choice, retreat slots being colourless so the set is genuinely ours to pick.
    build_after: float = 0.0
    #: ADR-0069 §5c's resource premium on the discarded Energy — worth ABOVE a reusable Basic, so a
    #: plain Basic pays nothing and only a one-shot is charged.
    resource_premium: float = 0.0
    #: A switch-class ITEM pays a CARD and no Energy (§11's rider), so its cost is the card's Worth
    #: rather than a build delta. Mutually exclusive with the build legs in practice.
    card_worth: float = 0.0

    def retreat_cost(self) -> float:
        """The BUILD the discard destroys, plus the resource premium — the exact mirror of the
        attach decider (1a prices an attach as `+build`; a retreat pays `-build`), so the two
        cannot disagree about what an Energy is worth.

        Worked: Mega Starmie ex at 3/3 of Nebula Beam stands at `(3/3)^2 x 210 = 210`; after paying
        retreat 2 it stands at `(1/3)^2 x 210 = 23`, so the retreat costs **187 damage** of build —
        two turns of attaching thrown away, and exactly why "insanely retreat happy" opened this
        grill. A free-retreat body pays 0. Deliberately NOT refunded for discard-recursion decks:
        `_recover_units` already credits that recycling on the attack option, and discounting here
        would pay it twice."""
        return max(0.0, self.build_before - self.build_after) + \
            max(0.0, self.resource_premium) + max(0.0, self.card_worth)


@dataclass
class PromoteRetreatInputs:
    """The board facts a promote/retreat option's value reads, so the equation stays pure."""
    #: B — the body being brought to the Active Spot.
    body: PromoteBody = field(default_factory=PromoteBody)
    #: A — the body leaving it. None at a body PICK and at a forced promote (§9).
    retreat: RetreatSide | None = None


@dataclass
class PromoteRetreatValue:
    """The value with its inner terms — the decider's legible working (ADR-0008/0019), carried on
    the decision record as the per-option rows #146/#148 consume. ``total`` is the transparent net,
    so a wrong answer is diagnosable term by term rather than as one number."""
    my_yield: float = 0.0
    closure: float = 0.0
    exposure: float = 0.0
    tempo_denied: float = 0.0
    fatal: float = 0.0
    preservation: float = 0.0
    retreat_cost: float = 0.0
    total: float = 0.0


def promote_value(inp: PromoteRetreatInputs) -> PromoteRetreatValue:
    """The value of a promote/retreat option, in damage (see module docstring).

    ONE evaluator for all three sites: pass ``retreat=None`` for a body PICK or a forced promote,
    and a :class:`RetreatSide` for the whether-to-retreat question at MAIN."""
    b = inp.body
    my, clos = b.my_yield(), max(0.0, float(b.closure))
    expo, tempo, fatal = b.exposure(), b.tempo_denied(), b.fatal()

    # The A-side terms are constant across destinations, so they belong ONLY on the whether-site's
    # retreat option — at the pick site they could change no ordering (§9).
    preserved = inp.retreat.body.preservation() if inp.retreat is not None else 0.0
    cost = inp.retreat.retreat_cost() if inp.retreat is not None else 0.0

    total = my + clos - expo + tempo - fatal + preserved - cost
    return PromoteRetreatValue(my_yield=my, closure=clos, exposure=expo, tempo_denied=tempo,
                               fatal=fatal, preservation=preserved, retreat_cost=cost,
                               total=total)
