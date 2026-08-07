"""The CLOCKS: turns until they knock me out, until I can afford my attack, until a body dies.

`incoming` takes an explicit energy policy. `UNCHARGED` is the strictly-pessimistic one, and the only
policy a catastrophe-grade survival boolean may take."""
from __future__ import annotations


from dataclasses import dataclass

from common.strategy.combat_math.policy import HARVEST_POSSIBLE, UNCHARGED


@dataclass(frozen=True)
class SurvivalClock:
    """ADR-0117: ``turns`` = first turn accumulated incoming reaches my HP, else ``max_t + 1``. ``exact``
    interpolates where inside that turn the crossing falls; opt-in, and repeats ``turns`` if none."""

    turns: int
    exact: float


class ClockMixin:
    """Turns-until: the survival and affordability clocks."""

    def doomed_incoming(self, ma: dict | None, oa: dict | None, *, charged: dict | None = None,
                        context: dict | None = None) -> int:
        """Worst incoming to ``ma`` from the opponent's Active ``oa`` at t=1. Returns the DAMAGE — the
        caller compares it to my HP. Gates on affordability, unlike :meth:`active_doomed` (ADR-0064 §2)."""
        if not oa:
            return 0
        return int(self.incoming(ma, [oa], 1, charged=charged, context=context))

    def reachable_incoming(self, my_body: dict | None, opp_bodies, *, forward_ids=None,
                           charged: dict | None = None, evo_min_energy: int = 0,
                           context: dict | None = None, my_benched: bool = False) -> int:
        """``incoming(t=1)`` (ADR-0064): worst W/R-adjusted damage the opponent could deal ``my_body``
        NEXT TURN, counting one development step. All arguments are documented on :meth:`incoming`."""
        return self.incoming(my_body, opp_bodies, 1, forward_ids=forward_ids, charged=charged,
                             my_benched=my_benched,
                             evo_min_energy=evo_min_energy, context=context)

    def _promotion_open(self, opp_bodies, opp_active, *, switch_enabler: bool = False) -> bool:
        """Can a BENCHED opponent body attack next turn (ADR-0071 decision 6) — retreat-then-attack is
        legal in ONE turn, so a benched attacker owes Energy, never tempo. Every leg fails OPEN."""
        if opp_active is None or switch_enabler:
            return True
        if not any(b is opp_active for b in opp_bodies):
            return True                               # KO'd Active — the replacement promotes for free
        st = self._card_stat(opp_active.get("id"))
        cost = getattr(st, "retreatCost", None) if st else None
        if cost is None:
            return True
        return len(opp_active.get("energies") or []) >= int(cost)

    def incoming(self, my_body: dict | None, opp_bodies, t: int = 1, *, forward_ids=None,
                 charged: dict | None = None, evo_min_energy: int = 0,
                 context: dict | None = None, my_benched: bool = False,
                 opp_active: dict | None = None, switch_enabler: bool = False) -> int:
        """Worst W/R-adjusted damage the opponent could deal ``my_body`` at turn ``t`` (ADR-0064); ``t`` is
        clamped ``>= 1`` and moves ONLY energy. ``charged``: None = ceiling, else ``{base_attach, burst_on_evo}``."""
        my_hp = (my_body or {}).get("hp", 0)
        if not (self.stats and my_hp):
            return 0
        turns = max(1, int(t))
        worst = 0
        for form_id, form_body, attached, grant, is_current in self._attacker_forms(
                opp_bodies, forward_ids=forward_ids, evo_min_energy=evo_min_energy,
                opp_active=opp_active, switch_enabler=switch_enabler):
            worst = max(worst, self._reach_form_damage(
                my_body, form_id, form_body, attached, charged, context,
                exclude=grant.get("same_lock") if is_current else None,
                bonus=grant.get("self_bonus", 0) if is_current else 0,
                attaches=turns, my_benched=my_benched, is_current=is_current))
        return worst

    def _attacker_forms(self, opp_bodies, *, forward_ids=None, evo_min_energy: int = 0,
                        opp_active=None, switch_enabler: bool = False):
        """Every opponent FORM that could attack next turn — ``(form_id, form_body, attached, grant,
        is_current)``. ONE enumeration for :meth:`incoming` and :meth:`_bench_payload`, so they cannot drift."""
        fwd = forward_ids if forward_ids is not None else self.forward_card_ids
        promotable = self._promotion_open(opp_bodies, opp_active,
                                          switch_enabler=switch_enabler)
        for body in opp_bodies:
            if not body:
                continue
            if not promotable and opp_active is not None and body is not opp_active:
                continue
            grant = self._grant(body) or {}
            attached = len(body.get("energies") or [])
            if not grant.get("self_lock"):            # a self-locked body still yields its FORWARD forms:
                yield body.get("id"), body, attached, grant, True    # evolving clears attack effects
            if attached < evo_min_energy:
                continue                              # bare pre-evo — not a credible evolving threat
            for fid in (fwd(body.get("id")) or ()):
                yield fid, {"id": fid, "energies": body.get("energies") or []}, attached, grant, False

    def _bench_rider(self, attack_id) -> int:
        """``attack_id``'s snipe + spread riders on ONE of my BENCHED bodies, summed. Riders ignore
        Weakness/Resistance (ADR-0022), so this is deliberately NOT routed through the W/R damage oracle."""
        return self.rider_snipe(attack_id) + self.rider_spread(attack_id)

    def _reach_form_damage(self, my_body, form_id, form_body, attached, charged, context, *,
                           exclude, bonus, is_current: bool, attaches: int = 1,
                           my_benched: bool = False) -> int:
        """Worst damage ONE attacker form deals ``my_body`` under ``charged``, given ``attaches`` attach-turns.
        ``my_benched`` = area at damage time (ADR-0070 §9); :data:`UNCHARGED` skips the gate on a CURRENT form."""
        stat = self._card_stat(form_id)
        if not stat:
            return 0
        if my_benched and self.is_tera((my_body or {}).get("id")):
            return 0                                  # Tera: no attack damage while Benched
        if charged is None or charged == UNCHARGED:
            unconditional = (charged == UNCHARGED and is_current)
            if not unconditional and not self._affords(stat, form_body, None, attached, attaches,
                                                       charged, is_current=is_current):
                return 0
            if my_benched:
                return max((self._bench_rider(aid) for aid in (stat.attacks or ())
                            if aid != exclude), default=0)
            dmg = self.predicted_max_damage(stat, my_body, exclude_attack=exclude, context=context)
            return int(dmg) + bonus if dmg else 0
        best = 0
        for aid in (stat.attacks or ()):
            if aid == exclude:
                continue
            if not self._affords(stat, form_body, aid, attached, attaches, charged,
                                 is_current=is_current):
                continue
            best = max(best, self._bench_rider(aid) if my_benched
                       else int(self.predicted_damage(form_id, aid, my_body,
                                                      bound="max", context=context)))
        if my_benched:
            return best
        return best + bonus if best else 0

    def turns_to_ko(self, attacker_id, energy: int, body: dict | None, *,
                    context: dict | None = None) -> float | None:
        """Feasibility turns for ``attacker_id`` (carrying ``energy``) to fell ``body`` — hp over its best
        affordable per-turn damage. None when it deals no damage. The KO Race's mechanical core (ADR-0040)."""
        import math
        hp = (body or {}).get("hp", 0)
        stat = self._card_stat(attacker_id)
        if not (hp and stat):
            return None
        best = 0
        for aid in (stat.attacks or ()):
            if self.attack_cost(aid) > energy:
                continue
            best = max(best, self.predicted_damage(attacker_id, aid, body, context=context))
        if best <= 0:
            return None
        return float(math.ceil(hp / best))

    def turns_to_afford(self, body: dict | None, *, forward_ids=None,
                        attaches_per_turn: int = 1, max_hops: int = 3,
                        typed: bool = False) -> int | None:
        """Earliest turn ``body``'s LINE is ARMED — biggest attack's cost payable, NOT lethality. None = unknown.
        MAX (never sum) of the energy-deficit and forward-hop legs; ``typed`` counts only colour-matched Energy."""
        from common import needs
        cid = (body or {}).get("id")
        st = self._card_stat(cid)
        if st is None:
            return None
        fwd = forward_ids if forward_ids is not None else self.forward_card_ids
        fwd_stats = [self._card_stat(f) for f in (fwd(cid) or ())]
        costs = [c for c in (getattr(s, "maxDamageCost", None)
                             for s in (st, *fwd_stats) if s is not None) if c is not None]
        if not costs:
            return None
        deepest = max(((s, getattr(s, "maxDamageCost", 0) or 0) for s in (st, *fwd_stats)
                       if s is not None and getattr(s, "maxDamageCost", None) is not None),
                      key=lambda pair: pair[1], default=(None, 0))[0]
        deficit = max(costs) - len((body or {}).get("energies") or [])
        if typed and deepest is not None:
            aid = max((getattr(deepest, "attacks", None) or ()), key=self.attack_damage, default=None)
            if aid is not None:
                matched, slots = self.matched_slots(body, aid)
                if slots:
                    deficit = slots - matched
        hops = max(self._forward_hop_depths(st, fwd_stats, max_hops=max_hops).values(), default=0)
        return needs.turns_to_ready(energy_deficit=deficit, evolve_hops=hops,
                                    attaches_per_turn=attaches_per_turn)

    def turns_to_ko_me(self, my_body: dict | None, opp_bodies, *, charged: dict | None = None,
                       max_t: int = 8, context: dict | None = None, my_benched: bool = False,
                       my_bench=(), key_ids=frozenset(), reading: str = HARVEST_POSSIBLE,
                       opp_active: dict | None = None, switch_enabler: bool = False) -> int:
        """Earliest turn the opponent's board can KO ``my_body``, else ``max_t + 1``. Damage ACCUMULATES
        (ADR-0071 decision 4). Defined as :meth:`survival_clock`'s ``.turns``, so the two cannot disagree."""
        return self.survival_clock(
            my_body, opp_bodies, charged=charged, max_t=max_t, context=context,
            my_benched=my_benched, my_bench=my_bench, key_ids=key_ids, reading=reading,
            opp_active=opp_active, switch_enabler=switch_enabler).turns

    def survival_clock(self, my_body: dict | None, opp_bodies, *, charged: dict | None = None,
                       max_t: int = 8, context: dict | None = None, my_benched: bool = False,
                       my_bench=(), key_ids=frozenset(), reading: str = HARVEST_POSSIBLE,
                       opp_active: dict | None = None,
                       switch_enabler: bool = False) -> SurvivalClock:
        """:meth:`turns_to_ko_me`'s accumulation at BOTH resolutions (see :class:`SurvivalClock`). The BENCH
        leg has no running total to interpolate, so it reports ``exact == turns``."""
        hp = (my_body or {}).get("hp", 0)
        if not hp:
            return SurvivalClock(max_t + 1, float(max_t + 1))
        if hp < 0:
            # Past dead: `dealt >= hp` at t=1 before anything is dealt, so interpolating would divide
            # by the turn's zero damage. The integer route answered 1 here before ADR-0117 and still must.
            return SurvivalClock(1, 1.0)
        horizon = max(1, int(max_t))
        if my_benched:
            bench = list(my_bench) or [my_body]
            try:
                me = next(i for i, b in enumerate(bench) if b is my_body)
            except StopIteration:                     # not in the snapshot — read it alone
                bench, me = [my_body], 0
            clock = self.bench_harvest_clock(bench, opp_bodies, charged=charged, max_t=horizon,
                                             key_ids=key_ids, reading=reading,
                                             opp_active=opp_active)
            turns = clock.get(me, horizon + 1)
            return SurvivalClock(turns, float(turns))
        dealt = 0
        for t in range(1, horizon + 1):
            hit = self.incoming(my_body, opp_bodies, t, charged=charged, context=context,
                                opp_active=opp_active, switch_enabler=switch_enabler)
            dealt += hit
            if dealt >= hp:
                # ``hit`` is necessarily > 0: the total was BELOW a non-zero ``hp`` before it, so ``hit``
                # is what crossed. A guard would only hide a future change to that invariant.
                return SurvivalClock(t, (t - 1) + (hp - (dealt - hit)) / hit)
        return SurvivalClock(horizon + 1, float(horizon + 1))
