"""The CLOCKS: how many turns until they knock me out, until I can afford my attack, until a body dies.

`incoming` takes an explicit energy policy because the question has more than one honest answer; `UNCHARGED` is the
strictly-pessimistic one, and it is the only policy a catastrophe-grade survival boolean may take."""
from __future__ import annotations


from dataclasses import dataclass

from common.strategy.combat_math.policy import HARVEST_POSSIBLE, UNCHARGED


@dataclass(frozen=True)
class SurvivalClock:
    """Both readings of ONE :meth:`CombatMath.survival_clock` accumulation — the **Fractional
    Survival Clock** (ADR-0117, amending ADR-0071 decision 4).

    ``turns`` is the shipped integer: the first turn at which accumulated incoming damage reaches
    my HP, or ``max_t + 1`` when the body survives the horizon. Every consumer that existed before
    ADR-0117 reads this and is unaffected by the field beside it.

    ``exact`` is where inside that turn the crossing actually falls, interpolated linearly:

        exact = (turns - 1) + (hp - dealt(turns - 1)) / incoming(turns)

    The precision is not new information — ``dealt`` is continuous and the accumulation already
    computes it; the integer threshold is simply where it was being discarded.

    ⚠️ **This recovers a MINORITY of the Flat Tie.** Quantization was 10.0% of that defect; the rest
    is a **Structural Zero** no resolution can touch, because :meth:`incoming` is a per-turn MAXIMUM
    over their forms — removing a body that never leads that maximum moves nothing, at any
    precision. Do not cite this class as the fix for Issue #398; it is a prerequisite for one.
    Numbers, the counter-example that narrowed the claim, and the reasoning live in ADR-0117
    and are deliberately NOT restated here; the instrument is
    ``tools/train/probes/fractional_clock_sweep.py``.

    The two fields are produced by ONE loop rather than two passes, so they cannot drift — the
    failure mode ADR-0117 explicitly rejected a second oracle to avoid. When there is no
    crossing inside the horizon, ``exact`` repeats ``turns`` exactly rather than extrapolating past
    it: there is nothing to interpolate, and inventing a value beyond the window would be a claim
    the accumulation does not make.

    ``exact`` is opt-in. A caller taking it states why at the call site; the integer stays the
    default, so ADR-0071 decision 4's accumulate semantics are unchanged for every family that was
    not measured here (`survival`, `readiness`, `threat` each carry scale anchors calibrated
    against the integer clock)."""

    turns: int
    exact: float


