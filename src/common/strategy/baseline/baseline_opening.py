"""BASELINE cluster: OPENING — opening-hand / mulligan / game-start decisions (ADR-0025). Don't
redraw a hand you can already start; open with the body your deck declared. Pure data, no Mixin.

**The Set-Up ACTIVE pick is ONE rule reading ONE deck declaration (ADR-0079).** It used to be five
rungs across two layers — `open-the-accelerator` (+40, `accel_source` Role), `open-the-item-lock-
starter` (+35, `item_lock` Tag), `dont-open-multiprize-active` (−15), `dont-open-with-the-engine`
(−12), and mega_lucario's card-id-gated `start-solrock-over-lunatone` (+12). All five are DELETED.

Why the whole pile went, rather than one more rung joining it:

* **The positives were deck opinions expressed by proxy.** "Open the accelerator" / "open the
  item-locker" are a deck saying which body it wants Active, spelled as a Role and a Tag. A
  declaration says it directly AND in order, so the proxies buy nothing the list doesn't.
* **The negatives second-guessed an explicit ranking.** A guard that demotes a body the deck
  deliberately ranked first is not a rail, it is an override of deck intent — and the escape hatches
  it needed for that (`_WINCON_ROLES`) are exactly the complexity a ranking removes.
* **They ordered each other by accident.** A deck holding both an `accel_source` and an `item_lock`
  body had its opener settled by `+40 > +35` — a comparison between two independently-tuned numbers
  no deck ever grilled.
* **The card-id reflex was already shipped.** `start-solrock-over-lunatone` gated on
  `card_id == SOLROCK`. The ids now live in the deck's declaration, never in a trigger (ADR-0034).

The frames: dragapult `f2` (Dreepy/Munkidori both 0.0 → the option-index tie-break opened the
fragile Line base) and mega_lucario `f1` (Riolu/Lunatone both 0.0 → it opened the draw engine). Two
decks, two frames, one root cause — the seam did not rank the field.
"""
from common.strategy.context import _IS_FIRST, _MULLIGAN, _NO, _SETUP_ACTIVE, _YES
from common.strategy.strategy import Hypothesis

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
        id="open-the-declared-starter",
        rationale="At the pregame Set-Up Active pick, open with the highest-ranked body the deck "
                  "DECLARED it wants there (`Strategy.starter_priority`, highest first) among those "
                  "actually on offer. The one rule at this seam, and the successor to all five it "
                  "replaced (ADR-0079). Card-name-free: the ids live in the deck's declaration, and "
                  "this trigger reads only the resolved `board.top_starter_id` — the same shape as "
                  "`fetch-deck-priority` over `Strategy.fetch_priority`. Deck-keyed opt-in, so it is "
                  "silent for a deck that has not declared (a pre-doctrine agent); every AUTHORED "
                  "agent must declare a COMPLETE ranking of its startable bodies, which "
                  "`test_setup_active_placement` enforces — completeness is what lets one boolean "
                  "carry the whole order, since a forced single pick (minCount/maxCount 1) reads only "
                  "the winner. Seed 40 for band legibility (`docs/weights.md` 'core doctrine', the "
                  "band its ancestor `open-cinderace` occupied); with nothing else scoring at this "
                  "seam the magnitude is behaviourally free, and per-deck strength belongs in "
                  "`weight_overrides` (ADR-0035). Fixes dragapult f2 (Munkidori over the fragile "
                  "Dreepy) and mega_lucario f1 (Solrock over the Lunatone draw engine) at source: "
                  "both were option-index tie-breaks between options that all scored 0.0.",
        when=lambda c: c.select_context == _SETUP_ACTIVE and c.card_is_top_starter,
        weight=40, status="assumed"),
]
