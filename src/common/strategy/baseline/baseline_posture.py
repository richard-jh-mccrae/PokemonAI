"""BASELINE cluster: POSTURE — risk scales with prize position (learnthetcg fundamentals digest,
proposal `risk-scales-with-prize-position`). The *ahead* half only: when I'm clearly AHEAD on prizes
I should minimise whiff — stabilise and don't gamble a working position for variance I don't need.
The *behind* half (safe-line-loses -> take the low-% line) is already modelled by the gamble tier
(ADR-0039, closed-form expectimax), so it is NOT re-authored here.

Pure-data General-Strategy Hypotheses, no Pilot Mixin (ADR-0025). Fires on the PLAY select. This
cluster is an opponent-position-driven PRIOR that must not move live behavior until the ladder tunes
it: every rule ships default-OFF (`weight=0`, `status="assumed"`, intended seed noted as
`SEED(ladder): NN` in the rationale). Weight 0 = wired + telemetry-visible, contributes nothing to
the argmax.
"""
from common.strategy.context import _PLAY
from common.strategy.strategy import Hypothesis

_AHEAD_MARGIN = 1   # prizes I must be AHEAD by (opp_remaining − my_remaining) before the play-safe
                    # prior engages. `my_prizes_remaining < opp_prizes_remaining` says I'm ahead;
                    # the margin guards the 0/0 UNPOPULATED default (both 0 -> diff 0 -> silent) and
                    # the 6/6 opening (diff 0 -> silent), and lets the ladder raise the bar to "clearly
                    # ahead" (>=2) without a code change. ladder-tunable.

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
