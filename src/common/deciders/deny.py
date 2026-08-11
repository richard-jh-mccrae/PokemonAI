"""Deny Relevance (ADR-0080): what an Energy strip actually takes away, per opponent body, priced NOW.

`_DENY_CHARGED` is what makes it *now* — no credit for the attach they make next turn."""
from __future__ import annotations


from collections import Counter

from common.deciders.facts import Board
from common.deciders.snipe import _BRIEF_THREAT_BOOST
from common.deny_relevance import MAX_ATTACK_DAMAGE as _DENY_RELEVANCE_NORM
from common.strategy.context import (FOLLOWUP_W, _ACTIVE, _BENCH, _DISCARD_ENERGY, _ENERGY, _PLAY,
                                     _POSTURE_MIN_COVERAGE, _POSTURE_UNFAVORED)
from common.strategy.denial import coin_odds
from common.strategy.sequence import followup_damage


# The old hand-value term is DELETED (Issue #386) with the develop rung whose leaf it belonged to.
# Its question is now `state_value`'s `hand` family, which prices the hand as a LEDGER (ADR-0127).
_DENIAL_PLAY_W = 1.0       # points per damage-point denied, at the PLAY

_DENIAL_TARGET_W = 1.0     # points per damage-point denied, at the DISCARD_ENERGY select. Nothing
                           # scored that select before, so a won flip stripped option [0].

#: DERIVED, not chosen (ADR-0080): exactly the normalizer relevance divides by, so `K x relevance` IS
#: the setback damage. NOT an exchange rate — that is the Worth Damage Rate, MOOT for deny.
_DENY_RELEVANCE_K = _DENY_RELEVANCE_NORM

_DENIAL_UNFAVORED = 0.3    # Lever A (ADR-0026) as a MULTIPLIER on deny's value, never a flat rung
                           # beside it: scaling 0 leaves 0, so it cannot resurrect a whiff. Its
                           # ADR-0078 decision 6 retirement is WITHDRAWN; this is Lever A's last consumer.

_DENIAL_FORWARD = 0.5      # Credit for what the stripped Energy would pay on the target's FORWARD
                           # form — evolving keeps attached cards (rules.md:98), so a pre-evolution's
                           # Energy is BANKED. Two frames force 0.154 < _DENIAL_FORWARD < 0.8.


