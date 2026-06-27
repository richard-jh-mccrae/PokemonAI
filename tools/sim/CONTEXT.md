# Agent Checks (`tools/sim/`)

The pre-submission verification harness. Given one agent, it runs a gated sequence of
checks proving the agent is legal, plays a full match against itself without crashing or
timing out, and still works once packaged. It drives the **real** competition simulator —
the `cabt` environment on `kaggle-environments`, the same code the Kaggle ladder runs —
rather than a stand-in. See [ADR-0010](../../docs/adr/0010-local-agent-verification-on-cabt-env.md).

The same native engine also powers the **Battle** — a local head-to-head between two
contestants for a quick comparative read (`python tools/sim/battle.py <A> <B> -n N`).

Consumes the **Bundle** assembled by `submit.package` (via `build`)
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
The self-contained submission `submit.package` produces: `main.py` + `deck.csv` + the
shared `cg/` engine + `common/` runtime, and nothing else. The unit uploaded and graded;
**Deployability** is a statement about it. (ADR-0004 also calls this the "submission
directory" — same thing.)
_Avoid_: Submission (the Bundle **plus** its Manifest and tracking — a distinct term owned by [Submission & Tracking](../submit/CONTEXT.md)), package, zip, dist

**Match**:
One game on the cabt engine between two seated agents — from start to a win, loss, or draw.
The unit **Playability** is checked over, and the unit a **Battle** is made of. The engine's
`battle_*` API (`cg.game`) drives a single Match; "battle" *at that layer* means one game —
distinct from a **Battle** here, which is the N-Match series.
_Avoid_: game, episode, battle (the engine's single-game API — a Battle here is many Matches)

**Battle**:
A series of N **Matches** between two contestants, run locally to read one contestant's
strength against another. A contestant is either a **Build** (named by its id, extracted from
the ledger) or a **working-tree agent** (named by its agent name, run live from
`src/agents/<name>` — your uncommitted edits). A quick comparative signal **for curiosity,
not a promotion gate** — local self-play is noisy and mirror-biased, and the project's own
evidence is that local measures mislead (the ladder is the real judge; see
`data/training-a-model-breakdown.md`). A Battle whose two contestants are the same thing is a
**mirror** — it should land near 50%, a sanity check that the harness itself is fair.
_Avoid_: tournament, ladder, gauntlet, self-play (only the mirror case is self-play), sparring

**Battle Report**:
The text summary a Battle prints — per-contestant wins, draws, and crashes; each Build's
win-rate with a 95% confidence interval (the noise/honesty knob — wide at low N); and
throughput. The whole output of a Battle; not persisted in v1.
_Avoid_: results, scorecard, leaderboard
