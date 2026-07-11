# M4 — pool-wide fan-out + coverage ledger 🟢 CORE DONE (2026-07-11; the burn-down continues)

**Goal:** ChainDefs for the full 1267-card pool, derived mostly by pipeline, verified per
card, tracked in a committed ledger. Exact parity is only ever *measured* by
divergence-free replay. M4's MACHINERY is complete and every gate is green; what remains
is corpus grinding — working the deferred tail through the (now fully built) loop.

## As-built (all eight build items)

1. **`tools/parity/seed_chains.py`** → `src/cgpy/defs/generated_chains.json` (committed;
   overrides win per chain key). Sentence-consumption rules (`R-…`): a chain seeds ONLY
   when EVERY sentence of its text is consumed — one leftover defers the whole chain.
   Live: **1074/1556 attacks** (533 vanilla + 541 rule-seeded) and **856/1267 cards**;
   the rest carry explicit `{"deferred": reason}`. Unmatched sentences →
   `reports/parity/unparsed_sentences.json` grouped by template hash (playRate-ranked
   when `data/meta` exists) = the hand-authoring queue. Loader validation: a pool chain
   without a def OR a deferral is a **load error** (`chain.load_chain_defs`).
   Deferral semantics (pinned): deferred **cards** = option absent (loud in replay);
   deferred **attacks** = offered (menu parity) but `UnsupportedCard` on use;
   `menuOffer: false` marks the engine-gated conditional class (Terminal Period).
2. **`tools/parity/capture_card.py`** — per-card micro-traces: `--attack` targets drive
   through the PROVEN audit shell (`audit_attacks._drive_to_attack` + a recording
   `battle_select` wrapper — don't re-derive scenario logic, it bites); card-play targets
   use a target-biased chaos policy (promotes its line after KOs, avoids deferred attacks
   in the tail). Output = standard `parity-trace/1` with god frames.
3. **Coverage ledger** — `data/engine/coverage.json` (committed) + `tools/parity/report.py`:
   per-card `status` = weakest chain, statuses verified > derived > seeded > unprobed >
   deferred; evidence = committed traces that exercised the chain (PLAY/ATTACH/EVOLVE/
   ATTACK logs + select `effect` refs). Current: **62/1267 cards fully verified, chains
   125 verified / 1324 derived / 524 seeded / 849 deferred**, 54 committed traces,
   4513/4513 clean frames.
4. **Op conformance** — `tests/parity/test_op_conformance.py`: every interpreter op maps
   to a committed pinning trace (52/54; `UNPINNED` lists the two with reasons — the list
   is asserted EXACTLY, so it only shrinks deliberately).
5. **`tools/parity/from_cabt.py`** — kaggle/arena `env.toJSON()` → GOD-FREE parity traces
   (+1 action offset; step-1 actions are the decks). Replayer reveal-oracle path built:
   draws/coins from the mover's own windows, prize identities bind AT TAKE TIME
   (multiset-exact provisional swap in `rng.prize_take`), revealed deck listings adopt
   order. The committed fixture (`tests/fixtures/match-replay.json`) converts and replays
   4/60 green — the divergence NAMES the next card (Levincia 1254: stadium per-turn
   activated effect, machinery not yet built).
6. **`tools/parity/onboard_card.py <id> [--attack N] [--promote]`** — the future-card
   one-command: seed → capture → replay → promote → ledger flip. Proven end-to-end
   (Torchic 410 / Collect). `extract_dsl.py --check` + `snapshot_tables.py --check`
   remain the new-set alarms; a genuinely new native symbol = interpreter op +
   conformance fixture (the only code-touching path).
7. **Audit-corpus reuse** — `CG_ENGINE=py` runs the WHOLE ADR-0032 measurement harness on
   cgpy (`audit_attacks.py` main wires the alias); `tools/parity/diff_audit_engines.py`
   compares record-for-record, zero tolerance (coin attacks compare on the deterministic
   min/max fork rows). **Sample gate: 46/46 equal** after modeling the Crustle defense
   passive (+ Nebula's `ignoreDefenderEffects`). The full-pool run is the nightly manual
   command (determinism.md §10).
8. **Hardening** — `tests/parity/test_selfplay_smoke.py` (DLL-free seeded chaos self-play,
   agent decks, terminates crash-free); chaos-corpus expansion stays
   `capture_match.py` over any legal decks (regenerable, gitignored).

## Interpreter growth (all trace-pinned or seeded-and-conformance-tracked)

24 new ops (recoil, heal self/each/choose, discard own energy n/all, self+opp conditions
incl. the FULL checkup machine, coin pre-programs — fail-on-tails / bonus-if-heads /
count-and-until-tails per-heads — mill, discard-hand-draw, take-less transient, may-ask
ctx 43, deck-energy-attach, discard-energy-attach-self, opponent-switches, self-return,
counter distribution ctx 14), granular ignore flags, visible-state scalers, deterministic
condBonus, defender-retreat + opponent-item locks, `allowedFirstTurn`, attack `legal`
menu gates, a two-sided KO sweep with a claims queue (recoil self-KOs, checkup KOs,
simultaneous = draw), and no-Pokémon adjudication on voluntary departure. New pins are
digested in docs/pyeng/determinism.md §9–10.

## The remaining tail (the queue, biggest first — all workable with the built loop)

- **Items/Supporters** (~107 deferred): multi-sentence texts — extend TRN rules +
  `onboard_card.py` per card. The unparsed-sentences report is the ranked queue.
- **Abilities** (~600 Pokémon deferred mostly for ability text): the hard tail —
  probe-confirm each via micro-traces; Crustle-template defense passives now seed
  mechanically (R-P01).
- **Tools/Stadiums/Special energies** (60 deferred): passive/hooked machinery per card;
  Levincia-class per-turn stadium effects need a new select-shape pin first.
- **Attack tail** (473 deferred): random-discard family needs a hand-pick randomness
  channel; multi-clause coins; energy-move riders. Run the nightly audit diff to catch
  any WRONG live seed wholesale.
- The two `UNPINNED` conformance ops (xDiscardEnergyAttachSelf needs discard fuel staged;
  xDiscardHandDraw has no live lone-sentence trainer yet).

## Cold-start commands

```bash
python -m pytest tests/parity -q            # the whole gate (DLL-free): 186 tests
python tools/parity/seed_chains.py --stats  # seed-layer rollup
python tools/parity/report.py               # rebuild data/engine/coverage.json + rollup
python tools/parity/onboard_card.py <id> [--attack N] [--promote]   # one-card loop (DLL)
python tools/parity/from_cabt.py <episode.json> --replay            # real-game corpus
# nightly full-pool cross-engine audit: determinism.md §10
```
