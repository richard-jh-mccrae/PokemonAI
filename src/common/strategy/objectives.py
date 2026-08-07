"""Tier 3 — Match Objectives (ADR-0040): the KO Race and the two-sided Prize Path.

Closed-form turns-to-KO arithmetic over attack SEQUENCES. Against a standing wall every min-turn
sequence fells it in the same number of turns, so the biggest single hit is fake value; what differs
is the incidental bench chip banked along the way. `race_values` is the pure math; `ObjectivesMixin`
prices an ATTACK option with it. Kill-switch `objectives_race`, in `common.runtime.PROFILE`.
"""
from __future__ import annotations

import math

from common.grading import HORIZON as _HORIZON
from common.strategy.context import _BENCH_PLACEMENT_CONTEXTS, _PLAY

_RACE_HORIZON = 8        # give up beyond this many turns — no wall math on an unbounded grind
_RACE_LATER_CHIP = 0.9   # later-turn chip is less certain than chip banked THIS turn (the target can
                         # evolve/retreat/heal) — the tempo tiebreak that prefers starting the chip now


def race_values(attacks: dict, hp: int, horizon: int = _RACE_HORIZON) -> dict:
    """KO Race vs a standing wall of ``hp``, over ``attacks = {aid: (damage, chip)}``:
    ``{aid: (my turns to fell the wall starting here, max chip banked by the rest)}``."""
    dmgs = {a: d for a, (d, _c) in attacks.items() if d > 0}
    if not dmgs or hp <= 0:
        return {}
    max_d = max(dmgs.values())
    items = tuple((d, attacks[a][1]) for a, d in dmgs.items())
    out = {}
    for aid, d in dmgs.items():
        rem = max(0, hp - d)
        t_star = 1 + math.ceil(rem / max_d)
        if t_star > horizon:
            continue
        out[aid] = (t_star, _best_rest_chip(items, rem, t_star - 1))
    return out


def _best_rest_chip(items: tuple, need: int, turns: int) -> int:
    """Max total chip from exactly ``turns`` further attacks (reuse allowed) whose damage sums
    to at least ``need``; 0 when ``turns`` is 0 (the wall dies on the first hit)."""
    memo: dict = {}

    def go(need: int, turns: int):
        if turns == 0:
            return 0 if need <= 0 else None
        key = (need, turns)
        if key not in memo:
            memo[key] = max((c + sub for d, c in items
                             if (sub := go(max(0, need - d), turns - 1)) is not None),
                            default=None)
        return memo[key]

    return go(need, turns) or 0


def threat_turns(hp: int, forms) -> int | None:
    """Threat Clock (ADR-0045): fewest opponent turns until a body of ``hp`` HP is Knocked Out by any
    of ``forms`` = ``(cost, damage, energy, evo_hops, promo)``. Energy accrues at ~1/turn (rules.md §4)."""
    best = None
    for cost, damage, energy, evo_hops, promo in forms:
        if damage <= 0:
            continue
        first_attack = max(1, evo_hops, cost - energy) + promo
        hits = math.ceil(hp / damage)
        ko = first_attack + hits - 1
        best = ko if best is None else min(best, ko)
    return best


_MATCH_CONFIDENCE_MIN = 0.55   # below this the Game Plan WITHHOLDS its directed goal — defer to the Turn
                               # Planner's own ladder + the tuned weights (the ADR-0045 low-confidence fallback)
_STALL_AHEAD = 2.0             # "clearly ahead" in the race: margin enough to build (STALL) rather than
                               # over-press before the win-condition is online
_MODE_GOAL = {"SETUP": "develop", "RACE": "ko_on_path", "STALL": "develop",
              "STABILIZE": "survive", "SACRIFICE": "trade", "CLOSE": "close"}


def plan_confidence(race_ahead, survival) -> float:
    """The Match Planner's closed-form confidence ∈ [0,1] (ADR-0045): neutral 0.5, raised by the race
    margin and my Active's survival window. A LINEAR feasibility score, NOT a learned win-probability."""
    c = 0.5
    if race_ahead is not None:
        c += 0.12 * race_ahead
    if survival is not None:
        c += 0.05 * (survival - 1)
    return max(0.0, min(1.0, c))


_PATH_BENCH_EXTRA = 1    # a benched body costs ~one extra turn to bring into KO range
                         # (gust / promote / wait) — the feasibility surcharge either side pays
