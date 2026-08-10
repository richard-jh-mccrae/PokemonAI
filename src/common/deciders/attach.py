"""The attach decider (ADR-0069): the axes-sum marginal — attack axis + Retreat Equity + Ability
Fuel − evaporation loss — pricing every Energy attach and every accelerator recipient. The rungs it
replaced are in `tools/rung_registry.py` (FOLDED, ADR-0069 group).

A Pokémon TOOL takes its own channel (:meth:`AttachMixin._tool_attach_value`, Issue #423): its local
value is only the canonical Active-position option marginal; direct HP stays in state survival."""
from __future__ import annotations


from common.card_worth import ENERGY_TIER
from common.deciders.facts import Board
from common.strategy.combat import Budget
from common.strategy.context import (_ACTIVE, _ATTACH, _ATTACH_FROM, _ATTACK, _ATTACKER_ROLES,
                                     _BENCH, _CARD, _END, _MAIN, _RETREAT, KO_SCORE)


# Every constant below is pinned by an inequality in tests/strategy/test_attach_bands.py — change one
# and the band tests re-check the whole set. That is the retune protocol.

# 1.0 makes the marginal a DIRECT damage currency: one marginal point is one rung point.
_ATTACH_VALUE_SCALE = 1.0

# Orthogonal channel in DAMAGE units, summed with the attack axis before the scale.
_ATTACH_ABILITY_FUEL = 3.0     # a dormant in-play Ability switched on

# Resource TIE-BREAK (ADR-0069 §5c): among equal marginals spend the RENEWABLE card. Sub-band by
# construction — 0.05 x (30 - 8) < one scaled build step — so it orders equals and overturns nothing.
_ATTACH_RESOURCE_TIEBREAK = 0.05

#: Every key an attach row carries, at its zero. Both channels build through :func:`_attach_row`, so
#: the shape `_attach_working` and the wire depend on cannot drift between them.
_ATTACH_ROW_ZEROS = {
    "i": None, "target": None, "energy": None, "slot": None,
    "marginal": 0.0, "tactical": 0.0, "attack_axis": 0.0, "this_turn": 0.0, "build": 0.0,
    "accel_value": 0.0, "retreat_equity": 0.0, "ability_fuel": 0.0, "evaporation_loss": 0.0,
    "units": 0, "role_gated": False, "spent_utility_gated": False, "overkill": False,
    "doomed": False, "burst": False, "evaporates": False, "line_value": 0.0, "resource_cost": 0.0,
}


def _attach_row(**legs) -> dict:
    """One row, whichever channel priced it — an unnamed leg reads as its zero, never as absent.
    A misspelled leg RAISES: silently it would add a junk key and leave the real one reading 0.0."""
    unknown = set(legs) - set(_ATTACH_ROW_ZEROS)
    if unknown:
        raise KeyError(f"attach row has no leg(s) {sorted(unknown)}")
    return {**_ATTACH_ROW_ZEROS, **legs}


