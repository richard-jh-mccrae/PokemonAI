"""BASELINE cluster: DISRUPTION — free pre-attack disruption Items (ADR-0025). Strip opponent Energy
before the turn-ending attack when there's something to strip. Pure data, no Mixin. (Grows as more
disruption mechanics — hand disruption, ability lock — land.)
"""
from common.strategy.context import _PLAY
from common.strategy.strategy import Hypothesis

_POSTURE_UNFAVORED = 0.45     # matchup favorability at/below which a straight race loses (lever A)
_POSTURE_FAVORED = 0.55       # ...at/above which deny the opponent outs (the favored half's mirror
                              # constant; 0.45-0.55 = the noise band around the 0.5 prior)
_POSTURE_MIN_COVERAGE = 0.25  # min matchup coverage to trust the favorability prior
_STACKED_HAND = 6             # opponent hand size at/above which a `draw` engine has visibly STACKED
                              # resources (opening hand 7, +1/turn) — worth a hand_disruption Supporter
                              # to strip; below it HOLD (don't gift a fresh hand). ADR-0051 Phase 3b, ladder-tunable
_REFRESH_HAND_FLOOR = 5       # my hand size at/above which a SYMMETRIC redraw (Judge → 4) is a net card
                              # LOSS for me — below it a symmetric refresh is a fine small-hand dig. Pairs
                              # with the (mine > theirs) gift test. ml 85709280 f111 (my 8 vs opp 1), ladder-tunable
_TAILORED_HAND = 3            # opponent hand size at/below which a hand they just tailored DOWN (dumped
                              # normally-kept cards to commit to a few key pieces) is worth Iono-ing to
                              # scatter — the MIRROR threshold of `_STACKED_HAND` (which fires on a BIG
                              # stacked hand). Above it there's no tailored-down commitment to disrupt.
_COMEBACK_HAND_FLOOR = 2      # my hand size at/below which emptying it further into an enabled Unfair-Stamp
                              # is half-dead next turn — a 1-card hand can't rebuild after their post-KO
                              # redraw. At/below this, demote a hand-spend; hold a recovery out.

