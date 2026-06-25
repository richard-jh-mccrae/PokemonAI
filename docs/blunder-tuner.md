# Blunder Tuner (`tools/train/` — planned)

Compiles the **Correction** log into agent improvements. The companion to the
[blunder inspector](blunder-inspector.md): the inspector *produces* Corrections, the Tuner
*consumes* them. Job A of [ADR-0009](adr/0009-training-methodology.md); design fixed in
[ADR-0017](adr/0017-corrections-compile-to-hypotheses.md). **Status: designed, not built.**

## How it works

Input: `data/corrections/corrections.jsonl` (each Correction embeds the agent `obs` for its
Decision — int-enum, the Pilot's exact input; ADR-0015 amendment). For each Correction:

1. **Featurize** — `Pilot.explain(obs)` ([src/common/pilot.py](../src/common/pilot.py)) returns an
   `OptionTrace` per option, whose `.fired` is the set of Hypotheses that fired (the feature vector).
2. **Derive `attribution`** — diff `fired(correct)` vs `fired(chosen)`:
   - **differ** → `hypothesis:<id>` → route **W** (weights can reorder)
   - **identical** → `missing_hypothesis` → route **H** (no weight reorders identical features)
   - gap is the combat term → `tactical` (out of scope)
3. **Fan-out** (one Correction → several signals):
   - **W**: a ranking constraint `Σ wᵢ·(firedᵢ_correct − firedᵢ_chosen) + Δtactical > 0`. Fit all
     constraints by convex **linear-ranking** (structured-perceptron / logistic rank, ADR-0009),
     band-regularized to the [weights scale](weights.md) for legibility → write the per-deck
     **`tuned.json`** (the `{hyp_id: weight}` overrides the Pilot merges by id — `pilot.py:_weight`).
   - **H**: propose a **Hypothesis** (`id`, `rationale` from the Correction, seed weight by band, a
     `when()` *sketch*) for a human to commit to `strategy.py` / `general_strategy.py`. *Highest
     leverage — one blunder fixes a whole class of states.*
   - **status**: transition the implicated Hypothesis (`assumed → confirmed/refuted`) — the
     documented experiment trail the Strategy Category scores.

Output: `tuned.json` (machine, automatic) + proposed Hypothesis edits (assisted, human-committed) +
status updates. **The ladder A/B (Job C) is the only ship gate** — the Tuner never self-validates.

## Build notes / gotchas (read before implementing)

- **`obs` must be embedded** in each Correction (update the inspector); **backfill the existing
  records** from their retained replays (`submissions/<…>/replays/<episode>.json`). Fallback: the
  Tuner can re-derive `obs` from the replay by `(episode_id, frame, seat)` — identical accuracy,
  but replay-dependent.
- **Verify `obs` alignment** before trusting featurization: the film offsets `selected` by **+1**
  (a select at frame `i` is answered by `selected[i+1]`) — confirm the frame's `obs` pairs with the
  same Decision before featurizing.
- **Featurize from `obs` (int enums), never `current`** (full-info, *string* enums — the Pilot
  can't read it).
- The Pilot is **pure Python, no engine** for Tier-0 — runs offline on `obs`.
- Code moved to `src/` (`src/common/{pilot,strategy,general_strategy}.py`, `src/agents/<deck>/`).
  `tuned.json` lives per-deck at `src/agents/<deck>/tuned.json`; the Pilot loads it as `overrides`.

## Future improvements (for a later session)

1. **Tier-1 value-preference labels** — once the Base Value Model (Job B) exists, emit
   `V(after-correct) > V(after-chosen)`. Needs a one-step engine apply for `after-correct` (clean
   mid-turn; murky for turn-enders). Off-policy *rollout* stays rejected (ADR-0009).
2. **Whole-game regression** — re-rank every Decision in a corrected replay with the new weights;
   flag any previously-good Decision the change would flip.
3. **Auto-propagation** — index Decisions by fired-Hypothesis signature; auto-label structurally
   similar Decisions to a tagged blunder, behind a human spot-check gate (precision risk — keep
   corrections gold).
4. **Outcome weighting** — weight a Correction by whether that game was won/lost.
5. **Winner-imitation labels** — ADR-0009's 3rd (broad/silver) label source: the winner's move in
   strong replays, complementing corrections.
6. **Symmetry augmentation** — seat-swap / bench-permutation invariances to multiply labels.
7. **Assisted `when()` authoring** — LLM proposes the executable trigger from rationale + the
   feature delta, with auto-generated unit tests; human reviews.
8. **Status automation** — drive `assumed→testing→confirmed/refuted` from correction counts +
   ladder A/B outcomes.
