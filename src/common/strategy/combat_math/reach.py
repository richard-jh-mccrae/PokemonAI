"""Affordability: what this body can do with what it holds, and with what it could still reach.

The pair is a counterfactual — 'right now' against 'under the full Budget' — and the difference
between them is exactly what an enabler play buys."""
from __future__ import annotations


from common.deck_odds import draw_hit_probability
from common.strategy.combat_math.budget import Budget, _can_pay
from common.strategy.context import KO_SCORE


# Tactical scalars owned by the oracle (ADR-0052) — used solely by closed-form combat valuation.
_EFFICIENCY = 0.1          # per-Energy tiebreak, far below prize granularity (1) so it never overrides it


class ReachMixin:
    """What a body can knock out, damage or afford."""

    def can_ko_cheapest(self, my_stat, defender: dict | None) -> bool:
        """The attacker's CHEAPEST attack would Knock Out ``defender`` this turn. Fail-closed — the
        card-level ``minCostDamage`` fallback is RETIRED (ADR-0052): no record, no claim."""
        hp = (defender or {}).get("hp", 0)
        if not (my_stat and hp):
            return False
        cheap = [aid for aid in (my_stat.attacks or ())
                 if self.attack_cost(aid, None) == my_stat.minAttackCost
                 and self.attack_stat(aid) is not None]
        return any(self.predicted_damage(my_stat.cardId, aid, defender) >= hp for aid in cheap)

    def can_ko_affordable(self, attacker: dict | None, defender: dict | None) -> bool:
        """The attacker's best CURRENTLY AFFORDABLE attack KOs ``defender`` this turn — every affordable
        attack is scanned, so a big non-cheapest KO is seen. Fail-closed."""
        if not (attacker and defender):
            return False
        stat = self._card_stat(attacker.get("id"))
        hp = defender.get("hp", 0)
        if not (stat and hp):
            return False
        energy = len(attacker.get("energies") or [])
        return any(self.predicted_damage(attacker.get("id"), aid, defender) >= hp
                   for aid in (stat.attacks or ()) if self.attack_cost(aid) <= energy)

    def can_damage(self, attacker: dict | None, defender: dict | None) -> bool:
        """The attacker, with its CURRENT Energy, has an affordable attack dealing >0 damage to
        ``defender``. A conditional attack that computes to 0 is NO threat. Fail-closed."""
        if not (attacker and defender):
            return False
        stat = self._card_stat(attacker.get("id"))
        if not (stat and defender.get("hp")):
            return False
        energy = len(attacker.get("energies") or [])
        return any(self.predicted_damage(attacker.get("id"), aid, defender) > 0
                   for aid in (stat.attacks or ()) if self.attack_cost(aid) <= energy)

    def maxed_kos(self, attacker: dict | None, defender: dict | None) -> bool:
        """The attacker's BIGGEST-damage attack, fully powered and IGNORING current Energy, would KO
        ``defender``. False ⇒ un-KO-able this turn even maxed, so a one-shot burst buys no KO."""
        if not (attacker and defender):
            return False
        stat = self._card_stat(attacker.get("id"))
        hp = defender.get("hp", 0)
        if not (stat and hp and stat.attacks):
            return False
        best_aid = max(stat.attacks, key=self.attack_damage)    # biggest printed attack
        return self.predicted_damage(attacker.get("id"), best_aid, defender) >= hp

    def best_reachable_damage(self, my_body: dict | None, *, budget: Budget) -> float:
        """The biggest PRINTED damage among the attacks ``my_body`` can reach this turn under ``budget``
        (ADR-0069 §2). ANY reachable attack, not the biggest it might someday afford. Fail-CLOSED at 0.0."""
        stat = self._card_stat((my_body or {}).get("id"))
        if stat is None or budget is None:
            return 0.0
        return float(max((self.attack_damage(aid) for aid in (stat.attacks or ())
                          if self.reachable_attach(my_body, aid, budget=budget)), default=0))

    def best_reachable_damage_vs(self, my_body: dict | None, defender: dict | None, *,
                                 budget: Budget, context: dict | None = None) -> float:
        """Biggest damage ``my_body`` can reach this turn AGAINST ``defender`` — :meth:`best_reachable_damage`
        read through the damage oracle, so W/R and prevention apply (Issue #281). A SIBLING, not a replacement."""
        stat = self._card_stat((my_body or {}).get("id"))
        if stat is None or budget is None:
            return 0.0
        return float(max((self.predicted_damage((my_body or {}).get("id"), aid, defender,
                                                context=context)
                          for aid in (stat.attacks or ())
                          if self.reachable_attach(my_body, aid, budget=budget)), default=0))

    def best_reachable_bench_damage(self, my_body: dict | None, defender: dict | None, *,
                                    budget: Budget) -> float:
        """Biggest damage ``my_body`` can put on ONE opponent BENCHED body (Issue #284). Reads
        :meth:`rider_snipe`, not :meth:`_bench_rider` — a spread SHARES budget; no attack prints both (1556 swept)."""
        stat = self._card_stat((my_body or {}).get("id"))
        if stat is None or budget is None:
            return 0.0
        target_id = (defender or {}).get("id")
        if self._card_stat(target_id) is None or self.is_tera(target_id):
            return 0.0                                # unreadable, or immune while Benched (§11)
        return float(max((self.rider_snipe(aid) for aid in (stat.attacks or ())
                          if self.reachable_attach(my_body, aid, budget=budget)), default=0))

    def readiness_p(self, my_body: dict | None, attack_id=None, *, budget: Budget,
                    enabler_budget: Budget | None = None,
                    copies: int = 0, pool: int = 0, draws: int = 0, p_by_type=None) -> float:
        """P(``my_body`` is READY to use the attack this turn) — the EV variant of :meth:`reachable_attach`.
        Fail-CLOSED at 0.0: no enabler modelled, or one that still would not pay, is worth nothing."""
        now = self.reachable_attach_p(my_body, attack_id, budget=budget, p_by_type=p_by_type)
        if now >= 1.0:
            return 1.0
        if enabler_budget is None:
            return now
        via = self.reachable_attach_p(my_body, attack_id, budget=enabler_budget,
                                      p_by_type=p_by_type)
        if via <= 0.0:
            return now                             # no enabler pays -> only what I already hold
        return max(now, via * draw_hit_probability(copies, pool, draws))

    def attack_realising_p(self, attack_id, *, budget, body=None, p_by_type=None) -> float:
        """P(``budget`` plus ``body``'s attached Energy really pays ``attack_id``) — ADR-0074. 1.0 with no
        probability map and 1.0 for an unresolvable cost: no claim must not manufacture a discount."""
        if not p_by_type:
            return 1.0
        slots = self._attack_slots(attack_id)
        if not slots:
            return 1.0
        return budget.realising_p(slots, p_by_type, attached=self._attached_units(body))

    def best_affordable_ko_value(self, opp: dict, attacker_id: int | None, energy: int, *,
                                 opp_bench=(), bound: str = "exact", body: dict | None = None,
                                 extra_type=None, extra_units: int = 0,
                                 boost_amount: int = 0, boost_type=None,
                                 promote_bench_names=None, attack_p=None,
                                 budget: Budget | None = None) -> float:
        """Best KO value ``attacker_id`` reaches against the opponent's Active — KO_SCORE + prize −
        efficiency + rider. ``budget`` (ADR-0075) is authoritative and EXCLUSIVE: ``energy``/extras ignored."""
        stat = self._card_stat(attacker_id)
        opp_hp = (opp or {}).get("hp", 0)
        if not (stat and opp_hp):
            return 0.0
        wild = (max(0, energy - len(body.get("energies") or []) - extra_units)
                if body is not None else 0)
        if extra_type is None and extra_units:
            wild += extra_units     # UNKNOWN-type extra stays wild; only a provably-colourless one is strict
        ctx = None
        if boost_amount or promote_bench_names is not None:
            ctx = {}
            if boost_amount:
                ctx["atk_boosts"] = ((boost_amount, boost_type, False),)
            if promote_bench_names is not None:
                ctx["atk_bench_names"] = tuple(promote_bench_names)
        attached = self._attached_units(body) if budget is not None else ()
        best = 0.0
        for aid in (stat.attacks or ()):
            cost = self.attack_cost(aid)
            if budget is not None:
                # TYPED leg (ADR-0075): the Budget is authoritative and exclusive. Fail-CLOSED on an
                # unresolvable cost, matching `reachable_attach`: no slots, no claim.
                slots = self._attack_slots(aid)
                if not slots or not any(_can_pay(slots, attached + tuple(option), budget.caps)
                                        for option in budget.options):
                    continue
            else:
                if cost > energy:                               # can't afford this attack right now
                    continue
                if body is not None and not self.attack_type_payable(
                        aid, body, extra_type=extra_type, extra_units=extra_units, wild_units=wild):
                    continue                                    # count met, a specific-type slot is not
            eff_bound = bound
            if bound == "min" and promote_bench_names is not None:
                # A requiresBench-only conditional whose partner is provably benched is deterministic —
                # read the printed damage, not the does-nothing floor.
                ast = self.attack_stat(aid)
                if (ast is not None and getattr(ast, "requiresBench", None)
                        and all(n in promote_bench_names for n in ast.requiresBench)
                        and (ast.damageMax is None or ast.damageMax == ast.damage)):
                    eff_bound = "exact"
            # Prevention is attack-scoped (ADR-0032): a benched non-ex, or an ignore-flag attack, still
            # registers its KO against a prevent_ex_damage wall.
            dmg = self.predicted_damage(attacker_id, aid, opp, bound=eff_bound, context=ctx)
            if dmg >= opp_hp:
                val = (KO_SCORE + self.prize_value(opp) - _EFFICIENCY * cost
                       + self.bench_snipe_bonus(opp_bench, aid) + self.bench_spread_bonus(opp_bench, aid))
                if attack_p is not None:
                    val *= max(0.0, min(1.0, float(attack_p(aid))))   # ranked consumer: EV, not claim
                best = max(best, val)
        return best

    def best_affordable_damage(self, attacker_id: int | None, energy: int, defender: dict | None, *,
                               body: dict | None = None, extra_type=None, extra_units: int = 0,
                               bound: str = "exact", context: dict | None = None) -> float:
        """The biggest damage ``attacker_id`` (carrying ``energy``) can land on ``defender`` this turn —
        max over attacks affordable in COUNT and payable in COLOUR. Omitting ``body`` fails OPEN."""
        stat = self._card_stat(attacker_id)
        if not stat:
            return 0.0
        best = 0.0
        for aid in (stat.attacks or ()):
            if self.attack_cost(aid) > energy:
                continue                                  # can't afford this attack right now
            if body is not None and not self.attack_type_payable(
                    aid, body, extra_type=extra_type, extra_units=extra_units):
                continue                                  # count met, a specific-type slot is not
            best = max(best, float(self.predicted_damage(attacker_id, aid, defender,
                                                         bound=bound, context=context)))
        return best
