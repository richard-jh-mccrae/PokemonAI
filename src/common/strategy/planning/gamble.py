"""The GAMBLE line: a KO that needs a card we do not hold, priced by the odds of finding it.

`value x P(hit)` against the deterministic baseline — so a gamble commits only when it beats what is already certain,
and the odds come from the deck tracker's real counts rather than from a guess at what is left."""
from __future__ import annotations


from common import playability
from common.strategy.context import KO_SCORE, _PLAY
from common.strategy.planning.turn_line import TurnLine


_PLANNER_ENABLER_ITEM_SLOT = 6.0  # an Item enabler's credit WHEN it preserves the one-per-turn Supporter
                               # slot for a competing Supporter in hand; below a free direct-evolve (8)

_PLANNER_ENABLER_ITEM_BASE = 2.0  # the same credit with NO Supporter competing. All three (free 8 /
                               # item 6|2 / supporter 0) are sub-prize: a same-KO tiebreak, never a reorder


class GambleMixin:
    """Probabilistic KO lines, priced against the certain alternative."""

    def _best_gamble_line(self, obs, select, board, options, traces):
        """The best **Gamble Line** on this menu, or None: play a Hand Refresh FIRST because the draw
        probably yields the enabler this turn's KO needs (ADR-0039). Working on `_gamble_trace`."""
        def stand_down(why):
            if not self._planning:
                self._gamble_trace = {"considered": False, "why": why}
            return None
        if self._planning:
            return None                             # mid engine-sim: silent, never clobber the trace
        if not getattr(self, "gamble_lines", False):
            return stand_down("feature off (gamble_lines)")
        if board.turn <= 1:
            return stand_down("turn 1")
        if board.energy_attached:
            return stand_down("attach already spent this turn")
        if board.active_can_ko:
            return stand_down("active already reaches a KO")
        if any(t.tactical >= KO_SCORE for t in traces):
            return stand_down("a KO is already on the tuned menu")
        # the binary protected-hand stand-downs are REPLACED by the graded keep-cost priced in below
        from common.strategy.doctrines.doctrine_shuffle_refresh import _draw_branches
        me = self._my_player(obs)
        hand = [c for c in (me.get("hand") or []) if c and c.get("id") is not None]
        hand_ids = [c.get("id") for c in hand]                # WP6: for the shuffle keep-cost
        ma = next((p for p in (me.get("active") or []) if p), None)
        opp = self._opp_active(obs)
        hp = (opp or {}).get("hp", 0)
        stat = self.stats.get(board.my_active_id) if (self.stats and board.my_active_id) else None
        if not (hp and stat and ma):
            return None
        discard_basic_types = {                               # WP1: Basic-Energy types in my visible
            st.energyType for c in (me.get("discard") or [])  # discard — the recycle closure's source
            if c and (st := self.stats.get(c.get("id"))) is not None
            and st.is_basic_energy and st.energyType is not None}
        # ANCHORED: exact deck counts, a plain window hypergeometric. PRE-ANCHOR: the decklist is known
        # and only the prize assignment is random, so price with the prize-split-weighted window sum.
        counts = board.deck_known_counts
        anchored = bool(counts)
        if anchored:
            class_counts = counts
            deck_count = sum(counts.values())
            prizes_hidden = 0
        else:
            from collections import Counter as _Counter
            unseen = _Counter(self.deck)
            unseen.subtract(self._visible_card_counts(me))    # copies provably outside deck+prizes
            class_counts = {cid: n for cid, n in unseen.items() if n > 0}
            prizes_hidden = sum(1 for p in (me.get("prize") or [])
                                if not (isinstance(p, dict) and p.get("id") is not None))
            deck_count = sum(class_counts.values()) - prizes_hidden   # hidden deck cards (H − prizes)
            if deck_count <= 0 or not class_counts:
                return stand_down("pre-anchor: deck bookkeeping unresolved")
        classes = self._gamble_ko_classes(board, stat, ma, opp, hp, class_counts, hand, discard_basic_types)
        classes = classes + self._gamble_evolution_ko_classes(obs, board, ma, opp, class_counts, hand)
        classes = classes + self._gamble_pump_ko_classes(obs, board, stat, ma, opp, hp, class_counts, hand)
        classes = classes + self._gamble_gust_ko_classes(obs, board, ma, self._opp_player(obs), hand,
                                                         class_counts)
        classes = classes + self._gamble_survival_classes(obs, board, me, class_counts, hand)
        if not classes:
            return stand_down("no one-enabler-short KO class on this board")
        det = self._gamble_det_baseline(board, stat, ma, opp, hp, traces, hand)
        pool = deck_count + max(0, len(hand) - 1)             # the shuffle-grown draw pool
        burst_copies = self._gamble_burst_copies(class_counts, hand, stat)   # the recovery class (below)
        from common.deck_odds import draw_hit_probability, draw_hit_with_engines
        if anchored:
            def hit(cp, n):
                return draw_hit_probability(cp, pool, n)
        else:
            def hit(cp, n):
                return self._prize_split_hit(cp, deck_count, prizes_hidden, pool, n)
        # per-class draw-engine windows; the class's own ids are EXCLUDED so a sought evolution that
        # is itself an engine never double-counts. ANCHORED-only: pre-anchor stays plain (under-count).
        class_engines = []
        for _c, _v, _l, sought, (_sc, sup_ids) in classes:
            if anchored:
                class_engines.append(self._gamble_draw_engines(
                    me, class_counts, set(sought) | set(sup_ids)))
            else:
                class_engines.append((0, (), []))
        best = None                                           # (ev, index, rationale)
        evals = []                                            # per (refresh option × class) working rows
        for i, o in enumerate(options):
            if o.get("type") != _PLAY:
                continue
            cid = self._option_card_id(obs, select, o)
            ns = _draw_branches(cid, board)
            if (ns is None or cid is None or not self.functions
                    or "shuffle_hand" not in self.functions.tags(cid)):
                continue
            # the Supporter-tutor supplement is live only for an ITEM refresh with the Supporter slot
            # unspent — a Supporter refresh spends it, so a drawn Supporter tutor is dead in ITS window
            rst = self.stats.get(cid) if self.stats else None
            sup_live = bool(rst is not None and getattr(rst, "is_item", False)
                            and not board.supporter_played)
            # the KEEP-COST of shuffling this hand away (the played refresh is discarded, not
            # shuffled): the gamble must beat det PLUS this graded floor
            hand_keep = self._hand_keep(hand_ids, cid, class_counts, pool, max(ns), board,
                                        prizes_hidden=prizes_hidden, deck_count=deck_count)
            # the refresh CHAIN: a drawn shuffle-refresh inside this window opens a fresh full window
            # at the same outs. Anchored-only, like the draw engines.
            ch_c, ch_w = (self._gamble_chain_refreshes(class_counts, sup_live, board)
                          if anchored else (0, 0))
            for (copies, ko_value, label, sought, (sup_copies, _sup_ids)), (e_cp, e_ws, _e_ids) \
                    in zip(classes, class_engines):
                eff = copies + (sup_copies if sup_live else 0)
                if e_cp:
                    # a missed refresh may still hit a draw engine digging the SAME outs, thinned pool
                    p = sum(draw_hit_with_engines(eff, pool, n, e_cp, e_ws) for n in ns) / len(ns)
                else:
                    p = sum(hit(eff, n) for n in ns) / len(ns)
                if ch_c and ch_w:
                    # the chain branch conditions on missing EVERY counted out and engine, so it is
                    # DISJOINT from the mass above — exactly additive. Chains inside chains: unmodeled.
                    boost = sum(max(0.0, draw_hit_probability(eff + e_cp + ch_c, pool, n)
                                    - draw_hit_probability(eff + e_cp, pool, n))
                                for n in ns) / len(ns)
                    p = min(1.0, p + boost * draw_hit_probability(copies, max(0, pool - 1), ch_w))
                ev = p * ko_value
                if burst_copies and det > 0:
                    # the RECOVERY class: the miss branch may still redraw the held burst Energy and
                    # bank the deterministic chip. Independence approximation — errs small, adds only.
                    p_re = sum(hit(burst_copies, n) for n in ns) / len(ns)
                    ev += (1 - p) * p_re * det
                row = {"i": i, "cid": cid, "draws": max(ns), "label": label,
                       "p": round(p, 3), "ev": round(ev, 1)}
                if sup_live and sup_copies:
                    row["post_item_sup"] = sup_copies         # the Item-refresh Supporter supplement
                if ch_c and ch_w:
                    row["chain_refresh"] = [ch_c, ch_w]       # drawn-refresh chain: copies, window
                if hand_keep:
                    row["keep"] = round(hand_keep, 1)         # WP6: the shuffled-hand keep-cost floor
                evals.append(row)
                bar = det + hand_keep                         # WP6: beat the held line + the keep-cost
                if ev > bar and (best is None or ev - hand_keep > best[0]):
                    best = (ev - hand_keep, i,
                            f"gamble: {p:.0%} the {max(ns)}-card draw finds {label} for the KO "
                            f"(EV {ev:.0f} > held line {det:.0f} + keep {hand_keep:.0f})")
        self._gamble_trace = {                     # the full working, win or stand-down (ADR-0019)
            "considered": True, "anchored": anchored, "prizes_hidden": prizes_hidden,
            "pool": pool, "det": round(det, 1), "burst": burst_copies,
            "classes": [{"label": la, "copies": c, "value": round(v, 1), "sought": s,
                         **({"post_item_sought": si, "post_item_copies": sc} if sc else {}),
                         **({"engine_copies": ec, "engine_windows": list(ew), "engine_ids": ei}
                            if ec else {})}
                        for (c, v, la, s, (sc, si)), (ec, ew, ei) in zip(classes, class_engines)],
            "evals": evals,
            "best": ([best[1], round(best[0], 1)] if best is not None else None)}
        if best is None:
            return None
        return TurnLine(next_step=[best[1]], goal="gamble", value=best[0], rationale=best[2])

    def _prize_split_hit(self, u: int, deck_count: int, prizes_hidden: int, pool: int, draws: int,
                         certain: int = 0) -> float:
        """P(≥1 enabler in the ``draws``-card refresh) PRE-ANCHOR: the ``u`` unseen copies split over
        deck and prizes. ``certain`` = outs known in the pool regardless. Bad input → 0.0, never raises."""
        from math import comb
        from common.deck_odds import draw_hit_probability
        try:
            u, d, k, certain = int(u), int(deck_count), int(prizes_hidden), int(certain)
        except Exception:
            return 0.0
        if u <= 0 or d <= 0:
            # no unseen outs to split (or no deck for them to sit in) — only the certain copies draw
            return draw_hit_probability(certain, pool, draws) if certain > 0 else 0.0
        if k <= 0:
            return draw_hit_probability(u + certain, pool, draws)   # no hidden prizes -> every copy in deck
        h = d + k
        u = min(u, h)                                          # can't split more copies than positions
        denom = comb(h, u)                                     # u ≤ h -> comb(h, u) > 0, no zero-div
        total = 0.0
        for j in range(max(0, u - k), min(u, d) + 1):          # j = enabler copies landing in the deck
            total += comb(d, j) * comb(k, u - j) / denom * draw_hit_probability(j + certain, pool, draws)
        return max(0.0, min(1.0, total))

    def _gamble_burst_copies(self, counts: dict, hand: list, stat) -> int:
        """Pool-wide copies (INCLUDING the returned hand copy) of a held `discard_eot` burst Energy
        that funds an attack of my Active by COUNT — the recovery-class enabler. 0 when none held."""
        best = 0
        for c in hand:
            cid = c.get("id")
            est = self.stats.get(cid) if (self.stats and cid is not None) else None
            if not est or getattr(est, "hp", 1) != 0:
                continue
            tags = self.functions.tags(cid) if self.functions else []
            if "discard_eot" not in tags:
                continue
            in_hand = sum(1 for c2 in hand if c2.get("id") == cid)
            best = max(best, counts.get(cid, 0) + in_hand)
        return best

    def _deploy_odds(self, cid, board, counts: dict) -> float:
        """The deadline gate (`common.gate_library`, ADR-0065): P(card ``cid``'s role is realisable by
        its deadline). Evolution / fetcher / need-met classes are gated; everything else stays 1.0."""
        from common import gate_library
        st = self.stats.get(cid) if (self.stats and cid is not None) else None
        if gate_library.is_evolution(st):
            return gate_library.deploy_odds(st, playable=playability.playable_from_hand(
                cid, stats=self.stats, zones=self._playability_zones(board, counts)))
        if st is not None and not st.is_pokemon and not st.is_energy:
            tags = self.functions.tags(cid) if self.functions else ()
            if ({"rush_evolve", "tutor_mega"} & set(tags)) and getattr(board, "wincon_in_hand", False):
                return gate_library.need_met_odds(need_met=True)   # wincon-tutor, wincon already in hand
            fetch_set = self._fetch_deadness_set(cid)
            empty = getattr(board, "deck_empty_ids", None) or frozenset()
            if fetch_set and all(t in empty for t in fetch_set):
                return gate_library.fetch_deploy_odds(targets_exhausted=True)
            if "recycle" in tags and getattr(board, "recycle_dead_only", False):
                return gate_library.fetch_deploy_odds(targets_exhausted=True)
        return 1.0

    def _slot_basic_in_zone(self, want, lock, zone: str, counts: dict, discard_basic_types: set) -> bool:
        """A Basic Energy filling slot ``want`` (``None`` = colourless: any Basic) and passing the
        fetch's type ``lock`` is still available in ``zone`` — the deck or the visible discard."""
        if lock is not None and want is not None and lock != want:
            return False                                      # a type-locked fetch can't supply this slot

        def _ok(et) -> bool:
            if et is None:
                return False
            if want is not None and et != want:               # a specific slot needs its exact type
                return False
            return lock is None or et == lock                 # a locked fetch only finds its lock type

        if zone == "deck":
            return any((st := self.stats.get(c)) is not None and st.is_basic_energy
                       and _ok(getattr(st, "energyType", None))
                       for c, n in counts.items() if n > 0)
        if zone == "discard":
            return any(_ok(et) for et in discard_basic_types)
        return False

    def _fetch_reaches_slot(self, want, cid: int, counts: dict, discard_basic_types: set) -> bool:
        """True iff card ``cid``'s FETCH clauses (`card_effects.json`, ADR-0032) can put a Basic Energy
        filling slot ``want`` into hand, its target still reachable. Non-decidable clauses are skipped."""
        from common.fetch_closure import fetch_is_unconditional
        return any(cl.get("kind") == "fetch" and cl.get("target") == "basic_energy"
                   and fetch_is_unconditional(cl)
                   and self._slot_basic_in_zone(want, cl.get("energy_type"), cl.get("zone"),
                                                counts, discard_basic_types)
                   for cl in (self.effects.clauses(cid) if self.effects else ()))

    def _supporter_energy_tutor_reaches(self, tid, want, counts: dict, discard_basic_types: set) -> bool:
        """True iff Supporter ``tid`` can put a slot-filling Energy in hand or attach it — a deck
        fetch, an unconditional accel, or the trainer-fetch 2-hop. LIVE only with the slot unspent."""
        from common.fetch_closure import fetch_is_unconditional
        st = self.stats.get(tid) if self.stats else None
        if st is None or not st.is_supporter:
            return False
        for cl in (self.effects.clauses(tid) if self.effects else ()):
            kind = cl.get("kind")
            if kind == "fetch" and not fetch_is_unconditional(cl):
                continue
            if (kind == "fetch" and cl.get("zone") == "deck"
                    and cl.get("target") in ("basic_energy", "energy")):
                if self._slot_basic_in_zone(want, cl.get("energy_type"), "deck",
                                            counts, discard_basic_types):
                    return True
            elif kind == "accel" and cl.get("energy") == "basic" and not cl.get("condition"):
                if self._slot_basic_in_zone(want, None, cl.get("source"),
                                            counts, discard_basic_types):
                    return True
            elif kind == "fetch" and cl.get("zone") == "deck" and cl.get("target") == "trainer":
                if any(n > 0 and (ist := self.stats.get(t)) is not None and ist.is_item
                       and self._fetch_reaches_slot(want, t, counts, discard_basic_types)
                       for t, n in counts.items()):
                    return True
        return False

    def _gamble_chain_refreshes(self, counts: dict, sup_live: bool, board) -> tuple:
        """USABLE shuffle-refresh copies still in my DECK whose draw opens a fresh window inside this
        one — ``(copies, min_window)``; ``(0, 0)`` when none. Under-counts: no chains inside chains."""
        from common.strategy.refresh import own_draw_count
        copies, window = 0, None
        for tid, n in counts.items():
            if n <= 0 or not self.functions or "shuffle_hand" not in self.functions.tags(tid):
                continue
            st = self.stats.get(tid) if self.stats else None
            if st is None:
                continue
            draw_conditions = [clause.get("condition") for clause in self.effects.clauses(tid)
                               if clause.get("kind") == "draw"] if self.effects else []
            if not draw_conditions or not any(self._condition_holds(condition, board)
                                              for condition in draw_conditions):
                continue
            if getattr(st, "is_supporter", False):
                if not sup_live:
                    continue
            elif not getattr(st, "is_item", False):
                continue
            w = own_draw_count(tid, board.my_prizes_remaining, board.opp_prizes_remaining)
            if not w or w <= 0:
                continue
            copies += n
            window = int(w) if window is None else min(window, int(w))
        return (copies, window or 0)

    def _gamble_draw_engines(self, me: dict, counts: dict, exclude: set) -> tuple:
        """The refresh window's usable DRAW ENGINES — ``(engine_copies, stage_windows, engine_ids)``
        for `deck_odds.draw_hit_with_engines`. ``exclude`` drops ids the class already counts."""
        bases: dict = {}                                      # base name -> eligible bodies on board
        for b in ((me.get("active") or []) + (me.get("bench") or [])):
            if not b or b.get("appearThisTurn"):
                continue
            st = self.stats.get(b.get("id")) if self.stats else None
            nm = getattr(st, "name", None)
            if nm:
                bases[nm] = bases.get(nm, 0) + 1
        ids, copies_total, activations, min_window = [], 0, 0, None
        for eid, n in counts.items():
            if n <= 0 or eid in exclude:
                continue
            st = self.stats.get(eid) if self.stats else None
            base = getattr(st, "evolvesFrom", None) if st else None
            if not base or not bases.get(base):
                continue
            for cl in (self.effects.clauses(eid) if self.effects else ()):
                if cl.get("kind") == "draw" and cl.get("condition") == "once_per_turn_ability":
                    window = int(cl.get("window") or cl.get("amount") or 0)
                    if window <= 0:
                        break
                    ids.append(eid)
                    copies_total += n
                    activations += min(n, bases[base])
                    min_window = window if min_window is None else min(min_window, window)
                    break
        if not ids or not activations:
            return 0, (), []
        return copies_total, (min_window,) * activations, sorted(ids)

    def _supporter_evolution_tutor_reaches(self, tid, eid, counts: dict) -> bool:
        """True iff Supporter ``tid`` can deliver the evolution ``eid`` — a deck fetch reaching it, or
        the trainer-fetch 2-hop. Live only post-Item-refresh (the caller gates on the Supporter slot)."""
        from common.fetch_closure import fetch_is_unconditional
        st = self.stats.get(tid) if self.stats else None
        if st is None or not st.is_supporter:
            return False
        if self._fetch_reaches_pokemon(eid, tid, counts):
            return True
        return any(cl.get("kind") == "fetch" and cl.get("zone") == "deck"
                   and cl.get("target") == "trainer" and fetch_is_unconditional(cl)
                   and any(n > 0 and (ist := self.stats.get(t)) is not None and ist.is_item
                           and self._fetch_reaches_pokemon(eid, t, counts)
                           for t, n in counts.items())
                   for cl in (self.effects.clauses(tid) if self.effects else ()))

    def _fetch_reaches_pokemon(self, target_id: int, cid: int, counts: dict) -> bool:
        """True iff card ``cid``'s ``zone: deck`` FETCH clauses can pull the Pokémon ``target_id``
        (still in ``counts``). Delegates to the shared `common.fetch_closure` graph (ADR-0065)."""
        from common import fetch_closure
        return fetch_closure.fetch_reaches_pokemon(
            target_id, cid, counts, self._closure_stat_of, self._closure_clauses_of)

    def _whiff_odds(self, board, body) -> float:
        """P(the opponent still holds ≥1 copy of ``body``'s line). Lower = the whiff-maximising
        target; fails OPEN to 1.0 without an Opponent Model, so the tiebreak silently no-ops."""
        opp_model = getattr(board, "opponent", None)
        if opp_model is None:
            return 1.0
        try:
            return float(opp_model.copies_left_odds((body or {}).get("id")))
        except Exception:
            return 1.0

    def _composed_budget(self, card_id, *, benched: bool, supporter_spent: bool = False):
        """The Attach Budget toward one KO line's attacker, or None without a model. ``supporter_spent``
        closes the Supporter leg for a line that plays a Supporter as its own step (ADR-0075)."""
        model = self._state_model
        if model is None or card_id is None:
            return None
        return model.mine.attach_budget_for_card(card_id, benched=benched,
                                                 supporter_spent=supporter_spent)

    def _composed_attack_p(self, card_id, body, *, benched: bool, supporter_spent: bool = False):
        """``attack_id -> P(the composed line's Energy is really there)``, or None when nothing can be
        priced — the caller then makes no claim. The RANKED half of ADR-0074's Leg Assignment."""
        budget = self._composed_budget(card_id, benched=benched, supporter_spent=supporter_spent)
        model = self._state_model
        if budget is None or model is None:
            return None
        p_by_type = model.mine.deck_energy_p
        if not p_by_type:
            return None
        return lambda aid: self.combat.attack_realising_p(
            aid, budget=budget, body=body, p_by_type=p_by_type)

    def _composed_line_p(self, obs, board, opp, card_id, energy: int, body, attack_p,
                         budget=None) -> float:
        """P(the composed line's KO really lands) — read back off the weighted/unweighted valuations,
        so the weight stays tied to the line the ranker committed to (ADR-0074). 1.0 with no price."""
        if attack_p is None:
            return 1.0
        raw = self._best_affordable_ko_value(obs, board, opp, card_id, energy,
                                             bound="min", body=body, budget=budget)
        if raw <= 0:
            return 0.0
        weighted = self._best_affordable_ko_value(obs, board, opp, card_id, energy,
                                                  bound="min", body=body, attack_p=attack_p,
                                                  budget=budget)
        return max(0.0, min(1.0, weighted / raw))

    def _ko_line_pricing(self, card_id, body, *, benched: bool, supporter_spent: bool = False):
        """``(budget, attack_p)`` for ONE KO line's attacker (ADR-0075 decision 4): ``card_id`` names
        the card whose ATTACKS are read; ``body`` is the on-board dict carrying the ATTACHED Energy."""
        budget = self._composed_budget(card_id, benched=benched, supporter_spent=supporter_spent)
        if budget is None:
            return None, None
        return budget, self._composed_attack_p(card_id, body, benched=benched,
                                               supporter_spent=supporter_spent)

    def _gamble_det_baseline(self, board, stat, ma, opp, hp: int, traces, hand: list) -> float:
        """The DETERMINISTIC baseline a gamble must beat: the best tactical already on the menu, or
        the best after-attach chip the HELD Energy reaches."""
        det = max((t.tactical for t in traces), default=0.0)
        hand_ids = frozenset(c.get("id") for c in hand)
        units = self._best_hand_attach_units(hand_ids, stat)
        energy_after = board.my_active_energy + units
        # extra_type=0: the held attach is priced as colourless, funding {C} slots only — the
        # conservative read (a held TYPED enabler voids the gamble class upstream anyway)
        return max(det, self._best_affordable_damage(board.my_active_id, energy_after, opp,
                                                     body=ma, extra_type=0, extra_units=units))

    def _closure_stat_of(self, cid):
        return self.stats.get(cid) if (self.stats and cid is not None) else None

    def _closure_clauses_of(self, cid):
        return self.effects.clauses(cid) if self.effects else ()

    def _card_reaccess_outs(self, cid, counts: dict) -> int:
        """The copies in my DECK that re-access ``cid`` once it is shuffled back in — the
        `common.fetch_closure` graph pointed BACKWARDS, one implementation for gain side and keep."""
        from common import fetch_closure
        return fetch_closure.reaccess_outs(cid, counts, self._closure_stat_of, self._closure_clauses_of)

    def _is_energy_tutor(self, obs, select, option) -> bool:
        """This PLAY option is a `tutor_energy` Trainer (Hilda class) — it searches an attachable
        Energy into hand, supplying the attach an enabling line lacks (the 4298 shape)."""
        cid = self._option_card_id(obs, select, option)
        return bool(cid is not None and self.functions and "tutor_energy" in self.functions.tags(cid))

    def _is_evolution_tutor(self, obs, select, option) -> bool:
        """This PLAY option is a `rush_evolve` Trainer (Salvatore class) — it evolves one of my in-play
        Pokémon straight from the deck, its own allowance making every in-play body a legal target."""
        cid = self._option_card_id(obs, select, option)
        return bool(cid is not None and self.functions and "rush_evolve" in self.functions.tags(cid))

    def _is_item_pokemon_tutor(self, obs, select, option) -> bool:
        """This PLAY option is an ITEM that fetches an evolution-form Pokémon into HAND (`tutor_mega`
        / `tutor_pokemon`). False when the card, its stat or its tags are unknown (fail-closed)."""
        cid = self._option_card_id(obs, select, option)
        if cid is None or not self.functions or not self.stats:
            return False
        stat = self.stats.get(cid)
        if stat is None or not getattr(stat, "is_item", False):
            return False
        tags = self.functions.tags(cid)
        return "tutor_mega" in tags or "tutor_pokemon" in tags

    def _is_rare_candy(self, obs, select, option) -> bool:
        """This PLAY option is Rare Candy — a Basic→Stage-2 evolve SKIP needing the Stage-2 already in
        hand. Matched by the `rare_candy` Function Tag; False without a tag table (fail-closed)."""
        cid = self._option_card_id(obs, select, option)
        return bool(self.functions and cid is not None
                    and playability.RARE_CANDY_TAG in set(self.functions.tags(cid)))

    def _item_enabler_cost(self, board) -> float:
        """The cost credit for an Item enabler: the WIDER ``_PLANNER_ENABLER_ITEM_SLOT`` only when a
        Supporter in hand actually wants this turn's slot, else ``_PLANNER_ENABLER_ITEM_BASE``."""
        competes = self._gust_supporter_in_hand(board) or not board.no_supporter_in_hand
        return _PLANNER_ENABLER_ITEM_SLOT if competes else _PLANNER_ENABLER_ITEM_BASE

    def _gust_supporter_in_hand(self, board) -> bool:
        """MY hand holds a `gust` Supporter — the sharpest claimant on this turn's one Supporter slot.
        False without stats/functions (fail-closed)."""
        if not (self.stats and self.functions):
            return False
        for cid in board.hand_ids:
            st = self.stats.get(cid)
            if st is not None and st.is_supporter and "gust" in self.functions.tags(cid):
                return True
        return False

    def _affords_snipe_ko(self, body_id, energy: int, target_hp: int) -> bool:
        """True iff ``body_id`` carrying ``energy`` can pay an attack whose unconditional bench-snipe
        rider (`combat.rider_snipe`) reaches ``target_hp`` — the exact snipe-KO test (no W/R on the Bench)."""
        stat = self.stats.get(body_id) if (self.stats and body_id is not None) else None
        if not (stat and target_hp):
            return False
        return any(self._attack_cost(aid) <= energy and self.combat.rider_snipe(aid) >= target_hp
                   for aid in (stat.attacks or ()))

    def _stage2_roots_at(self, stage2_stat, basic_name: str) -> bool:
        """The Stage-2's evolution chain roots at the Basic ``basic_name`` — the exact two-hop line Rare
        Candy skips, by name against the card data. False when the Stage-1 can't be resolved."""
        stage1_name = getattr(stage2_stat, "evolvesFrom", None)
        if not stage1_name:
            return False
        for s1_id in self.stats.ids_for_name(stage1_name):
            s1 = self.stats.get(s1_id)
            if s1 is not None and getattr(s1, "evolvesFrom", None) == basic_name:
                return True
        return False
