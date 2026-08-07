"""The forward LINE: what evolving a body would be worth, how many hops away the payoff is, and what prizes the line
carries.

Energy on a pre-evolution is BANKED, not spent — evolving keeps attached cards — so a forward read prices the payoff
attack, never the pre-evolution's own."""
from __future__ import annotations


from typing import NamedTuple


class LinePrize(NamedTuple):
    """The greatest prize value in a card's evolution line, and how far away that form is —
    :meth:`CombatMath.forward_line_prize`'s answer (ADR-0119 decision 2).

    NAMED rather than a bare 2-tuple, for the reason `state_model.ForwardPayoff` gives and MORE
    sharply than that one needs it. `ForwardPayoff` argues a swap would be caught because two of its
    three fields are numbers and the third is a flag. No such luck here: ``prize`` runs {0,1,2,3} and
    ``hops`` runs {0..3}, so a transposed unpack is type-correct, range-correct, and silently wrong —
    it would discount a line by its own prize value and price it by its distance. Six call sites
    unpack this.

    Deliberately NOT the same shape as `forward_payoff_terms`' bare ``(owed_damage, hops)`` twin:
    that one's fields differ in type and magnitude, so it does not carry this hazard."""

    #: Greatest `prize_value` anywhere in the line INCLUDING the card itself. 0 for an unknown card.
    prize: int
    #: Evolutions from the card to that form. 0 when the card already IS the best-prize form.
    hops: int


class ForwardLineMixin:
    """What a body's evolved form would be worth."""

    @staticmethod
    def _forward_hop_depths(st, fwd_stats, *, max_hops: int = 3) -> dict:
        """``{forward form NAME: how many evolutions it is above ``st``}`` — the ``evolvesFrom``
        name-chain depth, over the forward closure ``fwd_stats``.

        Extracted from :meth:`turns_to_afford`, which still takes the ``max`` of these values as its
        forward-hop leg, so the rule that reads *"how far is that form"* has ONE home. Issue #285
        needed the same walk to answer a DIFFERENT aggregation — the hops to the best-DAMAGE form,
        not to the deepest one — and re-deriving it there would have left two copies of a depth rule
        free to drift, which is the failure :meth:`card_level_damage` was extracted to end.

        Keyed by NAME rather than by card id because evolution in this set is BY NAME (`docs/rules.md`
        §4 — the card names its previous stage), which is also why the pool-level forward index is
        name-keyed (`scouting/forward_index.py`). Every printing of a name therefore shares one depth.

        ``max_hops`` guards a malformed chain rather than a real evolution cycle — the rules cannot
        produce one — and a form whose chain does not ground out on ``st`` within it is OMITTED, which
        is the fail-closed direction: no depth claimed for a line we cannot walk."""
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
        """``(owed_damage, hops)`` — the two legs of a :class:`state_model.ForwardPayoff` that are
        computable from CARD KNOWLEDGE alone, for **either** side's body (Issue #285, POC-T3.5).

        ``owed_damage`` is the best printed damage anywhere in ``card_id``'s forward closure MINUS the
        card's own, floored at 0 (a forward form that hits softer owes nothing); ``hops`` is how many
        evolutions away that best form is. ``(0.0, 0)`` for an unknown card or a dead-end line — no
        claim, and no phantom credit.

        **The third leg, ``reachable``, is deliberately absent**, because it is not card knowledge:
        it asks whether a copy of that form is still gettable, which needs a decklist plus the zones.
        `MySide.forward_payoff` answers it from `unseen_counts` + `hand_ids`; `TheirSide` cannot and
        fails OPEN. Returning a two-tuple keeps that asymmetry at the seam where it is decided rather
        than letting this oracle invent an answer for a side that has none.

        ``forward_ids`` is the same availability-gate callable :meth:`turns_to_afford` takes, so a
        caller that has narrowed the closure (a matched-Read rep list, `CURRENT_FORMS_ONLY`) gets the
        narrowed reading here too. None → :meth:`forward_card_ids`, the pool-level index (ADR-0020).

        The damage read is the PRINTED ``maxDamage``, matching `MySide.forward_payoff` exactly so the
        two sides price one line the same way. It is therefore blind in the way the printed index is
        blind — Alakazam's whole threat is a scaling term and reads 10 — and the board-priced
        alternative (:meth:`forward_threat_ceiling`) is deliberately NOT substituted here: it would
        give the opponent's line a different valuation basis from my own for the same card."""
        st = self._card_stat(card_id) if card_id is not None else None
        if st is None:
            return (0.0, 0)
        fwd = forward_ids if forward_ids is not None else self.forward_card_ids
        # SORTED because the closure is a frozenset and the scan below breaks ties on `>`: with two
        # forward forms owing the same damage at different depths, set-iteration order would pick the
        # hops. Swept the pool — 457 cards have a non-empty closure and NONE ties — so this is
        # insurance rather than a fix, and it is here rather than in `turns_to_afford` because that
        # oracle is ADR-0070's and must stay byte-identical.
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
        """:class:`LinePrize` — the greatest prize value anywhere in ``card_id``'s line
        INCLUDING itself, and how many evolutions away that form is (ADR-0119 decision 2).

        The prize a body's LINE ultimately presents, which its own `prize_value` cannot distinguish:
        Staryu and a dead-end Basic are both 1-prize cards, but one of them is a Mega Starmie ex one
        hop from now. ``(0, 0)`` for an unknown card — no claim, and no phantom credit.

        **The hops are hops to the best-PRIZE form, and that is why this is not a reading of
        :meth:`forward_payoff_terms`.** That one returns the distance to the best-DAMAGE form (Issue
        #285), and the two diverge on any line whose biggest attacker is not its biggest prize. Both
        take their depths from :meth:`_forward_hop_depths`, which stays the ONE home for *"how far is
        that form"* — this is its third aggregation, not a fourth walk.

        CARD KNOWLEDGE ONLY, like the damage twin: `evolvesFrom` chains and `prize_value`, both of
        which the stat cache holds for every card in the set. No board, no zones, no reachability —
        the availability question belongs to the caller, and on the opponent's side there is no
        sound answer to it anyway (`TheirSide.forward_payoff` fails OPEN for the same reason)."""
        st = self._card_stat(card_id) if card_id is not None else None
        if st is None:
            return LinePrize(0, 0)
        fwd = forward_ids if forward_ids is not None else self.forward_card_ids
        # SORTED for the reason `forward_payoff_terms` states one method up: the closure is a
        # frozenset and the scan breaks ties on `>`, so set-iteration order would otherwise pick the
        # hops among two equal-prize forms at different depths. Here ties are NOT hypothetical the
        # way they are for damage — prize values run {1, 2, 3}, so any line with two ex forms ties —
        # and the sort makes the shallower one win deterministically, which is the reading that
        # under-discounts least.
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
        """Every ``(snipe, spread)`` rider payload their board could put on my Bench at turn ``t``.

        Attacking ends their turn (rules.md §5), so a turn's bench damage is ONE attack's payload
        from ONE attacker — but the CHOICE of attack belongs to the harvest solver, not to a
        pre-filter here, so this returns all of them. The two halves stay SPLIT because they
        allocate differently: the snipe is indivisible and the spread is not (ADR-0071 decision 2)."""
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