class ClockMixin:
    """Turns-until: the survival and affordability clocks."""

    def doomed_incoming(self, ma: dict | None, oa: dict | None, *, charged: dict | None = None,
                        context: dict | None = None) -> int:
        """The Threat-Clock CURVE re-expression of the survival doom read (S1b of
        docs/plans/opponent-value-equation-unification.md): worst incoming to ``ma`` from the
        opponent's Active ``oa`` via :meth:`incoming` at t=1. Returns the DAMAGE — the caller
        compares it to my HP (``>= my_hp`` ⇒ doomed).

        NOT byte-identical to :meth:`active_doomed`, by design — ADR-0064 §2 keeps that one
        unconditionally worst-case. The curve gates the current form on affordability
        (``can_pay_cheapest`` under one attach); that is the ONE remaining divergence, and it is
        what the doom SHADOW measures before any survival swap.

        A second divergence used to be claimed here — that the curve omits the
        ``hand_size_attacker`` forward counter. It was never true on a production path (Issue
        #213): the hand-size attack carries the Damage Formula's ``atk_hand`` scaler like any other
        scaling attack, and the scaler rides the ``context`` kwarg that **every live Incoming
        consumer threads**, so both reads price it — the curve in fact reads HIGHER, because the
        generic term prices a forward form at the full hand where the retired branch spent the
        evolving card.

        That clause used to state a COUNT — *"all six Incoming call sites thread the per-decision
        damage context"* — and Issue #343 replaced it, **not because the arithmetic was wrong**.
        Re-taken at that issue's base, the number was exactly right under the reading it was written
        in: six consumer calls spelled ``incoming`` or ``doomed``, every one of them threading. The
        sentence still misled, and the ambiguity is the reason. "Incoming" names a FAMILY here —
        :meth:`reachable_incoming` and :meth:`turns_to_ko_me` funnel into :meth:`incoming` and carry
        the same ``context`` — and under that wider reading the census stood at twenty consumer call
        sites with four threading nothing (``pilot._opponent_target_rows`` and
        ``pilot._strip_delta_terms``, two clock legs each). ``docs/plans/term-sufficiency-audit.md``
        F2 read it the wide way, cited this very sentence as an invariant, and concluded
        ``state_value`` was the lone exception; it was not.

        So a defensible number still rotted into a false reassurance, which is the argument for a
        PROPERTY — and for asserting it rather than asserting it in prose:
        ``tests/strategy/test_target_rows_damage_context.py`` walks the consumer modules, fails on
        any call site that prices no context, keeps an allowlist that is empty today, and carries a
        positive control so the sweep cannot go quietly blind.

        ``charged`` selects the policy — ``None`` = ceiling, the survival read's worst-case."""
        if not oa:
            return 0
        return int(self.incoming(ma, [oa], 1, charged=charged, context=context))

    # --- reachable Incoming: the opponent's next DEVELOPMENT step (ADR-0064) ----------------
    def reachable_incoming(self, my_body: dict | None, opp_bodies, *, forward_ids=None,
                           charged: dict | None = None, evo_min_energy: int = 0,
                           context: dict | None = None, my_benched: bool = False) -> int:
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
                             my_benched=my_benched,
                             evo_min_energy=evo_min_energy, context=context)

    def _promotion_open(self, opp_bodies, opp_active, *, switch_enabler: bool = False) -> bool:
        """Can a BENCHED opponent body attack next turn — the promotion gate (ADR-0071 decision 6).

        Retreat is an ordinary turn action (rules.md:74) limited to once per turn and paid in
        **Energy discard** (:89), and attacking ends the turn, so retreat-then-attack is legal in ONE
        turn: a benched attacker owes Energy, never tempo. Open when their Active can pay its printed
        retreat cost, when ``switch_enabler`` says a switch-class out cannot be ruled out, or when
        ``opp_active`` is absent — a body removed from the list is a body that was Knocked Out, and
        the replacement Active is chosen from the Bench for FREE (rulebook.txt:176), which is exactly
        the case `survival_shift` constructs. Fail-OPEN on an unreadable retreat cost.

        ``switch_enabler`` is caller-computed: whether they hold a Switch is a Read/deck-tracker
        question, and `CombatMath` is board-only and deck-agnostic. Every leg here fails OPEN, because
        this gate can only ever make a threat read LESS pessimistic and a survival read must never
        under-prepare (CONTEXT.md, Threat Clock)."""
        if opp_active is None or switch_enabler:
            return True
        if not any(b is opp_active for b in opp_bodies):
            return True                               # their Active is off the board — free promotion
        st = self._card_stat(opp_active.get("id"))
        cost = getattr(st, "retreatCost", None) if st else None
        if cost is None:
            return True                               # unreadable -> admit (pessimistic on threat)
        return len(opp_active.get("energies") or []) >= int(cost)

    def incoming(self, my_body: dict | None, opp_bodies, t: int = 1, *, forward_ids=None,
                 charged: dict | None = None, evo_min_energy: int = 0,
                 context: dict | None = None, my_benched: bool = False,
                 opp_active: dict | None = None, switch_enabler: bool = False) -> int:
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
        worst = 0
        for form_id, form_body, attached, grant, is_current in self._attacker_forms(
                opp_bodies, forward_ids=forward_ids, evo_min_energy=evo_min_energy,
                opp_active=opp_active, switch_enabler=switch_enabler):
            worst = max(worst, self._reach_form_damage(
                my_body, form_id, form_body, attached, charged, context,
                exclude=grant.get("same_lock") if is_current else None,
                bonus=grant.get("self_bonus", 0) if is_current else 0,
                attaches=turns, my_benched=my_benched, is_current=is_current))
        return worst

    def _attacker_forms(self, opp_bodies, *, forward_ids=None, evo_min_energy: int = 0,
                        opp_active=None, switch_enabler: bool = False):
        """Every opponent FORM that could attack next turn — ``(form_id, form_body, attached, grant,
        is_current)`` per form, current forms plus their forward evolutions.

        ONE enumeration, because two reads consume it: :meth:`incoming` (the damage curve) and
        :meth:`_bench_payload` (the rider payload). Keeping them separate let them drift — the rider
        read silently skipped the ``evo_min_energy`` bounded-pessimism guard (ADR-0064), crediting a
        bare 0-Energy pre-evolution's riders where the damage read would not. Same reasoning as
        `_build_standing` in ADR-0070: one function owns the fact, so the readings cannot disagree.

        Applies the transient self-lock (ADR-0033) and the promotion gate (ADR-0071 decision 6). A
        forward form is grant-free — **evolving clears attack effects** (`docs/rules.md` §4:
        *"Evolving keeps attached cards + damage counters; clears Special Conditions and attack
        effects"*), and that is why a self-locked body still yields its FORWARD forms: the lock
        says *this* Pokémon cannot attack next turn, and the Pokémon it evolves into is not it.
        Skipping the whole line was an UNDER-read (POC-T1, Issue #260) — the legacy
        `forward_incoming_damage` this curve now subsumes never applied the lock to forward forms,
        and dropping them on the fold would have made a survival read less pessimistic than the read
        it replaced. Fixed here rather than compensated for at the fold, because the fold's whole
        premise is that there is ONE implementation."""
        fwd = forward_ids if forward_ids is not None else self.forward_card_ids
        promotable = self._promotion_open(opp_bodies, opp_active,
                                          switch_enabler=switch_enabler)
        for body in opp_bodies:
            if not body:
                continue
            if not promotable and opp_active is not None and body is not opp_active:
                continue                              # stuck behind an Active that can't pay retreat
            grant = self._grant(body) or {}
            attached = len(body.get("energies") or [])
            if not grant.get("self_lock"):            # locked: this body can't attack at all — but
                yield body.get("id"), body, attached, grant, True    # its evolutions still can
            if attached < evo_min_energy:
                continue                              # bare pre-evo — not a credible evolving threat
            for fid in (fwd(body.get("id")) or ()):   # forward forms — carry the attached Energy
                yield fid, {"id": fid, "energies": body.get("energies") or []}, attached, grant, False

    def _bench_rider(self, attack_id) -> int:
        """What ``attack_id`` puts on ONE of my BENCHED bodies: its snipe and spread riders, summed
        (an attack carrying both can aim both at the same body — the worst case, and the additive
        convention `objectives.py` already uses over a bench pool). Riders ignore Weakness and
        Resistance (ADR-0022), so this is deliberately NOT routed through the W/R damage oracle."""
        return self.rider_snipe(attack_id) + self.rider_spread(attack_id)

    def _reach_form_damage(self, my_body, form_id, form_body, attached, charged, context, *,
                           exclude, bonus, is_current: bool, attaches: int = 1,
                           my_benched: bool = False) -> int:
        """The worst damage ONE attacker form (current or evolved) deals ``my_body`` under the
        ``charged`` energy policy (see :meth:`incoming`), given ``attaches`` manual attach-turns of
        Energy available (1 = the ADR-0064 one-step read; the Threat-Clock curve passes ``t``). 0
        when the form resolves no stat, cannot afford to attack, or deals nothing.

        ``my_benched`` is the AREA-AT-DAMAGE-TIME of ``my_body`` (ADR-0070 §9): an attack's printed
        damage lands on the ACTIVE, so a benched body is reachable only by the snipe/spread riders —
        and not at all if it is Tera (rules.md §185). The attacker-side self-bonus grant raises
        printed damage, not a rider, so it is not applied on the bench path.

        ``is_current`` distinguishes the body as it STANDS from a form it could evolve into, and it
        is load-bearing under exactly one policy: :data:`UNCHARGED` charges the current form NO
        affordability at all (the hidden-burst lesson — a body already on the board can hold Energy
        we cannot see, so "its cheapest attack costs more than it carries" is not a proof it will not
        swing), while a form that does not exist yet must still be reachable."""
        stat = self._card_stat(form_id)
        if not stat:
            return 0
        if my_benched and self.is_tera((my_body or {}).get("id")):
            return 0                                  # Tera: no attack damage while Benched
        if charged is None or charged == UNCHARGED:   # ceiling family: pay the gate, credit biggest
            unconditional = (charged == UNCHARGED and is_current)
            if not unconditional and not self._affords(stat, form_body, None, attached, attaches,
                                                       charged, is_current=is_current):
                return 0
            if my_benched:
                return max((self._bench_rider(aid) for aid in (stat.attacks or ())
                            if aid != exclude), default=0)
            dmg = self.predicted_max_damage(stat, my_body, exclude_attack=exclude, context=context)
            return int(dmg) + bonus if dmg else 0
        best = 0
        for aid in (stat.attacks or ()):
            if aid == exclude:
                continue
            if not self._affords(stat, form_body, aid, attached, attaches, charged,
                                 is_current=is_current):
                continue                              # unaffordable in count or in colour
            best = max(best, self._bench_rider(aid) if my_benched
                       else int(self.predicted_damage(form_id, aid, my_body,
                                                      bound="max", context=context)))
        if my_benched:
            return best
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
                        attaches_per_turn: int = 1, max_hops: int = 3,
                        typed: bool = False) -> int | None:
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
        consumer ``pilot._opp_turns_to_ready`` DELEGATES here (byte-identical).

        ``typed`` picks the energy leg's reading, and it is a FAIL-DIRECTION choice, not a quality
        one — which is why it is a per-consumer parameter like ``charged`` rather than a fix applied
        everywhere. The default COUNT reading (cost minus attached) over-credits off-colour Energy,
        so a body reads armed sooner than it is: pessimistic about THEIR clock, which is the safe
        direction for a threat read. ``typed=True`` counts only Energy that fills a slot of the
        payoff's real cost shape, by the same matcher :meth:`reachable_attach` uses — correct for MY
        bodies, where over-crediting a {D} toward a {P} would price an unpayable line as armed
        (ADR-0070 §2: the evolve decider's deploy delta rides this clock)."""
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
        deepest = max(((s, getattr(s, "maxDamageCost", 0) or 0) for s in (st, *fwd_stats)
                       if s is not None and getattr(s, "maxDamageCost", None) is not None),
                      key=lambda pair: pair[1], default=(None, 0))[0]
        deficit = max(costs) - len((body or {}).get("energies") or [])
        if typed and deepest is not None:
            aid = max((getattr(deepest, "attacks", None) or ()), key=self.attack_damage, default=None)
            if aid is not None:
                matched, slots = self.matched_slots(body, aid)
                if slots:
                    deficit = slots - matched
        hops = max(self._forward_hop_depths(st, fwd_stats, max_hops=max_hops).values(), default=0)
        return needs.turns_to_ready(energy_deficit=deficit, evolve_hops=hops,
                                    attaches_per_turn=attaches_per_turn)

    def turns_to_ko_me(self, my_body: dict | None, opp_bodies, *, charged: dict | None = None,
                       max_t: int = 8, context: dict | None = None, my_benched: bool = False,
                       my_bench=(), key_ids=frozenset(), reading: str = HARVEST_POSSIBLE,
                       opp_active: dict | None = None, switch_enabler: bool = False) -> int:
        """The earliest future turn the opponent's board can KO ``my_body`` — the survival-window
        inversion of the Threat-Clock curve — or ``max_t + 1`` when it survives the horizon.

        **Damage ACCUMULATES** (ADR-0071 decision 4). The Active leg is
        ``min{ t : Σᵢ₌₁..ᵗ incoming(i) ≥ hp }``: counters persist, so a body that survives one swing
        is not safe forever. That is not a new semantic — CONTEXT.md's Threat Clock already specified
        *"accumulating over turns when one hit doesn't KO"*, and the offensive twin
        :meth:`turns_to_ko` is already rate-based; the one-swing reading was the outlier. The sum of
        per-turn maxima errs PESSIMISTIC — it charges nothing for the retreat that switching
        attackers costs — which is the bounded-pessimism convention (ADR-0064) and the direction that
        deflates rescue credit. So this is deliberately NOT the exact mirror of single-attacker
        :meth:`turns_to_ko`.

        The BENCH leg asks the shared-budget question instead: the first ``t`` at which ``my_body``
        falls in the :meth:`bench_harvest` of ``t`` allocated payloads. The two areas never contend —
        printed damage always lands on the Active and riders always on the Bench — so they are
        independent by card mechanics rather than by assumption.

        ``my_bench`` / ``key_ids`` / ``reading`` are the harvest inputs; omitting ``my_bench`` reads
        the body ALONE, which reproduces the per-body answer for an undeclared caller, and the
        default ``reading`` is the conservative one. Removing an opponent body can only RAISE the
        result, so the Δ across a removal is the turns of survival bought.

        Returns the INTEGER reading. :meth:`survival_clock` runs the identical accumulation and
        additionally reports where INSIDE that turn the crossing falls; this method is defined as
        its ``.turns`` field, so the two readings cannot disagree."""
        return self.survival_clock(
            my_body, opp_bodies, charged=charged, max_t=max_t, context=context,
            my_benched=my_benched, my_bench=my_bench, key_ids=key_ids, reading=reading,
            opp_active=opp_active, switch_enabler=switch_enabler).turns

    def survival_clock(self, my_body: dict | None, opp_bodies, *, charged: dict | None = None,
                       max_t: int = 8, context: dict | None = None, my_benched: bool = False,
                       my_bench=(), key_ids=frozenset(), reading: str = HARVEST_POSSIBLE,
                       opp_active: dict | None = None,
                       switch_enabler: bool = False) -> SurvivalClock:
        """:meth:`turns_to_ko_me`'s accumulation, reported at BOTH resolutions — see
        :class:`SurvivalClock` for what each field means and why the fractional one exists.

        Same arguments, same semantics, same answer in ``.turns``. The only addition is ``.exact``,
        the interpolated crossing point, which is arithmetic over values this loop already
        produces (``dealt``, ``incoming(t)``, ``hp``) — no new constant and no second oracle, so
        there is nothing that could drift from the integer beside it.

        The BENCH leg has no accumulation of its own to interpolate: :meth:`bench_harvest_clock`
        answers a shared-budget ALLOCATION question in whole turns, and there is no running total
        whose crossing could be read finer. It reports ``exact == turns``, which is honest rather
        than lossy — that precision was never computed there in the first place. If the bench leg
        ever needs the same discrimination, the fix is to widen the harvest clock, not to
        manufacture a fraction here."""
        hp = (my_body or {}).get("hp", 0)
        if not hp:
            return SurvivalClock(max_t + 1, float(max_t + 1))
        if hp < 0:
            # A NEGATIVE hp is already past dead, and the accumulation cannot interpolate a crossing
            # it started on the far side of — `dealt >= hp` is true at t=1 before anything is dealt,
            # so the divisor would be the turn's zero damage. The integer route answered 1 here
            # before ADR-0117 and still must: this is the byte-identical guarantee, and a
            # regression to ZeroDivisionError on a body the caller already knows is dead is not a
            # sharper answer, just a louder one.
            return SurvivalClock(1, 1.0)
        horizon = max(1, int(max_t))
        if my_benched:
            bench = list(my_bench) or [my_body]
            try:
                me = next(i for i, b in enumerate(bench) if b is my_body)
            except StopIteration:                     # not in the snapshot — read it alone
                bench, me = [my_body], 0
            clock = self.bench_harvest_clock(bench, opp_bodies, charged=charged, max_t=horizon,
                                             key_ids=key_ids, reading=reading,
                                             opp_active=opp_active)
            turns = clock.get(me, horizon + 1)
            return SurvivalClock(turns, float(turns))
        dealt = 0
        for t in range(1, horizon + 1):
            hit = self.incoming(my_body, opp_bodies, t, charged=charged, context=context,
                                opp_active=opp_active, switch_enabler=switch_enabler)
            dealt += hit
            if dealt >= hp:
                # ``hit`` is necessarily > 0 here — the running total was BELOW ``hp`` before it
                # (0 at t=1, and ``hp`` is non-zero above), so ``hit`` is what crossed. A guard
                # would only hide a future change to that invariant, so there isn't one.
                return SurvivalClock(t, (t - 1) + (hp - (dealt - hit)) / hit)
        return SurvivalClock(horizon + 1, float(horizon + 1))
