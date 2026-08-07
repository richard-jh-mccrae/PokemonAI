"""The setup-turn reads: what can legally open, and which starter the deck wants Active.

Starter order is the deck's, but the marginal is general — an opener that routes only at setup is worth more on turn 1
than its raw body suggests."""
from __future__ import annotations


from common.strategy.context import _OPENER_TAG, _SETUP_ACTIVE



class OpeningMixin:
    """Who can open, and who should."""

    def _hand_startable(self, hand: list) -> bool:
        """True if a card in hand can take the Active Spot WITHOUT being a Basic — i.e. by the Ability
        route. Scoped to the mulligan keep, where that is the only interesting case: a hand holding
        any Basic never reaches the prompt (rulebook L224 — "if either player has no Basic Pokémon in
        their opening hand, that player must take a mulligan"). Deliberately NARROWER than
        `_is_startable_body`, which is why it reads `_opens_from_hand` rather than calling it — the
        Basic half would make this trivially true on a hand that cannot mulligan anyway.

        The deck `starter` Role was a second accepted signal here until ADR-0079 retired it: every
        declaration in the repo was either a Basic (moot per the rule above) or Cinderace, which
        carries the `opener` Tag anyway — so it never changed this answer. Naming a deck's openers is
        now `Strategy.starter_priority`'s job, at the Set-Up ACTIVE pick rather than the mulligan."""
        return any(self._opens_from_hand(c.get("id")) for c in hand if c)

    def _is_startable_body(self, cid: int | None) -> bool:
        """True iff this card can legally take the Active Spot at the pregame Set-Up pick — a Basic
        Pokémon, or one that `_opens_from_hand`. This is the universe `Strategy.starter_priority` must
        rank COMPLETELY (ADR-0079 decision 5).

        Lives here, on the runtime, rather than in the test that consumes it: the completeness
        invariant is only worth anything if it measures the declaration against what the ENGINE can
        actually offer, and a re-implementation in the test would be free to drift from it — which is
        the failure the invariant exists to prevent. Returns False on unknown stats, so a caller that
        needs the answer to be MEANINGFUL must first establish that stats loaded (the test asserts a
        non-empty startable set for exactly this reason)."""
        if cid is None or not self.stats:
            return False
        st = self.stats.get(cid)
        if not st or not st.is_pokemon:
            return False
        return not st.evolvesFrom or self._opens_from_hand(cid)

    def _opens_from_hand(self, cid: int | None) -> bool:
        """This card's own Ability puts it into the Active Spot straight from hand — the `opener`
        Function Tag (Cinderace's Explosiveness: "if this Pokémon is in your hand when you are setting
        up to play, you may put it face down in the Active Spot"). The ONE definition of the
        Ability route into the Active Spot; both readers below derive from it so they cannot drift."""
        return bool(self.functions) and cid is not None and _OPENER_TAG in self.functions.tags(cid)

    def _opener_marginal(self, cid: int | None, hand_ids) -> float:
        """**Opener Marginal** (ADR-0081 decision 4): ADR-0070's body-substituted evolve delta, in
        DAMAGE, read at turn 0. Non-zero only when a card in hand evolves from `cid` AND that card is
        a declared Line payoff; then `maxDamage(payoff) - maxDamage(cid)`. Zero otherwise.

        Silent by default BY CONSTRUCTION, which is what lets the declaration keep every frame it
        already gets right without a threshold constant to tune (ADR-0065). The Line gate is
        load-bearing rather than a refinement: without it this fires on five promotable bodies across
        the three authored decks and only one firing is wanted — a mid-line stepping stone (Drakloak)
        or a draw engine (Dudunsparce) would otherwise promote its own base, rebuilding the guard
        pile ADR-0079 deleted.

        Matches on the evolution's `evolvesFrom` NAME, not an id, so reprints of the same body (Raboot
        is both 152 and 665) resolve identically. Reads the HAND only — at turn 0 the deck carries no
        frame-specific information, so deck odds would be a per-deck constant the ranking already
        encodes (ADR-0081 decision 3)."""
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
        """Is the pregame Set-Up pick this body's ONLY route into play? The DERIVED pin (ADR-0081
        decision 1) — true for an `opener`-tagged Evolution whose previous stage is absent from this
        deck, i.e. Cinderace in a deck running no Raboot. Skipping such a body forfeits it
        permanently, so the Opener Marginal may not move it.

        Computed from the DECKLIST rather than declared, which is what keeps it correct for free: add
        the previous stage to the deck and the pin lifts by itself, where a declared marker would go
        stale. Derivation-first with declaration as the confirm/override is the established pattern
        (ADR-0079 amendment F, `_derived_accel_body_ids`).

        **Fails CLOSED** — pins when it cannot tell — deliberately the opposite of
        `_is_startable_body`. The asymmetry is justified by consequence, not symmetry: a MISSING pin
        permanently forfeits a card, while a spurious one merely opens suboptimally. Pinning
        everything degrades exactly to the pre-ADR-0081 behaviour (the declared order, verbatim)."""
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
        """**Effective Starter Order** (ADR-0081 decision 5): the declaration as resolved against THIS
        opening hand. Pinned entries hold their declared slot; unpinned entries re-sort among the
        slots left over, by (Opener Marginal desc, declared rank asc).

        The override is STRUCTURAL — it changes what the declaration SAYS, not what anything SCORES —
        so the seam keeps one rule and one boolean (ADR-0079 decision 5 survives intact) and the
        reorder cannot be disarmed by a learned weight. Scoring it additively would have made
        correctness depend on `open-the-declared-starter`'s tuned magnitude staying small.

        Returns the declaration untouched when no body has a marginal, which is the overwhelmingly
        common case — so the pin predicate is not even consulted on an ordinary hand."""
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
        """The body the deck most wants Active among the ones actually on offer — the first id in the
        **Effective Starter Order** present in this SETUP_ACTIVE select's options. None off that
        select, on an empty declaration, or when nothing offered is ranked.

        One id, not a rank, because SETUP_ACTIVE is a forced single pick (minCount/maxCount 1): argmax
        reads only the winner, so under a COMPLETE list this collapses the whole ordering losslessly
        (ADR-0079 decision 5). Twin of `_top_fetch_priority_id`, except that the order it scans is
        hand-conditional (ADR-0081) rather than the declaration verbatim."""
        sp = getattr(self.strategy, "starter_priority", None)
        if not sp or not select or select.get("context") != _SETUP_ACTIVE:
            return None
        present = set()
        for opt in (select.get("option") or []):
            card = self._option_pokemon(obs, select, opt)
            if card and card.get("id") is not None:
                present.add(card["id"])
        return next((cid for cid in self._effective_starter_order(obs, sp) if cid in present), None)
