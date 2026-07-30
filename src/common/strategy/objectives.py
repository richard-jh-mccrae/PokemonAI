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


def threat_turns(hp: int, forms) -> int | None:
    """The Threat Clock arithmetic (ADR-0045): the fewest opponent turns until a body of ``hp`` HP is
    Knocked Out by any of ``forms``.

    ``forms``: iterable of ``(cost, damage, energy, evo_hops, promo)`` per candidate attacker form —
    ``cost`` Energy the attack needs, ``damage`` per-hit damage (already Weakness/Resistance-adjusted
    vs my body), ``energy`` on the attacker now, ``evo_hops`` evolutions to reach this form, ``promo``
    the promotion surcharge (turns of friction to bring a benched attacker to the Active Spot; 0 for a
    true bench-snipe or a free promotion). Energy accrues at the ~1/turn rule floor (docs/rules.md §4).

    Per form: its FIRST attack lands on turn ``max(1, evo_hops, cost − energy) + promo`` — evolution and
    Energy attach run concurrently (one of each per turn) and the turn's attach counts toward that same
    turn's attack (docs/rules.md §4: attach precedes attack), so a 0-Energy body needing one more Energy
    for a KO attack still fires on the opponent's very next turn (turn 1); ``promo`` adds the benched
    body's promotion friction. Then ``ceil(hp/damage)`` hits accumulate one per turn, so it KOs on turn
    ``first_attack + hits − 1``. Returns the min over forms."""
    best = None
    for cost, damage, energy, evo_hops, promo in forms:
        if damage <= 0:
            continue                       # a form that can't dent my body never sets the clock
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
    """The Match Planner's closed-form per-strategy **confidence** ∈ [0,1] (ADR-0045): neutral 0.5, raised
    by the race margin (turns I'm ahead in the two-sided Prize Path) and by my Active's survival window
    (the Threat Clock turns before it is in danger). A legible LINEAR feasibility score — NOT a learned
    win-probability (the parked value model may refine it later, never be it). Weights are seeds matured
    via ladder corrections (the gauntlet is invalid — [[gauntlet-invalid-ladder-only]])."""
    c = 0.5
    if race_ahead is not None:
        c += 0.12 * race_ahead
    if survival is not None:
        c += 0.05 * (survival - 1)
    return max(0.0, min(1.0, c))


_PATH_BENCH_EXTRA = 1    # a benched body costs ~one extra turn to bring into KO range
                         # (gust / promote / wait) — the feasibility surcharge either side pays
_PROMOTE_TAGS = frozenset({"switch"})   # a card that swaps the opponent's OWN Active for a benched body
                                        # without paying a retreat — waives the Threat Clock promotion
                                        # surcharge (gust drags MY Active, so it does NOT promote theirs)

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

_PRED_LEAD = 2.0         # the γ-gated opponent OVERLAY (Tier 4, ADR-0040 §5): a Read-predicted,
                         # not-yet-fielded attacker joins the their-side math with a deploy lead of
                         # ceil(_PRED_LEAD / γ) turns — γ→1 ⇒ 2 turns out, γ→0 ⇒ infinitely far
                         # (structurally no regression on an unrecognized opponent), CONTINUOUS per
                         # the phase-grilling contract (no confidence cliff)


def prize_paths(bodies, prizes_needed: int, reach=None):
    """The cheapest Prize Path over ``bodies`` (ADR-0040): ``(frozenset(keys), total_turns)``.

    ``bodies``: ``((key, prize_value, turns), …)`` — each KO-able body, its prize yield ({1,2,3})
    and the feasibility turns to fell it. The cheapest path = the subset whose prize sum reaches
    ``prizes_needed`` in the fewest total turns (ties → fewer bodies, then bigger prize sum —
    prefer the compact overshoot). ≤6 bodies a side ⇒ ≤64 subsets, trivial by construction.

    ``reach`` (optional, snipe_prize_reach): ``{key: rider-reach-cost}`` — a PURE tie-break sorted
    AFTER (turns, bodies, prizes), so it can never change the chosen turn count (``my_path_turns``
    and ``race_ahead`` are untouched). Among prize-completing subsets tied on real turn cost, it
    prefers the one whose bench member my repeatable snipe rider finishes soonest — the body that
    rides to a KO alongside my main attacks instead of demanding a dedicated gust-up (83667237-107:
    Makuhita @ ⌈80/50⌉=2 riders beats Lunatone/Solrock @ ⌈110/50⌉=3, so the +1 prize lands on the
    rider-finishable body). ``None`` (or a key absent) contributes 0 → behaviour identical to before.

    ``prizes_needed <= 0`` → ``(frozenset(), 0.0)`` (already won). No subset reaches the count
    (their visible board is worth fewer prizes than I still need) → ``(frozenset(), None)`` —
    the path runs through bodies not yet in play, so consumers stay silent.
    """
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


