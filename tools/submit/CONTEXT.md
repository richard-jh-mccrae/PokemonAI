# Submission & Tracking (`tools/submit/`)

Builds a traceable **Submission** from an agent, uploads it to the Simulation competition,
and keeps a durable record of *what each agent was* against *how it performed* — so the
project's growth over time is legible and joinable (the evidence base for the Strategy
Writeup, see [ADR-0012](../../docs/adr/0012-optimize-for-strategy-category.md)).

Reuses **Bundle** (ADR-0004), **Pilot** / **Strategy** / **Hypothesis** / **Role** /
**Posture** (Agent Runtime), **Archetype** (Meta Tracker), and **Correction** (Agent Runtime) —
defined in their own contexts and not redefined here.

## Language

### Submission

**Submission**:
A built, traceable agent — a **Bundle** plus its **Manifest** — destined for (or already
uploaded to) the Simulation competition, identified by a **Submission Id**.
_Avoid_: Bundle (just the package — a Submission is the Bundle plus its Manifest), upload, entry, version

**Submission Id**:
The monotonic integer assigned to a Submission *before* upload — the local join key, distinct
from Kaggle's server-assigned `ref`.
_Avoid_: ref (that is Kaggle's), version, build number

### Records

**Manifest**:
A Submission's machine-readable **decision-steering fingerprint** — a declarative record of
every input that steers the agent's play, plus build provenance. (See ADR-0019 for the full
element list.)
_Avoid_: config, metadata, snapshot

**Agent Brief**:
The self-contained HTML carried inside each Submission that **embeds** its Manifest and renders
it for a human — one file that is both machine- and human-readable, the at-a-glance state of
that agent at build time.
_Avoid_: report, readme, version_control card

**Build Ledger**:
The local, gitignored `builds.jsonl` recording every `build`. The pool `submit` draws from —
by id, or the most recent by default — uploading that build's *exact* zip. `submit` then
promotes the chosen build into Agent History.
_Avoid_: Agent History (the committed *submitted* record), history

**Agent History**:
The committed, durable record of *what each agent was* — one entry per Submission actually
uploaded (state summary + join keys + lineage + experiment intent).
_Avoid_: log, changelog, Build Ledger (that is the local pre-submit pool)

**Performance Log**:
The committed record of *how each agent performed over time* — time-stamped samples per
Submission (score, rank, win/loss, per-Archetype matchups, **Efficiency**, **Decision
Telemetry** aggregates). Separate from Agent History because performance varies with time
while state does not.
_Avoid_: results, scores, metrics

**Dashboard**:
The generated over-time view across all Submissions that charts the Performance Log against
agent state — the growth-and-development picture.
_Avoid_: report, Brief (that is per-Submission)

### Signals

**Decision Telemetry**:
The per-decision trace the agent emits at runtime — for each decision, every legal option's
score and the Hypotheses that fired — the as-run record of *how it chose*.
_Avoid_: log, debug output, trace

**Efficiency**:
A Submission's processing cost — how quickly it decides and how reliably it stays within the
time budget. The benchmarking signal, distinct from playing strength.
_Avoid_: speed, performance (that is the score/record side)
