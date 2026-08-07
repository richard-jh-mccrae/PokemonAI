"""The energy-attach decider (ADR-0069): the axes-sum marginal — attack axis + Retreat Equity + Ability Fuel -
evaporation loss — that decides every Energy attach and every accelerator recipient.

It REPLACED nineteen tuned rungs; where each went is `tools/rung_registry.py` (`FOLDED`, ADR-0069 group). The three
that survive are positional structure, band-constrained in `baseline_energy.py`."""
from __future__ import annotations


from common.card_worth import ENERGY_TIER
from common.deciders.facts import Board
from common.strategy.combat import Budget
from common.strategy.context import _ACTIVE, _ATTACH, _ATTACH_FROM, _ATTACKER_ROLES, _BENCH, _CARD, _RETREAT


# ── the ATTACH DECIDER's constants (ADR-0069; kill-switch `attach_value`, shipped ON) ─────────
# Every one is DERIVED, not folklore: each is pinned by an inequality in
# tests/strategy/test_attach_bands.py, solved against the SHIPPED decks' real build steps. Change a
# constant and the band tests re-check the whole set — that is the retune protocol, not a comment.
#
# Damage->weight calibration (ADR-0060 calibration-anchor). Retuned CONSTRAINT-FIRST for the swap:
# the written inequalities give a feasible region, `tools/train/probes/attach_decider_sweep.py`
# picks inside it on corpus score-diff (agreement with the retired pile peaks flat over [1.0, 1.5];
# 0.3 — the shadow-era seed, sized so a flat +15 rung floor still carried small attaches — costs 3
# extra corpus regressions because a real early build step then scores below a +8 Tool equip).
# 1.0 is the region's lower edge AND makes the marginal a DIRECT damage currency: one point of
# marginal is one rung point, the same units the ADR-0062 damage tacticals already speak.
_ATTACH_VALUE_SCALE = 1.0

# The two orthogonal CHANNELS, in DAMAGE units so they sum with the attack axis before scaling.
# Both are LOW-BAND by ruling: a mobility/fuel signal breaks ties among build-equal options and must
# never outrank one real build step (the thinnest shipped step is Staryu's first slot toward Nebula
# Beam, 210/9 x 0.25 = 5.83). "~half the smallest live build credit" -> 3.0.
# NB the channels are in damage units BEFORE the scale, so raising the scale never lets a channel
# overtake a build step — the constraint is scale-invariant by construction.
_ATTACH_RETREAT_EQUITY = 3.0   # FULL coverage of the printed Retreat cost (colourless -> type-agnostic)

_ATTACH_ABILITY_FUEL = 3.0     # a dormant in-play Ability switched on (the {D} a bare Munkidori wants)

# The resource TIE-BREAK (ADR-0069 §5c): among equal marginals, spend the RENEWABLE card. Charged on
# the worth a card carries ABOVE a reusable Basic (`card_worth.ENERGY_TIER`), so a plain Basic pays
# nothing and only a one-shot (Ignition's `discard_eot` band, 30) is nudged. Sub-band by
# construction: 0.05 x (30 - 8) = 1.1 < one scaled build step (1.0 x 5.83 = 5.83), so it can order
# equals and never overturn a real build difference.
_ATTACH_RESOURCE_TIEBREAK = 0.05

# A pre-evolution's Energy carries through evolution, but the body must still EVOLVE before the
# payoff fires — so its forward build is discounted below an already-evolved body's (83007714-22)
# and below a this-turn arm of the doomed Active (82522726-7, 85785606-19/21).
_ATTACH_PREEVO_DISCOUNT = 0.25


