# M0 — DSL vocabulary, table snapshots, determinism pins ✅ DONE

**Status:** complete 2026-07-10 (commit `a509725`). This doc is the as-built record + the
re-run/regen commands. Nothing to resume unless the competition ships a NEW engine binary.

## What exists

- **DSL vocabulary** — `src/cgpy/defs/dsl_vocabulary.json`: the native `Chain` (71 ops) /
  `State` (39 ops) / pipeline free-function surface with **names + typed params + arities**,
  mined from the un-stripped `src/cg/libcg.so` by `tools/parity/extract_dsl.py` (pure-Python
  mangled-symbol grep + batched `c++filt`; Git Bash has c++filt on Windows).
  `--check` = drift alarm. **This is the interpreter checklist**: a cgpy chain op should map
  to a native verb name wherever the mapping is direct.
- **Card/attack tables** — `src/cgpy/defs/{card_data,attack_data}.json` (1267 cards / 1556
  attacks, the DLL's own AllCard/AllAttack dump) + `tables_meta.json` (source-binary sha256s
  + probe-pinned `BattleStart` deck-validation codes). Regen: `tools/parity/snapshot_tables.py`
  (needs DLL; `--check` for staleness).
- **Determinism pins** — `docs/pyeng/determinism.md` (the prose record) enforced by
  `tests/parity/test_determinism_pins_engine.py` (5 tests, skip cleanly without the DLL).
  Probe tool: `tools/parity/pin_determinism.py --probe {serials,options,selectdeck,fork,mulligan}`.
- **ADR-0050** — the decision record (reverses ADR-0010 with the parity-gate mitigation).

## The pins a resuming session must NOT re-derive (they're settled)

- Serials: seat 0 submitted-position i → `3+i`; seat 1 → `63+i`; serials 1-2 reserved.
  Frame-0 god decks are already shuffled; the initial shuffle is UNLOGGED.
- **Deck top = the END of the deck array** (draws pop the tail). Prize row: last = top.
- `select.deck` listings preserve the TRUE internal deck order (== god view); DECK-area
  option `index` points into that listing.
- `search_begin` fork: reshuffles predictions itself (given order NOT preserved) but is
  deterministic across identical calls.
- `IsFirst` is always posed to seat 0, pre-deal. Deck-validation errorTypes: 1 unknown id,
  2 >4-per-name, 3 no basic, 4 ACE-SPEC (even two distinct).
- Enum encodings: live obs = ints; visualize frames = name-strings with a +1 `selected` offset.

## If the engine updates mid-competition

1. `python tools/parity/extract_dsl.py --check` and
   `python tools/parity/snapshot_tables.py --check` — both must fail loudly if anything moved.
2. Regenerate both, diff the vocabulary (new ops = new interpreter executors needed),
3. Re-run the pin tests + the whole parity corpus; every divergence is a changed behavior to
   re-pin.
