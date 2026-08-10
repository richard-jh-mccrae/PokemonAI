"""The hand's OUTFLOW: what a shuffle-refresh swings, what a forced discard sheds, and what a hand-size relief play
is worth.

The four refresh legs split by WHOSE hand they price and are NOT symmetric — my hand is face-up so its leg grades each
card; theirs is a `handCount`, so its legs can only be count x rate."""
from __future__ import annotations


from collections import Counter

from common.deciders.facts import Board, ShedPlan
from common.grading import halve as _halve
from common.strategy.combat import UNCHARGED
from common.strategy.context import _PLAY, _TO_HAND
from common.strategy.refresh import fresh_cards, net_change, opponent_shuffles, refresh_branches


# STRIP and GIFT are one leg split by SIGN, never two live terms: both read the single signed `opp_net`, so a
# one-sided refresh (Lillie's, Lacey) zeroes it outright and leaves `CYCLE − SHED`.
_REFRESH_CYCLE = 20        # the DRAW side, flat: cards I have not seen are only as good as what the deck can
                           # still supply. Bounded and flat so the `hold-*-dont-shuffle` guards can cancel it.

# The OPPONENT-HAND rates stay FLAT: grading them needs a WORTH for cards we cannot see, and 59.4% of an
# opponent rep build prices `role_value` 0. Issue #395's role sheet is an ORDINAL over IN-PLAY bodies, not that.
_REFRESH_OPPONENT_HAND_STRIP = 4   # per card stripped from THEIR hand — certain denial.

_REFRESH_OPPONENT_HAND_GIFT = 8    # per card HANDED to them. The 4-vs-8 ratio is the denial haircut: denying
                           # them a card is worth about half handing them one, because they redraw into a fresh one.

_REFRESH_OPPONENT_HAND_FRESH = 2   # per stripped card THEY DREW LAST TURN — live resources denied, versus cards
                           # they have demonstrably been unable to play.

# The discard equation's engine-supporter keep floor. `heal`/`clutch_heal` are DELIBERATELY OUT: a heal
# Supporter is RECOVERY, not card advantage, and takes general worth instead of this shared engine slot.
_ENGINE_KEEP_TAGS = frozenset({"draw", "search", "dig"})

_ENGINE_SUPPORTER_KEEP = 8.0     # discard-CONTEXT worth, not general worth: sized to the −8 band of
                                 # the discard-keep rung it replaced (ADR-0065 seam-D)


