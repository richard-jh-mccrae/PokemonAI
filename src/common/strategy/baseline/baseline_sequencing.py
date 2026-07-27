"""BASELINE cluster: SEQUENCING — within-turn play ordering (ADR-0025). Dig (draw/search) before
irreversible commitments. Pure data, no Mixin. (The free-dig family; `_finish_turn_last` in the Pilot
handles attack-last sequencing structurally.)
"""
from common.strategy.context import _ABILITY, _PLAY
from common.strategy.strategy import Hypothesis

HYPOTHESES = [
    Hypothesis(
        id="use-the-draw-engine-ability",
        rationale="Activate a pure card-advantage Ability at the MAIN menu — a `draw`/`dig` Ability "
                  "(Drakloak Recon Directive, Dudunsparce Run Away Draw, Bibarel) has NO combat value "
                  "(`_tactical`=0 for a non-attack option) and `dig-before-commit` only fires on `_PLAY`, "
                  "so nothing endorsed it: it scored 0, `_finish_turn_last` dropped it to tier 4 beside "
                  "the turn-ending attack, and any positive-tactical attack ended the turn first — the "
                  "free draw/dig was systematically skipped whenever an attack was on the menu (probe: "
                  "Recon + Run Away Draw both scored 0, fired={}). The `_ABILITY` sibling of "
                  "`dig-before-commit`: give a draw/dig Ability a positive weight so it sequences to tier "
                  "0 (before the attack). Scoped to `draw`/`dig` and non-`cost_discard` — a blanket "
                  "'activate any ability' risks firing a counter-move/heal with no good target (deferred "
                  "refinement). Silent for decks with no draw/dig Ability.",
        when=lambda c: c.option_type == _ABILITY
        and ("draw" in c.tags or "dig" in c.tags) and "cost_discard" not in c.tags,
        weight=18, status="assumed"),
    Hypothesis(
        id="dig-before-commit",
        rationale="Play free draw/search before irreversible commitments (Energy attach in setup, the "
                  "turn-ending attack while racing — `_finish_turn_last` still attacks same turn) since "
                  "they cost nothing and see more deck. Stands down for discard-cost search "
                  "(`cost_discard`, not free). STANDS DOWN on a Shuffle-Refresh (`shuffle_hand`) since "
                  "ADR-0060: this rung is hand-size-BLIND, and a flat endorsement of Judge/Harlequin/"
                  "Lillie's is exactly what made the Pilot shed an 8-card hand to redraw 4 (ml f111 "
                  "CRITICAL, ms f60, ms f94). A refresh's value is its card SWING — the `refresh_swing` "
                  "oracle owns that card class end to end and carries the `_REFRESH_CYCLE` credit this "
                  "rung used to supply. ADR-0024's anti-hoarding finding survives INSIDE the oracle. "
                  "STANDS DOWN on a POKEMON play (2026-07-17 tag-completeness audit): benching a body "
                  "whose Ability draws LATER (Lunatone Lunar Cycle, Fezandipiti Flip the Script) is not "
                  "a dig — nothing resolves on the play, and the +20 out-ranked the wincon base "
                  "(ml0703 f44). A play-triggered tutor body (Meowth ex) is owned by its dedicated "
                  "`bench-the-supporter-tutor` rung, not double-credited here.",
        when=lambda c: c.option_type == _PLAY
        and ("draw" in c.tags or "search" in c.tags)
        and "cost_discard" not in c.tags
        and "shuffle_hand" not in c.tags
        and not (c.stat is not None and getattr(c.stat, "is_pokemon", False)),
        weight=20, status="assumed"),
    Hypothesis(
        id="dont-play-damage-boost-when-cant-attack",
        rationale="A flat this-turn attack-damage boost (Premium Power Pro / Black Belt's Training / Maximum "
                  "Belt — `CardStat.damageBoost > 0`) is worth NOTHING unless you attack this turn, and its "
                  "effect expires at end of turn — so don't play it when the Active can't pay any attack this "
                  "turn (`not active_attack_provable`): the guaranteed-dead case (turn-1-going-first can't "
                  "attack, or an unpowered Active with no Energy to reach a cost). The boost would be "
                  "discarded having buffed nothing (ep83966336 f14: two Premium Power Pro over End with a "
                  "0-Energy Riolu and no Energy in hand). −12 nets it below End; silent whenever an attack IS "
                  "affordable, so a real pre-attack boost keeps its tactical value (`_boost_lethal_tactical`). "
                  "Reads the **Provable Budget** leg (#142, ADR-0067 amendment), NOT the famine leg: the boost "
                  "is spent irrevocably now and expires unused if the reach never materialises, so a false "
                  "live-ness is the costly error here — the opposite fail direction from a stand-down gate.",
        when=lambda c: c.option_type == _PLAY and c.stat is not None
        and getattr(c.stat, "damageBoost", 0) > 0 and not c.board.active_attack_provable,
        weight=-12, status="assumed"),
    Hypothesis(
        id="dont-spend-unneeded-supporter",
        rationale="Playing a draw Supporter is NOT mandatory just because it's in hand (learnthetcg "
                  "`dont-spend-unneeded-supporter`). When the turn's directed goal is ALREADY met and "
                  "there is no dig/thinning value left in drawing, HOLD the Supporter — most often save "
                  "the Boss's Orders (`gust`) or an evolution-tutor (`rush_evolve`) Supporter for a later "
                  "decisive turn, so the payoff is a preserved scarce future resource, not tempo now. "
                  "Gated on the new `Board.turn_goal_satisfied` predicate (the directed goal met AND "
                  "nothing still being searched — fails SAFE to False, so this stays silent unless the "
                  "goal is provably done). Scoped to a SUPPORTER whose value is draw/gust/positioning "
                  "(`draw`/`gust`/`rush_evolve`) and NOT a genuine `dig` (looking deeper for a needed "
                  "piece keeps real value). SEED(ladder): -15 — a demotion below End, never a veto (the "
                  "tuned layer matures it). Weight 0 = WIRED + INERT until the ladder validates.",
        when=lambda c: c.option_type == _PLAY and c.stat is not None
        and getattr(c.stat, "is_supporter", False)
        and ("draw" in c.tags or "gust" in c.tags or "rush_evolve" in c.tags)
        and "dig" not in c.tags
        and getattr(c.board, "turn_goal_satisfied", False),
        weight=0, status="assumed"),
]
