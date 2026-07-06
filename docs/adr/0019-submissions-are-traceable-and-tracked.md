# Submissions are traceable, self-describing, and tracked against performance

Status: accepted

We optimize for the **Strategy** category ([ADR-0012](0012-optimize-for-strategy-category.md)) —
scored on documented reasoning, tested Hypotheses, and matchup strength over a months-long
competition whose field shifts under us. To show the system's growth and tie each agent change
to its results, **every build embeds its own decision-steering fingerprint and leaves a durable
record joined to its performance.** Today `package_agent` ([ADR-0004](0004-shared-common-packaged-per-submission.md))
only zips a **Bundle**; nothing records what an agent *was* or how it *did*.

## Decision

- **Each Submission embeds a Manifest** — its machine-readable decision-steering fingerprint:
  General + deck **Hypotheses** with authored/effective/overridden weights, `status`, and trigger
  source; **Roles**; win-condition **Lines**; `params` (incl. Tier); deck-card **Function Tags**;
  capability flags (Posture, Automatic Value Model, overrides); the decklist; provenance; a
  `schema_version`; and per-component digests. The Manifest is **embedded** in a self-contained
  **Agent Brief** (HTML) that also renders it for a human — one file, both machine- and
  human-readable — replacing `deck.txt` + `version_control.md` in the Bundle.
- **The Manifest is built declaratively** — `import` the deck **Strategy** + the **General
  Strategy** and `stat` the staged Bundle. `search_budget` moves into `Strategy.params` so Tier is
  *declared*. The packager never imports `main.py`, never loads the engine, never parses source.
- **Training provenance ships as a sidecar `tuned.meta.json`** (`tuned_at`, `corrections_count`,
  `corrections_hash` = sha256 of the sorted own-Correction ids) beside the existing `tuned.json`
  ([ADR-0018](0018-applying-tuner-output.md)) — leaving the runtime `overrides` contract untouched.
- **A submit tool (`tools/submit/`) wraps packaging with `build` / `submit` / `collect`.** It
  uploads to the **Simulation** competition (`pokemon-tcg-ai-battle`) — the agent's graded track —
  while the records it produces are the evidence base for the **Strategy** Writeup. `submit` is
  **never implicit** and is gated: it runs the Deployability / Playability harness ([ADR-0010](0010-local-agent-verification-on-cabt-env.md)),
  refuses a `-dirty` work tree by default (override required — so every leaderboard point maps to
  an exact commit), and is quota-aware (5/day).
- **A monotonic Submission Id** (overridable) is baked into the Manifest and the upload message;
  Kaggle's server-assigned `ref` is captured afterward by matching that message.
- **Two committed logs are the spine:** `data/agent_history.jsonl` (append-once, one immutable row
  per Submission — state summary, join keys, lineage `parent_submission_id`, experiment intent) and
  `data/performance.jsonl` (append-only time-stamped samples — score, rank, win/loss, per-Archetype
  matchups, Efficiency, and Decision Telemetry aggregates). The Bundles live in `data/submissions/`
  (gitignored, kept locally forever). `collect` fills the Performance Log from three sources: score
  + rank via `kaggle competitions submissions --csv`; win/loss + per-Archetype matchups by parsing
  the match **replays** (via `classify`); and per-decision time, cold-start, and timeouts from the
  Submission's own match **logs**.
- **The agent emits always-on, tagged Decision Telemetry to `stderr`** from `Pilot.explain()` — the
  trace `decide()` already computes — recording every legal option's score and which Hypotheses
  fired. `collect` aggregates it (e.g. tier mix, per-Hypothesis fire-frequency, decision margin) and
  can also reconstruct traces offline by replaying `Pilot.explain()` on any match's replay. The
  record also carries **sparse reorder markers** (`deferred`/`needy` per-opt, `reordered`/`grabbed`
  top-level) so a reader can tell when `chosen` came from a decide()-only selection step (attack-last
  resequencing, the needy-Line attach tie-break, the greedy multi-pick grab) rather than
  argmax(`score`) — otherwise a legitimate sequencing pick reads as an unexplained "top-score not
  chosen" and `/blunder-buster` could misdiagnose it as a scoring bug. Sparse → an un-reordered
  record stays byte-identical to the pre-marker era, so the tuner/retest keep reading unchanged.

## Considered options

- **Sourcing runtime state by AST-parsing `main.py`** (brittle; silently wrong when wiring shifts)
  or **by constructing the Pilot at build** (couples packaging to the engine). Rejected for
  declarative `import` + `stat`.
- **Nesting training provenance inside `tuned.json`.** Rejected — it would change the runtime
  `overrides` contract `main.py` loads; the sidecar leaves runtime untouched.
- **Manifest in the zip only / an ephemeral sidecar.** Rejected — a *committed* `agent_history`
  is the durable growth record the Writeup cites; `dist/`-style ephemera can't be.
- **Gated/opt-in Decision Telemetry.** Unnecessary: only the submitter can download their own match
  logs (replays are public, logs are not), and the trace is already computed — so always-on is both
  private and free.

## Consequences

- A future capability appears in the Manifest only if it is **declared** (a `Strategy` field or a
  shipped file), not merely wired — capabilities gain a single source of truth.
- `search_budget` now lives in `Strategy.params`; `main.py` reads it from there.
- Reproducibility is enforced by refuse-on-dirty.
- Tree-depth / branch Telemetry is reserved until Tier-1 Search exists.
- The Strategy Writeup becomes a byproduct of disciplined submission, not a separate effort.
- Note: ADR-0002 (extracts-only retention) governs the **Meta Tracker** only; a Submission keeps
  the full replay **and** log of its own matches for Efficiency and Telemetry.
