# Agent Checks (`tools/sim/`)

The pre-submission verification harness. Given one agent, it runs a gated sequence of
checks proving the agent is legal, plays a full match against itself without crashing or
timing out, and still works once packaged. It drives the **real** competition simulator —
the `cabt` environment on `kaggle-environments`, the same code the Kaggle ladder runs —
rather than a stand-in. See [ADR-0010](../../docs/adr/0010-local-agent-verification-on-cabt-env.md).

Consumes the **Bundle** assembled by `package_agent`
([ADR-0004](../../docs/adr/0004-shared-common-packaged-per-submission.md)) and the agent
vocabulary (**Pilot**, **Strategy**) from the
[Agent Runtime](../../src/common/CONTEXT.md) context.

## Language

**Agent Check**:
The whole gated verification of a single agent — **contents → legality → playability →
deployability** — short-circuiting at the first failed stage. The thing a developer runs
before uploading (`python tools/sim/check_agent.py <name>`).
_Avoid_: test (too generic), smoke test, validation

**Playability**:
The property that an agent, run against itself on the cabt engine, finishes every match
with both seats ending cleanly — no crash, timeout, or illegal move. Verified from the
**source** agent over several matches, because the engine is nondeterministic.
_Avoid_: works, passes, runs (name the property, not the outcome)

**Deployability**:
The property that the agent's shipped **Bundle** — once assembled, compressed, and
extracted — contains exactly what it should (and no stray files) and still plays a clean
match. Verified on the **extracted** artifact, never the source tree.
_Avoid_: packaged, shippable, valid

**Bundle**:
The self-contained submission `package_agent` produces: `main.py` + `deck.csv` + the
shared `cg/` engine + `common/` runtime, and nothing else. The unit uploaded and graded;
**Deployability** is a statement about it. (ADR-0004 also calls this the "submission
directory" — same thing.)
_Avoid_: Submission (the Bundle **plus** its Manifest and tracking — a distinct term owned by [Submission & Tracking](../submit/CONTEXT.md)), package, zip, dist
