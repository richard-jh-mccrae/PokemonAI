"""Assembles the per-turn `Board` — the one place a turn-level fact is derived.

A decider reads `board.x`; it never re-derives x. An unconsumed Board field is an unbuilt feature. The
two known-top STATIC helpers stay in `pilot.py`, which they name by class."""
from __future__ import annotations


from collections import Counter

from common.deciders.facts import Board
from common.deciders.plan_choice import _posture_gamma, choose_plan
from common.scouting.briefs import match_brief, resolve_brief_cards
from common.scouting.matchup import matchup_favorability
from common.strategy import Plan
from common.strategy.combat import CURRENT_FORMS_ONLY, UNCHARGED
from common.strategy.context import (_ATTACK, _DECK, _DRAW, _DRAW_REVERSE, _MAIN, _MOVE_CARD, _MOVE_CARD_REVERSE,
                                     _SHUFFLE, _SWITCH, _TO_ACTIVE)



class BoardMixin:
    """Builds the `Board` for this turn."""

    def _board(self, obs: dict, select: dict | None = None, *, carried=None) -> Board:
        """Summarise the shared board once per decision. ``carried`` makes the build PURE (ADR-0068
        decision 2) — a HYPOTHETICAL caller passes it; a live decision passes nothing and writes back."""
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        ma = next((p for p in (me.get("active") or []) if p), None)
        oa = next((p for p in (opp.get("active") or []) if p), None)
        # OPPONENT-as-attacker context, cached per decision (ADR-0032 P1): scalers priced off THEIR
        # visible state — hand/bench/Energy/discard.
        self._opp_attack_context = self._damage_context(obs, attacker_is_me=False)
        prizes = obs.get("own_prizes")             # exact prize multiset from deck-tracker, or None
        if prizes:                                 # keys are card ids: coerce str->int so a JSON-captured
            prizes = {int(k): v for k, v in prizes.items()}   # obs (a Correction) matches the int decklist

        deck_empty = self._deck_empty_ids(me, prizes)
        deck_known = self._deck_known_counts(me, prizes)
        deck_odds_map = self._deck_contains_prob(me, deck_known)   # probabilistic complement (ADR-0029)
        read = self.opponent.observe(obs)            # ADR-0047 fan-out: Identity (Scout) + Resources
        if self.scout is None:                       # preserve Posture-off semantics
            read = None
        gamma = _posture_gamma(read) if self.posture else 0.0    # the kill-switch zeroes γ
        my_arch = self.strategy.params.get("my_archetype")
        fav, cov = (matchup_favorability(self.scout.artifact, my_arch, read.candidates)
                    if (self.posture and self.scout and read and my_arch) else (0.5, 0.0))
        # covers-routed (ADR-0027), γ-gated: on an empty early board the Read's top candidate is just
        # the prior favourite, so γ>0 keeps `board.brief` off until the opponent is recognized.
        brief = match_brief(self.briefs, read) if (self.posture and read and gamma > 0) else None
        self.opponent.note_brief(brief)
        # ADR-0064 Decision 1: charged Incoming ONLY behind a γ-matched Brief; an unrecognized opponent
        # stays None -> worst-case ceiling. Never relax pessimism on a guess.
        self._incoming_budget = {"base_attach": 1, "burst_on_evo": 2} if brief is not None else None
        _opp_res = getattr(self.opponent, "resources", None)
        # Brief threats/targets resolved to card ids (ADR-0027). An old/None provider -> empty.
        _ids_for_name = getattr(self.stats, "ids_for_name", None)
        brief_threat_ids, brief_target_roles = (
            resolve_brief_cards(brief, _ids_for_name)
            if (brief is not None and _ids_for_name is not None) else (frozenset(), {}))
        matchup_plan = self._matchup_plan(opp, brief_target_roles, read, gamma)   # ADR-0051 spine
        # The StateModel for this decision (ADR-0068) — lazy, so it costs only the fields read. Built
        # HERE, not earlier: `TheirSide`'s clocks take the Read's energy policy resolved just above.
        model = self._snapshot(obs, my_index=yi, deck_empty=deck_empty,
                               read=read, brief=brief,
                               matchup_plan=matchup_plan, gamma=gamma, favorability=fav,
                               matchup_coverage=cov, carried=carried)
        active_doomed = self._active_doomed(ma, oa, opp)
        active_lethal = self._active_cheap_attack_kos(ma, oa)   # its turn is done — build the successor
        # Energy my Active can PAY an attack with this turn: attached + the best unspent hand attach.
        payable = ((model.mine.active.energy_count if model.mine.active is not None else 0)
                   + (0 if model.energy_attached
                      else self._best_hand_attach_units(
                          frozenset(model.mine.hand_ids),
                          self.stats.get((ma or {}).get("id")) if self.stats else None)))
        famine = model.mine.active_famine
        # 0 attached, yet an attack is still reachable this turn — two stall-gust rules need it.
        unarmed_but_able = (model.mine.active is not None
                            and model.mine.active.energy_count == 0 and not famine)
        base_plan = (choose_plan(state, self.strategy, self.stats) if state.get("players")
                     else Plan.SETUP)
        path_sig = self._path_signals(obs, me, opp, ma, oa,   # Tier-3 two-sided Prize Path (ADR-0040),
                                      len(me.get("prize") or []),   # ranking data only
                                      len(opp.get("prize") or []),
                                      read, gamma,
                                      carried=carried)              # snapshot ⇒ pure (ADR-0068)
        phase = self._derive_phase(base_plan, path_sig["race_ahead"], active_doomed,
                                   len(me.get("prize") or []),   # ADVISORY phase, hysteretic
                                   favorability=fav, coverage=cov,
                                   carried=carried)
        opp_doomed = oa is None or (oa or {}).get("hp", 1) <= 0    # ADR-0044: forced promote next turn
        board = Board(
            opp_active_doomed=opp_doomed,
            forced_promotion_key=self._forced_promotion_key(opp, opp_doomed),
            my_bench=model.mine.bench_count,
            bench_full=model.mine.bench_full,                   # reads the engine's own `benchMax`
            my_active_id=(ma or {}).get("id"),
            my_active_energy=(model.mine.active.energy_count
                              if model.mine.active is not None else 0),  # UNITS, not typed count
            my_active_hp=(ma or {}).get("hp", 0),
            opp_bench=tuple((b.card_id, b.body.get("hp", 0)) for b in model.theirs.bench),
            known_top=tuple(model.carried.get("known_top") or ()),
            turn=model.mine.turn,
            energy_attached=model.energy_attached,
            supporter_played=model.supporter_played,
            hand_startable=self._hand_startable(me.get("hand") or []),
            active_doomed=active_doomed,
            incoming_active_damage=self._incoming_active_damage(ma, oa),
            active_cheap_attack_kos=active_lethal,
            active_can_ko=self._active_can_ko(ma, oa),
            active_maxed_kos=self._active_maxed_kos(ma, oa),
            gust_best_ko_prizes=self._gust_best_ko_prizes(ma, opp, payable),
            active_ko_prizes=self._active_ko_prizes(ma, oa, payable),
            gust_best_total_prizes=self._gust_best_total_prizes(ma, opp, payable),
            menu_attack_total_prizes=self._menu_attack_total_prizes(ma, oa, opp, payable),
            gust_ko_energy_swing=self._gust_ko_energy_swing_calc(ma, oa, opp, payable),
            stall_swap_pointless=self._stall_swap_pointless(opp),
            my_prizes_remaining=model.prize_race.my_prizes_remaining,
            opp_prizes_remaining=model.prize_race.opp_prizes_remaining,
            reusable_energy_in_hand=self._has_reusable_energy(me.get("hand") or []),
            recycle_dead_only=self._recycle_dead_only(me),
            active_famine=famine,
            active_unarmed_but_able=unarmed_but_able,
            active_attack_provable=(not model.mine.attack_blocked        # the rules gate first
                                    and model.mine.reachable_attach(model.mine.active, provable=True)
                                    and not self._attack_impossible_on_menu(
                                        select, model.mine.attach_budget(model.mine.active,
                                                                         provable=True))),
            immediate_preevo_in_play=self._immediate_preevo_in_play(me),
            deploy_now_ids=self._deploy_now_ids(me, state.get("turn", 0)),
            active_arm_available=self._active_arm_available(ma, self._bench_wincon_ready(me)),
            active_fully_powered=self._active_fully_powered(ma),
            energy_placeable=self._energy_placeable(me),
            wincon_in_play=self._wincon_in_play(me),
            wincon_prize_value=self._wincon_prize_value(),
            wincon_in_hand=self._wincon_in_hand(me),
            line_preevo_in_play=self._line_preevo_in_play(me),
            line_preevo_in_hand=self._line_preevo_in_hand(me),
            bench_line_member_needs=self._bench_line_member_needs(me),
            wincon_base_deployable=self._payoff_immediate_preevo_available(me),
            wincon_in_hand_undeployable=self._wincon_in_hand_undeployable(me),
            accel_recipient_missing=self._accel_recipient_missing(me),
            support_in_play=self._support_in_play(me),
            in_play_ids=frozenset(p.get("id") for p in ((me.get("active") or []) + (me.get("bench") or []))
                                  if p and p.get("id") is not None),
            in_play_attack_colors=self._in_play_attack_colors(me),
            in_play_required_colors=(self._in_play_attack_colors(me) | self._in_play_ability_fuel_colors(me)),
            in_play_unfueled_ability_colors=self._in_play_unfueled_ability_colors(me),
            setup_placed_ids=self._setup_placed_ids(obs),
            hand_duplicate_ids=self._hand_duplicate_ids(me),
            top_fetch_priority_id=self._top_fetch_priority_id(select),
            top_starter_id=self._top_starter_id(obs, select),
            weakest_bench_hp=self._weakest_snipe_hp(obs, select),
            strongest_forward_bench=self._strongest_forward_snipe(obs, select),
            snipe_damage=self._snipe_damage(obs, (ma or {}).get("id"), select),
            snipe_ko_available=self._snipe_ko_available(
                opp, self._snipe_damage(obs, (ma or {}).get("id"), select)),
            best_counter_slot=self._best_counter_slot(obs, select) if select else None,
            best_counter_source_slot=self._best_counter_source_slot(obs, select) if select else None,
            max_counter_move_number=self._max_counter_move_number(select) if select else 0,
            stadium_in_play=model.stadium_id,
            opp_stadium_in_play=model.stadium_is_theirs,
            bench_wincon_ready=self._bench_wincon_ready(me),
            best_promote_slot=self._best_promote_slot(me),
            evolve_to_ready_wincon_available=self._evolve_to_ready_wincon_available(me),
            bench_wincon_prize_value=self._bench_wincon_prize_value(me),
            bench_wincon_underpowered=self._bench_wincon_underpowered(me),
            opp_cannot_punish_wincon=self._opp_cannot_punish_wincon(me, opp),
            basic_energy_in_deck=self._basic_energy_in_deck(deck_empty),
            my_discard_basic_energy=model.mine.discard_energy_counts,
            opp_discard_energy=model.theirs.discard_energy_counts,        # both discards are PUBLIC
            active_best_attack_locked=self._active_best_attack_locked(ma),
            opp_has_stage2=self._board_has_stage2(opp),
            opp_has_colorless_ability=self._board_has_colorless_ability(opp),
            hand_ids=frozenset(model.mine.hand_ids),
            search_deck_ids=(frozenset(c.get("id") for c in (select.get("deck") or [])
                                       if c and c.get("id") is not None)
                             if select and select.get("deck") else None),
            hand_basic_energy=model.mine.hand_energy_counts,
            no_supporter_in_hand=self._no_supporter_in_hand(me),
            opp_has_played_gust=self._opp_has_played_gust(),
            active_is_wincon=bool(ma) and ma.get("id") in self._wincon_set(),
            active_is_weak_preevo=self._active_is_weak_preevo(ma),
            can_wall_line_with_disruptor=self._can_wall_line_with_disruptor(me, ma, oa),
            can_lock_line_with_disruptor=self._can_lock_line_with_disruptor(
                me, ma, oa, state.get("turn", 0)),
            priority_wincon_slot=self._priority_wincon_slot(
                me, active_lethal, active_doomed),
            attach_from_concentrate_slot=self._attach_from_concentrate_slot(me, select),
            stall_target_exists=self._stall_target_exists(opp),
            stall_target_is_keystone=self._stall_target_is_keystone(opp),
            opp_has_energy_in_play=self._opp_has_energy_in_play(opp),
            opp_active_has_energy=bool(oa and (oa.get("energies") or [])),
            opp_active_can_damage_us=self._opp_active_can_damage_us(ma, oa),
            opp_hand_size=model.theirs.hand_size,
            my_hand_size=model.mine.hand_size,
            # Opponent RESOURCES (ADR-0047) flattened for `when()` triggers. Each read fails OPEN.
            opp_took_ko_this_turn=bool(getattr(_opp_res, "took_ko_this_turn", False)),
            my_pokemon_koed_last_turn=bool(getattr(_opp_res, "my_pokemon_koed_last_turn", False)),
            opp_hand_size_delta=getattr(_opp_res, "hand_size_delta", None),
            opp_last_turn_dumped=bool(getattr(_opp_res, "last_turn_dumped", False)),
            opp_deckout_in_turns=getattr(_opp_res, "deckout_in_turns", None),
            opp_comeback_disruptor=bool(brief is not None
                                        and self.opponent.disposition("opp_comeback_disruptor", False)),
            opp_hand_strip_odds=self._opp_hand_strip_odds(),
            deck_empty_ids=deck_empty,
            deck_known_counts=deck_known,
            deck_contains_odds=deck_odds_map,
            opp_active_condition_gift=self._opp_active_condition_gift(opp),
            active_condition_ko_prizes=self._active_condition_ko_prizes(opp, oa),
            read=read,                                              # None = Posture off (ADR-0026)
            opponent=self.opponent,
            posture_confidence=gamma,                               # γ ∈ [0,1] the levers scale by
            favorability=fav, matchup_coverage=cov,                 # lever-A signal + its reliability
            brief=brief,                                            # None = no matched Brief (ADR-0027)
            brief_threat_ids=brief_threat_ids,                      # resolved to card ids
            brief_target_roles=brief_target_roles,
            matchup_plan=matchup_plan,                              # ADR-0051 target-priority spine
            **path_sig,                                             # Tier-3 two-sided Prize Path
            line_ready=(base_plan == Plan.RACE),
            phase=phase,                                            # ADVISORY: bands + trace, never a gate
        )
        if self.promote_ko_aware and select is not None and select.get("context") in (_TO_ACTIVE, _SWITCH):
            board.ko_promote_slot = self._ko_aware_promote_slot(obs, board, me, oa)   # None when no
            #                                             benched body reaches a KO -> inert
        board.game_plan = self.plan_match(obs, board)   # the Match Planner (ADR-0045) runs first each turn;
        board.turn_goal_satisfied = self._turn_goal_satisfied(board, select)
        # The three per-decision caches below all serve ADR-0076 Amendment C's resolve-once promise:
        # each read is per BODY or per HAND while `_context` runs per OPTION.
        self._item_hold_cache = {}                  # keyed by CARD ID (`_item_hold_price`)
        self._snipe_relevance_cache = {}            # keyed by id(body)
        self._snipe_peer_cache = None               # `[(relevance, priority)]` over the WHOLE menu, for
                                                    # the Brief tiebreak; per-option would be O(n^2)
        self._opponent_target_cache = self._opponent_target_rows(obs, board)
        if self.deny_relevance and self._opponent_target_cache is not None:
            _rel_rows = self._opponent_target_cache[1]
            # AFFORDABLE relevance, not full: spending the card prices only what they can do NOW
            # (ADR-0080 Amendment B). The weighting lives on the callee, so the two reads cannot drift.
            board.deny_relevance_best = self._best_area_weighted_relevance(_rel_rows, opp, oa)
            board.deny_relevance_rows = tuple(
                (r["area"], r["bi"], dict(r.get("relevance_by_type") or {}), r.get("strip_shift"))
                for r in _rel_rows)
        return board

    def _observe_known_top(self, obs: dict) -> None:
        """Consume real logs into the self-verifying known-top deck belief."""
        logs = obs.get("logs") or []
        if not logs:
            return
        state = obs.get("current") or {}
        yi = state.get("yourIndex", 0)
        known = [tuple(x) for x in (getattr(self, "_known_top", None) or ())]
        placed_top = []

        def flush_top():
            nonlocal known, placed_top
            if placed_top:
                known = placed_top + known
                placed_top = []

        for lg in logs:
            if lg.get("playerIndex") != yi:
                continue
            typ = lg.get("type")
            if typ == _SHUFFLE:
                known = []
                placed_top = []
                continue
            if typ == _DRAW:
                flush_top()
                known = self._known_top_reconcile(known, lg)
                continue
            if typ == _DRAW_REVERSE:
                known = []
                placed_top = []
                continue
            if typ == _MOVE_CARD_REVERSE:
                if lg.get("fromArea") == _DECK or lg.get("toArea") == _DECK:
                    known = []
                    placed_top = []
                continue
            if typ != _MOVE_CARD:
                if lg.get("fromArea") == _DECK or lg.get("toArea") == _DECK:
                    known = []
                    placed_top = []
                continue
            fr, to = lg.get("fromArea"), lg.get("toArea")
            if to == _DECK:
                key = self._known_top_log_key(lg)
                if key is None:
                    known = []
                    placed_top = []
                else:
                    placed_top.append(key)
                continue
            if fr == _DECK:
                flush_top()
                known = self._known_top_reconcile(known, lg)

        flush_top()
        self._known_top = tuple(known) or None

    def _opp_hand_strip_odds(self) -> float:
        """P(their deck still holds ≥1 `hand_disruption` card that shuffles MY hand away). Fails OPEN
        to 0.0 — any gap claims NO exposure, so the deferral veto reading it never fires on a guess."""
        if self.opponent is None or not self.functions:
            return 0.0
        try:
            odds = self.opponent.copies_left_odds()
            return max((p for cid, p in odds.items()
                        if "hand_disruption" in self.functions.tags(cid)), default=0.0)
        except Exception:
            return 0.0

    def _turn_goal_satisfied(self, board: Board, select: dict | None) -> bool:
        """DELIBERATELY ALWAYS FALSE: no sound "this turn's directed goal is met" oracle exists yet and
        every proxy over-claims. WIRED and telemetry-visible; its only consumer ships at weight 0."""
        return False

    def _typed_boost_total(self, obs: dict, body_stat, defender: dict | None) -> int:
        """Flat this-turn damage-boost for ``body_stat``: boosts already played plus playable copies in
        hand. Each boost's own attacker-type and defender-{ex} gates apply, so an uncashable one is 0."""
        if body_stat is None:
            return 0
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        dstat = self.stats.get((defender or {}).get("id")) if (self.stats and defender) else None
        def_is_ex = bool(dstat and dstat.is_ex_body)

        def applies(atype, vs_ex) -> bool:
            if atype is not None and getattr(body_stat, "energyType", None) != atype:
                return False
            return not (vs_ex and not def_is_ex)

        total = 0
        for amount, atype, vs_ex in self._turn_boosts.boosts_for(yi):
            if applies(atype, vs_ex):
                total += amount
        supporter_spent = bool(state.get("supporterPlayed"))
        for c in (me.get("hand") or []):
            st = self.stats.get((c or {}).get("id")) if (self.stats and c) else None
            if st is None or not getattr(st, "damageBoost", 0) or getattr(st, "hp", 0):
                continue
            if st.is_tool:                                     # a Tool boost lives while ATTACHED
                continue                                       # (visible board state, priced elsewhere)
            if st.is_supporter and supporter_spent:
                continue
            if applies(st.damageBoostType, st.damageBoostVsEx):
                total += st.damageBoost
        return total

    def _opp_has_played_gust(self) -> bool:
        """A `gust`-tagged card sits in their discard, so they CAN drag my benched wincon up. Their
        discard is a PUBLIC zone (docs/rules.md), so this is sound knowledge, not an estimate."""
        model = self._state_model
        if model is None or not self.functions:
            return False
        return any("gust" in self.functions.tags(cid) for cid in model.theirs.discard_ids)

    def _energy_placeable(self, me: dict) -> bool:
        """Can any in-play body still absorb Energy productively. Fail-OPEN (True) without stats: only
        suppress the held-Energy guard on a positive confirmation that no body can use the Energy."""
        if not self.stats:
            return True
        for p in (me.get("active") or []) + (me.get("bench") or []):
            if not p:
                continue
            stat = self.stats.get(p.get("id"))
            cost = getattr(stat, "maxDamageCost", None) if stat else None
            if cost and len(p.get("energies") or []) < cost:
                return True
        return False

    def _reusable_energy_id(self, hand: list):
        """The first reusable (non-`discard_eot`) TYPED Energy card id in ``hand``. The engine reports
        `energyType == 0` for Trainers *and* colourless specials, so `not in (None, 0)` excludes both."""
        for c in hand:
            cid = c.get("id") if c else None
            if cid is None:
                continue
            stat = self.stats.get(cid) if self.stats else None
            tags = self.functions.tags(cid) if self.functions else []
            if stat and stat.hp == 0 and stat.energyType not in (None, 0) and "discard_eot" not in tags:
                return cid
        return None

    def _has_reusable_energy(self, hand: list) -> bool:
        """The boolean projection of `_reusable_energy_id`."""
        return self._reusable_energy_id(hand) is not None

    def _hand_duplicate_ids(self, me: dict) -> frozenset:
        """Card ids I hold 2+ copies of in hand, EXCLUDING fungible Energy — a spare Energy is always a
        future attach, never a redundant pitch."""
        counts = Counter(c.get("id") for c in (me.get("hand") or []) if c and c.get("id") is not None)
        out = set()
        for cid, n in counts.items():
            if n < 2:
                continue
            stat = self.stats.get(cid) if self.stats else None
            if stat and stat.is_energy:
                continue                                  # fungible Energy: spare is never a redundant pitch
            out.add(cid)
        return frozenset(out)

    def _incoming_active_damage(self, ma: dict | None, oa: dict | None) -> int:
        """Worst next-turn damage their Active deals mine (ADR-0052) — a +HP tool's survival breakpoint.
        `CURRENT_FORMS_ONLY` makes it CURRENT-form; the line it becomes is `active_doomed`'s question."""
        model = self._state_model
        if model is None:
            return 0
        return int(model.theirs.incoming(ma, 1, bodies=[oa], charged=UNCHARGED,
                                         forward_ids=CURRENT_FORMS_ONLY,
                                         context=self._opp_attack_context))

    def _attack_impossible_on_menu(self, select, budget) -> bool:
        """The ENGINE says my Active cannot attack: at the open menu, no ATTACK option. NOT decisive
        while the attach BUDGET could still turn one on — the "reusable Energy in hand" test under-reads."""
        if not select or select.get("context") != _MAIN:
            return False
        opts = select.get("option") or []
        if not opts or any(o.get("type") == _ATTACK for o in opts):
            return False
        return not (budget is not None and budget.size > 0)

    def _active_fully_powered(self, ma: dict | None) -> bool:
        """My Active already carries its HIGHEST-damage attack's cost. False when the stat/cost is
        unknown (fail-closed, so the keep-at-discard rules stay protective)."""
        stat = self.stats.get((ma or {}).get("id")) if (self.stats and ma) else None
        cost = getattr(stat, "maxDamageCost", 0) or 0
        if not cost:
            return False
        return len((ma or {}).get("energies") or []) >= cost

    def _active_cheap_attack_kos(self, ma: dict | None, oa: dict | None) -> bool:
        """My Active's CHEAPEST attack KOs their current Active — the mirror of `_active_doomed`."""
        if not (self.stats and ma and oa):
            return False
        return self._can_ko(self.stats.get(ma.get("id")), oa)

    def _can_wall_line_with_disruptor(self, me: dict, ma: dict | None, oa: dict | None) -> bool:
        """Premise of the retreat-to-promote-a-sacrificial-wall maneuver. ⚠️ Its RETREAT half has NO
        consumer left (Issue #386); only the ATTACH rung in `baseline_energy.py` still reads this."""
        if not (self.functions and ma and ma.get("id") in self._line_preevo_set()):
            return False
        has_lock = any(b and "item_lock" in self.functions.tags(b.get("id"))
                       for b in (me.get("bench") or []))
        return has_lock and self._opp_active_can_damage_us(ma, oa)

    def _can_lock_line_with_disruptor(self, me: dict, ma: dict | None, oa: dict | None,
                                      turn: int) -> bool:
        """OFFENSIVE variant of the disruptor maneuver: unlike `_can_wall_line_with_disruptor` it does
        NOT need the opponent to threaten damage now — their Item-reliant SETUP turn is the target."""
        if not (getattr(self, "disruptor_lock_maneuver", False) and self.functions
                and turn <= 2 and ma and self.stats):
            return False
        ma_id = ma.get("id")
        # Eligible Active: a fragile wincon LINE pre-evo, OR a retreatable NON-attacking support-ex
        # PIVOT we would cycle out anyway. Both sac into the benched item_lock.
        ma_stat = self.stats.get(ma_id)
        is_support_ex_pivot = (ma_stat is not None and ma_stat.is_ex_body
                               and ma_id not in self._wincon_set())
        if not (ma_id in self._line_preevo_set() or is_support_ex_pivot):
            return False
        has_lock = any(b and "item_lock" in self.functions.tags(b.get("id"))
                       for b in (me.get("bench") or []))
        if not has_lock:
            return False
        line_ids = self._line_preevo_set() | self._wincon_set()
        in_play = [p for p in (me.get("active") or []) if p] + [b for b in (me.get("bench") or []) if b]
        if any((p.get("energies") or []) for p in in_play if p.get("id") in line_ids):
            return False                                  # a wincon Line body is already being energized
        # ^ RETAINED DELIBERATELY though doctrinally too strict (user rulings 2026-07-28/29): deleting
        # it measured −4.75% over 2400 games (ADR-0072 A/B). The real fix is the value question, #165.
        if ma_stat is None or getattr(ma_stat, "retreatCost", 0) > len(ma.get("energies") or []) + 1:
            return False                                  # the retreat must be reachable this turn
        return not self._active_maxed_kos(ma, oa)         # don't waste a body that could KO instead

    # Gust Board-signal builders live in doctrine_gust.GustMixin. `_opp_has_hand_size_attacker` is
    # DELETED (ADR-0102) with its Board field and rungs, and deliberately NOT replaced.
    def _opp_has_energy_in_play(self, opp: dict | None) -> bool:
        """Any opponent Pokémon carries Energy — a target an `energy_denial` Item can strip. With none
        in play the coin-flip denial whiffs, so the Item is held."""
        if not opp:
            return False
        board = (opp.get("active") or []) + (opp.get("bench") or [])
        return any(p and (p.get("energies") or []) for p in board)