_PROMOTE_TAGS = frozenset({"switch"})   # swaps the opponent's OWN Active for a benched body with no
                                        # retreat — waives the Threat Clock promotion surcharge

_STAB_ENTER = -1.0       # STABILIZE hysteresis (ADR-0040): enter when clearly BEHIND in the race …
_STAB_EXIT = 1.0         # … leave only when clearly AHEAD — between the two, hold the previous label
_CLOSE_PRIZES = 2        # CLOSE: payoff online and at most this many of my prizes left to take
_UNFAVORED = 0.45        # matchup favorability at/below which the straight race loses (Lever A band,
                         # mirrors baseline_disruption._POSTURE_UNFAVORED) — an unfavored, sufficiently
                         # covered Read shifts the STABILIZE enter bar out by one turn (survive-first)
_FAV_MIN_COVERAGE = 0.25 # min matchup coverage to trust favorability as a phase input (else the 0.5
                         # prior default drives nothing — the Read must actually recognize the opp)
_FAV_STAB_SHIFT = 1.0    # how far the unfavored read relaxes the STABILIZE enter threshold (turns)

_PATH_STICKY = 0.5       # path stickiness (ADR-0040): keep last decision's chosen prize path unless
                         # the new cheapest is MORE than this many turns better — coherence across
                         # turns without commitment (the anti-oscillation twin of the phase hysteresis)

_PRED_LEAD = 2.0         # the γ-gated opponent OVERLAY (Tier 4, ADR-0040 §5): a Read-predicted, not-yet-
                         # fielded attacker joins their-side math ceil(_PRED_LEAD / γ) turns out


def prize_paths(bodies, prizes_needed: int, reach=None):
    """Cheapest Prize Path over ``bodies = ((key, prize_value, turns), …)``: ``(keys, total_turns)``
    (ADR-0040). ``reach`` ties AFTER (turns, bodies, prizes), so it never moves the turn count."""
    if prizes_needed <= 0:
        return frozenset(), 0.0
    items = tuple(bodies)
    reach = reach or {}
    best = None                      # (turns, len, -prizes, reach_sum, keys)
    for mask in range(1 << len(items)):
        prizes = turns = n = 0
        reach_sum = 0.0
        keys = []
        for i, (key, pv, t) in enumerate(items):
            if mask & (1 << i):
                prizes, turns, n = prizes + pv, turns + t, n + 1
                reach_sum += reach.get(key, 0.0)
                keys.append(key)
        if prizes >= prizes_needed:
            cand = (turns, n, -prizes, reach_sum, frozenset(keys))
            if best is None or cand[:4] < best[:4]:
                best = cand
    if best is None:
        return frozenset(), None
    return best[4], float(best[0])


def _reaches_my_bench(select, option) -> bool:
    """This option puts a Pokémon onto MY Bench — a `PLAY` from hand at MAIN, or either
    `_BENCH_PLACEMENT_CONTEXTS`, which carry a CARD-target option rather than a `PLAY`."""
    if (select or {}).get("context") in _BENCH_PLACEMENT_CONTEXTS:
        return True
    return option.get("type") == _PLAY


def _phase_from(prev, base, race_ahead, active_doomed: bool, my_prizes: int,
                favorability: float, coverage: float, *, enabled: bool):
    """The advisory phase's PURE core (ADR-0068): previous label in, new label out. Memory passed as
    an argument cannot leak a planner fork's hypothetical phase into the live game; ``self`` did."""
    from common.strategy.strategy import Plan
    if not enabled:
        return base
    enter = _STAB_ENTER
    if coverage >= _FAV_MIN_COVERAGE and favorability <= _UNFAVORED:
        enter += _FAV_STAB_SHIFT                    # unfavored: enter STABILIZE one turn sooner
    phase = base
    if race_ahead is not None and active_doomed:
        if prev == Plan.STABILIZE:
            if race_ahead < _STAB_EXIT:            # keep stabilizing until clearly ahead
                phase = Plan.STABILIZE
        elif race_ahead <= enter:                  # enter clearly behind (bar relaxed if unfavored)
            phase = Plan.STABILIZE
    if base == Plan.RACE and 0 < my_prizes <= _CLOSE_PRIZES:
        phase = Plan.CLOSE                         # endgame overrides: force the finishing line
    return phase


