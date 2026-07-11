# M4 — pool-wide fan-out + coverage ledger 🟢 CORE DONE (2026-07-11; the burn-down continues)

> **Burn-down batch 4 (2026-07-12):** attacks **1175→1238 live** (+63); three sub-batches,
> all capture-first. **4a — the reveal-hand family ×9** (`xOppHandReveal` /
> `xOppHandRevealChoose` / `xDamagePerRevealed`, rules R-E01/E02): the LOOKING round-trip
> with owner-hidden in-moves, the FIFO drain through `hand_pick_expect`, discard-all-
> Items+Tools, per-Trainer/per-Energy scalers, choose-to-discard / choose-to-deck-bottom
> (pseudo `toArea` 14), oppHand menu gates; rode-along ability tail: **Silcoon Multiplying
> Cocoon** (onEvolve ask) + **Luxio Fighting Roar** (evolve-immediate passive, megaEx
> counts as {ex}). **4b — ALL 25 "Then, shuffle your deck." stragglers** (R-B17 rewrite +
> R-E03/E05-E08): may-ask searches, unrevealed to-hand prints (min-1 "a card"), benched-
> count caps, new nouns (Basic {X} / possessive-family / quoted-name / resistance /
> DB-exact species+trainer names), and the attach-distribution machinery
> (`xDeckEnergyAttachDistribute` any-way vs one-target, sequential typed buckets,
> distinct-types caps, no-target picks stay in deck; per-bench attach/evolve loops;
> `xDeckEvolveChooseAndShuffle`; distinct-to-hand). **Future/Ancient targets seed from the
> official CSV Category column** — no native table carries the tag and sgc87_9300 f51
> proves the engine filters by it. **4c — 29/30 multi-clause coins** (R-F01-F03; 528
> Try-to-Imitate deferred: attack-copy machinery): effect-KOs (no HP log, straight stack
> discard through the normal claims flow), the both-sides-die sweep order (CREDITED side
> first — pinned), opponent-owned flips, per-heads riders (energy discards, mills,
> discard-pile recoveries, heads-capped searches), pre→rider coin threading (Magical
> Leaf), condition-choose (ctx 47), shuffle-mon-into-deck, Sand-Attack's defender
> attack-gate transient. **Trainers:** Rare Candy (pair-gated PLAY + ctx-37 skip-evolve)
> + Hand Trimmer (both trim to 5, opponent first, min=max=hand−5 picks, FIFO-drained) +
> **Levincia** = the per-turn stadium-ability machinery (MAIN option area 7 + once-per-
> player-turn marker), unblocking the cabt match-replay fixture **4/60 → 34/60 green**
> (with god-free provisional-prize listing reconciliation in the replayer); its next
> divergence names card 269's ability — the ability tail. Fixtures 152→**293** (26321
> clean frames), ops **92/92 pinned**, gate **906**, cross-engine audits over all three
> sub-batches: **0 divergent**. Pins digested in determinism.md §9d.

> **Burn-down batches 2b–3 (2026-07-11, later same day):** attacks **1143→1175 live**.
> Batch 2b built the **hand-pick rng channel** (`SeededRng.hand_pick` + replay FIFO from
> opp-turn hand-exit MOVE_CARDs + `hand_pick_expect` alignment drain through Judge-class
> movers — the designed hazard, now closed) → all 12 Psych Out / Astonish / Hand Trim /
> Outlaw Leg / Horrifying Bite texts live (ops `xOppHandDiscardRandom` /
> `xOppHandShuffleInRandom`, rules R-B28/29 + R-C10); per-variant shuffle semantics,
> the Hand Trim `oppHandAbove` menu gate and Ascension's EVOLVES_TO `contextCard` all
> pinned. Batch 3: **count-scaled discards** (`xDiscardEnergyCountScaled` /
> `xDiscardHandCountScaled` + per/bonus damage ops, R-D01 — Steel Burst class ×13),
> **gust** (`effectSwitchEnemy` + `damageNew`, R-D02 ×4), **stadium-discard rider**
> (`xDiscardStadium`, R-D03 ×3), and the **`retreat.freeIfNoEnergy` passive** (Melt
> Away — pinned from a RETREAT-menu divergence; Charmander 788 same text). Fixtures
> 133→152 (15199 clean frames), ops **69/69 pinned**, gate 483, cross-engine audit both
> batches 0 divergent. Pins digested in determinism.md §9c.

