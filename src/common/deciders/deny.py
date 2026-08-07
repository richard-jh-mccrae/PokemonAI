"""Deny Relevance (ADR-0080): what an Energy strip actually takes away, per opponent body, priced NOW.

`_DENY_CHARGED` is the ruling that makes it *now*: no credit for the attach they make next turn. At `base_attach: 1` a
single strip is cancelled by construction wherever the body can re-afford its attack."""
from __future__ import annotations


from collections import Counter

from common.deciders.facts import Board
from common.deciders.snipe import _BRIEF_THREAT_BOOST
from common.deny_relevance import MAX_ATTACK_DAMAGE as _DENY_RELEVANCE_NORM
from common.strategy.context import (FOLLOWUP_W, _ACTIVE, _BENCH, _DISCARD_ENERGY, _ENERGY, _PLAY,
                                     _POSTURE_MIN_COVERAGE, _POSTURE_UNFAVORED)
from common.strategy.denial import coin_odds
from common.strategy.sequence import followup_damage


# WP-N5b/N5d's hand-value term (`_hand_readiness`, `_held_undeployable`, `_HAND_READINESS_W/_CAP`
# and the `_HAND_TIEBREAK_*` ε alternative) is DELETED by POC-T4/5 (Issue #386) along with the
# develop rung whose LEAF it was a term of. The question it answered — what are the cards still in
# my hand at end-of-turn worth? — is now `state_value`'s `hand` family, which prices the hand as a
# LEDGER (supply against DEMAND, ADR-0127) rather than as a one-sided credit; that is why the cap
# is not carried over (`state_value` §`hand`). `leaf_hand_value` survives as the flag gating the
# held-context CAPTURE the state model needs (`planner._leaf_state_model`), not this term.
_DENIAL_PLAY_W = 1.0       # points per damage-point denied, at the PLAY. REPLACES `play-energy-denial`'s
                           # flat +20, which paid the same for turning off a 270 nuke as for shaving 70
                           # off a benched body. Same lesson as ADR-0060: price the quantity, don't
                           # threshold it.

_DENIAL_TARGET_W = 1.0     # points per damage-point denied, at the DISCARD_ENERGY select. Ranks the
                           # Hammer's TARGET once its coin comes up heads; nothing scored that select
                           # before, so a won flip stripped option [0] — the OLDEST-attached Energy.

#: ADR-0080 / Issue #187: the factor standing where `opp_denial_best` supplied a damage MAGNITUDE, now
#: that relevance is a [0,1] scalar. **DERIVED, not chosen** — it is exactly the normalizer relevance
#: was divided by, so `K x relevance == the setback damage` and the armed fire rung is a strict
#: GENERALISATION of the incumbent's own arithmetic rather than a re-scaling of it. There is no free
#: parameter here: pin it to anything else and `K x relevance` stops being a damage figure at all.
#:
#: Measured on the ADR-0062 anchors AT ISSUE #187, the identity reproduced the incumbent to the cent
#: where the readings coincided, and diverged only upward where relevance saw a setback `_denial_at`
#: could not — **f12 +55.0 vs +22.50, f26 +16.25 vs +1.25**, same sign, same decision, strictly
#: better informed.
#: ⚠️ That comparison is the DERIVATION RECORD, not a live cross-check, and **both armed figures have
#: since moved** — do not read them as current. f12 now prices +22.50 (ADR-0084 Amendment A applied
#: the mandated `_DENIAL_FORWARD` discount to the armed read, which had been crediting the forward
#: form at double) and f26 now prices +95.00 (decision 5 dropped the bench weight in favour of the
#: promotion gate). Issue #228 then armed the flag and DELETED the ADR-0062 magnitude rung
#: (`opp_denial_best` / `_denial_at`), so there is no second instrument left to compare against at
#: all. K stays pinned to the normalizer for the reason it was derived — it cancels the division
#: relevance performs — and that is now the only thing holding it. The live pin is
#: `test_deny_relevance_consumer.py::test_the_fire_factor_is_the_normalizer_so_it_prices_in_damage_units`.
#:
#: ⚠️ **The witness moved (ADR-0084 decision 8).** This note used to cite f21/f29's benched Dragapult
#: ex pricing **-1.25 on both**. That figure was `70 x _DENIAL_BENCH`, and decision 5 retired the
#: constant from this rung in favour of ADR-0071's promotion GATE (Issue #228 then deleted the
#: constant outright with the rest of the OFF path). On that board the gate SHUTS (their Terapagos ex
#: holds 0 Energy against retreat cost 2, and no switch survives the read), so the bench carries no
#: weight, `deny_relevance_best` is 0, and the rung takes its whiff branch at **0.00** — same
#: decision, different number. f12 and f26 are the surviving witnesses; f21/f29 now witness the
#: GATE instead. K itself is untouched: decision 5 changed an area WEIGHT, which multiplies outside
#: this normalizer, so there was never a free parameter here to re-derive.
#:
#: It is **NOT an exchange rate** and must never be reused as one: that is the Worth Damage Rate, which
#: ADR-0080 decision 1 rules MOOT for deny and `common/currency.py`'s guard test keeps absent by design.
#: The distinction is that this factor cancels a normalizer inside ONE instrument's own units; a rate
#: would carry a value ACROSS two currencies.
_DENY_RELEVANCE_K = _DENY_RELEVANCE_NORM

