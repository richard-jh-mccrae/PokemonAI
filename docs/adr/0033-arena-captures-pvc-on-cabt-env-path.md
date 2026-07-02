# ADR-0033: Arena captures PvC Matches on the cabt-env path (human bridged as an env agent)

**Context.** The Arena (`tools/arena/`) hosts live **PvC Matches** — a human **Visitor**
vs one of our agents. The requirement that shaped this decision: PvC replays are
**training data**, not keepsakes — they must be blunder-taggable and Tuner-usable like
the Self-play Corpus. Two engine paths exist ([ADR-0022](0022-selfplay-corpus-uses-cabt-env-path.md)):
the raw `battle_*` loop (`cg/game.py`) and the cabt-env path (`env.run` → `env.toJSON`).
Only `env.toJSON()` carries the per-frame agent `obs` the Tuner replays the Pilot on;
a `battle_*` capture would be human-viewable but Tuner-dead.

**Decision.** The Arena drives the **kaggle-env cabt environment**, wrapping the Visitor
as an env agent callable — a *human bridge* that publishes each observation to the
Table's WebSocket and blocks on a queue until the browser returns option indices. Each
**Table** runs its env in its own subprocess (the engine holds one battle per process).
On game end (or **Forfeit**) the Arena writes `env.toJSON()` to `data/replays/PvC/`,
embedding Arena metadata — Visitor name, the **Rating**, `abandoned` flag — in the
replay's `info` block so the file stays one self-contained artifact for the SSH pull.

**Considered options.**
- **Raw `battle_*` loop + custom replay writer** — less plumbing (no env, no bridge
  callable). Rejected: replays lack per-frame agent `obs` (Tuner-dead), and it
  re-derives a replay writer the env already provides.
- **Capture both formats** — rejected: redundant; the cabt format already renders in
  the vendored visualizer (ADR-0014) and feeds every downstream tool.

**Consequences.**
- **Timeout overrides are mandatory.** The cabt defaults (`runTimeout` 2000s, overage
  accounting) would forfeit a slow human mid-game. The Arena must raise/disable these
  at `env.make(configuration=...)` — verify enforcement behavior at build time.
- The bridge is synchronous: a stuck human blocks its Table's env thread. The Forfeit
  idle timeout (~10 min) is therefore the *only* cleanup path — it must inject a
  concede/forfeit and reclaim the subprocess.
- The `info` block carries non-engine keys (`visitor`, `rating`, `abandoned`);
  downstream tools ignore unknown keys. PvC replays enter the same tagging pipeline as
  the Self-play Corpus.
- Human opponents give the correction loop the diverse-opponent games the mirror-only
  corpus lacks.
