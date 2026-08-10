"""The promote/retreat decider's Pilot-side half (ADR-0100): assemble `PromoteRetreatInputs`, and pick the
slot that promotes after a KO. Equation: `common/promote_retreat_value.py`. Cost: `common/retreat_cost.py`."""
from __future__ import annotations


from common import board_delta, retreat_cost
from common.card_worth import ENERGY_TIER
from common.deciders.attach import _ATTACH_RESOURCE_TIEBREAK
from common.deciders.facts import Board
from common.deciders.plan_choice import _min_attack_cost
from common.grading import HORIZON as _HORIZON
from common.promote_retreat_value import PromoteBody, PromoteRetreatInputs, promote_value
from common.strategy.context import (_ATTACK, _BENCH, _END, _MAIN, _PLAY, _RETREAT, _SWITCH,
                                     _TO_ACTIVE, KO_SCORE)


# A manual retreat always spends its once-per-turn allowance, even when no valuable build is
# discarded. One existing resource-tiebreak unit gives that real option a strict cost without
# introducing another tuned magnitude.
_RETREAT_ALLOWANCE_COST = _ATTACH_RESOURCE_TIEBREAK


class PromoteRetreatMixin:
    """Board facts for the promote/retreat decider, plus the after-KO promote slot."""

    def _retreat_sequence_override(self, select: dict, board: Board, options: list,
                                   traces: list, composed_index: int):
        """Take a positive retreat that is the only root route to a decisive attack.

        Composer cannot enumerate the replacement Active's newly exposed attack menu from a live
        MAIN snapshot.  The promote/retreat equation already prices the move's yield, position and
        retreat payment, while ``_promote_ko_tactical`` proves the promoted body crosses the KO
        line.  Use that complete benefit-minus-cost verdict over attacking or ending with an Active
        that cannot itself Knock Out the target.
        """
        if ((select or {}).get("context") != _MAIN or board.active_can_ko
                or not (0 <= composed_index < len(options))
                or options[composed_index].get("type") not in (_ATTACK, _END)
                or traces[composed_index].tactical >= KO_SCORE):
            return None
        candidates = []
        for index, option in enumerate(options):
            if option.get("type") != _RETREAT:
                continue
            row = traces[index].promote_retreat_working or {}
            net = float(row.get("total") or 0.0)
            if net <= 0.0 or traces[index].tactical < KO_SCORE:
                continue
            candidates.append((net, float(traces[index].tactical), -index, index))
        if not candidates:
            return None
        winner = max(candidates)[-1]
        return winner, "cost-benefit: retreat is the positive route to the decisive attack"

    def _promote_body(self, obs: dict, board: Board, raw: dict | None, *, draws: int = 0) -> PromoteBody:
        """Read one body as Active into the sub-lethal promote residual (ADR-0100 §3-§7)."""
        from common.state_model import BodyView
        raw = raw or {}
        model = self._state_model
        mine = model.mine if model is not None else None
        view = BodyView(raw, combat=self.combat, is_active=True)
        # CARD RULE (`docs/rules.md` §2): no attack on turn 1, so a body promoted then earns NO yield.
        can_swing = board.turn > 1
        if mine is not None and can_swing:
            from common.currency import PRIZE_DAMAGE_RATE
            reach = model.combat_realization(view).now_prizes * PRIZE_DAMAGE_RATE
        else:
            reach = 0.0
        opp = self._opp_player(obs) or {}
        opp_active = (model.theirs.active_raw if model is not None
                      else next((p for p in (opp.get("active") or []) if p), None))
        # No `charged=`: each clock takes the Read's threaded `_incoming_budget` (POC-T1).
        clock = dict(context=self._opp_attack_context,
                     key_ids=self._harvest_key_ids(), opp_active=opp_active,
                     switch_enabler=self._opp_switch_enabler())
        if model is None:
            ko_active = _HORIZON                       # no snapshot: make NO claim (fail-safe)
        else:
            ko_active = model.theirs.turns_to_ko_me(raw, my_benched=False,
                                                    my_bench=self._my_bench_raws(obs), **clock)
        cid = raw.get("id")
        tags = self.functions.tags(cid) if (self.functions and cid is not None) else []
        return PromoteBody(
            reach=reach,
            # Same card rule: the race leg REPLACES `reach`, so ungated it re-introduces turn-1 damage.
            wall_progress=self._promote_wall_progress(obs, board, raw) if can_swing else None,
            accel_value=self._promote_accel_value(obs, board, raw) if can_swing else 0.0,
            closure=self._promote_closure(obs, raw, draws=draws if can_swing else 0),
            prizes=self._prize_value(raw),
            ko_active=ko_active,
            tempo_step=self._promote_tempo_step(raw),
            denies_items=("item_lock" in tags and self._opp_items_live()),
            opp_prizes_remaining=board.opp_prizes_remaining,
            takes_ko=self._promote_body_kos(obs, board, raw))

    def _promote_wall_progress(self, obs: dict, board: Board, raw: dict) -> float | None:
        """Per-turn wall progress (``hp / t_star``) for a body promoted into a STANDING wall, else None
        (ADR-0040, ADR-0100 §3a). No chip term — that tie-break is within one body, not across bodies."""
        from common.strategy.objectives import race_values
        if not getattr(self, "objectives_race", False):
            return None
        opp = self._opp_active(obs)
        hp = (opp or {}).get("hp", 0)
        cid = (raw or {}).get("id")
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if not (hp and stat and stat.attacks):
            return None
        energy = len(raw.get("energies") or [])
        table = {}
        for aid in (stat.attacks or ()):
            if self.combat.attack_cost(aid) > energy:
                continue                              # not affordable on the Energy it carries
            dmg = self.predicted_damage(cid, aid, opp)
            if dmg <= 0:
                continue
            if dmg >= hp:
                return None                           # no wall — B takes the KO, the KO layer's turf
            table[aid] = (dmg, 0)                     # chip omitted deliberately
        vals = race_values(table, hp)
        if not vals:
            return None
        return hp / min(t_star for t_star, _chip in vals.values())

    def _promote_accel_value(self, obs: dict, board: Board, raw: dict) -> float:
        """Best affordable acceleration rider through the canonical exhaustive allocation."""
        import math
        model = self._state_model
        cid = (raw or {}).get("id")
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if model is None or not (stat and stat.attacks):
            return 0.0
        from common.currency import PRIZE_DAMAGE_RATE
        from common.strategy.combat_math.budget import WILD_CODE
        attached = len(raw.get("energies") or [])
        best = 0.0
        for aid in stat.attacks or ():
            attack = self._attack_stat(aid)
            if attack is None or self.combat.attack_cost(aid) > attached:
                continue
            usable = self._recover_units(aid, {}, board, obs)
            if usable <= 0.0:
                continue
            whole = max(1, int(math.ceil(usable)))
            code = (attack.recoverEnergyType
                    if attack.recoverEnergyType is not None else WILD_CODE)
            allocation = model.allocate_recovery_energy(attack.recoverTarget, (code,) * whole)
            best = max(best, allocation.value_prizes * min(1.0, usable / whole)
                       * PRIZE_DAMAGE_RATE)
        return best

    def _promote_closure(self, obs: dict, raw: dict, *, draws: int) -> float:
        """``max`` over attacks of ``damage(a) x [readiness_p(a | enabler) - readiness_p(a)]`` — the odds
        this turn's dig readies an unready body (ADR-0100 §5). Fail-CLOSED at 0.0 throughout (ADR-0067)."""
        from common.currency import PRIZE_DAMAGE_RATE
        from common.deck_odds import draw_hit_probability
        model = self._state_model
        mine = model.mine if model is not None else None
        cid = (raw or {}).get("id")
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if draws <= 0 or mine is None or not (raw and stat and stat.attacks):
            return 0.0
        pool = mine.deck_count
        best = 0.0
        for etype, count in (mine.deck_energy_counts or {}).items():
            copies = int(getattr(count, "expected", count) or 0)
            probability = draw_hit_probability(copies, pool, draws)
            delta = model.readiness_supply_delta(raw, model.energy_supply_for_units((etype,)))
            best = max(best, max(0.0, delta) * PRIZE_DAMAGE_RATE * probability)
        return best

    def _promote_tempo_step(self, raw: dict) -> float:
        """``incoming(t=2) - incoming(t=1)`` against the body that would be my Active — one development
        step's threat growth off the Threat-Clock curve (ADR-0100 §6). 0.0 without a snapshot."""
        model = self._state_model
        if model is None or not raw:
            return 0.0
        ctx = self._opp_attack_context
        return float(max(0, model.theirs.incoming(raw, 2, context=ctx)
                         - model.theirs.incoming(raw, 1, context=ctx)))

    def _opp_items_live(self) -> bool:
        """Does the opponent PROVABLY still hold live Item copies — the gate on `tempo_denied`
        (ADR-0100 §6). Fail-CLOSED, unlike a survival read: this term ENDORSES a play (ADR-0067)."""
        if self.opponent is None or not self.stats:
            return False
        try:
            odds = self.opponent.copies_left_odds()
            if not odds:                              # unrecognised opponent — claim nothing
                return False
            return any(p > 0 for cid, p in odds.items()
                       if (st := self.stats.get(cid)) is not None and st.is_item)
        except Exception:
            return False

    def _promote_body_kos(self, obs: dict, board: Board, raw: dict) -> bool:
        """Does this body take a Knock Out on arrival — ruling 5's fatal-step stand-down. MAGNITUDE is
        `_promote_ko_tactical`'s, summed on the same option (ADR-0100 §1, §11)."""
        opp = self._opp_active(obs)
        if not (opp and opp.get("hp") and raw):
            return False
        return self._best_affordable_ko_value(
            obs, board, opp, raw.get("id"), len(raw.get("energies") or []), body=raw) > 0

    def _turn_dig_depth(self, obs: dict) -> int:
        """The cards this turn's REMAINING dig still reaches — the closure term's draw window
        (ADR-0100 §5). The MENU is the fact about whether a use is left (ADR-0070 §7)."""
        if self.functions is None:
            return 0
        me = self._my_player(obs) or {}
        bodies = [p for p in ((me.get("active") or []) + (me.get("bench") or [])) if p]
        return sum(self.functions.dig_depth(b.get("id")) for b in bodies
                   if b.get("id") is not None and self._ability_on_menu(obs, b.get("id")))

    def _retreat_resource_premium(self, active: dict, discarded_indices) -> float:
        """Tie-break cost of the physical Energy cards one exact payment discards."""
        cards = list(active.get("energyCards") or ())
        return _ATTACH_RESOURCE_TIEBREAK * sum(
            max(0.0, self._role_value((cards[index] or {}).get("id")) - ENERGY_TIER)
            for index in discarded_indices if 0 <= int(index) < len(cards))

    @staticmethod
    def _persistent_residual(val) -> float:
        """Consequences not owned by the canonical position projection."""
        return val.my_yield + val.closure + val.tempo_denied - val.fatal

    def _promote_retreat_decision(self, obs: dict, select: dict, board: Board, ctx, option: dict):
        """The PROMOTE/RETREAT DECIDER: price ONE option (ADR-0100). Returns the TERM row, or None to
        abstain. ONE evaluator for §9's `pick` and `whether` sites, so the two cannot diverge."""
        if not getattr(self, "promote_retreat_value", False):
            return None
        sctx, otype = ctx.select_context, ctx.option_type
        my_index = (obs.get("current") or {}).get("yourIndex", 0)
        if sctx in (_TO_ACTIVE, _SWITCH):
            if option.get("playerIndex") not in (None, my_index):
                return None                           # a Boss's-gust target — the gust equation's turf
            raw = self._option_pokemon(obs, select, option)
            if not raw:
                return None
            # §5: at a FORCED promote no play window remains, so no dig can happen.
            draws = 0 if sctx == _TO_ACTIVE else self._turn_dig_depth(obs)
            body = self._promote_body(obs, board, raw, draws=draws)
            val = promote_value(PromoteRetreatInputs(body=body))
            position = 0.0
            if self._state_model is not None:
                from common import board_choice, currency, state_value
                try:
                    after = board_choice.promoted_active_model(
                        self._state_model, int(option.get("index")))
                    position = state_value.position_state_value(after) * currency.PRIZE_DAMAGE_RATE
                except (TypeError, ValueError, board_delta.Unmodellable):
                    position = 0.0
            return self._promote_row(val, site="pick", position_delta=position)
        if sctx != _MAIN:
            return None
        is_switch_item = (otype == _PLAY and "switch" in (ctx.tags or []))
        if otype != _RETREAT and not is_switch_item:
            return None
        active = self._my_active(obs)
        if active is None:
            return None                               # no readable Active — make no claim
        draws = self._turn_dig_depth(obs)
        if self._state_model is None:
            return None
        from common import board_choice, currency, state_value
        before_position = state_value.position_state_value(self._state_model)
        candidates = []
        if otype == _RETREAT:
            for outcome in board_choice.legal_manual_retreat_outcomes(self._state_model):
                candidates.append((outcome.bench_index, outcome.model,
                                   _RETREAT_ALLOWANCE_COST
                                   + self._retreat_resource_premium(
                                       active, outcome.discard_indices)))
        else:
            worth = max(0.0, self._role_value(ctx.card_id))
            for index, raw in enumerate(self._my_bench_raws(obs)):
                if raw:
                    try:
                        candidates.append((index, board_choice.promoted_active_model(
                            self._state_model, index), worth))
                    except board_delta.Unmodellable:
                        continue
        best_row = None
        for index, after, resource_cost in candidates:
            raw = self._my_bench_raws(obs)[index]
            val = promote_value(PromoteRetreatInputs(
                body=self._promote_body(obs, board, raw, draws=draws)))
            position = ((state_value.position_state_value(after) - before_position)
                        * currency.PRIZE_DAMAGE_RATE)
            row = self._promote_row(val, site="whether", position_delta=position,
                                    resource_cost=resource_cost)
            if best_row is None or row["total"] > best_row["total"]:
                best_row = row
        return best_row

    @staticmethod
    def _promote_row(val, *, site: str, position_delta: float = 0.0,
                     resource_cost: float = 0.0) -> dict:
        """The decider's per-option working (ADR-0008/0019), rounded for the wire. No agreement bit:
        this DECIDES, so there is one emission path."""
        residual = PromoteRetreatMixin._persistent_residual(val)
        total = residual + float(position_delta) - float(resource_cost)
        return {"site": site, "tactical": total,
                "my_yield": round(val.my_yield, 2), "closure": round(val.closure, 2),
                "exposure": 0.0, "tempo_denied": round(val.tempo_denied, 2),
                "fatal": round(val.fatal, 2), "preservation": 0.0,
                "retreat_cost": round(resource_cost, 2),
                "position_delta": round(position_delta, 2), "total": round(total, 2)}

    def _promote_ko_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """KO_SCORE-class value for the body PICK that takes the prize (ADR-0100 §11) — the Solver and
        the Planner are MAIN-only, so at TO_ACTIVE/SWITCH no other layer prices the KO. One kill-switch."""
        if not getattr(self, "promote_retreat_value", False):
            return 0.0
        if select.get("context") not in (_TO_ACTIVE, _SWITCH):
            return 0.0
        my_index = (obs.get("current") or {}).get("yourIndex", 0)
        if option.get("playerIndex") not in (None, my_index):
            return 0.0                                # a gust target (opponent body), not my pick
        opp = self._opp_active(obs)
        if not (opp and opp.get("hp")):
            return 0.0
        raw = self._option_pokemon(obs, select, option)
        if not raw:
            return 0.0
        return self._best_affordable_ko_value(
            obs, board, opp, raw.get("id"), len(raw.get("energies") or []), body=raw)

    def _effective_retreat_cost(self, obs: dict, ma: dict | None) -> int:
        """The Active's EFFECTIVE Retreat Cost in Energy (ADR-0100 §8). Grants fail-CLOSED to the PRINTED
        cost. Takes ``obs`` because `retreatFreeGrant` lives on ANOTHER of my bodies, not the retreater."""
        return retreat_cost.effective_retreat_cost(
            ma, stat_of=self._stat_of, my_bodies=self._my_in_play_raws(obs), combat=self.combat)

    def _attached_retreat_delta(self, body: dict | None) -> int:
        """Σ ``retreatReduction`` over the Tools attached to ``body`` — the SIGNED amount to SUBTRACT
        from a printed Retreat Cost (`common.retreat_cost`, Issue #306)."""
        return retreat_cost.attached_retreat_delta(body, self._stat_of)

    def _can_retreat(self, ma: dict | None) -> bool:
        """My Active can pay its Retreat Cost this turn. `_attached_retreat_delta` is SIGNED and
        SUBTRACTED. Fail-CLOSED on an unknown stat: a KO_SCORE claim must not assume an unproven retreat."""
        if not ma or not self.stats:
            return False
        stat = self.stats.get(ma.get("id"))
        if stat is None:
            return False
        cost = max(0, getattr(stat, "retreatCost", 0) - self._attached_retreat_delta(ma))
        try:
            return bool(retreat_cost.payment_options(
                ma, cost, stat_of=self.stats.get, combat=self.combat))
        except board_delta.Unmodellable:
            return False

    def _promote_target_kos(self, obs: dict, select: dict, option: dict) -> bool:
        """At a TO_ACTIVE promote, can the body this option brings up Knock Out the opp Active this turn?
        Fail-closed on missing stats/target."""
        poke = self._option_pokemon(obs, select, option)
        if not poke:
            return False
        stat = self.stats.get(poke.get("id")) if self.stats else None
        return self._can_ko(stat, self._opp_active(obs))

    def _promote_target_can_attack(self, obs: dict, select: dict, option: dict) -> bool:
        """At a TO_ACTIVE promote, can the body this option brings up attack this turn? — a live
        interposer, not a dead wall. Fail-closed on missing context/stats/target."""
        if select.get("context") != _TO_ACTIVE:
            return False
        poke = self._option_pokemon(obs, select, option)
        cid = (poke or {}).get("id")
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if not (poke and stat and stat.minAttackCost is not None):
            return False
        return len(poke.get("energies") or []) >= stat.minAttackCost

    def _promote_target_hits_weakness(self, obs: dict, select: dict, option: dict) -> bool:
        """At a TO_ACTIVE promote, would the body this option brings up strike the opp Active on its
        Weakness (so, doubled — `docs/rules.md` §5)? Fail-closed on missing context/stats/Active."""
        if select.get("context") != _TO_ACTIVE:
            return False
        poke = self._option_pokemon(obs, select, option)
        stat = self.stats.get((poke or {}).get("id")) if (self.stats and poke) else None
        oa = self._opp_active(obs)
        opp_stat = self.stats.get((oa or {}).get("id")) if (self.stats and oa) else None
        return bool(stat and opp_stat and stat.energyType is not None
                    and opp_stat.weakness is not None and opp_stat.weakness == stat.energyType)

    def _best_promote_slot(self, me: dict) -> tuple | None:
        """(_BENCH, index) of the READY benched win-condition carrying the MOST Energy; None when none is
        ready. Distinct from `_priority_wincon_slot`, which targets the one still UNDER its max attack."""
        wincon = self._wincon_set()
        if not wincon:
            return None
        best = None                                   # (energy, index)
        for i, p in enumerate(me.get("bench") or []):
            if p and p.get("id") in wincon:
                e = len(p.get("energies") or [])
                if e >= _min_attack_cost(self.stats, p.get("id")) and (best is None or e > best[0]):
                    best = (e, i)
        return (_BENCH, best[1]) if best else None

    def _ko_aware_promote_slot(self, obs: dict, board: Board, me: dict,
                               opp: dict | None) -> tuple | None:
        """(_BENCH, index) of the benched body whose best affordable attack — counting this turn's unspent
        attach and a playable boost — KOs the opp Active. A steering signal, not a Lethal lock."""
        if not (opp and opp.get("hp")):
            return None
        ma = next((p for p in (me.get("active") or []) if p), None)
        bench = me.get("bench") or []
        hand_ids = frozenset(c.get("id") for c in (me.get("hand") or [])
                             if c and c.get("id") is not None)
        hand_basic = self._hand_basic_energy(me.get("hand") or [])       # {EnergyType: count}
        best = None                                                      # (energy, index)
        for i, p in enumerate(bench):
            if not p:
                continue
            e = len(p.get("energies") or [])
            pstat = self.stats.get(p.get("id")) if self.stats else None
            # typed to the body's own Energy when the hand holds that Basic, else WILD (fail-open)
            if not board.energy_attached and self._best_hand_attach_units(hand_ids, pstat) >= 1:
                planned = 1
                ptype = (pstat.energyType if (pstat and pstat.energyType in hand_basic) else None)
            else:
                planned, ptype = 0, None
            boost = self._typed_boost_total(obs, pstat, opp)
            bench_names = self._promote_bench_names(me, i, ma)
            ko = self._best_affordable_ko_value(
                obs, board, opp, p.get("id"), e + planned, bound="min", body=p,
                extra_type=ptype, extra_units=planned, boost_amount=boost,
                boost_type=(pstat.energyType if pstat else None), promote_bench_names=bench_names)
            if ko > 0 and (best is None or e > best[0]):
                best = (e, i)
        return (_BENCH, best[1]) if best else None

    def _promote_bench_names(self, me: dict, promoted_index: int, ma: dict | None) -> set:
        """Names on my Bench AFTER promoting slot ``promoted_index`` — the others plus the retreating
        Active. The `requiresBench` partner set a promoted attacker can count on."""
        names = set()
        for j, b in enumerate(me.get("bench") or []):
            if j == promoted_index or not b:
                continue
            st = self.stats.get(b.get("id")) if self.stats else None
            if st is not None and st.name:
                names.add(st.name)
        ma_stat = self.stats.get((ma or {}).get("id")) if (self.stats and ma) else None
        if ma_stat is not None and ma_stat.name:
            names.add(ma_stat.name)
        return names

    def _forced_promotion_key(self, opp: dict, doomed: bool) -> int | None:
        """ADR-0044 Forced-Promotion Read: with their Active doomed, they promote their highest
        OWN-damage READY bench attacker. Returns ``id(body)`` for duplicate-safe matching."""
        if not doomed or not self.stats:
            return None
        best = None                                          # (own_damage, hp, id(body))
        for b in (opp.get("bench") or []):
            if not b:
                continue
            stat = self.stats.get(b.get("id"))
            own = self._threat_own_damage(b.get("id"), stat)
            if own <= 0:
                continue
            if getattr(stat, "tera", False):
                continue                                     # Tera on the Bench takes no damage
            reach = len(b.get("energies") or []) + 1         # + the manual attach on their promote turn
            min_cost = getattr(stat, "minAttackCost", None) if stat else None
            if min_cost is not None and reach < min_cost:
                continue                                     # can't attack next turn — not their promote
            cand = (own, b.get("hp", 0), id(b))
            if best is None or cand[:2] > best[:2]:
                best = cand
        return best[2] if best else None
