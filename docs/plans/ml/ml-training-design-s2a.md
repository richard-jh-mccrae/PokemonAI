# Build Session 2a Design — Value Net v2: Features & Matchup Encoding (LOCKED)

**Status:** design locked 2026-07-13 (Fable 5 design grill; user-approved forks). Build Session 2a
**executes** this — it does not re-derive the decisions. Deviations discovered during
build get recorded here with a reason, not silently applied.

**Grounding (verified at design time):**
- 17-feature extractor: `src/common/value/features.py` (`FEATURE_NAMES` fixed order,
  pure-on-`Board`, sentinel 12.0 for unknown path-turns).
- Runtime: `src/common/value/model.py` — name-pinned loader, null-model fail-open,
  standardize-then-dot logistic.
- Consumption: capped planner-leaf term `_PLANNER_VALUE_W × (P−0.5)`
  (`src/common/strategy/planner.py:1543`, `_value_term` at :1633) + `win_prob` telemetry.
- Extraction: `tools/train/value/extract.py` replays `pilot._board(obs, select)` per MAIN
  decision frame → the Read (candidates/γ/favorability) is **reconstructable offline exactly as
  the agent saw it**.
- Read surface: `src/common/scouting/read.py` — `candidates: [(archetype, posterior)]`,
  `unknown_mass`, confidence; favorability+coverage from `scouting/matchup.py`.

## D1 — Matchup conditioning: replayed-Read posterior block (user-locked)

New feature block, computed identically at train and runtime (zero train/serve skew):

- One feature per archetype in a **build-time pinned vocabulary** `ARCHETYPE_VOCAB` (new tuple
  in `features.py`, next to `FEATURE_NAMES`): value = the posterior the Read assigns that
  archetype at this decision (0.0 when absent). Feature names generated as `arch:<name>`.
- Plus `read_unknown_mass` and `favorability_coverage` (the trust-weighting scalars;
  `posture_confidence` γ is already feature #9).
- `Board` gains what `features_from_board` needs (candidates reachable via the Board's Read;
  keep the function pure/total — `read is None` → all-zeros + `unknown_mass=1.0`).
- **True deck identity (replay `info.TeamNames`) is never a training input** — evaluation
  stratification only.

Vocabulary rules: vocab = the meta archetypes present in the corpus (cap ~16, rest folds into
unknown-mass behavior); the shipped `value_model.json` carries `"archetypes"` and the loader
requires an **exact match** with the build's `ARCHETYPE_VOCAB` (drift → null model, same rule
as feature names). Meta rotation ⇒ update vocab + retrain (the Work Package 6 rotation loop).

## D2 — Feature growth (append-only; the 17 keep their order)

**Mandatory core adds** (Board primitives, extending `Board`/`_board` where a field is missing):
`turn_index`, `my_hand_size`, `opp_hand_size`, `my_deck_count`, `opp_deck_count`,
`opp_active_hp`, `opp_active_energy`, `my_total_energy_in_play`, `opp_total_energy_in_play`,
`active_can_ko` (0/1), `wincon_in_play` (0/1), `wincon_prize_value`, `energy_attached` (0/1),
`supporter_played` (0/1) — the last two are meaningful on simmed end-of-turn leaf boards.

**Optional candidates behind ablation** (keep iff episode-split holdout logloss improves):
`gust_best_ko_prizes`, `active_ko_prizes`, `active_maxed_kos`, opp-bench energized count
(needs a Board extension — only if cheap).

Philosophy unchanged (ADR-0042): already-computed objective primitives only. Explicitly
**excluded**: Match-Planner mode / directed goal (circular — the value net feeds the planner),
opponent hidden-hand content (counts only), engine-internal state.

## D3 — Capacity: measure, ship MLP if in budget, distill fallback (user-locked)

Train **both** offline: (a) logistic-v2 on the grown features — the baseline, the Value-Net Gate
comparison floor, and the guaranteed fallback; (b) a 2×64 ReLU MLP (Modicum sizing).

**Runtime budget gate** (both must pass to ship the MLP):
1. Hand-rolled pure-Python forward ≤ **1 ms/call** mean over 10k `predict()` calls on the dev
   box (worst-case ≈ 200 decisions × 40 leaves × 1 ms ≈ 8 s/match, inside the ~10-min budget).
2. `tools/sim/battle.py` throughput regression < 10% vs logistic-v2 at equal config.

Fails either → **distill**: logistic over base features + ≤16 pairwise product columns ranked
by the MLP's pairwise permutation importance; product features named `a*b` (name-pinning
intact). Ship whichever passed; keep both artifacts in the training run dir.

**Artifact format v2** (`value_model.json`):
`{"format": 2, "kind": "logistic"|"mlp", "features": [...], "archetypes": [...],
"mean": [...], "std": [...], ...}` — logistic adds `"weights"`; mlp adds
`"layers": [{"w": [[...]], "b": [...]}, ...], "activation": "relu"`.
Loader (`model.py`): missing `format` → v1 logistic path (back-compat with the committed
seed); unknown `kind`/shape/name mismatch → null model. `predict()` signature unchanged;
runtime stays stdlib-only.

## D4 — Training protocol

- **Fix the holdout leak:** `train.py` currently splits every k-th **row** — rows within one
  game are correlated, so holdout logloss is optimistic. v2 splits by **episode id**; all Value-Net Gate
  numbers come from episode-level splits. Additionally hold out one **entire deck pair** for
  the cross-deck generalization read.
- Offline deps: torch (or numpy) via `requirements-train.txt` — never imported by `src/`.
  Fixed seeds, deterministic; record git rev + corpus manifest id in `meta`.
- Labels unchanged: terminal win/loss per seat, γ=1, draws skipped (`extract.py`).
- Report in `meta`: rows, positives, train/holdout logloss (episode-split), held-out-pair
  logloss, ECE (10-bucket reliability), runtime µs/call for the shipped kind.

## Acceptance → Value-Net Gate mapping

Value-Net Gate checklist items in `ml-training-build.md` are measured exactly as defined here: "beats seed
+ 0.69 floor" on the **episode-split** holdout; calibration = the D4 reliability curve;
cross-deck = the held-out pair; runtime cost = the D3 gate numbers. Sanity probes extend
`tools/train/value/sanity.py` (prize-diff monotonicity, captured-lethal → high P, mirror
opening ≈ 0.5, and new: γ=0 board must predict ≈ the general model's output).

## Non-goals (v2 backlog, with triggers)

- Per-archetype model split — trigger: the Value-Net Gate shows per-archetype calibration gaps the posterior
  block doesn't close (Hearthstone +6.5% precedent).
- Oracle guiding (train with hidden info, anneal away) — sample-efficiency lever if corpus
  volume ever becomes the constraint.
- Deep-set/permutation-invariant encoders — only with a neural policy, not this apprentice
  architecture.
