# Blunder Tuner (`tools/train/` — planned)

Compiles the **Correction** log into agent improvements. The companion to the
[blunder inspector](blunder-inspector.md): the inspector *produces* Corrections, the Tuner
*consumes* them. Job A of [ADR-0009](adr/0009-training-methodology.md); design fixed in
[ADR-0017](adr/0017-corrections-compile-to-hypotheses.md).

**Status: built and verified end-to-end (TDD).** `tools/train/tuner/` (`attribution`, `featurize`,
`fit`, `propose`, `run`, `io`) + the engine-backed `tools/train/tune.py` CLI, all green
(`tests/test_tuner_*.py`). The inspector **auto-embeds `obs`** in every Correction (aligned to
`film[frame+1]`, verified 43/43); pre-`obs` records are backfilled with
`tools/train/backfill_obs.py`. `tune.py` produces a per-deck `tuned.json` + Hypothesis proposals
from the real log. Limitation: multi-select Decisions featurize on the first chosen/correct index
only (v1).

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
status updates. `tune.py` also writes a durable, committed **`data/proposals/<deck>.json`** snapshot
(`open[]` proposals + `skipped[]`, each stamped with source `agent_build`/`built_at`) — the
`/blunder-buster` cluster source, and a git-tracked timeline of how open blunders shrink per build.
**The ladder A/B (Job C) is the only ship gate** — the Tuner never self-validates.

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

## Applying improvements — the conversion loop ([ADR-0018](adr/0018-applying-tuner-output.md))

The Tuner's two outputs reach the agent two different ways.

**Weights (`tuned.json`) — deterministic, no LLM.** `main.py` loads it as the Pilot's `overrides`
(like `deck.csv`); `package_agent` ships it in the Bundle; `Pilot._weight` resolves each weight as
`overrides.get(h.id, h.weight)`. The file is written **sparse** — only weights that differ from the
authored seed (`tuner.io.sparse_overrides`) — so it *is* the set of deltas that take effect; `{}`
means no weight-route corrections yet (all leverage is in the proposals). `tune.py` prints the
`seed -> new` diff; `tests/test_tuned_wiring.py` guards that every shipped key is a real Hypothesis id.

**Hypotheses (`missing_hypothesis` proposals) — the `/blunder-buster` skill.** An interactive
Claude session, per **cluster** of related Corrections:
1. read the cluster's rationales + states + the **live feature catalog** (`Context`/`Board` in
   `pilot.py`, `cg/api.py` enums, function tags, existing Hypotheses as style examples);
2. author a general `when()` predicate (prefer universal features over `card_id`s; in-band seed);
3. run the **Verifier** — inject it, re-fit over all Corrections, require *cluster-satisfied +
   no-regression + suite-green*; iterate until it passes;
4. present a **diff** to `general_strategy.py` (universal) or `agents/<deck>/strategy.py`
   (deck-specific); the human commits. No auto-commit of executable code.

Status: `assumed` → `testing` (Verifier passed) → `confirmed`/`refuted` (human, after ladder A/B).
The `rationale` is the **authoring spec**, so the inspector prompts for the *general rule* at capture.

### Build order (shipped)
1. **Wire weights** (deterministic) — done: `main.py` loads `overrides=_read_tuned()`,
   `package_agent` ships `agents/<deck>/tuned.json`, `Pilot._weight` applies it, sparse + guarded.
2. **Verifier** (`tools/train/tuner/verify.py`): inject candidate Hypothesis → re-fit over all
   Corrections → assert cluster-satisfied + no-regression + suite-green. Reuses `featurize` + `fit`.
3. **`/blunder-buster` skill**: bundle-prep (cluster + catalog + states) → author → verify → diff.
4. **Guiding rationale prompt** in the inspector (free prose; elicit the general rule).

### System-test coverage (real agent, end to end)

`tests/test_blunder_system.py` exercises the whole feature on the **real** strategy/engine/bundle
(skips cleanly if the native engine is absent):

- **ST-1** tag a Decision + author a Correction *with a note* → stored with auto-`obs`, decoded
  labels, and the build identity parsed from the replay path (real inspector spine).
- **ST-2** a noted Correction → a new-Hypothesis **proposal** carrying the note (real engine `tune()`, H route).
- **ST-3** a Correction → a **weight delta** in `tuned.json` (real engine `tune()`, W route).
- **ST-4** the packaged bundle **applies the tune in a real decision** (subprocess, cwd = bundle).
- **ST-5** the packaged bundle **fires a newly committed `when()`** (subprocess).

`tests/test_agent_tuned_system.py` additionally pins that the shipped bundle resolves a tuned weight
through `Pilot._weight`; `tests/test_tuned_wiring.py` guards that every shipped override key is a
real Hypothesis id (else it is silently ignored).

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
9. **API authoring tool (deferred mode B, ADR-0018)** — `author.py` calls the Anthropic API per
   cluster → candidate `when()` → Verifier → diff. Bolts onto the same Verifier + catalog; justify
   it only when authoring volume grows.
10. **Machine-extracted feature catalog** — emit the `Context`/`Board`/`CardStat` fields + enums +
    function tags as a structured catalog (built with mode B, so the API call has the vocabulary).
