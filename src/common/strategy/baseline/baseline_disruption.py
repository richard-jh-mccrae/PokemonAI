"""BASELINE cluster: DISRUPTION — free pre-attack disruption Items (ADR-0025). Strip opponent Energy
before the turn-ending attack when there's something to strip. Pure data, no Mixin. (Grows as more
disruption mechanics — hand disruption, ability lock — land.)
"""
from common.strategy.context import _PLAY
from common.strategy.strategy import Hypothesis, Plan

HYPOTHESES = [
    Hypothesis(
        id="play-energy-denial",
        rationale="Play an energy-denial Item (Function Tag `energy_denial`, e.g. Crushing Hammer — "
                  "'flip a coin; if heads, discard an Energy from 1 of the opponent's Pokémon') BEFORE "
                  "your turn-ending attack, whenever the opponent's ACTIVE carries Energy to strip. "
                  "Chipping the imminent attacker back an Energy (a powered Active toward un-attacking, "
                  "e.g. a Riolu mid-evolution to Mega Lucario ex) is free disruption: the Item costs "
                  "nothing, so `_finish_turn_last` sequences it tier 0 and you strip AND still attack the "
                  "same turn (attack-last). A positional weight — a lethal attack still outranks it on "
                  "tactical, so the KO is taken (after the free strip; the attack is just held one slot). "
                  "Stands down when the opponent's Active has no Energy (stripping a benched SUPPORT's "
                  "lone Energy is a wasted coin-flip — ep82753102 f37, the Item is better held than burnt "
                  "on a body that isn't attacking), AND when my Active can ALREADY Knock Out their Active "
                  "this turn (`active_cheap_attack_kos`): the strip is moot when the body is about to be "
                  "KO'd anyway — just take the KO and save the Item (ep82748422 f26, Jetting Blow KOs the "
                  "Active).",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _PLAY
        and "energy_denial" in c.tags and c.board.opp_active_has_energy
        and not c.board.active_cheap_attack_kos,
        weight=20, status="testing"),
    Hypothesis(
        id="play-harlequin-vs-hand-size",
        rationale="Play a hand-disruption Supporter (Function Tag `hand_disruption`, e.g. Harlequin — "
                  "both players shuffle their hand into the deck and redraw) when the opponent's deck "
                  "SCALES its damage with hand size: a `hand_size_attacker` is in play or in a committed "
                  "evolution line (e.g. Alakazam's Powerful Hand — '2 damage counters per card in your "
                  "hand'; detected via the tag + forward-evolution line, so a Kadabra building toward "
                  "Alakazam already counts). Shrinking their hand cuts that attacker's damage — a "
                  "card-fact Posture read, not a meta guess. The deck's own `hold-wincon-dont-shuffle` "
                  "still suppresses it when YOUR win-condition is in hand (don't shuffle away your "
                  "payoff), and `_finish_turn_last` sequences the shuffle after your attach and before "
                  "the attack — so you disrupt AND still attack (or take a KO) the same turn.",
        when=lambda c: c.plan in (Plan.SETUP, Plan.RACE) and c.option_type == _PLAY
        and "hand_disruption" in c.tags and c.board.opp_has_hand_size_attacker,
        weight=25, status="testing"),
]
