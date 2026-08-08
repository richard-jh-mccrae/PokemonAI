"""The forward LINE: what evolving a body would be worth, how many hops away the payoff is, its prizes.

Energy on a pre-evolution is BANKED, not spent — evolving keeps attached cards — so a forward read
prices the payoff attack, never the pre-evolution's own."""
from __future__ import annotations


from typing import NamedTuple


class LinePrize(NamedTuple):
    """:meth:`CombatMath.forward_line_prize`'s answer (ADR-0119 decision 2). NAMED because both fields
    run small ints — a transposed unpack is type-correct, range-correct, and silently wrong."""

    #: Greatest `prize_value` anywhere in the line INCLUDING the card itself. 0 for an unknown card.
    prize: int
    #: Evolutions from the card to that form. 0 when the card already IS the best-prize form.
    hops: int


class ForwardLineMixin:
    """What a body's evolved form would be worth."""

    @staticmethod
    def _forward_hop_depths(st, fwd_stats, *, max_hops: int = 3) -> dict:
        """``{forward form NAME: evolutions above ``st``}`` over the closure ``fwd_stats``. Keyed by NAME
        because evolution is BY NAME; a chain not grounding out within ``max_hops`` is OMITTED (fail-closed)."""
        parent = {s.name: getattr(s, "evolvesFrom", None) for s in fwd_stats
                  if s is not None and s.name}
        own = getattr(st, "name", None)
        depths: dict = {}
        for name in parent:
            d, n = 0, name
            while n and n != own and d <= max_hops:
                d, n = d + 1, parent.get(n)
            if n == own:
                depths[name] = d
        return depths

    def forward_payoff_terms(self, card_id, *, forward_ids=None, max_hops: int = 3) -> tuple:
        """``(owed_damage, hops)`` — the ForwardPayoff legs computable from CARD KNOWLEDGE alone, for
        either side (Issue #285). ``reachable`` is deliberately absent: it needs zones. ``(0.0, 0)`` = no claim."""
        st = self._card_stat(card_id) if card_id is not None else None
        if st is None:
            return (0.0, 0)
        fwd = forward_ids if forward_ids is not None else self.forward_card_ids
        # SORTED because the closure is a frozenset and the scan below breaks ties on `>`: set-iteration
        # order would otherwise pick the hops among two forms owing equal damage at different depths.
        fwd_stats = [self._card_stat(f) for f in sorted(fwd(card_id) or ())]
        depths = self._forward_hop_depths(st, fwd_stats, max_hops=max_hops)
        own = float(getattr(st, "maxDamage", 0) or 0)
        best_owed, best_hops = 0.0, 0
        for s in fwd_stats:
            if s is None or not s.name or s.name not in depths:
                continue
            owed = max(0.0, float(getattr(s, "maxDamage", 0) or 0) - own)
            if owed > best_owed:
                best_owed, best_hops = owed, depths[s.name]
        return (best_owed, best_hops)

    def forward_line_prize(self, card_id, *, forward_ids=None, max_hops: int = 3) -> LinePrize:
        """:class:`LinePrize` — the greatest prize value anywhere in ``card_id``'s line INCLUDING itself,
        and the hops to THAT form (ADR-0119 decision 2). Card knowledge only; ``(0, 0)`` = no claim."""
        st = self._card_stat(card_id) if card_id is not None else None
        if st is None:
            return LinePrize(0, 0)
        fwd = forward_ids if forward_ids is not None else self.forward_card_ids
        # SORTED for the reason `forward_payoff_terms` states: prize values run {1, 2, 3}, so ties are
        # routine, and the sort makes the SHALLOWER of two equal-prize forms win deterministically.
        fwd_stats = [self._card_stat(f) for f in sorted(fwd(card_id) or ())]
        depths = self._forward_hop_depths(st, fwd_stats, max_hops=max_hops)
        best_prize, best_hops = int(st.prize_value), 0
        for s in fwd_stats:
            if s is None or not s.name or s.name not in depths:
                continue
            if int(s.prize_value) > best_prize:
                best_prize, best_hops = int(s.prize_value), depths[s.name]
        return LinePrize(best_prize, best_hops)

    def _bench_payload_pairs(self, opp_bodies, t: int, *, charged=None, opp_active=None,
                             switch_enabler: bool = False) -> set:
        """Every ``(snipe, spread)`` rider payload their board could put on my Bench at turn ``t``. The
        halves stay SPLIT because they allocate differently — snipe indivisible, spread not (ADR-0071)."""
        pairs = set()
        for form_id, form_body, attached, grant, is_current in self._attacker_forms(
                opp_bodies, opp_active=opp_active, switch_enabler=switch_enabler):
            stat = self._card_stat(form_id)
            if not stat:
                continue
            for aid in (stat.attacks or ()):
                if is_current and aid == grant.get("same_lock"):
                    continue
                if not self._affords(stat, form_body, aid, attached, t, charged,
                                     is_current=is_current):
                    continue
                pair = (self.rider_snipe(aid), self.rider_spread(aid))
                if any(pair):
                    pairs.add(pair)
        return pairs
