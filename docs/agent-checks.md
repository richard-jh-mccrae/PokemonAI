# Agent Checks

Pre-submission verification for one agent: is its deck legal, does it play a full match
against itself without crashing or timing out, and does the packaged bundle still run?
Driven by the **real** cabt simulator (`kaggle-environments`) — see
[ADR-0010](adr/0010-local-agent-verification-on-cabt-env.md) and the
[glossary](../tools/sim/CONTEXT.md).

## The four gated stages

`tools/sim/check_agent.py` runs these in order, stopping at the first failure:

1. **contents** — the source agent dir (`src/agents/<name>/`) has `main.py` + `deck.csv`.
2. **legality** — `deck.csv` is exactly 60 integer rows and the engine accepts it; the precise
   rule is reported (invalid id / >4 copies / no Basic Pokémon / >1 ACE SPEC).
3. **playability** — the agent plays itself 5 times on the cabt engine; every seat must finish
   `DONE` (no crash `ERROR`, timeout `TIMEOUT`, or illegal move/deck `INVALID`).
4. **deployability** — `tools/submit/package.py` builds the Bundle; its archive must be **≤ 197.7
   MiB** (the grader's submission-size cap), it is extracted to a clean dir, its contents are
   checked (`main.py`, `deck.csv`, `cg/`, `common/`), and it plays one match in a **fresh
   subprocess** — proving the shipped artifact is self-contained.

A failed playability/deployability match saves a replay to
`reports/<name>-<stage>-fail.{json,html}` for triage (`reports/` is gitignored).

## Grader resources

Each submission runs in a fixed Kaggle sandbox. What we ship — and how much per-move compute we
spend — is bounded by these (competition-stated; size enforced by stage 4 above):

| Resource | Budget | What it bounds |
|---|---|---|
| Submission size | **197.7 MiB** | the shipped Bundle: engine + `common/` + deck + any offline artifacts (Scouting dossier, card-stat cache, the value model). Generous today; watch it as the value model grows. |
| RAM | **12.2 GiB** | resident memory at runtime — ample, so eager-loading the meta artifact + card cache + a value model is safe. This *relaxes* the old "modest RAM cap" assumption: memory is not the ceiling. |
| Disk | **11.8 GiB** | scratch + the extracted submission. Not a binding constraint. |
| vCPUs | **2** | per-move compute. The **Search budget** (Tier-1 lookahead) must fit the per-move time on 2 cores — this, with the match clock, is the real ceiling on lookahead. |

Time is separate: ≈10 min per-player per match (running out = loss). The binding runtime
constraint is therefore **compute, not memory** — wall-clock on 2 vCPUs gates Tier-1 Search
escalation (see [Agent Architecture](agent-architecture.md) → Metareasoning / the Search budget).

## Setup

The simulator dependency (`kaggle-environments`, pinned to the ladder version — ADR-0010) is
heavy, so it lives in a venv; the fast unit suite never imports it.

```
python -m venv .venv
.venv\Scripts\pip install -r tools/sim/requirements.txt pytest
```

## Run

```
# one agent, end to end
.venv\Scripts\python tools/sim/check_agent.py slowking

# faster dev loop: fewer matches, skip the packaging stage
.venv\Scripts\python tools/sim/check_agent.py slowking --matches 2 --no-deployability
```

Exit code is 0 if every stage passes, 1 otherwise.

## Tests

```
# fast unit suite (system Python): contents/legality run, the cabt stages skip
python -m pytest tests/ -q

# full harness incl. the cabt stages (in the venv)
.venv\Scripts\python -m pytest tests/test_check_agent.py -q
```
