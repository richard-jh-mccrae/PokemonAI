"""BASELINE cluster: POSTURE — risk scales with prize position; the *AHEAD* half only, the behind
half being the gamble tier's (ADR-0039). Pure data, no Pilot Mixin (ADR-0025).

⚠️ Every rule here ships default-OFF at `weight=0` — wired and telemetry-visible, contributing
nothing to the argmax — until the ladder tunes the `SEED(ladder)` value named in its rationale.
"""
from common.strategy.context import _PLAY
from common.strategy.strategy import Hypothesis

_AHEAD_MARGIN = 1   # prizes ahead (opp_remaining − my_remaining) before the prior fires; ladder-tunable,
                    # and it guards the 0/0 UNPOPULATED default and the 6/6 opening (both diff 0).

HYPOTHESES = [
    Hypothesis(
        id="play-safe-when-ahead-on-prizes",
        rationale="Risk scales with prize POSITION (learnthetcg fundamentals): when I'm clearly AHEAD "
                  "on prizes I want to MINIMISE whiff, not court variance. The one broadly-recognizable "
                  "high-variance / all-or-nothing PLAY in the card vocabulary is a `shuffle_hand` refresh "
                  "(Judge / Iono / Harlequin / Lillie's) — it trades a KNOWN, working hand for a random "
                  "redraw. Ahead, that certainty is worth more than the dig, so demote the refresh so a "
                  "stabilising line is preferred. Keyed on the PRIZE-lead axis "
                  "(`opp_prizes_remaining − my_prizes_remaining >= _AHEAD_MARGIN`), which is orthogonal to "
                  "the swing oracle's card-count axis (ADR-0060 `_refresh_swing_tactical`, keyed on "
                  "the card's printed draw counts) and matchup-favorability (`dont-gift-a-refresh-when-favored`, keyed on "
                  "favorability) rules — this is the net-new prize-position half the proposal asks for. "
                  "SEED(ladder): -8 (a small demotion prior, never an override). Ships default-OFF at "
                  "weight 0: an opponent-position prior stays telemetry-only until the ladder validates the "
                  "sign and size. LIMITATION (honest): `shuffle_hand` is only a proxy for 'high variance' — "
                  "when my hand is genuinely dead a refresh is still correct even ahead, so this must stay a "
                  "small prior that the positive shuffle-refresh dead-hand doctrine (and any KO) outranks; "
                  "it deliberately does NOT touch _PLAY of develops (the stabilise-UP nudge is left "
                  "unauthored rather than fire a broad speculative trigger).",
        when=lambda c: c.option_type == _PLAY
        and "shuffle_hand" in c.tags
        and (c.board.opp_prizes_remaining - c.board.my_prizes_remaining) >= _AHEAD_MARGIN,
        weight=0, status="assumed"),
]
