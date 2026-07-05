# common/

Deck-agnostic **Agent Runtime** — the shared code behind every deck build. Bundled into each
submission as the `common` package and imported as `common.*` in dev and on the grader
(ADR-0004). A deck customises it only through its `agents/<deck>/strategy.py` + `deck.csv`.

- Architecture spine: [../../docs/agent-architecture.md](../../docs/agent-architecture.md)
- Glossary / domain language: [CONTEXT.md](CONTEXT.md)

## Modules

| Module | What it is | Public surface |
|---|---|---|
| `pilot.py` | The **Pilot**: deck-agnostic `Sense → Plan → Score → Act` engine. Reads the raw obs dict (no native lib), always returns a legal selection. | `Pilot(strategy, deck, …).decide(obs) -> list[int]`, `choose_plan`, `Context` |
| `strategy.py` | The declarative **Strategy** a deck supplies — pure data, no engine/control flow; owns the closed `Plan` vocab. | `Strategy`, `Line`, `Ready`, `Hypothesis`, `Plan` |
| `cards.py` | **CardFunctions**: O(1) Function-Tag lookup; partial & additive (unknown card → no tags, missing file → empty). | `CardFunctions.load().tags(card_id) -> list[str]` |
| `scouting/` | The **Scout** → **Read** (opponent recognition). Its own multi-module package. | `from common.scouting import Scout` |
| `value/` | Automatic Value Model loader (`state → P(win)`). | *planned* |
| `card_functions.json` | Shipped Function-Tag table `{cardId: [tags]}`, built offline by `tools/build_card_functions.py`. | data artifact |

Tests are fast and lib-free (build obs dicts by hand): `python -m pytest tests/ -q`.
