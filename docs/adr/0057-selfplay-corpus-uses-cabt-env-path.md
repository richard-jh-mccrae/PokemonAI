# ADR-0057: The self-play corpus uses the cabt-env path (for Tuner-usable obs), not the A/B harness

**Status.** Accepted and BUILT — `tools/sim/selfplay.py` generates the own-game corpus on the cabt-env
path (carrying the per-frame agent `obs`, so Corrections are Tuner-usable), while `battle.py` stays the
isolated-subprocess A/B path. (Renumbered 0022 -> 0057 on 2026-07-14: ADR-0022 is the Gust doctrine. See docs/adr/README.md.)

**Context.** M1b generates **our agent's own games** as replays for the ADR-0009 own-Pilot
correction loop (tag blunders → Corrections → Tuner → weights).
[ADR-0021](0021-prefilter-balances-seats.md) built the A/B Pre-filter on `tools/sim/battle.py`
(isolated subprocesses — the only way to A/B two *different* configs) and noted battle.py could emit
taggable replays via `visualize_data()`. Grilling M1b (2026-06-29) showed that is insufficient for the
corpus:

- A Correction is only **Tuner-usable if it carries the per-frame agent `obs`** (int-enum): `featurize`
  does `pilot.explain(correction.obs)` and the Tuner **skips** any correction with `obs=None`
  ([featurize.py:26](../../tools/train/tuner/featurize.py:26), [run.py:49](../../tools/train/tuner/run.py:49)).
- `visualize_data()` yields the `current`/`select`/`selected` film but **not** `obs`; the cabt env adds
  `obs` separately from `env.steps` in `finish()`. So a battle.py film-only replay is *human-taggable*
  but **Tuner-dead** — the loop would look closed yet tune nothing.
- The cabt env (`env.run` → `env.toJSON()`) produces the film *with* `obs` and the exact +1 alignment the
  inspector/Tuner already rely on — and the machinery exists in `check_agent` (`_run_match` + `env.toJSON`).
- The corpus is **mirror self-play** anyway (one agent exists), where the cabt env's single-interpreter
  limit (the reason battle.py exists for A/B) does not bite.

**Decision.**
- Generate the corpus on the **cabt-env path** in a new `tools/sim/selfplay.py`
  (`<agent> -n N [--overlay path]`), reusing check_agent's `_run_match` / `env.toJSON()`. **Not** a
  battle.py `--save-replays` (Tuner-dead) and **not** the dropped `tools/selfplay/` dir (that was the
  A/B evaluator).
- **Save layout:** `data/replays/selfplay/<agent>_<YYYYMMDD-HHMMSS>_<sha>[-selfplay]/<episode_id>.json`
  (gitignored). The stem matches `provenance.build_identity`'s pattern, so Corrections **auto-file under
  a real build folder**, not `_UNFILED`. Inject `info.EpisodeId` (a globally-unique deterministic int —
  the dedup/review keys assume per-game uniqueness, [store.py:27](../../tools/train/blunder/store.py:27))
  and `info.TeamNames` (distinct per seat; in a mirror both seats are our Pilot, so both are mined).
- **Config selection:** set `AGENT_OVERLAY` before `env.run` so both seats play a chosen config — mines
  the candidate's error surface, not only the default.

**Considered options.**
- **battle.py `--save-replays` (film-only)** — rejected: Tuner-dead (no `obs`); hand-reconstructing
  `obs` + the +1 alignment in battle.py is fiddly and duplicates what the cabt env already does.
- **battle.py with hand-captured obs** — deferred: only needed for a *varied-opponent* corpus (different
  bundles → battle.py isolation), which needs handcrafted opponent agents we don't have yet. Revisit then.

**Consequences.** Two engine paths by design: `battle.py` (A/B Pre-filter, isolated subprocesses) and
`tools/sim/selfplay.py` (own-game corpus, cabt env). The corpus is mirror-only until opponent agents
exist. The `replay_ref` reserved in the Battle Result (ADR-0021) stays vestigial. No inspector/Tuner
changes — the Correction schema already supports self-play (`submission_id=None`, `agent_version` as the
non-ladder timeline key).
