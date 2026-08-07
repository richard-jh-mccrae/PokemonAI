"""Everything that pays an attack cost: what is attached, what the hand and the accelerators could supply.

A Function Tag says a card MIGHT supply Energy; an Effect Clause says how much (ADR-0067). An untagged
card is never even inspected."""
from __future__ import annotations


from collections import Counter

from common.board_cards import body_unit_codes, card_id as body_card_id
from common.strategy.combat_math.budget import (AttachUnit, Budget, DISCARD_SUPPLY, WILD_CODE, _AttachCtx,
                                                _Contribution, _RECUR_RELOAD_CAP, _can_pay, _matched_slots,
                                                unit_colours,
                                                units_for_codes)
from common.strategy.combat_math.policy import UNCHARGED


_ACCEL_TAGS = frozenset({"tutor_energy", "energy_accel"})


class EnergyMixin:
    """What Energy a body has, and what it could still get."""

    #: **Energy UNIT** codes attached to a body (``Pokemon.energies``) — NOT card ids; the cards-vs-units
    #: split lives in :mod:`common.board_cards` (Issue #297).
    attached_unit_codes = staticmethod(body_unit_codes)

    #: ``EnergyType`` UNIT codes as Budget units — see :func:`units_for_codes`.
    units_for_codes = staticmethod(units_for_codes)

    def attached_type_counts(self, target: dict) -> dict:
        """{EnergyType: count} of the SPECIFIC-colour Energy attached to ``target``. A COLORLESS or
        multi-colour unit counts under nothing — the residual is ``len(energies) - sum(counts.values())``."""
        counts: Counter = Counter()
        for code in self.attached_unit_codes(target):
            colours = unit_colours(code)
            if len(colours) == 1 and 0 not in colours:
                counts[next(iter(colours))] += 1
        return counts

    def attack_type_payable(self, aid, target: dict | None, *, extra_type=None,
                            extra_units: int = 0, wild_units: int = 0) -> bool:
        """Sound-or-silent TYPE affordability on top of the count check. ``wild_units`` are attaches of
        UNKNOWN type (fail-OPEN); True whenever the attack record doesn't resolve — never a false suppression."""
        ast = self.attack_stat(aid)
        types = getattr(ast, "energyTypes", ()) if ast else ()
        need = Counter(t for t in types if t not in (0, None))
        if not need or target is None:
            return True
        attached = self.attached_type_counts(target)
        # ``extra_type`` counts as typed coverage only when it names exactly one SPECIFIC colour —
        # `provision_codes_or_floor` can hand this leg ``WILD_CODE`` (Issue #418).
        specific = unit_colours(extra_type) - {0} if extra_type is not None else frozenset()
        if len(specific) == 1 and extra_units > 0:
            attached = attached.copy()
            attached[next(iter(specific))] += extra_units
        unresolved = sum(1 for code in self.attached_unit_codes(target)
                         if len(unit_colours(code)) != 1)
        missing = sum(max(0, n - attached.get(t, 0)) for t, n in need.items())
        return missing <= wild_units + unresolved

    def attach_budget(self, target: dict | None, hand_ids, *, energy_attached: bool = False,
                      supporter_played: bool = False, deck_energy_types=(),
                      hand_energy_types=(), discard_energy_counts=None,
                      target_benched: bool = False, more_prizes_than_opp: bool = False) -> Budget:
        """This turn's FULL Energy-attach capacity toward ``target`` — the **Attach Budget**. Yield fails
        CLOSED, deck presence fails OPEN (ADR-0067). Zone facts arrive as arguments: no Board, no Pilot."""
        ctx = _AttachCtx(deck=frozenset(deck_energy_types or ()),
                         discard=dict(discard_energy_counts or {}),
                         benched=bool(target_benched), more_prizes=bool(more_prizes_than_opp))
        target_stat = self._card_stat((target or {}).get("id"))
        items, supporters = [], []
        for group, cid in enumerate(hand_ids or ()):
            contrib = self._attach_contribution(cid, group, target_stat, ctx)
            if contrib is not None:
                (supporters if contrib.is_supporter else items).append(contrib)
        playsets = [items] + ([] if supporter_played else [items + [s] for s in supporters])

        caps = {DISCARD_SUPPLY: dict(ctx.discard)}
        caps.update({c.group: c.cap for c in items + supporters if c.group is not None})

        special = self._special_energy_groups(hand_ids, target_stat)
        options = set()
        for playset in playsets:
            # The manual attach plays exactly ONE source, but a source is a GROUP: a Basic Energy is
            # one unit, a Special Energy is however many its provision prints (Issue #142).
            groups = [(AttachUnit(frozenset(hand_energy_types)),)] if hand_energy_types else []
            groups += [(u,) for c in playset for u in c.hand_yields]
            groups += list(special)
            manual = [()] if energy_attached else [()] + groups
            effect = tuple(u for c in playset for u in c.effect_units)
            options.update(effect + m for m in manual)
        return Budget(options=tuple(sorted(options, key=lambda o: (-len(o), str(o)))), caps=caps)

    def _special_energy_groups(self, hand_ids, target_stat) -> tuple:
        """Manual-attach source groups for the SPECIAL Energy in hand — one group per card, sized by its
        `provides:N` tag. Fail-CLOSED on an untagged card, an unknown stat or an unknown target."""
        if target_stat is None or not self.functions:
            return ()
        groups = []
        for cid in (hand_ids or ()):
            stat = self._card_stat(cid)
            if stat is None or not stat.is_special_energy:
                continue
            codes = self.provision_codes(cid, target_stat)
            if not codes:                      # unreadable (None) or a zero claim — no group either way
                continue
            groups.append(units_for_codes(codes))
        return tuple(groups)

    def _attach_contribution(self, card_id, group: int, target_stat, ctx: _AttachCtx):
        """What one hand card offers the Budget, or None if it offers nothing (fail-CLOSED)."""
        tags = frozenset(self.functions.tags(card_id)) if self.functions else frozenset()
        stat = self._card_stat(card_id)
        if not (tags & _ACCEL_TAGS) or stat is None or not (stat.is_item or stat.is_supporter):
            return None                        # untagged, unknown, or a Pokémon (attack-based accel)
        clauses = self.effects.clauses(card_id) if self.effects else ()
        gid = group if any(cl.get("distinct_types") for cl in clauses) else None
        effect = [u for cl in clauses for u in self._accel_units(cl, target_stat, ctx, gid)]
        yields = [u for cl in clauses for u in self._hand_yield_units(cl, target_stat, ctx, gid)]
        # A "of DIFFERENT types" card yielding fewer units than it prints does not say WHICH half is
        # lost. Ruled fail-CLOSED (ADR-0067): the HAND half survives, so the unit needs the manual attach.
        while (gid is not None and effect
               and len(effect) + len(yields) > len(self._palette(effect + yields))):
            effect.pop()
        if not (effect or yields):
            return None
        cap = {t: 1 for t in self._palette(effect + yields)} if gid is not None else {}
        return _Contribution(stat.is_supporter, tuple(effect), tuple(yields), gid, cap)

    @staticmethod
    def _palette(units) -> frozenset:
        """Every colour the card's units could take — the width of its distinct-types capacity."""
        return frozenset(t for u in units for t in u.types)

    @staticmethod
    def _unit_groups(source, group) -> tuple:
        """The capacity groups a unit answers to: its card's distinct-types group (when it has one)
        and, for anything drawn from the public discard, the shared pile."""
        return tuple(g for g in (group, DISCARD_SUPPLY if source == "discard" else None)
                     if g is not None)

    def _accel_units(self, clause: dict, target_stat, ctx: _AttachCtx, group) -> tuple:
        """Units an ``accel`` clause attaches BY ITS EFFECT — independent of the manual attach."""
        if clause.get("kind") != "accel" or not self._accel_target_ok(clause, target_stat, ctx):
            return ()
        condition = clause.get("condition")
        if condition is not None and not ctx.condition_met(condition):
            return ()
        source = clause.get("source")
        pool = self._clause_pool(ctx.source_types(source), clause.get("energy_type"))
        groups = self._unit_groups(source, group)
        return tuple(AttachUnit(pool, groups, source)
                     for _ in range(int(clause.get("amount") or 0))) if pool else ()

    def _hand_yield_units(self, clause: dict, target_stat, ctx: _AttachCtx, group: int) -> tuple:
        """Units a clause puts in HAND rather than attaching — playable only via the turn's ONE manual
        attach, so they compete for it instead of summing."""
        kind = clause.get("kind")
        source = clause.get("source")
        if kind == "accel":
            if not self._accel_target_ok(clause, target_stat, ctx):
                return ()
            condition = clause.get("condition")
            if condition is not None and not ctx.condition_met(condition):
                return ()
            pool = self._clause_pool(ctx.source_types(source), clause.get("energy_type"))
            amount = int(clause.get("to_hand") or 0)
        elif kind == "fetch" and clause.get("zone") == "deck":
            if clause.get("target") not in ("basic_energy", "energy"):
                return ()                      # a Pokémon/Trainer fetch is no Energy at all
            from common.fetch_closure import fetch_is_unconditional
            if not fetch_is_unconditional(clause):
                return ()          # a dig / gated / undecidable find is no promise of a unit at all
            # `amount` is deliberately NOT read: these units compete for the ONE manual attach rather
            # than summing, and on a `choice` clause the amount is a cap SHARED with a non-Energy leg.
            pool, source = self._clause_pool(ctx.deck, clause.get("energy_type")), "deck"
            amount = 1
        else:
            return ()
        return tuple(AttachUnit(pool, self._unit_groups(source, group), source)
                     for _ in range(amount)) if pool else ()

    @staticmethod
    def _clause_pool(available: frozenset, energy_type) -> frozenset:
        """The colours a clause can actually deliver: its source zone's, narrowed by a type lock."""
        return available if energy_type is None else available & {energy_type}

    @staticmethod
    def _accel_target_ok(clause: dict, target_stat, ctx: _AttachCtx) -> bool:
        """May this ``accel`` clause legally attach to the body being budgeted? Fail-CLOSED on an unknown
        body or an unmodelled target class — a restricted accel never funds a body it cannot reach."""
        if target_stat is None:
            return False
        target_type = clause.get("target_type")
        if target_type is not None and getattr(target_stat, "energyType", None) != target_type:
            return False
        target = clause.get("target")
        if target in (None, "any_pokemon"):
            return True
        if target == "stage2":
            return bool(getattr(target_stat, "stage2", False))
        if target == "benched":
            return ctx.benched
        return False

    def _attached_units(self, body: dict | None) -> tuple:
        """The Energy already ON the body, as Budget units — one per **Energy Unit**, carrying the colours
        it can pay. A colourless unit pays colourless slots only; an unrecognised code is wild (fail-open)."""
        return units_for_codes(self.attached_unit_codes(body))

    def _attack_slots(self, attack_id) -> tuple:
        """An attack's per-slot cost as EnergyType codes; () when no record resolves OR the cost is
        0 (the pinned unknown/0-cost quirk) — the caller then makes no claim."""
        ast = self.attack_stat(attack_id)
        if ast is None:
            return ()
        return tuple(ast.energyTypes) or (0,) * int(ast.cost or 0)

    def reachable_attach(self, my_body: dict | None, attack_id=None, *, budget: Budget) -> bool:
        """Can ``my_body`` PAY (and legally use) an attack THIS turn under ``budget``? ``attack_id`` None
        asks the FAMINE question (is ANY attack reachable). Fail-CLOSED; attack locks honoured (ADR-0033)."""
        stat = self._card_stat((my_body or {}).get("id"))
        if stat is None or budget is None:
            return False
        grant = self._grant(my_body) or {}
        if grant.get("self_lock"):
            return False
        attack_ids = (attack_id,) if attack_id is not None else tuple(stat.attacks or ())
        attached = self._attached_units(my_body)
        return any(_can_pay(slots, attached + tuple(option), budget.caps)
                   for aid in attack_ids if aid != grant.get("same_lock")
                   for slots in (self._attack_slots(aid),) if slots
                   for option in budget.options)

    def reachable_attach_p(self, my_body: dict | None, attack_id=None, *, budget: Budget,
                           p_by_type=None) -> float:
        """The EV reading of :meth:`reachable_attach`: P(``my_body`` can pay an attack this turn), best
        attack by probability (ADR-0074 decision 6). RANKED consumers only; a gate takes the boolean."""
        stat = self._card_stat((my_body or {}).get("id"))
        if stat is None or budget is None:
            return 0.0
        grant = self._grant(my_body) or {}
        if grant.get("self_lock"):
            return 0.0
        if not p_by_type:
            return 1.0 if self.reachable_attach(my_body, attack_id, budget=budget) else 0.0
        attack_ids = (attack_id,) if attack_id is not None else tuple(stat.attacks or ())
        attached = self._attached_units(my_body)
        best = 0.0
        for aid in attack_ids:
            if aid == grant.get("same_lock"):
                continue
            slots = self._attack_slots(aid)
            if not slots:
                continue                       # unresolvable cost makes NO claim, either direction
            p = budget.realising_p(slots, p_by_type, attached=attached)
            if p > best:
                best = p
                if best >= 1.0:
                    break
        return best

    def provision_codes(self, card_id, holder_stat) -> tuple | None:
        """**The provision seam** (Issue #418): the ``EnergyType`` UNIT codes attaching this Energy CARD
        puts on ``energies`` for THIS ``holder_stat``. ``()`` = a Tool, claiming zero; ``None`` = unreadable."""
        stat = self._card_stat(card_id)
        if stat is None:
            return None
        if stat.is_tool:
            return ()
        colour = getattr(stat, "energyType", None)
        if colour is None:
            return None
        if stat.is_basic_energy:
            return (int(colour),)
        count = (self.functions.energy_provision(
            card_id, evolution=getattr(holder_stat, "evolvesFrom", None) is not None)
            if self.functions is not None else 0)
        return (int(colour),) * int(count) if count > 0 else None

    def provision_codes_or_floor(self, card_id, holder_stat) -> tuple:
        """:meth:`provision_codes` with a FLOOR for an unreadable provision: ONE unit, of the card's own
        colour when known else :data:`WILD_CODE`. The DECIDER's arity — pricing an attach at zero lies."""
        codes = self.provision_codes(card_id, holder_stat)
        if codes is not None:
            return codes
        colour = getattr(self._card_stat(card_id), "energyType", None)
        return (WILD_CODE,) if colour is None else (int(colour),)

    def restage_energy(self, body: dict | None, holder_stat) -> dict | None:
        """``body`` as its attached Energy CARDS render on a DIFFERENT holder stage (Issue #418) —
        ``holder_stat`` is the stage to re-read AGAINST. Returns ``body`` by identity when unreadable."""
        entries = tuple((body or {}).get("energyCards") or ())
        if not entries:
            return body                        # nothing to re-derive from; the units stand as given
        was = self._card_stat((body or {}).get("id"))
        before, after = [], []
        for entry in entries:
            cid = body_card_id(entry)
            old, new = self.provision_codes(cid, was), self.provision_codes(cid, holder_stat)
            if old is None or new is None:
                return body                    # fail-CLOSED: an unreadable card decides nothing
            before.extend(old)
            after.extend(new)
        if tuple(before) != tuple(body_unit_codes(body)):
            return body                        # the model already disagrees with this board
        return dict(body, energies=after) if tuple(after) != tuple(before) else body

    @staticmethod
    def wild_units(count: int = 1) -> tuple:
        """``count`` UNTYPED Budget units — Energy whose colour is not yet chosen. Each pays any one slot:
        fail-OPEN, exactly as :meth:`attack_type_payable` treats an unresolvable attached Energy."""
        return tuple(AttachUnit(frozenset()) for _ in range(max(0, int(count))))

    def matched_slots(self, my_body: dict | None, attack_id, *, extra_units=()) -> tuple:
        """``(matched, total)`` typed cost slots of ``attack_id`` that ``my_body``'s attached Energy plus
        ``extra_units`` covers (ADR-0069 §3). ``(0, 0)`` when no cost record resolves — no typed claim."""
        slots = self._attack_slots(attack_id)
        if not slots:
            return (0, 0)
        units = self._attached_units(my_body) + tuple(extra_units)
        return (_matched_slots(slots, units), len(slots))

    def without_expiring_energy(self, body: dict | None) -> dict | None:
        """``body`` once the rules discard its EVAPORATING Energy (Issue #286). Card identity comes from
        ``energyCards``, NEVER ``energies`` (units, not cards). Fail-CLOSED per card; identity if none left."""
        entries = tuple((body or {}).get("energyCards") or ())
        holder = self._card_stat((body or {}).get("id"))
        if not entries or self.effects is None or self.functions is None or holder is None:
            return body
        units, keep, dropped = list(body_unit_codes(body)), [], 0
        for entry in entries:
            cid = body_card_id(entry)
            clauses = self.effects.clauses(cid) if cid is not None else ()
            removed = 0
            if any(cl.get("rider") == "discard_eot" for cl in (clauses or ())):
                for code in (self.provision_codes(cid, holder) or ()):
                    if code in units:
                        units.remove(code)
                        removed += 1
            # The card STAYS unless its units actually left — dropping it while its units survive would
            # hand the caller a body whose two Energy keys disagree. Per-CARD: `dropped` can't see a no-op.
            if not removed:
                keep.append(entry)
            dropped += removed
        if not dropped:
            return body                       # identity: nothing expires, nothing is re-keyed
        return dict(body, energies=units, energyCards=keep)

    def _evolve_accel(self, stat) -> tuple:
        """``(EnergyType, units)`` an ON-EVOLVE deck-search Ability attaches to the form being evolved
        INTO (Issue #257). Effect-Clause-quantified, fail-CLOSED; ONLY the on-evolve trigger is credited."""
        if stat is None or self.functions is None or self.effects is None:
            return (None, 0)
        cid = getattr(stat, "cardId", None)
        if cid is None or not (_ACCEL_TAGS & frozenset(self.functions.tags(cid))):
            return (None, 0)                          # untagged: never even inspected
        for cl in (self.effects.clauses(cid) or ()):
            if (cl.get("kind") == "accel" and cl.get("trigger") == "on_evolve"
                    and cl.get("source") == "deck" and cl.get("target") == "own_line"):
                etype, units = cl.get("energy_type"), int(cl.get("amount") or 0)
                if etype is not None and units > 0:
                    return (etype, units)
        return (None, 0)

    def _affords(self, stat, form_body, aid, attached: int, t: int, charged, *,
                 is_current: bool) -> bool:
        """Whether ``aid`` is payable at turn ``t`` under the ``charged`` policy (see :meth:`incoming`).
        Per-FORM under the ceiling; :data:`UNCHARGED` is per-form too but fail-OPEN on an unresolvable cost."""
        if charged == UNCHARGED:                      # doom: fail-OPEN on an unresolvable cost
            return (getattr(stat, "minAttackCost", None) or 0) <= attached + t
        if charged is None:                           # ceiling: pay cheapest, credit anything
            return bool(stat.can_pay_cheapest(attached + t))
        base = charged.get("base_attach", 1)
        # The Ignition-class colourless burst lands its full {C}{C}{C} only on an Evolution. A
        # single-card allowance, so it is flat in the turn count, never scaled by ``t``.
        burst = charged.get("burst_on_evo", 0) if getattr(stat, "evolvesFrom", None) else 0
        wild = t * base
        # Their ON-EVOLVE deck-search Ability (Issue #257) — the hop is the trigger, so a current form
        # never earns it. TYPED and flat in ``t``. CHARGED only: the ceiling already credits everything.
        acc_type, acc_units = (None, 0) if is_current else self._evolve_accel(stat)
        if self.attack_cost(aid) > attached + wild + burst + acc_units:
            return False
        return bool(self.attack_type_payable(aid, form_body, wild_units=wild,
                                             extra_type=acc_type, extra_units=acc_units))

    def discard_recur_fuel(self, body: dict | None, opp_discard_energy: dict | None, *,
                           forward_ids=None, scope: str = "any") -> int:
        """The extra Basic Energy a `discard_energy_recur` line can reload from the opponent's DISCARD next
        turn. ``scope``: "any" = could it refuel at all (fail-OPEN caution); "self_arming" = a clock input."""
        if not (self.functions and self.stats) or not opp_discard_energy:
            return 0
        st = self._card_stat((body or {}).get("id"))
        if st is None:
            return 0
        fwd = forward_ids if forward_ids is not None else self.forward_card_ids
        forward_stats = [self._card_stat(f) for f in (fwd(st.cardId) or ())]
        forms = [st, *forward_stats]
        recur = next((s for s in forms if s is not None
                      and "discard_energy_recur" in self.functions.tags(s.cardId)), None)
        if recur is None or recur.energyType is None:
            return 0
        cap = _RECUR_RELOAD_CAP
        if scope == "self_arming":
            clause = self._energy_recur_clause(recur.cardId)
            if clause is None:
                return 0                              # no clause, no claim (fail-CLOSED on yield)
            if clause.get("trigger") != "on_evolve" or clause.get("target") == "bench_only":
                return 0                              # the reload does not reach this body's cost
            if recur is st:
                return 0                              # the hop already happened — it fires once
            cap = min(cap, int(clause.get("amount") or 0))
        return min(int(opp_discard_energy.get(recur.energyType, 0)), cap)

    def _energy_recur_clause(self, card_id) -> dict | None:
        """The card's ``energy_recur`` Effect Clause (amount / trigger / target scope), or None when
        the compendium has nothing for it — the fail-CLOSED read a yield question must take."""
        if self.effects is None:
            return None
        return next((c for c in (self.effects.clauses(card_id) or ())
                     if c.get("kind") == "energy_recur"), None)
