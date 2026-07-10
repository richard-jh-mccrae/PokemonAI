# Blunder Tuner (`tools/train/` — planned)

Compiles the **Correction** log into agent improvements. The companion to the
[blunder inspector](blunder-inspector.md): the inspector *produces* Corrections, the Tuner
*consumes* them. Job A of [ADR-0009](adr/0009-training-methodology.md); design fixed in
[ADR-0017](adr/0017-corrections-compile-to-hypotheses.md).

**Status: built and verified end-to-end (TDD).** `tools/train/tuner/` (`attribution`, `featurize`,
`fit`, `propose`, `run`, `io`) + the engine-backed `tools/train/tune.py` CLI, all green
(`tests/tuner/test_tuner_*.py`). The inspector **auto-embeds `obs`** in every Correction (aligned to
`film[frame+1]`, verified 43/43); pre-`obs` records are backfilled with
`tools/train/backfill_obs.py`. `tune.py` produces a per-deck `tuned.json` + Hypothesis proposals
from the real log. Limitation: multi-select Decisions featurize on the first chosen/correct index
only (v1).

## How it works

Input: the **per-build correction tree** `data/corrections/<agent_build>/corrections.jsonl`
(`store.load_corrections` unions it; ADR-0015 amendment), each Correction embedding the agent `obs`
for its Decision — int-enum, the Pilot's exact input.

**Scoped Corrections skip the router entirely.** A `turn`- or `match`-scope Correction
([ADR-0049](adr/0049-corrections-carry-a-scope-decision-turn-or-match.md)) names no better option at
one state, so it is not a ranking label. `tuner/run.py` short-circuits it **before**
`ranking_constraint()` and appends it to `proposals[]` (→ `open[]`) with `seed_weight = 0` — a
sequencing error can never move a Tier-0 weight. Its Anchor's fired-rule diff still rides along as
`attribution`, as *information* for routing. `tune.py` tags its worklist lines `[TURN <n>]` /
`[MATCH]`, alongside the existing `[PLANNED]` / `[LETHAL]` / `[POSTURE≠ …]` marks.

For each **decision-scope** Correction:

1. **Featurize** — `Pilot.explain(obs)` ([src/common/pilot.py](../src/common/pilot.py)) returns an
   `OptionTrace` per option, whose `.fired` is the set of Hypotheses that fired (the feature vector).
2. **Derive `attribution`** — diff `fired(correct)` vs `fired(chosen)`:
   - **differ** → `hypothesis:<id>` → route **W** (weights can reorder)
   - **identical** → `missing_hypothesis` → route **H** (no weight reorders identical features)
   - gap is the combat term → `tactical` (out of scope)
3. **Fan-out** (one Correction → several signals):
   - **W**: a ranking constraint `Σ wᵢ·(firedᵢ_correct − firedᵢ_chosen) + Δtactical > 0`. Fit all
     constraints with a **soft-margin** structured perceptron (`fit.fit_weights`): an L2 pull back to
     the authored seed (`reg`) + a band clamp (±100, [weights scale](weights.md)) bound the fit, and
     a **pocket** returns the lowest-objective iterate `J = Σ hinge + ½·reg·Σ(w−seed)²` (not the
     oscillating last step). The quadratic drift term is what separates a good fit from an overfit:
     spreading a small move over several weights is cheap, but collapsing one doctrine weight far from
     its seed is expensive, so the fit only does the latter when the ranking payoff truly outweighs it.
     `reg` is the **conservatism knob** (`tune.py --reg`, default `fit.DEFAULT_REG=0.25`); the
     [ladder A/B](adr/0009-training-methodology.md) is the ultimate arbiter of magnitude. Result →
     the per-deck **`tuned.json`** (the `{hyp_id: weight}` overrides the Pilot merges by id —
     `pilot.py:_weight`).
   - **H**: propose a **Hypothesis** (`id`, `rationale` from the Correction, seed weight by band, a
     `when()` *sketch*) for a human to commit to `strategy.py` / `general_strategy.py`. *Highest
     leverage — one blunder fixes a whole class of states.*
   - **status**: transition the implicated Hypothesis (`assumed → confirmed/refuted`) — the
     documented experiment trail the Strategy Category scores.

