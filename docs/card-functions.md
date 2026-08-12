# Card-function data

`src/common/card_functions.json` is the generated portable behavior table loaded by
`common.cards.CardFunctions`.

Bellman uses it as factual input for card Worth, causal needs, opponent body classification, and
board potential. Exact action consequences still come from native/cgpy engine transitions; tags do
not select actions or replace engine rules.

Reserved JSON keys begin with `_`; numeric keys are card IDs. Values are stable behavior labels such
as `draw`, `search`, `energy_accel`, `gust`, `heal`, and parametric provision/dig labels.

Regenerate with `python tools/build_card_functions.py`. Structural facts such as HP, stage, card
type, weakness, and prize value come from the card-stat provider, not this table.
