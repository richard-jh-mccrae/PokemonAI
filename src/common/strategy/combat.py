"""CombatMath — the KO oracle (ADR-0052): one closed-form home for damage/KO judgment.

Constructed from the knowledge seams — the Stat Provider (ADR-0056), ``CardFunctions``, and the
match-scoped ``TransientTracker`` — and handed per-decision facts (the damage context, the
opponent's bench) as explicit call arguments. Composes the pure ``damage.py`` seam; never reads
a Pilot or a Board, so it is testable standalone and injectable wherever combat judgment is
needed (the doctrines' future explicit dependency).
"""
from __future__ import annotations

from collections import Counter

from common.strategy.context import KO_SCORE
from common.strategy.damage import compute_active_damage, wr_adjust

# Tactical scalars owned by the oracle (ADR-0052) — used solely by closed-form combat valuation.
_EFFICIENCY = 0.1          # per-Energy tiebreak: among equal-outcome attacks prefer the cheaper one;
                           # far below prize granularity (1) so it never overrides prize value
_BENCH_SNIPE = 0.005       # per-point value of an attack's bench-snipe/spread rider, capped below —
_BENCH_SNIPE_CAP = 0.9     # a sub-prize tiebreak: the equal-outcome KO that ALSO snipes wins,
                           # without ever overriding a prize (ADR-0022 #14)


