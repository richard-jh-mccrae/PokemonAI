"""Assembles the per-turn `Board` — the one place a turn-level fact is derived.

A decider reads `board.x`; it never re-derives x. That is the whole contract: an unconsumed Board field is an unbuilt
feature, and a fact derived twice is a fact that will eventually disagree with itself.

The two known-top STATIC helpers stay in `pilot.py`: `_known_top_reconcile` names `Pilot` by class, so moving it would
be a code change rather than a move."""
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
        """Summarise the shared board once per decision (see Board).

        ``carried`` (a :class:`~common.state_model.CarriedState` snapshot) makes the build PURE
        (ADR-0068 decision 2): the two hysteresis memories — the phase Schmitt trigger and the
        Prize-Path stickiness — are then read from the snapshot instead of ``self``, and the new
        values are not written back. Callers building a HYPOTHETICAL board pass it, which is what
        retires the hand-written snapshot/restore guards that each such site previously had to
        remember. A live decision passes nothing and keeps the in-order write, byte-identically."""
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        ma = next((p for p in (me.get("active") or []) if p), None)
        oa = next((p for p in (opp.get("active") or []) if p), None)
        # OPPONENT-as-attacker context, cached per decision (ADR-0032 P1): Incoming estimates price
        # their scalers off THEIR visible state — hand/bench/Energy/discard (opp Kyogre's Riptide is exact)
        self._opp_attack_context = self._damage_context(obs, attacker_is_me=False)
        prizes = obs.get("own_prizes")             # exact prize multiset from deck-tracker, or None
        if prizes:                                 # keys are card ids: coerce str->int so a JSON-captured
            prizes = {int(k): v for k, v in prizes.items()}   # obs (a Correction) matches the int decklist

        deck_empty = self._deck_empty_ids(me, prizes)
        deck_known = self._deck_known_counts(me, prizes)
        deck_odds_map = self._deck_contains_prob(me, deck_known)   # probabilistic complement (ADR-0029)
        read = self.opponent.observe(obs)            # ADR-0047 fan-out: Identity (Scout) + Resources
        if self.scout is None:                       # preserve Posture-off semantics (facade returns Read())
            read = None                              # the Read (M2.0); γ/favorability derive from it
        gamma = _posture_gamma(read) if self.posture else 0.0    # γ threads into snipe rank; kill-switch zeroes it
        my_arch = self.strategy.params.get("my_archetype")
        fav, cov = (matchup_favorability(self.scout.artifact, my_arch, read.candidates)
                    if (self.posture and self.scout and read and my_arch) else (0.5, 0.0))
        # covers-routed (ADR-0027), γ-gated to a RECOGNIZED opponent: on an empty early board the Read's
        # top candidate is just the prior favourite -> gate on γ>0 to keep board.brief off until recognized.
        brief = match_brief(self.briefs, read) if (self.posture and read and gamma > 0) else None
        self.opponent.note_brief(brief)              # feed the γ-gated Brief to Dispositions (ADR-0047)
        # ADR-0064 Decision 1: the reachable-Incoming energy policy. Charged (per-attack typed-cost
        # affordability) ONLY behind a γ-matched Brief — the calibrated "we know what they run" signal;
        # an unrecognized opponent stays None → worst-case ceiling (never relax pessimism on a guess).
        # burst_on_evo credits an Ignition-class colourless burst ({C}{C}{C} on an Evolution): it only
        # ever makes a COLOURLESS-costed attack more reachable (the pessimism-safe direction — it can
        # never fund a typed {F}{F}), so a flat matched-archetype allowance keeps a burst nuke doomed
        # while the typed/colourless split sharpens genuine typed-cost reach (the variant-2 read).
        self._incoming_budget = {"base_attach": 1, "burst_on_evo": 2} if brief is not None else None
        _opp_res = getattr(self.opponent, "resources", None)   # match-scoped Resources tracker (flattened below)
        # Resolve the matched Brief's name-keyed threats/targets to card ids (ADR-0027 consumer). Guarded
        # like forward_max_damage: an old/None provider -> empty, never crashes. Behavior-neutral surface.
        _ids_for_name = getattr(self.stats, "ids_for_name", None)
        brief_threat_ids, brief_target_roles = (
            resolve_brief_cards(brief, _ids_for_name)
            if (brief is not None and _ids_for_name is not None) else (frozenset(), {}))
        matchup_plan = self._matchup_plan(opp, brief_target_roles, read, gamma)   # ADR-0051 spine
        # The StateModel for this decision (ADR-0068) — the ONE two-sided snapshot the migrated Board
        # fields below read instead of each calling its own hand-rolled helper. Construction computes
        # NOTHING (every field is lazy), so building it here costs only the fields actually read; new
        # consumers from Phase 1a on take it directly rather than going through Board at all.
        #
        # **Built HERE rather than at the top of `_board()`** (POC-T1, Issue #260). `TheirSide`'s clock
        # family takes the Read's `charged` energy policy and the forward-availability gate as
        # CONSTRUCTOR arguments (the T0 API, Issue #259), and both are resolved by the Read/Brief
        # fan-out above — so a model built before them is strictly WORSE than the CombatMath bypasses
        # it is meant to replace, which is exactly why every live consumer bypassed it. Nothing between
        # the old build site and here reads `self._state_model`, so the move is behaviour-neutral; the
        # threading below is what closes the gap.
        model = self._snapshot(obs, my_index=yi, deck_empty=deck_empty,
                               read=read, brief=brief,
                               matchup_plan=matchup_plan, gamma=gamma, favorability=fav,
                               matchup_coverage=cov, carried=carried)
        active_doomed = self._active_doomed(ma, oa, opp)
        active_lethal = self._active_cheap_attack_kos(ma, oa)   # its turn is done — build the successor
        # the Energy my Active can actually PAY an attack with this turn: attached + the best unspent
        # hand attach (Ignition = 3 on an Evolution) — the gust/offense affordability gate (f31)
        payable = ((model.mine.active.energy_count if model.mine.active is not None else 0)
                   + (0 if model.energy_attached
                      else self._best_hand_attach_units(          # ← StateModel (POC-T1): my hand
                          frozenset(model.mine.hand_ids),         #   and my Active's Energy both
                          self.stats.get((ma or {}).get("id")) if self.stats else None)))
        # **Famine** (#142) — "my Active cannot attack this turn", read ONCE off the model: no attack
        # reachable under the full Attach Budget, or the rules forbid one at all (`attack_blocked`).
        famine = model.mine.active_famine
        # 0 attached, yet an attack is still reachable this turn — the fact behind "go down swinging
        # rather than stall-gust". Derived here because two stall-gust rules need the identical clause.
        unarmed_but_able = (model.mine.active is not None
                            and model.mine.active.energy_count == 0 and not famine)
        base_plan = (choose_plan(state, self.strategy, self.stats) if state.get("players")
                     else Plan.SETUP)                   # the readiness core (SETUP→RACE)
        path_sig = self._path_signals(obs, me, opp, ma, oa,   # Tier-3 two-sided Prize Path (ADR-0040):
                                      len(me.get("prize") or []),   # re-derived every decision,
                                      len(opp.get("prize") or []),  # ranking data only; their-side
                                      read, gamma,                  # sees the γ-gated Read overlay (T4)
                                      carried=carried)              # snapshot ⇒ pure (ADR-0068)
        phase = self._derive_phase(base_plan, path_sig["race_ahead"], active_doomed,
                                   len(me.get("prize") or []),   # derived ADVISORY phase (hysteretic)
                                   favorability=fav, coverage=cov,  # + Tier-4 favorability (Lever A)
                                   carried=carried)                 # snapshot ⇒ pure (ADR-0068)
        opp_doomed = oa is None or (oa or {}).get("hp", 1) <= 0    # ADR-0044: forced promote next turn
        board = Board(
            opp_active_doomed=opp_doomed,
            forced_promotion_key=self._forced_promotion_key(opp, opp_doomed),
            my_bench=model.mine.bench_count,                    # ← StateModel (POC-T1): bench
            bench_full=model.mine.bench_full,                   #   occupancy has ONE derivation,
            #                                                     and `bench_full` reads the
            #                                                     engine's own `benchMax`
            my_active_id=(ma or {}).get("id"),
            my_active_energy=(model.mine.active.energy_count            # ← StateModel (POC-T1):
                              if model.mine.active is not None else 0),  #   UNITS, not typed count
            my_active_hp=(ma or {}).get("hp", 0),
            opp_bench=tuple((b.card_id, b.body.get("hp", 0)) for b in model.theirs.bench),
            known_top=tuple(model.carried.get("known_top") or ()),
            turn=model.mine.turn,                               # ← StateModel: the turn/allowance
            energy_attached=model.energy_attached,              #   facts, off their one home
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
            my_prizes_remaining=model.prize_race.my_prizes_remaining,   # ← StateModel (ADR-0068):
            opp_prizes_remaining=model.prize_race.opp_prizes_remaining,  # the ONE prize-race read
            reusable_energy_in_hand=self._has_reusable_energy(me.get("hand") or []),
            recycle_dead_only=self._recycle_dead_only(me),
            active_famine=famine,                                        # ← StateModel (#142): the ONE
            active_unarmed_but_able=unarmed_but_able,
            active_attack_provable=(not model.mine.attack_blocked        # the rules first: a boost on
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
            stadium_in_play=model.stadium_id,                   # ← StateModel (POC-T1): the
            opp_stadium_in_play=model.stadium_is_theirs,         #   Stadium and who owns it
            bench_wincon_ready=self._bench_wincon_ready(me),
            best_promote_slot=self._best_promote_slot(me),
            evolve_to_ready_wincon_available=self._evolve_to_ready_wincon_available(me),
            bench_wincon_prize_value=self._bench_wincon_prize_value(me),
            bench_wincon_underpowered=self._bench_wincon_underpowered(me),
            opp_cannot_punish_wincon=self._opp_cannot_punish_wincon(me, opp),
            basic_energy_in_deck=self._basic_energy_in_deck(deck_empty),
            my_discard_basic_energy=model.mine.discard_energy_counts,    # ← StateModel: both discards
            opp_discard_energy=model.theirs.discard_energy_counts,        # are PUBLIC, so sound counts
            active_best_attack_locked=self._active_best_attack_locked(ma),
            opp_has_stage2=self._board_has_stage2(opp),
            opp_has_colorless_ability=self._board_has_colorless_ability(opp),
            hand_ids=frozenset(model.mine.hand_ids),                      # ← StateModel
            search_deck_ids=(frozenset(c.get("id") for c in (select.get("deck") or [])
                                       if c and c.get("id") is not None)
                             if select and select.get("deck") else None),
            hand_basic_energy=model.mine.hand_energy_counts,               # ← StateModel
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
            opp_hand_size=model.theirs.hand_size,               # ← StateModel (POC-T1): THE
            my_hand_size=model.mine.hand_size,                   #   supplier of BOTH hand counts
            # Opponent RESOURCES (ADR-0047) flattened for `when()` triggers — sourced from the tracker
            # observed at self.opponent.observe(obs) above; each read fails OPEN (unknown -> no-fire default).
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
            read=read,                                              # Posture Read (ADR-0026); None = off
            opponent=self.opponent,                                 # Opponent Model facade (ADR-0047)
            posture_confidence=gamma,                               # γ ∈ [0,1] the levers scale by
            favorability=fav, matchup_coverage=cov,                 # lever-A signal + its reliability
            brief=brief,                                            # matched Matchup Brief (ADR-0027); None = off
            brief_threat_ids=brief_threat_ids,                      # its threats/targets resolved to card ids
            brief_target_roles=brief_target_roles,                  # (behavior-neutral consumer surface)
            matchup_plan=matchup_plan,                              # ADR-0051 unified target-priority spine
            **path_sig,                                             # Tier-3 two-sided Prize Path
            line_ready=(base_plan == Plan.RACE),                    # the readiness signal old plan
                                                                    # gates migrated to (ADR-0040)
            phase=phase,                                            # derived ADVISORY phase — bands +
                                                                    # trace only, never a gate
        )
        if self.promote_ko_aware and select is not None and select.get("context") in (_TO_ACTIVE, _SWITCH):
            board.ko_promote_slot = self._ko_aware_promote_slot(obs, board, me, oa)   # KO-aware,
            #                                             boost-inclusive promote target (KO-gated; None
            #                                             when no benched body reaches a KO -> inert)
        board.game_plan = self.plan_match(obs, board)   # the Match Planner (ADR-0045) runs first each turn;
        board.turn_goal_satisfied = self._turn_goal_satisfied(board, select)  # BUILD 4 predicate
        # ADR-0076: the shared per-body opponent-target value, resolved ONCE per `_board()` call and
        # cached (the `_opp_attack_context` stash precedent) — the deny fire rung and the
        # live `gust_target` slot emission read this SAME cache rather than each re-running the
        # per-body `turns_to_ko_me` simulation from scratch.
        self._item_hold_cache = {}                  # per-decision, keyed by CARD ID — the free-Item
                                                    # hold price (`_item_hold_price`, Issue #261 item
                                                    # 2f). Resolving it walks the whole hand through
                                                    # `_resolve_needs`, and the deciders that read it
                                                    # run per OPTION over a hand that routinely holds
                                                    # two copies of the same Item.
        self._snipe_relevance_cache = {}            # per-decision, keyed by id(body) — the curve
                                                    # reads are per BODY while `_context` runs per
                                                    # OPTION, and a DAMAGE select offers the same
                                                    # bench repeatedly (ADR-0076 Amendment C's
                                                    # resolve-once-per-decision promise).
        self._snipe_peer_cache = None               # per-decision `[(relevance, priority)]` over the
                                                    # WHOLE menu, for the Brief tiebreak (ADR-0085
                                                    # Amendment H). Built once: the tiebreak is
                                                    # inherently peer-relative, so computing it per
                                                    # option would rebuild every rival's Context on
                                                    # every option — O(n^2) `_context` per decision.
        self._opponent_target_cache = self._opponent_target_rows(obs, board)
        if self.deny_relevance and self._opponent_target_cache is not None:
            # Deny Relevance, resolved ONCE per decision off that same cache (ADR-0080, Issue #187).
            # The three deny surfaces read these fields; none re-scores a body, so the ADR-0076
            # Amendment C "resolved once per decision" promise covers deny too.
            _rel_rows = self._opponent_target_cache[1]
            # The AREA weighting and its ADR-0084 decision-5 derivation now live on
            # `_best_area_weighted_relevance`,
            # so the ladder `_denial_play_tactical` reads and this per-decision build cannot drift.
            # The reading is the AFFORDABLE one, not the full one: spending the card prices only what
            # they can do NOW (ADR-0080 Amendment B). Measured on the four ADR-0062 anchors, this is
            # what keeps all four signs: f21/f29 hold (-6.50), f12 plays (+16.00), f26 plays (+0.50).
            # Full relevance here fires on f21/f29 (+2.50) off an unaffordable Phantom Dive.
            board.deny_relevance_best = self._best_area_weighted_relevance(_rel_rows, opp, oa)
            board.deny_relevance_rows = tuple(
                (r["area"], r["bi"], dict(r.get("relevance_by_type") or {}), r.get("strip_shift"))
                for r in _rel_rows)
        return board                                    # COMPUTE-ONLY here — nothing scores off it yet (S2)

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
        """`Board.opp_hand_strip_odds` — the held-card-risk exposure leg (hypergeometric-fetch-closure
        §Round 8 §5): P(the opponent's deck still holds ≥1 card that shuffles MY hand away), read as
        the max `copies_left_odds` over the matched Read's representative build restricted to
        `hand_disruption`-tagged cards (Judge / Harlequin / Unfair Stamp — verified tags,
        card_functions.json). `copies_left_odds` already nets out their tracker-observed plays (a
        Judge in their discard is a Judge they no longer hold). Fails OPEN to 0.0 — no facade, no
        functions table, no confident Read, or any error claims NO exposure, so the deferral veto
        reading this never fires on a guess (the declared suppressor fail direction)."""
        if self.opponent is None or not self.functions:
            return 0.0
        try:
            odds = self.opponent.copies_left_odds()
            return max((p for cid, p in odds.items()
                        if "hand_disruption" in self.functions.tags(cid)), default=0.0)
        except Exception:
            return 0.0

    def _turn_goal_satisfied(self, board: Board, select: dict | None) -> bool:
        """BUILD 4 predicate — is THIS turn's directed goal already met, so a draw/gust/evolution Supporter
        could be HELD for a later decisive turn (`dont-spend-unneeded-supporter`)?

        DELIBERATELY FAILS SAFE TO FALSE. A sound "the directed goal is *met*" oracle is not derivable from
        the current Board signals: the Game Plan exposes the directed goal-KIND (survive / ko_on_path /
        trade) and its confidence, but NOT a per-mode completion state, and a plausible proxy ("I can attack,
        so I'm done") over-claims — drawing could still find the piece that turns a chip into a lethal, so
        holding on that proxy would lose tempo. Rather than assert an unsound True, the predicate returns
        False until a sound completion oracle exists. The field is WIRED and telemetry-visible; its only
        consumer ships at weight 0 (inert), and its intended-True board is exercised directly in tests.
        `select` is threaded so a future sound derivation can require "not mid-search/tutor" (nothing still
        being resolved) without another signature change."""
        return False

    def _typed_boost_total(self, obs: dict, body_stat, defender: dict | None) -> int:
        """Total flat this-turn damage-boost applicable to ``body_stat`` attacking the opponent's
        Active — the boosts already PLAYED this turn (`TurnBoostTracker`) plus the playable boost-Item
        copies still in MY hand (Items stack; a Supporter is one/turn, dropped once `supporterPlayed`).
        Each boost carries its own gates — the attacker-type ("your {F} Pokémon") and the defender-{ex}
        scope — applied here so a boost the line can't legally cash is never counted. 0 with no body."""
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
        """True if the opponent has played a gust (a Boss's Orders-style forced-switch) this game — a
        `gust`-tagged card sits in their discard. It means they CAN drag my benched win-condition into the
        Active and Knock it Out, so hiding the finisher on the Bench is less safe: interposing a cheap attacker
        at a promote taxes their next gust and denies the free front-line prize. False with no functions.

        Reads :attr:`TheirSide.discard_ids` (POC-T1, Issue #260). Their discard is a PUBLIC zone in
        both directions (`docs/rules.md`), so scanning it is sound knowledge rather than an estimate —
        which is exactly why it belongs on the snapshot and not in an ad-hoc walk here. The zone was
        homed at T0 and INERT; this is its first consumer."""
        model = self._state_model
        if model is None or not self.functions:
            return False
        return any("gust" in self.functions.tags(cid) for cid in model.theirs.discard_ids)

    def _energy_placeable(self, me: dict) -> bool:
        """True if any of my in-play Pokémon can still absorb Energy productively — it carries fewer
        Energy than its highest-damage attack costs (so a manual attach builds it toward a bigger
        attack). When False, a held Energy has no useful home this turn (every body is maxed, or the
        Bench is empty and the Active is fully powered), so shuffling it away with a hand-refresh costs
        nothing. Fail-OPEN (True) when stats are unavailable — only SUPPRESS the held-Energy guard when
        we can positively confirm no body can use the Energy (ep83038055 f40)."""
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
        """The first **reusable** (non-discard) Energy card id in ``hand`` — a *typed* Energy card
        (hp 0 with a real `energyType`) that is not tagged `discard_eot`. NB the engine reports
        `energyType == 0` for Trainers *and* colourless special energies (e.g. Ignition), so a typed
        basic Energy is `energyType not in (None, 0)` — that excludes Trainers and Ignition. None when
        the hand holds none."""
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
        """Is a reusable Energy in hand? The boolean projection of `_reusable_energy_id` — used to
        prefer a Basic over a discard-at-end-of-turn Energy when both are available (deck-agnostic)."""
        return self._reusable_energy_id(hand) is not None

    def _hand_duplicate_ids(self, me: dict) -> frozenset:
        """Card ids I hold 2+ copies of in hand, EXCLUDING fungible Energy (Basic / Special). The
        keep-value floor `discard-the-hand-duplicate` reads this: a second copy of an effect card
        (Supporter / Item / Pokémon) is the lowest-keep pitch at a forced discard — keep one, shed the
        rest — so a singleton disruptor (a lone Boss's Orders / Harlequin) is never discarded over a
        duplicate. Energy is excluded because a spare Energy is always a future attach, never redundant."""
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
        """Worst next-turn damage their Active deals mine (the KO oracle's read, ADR-0052) —
        exposed on the Board so a +HP tool can test a survival breakpoint."""
        model = self._state_model
        if model is None:
            return 0
        # Off the SNAPSHOT (POC-T1). `CURRENT_FORMS_ONLY` empties the forward-availability gate,
        # which is what makes this the CURRENT-form read: the Board exposes it so a +HP Tool can test
        # a survival breakpoint against what the body in front of me hits for today, and the line it
        # becomes is `active_doomed`'s question, not this one.
        return int(model.theirs.incoming(ma, 1, bodies=[oa], charged=UNCHARGED,
                                         forward_ids=CURRENT_FORMS_ONLY,
                                         context=self._opp_attack_context))

    def _attack_impossible_on_menu(self, select, budget) -> bool:
        """The ENGINE says my Active cannot attack this turn: I am at the open turn menu and it lists no
        ATTACK option. Authoritative where the closed-form energy math is not — it already accounts for
        a transient attack-lock, a Special Condition, and turn-1-going-first, and unlike the ADR-0033
        tracker it survives a single-frame retest (a Correction carries one `obs`, so the tracker never
        saw last turn's attack).

        NOT decisive while THIS TURN'S ATTACH BUDGET could still turn an attack on — only once the
        budget is empty does an empty attack menu mean 'no attack this turn'. The guard is the Budget
        and not "a reusable Energy card sits in hand" (#142): the narrower reading is the SAME
        under-read as the retired `+1`, and it fired at dragapult f70, where the hand was three
        Supporters and Crispin's fetch-and-attach was invisible to it."""
        if not select or select.get("context") != _MAIN:
            return False
        opts = select.get("option") or []
        if not opts or any(o.get("type") == _ATTACK for o in opts):
            return False
        return not (budget is not None and budget.size > 0)

    def _active_fully_powered(self, ma: dict | None) -> bool:
        """My Active already carries the Energy for its HIGHEST-damage attack (attached ≥
        `maxDamageCost`) — a burst Energy (Ignition) has no urgent job on it. False when the stat /
        cost is unknown (fail-closed: the keep-at-discard rules stay protective, ep83454549 f36)."""
        stat = self.stats.get((ma or {}).get("id")) if (self.stats and ma) else None
        cost = getattr(stat, "maxDamageCost", 0) or 0
        if not cost:
            return False
        return len((ma or {}).get("energies") or []) >= cost

    def _active_cheap_attack_kos(self, ma: dict | None, oa: dict | None) -> bool:
        """True if my Active's cheapest attack KOs the opponent's CURRENT Active this turn — so a costly
        burst Energy (e.g. Ignition -> Nebula Beam) is unnecessary. The mirror of `_active_doomed`
        (me attacking them, cheapest attack), via the shared `_can_ko` oracle."""
        if not (self.stats and ma and oa):
            return False
        return self._can_ko(self.stats.get(ma.get("id")), oa)

    def _can_wall_line_with_disruptor(self, me: dict, ma: dict | None, oa: dict | None) -> bool:
        """The retreat-to-promote-the-sacrificial-wall maneuver premise (dragapult f32/f20): my Active is
        a fragile developing win-condition LINE pre-evo (a Line pre-evolution, NOT the payoff), a benched
        `item_lock` disruptor (Budew's Itchy Pollen) can be promoted as a sacrificial wall, and the
        opponent's Active can damage that fragile line NOW (`_opp_active_can_damage_us`) — so retreat it to
        safety, promote the wall, item-lock, and evolve the line on the Bench behind cover. Board-SOUND
        (visible zones); silent for decks with no benched item-lock opener (no-op on mega_starmie /
        mega_lucario) and once the Active is the payoff (not a pre-evo). (`hold-position-in-setup` is
        DELETED, ADR-0100 §11, so there is no longer a setup brake to stand down.)

        ⚠️ **The RETREAT half of the maneuver no longer has a consumer.** This used to back
        `retreat-to-wall-the-line`, whose fire `_finish_turn_last` rode to sequence the retreat tier-0.
        POC-T4/5 (Issue #386) deleted that rung and the tier died with it — silently, because the tier
        matched the rung by ID. What survives is the ATTACH half: this signal still feeds the live
        `feed-the-line-for-disruptor-lock` (`baseline_energy.py`), the rung that funds the retreat. So
        the premise is still computed and still read; only the *"go first"* ordering claim is gone."""
        if not (self.functions and ma and ma.get("id") in self._line_preevo_set()):
            return False
        has_lock = any(b and "item_lock" in self.functions.tags(b.get("id"))
                       for b in (me.get("bench") or []))
        return has_lock and self._opp_active_can_damage_us(ma, oa)

    def _can_lock_line_with_disruptor(self, me: dict, ma: dict | None, oa: dict | None,
                                      turn: int) -> bool:
        """The OFFENSIVE variant of the disruptor maneuver (dragapult f20/t2, `disruptor_lock_maneuver`):
        early game, my Active is a fragile win-condition LINE pre-evo (f20) OR a retreatable support-ex
        PIVOT (f20's t2 sibling — Fezandipiti ex) with nothing better to do, and a benched `item_lock`
        disruptor (Budew) can be promoted to deny the opponent their Item turn — attach -> retreat the
        pivot/line-preevo into Budew -> promote -> Itchy Pollen. Unlike
        `_can_wall_line_with_disruptor` this does NOT require the opponent to threaten damage NOW (their
        Item-reliant SETUP turn is the target). Gated instead on: `turn` <= 2 (the lock bites their
        setup), NO win-condition Line body already carries Energy (nothing is being DEVELOPED — else
        that energy should advance the wincon, not fund the maneuver; the f21 boundary), the retreat is
        reachable this turn on ONE more Energy (a line-preevo Basic's cheap retreat), and the Active
        can't already KO (not a wincon attacker being wasted). Kill-switched; board-SOUND (visible
        zones); silent for decks with no benched item-lock opener. SHIP-AND-REFINE: its ladder value is
        matchup-dependent (a fragile promoted disruptor may concede a prize) — the kill-switch is the
        lever if it underperforms."""
        if not (getattr(self, "disruptor_lock_maneuver", False) and self.functions
                and turn <= 2 and ma and self.stats):
            return False
        ma_id = ma.get("id")
        # Eligible Active: a fragile win-condition LINE pre-evo (the original trigger, e.g. Dreepy), OR a
        # retreatable NON-attacking support-ex PIVOT (e.g. Fezandipiti ex, 85786096-t2) — an ex we would
        # cycle out anyway, NOT a wincon-line body. Both sac into the benched item_lock; the shared guards
        # below (nothing developed / cheap retreat / can't-KO) keep either variant a sound recovery line.
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
                                                          # -> develop it, don't retreat for the lock (f21)
        # ^ RETAINED DELIBERATELY, and known to be doctrinally wrong (user rulings 2026-07-28/29).
        # It was deleted on this branch and the deletion was REVERTED here, on evidence:
        #
        #   * The doctrine says it is too strict. On 86091435-13 the correct play is to retreat the
        #     Dreepy into Budew while severely behind, and this guard forbids it purely because the
        #     line carries one partial Energy. A boolean cannot say "behind, so protection plus
        #     disruption beats one more development step". That ruling stands.
        #   * But deleting it LOSES GAMES. The ADR-0072 mid-build paired A/B over 2400 games
        #     (`gauntlet_swap_ab.py --stage mid-build`, build-vs-build because there is no flag to
        #     overlay) returned delta -4.75%, 95% CI [-8.22%, -1.28%], 0 crashes — CI-lo through the
        #     -5% floor, and all SIX directed matchups negative at +-3.5% precision, so not noise.
        #     The per-frame gates were clean (1 corpus flip, that fix; Discrimination Gate PASS), so
        #     this is exactly the effect only the A/B can see.
        #   * WHY it costs more than the one frame it fixes: this gate feeds TWO rungs, and the
        #     heavier one is not the retreat. `retreat-to-wall-the-line` (w30) is the retreat;
        #     `feed-the-line-for-disruptor-lock` (w55, baseline_energy) is the ATTACH that funds it.
        #     Ungated, the attach rung diverts the turn's Energy into paying a retreat on boards
        #     where the line was already being built — which is the diversion `f21` actually ruled
        #     on, so the guard's own citation is apt for the attach even though it over-reaches on
        #     the retreat.
        #
        # The real fix is NOT a better boolean here: it is the value question (what a
        # protection/disruption turn is worth against the race) composed across a multi-step turn.
        # Owned by #165 (Turn Planner) with #145's currency work; both frames are recorded there.
        # Until one of those lands, this crude guard is measurably earning its keep, so it stays.
        # An untested middle option is on the record if anyone wants it: keep the guard on the w55
        # attach rung and drop it only for the w30 retreat rung, then re-run the same A/B.
        if ma_stat is None or getattr(ma_stat, "retreatCost", 0) > len(ma.get("energies") or []) + 1:
            return False                                  # the retreat must be reachable this turn
        return not self._active_maxed_kos(ma, oa)         # don't waste a body that could KO instead

    # (Gust Board-signal builders — _active_ko_prizes, _opp_active_condition_gift, etc. — are in
    # doctrine_gust.GustMixin; `_board` calls them as `self.…`.)
    # `_opp_has_hand_size_attacker` DELETED (ADR-0102, Issue #261 item 2c) with the `Board` field and
    # the two rungs it gated. It asked the `hand_size_attacker` Function Tag whether a line scales off
    # the hand, and NOTHING replaces it: a card-fact reader in front of the survival clock would be a
    # second enumeration of the Damage Formula's scaler families, free to drift from the oracle it
    # guards. `_hand_size_relief_tactical` asks the clock instead (ADR-0102 decision 5).
    def _opp_has_energy_in_play(self, opp: dict | None) -> bool:
        """True if any of the opponent's Pokémon (Active or Bench) carries Energy — a target an
        energy-denial Item (Function Tag `energy_denial`, e.g. Crushing Hammer) can strip. The
        whether-to-play gate for `play-energy-denial`: with no Energy in play the coin-flip denial
        whiffs, so hold the Item. Closed-form off the board snapshot, no Search."""
        if not opp:
            return False
        board = (opp.get("active") or []) + (opp.get("bench") or [])
        return any(p and (p.get("energies") or []) for p in board)
