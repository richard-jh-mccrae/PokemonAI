"""Everything that pays an attack cost: what is attached, what the hand and the accelerators could still supply, and what
a special Energy provides.

A Function Tag says a card MIGHT supply Energy; an Effect Clause says how much (ADR-0067). An untagged card is never
even inspected."""
from __future__ import annotations


from collections import Counter

from common.board_cards import body_unit_codes, card_id as body_card_id
from common.strategy.combat_math.budget import (AttachUnit, Budget, DISCARD_SUPPLY, WILD_CODE, _AttachCtx,
                                                _Contribution, _RECUR_RELOAD_CAP, _can_pay, _matched_slots,
                                                unit_colours,
                                                units_for_codes)
from common.strategy.combat_math.policy import UNCHARGED


_ACCEL_TAGS = frozenset({"tutor_energy", "energy_accel"})   # the Function-Tag ROUTING gate of the
                           # Attach Budget: a tag says a card MIGHT supply Energy, an Effect Clause
                           # says how much (ADR-0067) — an untagged card is never even inspected


class EnergyMixin:
    """What Energy a body has, and what it could still get."""

    # --- typed affordability ---------------------------------------------------------------
    #: The **Energy Units** attached to a body, as ``EnergyType`` codes — the engine's
    #: ``Pokemon.energies``, read as what it is (Issue #297).
    #:
    #: Bound here so the typed-affordability family has ONE name for it:
    #: :meth:`attached_type_counts`, :meth:`attack_type_payable` and :meth:`_attached_units` used to
    #: be three separate walks that each fed the code to :meth:`_card_stat` **as a card id** — an
    #: identity round-trip that returned the right colour for codes 1-8 purely because the eight
    #: Basic Energy card ids equal their type codes, and that mis-answered every other code (0
    #: became "unresolvable, therefore wild"; 9-11 resolved to a Special Energy card whose own
    #: ``energyType`` is 0 and counted as nothing).
    #:
    #: The implementation lives in :mod:`common.board_cards` beside the CARD walk, because the two
    #: are one distinction and a body-shape read has one home.
    attached_unit_codes = staticmethod(body_unit_codes)

    #: ``EnergyType`` UNIT codes as Budget units — see :func:`units_for_codes`. Exposed on the oracle
    #: because the Pilot and the planner reach every card fact through their `CombatMath` handle.
    units_for_codes = staticmethod(units_for_codes)

    def attached_type_counts(self, target: dict) -> dict:
        """{EnergyType: count} of the SPECIFIC-colour Energy attached to ``target``.

        A unit that names exactly one colour (``GRASS``..``DRAGON``) counts under it. A COLORLESS
        unit does not — it pays a colourless slot only, which no entry here can express. Neither
        does a multi-colour unit (``RAINBOW``, ``TEAM_ROCKET``): a histogram cannot say "either", so
        crediting one of its colours would be a claim the unit does not support. Both are visible to
        the consumers that need them as the residual ``len(energies) - sum(counts.values())``, and
        exactly in :meth:`_attached_units`, which prices per-slot rather than per-colour."""
        counts: Counter = Counter()
        for code in self.attached_unit_codes(target):
            colours = unit_colours(code)
            if len(colours) == 1 and 0 not in colours:
                counts[next(iter(colours))] += 1
        return counts

    def attack_type_payable(self, aid, target: dict | None, *, extra_type=None,
                            extra_units: int = 0, wild_units: int = 0) -> bool:
        """Sound-or-silent TYPE affordability on top of the count check: every SPECIFIC-type slot
        of ``aid``'s cost (``AttackStat.energyTypes``) must be covered by the target's attached
        typed Energy, plus ``extra_units`` of ``extra_type`` when that is a specific type — a
        colourless/special extra (type 0/None, e.g. Ignition's {C}{C}{C}) pays colourless slots
        only — plus ``wild_units`` hypothetical attaches of UNKNOWN type, each able to cover any
        one specific slot (fail-open: the hand/deck might supply the needed type). True whenever the
        attack record doesn't resolve (the count check stays the sole authority — never a false
        suppression).

        An attached unit that names no single colour joins ``wild_units`` rather than ``attached``,
        because this coarse arithmetic has no way to say "either of two" — a ``RAINBOW`` really does
        pay any one slot, a ``TEAM_ROCKET`` pays one of two, and crediting both as one wild unit is
        the fail-open direction this method already documents. A ``COLORLESS`` unit is NOT among
        them (Issue #297): it pays colourless slots only, which this method's ``need`` has already
        filtered out, so it must contribute nothing here. It used to contribute a wild unit — an
        attached Ignition Energy handed a typed line three units it cannot legally pay with — for no
        better reason than that ``_card_stat(0)`` is None. The exact per-slot assignment lives in
        :meth:`reachable_attach` over :meth:`_attached_units`, which keeps the full colour set."""
        ast = self.attack_stat(aid)
        types = getattr(ast, "energyTypes", ()) if ast else ()
        need = Counter(t for t in types if t not in (0, None))
        if not need or target is None:
            return True
        attached = self.attached_type_counts(target)
        # The EXTRA's colour is read the way every other colour in this module is read — through
        # :func:`unit_colours` — so ``extra_type`` obeys the same rule the paragraph above states for
        # an ATTACHED unit: it counts as typed coverage only when it names exactly one SPECIFIC
        # colour. Behaviour-identical to the older ``extra_type not in (None, 0)`` test on every code
        # the enum has (COLORLESS resolves to {0}, which ``need`` has already filtered out; RAINBOW,
        # TEAM_ROCKET and an unknown code named a key ``need`` never queries, so each contributed
        # nothing then and contributes nothing now) — but true by construction rather than by
        # arithmetic accident, which matters now that `provision_codes_or_floor` can hand this leg
        # ``WILD_CODE`` for an Energy whose colour could not be pinned down (Issue #418).
        specific = unit_colours(extra_type) - {0} if extra_type is not None else frozenset()
        if len(specific) == 1 and extra_units > 0:
            attached = attached.copy()
            attached[next(iter(specific))] += extra_units
        unresolved = sum(1 for code in self.attached_unit_codes(target)
                         if len(unit_colours(code)) != 1)
        missing = sum(max(0, n - attached.get(t, 0)) for t, n in need.items())
        return missing <= wild_units + unresolved

    # --- reachable Attach: MY next DEVELOPMENT step (issue #137 / ADR-0067) -----------------
    def attach_budget(self, target: dict | None, hand_ids, *, energy_attached: bool = False,
                      supporter_played: bool = False, deck_energy_types=(),
                      hand_energy_types=(), discard_energy_counts=None,
                      target_benched: bool = False, more_prizes_than_opp: bool = False) -> Budget:
        """This turn's FULL Energy-attach capacity toward ``target`` — the **Attach Budget**.

        Enumerates the manual attach (iff ``energy_attached`` is False) plus the attach EFFECT of
        every PLAYABLE accel/tutor card in ``hand_ids``, each at its **Effect-Clause-quantified**
        yield — never a flat ``+1`` (that under-read IS the f70 bug: Crispin attaches one Basic by
        its effect AND hands a second of a different type the manual attach then plays, reaching a
        2-cost typed attack from zero).

        Two epistemics, split by what is uncertain (ADR-0067):
        - **Yield fails CLOSED.** Function Tags only ROUTE (``_ACCEL_TAGS``); the amounts, source
          zone, target restriction and play conditions come from Effect Clauses. An unmodelled
          clause kind, target class, source zone or condition contributes **zero** — the oracle
          never guesses a yield, so a PROVABLE famine still fires its stall.
        - **Deck presence fails OPEN.** ``deck_energy_types`` is the *not-provably-empty* typed
          set (the sound emptiness oracle, per type), not a provably-present one: with a thin
          3-copy Energy suite nothing is provable before a search anchors the prizes, and a strict
          gate would re-fire the very famine this exists to kill. The honest hypergeometric lives
          in :meth:`readiness_p` alone.

        Quotas are structural, never a branch thicket: Items all play; each Supporter is a separate
        alternative play-set (one Supporter per turn — a tutor Supporter and the manual attach CAN
        co-occur, two Supporters cannot); and the single manual attach plays exactly ONE Energy
        source (an Energy already in hand, or one a played card fetched there).

        A Pokémon-borne accel is deliberately never counted: its acceleration is an ATTACK
        (Cinderace's Turbo Flare), and attacking ends the turn, so it can never fund another
        attack this turn — the self-side mirror of ADR-0064's attack-based-accel exclusion.

        Zone facts arrive as ARGUMENTS (no Board, no Pilot). ``deck_energy_types`` /
        ``hand_energy_types`` are EnergyType codes; ``discard_energy_counts`` is a
        ``{EnergyType: count}`` map — the discard is PUBLIC, so its yields are capped at the
        supply really sitting there (two Wondrous Patches over one {P} is one attach), while the
        hidden deck stays a type set. ``target_benched`` places the body for a bench-restricted
        clause, and ``more_prizes_than_opp`` answers Rosa's Encouragement's prize gate.
        """
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
            # one unit, a Special Energy is however many its provision prints (#142).
            groups = [(AttachUnit(frozenset(hand_energy_types)),)] if hand_energy_types else []
            groups += [(u,) for c in playset for u in c.hand_yields]
            groups += list(special)
            manual = [()] if energy_attached else [()] + groups
            effect = tuple(u for c in playset for u in c.effect_units)
            options.update(effect + m for m in manual)
        return Budget(options=tuple(sorted(options, key=lambda o: (-len(o), str(o)))), caps=caps)

    def _special_energy_groups(self, hand_ids, target_stat) -> tuple:
        """Manual-attach source groups for the SPECIAL Energy in hand — one group per card, sized by
        its `provides:N` Function Tag and coloured by its ``energyType`` (#142).

        A Special Energy is not one unit of its own colour, so the hand leg's typed-Basic count
        cannot see it: Ignition Energy provides {C}{C}{C} on an Evolution, which is a Mega Starmie ex
        armed from ZERO by a single attach. Left unmodelled it is a FALSE FAMINE on a shipped deck —
        the same bug class as the retired `+1`, one zone over.

        Colour follows :meth:`_attached_units` exactly, so a hypothetical attach and the real board
        it models agree: a colourless provision carries ``{0}`` and pays colourless slots only. Since
        Issue #418 that is a fact rather than a promise — both sides now compose the provision
        through :meth:`provision_codes` and the colour through :func:`units_for_codes`, where before
        this leg spelled the pool ``frozenset({etype})`` and so disagreed with the attached side on
        RAINBOW and TEAM_ROCKET.

        Fail-CLOSED on an untagged card, an unknown stat or an unknown target."""
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
        # "of DIFFERENT types" bounds the card two ways. Its per-COLOUR half is the group cap below
        # (two units can never share a colour). Its COUNT half must be settled here, because when a
        # card yields fewer units than it prints, the card text does not say WHICH half is lost.
        #
        # Crispin over a deck down to one not-provably-empty colour finds ONE Energy — and "put 1 of
        # them into your hand. Attach the other" leaves it open whether that lone card is the
        # put-in-hand half or the attach half. Ruled FAIL-CLOSED (ADR-0067, grilled 2026-07-24): the
        # HAND half survives, so the unit needs the turn's manual attach and is worth nothing once
        # that is spent. The braver reading would have the card attach by itself with the attach
        # already gone — a claim no source settles, in the direction ADR-0067 forbids guessing in.
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
        """Units a clause puts in HAND rather than attaching — playable only via the turn's ONE
        manual attach, so they compete for it instead of summing.

        Two shapes: an ``accel`` clause's ``to_hand`` rider (Crispin's "put 1 of them into your
        hand" half — carried HERE and not as a ``fetch`` clause, because a ``fetch`` row would
        re-arm the gamble energy-closure that `effect_overrides.json` deliberately excludes it
        from), and a plain deck ``fetch`` of an Energy (Fighting Gong's {F}-locked search, Hilda).
        A ``to_hand`` rider rides its clause's own target/condition gates: an accel the body can't
        legally receive is not played for its hand half either."""
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
            # The clause's `amount` is deliberately NOT read: these units compete for the turn's ONE
            # manual attach rather than summing, so a second unit of the same pool buys the budget
            # nothing, and on a `choice` clause (Bug Catching Set) the amount is a cap SHARED with a
            # non-Energy leg that may consume all of it.
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
        """May this ``accel`` clause legally attach to the body being budgeted? Fail-CLOSED on an
        unknown body or an unmodelled target class — a restricted accel never funds a body it
        cannot reach (Wondrous Patch is BENCHED-{P}-only; Rosa's Encouragement is Stage-2-only)."""
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
        """The Energy already ON the body, as Budget units — one per **Energy Unit**, carrying the
        colours that unit can pay (:func:`unit_colours`).

        A typed Basic keeps its colour, a colourless one pays colourless slots only, a RAINBOW or an
        unrecognised code is wild (fail-open, exactly as :meth:`attack_type_payable` treats it).
        This is the read `_special_energy_groups` says it mirrors — *"a colourless provision carries
        ``{0}`` and pays colourless slots only"* — and until Issue #297 it did not: the colour came
        from feeding an ``EnergyType`` code to the card table, so the one Energy the contract names
        got ``frozenset()`` (wild) attached and ``{0}`` in hand."""
        return units_for_codes(self.attached_unit_codes(body))

    def _attack_slots(self, attack_id) -> tuple:
        """An attack's per-slot cost as EnergyType codes; () when no record resolves OR the cost is
        0 (the pinned unknown/0-cost quirk) — the caller then makes no claim."""
        ast = self.attack_stat(attack_id)
        if ast is None:
            return ()
        return tuple(ast.energyTypes) or (0,) * int(ast.cost or 0)

    def reachable_attach(self, my_body: dict | None, attack_id=None, *, budget: Budget) -> bool:
        """Can ``my_body`` PAY (and legally use) an attack THIS turn under ``budget``? — the
        self-side mirror of :meth:`reachable_incoming` (ADR-0064), the **Reachable Attach** oracle.

        ``attack_id`` None asks the FAMINE question: is ANY attack reachable? (Scanning all attacks
        rather than the cheapest-by-count is what makes the boolean sound once types matter — a
        cheap ``{F}{F}`` can be unpayable while a dearer ``●●●`` is not.) So a famine — the premise
        the stall-gust family had wrong at f70 — is ``not reachable_attach(active, None)``, never
        "0 Energy attached".

        Affordability is per-slot TYPED against attached Energy plus the Budget, and any single
        Budget option may pay. Transient attack locks are honoured (ADR-0033): a blanket
        ``self_lock`` body reaches nothing and a ``same_lock`` attack is skipped, so "payable" can
        never mean an attack the engine will not offer. Fail-CLOSED throughout: an unknown body,
        an unresolvable attack record or a 0-cost quirk makes NO claim."""
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
        """The EV reading of :meth:`reachable_attach`: P(``my_body`` can really pay an attack this
        turn), taking the BEST attack by probability (ADR-0074 decision 6, #175).

        Exactly 1.0 when a payable attack needs nothing from the deck, and 0.0 whenever the boolean
        oracle says nothing is payable at all — the two readings agree on feasibility by
        construction, because both walk the same locks, the same attacks and the same matcher. With
        no probability map it degenerates to ``1.0 if reachable_attach(...) else 0.0``, so an
        unweighted caller is unchanged.

        For RANKED consumers only. A gating consumer takes :meth:`reachable_attach` — see **Leg
        Assignment** in ``src/common/CONTEXT.md``."""
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
        """**The provision seam** (Issue #418): the ``EnergyType`` UNIT codes attaching this Energy
        CARD puts on ``energies``, for THIS holder. ``None`` when it cannot be read.

        *"How many units does this Energy card provide this body, and in what colour?"* is ONE
        question, and this is the ONE place its two halves are composed — the colour from
        ``CardStat.energyType`` and the count from `CardFunctions.energy_provision`. Before Issue
        #418 SIX readers answered it: two composed the accessors (this function's ancestor
        `board_delta._provided_units`, and :meth:`_special_energy_groups`) and four hardcoded a 3
        whenever the holder was an Evolution and the card carried the ``discard_eot`` rider, and a 1
        otherwise. That hardcode is right only by the coincidence that Ignition Energy is the sole
        card carrying BOTH ``discard_eot`` and ``provides_evo`` — a future ``provides_evo`` card
        without the rider would read 1 where it should read N.

        ``holder_stat`` is the RECIPIENT's `CardStat`, not the Energy card's, because the provision
        is a property of the holder as well as of the card: Ignition Energy provides {C} on a Basic
        and {C}{C}{C} on an Evolution (card text, `data/EN_Card_Data.csv` 17), so the same card
        renders ``[0]`` or ``[0, 0, 0]`` and NEVER ``[17]`` (`common/board_cards.py`). A Basic
        Energy is one unit of its own colour and carries no tag — the case that would otherwise fail
        closed to nothing.

        Three answers, and they are three different facts:

        * ``(code, ...)`` — the provision, read.
        * ``()`` — a CLAIM of zero: this card is a Pokémon **Tool**, which rides
          ``OptionType.ATTACH`` exactly as an Energy does and provides no Energy at all. Positively
          ``is_tool`` rather than "not ``is_energy``", and fail-OPEN in the same direction
          `Pilot._attach_is_energy` already takes: ``cardType`` is the one `CardStat` field a
          hand-built board routinely omits, so reading its ABSENCE as "not Energy" would silently
          zero the provision on a board that is merely under-described.
        * ``None`` — UNREADABLE (ADR-0067, fail-CLOSED): no ``CardStat``, no ``energyType``, or a
          Special Energy with no ``provides:N`` Function Tag. The caller then makes no claim;
          `board_delta._provided_units` turns it into an `Unmodellable` refusal and
          :meth:`provision_codes_or_floor` turns it into the minimal reading a decider can price.
        """
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
        """:meth:`provision_codes`, with the FLOOR reading substituted for an unreadable provision:
        ONE unit — of the card's own colour when the stat gives one, else :data:`WILD_CODE`.

        The DECIDER's arity. An option has to be priced and ordered whatever the compendium knows,
        so "make no claim" cannot mean "return nothing" here the way it can at the apply seam: an
        attach the decider prices at zero units reads as *"this attach does nothing"*, which is a
        confident and wrong claim about a legal play. One unit is the smallest a legal Energy attach
        can deliver, and the colour follows the same split every other unresolved-Energy read in this
        module already takes — the card's own code when known, WILD when not.

        Both halves reproduce what the four retired hardcodes did on the cards they could not read,
        so the floor changes no shipped decision; what it does not do is let an unreadable card
        inherit the ``discard_eot``-shaped guess at THREE.

        A shipped deck never reaches the floor's tag branch. `test_attach_budget_coverage.py` fails
        a deck whose Special Energy carries no ``provides:N`` tag, so that half covers a card the
        audit already forbids — it exists so an unaudited hand-built board degrades instead of
        claiming nothing at all."""
        codes = self.provision_codes(card_id, holder_stat)
        if codes is not None:
            return codes
        colour = getattr(self._card_stat(card_id), "energyType", None)
        return (WILD_CODE,) if colour is None else (int(colour),)

    def restage_energy(self, body: dict | None, holder_stat) -> dict | None:
        """``body`` as its attached Energy CARDS render on a DIFFERENT holder stage — the
        hypothetical an EVOLVE decider must ask about (Issue #418, D3).

        The sibling of :meth:`without_expiring_energy`: that one asks *what does this body hold once
        the expiring Energy is gone*, this one asks *what do the same cards provide once this body is
        an Evolution*. Both return a plain raw body, so every oracle below is asked the ordinary
        question about an ordinary board.

        `board_delta._evolve` performs exactly this substitution at the APPLY seam and REFUSES
        (`Unmodellable`) when the provision model disagrees with the engine about the board as it
        already stands. A decider cannot refuse, so the same self-check lands here as a DECLINE:
        ``body`` is returned by identity — unchanged, and therefore reading exactly as it did before
        Issue #418 — whenever the cards cannot be re-derived or the re-derivation of the CURRENT
        stage does not reproduce the ``energies`` the engine renders. Compounding a provision error
        we can already see is worse than the under-read it would replace.

        ``holder_stat`` is the stage to re-read AGAINST — the evolution card's `CardStat`, not the
        pre-evolution's."""
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
        """``count`` UNTYPED Budget units — Energy whose colour is not yet chosen (an accelerator's
        routed Basics, drawn from a zone the recipient pick does not fix). Each pays any one slot:
        fail-OPEN, exactly as :meth:`attack_type_payable` treats an unresolvable attached Energy."""
        return tuple(AttachUnit(frozenset()) for _ in range(max(0, int(count))))

    def matched_slots(self, my_body: dict | None, attack_id, *, extra_units=()) -> tuple:
        """``(matched, total)`` typed cost slots of ``attack_id`` that ``my_body``'s attached Energy
        plus ``extra_units`` covers — the typed BUILD read (ADR-0069 §3).

        Uses the matcher :meth:`reachable_attach` uses, so build progress and reachability can never
        disagree: an Energy that fills no slot scores no build (off-type waste is then an emergent
        zero, not a separate flag) and a colourless slot absorbs any type (so a genuinely usable
        off-colour attach is never mislabeled). ``(0, 0)`` when no cost record resolves — the caller
        then makes no typed claim and falls back to the count reading."""
        slots = self._attack_slots(attack_id)
        if not slots:
            return (0, 0)
        units = self._attached_units(my_body) + tuple(extra_units)
        return (_matched_slots(slots, units), len(slots))

    def without_expiring_energy(self, body: dict | None) -> dict | None:
        """``body`` as it will stand once the rules discard its EVAPORATING Energy — the hypothetical
        a FORWARD clock must be asked about (Issue #286, POC-T3.5).

        The subtractive mirror of `MySide.best_reachable_damage`'s ``extra_unit_codes``: that one
        asks *what if this body also held X*, this one asks *what does it hold once X is gone*. Both
        return a plain raw body, so every oracle below is asked the ordinary question about an
        ordinary board and nothing learns a second vocabulary.

        **Card identity comes from ``energyCards``, never from ``energies``**, and that is the whole
        difficulty rather than a detail. ``energies`` is a list of ``EnergyType`` UNITS, not cards
        (`common/board_cards.py`): one Ignition Energy is card **17** on ``energyCards`` and renders
        as ``[0, 0, 0]`` — three COLORLESS units — on ``energies``. Filtering ``energies`` for card
        17 therefore matches nothing at all and the strip would be silently inert, which is exactly
        the shape this codebase has been bitten by before (Issue #297).

        Three committed sources, each answering the part only it can:

        * **which cards expire** — the Effect Clause's ``rider == "discard_eot"``. The behavioural
          Function Tag of the same name exists too, and is deliberately NOT the instrument: the tag
          says *that* a card evaporates, the clause is the parametric record (ADR-0032/ADR-0067).
        * **how many units each provides, and in what colour** — :meth:`provision_codes`, the ONE
          composition of `CardFunctions.energy_provision` with ``CardStat.energyType``. It takes the
          HOLDER's stage, because Ignition provides ``{C}`` on a Basic and ``{C}{C}{C}`` on an
          Evolution. This docstring used to record that it was NOT the codebase's only reading of
          that quantity — `pilot._attach_provision`, `pilot._attach_lethal_tactical`,
          `planner._attach_provided` and `planner._best_hand_attach_units` each hardcoded
          a 3 on an Evolution holding the ``discard_eot`` rider and a 1 otherwise — and declined to
          fix it. Issue #418 did: all
          four now read the seam, and the codes removed here are the codes those sites add.

        Fail-CLOSED at every step, and per CARD as well as per body: no clause compendium, no
        clause, no resolvable HOLDER (the provision is stage-dependent, so an unknown stage cannot
        size it), no provision tag, no matching unit, or no ``energyCards`` key at all, and that card
        is left exactly where it was. When nothing at all was removed the body is returned **by
        identity**, so the overwhelmingly common case (no expiring Energy anywhere on the board)
        costs one walk and no allocation, and a caller may use ``is`` to detect it."""
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
            # The card STAYS unless its units actually left. Dropping it while its units survive
            # would hand the caller a body whose two Energy keys disagree — the exact cards-vs-units
            # split `common/board_cards.py` exists to keep straight — and the guard is per-CARD
            # because the whole-body `dropped` check below cannot see one card's silent no-op.
            if not removed:
                keep.append(entry)
            dropped += removed
        if not dropped:
            return body                       # identity: nothing expires, nothing is re-keyed
        return dict(body, energies=units, energyCards=keep)

    def _evolve_accel(self, stat) -> tuple:
        """``(EnergyType, units)`` an ON-EVOLVE deck-search Ability attaches to the form being
        evolved INTO — the opponent-side reading of the `_ACCEL_TAGS` family (**Issue #257**).

        Marnie's Grimmsnarl ex 648's Punk Up is the shipped case, verified at source: *"When you play
        this Pokémon from your hand to evolve 1 of your Pokémon during your turn, you may search your
        deck for up to 5 Basic {D} Energy cards and attach them to your Marnie's Pokémon"* — and a
        Marnie's Grimmsnarl ex is itself a Marnie's Pokémon, so it may take them. Five Energy in one
        turn, arriving on exactly the hop the Threat Clock is already counting.

        **Effect-Clause-quantified, fail-CLOSED** — ADR-0067's self-side rule, mirrored. The Function
        Tag only ROUTES; the amount, the type, the source zone and the TRIGGER come from the clause,
        and a tagged card the compendium says nothing about yields zero. Deck PRESENCE fails open
        (we cannot see their deck, and under-crediting an opponent's reach is the unsafe direction
        for a threat read) — the same asymmetry ADR-0067 draws on my own side.

        **Only the ON-EVOLVE trigger.** That is not a shortcut, it is the boundary of what a per-FORM
        read can honestly answer: the hop IS the trigger, so the credit lands exactly where the curve
        is already looking. A pool sweep for "search your deck … and attach" turned up 29 cards; all
        but five are ATTACKS, which end the turn and so can never fund another attack (ADR-0064's
        existing exclusion). Of the five Abilities, the four this deliberately does NOT credit each
        need a BOARD-level premise the per-form structure cannot carry, and each is recorded rather
        than silently dropped:

          * **641 Steven's Metagross ex** X-Boot — once per turn, unconditional, targets "your {P}
            Pokémon and {M} Pokémon". Available to a body ALREADY in play, so crediting it is a
            question about their board ("does an X-Boot body exist?"), not about this form.
          * **340 Yanmega ex** Buzzing Boost — fires on moving Bench→Active, i.e. on the promotion
            the `_promotion_open` gate already models separately.
          * **834 Toxtricity** Sinister Surge — targets "1 of your Benched {D} Pokémon", so it never
            funds the attacker itself (the Aura Jab shape, one zone over).
          * **871 Heliolisk** Frilled Generator — gated on having played Canari from HAND this turn,
            which is hidden information; fail-closed, no credit.

        These are the "on-board accel abilities … a Brief-derived budget scan is the proper home if
        one arrives" residual the doom-shadow grill already flagged (RULED appendix, 2026-07-23).
        Under-crediting them under-rates their clock, which is the direction this method otherwise
        errs against — stated, not papered over."""
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

        ONE function owns affordability, so the damage read (:meth:`_reach_form_damage`) and the
        rider read (:meth:`_bench_payload`) cannot drift about which attacks are on the menu — the
        `_build_standing` lesson from ADR-0070, applied here because #163 added a second consumer.

        Under the ceiling policy (``charged is None``) the question is per-FORM, not per-attack: a
        form contributes once it can pay its CHEAPEST attack, and ``aid`` is then irrelevant.

        ``is_current`` has NO default here or on :meth:`_reach_form_damage`, deliberately. It is one
        concept read by two methods, and a default would have to pick a fail direction for both: True
        suppresses the Issue #257 evolve-accel credit (under-reading their clock — the unsafe
        direction), False credits it on a body already in play (reach that does not exist). Every
        call site knows which it holds, so the answer is to make them say it.

        Under :data:`UNCHARGED` it is per-form too, but read FAIL-OPEN: an unresolvable cost counts
        as payable. That is the one substantive difference from the ceiling, and it is deliberate —
        ``can_pay_cheapest`` reads ``(minAttackCost or 99)``, a fail-CLOSED idiom whose own docstring
        scopes it to "a my-side claim is never assumed". Pointed at the OPPONENT it says *"I cannot
        tell what this costs, so assume it cannot reach me"*, which is the one thing a survival read
        must never say. The current form skips this check entirely; see :meth:`_reach_form_damage`."""
        if charged == UNCHARGED:                      # doom: fail-OPEN on an unresolvable cost
            return (getattr(stat, "minAttackCost", None) or 0) <= attached + t
        if charged is None:                           # ceiling: pay cheapest, credit anything
            return bool(stat.can_pay_cheapest(attached + t))
        base = charged.get("base_attach", 1)
        # Ignition-class colourless burst lands its full {C}{C}{C} only on an Evolution (rules.md /
        # card text) — a Basic form gets the plain single attach, no burst. A single-card allowance,
        # so it is flat in the turn count, never scaled by ``t``.
        burst = charged.get("burst_on_evo", 0) if getattr(stat, "evolvesFrom", None) else 0
        wild = t * base
        # Their own ON-EVOLVE deck-search Ability (Issue #257), on a form they would EVOLVE INTO —
        # the hop is the trigger, so a current form never earns it. TYPED, so unlike the colourless
        # burst it can pay a specific slot; flat in ``t`` for the same reason the burst is (it fires
        # once, on the hop). CHARGED only: the ceiling already credits every attack a form can reach.
        acc_type, acc_units = (None, 0) if is_current else self._evolve_accel(stat)
        if self.attack_cost(aid) > attached + wild + burst + acc_units:
            return False
        return bool(self.attack_type_payable(aid, form_body, wild_units=wild,
                                             extra_type=acc_type, extra_units=acc_units))

    def discard_recur_fuel(self, body: dict | None, opp_discard_energy: dict | None, *,
                           forward_ids=None, scope: str = "any") -> int:
        """The extra Basic Energy a `discard_energy_recur` line can reload from the opponent's DISCARD
        next turn — the Threat Clock's discard-fuel input (S2 of
        docs/plans/opponent-value-equation-unification.md). A refueler taps its own discard as an
        extra energy reservoir beyond the 1 manual attach/turn, so its line is faster (lower
        :meth:`turns_to_afford`) and more dangerous (higher :meth:`incoming`). Verified card facts
        (EN_Card_Data.csv): Mega Lucario ex 678 Aura Jab attaches up to 3 Basic {F} from its discard
        to its **Benched** Pokémon; Archaludon ex 190 Assemble Alloy up to 2 Basic {M} to its {M}
        Pokémon, **on evolving**.

        ``scope`` picks WHICH question is being asked, and the two are genuinely different (Issue
        #204's grill agenda item 2, resolved here against the card text rather than deferred):

        - ``"any"`` (default, the shipped reading) — *"could this line refuel at all?"* A fail-OPEN
          caution signal: the doom-relax stands down when a refueler has fuel in the bin, because a
          reload outside the attach budget is exactly what a relaxed survival read cannot see. Tag-
          routed and type-capped; it deliberately does not care where the Energy lands.
        - ``"self_arming"`` — *"does the reload help THIS body pay for its own attack?"* That is a
          CLOCK input (`turns_to_afford`), so a wrong answer is a wrong number rather than a missed
          caution, and it is quantified by **Effect Clause**, never by the boolean tag (ADR-0067's
          rule: the tag ROUTES, the clause says how much and under what predicate). The two shipped
          lines answer this differently and the texts are unambiguous:

          * **Assemble Alloy is an Ability that fires "when you play this Pokémon from your hand to
            evolve"** and attaches to "your {M} Pokémon" — which includes the body that just evolved.
            So it funds precisely the hop this clock is already counting. **Credited.**
          * **Aura Jab is an ATTACK** whose reload targets "your **Benched** Pokémon" — never the
            attacker. Crediting it toward arming Mega Lucario ex would be circular (it must already
            be armed to attack) and toward arming a Riolu it is simply not yet available. **Not
            credited.**

          **Declared gap** (source-verified, not an oversight): Aura Jab's reload IS real for OTHER
          benched bodies once a Mega Lucario ex is in play and attacking. Pricing that needs a
          board-level "an armed refueler exists and will swing" premise rather than a per-body one,
          so it is left out — which UNDER-rates their bench clock, the one direction this method
          otherwise errs against. Recorded rather than papered over.

        0 when no form in the body's line (current + forward) carries the tag, no Basic Energy of the
        line's type sits in the discard, or functions/stats are blind (fail-open). Pure: a caller
        models the fuel by augmenting a body's ``energies`` and re-reading the clock."""
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
