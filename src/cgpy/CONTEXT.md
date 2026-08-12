# cgpy — the pure-Python twin of the native engine (ADR-0059)

**Runtime boundary:** offline diagnostics, tests, and simulation only. This package is never a
Kaggle dependency and must never be copied into a submission. Production agents use native `cg`;
the package and exact-artifact gates reject any ZIP path or file content mentioning `cgpy`.

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

M0 (vocabulary, snapshots, determinism pins), M1 (harness; setup + vanilla game loop),
M2 (chain interpreter, 50-card union), M3 (verification API + `CG_ENGINE=py` drop-in) and
the **M4 core** (pool-wide fan-out) are complete. M4 shipped: `tools/parity/seed_chains.py`
→ `defs/generated_chains.json` (sentence-consumption rules; 1074/1556 attacks + 856/1267
cards live, the rest explicitly deferred; loader validates full pool coverage),
`capture_card.py` per-card micro-traces (audit drive-shell + recorder), the committed
coverage ledger `data/engine/coverage.json` + `report.py` (statuses verified/derived/
seeded/unprobed/deferred; 54 committed traces, 4513 clean frames), the op-conformance
gate (52/54 ops trace-pinned), the cross-engine audit seam (`CG_ENGINE=py
audit_attacks.py` + `diff_audit_engines.py` — sample 46/46 equal incl. Crustle's defense
passive), `from_cabt.py` god-free replays (take-time prize binding, listing-order
adoption), `onboard_card.py` (the future-card one-command), and a DLL-free self-play
smoke. New behavior pins: docs/pyeng/determinism.md §9–10. The 2026-07-12 ability-tail
batch added the god-free reveal-oracle channels (draw-side prize swap, pre-step listing
adoption, `look_feed` DECK→LOOKING binding) and the **kaggle-episode ladder**: all 414
real episodes under the main checkout's `data/replays/` convert + replay
(`tests/parity/test_cabt_replays.py` pins two end-to-end; 123/414 fully green). Ongoing:
burn down the deferred tail through that ladder — the attribution tally (first
divergence → card id) is the ranked queue, digested in
data/handoffs/CGGame/05-m4-pool-fanout.md.