class DenyMixin:
    """What stripping this Energy takes away from the opponent, this turn."""

    def _unfavored(self, board: Board) -> bool:
        """The Read says the straight race loses (Lever A, ADR-0026) — a compiled favorability at or
        below `_POSTURE_UNFAVORED`, backed by enough coverage to trust the prior."""
        return (board.matchup_coverage >= _POSTURE_MIN_COVERAGE
                and board.favorability <= _POSTURE_UNFAVORED)

    def _denial_play_tactical(self, obs: dict, board: Board, ctx) -> float:
        """`coin_odds x _DENIAL_PLAY_W x (unfavored?) x K x relevance − _item_hold_price` (ADR-0080).
        A whiff pays the hold price and so prices NEGATIVE, which is what declines."""
        if ctx.option_type != _PLAY or "energy_denial" not in ctx.tags:
            return 0.0
        if not self.deny_relevance:
            return 0.0          # DEGRADED MODE, never a rollback — see the flag's note in runtime.py
        # `None` on the Board is ABSENT, not zero (ADR-0093 decision 2), so recompute rather than read
        # it as a whiff. A genuine 0.0 survives the ladder and is a real hold.
        value = _DENY_RELEVANCE_K * self._deny_relevance_best(obs, board)
        weight = _DENIAL_PLAY_W * (1.0 + _DENIAL_UNFAVORED if self._unfavored(board) else 1.0)
        # NO whiff short-circuit: declining needs a STRICTLY negative score. `_finish_turn_last`
        # promotes on `score > 0`, so a bare 0.0 quota-free Item ties with End by option index.
        return (coin_odds(ctx.tags) * weight * value
                - self._item_hold_price(obs, board, ctx.card_id))

    def _denial_target_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """Rank the strip's TARGET at a DISCARD_ENERGY select: a pure `argmax relevance`, scored per
        OPTION and keyed on the option's Provider-resolved TYPE, never on its position."""
        if (select or {}).get("context") != _DISCARD_ENERGY or option.get("type") != _ENERGY:
            return 0.0
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        area = option.get("area")
        if area == _ACTIVE:
            if board.active_can_ko:
                return 0.0                     # it dies this turn — stripping it denies nothing
            target, weight, key = next((p for p in (opp.get("active") or []) if p), None), 1.0, \
                ("active", 0)
        elif area == _BENCH:
            bench = opp.get("bench") or []
            idx = option.get("index", -1)
            target = bench[idx] if 0 <= idx < len(bench) else None
            # No area weight — relevance already prices a benched body's slower clock through its own
            # line scan, so discounting again double-counts. The fire rung carries the promotion GATE.
            weight = 1.0
            key = ("bench", idx)
        else:
            return 0.0
        if not self.deny_relevance:
            return 0.0          # DEGRADED MODE, never a rollback — see the flag's note in runtime.py
        etype = self._option_energy_type(target, option)
        rel_map = self._deny_relevance_map(obs, board)
        rel = (rel_map.get(key) or {}).get(etype, 0.0)
        base = _DENIAL_TARGET_W * weight * _DENY_RELEVANCE_K * rel
        return base + self._deny_strip_delta_tiebreak(obs, board, select, key, rel, rel_map)

    def _deny_strip_delta_tiebreak(self, obs: dict, board: Board, select: dict, key,
                                   rel: float, rel_map: dict) -> float:
        """Among candidates tied on relevance EXACTLY, prefer the one whose strip buys turns of survival
        (ADR-0084 decision 2). It may ORDER a tie; it may never GATE one (decision 7)."""
        shifts = self._deny_strip_shift_map(obs, board)
        mine = shifts.get(key)
        if mine is None or not rel:
            return 0.0                            # absent reading, or nothing relevant — not a zero
        # Peers come off the SELECT, not the board: an Energy no option targets is not a candidate,
        # and ranking against it would invent a tie the engine never posed.
        peers = []
        for opt in (select.get("option") or ()):
            if opt.get("type") != _ENERGY:
                continue
            area = opt.get("area")
            k = ("active", 0) if area == _ACTIVE else (
                ("bench", opt.get("index", -1)) if area == _BENCH else None)
            if k is None or k not in rel_map:
                continue
            if k[0] == "active" and board.active_can_ko:
                continue                          # already scored 0.0 by the caller; letting it hold
                #                                   the largest shift would mute the tiebreak entirely
            r = (rel_map.get(k) or {}).get(
                self._option_energy_type(self._deny_body_at(obs, k), opt), 0.0)
            peers.append((r, k))
        tied = {k for r, k in peers if r == rel}
        if len(tied) < 2:
            return 0.0                            # nothing tied with me — relevance already decided
        best = max((shifts.get(k) for k in tied), key=lambda s: (s is not None, s))
        if best is None or best <= 0 or mine != best:
            return 0.0                            # no strict winner, or I am not it
        if sum(1 for k in tied if shifts.get(k) == best) > 1:
            return 0.0                            # tied on the clock too — no preference expressible
        # Half the finest distinction relevance draws on THIS menu, or `1 / K` (one damage unit) when
        # it draws none — never this candidate's own relevance, which would swamp the other tacticals.
        from common.currency import tiebreak_bonus
        return _DENIAL_TARGET_W * tiebreak_bonus([r for r, _k in peers], _DENY_RELEVANCE_K)

    def _deny_body_at(self, obs: dict, key) -> dict | None:
        """The opponent body a ``(area, bi)`` deny key names, read off the live obs."""
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        area, bi = key
        bodies = [b for b in (opp.get("active") if area == "active" else opp.get("bench")) or [] if b]
        return bodies[bi] if 0 <= bi < len(bodies) else None

    def _option_energy_type(self, target: dict | None, option: dict):
        """The `EnergyType` a ``DISCARD_ENERGY`` option contributes. ``energyIndex`` indexes the body's
        attached CARDS, not the ``energies`` UNITS they provide. Never inferred from the card id."""
        k = option.get("energyIndex")
        if target is None or k is None:
            return None
        cards = target.get("energyCards") or []
        if 0 <= k < len(cards):
            cid = (cards[k] or {}).get("id")
        else:
            units = target.get("energies") or []
            cid = units[k] if 0 <= k < len(units) else None
        if cid is None:
            return None
        est = self.stats.get(cid) if self.stats else None
        return getattr(est, "energyType", None) if est else None

    def _lock_sequence_cost(self, attack_id, board: Board) -> float:
        """Horizon-2 lock cost (ADR-0061): the damage this attack's lock FORFEITS next turn. A COST,
        never a credit, so a lock-free attack is 0 — as is a doomed Active or a lone affordable attack."""
        st = self._attack_stat(attack_id)
        if not st or board.active_doomed:
            return 0.0
        active = self.stats.get(board.my_active_id) if (self.stats and board.my_active_id) else None
        affordable = {aid: self._attack_damage(aid)
                      for aid in (getattr(active, "attacks", None) or ())
                      if self._attack_cost(aid) <= board.my_active_energy}
        if len(affordable) <= 1:
            return 0.0                                   # lone attack: never charged
        mine = followup_damage(attack_id, affordable=affordable,
                               full_lock=bool(getattr(st, "nextTurnSelfLock", False)),
                               same_attack_lock=bool(getattr(st, "nextTurnSameAttackLock", False)))
        return FOLLOWUP_W * max(0.0, max(affordable.values()) - mine)

    def _deny_relevance_best(self, obs: dict, board: Board) -> float:
        """`Board.deny_relevance_best`, cached-or-computed. `None` on the Board means ABSENT, never a
        measured zero, so it is recomputed; a genuine 0.0 survives the ladder and is a real HOLD."""
        if board.deny_relevance_best is not None:
            return board.deny_relevance_best
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else None
        oa = next((p for p in ((opp or {}).get("active") or []) if p), None)
        return self._best_area_weighted_relevance(self._deny_rows(obs, board), opp, oa)

    def _deny_relevance_map(self, obs: dict, board: Board) -> dict:
        """``{(area, bi): {EnergyType: relevance}}``, cached-or-computed. The fallback matters: without
        it a hand-built board would emit NO deny slots and read as a whiff rather than fail closed."""
        if board.deny_relevance_rows:
            return {(a, i): rel for a, i, rel, _shift in board.deny_relevance_rows}
        result = self._deny_rows(obs, board)
        return {(r["area"], r["bi"]): dict(r.get("relevance_by_type") or {}) for r in result}

    def _deny_strip_shift_map(self, obs: dict, board: Board) -> dict:
        """``{(area, bi): strip_shift}`` — the ADR-0084 strip Δ per body, a delta OF `turns_to_ko_me`
        and not a reading of it. ``None`` means ABSENT, not zero (the flag is off, or no reading)."""
        if board.deny_relevance_rows:
            return {(a, i): shift for a, i, _rel, shift in board.deny_relevance_rows}
        return {(r["area"], r["bi"]): r.get("strip_shift") for r in self._deny_rows(obs, board)}

    def _deny_rows(self, obs: dict, board: Board) -> list:
        """The per-decision opponent-target rows, cached-or-computed — the one ladder both deny maps
        read."""
        result = getattr(self, "_opponent_target_cache", None)
        if result is None:
            result = self._opponent_target_rows(obs, board)
        return list(result[1]) if result else []

    def _relevance_terms(self, b, *, doomed: frozenset, area: str, bi: int, brief_ids=()) -> dict:
        """Deny Relevance per opponent body (ADR-0080). ⚠️ ``relevance_energy`` indexes ``energies``
        (UNITS) and is DIAGNOSTIC ONLY — a consumer must key off ``relevance_by_type`` instead."""
        from common import deny_relevance as dr
        blank = {"relevance": 0.0, "relevance_energy": None, "relevance_attack_leg": 0.0,
                 "relevance_ability_leg": 0.0, "relevance_setback": 0, "relevance_forward": 0,
                 "relevance_by_type": {}, "relevance_fire": 0.0}
        energies = list((b or {}).get("energies") or [])
        if not energies or (area, bi) in doomed:
            return blank
        line_attacks, ability_types = self._line_attack_costs(b.get("id"))
        model = self._state_model
        if model is None:
            return blank                       # no snapshot: the instrument claims nothing
        counts = model.theirs.view_of(b).attached_types      # ← StateModel (POC-T1)
        best = dict(blank)
        by_type: dict = {}
        fire = 0.0
        for j, eid in enumerate(energies):
            est = self.stats.get(eid) if self.stats else None
            etype = getattr(est, "energyType", None) if est else None
            got = dr.strip_relevance(energy_type=etype, type_count=counts.get(etype, 0),
                                     line_attacks=line_attacks, ability_types=ability_types,
                                     total_attached=len(energies), attached_counts=counts,
                                     # ADR-0084 Amendment A: without the discount the armed read
                                     # credited a forward form in full.
                                     forward_discount=_DENIAL_FORWARD)
            by_type[etype] = got["relevance"]
            fire = max(fire, got["affordable_relevance"])
            if best["relevance_energy"] is None or got["relevance"] > best["relevance"]:
                best = {"relevance": got["relevance"], "relevance_energy": j,
                        "relevance_attack_leg": got["attack_leg"],
                        "relevance_ability_leg": got["ability_leg"],
                        "relevance_setback": got["setback_damage"],
                        "relevance_forward": got["forward_setback"],
                        "relevance_by_type": {}, "relevance_fire": 0.0}
        if b.get("id") in (brief_ids or ()):
            # The Brief sharpens the RANK only (ADR-0080 decision 2). It must NOT touch the fire leg:
            # that is compared against the HOLD PRICE, so a multiplier there can lift a hold above 0.
            best = dict(best, relevance=min(1.0, best["relevance"] * _BRIEF_THREAT_BOOST))
            by_type = {t: min(1.0, v * _BRIEF_THREAT_BOOST) for t, v in by_type.items()}
        return dict(best, relevance_by_type=by_type, relevance_fire=fire)

    def _strip_delta_terms(self, ma, bodies, i, phase, *, opp_active, enabler) -> dict:
        """Deny's slice of the shared marginal (ADR-0078 D1): the same two-term value the removal Δ uses,
        read under `_DENY_CHARGED` — under the ceiling it is 0. ``energies[:-1]``: ADR-0084 decision 3."""
        from common import needs
        b = bodies[i]
        energies = list((b or {}).get("energies") or [])
        if not energies:
            return {"strip_shift": 0, "deny_value": 0.0}       # nothing to strip — the whiff, derived
        stripped = dict(b)
        stripped["energies"] = energies[:-1]                   # one Energy gone; the body remains
        model = self._state_model
        if model is None:
            return {"strip_shift": 0, "deny_value": 0.0}       # no snapshot: the Δ claims nothing
        # BOTH legs must name `_DENY_CHARGED` and `context` — the return DIFFERENCES them, and a
        # threaded leg minus a blind one is two questions. INTEGER, unlike `survival_shift` (ADR-0117).
        ctx = self._opp_attack_context
        base = model.theirs.turns_to_ko_me(ma, bodies=bodies, opp_active=opp_active,
                                           switch_enabler=enabler, charged=self._DENY_CHARGED,
                                           context=ctx)
        after = model.theirs.turns_to_ko_me(ma, bodies=bodies[:i] + [stripped] + bodies[i + 1:],
                                            opp_active=stripped if b is opp_active else opp_active,
                                            switch_enabler=enabler, charged=self._DENY_CHARGED,
                                            context=ctx)
        return {"strip_shift": after - base,                   # BOTH legs under `_DENY_CHARGED`; the
                                                               # caller's `base_t` is the CEILING
                "deny_value": needs.opponent_target_value(prize_advance=0.0,
                                                          survival_shift=after - base, phase=phase)}

    def _best_area_weighted_relevance(self, rel_rows, opp: dict | None,
                                      oa: dict | None) -> float:
        """The best relevance anywhere on their board. AREA-WEIGHTED through ADR-0071's promotion GATE,
        not a flat discount: a bench row counts in full when the gate is open, not at all when shut."""
        bodies = [b for b in ([oa] if oa else []) + list((opp or {}).get("bench") or []) if b]
        promotion_open = bool(bodies) and self.combat._promotion_open(
            bodies, oa, switch_enabler=self._opp_switch_enabler())
        return max((r.get("relevance_fire", 0.0) * (1.0 if r["area"] == "active"
                                                    else (1.0 if promotion_open else 0.0))
                    for r in rel_rows), default=0.0)

    def _opponent_target_rows(self, obs: dict, board) -> tuple | None:
        """The SHARED per-body opponent-target value (ADR-0076) as ``(phase, rows)``, keyed by the
        deny-slot ``(area, bi)``. Runs MID-SIM by design — it is LIVE, not a shadow (ADR-0093 D3)."""
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) else None
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else None
        ma = next((p for p in ((me or {}).get("active") or []) if p), None)
        active_list = [p for p in ((opp or {}).get("active") or []) if p]
        bench_list = [p for p in ((opp or {}).get("bench") or []) if p]
        bodies = active_list + bench_list
        if not (ma and bodies):
            return None
        from common import needs
        phase = needs.phase_scale(race_ahead=getattr(board, "race_ahead", None),
                                  opp_prizes_remaining=getattr(board, "opp_prizes_remaining", 0))
        model = self._state_model
        if model is None:
            return None                          # no snapshot: no target rows, no gust/deny slots
        opp_active = active_list[0] if active_list else None
        enabler = self._opp_switch_enabler()
        # `charged=None` is the CEILING, stated not inherited: a THREAT read keeps the worst-case
        # policy. `context` sits in `clock` so the Δ below cannot difference threaded against blind.
        clock = dict(bodies=bodies, charged=None, opp_active=opp_active, switch_enabler=enabler,
                     context=self._opp_attack_context)
        # THE FRACTIONAL READING, opted into here and nowhere else (ADR-0117); other clock families
        # keep the integer. ⚠️ A body that never leads is a Structural Zero at any resolution (Issue #398).
        base_exact = model.theirs.survival_clock(ma, **clock).exact
        # Deny Relevance's REDUNDANCY gate (ADR-0080 step 2), resolved once per decision: which of
        # their bodies die to our Knock Out this turn, and so deny nothing.
        doomed_ids = frozenset()
        if self.deny_relevance:
            doomed_ids = (frozenset({("active", 0)} if getattr(board, "active_can_ko", False)
                                    else ())
                          | frozenset(("bench", j)
                                      for j in self._bench_doomed_by_me(ma, bench_list)))
        # The ADR-0051 spine, resolved once per decision. `None` -> the row carries 0.0, the same
        # "unroled" reading `MatchupPlan.priority` gives, so no consumer special-cases it.
        plan = getattr(board, "matchup_plan", None)
        rows = []
        for i, b in enumerate(bodies):
            shift = model.theirs.survival_clock(
                ma, **dict(clock, bodies=bodies[:i] + bodies[i + 1:])).exact - base_exact
            # `advance` is THE LINE'S prize (ADR-0119 D2) — what removing it denies is the form that
            # never arrives. `prize` keeps the OWN printed value: `prize_race` moves by THAT on a KO.
            prize = model.theirs.view_of(b).prize_value
            line_prize, line_hops = model.theirs.forward_line_prize(b.get("id"))
            advance = needs.line_prize_advance(own_prize=prize, max_line_prize=line_prize,
                                               hops=line_hops)
            val = needs.opponent_target_value(prize_advance=advance, survival_shift=shift,
                                              phase=phase)
            area, bi = ("active", i) if i < len(active_list) else ("bench", i - len(active_list))
            row = {"body": b, "area": area, "bi": bi, "id": b.get("id"), "prize": prize,
                   "prize_advance": advance, "survival_shift": shift, "value": val,
                   # THE ROLE SHEET as its OWN leg (Issue #395 D7), never folded into `value`, which
                   # keeps its ceiling. An ORDINAL priority: never sum it into a prize-denominated number.
                   "role_priority": (plan.priority(b.get("id")) if plan is not None else 0.0)}
            if self.deny_strip_delta:
                row.update(self._strip_delta_terms(ma, bodies, i, phase,
                                                   opp_active=opp_active, enabler=enabler))
            if self.deny_relevance:
                row.update(self._relevance_terms(
                    b, doomed=doomed_ids, area=area, bi=bi,
                    brief_ids=getattr(board, "brief_threat_ids", ()) or ()))
            rows.append(row)
        return phase, rows

    def _line_attack_costs(self, card_id) -> tuple:
        """``([(damage, {EnergyType: slots}, cost, is_forward), …], ability_fuel_types)`` over the body
        and its forward forms. Colourless slots are DROPPED: anything pays them, so none is critical."""
        from collections import Counter
        if not self.stats:
            return (), frozenset()
        forward = set(self.combat.forward_card_ids(card_id))
        attacks, fuels = [], set()
        for cid in {card_id} | forward:
            st = self.stats.get(cid) if cid is not None else None
            if not st:
                continue
            fuels.update(t for t in (getattr(st, "abilityEnergyTypes", ()) or ()) if t not in (0, None))
            for aid in (getattr(st, "attacks", ()) or ()):
                ast = self.combat.attack_stat(aid)
                need = Counter(t for t in (getattr(ast, "energyTypes", ()) or ()) if t not in (0, None))
                attacks.append((self.combat.attack_damage(aid), dict(need),
                                self.combat.attack_cost(aid, default=0), cid in forward))
        return tuple(attacks), frozenset(fuels)
