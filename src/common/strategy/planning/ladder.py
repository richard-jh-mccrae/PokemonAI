"""The Goal LADDER: what to plan when no win is provable — KO for prizes, KO the key threat, stabilize, heal, lock, or
deliberately forgo a KO.

Ranked against each other by the same leaf, so the ladder is an ordering over goals rather than a chain of special
cases."""
from __future__ import annotations


from common.strategy.context import _ACTIVE, _BENCH, _EVOLVE, _PLAY, _RETREAT
from common.strategy.planning.turn_line import TurnLine, _GOAL_LINE


_PLANNER_PATH_W = 25.0         # Tier-3 (ADR-0040): the KO'd key threat sits on MY cheapest Prize
                               # Path — sub-prize, ranks lines within the rung, never beats a prize

_PLANNER_ENABLER_FREE = 8.0    # cheapest-enabler tier (ADR-0031): a FREE direct-evolve (evolved form
                               # already in hand, pre-evo legally evolvable this turn) is the cheapest
                               # first step to the SAME KO — no card leaves the deck, no tutor spent.

_PLANNER_GAMEPLAN_W = 20.0     # ADR-0045 (S3): a candidate line SERVING the Match Planner's directed goal
                               # gets this × the Game Plan's confidence — sub-prize (< one KO_SCORE), ranks
                               # WITHIN a rung, never beats a prize; kill-switch `match_planner_steer`

_PLANNER_DECKOUT_W = 5.0       # a sub-prize nudge toward pressing a KO/grind line when the opponent is
                               # near deck-out; never a reorder

_PLANNER_DECKOUT_TURNS = 3     # "near deck-out" horizon: fire only when they exhaust within this many turns


