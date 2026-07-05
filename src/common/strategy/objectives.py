"""Tier 3 — Match Objectives (ADR-0040): the KO Race.

Closed-form turns-to-KO arithmetic over attack SEQUENCES — the opponent-static multi-turn read at
the same epistemic tier as Incoming/Survival Window (docs/architecture/tier-3-match-objectives.md).
Against a standing wall (no affordable attack KOs this turn) every min-turn sequence fells the
wall in the same number of turns, so the biggest single hit is fake value; what actually differs
between sequences is the incidental chip (bench-snipe / spread riders) they bank along the way —
the `a21472` class: 2×Jetting+Nebula = 450 ≥ 440 in the same three turns as Nebula-first, plus
100 chip onto the benched Riolu.

`race_values` is the pure math; `ObjectivesMixin` prices an ATTACK option as per-turn wall
progress plus the (tempo-discounted) chip of the best min-turn sequence STARTING with it,
consumed by `Pilot._tactical` in place of the greedy single-hit damage. Kill-switch
`objectives_race` (wired in every agent's main.py; an overlay can force it off for A/B).
"""
from __future__ import annotations

import math

from common.strategy.context import _PLAY

_RACE_HORIZON = 8        # give up beyond this many turns — no wall math on an unbounded grind
_RACE_LATER_CHIP = 0.9   # later-turn chip is slightly less certain than chip banked THIS turn
                         # (the target can evolve/retreat/heal) — the tempo tiebreak that prefers
                         # starting the chip now over an equal-chip sequence that defers it


def race_values(attacks: dict, hp: int, horizon: int = _RACE_HORIZON) -> dict:
    """The KO Race table vs a standing wall: ``{attack_id: (t_star, rest_chip)}``.

    ``attacks``: ``{attack_id: (damage, chip)}`` — exact per-use damage vs the wall and the
    face-value incidental bench chip the attack banks per use. ``hp``: the wall's remaining HP.

    ``t_star`` = fewest of my turns to fell the wall in a sequence STARTING with this attack
    (following up with the hardest hitter is always turn-optimal, so
    ``t_star = 1 + ceil((hp - dmg) / max_dmg)``). ``rest_chip`` = the max total chip of the
    remaining ``t_star - 1`` attacks over min-turn sequences starting with it (a small
    memoized DP — attacks reuse freely; an early kill inside a min-turn sequence is impossible
    by minimality, so every hit lands on the live wall). Attacks that cannot start a
    within-``horizon`` KO are absent; empty when nothing deals damage.
    """
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


_PATH_BENCH_EXTRA = 1    # a benched body costs ~one extra turn to bring into KO range
                         # (gust / promote / wait) — the feasibility surcharge either side pays

_STAB_ENTER = -1.0       # STABILIZE hysteresis (ADR-0040): enter when clearly BEHIND in the race …
_STAB_EXIT = 1.0         # … leave only when clearly AHEAD — between the two, hold the previous label
_CLOSE_PRIZES = 2        # CLOSE: payoff online and at most this many of my prizes left to take

_PRED_LEAD = 2.0         # the γ-gated opponent OVERLAY (Tier 4, ADR-0040 §5): a Read-predicted,
                         # not-yet-fielded attacker joins the their-side math with a deploy lead of
                         # ceil(_PRED_LEAD / γ) turns — γ→1 ⇒ 2 turns out, γ→0 ⇒ infinitely far
                         # (structurally no regression on an unrecognized opponent), CONTINUOUS per
                         # the phase-grilling contract (no confidence cliff)


def prize_paths(bodies, prizes_needed: int):
    """The cheapest Prize Path over ``bodies`` (ADR-0040): ``(frozenset(keys), total_turns)``.

    ``bodies``: ``((key, prize_value, turns), …)`` — each KO-able body, its prize yield ({1,2,3})
    and the feasibility turns to fell it. The cheapest path = the subset whose prize sum reaches
    ``prizes_needed`` in the fewest total turns (ties → fewer bodies, then bigger prize sum —
    prefer the compact overshoot). ≤6 bodies a side ⇒ ≤64 subsets, trivial by construction.

    ``prizes_needed <= 0`` → ``(frozenset(), 0.0)`` (already won). No subset reaches the count
    (their visible board is worth fewer prizes than I still need) → ``(frozenset(), None)`` —
    the path runs through bodies not yet in play, so consumers stay silent.
    """
    if prizes_needed <= 0:
        return frozenset(), 0.0
    items = tuple(bodies)
    best = None                      # (turns, len, -prizes, keys)
    for mask in range(1 << len(items)):
        prizes = turns = n = 0
        keys = []
        for i, (key, pv, t) in enumerate(items):
            if mask & (1 << i):
                prizes, turns, n = prizes + pv, turns + t, n + 1
                keys.append(key)
        if prizes >= prizes_needed:
            cand = (turns, n, -prizes, frozenset(keys))
            if best is None or cand[:3] < best[:3]:
                best = cand
    if best is None:
        return frozenset(), None
    return best[3], float(best[0])