_DENIAL_UNFAVORED = 0.3    # Lever A (ADR-0026), as a MULTIPLIER on the priced denial rather than a flat
                           # rung beside it: when the Read says the race is lost, a strip that already
                           # denies something is worth MORE. It can never make a whiff worth playing —
                           # scaling 0 leaves 0, and scaling a negative play value leaves it negative.
                           # This is the whole point (ms 83968638 f17, CRITICAL): the old flat
                           # `disrupt-when-unfavored` (+18) rode `opp_denial_best > 0` (the raw PRESENCE
                           # of denial) and so OVERRODE the oracle's own hold — a free Item at score > 0
                           # is tiered ahead of everything. A booster must scale the oracle, never add to it.
                           # RE-EXPRESSED ON RELEVANCE (user ruling 2026-07-30, ADR-0080 Amendment B): its
                           # SUBJECT is now "deny's value, whichever instrument supplies it" rather than
                           # "the priced denial magnitude". It multiplies the whole product, so it is
                           # scale-invariant — a 30% amplification is 30% whether the term it scales is a
                           # damage figure or `K x relevance`, and the f17 discipline survives verbatim
                           # (relevance 0 -> 0, so it still cannot resurrect a whiff). Since Issue #228
                           # deleted the ADR-0062 magnitude rung, `K x relevance` is the ONLY term it
                           # scales; the scale-invariance argument is what made that deletion safe.
                           # ADR-0078 decision 6 had retired this outright, on the grounds that it and
                           # `needs.phase_scale` "say the same thing multiplicatively". That retirement is
                           # **WITHDRAWN**: under ADR-0080 deny reads `phase_scale` on NO surface, so the
                           # substitution justifying it no longer exists, and retiring it unreplaced would
                           # have deleted Lever A from the live codebase (this is its last consumer).

_DENIAL_FORWARD = 0.5      # ADR-0062 amendment: credit for what the stripped Energy would pay for on the
                           # target's FORWARD form. "Evolving keeps attached cards" (rules.md:98), so
                           # Energy on a pre-evolution is BANKED, not spent: a Riolu's own Accelerating
                           # Stab ({F}, 30) is not what its Energy is for — Mega Lucario ex's Aura Jab
                           # ({F}, 130) is. Discounted because the payoff is a TURN AWAY (they must evolve
                           # first) and CONTINGENT (they must actually hold the evolution). The bound is
                           # DERIVED from two frames, not tuned: ms 82225643 f12 (Active Riolu, 1 Energy)
                           # must PLAY, and dragapult 85046350 f32 (Active Gabite, 1 Energy, forward 100)
                           # must stay BELOW the retreat-to-wall (30) it would otherwise bury — which
                           # forces 0.154 < _DENIAL_FORWARD < 0.8.