class GoalLadderMixin:
    """The below-win goals, and the lines that serve each."""

    def _gameplan_goal_bonus(self, line_goal: str, board) -> float:
        """The Match Planner seam (ADR-0045 S3): a confidence-scaled sub-prize bump when a candidate
        line's goal serves the Game Plan's directed goal. Silent unless ``match_planner_steer`` is on."""
        if not getattr(self, "match_planner_steer", False):
            return 0.0
        gp = getattr(board, "game_plan", None)
        if gp is None or not gp.directed_goal:
            return 0.0
        return (_PLANNER_GAMEPLAN_W * gp.confidence
                if line_goal in _GOAL_LINE.get(gp.directed_goal, ()) else 0.0)

    def _deckout_grind_bonus(self, board) -> float:
        """A sub-prize nudge toward pressing a KO/grind line when the opponent is near deck-out
        (``opp_resource_reads``, ships ON). Ranks WITHIN a rung, never reorders (ADR-0031)."""
        if not getattr(self, "opp_resource_reads", False):
            return 0.0
        t = getattr(board, "opp_deckout_in_turns", None)
        if t is None or t > _PLANNER_DECKOUT_TURNS:
            return 0.0
        return _PLANNER_DECKOUT_W

    def _condition_holds(self, condition, board) -> bool:
        """A clause's dynamic ``condition`` gate against the Board — TRUE only when absent or PROVABLY
        satisfied now; anything else fails closed. Active-spot :meth:`_condition_holds_for`."""
        return self._condition_holds_for(condition, cur_hp=board.my_active_hp,
                                         attached=board.my_active_energy,
                                         my_pokemon_koed_last_turn=board.my_pokemon_koed_last_turn)

    def _condition_holds_for(self, condition, *, cur_hp: int, attached: int,
                             my_pokemon_koed_last_turn: bool = False) -> bool:
        """:meth:`_condition_holds` asked of ONE body (Issue #409). Both gates are per-TARGET at the
        card text, so reading them off the Active would answer about the wrong Pokémon."""
        if not condition:
            return True
        if condition == "remaining_hp_30_or_less":
            return bool(cur_hp) and cur_hp <= 30
        if condition == "energy_3_plus":
            return attached >= 3
        if condition == "pokemon_ko_last_turn":
            return my_pokemon_koed_last_turn
        return False

    def _heal_candidate(self, cid: int, board, active_stat) -> tuple[int, int] | None:
        """What playing heal-card ``cid`` on my Active would leave: ``(healed_hp, energy_total)``, or
        None. Issue #349's ``each_of`` / ``amount_per`` are deliberately NOT read — a ruling, not a gap."""
        attach = 0 if board.energy_attached else self._best_hand_attach_units(board.hand_ids, active_stat)
        return self._heal_body_candidate(cid, active_stat, is_active=True,
                                         cur_hp=board.my_active_hp,
                                         attached=board.my_active_energy, attach_units=attach)

    def _heal_body_candidate(self, cid: int, stat, *, is_active: bool, cur_hp: int, attached: int,
                             attach_units: int, max_hp: int | None = None) -> tuple[int, int] | None:
        """:meth:`_heal_candidate` asked of ANY of my bodies, Active or benched (Issue #409).
        ``max_hp`` is the restore CEILING, a parameter because a +HP Tool moves it off the printed HP."""
        max_hp = int(max_hp) if max_hp else (getattr(stat, "hp", 0) or 0)
        for clause in (self.effects.clauses(cid) if self.effects else ()):
            if clause.get("kind") != "heal":
                continue
            if not self._condition_holds_for(clause.get("condition"), cur_hp=cur_hp,
                                             attached=attached):
                continue                              # gate fails / not board-checkable: fail-closed
            if not self._heal_restriction_targets(clause.get("restriction"), stat,
                                                  is_active=is_active):
                continue
            amount = clause.get("amount")
            healed = max_hp if amount == "all" else min(max_hp, cur_hp + int(amount or 0))
            rider = clause.get("rider")
            if rider == "bounce_energy_to_hand":
                energy_total = attach_units           # all Energy bounced; only re-attach pays
            elif rider == "discard_own_energy":
                energy_total = max(0, attached - 1) + attach_units
            else:
                energy_total = attached + attach_units
            return (healed, energy_total)
        # The legacy Function-Tag fallback stays ACTIVE-ONLY, deliberately: the tag carries no
        # restriction, so on a benched candidate it would be a guess. Fail closed instead.
        if is_active and self.functions and "clutch_heal" in self.functions.tags(cid):
            return (max_hp, attach_units)             # legacy tag path: full heal + Energy bounce
        return None

    def _best_hand_attach_units(self, hand_ids, active_stat) -> int:
        """Energy units the best single attach from ``hand_ids`` gives my Active — 3 for a
        `discard_eot` burst onto an Evolution, 1 for any other Energy card, 0 when the hand has none."""
        best = 0
        for cid in hand_ids:
            st = self.stats.get(cid) if self.stats else None
            if st is None or getattr(st, "hp", 0):
                continue
            tags = self.functions.tags(cid) if self.functions else []
            # a typed Energy, a Basic/Special by cardType, or a colourless discard-burst (energyType 0)
            if not (getattr(st, "energyType", 0) not in (None, 0)
                    or st.is_energy
                    or "discard_eot" in tags):
                continue
            best = max(best, len(self.combat.provision_codes_or_floor(cid, active_stat)))
        return best

    def _plan_fingerprint(self, obs, select) -> tuple:
        """A hashable snapshot of everything a plan depends on — turn, both boards, my hand, my prize
        count, the manual-attach flag, the option signature. Any reveal changes it, so the cache re-plans."""
        cur = obs.get("current") or {}
        me, opp = self._my_player(obs), self._opp_player(obs)

        def body(p):
            return (p.get("id"), len(p.get("energies") or []), p.get("hp")) if p else None

        def side(pl):
            return (tuple(body(x) for x in (pl.get("active") or [])),
                    tuple(body(x) for x in (pl.get("bench") or [])))

        hand = tuple(sorted(c.get("id") for c in (me.get("hand") or []) if c and c.get("id") is not None))
        opts = tuple((o.get("type"), o.get("attackId"), o.get("area"), o.get("index"),
                      o.get("inPlayArea"), o.get("inPlayIndex")) for o in (select.get("option") or []))
        return (cur.get("turn"), side(me), side(opp), hand, len(me.get("prize") or []),
                bool(cur.get("energyAttached")), opts)

    def _ko_for_prizes_lines(self, obs, select, board, options, traces) -> list:
        """The **KO-for-prizes** goal (ADR-0031): multi-step enabling lines that unlock an otherwise-
        missed KO of the opponent's Active, one candidate per enabling first-step. Empty when none."""
        opp = self._opp_active(obs)
        if not (opp or {}).get("hp"):
            return []
        opp_player = self._opp_player(obs)
        # Each builder calls `_ko_line_pricing` itself: the Attach Budget is per TARGET BODY and
        # cannot be computed once for the menu (ADR-0075).
        threat = self._threat_magnitude(opp)
        lines = []
        for i, o in enumerate(options):
            cost = 0.0                                    # cheapest-enabler tier (ADR-0031): an enabler
                                                          # PRESERVING resources outranks a tutor reaching
                                                          # the SAME KO; 0 = the scarce Supporter tutor
            if o.get("type") == _RETREAT:
                cand = self._retreat_ko_candidate(obs, board, opp, opp_player)
                kind, cost = "retreat", _PLANNER_ENABLER_FREE   # spends no card/slot — a free enabler
            elif o.get("type") == _EVOLVE and o.get("inPlayArea") == _ACTIVE:
                cand = self._evolve_ko_candidate(obs, select, board, o, opp, opp_player)
                kind, cost = "free evolve", _PLANNER_ENABLER_FREE
            elif o.get("type") == _EVOLVE and o.get("inPlayArea") == _BENCH:
                retreat_on_menu = any(x.get("type") == _RETREAT for x in options)
                cand = self._free_evolve_ko_candidate(obs, select, board, o, opp, opp_player,
                                                      retreat_on_menu)
                kind, cost = "free evolve", _PLANNER_ENABLER_FREE
            elif o.get("type") == _PLAY and self._is_evolution_tutor(obs, select, o):
                retreat_on_menu = any(x.get("type") == _RETREAT for x in options)
                cand = self._tutor_evolve_ko_candidate(obs, board, opp, opp_player, retreat_on_menu)
                kind = "evolution tutor"                  # a Supporter — least-preferred enabler (cost 0)
            elif (o.get("type") == _PLAY and getattr(self, "enabler_item_composer", False)
                  and self._is_item_pokemon_tutor(obs, select, o)):
                retreat_on_menu = any(x.get("type") == _RETREAT for x in options)
                cand = self._item_evolve_ko_candidate(obs, select, board, o, opp, opp_player,
                                                      retreat_on_menu)
                kind, cost = "item tutor", self._item_enabler_cost(board)   # the Item's edge over the
                #                       scarce Supporter tutor is CONDITIONAL on preserving the slot
            elif (o.get("type") == _PLAY and getattr(self, "enabler_item_composer", False)
                  and self._is_rare_candy(obs, select, o)):
                retreat_on_menu = any(x.get("type") == _RETREAT for x in options)
                cand = self._rare_candy_ko_candidate(obs, select, board, o, opp, opp_player,
                                                     retreat_on_menu)
                kind, cost = "rare candy", self._item_enabler_cost(board)   # a Basic->Stage2 skip Item,
                #                       tiered like the item tutor (slot-preservation credit)
            elif o.get("type") == _PLAY:
                cand = self._supporter_ko_candidate(obs, select, board, o, opp, opp_player)
                kind = "energy tutor"
            else:
                continue
            if cand is None:
                continue
            prizes, survives, *rest = cand
            # ADR-0074 decision 4: the prize term is weighted by P(the line's Energy is really
            # there); a candidate carrying no probability passes 1.0.
            line_p = max(0.0, min(1.0, float(rest[0]))) if rest else 1.0
            value = self._leaf_value(prizes=prizes * line_p, active_survives=survives,
                                     threat_removed=threat)
            value += self._gameplan_goal_bonus("ko_for_prizes", board)       # ADR-0045 seam (S3)
            value += self._deckout_grind_bonus(board)                        # BUILD 2 seam (opp_resource_reads)
            value += cost                                 # sub-prize/sub-survival: breaks a same-KO tie
                                                          # among enablers, never over a real prize delta
            odds = "" if line_p >= 1.0 else f" at p={line_p:.2f}"
            lines.append(TurnLine(next_step=[i], goal="ko_for_prizes", value=value,
                                  rationale=(f"plan (ko_for_prizes): {kind} unlocks a "
                                             f"{int(prizes)}-prize KO{odds}")))
        return lines

    def _ko_key_threat_lines(self, obs, select, board, options) -> list:
        """The **KO-the-key-threat** goal (`planner_key_threat`): enabling lines that unlock a
        bench-snipe KO of the benched TOP threat. Snipes ignore W/R, so ``rider >= hp`` is exact."""
        opp_player = self._opp_player(obs)
        bench = [p for p in (opp_player.get("bench") or []) if p]
        if not bench:
            return []
        ranked = [(self._body_threat_rank(obs, p, board.read, board.posture_confidence), p)
                  for p in bench]
        if getattr(self, "ko_target_whiff", False):
            # DEFAULT OFF: among EQUAL-rank targets prefer the one they are LEAST able to replace.
            # A pure tiebreak — threat rank stays the dominant key; fails OPEN, so no reorder.
            top_rank, top = max(ranked, key=lambda t: (t[0], -self._whiff_odds(board, t[1])))
        else:
            top_rank, top = max(ranked, key=lambda t: t[0])
        top_stat = self.stats.get(top.get("id")) if self.stats else None
        own_mag = float(getattr(top_stat, "maxDamage", 0) or 0) if top_stat else 0.0
        fwd_fn = getattr(self.stats, "forward_max_damage", None)
        fwd_mag = float(fwd_fn(top.get("id")) or 0) if fwd_fn is not None else 0.0
        threat_mag = max(own_mag, fwd_mag)             # the SAME damage basis the rank uses, so a
                                                       # 0-printed body with a big forward line counts
        hp = top.get("hp", 0)
        if top_rank <= 0 or threat_mag <= 0 or not hp or self._is_tera(top.get("id")):
            return []                                 # nothing benched actually threatens (or Tera-immune)
        me = self._my_player(obs)
        opp = self._opp_active(obs)
        others = [p for p in ([opp] + [p for p in bench if p is not top]) if p]
        extra = 1 if (board.reusable_energy_in_hand and not board.energy_attached) else 0
        prizes = self._prize_value(top)
        lines = []
        for i, o in enumerate(options):
            if o.get("type") == _RETREAT:
                cand = self._retreat_snipe_candidate(me, others, hp, extra)
                kind = "retreat"
            elif o.get("type") == _EVOLVE and o.get("inPlayArea") == _ACTIVE:
                evolved_id = self._option_card_id(obs, select, o)
                if not self._affords_snipe_ko(evolved_id, board.my_active_energy + extra, hp):
                    continue
                estat = self.stats.get(evolved_id) if self.stats else None
                my_hp = getattr(estat, "hp", 0) or 0
                cand = (bool(my_hp) and self._incoming_worst(evolved_id, my_hp, others) < my_hp)
                kind = "evolve"
            elif o.get("type") == _PLAY:
                if (board.energy_attached or board.reusable_energy_in_hand
                        or not self._is_energy_tutor(obs, select, o)):
                    continue                          # mirrors `_supporter_ko_candidate`'s gate
                cand = self._retreat_snipe_candidate(me, others, hp, extra=1)
                kind = "energy tutor"
            else:
                continue
            if cand is None:
                continue
            value = self._leaf_value(prizes=prizes, active_survives=bool(cand),
                                     threat_removed=threat_mag)
            if (getattr(self, "objectives_path", False)          # Tier-3 (ADR-0040): a key threat ON my
                    and top.get("id") in board.path_target_ids):  # cheapest Prize Path advances the MATCH
                value += _PLANNER_PATH_W                          # win — sub-prize bump, ranks within rung
            value += self._gameplan_goal_bonus("ko_key_threat", board)       # ADR-0045 seam (S3)
            value += self._deckout_grind_bonus(board)                        # BUILD 2 seam (opp_resource_reads)
            lines.append(TurnLine(
                next_step=[i], goal="ko_key_threat", value=value,
                rationale=f"plan (ko_key_threat): {kind} unlocks the snipe-KO of the benched key threat"))
        return lines
