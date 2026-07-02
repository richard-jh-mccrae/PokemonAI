"""BASELINE cluster: DISRUPTION — free pre-attack disruption Items (ADR-0025). Strip opponent Energy
before the turn-ending attack when there's something to strip. Pure data, no Mixin. (Grows as more
disruption mechanics — hand disruption, ability lock — land.)
"""
from common.strategy.context import _PLAY
from common.strategy.strategy import Hypothesis, Plan

_POSTURE_UNFAVORED = 0.45     # matchup favorability at/below which a straight race loses (lever A)
_POSTURE_MIN_COVERAGE = 0.25  # min matchup coverage to trust the favorability prior

HYPOTHESES = [
    Hypothesis(
        id="play-energy-denial",
        rationale="Play a free `energy_denial` Item (e.g. Crushing Hammer) before the turn-ending attack "
                  "whenever the opponent's Active carries Energy to strip — it costs nothing, so "
                  "`_finish_turn_last` sequences it tier 0 and you strip AND still attack the same turn; "
                  "a lethal attack still outranks it (KO taken after the free strip). Stands down when "
                  "the opponent's Active has no Energy (ep82753102 f37 — don't burn it on a body that "
                  "isn't attacking) or when my Active can already KO theirs this turn "
                  "(`active_cheap_attack_kos`; ep82748422 f26 — just take the KO, save the Item).",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _PLAY
        and "energy_denial" in c.tags and c.board.opp_active_has_energy
        and not c.board.active_cheap_attack_kos,
        weight=20, status="testing"),
    Hypothesis(
        id="play-harlequin-vs-hand-size",
        rationale="Play a `hand_disruption` Supporter (e.g. Harlequin, which shuffles both hands into "
                  "the deck and redraws) when the opponent has a `hand_size_attacker` in play or a "
                  "committed evolution line into one (e.g. Alakazam's Powerful Hand scales with hand "
                  "size) — shrinking their hand cuts that attacker's damage. `hold-wincon-dont-shuffle` "
                  "still suppresses it when your own win-condition is in hand, and `_finish_turn_last` "
                  "sequences the shuffle before the attack so you disrupt and still attack the same turn.",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _PLAY
        and "hand_disruption" in c.tags and c.board.opp_has_hand_size_attacker,
        weight=25, status="testing"),
    Hypothesis(
        id="disrupt-when-unfavored",
        rationale="Lever A (ADR-0026): when the Read says the matchup is unfavorable (compiled win-rate "
                  "at/below `_POSTURE_UNFAVORED`, backed by `_POSTURE_MIN_COVERAGE` evidence), up-weight "
                  "an already-useful free disruption (`energy_denial` or `hand_disruption` against its "
                  "trigger) since the straight race loses. Rides on top of the base disruption rule so it "
                  "never boosts a wasteful one, stands down at even/unknown matchup, and never overrides "
                  "a KO; the favored->race half is deferred (no aggressive-option tag yet).",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _PLAY
        and c.board.matchup_coverage >= _POSTURE_MIN_COVERAGE
        and c.board.favorability <= _POSTURE_UNFAVORED
        and (("energy_denial" in c.tags and c.board.opp_active_has_energy)
             or ("hand_disruption" in c.tags and c.board.opp_has_hand_size_attacker)),
        weight=18, status="testing"),
]