class DenyMixin:
    """What stripping this Energy takes away from the opponent, this turn."""

    def _unfavored(self, board: Board) -> bool:
        """The Read says the straight race loses (Lever A, ADR-0026) — a compiled favorability at or
        below `_POSTURE_UNFAVORED`, backed by enough coverage to trust the prior."""
        return (board.matchup_coverage >= _POSTURE_MIN_COVERAGE
                and board.favorability <= _POSTURE_UNFAVORED)

    def _denial_play_tactical(self, obs: dict, board: Board, ctx) -> float:
        """Value of PLAYING an energy-denial Item (ADR-0062): what the strip actually takes away,
        priced by its odds, net of the HOLD PRICE — what spending the card costs.

            coin_odds(card) * _DENIAL_PLAY_W * (unfavored?) * value  -  _item_hold_price(card)

        where ``value`` is `K x relevance` (ADR-0080, Issue #187). It was the ADR-0062 damage
        magnitude `opp_denial_best` until Issue #228 armed the flag and deleted that oracle; OFF now
        stands the rung down entirely — DEGRADED MODE, never a rollback.

        **The hold is no longer deny's own constant** (Issue #261 item 2f, old Issue #212). It was
        `_DENIAL_ITEM_COST = 10`, and its rationale — *"an Item is finite, and `_finish_turn_last`
        tiers a free Item ahead of everything"* — is a property of the SEQUENCER, true of every free
        Item and priced for exactly one card class. `_item_hold_price` generalises it onto the Needs
        assignment: `max(needs.keep_v2(this card), hold_value.ITEM_HOLD_FLOOR)` crossed at
        `currency.ITEM_HOLD_WORTH_RATE`. On all four committed deny anchors the floor BINDS — a
        role-less Hammer's only slot is the very `deny` slot this rung is already pricing, so its
        assignment marginal collapses on exactly the boards where the strip whiffs; `hold_value`'s
        module docstring carries that measurement and the reasoning, once, rather than here as well.
        The consequence for THIS rung: the swap is arithmetically identical on every ruled frame.

        Silent unless the card is `energy_denial`. A whiff (value 0 — surplus Energy, no affordable
        attack, or the only energized body is one I am about to KO) still pays the hold price and so
        prices at **-`hold`**, which DECLINES. It used to short-circuit to a bare 0.0,
        and this docstring used to claim that "prices at 0 and is held" — it did not: `_finish_turn_last`
        promotes only on `score > 0`, so a 0.0 free Item landed in the last tier TIED with End and
        stable score order played it by option index (Issue #228; the asymmetry ADR-0084 decision 8
        knowingly handed forward). Declining REQUIRES a STRICTLY negative score, not merely a
        non-positive one. Half of all Crushing Hammers do nothing whatever the board looks like, so
        the coin is priced here rather than absorbed into a tuned constant.

        The unfavored Read (Lever A) SCALES this value and is never added beside it — see
        `_DENIAL_UNFAVORED`. A multiplier cannot resurrect a hold; the flat rung it replaces did
        exactly that, and played a Hammer into a KO turn against a bare bench (ms 83968638 f17)."""
        if ctx.option_type != _PLAY or "energy_denial" not in ctx.tags:
            return 0.0
        # ARMED (ADR-0080, Issue #187): `K x relevance` replaces the damage magnitude. Same SHAPE —
        # odds x weight x value - keep price — so the whiff hold, the Lever A scaling and the
        # `_finish_turn_last` interaction all survive unchanged; only what supplies "value" moves.
        if not self.deny_relevance:
            return 0.0          # DEGRADED MODE, never a rollback — see the flag's note in runtime.py
        # `None` on the Board is ABSENT, not zero (ADR-0093 decision 2), so it is RECOMPUTED
        # rather than read as a whiff. A genuine 0.0 survives the ladder and is a real hold.
        value = _DENY_RELEVANCE_K * self._deny_relevance_best(obs, board)
        weight = _DENIAL_PLAY_W * (1.0 + _DENIAL_UNFAVORED if self._unfavored(board) else 1.0)
        # NO whiff short-circuit. A `value` of 0 is a real read saying "nothing here", and it must
        # still pay the hold price: `odds x weight x 0 - hold` = -10.0 on the anchors, which DECLINES.
        # Returning a bare 0.0 here did not — `_finish_turn_last` promotes only on `score > 0`, so a
        # 0.0 free Item landed in the last tier TIED with End and stable score order played it by
        # option index. The OFF path escaped that by arithmetic accident (its magnitude is rarely
        # exactly 0 while the card is playable); a categorical [0,1] scalar is 0 routinely and by
        # design, which is what turned a latent contract violation into a live defect at arming time.
        # `hold_value.hold_price` is STRICTLY POSITIVE for the same reason the constant had to be:
        # a keep-machinery reading alone goes to 0 on exactly the boards where the strip whiffs.
        return (coin_odds(ctx.card_id) * weight * value
                - self._item_hold_price(obs, board, ctx.card_id))

    def _denial_target_tactical(self, obs: dict, select: dict, board: Board, option: dict) -> float:
        """Rank the Crushing Hammer's TARGET once its coin comes up heads (ADR-0062).

        The engine poses a DISCARD_ENERGY select over every Energy on the opponent's board, ordered
        OLDEST-ATTACHED FIRST. Nothing scored it: every option came back 0.0, so the argmax fell
        through to index 0 and we stripped whatever Energy happened to land first — routinely a Basic
        on a benched support mon while their Active sat one Energy above its nuke. That is the literal
        waste. Score each option by what removing it actually denies.

        The DOOMED Active scores 0 here for the same reason Deny Relevance's redundancy gate zeroes
        its row: Energy on a body I am about to knock out is not worth taking. A won flip should land
        on the bench instead of shaving a corpse.

        ARMED (ADR-0080, Issue #187) this is a **pure `argmax relevance`**, scored per OPTION rather
        than per body — which is what makes the within-body rulings expressible at all: on a Munkidori
        holding `{D}` + `{P}`, both options point at the same body, and only the Energy's own TYPE
        separates muting Adrena-Brain from shaving Mind Bend's cost. The lookup is therefore keyed on
        the option's Provider-resolved type (`_option_energy_type`), never on its position."""
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
            # No area weight at all — a PURE `argmax relevance` (user ruling, 2026-07-30). Relevance
            # already prices a benched body's slower clock through its own line scan, so discounting
            # it again double-counts. `_DENIAL_BENCH` was the OFF-path weight here and is DELETED
            # (Issue #228, directive 1); the promotion GATE carries its question on the fire rung.
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
        """The ADR-0084 decision 2 tiebreak: among candidates tied on relevance EXACTLY, prefer the
        one whose strip actually buys turns of survival. Returns 0.0 whenever there is nothing to
        break.

        **Lexicographic, and provably so — the bound is DERIVED, not hand-set.** The adjustment is
        half the FINEST distinction relevance actually draws: the smallest positive gap between two
        distinct relevance values on this menu, falling back to ``1 / K`` — one unit of damage — when
        the menu draws no distinction at all. Since ``K x relevance`` IS the setback damage
        (ADR-0080 Amendment B) and damage is integral, two relevance values that differ at all differ
        by at least ``1 / K``, so half of that can never overtake a difference relevance settled.

        Deriving the bound rather than fixing it is the whole point: a hardcoded epsilon would be a
        constant sized against relevance's current arithmetic, and this repo has a recorded case of a
        new positive term silently voiding every guard calibrated against the previous arithmetic
        (ADR-0063). A rotted bound would begin overriding real differences with nothing failing
        loudly. Any fraction in (0, 1) is equally sound; a half is the midpoint of that proven-safe
        interval, NOT a value fitted to data.

        It is also deliberately TINY — a fraction of one damage unit. An earlier draft bounded the top
        tier by its own relevance, which is order-safe (nothing sits above it) but yields a bonus of
        ~125 score units on a real board. That would order the tie correctly and then swamp the other
        twenty-odd tacticals summed into the same option score, converting a tiebreak into a rung.

        **Why this may not GATE.** The clock reads *"does this strip delay MY defeat by a whole turn
        or more"*, which is strictly narrower than *"does this strip do anything"* — it is blind to
        Ability mutes, to sub-turn setbacks, and to any strip that wrecks their plan without touching
        their clock against me. Measured, a `strip_shift > 0` gate on the keep price would suppress
        128 of 218 relevance-positive corpus rows (ADR-0084 decision 7, the reversal). Ordering a tie
        asserts no worth; gating one asserts a great deal.

        Silent, by construction, on the cases the clock cannot speak to: a body tied with itself
        across two Energy TYPES reads ONE delta (`strip_shift` is per body, and which Energy you
        remove never changes it — 109 bodies, 0 cases), so no strict maximum exists and no preference
        is manufactured."""
        shifts = self._deny_strip_shift_map(obs, board)
        mine = shifts.get(key)
        if mine is None or not rel:
            return 0.0                            # absent reading, or nothing relevant — not a zero
        # Every candidate this menu actually offers, as (relevance, key). Peers are read off the
        # SELECT rather than off the board: an Energy no option targets is not a candidate, and
        # ranking against it would invent a tie the engine never posed.
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
                continue                          # the caller already scored this option 0.0 — a body
                #                                   dying to my KO is not a candidate, and letting it
                #                                   hold the largest shift would make `best`
                #                                   unreachable and silently re-mute the tiebreak on
                #                                   the live bench candidate
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
        # The finest distinction relevance actually draws on THIS menu; `1 / K` (one damage unit) when
        # it draws none. Never this candidate's own relevance — see the docstring. The arithmetic is
        # shared with snipe's tiebreak (`currency.tiebreak_bonus`, extracted 2026-07-30 by ADR-0085
        # Amendment H) because it is the piece most likely to drift; the GUARDS above stay separate,
        # which is the whole point of the divergence recorded there.
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
        """The `EnergyType` a ``DISCARD_ENERGY`` option's own Energy contributes, or ``None``.

        Resolved through the Stat Provider from the option's ``energyIndex``, which indexes the
        body's attached **cards** (`energyCards`) — NOT its ``energies``, which lists the units those
        cards PROVIDE and so runs longer on any multi-unit Energy (Ignition provides `{C}{C}{C}`).
        Falls back to ``energies`` for a hand-built obs that carries no `energyCards`, where the two
        coincide because such fixtures hold single-unit Basic Energy.

        Never infers the type from the card id: they coincide for Basic Energy (Basic `{F}` is card 6
        and FIGHTING is 6) but that is a coincidence in the data — Ignition Energy is card id 17."""
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
        """Horizon-2 lock cost (ADR-0061): the damage this attack's lock actually FORFEITS next turn,
        not a flat constant. Replaces `_LOCK_COST = 40`, which charged one number for two structurally
        different locks:

        - **same-attack lock** (Mega Brave 270 / Aura Jab 130): 270+130 == 130+270. You can never Mega
          Brave twice in a row WHICHEVER you open with, so the lock forfeits nothing the other ordering
          would have had — cost **0**. The flat 40 was a phantom charge biasing every pick toward Aura Jab.
        - **full lock** (Blood Moon 240, "can't use attacks"): 240 + 0 loses to a lock-free 130/turn's
          260 — cost **~240**, not 40.

        Cost = `FOLLOWUP_W * (best follow-up a lock-free pick would leave − the follow-up THIS pick
        leaves)`, so a lock-free attack is always 0 and the term never inflates an attack's score (it is
        a cost, never a credit — attacks keep their scale against develops).

        Zero when the Active is `active_doomed`: there is no next turn for it, so every lock is free and
        we front-load. Zero when it is the only affordable attack — chipping must still beat passing
        (the invariant `_lock_cost_applies` held, preserved here)."""
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
        """`Board.deny_relevance_best`, cached-or-computed — the fire rung's value.

        The SAME cache-or-compute ladder `_deny_relevance_map` and `_deny_strip_shift_map` carry, and
        for the same stated reason: *without the fallback an armed hand-built board would emit no
        deny read and score as a whiff, which is a silent behaviour change rather than a fail-closed
        one.* This surface was the one of the three that lacked it (Issue #228), and it is the one
        that moved three Discrimination Gate frames.

        A `None` on the Board means ABSENT, never a measured zero, so it must never be read as one —
        it is recomputed here instead. A genuine 0.0 (no Energy doing work, surplus Energy, or the
        only live body dies to my KO this turn) survives the ladder unchanged and is a real HOLD."""
        if board.deny_relevance_best is not None:
            return board.deny_relevance_best
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else None
        oa = next((p for p in ((opp or {}).get("active") or []) if p), None)
        return self._best_area_weighted_relevance(self._deny_rows(obs, board), opp, oa)

    def _deny_relevance_map(self, obs: dict, board: Board) -> dict:
        """``{(area, bi): {EnergyType: relevance}}`` — the resolved Deny Relevance read, per body.

        Prefers what `_board()` already stashed on the Board; falls back to the per-decision
        `_opponent_target_cache`, then to a fresh compute for a hand-built `board` that never went
        through `_board()` (test fixtures). Exactly the cache-or-compute ladder the `gust_target`
        slot uses — without the fallback an armed hand-built board would emit NO deny slots and read
        as a whiff, which is a silent behaviour change rather than a fail-closed one."""
        if board.deny_relevance_rows:
            return {(a, i): rel for a, i, rel, _shift in board.deny_relevance_rows}
        result = self._deny_rows(obs, board)
        return {(r["area"], r["bi"]): dict(r.get("relevance_by_type") or {}) for r in result}

    def _deny_strip_shift_map(self, obs: dict, board: Board) -> dict:
        """``{(area, bi): strip_shift}`` — the ADR-0084 **strip Δ** per body, the target pick's
        lexicographic tiebreak key. Named for the delta, never "clock": `strip_shift` is a
        delta OF `turns_to_ko_me`, not a reading of it (CONTEXT.md, The Two Clocks). Same cache-or-compute ladder as `_deny_relevance_map`, off the
        SAME rows, so the rank and its tiebreak cannot drift apart.

        A value of ``None`` means **absent, not zero** — `deny_strip_delta` is off, or the row never
        carried a reading. The distinction is load-bearing: a delta may break a tie but must never
        GATE one (ADR-0084 decision 7), and an absent reading must leave the ranking exactly as
        relevance alone ordered it."""
        if board.deny_relevance_rows:
            return {(a, i): shift for a, i, _rel, shift in board.deny_relevance_rows}
        return {(r["area"], r["bi"]): r.get("strip_shift") for r in self._deny_rows(obs, board)}

    def _deny_rows(self, obs: dict, board: Board) -> list:
        """The per-decision opponent-target rows, cached-or-computed — the one ladder both deny maps
        read. Falls back to a fresh compute for a hand-built `board` that never went through
        `_board()` (test fixtures); without it an armed hand-built board would emit NO deny slots and
        read as a whiff, which is a silent behaviour change rather than a fail-closed one."""
        result = getattr(self, "_opponent_target_cache", None)
        if result is None:
            result = self._opponent_target_rows(obs, board)
        return list(result[1]) if result else []

    def _relevance_terms(self, b, *, doomed: frozenset, area: str, bi: int, brief_ids=()) -> dict:
        """The DENY instrument's value — **Deny Relevance**, the read that replaced the magnitude
        (ADR-0080, Issue #199 grill; `common/deny_relevance.py` owns the scoring, this owns the plumbing).

        Emits, per opponent body: the best relevance achievable against it, WHICH attached Energy
        achieves it, ``relevance_by_type`` for a consumer that must score a SPECIFIC Energy, and the
        per-leg components for diagnosis. Consumed by the three deny surfaces since Issue #187
        (ADR-0080 decision 4); still gated on `deny_relevance`.

        ⚠️ **``relevance_energy`` is an index into ``energies`` and is DIAGNOSTIC ONLY — never match
        an engine option against it.** A ``DISCARD_ENERGY`` option identifies its Energy by
        ``energyIndex``, which indexes the body's attached *cards* (``energyCards`` / ``p.energy``),
        while ``energies`` is what those cards PROVIDE (`cgpy.options.provided_energy`) — one entry
        per unit, so an Ignition Energy contributes three. The two only coincide on a body holding
        nothing but single-unit Basic Energy. ``relevance_by_type`` exists so surface (c) can key off
        the option's Provider-resolved TYPE instead, which is what relevance is actually a function
        of; Issue #187's spec originally assumed a positional match and was corrected here.

        The two gates come first and force 0 before any leg is scored:
          * **liveness** — no attached Energy, which also delivers ADR-0062's whiff structurally;
          * **redundancy** — this body dies to our Knock Out this turn (`active_can_ko` for the
            Active, `_bench_doomed_by_me` for the bench), so we never spend a Hammer on a corpse.

        The Energy's TYPE is resolved through the Stat Provider, never inferred from its card id:
        the two coincide for Basic Energy (Basic ``{F}`` is card 6 and FIGHTING is 6) but that is a
        coincidence in the data, and Ignition Energy is card id 17 with a colourless contribution.
        A colourless/special Energy therefore scores 0 on the typed leg, which is correct — it pays
        no specific-type slot and so is never on a plan's critical path.

        A matched Brief's ``threats`` MULTIPLY the derived rank, never source it (ADR-0080
        decision 2): authored scouting sharpens a read that already works without it. The Brief-free
        path deliberately does NOT fall back to `Scout._target_role`, which orders `prize_liability`
        (any *ex* body) above `attacker` and so would top an unbriefed board with exactly the
        Meowth ex the doctrine says to ignore."""
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
                                     # ADR-0084 Amendment A: the ADR-0080-mandated forward discount,
                                     # the SAME constant `_denial_at` applies on the OFF path. Without
                                     # it the armed read credited a forward form in full.
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
            # The Brief sharpens the RANK (ADR-0080 decision 2's own word) — the keep price and the
            # target pick. It deliberately does NOT touch the fire reading: that one is compared
            # against the free-Item HOLD PRICE, so a multiplier there can lift a hold above zero, and "a
            # booster must scale the oracle, never override it" is the f17 ruling (ADR-0062). Measured:
            # boosting the fire leg turns f21's -1.25 into +0.94 and plays the Hammer the human ruled
            # against, on a board where the ONLY thing that changed is that the body is Brief-named.
            best = dict(best, relevance=min(1.0, best["relevance"] * _BRIEF_THREAT_BOOST))
            by_type = {t: min(1.0, v * _BRIEF_THREAT_BOOST) for t, v in by_type.items()}
        return dict(best, relevance_by_type=by_type, relevance_fire=fire)

    def _strip_delta_terms(self, ma, bodies, i, phase, *, opp_active, enabler) -> dict:
        """The DENY instrument's slice of the shared marginal (ADR-0078 decision 1; built by #199).

        The removal Δ beside it asks "what do I buy by taking this body OFF the board" — the gust /
        snipe question. A Hammer cannot ask that: it discards ONE Energy and the body stays. So deny
        plugs its own Δ into the shared currency (the design doc's *"each plugs its own `Δ` into the
        two terms"*), in the shape the user's ruling fixes — see SHAPE below.

        Mechanism mirrors the deleted S2 recur diagnostic in the opposite direction — it augments a COPY of the
        body's ``energies`` upward to model discard fuel; this drops one, so no live primitive is
        touched and no caller's body dict is mutated.

        **SHAPE (user ruling, ADR-0078 Amendments B + C).** Deny's Δ is the SAME two-term marginal the
        removal Δ uses — ``needs.opponent_target_value`` over a ``turns_to_ko_me`` difference — so the
        one-backend claim of decision 1 holds for real. Only the POLICY differs (below).

        A fully-stripped body reads as not attacking within the horizon, so its Δ runs to the horizon.
        That is **correct, not a runaway**, for two reasons the user's ruling names: a bare body
        genuinely cannot attack on the board as it stands, and a Hammer cannot take it below zero, so
        the value SATURATES rather than compounding — `_strip_delta_terms` returns 0 for a bare body,
        which is that floor. `needs._SURVIVAL_CAP` (0.9) then bounds the term regardless, so deny stays
        sub-prize and can never out-price a real prize outcome. An earlier draft of this method priced
        a one-step damage swing instead, on the mistaken worry that the horizon Δ "overstates"; the cap
        already contained it, and the corpus preferred this shape (see Amendment C's table).

        ``prize_advance`` is **0**, and that is a ruling, not an omission (ADR-0078 decision 1 /
        design doc line 50, "deny (pure tempo)"): a strip takes no Prizes. The forward-form case that
        might look like a prize term is already inside the curve — S1a established ``forward_card_ids``
        is all-descendants, so the read already sees what a body evolves into off the Energy it is
        banking (ADR-0063's `_DENIAL_FORWARD` instinct, derived).

        A body holding no Energy yields 0: there is nothing to strip, which is the ADR-0062 whiff
        arriving structurally instead of as a separate gate.

        **POLICY (design doc ruling 2, the load-bearing per-consumer conservatism).** This Δ is read
        under `_DENY_CHARGED`, NOT the ceiling the removal Δ beside it uses, and the difference is not
        a refinement — under the ceiling the Δ is identically 0 by construction. The ceiling checks a
        form's affordability against its CHEAPEST attack and then credits its BIGGEST regardless
        (`incoming`'s own contract: *"a form contributes its biggest attack once it can pay its
        cheapest under `attached + t`; the bigger attack's affordability is NOT charged"*), so
        removing one Energy cannot change what it deals. Only a charged policy prices the per-attack
        typed affordability a strip actually attacks.

        `_DENY_CHARGED` carries the **user's ruling of 2026-07-28** (ADR-0078 Amendment B): the Δ is
        INSTANTANEOUS — `base_attach: 0`, no credit for the Energy they re-attach next turn — and it
        is only ever taken over opponent bodies carrying Energy right now. See that constant for why
        the design doc's "slow" (`base_attach: 1`) reading was the thing gate 1 measured as broken.

        **`energies[:-1]` is arbitrary and measured HARMLESS, not assumed harmless (ADR-0084 decision
        3).** Removing "the last-attached Energy" looks like it should matter under a typed
        affordability policy, and it does not: across **109 corpus bodies holding two or more
        Energies, which Energy is removed changes `turns_to_ko_me` in ZERO cases**, with zero false
        negatives for this policy. So the per-removed-TYPE generalisation the charged framing implies
        is measurably inert, while raising cost from 2 simulations per body per decision to
        `1 + Ntypes`. That is an EMPIRICAL rather than a provable guarantee: if a board ever appears
        where a body holds one critical and one surplus Energy AND sets the clock, re-run that
        measurement rather than re-deriving the question. The harness was
        `tools/train/probes/deny_gate217.py`, deleted by Issue #243 once ADR-0084 recorded its
        answer; rebuild it from that ADR's description rather than editing a stale one — a harness
        whose six hardcoded anchors have gone quietly out of date is a trap, not a head start.

        **Consumer (ADR-0084 decision 7).** Exactly ONE: the target pick's lexicographic tiebreak
        (`_deny_strip_delta_tiebreak`). This Δ may order a tie; it may never GATE one. It reads *"does this
        strip delay MY defeat by a whole turn or more"*, which is strictly narrower than *"does this
        strip do anything"* — blind to Ability mutes, to sub-turn setbacks, and to any strip that
        wrecks their plan without touching their clock against me. Measured, a `strip_shift > 0` gate
        on the keep price would have suppressed **128 of 218** relevance-positive rows."""
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
        # Off the SNAPSHOT (POC-T1). Both legs name `bodies` — the second is a COUNTERFACTUAL board
        # with the stripped copy spliced in — and both name `_DENY_CHARGED` explicitly, because this
        # Δ is measured under the zero-attach budget and must NOT drift onto the Read's threaded one
        # (see `_DENY_CHARGED` for why the "slow" reading was what gate 1 measured as broken).
        #
        # Both legs also name `context` (Issue #343), and for the opposite reason to `_DENY_CHARGED`:
        # the policy is a per-consumer RULING that this Δ deliberately does not share, while the
        # context is a per-decision FACT about the board that every consumer must price the same way.
        # Omitting it did not make the strip read conservative, it made it silent — a scaling
        # attacker contributed 0, so disarming their real threat priced at nothing. Threading it into
        # BOTH legs is the one thing that must not be got wrong: the return below differences them,
        # and a threaded leg minus a blind one is a comparison between two different questions.
        # `self._opp_attack_context` is `None` on a hand-built board that never went through
        # `_board`, which reproduces exactly today's reading rather than raising — the same
        # fail-to-current-behaviour contract `_deny_rows` gives such a caller.
        #
        # STAYS ON THE INTEGER READING, stated because the sibling Δ did not (ADR-0117).
        # `_opponent_target_rows`' `survival_shift` took the Fractional Survival Clock and this
        # `strip_shift` lands in the SAME row dict, so the asymmetry is visible and needs a reason
        # rather than a shrug. The reason is scope, not principle: this Δ's consumer is ADR-0084
        # decision 7's LEXICOGRAPHIC TIEBREAK, whose ordering was measured under whole turns, and
        # the fractional reading has not been measured here. CONTEXT.md's Two Clocks entry records
        # the open half — `strip_shift > 0` still means "delays my death by a whole turn or more",
        # the 128-of-218 gap Issue #217 measured. Widening it is unscoped work, not an oversight.
        ctx = self._opp_attack_context
        base = model.theirs.turns_to_ko_me(ma, bodies=bodies, opp_active=opp_active,
                                           switch_enabler=enabler, charged=self._DENY_CHARGED,
                                           context=ctx)
        after = model.theirs.turns_to_ko_me(ma, bodies=bodies[:i] + [stripped] + bodies[i + 1:],
                                            opp_active=stripped if b is opp_active else opp_active,
                                            switch_enabler=enabler, charged=self._DENY_CHARGED,
                                            context=ctx)
        return {"strip_shift": after - base,                   # BOTH legs under `_DENY_CHARGED` — the
                                                               # caller's `base_t` is the CEILING
                                                               # baseline, and differencing across two
                                                               # policies would be meaningless
                "deny_value": needs.opponent_target_value(prize_advance=0.0,
                                                          survival_shift=after - base, phase=phase)}

    def _best_area_weighted_relevance(self, rel_rows, opp: dict | None,
                                      oa: dict | None) -> float:
        """The best relevance achievable anywhere on their board — `Board.deny_relevance_best`.

        AREA-WEIGHTED, and deliberately so. The 2026-07-30 ruling dropped `_DENIAL_BENCH` from the
        TARGET pick (surface c), where relevance already prices a benched body's own line scan; it
        did NOT drop the question this rung asks, which is whether that benched body can REACH the
        Active position at all. ADR-0084 decision 5 answered it with ADR-0071's promotion GATE rather
        than a flat discount: a bench row counts in full when the gate is open and not at all when it
        is shut. Measured over all 21 Hammer-ruled corpus frames: ZERO sign changes vs the constant.

        Extracted from `_board()` by Issue #228 so the ladder below and the per-decision build share
        ONE definition — a second spelling of "which rows count, and how much" is exactly the drift
        that put a whiff and an absent read at the same value in the first place."""
        bodies = [b for b in ([oa] if oa else []) + list((opp or {}).get("bench") or []) if b]
        promotion_open = bool(bodies) and self.combat._promotion_open(
            bodies, oa, switch_enabler=self._opp_switch_enabler())
        return max((r.get("relevance_fire", 0.0) * (1.0 if r["area"] == "active"
                                                    else (1.0 if promotion_open else 0.0))
                    for r in rel_rows), default=0.0)

    def _opponent_target_rows(self, obs: dict, board) -> tuple | None:
        """S3 opponent-target value, the SHARED per-body computation (ADR-0076): `prize_advance +
        phase × survival_shift` (`needs.opponent_target_value`) for every opponent in-play body —
        the ONE place both the S3a diagnostic (deleted by Issue #261 item 2h) and the live
        `gust_target` slot emission (`_resolve_needs`) read it, so they cannot drift apart.
        `survival_shift` is the turns of survival bought by removing the body — a Δ of the
        **Fractional Survival Clock** (`combat.survival_clock().exact`, ADR-0117), so it is a
        real number rather than whole turns; at integer resolution most removals quantise to 0 and
        the ranking flat-ties. `prize_advance` is its prize value (the if-KO'd
        term); `phase` is the KO-race scale (`needs.phase_scale`). A THREAT read, so it keeps the
        conservative default reading; `opp_active` is passed for the promotion gate, which opens
        correctly when the loop removes it (the replacement Active is chosen from the Bench for
        free, rulebook.txt:176). Redundancy (the ADR-0044 guards) and instrument-specifics (chip vs
        KO, reachability) are each consumer's own job, not priced here.

        Returns ``(phase, rows)``; each row carries the raw ``body`` dict, its ``area``
        (``"active"``/``"bench"``) and within-area index ``bi`` (the deny-slot key convention), plus
        ``id``/``prize``/``survival_shift``/``value``/``role_priority``. The last is the ADR-0051
        role sheet as its OWN leg (Issue #395 D7) — an ordinal priority, never summed into ``value``,
        whose meaning and ceiling are unchanged by it. None when sparse: no live my Active, or no
        opponent in-play bodies.

        **Runs MID-SIM** (ADR-0093 decision 3). It used to early-return `None` under the
        planner's `_planning` reentrancy flag, alongside the three SHADOWS — but this is the LIVE
        computation both the deny fire rung and the `gust_target` slot emission read, not a
        diagnostic, and withholding it mid-sim made the agent evaluate a different policy inside its
        own rollout than outside it. That is the third confirmed source of continuation collateral
        in this repo (ADR-0072 finding 2, ADR-0070 amendment H, Issue #228). The guard was a COST
        decision, not a correctness one — nothing below starts a nested engine search; `turns_to_ko_me`
        is the closed-form S1 curve. It moved onto `_opponent_target_shadow`, the caller that
        genuinely wanted no shadow work in rollouts, and Issue #261 item 2h then deleted that caller
        — so the guard is gone entirely and these rows simply always run."""
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
        # Off the SNAPSHOT (POC-T1), with the counterfactual board named explicitly: the removal Δ
        # below asks the clock about a board with one of their bodies gone, which is precisely the
        # question the old model route could not express and the reason this read bypassed it.
        #
        # `charged=None` is the CEILING, stated rather than inherited. This is a THREAT read, so it
        # keeps the worst-case energy policy whatever the Read says (ADR-0064 Decision 1 keeps the
        # conservatism per-consumer); taking the snapshot's threaded budget here would silently relax
        # every gust/deny target value behind a matched Brief.
        #
        # `context` is the THEIRS-direction Damage Formula dict, and its omission here was an
        # OVERSIGHT rather than a second conservatism ruling (Issue #343): the energy policy above
        # was considered and stated, the scaler context was not named at all. It is not the same
        # KIND of choice — `charged` picks how much Energy to credit them, while `context` decides
        # whether a scaling attack is priced AT ALL, and dropping it is not conservative but BLIND
        # (a variable absent from the context contributes 0, so Powerful Hand read as 0 damage).
        # `self._opp_attack_context` is `_damage_context(obs, attacker_is_me=False)`, allocated once
        # per decision by `_board` above, which is the same dict the sibling Incoming reads take.
        # It goes into `clock` rather than onto each call so the removal Δ below cannot difference a
        # threaded leg against a blind one — the two legs are one question by construction.
        clock = dict(bodies=bodies, charged=None, opp_active=opp_active, switch_enabler=enabler,
                     context=self._opp_attack_context)
        # THE FRACTIONAL READING, opted into here and nowhere else (ADR-0117). `survival_shift`
        # is a Δ of this clock under removal of one of their bodies, and the integer reading threw
        # away the size of that move: where a removal DOES shift the clock, `dealt` already knows by
        # how much (`incoming` prices through the Damage Formula and its evolution reach is maximal
        # at t=1, so energy cost, scaled damage, riders, weakness and the full forward closure are
        # all in there). This reads the crossing point instead of the turn it lands in.
        #
        # ⚠️ It fixes a MINORITY of the Flat Tie. `incoming` is a per-turn MAXIMUM, so a body scores
        # only where it is the unique lead at some turn before the crossing — most opponent bodies
        # never lead, and price at EXACTLY 0 at any resolution (a Structural Zero). The Active is
        # usually that lead, so on the BENCH, which is the only scope `gust_target_slot` reads, this
        # term still ranks almost nothing. That is Issue #398's open defect, not something this line
        # claims to have solved. Numbers and derivation: ADR-0117, not restated here.
        #
        # The other clock families (`survival`, `readiness`, `threat`) keep the integer: each
        # carries scale anchors calibrated against it, and widening them is a separate, unmeasured
        # change.
        base_exact = model.theirs.survival_clock(ma, **clock).exact
        # Deny Relevance's REDUNDANCY gate (ADR-0080 step 2), resolved once for the whole decision
        # rather than per body: which opponent bodies die to our Knock Out this turn, and so deny
        # nothing. Keyed by the row's own (area, bi) convention. Only built when the read is armed.
        doomed_ids = frozenset()
        if self.deny_relevance:
            doomed_ids = (frozenset({("active", 0)} if getattr(board, "active_can_ko", False)
                                    else ())
                          | frozenset(("bench", j)
                                      for j in self._bench_doomed_by_me(ma, bench_list)))
        # The ADR-0051 spine, resolved once for the whole decision rather than per body. `None` when
        # the kill-switch is off or the Board predates it — the row then carries 0.0, which is the
        # same "unroled" reading `MatchupPlan.priority` gives, so no consumer has to special-case it.
        plan = getattr(board, "matchup_plan", None)
        rows = []
        for i, b in enumerate(bodies):
            shift = model.theirs.survival_clock(
                ma, **dict(clock, bodies=bodies[:i] + bodies[i + 1:])).exact - base_exact
            # THE LINE'S PRIZE, not the body's own (ADR-0119 decision 2). A 1-prize Staryu one
            # hop from a 3-prize Mega Starmie ex prices at 2: what removing it DENIES is the form
            # that never arrives, and `prize_value` structurally cannot say so. This is the leg the
            # winner-take-all `survival_shift` above cannot supply — that one is lead-only because
            # the rules allow one attack a turn, so every non-leading body's removal Δ is a
            # Structural Zero however finely the clock is read.
            #
            # `prize` keeps the body's OWN value in the row: `prize_race` moves by THAT when the KO
            # actually lands, and consumers grouping equal-prize bodies mean the printed one.
            prize = model.theirs.view_of(b).prize_value
            line_prize, line_hops = model.theirs.forward_line_prize(b.get("id"))
            advance = needs.line_prize_advance(own_prize=prize, max_line_prize=line_prize,
                                               hops=line_hops)
            val = needs.opponent_target_value(prize_advance=advance, survival_shift=shift,
                                              phase=phase)
            area, bi = ("active", i) if i < len(active_list) else ("bench", i - len(active_list))
            row = {"body": b, "area": area, "bi": bi, "id": b.get("id"), "prize": prize,
                   "prize_advance": advance, "survival_shift": shift, "value": val,
                   # THE ROLE SHEET, as its own leg (Issue #395 D7) — exactly as `_relevance_terms`
                   # and `_strip_delta_terms` below attach theirs and let each consumer combine.
                   #
                   # It is NOT folded into `value`, and that is the ruling rather than an omission.
                   # `value` keeps its prize+clock meaning and its `TARGET_VALUE_CEILING` (3.9), so
                   # the two rates derived from that ceiling — `state_value._THREAT_W` and
                   # `currency.GUST_TARGET_WORTH_RATE` — are untouched and nothing is re-banded. A
                   # single fused scalar would also erase the thing the architecture already gets
                   # right: gust, snipe and deny ask DIFFERENT questions of the same body and each
                   # already weighs the steering layer differently.
                   #
                   # This is an ORDINAL priority, not a worth (D1) — it must never be summed into a
                   # prize-denominated number without a rate, and the only rate at this seam is
                   # derived from `currency.GUST_TARGET_BAND`, never authored.
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
        """Every attack of every form in an opponent body's LINE, as
        ``([(damage, {EnergyType: slots}, total_cost, is_forward), …], ability_fuel_types)``.

        The line is the body plus all its forward forms (`combat.forward_card_ids`, all-descendants
        since S1a) because attached Energy carries THROUGH an evolution — which is what lets an
        Energy on a Riolu be priced by Mega Lucario ex's Mega Brave rather than by Riolu's own
        30-damage poke. Colourless slots are dropped: they are payable by anything, so no specific
        Energy is ever on their critical path (this is why an Energy on a Meowth ex, whose Tuck Tail
        costs ``●●●``, scores 0 — the doctrine's *"ignore it"*).

        ``ability_fuel_types`` unions `CardStat.abilityEnergyTypes` over the line — the shipped
        ADR-0032 parse (Munkidori's Adrena-Brain *"if this Pokémon has any {D} Energy attached"*),
        read here rather than re-derived so deny and the attach marginal (Issue #139) cannot drift."""
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