class AttachMixin:
    """The attach marginal: what this Energy, on this body, buys."""

    def _attach_readiness(self, cid, energy: int) -> float:
        """Best printed damage the body ``cid`` can afford with ``energy`` Energy — a 2-point
        threshold model off `CardStat` (cheapest attack / biggest attack). Opponent-independent, so
        it credits a BENCHED body's progress toward its OWN payoff (Nebula Beam 210 at 3, Jetting
        Blow 120 at 1) and reads 0 below the cheapest cost. The marginal of an attach is the delta of
        this across the extra Energy — over-attach on a maxed body is 0, a threshold-crossing attach
        is a big jump (the concentrate signal falls out)."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        if st is None:
            return 0.0
        maxc, minc = getattr(st, "maxDamageCost", None), getattr(st, "minAttackCost", None)
        if maxc is not None and energy >= maxc:
            return float(getattr(st, "maxDamage", 0) or 0)
        if minc is not None and energy >= minc:
            return float(getattr(st, "minCostDamage", 0) or getattr(st, "maxDamage", 0) or 0)
        return 0.0

    def _opp_body_hps(self, obs: dict) -> list:
        """Current HP of every opponent Pokémon in play (Active + Bench) — the overkill-cap read: a
        bigger attack buys nothing once the current one already covers the biggest body on the board."""
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        opp = players[1 - yi] if len(players) > 1 else None
        if not opp:
            return []
        bodies = list(opp.get("active") or []) + list(opp.get("bench") or [])
        return [m.get("hp", 0) for m in bodies if m]

    def _line_payoff_stat(self, cid):
        """The CardStat whose attack a body's Energy ultimately FUELS — evolution-lookahead (attach
        grill Ruling 5a). A win-condition-Line PRE-evolution's Energy carries through evolution and
        builds toward the LINE's PAYOFF attack (a Staryu's Energy builds toward Mega Starmie's Nebula
        Beam CCC=210, NOT Staryu's own Water Gun, maxed at 1), so its progress must be priced by the
        payoff, not the pre-evo's cheap own attack. Returns the payoff's stat for a wincon-Line
        pre-evolution, else the body's own stat (a terminal/own-attacker body is priced by itself)."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        if cid is None or not self.stats:
            return st
        for line in self._wincon_lines():
            if cid in (line.path or []) and cid != line.payoff:
                return self.stats.get(line.payoff) or st
        return st

    def _attach_progress(self, cid, energy: int) -> float:
        """The COUNT reading of convex forward-build value — body ``cid`` at ``energy`` Energy toward
        the biggest attack it FUELS. ``(min(e, M) / M)**2 * maxDamage`` — the SQUARE makes the
        marginal of the k-th Energy INCREASE with k, so completing a started carrier is worth more
        than starting a fresh body: concentrate on the most-built survivable carrier falls out
        (82523811-59, 82749168-61), while the maxed body's marginal is 0 (over-attach). `M`/`maxDamage`
        come from the LINE PAYOFF (`_line_payoff_stat`), so a wincon pre-evo builds toward its evolution's
        attack, not its own cheap one (82752604-61, 83116081-21, 85059103-84).

        The DECIDER prefers the TYPED slot-fraction reading (`_attach_build_delta`, ADR-0069 §3) and
        only falls back here when the payoff attack's per-slot cost does not resolve — where a typed
        claim would be a guess and the count reading makes none."""
        st = self._line_payoff_stat(cid)
        maxc = getattr(st, "maxDamageCost", None) if st is not None else None
        dmax = float(getattr(st, "maxDamage", 0) or 0) if st is not None else 0.0
        if not maxc or maxc <= 0 or dmax <= 0:
            return self._attach_readiness(cid, energy)
        frac = min(energy, maxc) / maxc
        value = frac * frac * dmax
        if cid in self._line_preevo_set():
            value *= _ATTACH_PREEVO_DISCOUNT
        return value

    def _payoff_attack_id(self, payoff_stat):
        """The attack a body's Energy is ultimately BUILDING toward — the biggest-damage attack of
        the line payoff. None when no attack record resolves (the caller then makes no typed claim)."""
        aids = tuple(getattr(payoff_stat, "attacks", None) or ())
        return max(aids, key=self.combat.attack_damage) if aids else None

    def _build_standing(self, target: dict | None, extra_units=()) -> float:
        """**Build Standing** — the LEVEL of ``target``'s convex typed build credit, optionally over a
        hypothetical body also carrying ``extra_units`` (ADR-0070 §2).

        ``(matched/slots)**2 * maxDamage``, where ``matched`` is the greedy typed assignment of the
        body's attached Energy against the LINE PAYOFF attack's cost shape — by the SAME matcher
        `reachable_attach` uses, so "fits" and "reaches" can never disagree. Two consequences that
        used to need their own rungs: an Energy filling no slot earns ZERO build (off-type waste is
        emergent, never a separate colourless-blind boolean), and a colourless slot absorbs any type
        (so Munkidori's {D} in Mind Bend's ● is real progress, not "wasted"). A pre-evolution keeps
        the `_ATTACH_PREEVO_DISCOUNT`; the evolution-lookahead payoff pricing carries over unchanged
        from the count reading, which is the fallback when the payoff attack's per-slot cost does not
        resolve (where a typed claim would be a guess).

        The LEVEL is the shared form: #139 needs only its DIFFERENCE under an option's provision
        (`_attach_build_delta`, below), while #140 needs the level itself — an evolve moves no Energy,
        so its deploy value is `standing(evolved) − standing(pre-evolution)` on the SAME attached
        Energy, and **evolving is precisely the removal of the pre-evolution discount**. One function
        owns build credit so the two readings cannot drift."""
        if not target:
            return 0.0
        tcid = target.get("id")
        st = self._line_payoff_stat(tcid)
        dmax = float(getattr(st, "maxDamage", 0) or 0) if st is not None else 0.0
        aid = self._payoff_attack_id(st)
        if aid is not None and dmax > 0:
            matched, slots = self.combat.matched_slots(target, aid, extra_units=extra_units)
            if slots:
                value = ((matched / slots) ** 2) * dmax
                return value * (_ATTACH_PREEVO_DISCOUNT if tcid in self._line_preevo_set() else 1.0)
        have = len(target.get("energies") or [])          # no typed cost record -> the count reading
        return self._attach_progress(tcid, have + len(extra_units))

    def _attach_build_delta(self, target: dict | None, extra_units) -> float:
        """The CONVEX, TYPED build progress ``extra_units`` buys on ``target`` (ADR-0069 §3) — the
        DIFFERENCE of :meth:`_build_standing` with and without the option's provision.

        The branch (typed vs the count fallback) is chosen by the payoff attack's cost record, which
        no attach changes, so both legs always read the same way and the difference is exact."""
        return self._build_standing(target, extra_units) - self._build_standing(target)

    def _partner_absent(self, cid, obs: dict) -> bool:
        """Ruling 6: `cid` is a co-dependent ENGINE body whose value requires a partner in play
        (Solrock needs a Lunatone, and vice-versa — `strategy.partners`), and NONE of its declared
        partners is on my board right now → a dead attach target, value it at 0. Partner-AGNOSTIC in
        the general oracle: the pairing itself is deck-declared data (ADR-0034). False for any body
        with no declared partner."""
        partners = getattr(self.strategy, "partners", None) or {}
        need = partners.get(cid)
        if not need:
            return False
        me = self._my_player(obs)
        in_play = {m.get("id") for m in ((me.get("active") or []) + (me.get("bench") or [])) if m}
        return not any(p in in_play for p in need)

    def _accel_attack_id(self, cid):
        """The body's attack that carries an energy-accel rider (recoverN > 0) — Turbo Flare / Aura
        Jab. None when the body has no accelerator attack."""
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        for aid in (getattr(st, "attacks", None) or ()):
            ast = self._attack_stat(aid)
            if ast and getattr(ast, "recoverN", 0):
                return aid
        return None

    def _accel_routed_value(self, obs: dict, board: Board, routed: int) -> float:
        """Value of the ``routed`` Energy an accelerator attack (Turbo Flare) attaches to the Bench —
        Ruling 4: an attach that FIRES an accelerator is worth the forward build the routed Energy
        buys on the survivable carrier, not the accelerator's own face damage. Concentrated onto the
        single Bench Line body that gains the most (the accel routes 'in any way you like'), priced in
        the same convex-build currency (`_attach_progress`)."""
        if routed <= 0:
            return 0.0
        me = self._my_player(obs)
        line_ids = self._line_preevo_set() | self._wincon_set()
        wild = self.combat.wild_units(routed)   # the routed colours aren't fixed by this pick — fail-open
        best = 0.0
        for b in (me.get("bench") or []):
            if not b:
                continue
            cid = b.get("id")
            if cid not in line_ids and self._is_utility_body(cid):
                continue                                       # don't credit routing onto a utility body
            best = max(best, self._attach_build_delta(b, wild))
        return best

    def _attach_body_view(self, target: dict | None):
        """The StateModel :class:`BodyView` wrapping this raw board dict — the handle the
        affordability family (Budget / reachability) is keyed on. None off-board or when no model has
        been built (the decider then makes no this-turn claim)."""
        model = self._state_model
        if model is None or not target:
            return None
        return next((b for b in model.mine.bodies if b.body is target), None)

    def _reusable_hand_energy_id(self, obs: dict):
        """A REUSABLE (non-`discard_eot`) Energy card id in my hand — the conservation alternative a
        burst's tonight-credit is capped against (ADR-0069 §5b). ONE predicate, at two arities:
        `_has_reusable_energy` is this lookup's boolean projection, so "does one exist" and "which
        one" cannot disagree — which the cap depends on, since it would otherwise fire with no
        alternative to fall back to. None when the hand holds none."""
        return self._reusable_energy_id(self._my_player(obs).get("hand") or [])

    def _attacker_alternative_in_play(self, obs: dict, target: dict | None) -> bool:
        """Is a REAL attacker alternative on my board right now — some OTHER body of mine that is a
        win-condition Line member or carries an attacker Role (not itself dead through a missing
        partner) AND that would gain actual build from THIS Energy?

        This is what makes the role gate BOARD-EVALUATED (ADR-0069 §4, the Ruling-6 pattern
        generalized). "This body's job is not attacking" is only a reason to withhold Energy while
        somebody else can take it; on a lone or attacker-less board the utility body IS the attacker,
        and pricing it at zero would score the only legal home BELOW ending the turn.

        Deliberately IN PLAY, not "could use THIS colour". Making the test per-provision is tempting
        once build is typed — a dead colour is withheld on behalf of a body that cannot take it — but
        it was MEASURED and rejected: it inverts 86091728-19, where the human ruled that the line eats
        the {P} first even though the {D} in the same hand is useless to the line. That frame says the
        priority is a resource-sequencing doctrine (which Energy to spend this turn), not a gating
        one, and ADR-0069 §4 states the gate as written here. See
        docs/plans/attach-decider-swap-review.md for the ruling the two follow-up doctrine pins owe."""
        line_ids = self._recognized_line_preevo_set() | self._wincon_set()
        me = self._my_player(obs)
        for p in ((me.get("active") or []) + (me.get("bench") or [])):
            if not p or p is target:
                continue
            cid = p.get("id")
            if (cid in line_ids
                    or ((_ATTACKER_ROLES & set(self._roles_of(cid)))
                        and not self._partner_absent(cid, obs))):
                return True
        return False

    def _is_spent_utility_liability(self, card_id: int | None) -> bool:
        """True for an in-play one-shot utility ex whose value is already cashed.

        Meowth ex is the motivating source-verified case: id 1071's Last-Ditch Catch fires only when
        played from hand onto the Bench, while Tuck Tail is 3 Energy for 60 damage and the body gives
        up 2 prizes. This is not the broad utility-body read: Lunatone-style engines may still bank
        mobility through Retreat Equity. It is the narrower "do not turn a spent support ex into a
        larger giveaway while a real attacker can take the Energy" ruling."""
        if card_id is None or not self.functions or not self.stats:
            return False
        stat = self.stats.get(card_id)
        if stat is None or not getattr(stat, "is_ex_body", False):
            return False
        roles = set(self._roles_of(card_id))
        if roles & _ATTACKER_ROLES:
            return False
        if card_id in (self._line_preevo_set() | self._wincon_set()):
            return False
        return "supporter_tutor" in set(self.functions.tags(card_id))

    def _attach_retreat_equity(self, target: dict | None, units: int, burst: bool) -> float:
        """**Retreat Equity** — the mobility an attach buys by paying toward the body's printed
        Retreat cost (ADR-0069 §1; glossary in `common/CONTEXT.md`).

        The attack terms structurally cannot see this: the turn-1 Energy onto a lone Lunatone buys no
        damage tonight and no build the deck cares about, but it pays the pivot that later lets
        Solrock attack. TYPE-AGNOSTIC, because Retreat slots are colourless (rules.md §3) — which is
        exactly the value an off-type desperation attach buys. Zero on a body already funded for its
        retreat, on a free-retreat body (TEF Dunsparce has NO Retreat cost, so the "don't feed
        Dunsparce the only {D}" lesson survives any mobility credit), and on a burst (it leaves play
        at end of turn, so it funds no future pivot)."""
        if burst or not target:
            return 0.0
        st = self.stats.get(target.get("id")) if self.stats else None
        cost = int(getattr(st, "retreatCost", 0) or 0)
        if cost <= 0:
            return 0.0
        have = len(target.get("energies") or [])
        if have >= cost:
            return 0.0                                     # already funded — the pivot is already paid
        covered = min(have + units, cost) - min(have, cost)
        return _ATTACH_RETREAT_EQUITY * covered / cost

    def _attach_value(self, obs: dict, select: dict, board: Board, option: dict):
        """The ATTACH DECIDER: price ONE energy-attach option as an AXES-SUM (ADR-0069).

            marginal = attack_axis + retreat_equity + ability_fuel − evaporation_loss
            attack_axis = max(this_turn, build, accel_value)

        MAX within the attack axis because its three terms re-read ONE progress (a single Energy is
        never double-paid for the same attack); SUM across the channels because Retreat Equity and
        Ability Fuel are INDEPENDENT card features — a {D} that both fills Mind Bend's colourless slot
        and wakes Adrena-Brain beats the same-build {P} outright, with no tie-break coincidence.

        Returns a per-option working row (the decider's legible working, ADR-0008/0019 — the
        substrate #146/#148 consume), or None to ABSTAIN: a Pokémon Tool rides `OptionType.ATTACH`
        but is not Energy, so it is never priced here.

        The terms, and the rung each one retired:
          * `this_turn`      — a TRUE COUNTERFACTUAL under the full Attach Budget: best reachable
                               damage with this Energy committed minus best reachable damage without
                               it, both legs typed and sound (ADR-0067), both at the same residual
                               capacity. So an attach that needs a budget partner is credited instead
                               of read as futile (the f70 under-read), a type-unpayable attack stops
                               reading as reachable, ANY attack a doomed Active unlocks counts (not
                               only its biggest — the Mega-Starmie tempo arm), and an option on a body
                               the accel already reaches is credited only for what it UNIQUELY adds.
          * `build`          — typed slot-fraction progress toward the line payoff (`_attach_build_delta`).
          * `accel_value`    — the forward build the Energy an ACTIVE accelerator ROUTES buys.
          * `retreat_equity` / `ability_fuel` — the two orthogonal channels.
          * `evaporation_loss` — a `discard_eot` Energy that leaves play UNCASHED costs its own worth,
                               so ending the turn genuinely beats torching an Ignition on turn 1.
        Gates land PER-AXIS: the board-evaluated role gate and the overkill cap zero the ATTACK AXIS
        only (a role-gated body still banks mobility and fuel). A spent one-shot utility liability is
        narrower and harsher: while a real attacker can take the Energy, it banks no attack, mobility
        or fuel value. The survival gate zeroes `build` for a doomed Active EXCEPT a wincon-Line
        pre-evolution (the evolution-escape: Energy carries through evolution, and a Mega evolving
        does not end the turn); evaporation is GLOBAL.

        `tactical` is what the option actually scores: the marginal scaled into the rung band, less
        the sub-band resource tie-break that spends the renewable card among equals. It MAY be
        NEGATIVE — the decider is allowed to say "attach nothing" and mean it.
        """
        ctx = select.get("context")
        is_attach = option.get("type") == _ATTACH
        is_from = ctx == _ATTACH_FROM and option.get("type") == _CARD
        if not (is_attach or is_from):
            return None
        ecid = self._option_card_id(obs, select, option)
        estat = self.stats.get(ecid) if (self.stats and ecid is not None) else None
        if is_attach and not self._attach_is_energy(estat):
            return None                                        # a Pokémon Tool is not Energy
        target = self._attach_target(obs, option)
        if target is None and is_from:
            target = self._option_pokemon(obs, select, option)
        if target is None:
            return None
        tcid = target.get("id")
        target_stat = self.stats.get(tcid) if (self.stats and tcid is not None) else None
        # The recipient's real board AREA. An ATTACH_FROM option carries it as `area` (an accel usually
        # routes to the Bench, but the engine does offer the Active — and the survival gate has to see
        # a DOOMED Active recipient, or the accelerated Energy sinks into a body that dies holding it).
        area = option.get("inPlayArea") if is_attach else option.get("area", _BENCH)
        etags = set(self.functions.tags(ecid)) if (self.functions and is_attach and ecid is not None) else set()
        burst = "discard_eot" in etags
        # The PROVISION, off the ONE seam (Issue #418): how many units this card puts on THIS holder
        # and in what colour — a CARD FACT (Ignition Energy provides {C} on a Basic and {C}{C}{C} on
        # an Evolution), never bent by a valuation heuristic. An ATTACH commits a known card, while
        # an ATTACH_FROM recipient pick receives an Energy whose colour this decision does not fix —
        # one wild unit, fail-open.
        codes = self.combat.provision_codes_or_floor(ecid, target_stat) if is_attach else ()
        units = len(codes) if is_attach else 1
        provision = (self.combat.units_for_codes(codes) if is_attach
                     else self.combat.wild_units(units))
        # -- the attack axis, term 1: tonight's counterfactual ------------------------------------
        # The survival gate's THIS-TURN half: going down swinging is only worth buying when it is
        # actually the line. A READY benched win-condition that I can pivot into strictly dominates
        # whatever the doomed Active could swing for, so tonight's damage is not this attach's to buy
        # (83007714-65: the Ignition onto doomed Cinderace before the retreat into a ready Mega
        # Starmie ex was pure waste — the charter frame of the deleted `dont-feed-the-doomed`).
        # The pivot must be LEGAL NOW, which only the engine's own menu can say: at 82525101-69 the
        # bench Mega is "ready" for Jetting Blow but carries too little Energy to pay the 2-cost
        # retreat, so no RETREAT option is offered and arming the doomed Active for 120 IS the play.
        # Reading `bench_wincon_ready` alone would call both frames the same and break that one.
        arm_dominated = (area == _ACTIVE and board.active_doomed and board.bench_wincon_ready
                         and any(o.get("type") == _RETREAT for o in (select.get("option") or ())))
        # Only the ACTIVE fires this turn, and the player going FIRST cannot attack on its turn 1
        # (rules.md §2 / rulebook L152), so on either of those there is no tonight to buy.
        view = self._attach_body_view(target)
        can_attack_tonight = (area == _ACTIVE and board.turn > 1 and view is not None
                              and not arm_dominated)
        this_turn = base_dmg = committed_dmg = 0.0
        if can_attack_tonight and is_attach:
            mine = self._state_model.mine
            base_dmg = mine.best_reachable_damage(view, manual_spent=True)
            committed_dmg = mine.best_reachable_damage(view, extra_unit_codes=codes,
                                                       manual_spent=True)
            this_turn = max(0.0, committed_dmg - base_dmg)
            if burst and this_turn > 0:
                this_turn = self._burst_capped_tonight(obs, view, target_stat, this_turn,
                                                       base_dmg, committed_dmg)
        # -- the attack axis, terms 2 and 3 -------------------------------------------------------
        # The survival gate: a doomed carrier banks no forward build — EXCEPT a wincon-Line
        # pre-evolution, whose Energy carries through evolution (the evolution-escape).
        survives = not (area == _ACTIVE and board.active_doomed)
        # A `discard_eot` burst earns NO build, ever: build is FORWARD value and the card is discarded
        # at end of turn, so there is nothing forward about it. Only `this_turn` — what it cashes
        # before it goes — can credit a burst. (Without this the Ignition's honest 3 units read as a
        # full Nebula Beam build and beat the reusable Basic even where its attack cannot KO, which is
        # exactly the 83116501-70 blunder the no-KO cap exists to prevent; the cap alone does not
        # reach it, because it caps `this_turn` and the build axis was quietly out-bidding it.)
        build = (self._attach_build_delta(target, provision)
                 if (not burst and (survives or tcid in self._line_preevo_set())) else 0.0)
        accel_value = 0.0
        feeds_accel = (area == _ACTIVE and "accel_source" in self._roles_of(tcid)
                       and self._attach_target_needs(target)
                       and not board.accel_recipient_missing and not board.bench_wincon_ready)
        if feeds_accel:
            aid = self._accel_attack_id(tcid)
            ast = self._attack_stat(aid) if aid is not None else None
            if ast is not None:
                # EXPECTED routing for the value estimate: the printed ceiling capped by what the
                # recipients can actually use. (The live accel commitment's `_recover_units` also
                # floors this by the prize-paranoid deck-fuel bound — a grader-safety concern for a
                # COMMITMENT, not for a valuation.)
                routed = min(getattr(ast, "recoverN", 0), self._recover_recipient_need(ast, board, obs))
                accel_value = self._accel_routed_value(obs, board, routed)
        # -- the per-axis gates -------------------------------------------------------------------
        # The ROLE gate, board-evaluated: a body whose job is non-attacking (wall / draw-engine /
        # partnerless co-dependent engine, and not a win-condition Line member) advances no valued
        # attack — but only while somebody else can take the Energy.
        # The bodies the deck's PLAN attacks with: every declared attacker Line's members (ADR-0048's
        # broadened set, so a secondary attacker's base is a plan piece too — Makuhita on the
        # Makuhita -> Hariyama prize-wall line is `evolution_base`, a Role that names a Line stage
        # rather than an attack) plus the win-condition payoffs. NARROWER sets stay narrow elsewhere in
        # this equation on purpose: the pre-evolution discount and the evolution-escape read
        # `_line_preevo_set`, which is win-condition-only by design.
        line_ids = self._recognized_line_preevo_set() | self._wincon_set()
        # A body the deck gave ROLES, none of which is an attacker Role, has been DECLARED a
        # non-attacking plan piece — the general form of the `engine`-only read `_is_utility_body`
        # already makes. It is what catches a `counter_mover` (dragapult's Munkidori: "the attach seam
        # reads the Role — a stuck-Active Munkidori may take its {P} … once the benched line is fed")
        # and a sacrificial `starter`, neither of which carries a `_UTILITY_TAGS` tag. Reading it here
        # rather than widening `_is_utility_body` keeps the change inside the attack axis, which is the
        # only place a declared role means "do not fund this to attack".
        declared = set(self._roles_of(tcid))
        non_attacking = tcid not in line_ids and (
            self._is_utility_body(tcid) or self._is_draw_engine_body(tcid)
            or self._partner_absent(tcid, obs)
            or (bool(declared) and not (_ATTACKER_ROLES & declared)))
        attacker_alternative = self._attacker_alternative_in_play(obs, target)
        role_gated = non_attacking and attacker_alternative
        spent_utility_gated = self._is_spent_utility_liability(tcid) and attacker_alternative
        # The OVERKILL cap: once the ACTIVE already KOs the opponent's Active AND what it can afford
        # RIGHT NOW already covers the biggest body on their board, a bigger attack buys nothing more
        # this game-state — develop a second threat instead (82750161-59). Opponent-aware, so it
        # stands down while a bench threat still out-HPs the affordable attack (82523811-59).
        overkill = False
        if area == _ACTIVE and board.active_cheap_attack_kos:
            opp_hp = self._opp_body_hps(obs)
            # DELIBERATE CombatMath bypass (POC-T1's documented list): the #142 EMPTY-Budget leg —
            # "what can this body do with what is attached RIGHT NOW", the baseline of the
            # counterfactual. The model's route always carries the FULL Budget, so the empty leg has
            # no model expression by construction.
            if opp_hp and max(opp_hp) <= self.combat.best_reachable_damage(target, budget=Budget()):
                overkill = True
        # The EVAPORATION gate, global: a `discard_eot` Energy that buys nothing before it is
        # discarded at end of turn banks nothing durable — and costs what it was worth.
        gated_off = role_gated or spent_utility_gated
        cashed = this_turn > 0 and not gated_off and not overkill
        evaporates = burst and not cashed
        resource_cost = self._role_value(ecid) if (is_attach and ecid is not None) else 0.0
        evaporation_loss = resource_cost if evaporates else 0.0
        # -- the axes-sum -------------------------------------------------------------------------
        attack_axis = 0.0 if (gated_off or overkill or evaporates) else max(
            this_turn, build, accel_value, 0.0)
        retreat_equity = 0.0 if spent_utility_gated else self._attach_retreat_equity(target, units, burst)
        ability_fuel = (_ATTACH_ABILITY_FUEL if (not spent_utility_gated and not burst and is_attach
                                                and self._attach_fuels_dormant_ability(estat, target))
                        else 0.0)
        marginal = attack_axis + retreat_equity + ability_fuel - evaporation_loss
        # The resource TIE-BREAK: charged on worth ABOVE a reusable Basic, so a plain Basic pays
        # nothing and only the one-shot is nudged. Sub-band — it orders equals, never overturns build.
        tactical = (marginal * _ATTACH_VALUE_SCALE
                    - _ATTACH_RESOURCE_TIEBREAK * max(0.0, resource_cost - ENERGY_TIER))
        # The resolved target SLOT (board area, position) — the comparison key for the corpus sweep,
        # NOT the raw option index: duplicate energy-source options and identical-effect target copies
        # otherwise read as false disagreements (82523811-59, 82750161-59). type-8 ATTACH carries
        # inPlayArea/inPlayIndex; the type-3 ATTACH_FROM recipient carries area/index.
        slot = [area, option.get("inPlayIndex") if is_attach else option.get("index")]
        return {"i": None, "target": tcid, "energy": ecid, "slot": slot,
                "marginal": round(marginal, 2), "tactical": round(tactical, 2),
                "attack_axis": round(attack_axis, 2), "this_turn": round(this_turn, 2),
                "build": round(build, 2), "accel_value": round(accel_value, 2),
                "retreat_equity": round(retreat_equity, 2), "ability_fuel": round(ability_fuel, 2),
                "evaporation_loss": round(evaporation_loss, 2), "units": units,
                "role_gated": role_gated, "spent_utility_gated": spent_utility_gated,
                "overkill": overkill, "doomed": not survives,
                "burst": burst, "evaporates": evaporates,
                "line_value": round(0.0 if gated_off else self._role_value(tcid), 1),
                "resource_cost": round(resource_cost, 1)}

    def _burst_capped_tonight(self, obs: dict, view, target_stat, this_turn: float,
                              base_dmg: float, committed_dmg: float) -> float:
        """The burst's no-KO CAP (ADR-0069 §5b): a cashable one-shot earns at most what the best
        REUSABLE Basic in hand would have earned tonight — UNLESS its attack converts a KO the Basic
        cannot reach.

        This is the whole of `conserve-burst-when-no-ko` / `conserve-discard-energy-prefer-basic` as
        arithmetic: when Ignition's {C}{C}{C} unlocks Nebula Beam 210 against a 200-HP Active the cap
        lifts and the burst is spent (82523811-105); when even the big attack cannot KO (Nebula 210
        vs a 300-HP wall) the Basic does tonight's job just as well, so the burst keeps only the
        Basic's credit and loses the resource tie-break (83664340-45). No reusable Basic in hand ->
        no alternative -> no cap.

        The alternative's provision comes off the SAME seam the burst's does (Issue #418) rather
        than from its card id: `_reusable_energy_id` admits any TYPED Energy, which includes typed
        Specials (Telepath Psychic is card 19, whose id resolves to no colour at all), so the cap's
        counterfactual leg was over-reading in exactly the direction it exists to restrain."""
        reusable = self._reusable_hand_energy_id(obs)
        if reusable is None:
            return this_turn
        opp_hp = (self._opp_active(obs) or {}).get("hp", 0) or 0
        reusable_dmg = self._state_model.mine.best_reachable_damage(
            view, extra_unit_codes=self.combat.provision_codes_or_floor(reusable, target_stat),
            manual_spent=True)
        if committed_dmg >= opp_hp > reusable_dmg:
            return this_turn                                   # the burst converts a KO the Basic misses
        return min(this_turn, max(0.0, reusable_dmg - base_dmg))

    def _attach_decision(self, obs: dict, select: dict, board: Board, option: dict):
        """The decider's working ROW for this option, or None when the decider does not speak here:
        the kill-switch is OFF, the option is not an energy attach, or it is a Pokémon Tool. The ONE
        pricing call per option — the score term and the planner's spend account both read it, so
        neither can price a different attach than the other."""
        if not getattr(self, "attach_value", False):
            return None
        return self._attach_value(obs, select, board, option)

    def _attach_value_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """The ATTACH decider's contribution to an option's score (kill-switch `attach_value`,
        shipped ON). 0 when the switch is OFF — DEGRADED MODE, not a rollback: the rungs this
        replaced are deleted, so OFF means attach endorsements go SILENT and the surviving structure
        rungs decide alone. Also 0 off an energy-attach option and on a Tool (`_attach_value`
        abstains). Prize math stays OUT (ADR-0069 §6) — the race belongs to one scalar, in Phase 2.

        Signed like the ADR-0062 tacticals and — unlike every shadow-era fold — allowed to go
        NEGATIVE, which is what lets the decider score an attach below ending the turn."""
        row = self._attach_decision(obs, select, board, option)
        return 0.0 if row is None else row["tactical"]

    def _attach_working(self, obs: dict, select: dict, board: Board, options: list):
        """The attach decider's LEGIBLE WORKING (ADR-0069 §9): the per-option axes rows for every
        energy-attach option on the menu, attached to the decision record.

        This replaces the fourth shadow and its self-referential agreement bit — one emission path
        carrying one truth. The rows are the substrate the value-working emitter (#146) and the
        term-level blunder loop (#148) consume: a reader sees WHICH axis carried a pick, not just
        that it won. A Pokémon Tool ABSTAINS (not Energy) and is counted, never priced. None off an
        attach menu or mid-sim (`self._planning`), so the wire key stays sparse."""
        if self._planning:
            return None
        ctx = select.get("context")
        attach_idx = [i for i, o in enumerate(options)
                      if o.get("type") == _ATTACH or (ctx == _ATTACH_FROM and o.get("type") == _CARD)]
        if not attach_idx:
            return None
        rows, abstained = [], 0
        for i in attach_idx:
            row = self._attach_value(obs, select, board, options[i])
            if row is None:                                    # a Tool abstains — no row
                abstained += 1
                continue
            row["i"] = i
            rows.append(row)
        return {"eq": rows, "abstained": abstained} if rows else None
