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
]
