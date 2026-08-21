# Shared agent runtime

Every shipped deck uses one system: `common.runtime.AgentRuntime`. Live decisions come from the
Ledger (`common/ledger/`, a 1-ply worth-differencing decider over `common/board/` BoardState,
ADR-0145); the shell around it does declarative pregame, forced selections, attack-lock folding,
and a last-resort crash fallback. The pre-Ledger Bellman planner is quarantined under
`deprecated/bellman/` (ADR-0149) and extends this shell as the offline teacher.

## Language

**Ledger**:
The live decider: board value = card worth × zone multiplier, both sides, prizes; an option's
price is the swing it causes and only ending the turn is worth zero.
_Avoid_: Evaluator stack, value families

**Swing**:
One option's price under the Ledger: value after minus value now, expected value at chance points.
_Avoid_: Score, reward

**Strategy**:
An authored, conditional hint about decision sequences likely to reach valuable end states.
It schedules search traversal and never changes action or board value.
_Avoid_: Need, rule, reward

**General Strategy**:
A deck-independent Strategy shared by every pilot, such as taking inexpensive information first.
_Avoid_: Generic value

**Deck Strategy**:
Own-deck doctrine that may add to or explicitly override General Strategies.
_Avoid_: Card Role, hard-coded line

**Opponent Strategy**:
Scouting doctrine activated by the matched opponent Brief.
_Avoid_: Opponent Role, matchup value

**Pokémon Role**:
Deck or scouting doctrine describing a Pokémon's strategic job, such as primary attacker, backup attacker, or support.
Roles contribute to development, preservation, and KO value.
_Avoid_: Win condition, secondary attacker, Trainer function, Strategy

**General Pokémon Role**:
A deck-independent Pokémon Role used whenever the same body has the same strategic job for either player.
_Avoid_: Repeated deck Role, Card Function

**Pre-evolution Role**:
Scouting doctrine marking an undeveloped Pokémon whose known evolution line makes it a valuable denial target.
_Avoid_: Win condition base, automatic deck Role

**Evolution Relationship**:
The intrinsic ancestry between Pokémon cards. It comes from card facts and is not deck doctrine.
_Avoid_: Authored evolution map, Pokémon Role

**Card Function**:
An intrinsic Trainer or Energy capability shared across decks, such as search, draw, gust, or acceleration.
_Avoid_: Pokémon Role, deck doctrine

The runtime performs declarative setup choices, resolves Roles and evolution from the unified
card records (deck declarations REPLACE authored defaults), builds the deck's LedgerContext
from them and `ledger_overrides`, and sends every normal-turn decision to `common.ledger`.

Deck-local policy is data in `src/agents/<deck>/strategy.py`:

- Pokémon Roles; evolution relationships are derived from card facts;
- Deck Strategies and explicit General Strategy overrides — authored in the declaration
  language `strategy/strategies.py` keeps; the activation engine lives with the teacher;
- starter priority and preferred first/second turn;
- partner dependencies;
- prize routes;
- upward-only Worth overrides and `ledger_overrides`.

The live decision path:

- `ledger/`: the decider, worth/zone evaluation, option previews, and sampled-hand chance
  (ADR-0145), plus the preview seam over the providers (ADR-0146);
- `board/`: BoardState, the typed observable board (ADR-0144);
- `cards/`: the unified card store (ADR-0143) and per-function mechanics
  (`fetch.py`, `draw.py`, `damage.py`, `energy.py`, `attack_lock.py`);
- `native_engine.py`: the production `cg` transition provider — forks the engine, enumerates and
  applies actions, never ranks; unknown zones use low-discrepancy identity spacing so the
  deployment world cannot inherit numeric-id ordering as fake draw knowledge;
- `engine.py`: offline cgpy twin of the provider, excluded from submissions;
- `refresh.py`: the printed-counts shuffle-refresh transition both providers emit and the Ledger
  prices analytically;
- `information.py`: exact hypergeometric draw/reveal outcome classes for the offline provider;
- `card_effects.json`: the audited effect-clause source the store records are generated from
  (`tools/build_pokemon_cards.py`); its runtime loader lives with the teacher;
- `algebra.py`, `api.py`, `options.py`: the transition algebra, decision contracts, and
  legal-action enumeration (the providers' canonical DecisionState moved to the quarantine —
  the live path builds none, pinned in `tests/ledger`).

Neutral retained services are Scouting, card/stat providers, card-function data, own-deck tracking,
option equivalence, telemetry, and board-card traversal.
