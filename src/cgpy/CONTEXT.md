# cgpy — the pure-Python twin of the native engine (ADR-0050)

A standalone reimplementation of the `src/cg` native engine (`cg.dll`/`libcg.so`), at exact
parity, verified by trace replay. `src/cg/` is never modified; cgpy never imports it (importing
`cg` loads the DLL).

## Language

- **Trace** — a recorded native game as an executable specification: per select, the mover's
  verbatim live observation, the `choice` answered, and the aligned **God Frame**
  (`visualize_data`-style full-information state: ordered decks, hands, prizes). Format
  `parity-trace/1` (`verify/trace.py`), minted by `tools/parity/capture_match.py` (needs the
  DLL). Committed curated traces live in `tests/fixtures/parity/`; the bulk regenerable corpus
  in `data/parity/` (gitignored).
- **Replay** — driving cgpy through a Trace: same decks, same choices, randomness bound from
  the record (draw identities from the mover's own DRAW logs, coins from COIN logs, prize
  identities from god frames, deck order re-synced per frame). Every frame must compare equal
  with **no normalization** (`verify/replayer.py`, `verify/differ.py`). A trace is **green**
  when it replays to the same result divergence-free.
- **The parity gate** — `tests/parity/test_replay_fixtures.py`: every committed trace green.
  DLL-free by construction (the trace IS the native side), so it runs everywhere — this is the
  mechanical answer to ADR-0010's drift objection. CI runs it as a named step.
- **Pin** — an empirical fact about native behavior established by probe or trace divergence
  (serial scheme, option ordering, mulligan protocol, LIFO returns, …). Recorded in
  `docs/pyeng/determinism.md`; load-bearing ones are enforced by
  `tests/parity/test_determinism_pins_engine.py` (skips without the DLL).
- **ChainDef** — a card's behavior as DATA: a list of ops over the recovered effect-DSL
  vocabulary, interpreted by `chain.py` on a resumable **EffectFrame** stack. Hand-authored
  layer: `defs/chain_overrides.json`; machine-seeded layer (pool-wide fan-out, M4):
  `defs/generated_chains.json`. A def-less card exercised at runtime raises
  **UnsupportedCard** — fail-loud, never guess.
- **DSL vocabulary** — `defs/dsl_vocabulary.json`: the native `Chain`/`State` symbol surface
  (names + arities) mined from the un-stripped `libcg.so` by `tools/parity/extract_dsl.py`;
  `--check` is the drift alarm for engine updates.
- **Card tables** — `defs/{card_data,attack_data}.json`: the engine's own AllCard/AllAttack
  dump (`tools/parity/snapshot_tables.py`), so cgpy needs no DLL; `tables_meta.json` carries
  the source-binary hashes + probe-pinned deck-validation error codes.

## Module map

`schema.py` (wire enums, twin of `cg/api.py`) · `cards.py` (CardDB + native deck validation) ·
`state.py` (GameState/zones/serials/EffectFrame; per-seat log outboxes; `clone()`) ·
`render.py` (per-seat masking == `GetBattleData`; god frames) · `options.py` (ALL option
building + ordering) · `turn.py` (setup/mulligan machine, turn loop, KO/prize/promotion) ·
`damage.py` (base→mods→×W→−R→mods) · `chain.py` (the DSL interpreter) · `engine.py` (facade:
start/step/observation/clone/`fork()`) · `verify/` (trace/differ/replayer) ·
`search.py` (M3: `state_from_obs`/`state_from_visualize` structured seeding, the state
token, clone-per-step sessions) · `game.py` (M3: the `cg/game.py`-shaped battle singleton,
`visualize_data`) · `compat/` + `alias.py` (M3: the `cg` package surface + `sys.modules`
mapping, env `CG_ENGINE=py`).

## Invariants

- Deck lists are bottom-first: **the top of the deck is the list end**.
- Serials: seat 0 submitted position i → `3+i`; seat 1 → `63+i`.
- Hand order is identity-tracked (draws append; removals compact) — never synced, always
  asserted against god frames.
- Zone returns are **LIFO** (mulligan hand→deck, KO energy discards).
- Options are built ONLY in `options.py`; ordering is part of the parity contract.
- Chain programs and frames are plain data — no closures in state, so `clone()` is a deepcopy.

## Status (2026-07-11)

M0 (vocabulary, snapshots, determinism pins), M1 (harness; setup + vanilla game loop —
12/12 vanilla traces green), M2 (chain interpreter, 50-card union burn-down — 29 committed
traces green, CI gate) and M3 (verification API + drop-in selection) are complete. M3
shipped: `search.py` (structured seeding at MAIN, trainer mid-effect and token-exact
selects; native-verbatim validation; deterministic prediction reshuffle per pin §4;
clone-per-step sessions), `game.py`/`compat/`/`alias.py` (`CG_ENGINE=py` runs the whole
battle harness + agents unchanged — 42-game gate, zero crashes), the clone-safety gate
(fork at every select of every trace), the native-vs-cgpy verdict-agreement gate on the
seeded lethal fixtures, and the DLL-free lethal harness (`engine_confirms_py`,
`lethal_probe.py --engine py`, the f15/f24 win-line drives). Next: M4 (pool-wide fan-out +
coverage ledger `data/engine/coverage.json`).