Output: `tuned.json` (machine, automatic) + proposed Hypothesis edits (assisted, human-committed) +
status updates. `tune.py` **defaults to every agent in the log** (`--agent <deck>` narrows to one), so a
`/blunder-buster` run sweeps *all* decks' open blunders in one pass. It writes a durable, committed
**`data/corrections/tuner/<deck>.json`** snapshot per agent (`open[]` proposals + `skipped[]` + `reviewed[]`,
each stamped with source `agent_build`/`built_at`) — the `/blunder-buster` cluster source, and a git-tracked
timeline of how open blunders shrink per build.
**The ladder A/B (Job C) is the only ship gate** — the Tuner never self-validates.

**The reviewed ledger (`data/corrections/reviewed.json`).** Auto-reconciliation drops a blunder once a
rule *satisfies* it; a blunder consciously **set aside** would otherwise resurface every run. The ledger
(hand-editable JSON, keyed by the Scope's subject) records dispositions — `refuted` (a bad correction,
e.g. it forgoes a Knock Out — *also* dropped from the weight fit so it stops pressuring weights),
`deferred` (needs new infra), `covered` (handled by an existing rule). `tune.py` partitions these out
of the active corpus before routing (so they leave `open[]` / `UNSATISFIED`) and lists them under
`reviewed (excluded)` (and `reviewed[]` in the snapshot) — no silent drop. Append with
`python tools/train/review_correction.py <key> <disposition> "<reason>"` (loader:
`tools/train/blunder/reviewed.py`). The key is `<episode>-<frame>` for a decision Correction,
`<episode>-t<turn>s<seat>` for a turn one, `<episode>-m<seat>` for a match one — so disposing of a
Turn Correction never retires the Decision Corrections inside that turn. Every `open[]`/`skipped[]`
snapshot entry carries its `key` (plus `scope`/`subject`) so the dashboard resolves it exactly.

**The CRITICAL marker — must-fix-first.** Write the uppercase token `CRITICAL` into a Correction's
`rationale` to flag a blunder that `/blunder-buster` must resolve **before any other work** (the
marker is case-sensitive, word-boundary — lowercase "critical" prose is not a flag;
`train.blunder.correction.is_critical`). The pipeline surfaces it so the skill never hand-greps: a
`missing_hypothesis` proposal carries `critical` (`tuner.propose`), the durable
`data/corrections/tuner/<deck>.json` `open[]`/`skipped[]` entries serialize `"critical": true`
(`tuner.io.write_proposals`), `tune.py` prints a `*** N CRITICAL … FIRST (blocking) ***` banner and
tags each `PROPOSE`/`UNSATISFIED` line `[CRITICAL]` (with its rationale), and `blunders.html` badges
each `⚠ CRITICAL`. The skill resolves the cohort serially, one reviewed checkpoint each, to a
terminal outcome before any non-critical cluster — and **hard-stops for human acknowledgement** if a
CRITICAL one would only resolve to `refuted`. See `.claude/skills/blunder-buster/SKILL.md`.

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
authored seed (`tuner.io.sparse_overrides`) — so it *is* the set of deltas that take effect.