HYPOTHESES = [
    Hypothesis(
        id="play-energy-denial",
        rationale="Play a free `energy_denial` Item (e.g. Crushing Hammer) before the turn-ending attack "
                  "whenever the opponent's Active carries Energy to strip AND that Active can actually hurt "
                  "us with an affordable attack (`opp_active_can_damage_us`) — it costs nothing, so "
                  "`_finish_turn_last` sequences it tier 0 and you strip AND still attack the same turn; a "
                  "lethal attack still outranks it (KO taken after the free strip). Stands down when the "
                  "opponent's Active has no Energy (ep82753102 f37), when its energized attack CAN'T hurt us "
                  "— a conditional / all-unaffordable attacker (Kyogre off an empty discard), so the strip is "
                  "worthless (dragapult f6) — or when my Active can already KO theirs this turn with its BEST "
                  "affordable attack (`active_can_ko`, not just the cheapest, so a Phantom-Dive-class KO is "
                  "seen too; ep82748422 f26 — just take the KO, save the Item).",
        when=lambda c: c.option_type == _PLAY
        and "energy_denial" in c.tags and c.board.opp_active_has_energy
        and c.board.opp_active_can_damage_us and not c.board.active_can_ko,
        weight=20, status="testing"),
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
                  "an already-useful free disruption (`energy_denial` or `hand_disruption` against its "
                  "trigger) since the straight race loses. Rides on top of the base disruption rule so it "
                  "never boosts a wasteful one, stands down at even/unknown matchup, and never overrides "
                  "a KO; the favored half is `dont-gift-a-refresh-when-favored` (ADR-0026 amendment).",
        when=lambda c: c.option_type == _PLAY
        and c.board.matchup_coverage >= _POSTURE_MIN_COVERAGE
        and c.board.favorability <= _POSTURE_UNFAVORED
        and (("energy_denial" in c.tags and c.board.opp_active_has_energy
              and c.board.opp_active_can_damage_us)
             or ("hand_disruption" in c.tags and c.board.opp_has_hand_size_attacker)),
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
                  "board-dominated, never overrides a KO.",
        when=lambda c: c.option_type == _PLAY
        and "hand_disruption" in c.tags
        and c.board.matchup_coverage >= _POSTURE_MIN_COVERAGE
        and c.board.favorability >= _POSTURE_FAVORED,
        weight=-15, status="testing"),
    Hypothesis(
        id="strip-the-stacked-engine-hand",
        rationale="ADR-0051 Phase 3b (proactive disruption): play a `hand_disruption` Supporter "
                  "(Judge / Iono / Harlequin) to strip the opponent's stacked hand on their draw "
                  "ENGINE's swing turn — when a `draw`-tagged engine is in play "
                  "(`opp_draw_engine_in_play`, Dudunsparce / Budew class) AND their hand has stacked "
                  "to `_STACKED_HAND`+ cards AND it exceeds mine (the don't-gift-a-refresh guard: we "
                  "net-strip resources instead of handing them a fresh hand). Below the threshold the "
                  "rule stays silent — that IS the HOLD. Scoped to draw-engine decks: a hand-size "
                  "attacker is the separate `play-harlequin-vs-hand-size` trigger. Rides "
                  "`hold-wincon-dont-shuffle` (a `shuffle_hand` refresh is suppressed while my own "
                  "win-condition is in hand) and `_finish_turn_last` tier 3 (shuffle sequences AFTER "
                  "the attach), so it never overrides a KO or buries my setup. The don't-gift guard "
                  "(theirs > mine) applies ONLY to a SYMMETRIC `shuffle_hand` refresh (Judge / Iono — "
                  "refills both hands); a ONE-SIDED disruption (strips the opponent only, no "
                  "`shuffle_hand`) can't gift a fresh hand, so it fires regardless of my hand size.",
        when=lambda c: c.option_type == _PLAY
        and "hand_disruption" in c.tags
        and c.board.opp_draw_engine_in_play
        and c.board.opp_hand_size >= _STACKED_HAND
        and (c.board.opp_hand_size > c.board.my_hand_size   # symmetric refresh: only when net-positive
             or "shuffle_hand" not in c.tags),              # one-sided strip: no gift, fire regardless
        weight=22, status="testing"),
    Hypothesis(
        id="dont-shuffle-away-the-bigger-hand",
        rationale="The card-mechanical sibling of `dont-gift-a-refresh-when-favored` (which is keyed on "
                  "matchup POSTURE): a SYMMETRIC hand refresh — both players shuffle their hand into the "
                  "deck and redraw to a fixed count (Judge → 4; `shuffle_hand`+`hand_disruption`) — is "
                  "card-NEGATIVE for me whenever my hand is large AND bigger than the opponent's, "
                  "regardless of who is favored. Playing it then discards my good cards and REFILLS the "
                  "opponent's smaller hand (ml 85709280 f111, CRITICAL: Judge with my hand 8 vs opp 1 = I "
                  "net −4 and gift them +3; the attack-last resequencer masked it because the KO still "
                  "landed after the wasteful Judge). Fires only when net-negative: my hand ≥ "
                  "`_REFRESH_HAND_FLOOR` (a redraw-to-4 is a real loss) AND my hand > the opponent's (I "
                  "gift more than I strip). Structurally EXCLUSIVE with the disruptive uses that require "
                  "opp_hand > my_hand — `strip-the-stacked-engine-hand` (+22) and `play-harlequin-vs-hand-"
                  "size` (+25, keyed on a hand_size_attacker) — so it never suppresses a net-positive "
                  "strip. −25 sinks Judge's +20 dig below End (don't play it), a soft demotion, never "
                  "overrides a KO (`_finish_turn_last`). Deck-agnostic (the human's own framing).",
        when=lambda c: c.option_type == _PLAY
        and "hand_disruption" in c.tags and "shuffle_hand" in c.tags
        and c.board.my_hand_size >= _REFRESH_HAND_FLOOR
        and c.board.my_hand_size > c.board.opp_hand_size,
        weight=-25, status="assumed"),
    Hypothesis(
        id="disrupt-the-tailored-hand",
        rationale="SEED(ladder): 22. The MIRROR of `strip-the-stacked-engine-hand`: that rule strips a "
                  "BIG stacked hand; THIS one Iono-s a hand the opponent has TAILORED DOWN to a few key "
                  "cards. Signal: they dumped normally-kept cards last turn (`opp_last_turn_dumped` — an "
                  "Ultra-Ball-class discard growth ≥2, committing to the few they held) AND their hand is "
                  "now SMALL (`opp_hand_size <= _TAILORED_HAND`, they're down to those key pieces). A "
                  "`hand_disruption` Supporter (Iono / Judge) scatters those specific kept cards back into "
                  "the deck. Structurally DISTINCT from `strip-the-stacked-engine-hand` (which is "
                  "draw-engine-scoped and fires at `_STACKED_HAND`+ cards exceeding mine) — this is the "
                  "small-tailored-hand half and needs no draw engine in play. Rides "
                  "`hold-wincon-dont-shuffle` (suppressed while my own win-condition is in hand) and "
                  "`_finish_turn_last` (the shuffle sequences before the attack, so I disrupt and still "
                  "attack the same turn); never overrides a KO. Ships default-OFF (weight 0, ADR-0009 "
                  "by-id override): an opponent-model prior that must not move live behavior until the "
                  "ladder tunes the seed.",
        when=lambda c: c.option_type == _PLAY
        and "hand_disruption" in c.tags
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
