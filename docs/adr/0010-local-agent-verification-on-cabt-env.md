# Local agent verification runs on the real cabt env (kaggle-environments), not the raw `cg` loop

**Status.** Accepted and BUILT — `tools/sim/check_agent.py` verifies agents on the real `cabt` env,
with `kaggle-environments` pinned and venv-isolated in `tools/sim/requirements.txt` (the fast unit
suite never imports it).

**Context.** Before submitting an agent we need to know it is legal, plays a full match
against itself without crashing or timing out, and still works once packaged. There are
two ways to drive battles locally: the low-level `cg.game` loop (`battle_start` /
`battle_select` / `battle_finish`), or the actual competition harness — the `cabt`
environment on `kaggle-environments`, the same code the Kaggle ladder runs. The `cabt`
env is not a standalone package; it ships *inside* `kaggle-environments` (verified:
`make("cabt")` resolves on `1.30.1`) and drives its own bundled engine, while the agent
supplies the full `cg/` from its Bundle.

**Decision.** The agent-check harness (`tools/sim/`) verifies agents on the real `cabt`
env via `kaggle-environments==1.30.1` (the ladder's pinned version).

- Matches run through `make("cabt")` + `env.run(...)`; a seat passes iff its
  `status == "DONE"`, which already distinguishes crash (`ERROR`), slow (`TIMEOUT`), and
  illegal move/deck (`INVALID`). The agent supplies its own deck on the `select is None`
  step, so the real deck path is exercised, not bypassed.
- Agents are loaded **in-process as modules** (one instance per seat) for **playability**. A
  function agent is not parallelizable, so `env.run` runs it in the current process; loading
  the module twice gives each seat its own module-level state.
- **Deployability** instead runs the extracted Bundle in a fresh **subprocess** (cwd = the
  Bundle): once `cg`/`common` are imported from `src/` they are cached in
  `sys.modules`, so only a clean interpreter can prove the *Bundle's own* copies load and
  run — i.e. that the shipped artifact is self-contained.
- Deck **legality** is pre-checked by calling `cg.game.battle_start` directly — the same
  engine verdict the env uses, but it exposes the precise `errorType` (invalid id / >4
  copies / no Basic Pokémon / >1 ACE SPEC) that the env collapses into a generic message.
- The heavy dependency is isolated: pinned in `tools/sim/requirements.txt`, installed into
  a `.venv`, and never imported by the fast unit suite — the `playability` /
  `deployability` tests `importorskip("kaggle_environments")`.

**Consequences.**

- Grader-faithful: identical env semantics, free crash/timeout/illegal detection, and HTML
  + JSON episode replays (`env.render(mode="html")` / `env.toJSON()`, the latter in the
  same format as the meta-tracker replay fixtures) for triaging a failed match.
- `kaggle-environments==1.30.1` pulls a large tree (jax/flax/transformers/openai/litellm/
  open_spiel/pettingzoo). Acceptable because it is venv-isolated and optional for the unit
  suite. Pinned to the ladder version — re-pin and re-verify if the ladder bumps.
- In-process seats share the one `cg` engine and the Search API's global `agent_ptr`. Fine
  for non-search agents; when a Search-based agent must play itself, switch that case to
  agent-vs-baseline or true subprocess isolation.
- Rejected: the raw `cg.game` loop (not grader-faithful; would re-implement deck supply,
  status/timeout semantics, and replay rendering); re-implementing deck legality in Python
  (drifts as the card pool changes mid-competition); a bespoke subprocess IPC harness now
  (premature — only needed once a Search agent self-plays).