class ObjectivesMixin:
    """Pilot-side Tier-3 Match Objectives (ADR-0040). Depends on Pilot internals (``stats``,
    ``attack_costs``, ``predicted_damage``, the rider lookups, ``_opp_active``), so it is mixed
    into the Pilot like the PlannerMixin."""

    def _race_attack_tactical(self, obs, board, attack_id, dmg_ctx) -> float | None:
        """The KO-Race price of this ATTACK option against a standing wall, or None to keep the
        greedy single-hit price (REQ-OBJ-0001).

        Fires only when ``objectives_race`` is on and NO affordable attack KOs the opponent's
        Active this turn (``board.active_can_ko`` false — the wall condition). Price =
        ``hp / t_star`` per-turn wall progress (equal for every min-turn starter, lower for a
        slower starter) + this attack's own chip + the tempo-discounted best rest-of-sequence
        chip, both capped by the opponent's total benched HP (chip beyond the bench pool lands
        nowhere). Sequences are over my Active's CURRENTLY affordable attacks (opponent-static,
        energy assumed non-decreasing — a discard-cost Energy nuance is out of v1 scope)."""
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
            if self.attack_costs.get(aid, 99) > board.my_active_energy:
                continue
            d = self.predicted_damage(board.my_active_id, aid, opp, context=dmg_ctx)
            if d <= 0:
                continue
            chip = (self._rider_snipe(aid) + self._rider_spread(aid)) if bench_pool else 0
            table[aid] = (d, chip)
        vals = race_values(table, hp)
        if attack_id not in vals:
            return None
        t_star, rest_chip = vals[attack_id]
        own_chip = min(table[attack_id][1], bench_pool)
        rest = min(rest_chip, max(0, bench_pool - own_chip))
        return hp / t_star + own_chip + _RACE_LATER_CHIP * rest

    # ------------------------------------------------------ the two-sided Prize Path (Board signals)

    def _my_turns_to_ko(self, obs, my_active_id: int | None, energy: int, body: dict) -> float | None:
        """My feasibility turns to fell opponent ``body``: hp over my Active's best affordable
        per-turn damage vs THAT defender (weakness/riders per the oracle), plus the bench
        surcharge when it isn't their Active. None when I deal it no damage (infeasible)."""
        hp = (body or {}).get("hp", 0)
        stat = self.stats.get(my_active_id) if (self.stats and my_active_id) else None
        if not (hp and stat):
            return None
        best = 0
        for aid in (stat.attacks or ()):
            if self.attack_costs.get(aid, 99) > energy:
                continue
            best = max(best, self.predicted_damage(my_active_id, aid, body))
        if best <= 0:
            return None
        return float(math.ceil(hp / best))

    def _their_turns_to_ko(self, opp: dict, body: dict, read=None, gamma: float = 0.0) -> float | None:
        """Their feasibility turns to fell MY ``body``: hp over the biggest per-turn damage any of
        their in-play Pokémon's attacks deal it (worst-case ceiling — affordability not charged,
        matching Incoming's pessimistic read), OR a Read-PREDICTED attacker's damage behind its
        γ-continuous deploy lead (the Tier-4 overlay: the second Mega Lucario is priced before it
        is benched — ``ceil(_PRED_LEAD / γ)`` extra turns, unrecognized ⇒ never competitive).
        None when nothing they show (or credibly threaten) damages it."""
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
                    continue                       # on the board already — the visible pass owns it
                stat = self.stats.get(intel.cardId)
                d = self._predicted_max_damage(stat, body) if stat else 0
                if d > 0:
                    t = math.ceil(hp / d) + lead
                    predicted = t if predicted is None else min(predicted, t)
        if visible is None:
            return float(predicted) if predicted is not None else None
        return float(min(visible, predicted)) if predicted is not None else visible

    def _path_signals(self, obs, me: dict, opp: dict, ma: dict | None, oa: dict | None,
                      my_prizes: int, opp_prizes: int, read=None, gamma: float = 0.0) -> dict:
        """The per-decision two-sided Prize Path read (ADR-0040): my cheapest path over their
        visible bodies and their cheapest path over mine, feasibility-weighted by turns-to-KO
        (`_my_turns_to_ko` / `_their_turns_to_ko` + the bench surcharge; the their-side sees
        Read-predicted attackers behind the γ-continuous lead — the Tier-4 overlay). Re-derived
        every decision — a ranking objective, never a lock. Returns the five Board field values."""
        energy = len((ma or {}).get("energies") or [])
        mine = []
        for body, extra in ([(oa, 0)] if oa else []) + [(b, _PATH_BENCH_EXTRA)
                                                        for b in (opp.get("bench") or []) if b]:
            t = self._my_turns_to_ko(obs, (ma or {}).get("id"), energy, body)
            if t is not None:
                mine.append((id(body), self._prize_value(body), t + extra, body.get("id")))
        theirs = []
        for body, extra in ([(ma, 0)] if ma else []) + [(b, _PATH_BENCH_EXTRA)
                                                        for b in (me.get("bench") or []) if b]:
            t = self._their_turns_to_ko(opp, body, read, gamma)
            if t is not None:
                theirs.append((id(body), self._prize_value(body), t + extra, body.get("id")))
        my_keys, my_turns = prize_paths([(k, pv, t) for k, pv, t, _cid in mine], my_prizes)
        their_keys, their_turns = prize_paths([(k, pv, t) for k, pv, t, _cid in theirs], opp_prizes)
        return {
            "my_path_turns": my_turns,
            "their_path_turns": their_turns,
            "race_ahead": (their_turns - my_turns
                           if my_turns is not None and their_turns is not None else None),
            "path_target_ids": frozenset(cid for k, _pv, _t, cid in mine
                                         if k in my_keys and cid is not None),
            "their_path_my_ids": frozenset(cid for k, _pv, _t, cid in theirs
                                           if k in their_keys and cid is not None),
        }

    # --------------------------------------------------------------------- the derived advisory phase

    def _derive_phase(self, base, race_ahead, active_doomed: bool, my_prizes: int):
        """The ADVISORY match phase (ADR-0040, hardened by the 2026-07-05 phase grilling): a pure
        function of the objectives — memoryless (backwards transitions free) except the STABILIZE
        label's hysteresis (enter clearly behind at ``<= _STAB_ENTER``, leave only clearly ahead at
        ``>= _STAB_EXIT`` — the Schmitt trigger that kills near-threshold oscillation). CLOSE fires
        with the payoff online and ≤``_CLOSE_PRIZES`` prizes left (endgame: force the line). NEVER an
        eligibility gate — consumed only by the small baseline_phases band weights and the trace;
        ``objectives_phases`` off → the readiness base (SETUP/RACE) unchanged."""
        from common.strategy.strategy import Plan
        if not getattr(self, "objectives_phases", False):
            self._phase_prev = base
            return base
        phase = base
        if race_ahead is not None and active_doomed:
            if getattr(self, "_phase_prev", None) == Plan.STABILIZE:
                if race_ahead < _STAB_EXIT:            # keep stabilizing until clearly ahead
                    phase = Plan.STABILIZE
            elif race_ahead <= _STAB_ENTER:            # enter only clearly behind
                phase = Plan.STABILIZE
        if base == Plan.RACE and 0 < my_prizes <= _CLOSE_PRIZES:
            phase = Plan.CLOSE                         # endgame overrides: force the finishing line
        self._phase_prev = phase
        return phase

    # ------------------------------------------------------------- per-option Path consumers (Context)

    def _target_on_path(self, obs, select, option, board) -> bool:
        """This snipe/damage target sits on MY cheapest Prize Path (``board.path_target_ids``) —
        its KO advances the match win, not just the board (REQ-OBJ-0005). Gated by
        ``objectives_path``; False when the path is unknown (consumers stay silent)."""
        if not getattr(self, "objectives_path", False) or not board.path_target_ids:
            return False
        poke = self._option_pokemon(obs, select, option)
        cid = (poke or {}).get("id")
        return cid is not None and cid in board.path_target_ids

    def _bench_shortens_their_path(self, obs, select, option, stat, board) -> bool:
        """Playing THIS Pokémon to my Bench would strictly IMPROVE the opponent's cheapest Prize
        Path — completing a previously-uncompletable route or shortening the existing one (the
        'benching the second Mega hands them their exact 6' case — ADR-0040 Path Denial,
        REQ-OBJ-0006). A soft per-option signal; gated by ``objectives_path``."""
        if not getattr(self, "objectives_path", False):
            return False
        if option.get("type") != _PLAY or not stat or getattr(stat, "hp", 0) <= 0:
            return False
        if board.opp_prizes_remaining <= 0:
            return False
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        ma = next((p for p in (me.get("active") or []) if p), None)
        theirs = []
        for body, extra in ([(ma, 0)] if ma else []) + [(b, _PATH_BENCH_EXTRA)
                                                        for b in (me.get("bench") or []) if b]:
            t = self._their_turns_to_ko(opp, body)
            if t is not None:
                theirs.append((id(body), self._prize_value(body), t + extra))
        cid = self._option_card_id(obs, select, option)
        hypo = {"id": cid, "hp": getattr(stat, "hp", 0)}
        t_new = self._their_turns_to_ko(opp, hypo)
        if t_new is None:
            return False                     # they can't even damage it — benching gifts nothing
        _keys, new_turns = prize_paths(
            theirs + [("hypo", self._prize_value(hypo), t_new + _PATH_BENCH_EXTRA)],
            board.opp_prizes_remaining)
        old_turns = board.their_path_turns
        if new_turns is None:
            return False
        return old_turns is None or new_turns < old_turns
