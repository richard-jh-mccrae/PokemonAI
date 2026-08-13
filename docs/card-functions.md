# Card-function data

`src/common/card_functions.json` is the generated portable behavior table loaded by
`common.cards.CardFunctions`.

Bellman uses it as factual input for card Worth, causal needs, opponent body classification, and
board potential. Exact action consequences still come from native/cgpy engine transitions; tags do
not select actions or replace engine rules.

Reserved JSON keys begin with `_`; numeric keys are card IDs. Values are stable behavior labels such
as `draw`, `search`, `energy_accel`, `gust`, `heal`, `switch`, and `retreat_reduction`. Exact board
changes, including a Tool's retreat-cost reduction, remain engine transition facts.

`partner:<card-id>` is a printed in-play dependency (for example, Lunatone ↔ Solrock), compiled by
the shared value registry. It is card data, never a deck-local `Strategy.partners` declaration.
`role:<name>` and `evolves:<card-id>` likewise declare a card's shared role and one-hop evolution;
the registry normalizes those edges into complete Bellman lines, and Scouting exposes tagged next
forms even before it recognizes an archetype.

Regenerate with `python tools/build_card_functions.py`. Structural facts such as HP, stage, card
type, weakness, and prize value come from the card-stat provider, not this table.
