"""The GAMBLE line: a KO that needs a card we do not hold, priced by the odds of finding it.

`value x P(hit)` against the deterministic baseline — so a gamble commits only when it beats what is already certain,
and the odds come from the deck tracker's real counts rather than from a guess at what is left."""
from __future__ import annotations


from common import playability
from common.strategy.context import KO_SCORE, _PLAY
from common.strategy.planning.turn_line import TurnLine


_PLANNER_ENABLER_ITEM_SLOT = 6.0  # BUILD 4 (`enabler_item_composer`): an Item enabler's credit WHEN it
                               # preserves the scarce one-per-turn Supporter slot for a slot-competing
                               # Supporter in hand (a `gust` Boss's Orders / another high-value Supporter).
                               # Wider gap over the Supporter-tutor path (0) — the preservation is real —
                               # but still below a free direct-evolve (8): the Item spends a card.

_PLANNER_ENABLER_ITEM_BASE = 2.0  # BUILD 4: the SAME Item enabler's credit when NO Supporter competes for
                               # the slot — keeping it is worth little, so the gap shrinks toward the tutor.
                               # All three (free 8 / item 6|2 / supporter 0) stay sub-prize/sub-survival:
                               # they only break a same-KO tie among enablers, never outrank a genuine
                               # prize or survival delta (decision 3).


