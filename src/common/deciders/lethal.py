"""The this-turn win search: the ENABLERS that turn a non-lethal board lethal — grab the missing card, attach the
missing Energy, retreat into the attacker that can, boost the damage over the line.

Every leg is sound-only: it fires when the win is provable, never on a rollout estimate (ADR-0030)."""
from __future__ import annotations


from common.deciders.facts import Board
from common.strategy.combat import _EFFICIENCY
from common.strategy.context import KO_SCORE, _ACTIVE, _ATTACH, _CARD, _PLAY, _RETREAT, _TO_HAND


_RETREAT_POSITION_EPS = 0.001  # tie-break only: when retreating into a ready wincon takes the SAME KO the
                           # spent Active could, prefer it. Tiny — never beats a real edge.


class LethalMixin:
    """Enabler plays that make this turn's KO — or the game — reachable."""

    def _grab_lethal_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """KO_SCORE-class value for a `_TO_HAND` grab supplying THIS turn's KO-enabling attach (ADR-0030). The
        retreat branch needs all three: the retreat LEGAL, the grab NECESSARY, and the grab the MARGINAL Energy."""
        if (select.get("context") != _TO_HAND or option.get("type") != _CARD
                or board.turn <= 1 or board.energy_attached or board.my_prizes_remaining <= 0):
            return 0.0
        opp = self._opp_active(obs)
        if opp is None or not (opp or {}).get("hp"):
            return 0.0
        cid = self._option_card_id(obs, select, option)
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        tags = self.functions.tags(cid) if (self.functions and cid is not None) else []
        direct = bool(stat and getattr(stat, "hp", 0) == 0
                      and getattr(stat, "energyType", 0) and "discard_eot" not in tags)
        tutor = ("tutor_energy" in tags
                 and (self._tutor_energy_certain(board) or self._search_pool_has_reusable_energy(board)))
        if not (direct or tutor):
            return 0.0
        etype = getattr(stat, "energyType", None) if direct else None      # a tutor's type is WILD
        me = self._my_player(obs)
        ma = next((p for p in (me.get("active") or []) if p), None)

        def kos(attacker_id, energy, body, units=1):
            return self._best_affordable_ko_value(obs, board, opp, attacker_id, energy, bound="min",
                                                  body=body, extra_type=etype, extra_units=units) > 0

        ko = kos(board.my_active_id, board.my_active_energy + 1, ma)
        if not ko and self._can_retreat(ma):              # retreat into a benched attacker, then attach
            ko = any(kos(p.get("id"), len(p.get("energies") or []) + 1, p)
                     # NECESSARY: the body doesn't already take the KO on the Energy it carries
                     and not kos(p.get("id"), len(p.get("energies") or []), p, units=0)
                     for p in (me.get("bench") or []) if p)
        if ko and board.reusable_energy_in_hand and direct:
            ko = False                                    # MARGINAL: a reusable Energy is already in hand,
                                                          # so this grab is not the source of the attach
        return (KO_SCORE + self._prize_value(opp)) if ko else 0.0

    def _grab_enabler_lethal_tactical(self, obs: dict, select: dict, board: Board,
                                      option: dict) -> float:
        """KO_SCORE-class value for grabbing the BODY that turns my Active's `requiresBench` attack on and WINS.
        `damageMin` is 0 here, so the floor is vacuous: demand a DETERMINISTIC attack and read the exact damage."""
        if (select.get("context") != _TO_HAND or option.get("type") != _CARD
                or board.turn <= 1 or board.bench_full or board.my_prizes_remaining <= 0):
            return 0.0
        opp = self._opp_active(obs)
        if not (opp or {}).get("hp") or not self.stats:
            return 0.0        # attack records resolve per-aid below, so no table-level gate (ADR-0056)
        cid = self._option_card_id(obs, select, option)
        stat = self.stats.get(cid) if cid is not None else None
        if not stat or not stat.is_pokemon or stat.evolvesFrom:   # a benchable Basic Pokémon only
            return 0.0
        active = self.stats.get(board.my_active_id) if board.my_active_id is not None else None
        if not active:
            return 0.0
        ctx = self._my_damage_context(obs)
        have = set(ctx.get("atk_bench_names") or ())
        would_have = have | {stat.name}
        for aid in (getattr(active, "attacks", None) or ()):
            ast = self._attack_stat(aid)
            need = getattr(ast, "requiresBench", None)
            if not need or set(need) <= have:                 # unconditional, or already satisfied
                continue
            if not set(need) <= would_have:                   # this body isn't the missing piece
                continue
            if self._attack_cost(aid) > board.my_active_energy:
                continue                                      # affordable on ATTACHED Energy alone
            if not ast.is_deterministic:
                continue                                      # some OTHER clause is conditional — no lock
            dmg = self.predicted_damage(board.my_active_id, aid, opp, bound="exact",
                                        context={**ctx, "atk_bench_names": tuple(would_have)})
            if not (dmg and dmg >= (opp.get("hp") or 0)):
                continue
            wins = (self._prize_value(opp) >= board.my_prizes_remaining or not board.opp_bench)
            if wins and not self._is_simultaneous_draw(board, aid, self._prize_value(opp)):
                return KO_SCORE + self._prize_value(opp)
        return 0.0

    def _grab_retreat_tool_lethal_tactical(self, obs: dict, select: dict, board: Board,
                                           option: dict) -> float:
        """KO_SCORE-class value for grabbing a retreat-reduction Tool (Air Balloon) that FREES a retreat into
        an already-winning benched attacker. Gated on `retreat_enabler_lethal`; SOUND (min-bound + win)."""
        if (not getattr(self, "retreat_enabler_lethal", False) or select.get("context") != _TO_HAND
                or option.get("type") != _CARD or board.turn <= 1 or board.my_prizes_remaining <= 0):
            return 0.0
        opp = self._opp_active(obs)
        if not (opp or {}).get("hp"):
            return 0.0
        me = self._my_player(obs)
        ma = next((p for p in (me.get("active") or []) if p), None)
        if ma is None or self._can_retreat(ma):            # only when a Tool is NEEDED to retreat
            return 0.0
        need = self._retreat_shortfall(ma)
        cid = self._option_card_id(obs, select, option)
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if not (need > 0 and stat is not None and getattr(stat, "retreatReduction", 0) >= need):
            return 0.0
        if not self._bench_body_wins_if_promoted(obs, board, opp, me, ma):
            return 0.0
        return KO_SCORE + self._prize_value(opp)

    def _attach_retreat_tool_lethal_tactical(self, obs: dict, select: dict, board: Board,
                                             option: dict) -> float:
        """The second half of the retreat-enabler lethal: attaching that Tool to the ACTIVE, so it lands on the
        body that must RETREAT rather than on the wincon the tool doctrine would prefer. Same gate/soundness."""
        if (not getattr(self, "retreat_enabler_lethal", False) or board.turn <= 1
                or option.get("type") != _ATTACH or option.get("inPlayArea") != _ACTIVE
                or board.my_prizes_remaining <= 0):
            return 0.0
        opp = self._opp_active(obs)
        if not (opp or {}).get("hp"):
            return 0.0
        me = self._my_player(obs)
        ma = next((p for p in (me.get("active") or []) if p), None)
        if ma is None or self._can_retreat(ma):            # a Tool is still NEEDED to retreat
            return 0.0
        need = self._retreat_shortfall(ma)
        cid = self._option_card_id(obs, select, option)
        stat = self.stats.get(cid) if (self.stats and cid is not None) else None
        if not (need > 0 and stat is not None and getattr(stat, "retreatReduction", 0) >= need):
            return 0.0
        if not self._bench_body_wins_if_promoted(obs, board, opp, me, ma):
            return 0.0
        return KO_SCORE + self._prize_value(opp)

    def _search_pool_has_reusable_energy(self, board) -> bool:
        """Does THIS search's revealed pool (`search_deck_ids`) hold a reusable Basic Energy (hp 0, a real
        `energyType`, not `discard_eot`)? The single-frame complement to `_tutor_energy_certain`."""
        sd = board.search_deck_ids
        if not sd or not self.stats:
            return False
        for eid in sd:
            est = self.stats.get(eid)
            etags = self.functions.tags(eid) if self.functions else []
            if (est and getattr(est, "hp", 0) == 0 and getattr(est, "energyType", 0)
                    and "discard_eot" not in etags):
                return True
        return False

    def _attach_lethal_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """KO_SCORE-class value for an ATTACH that UNLOCKS a knockout this turn, modelling the post-attach
        Energy through `provision_codes`. Fires only when the attach is NECESSARY (the Active can't already KO)."""
        if option.get("type") != _ATTACH or option.get("inPlayArea") != _ACTIVE:
            return 0
        if board.turn <= 1:        # turn 1 going first: can't attack this turn (rules.md §first-turn),
            return 0               # so no attach is lethal — burst would just be discarded
        opp = self._opp_active(obs)
        opp_hp = (opp or {}).get("hp", 0)
        active_stat = self.stats.get(board.my_active_id) if (self.stats and board.my_active_id) else None
        if not (active_stat and opp and opp_hp):
            return 0
        eid = self._option_card_id(obs, select, option)
        # Count AND colour together, keyed on the ACTIVE as the holder (Issue #418). A colourless code pays a
        # {C} slot and NEVER a specific one; `()` means the card provides nothing (a Tool riding ATTACH).
        codes = self.combat.provision_codes_or_floor(eid, active_stat)
        provided_units = len(codes)
        etype = codes[0] if codes else None
        me = self._my_player(obs)
        ma = next((p for p in (me.get("active") or []) if p), None)
        bench_names = tuple(                                     # the requiresBench partner set: attaching to
            (self.stats.get(b.get("id")).name if self.stats and self.stats.get(b.get("id")) else "")
            for b in (me.get("bench") or []) if b)               # the ACTIVE leaves the Bench unchanged, so
        # the current bench IS what the unlocked attack fires under. Without it an attack that "does nothing"
        # w/o its partner phantom-KOs here.

        def best_affordable(energy: int, extra_units: int = 0) -> float:
            # Per-attack oracle (ADR-0032): adjust-then-max, type-guarded, and `atk_bench_names` at an exact
            # bound — so an ignore-flag attack is seen and a prevented defender correctly yields 0.
            return self._best_affordable_damage(
                board.my_active_id, energy, opp, body=ma, extra_type=etype,
                extra_units=extra_units, context={"atk_bench_names": bench_names})

        cur = board.my_active_energy
        if best_affordable(cur) >= opp_hp:                  # already lethal — no attach needed
            return 0
        if best_affordable(cur + provided_units, extra_units=provided_units) >= opp_hp:
            return KO_SCORE + self._prize_value(opp)
        return 0

    def _retreat_to_lethal_tactical(self, obs: dict, board: Board, option: dict) -> float:
        """KO_SCORE-class value for a RETREAT bringing a READY benched wincon up to take the KO. Fires ONLY when
        that KO is STRICTLY BETTER than the one my current Active can already take, so no prize is forfeited."""
        if option.get("type") != _RETREAT:
            return 0
        opp = self._opp_active(obs)
        if not (opp and opp.get("hp")):
            return 0
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        ma = next((p for p in (me.get("active") or []) if p), None)
        my_active_ko = self._best_affordable_ko_value(
            obs, board, opp, board.my_active_id, board.my_active_energy, body=ma)
        best = 0.0
        for p in (me.get("bench") or []):
            if not p:
                continue
            energy = len((p.get("energies") or []))
            best = max(best, self._best_affordable_ko_value(obs, board, opp, p.get("id"), energy, body=p))
        if best <= my_active_ko:                         # the Active already takes this KO (or better):
            return 0                                     # just attack — don't waste the retreat
        return best + _RETREAT_POSITION_EPS

    def _best_affordable_ko_value(self, obs: dict, board: Board, opp: dict, attacker_id: int | None,
                                  energy: int, *, bound: str = "exact", body: dict | None = None,
                                  extra_type=None, extra_units: int = 0,
                                  boost_amount: int = 0, boost_type=None,
                                  promote_bench_names=None, attack_p=None, budget=None) -> float:
        """Forward to the KO oracle's ``best_affordable_ko_value`` (ADR-0052) with the Board's ``opp_bench``.
        ``budget`` supersedes ``energy`` when given; ``attack_p`` weights a ranked consumer's claim."""
        return self.combat.best_affordable_ko_value(
            opp, attacker_id, energy, opp_bench=board.opp_bench, bound=bound, body=body,
            extra_type=extra_type, extra_units=extra_units,
            boost_amount=boost_amount, boost_type=boost_type,
            promote_bench_names=promote_bench_names, attack_p=attack_p, budget=budget)

    def _best_affordable_damage(self, attacker_id, energy: int, defender: dict | None, *,
                                body: dict | None = None, extra_type=None, extra_units: int = 0,
                                bound: str = "exact", context: dict | None = None) -> float:
        """A PURE forward to the KO oracle's ``best_affordable_damage`` — the house shape for reaching
        `CombatMath`, matching `_attack_cost` / `predicted_damage` / `_attack_type_payable`."""
        return self.combat.best_affordable_damage(
            attacker_id, energy, defender, body=body, extra_type=extra_type,
            extra_units=extra_units, bound=bound, context=context)

    def _boost_lethal_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """KO_SCORE-class value for a play that UNLOCKS a knockout — ONE term with two legs, since only the
        crossing's side differs: ``dmg + boost*copies >= hp`` vs ``dmg >= hp + hp_shift``, which is SIGNED."""
        t = option.get("type")
        if board.turn <= 1:            # turn 1 going first: can't attack, no boost is lethal
            return 0
        cid = self._option_card_id(obs, select, option)
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        if st is None:
            return 0
        opp = self._opp_active(obs)
        opp_hp = (opp or {}).get("hp", 0)
        active = self.stats.get(board.my_active_id) if (self.stats and board.my_active_id) else None
        if not (active and opp and opp_hp):
            return 0
        opp_stat = self.stats.get(opp.get("id")) if self.stats else None
        boost, hp_shift = 0, 0
        if getattr(st, "damageBoost", 0):
            # ── the DAMAGE side: lift my attack over their HP ────────────────────────────────────
            if t == _PLAY and (st.is_item or st.is_supporter):  # Item stacks; a Supporter is one/turn
                copies = 1 if st.is_supporter else self._hand_count_of(obs, cid)
            elif (t == _ATTACH and st.is_tool
                  and option.get("inPlayArea") == _ACTIVE):     # a boost Tool onto my attacker
                copies = 1
            else:
                return 0
            if st.damageBoostType is not None and active.energyType != st.damageBoostType:
                return 0                                        # "your {F} Pokémon" — attacker-type gate
            if not st.applies_to_holder(active):
                return 0                                        # the owner-family HOLDER gate
            if st.damageBoostVsEx and not (opp_stat and opp_stat.is_ex_body):
                return 0                                        # "{ex}" defender gate (incl. Mega ex)
            boost = st.damageBoost * copies
        elif t == _PLAY and st.is_stadium:
            # ── the HP side: lower their HP under my attack (Issue #424) ─────────────────────────
            shift = self._stadium_hp_shift(obs, cid, opp_stat)
            if shift is None:
                return 0                                        # a clause the seam cannot price
            hp_shift = shift
        else:
            return 0
        need = opp_hp + hp_shift                                # the defender's HP AFTER this play
        if need <= 0:                                           # a body the play alone would floor:
            return 0                                            # not a crossing this term can state
        ctx = self._my_damage_context(obs)
        for aid in (active.attacks or ()):
            cost = self._attack_cost(aid)
            if cost > board.my_active_energy:
                continue
            dmg = self.predicted_damage(board.my_active_id, aid, opp, context=ctx)
            if dmg >= opp_hp:
                return 0                                    # an affordable KO already exists — just attack
        best = 0.0
        for aid in (active.attacks or ()):
            cost = self._attack_cost(aid)
            if cost > board.my_active_energy:
                continue
            dmg = self.predicted_damage(board.my_active_id, aid, opp, context=ctx)
            if dmg <= 0:                                    # a boost never lifts a does-nothing attack
                continue
            if (dmg + boost >= need
                    and not self._is_simultaneous_draw(board, aid, self._prize_value(opp))):
                best = max(best, KO_SCORE + self._prize_value(opp) - _EFFICIENCY * cost)
        return best
