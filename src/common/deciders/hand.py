"""The hand's OUTFLOW: what a shuffle-refresh swings, what a forced discard sheds, and what a hand-size relief play is
worth.

The four refresh legs split by WHOSE hand they price and are NOT symmetric — my hand is face-up so its leg grades each
card; theirs is a `handCount`, so its legs can only be count x rate."""
from __future__ import annotations


from collections import Counter

from common.deciders.facts import Board, ShedPlan
from common.grading import halve as _halve
from common.strategy.combat import UNCHARGED
from common.strategy.context import _PLAY, _TO_HAND
from common.strategy.refresh import fresh_cards, net_change, opponent_shuffles, refresh_branches


# A shuffle-refresh moves cards in four directions and they are NOT worth the same per card. Pricing
# them symmetrically is what broke the guard family on the first cut: a per-card credit for cards I
# DRAW reached +76 and went straight through `hold-wincon-dont-shuffle` (−25),
# `hold-irreplaceable-tool-dont-shuffle` (−30) and `dont-refresh-into-a-probable-miss` (−25), which
# were all calibrated against `dig-before-commit`'s flat +20.
#
# The four legs split by WHOSE HAND they price, and the two sides are priced by different means for a
# structural reason: my hand is FACE-UP to me, so its leg can ask each held card what my board loses
# without it (the graded SHED); theirs is a `handCount` and nothing else, so their legs can only ever
# be `card count × a per-card rate`. The constants below carry `OPPONENT_HAND` in their names because
# reading `_REFRESH_STRIP` as "cards stripped from ME" is the natural misreading, and it inverts the
# sign of the whole term (Issue #261 review, 2026-08-01).
#
#   MY hand:     _REFRESH_CYCLE (+, flat)          · the SHED (−, GRADED — `_refresh_shed_keepcost`)
#   THEIR hand:  _REFRESH_OPPONENT_HAND_STRIP (+)  · _OPPONENT_HAND_FRESH (+)  · _OPPONENT_HAND_GIFT (−)
#
# STRIP and GIFT are one leg split by SIGN, never two live terms: both read the single signed
# `opp_net`, so `max(-opp_net, 0)` and `max(opp_net, 0)` cannot both be non-zero. A one-sided refresh
# (Lillie's, Lacey — they shuffle only MY hand) zeroes `opp_net` outright, leaving `CYCLE − SHED`.
_REFRESH_CYCLE = 20        # the DRAW side, flat: cards I have not seen are speculative and only as
                           # good as what the deck can still supply — which is precisely what the
                           # `hold-*-dont-shuffle` / probable-miss guards adjudicate. Bounded and flat
                           # so those guards can still cancel it, exactly as they could cancel the +20
                           # `dig-before-commit` used to supply blindly.

# _REFRESH_SHED (the flat −8/card-lost shed) RETIRED 2026-07-18 (ADR-0065), and its Σ-over-copies
# successor RETIRED 2026-08-01 (ADR-0101): the shed side is now the v2 assignment SET marginal over
# the whole hand (`_refresh_shed_keepcost`). ENERGY_TIER (8, `common.card_worth`) is the old flat anchor.
#
# The three OPPONENT-HAND rates below stay FLAT deliberately, and the reason is measured rather than
# doctrinal (ADR-0101; hand-disruption-grill-spec.md design A, PARKED). Grading them needs a worth for
# cards we cannot see, i.e. an expectation over their representative build — and 59.4% of that build
# prices `_role_value` 0 today, because role declarations come from OUR deck. The missing 59% is
# exactly their attackers and wincons, so a "derived" GIFT would be biased DOWNWARD precisely where it
# matters, making "Judge into their small hand" look cheap — ml f111's CRITICAL blunder.
#
# ⚠️ **The prerequisite is STILL UNMET, and Issue #395 did not discharge it** (D9). That issue built
# the shared opponent role sheet `gusting-keepcost-design.md` §2 names — `matchup_plan.ROLE_REGISTRY`
# plus `derive_general_roles` — and it is deliberately NOT the quantity these rates need. It is an
# ORDINAL PRIORITY over bodies IN PLAY; grading a hand strip needs a WORTH over cards we cannot see,
# an expectation across their representative build. The two are different quantities and citing the
# first does not supply the second. `card_worth.role_value` is untouched, so the 59.4% figure above is
# unchanged and remains exactly the reason. These retire when that worth exists, not before — and a
# later reader must not read "the role sheet exists now" as the condition having been met.
_REFRESH_OPPONENT_HAND_STRIP = 4   # per card stripped from THEIR hand — certain denial (ms f43/f45/f100/f64).

_REFRESH_OPPONENT_HAND_GIFT = 8    # per card HANDED to them: Judge into a 1-card opponent hand REFILLS
                           # them to 4. Priced like a shed — a card in their hand is as real as one in
                           # mine. The 4-vs-8 ratio is the denial haircut: denying them a card is worth
                           # about half handing them one, because they redraw into a fresh one.

_REFRESH_OPPONENT_HAND_FRESH = 2   # per stripped card THEY DREW LAST TURN (`opp_hand_size_delta` > 0):
                           # live resources denied, versus cards they have demonstrably been unable to play.

# _REFRESH_BENCH_BODY / `_refresh_cycle_adaptive` (the ADAPTIVE draw credit — "CYCLE should scale to
# the open bench-deploy need", ep83038055 f40) DELETED 2026-08-01 with the shadow that was its only
# reader (ADR-0101). It reported beside the flat CYCLE and decided nothing, so it fell with
# `_refresh_shed_shadow`; the promotion question it was measuring is now T3's, where a starved bench
# is priced by the `development` term family rather than by a second credit inside this equation.
# _GRAB_REFRESH_DRAW (the 0.1/card SUB-POINT grab tie-break) RETIRED 2026-08-06 (ADR-0122 amendment)
# together with the `grab-a-draw-supporter-in-setup` +10 it decorated. It was sized so a draw
# Supporter "tops out at <= +10.8 — never crossing the +15 chain opener", i.e. specified never to be
# able to say what ep86088989 f29 needed it to say. `_grab_refresh_value` now prices the grab by the
# refresh's real SWING (`_refresh_swing`), the same quantity the PLAY site scores.
# The discard equation's engine-supporter keep floor (ADR-0065 seam-D) — mirrors the ladder's
# `keep-engine-supporter-at-discard` (−8): a draw/search/dig SUPPORTER that is not hand_disruption
# is a draw engine kept over pure filler. Discard-CONTEXT (not general worth), tuned to the −8 band.
# NOTE: `heal`/`clutch_heal` are DELIBERATELY OUT (classification fix, 2026-07-21) — a heal Supporter
# (Wally's Compassion) is RECOVERY, not card advantage, and does not belong on the draw-engine slot.
# It was pricing Wally's at a saturated ~2.6 on the shared engine slot AND (as an `engine_cids`
# member) barring it from its rightful `general` worth (recovery role 20 → ~9). A heal that also
# genuinely draws still qualifies via its `draw`/`dig` tag; a pure heal now takes general worth.
_ENGINE_KEEP_TAGS = frozenset({"draw", "search", "dig"})

