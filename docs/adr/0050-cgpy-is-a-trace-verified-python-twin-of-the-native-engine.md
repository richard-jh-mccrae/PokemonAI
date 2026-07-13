# ADR-0050: cgpy is a trace-verified pure-Python twin of the native engine

**Status:** accepted (2026-07-10)

## Context

Everything the project does runs through the black-box native C++ engine (`src/cg/cg.dll` /
`src/cg/libcg.so`) behind the ctypes shim in `src/cg/`. Two limits motivate owning the rules:

1. **No DLL-free play.** Local games, self-play, and any in-process stepping of arbitrary states
   require the binary. The native RNG is unseeded (`std::mt19937` from `std::random_device`;
   `BattleStart` takes no seed), so reproducibility is only ever statistical (ADR-0021).
2. **The multi-step lethal verifier is blocked.** `planner.py::_engine_confirms_win` can only seed
   the native fork from `obs["search_begin_input"]` — an opaque 84-char blob that captured
   correction fixtures don't carry. In the unit suite the cascade verifier therefore no-ops
   (false-greens), and the two retreat-to-promote maneuvers are deferred on exactly this
   (`data/handoffs/pokemonai-handoff-lethal-multistep-verification-tool.md`).

[ADR-0010](0010-local-agent-verification-on-cabt-env.md) rejected re-implementing engine slices
("drifts as the card pool changes mid-competition"). That reasoning held for unverified
re-implementations. Reconnaissance changed the calculus:

- `libcg.so` is **not stripped**. Its symbols expose the engine's real shape: a `State` class
  (~47 game ops), a `Chain` effect-DSL of **~70 named primitives with recovered arities**
  (`effectDraw`, `effectDeckToBenchAndShuffle`, `postEffectParalyzeIfCoinHead`,
  `targetCondition(TargetType,int,Comparator)`, …), a `CalcDamage→AfterDamage` damage pipeline and
  a `PullTrigger` event system. Card logic is **compositions of a small vocabulary**, not 1267
  bespoke scripts.
- The binary is a perfect **differential oracle**: `battle_start`/`battle_select` drive full
  matches; `visualize_data()` exposes the god-view (ordered decks, hands, per-frame `selected`);
  coins appear as `Coin` logs. Recorded games are exact, replayable specifications.
- The card DB (`AllCard`/`AllAttack`) dumps to ~664 KB of committable JSON.

## Decision

Build **`src/cgpy/`** — a pure-Python engine at exact parity with the native binary — under four
rules:

1. **Parity is pinned by recorded native traces, not by review.** A trace (per-frame observations +
   choices, minted from the DLL) replays through cgpy with hidden-card identity bound lazily at
   reveal points (`RevealOracle`, multiset-integrity-checked) and coin outcomes bound from `Coin`
   logs. Every frame must compare equal with **no normalization** (option/log/zone order as-is).
   A **CI parity gate** replays the committed corpus **DLL-free** (the trace *is* the native side)
   and fails on any divergence — this is the mechanical answer to ADR-0010's drift objection, and
   it runs on every push, both OSes.
2. **Effects are data.** One interpreter executor per recovered `Chain` verb (native names
   verbatim; the symbol table is the checklist, drift-checked against the binary). Per-card
   behavior is a **ChainDef** — a JSON list of ops — in a generated + hand-override two-layer
   table (the `attack_overrides.json` house pattern). A pool card without a def or an explicit
   `deferred` entry is a load error, never a silent gap.
3. **cgpy owns its randomness.** A seedable RNG gives reproducible self-play the native engine
   never had; `manual_coin` surfaces flips as `COIN_HEAD` selects exactly like
   `SearchBegin(manual_coin=True)`; scripted oracles serve replay.
4. **`src/cg/` is never modified.** Engine selection is `sys.modules` aliasing
   (`cgpy.alias.install_if_enabled()`, env `CG_ENGINE=py`) added additively at harness entry
   points; unset, behavior is byte-identical to today. The verification API
   (`cgpy.search.state_from_obs` / `state_from_visualize`, clone-per-step) accepts **structured**
   state — no opaque blob — which is what unblocks fixture-seeded multi-step lethal verification.

Milestones: M0 determinism pins (serials, option ordering, fork semantics) → M1 harness +
vanilla-loop parity → M2 the 3 agent decks' 50-card union at full parity + the CI gate → M3
verification API + `CG_ENGINE=py` → M4 pool-wide fan-out behind a per-card coverage ledger
(`data/engine/coverage.json`).

## Consequences

- The parity corpus and DSL vocabulary become versioned artifacts; an engine update that adds
  symbols or changes behavior fails CI loudly instead of drifting silently.
- The Lethal Solver / Turn Planner gain a fixture-seedable, clonable, deterministic oracle;
  `tests/` can verify whole candidate turns end-to-end without the DLL.
- Self-play becomes seed-reproducible (a property the native engine cannot offer).
- Cost: the effect-catalog burn-down is real work at the pool's tail (abilities especially); it is
  incremental behind fail-loud `UnsupportedCard` + the ledger, never a cliff.
- The grader still runs the native engine; cgpy is a local instrument. Any cgpy/native
  disagreement is a cgpy bug by definition (the sim is authoritative, rulebook L674).

## Considered and rejected

- **Statistical comparison as the parity gate** (play N games on each engine, compare
  distributions): cannot localize faults, needs huge N for rare branches, flaky in CI. Rejected
  for oracle-bound exact replay.
- **Per-card bespoke Python** (1267 hand-written effects): unmaintainable and unverifiable;
  contradicts the engine's own compositional design.
- **Reproducing the native `search_begin_input` blob**: opaque, engine-instance-specific, and
  unnecessary — structured state carries strictly more information.
- **Editing `src/cg/` to add an engine switch**: the wrapper is competition-provided and
  off-limits; aliasing achieves selection additively.
- **Replacing the kaggle cabt env**: it embeds its own native lib and is the grader's contract;
  out of scope.
