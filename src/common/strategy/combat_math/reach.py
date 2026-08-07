"""Affordability: what this body can actually do with what it holds, and with what it could still reach.

The pair is a counterfactual — 'right now' against 'under the full Budget' — and both legs matter, because the
difference between them is exactly what an enabler play buys."""
from __future__ import annotations


from common.deck_odds import draw_hit_probability
from common.strategy.combat_math.budget import Budget, _can_pay
from common.strategy.context import KO_SCORE


# Tactical scalars owned by the oracle (ADR-0052) — used solely by closed-form combat valuation.
_EFFICIENCY = 0.1          # per-Energy tiebreak: among equal-outcome attacks prefer the cheaper one;
                           # far below prize granularity (1) so it never overrides prize value


class ReachMixin:
    """What a body can knock out, damage or afford."""

    # --- reachability (can X KO / hurt Y) ---------------------------------------------------
    def can_ko_cheapest(self, my_stat, defender: dict | None) -> bool:
        """The attacker's CHEAPEST attack would Knock Out ``defender`` this turn — per-attack
        oracle over the cheapest-cost attacks (prevention is attack-scoped: an ignore-flag attack
        still KOs through a wall). Fail-closed on missing stats/HP/records — the card-level
        ``minCostDamage`` fallback is RETIRED (ADR-0052): no record, no claim."""
        hp = (defender or {}).get("hp", 0)
        if not (my_stat and hp):
            return False
        cheap = [aid for aid in (my_stat.attacks or ())
                 if self.attack_cost(aid, None) == my_stat.minAttackCost
                 and self.attack_stat(aid) is not None]
        return any(self.predicted_damage(my_stat.cardId, aid, defender) >= hp for aid in cheap)

    def can_ko_affordable(self, attacker: dict | None, defender: dict | None) -> bool:
        """The attacker's best attack it can currently AFFORD (its attached Energy) KOs
        ``defender`` this turn — scans every affordable attack, so a big non-cheapest KO is seen
        (Mega Starmie at CCC KOs with Nebula Beam though Jetting Blow can't). Fail-closed."""
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
        ``defender`` — 'can they hurt me with what they hold NOW'. A conditional attack that
        computes to 0 (Riptide off an empty discard) or an all-unaffordable set is NO threat.
        Fail-closed."""
        if not (attacker and defender):
            return False
        stat = self._card_stat(attacker.get("id"))
        if not (stat and defender.get("hp")):
            return False
        energy = len(attacker.get("energies") or [])
        return any(self.predicted_damage(attacker.get("id"), aid, defender) > 0
                   for aid in (stat.attacks or ()) if self.attack_cost(aid) <= energy)

    def maxed_kos(self, attacker: dict | None, defender: dict | None) -> bool:
        """The attacker's BIGGEST-damage attack (fully powered, IGNORING current Energy) would KO
        ``defender`` — 'could I KO if I loaded up?'. When False the defender is un-KO-able this
        turn even maxed, so a one-shot burst buys no KO. Fail-closed."""
        if not (attacker and defender):
            return False
        stat = self._card_stat(attacker.get("id"))
        hp = defender.get("hp", 0)
        if not (stat and hp and stat.attacks):
            return False
        best_aid = max(stat.attacks, key=self.attack_damage)    # biggest printed attack
        return self.predicted_damage(attacker.get("id"), best_aid, defender) >= hp

    def best_reachable_damage(self, my_body: dict | None, *, budget: Budget) -> float:
        """The biggest PRINTED damage among the attacks ``my_body`` can reach this turn under
        ``budget`` — the counterfactual leg of the attach marginal (ADR-0069 §2).

        ANY reachable attack, not the biggest one it might someday afford: a doomed Active that
        unlocks a smaller real attack tonight is credited for exactly that (the Mega-Starmie tempo
        case the rung layer's biggest-attack-only exemption lost). Opponent-independent — the
        overkill cap, not this read, owns "a bigger attack buys nothing". Fail-CLOSED at 0.0."""
        stat = self._card_stat((my_body or {}).get("id"))
        if stat is None or budget is None:
            return 0.0
        return float(max((self.attack_damage(aid) for aid in (stat.attacks or ())
                          if self.reachable_attach(my_body, aid, budget=budget)), default=0))

    def best_reachable_damage_vs(self, my_body: dict | None, defender: dict | None, *,
                                 budget: Budget, context: dict | None = None) -> float:
        """Biggest damage ``my_body`` can reach this turn AGAINST ``defender`` — the same
        Budget-affordability filter as :meth:`best_reachable_damage`, read through the damage
        oracle instead of the printed number, so Weakness / Resistance / prevention / boosts apply
        (Issue #281, POC-T3.5).

        A SIBLING, not a replacement, and the split is load-bearing rather than tidy. The incumbent
        is the counterfactual leg of the attach marginal (ADR-0069 §2) and is deliberately
        opponent-INDEPENDENT — *"the overkill cap, not this read, owns 'a bigger attack buys
        nothing'"* — so teaching it about the defender would move `attach_value`, which is
        corpus-ruled. Two questions, two methods.

        Everything except the damage read is the incumbent's, deliberately: `reachable_attach`
        under the same Attach ``budget`` stays the ONE opinion about affordability this family
        holds. (:meth:`can_ko_affordable` also scans through :meth:`predicted_damage` and was
        considered for the same job — it asks affordability of the *attached* Energy, a strictly
        different and weaker question than the Budget, and a family holding two opinions about
        affordability is what the sole-supplier ruling forbids.)

        ``bound`` is the oracle's default ``"exact"`` and is not a parameter. An OFFENSIVE
        reachability read is neither a lethal guarantee nor a worst case — the two readings that
        own ``"min"`` and ``"max"`` (`Lethal reads "min", Incoming "max"`, :meth:`predicted_damage`)
        — so there is one right answer here and no caller to give a choice to.

        Fail-CLOSED at 0.0, like the incumbent: no ``CardStat``, no Budget, no claim."""
        stat = self._card_stat((my_body or {}).get("id"))
        if stat is None or budget is None:
            return 0.0
        return float(max((self.predicted_damage((my_body or {}).get("id"), aid, defender,
                                                context=context)
                          for aid in (stat.attacks or ())
                          if self.reachable_attach(my_body, aid, budget=budget)), default=0))

    def best_reachable_bench_damage(self, my_body: dict | None, defender: dict | None, *,
                                    budget: Budget) -> float:
        """Biggest damage ``my_body`` can put on ONE of the opponent's **BENCHED** bodies this turn
        — the bench sibling of :meth:`best_reachable_damage_vs` (Issue #284, POC-T3.5).

        A THIRD method rather than an ``area`` flag on either sibling, because the bench is a
        different damage ROUTE and not a different defender. An attack's printed damage lands on the
        Active; a benched body is reachable only through the attack's snipe RIDER, which ignores
        Weakness and Resistance by rule (ADR-0022) and therefore never routes through
        :meth:`predicted_damage` — the oracle says so about this very attack: *"Jetting Blow is
        zeroed (its bench rider is a separate path)"*. :meth:`_reach_form_damage` already draws the
        same line for INCOMING damage onto my Bench; this is that line seen from the other side.

        **The rider read is :meth:`rider_snipe`, NOT :meth:`_bench_rider`**, and the difference is
        the direction. ``_bench_rider`` sums snipe and spread as a WORST CASE for a body of mine —
        sound when over-reading their reach is the safe error. Here the same sum would over-read MY
        reach, and a spread is a SHARED counter budget across their whole Bench (Phantom Dive: *"Put
        6 damage counters on your opponent's Benched Pokémon in any way you like"*), so crediting
        its full total against every body separately would claim three Knock Outs from one 60-counter
        payload. The subset question has an owner already — :meth:`spread_ko_prizes`, whose
        ``best_ko_subset`` knapsack answers it in PRIZES over a whole Bench — and it does not
        compose into a per-body reach. Snipe riders are indivisible by construction (*"Each snipe
        unit lands entirely on ONE body (single-target text)"*, :meth:`_harvest_residual`), so this
        under-reads rather than over-reads. **No pool attack prints both riders** — swept over all
        1556 attack records, `benchSnipe` and `benchSpread` are never both non-zero on one attack —
        so on this set the choice costs the three spread attacks (Flutter Mane 20, Sinistcha 40,
        Dragapult ex 60) and nothing else.

        Affordability is :meth:`reachable_attach` under the same Attach ``budget`` as both siblings,
        so this family keeps ONE opinion about what I can pay for.

        Fail-CLOSED at 0.0 on **either** side being unreadable, which is stricter than
        :meth:`is_tera` alone and deliberately so. That oracle fails OPEN on a missing stat (False =
        not Tera) because its own consumers must never suppress a real Lethal; here an unresolvable
        benched body could be an Antique Plume Fossil, a Misty's Magikarp or a Poltchageist — all
        carry unconditional prevent-all-while-Benched and `CardStat` has no field for it
        (`docs/rules.md` §11, ADR-0020) — and crediting a Knock Out against one would invent
        pressure. So the defender's stat is checked BEFORE the oracle is asked, the same order
        `MySide.active_famine` uses for the same reason."""
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
        """P(``my_body`` is READY to use the attack this turn) — the EV variant of
        :meth:`reachable_attach`, and the probabilistic MIDDLE the interim promote/retreat
        ``fetch_enables_p`` never had (it shipped a bare 1.0/0.0).

        1.0 when ``budget`` — what I hold NOW — already reaches. Otherwise, if drawing a still-in-
        deck enabler WOULD reach (``enabler_budget``, the same Budget computed as though that card
        were in hand), the exact hypergeometric that the turn's remaining dig finds one:
        ``draw_hit_probability(copies, pool, draws)``. Fail-CLOSED at 0.0 — no enabler modelled, or
        an enabler that still would not pay, is worth nothing, never its bare draw odds.

        ``p_by_type`` (ADR-0074 decision 6, #175) additionally prices the DECK-fetch leg inside each
        Budget: this method priced the *draw* honestly while leaving deck presence a fail-open
        boolean, so a line resting on the last copy of a colour read the same as one resting on
        three. Omitted, every reading is 1.0/0.0 and the result is byte-identical to before."""
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
        """P(``budget`` plus ``body``'s attached Energy really pays ``attack_id``) — the Probability
        Leg applied to ONE attack's typed cost (ADR-0074, #175). 1.0 with no probability map (an
        unweighted caller), and 1.0 for a cost this oracle cannot resolve — an unknown cost makes no
        claim, so it must not manufacture a discount either."""
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
        """The best KO value ``attacker_id`` (carrying ``energy`` Energy) reaches against the
        opponent's Active — KO_SCORE + prize − efficiency + bench-snipe rider, the ONE band every
        hypothetical attacker is priced on (retreat/gust/promote/attach/boost lookaheads). 0 if no
        affordable attack knocks the defender out; ``bound="min"`` for the Lethal Solver's sound
        floor (a coin-conditional KO never locks a phantom).

        ``body`` (the attacker's on-board dict) arms the ``attack_type_payable`` guard: an attack
        whose SPECIFIC-type slots the body's attached Energy provably can't cover is dropped even
        when the count suffices. Energy beyond the body's attached cards — a planned attach — is
        ``extra_units`` of ``extra_type`` when the caller knows the card, else counted WILD
        (fail-open). ``boost_amount``/``boost_type`` price a typed flat this-turn damage boost
        through the oracle's own ``atk_boosts`` context (attacker-type gate, before-W/R placement).
        ``promote_bench_names`` names the bodies that WILL sit on my Bench after the presumed
        promote/retreat — a ``requiresBench`` attack whose partner is provably benched then reads
        its printed damage rather than the does-nothing floor. ``opp_bench`` is the Board's
        ``((cardId, hp), …)`` snapshot behind the rider tiebreaks.

        ``attack_p`` (ADR-0074, #175) weights each candidate attack by P(the Energy it needs is
        really there) — ``attack_p(attack_id) -> float``. It is the RANKED-consumer hook and is
        omitted by every lock: with it absent the method is byte-identical to before. Because the
        weight is applied per attack BEFORE the max, the winner is the attack with the best
        *expected* value, not the best value that might not happen.

        ``budget`` (ADR-0075, #177) replaces the COUNT with the **Attach Budget** — the typed
        capacity toward THIS attacker. Affordability then asks the one predicate
        :meth:`reachable_attach` asks, ``_can_pay`` per slot over each option, so a planned attach
        pays a specific-type slot only when the cards really produce that colour. ``energy`` and
        ``extra_units``/``extra_type`` are IGNORED on this leg — the Budget is the whole truth — and
        the count gate is subsumed (``_can_pay`` refuses when there are fewer units than slots).

        **Refusal and ranking are separate** (ADR-0075 decision 7). ``budget`` decides WHETHER the
        KO is real: it fails CLOSED, so an attack whose slots do not resolve is skipped and makes no
        claim, where ``attack_type_payable`` would fail open. ``attack_p`` decides what a real KO is
        WORTH. The order is refuse-then-weight — a refused attack never reaches the multiply, so an
        unpayable attack and a certain-but-worthless one stay distinguishable."""
        stat = self._card_stat(attacker_id)
        opp_hp = (opp or {}).get("hp", 0)
        if not (stat and opp_hp):
            return 0.0
        wild = (max(0, energy - len(body.get("energies") or []) - extra_units)
                if body is not None else 0)
        if extra_type is None and extra_units:
            wild += extra_units     # UNKNOWN-type extra stays wild — only a provably-colourless
                                    # extra (extra_type=0, Ignition) is strict; never false-suppress
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
                # TYPED leg (ADR-0075): the Budget is authoritative and exclusive — `energy` and the
                # wild extras are not consulted. Fail-CLOSED on an unresolvable cost, matching
                # `reachable_attach`: no slots, no claim (the fail-open `attack_type_payable` would
                # have counted it). Verified inert on real data — no card prints a 0-cost attack.
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
                ast = self.attack_stat(aid)                     # a requiresBench-only conditional whose
                if (ast is not None and getattr(ast, "requiresBench", None)                # partner is
                        and all(n in promote_bench_names for n in ast.requiresBench)       # provably
                        and (ast.damageMax is None or ast.damageMax == ast.damage)):       # benched
                    eff_bound = "exact"     # is deterministic — read printed, not the does-nothing floor
            # per-attack oracle (ADR-0032): prevention is attack-scoped — a benched non-ex (or an
            # ignore-flag attack) still registers its KO against a prevent_ex_damage wall
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
        """The biggest damage ``attacker_id`` (carrying ``energy`` Energy) can actually land on
        ``defender`` this turn — max over its attacks that are affordable in COUNT and payable in
        COLOUR. 0 when nothing resolves or nothing is affordable.

        The sibling of :meth:`best_affordable_ko_value` one rung down: that one asks *"does an
        affordable attack KILL"* and answers on the KO band; this asks *"how hard does the best
        affordable attack HIT"* and answers in raw damage. Both are needed, because the questions
        differ wherever the answer is a non-lethal swing — which is the whole of
        ``best_affordable(E) − best_affordable(E − 1)``, the deny oracle's own shape (ADR-0062) and
        the shape :meth:`pilot.Pilot._heal_bounce_cost` prices a heal's Energy bounce with.

        **Extracted rather than authored** (Issue #409): this exact loop was already spelled out at
        two call sites — ``_attach_lethal_tactical``'s inner ``best_affordable`` and
        ``_gamble_det_baseline``'s scan — and a third consumer arriving was the moment two spellings
        became three. They differed in nothing but which kwargs they passed, so both now delegate
        here and the affordability rule has ONE home. That matters more than the duplication: the
        count gate and the colour gate must stay in lockstep, and a copy is free to gain one and not
        the other.

        ``body`` arms the colour gate exactly as it does on the KO twin — omitting it (the shape a
        post-bounce re-attach takes, where the attached counts are stale by construction) counts the
        Energy as WILD and so fails OPEN, which is the direction a *cost* estimate must err in."""
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
