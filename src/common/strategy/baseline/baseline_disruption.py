"""BASELINE cluster: DISRUPTION — free pre-attack disruption Items (ADR-0025). Strip opponent Energy
before the turn-ending attack when there's something to strip. Pure data, no Mixin. (Grows as more
disruption mechanics — hand disruption, ability lock — land.)
"""
from common.strategy.context import _PLAY, _POSTURE_FAVORED, _POSTURE_MIN_COVERAGE
from common.strategy.refresh import refills_opponent
from common.strategy.strategy import Hypothesis
# _REFRESH_HAND_FLOOR RETIRED (ADR-0060): it guessed at "my hand is big enough that a redraw loses
# cards", but the card's own printed draw count IS that number (Judge 4, Lillie's 6/8, Harlequin EV 4).
# _STACKED_HAND (6) RETIRED (ADR-0102): its one reader, `strip-the-stacked-engine-hand`, is deleted.
_TAILORED_HAND = 3            # opponent hand size at/below which a hand they just tailored DOWN (dumped
                              # normally-kept cards to commit to a few key pieces) is worth Iono-ing to
                              # scatter — the MIRROR of the retired `_STACKED_HAND` 6 (which fired on a
                              # BIG stacked hand). Above it there's no tailored-down commitment to disrupt.
_COMEBACK_HAND_FLOOR = 2      # my hand size at/below which emptying it further into an enabled Unfair-Stamp
                              # is half-dead next turn — a 1-card hand can't rebuild after their post-KO
                              # redraw. At/below this, demote a hand-spend; hold a recovery out.

