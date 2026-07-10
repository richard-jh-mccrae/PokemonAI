# M4 — pool-wide fan-out + coverage ledger ⬜ TODO (after M3; spans sessions)

**Goal:** ChainDefs for the full 1267-card pool (user will add future sets later), derived
mostly by pipeline, verified per card, tracked in a committed ledger. Exact parity is only
ever *measured* by divergence-free replay.

## Build items

1. **`tools/parity/seed_chains.py`** → `src/cgpy/defs/generated_chains.json` (machine layer;
   `chain_overrides.json` wins per chain). Seed sources in priority order:
   (a) structured tables — 533 vanilla attacks get empty programs free; `AttackStat`
   (`src/common/scouting/provider.py`, 96.6% engine-verified + `attack_overrides.json` tail)
   maps fields→op fragments (benchSnipe→postEffectDamageBench, recoil→postEffectDamagePokemon
   self, damageMin=0+does-nothing→preEffectFailAttackCoinTail, …); `card_effects.json`
   heal/draw clauses; `card_functions.json` tags as triage only.
   (b) text rules over the formulaic effect texts (rule ids `R-…` so mis-seeds fix by rule).
   (c) everything unmatched → `reports/parity/unparsed_sentences.json` grouped by template
   hash = the hand-authoring queue, ordered by meta play-rate
   (`tools/meta_tracker/meta_usage.py`).
   Loader validation: EVERY pool card has a def or an explicit `{"deferred": reason}` —
   a missing card is a load error.
2. **`tools/parity/capture_card.py`** — per-card micro-traces (2-5 scenarios) by reusing the
   existing drive-shells: `tools/meta_tracker/probe_cards.py` (probe_card stable/attack/ko,
   probe_pokemon, probe_evolution), `tools/sim/audit_attacks.py` (defender panel +
   `_coin_fork`), `probe_restrictions.py`. Wrap them with the trace recorder instead of
   re-deriving scenario logic.
3. **Coverage ledger** — `data/engine/coverage.json` (committed):
   `{cardId: {status, chains:{chainId: status}, evidence: [trace ids], updated}}`,
   `status ∈ {verified, derived, seeded, unprobed, deferred}`; `tools/parity/report.py`
   rollup by status × card-type × effect family. Report parity as
   (verified/1267, clean frames/total, ops conformance-covered/71).
4. **Op-conformance fixtures** — per interpreter op, 1-2 minimal cards' micro-traces
   committed as that op's semantic pin (`tests/parity/test_op_conformance.py`).
5. **`tools/parity/from_cabt.py`** — convert kaggle/arena/selfplay `env.toJSON()` replays
   (+1 `selected` offset, per-frame agent obs; see `tools/sim/record.py` and
   `tests/fixtures/match-replay.json`) into parity traces → real-opponent games become
   corpus for free. NOTE: these carry NO god frames — the replayer's pure RevealOracle path
   (bind at reveal, multiset-checked) must work without god sync; prize identities bind at
   take-time (the owner's own MOVE log carries the serial).
6. **`tools/parity/onboard_card.py <id>`** — the future-card one-command: seed → capture →
   replay → ledger flip. A genuinely new mechanic (new native symbol) = interpreter op +
   conformance fixture — the only code-touching path. `extract_dsl.py --check` +
   `snapshot_tables.py --check` are the new-set alarms.
7. **Audit-corpus reuse** — give `audit_attacks.measure_attack` a pluggable engine seam (it
   already threads `battle_select` through `_drive_to_attack`) and replay the ~9,500 ADR-0032
   measurements against cgpy: wholesale attack-family parity. Zero tolerance on divergence.
8. **Hardening:** chaos-corpus expansion over fuzzed legal pool decks (`data/parity/`,
   regenerable), a nightly full-pool parity run (manual command, not CI), a seeded free-run
   self-play smoke (crash/legality/termination — no native needed).

## Priorities within the pool

vanilla attacks (free) → AttackStat-covered attack families (audit replay) → Items/Supporters
(text rules are high-yield; ~85% expected auto) → Tools/Stadiums/Special Energy (65, hand) →
Abilities (the hard tail, ~200-300, trigger/timing semantics — probe-confirm each).
