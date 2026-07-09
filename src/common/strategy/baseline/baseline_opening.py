"""BASELINE cluster: OPENING — opening-hand / mulligan / game-start decisions (ADR-0025). Don't
redraw a hand you can already start; open with the piece your deck's Roles nominate. Pure data,
no Mixin.
"""
from common.strategy.baseline.baseline_bench import _multi_prize
from common.strategy.context import _IS_FIRST, _MULLIGAN, _NO, _SETUP_ACTIVE, _WINCON_ROLES, _YES
from common.strategy.strategy import Hypothesis, Plan

HYPOTHESES = [
    Hypothesis(
        id="keep-a-startable-hand",
        rationale="Don't mulligan away a hand you can already start — if a Pokémon in hand can take "
                  "the Active Spot (a Basic, or via an opening Ability like Explosiveness), keep it "
                  "rather than redraw and give the opponent a free card.",
        when=lambda c: c.select_context == _MULLIGAN and c.option_type == _YES
        and c.board.hand_startable,
        weight=-40, status="assumed"),
    Hypothesis(
        id="honor-preferred-start",
        rationale="At the coin toss, honor the deck's declared tempo "
                  "(`Strategy.params['preferred_start']` = 'first'|'second'): a turbo deck wants SECOND "
                  "(going first can't attack turn 1, wasting burst Energy), a setup-heavy deck wants "
                  "FIRST. This selector only penalises the option that contradicts the declaration; "
                  "undeclared decks are untouched. Folded from mega_starmie `prefer-going-second`.",
        when=lambda c: c.select_context == _IS_FIRST and (
            (c.option_type == _YES and c.params.get("preferred_start") == "second")
            or (c.option_type == _NO and c.params.get("preferred_start") == "first")),
        weight=-30, status="assumed"),
    Hypothesis(
        id="open-the-accelerator",
        rationale="At the Set-Up Active pick, prefer an `accel_source`-Role opener — it turns its "
                  "acceleration on from turn one (e.g. Cinderace: Explosiveness opens the Spot, Turbo "
                  "Flare loads the Bench). Role-keyed opt-in; folded from mega_starmie `open-cinderace`.",
        when=lambda c: c.select_context == _SETUP_ACTIVE   # pregame pick: the line can't be ready yet
        and "accel_source" in c.roles,
        weight=40, status="assumed"),
    Hypothesis(
        id="open-the-item-lock-starter",
        rationale="At the pregame Set-Up Active pick, prefer a candidate carrying the `item_lock` tag "
                  "(Budew — Itchy Pollen: 0-cost attack, blocks the opponent's Item cards next turn): "
                  "leading with a free item-lock disruptor taxes an item-heavy setup engine while our "
                  "own wincon assembles. Tag-keyed opt-in twin of `open-the-accelerator` (which keys the "
                  "`accel_source` Role); +35, just below it. A pregame pick, so KO-safe; no first/second "
                  "gate needed (opening the lock going first just waits to fire T2). Silent for decks "
                  "with no `item_lock` card.",
        when=lambda c: c.select_context == _SETUP_ACTIVE and "item_lock" in c.tags,
        weight=35, status="assumed"),
    Hypothesis(
        id="dont-open-multiprize-active",
        rationale="At the pregame Set-Up Active pick (`_SETUP_ACTIVE`), DON'T open with a non-wincon "
                  "multi-prize ex (Meowth ex) — the Active Spot is the most-exposed slot, so a 2-prize "
                  "(ex) / 3-prize (Mega ex) liability there hands the opponent an easy multi-prize KO, "
                  "and Meowth ex's Last-Ditch Catch only triggers on an IN-GAME bench-from-hand "
                  "(EN_Card_Data row 1071 / rulebook L96), so opening it ALSO forfeits the free Supporter "
                  "fetch. The Active-pick mirror of `dont-bench-multiprize` (same −15, same `_WINCON_ROLES` "
                  "escape so a deck that MEANS to open its Basic-ex attacker still can) and the sibling of "
                  "`dont-pre-bench-the-supporter-tutor` (which owns the pregame BENCH decline). No explicit "
                  "'a plain Basic is also on offer' gate is needed: SETUP_ACTIVE is a forced single pick "
                  "(minCount 1, so decide()'s take-fewer never trims), so when the ex is the ONLY startable "
                  "Basic it stays the max-scoring option and is still placed — the −15 only bites when a "
                  "plain Basic (Riolu/Solrock/Lunatone at score 0) outscores it. mega_lucario opened Meowth "
                  "ex ~4/25 self-play games (residual-blunder audit 2026-07-05).",
        when=lambda c: c.select_context == _SETUP_ACTIVE and _multi_prize(c.stat)
        and not (_WINCON_ROLES & set(c.roles)),
        weight=-15, status="assumed"),
]