class AttachMixin:
    """The attach marginal: what this Energy, on this body, buys."""

    def _opp_body_hps(self, obs: dict) -> list:
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        opp = players[1 - yi] if len(players) > 1 else None
        if not opp:
            return []
        bodies = list(opp.get("active") or []) + list(opp.get("bench") or [])
        return [m.get("hp", 0) for m in bodies if m]

    def _build_standing(self, target: dict | None, extra_units=()) -> float:
        """Damage-currency adapter over canonical multi-turn attack realization."""
        if not target or self._state_model is None:
            return 0.0
        supply = extra_units if hasattr(extra_units, "persistent") else None
        profile = self._state_model.combat_realization(target, supply=supply)
        return profile.value_prizes * self._state_value_damage_rate()

    def _attach_build_delta(self, target: dict | None, extra_units) -> float:
        """Forward realization ``extra_units`` buys on ``target`` (ADR-0069 §3). Both legs take the
        same typed/count branch. The board marginal also saturates duplicate attackers, so progress
        on the primary line beats reopening its cheap attack on every copy.

        A first persistent step can be hidden when the future-realization clock already has enough
        evolution turns to attach later.  That does not make this turn's expiring manual-attach
        allowance worthless.  In that exact zero-delta case, retain the typed standing-build step
        only while no stronger same-card copy has already established the primary.  Thus a pair of
        bare Line bases may start either copy, but a bare duplicate cannot reopen progress beside an
        already-started one.
        """
        if not target or self._state_model is None:
            return 0.0
        supply = extra_units if hasattr(extra_units, "persistent") else None
        if supply is None:
            return 0.0
        canonical = self._state_model.readiness_supply_value_damage(target, supply)
        if canonical != 0.0:
            return canonical

        before = self._state_model.combat_build_profile(target).value_damage
        after = self._state_model.combat_build_profile(target, supply=supply).value_damage
        if after <= before:
            return canonical
        view = self._state_model.mine.view_of(target)
        if view is None:
            return canonical
        stronger_copy = any(
            body is not view and body.body is not view.body and body.card_id == view.card_id
            and self._state_model.combat_build_profile(body).value_damage > before
            for body in self._state_model.mine.bodies)
        return canonical if stronger_copy else after - before

    def _partner_absent(self, cid, obs: dict) -> bool:
        """A co-dependent ENGINE body with none of its declared partners in play — a dead attach
        target. The pairing is deck-declared data (`strategy.partners`, ADR-0034)."""
        partners = getattr(self.strategy, "partners", None) or {}
        need = partners.get(cid)
        if not need:
            return False
        me = self._my_player(obs)
        in_play = {m.get("id") for m in ((me.get("active") or []) + (me.get("bench") or [])) if m}
        return not any(p in in_play for p in need)

    def _accel_attack_id(self, cid):
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        for aid in (getattr(st, "attacks", None) or ()):
            ast = self._attack_stat(aid)
            if ast and getattr(ast, "recoverN", 0):
                return aid
        return None

    def _accel_routed_value(self, obs: dict, board: Board, routed: int, attack=None) -> float:
        """An attach that FIRES an accelerator is worth the forward build the ``routed`` Energy buys,
        not the accelerator's own face damage — concentrated on the Bench Line body that gains most."""
        if routed <= 0:
            return 0.0
        model = self._state_model
        if model is None:
            return 0.0
        from common.strategy.combat_math.budget import WILD_CODE
        scope = getattr(attack, "recoverTarget", "bench")
        code = getattr(attack, "recoverEnergyType", None)
        allocation = model.allocate_recovery_energy(
            scope, ((WILD_CODE if code is None else code),) * routed)
        return allocation.value_prizes * self._state_value_damage_rate()

    @staticmethod
    def _state_value_damage_rate() -> float:
        from common.currency import PRIZE_DAMAGE_RATE
        return PRIZE_DAMAGE_RATE

    def _attach_body_view(self, target: dict | None):
        """The :class:`BodyView` the affordability family is keyed on. None with no model."""
        model = self._state_model
        if model is None or not target:
            return None
        return next((b for b in model.mine.bodies if b.body is target), None)

    def _reusable_hand_energy_id(self, obs: dict):
        """A REUSABLE (non-`discard_eot`) Energy card id in my hand — the alternative a burst's
        tonight-credit is capped against (ADR-0069 §5b). `_has_reusable_energy` projects this."""
        return self._reusable_energy_id(self._my_player(obs).get("hand") or [])

    def _attacker_alternative_in_play(self, obs: dict, target: dict | None) -> bool:
        """Is another attacker on my board now — what makes the role gate BOARD-EVALUATED (ADR-0069 §4).
        IN PLAY, never "could use THIS colour": the per-provision variant was measured and inverts."""
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
        """An in-play one-shot utility ex whose value is already cashed. NARROWER than the utility-body
        read — engine bodies still bank mobility through Retreat Equity; this one banks nothing."""
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

    def _attach_position_delta(self, obs: dict, option: dict) -> float:
        """Canonical Active-position marginal, crossed once from prizes into damage currency."""
        if self._state_model is None:
            return 0.0
        from common import board_delta, currency, state_value
        try:
            delta = board_delta.transition(
                obs, option, seat_index=int(self._state_model.my_index), combat=self.combat,
                context=((obs.get("select") or {}).get("context")))
            after = self._state_model.rebuilt(delta.obs, reuse_their_side=delta.shares_opponent)
        except board_delta.Unmodellable:
            return 0.0
        return state_value.active_position_delta(self._state_model, after) * currency.PRIZE_DAMAGE_RATE

    def _attach_value(self, obs: dict, select: dict, board: Board, option: dict):
        """Price ONE attach option as an AXES-SUM (ADR-0069): MAX within the attack axis (its terms
        re-read one progress), SUM across the channels. A Tool routes to its own channel."""
        ctx = select.get("context")
        is_attach = option.get("type") == _ATTACH
        is_from = ctx == _ATTACH_FROM and option.get("type") == _CARD
        if not (is_attach or is_from):
            return None
        ecid = self._option_card_id(obs, select, option)
        estat = self.stats.get(ecid) if (self.stats and ecid is not None) else None
        if is_attach and not self._attach_is_energy(estat):
            return self._tool_attach_value(obs, board, option, ecid, estat)
        target = self._attach_target(obs, option)
        if target is None and is_from:
            target = self._option_pokemon(obs, select, option)
        if target is None:
            return None
        tcid = target.get("id")
        target_stat = self.stats.get(tcid) if (self.stats and tcid is not None) else None
        # The recipient's board AREA: `inPlayArea` for a manual ATTACH, `area` for an ATTACH_FROM
        # recipient pick (which the engine may point at the Active, so the survival gate must see it).
        area = option.get("inPlayArea") if is_attach else option.get("area", _BENCH)
        etags = set(self.functions.tags(ecid)) if (self.functions and is_attach and ecid is not None) else set()
        burst = "discard_eot" in etags
        # The PROVISION, off the ONE seam (Issue #418) — a CARD FACT (Ignition gives {C} on a Basic and
        # {C}{C}{C} on an Evolution). An ATTACH_FROM's colour is unfixed: one wild unit, fail-open.
        codes = self.combat.provision_codes_or_floor(ecid, target_stat) if is_attach else ()
        units = len(codes) if is_attach else 1
        provision = (self.combat.units_for_codes(codes) if is_attach
                     else self.combat.wild_units(units))
        build_supply = None
        if self._state_model is not None:
            from common.strategy.combat_math.budget import WILD_CODE
            build_supply = (self._state_model.energy_supply_from_card(ecid)
                            if is_attach and ecid is not None else
                            self._state_model.energy_supply_for_units((WILD_CODE,) * units))
        # A ready benched wincon I can pivot into dominates whatever the doomed Active could swing for.
        # The pivot must be LEGAL NOW — only the MENU can say so; `bench_wincon_ready` alone cannot.
        arm_dominated = (area == _ACTIVE and board.active_doomed and board.bench_wincon_ready
                         and any(o.get("type") == _RETREAT for o in (select.get("option") or ())))
        visible_retreat = any(o.get("type") == _RETREAT for o in (select.get("option") or ()))
        # Only the ACTIVE fires this turn, and the player going FIRST cannot attack on its turn 1
        # (rules.md §2 / rulebook L152). A benched recipient can also fire tonight when the
        # doomed Active has a legal retreat on the root menu; this is still an attach MARGINAL, not
        # credit for the promoted body's whole attack.
        view = self._attach_body_view(target)
        can_attack_tonight = (area == _ACTIVE and board.turn > 1 and view is not None
                              and not arm_dominated)
        can_pivot_tonight = (area == _BENCH and board.turn > 1 and view is not None
                             and board.active_doomed and visible_retreat)
        this_turn = base_dmg = committed_dmg = 0.0
        if (can_attack_tonight or can_pivot_tonight) and is_attach:
            mine = self._state_model.mine
            base_dmg = mine.best_reachable_damage(view, manual_spent=True)
            committed_dmg = mine.best_reachable_damage(view, extra_unit_codes=codes,
                                                       manual_spent=True)
            pivot_alternative = (max((mine.best_reachable_damage(body, manual_spent=True)
                                      for body in mine.bench if body is not view), default=0.0)
                                 if can_pivot_tonight else 0.0)
            this_turn = max(0.0, committed_dmg - max(base_dmg, pivot_alternative))
            opp_hp = (self._opp_active(obs) or {}).get("hp", 0) or 0
            if can_pivot_tonight and base_dmg >= opp_hp > 0:
                this_turn = 0.0                 # the pivot's existing attack already takes the KO
            if burst and this_turn > 0:
                this_turn = self._burst_capped_tonight(obs, view, target_stat, this_turn,
                                                       base_dmg, committed_dmg)
        # The survival gate: a doomed carrier banks no forward build — EXCEPT a wincon-Line
        # pre-evolution, whose Energy carries through evolution (the evolution-escape).
        survives = not (area == _ACTIVE and board.active_doomed)
        # A `discard_eot` burst earns NO build, ever: build is FORWARD value and the card is discarded
        # at end of turn. Only `this_turn` — what it cashes before it goes — can credit a burst.
        build = (self._attach_build_delta(target, build_supply)
                 if (not burst and (survives or tcid in self._line_preevo_set())) else 0.0)
        accel_value = 0.0
        feeds_accel = (area == _ACTIVE and "accel_source" in self._roles_of(tcid)
                       and self._attach_target_needs(target)
                       and not board.accel_recipient_missing and not board.bench_wincon_ready)
        if feeds_accel:
            aid = self._accel_attack_id(tcid)
            ast = self._attack_stat(aid) if aid is not None else None
            if ast is not None:
                # EXPECTED routing for a VALUATION: printed ceiling capped by recipient need. The live
                # COMMITMENT (`_recover_units`) also floors it by the prize-paranoid deck-fuel bound.
                routed = min(getattr(ast, "recoverN", 0), self._recover_recipient_need(ast, board, obs))
                accel_value = self._accel_routed_value(obs, board, routed, ast)
        # The bodies the deck's PLAN attacks with — ADR-0048's BROADENED set. The narrower sets stay
        # narrow on purpose: the pre-evo discount and evolution-escape read win-condition-only.
        line_ids = self._recognized_line_preevo_set() | self._wincon_set()
        # A body given ROLES, none of them an attacker Role, is a DECLARED non-attacking plan piece.
        # Read here rather than by widening `_is_utility_body`, so the effect stays in the attack axis.
        declared = set(self._roles_of(tcid))
        non_attacking = tcid not in line_ids and (
            self._is_utility_body(tcid) or self._is_draw_engine_body(tcid)
            or self._partner_absent(tcid, obs)
            or (bool(declared) and not (_ATTACKER_ROLES & declared)))
        attacker_alternative = self._attacker_alternative_in_play(obs, target)
        role_gated = non_attacking and attacker_alternative
        spent_utility_gated = self._is_spent_utility_liability(tcid) and attacker_alternative
        # The OVERKILL cap: a bigger attack buys nothing once what the Active affords NOW already
        # covers their biggest body. Opponent-aware, so a bench threat that out-HPs it stands it down.
        overkill = False
        if area == _ACTIVE and board.active_cheap_attack_kos:
            opp_hp = self._opp_body_hps(obs)
            # DELIBERATE CombatMath bypass (POC-T1's documented list): the EMPTY-Budget leg has no
            # model expression — the model's route always carries the FULL Budget.
            if opp_hp and max(opp_hp) <= self.combat.best_reachable_damage(target, budget=Budget()):
                overkill = True
        # EVAPORATION, global: an uncashed `discard_eot` Energy costs what it was worth.
        gated_off = role_gated or spent_utility_gated
        cashed = this_turn > 0 and not gated_off and not overkill
        evaporates = burst and not cashed
        resource_cost = self._role_value(ecid) if (is_attach and ecid is not None) else 0.0
        evaporation_loss = resource_cost if evaporates else 0.0
        attack_axis = 0.0 if (gated_off or overkill or evaporates) else max(
            this_turn, build, accel_value, 0.0)
        # A burst can cash out through an attack OR a manual retreat before it evaporates, never
        # both. A doomed Active's newly unlocked Retreat is likewise absent from this root menu, so
        # neither live ranking nor the root-option composer can commit the claimed continuation.
        # Exact visible Retreat remains legal and is priced when actually chosen.
        phantom_doomed_retreat = area == _ACTIVE and board.active_doomed and not visible_retreat
        retreat_equity = (0.0 if (spent_utility_gated or burst or phantom_doomed_retreat)
                          else self._attach_position_delta(obs, option))
        ability_fuel = (_ATTACH_ABILITY_FUEL if (not spent_utility_gated and not burst and is_attach
                                                and self._attach_fuels_dormant_ability(estat, target))
                        else 0.0)
        marginal = attack_axis + retreat_equity + ability_fuel - evaporation_loss
        # Charged on worth ABOVE a reusable Basic, so a plain Basic pays nothing.
        tactical = (marginal * _ATTACH_VALUE_SCALE
                    - _ATTACH_RESOURCE_TIEBREAK * max(0.0, resource_cost - ENERGY_TIER))
        # The resolved target SLOT, not the raw option index (duplicate sources would read as false
        # disagreements). ATTACH carries inPlayArea/inPlayIndex; ATTACH_FROM carries area/index.
        slot = [area, option.get("inPlayIndex") if is_attach else option.get("index")]
        return _attach_row(
            target=tcid, energy=ecid, slot=slot,
            marginal=round(marginal, 2), tactical=round(tactical, 2),
            attack_axis=round(attack_axis, 2), this_turn=round(this_turn, 2),
            build=round(build, 2), accel_value=round(accel_value, 2),
            retreat_equity=round(retreat_equity, 2), ability_fuel=round(ability_fuel, 2),
            evaporation_loss=round(evaporation_loss, 2), units=units,
            role_gated=role_gated, spent_utility_gated=spent_utility_gated,
            overkill=overkill, doomed=not survives,
            burst=burst, evaporates=evaporates,
            line_value=round(0.0 if gated_off else self._role_value(tcid), 1),
            resource_cost=round(resource_cost, 1))

    def _tool_attach_value(self, obs: dict, board: Board, option: dict, ecid, estat):
        """Price only the Tool's canonical mobility marginal; survival owns direct HP value."""
        target = self._attach_target(obs, option)
        if target is None:
            return None
        active = self._my_active(obs)
        marginal = self._attach_position_delta(obs, option)
        if marginal == 0.0:
            return None
        resource_cost = self._role_value(ecid) if ecid is not None else 0.0
        tactical = (marginal * _ATTACH_VALUE_SCALE
                    - _ATTACH_RESOURCE_TIEBREAK * max(0.0, resource_cost - ENERGY_TIER))
        return _attach_row(
            target=target.get("id"), energy=ecid,
            slot=[option.get("inPlayArea"), option.get("inPlayIndex")],
            marginal=round(marginal, 2), tactical=round(tactical, 2),
            retreat_equity=round(marginal, 2),
            doomed=bool(target is active and board.active_doomed),
            line_value=round(self._role_value(target.get("id")), 1),
            resource_cost=round(resource_cost, 1))

    def _burst_capped_tonight(self, obs: dict, view, target_stat, this_turn: float,
                              base_dmg: float, committed_dmg: float) -> float:
        """The burst's no-KO CAP (ADR-0069 §5b): a cashable one-shot earns at most what the best
        REUSABLE Basic in hand would tonight — unless its attack converts a KO the Basic cannot."""
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
        """The ONE pricing call per option — the score term and the planner's spend account both read
        it, so neither can price a different attach than the other."""
        if not getattr(self, "attach_value", False):
            return None
        return self._attach_value(obs, select, board, option)

    def _attach_value_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """0 when `attach_value` is OFF — DEGRADED MODE, not a rollback: the rungs this replaced are
        deleted. SIGNED, and allowed to go NEGATIVE, so an attach can score below ending the turn."""
        row = self._attach_decision(obs, select, board, option)
        return 0.0 if row is None else row["tactical"]

    def _attach_working(self, obs: dict, select: dict, board: Board, options: list):
        """The attach decider's LEGIBLE WORKING (ADR-0069 §9). A Tool no channel prices ABSTAINS and is
        counted. None off an attach menu or mid-sim (`self._planning`), so the wire key stays sparse."""
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
            if row is None:                                    # no channel prices it — no row
                abstained += 1
                continue
            row["i"] = i
            rows.append(row)
        return {"eq": rows, "abstained": abstained} if rows else None

    def _attach_sequence_override(self, obs: dict, select: dict, board: Board, options: list,
                                  traces: list, composed_index: int, *, composed_result=None,
                                  score_epsilon: float = 0.0, same_line_only: bool = False):
        """Use a positive persistent setup attach before a non-winning turn ender.

        The composer correctly charges the card leaving hand, but its one-board leaf has no value
        for the manual-attach allowance that expires at turn end.  This boundary prices that tempo
        only when the attach either unlocks an immediate attack or advances the already-started
        primary line, and its benefit exceeds the shared card cost. Final-prize attacks already
        available at the root remain outside it.

        When the composer's positive line already starts with an attach before a discard-cost play,
        the sequence has paid the whole line's costs. Resolve only the Energy/recipient subdecision
        through this attach equation among near-best positive versions of that same temporal line.
        This prevents the coarse state leaf from sending Energy to an off-role body, while every
        candidate still carries both the Energy's shared Worth and the later discard costs.
        """
        if ((select or {}).get("context") != _MAIN or board.energy_attached
                or not (0 <= composed_index < len(options))
                or options[composed_index].get("type") not in (_ATTACH, _ATTACK, _END)):
            return None
        if options[composed_index].get("type") == _ATTACH:
            chosen = getattr(composed_result, "chosen", None)
            root = getattr(composed_result, "root_value", None)
            candidates = (getattr(composed_result, "selection_candidates", ())
                          or getattr(composed_result, "candidates", ()))
            if chosen is not None and root is not None and candidates:
                def _costed_play(index: int) -> bool:
                    cid = traces[index].card_id if 0 <= index < len(traces) else None
                    return bool(self.functions and cid is not None
                                and "cost_discard" in self.functions.tags(cid))

                eligible = set()
                floor = float(chosen.score) - max(0.0, float(score_epsilon))
                for candidate in candidates:
                    first = candidate.first_index
                    steps = tuple(getattr(candidate, "steps", ()) or ())
                    if (candidate.coverage_gap or candidate.score < floor or candidate.score <= root
                            or first is None or not (0 <= first < len(options))
                            or options[first].get("type") != _ATTACH
                            or not any(_costed_play(step.index) for step in steps[1:])):
                        continue
                    eligible.add(first)

                ranked = []
                for index in eligible:
                    row = self._attach_value(obs, select, board, options[index])
                    if row is None or float(row["tactical"]) <= 0.0:
                        continue
                    net = float(row["tactical"]) - float(row["resource_cost"])
                    ranked.append((net, float(row["tactical"]), -index, index))
                if ranked:
                    winner = max(ranked)[-1]
                    if winner != composed_index:
                        return winner, ("cost-benefit: resolve the positive attach-before-discard line by "
                                        "attach benefit minus shared Energy worth")
            if same_line_only:
                return None

        if (options[composed_index].get("type") == _ATTACK
                and traces[composed_index].tactical >= KO_SCORE and board.active_can_ko
                and self._prize_value(self._opp_active(obs)) >= board.my_prizes_remaining):
            return None                              # no later turn exists to realize setup value
        priority = board.priority_wincon_slot

        candidates = []
        for index, option in enumerate(options):
            if option.get("type") != _ATTACH:
                continue
            row = self._attach_value(obs, select, board, option)
            if row is None:
                continue
            immediate = row["slot"][0] == _ACTIVE and row["this_turn"] > 0.0
            focused = ((priority is None or tuple(row["slot"]) == tuple(priority))
                       and not row["burst"] and row["build"] > 0.0
                       and not (row["slot"][0] == _ACTIVE and board.active_doomed))
            if not (immediate or focused):
                continue
            net = float(row["tactical"]) - float(row["resource_cost"])
            if net > 0.0:
                candidates.append((net, float(row["tactical"]), -index, index))
        if not candidates:
            return None
        winner = max(candidates)[-1]
        if winner == composed_index:
            return None
        return winner, "cost-benefit: realize positive attack/setup attach before ending the turn"