class CombatMath:
    """The oracle instance the Pilot builds once and delegates to.

    Args:
        stats: the Stat Provider (``get``/``attack``/forward queries), or None (stat-blind —
            every read fails open to 0/None exactly like a stat-blind Pilot).
        functions: ``CardFunctions`` (defender-side prevention tags), or None.
        transients: the match-scoped ``TransientTracker`` (live next-turn grants keyed by body
            serial, ADR-0033), or None — no live shields/locks are then modeled.
    """

    def __init__(self, stats, functions, transients=None):
        self.stats = stats
        self.functions = functions
        self._transients = transients

    # --- record access (the Stat Provider seam, ADR-0056) ------------------------------
    def attack_stat(self, attack_id):
        """The attack's ``AttackStat`` off the provider; None unknown / stat-blind."""
        if self.stats is None:
            return None
        return getattr(self.stats, "attack", lambda _aid: None)(attack_id)

    def attack_cost(self, attack_id, default=99):
        """The attack's Energy count; ``default`` when no record resolves (99 = fail-closed)."""
        st = self.attack_stat(attack_id)
        return st.cost if st is not None else default

    def attack_damage(self, attack_id) -> int:
        """The attack's printed damage; 0 for an unknown attack."""
        st = self.attack_stat(attack_id)
        return st.damage if st is not None else 0

    def _card_stat(self, card_id):
        return self.stats.get(card_id) if (self.stats and card_id is not None) else None

    def _grant(self, poke: dict | None) -> dict | None:
        """The live transient grant on a body (serial-gated), or None."""
        if self._transients is None:
            return None
        return self._transients.grant_for_serial((poke or {}).get("serial"))

    # --- the damage core ----------------------------------------------------------------
    def predicted_damage(self, attacker_id: int | None, attack_id, defender: dict | None, *,
                         bound: str = "exact", context: dict | None = None) -> float:
        """The damage oracle (ADR-0032 E1): damage ``attack_id`` deals to the defending Active —
        the ONE closed-form path every Tier-0 damage estimate routes through. Resolves ids to
        stats/tags, then delegates to the pure ``compute_active_damage`` (the unit the engine
        audit diffs). Honors the attack's ignore flags: Nebula Beam lands 210 through Crustle's
        ex-prevention; Jetting Blow is zeroed (its bench rider is a separate path). ``bound``
        picks a conditional attack's floor/ceiling/printed — Lethal reads "min", Incoming "max"."""
        d_id = (defender or {}).get("id")
        return compute_active_damage(
            self.attack_stat(attack_id),
            self._card_stat(attacker_id),
            self._card_stat(d_id),
            frozenset(self.functions.tags(d_id)) if (self.functions and d_id is not None)
            else frozenset(),
            bound=bound, context=context,
            defender_transient=self._grant(defender))

    def predicted_max_damage(self, attacker_stat, defender: dict | None, *,
                             exclude_attack=None, context: dict | None = None) -> float:
        """The worst damage ``attacker_stat``'s attacks deal to ``defender`` — max over the
        per-attack oracle when EVERY attack's record resolves (a partially-known table never
        SHRINKS a worst case), else the card-level ``maxDamage`` x W/R (``wr_adjust`` — the one
        card-level rule). ``context`` prices the attacker's scalers (the opponent-context dict
        the Pilot stashes per decision — hand size, bench, attached Energy, open discard).

        NOTE: does NOT filter by the opponent's Energy affordability — the Incoming estimate
        assumes the opponent can power its biggest attack (conservative over-estimate; see
        docs/todo/incoming-affordability.md before changing this)."""
        if not attacker_stat:
            return 0
        aids = tuple(a for a in (attacker_stat.attacks or ()) if a != exclude_attack)
        if aids and all(self.attack_stat(a) is not None for a in aids):
            # bound="max": Incoming is the WORST case — a coin/conditional attack threatens its
            # ceiling ("If heads, +20" counts the 20), so survival math never under-plans
            return max(self.predicted_damage(attacker_stat.cardId, a, defender, bound="max",
                                             context=context)
                       for a in aids)
        d_stat = self._card_stat((defender or {}).get("id"))
        return wr_adjust(attacker_stat, d_stat, attacker_stat.maxDamage or 0)

    # --- card-tier combat facts -----------------------------------------------------------
    def prize_value(self, poke: dict | None) -> int:
        """Prizes a knockout of this body yields — Mega ex 3, ex 2, else 1 (the record's own
        question, ADR-0056); 1 for an unknown body."""
        stat = self._card_stat((poke or {}).get("id"))
        return stat.prize_value if stat else 1

    def is_tera(self, card_id) -> bool:
        """A Tera Pokémon — takes NO damage from attacks while BENCHED (engine ``CardData.tera``),
        so no bench-snipe/spread math may ever credit damage against it there. Fail-open (False)
        without stats: a phantom snipe-prize vs Tera could lock a false Lethal."""
        st = self._card_stat(card_id)
        return bool(getattr(st, "tera", False))

    def rider_snipe(self, attack_id) -> int:
        """The attack's unconditional bench-snipe rider damage (0 unknown)."""
        st = self.attack_stat(attack_id)
        return st.benchSnipe if st else 0

    def rider_spread(self, attack_id) -> int:
        """The attack's distributable opp-bench spread total (0 unknown)."""
        st = self.attack_stat(attack_id)
        return st.benchSpread if st else 0

    def rider_recoil(self, attack_id) -> int:
        """The attack's unconditional self-damage (0 unknown).

        UNCONSUMED: zero callers and zero tests. Its siblings `rider_snipe`/`rider_spread` are both
        live. Recoil IS priced — but through `_recoil_flips_doom`, which reads `AttackStat.recoil`
        directly, so this accessor never got wired. Delete on the next combat pass unless a caller
        appears."""
        st = self.attack_stat(attack_id)
        return st.recoil if st else 0

    # --- bench-rider prize math (opp_bench = ((cardId, hp), …), the Board snapshot) -------
    def snipe_ko_prizes(self, opp_bench, rider: int) -> int:
        """Max prize among the opponent's benched Pokémon a bench-snipe ``rider`` KNOCKS OUT —
        bench HP <= rider (bench snipes ignore Weakness/Resistance, ADR-0022); Tera bodies take
        none. 0 when the rider finishes nothing."""
        if rider <= 0:
            return 0
        return max((self.prize_value({"id": cid}) for cid, hp in opp_bench
                    if hp and hp <= rider and not self.is_tera(cid)),
                   default=0)

    @staticmethod
    def best_ko_subset(items, budget: int) -> frozenset:
        """Indices of the max-total-prize subset of ``items`` (``[(hp, prize), …]``) whose total
        HP fits in ``budget`` — a small knapsack (bench <= 5, so <= 32 subsets). Ties break to the
        cheaper set (fewest counters). Empty frozenset when nothing is affordable."""
        best_prize, best_cost, best_mask = 0, 0, 0
        for mask in range(1 << len(items)):          # bench <= 5 -> <= 32 subsets
            cost = prize = 0
            for i, (hp, pv) in enumerate(items):
                if mask & (1 << i):
                    cost, prize = cost + hp, prize + pv
            if cost <= budget and (prize > best_prize
                                   or (prize == best_prize and prize and cost < best_cost)):
                best_prize, best_cost, best_mask = prize, cost, mask
        return frozenset(i for i in range(len(items)) if best_mask & (1 << i))

    def spread_ko_prizes(self, opp_bench, spread: int) -> int:
        """Max total prizes from distributing a ``spread`` (Phantom Dive's ``benchSpread``) across
        the opponent's Bench to KNOCK OUT benched Pokémon — the ``best_ko_subset`` knapsack
        (spread counters ignore W/R; Tera bodies take none). 0 when nothing is finishable."""
        if spread <= 0:
            return 0
        items = [(hp, self.prize_value({"id": cid})) for cid, hp in opp_bench
                 if hp and hp <= spread and not self.is_tera(cid)]
        return sum(items[i][1] for i in self.best_ko_subset(items, spread))

    # --- typed affordability ---------------------------------------------------------------
    def attached_type_counts(self, target: dict) -> dict:
        """{EnergyType: count} of the SPECIFIC (typed Basic) Energy attached to ``target`` — a
        special/colourless Energy reports type 0 and pays a colourless slot only, so it isn't
        counted. Fail-open: an unresolvable id is skipped (undercount only relaxes a suppression)."""
        counts: Counter = Counter()
        for eid in (target.get("energies") or []):
            est = self._card_stat(eid)
            t = getattr(est, "energyType", None) if est else None
            if t not in (None, 0):
                counts[t] += 1
        return counts

    def attack_type_payable(self, aid, target: dict | None, *, extra_type=None,
                            extra_units: int = 0, wild_units: int = 0) -> bool:
        """Sound-or-silent TYPE affordability on top of the count check: every SPECIFIC-type slot
        of ``aid``'s cost (``AttackStat.energyTypes``) must be covered by the target's attached
        typed Energy, plus ``extra_units`` of ``extra_type`` when that is a specific type — a
        colourless/special extra (type 0/None, e.g. Ignition's {C}{C}{C}) pays colourless slots
        only — plus ``wild_units`` hypothetical attaches of UNKNOWN type, each able to cover any
        one specific slot (fail-open: the hand/deck might supply the needed type). An attached
        Energy whose type can't be resolved counts as wild too. True whenever the attack record
        doesn't resolve (the count check stays the sole authority — never a false suppression)."""
        ast = self.attack_stat(aid)
        types = getattr(ast, "energyTypes", ()) if ast else ()
        need = Counter(t for t in types if t not in (0, None))
        if not need or target is None:
            return True
        attached = self.attached_type_counts(target)
        if extra_type not in (None, 0) and extra_units > 0:
            attached = attached.copy()
            attached[extra_type] += extra_units
        unresolved = sum(
            1 for eid in (target.get("energies") or [])
            if getattr(self._card_stat(eid), "energyType", None) is None)
        missing = sum(max(0, n - attached.get(t, 0)) for t, n in need.items())
        return missing <= wild_units + unresolved

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

    # --- Incoming (worst-case, opponent-static — the survival reads) ------------------------
    def forward_card_ids(self, card_id) -> frozenset:
        """Card ids the body's evolution line evolves INTO (the provider primitive; empty when
        no provider / dead-end / unknown id)."""
        fci = getattr(self.stats, "forward_card_ids", None)
        return fci(card_id) if (fci is not None and card_id is not None) else frozenset()

    def incoming_active_damage(self, ma: dict | None, oa: dict | None, *,
                               context: dict | None = None) -> int:
        """Closed-form worst damage the opponent's Active deals my Active next turn — its biggest
        attack (per-attack ceiling), honoring a live transient grant on THEIR Active: a self-lock
        means no attack at all, a same-attack lock excludes that one, a self-bonus raises the hit.
        0 when unknown. WORST-CASE by design — affordability deliberately NOT charged (the hidden
        burst-Energy lesson; docs/todo/incoming-affordability.md)."""
        if not (self.stats and ma and oa):
            return 0
        opp_stat = self._card_stat(oa.get("id"))
        if not opp_stat:
            return 0
        grant = self._grant(oa) or {}
        if grant.get("self_lock"):
            return 0
        dmg = self.predicted_max_damage(opp_stat, ma, exclude_attack=grant.get("same_lock"),
                                        context=context)
        return int(dmg + grant.get("self_bonus", 0)) if dmg else int(dmg)

    def forward_incoming_damage(self, ma: dict | None, oa: dict | None, opp: dict | None, *,
                                context: dict | None = None) -> int:
        """Worst-case incoming if the opponent EVOLVES their Active's line next turn (play AS IF
        they evolve): for each forward form affordable on their Energy + one attach, a
        ``hand_size_attacker`` contributes its hand-scaled counters (W/R-free, hand one short —
        a card is spent evolving), ANY form its printed damage W/R-adjusted vs my Active. 0 when
        unknown / no ``opp`` dict (the forward read needs their hand size)."""
        if not (self.stats and self.functions and ma and oa and opp):
            return 0
        if not self._card_stat(ma.get("id")):
            return 0
        hand = max(0, (opp.get("handCount", 0) or 0) - 1)   # ≥1 card spent to play the evolution
        oa_energy = len(oa.get("energies") or [])
        best = 0
        for fid in self.forward_card_ids(oa.get("id")):
            fstat = self._card_stat(fid)
            if not fstat:
                continue
            if (fstat.minAttackCost or 0) > oa_energy + 1:   # unaffordable even with next turn's attach
                continue
            if "hand_size_attacker" in self.functions.tags(fid):
                best = max(best, (fstat.handSizeDamage or 0) * hand)   # counters ignore W/R
            best = max(best, int(self.predicted_max_damage(fstat, ma, context=context)))
        return best

    def active_doomed(self, ma: dict | None, oa: dict | None, opp: dict | None = None, *,
                      context: dict | None = None) -> bool:
        """The opponent can Knock Out my Active next turn — its biggest CURRENT attack OR the
        attack its Active reaches by EVOLVING >= my Active's HP. WORST-CASE (the ceiling): Energy
        affordability is deliberately not charged — a hidden Ignition-class burst reaches a costly
        nuke in one turn (the planner_6858 lesson). A survival read must never under-prepare."""
        my_hp = (ma or {}).get("hp", 0)
        if not my_hp:
            return False
        threat = max(self.incoming_active_damage(ma, oa, context=context),
                     self.forward_incoming_damage(ma, oa, opp, context=context))
        return threat >= my_hp

    def doomed_incoming(self, ma: dict | None, oa: dict | None, *, charged: dict | None = None,
                        context: dict | None = None) -> int:
        """The Threat-Clock CURVE re-expression of the survival doom read (S1b of
        docs/plans/opponent-value-equation-unification.md): worst incoming to ``ma`` from the
        opponent's Active ``oa`` via :meth:`incoming` at t=1. Returns the DAMAGE — the caller
        compares it to my HP (``>= my_hp`` ⇒ doomed).

        NOT byte-identical to :meth:`active_doomed`, by design — ADR-0064 §2 keeps that one
        unconditionally worst-case. The curve (a) gates the current form on affordability
        (``can_pay_cheapest`` under one attach) and (b) omits the ``hand_size_attacker`` forward
        counter. Those two are exactly the divergences the doom SHADOW measures before any survival
        swap. ``charged`` selects the policy — ``None`` = ceiling, the survival read's worst-case."""
        if not oa:
            return 0
        return int(self.incoming(ma, [oa], 1, charged=charged, context=context))

    # --- reachable Incoming: the opponent's next DEVELOPMENT step (ADR-0064) ----------------
    def reachable_incoming(self, my_body: dict | None, opp_bodies, *, forward_ids=None,
                           charged: dict | None = None, evo_min_energy: int = 0,
                           context: dict | None = None) -> int:
        """The **Incoming that counts ONE development step** (ADR-0064): worst W/R-adjusted damage
        the opponent's affordable attackers among ``opp_bodies`` could deal ``my_body`` NEXT TURN —
        each body's CURRENT form plus its reachable EVOLUTION forms (promote → evolve → attach →
        attack, legal in one turn per rules.md §4), under one attach's Energy. The leaf survival term
        and the promote stand-down share it.

        This is ``incoming(t=1)`` and DELEGATES to :meth:`incoming` — the one implementation, so the
        one-step read stays byte-identical with the N-turn Threat-Clock curve by construction
        (Threat-Clock unification S1; docs/plans/opponent-value-equation-unification.md). All
        arguments (``forward_ids`` availability gate, ``charged`` energy policy, ``evo_min_energy``
        bare-pre-evo guard, transient locks) are documented on :meth:`incoming`."""
        return self.incoming(my_body, opp_bodies, 1, forward_ids=forward_ids, charged=charged,
                             evo_min_energy=evo_min_energy, context=context)

    def incoming(self, my_body: dict | None, opp_bodies, t: int = 1, *, forward_ids=None,
                 charged: dict | None = None, evo_min_energy: int = 0,
                 context: dict | None = None) -> int:
        """Worst W/R-adjusted damage the opponent's affordable attackers among ``opp_bodies`` could
        deal ``my_body`` at future turn ``t`` — the **Threat-Clock curve**, the N-turn generalisation
        of ``reachable_incoming`` (ADR-0064 was ``t=1``; S1 of
        docs/plans/opponent-value-equation-unification.md). 0 when unknown.

        Over ``t`` turns the opponent has had ``t`` attach-turns, so ``t`` moves ONLY the ENERGY
        budget — the evolution reach is already MAXIMAL at ``t=1`` (``forward_card_ids`` is
        all-descendants, existence-gated: every forward form is considered under the current energy
        budget, per ADR-0064's availability gate). Card-effect acceleration and discard-recur fuel
        are NOT modelled here (S2 layers them onto the budget); this is the visible-clock read.
        ``t`` is clamped to ``>= 1``; ``t=1`` reproduces ``reachable_incoming`` exactly.

        ``forward_ids``: callable ``cardId -> iterable`` of the forward card ids to consider — the
        AVAILABILITY gate (ADR-0064 Decision 4: pool-forward existence for the threat read,
        matched-Read rep list for the safety read). None → ``forward_card_ids`` (the pool-level index).

        ``charged``: the ENERGY policy (ADR-0064 Decision 1) — the per-consumer conservatism the
        unification keeps as a PARAMETER (survival passes the ceiling, deny/board-clock the slow read).
        - ``None`` → **ceiling** (worst-case, the hidden-burst-safe survival read): a form contributes
          its biggest attack once it can pay its CHEAPEST under ``attached + t`` attaches; the bigger
          attack's affordability is NOT charged. Mirrors the historical ``_incoming_worst`` at ``t=1``.
        - ``{"base_attach": int, "burst_on_evo": int}`` → **charged**: per-attack typed-cost
          affordability under ``attached + t*base_attach`` manual attaches (each wild — pays any one
          typed slot) + ``burst_on_evo`` colourless-only units available ONLY when the attacking form
          is an Evolution (a matched-Read burst-Energy allowance: Ignition provides {C} on a Basic but
          {C}{C}{C} on an Evolution, so the +2 lands only on an evolved form; it pays colourless slots
          only, never a typed {F}{F}). The burst is a single-card allowance — flat in ``t``, not scaled.

        ``evo_min_energy``: the minimum Energy an opponent body must ALREADY carry for its forward
        evolution forms to count (default 0 — credit every pre-evolution). A catastrophe-grade consumer
        (the ``-KO_SCORE`` loss rung) passes 1: a bare 0-Energy pre-evolution is not a credible
        game-ender (it needs the evolution IN HAND plus a from-scratch attach), and crediting it
        manufactures phantom doom (the bounded-pessimism guard, ADR-0064). The current form is always
        counted regardless.

        Transient locks (ADR-0033) are honoured on a body's CURRENT form only — a self-lock skips it
        entirely, a same-attack lock excludes that attack, a self-bonus raises the hit; a forward
        form is grant-free (evolving clears attack effects, rules.md §4). Benched bodies carry no
        grant (serial-gated), so only their live Active is ever lock-adjusted."""
        my_hp = (my_body or {}).get("hp", 0)
        if not (self.stats and my_hp):
            return 0
        turns = max(1, int(t))
        fwd = forward_ids if forward_ids is not None else self.forward_card_ids
        worst = 0
        for body in opp_bodies:
            if not body:
                continue
            grant = self._grant(body) or {}
            if grant.get("self_lock"):
                continue                              # this body can't attack at all next turn
            attached = len(body.get("energies") or [])
            worst = max(worst, self._reach_form_damage(
                my_body, body.get("id"), body, attached, charged, context,
                exclude=grant.get("same_lock"), bonus=grant.get("self_bonus", 0), attaches=turns))
            if attached < evo_min_energy:
                continue                              # bare pre-evo — not a credible evolving threat here
            for fid in (fwd(body.get("id")) or ()):   # forward forms — carry the attached Energy
                evo = {"id": fid, "energies": body.get("energies") or []}
                worst = max(worst, self._reach_form_damage(
                    my_body, fid, evo, attached, charged, context, exclude=None, bonus=0,
                    attaches=turns))
        return worst

    def _reach_form_damage(self, my_body, form_id, form_body, attached, charged, context, *,
                           exclude, bonus, attaches: int = 1) -> int:
        """The worst damage ONE attacker form (current or evolved) deals ``my_body`` under the
        ``charged`` energy policy (see :meth:`incoming`), given ``attaches`` manual attach-turns of
        Energy available (1 = the ADR-0064 one-step read; the Threat-Clock curve passes ``t``). 0
        when the form resolves no stat, cannot afford to attack, or deals nothing."""
        stat = self._card_stat(form_id)
        if not stat:
            return 0
        if charged is None:                           # ceiling: pay cheapest, credit biggest
            if not stat.can_pay_cheapest(attached + attaches):
                return 0
            dmg = self.predicted_max_damage(stat, my_body, exclude_attack=exclude, context=context)
            return int(dmg) + bonus if dmg else 0
        base = charged.get("base_attach", 1)
        # Ignition-class colourless burst lands its full {C}{C}{C} only on an Evolution (rules.md /
        # card text) — a Basic form gets the plain single attach, no burst. A single-card allowance,
        # so it is flat in the turn count, never scaled by ``attaches``.
        burst = charged.get("burst_on_evo", 0) if getattr(stat, "evolvesFrom", None) else 0
        wild = attaches * base
        best = 0
        for aid in (stat.attacks or ()):
            if aid == exclude:
                continue
            if self.attack_cost(aid) > attached + wild + burst:
                continue                              # count-unaffordable even with the burst allowance
            if not self.attack_type_payable(aid, form_body, wild_units=wild):
                continue                              # a typed slot can't be paid (burst is colourless-only)
            best = max(best, int(self.predicted_damage(form_id, aid, my_body,
                                                       bound="max", context=context)))
        return best + bonus if best else 0

    def turns_to_ko(self, attacker_id, energy: int, body: dict | None, *,
                    context: dict | None = None) -> float | None:
        """Feasibility turns for ``attacker_id`` (carrying ``energy``) to fell ``body`` — hp over
        its best affordable per-turn damage vs THAT defender (W/R + riders per the oracle). None
        when it deals no damage (infeasible). The mechanical core of the KO Race (ADR-0040) —
        surcharges/γ-modulation stay with the objectives that own them."""
        import math
        hp = (body or {}).get("hp", 0)
        stat = self._card_stat(attacker_id)
        if not (hp and stat):
            return None
        best = 0
        for aid in (stat.attacks or ()):
            if self.attack_cost(aid) > energy:
                continue
            best = max(best, self.predicted_damage(attacker_id, aid, body, context=context))
        if best <= 0:
            return None
        return float(math.ceil(hp / best))

    def turns_to_afford(self, body: dict | None, *, forward_ids=None,
                        attaches_per_turn: int = 1, max_hops: int = 3) -> int | None:
        """The earliest future turn ``body``'s LINE is ARMED — its biggest-damage attack's COST is
        payable (NOT lethality — the armed-threshold blocker) — the Threat Clock's affordability +
        evolve leg behind the deny-slot deadline (S1c of
        docs/plans/opponent-value-equation-unification.md). The MAX of two PARALLEL legs (never the
        sum): the ENERGY deficit (max ``maxDamageCost`` over the body's current + forward forms,
        minus attached, at ``attaches_per_turn``) and the FORWARD hops (the ``evolvesFrom``
        name-chain depth to the deepest owed form, one evolve/turn, depth-guarded by ``max_hops``).
        None when the body/its stats are unknown or no form's biggest-attack cost is known
        (fail-closed — the caller emits no deny slot).

        Shares the forward index and the energy model with :meth:`incoming` — the Threat Clock's two
        legs (the damage curve + the affordability clock) in ONE home. ``forward_ids`` overrides the
        forward callable (the availability gate); ``attaches_per_turn`` is the policy attach rate
        (1 = the slow deny read, the per-consumer conservatism kept as a parameter). The deny-clock
        consumer ``pilot._opp_turns_to_ready`` DELEGATES here (byte-identical)."""
        from common import needs
        cid = (body or {}).get("id")
        st = self._card_stat(cid)
        if st is None:
            return None
        fwd = forward_ids if forward_ids is not None else self.forward_card_ids
        fwd_stats = [self._card_stat(f) for f in (fwd(cid) or ())]
        costs = [c for c in (getattr(s, "maxDamageCost", None)
                             for s in (st, *fwd_stats) if s is not None) if c is not None]
        if not costs:
            return None
        deficit = max(costs) - len((body or {}).get("energies") or [])
        parent = {s.name: getattr(s, "evolvesFrom", None) for s in fwd_stats
                  if s is not None and s.name}
        hops = 0
        for name in parent:
            d, n = 0, name
            while n and n != st.name and d <= max_hops:
                d, n = d + 1, parent.get(n)
            if n == st.name:
                hops = max(hops, d)
        return needs.turns_to_ready(energy_deficit=deficit, evolve_hops=hops,
                                    attaches_per_turn=attaches_per_turn)

    # --- KO valuation (the shared band every hypothetical attacker is priced on) ------------
    def bench_snipe_bonus(self, opp_bench, attack_id) -> float:
        """Sub-prize tiebreak (ADR-0022 #14): an attack that ALSO snipes a benched Pokémon is
        worth a little extra board value — scaled by the rider, capped below a prize; 0 with no
        clean rider or no benched target."""
        rider = self.rider_snipe(attack_id)
        if rider <= 0 or not opp_bench:
            return 0
        return min(_BENCH_SNIPE_CAP, _BENCH_SNIPE * rider)

    def bench_spread_bonus(self, opp_bench, attack_id) -> float:
        """Sub-prize tiebreak for a distributable bench SPREAD that doesn't finish a bench mon —
        it still pre-loads the Bench. Mirrors ``bench_snipe_bonus``; nonzero only for spreads."""
        spread = self.rider_spread(attack_id)
        if spread <= 0 or not opp_bench:
            return 0
        return min(_BENCH_SNIPE_CAP, _BENCH_SNIPE * spread)

    def best_affordable_ko_value(self, opp: dict, attacker_id: int | None, energy: int, *,
                                 opp_bench=(), bound: str = "exact", body: dict | None = None,
                                 extra_type=None, extra_units: int = 0,
                                 boost_amount: int = 0, boost_type=None,
                                 promote_bench_names=None) -> float:
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
        ``((cardId, hp), …)`` snapshot behind the rider tiebreaks."""
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
        best = 0.0
        for aid in (stat.attacks or ()):
            cost = self.attack_cost(aid)
            if cost > energy:                                   # can't afford this attack right now
                continue
            if body is not None and not self.attack_type_payable(
                    aid, body, extra_type=extra_type, extra_units=extra_units, wild_units=wild):
                continue                                        # count met, a specific-type slot is not
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
                best = max(best, val)
        return best
