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
  this context; load-bearing ones are enforced by
  `tests/parity/test_determinism_pins_engine.py` (skips without the DLL).
- **Experiment Snapshot** — an immutable, versioned identity of one complete cgpy state and its
  randomness at a legal decision boundary. It can recreate the same experimental starting point.
- **Experiment Root** — one independently mutable fork of an Experiment Snapshot assigned to an
  experimental method.
- **Randomness Epoch** — a bounded interval governed by one declared random state. A replay-derived
  Experiment Root starts a new epoch instead of claiming continuation of native randomness.
- **Chance Sample Key** — the versioned identity of one sampled chance outcome within an Experiment
  Root. The same branch and sample retain the same identity regardless of traversal order.
- **Chance Branch Key** — the versioned identity of one exact or sampled branch from a Chance Node.
  It identifies reproducible resolution without exposing the hidden outcome payload.
- **Chance Expansion** — one bounded exact or sampled probability distribution from a Chance Node
  to successor Search Nodes. It never evaluates or selects those successors.
- **Primitive Action** — one complete answer to the current engine menu. A multi-select answer is
  one Primitive Action even when it names several cards.
- **Turn Search Environment** — the cgpy experiment interface that exposes one Primitive Action per
  transition while keeping exact engine state private from policy and value consumers.
- **Search Node** — an immutable, typed search position whose exact engine state remains owned by
  its Turn Search Environment.
- **Search State Key** — the versioned canonical identity of a Search Node's rule-relevant state and
  metadata. Random generator state and diagnostic history are not part of this identity.
- **Perspective Seat** — the fixed seat whose legal observation and outcome value define one search.
  It is independent of the absolute seat currently acting.
- **Information Boundary** — a typed stop where advancing would require information unavailable to
  the Perspective Seat, including an opponent decision or unresolved hidden randomness.
- **Primitive Transition** — the versioned record of one Primitive Action and its resulting Search
  Node, suitable for replay by resolving its Action Identity against the current legal roster.
- **Chance Transition** — the versioned record of one Chance Branch Key, its probability, and
  resulting Search Node. It resolves randomness without pretending the outcome was strategic.
- **Paired-Seed Case** — one comparison unit that gives every method the same Experiment Snapshot
  and seed conditions. A seat-swapped orientation has its own starting-state identity.
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
token, clone-per-step sessions) · `experiment/` (versioned exact roots, legal-view policy roots,
primitive and chance turn-search nodes, paired-seed matches, parity manifests, branch keys) ·
`game.py` (M3: the `cg/game.py`-shaped battle singleton,
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
smoke. New behavior pins live in parity tests. The 2026-07-12 ability-tail
batch added the god-free reveal-oracle channels (draw-side prize swap, pre-step listing
adoption, `look_feed` DECK→LOOKING binding) and the **kaggle-episode ladder**: all 414
real episodes under the main checkout's `data/replays/` convert + replay
(`tests/parity/test_cabt_replays.py` pins two end-to-end; 123/414 fully green). Ongoing:
burn down the deferred tail through that ladder — the attribution tally (first
divergence → card id) is the ranked queue, digested in
data/handoffs/CGGame/05-m4-pool-fanout.md.