_ENGINE_SUPPORTER_KEEP = 8.0


class HandMixin:
    """Refresh swing, forced-discard shed and hand-size relief."""

    def _is_simultaneous_draw(self, board: Board, attack_id, opp_active_prize: int) -> bool:
        """True iff a game-winning KO with this attack is actually a DRAW (ADR-0022 #2): its UNCONDITIONAL
        recoil also Knocks Out my own Active and hands the opponent their LAST prize at the same Checkup as
        my own lethal — a simultaneous win, which the competition rules score as a draw (not a win, and not
        a loss). Requires both prize counts in the obs; conservative (only fires on a forced recoil that
        clears my Active's HP). Half (a) only — suppress the false win; valuing a forced draw above a loss
        is a noted refinement."""
        mp, op = board.my_prizes_remaining, board.opp_prizes_remaining
        if mp <= 0 or op <= 0:
            return False
        if opp_active_prize < mp:                            # this KO doesn't take my last prize -> not lethal
            return False
        recoil = self.combat.rider_recoil(attack_id)
        if not board.my_active_hp or recoil < board.my_active_hp:   # recoil doesn't self-KO my Active
            return False
        my_prize = self._prize_value({"id": board.my_active_id})
        return my_prize >= op                                # my self-KO gives them their last prize too

    def _stranded_evolution_set(self) -> frozenset:
        """Deck card ids that can NEVER be deployed from hand in this deck: evolutions whose
        previous-stage chain (`CardStat.evolvesFrom` names, walked to full depth) can't reach a
        Basic using only cards on the deck list — e.g. a Stage-2 Explosiveness opener with no
        Stage 1 in the deck (Cinderace without Raboot): in hand it is a dead card. Deck-static,
        so computed once; empty without a stats provider (fail-open — no card is called dead
        on unknown facts).

        The DECK-STATIC reading of `common.playability` (ADR-0104): same backward walk, with the
        whole decklist standing in for the reachable zone and nothing in play. Consolidated onto the
        one oracle by Issue #288 — this used to carry a private copy of the recursion, and the copy
        had no Rare Candy escape, so a deck running Rare Candy but no Stage 1 would have had its
        Stage 2 called permanently dead. That fix is provably silent on all four shipped decks (none
        holds both), which is exactly why the duplicate could survive."""
        cached = getattr(self, "_stranded_cache", None)
        if cached is not None:
            return cached
        if not self.stats:
            self._stranded_cache = frozenset()     # no facts, no card called dead
            return self._stranded_cache
        from common import playability
        deck_ids = set(self.deck or ())
        zones = playability.zones(self.stats, deck_ids=deck_ids,
                                  rare_candy_reachable=self._rare_candy_reachable(deck_ids))
        self._stranded_cache = frozenset(
            cid for cid in deck_ids
            if (st := self.stats.get(cid)) is not None and st.evolvesFrom
            and not playability.playable_from_hand(cid, stats=self.stats, zones=zones))
        return self._stranded_cache

    def _refresh_swing_tactical(self, obs: dict, board: Board, ctx) -> float:
        """Closed-form value of a shuffle-refresh (ADR-0060, SHED graded by ADR-0065). Judge/Harlequin
        are symmetric REFILLS, not strips: each player shuffles their hand away and redraws to the
        card's printed count, so the play is fully described by how many cards move, in which direction
        (strategy/refresh.py):

          MY hand      CYCLE                                 flat, speculative, guard-cancellable
                     - set_keep_v2(whole hand)               the graded SHED — what I lose
          THEIR hand + OPPONENT_HAND_STRIP * max(-opp_net,0) cards their shuffle takes  (certain)
                     + OPPONENT_HAND_FRESH * f               …of which they drew last turn
                     - OPPONENT_HAND_GIFT  * max(opp_net,0)  cards their redraw hands them (certain)

        Both opponent-side rates read the ONE signed `opp_net`, so STRIP and GIFT are a single leg
        split by sign and can never both fire; a one-sided refresh (Lillie's/Lacey shuffle only MY
        hand) zeroes `opp_net` and leaves `CYCLE − SHED` alone.

        The card's own printed draw count is the break-even. **The SHED side is graded** (WP7): it was
        a flat ``_REFRESH_SHED × cards-lost``, propped up by the hand-QUALITY guards (`hold-wincon` /
        `hold-line-piece-dont-shuffle` / `hold-irreplaceable-tool-dont-shuffle`) — a wincon and a dreg
        cost the same to shuffle.
        It became ``Σ keep_cost`` over the actual hand, and is now (ADR-0101) the **v2 assignment set
        marginal** `_refresh_shed_keepcost` — one price for the JOINT shed, so duplicate plan pieces
        cost what the pair is worth rather than twice what one is. A live hand of wincons/engines is
        expensive to shuffle, a dead hand nearly free, and the guards fold in as one currency.

        The DRAW side stays flat (`dont-refresh-into-a-probable-miss` owns redraw quality, a separate
        jurisdiction). Silent (0) on anything that is not the PLAY of a known refresh."""
        if ctx.option_type != _PLAY:
            return 0.0
        return self._refresh_swing(obs, board, ctx)

    def _refresh_swing(self, obs: dict, board: Board, ctx) -> float:
        """The refresh's own SWING, seam-free: ``CYCLE − SHED + STRIP + FRESH − GIFT`` for the card
        ``ctx.card_id``, on the board as it stands. 0.0 for a card that is not a known refresh.

        Extracted from `_refresh_swing_tactical` when the GRAB site needed the identical quantity
        (ADR-0122 amendment). Written once because the alternative is the drift this file has already
        paid for twice — `_removal_ranking_legs`' own docstring: *"a third leg reaches one site and
        not the other, which is exactly how `Pilot._order_key` came to exist."*

        **It is the same number at both seams, and that is a fact about the card rather than a
        convenience.** What a refresh is WORTH is what playing it does to the two hands; grabbing one
        buys exactly that, one step earlier. The only thing the grab site adds is WHEN it can be
        cashed, which is the caller's discount to apply, not this function's.

        Reading it at GRAB time is sound without adjustment, and the two hand terms are why.
        ``my_hand`` is the hand that will be SHUFFLED, and the fetched refresh is not in it — a
        played Supporter is discarded, not shuffled (`docs/rules.md`), so the shuffled set is the
        hand as it stands right now, which is what `board.my_hand_size` already reports. The shed
        side agrees by construction: `_refresh_shed_keepcost` excludes exactly one copy of
        ``ctx.card_id``, which is the copy that gets played — a no-op when the card is still in the
        deck, and correct when a duplicate is already held."""
        nets = net_change(ctx.card_id, my_hand=board.my_hand_size, opp_hand=board.opp_hand_size,
                          my_prizes_remaining=board.my_prizes_remaining,
                          opp_prizes_remaining=board.opp_prizes_remaining)
        if nets is None:
            return 0.0
        _my_net, opp_net = nets
        stripped = max(-opp_net, 0.0)
        fresh = fresh_cards(ctx.card_id, board.opp_hand_size, board.opp_hand_size_delta)
        return (_REFRESH_CYCLE
                - self._refresh_shed_keepcost(obs, board, ctx)
                + _REFRESH_OPPONENT_HAND_STRIP * stripped
                + (_REFRESH_OPPONENT_HAND_FRESH * fresh if stripped > 0 else 0.0)
                - _REFRESH_OPPONENT_HAND_GIFT * max(opp_net, 0.0))

    def _hand_size_relief_tactical(self, obs: dict, board: Board, ctx) -> float:
        """Value of playing a hand REFRESH against an attacker whose damage scales off a hand — the
        survival it buys me, or hands them (**ADR-0102**, promoting the hand-disruption grill's
        design B).

            relief = prize_to_damage( survival_value( turns_to_ko_me(the hands the card leaves)
                                                      − turns_to_ko_me(the hands as they stand) ) )

        Alakazam's Powerful Hand (MEG 743, *"2 damage counters … for each card in your hand"* = 20 per
        card in THEIR hand, aimed at MY Active) is INCOMING damage, so shrinking their hand is
        self-preservation, not opponent-worth. The whole term is therefore the same clock every other
        survival read speaks: ask `turns_to_ko_me` twice, once at the hands as they stand and once at
        the hands the card leaves both players on, and price the DIFFERENCE in the shared sub-prize
        survival currency (`needs.survival_value`), crossing to the damage scale on the derived
        `PRIZE_DAMAGE_RATE`. Nothing new is invented — the counterfactual is two keys of the Damage
        Formula's own opponent-as-attacker context, which is where every hand scaler already reads
        its count, and the two redraw numbers are `strategy/refresh.py`'s own branch facts.

        **BOTH hands, because the card moves both and the pool scales off both.** `atk_hand` is THEIR
        hand (Powerful Hand) and moves only for a symmetric refresh — the `opponent_shuffles`
        discriminator, exactly as `net_change` applies it. `def_hand` is MY hand, and it moves for
        every refresh in the table including the self-only ones: **Mega Froslass ex** (861, Resentful
        Refrain, *"50 damage for each card in your opponent's hand"*) and **Chandelure** (98, Mind
        Ruler, 30/card) are in the set, so holding ten cards in front of a Froslass is 500 incoming
        and a Lillie's down to six is the survival play. Pricing only their hand would have left the
        bigger of the two scalers unmodelled while claiming to price "the hand-size damage swing".

        **Marginal vs my own KO** (grill ruling 1a), which is why it replaces the flat rungs rather
        than joining them: 80 damage denied is worth ~0 when my Active survives either way (both
        clocks read the same, the difference is 0) and a great deal when it moves the clock. The flat
        +25 could not tell those apart, and its three failures all close here:

        * **Undervaluation** — `_REFRESH_OPPONENT_HAND_STRIP` x 4/card is a fifth of Powerful Hand's
          real 20/card; the clock reads the damage itself.
        * **The sign hole** — at their hand 1 the old terms netted ≈ +1, so the Pilot Judged an EMPTY
          Alakazam hand and refilled it from 20 to 80 damage against its own Active (ml 85709280 f111,
          *"an enormous blunder"*). Here the refill SHORTENS my clock, the shift is negative, and the
          term declines. Sign-correct by construction, not by a gate.
        * **The benched over-fire** — the retired rung fired on `opp_has_hand_size_attacker` anywhere
          in play, paying the same +25 for an Alakazam line that cannot attack for three turns. The
          accumulating clock prices a benched threat at its real distance, through the same promotion
          gate (`opp_active` + `switch_enabler`) every other threat read uses.

        There is deliberately **no card-fact gate** in front of the two clock reads. A guard asking
        "does any line here scale off a hand" would be a second enumeration of the Damage Formula's
        scaler families, free to disagree with the oracle it guards — the drift `card_level_damage`
        was extracted to end. The clock is the authority: on a board where nothing scales off a hand
        the two reads are equal and the term is 0, which is the same answer a guard would give and
        cannot fall out of step with the scaler table.

        **No Lever-A multiplier rides on top, and none is smuggled in either.** Stated precisely,
        because the loose version of this sentence is wrong: the Read-gated half of the deleted
        `disrupt-when-unfavored` (+18) is **not** re-expressed here — this term reads neither
        `favorability` nor `matchup_coverage`, so nothing "returns". It is SUBSTITUTED. ADR-0078
        decision 6 ruled that `_DENIAL_UNFAVORED` and `needs.phase_scale` say the same thing from
        different inputs, so a path carrying both multiplies one race read by itself, and named
        `phase_scale` the derived successor. Deny kept the Read-gated scaler only because it reads
        `phase_scale` on no surface (ADR-0080 decision 3, which says so in as many words); this term
        reads it directly, as its survival currency's own scaler — so the discipline the +18's
        posture half was owed ("posture SCALES the oracle, it is never re-added as a flat") is
        honoured by a scaler that was going to be here anyway, and is strictly the better instrument:
        board-derived, [0,1]-bounded, live without matchup coverage.

        **Fail direction.** Neither hand's size beyond the redraw count is knowable, so both clocks
        read hands that are CONSTANT over the horizon: the honest deterministic quantity, never a
        speculative refill projection.

        The energy policy is `UNCHARGED` — the DOOM policy, named rather than inherited, because this
        term is the graded generalisation of `_active_doomed` and must fail the way doom fails. The
        difference from the CEILING (`charged=None`) that the opponent-target rows take is not
        cosmetic: the ceiling reads an unresolvable attack cost through `can_pay_cheapest`, which is
        fail-CLOSED, and `_affords` says outright that pointed at the opponent this means *"I cannot
        tell what this costs, so assume it cannot reach me"* — the one thing a survival read must
        never say. Under `UNCHARGED` an unresolvable cost counts as payable and the current form is
        charged no affordability at all (the hidden-Ignition lesson). Threading the Read's own budget
        instead would let a matched Brief quietly relax a survival read (ADR-0064 keeps that
        conservatism per-consumer; the `doom-ceiling-fail-direction` whitelist entry is the policy).

        0 unless this is the PLAY of a refresh `strategy/refresh.py` knows, with a live Active to
        survive on and a counterfactual that actually moves a hand."""
        from common import needs
        from common.currency import prize_to_damage
        if ctx.option_type != _PLAY or not self.stats:
            return 0.0
        branches = refresh_branches(ctx.card_id, board.my_prizes_remaining,
                                    board.opp_prizes_remaining)
        model, now_ctx = self._state_model, self._opp_attack_context
        if branches is None or model is None or not now_ctx:
            return 0.0
        state = obs.get("current") or {}
        players = state.get("players") or []
        yi = state.get("yourIndex", 0)
        me = players[yi] if 0 <= yi < len(players) else {}
        opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
        ma = next((p for p in ((me or {}).get("active") or []) if p), None)
        if not (ma and opp):
            return 0.0
        # The two redraw counts, averaged over the card's coin branches exactly as the swing oracle
        # averages its own (Harlequin's 3/5 split is EV 4, the same number `net_change` prices). Their
        # hand moves only if the card shuffles it — the `opponent_shuffles` discriminator, applied
        # here for the same reason `net_change` applies it: a self-only refresh leaves them untouched.
        after = dict(now_ctx, def_hand=sum(m for m, _o in branches) / len(branches))
        if opponent_shuffles(ctx.card_id):
            after["atk_hand"] = sum(o for _m, o in branches) / len(branches)
        if after == now_ctx:
            return 0.0                      # the card moves no hand on this board: nothing to price
        clock = dict(charged=UNCHARGED,
                     opp_active=next((p for p in (opp.get("active") or []) if p), None),
                     switch_enabler=self._opp_switch_enabler())
        shift = (model.theirs.turns_to_ko_me(ma, context=after, **clock)
                 - model.theirs.turns_to_ko_me(ma, context=now_ctx, **clock))
        if not shift:
            return 0.0
        phase = needs.phase_scale(race_ahead=getattr(board, "race_ahead", None),
                                  opp_prizes_remaining=board.opp_prizes_remaining)
        return prize_to_damage(needs.survival_value(survival_shift=shift, phase=phase))

    def _grab_refresh_value(self, obs: dict, board: Board, ctx) -> float:
        """The DIFFERENCING value of grabbing a refresh: the swing playing it will produce
        (`_refresh_swing` — the identical quantity the PLAY site scores), discounted only for when it
        can be cashed. ADR-0122 amendment; ep86088989 f29 is the frame that forced it.

        **What this replaced, and why the replacement is a different KIND of thing.** It was
        ``_GRAB_REFRESH_DRAW × own_draw_count`` — 0.1 per card, deliberately sized so *"a draw
        Supporter (base +10) tops out at ≤ +10.8 — never crossing the +15 chain opener or a +18 line
        piece."* That constant did its stated job (it separated Lillie's 8 from Judge's 4 where the
        flat rung tied them) and could not do the job the board actually needed, **because it was
        specified never to.** On f29 — hand EMPTY, six prizes remaining, so Lillie's draws 8 — it
        priced the difference between a hand of 8 and a hand of 0 at **0.4 points**, and
        `grab-the-chain-opener` (+15) took a Team Rocket's Petrel instead.

        A sub-point tie-break cannot express a magnitude, and this is a magnitude. The two candidates
        do measurably different things to the board:

            Lillie's Determination   draws 8, one-sided       CYCLE 20 − shed 0 − gift 0   = +20
            Judge                    draws 4, REFILLS them 2  CYCLE 20 − shed 0 − gift 16  = +4

        The gift leg is the half the old term could not see at all: Judge shuffles BOTH hands, so it
        hands a 2-card opponent two fresh cards, while Lillie's touches only mine. Ranking by
        ``own_draw_count`` alone (8 ≻ 4) gets the right order here by luck — it would rank a big
        symmetric refill above a smaller one-sided one on a board where that is exactly backwards.

        **The quota discount is the one thing the grab adds** to the play-side number, and it is the
        shared convention rather than a rate invented here: a Supporter fetched after this turn's
        Supporter is spent cannot be cashed until next turn, so it takes `grading.halve(1)` — the
        same ADR-0070 §6 treatment `deploy_value` gives its own `supporter_quota_spent` leg.

        Gate unchanged from the term it replaces (setup `_TO_HAND`, a `draw` Supporter CARD known to
        `refresh_branches`), so this changes HOW MUCH the site says and never WHEN it speaks. Silent
        (0) otherwise."""
        if (board.line_ready or ctx.select_context != _TO_HAND or "draw" not in ctx.tags
                or not (ctx.stat and getattr(ctx.stat, "is_supporter", False))):
            return 0.0
        swing = self._refresh_swing(obs, board, ctx)
        if (obs.get("current") or {}).get("supporterPlayed"):
            swing *= _halve(1)
        return swing

    def _refresh_shed_keepcost(self, obs: dict, board: Board, ctx) -> float:
        """The graded SHED — the **v2 whole-hand assignment marginal** (ADR-0101, Issue #261 item 2b):
        what shuffling my hand away on a refresh costs = ``needs.set_keep_v2`` over EVERY held row,
        i.e. ``V(hand) − V(∅)`` under the exact bitmask-DP assignment of held cards to the board's
        resolved NEEDS (`_resolve_needs`), with each slot discounted by the closure's odds of
        re-supplying it inside the refresh's own draw window (`_refresh_slot_resupply`). One row per
        held copy except the played refresh itself (excluded once: it is discarded, not shuffled; a
        second held copy still charges — `_needs_hand_rows`).

        **Sets, not sums — the swap's whole point.** v1 was ``Σ keep_cost`` over the copies
        (`planner._hand_keep`, still the gamble keep-floor's own summation): it charged each duplicate
        wincon separately and OVER-priced the shed, so a refresh looked too costly on exactly the
        hands that most want refreshing. The assignment prices the pair as ONE covered line plus its
        succession slot, and a card covering nothing the board needs costs 0 however dear its catalog
        worth. The set marginal is the honest quantity here because a refresh sheds the hand
        JOINTLY — v1's per-copy sum was never the price of the move it was pricing.

        0 when the hand resolves to no rows or the card is not a known refresh — the CYCLE credit
        alone stands, matching the retired flat term's floor.

        **One floor moved, and in the safe direction.** v1 returned 0 when the deck bookkeeping was
        unresolved (no anchor and no usable unseen composition); v2 still prices the hand, because
        `_refresh_slot_resupply` returns all-zero resupply in that case and the assignment then
        charges the UNDISCOUNTED set marginal. So an unresolved tracker now makes the shed dearer
        rather than free — it over-prices the shuffle instead of under-pricing it, which is the
        fail direction this site has taken throughout (the WP-N6 sweep's "safe side")."""
        from common import needs
        from common.strategy.refresh import refresh_branches
        branches = refresh_branches(ctx.card_id, board.my_prizes_remaining, board.opp_prizes_remaining)
        if not branches:
            return 0.0
        draws = max(my_draw for my_draw, _opp in branches)
        rows = self._needs_hand_rows(obs, board, exclude_cid=ctx.card_id)
        if not rows:
            return 0.0
        slots, elig = self._resolve_needs(obs, board, rows)
        resupply = self._refresh_slot_resupply(slots, elig, rows, obs, board, draws)
        return needs.set_keep_v2(slots, elig, resupply, range(len(rows)))

    def _discard_fuel_types(self) -> frozenset:
        """Energy types a DISCARD-SOURCE accel attack in this deck wants IN the discard — the
        Aura-Jab class (``AttackStat.recoverN`` > 0, ``recoverSource == "discard"``; ``None`` in the
        set = the attack takes any Basic). Pitching a matching Basic Energy is FUEL, not loss —
        the zone-signed worth the spec's Round 7 ruled (Kyogre-class; correction 84071010-45 held
        surplus Energy FOR the recycle). Memoised — deck-fixed. Empty without stats/deck."""
        if self._discard_fuel_cache is None:
            types = set()
            for cid in set(self.deck):
                st = self.stats.get(cid) if self.stats else None
                for aid in (getattr(st, "attacks", None) or ()):
                    ast = self._attack_stat(aid)
                    if (ast is not None and getattr(ast, "recoverN", 0)
                            and getattr(ast, "recoverSource", None) == "discard"):
                        types.add(getattr(ast, "recoverEnergyType", None))
            self._discard_fuel_cache = frozenset(types)
        return self._discard_fuel_cache

    def _discard_needs_pick(self, obs: dict, select: dict, board: Board, options: list, picks: int):
        """**The** forced-discard DECIDER, unconditionally (ADR-0065 WP-N4, the per-family swap):
        the pick IS the keep-value v2 needs-assignment's cheapest removal (`_needs_v2` → `eq2_pick`,
        `needs.cheapest_removal` over the resolved slots, hedged at v1's post-gate keep), replacing
        v1's per-card gate composition with the global assignment. Same rows as v1's ranking
        (`_discard_equation_rows` — the deploy gates + fuel/burst flags v2 consumes); None when
        nothing is priceable, and since Issue #261 item 2h there is nothing under it to fall through
        TO — the caller's ordinary scored order takes the pick.

        There is no kill-switch (Issue #319). This read "the DECIDER under the `needs_keep_value`
        kill-switch" while that flag was assigned and never read — item 2h made the call site
        unconditional and nothing has gated this since. The flag is deleted rather than rewired
        because there is nothing to revert TO: item 2h deleted seam-D v1 AND the `_DISCARD` ladder,
        there is no `baseline_discard`, and no rung anywhere fires at `_DISCARD`, so an OFF branch
        would drop the select to the ordinary scored order — a path nothing has ever graded."""
        rows = self._discard_equation_rows(obs, select, board, options)
        if not rows:
            return None
        _keeps, eq2_pick = self._needs_v2(obs, board, rows, picks)
        return eq2_pick or None

    def _discard_equation_rows(self, obs: dict, select: dict, board: Board, options: list):
        """The card-worth discard equation's per-candidate rows — the priced input the keep-value v2
        needs-assignment (`_discard_needs_pick` → `_needs_v2`) consumes, plus the gates/fuel/burst
        flags the gust and refresh keep-value sites read off the same computation. Pure and
        deterministic (safe mid-sim). Returns ``[]`` when nothing is priceable.

        It used to return a second value, v1's ``(keep asc, pitch desc, worth asc, index)`` ranking,
        which was the seam-D decider's whole answer. That decider and the ladder under it are gone
        (Issue #261 item 2h), and a ranking nobody reads is a second definition of "cheapest to lose"
        sitting beside `needs.cheapest_removal` waiting to drift — so it goes with them."""
        me = self._my_player(obs)
        from collections import Counter
        hand_ids = [c.get("id") for c in (me.get("hand") or []) if c and c.get("id") is not None]
        held = Counter(hand_ids)
        counts = self._unseen_deck_counts(me, board)
        from common import fetch_closure
        def _recyclers(stat):
            in_hand = in_deck = 0
            for rid, n in held.items():
                if any(cl.get("kind") == "fetch" and cl.get("zone") == "discard"
                       and fetch_closure.fetch_target_matches(cl, stat)
                       for cl in (self.effects.clauses(rid) if self.effects else ())):
                    in_hand += n
            for rid, n in counts.items():
                if n > 0 and any(cl.get("kind") == "fetch" and cl.get("zone") == "discard"
                                 and fetch_closure.fetch_target_matches(cl, stat)
                                 for cl in (self.effects.clauses(rid) if self.effects else ())):
                    in_deck += n
            return in_hand, in_deck
        fuel_types = self._discard_fuel_types()
        rows = []
        for i, o in enumerate(options):
            cid = self._option_card_id(obs, select, o)
            if cid is None:
                continue
            st = self.stats.get(cid) if self.stats else None
            tags = self.functions.tags(cid) if (self.functions and cid is not None) else ()
            worth = self._role_value(cid)
            # The engine-supporter WORTH floor (Finding 2's 5th premise gate, mirrored for the swap):
            # a draw/search/dig SUPPORTER that is NOT hand_disruption (Lillie's, not Harlequin) is
            # a draw engine worth keeping over pure filler, though it carries no ROLE/TAG worth.
            # (heal/clutch_heal excluded — a pure-heal Supporter is recovery, not a draw engine.)
            # Discard-CONTEXT (mirrors `keep-engine-supporter-at-discard` −8). A WORTH floor, not a keep
            # floor — it is still discounted by re-access (a duplicate engine supporter is covered) and
            # by the gates (a need-met tutor still zeros), unlike a hard override.
            engine_supporter = bool(st is not None and getattr(st, "is_supporter", False)
                                    and (_ENGINE_KEEP_TAGS & set(tags)) and "hand_disruption" not in tags)
            if engine_supporter and worth < _ENGINE_SUPPORTER_KEEP:
                worth = _ENGINE_SUPPORTER_KEEP
                row_engine = True
            else:
                row_engine = False
            row = {"i": i, "cid": cid, "worth": round(worth, 1)}
            if row_engine:
                row["engine_supporter"] = True
            dup = held.get(cid, 0) >= 2
            in_play = cid in board.in_play_ids
            rec_hand, rec_deck = _recyclers(st) if (st is not None and worth > 0) else (0, 0)
            fuel = bool(st is not None and getattr(st, "is_basic_energy", False)
                        and (None in fuel_types
                             or getattr(st, "energyType", None) in fuel_types))
            deploy = self._deploy_odds(cid, board, counts)
            if dup:
                row["dup_hand"] = True
            if in_play:
                row["in_play"] = True
            if rec_hand:
                row["recycler"] = rec_hand
            if rec_deck:
                row["recycler_deck"] = rec_deck
            if fuel:
                row["fuel"] = True
            if deploy != 1.0:
                row["deploy"] = deploy
            # The DEPLOY-NOW spike (closing edge, ep86091435 f68): an in-play same-card copy does NOT
            # cover THIS body's this-turn evolution, so re-access is not bankable — zero the credit
            # and the card charges FULL worth. Distinguishes the open Drakloak (keep) from the
            # just-benched-base one (ep83686860 f18, not in deploy_now_ids -> re-access still credited).
            closing = self._gate_closing(cid, board)
            if closing:
                row["closing"] = True
            reaccess = 0.0 if closing else (1.0 if (dup or in_play or rec_hand) else 0.0)
            # A SPENT burst (ladder-win 83454549-36): a `discard_eot` Energy is precious until the
            # Active is fully powered — then it self-discards at end of turn anyway, so it is fodder.
            # DISCARD-CONTEXT (at a refresh it is a next-turn attach), so it lives in the row's
            # pitch term, not a general Worth gate.
            spent_burst = "discard_eot" in tags and getattr(board, "active_fully_powered", False)
            row["keep"] = 0.0 if (fuel or spent_burst) else round(worth * deploy * (1.0 - reaccess), 1)
            # The PITCH-PREFERENCE term (seam-D grill Finding 3): keep-cost is a KEEP floor and
            # cannot RANK a discard — a dreg, a duplicate, and a DEAD card all price keep 0. The
            # pitch side is `P(met | pitch) − P(met | keep)` going positive: a card whose role is
            # EXPIRED/useless (or whose discard is progress) is actively best gone. Mirrors the
            # ladder's positive-pitch premises at SOURCE (not their weights — the equation ranks):
            # `discard-the-dead-opener` (opener role spent), `discard-the-redundant-tutor` (wincon in
            # hand → the tutor's target is had), a stranded evolution (payoff with no base), the
            # declared `discard_fodder`, `fuel` (zone sign), and the SPENT burst above. `pitch` = the
            # count; it breaks the zero-keep ties so dead weight sheds before a live spare. The
            # `redundant_tutor` case is now ALSO priced keep 0 by the need-met gate (`_deploy_odds`);
            # the flag stays for the pitch tie-break + display. SHADOW-only, deciding nothing.
            self._apply_pitch_terms(row, cid, tags, board, fuel=fuel, spent_burst=spent_burst)
            rows.append(row)
        return rows

    def _apply_pitch_terms(self, row: dict, cid, tags, board, *, fuel: bool, spent_burst: bool):
        """Write the PITCH-PREFERENCE term and its flags onto a priced row, in place.

        Keep-cost is a KEEP floor and cannot RANK a discard — a dreg, a duplicate and a DEAD card all
        price keep 0 (seam-D grill Finding 3). The pitch side is `P(met | pitch) − P(met | keep)`
        going positive: a card whose role is EXPIRED or whose discard is progress is actively best
        gone. It mirrors the retired `_DISCARD` ladder's positive-pitch premises at SOURCE, never
        their weights — `discard-the-dead-opener` (opener role spent), `discard-the-redundant-tutor`
        (wincon in hand → the tutor's target is had), a stranded evolution (payoff with no base), the
        declared `discard_fodder`, `fuel` (zone sign), and the SPENT burst. ``pitch`` is the COUNT.

        TWO terms, and each difference between them is load-bearing (ADR-0106).

        ``deadness`` is the five expired-role bits, **categorical** — dead, or not — and it is what
        RANKS a discard among cards the assignment prices equal (`needs.cheapest_removal`'s deadness
        leg). It is a BIT rather than a count on purpose: nothing has ever ruled that a card which is
        both stranded and declared fodder is *deader* than one that is only fodder, and an order
        asserted from ignorance is the design ADR-0091 decision 2 rejects. Summing across a removal
        SET is a different claim and is correct — shedding two dead cards beats shedding one.

        ``pitch`` is the COUNT, unchanged, and adds the `fuel` zone sign. It gates LATENT worth
        (`_resolve_needs` withholds a general slot from a pitch-flagged row) and the shed predictor's
        junk band; both read it as ``> 0``. Fuel is deliberately absent from ``deadness``: a matching
        Energy is not EXPIRED, it is a discard that FILLS a slot, and `needs.pitch_gain` already
        prices that in the removal SCORE. Ranking on it too double-prices it — measured on
        `83966336|0|decision|27`, where the fuel Energy was also the only card covering the
        `fund_attack` slot, so its pitch gain and its keep loss cancelled to a tie and the second
        count then shed the attack's only funder (Discrimination Gate OK -> MISS, rank 1 -> 3).

        Shared by both row builders (Issue #261 item 2h): `_discard_equation_rows` over a discard
        menu, and `_needs_hand_rows` over the whole hand, which needs it since the fetch doctrine's
        shed predictor moved onto the v2 machinery — a card is dead weight or it is not, and two
        derivations of that would drift the discard decider away from the predictor of it."""
        roles = self._roles_of(cid)
        dead_opener = "opener" in tags
        redundant_tutor = bool(getattr(board, "wincon_in_hand", False)
                               and ({"rush_evolve", "tutor_mega"} & set(tags)))
        stranded = cid in self._stranded_evolution_set()
        fodder = "discard_fodder" in roles
        if dead_opener:
            row["dead_opener"] = True
        if redundant_tutor:
            row["redundant_tutor"] = True
        if stranded:
            row["stranded"] = True
        if fodder:
            row["fodder"] = True
        if spent_burst:
            row["spent_burst"] = True
        expired = (dead_opener, redundant_tutor, stranded, fodder, spent_burst)
        row["deadness"] = int(any(expired))                     # CATEGORICAL: dead, or not
        row["pitch"] = int(fuel) + sum(int(b) for b in expired)  # the COUNT, unchanged

    @staticmethod
    def _removal_ranking_legs(rows: list) -> dict:
        """The two ORDERING legs `needs.cheapest_removal` ranks equal-cost removals by, read off
        priced rows — ``{deadness, tiebreak}``, ready to splat.

        One spelling, because two callers need the SAME order and not merely the same idea of one:
        the discard DECIDER (`_needs_v2`) and the fetch doctrine's shed PREDICTOR (`_shed_signals`),
        which asks what the set the decider *would* take costs. A predictor ranking by a different
        key than the decider stops predicting it — the drift ADR-0103 Amendment A extracted
        `needs.removal_score` to close, one leg further down. Written twice, a third leg reaches one
        site and not the other, which is exactly how `Pilot._order_key` came to exist.

        ``deadness`` is the row's categorical dead bit; ``tiebreak`` is residual worth
        (``worth × deploy``) — the ADR-0065 WP-N3 leg, kept BELOW deadness because residual worth
        reads a catalog tier that a corpse still carries. Rows missing either field read 0, which is
        the neutral value for both legs (`_needs_hand_rows` output before `_as_discard_rows`
        enriches it carries no pitch terms at all, by design)."""
        return {"deadness": [r.get("deadness", 0) for r in rows],
                "tiebreak": [r.get("worth", 0.0) * r.get("deploy", 1.0) for r in rows]}

    def _cost_shed(self, obs: dict, board: Board = None, *, exclude_cid=None, picks: int):
        """**The ONE answer to "which cards does a `picks`-card play cost actually take?"** —
        `ShedPlan(hand_indices, row_indices, rows, cost)`, or ``None`` when the hand cannot legally
        pay (fewer than ``picks`` other cards, the engine's own `handOthers` gate).

        Two consumers, and they must not disagree:

        * `doctrine_fetch._shed_signals`, the fetch doctrine's shed PREDICTOR, which asks what the
          set costs so a dig can be priced. It used to spell this inline with a hardcoded ``2``.
        * `cost_shed_indices`, the apply seam's oracle: `board_expectation` has to APPLY Ultra
          Ball's *"discard 2 other cards"* before its search, and the set it assumes must be the set
          the live decider would actually pick. Predicting with any other formula is precisely the
          drift ADR-0103 Amendment A extracted `needs.removal_score` to close.

        The answer is `needs.cheapest_removal` — the equation that already DECIDES the forced
        discard — over the same rows, resolver and ordering legs `_needs_v2` uses. Deliberately NOT
        `keep_v2` at the select: Issue #406 built that, measured it worse (incumbent 23/30 against
        the spec's 17/30) and reverted it (ADR-0121).

        ``intrinsics`` are all-0.0 and ``resupply`` all-0.0, both inherited rather than re-chosen: a
        forced discard has no redraw window, and no v1 post-gate hedge exists over HAND rows.

        ``board`` defaults through `_board_hypothetical`, so a caller holding only a synthesized
        observation — which the apply seam always does — needs no `Board` of its own."""
        from common import needs
        board = self._board_hypothetical(obs) if board is None else board
        rows = self._as_discard_rows(self._needs_hand_rows(obs, board, exclude_cid=exclude_cid),
                                     obs, board)
        if len(rows) < int(picks):
            return None
        slots, elig = self._resolve_needs(obs, board, rows)
        resupply = [0.0] * len(slots)            # a forced discard has no redraw window (as `_needs_v2`)
        intrinsics = [0.0] * len(rows)           # no v1 post-gate hedge exists over the HAND rows
        pick = needs.cheapest_removal(slots, elig, resupply, intrinsics, int(picks),
                                      **self._removal_ranking_legs(rows))
        cost = needs.removal_score(slots, elig, resupply, intrinsics, pick)
        # `hand_i`, NOT `i`. The rows are built with one copy of `exclude_cid` already dropped, so a
        # row ordinal is short of the true hand position for every card sitting after the excluded
        # one. Reading `i` here made the picks collide with the played card's own index, which
        # `board_expectation._paid` then filtered out — turning a legal Ultra Ball into "not legal on
        # this board" whenever it was not the last card in hand.
        return ShedPlan(hand_indices=tuple(sorted(rows[k]["hand_i"] for k in pick)),
                        row_indices=tuple(pick), rows=rows, cost=float(cost))

    def cost_shed_indices(self, model, option: dict, picks: int) -> tuple:
        """The `shed` seam `board_expectation.expectation` takes — the HAND INDICES a cost would
        take, on the model's OWN observation.

        Public and model-shaped because the apply seam has no Pilot and cannot get one:
        `common/composer.py` holds no `Pilot` anywhere (its only `strategy` import is
        `strategy.context`, a pure constants module), and `StateModel.mine.needs` is either `None`
        in production or the LEAF resolution, which is resolved `include_general=False` with no
        pitch terms and pinned to the ROOT observation (Issue #400 Phase 2). So the composer's
        CALLER — which does hold a Pilot — passes this in, exactly as it already passes
        `search_api` / `deterministic` / `clauses_cover`.

        Raises nothing and returns ``()`` when the hand cannot pay, which the seam reads as a
        refusal rather than as a free cost."""
        obs = getattr(model, "source_obs", None) or {}
        seat = int(getattr(model, "my_index", 0))
        hand = ((obs.get("current") or {}).get("players") or [{}])[seat].get("hand") or ()
        index = (option or {}).get("index")
        played = (hand[index] or {}).get("id") if isinstance(index, int) and 0 <= index < len(hand) \
            else None
        plan = self._cost_shed(obs, exclude_cid=played, picks=picks)
        return plan.hand_indices if plan is not None else ()

    def _as_discard_rows(self, rows: list, obs: dict, board: Board) -> list:
        """`_needs_hand_rows` output re-read in DISCARD context — the pitch terms plus the two cheap
        re-access facts, on copies.

        Separate from `_needs_hand_rows` because the pitch terms are **context-dependent and the
        resolver reads them**: `_resolve_needs` withholds a card's general slot when its pitch term
        flags it dead, and its own comment says why the refresh rows must not carry one — *"a
        SHUFFLED burst IS a future attach, so they keep their general worth."* Writing the flags in
        the row builder made every refresh SHED read its hand as a discard, which is measurable and
        was measured: the Lillie's big-hand pins and two hyperclosure corpus frames all moved.

        A `cost_discard` fetch is the other case: those cards really are discarded, so discard
        semantics are the correct ones and the predictor asks for them explicitly.

        The re-access facts (`dup_hand` / `in_play`) carry the same names and meaning as
        `_discard_equation_rows`', which folds them into its `reaccess` discount. Deliberately NOT
        the recycler legs — those need that method's per-card effects closure, and omitting them is
        conservative for the consumer here (the shed predictor's junk band): a recyclable card reads
        as NOT replaceable, so a costly dig gets less lift than it might deserve, never more."""
        from collections import Counter
        held = Counter(r["cid"] for r in rows)
        out = []
        for r in rows:
            cid = r["cid"]
            tags = self.functions.tags(cid) if (self.functions and cid is not None) else ()
            row = dict(r)
            if held.get(cid, 0) >= 2:
                row["dup_hand"] = True
            if cid in board.in_play_ids:
                row["in_play"] = True
            self._apply_pitch_terms(
                row, cid, tags, board, fuel=bool(r.get("fuel")),
                spent_burst="discard_eot" in tags and getattr(board, "active_fully_powered", False))
            out.append(row)
        return out

    def _refresh_slot_resupply(self, slots, elig, rows, obs: dict, board: Board,
                               draws: int) -> list:
        """The slot-RESUPPLY leg for the REFRESH window (the WP-N5 residual's staged fix): per slot,
        P(the closure re-supplies it within the refresh's own ``draws``-card window) — the discount
        `needs.assignment_value` applies to a covered slot's marginal (×(1−r)) and credits an
        uncovered one (×r). The whole hand shuffles in with the played refresh, so the outs are the
        slot's supplier CLASSES pointed backwards over the shuffle-grown pool: deck copies + the
        tutors reaching any class (`fetch_closure.class_reaccess_outs` — each tutor once), with the
        slot's own eligible HELD copies joining as CERTAIN outs (a shuffled hand card is never
        prize-assignable) — v1's `_keep_cost` model per slot instead of per copy.

        Fail directions, all toward KEEP (a lower r → a higher shed price — the sweep's measured
        SAFE side): ``deploy_now`` / ``answer_doom`` slots stay 0.0 (the closing edge,
        `gate_library.closing_gate_reaccess` — re-access is not bankable against a this-turn
        deadline), and so does ANY ``deny`` or ``line`` slot at deadline ≤ 0 — a strip needed NOW
        (thread-2 ruling: not re-drawable in time) or the URGENT successor line slot (the
        answer-doom ruling: a doomed wincon's replacement is needed imminently); a slot with slack
        banks re-access like any other; the supplier classes are read off the HELD eligibility
        only (a deck-only filler
        class is not counted); the no-deadline (99) slots take the plain window, only
        ``fund_attack`` widens by its quota deadline (`gate_library.quota_window` re-derived:
        window = draws + deadline, one natural draw per intervening turn); unresolved deck
        bookkeeping → all-0.0 (no discount — v2 keeps over-pricing rather than under-pricing).
        Pre-anchor the outs are prize-split-weighted (`_prize_split_hit`), anchored the plain
        window draw — exactly the `_refresh_shed_keepcost` bookkeeping. Pitch-side (fuel) slots
        never enter the keep DP; theirs stay 0.0.

        ``general`` slots ALSO stay 0.0 — measured, not doctrinal (sweep 2026-07-20): their value
        already carries `_GENERAL_WORTH_W` (0.45), a latent-worth constant MEASURED with resupply
        at 0.0 (WP-N5: under-pricing 46→19 came from W alone), so W is empirically the site's
        whole re-access + latency discount. Stacking ×(1−r) on top priced a general slot at
        ~0.45 × v1's own re-access model and flipped the sweep to the UNSAFE side (under-pricing
        19→62, sign-flips 13→17). Re-open only as a JOINT re-measure of W and r, never r alone."""
        from common import fetch_closure
        from common.deck_odds import draw_hit_probability
        out = [0.0] * len(slots)
        me = self._my_player(obs)
        counts = board.deck_known_counts
        if counts:
            deck_count = sum(counts.values())
            prizes_hidden = 0                                    # anchored: the split is resolved
        else:
            from collections import Counter
            unseen = Counter(self.deck)
            unseen.subtract(self._visible_card_counts(me))
            counts = {cid: n for cid, n in unseen.items() if n > 0}
            prizes_hidden = sum(1 for p in (me.get("prize") or [])
                                if not (isinstance(p, dict) and p.get("id") is not None))
            deck_count = sum(counts.values()) - prizes_hidden
            if deck_count <= 0 or not counts:
                return out
        pool = deck_count + len(rows)                            # the shuffle-grown pool: rows ARE
        members: list = [[] for _ in slots]                      # the shuffled copies (refresh excluded)
        for k, js in enumerate(elig):
            for j in js:
                members[j].append(k)
        for j, s in enumerate(slots):
            if (s.supplied_by_pitch or s.kind in ("deploy_now", "answer_doom", "general")
                    or (s.kind in ("deny", "line") and s.deadline <= 0) or not members[j]):
                continue                       # closing edge: a THIS-TURN deadline (the urgent
                                               # successor, a ready-threat deny) can't bank re-access
            classes = {rows[k]["cid"] for k in members[j]}
            u = fetch_closure.class_reaccess_outs(classes, counts, self._closure_stat_of,
                                                  self._closure_clauses_of)
            certain = len(members[j])
            # fund_attack widens by its quota deadline; a LINE slot CLAMPS to its readiness deadline
            # (piece 1) — a wincon one attach from live gets only its ~1-2-draw re-access window, not
            # the whole refresh redraw, so its shed cost stays material; other slots take the window.
            if s.kind == "fund_attack":
                window = draws + s.deadline
            elif s.kind == "line":
                window = min(draws, s.deadline)
            else:
                window = draws
            if prizes_hidden > 0:
                r = self._prize_split_hit(u, deck_count, prizes_hidden, pool, window,
                                          certain=certain)
            else:
                r = draw_hit_probability(u + certain, pool, window)
            out[j] = max(0.0, min(1.0, r))
        return out