The fit ships **only if it earns it (adoption gate).** `tune()` keeps the fitted weights only when
they satisfy **strictly more** corrections than the authored seeds already do; otherwise the drift
bought nothing (or traded laterally) and the seeds are kept — so `{}` is the honest, common result on
a corpus whose blunders need new *rules*, not reweighting (this is why a hand-curated `tuned.json`
kept getting reset). `tune.py` prints `W-route: <sat>/<n> satisfied (fit adopted | seeds kept)`, the
`seed -> new` diff for any adopted change, and an **`UNSATISFIED`** line per correction the shipped
weights still can't honour (genuine conflict, or needs an H, not a weight). `tests/agents/test_tuned_wiring.py`
guards that every shipped key is a real Hypothesis id. (`tune.py` reconfigures stdout to UTF-8 so the
`→` in energy-attach labels can't crash the run on a cp1252 console.)

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

### Live Decision Telemetry — closing the loop ([ADR-0019](adr/0019-submissions-are-traceable-and-tracked.md))

The shipped agent emits one `@T` record per decision (`common.telemetry`); `collect` saves it as
`episode-<id>-agent-<seat>-logs.json` beside each replay. This is the **ground truth** trace the
blunder loop reads end to end:

- **See how it decided** — `train.blunder.telemetry_log` parses the log and joins a Correction's
  `(seat, frame)` to its live record (positional map, validated by option-count + `chosen`). The
  inspector surfaces it per frame (real `score`/`fired`/`margin`, plus the `lethal`/`planned` layer
  verdicts — the tagging shell renders them at the decision so the human tags knowing which layer
  drove the pick), and `record_correction` embeds it as `Correction.live_trace`.
- **Retest = see the log after the fix** — `train.tuner.retest` re-derives the decision under the
  candidate Pilot via `telemetry.to_record(pilot.explain(obs))` (the *same* `@T` format) and diffs it
  against `live_trace`: `chosen_before→after`, `margin`, `fixed` (correct now chosen), and the lifted
  `lethal_before→after` / `planned_before→after` verdicts (a Solver/Planner-layer fix's one-glance
  proof). Local + instant; the full-game ladder A/B stays the ship gate. `/blunder-buster` runs this
  per cluster member as before/after proof.
- **Layer routing** — a non-null `lethal` (ADR-0030) / `planned` (ADR-0031) in the live trace means
  that layer **short-circuited scoring** at the decision: no weight or `when()` can fix it; the fix
  is code in `planner.py` (the win rung vs the heuristic rungs — ADR-0037 joined the two into one
  module). The pipeline surfaces this — `tune.py` tags `PROPOSE` /
  `UNSATISFIED` / `SKIP` lines `[LETHAL]` / `[PLANNED]` (with a summary banner), and the proposals
  snapshot carries `"lethal_locked"` / `"planner_committed"` per entry — so `/blunder-buster` routes
  these clusters to the layer, not to rule authoring. (Only the committed half is auto-taggable; a
  `null` verdict on a missed win/line is the skill's step-2 read.)
- **Posture routing** ([ADR-0041](adr/0041-posture-is-observable-in-decision-telemetry.md)) — the live
  trace also carries `posture`: **who the agent thought it faced** (believed archetype `cands`, applied
  `gamma`, matched Brief `slug`). A misplay against a recognized opponent is a **matchup-doctrine**
  issue — fix the archetype's **Matchup Brief** / a posture lever / recognition, **never** a
  deck-agnostic `when()` that would misfire in other matchups. The inspector's **"opponent read was
  wrong"** checkbox writes a structured `Correction.posture_mismatch`; `tune.py` tags flagged lines
  `[POSTURE≠ <archetype>]` (with a banner) and the proposals snapshot carries
  `"posture_mismatch"` + `"believed_archetype"`, so `/blunder-buster` clusters by believed archetype
  and routes to the Brief (or hands full authoring to `/matchup-genie`). Even unflagged corrections
  carry `believed_archetype` as clustering context.

### Build order (shipped)
1. **Wire weights** (deterministic) — done: `main.py` loads `overrides=_read_tuned()`,
   `package_agent` ships `agents/<deck>/tuned.json`, `Pilot._weight` applies it, sparse + guarded.
2. **Verifier** (`tools/train/tuner/verify.py`): inject candidate Hypothesis → re-fit over all
   Corrections → assert cluster-satisfied + no-regression + suite-green. Reuses `featurize` + `fit`.
3. **`/blunder-buster` skill**: bundle-prep (cluster + catalog + states) → author → verify → diff.
4. **Guiding rationale prompt** in the inspector (free prose; elicit the general rule).

### System-test coverage (real agent, end to end)

`tests/blunder/test_blunder_system.py` exercises the whole feature on the **real** strategy/engine/bundle
(skips cleanly if the native engine is absent):

- **ST-1** tag a Decision + author a Correction *with a note* → stored with auto-`obs`, decoded
  labels, and the build identity parsed from the replay path (real inspector spine).
- **ST-2** a noted Correction → a new-Hypothesis **proposal** carrying the note (real engine `tune()`, H route).
- **ST-3** a Correction → a **weight delta** in `tuned.json` (real engine `tune()`, W route).
- **ST-4** the packaged bundle **applies the tune in a real decision** (subprocess, cwd = bundle).
- **ST-5** the packaged bundle **fires a newly committed `when()`** (subprocess).

`tests/agents/test_agent_tuned_system.py` additionally pins that the shipped bundle resolves a tuned weight
through `Pilot._weight`; `tests/agents/test_tuned_wiring.py` guards that every shipped override key is a
real Hypothesis id (else it is silently ignored).

## Future improvements (for a later session)

1. **Tier-1 value-preference labels** — once the Automatic Value Model (Job B) exists, emit
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
