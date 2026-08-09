"""The promote/retreat decider's Pilot-side half (ADR-0100): assemble `PromoteRetreatInputs`, and pick the
slot that promotes after a KO. Equation: `common/promote_retreat_value.py`. Cost: `common/retreat_cost.py`."""
from __future__ import annotations


from common import retreat_cost
from common.card_worth import ENERGY_TIER
from common.deciders.attach import _ATTACH_RESOURCE_TIEBREAK
from common.deciders.facts import Board
from common.deciders.plan_choice import _min_attack_cost
from common.grading import HORIZON as _HORIZON
from common.promote_retreat_value import PromoteBody, PromoteRetreatInputs, RetreatSide, promote_value
from common.strategy.combat import HARVEST_UNAVOIDABLE
from common.strategy.context import _BENCH, _MAIN, _PLAY, _RETREAT, _SWITCH, _TO_ACTIVE



class PromoteRetreatMixin:
    """Board facts for the promote/retreat decider, plus the after-KO promote slot."""

    def _promote_body(self, obs: dict, board: Board, raw: dict | None, *, draws: int = 0,
                      bench_after=None) -> PromoteBody:
        """Read ONE body AS THE ACTIVE into the decider's damage-currency view (ADR-0100 §3-§7).
        ``bench_after`` (RETREATING Active only) arms `preservation`; without it that leg reads 0."""
        from common.state_model import BodyView
        raw = raw or {}
        model = self._state_model
        mine = model.mine if model is not None else None
        view = BodyView(raw, combat=self.combat, is_active=True)
        # CARD RULE (`docs/rules.md` §2): no attack on turn 1, so a body promoted then earns NO yield.
        can_swing = board.turn > 1
        reach = float(mine.best_reachable_damage(view)) if (mine is not None and can_swing) else 0.0
        opp = self._opp_player(obs) or {}
        opp_active = (model.theirs.active_raw if model is not None
                      else next((p for p in (opp.get("active") or []) if p), None))
        # No `charged=`: each clock takes the Read's threaded `_incoming_budget` (POC-T1).
        clock = dict(context=self._opp_attack_context,
                     key_ids=self._harvest_key_ids(), opp_active=opp_active,
                     switch_enabler=self._opp_switch_enabler())
        if model is None:
            ko_active = ko_bench = _HORIZON           # no snapshot: make NO claim (fail-safe)
        else:
            ko_active = model.theirs.turns_to_ko_me(raw, my_benched=False,
                                                    my_bench=self._my_bench_raws(obs), **clock)
            if bench_after is None:
                ko_bench = ko_active                  # not asked — `preservation` reads 0, never a
            else:                                     # phantom rescue credit
                # A RESCUE read, so it declares UNAVOIDABLE (ADR-0071 decision 3): a redirectable
                # benched KO denies nothing, and crediting it inflates every bench rescue.
                ko_bench = model.theirs.turns_to_ko_me(raw, my_benched=True,
                                                       my_bench=list(bench_after),
                                                       reading=HARVEST_UNAVOIDABLE, **clock)
        cid = raw.get("id")
        tags = self.functions.tags(cid) if (self.functions and cid is not None) else []
        hand = (self._my_player(obs) or {}).get("hand") or ()
        no_energy_in_hand = not any(
            (st := self._stat_of((card or {}).get("id"))) is not None and st.is_energy
            for card in hand)
        mobility = (0.1 * self._effective_retreat_cost(obs, raw)
                    if not (raw.get("energies") or []) and no_energy_in_hand else 0.0)
        return PromoteBody(
            reach=reach,
            # Same card rule: the race leg REPLACES `reach`, so ungated it re-introduces turn-1 damage.
            wall_progress=self._promote_wall_progress(obs, board, raw) if can_swing else None,
            accel_units=self._promote_accel_units(obs, board, raw) if can_swing else 0.0,
            closure=self._promote_closure(obs, raw, draws=draws if can_swing else 0),
            prizes=self._prize_value(raw),
            ko_active=ko_active, ko_bench=ko_bench,
            tempo_step=self._promote_tempo_step(raw),
            denies_items=("item_lock" in tags and self._opp_items_live()),
            opp_prizes_remaining=board.opp_prizes_remaining,
            takes_ko=self._promote_body_kos(obs, board, raw),
            mobility_cost=mobility)

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

    def _promote_accel_units(self, obs: dict, board: Board, raw: dict) -> float:
        """Energy this body's accel rider would attach AND a recipient can USE (ADR-0100 §3b).
        `max` over AFFORDABLE attacks: it commits to one and picks the best (ADR-0069 §1)."""
        cid = (raw or {}).get("id")
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if not (stat and stat.attacks):
            return 0.0
        energy = len(raw.get("energies") or [])
        best = 0.0
        for aid in (stat.attacks or ()):
            if self.combat.attack_cost(aid) <= energy:
                best = max(best, self._recover_units(aid, {}, board, obs))
        return best

    def _promote_closure(self, obs: dict, raw: dict, *, draws: int) -> float:
        """``max`` over attacks of ``damage(a) x [readiness_p(a | enabler) - readiness_p(a)]`` — the odds
        this turn's dig readies an unready body (ADR-0100 §5). Fail-CLOSED at 0.0 throughout (ADR-0067)."""
        from common.state_model import BodyView
        model = self._state_model
        mine = model.mine if model is not None else None
        cid = (raw or {}).get("id")
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if draws <= 0 or mine is None or not (raw and stat and stat.attacks):
            return 0.0
        view = BodyView(raw, combat=self.combat, is_active=True)
        pool = mine.deck_count
        best = 0.0
        for aid in (stat.attacks or ()):
            dmg = float(self.combat.attack_damage(aid) or 0)
            if dmg <= 0:
                continue
            base = mine.readiness_p(view, aid)
            if base >= 1.0:
                continue                              # already ready — no double credit
            for etype, count in (mine.deck_energy_counts or {}).items():
                # `expected`, not the raw CountTriple — that raises into a "bad input -> 0.0" guard (Issue #167).
                copies = int(getattr(count, "expected", count) or 0)
                # DELIBERATE CombatMath bypass (POC-T1's list; `test_combat_bypass_census`): the target
                # is a HYPOTHETICAL body the board does not carry, so no `MySide` route can build it.
                enabler = self.combat.attach_budget(
                    raw, mine.hand_ids, energy_attached=mine.energy_attached,
                    supporter_played=mine.supporter_played,
                    deck_energy_types=mine.deck_energy_types,
                    hand_energy_types=frozenset(mine.hand_energy_types) | {etype},
                    discard_energy_counts=mine.discard_energy_counts,
                    target_benched=False,             # it is being promoted INTO the Active Spot
                    more_prizes_than_opp=mine.more_prizes_than_opp)
                p = mine.readiness_p(view, aid, enabler_budget=enabler, copies=copies,
                                     pool=pool, draws=draws)
                best = max(best, dmg * max(0.0, p - base))
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

    def _retreat_discard_choice(self, ma: dict, n: int) -> dict:
        """``ma`` after a retreat discards ``n`` Energy — the GREEDY cheapest-to-lose typed choice
        (ADR-0100 §8). A Retreat Cost slot is COLOURLESS, so which Energy goes is genuinely ours."""
        energies = list(ma.get("energies") or [])
        for _ in range(min(max(0, int(n)), len(energies))):
            keep = max(range(len(energies)),
                       key=lambda i: self._build_standing(
                           dict(ma, energies=energies[:i] + energies[i + 1:])))
            energies.pop(keep)
        return dict(ma, energies=energies)

    def _retreat_cost_legs(self, obs: dict, card_worth: float = 0.0, *, active=None) -> dict:
        """What LEAVING the Active Spot costs (ADR-0100 §8, ADR-0069 §5c). Computed ONCE per menu —
        §9's claim is that it is CONSTANT across destinations. ``card_worth`` prices a switch ITEM (§11)."""
        ma = self._my_active(obs) if active is None else active
        if not ma:
            return {}
        if card_worth > 0.0:                          # a Switch Item pays a card, never a build
            return {"card_worth": float(card_worth)}
        after = self._retreat_discard_choice(ma, self._effective_retreat_cost(obs, ma))
        discarded = list(ma.get("energies") or [])
        for eid in (after.get("energies") or []):     # the multiset difference — what actually goes
            if eid in discarded:
                discarded.remove(eid)
        # ADR-0069 §5c: charged on worth ABOVE a reusable Basic, so a plain Basic pays nothing.
        # Sub-band — it orders equals.
        premium = _ATTACH_RESOURCE_TIEBREAK * sum(
            max(0.0, self._role_value(eid) - ENERGY_TIER) for eid in discarded)
        return {"build_before": self._build_standing(ma),
                "build_after": self._build_standing(after), "resource_premium": premium}

    def _retreat_side(self, obs: dict, board: Board, *, promoted_raw, cost: dict,
                      active=None) -> RetreatSide:
        """The A-side of a voluntary swap, for ONE destination (ADR-0100 §4, §8). Only PRESERVATION is
        per-destination: the Bench A lands on depends on which body left it."""
        ma = self._my_active(obs) if active is None else active
        bench_after = [b for b in self._my_bench_raws(obs) if b is not promoted_raw] + [ma]
        return RetreatSide(body=self._promote_body(obs, board, ma, draws=0,
                                                   bench_after=bench_after), **cost)

    def _retreat_option_value(self, obs: dict, board: Board, active: dict | None) -> float:
        """ADR-0100 §9's whether-site asked as a COUNTERFACTUAL: what retreating off ``active`` is
        worth. 0.0 when unaffordable there — an option that does not exist buys nothing."""
        if not (getattr(self, "promote_retreat_value", False) and active):
            return 0.0
        # NOT `_can_retreat`, which consults no board-level grant — the divergence `common.retreat_cost`
        # records against Issue #149. This side must agree with the cost it then charges.
        if self._effective_retreat_cost(obs, active) > len(active.get("energies") or []):
            return 0.0
        cost = self._retreat_cost_legs(obs, active=active)
        draws = self._turn_dig_depth(obs)
        best = 0.0
        for raw in self._my_bench_raws(obs):
            if not raw or raw.get("id") is None:
                continue
            val = promote_value(PromoteRetreatInputs(
                body=self._promote_body(obs, board, raw, draws=draws),
                retreat=self._retreat_side(obs, board, promoted_raw=raw, cost=cost, active=active)))
            best = max(best, val.total)
        return best                                   # floored at 0: a retreat you would not take

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
            return self._promote_row(promote_value(PromoteRetreatInputs(body=body)), site="pick")
        if sctx != _MAIN:
            return None
        is_switch_item = (otype == _PLAY and "switch" in (ctx.tags or []))
        if otype != _RETREAT and not is_switch_item:
            return None
        # §11's rider: a switch-class ITEM takes the SAME equation as a manual retreat, at card Worth.
        worth = self._role_value(ctx.card_id) if is_switch_item else 0.0
        if self._my_active(obs) is None:
            return None                               # no readable Active — make no claim
        cost = self._retreat_cost_legs(obs, worth)    # CONSTANT across destinations (§9)
        draws = self._turn_dig_depth(obs)
        best = None
        for raw in self._my_bench_raws(obs):
            if not raw or raw.get("id") is None:
                continue
            val = promote_value(PromoteRetreatInputs(
                body=self._promote_body(obs, board, raw, draws=draws),
                retreat=self._retreat_side(obs, board, promoted_raw=raw, cost=cost)))
            if best is None or val.total > best.total:
                best = val
        return None if best is None else self._promote_row(best, site="whether")

    @staticmethod
    def _promote_row(val, *, site: str) -> dict:
        """The decider's per-option working (ADR-0008/0019), rounded for the wire. No agreement bit:
        this DECIDES, so there is one emission path."""
        return {"site": site, "tactical": val.total,
                "my_yield": round(val.my_yield, 2), "closure": round(val.closure, 2),
                "exposure": round(val.exposure, 2), "tempo_denied": round(val.tempo_denied, 2),
                "fatal": round(val.fatal, 2), "preservation": round(val.preservation, 2),
                "retreat_cost": round(val.retreat_cost, 2), "mobility_cost": round(val.mobility_cost, 2),
                "total": round(val.total, 2)}

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
        if cost == 0:
            return True                                   # free retreat
        return len(ma.get("energies") or []) >= cost

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
