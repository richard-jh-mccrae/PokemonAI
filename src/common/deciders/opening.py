"""The setup-turn reads: what can legally open, and which starter the deck wants Active."""
from __future__ import annotations


from common.strategy.context import _OPENER_TAG, _SETUP_ACTIVE



class OpeningMixin:
    """Who can open, and who should."""

    def _hand_startable(self, hand: list) -> bool:
        """Can a card in hand take the Active Spot WITHOUT being a Basic — the Ability route only. Scoped to
        the mulligan keep, where a hand holding any Basic never reaches the prompt (rulebook L224)."""
        return any(self._opens_from_hand(c.get("id")) for c in hand if c)

    def _is_startable_body(self, cid: int | None) -> bool:
        """Can this card legally take the Active Spot at the pregame Set-Up pick — a Basic, or an
        `_opens_from_hand`? The universe `Strategy.starter_priority` must rank COMPLETELY (ADR-0079)."""
        if cid is None or not self.stats:
            return False
        st = self.stats.get(cid)
        if not st or not st.is_pokemon:
            return False
        return not st.evolvesFrom or self._opens_from_hand(cid)

    def _opens_from_hand(self, cid: int | None) -> bool:
        """The `opener` Function Tag: this card's own Ability puts it into the Active Spot from hand. The ONE
        definition of that route — both readers below derive from it so they cannot drift."""
        return bool(self.functions) and cid is not None and _OPENER_TAG in self.functions.tags(cid)

    def _opener_marginal(self, cid: int | None, hand_ids) -> float:
        """**Opener Marginal** (ADR-0081 d4), in DAMAGE: `maxDamage(payoff) - maxDamage(cid)` when a card in
        hand evolves from `cid` AND is a declared Line payoff. Matches on `evolvesFrom` NAME, not id."""
        if cid is None or not self.stats or not hand_ids:
            return 0.0
        st = self.stats.get(cid)
        if not st or not st.name:
            return 0.0
        payoffs = self._wincon_payoff_ids()
        if not payoffs:
            return 0.0
        best = 0.0
        for hid in hand_ids:
            if hid not in payoffs:
                continue
            hst = self.stats.get(hid)
            if hst and hst.evolvesFrom == st.name:
                best = max(best, float(hst.maxDamage - st.maxDamage))
        return best

    def _route_only_at_setup(self, cid: int | None) -> bool:
        """Is the pregame Set-Up pick this body's ONLY route into play (ADR-0081 d1)? Computed off the
        DECKLIST, so adding the previous stage lifts it by itself. **Fails CLOSED** — pins when it cannot tell."""
        if cid is None:
            return False
        if not (self.stats and self.deck and self.functions):
            return True                                  # cannot tell -> freeze the declaration
        if not self._opens_from_hand(cid):
            return False                                 # not route-restricted: an ordinary body
        st = self.stats.get(cid)
        if st is None:
            return True                                  # opener-tagged but unknown -> pin
        if not st.evolvesFrom:
            return False                                 # a Basic can always be benched instead
        return st.evolvesFrom not in self._deck_body_names()

    def _effective_starter_order(self, obs: dict, sp: list) -> list:
        """**Effective Starter Order** (ADR-0081 d5): pinned entries hold their declared slot; unpinned ones
        re-sort among the rest by (Opener Marginal desc, declared rank asc). STRUCTURAL, never scored."""
        marginals = {}
        hand_ids = [c.get("id") for c in ((self._my_player(obs) or {}).get("hand") or [])
                    if c and c.get("id") is not None]
        if hand_ids:
            marginals = {cid: self._opener_marginal(cid, hand_ids) for cid in sp}
        if not any(marginals.values()):
            return list(sp)
        rank = {cid: i for i, cid in enumerate(sp)}
        pinned = {i for i, cid in enumerate(sp) if self._route_only_at_setup(cid)}
        movable = sorted((cid for i, cid in enumerate(sp) if i not in pinned),
                         key=lambda c: (-marginals.get(c, 0.0), rank[c]))
        out, it = list(sp), iter(movable)
        for i in range(len(out)):
            if i not in pinned:
                out[i] = next(it)
        return out

    def _top_starter_id(self, obs: dict, select: dict | None) -> int | None:
        """First id in the **Effective Starter Order** present in this SETUP_ACTIVE select's options; None off
        that select. One id, not a rank — a forced single pick means argmax reads only the winner (ADR-0079)."""
        sp = getattr(self.strategy, "starter_priority", None)
        if not sp or not select or select.get("context") != _SETUP_ACTIVE:
            return None
        present = set()
        for opt in (select.get("option") or []):
            card = self._option_pokemon(obs, select, opt)
            if card and card.get("id") is not None:
                present.add(card["id"])
        return next((cid for cid in self._effective_starter_order(obs, sp) if cid in present), None)
