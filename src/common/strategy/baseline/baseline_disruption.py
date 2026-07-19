"""BASELINE cluster: DISRUPTION — free pre-attack disruption Items (ADR-0025). Strip opponent Energy
before the turn-ending attack when there's something to strip. Pure data, no Mixin. (Grows as more
disruption mechanics — hand disruption, ability lock — land.)
"""
from common.strategy.context import (_PLAY, _POSTURE_FAVORED, _POSTURE_MIN_COVERAGE,
                                     _POSTURE_UNFAVORED)
from common.strategy.refresh import refills_opponent
from common.strategy.strategy import Hypothesis
_STACKED_HAND = 6             # opponent hand size at/above which a `draw` engine has visibly STACKED
                              # resources (opening hand 7, +1/turn) — worth a hand_disruption Supporter
                              # to strip; below it HOLD (don't gift a fresh hand). ADR-0051 Phase 3b, ladder-tunable
# _REFRESH_HAND_FLOOR RETIRED (ADR-0060): it guessed at "my hand is big enough that a redraw loses
# cards", but the card's own printed draw count IS that number (Judge 4, Lillie's 6/8, Harlequin EV 4).
_TAILORED_HAND = 3            # opponent hand size at/below which a hand they just tailored DOWN (dumped
                              # normally-kept cards to commit to a few key pieces) is worth Iono-ing to
                              # scatter — the MIRROR threshold of `_STACKED_HAND` (which fires on a BIG
                              # stacked hand). Above it there's no tailored-down commitment to disrupt.
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
    Hypothesis(
        id="play-harlequin-vs-hand-size",
        rationale="Play a `hand_disruption` Supporter (e.g. Harlequin, which shuffles both hands into "
                  "the deck and redraws) when the opponent has a `hand_size_attacker` in play or a "
                  "committed evolution line into one (e.g. Alakazam's Powerful Hand scales with hand "
                  "size) — shrinking their hand cuts that attacker's damage. `hold-wincon-dont-shuffle` "
                  "still suppresses it when your own win-condition is in hand, and `_finish_turn_last` "
                  "sequences the shuffle before the attack so you disrupt and still attack the same turn.",
        when=lambda c: c.option_type == _PLAY
        and "hand_disruption" in c.tags and c.board.opp_has_hand_size_attacker,
        weight=25, status="testing"),
    Hypothesis(
        id="disrupt-when-unfavored",
        rationale="Lever A (ADR-0026): when the Read says the matchup is unfavorable (compiled win-rate "
                  "at/below `_POSTURE_UNFAVORED`, backed by `_POSTURE_MIN_COVERAGE` evidence), up-weight "
                  "an already-useful free disruption since the straight race loses. The favored half is "
                  "`dont-gift-a-refresh-when-favored` (ADR-0026 amendment).\n\n"
                  "**The `energy_denial` half is RETIRED (ADR-0062 amendment).** It claimed to 'ride on "
                  "top of the base disruption rule so it never boosts a wasteful one' — but after "
                  "ADR-0062 retired the flat `play-energy-denial`, the base rung it rode became a signed "
                  "TACTICAL (`coin x denial - the cost of keeping the Item`, and zero when I can already "
                  "KO their Active). This rung kept the coarse `opp_denial_best > 0` gate — the raw "
                  "PRESENCE of denial — so a flat +18 sat on top of an oracle that had said HOLD, and a "
                  "free Item at score > 0 is tiered ahead of everything by `_finish_turn_last`. It played "
                  "a Hammer into a KO turn against a bare opponent bench (ms 83968638 f17, CRITICAL). "
                  "A booster must SCALE the oracle, never ADD to it: the unfavored amplification now "
                  "lives INSIDE `_denial_play_tactical` as `_DENIAL_UNFAVORED`, where multiplying a whiff "
                  "(0) or a hold (negative) cannot flip it positive.\n\n"
                  "The `hand_disruption` half SURVIVES because it stands on a different axis: it fires "
                  "against an `opp_has_hand_size_attacker` (Alakazam's Powerful Hand scales damage with "
                  "hand size), where the strip denies DAMAGE rather than cards — a quantity ADR-0060's "
                  "swing oracle does not model. It is a proxy for an unmodelled value, not an override "
                  "of a modelled one.",
        when=lambda c: c.option_type == _PLAY
        and c.board.matchup_coverage >= _POSTURE_MIN_COVERAGE
        and c.board.favorability <= _POSTURE_UNFAVORED
        and "hand_disruption" in c.tags
        and c.board.opp_has_hand_size_attacker,
        weight=18, status="testing"),
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
    Hypothesis(
        id="strip-the-stacked-engine-hand",
        rationale="NARROWED to ONE-SIDED disruption (ADR-0060). A card that strips the opponent's hand "
                  "WITHOUT shuffling mine (no `shuffle_hand`) has no card facts for the swing oracle to "
                  "read — there is no draw count, only a strip — so it keeps a tag-driven rung. Fires on "
                  "the draw ENGINE's swing turn: a `draw`-tagged engine in play (`opp_draw_engine_in_play`, "
                  "Dudunsparce / Budew class) AND their hand stacked to `_STACKED_HAND`+. It cannot gift "
                  "them a fresh hand (no self-refill), so my own hand size is irrelevant — the old "
                  "don't-gift guard was only ever needed for the SYMMETRIC case, which is now priced "
                  "exactly (a symmetric refill's gift is `_REFRESH_GIFT` per card handed back). NOTE: no "
                  "card in the current pool is one-sided — this is a live forward contract, not dead code, "
                  "and it is why the symmetric branch had to leave rather than the rung.",
        when=lambda c: c.option_type == _PLAY
        and "hand_disruption" in c.tags
        and "shuffle_hand" not in c.tags          # ADR-0060: symmetric refills are the oracle's
        and c.board.opp_draw_engine_in_play
        and c.board.opp_hand_size >= _STACKED_HAND,
        weight=22, status="testing"),
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