class GambleMixin:
    """Probabilistic KO lines, priced against the certain alternative."""

    def _best_gamble_line(self, obs, select, board, options, traces):
        """The best **Gamble Line** on this menu, or None: play a Hand Refresh (`shuffle_hand`)
        FIRST — before the turn's attach — because the draw probably yields the Energy that turns
        this turn into a KO the held hand cannot reach (the Lillie's-Determination class,
        ADR-0039/REQ-GAMBLE-0001).

        EV = P(enabling Outcome Class) × the enabled KO's tactical value, exact hypergeometric over
        the shuffle-grown pool (tracker-anchored counts + the returned hand); committed only when it
        beats the DETERMINISTIC baseline (the best menu tactical, or the best after-attach chip the
        held Energy reaches) — EV equality is the break-even, never a fixed threshold. Stands down:
        switch off / mid-sim (the engine re-run stays deterministic policy) / turn 1 / attach already
        spent / a KO already on the tuned menu / a protected hand (wincon, line piece, ACE-SPEC Tool
        — the keep-value floors own those shuffles) / pre-anchor (no exact counts, mirroring
        `dont-refresh-into-a-probable-miss`) / the hand already holds an enabler (just attach it).

        Records its full working — or WHY it stood down — on ``self._gamble_trace``, the sparse
        `gamble` block of Decision Telemetry (ADR-0019): the blunder shell shows it as a dropdown so
        a shuffle/fetch correction can see every number behind the (non-)gamble. Never recorded
        mid-sim (an engine re-run must not clobber the live decision's trace)."""
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
        # WP6: the binary protected-hand stand-downs (wincon / line pre-evo / ACE-SPEC Tool in hand)
        # are REPLACED by the graded keep-cost priced into the det baseline below — a wincon with its
        # tutors live shuffles cheap, an irreplaceable one-of near its full role value (the currency-
        # zone rule: replace the guard family, never bolt on beside it).
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
        # WP2 — the closure-COUNTS the classes are built over, and the window `hit` that prices them.
        # ANCHORED (prizes resolved): exact deck counts, a plain window hypergeometric. PRE-ANCHOR:
        # the decklist is still fully known (own deck) — only the prize assignment of unseen copies is
        # random, so build the classes over the unseen counts (`decklist − visible`) and price with the
        # prize-split-weighted window sum. The old `if not deck_known_counts: return None` priced EVERY
        # pre-anchor gamble at ZERO — the modeling-gap-as-caution failure the whole spec attacks.
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
        # WP4 — the Stage-2 draw-engine windows, per class (the class's own sought/supplement ids are
        # EXCLUDED so a Drakloak that is itself the sought evolution never double-counts). Engines are
        # an ANCHORED-only sharpening: pre-anchor the prize-split window stays plain (under-count,
        # never a guess about where the engine copies sit).
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
            # The Supporter-tutor supplement is live only for an ITEM refresh (Unfair Stamp) with the
            # one-per-turn Supporter slot unspent — a Supporter refresh spends the slot, so a drawn
            # Supporter tutor is dead in ITS window (spec §Missing, the 4-of-5 rule).
            rst = self.stats.get(cid) if self.stats else None
            sup_live = bool(rst is not None and getattr(rst, "is_item", False)
                            and not board.supporter_played)
            # WP6: the KEEP-COST of shuffling this refresh's hand away (the played refresh itself is
            # discarded, not shuffled) — Σ role value × (1 − re-access odds) over the shuffle redraw,
            # via the shared `_hand_keep` (duplicates priced marginally; one summation with the SHED).
            # The gamble must beat det PLUS this graded floor, replacing the binary protected-hand
            # stand-downs: a KO (≈ KO_SCORE) dwarfs it, an irreplaceable one-of raises the bar.
            hand_keep = self._hand_keep(hand_ids, cid, class_counts, pool, max(ns), board,
                                        prizes_hidden=prizes_hidden, deck_count=deck_count)
            # The refresh CHAIN (spec failure mode B, hand-expansion — built 2026-07-19): a drawn
            # shuffle-refresh inside this window is a fresh full window at the same outs — a drawn
            # Unfair Stamp (Item; live iff one of MY Pokémon was KO'd during their last turn) or a
            # drawn Supporter refresh (live only post-Item-refresh, the `sup_live` slot rule).
            # Anchored-only, like the draw engines (never a guess about where the copies sit).
            ch_c, ch_w = (self._gamble_chain_refreshes(class_counts, sup_live, board)
                          if anchored else (0, 0))
            for (copies, ko_value, label, sought, (sup_copies, _sup_ids)), (e_cp, e_ws, _e_ids) \
                    in zip(classes, class_engines):
                eff = copies + (sup_copies if sup_live else 0)
                if e_cp:
                    # WP4: the missed refresh may still hit a usable draw engine — its window digs
                    # the SAME class outs over the thinned pool (the two-window closed form).
                    p = sum(draw_hit_with_engines(eff, pool, n, e_cp, e_ws) for n in ns) / len(ns)
                else:
                    p = sum(hit(eff, n) for n in ns) / len(ns)
                if ch_c and ch_w:
                    # The chain branch conditions on missing EVERY counted out AND engine, so it is
                    # DISJOINT from the mass above — exactly additive (clamped for safety). Its
                    # fresh window prices the class's RAW copies (no Supporter supplement: a drawn
                    # Supporter refresh spends the slot; conservative for a drawn Stamp) over the
                    # re-shuffled pool (−1, the chain card itself is spent). Chains inside the
                    # chain are not modeled — an endorser under-counts.
                    boost = sum(max(0.0, draw_hit_probability(eff + e_cp + ch_c, pool, n)
                                    - draw_hit_probability(eff + e_cp, pool, n))
                                for n in ns) / len(ns)
                    p = min(1.0, p + boost * draw_hit_probability(copies, max(0, pool - 1), ch_w))
                ev = p * ko_value
                if burst_copies and det > 0:
                    # the RECOVERY class: the miss branch may still redraw the held burst Energy
                    # (returned to the pool by the shuffle) and bank the same after-attach chip the
                    # deterministic line held — the "no {W}, but the Ignition came back → Nebula
                    # anyway" branch. Independence approximation on the conditional (documented;
                    # errs small, and only ever ADDS honest EV to the miss side).
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
        """WP2: P(≥1 enabler in the ``draws``-card refresh) PRE-ANCHOR — the decklist is fully known,
        only the prize assignment of the class's ``u`` unseen enabler copies is random. Sum over
        ``j`` = copies-that-landed-in-the-deck of the hypergeometric prize-split weight × the window
        draw with ``j`` copies: ``Σ_j [C(deck,j)·C(prizes,u−j)/C(deck+prizes,u)] × hit(j, pool, n)``
        — ≤ ``u+1`` plain ``math.comb`` terms (``u ≤ 4`` in practice). The exact closed form the
        ``if not deck_known_counts: return None`` gate replaced with a zero (the modeling-gap-as-
        caution failure the fetch-closure spec attacks). Never raises; bad input → 0.0 (an endorser
        fails closed). Degenerates to the plain window draw when no prizes are hidden.

        ``certain`` = outs KNOWN to be in the drawn pool regardless of the split — the keep-cost
        side's own held copies, shuffled in from HAND (never prize-assignable). They join every
        branch's window draw (``hit(j + certain, …)``); the gain side passes the default 0."""
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
        """Copies (pool-wide, INCLUDING the returned hand copy) of a held `discard_eot` burst Energy
        that funds an attack of my Active by COUNT — the recovery-class enabler: a miss that redraws
        it re-banks the deterministic after-attach line. 0 when no such burst is held."""
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
        """The deadline gate (`common.gate_library`, ADR-0065): P(card ``cid``'s role is realisable
        by its deadline). Two card classes are gated today; everything else stays 1.0.

        **Evolution gate (Stage 1):** 1.0 for a playable evolution, 0.0 for a provably-unplayable
        one — nothing it can be put onto can reach the board. Errs toward 1.0 (keep): pre-anchor
        ``counts`` is the unseen deck, so a base still in the decklist keeps its evolution live —
        the gate bites only a genuinely dead card (ml ep83966336 f44: a Mega Lucario ex with every
        Riolu evolved/gone).

        That question is `common.playability`'s (ADR-0104), not this method's, and Issue #288 is why:
        the version inlined here compared ONE ``evolvesFrom`` name against the three zones, which
        gets two cases wrong. It called a Metagross live because a Metang sat in hand with every
        Beldum gone (the chain), and it called `grimmsnarl_ex`'s win condition DEAD whenever its
        Stage 1 was gone even with a Rare Candy in hand (the escape — card text at
        data/EN_Card_Data.csv id 1079). The eligibility gate in `pilot._resolve_needs` asks the same
        question, so the two must answer off one oracle or silently disagree about the same card.

        **Fetcher gate (searcher/recycler leg — acceptance pin ep83457493 f31):** a fetch TRAINER
        whose every target is provably dead — its deck whiff-set exhausted (`_fetch_deadness_set` ⊆
        `Board.deck_empty_ids`, the SOUND predicate behind `dont-search-an-empty-deck`) or its
        recycle pool all-dead (`Board.recycle_dead_only`, behind `dont-recycle-the-dead`) — realises
        no role, so it sheds freely instead of propping up the SHED at its tutor/recovery worth.
        Trainer-only: a Pokémon carrying a `recycle` tag (Kyogre) is a playable body regardless.

        **Need-met gate (the fetcher gate's cousin — ladder-win case ep82753102 f16):** a
        `rush_evolve` / `tutor_mega` WINCON-tutor whose wincon is already in hand
        (`Board.wincon_in_hand`) has its role SATISFIED — nothing left worth fetching — so it too
        collapses to 0. Fires live everywhere `keep_cost` is consumed (gamble keep-floor, refresh
        SHED), mirroring the ladder's `discard-the-redundant-tutor` premise as a Worth factor."""
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
        """A Basic Energy that FILLS the missing slot ``want`` (``None`` = colourless: any Basic) AND
        passes the fetch's type ``lock`` is still available in ``zone`` — the deck (``counts``) or the
        visible discard (``discard_basic_types``). The shared availability predicate behind the
        Item closure (`_fetch_reaches_slot`) and the post-Item-refresh Supporter closure."""
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
        """WP1: True iff card ``cid``'s **FETCH clauses** (``card_effects.json`` / ADR-0032 — the
        parametric tier a boolean Function Tag can't carry) can put a Basic Energy FILLING the missing
        slot ``want`` (``None`` = a colourless slot: any Basic) into hand, its target still reachable in
        the clause's source zone — a whole-deck search (``zone: deck``, a matching Basic still in
        ``counts``) or a recycle (``zone: discard``, a matching Basic type in the visible discard). The
        predicate lives in the card representation, NOT a card-text parse: Fighting Gong's ``{F}`` lock
        is its ``energy_type: 6`` clause, which the generic ``tutor_energy`` tag can't express. () for a
        card with no fetch clause. Errs by under-counting only (an endorser).

        A clause that is not an unconditional, decidable search (`fetch_closure.
        fetch_is_unconditional` — Bug Catching Set's top-7 dig, a board-gated or name-family clause)
        is skipped: this leg asserts the slot CAN be filled, so a probable find would be a fabricated
        endorsement. One shared predicate with the closure, never a re-spelled guard."""
        from common.fetch_closure import fetch_is_unconditional
        return any(cl.get("kind") == "fetch" and cl.get("target") == "basic_energy"
                   and fetch_is_unconditional(cl)
                   and self._slot_basic_in_zone(want, cl.get("energy_type"), cl.get("zone"),
                                                counts, discard_basic_types)
                   for cl in (self.effects.clauses(cid) if self.effects else ()))

    def _supporter_energy_tutor_reaches(self, tid, want, counts: dict, discard_basic_types: set) -> bool:
        """WP1 (Supporter branch): True iff Supporter ``tid`` can put a slot-filling Energy in hand or
        attach it, its target still reachable — LIVE only while the one-per-turn Supporter slot is
        unspent, which inside the refresh window means the refresh itself was an ITEM (Unfair Stamp;
        4/5 refreshes are Supporters and spend the slot — the caller gates on that). Three clause
        shapes (`card_effects.json`): an ``energy``/``basic_energy`` deck fetch (Hilda — Special
        Energy ignored, Basics-only matching, under-count); an UNconditional ``accel`` (Crispin
        attaches directly — bypasses nothing here, the manual attach is unspent anyway; a conditioned
        accel like Rosa's fails closed); the ``trainer`` fetch 2-hop (Petrel → an energy-fetch ITEM
        still in deck whose own target is reachable — spec-verified legal in one turn).

        Both fetch shapes are gated on `fetch_closure.fetch_is_unconditional`, the same predicate the
        closure's reach reading uses: a dig, a board gate or an undecidable name family is not the
        deterministic search this leg's claim rests on. The ``accel`` shape has always failed closed
        on a `condition` for the same reason, and now says so through the shared vocabulary."""
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
        """The refresh CHAIN (hypergeometric-fetch-closure §failure mode B, the drawn-expander leg —
        built 2026-07-19): USABLE shuffle-refresh copies still in my DECK whose draw opens a fresh
        full window inside this refresh's window — ``(copies, min_window)``. A drawn Unfair Stamp
        (Item) is usable iff one of MY Pokémon was KO'd during the opponent's last turn
        (`Board.my_pokemon_koed_last_turn` — the card's own play condition); a drawn SUPPORTER
        refresh (Judge / Lillie's / Harlequin) is usable iff the one-per-turn Supporter slot is
        UNSPENT in this window, i.e. the played refresh was an Item (``sup_live`` — the 4-of-5
        rule). Window = each card's own printed draw (`own_draw_count`), MIN across usable types
        (the engine convention — conservative when types mix). ``(0, 0)`` when none usable. Errs by
        under-counting: chains inside the chain, and the measured slot-dead cases (a Pokégear-class
        dig fetching a slot-dead Supporter), are never counted."""
        from common.strategy.refresh import own_draw_count
        copies, window = 0, None
        for tid, n in counts.items():
            if n <= 0 or not self.functions or "shuffle_hand" not in self.functions.tags(tid):
                continue
            st = self.stats.get(tid) if self.stats else None
            if st is None:
                continue
            if getattr(st, "is_item", False):
                if not getattr(board, "my_pokemon_koed_last_turn", False):
                    continue
            elif getattr(st, "is_supporter", False):
                if not sup_live:
                    continue
            else:
                continue
            w = own_draw_count(tid, board.my_prizes_remaining, board.opp_prizes_remaining)
            if not w or w <= 0:
                continue
            copies += n
            window = int(w) if window is None else min(window, int(w))
        return (copies, window or 0)

    def _gamble_draw_engines(self, me: dict, counts: dict, exclude: set) -> tuple:
        """WP4: the refresh window's usable DRAW ENGINES — ``(engine_copies, stage_windows,
        engine_ids)`` for `deck_odds.draw_hit_with_engines`. A drawn engine copy is usable iff its
        ability is unconditional-once-in-play (`draw` clause, ``condition: once_per_turn_ability`` —
        Drakloak's Recon, Dudunsparce's Run Away Draw; Fezandipiti's post-KO gate and Lunatone's
        Solrock+hand-discard gate fail CLOSED — the refresh empties the hand, the gate can't be
        promised) AND an eligible base for it is already on board (rules.md §4: a body in play since
        last turn, ``appearThisTurn`` False — evolving the drawn engine onto it is legal this turn;
        turn ≥ 2 is gated upstream). Depth = board-supported capacity, Σ per line of min(copies in
        pool, eligible bases) — never a hardcoded stage count (spec §recursion point 2). The stage
        window = the MINIMUM usable window (Recon sees 2, take-1 greedy; Run Away Draw sees 3) —
        conservative when lines mix. ``exclude`` drops ids the class already counts as outs (a
        Drakloak that IS the sought evolution never double-counts). Errs by under-counting only."""
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
        """WP5 (Supporter branch): True iff Supporter ``tid`` can deliver the evolution ``eid`` —
        a deck fetch reaching it (Hilda's `evolution` clause; Salvatore's rush-evolve puts it
        straight ONTO the body) or the Petrel 2-hop (→ an Item Pokémon-tutor still in deck that
        reaches it). Live only post-Item-refresh (the caller gates on the Supporter slot).

        The 2-hop's FIRST leg is gated on `fetch_closure.fetch_is_unconditional` like every other
        reach-side reader; the second is `_fetch_reaches_pokemon`, which asks the closure and so
        carries the same gate already."""
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
        """WP5/WP7: True iff card ``cid``'s ``zone: deck`` FETCH clauses can pull the Pokémon
        ``target_id`` (still in ``counts``) — Poké Pad's ``no_rule_box`` never fetches a Rule-Box Mega
        ex. Delegates to the shared `common.fetch_closure` graph (ADR-0065)."""
        from common import fetch_closure
        return fetch_closure.fetch_reaches_pokemon(
            target_id, cid, counts, self._closure_stat_of, self._closure_clauses_of)

    def _whiff_odds(self, board, body) -> float:
        """BUILD 1 helper: P(the opponent still holds ≥1 copy of ``body``'s line) via the Opponent Model
        (`copies_left_odds`). Lower = the opponent is LESS able to replace this body if I KO it — the
        whiff-maximising target. Fails OPEN to 1.0 ("assume replaceable") when no Opponent Model / no
        confident Read, so the tiebreak silently no-ops without a confident recognition."""
        opp_model = getattr(board, "opponent", None)
        if opp_model is None:
            return 1.0
        try:
            return float(opp_model.copies_left_odds((body or {}).get("id")))
        except Exception:
            return 1.0

    def _composed_budget(self, card_id, *, benched: bool, supporter_spent: bool = False):
        """The Attach Budget toward one KO line's attacker, or None without a model.

        The units answer "does this line REACH a KO"; the Budget itself answers "how likely is the
        Energy really there" (ADR-0074 decision 3) — the same oracle read twice, so reach and
        probability can never be computed off different budgets. It is also what ANSWERS the reach
        question (ADR-0075 decision 1), which is the third reading of that same one Budget.

        ``supporter_spent`` closes the Supporter leg for a line that plays a Supporter as its own
        enabling step (ADR-0075 decision 3) — the successor to the retired
        ``enabler_consumes_supporter`` split."""
        model = self._state_model
        if model is None or card_id is None:
            return None
        return model.mine.attach_budget_for_card(card_id, benched=benched,
                                                 supporter_spent=supporter_spent)

    def _composed_attack_p(self, card_id, body, *, benched: bool, supporter_spent: bool = False):
        """``attack_id -> P(the composed line's Energy is really there)`` for this candidate form,
        or None when nothing can be priced (no model / no Budget) — the caller then makes no claim
        and the line keeps its unweighted value, exactly as before #175.

        This is the RANKED-consumer half of ADR-0074's Leg Assignment: the `ko_for_prizes` ladder
        emits a compared scalar, so it weights; the Win Rung gates, so it never calls this."""
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
        """P(the composed line's KO really lands) — the weighted KO value over the unweighted one,
        i.e. the probability attached to whichever attack the weighted valuation actually picked
        (ADR-0074 decisions 3-4, #175).

        Reading it back off the two valuations, rather than recomputing a "best" attack here, is
        what keeps the weight tied to the line the ranker committed to. 1.0 with nothing to price
        (no model, an unresolvable cost), so an unweighted build is byte-identical."""
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
        """``(budget, attack_p)`` for ONE KO line's attacker — the single pricing seam EVERY
        ``ko_for_prizes`` builder reads (ADR-0075 decision 4).

        ``card_id`` names the card whose ATTACKS are read (an evolved form still in hand or deck for
        a composed line; the body itself for a retreat line); ``body`` is the on-board dict carrying
        the ATTACHED Energy, which for an evolve line is the PRE-evolution body the Energy carries
        through. ``benched`` places the target for a bench-restricted clause — and since no modelled
        accel clause requires an ACTIVE target, a retreat line takes True: "attach to the benched
        body, then retreat, then attack" is a real sequence and a strict superset.

        One Budget serves refusal and ranking both, so the two can never be computed off different
        budgets (ADR-0075 decision 7 — separate parameters, one source)."""
        budget = self._composed_budget(card_id, benched=benched, supporter_spent=supporter_spent)
        if budget is None:
            return None, None
        return budget, self._composed_attack_p(card_id, body, benched=benched,
                                               supporter_spent=supporter_spent)

    def _gamble_det_baseline(self, board, stat, ma, opp, hp: int, traces, hand: list) -> float:
        """The DETERMINISTIC baseline a gamble must beat: the best tactical already on the menu, or
        the best after-attach chip the HELD Energy reaches (attach the best hand Energy → biggest
        affordable non-KO damage) — the value the banked line (attach first, refresh after) keeps."""
        det = max((t.tactical for t in traces), default=0.0)
        hand_ids = frozenset(c.get("id") for c in hand)
        units = self._best_hand_attach_units(hand_ids, stat)
        energy_after = board.my_active_energy + units
        # extra_type=0: the held attach is priced as colourless — funds {C} slots only, the
        # conservative read (a held TYPED enabler voids the gamble class upstream anyway). The scan
        # is `combat.best_affordable_damage` (Issue #409), extracted so the affordability rule —
        # count gate AND colour gate, which must stay in lockstep — has one home.
        return max(det, self._best_affordable_damage(board.my_active_id, energy_after, opp,
                                                     body=ma, extra_type=0, extra_units=units))

    def _closure_stat_of(self, cid):
        return self.stats.get(cid) if (self.stats and cid is not None) else None

    def _closure_clauses_of(self, cid):
        return self.effects.clauses(cid) if self.effects else ()

    def _card_reaccess_outs(self, cid, counts: dict) -> int:
        """WP6/WP7: the copies in my DECK that re-access card ``cid`` once it is shuffled back in — the
        `common.fetch_closure` graph pointed BACKWARDS. Delegates to the ONE shared closure module
        (ADR-0065) so the gamble gain side and the keep-cost read the same implementation."""
        from common import fetch_closure
        return fetch_closure.reaccess_outs(cid, counts, self._closure_stat_of, self._closure_clauses_of)

    def _is_energy_tutor(self, obs, select, option) -> bool:
        """This PLAY option is a `tutor_energy` Trainer (Hilda class) — it searches an attachable
        Energy into hand, supplying the attach an enabling line lacks (the 4298 shape)."""
        cid = self._option_card_id(obs, select, option)
        return bool(cid is not None and self.functions and "tutor_energy" in self.functions.tags(cid))

    def _is_evolution_tutor(self, obs, select, option) -> bool:
        """This PLAY option is a `rush_evolve` Trainer (Salvatore class) — it evolves one of my
        in-play Pokémon straight from the deck, its own allowance covering setup-placed and
        this-turn bodies (so every in-play body is a legal target)."""
        cid = self._option_card_id(obs, select, option)
        return bool(cid is not None and self.functions and "rush_evolve" in self.functions.tags(cid))

    def _is_item_pokemon_tutor(self, obs, select, option) -> bool:
        """BUILD 3 helper: this PLAY option is an ITEM that fetches an evolution-form Pokémon into HAND
        (Mega Signal: `tutor_mega`; the generic `tutor_pokemon`) — the composer's committed first step.
        Distinct from `rush_evolve` (evolves straight from the deck — a Supporter) and `tutor_energy`.
        False when the card / its stat / its tags are unknown (fail-closed)."""
        cid = self._option_card_id(obs, select, option)
        if cid is None or not self.functions or not self.stats:
            return False
        stat = self.stats.get(cid)
        if stat is None or not getattr(stat, "is_item", False):
            return False
        tags = self.functions.tags(cid)
        return "tutor_mega" in tags or "tutor_pokemon" in tags

    def _is_rare_candy(self, obs, select, option) -> bool:
        """BUILD 1 helper: this PLAY option is Rare Candy — a Basic→Stage-2 evolve SKIP that needs the
        Stage-2 already in hand (NOT a tutor). Verified card text at data/EN_Card_Data.csv id 1079.

        Matched by the `rare_candy` Function Tag (ADR-0006), not by a private id constant. The old
        constant's justification was explicitly *"no other consumer needs the tag"*; Issue #288's
        playability gate needs exactly this fact about a card sitting in HAND OR DECK — a question no
        option-id comparison can answer — so the two would have had to agree by hand. False without a
        tag table, which is this branch's shipped fail direction (the composer is DEFAULT OFF and only
        ever ADDS a line)."""
        cid = self._option_card_id(obs, select, option)
        return bool(self.functions and cid is not None
                    and playability.RARE_CANDY_TAG in set(self.functions.tags(cid)))

    def _item_enabler_cost(self, board) -> float:
        """BUILD 4 (`enabler_item_composer`): the cost credit for an Item enabler (a pokemon-tutor Item or
        Rare Candy). The Item's only advantage over the Supporter-tutor path (credit 0) is that it does NOT
        spend the scarce one-per-turn Supporter slot. That preservation is worth the WIDER gap
        (``_PLANNER_ENABLER_ITEM_SLOT``) only when a Supporter in hand actually WANTS the slot this turn —
        canonically a `gust` Supporter (Boss's Orders, which could itself drag+KO) or any other high-value
        Supporter (``no_supporter_in_hand`` False ⇒ some Supporter competes). With no Supporter competing,
        keeping the slot is nearly free, so the gap SHRINKS to ``_PLANNER_ENABLER_ITEM_BASE``. Both credits
        stay sub-prize/sub-survival: a same-KO enabler tiebreak, never a reorder over a real prize."""
        competes = self._gust_supporter_in_hand(board) or not board.no_supporter_in_hand
        return _PLANNER_ENABLER_ITEM_SLOT if competes else _PLANNER_ENABLER_ITEM_BASE

    def _gust_supporter_in_hand(self, board) -> bool:
        """BUILD 4 helper: MY hand holds a `gust` Supporter (Boss's Orders class) — the sharpest claimant on
        this turn's one Supporter slot (it can itself drag a benched body up and KO). False without
        stats/functions (fail-closed) — an unrecognized hand never asserts the competing Supporter."""
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
        """BUILD 1 helper: the Stage-2 ``stage2_stat``'s evolution chain roots at the Basic ``basic_name`` —
        i.e. some Stage-1 card is named ``stage2_stat.evolvesFrom`` AND that Stage-1's ``evolvesFrom`` names
        the Basic. Verifies the exact two-hop line Rare Candy skips (Basic → Stage-1 → Stage-2), by name,
        against the real card data (never mainline recall — rules.md §4). False when the intermediate
        Stage-1 can't be resolved."""
        stage1_name = getattr(stage2_stat, "evolvesFrom", None)
        if not stage1_name:
            return False
        for s1_id in self.stats.ids_for_name(stage1_name):
            s1 = self.stats.get(s1_id)
            if s1 is not None and getattr(s1, "evolvesFrom", None) == basic_name:
                return True
        return False