def _phase_from(prev, base, race_ahead, active_doomed: bool, my_prizes: int,
                favorability: float, coverage: float, *, enabled: bool):
    """The advisory phase's PURE core (ADR-0068): previous label in, new label out.

    Extracted so the STABILIZE hysteresis stops being a side effect of building a board. The
    Schmitt trigger genuinely needs memory — enter clearly behind, leave only clearly ahead — but
    memory passed as an argument cannot leak a planner fork's hypothetical phase into the live game,
    where memory read off ``self`` did (and needed a hand-written guard at each site to stop it).
    """
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
    """Path stickiness's PURE core (ADR-0068): previous path in, ``(keys, turns, new_prev)`` out.

    Same rationale as :func:`_phase_from` — coherent multi-turn targeting needs the previous choice,
    but the caller decides whether to store the new one, so a simulated board cannot repoint the
    live turn's path.
    """
    current = frozenset(cid for k, _pv, _t, cid in mine if k in best_keys and cid is not None)
    if best_turns is not None and prev and prev != current:
        held = [(k, pv, t) for k, pv, t, cid in mine if cid in prev]
        keys2, turns2 = prize_paths(held, my_prizes)
        if turns2 is not None and turns2 <= best_turns + _PATH_STICKY:
            return keys2, turns2, frozenset(
                cid for k, _pv, _t, cid in mine if k in keys2 and cid is not None)
    return best_keys, best_turns, (current if best_turns is not None else prev)


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
            if self._attack_cost(aid) > board.my_active_energy:
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

    def _my_max_rider(self, ma: dict | None) -> int:
        """My Active's biggest bench-snipe rider (Jetting Blow 50) — the per-turn damage a snipe
        lands on a benched body WITHOUT a gust-up. Backs the ``snipe_prize_reach`` Prize-Path
        tie-break (a body finishable by repeated riders completes a prize alongside my main KOs).
        0 with no Active / no snipe attack."""
        stat = self.stats.get((ma or {}).get("id")) if (self.stats and ma) else None
        if not stat:
            return 0
        return max((self._rider_snipe(aid) for aid in (stat.attacks or ())), default=0)

    def _my_turns_to_ko(self, obs, my_active_id: int | None, energy: int, body: dict) -> float | None:
        """My feasibility turns to fell opponent ``body``: hp over my Active's best affordable
        per-turn damage vs THAT defender (weakness/riders per the oracle), plus the bench
        surcharge when it isn't their Active. None when I deal it no damage (infeasible)."""
        return self.combat.turns_to_ko(my_active_id, energy, body)

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

    # ------------------------------------------------------------------ the Threat Clock (ADR-0045)

    def _threat_clock(self, my_body: dict, opp: dict, read=None, gamma: float = 0.0) -> int | None:
        """The Threat Clock (ADR-0045): the fewest opponent turns until any of their attacker forms can
        afford AND land a KO of ``my_body`` in the Active Spot. Opponent-static, energy/evolution/
        promotion-aware, worst-case per-attack damage (Incoming's ceiling for coins). None when nothing
        they field or credibly evolve threatens the body. The defensive twin of the KO Race and the Match
        Planner's MULTI-TURN prep read (how many turns until each of my bodies is in danger, so we
        pre-snipe / pre-gust / heal ahead). Its Energy model is ~1 attach/turn (Read-γ-sharpenable for a
        burst-Energy archetype); it deliberately does NOT feed the survival-critical one-turn
        ``active_doomed`` boolean, which stays worst-case — a hidden Ignition-class burst must never be
        under-counted (the planner_6858 finding, docs/todo/incoming-affordability.md)."""
        hp = (my_body or {}).get("hp", 0)
        if not (hp and self.stats):
            return None
        return threat_turns(hp, self._threat_forms(my_body, opp))

    def _threat_forms(self, my_body: dict, opp: dict):
        """Yield ``(cost, damage, energy, evo_hops, promo)`` for every opponent attacker FORM vs
        ``my_body``. Each in-play body's current form and the forms its line forward-evolves INTO
        contribute, over the form's attacks — the **per-attack** oracle (worst-case, W/R-adjusted) when
        the attack records resolve (real cards, affordability-exact), else the **card-level** fallback
        (``CombatMath.card_level_damage`` at ``minAttackCost``; an unknown cost reads as 0 — payable).
        A benched body carries the promotion surcharge; the Active carries none. v1 models a forward form
        as ONE evolution hop (single-hop lines exact; multi-hop reads one turn optimistic — the
        defensive-safe direction, Read-γ-sharpenable)."""
        ctx = getattr(self, "_opp_attack_context", None)
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
                # ONE card-level fallback (Issue #213): `maxDamage` x W/R max'd with the hand-size
                # scaler. This used to be an EITHER/OR branch keyed off the Function Tag, while
                # the incoming read hand-rolled the same fact differently one module over.
                dmg = self.combat.card_level_damage(stat, my_body, context=ctx)
                yield (cost, dmg, energy, evo_hops, promo)

    def _promotion_surcharge(self, opp: dict) -> int:
        """The Threat Clock promotion surcharge (ADR-0045): ``_PATH_BENCH_EXTRA`` turns to bring a benched
        attacker to the Active Spot, WAIVED (0) when the opponent holds a promotion enabler — a ``switch``
        card revealed (active/bench/discard), or a cheap/free retreat on their current Active
        (``retreatCost`` ≤ its attached Energy). A stuck Active with no Switch keeps the full surcharge —
        exactly the human read that a benched threat behind a trapped Active is one turn further out."""
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

    def _path_signals(self, obs, me: dict, opp: dict, ma: dict | None, oa: dict | None,
                      my_prizes: int, opp_prizes: int, read=None, gamma: float = 0.0,
                      *, carried=None) -> dict:
        """The per-decision two-sided Prize Path read (ADR-0040): my cheapest path over their
        visible bodies and their cheapest path over mine, feasibility-weighted by turns-to-KO
        (`_my_turns_to_ko` / `_their_turns_to_ko` + the bench surcharge; the their-side sees
        Read-predicted attackers behind the γ-continuous lead — the Tier-4 overlay). Re-derived
        every decision — a ranking objective, never a lock. Returns the five Board field values."""
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
        theirs = []
        for body, extra in ([(ma, 0)] if ma else []) + [(b, _PATH_BENCH_EXTRA)
                                                        for b in (me.get("bench") or []) if b]:
            t = self._their_turns_to_ko(opp, body, read, gamma)
            if t is not None:
                theirs.append((id(body), self._prize_value(body), t + extra, body.get("id")))
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
            "path_target_keys": frozenset(my_keys),   # ADR-0044: on-path body IDENTITIES (id(body)),
                                                       # so a duplicate-species copy off my path is
                                                       # distinguished from the on-path one (card-id
                                                       # keying leaks between them)
            "their_path_my_ids": frozenset(cid for k, _pv, _t, cid in theirs
                                           if k in their_keys and cid is not None),
        }

    # --------------------------------------------------------------------- the derived advisory phase
    # The two Carried State members' PURE cores (ADR-0068 decision 2). Previous value in, new value
    # out — no `self`, so a derivation can never mutate Pilot state as a side effect of being
    # computed. The methods below are the thin live-path wrappers that choose whether to store.

    def _derive_phase(self, base, race_ahead, active_doomed: bool, my_prizes: int,
                      favorability: float = 0.5, coverage: float = 0.0, *, carried=None):
        """The ADVISORY match phase (ADR-0040, hardened by the 2026-07-05 phase grilling): a pure
        function of the objectives — memoryless (backwards transitions free) except the STABILIZE
        label's hysteresis (enter clearly behind at ``<= _STAB_ENTER``, leave only clearly ahead at
        ``>= _STAB_EXIT`` — the Schmitt trigger that kills near-threshold oscillation). CLOSE fires
        with the payoff online and ≤``_CLOSE_PRIZES`` prizes left (endgame: force the line).

        The **Tier-4 favorability input** (Lever A, γ-gated): a sufficiently-covered UNFAVORED Read
        relaxes the STABILIZE enter bar by ``_FAV_STAB_SHIFT`` turns — the straight race loses, so
        survive-first sooner. Coverage-gated (an unrecognized opponent's 0.5 prior drives nothing),
        so it never regresses an unknown matchup, and it moves only the ENTER threshold (the exit
        hysteresis is unchanged), so it can't cause phase flicker.

        NEVER an eligibility gate — consumed only by the small baseline_phases band weights and the
        trace; ``objectives_phases`` off → the readiness base (SETUP/RACE) unchanged.

        ``carried`` (a :class:`~common.state_model.CarriedState` snapshot) makes this call PURE: the
        hysteresis memory is read from the snapshot and the new value is NOT written back to the
        Pilot (ADR-0068 decision 2). The hypothetical/re-score paths pass it so a *simulated* board's
        phase can never leak into the live turn's memory — which is what the two hand-written
        snapshot/restore guards used to buy at every call site that remembered to write them. Live
        decisions pass nothing and keep the in-order write, byte-identically."""
        prev = (carried.get("phase_prev") if carried is not None
                else getattr(self, "_phase_prev", None))
        phase = _phase_from(prev, base, race_ahead, active_doomed, my_prizes, favorability,
                            coverage, enabled=getattr(self, "objectives_phases", False))
        if carried is None:
            self._phase_prev = phase                    # the live, in-order decision sequence
        return phase

    def _sticky_path(self, mine: list, my_prizes: int, best_keys, best_turns, *, carried=None):
        """Path stickiness (ADR-0040): when LAST decision's chosen path (by opponent card-id set) is
        still feasible and within ``_PATH_STICKY`` turns of the new cheapest, keep it — coherent
        multi-turn targeting without commitment (a clearly better path always wins; an infeasible
        previous path is dropped instantly).

        ``carried`` makes the call PURE (ADR-0068 decision 2): the previous path is read from the
        snapshot and the new one is not written back, so a hypothetical board cannot repoint the live
        turn's targeting. Live decisions pass nothing and keep the in-order write."""
        prev = (carried.get("my_path_prev") if carried is not None
                else getattr(self, "_my_path_prev", None))
        keys, turns, new_prev = _sticky_path_from(prev, mine, my_prizes, best_keys, best_turns)
        if carried is None:
            self._my_path_prev = new_prev               # the live, in-order decision sequence
        return keys, turns

    # ---------------------------------------------------------------------- the Match Planner (ADR-0045)

    def plan_match(self, obs, board):
        """The Match Planner (ADR-0045) — the Game Plan for this turn: the **mode** (the phase grown to
        six), the closed-form **confidence**, the **route** (my cheapest Prize Path target ids), and the
        **directed Turn Goal**. Runs first each turn (from ``_board``, after the objective signals are
        set); COMPUTE-ONLY until the seam wires it (S3) — nothing scores off it yet. Re-derived every
        decision, never a lock; when confidence is below ``_MATCH_CONFIDENCE_MIN`` the directed goal is
        WITHHELD (defer to the Turn Planner's own ladder + the tuned weights — the fallback)."""
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
        """Grow the four-phase base (``board.phase``) to the six-mode Game-Plan axis (ADR-0045):
        STABILIZE becomes **SACRIFICE** when my Active is doomed but a ready bench backup lets me trade it
        and race on prize math (the b4649 delay-wall); SETUP/RACE become **STALL** when I am clearly ahead
        in the race yet my win-condition is not online — build rather than over-press. Reuses the shipped
        phase derivation as the spine, so the advisory/gate-ban contract is inherited (no rule keys it)."""
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
        """This snipe/damage target sits on MY cheapest Prize Path (``board.path_target_ids``) —
        its KO advances the match win, not just the board (REQ-OBJ-0005). Gated by
        ``objectives_path``; False when the path is unknown (consumers stay silent)."""
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
        """At a promote/switch pick, THIS candidate body sits on the opponent's cheapest Prize Path
        (``board.their_path_my_ids``) — bringing it to the Active Spot walks it into the KO they
        most want (REQ-OBJ-0010, the promote half of Path Denial). Gated by ``objectives_path``."""
        if not getattr(self, "objectives_path", False) or not board.their_path_my_ids:
            return False
        poke = self._option_pokemon(obs, select, option)
        cid = (poke or {}).get("id")
        return cid is not None and cid in board.their_path_my_ids

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