def _sticky_path_from(prev, mine: list, my_prizes: int, best_keys, best_turns):
    """Path stickiness's PURE core (ADR-0068): previous path in, ``(keys, turns, new_prev)`` out —
    the caller decides whether to store, so a simulated board cannot repoint the live turn's path."""
    current = frozenset(cid for k, _pv, _t, cid in mine if k in best_keys and cid is not None)
    if best_turns is not None and prev and prev != current:
        held = [(k, pv, t) for k, pv, t, cid in mine if cid in prev]
        keys2, turns2 = prize_paths(held, my_prizes)
        if turns2 is not None and turns2 <= best_turns + _PATH_STICKY:
            return keys2, turns2, frozenset(
                cid for k, _pv, _t, cid in mine if k in keys2 and cid is not None)
    return best_keys, best_turns, (current if best_turns is not None else prev)


class ObjectivesMixin:
    """Pilot-side Tier-3 Match Objectives (ADR-0040). Depends on Pilot internals, so it is mixed into
    the Pilot like the PlannerMixin."""

    def _race_attack_tactical(self, obs, board, attack_id, dmg_ctx) -> float | None:
        """The KO-Race price of this ATTACK against a standing wall, or None to keep the greedy
        single-hit price. Chip is capped by the opponent's benched HP — chip beyond it lands nowhere."""
        if not getattr(self, "objectives_race", False) or board.active_can_ko:
            return None
        opp = self._opp_active(obs)
        hp = (opp or {}).get("hp", 0)
        stat = self.stats.get(board.my_active_id) if (self.stats and board.my_active_id) else None
        if not (hp and stat):
            return None
        bench_pool = sum(h for _cid, h in board.opp_bench if h)
        table = {}
        for aid in (stat.attacks or ()):
            if self._attack_cost(aid) > board.my_active_energy:
                continue
            d = self.predicted_damage(board.my_active_id, aid, opp, context=dmg_ctx)
            if d <= 0:
                continue
            chip = (self.combat.rider_snipe(aid) + self.combat.rider_spread(aid)) if bench_pool else 0
            table[aid] = (d, chip)
        vals = race_values(table, hp)
        if attack_id not in vals:
            return None
        t_star, rest_chip = vals[attack_id]
        own_chip = min(table[attack_id][1], bench_pool)
        rest = min(rest_chip, max(0, bench_pool - own_chip))
        return hp / t_star + own_chip + _RACE_LATER_CHIP * rest

    # ------------------------------------------------------ the two-sided Prize Path (Board signals)

    def _my_max_rider(self, ma: dict | None) -> int:
        """My Active's biggest bench-snipe rider — per-turn damage onto a benched body with no
        gust-up. Backs the ``snipe_prize_reach`` tie-break; 0 with no Active / no snipe attack."""
        stat = self.stats.get((ma or {}).get("id")) if (self.stats and ma) else None
        if not stat:
            return 0
        return max((self.combat.rider_snipe(aid) for aid in (stat.attacks or ())), default=0)

    def _my_turns_to_ko(self, obs, my_active_id: int | None, energy: int, body: dict) -> float | None:
        """My feasibility turns to fell opponent ``body`` — hp over my Active's best affordable
        per-turn damage vs THAT defender. None when I deal it no damage (infeasible)."""
        return self.combat.turns_to_ko(my_active_id, energy, body)

    def _their_turns_to_ko(self, opp: dict, body: dict, read=None, gamma: float = 0.0) -> float | None:
        """Their feasibility turns to fell MY ``body`` — worst-case ceiling (affordability not
        charged), or a Read-PREDICTED attacker behind its γ-continuous deploy lead. None when neither."""
        hp = (body or {}).get("hp", 0)
        if not (hp and self.stats):
            return None
        best = 0
        for their in [p for p in (opp.get("active") or []) if p] + [b for b in (opp.get("bench") or []) if b]:
            stat = self.stats.get(their.get("id"))
            if stat:
                best = max(best, self._predicted_max_damage(stat, body))
        visible = float(math.ceil(hp / best)) if best > 0 else None
        predicted = None
        if read is not None and gamma > 0:
            lead = math.ceil(_PRED_LEAD / gamma)
            for intel in (getattr(read, "threats", None) or ()):
                if getattr(intel, "seen", True):
                    continue                       # on the board already: the visible pass owns it
                stat = self.stats.get(intel.cardId)
                d = self._predicted_max_damage(stat, body) if stat else 0
                if d > 0:
                    t = math.ceil(hp / d) + lead
                    predicted = t if predicted is None else min(predicted, t)
        if visible is None:
            return float(predicted) if predicted is not None else None
        return float(min(visible, predicted)) if predicted is not None else visible

    # ------------------------------------------------------------------ the Threat Clock (ADR-0045)

    def _threat_clock(self, my_body: dict, opp: dict, read=None, gamma: float = 0.0) -> int | None:
        """The Threat Clock (ADR-0045): fewest opponent turns until any attacker form can afford AND
        land a KO of ``my_body``. Deliberately NOT the input to the worst-case ``active_doomed``."""
        hp = (my_body or {}).get("hp", 0)
        if not (hp and self.stats):
            return None
        return threat_turns(hp, self._threat_forms(my_body, opp))

    def _threat_forms(self, my_body: dict, opp: dict):
        """Yield ``(cost, damage, energy, evo_hops, promo)`` per opponent attacker FORM vs ``my_body``
        — each in-play body plus the forms its line evolves INTO. v1 models a forward form as ONE hop."""
        ctx = getattr(self, "_opp_attack_context", None)
        if ctx is None:                                  # outside `_board`: without the hand-size
            ctx = {"atk_hand": opp.get("handCount", 0) or 0}   # scaler the credit drops to 0 — an
            # UNDER-read on a survival path, the one direction this must never fail in
        promo_bench = self._promotion_surcharge(opp)
        bodies = ([(a, 0) for a in (opp.get("active") or []) if a]
                  + [(b, promo_bench) for b in (opp.get("bench") or []) if b])
        for body, promo in bodies:
            energy = len(body.get("energies") or [])
            bid = body.get("id")
            for cid, evo_hops in [(bid, 0)] + [(fid, 1) for fid in self._forward_card_ids(bid)]:
                stat = self.stats.get(cid)
                if not stat:
                    continue
                aids = tuple(stat.attacks or ())
                if aids and all(self._attack_stat(a) is not None for a in aids):
                    for aid in aids:
                        yield (self._attack_cost(aid),
                               self.predicted_damage(cid, aid, my_body, bound="max", context=ctx),
                               energy, evo_hops, promo)
                    continue
                cost = getattr(stat, "minAttackCost", None) or 0    # unknown cost → 0 (assume payable)
                dmg = self.combat.card_level_damage(stat, my_body, context=ctx)
                yield (cost, dmg, energy, evo_hops, promo)

    def _promotion_surcharge(self, opp: dict) -> int:
        """The Threat Clock promotion surcharge (ADR-0045), WAIVED (0) when the opponent holds a
        promotion enabler — a revealed ``switch`` card, or a payable retreat on their current Active."""
        if self.functions:
            for zone in ("active", "bench", "discard"):
                for c in (opp.get(zone) or []):
                    cid = c.get("id") if c else None
                    if cid is not None and _PROMOTE_TAGS & set(self.functions.tags(cid)):
                        return 0
        active = next((a for a in (opp.get("active") or []) if a), None)
        if active and self.stats:
            st = self.stats.get(active.get("id"))
            if st and getattr(st, "retreatCost", 99) <= len(active.get("energies") or []):
                return 0
        return _PATH_BENCH_EXTRA

    def _their_harvest_clock(self, my_bench: list) -> dict:
        """``{bench index: first turn it falls to their RIDERS}`` over MY whole Bench. The rider
        budget is a property of the Bench, so it is solved ONCE for the Bench, never per body."""
        model = getattr(self, "_state_model", None)
        if model is None or not my_bench:
            return {}
        return model.theirs.bench_harvest_clock(
            list(my_bench), key_ids=self._harvest_key_ids(),
            opp_active=model.theirs.active_raw)

    def _their_path_items(self, opp: dict, ma: dict | None, my_bench: list,
                          read=None, gamma: float = 0.0) -> list:
        """``[(key, prize_value, turns, card_id), …]`` — MY bodies as targets on THEIR Prize Path. ONE
        derivation for both consumers, or `_bench_path_delta`'s subtraction compares two questions."""
        bench = [b for b in (my_bench or []) if b]
        harvest = self._their_harvest_clock(bench)
        items = []
        rows = ([(ma, 0, None)] if ma else []) + [(b, _PATH_BENCH_EXTRA, i)
                                                  for i, b in enumerate(bench)]
        for body, extra, index in rows:
            t = self._their_turns_to_ko(opp, body, read, gamma)
            t = None if t is None else t + extra
            if index is not None and index in harvest:
                t = float(harvest[index]) if t is None else min(t, float(harvest[index]))
            if t is not None:
                items.append((id(body), self._prize_value(body), t, body.get("id")))
        return items

    def _path_signals(self, obs, me: dict, opp: dict, ma: dict | None, oa: dict | None,
                      my_prizes: int, opp_prizes: int, read=None, gamma: float = 0.0,
                      *, carried=None) -> dict:
        """The per-decision two-sided Prize Path read (ADR-0040): my cheapest path over their bodies
        and theirs over mine. Re-derived every decision — a ranking objective, never a lock."""
        energy = len((ma or {}).get("energies") or [])
        rider = self._my_max_rider(ma) if getattr(self, "snipe_prize_reach", False) else 0
        mine = []
        reach = {}                       # snipe_prize_reach: rider-finish tie-break (bench only)
        for body, extra in ([(oa, 0)] if oa else []) + [(b, _PATH_BENCH_EXTRA)
                                                        for b in (opp.get("bench") or []) if b]:
            t = self._my_turns_to_ko(obs, (ma or {}).get("id"), energy, body)
            if t is not None:
                key = id(body)
                mine.append((key, self._prize_value(body), t + extra, body.get("id")))
                if rider > 0:            # a benched body (extra>0) my rider can finish rides ~free
                    hp = body.get("hp", 0) or 0   # alongside my main KOs; the Active (extra==0) is
                    reach[key] = math.ceil(hp / rider) if extra else 0.0   # hit by the main attack
        theirs = self._their_path_items(opp, ma, [b for b in (me.get("bench") or []) if b],
                                        read, gamma)
        my_keys, my_turns = prize_paths([(k, pv, t) for k, pv, t, _cid in mine], my_prizes,
                                        reach=reach or None)
        my_keys, my_turns = self._sticky_path(mine, my_prizes, my_keys, my_turns, carried=carried)
        their_keys, their_turns = prize_paths([(k, pv, t) for k, pv, t, _cid in theirs], opp_prizes)
        return {
            "my_path_turns": my_turns,
            "their_path_turns": their_turns,
            "race_ahead": (their_turns - my_turns
                           if my_turns is not None and their_turns is not None else None),
            "path_target_ids": frozenset(cid for k, _pv, _t, cid in mine
                                         if k in my_keys and cid is not None),
            "path_target_keys": frozenset(my_keys),   # ADR-0044: body IDENTITIES (id(body)) — card-id
                                                       # keying leaks between duplicate-species copies
            "their_path_my_ids": frozenset(cid for k, _pv, _t, cid in theirs
                                           if k in their_keys and cid is not None),
        }

    # ----------------------------------------------------------------------- the derived advisory phase
    # The methods below are thin live-path wrappers over the PURE cores above (ADR-0068 decision 2).

    def _derive_phase(self, base, race_ahead, active_doomed: bool, my_prizes: int,
                      favorability: float = 0.5, coverage: float = 0.0, *, carried=None):
        """The ADVISORY match phase (ADR-0040) — NEVER an eligibility gate, only band weights and the
        trace. ``carried`` makes the call PURE: no write-back of the hysteresis memory (ADR-0068)."""
        prev = (carried.get("phase_prev") if carried is not None
                else getattr(self, "_phase_prev", None))
        phase = _phase_from(prev, base, race_ahead, active_doomed, my_prizes, favorability,
                            coverage, enabled=getattr(self, "objectives_phases", False))
        if carried is None:
            self._phase_prev = phase                    # the live, in-order decision sequence
        return phase

    def _sticky_path(self, mine: list, my_prizes: int, best_keys, best_turns, *, carried=None):
        """Path stickiness (ADR-0040): keep last decision's path while it stays feasible and within
        ``_PATH_STICKY`` turns of the new cheapest. ``carried`` makes the call PURE (ADR-0068)."""
        prev = (carried.get("my_path_prev") if carried is not None
                else getattr(self, "_my_path_prev", None))
        keys, turns, new_prev = _sticky_path_from(prev, mine, my_prizes, best_keys, best_turns)
        if carried is None:
            self._my_path_prev = new_prev               # the live, in-order decision sequence
        return keys, turns

    # ---------------------------------------------------------------------- the Match Planner (ADR-0045)

    def plan_match(self, obs, board):
        """The Match Planner (ADR-0045) — this turn's Game Plan: mode, closed-form confidence, route
        and directed Turn Goal. Below ``_MATCH_CONFIDENCE_MIN`` the directed goal is WITHHELD."""
        from common.strategy.strategy import GamePlan
        mode = self._derive_mode(board)
        ma = next((p for p in (self._my_player(obs).get("active") or []) if p), None)
        survival = self._threat_clock(ma, self._opp_player(obs)) if ma else None
        confidence = plan_confidence(board.race_ahead, survival)
        goal = _MODE_GOAL.get(mode.name) if confidence >= _MATCH_CONFIDENCE_MIN else None
        return GamePlan(mode=mode, confidence=confidence, route=board.path_target_ids,
                        route_turns=board.my_path_turns, directed_goal=goal,
                        rationale=(f"{mode.name.lower()} @ {confidence:.2f}"
                                   + (f" -> {goal}" if goal else " (low-confidence: defer)")))

    def _derive_mode(self, board):
        """Grow the four-phase base to the six-mode Game-Plan axis (ADR-0045): STABILIZE→SACRIFICE with
        a ready bench backup; SETUP/RACE→STALL when clearly ahead but the win-condition is not online."""
        from common.strategy.strategy import Plan
        mode = board.phase
        if (mode == Plan.STABILIZE and board.bench_wincon_ready
                and board.race_ahead is not None and board.race_ahead >= 0):
            return Plan.SACRIFICE
        if (mode in (Plan.SETUP, Plan.RACE) and not board.line_ready
                and board.race_ahead is not None and board.race_ahead >= _STALL_AHEAD):
            return Plan.STALL
        return mode

    # ------------------------------------------------------------- per-option Path consumers (Context)

    def _target_on_path(self, obs, select, option, board) -> bool:
        """This snipe/damage target sits on MY cheapest Prize Path. Gated by ``objectives_path``;
        False when the path is unknown, so consumers stay silent."""
        if not getattr(self, "objectives_path", False):
            return False
        poke = self._option_pokemon(obs, select, option)
        if getattr(self, "snipe_prize_redundant", False):   # ADR-0044: exact body-identity keying —
            return poke is not None and id(poke) in board.path_target_keys   # duplicate-safe
        if not board.path_target_ids:
            return False
        cid = (poke or {}).get("id")
        return cid is not None and cid in board.path_target_ids

    def _promote_target_on_their_path(self, obs, select, option, board) -> bool:
        """At a promote/switch pick, THIS body sits on the opponent's cheapest Prize Path — promoting
        it walks it into the KO they most want (Path Denial). Gated by ``objectives_path``."""
        if not getattr(self, "objectives_path", False) or not board.their_path_my_ids:
            return False
        poke = self._option_pokemon(obs, select, option)
        cid = (poke or {}).get("id")
        return cid is not None and cid in board.their_path_my_ids

    def _bench_shortens_their_path(self, obs, select, option, stat, board) -> bool:
        """Playing THIS Pokémon to my Bench would strictly IMPROVE the opponent's cheapest Prize Path.
        DERIVED from :meth:`_bench_path_delta` — the sign of the magnitude, so the two cannot drift."""
        return self._bench_path_delta(obs, select, option, stat, board) > 0.0

    def _bench_path_delta(self, obs, select, option, stat, board) -> float:
        """**How much** benching this body shortens the opponent's cheapest Prize Path, in turns
        (ADR-0086 decision 5). 0 when it gifts nothing or `objectives_path` is off — never an estimate."""
        if not getattr(self, "objectives_path", False):
            return 0.0
        if not _reaches_my_bench(select, option) or not stat or getattr(stat, "hp", 0) <= 0:
            return 0.0
        if board.opp_prizes_remaining <= 0:
            return 0.0
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        ma = next((p for p in (me.get("active") or []) if p), None)
        cid = self._option_card_id(obs, select, option)
        hypo = {"id": cid, "hp": getattr(stat, "hp", 0), "energies": []}
        bench_after = [b for b in (me.get("bench") or []) if b] + [hypo]
        after = self._their_path_items(opp, ma, bench_after, board.read, board.posture_confidence)
        if not any(k == id(hypo) for k, _pv, _t, _cid in after):
            return 0.0                       # they cannot reach it at all — benching gifts nothing
        _keys, new_turns = prize_paths([(k, pv, t) for k, pv, t, _cid in after],
                                       board.opp_prizes_remaining)
        old_turns = board.their_path_turns
        if new_turns is None:
            return 0.0                       # still uncompletable even WITH the body — no gift
        if old_turns is None:
            # uncompletable -> completable, graded against the shared HORIZON so it dominates a
            # mere shortening without being unbounded
            return float(max(0.0, _HORIZON - new_turns))
        return float(max(0.0, old_turns - new_turns))