HYPOTHESES = [
    # RETIRED 2026-07-14 (ADR-0062): `play-energy-denial` (+20 flat). Two defects, one cause — it was
    # a flat endorsement over a quantity:
    #   • its GATE (`opp_active_has_energy`) was narrower than the card. Crushing Hammer reads "discard
    #     an Energy from 1 of your opponent's POKEMON" and the engine (`op_trash_energy_enemy`) offers
    #     their ACTIVE **and** BENCH — so we stood down whenever their Active was bare and their bench
    #     was loaded, and 4 Hammers sat dead in hand all game against a bench-loading deck.
    #   • its WEIGHT paid the same +20 for turning off a 270 nuke as for shaving 70 off a benched body,
    #     and could never DECLINE one: `_finish_turn_last` tiers a free Item ahead of everything, so any
    #     positive score got it played (ms 82749168 f29, "wasted crushing hammer").
    # `pilot._denial_play_tactical` + `strategy/denial.py` now own it: coin x what-the-strip-actually-
    # takes-away, net of keeping the card. Same lesson as ADR-0060 — price the quantity, don't threshold
    # it. The TARGET is ranked separately at the DISCARD_ENERGY select, which nothing scored before.
    # RETIRED 2026-08-02 (ADR-0102, Issue #261 item 2c): `play-harlequin-vs-hand-size` (+25) and
    # `disrupt-when-unfavored` (+18). Both were flat proxies for ONE unmodelled quantity — the damage
    # Alakazam's Powerful Hand scales off the opponent's hand — and `pilot._hand_size_relief_tactical`
    # now prices it as the survival it actually buys (Δ `turns_to_ko_me` at the card's redraw count,
    # in the shared sub-prize survival currency). Three failures die with them:
    #   • the +25 had NO opponent-hand gate, so Judging an EMPTY Alakazam hand REFILLED it 20 -> 80
    #     damage against my own Active (ml 85709280 f111, "an enormous blunder"). The clock reads that
    #     refill as a SHORTENED survival window, so the term declines it by arithmetic, not by a gate.
    #   • it paid the same +25 for a BENCHED hand-size line three turns from attacking as for a live
    #     one. The accumulating clock grades the threat by distance, through the ADR-0071 promotion
    #     gate every other threat read uses.
    #   • +18's posture half survives as a MULTIPLIER, never a flat (the ADR-0062 discipline) — but as
    #     `needs.phase_scale` rather than `_DENIAL_UNFAVORED`, because ADR-0078 decision 6 ruled that
    #     one path carrying both scalers multiplies one race read by itself, and the relief term reads
    #     `phase_scale` directly. Deny keeps the Read-gated scaler for exactly the opposite reason
    #     (ADR-0080 decision 3: it reads `phase_scale` on no surface).
    # The `energy_denial` half of +18 was already retired by ADR-0062; that note is preserved in the
    # ADR-0063 record and in `_denial_play_tactical`'s docstring.
    Hypothesis(
        id="dont-gift-a-refresh-when-favored",
        rationale="Lever A's favored half (ADR-0026 amendment) — the variance principle: unfavored "
                  "seeks variance (the shipped half), FAVORED denies the opponent outs. The one "
                  "durdle that gifts outs when ahead is a SYMMETRIC refresh as your dig — Judge / "
                  "Harlequin (`hand_disruption`) refill the LOSING opponent's hand too; Lacey / "
                  "Lillie's don't. −15 demotes it to a last resort (+20 dig → +5) without killing "
                  "targeted counterplay (`play-harlequin-vs-hand-size` +25 → net +30). Coverage-gated, "
                  "structurally exclusive with `disrupt-when-unfavored` (≥0.55 vs ≤0.45); "
                  "board-dominated, never overrides a KO.\n\n"
                  "**Sign-gated on the actual gift (2026-07-19, hand-disruption grill ruling 3).** The "
                  "rung taxes GIFTING outs — but its bare `hand_disruption` gate was blind to which "
                  "DIRECTION the refill points, so it also demoted a Harlequin that STRIPS a stacked "
                  "opponent hand (ep83664991 f43: opp hand 8, Harlequin redraws them to ≈4 — a denial, "
                  "not a gift). `refills_opponent` (the ADR-0060 swing facts) fires the tax only when the "
                  "play actually grows their hand (`opp_net > 0`, i.e. their hand below the card's redraw "
                  "count); a strip of a big hand is now untaxed, and a self-only Lillie's/Lacey never "
                  "reaches this rung at all. Fail direction honored: an unknown refresh makes no gift "
                  "claim, so it is never over-suppressed.",
        when=lambda c: c.option_type == _PLAY
        and "hand_disruption" in c.tags
        and c.board.matchup_coverage >= _POSTURE_MIN_COVERAGE
        and c.board.favorability >= _POSTURE_FAVORED
        and refills_opponent(c.card_id, c.board.opp_hand_size,
                             c.board.my_prizes_remaining, c.board.opp_prizes_remaining),
        weight=-15, status="testing"),
    # RETIRED 2026-07-14 (ADR-0060): `dont-shuffle-away-the-bigger-hand` (−25). It required the
    # `hand_disruption` tag, so it could not reach Lillie's at ALL (ms f94, my 10 / opp 3: the shipped
    # Pilot PLAYED it — the one frame where the blunder reached the argmax), and its
    # `_REFRESH_HAND_FLOOR = 5` was no card's break-even (Judge's is 4, Lillie's is 6). The card's own
    # printed draw count IS the break-even, so `pilot._refresh_swing_tactical` + `strategy/refresh.py`
    # now own every SYMMETRIC refill (Judge / Harlequin / Unfair Stamp) and every self-only refresh
    # (Lillie's / Lacey), closed-form off the card facts.
    # RETIRED 2026-08-02 (ADR-0102, Issue #261 item 2c): `strip-the-stacked-engine-hand` (+22), and
    # `_STACKED_HAND = 6` with it — the rung was the constant's last reader. It was kept by ADR-0060 as
    # a forward contract for a ONE-SIDED strip (a card that empties their hand without refilling it),
    # and no such card is in the pool, so it has never fired. What the POC changes is the standard: a
    # nonzero weight on an unfired gate is not a dormant contract, it is an untested rung that will
    # fire at full strength the first time the pool grows — which is precisely how a stale gate
    # (`disrupt-when-unfavored`'s `opp_denial_best > 0`) came to play a Hammer into a KO turn. The
    # doctrine survives where doctrine belongs: docs/plans/hand-disruption-grill-spec.md's fold list
    # records the contract, and a one-sided strip arriving in a future set gets PRICED — its hand
    # reduction is the same `atk_hand` counterfactual `_hand_size_relief_tactical` already asks, and
    # its card strip is the same `net_change` leg `_refresh_swing_tactical` already prices.
    # `disrupt-the-tailored-hand` below is the MIRROR contract and is deliberately left standing: it
    # carries weight 0, so it decides nothing and cannot surprise a future pool.
    Hypothesis(
        id="disrupt-the-tailored-hand",
        rationale="SEED(ladder): 22. REFUTED FOR SYMMETRIC REFRESHES (ADR-0060) — retained ONLY as a "
                  "forward contract for a genuinely ONE-SIDED strip (an Iono-class card that reduces "
                  "the opponent's hand WITHOUT refilling it). No deck in the pool runs one, so this "
                  "rung is inert by construction, not by accident. Why refuted: the premise was that "
                  "a hand the opponent TAILORED DOWN to a few key cards (`opp_last_turn_dumped` + "
                  "`opp_hand_size <= _TAILORED_HAND`) is worth scattering. But every `hand_disruption` "
                  "card we actually hold — Judge (4/4), Harlequin (EV 4/4), Unfair Stamp (5/2) — is a "
                  "symmetric REFILL: playing one into a 2-card opponent hand HANDS THEM 4 CARDS, a net "
                  "+2 for them. The human's own CRITICAL (ml 85709280 f111) calls Judging a 1-card "
                  "opponent hand 'an enormous blunder'. Gated on `shuffle_hand` NOT in tags so it can "
                  "never fire on a refill; if a one-sided strip ever enters the pool, this rung is "
                  "already correct and only needs its ladder-tuned seed.",
        when=lambda c: c.option_type == _PLAY
        and "hand_disruption" in c.tags
        and "shuffle_hand" not in c.tags            # ADR-0060: a REFILL can never strip a small hand
        and c.board.opp_last_turn_dumped
        and c.board.opp_hand_size <= _TAILORED_HAND,
        weight=0, status="assumed"),
    Hypothesis(
        id="unfair-stamp-comeback-posture",
        rationale="SEED(ladder): -18. The DEFENSIVE half of the Unfair-Stamp doctrine (the offensive/user "
                  "half is already covered — both `dragapult_ex` and `mega_lucario` run and sequence Stamp "
                  "as a post-KO comeback). Unfair Stamp (ACE SPEC, verified in pool) is playable ONLY by a "
                  "player who had a Pokémon KO'd on the opponent's last turn — so the turn I take a KO "
                  "(`opp_took_ko_this_turn`) against an opponent recognized to run a post-KO hand "
                  "disruptor (`opp_comeback_disruptor`), I have just ENABLED their Stamp next turn. "
                  "Emptying my hand to near-zero now leaves it half-dead to that redraw (a 1-card hand "
                  "can't rebuild). So DEMOTE a further hand-spend — a `hand_disruption`/`shuffle_hand` "
                  "PLAY (the cleanest hand-emptying predicate the option model exposes: these refresh/"
                  "dump my hand) — but only when I'm already low (`my_hand_size <= _COMEBACK_HAND_FLOOR`), "
                  "keeping the trigger conservative; preserve a recovery out. A soft negative demotion, "
                  "board-dominated, never overrides a KO (`_finish_turn_last`). DOUBLE-inert by design: "
                  "weight 0 (ADR-0009 by-id override, ladder-gated) AND `opp_comeback_disruptor` is False "
                  "until a matchup Brief asserts it (a separate agent registers the property) — so the "
                  "trigger is normally False too. Both are intentional: an opponent-model prior wired for "
                  "telemetry that changes nothing live until ladder-validated AND a Brief recognizes the "
                  "opponent.",
        when=lambda c: c.option_type == _PLAY
        and ("hand_disruption" in c.tags or "shuffle_hand" in c.tags)
        and c.board.opp_took_ko_this_turn
        and c.board.opp_comeback_disruptor
        and c.board.my_hand_size <= _COMEBACK_HAND_FLOOR,
        weight=0, status="assumed"),
]