class HandMixin:
    """Refresh swing, forced-discard shed and hand-size relief."""

    def _is_simultaneous_draw(self, board: Board, attack_id, opp_active_prize: int) -> bool:
        """Is a game-winning KO with this attack actually a DRAW (ADR-0022 #2) — its UNCONDITIONAL recoil also
        KOs my Active and hands them their LAST prize at the same Checkup? Conservative; needs both counts."""
        mp, op = board.my_prizes_remaining, board.opp_prizes_remaining
        if mp <= 0 or op <= 0:
            return False
        if opp_active_prize < mp:                            # this KO doesn't take my last prize -> not lethal
            return False
        recoil = self.combat.rider_recoil(attack_id)
        if not board.my_active_hp or recoil < board.my_active_hp:   # recoil doesn't self-KO my Active
            return False
        my_prize = self._prize_value({"id": board.my_active_id})
        return my_prize >= op                                # my self-KO gives them their last prize too

    def _stranded_evolution_set(self) -> frozenset:
        """Deck ids that can NEVER be deployed from hand here — `common.playability` (ADR-0104) with the
        decklist as the reachable zone. Memoised; empty without stats (no card called dead on no facts)."""
        cached = getattr(self, "_stranded_cache", None)
        if cached is not None:
            return cached
        if not self.stats:
            self._stranded_cache = frozenset()     # no facts, no card called dead
            return self._stranded_cache
        from common import playability
        deck_ids = set(self.deck or ())
        zones = playability.zones(self.stats, deck_ids=deck_ids,
                                  rare_candy_reachable=self._rare_candy_reachable(deck_ids))
        self._stranded_cache = frozenset(
            cid for cid in deck_ids
            if (st := self.stats.get(cid)) is not None and st.evolvesFrom
            and not playability.playable_from_hand(cid, stats=self.stats, zones=zones))
        return self._stranded_cache

    def _refresh_swing_tactical(self, obs: dict, board: Board, ctx) -> float:
        """Card-flow benefit of a PLAY: deterministic fetch value plus any refresh swing."""
        if ctx.option_type != _PLAY:
            return 0.0
        return self._fetch_play_value(obs, board, ctx) + self._refresh_swing(obs, board, ctx)

    def _refresh_swing(self, obs: dict, board: Board, ctx) -> float:
        """``CYCLE − SHED + STRIP + FRESH − GIFT`` for ``ctx.card_id``; 0.0 off a known refresh. The PLAY and
        GRAB sites read the SAME number (ADR-0122) — a played Supporter is discarded, not shuffled."""
        nets = net_change(ctx.card_id, my_hand=board.my_hand_size, opp_hand=board.opp_hand_size,
                          my_prizes_remaining=board.my_prizes_remaining,
                          opp_prizes_remaining=board.opp_prizes_remaining)
        if nets is None:
            return 0.0
        _my_net, opp_net = nets
        stripped = max(-opp_net, 0.0)
        fresh = fresh_cards(ctx.card_id, board.opp_hand_size, board.opp_hand_size_delta)
        return (_REFRESH_CYCLE
                - self._refresh_shed_keepcost(obs, board, ctx)
                + _REFRESH_OPPONENT_HAND_STRIP * stripped
                + (_REFRESH_OPPONENT_HAND_FRESH * fresh if stripped > 0 else 0.0)
                - _REFRESH_OPPONENT_HAND_GIFT * max(opp_net, 0.0))

    def _hand_size_relief_tactical(self, obs: dict, board: Board, ctx) -> float:
        """The survival a hand REFRESH buys me or hands them (**ADR-0102**): Δ`turns_to_ko_me` over BOTH hands
        the card leaves. No card-fact gate — the clock is the authority; `UNCHARGED`, since the CEILING fails CLOSED."""
        from common import needs
        from common.currency import prize_to_damage
        if ctx.option_type != _PLAY or not self.stats:
            return 0.0
        branches = refresh_branches(ctx.card_id, board.my_prizes_remaining,
                                    board.opp_prizes_remaining)
        model, now_ctx = self._state_model, self._opp_attack_context
        if branches is None or model is None or not now_ctx:
            return 0.0
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) else {}
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        ma = next((p for p in ((me or {}).get("active") or []) if p), None)
        if not (ma and opp):
            return 0.0
        # The two redraw counts, averaged over the card's coin branches exactly as `net_change` averages its
        # own. Their hand moves only if the card shuffles it — the `opponent_shuffles` discriminator.
        after = dict(now_ctx, def_hand=sum(m for m, _o in branches) / len(branches))
        if opponent_shuffles(ctx.card_id):
            after["atk_hand"] = sum(o for _m, o in branches) / len(branches)
        if after == now_ctx:
            return 0.0                      # the card moves no hand on this board: nothing to price
        clock = dict(charged=UNCHARGED,
                     opp_active=next((p for p in (opp.get("active") or []) if p), None),
                     switch_enabler=self._opp_switch_enabler())
        shift = (model.theirs.turns_to_ko_me(ma, context=after, **clock)
                 - model.theirs.turns_to_ko_me(ma, context=now_ctx, **clock))
        if not shift:
            return 0.0
        phase = needs.phase_scale(race_ahead=getattr(board, "race_ahead", None),
                                  opp_prizes_remaining=board.opp_prizes_remaining)
        return prize_to_damage(needs.survival_value(survival_shift=shift, phase=phase))

    def _grab_refresh_value(self, obs: dict, board: Board, ctx) -> float:
        """Value of a TO_HAND grab, with an immediate draw Supporter's realised swing as a floor."""
        if ctx.select_context != _TO_HAND:
            return 0.0
        grab = max(self._grab_value_of(board, ctx.card_id, ctx.plan, obs=obs),
                   float(ctx.card_chain_value or 0.0))
        if (board.line_ready or "draw" not in ctx.tags
                or not (ctx.stat and getattr(ctx.stat, "is_supporter", False))):
            return grab
        swing = self._refresh_swing(obs, board, ctx)
        if (obs.get("current") or {}).get("supporterPlayed"):
            swing *= _halve(1)
        return max(grab, swing)

    def _refresh_shed_keepcost(self, obs: dict, board: Board, ctx) -> float:
        """The graded SHED (ADR-0101): ``set_keep_v2`` over every held row. **Sets, not sums** — a refresh sheds
        the hand JOINTLY. Unresolved bookkeeping leaves resupply 0, so the shed gets DEARER rather than free."""
        from common import needs
        from common.strategy.refresh import refresh_branches
        branches = refresh_branches(ctx.card_id, board.my_prizes_remaining, board.opp_prizes_remaining)
        if not branches:
            return 0.0
        draws = max(my_draw for my_draw, _opp in branches)
        rows = self._needs_hand_rows(obs, board, exclude_cid=ctx.card_id)
        if not rows:
            return 0.0
        resolved = self._resolve_needs(obs, board, rows)
        slots, elig = resolved
        resupply = self._refresh_slot_resupply(slots, elig, rows, obs, board, draws)
        return needs.set_keep_v2(slots, elig, resupply, range(len(rows)),
                                 edge_values=resolved.edge_values)

    def _discard_fuel_types(self) -> frozenset:
        """Energy types a DISCARD-SOURCE accel attack in this deck wants IN the discard (``None`` in the set =
        any Basic) — so pitching a matching Basic is FUEL, not loss. Memoised; empty without stats/deck."""
        if self._discard_fuel_cache is None:
            types = set()
            for cid in set(self.deck):
                st = self.stats.get(cid) if self.stats else None
                for aid in (getattr(st, "attacks", None) or ()):
                    ast = self._attack_stat(aid)
                    if (ast is not None and getattr(ast, "recoverN", 0)
                            and getattr(ast, "recoverSource", None) == "discard"):
                        types.add(getattr(ast, "recoverEnergyType", None))
            self._discard_fuel_cache = frozenset(types)
        return self._discard_fuel_cache

    def _discard_equation_rows(self, obs: dict, select: dict, board: Board, options: list):
        """The per-candidate priced rows `_needs_v2` consumes, plus the gates/fuel/burst flags the gust and
        refresh keep-value sites read off the same computation. Pure and deterministic (safe mid-sim)."""
        me = self._my_player(obs)
        from collections import Counter
        hand_ids = [c.get("id") for c in (me.get("hand") or []) if c and c.get("id") is not None]
        held = Counter(hand_ids)
        counts = self._unseen_deck_counts(me, board)
        from common import fetch_closure
        def _recyclers(stat):
            in_hand = in_deck = 0
            for rid, n in held.items():
                if any(cl.get("kind") == "fetch" and cl.get("zone") == "discard"
                       and fetch_closure.fetch_target_matches(cl, stat)
                       for cl in (self.effects.clauses(rid) if self.effects else ())):
                    in_hand += n
            for rid, n in counts.items():
                if n > 0 and any(cl.get("kind") == "fetch" and cl.get("zone") == "discard"
                                 and fetch_closure.fetch_target_matches(cl, stat)
                                 for cl in (self.effects.clauses(rid) if self.effects else ())):
                    in_deck += n
            return in_hand, in_deck
        fuel_types = self._discard_fuel_types()
        rows = []
        for i, o in enumerate(options):
            cid = self._option_card_id(obs, select, o)
            if cid is None:
                continue
            st = self.stats.get(cid) if self.stats else None
            tags = self.functions.tags(cid) if (self.functions and cid is not None) else ()
            worth = self._role_value(cid)
            # A WORTH floor, not a keep floor: a draw/search/dig SUPPORTER that is NOT hand_disruption is a
            # draw engine, still discounted by re-access and by the gates, unlike a hard override.
            engine_supporter = bool(st is not None and getattr(st, "is_supporter", False)
                                    and (_ENGINE_KEEP_TAGS & set(tags)) and "hand_disruption" not in tags)
            if engine_supporter and worth < _ENGINE_SUPPORTER_KEEP:
                worth = _ENGINE_SUPPORTER_KEEP
            # The marker describes the card's job, not whether this local floor happened to
            # increase its Worth.  Shared function Worth can already put a draw Supporter at the
            # same band, but discard diagnostics and downstream policy still need to distinguish
            # the engine from a disruption card at that band.
            row_engine = engine_supporter
            row = {"i": i, "cid": cid, "worth": round(worth, 1)}
            if row_engine:
                row["engine_supporter"] = True
            dup = held.get(cid, 0) >= 2
            in_play = cid in board.in_play_ids
            rec_hand, rec_deck = _recyclers(st) if (st is not None and worth > 0) else (0, 0)
            fuel = bool(st is not None and getattr(st, "is_basic_energy", False)
                        and (None in fuel_types
                             or getattr(st, "energyType", None) in fuel_types))
            deploy = self._deploy_odds(cid, board, counts)
            if dup:
                row["dup_hand"] = True
            if in_play:
                row["in_play"] = True
            if rec_hand:
                row["recycler"] = rec_hand
            if rec_deck:
                row["recycler_deck"] = rec_deck
            if fuel:
                row["fuel"] = True
            if deploy != 1.0:
                row["deploy"] = deploy
            # The DEPLOY-NOW closing edge: an in-play same-card copy does NOT cover THIS body's this-turn
            # evolution, so re-access is not bankable — zero the credit and the card charges FULL worth.
            closing = self._gate_closing(cid, board)
            if closing:
                row["closing"] = True
            reaccess = 0.0 if closing else (1.0 if (dup or in_play or rec_hand) else 0.0)
            # A SPENT burst: a `discard_eot` Energy is precious until the Active is fully powered — then it
            # self-discards anyway, so it is fodder. DISCARD-CONTEXT, hence the pitch term, not a Worth gate.
            spent_burst = "discard_eot" in tags and getattr(board, "active_fully_powered", False)
            row["keep"] = 0.0 if (fuel or spent_burst) else round(worth * deploy * (1.0 - reaccess), 1)
            self._apply_pitch_terms(row, cid, tags, board, fuel=fuel, spent_burst=spent_burst)
            rows.append(row)
        return rows

    def _apply_pitch_terms(self, row: dict, cid, tags, board, *, fuel: bool, spent_burst: bool):
        """Write the PITCH term and its flags onto a priced row, in place (ADR-0106). ``deadness`` is a BIT, not
        a count; ``fuel`` stays out of it — `needs.pitch_gain` prices that already, and ranking on it double-counts."""
        roles = self._roles_of(cid)
        dead_opener = "opener" in tags
        redundant_tutor = bool(getattr(board, "wincon_in_hand", False)
                               and ({"rush_evolve", "tutor_mega"} & set(tags)))
        stranded = cid in self._stranded_evolution_set()
        fodder = "discard_fodder" in roles
        if dead_opener:
            row["dead_opener"] = True
        if redundant_tutor:
            row["redundant_tutor"] = True
        if stranded:
            row["stranded"] = True
        if fodder:
            row["fodder"] = True
        if spent_burst:
            row["spent_burst"] = True
        expired = (dead_opener, redundant_tutor, stranded, fodder, spent_burst)
        row["deadness"] = int(any(expired))                     # CATEGORICAL: dead, or not
        row["pitch"] = int(fuel) + sum(int(b) for b in expired)  # the COUNT, unchanged

    @staticmethod
    def _removal_ranking_legs(rows: list) -> dict:
        """The two ORDERING legs `needs.cheapest_removal` ranks equal-cost removals by, ready to splat. ONE
        spelling, because the discard DECIDER and the shed PREDICTOR need the SAME order, not the same idea."""
        return {"deadness": [r.get("deadness", 0) for r in rows],
                "tiebreak": [r.get("worth", 0.0) * r.get("deploy", 1.0) for r in rows]}

    def _cost_shed(self, obs: dict, board: Board = None, *, exclude_cid=None, picks: int,
                   eligible_hand_indices=None):
        """**The ONE answer to "which cards does a `picks`-card cost actually take?"** — `needs.cheapest_removal`,
        the equation that already DECIDES the forced discard. NOT `keep_v2`: measured worse, reverted (ADR-0121)."""
        from common import needs
        board = self._board_hypothetical(obs) if board is None else board
        rows = self._as_discard_rows(self._needs_hand_rows(obs, board, exclude_cid=exclude_cid),
                                     obs, board)
        if len(rows) < int(picks):
            return None
        resolved = self._resolve_needs(obs, board, rows)
        slots, elig = resolved
        resupply = [0.0] * len(slots)            # a forced discard has no redraw window (as `_needs_v2`)
        intrinsics = [0.0] * len(rows)           # no v1 post-gate hedge exists over the HAND rows
        candidates = None if eligible_hand_indices is None else tuple(
            i for i, row in enumerate(rows) if row["hand_i"] in eligible_hand_indices)
        pick = needs.cheapest_removal(slots, elig, resupply, intrinsics, int(picks),
                                      candidates=candidates, edge_values=resolved.edge_values,
                                      **self._removal_ranking_legs(rows))
        if len(pick) != int(picks):
            return None
        cost = needs.removal_score(slots, elig, resupply, intrinsics, pick,
                                   edge_values=resolved.edge_values)
        # `hand_i`, NOT `i`. The rows drop one copy of `exclude_cid`, so a row ordinal is short of the true
        # hand position for every card after it — reading `i` collides the picks with the played card's index.
        return ShedPlan(hand_indices=tuple(sorted(rows[k]["hand_i"] for k in pick)),
                        row_indices=tuple(pick), rows=rows, cost=float(cost))

    def cost_shed_indices(self, model, option: dict, picks: int,
                          eligible_hand_indices=None) -> tuple:
        """The `shed` seam `board_expectation.expectation` takes. Model-shaped because the apply seam has no
        Pilot; its CALLER passes this in. ``()`` when the hand cannot pay — the seam reads that as a refusal."""
        obs = getattr(model, "source_obs", None) or {}
        seat = int(getattr(model, "my_index", 0))
        hand = ((obs.get("current") or {}).get("players") or [{}])[seat].get("hand") or ()
        index = (option or {}).get("index")
        played = ((hand[index] or {}).get("id")
                  if (option or {}).get("type") == _PLAY and isinstance(index, int)
                  and 0 <= index < len(hand) else None)
        plan = self._cost_shed(obs, exclude_cid=played, picks=picks,
                               eligible_hand_indices=eligible_hand_indices)
        return plan.hand_indices if plan is not None else ()

    def _as_discard_rows(self, rows: list, obs: dict, board: Board) -> list:
        """`_needs_hand_rows` output re-read in DISCARD context, on copies. Separate because `_resolve_needs`
        READS the pitch terms — writing them in the builder makes a refresh SHED price its hand as a discard."""
        from collections import Counter
        held = Counter(r["cid"] for r in rows)
        out = []
        for r in rows:
            cid = r["cid"]
            tags = self.functions.tags(cid) if (self.functions and cid is not None) else ()
            row = dict(r)
            if held.get(cid, 0) >= 2:
                row["dup_hand"] = True
            if cid in board.in_play_ids:
                row["in_play"] = True
            self._apply_pitch_terms(
                row, cid, tags, board, fuel=bool(r.get("fuel")),
                spent_burst="discard_eot" in tags and getattr(board, "active_fully_powered", False))
            out.append(row)
        return out

    def _refresh_slot_resupply(self, slots, elig, rows, obs: dict, board: Board,
                               draws: int) -> list:
        """P(the closure re-supplies each slot inside the refresh's ``draws`` window). Fail directions all toward
        KEEP; ``general`` stays 0.0 because `_GENERAL_WORTH_W` was measured AT r=0 — re-open W and r jointly."""
        from common import fetch_closure
        from common.deck_odds import draw_hit_probability
        out = [0.0] * len(slots)
        me = self._my_player(obs)
        counts = board.deck_known_counts
        if counts:
            deck_count = sum(counts.values())
            prizes_hidden = 0                                    # anchored: the split is resolved
        else:
            from collections import Counter
            unseen = Counter(self.deck)
            unseen.subtract(self._visible_card_counts(me))
            counts = {cid: n for cid, n in unseen.items() if n > 0}
            prizes_hidden = sum(1 for p in (me.get("prize") or [])
                                if not (isinstance(p, dict) and p.get("id") is not None))
            deck_count = sum(counts.values()) - prizes_hidden
            if deck_count <= 0 or not counts:
                return out
        pool = deck_count + len(rows)                            # the shuffle-grown pool: rows ARE
        members: list = [[] for _ in slots]                      # the shuffled copies (refresh excluded)
        for k, js in enumerate(elig):
            for j in js:
                members[j].append(k)
        for j, s in enumerate(slots):
            if (s.supplied_by_pitch or s.kind in ("deploy_now", "answer_doom", "general")
                    or (s.kind in ("deny", "line") and s.deadline <= 0) or not members[j]):
                continue                       # closing edge: a THIS-TURN deadline can't bank re-access
            classes = {rows[k]["cid"] for k in members[j]}
            u = fetch_closure.class_reaccess_outs(classes, counts, self._closure_stat_of,
                                                  self._closure_clauses_of)
            certain = len(members[j])
            if s.kind == "fund_attack":
                window = draws + s.deadline
            elif s.kind == "line":
                window = min(draws, s.deadline)
            else:
                window = draws
            if prizes_hidden > 0:
                r = self._prize_split_hit(u, deck_count, prizes_hidden, pool, window,
                                          certain=certain)
            else:
                r = draw_hit_probability(u + certain, pool, window)
            out[j] = max(0.0, min(1.0, r))
        return out