> **Burn-down batch 1 (2026-07-11, this worktree):** attacks **1074→1143 live** (Dig-family
> protection ×11, two-condition inflict, may-draw-until, discard-hand-draw riders,
> in-play/tools/named-attack scalers, 4 condBonus conds, defender damage-reduce +
> attack-lock transients, evolve-self-from-deck, hand-energy-attach, deck-attach
> choose-target); cards **856→870 live / 62→87 verified** (recovery items, look-reveal-take,
> coin-gust Catcher, double-inflict Laser, self-mill, Stage-1/Tera/named-family/any-number
> search nouns, `anyOf` union specs); **Blissey ex Happy Switch = the first authored
> ability override** (energy-move op). Batch 2a same day: Energy Switch (rides the
> move-energy op), Enhanced Hammer (energy filters), heal-active family, Boxed Order
> ("Your turn ends" completion flag) → cards **876 live / 90 verified**. Fixtures
> 54→133 (13930 clean frames), interpreter ops **62/62 conformance-pinned (UNPINNED
> emptied)**, cross-engine audit over all 69 new attacks: 0 divergent (+ the
> `staging-mismatch` skip class for own-board-sensitive scalers). New §9b pins:
> enum-order multi-inflict, idempotent-condition silence, switch-clears-with-recovers
> (reverse enum), tick `putDamageCounter=false`, `energyAttached` resets at TURN_END,
> imperative-"up to"-min-1, moved-energy keeps its attach tick, ACE-SPEC 1× deck rule.
> Latent `condBonus` dict-iteration crash fixed.

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

- **Abilities** (~463 Pokémon deferred for ability text): the hard tail — author per
  card via `chain_overrides.json` "ability" defs over existing/new ops, plain-mode
  `capture_card.py` micro-traces pin the select shapes (Blissey ex Happy Switch is the
  worked template; batch 4 added Silcoon's onEvolve and Luxio's evolve passive the
  same way). Card-level PASSIVES piggyback the same override file with data keys
  (`defense`, `retreat`, `evolve` — Crustle / Melt Away / Fighting Roar are the worked
  examples). Board-wide passives (Archaludon 170, Latias ex 184, N's Castle 1253,
  Rescue Board 1157) still need their machinery. **The cabt match-replay fixture's
  first divergence names card 269 (Iono's Kilowattrel) — a ready-made next target.**
- **Items/Supporters** (~84 deferred): per-card unique texts — extend TRN rules +
  `onboard_card.py` per card; the unparsed-sentences report is the ranked queue.
  Rare Candy / Hand Trimmer / Levincia (batch 4) are the worked select-shape
  templates for gated plays, both-player picks, and stadium abilities.
- **Tools/Stadiums/Special energies** (~59 deferred): passive/hooked machinery per
  card; the Levincia stadium-ability machinery (MAIN option area 7 + per-turn marker
  + `stadiumAbility` def key) now exists for the activated class.
- **Attack tail** (309 deferred, all composition tails now): 528 Try-to-Imitate
  (attack-copy machinery), energy-bounce-to-hand (×4), opponent-chooses-switch
  variants, move-your-energy variants, and singleton texts. Run the audit diff over
  each new batch (staging-mismatch rows are expected for own-board/opp-hand-sensitive
  effects — micro-trace those).

## Cold-start commands

```bash
python -m pytest tests/parity -q            # the whole gate (DLL-free): 186 tests
python tools/parity/seed_chains.py --stats  # seed-layer rollup
python tools/parity/report.py               # rebuild data/engine/coverage.json + rollup
python tools/parity/onboard_card.py <id> [--attack N] [--promote]   # one-card loop (DLL)
python tools/parity/from_cabt.py <episode.json> --replay            # real-game corpus
# nightly full-pool cross-engine audit: determinism.md §10
```
