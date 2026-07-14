# ADR-0055: One agent runtime owns the deployment profile

**Status.** Accepted (2026-07-13) and **BUILT** — `src/common/runtime.py` is merged to main: `PROFILE`
is the single deployment truth every agent, `tune.py` and `score_diff` build from, each `main.py` is
~5 lines (`make_agent(STRATEGY)`), and `tests/agents/test_runtime.py` pins PROFILE ↔ ctor signature both
ways. (The armed-off list in the body has since moved on — `brief_engine` was retired by ADR-0051;
`value_model` and `escalation` remain `False`.)

**Context.** Every agent's `main.py` (3 shipped + the byte-copy test fixture) carried the
same ~100-line shell: deck read, config/overlay resolution, knowledge-seam wiring, an
18-line `_params.get("<flag>", True)` kill-switch smear, telemetry, `OwnCardModel`, and the
`agent(obs)` callable. "What ships" lived as literals in four files; `tune._build_pilot`
kept a fifth hand-maintained copy. The drift class was live twice: the 2026-07-03
dark-planner incident (5 switches omitted from one main.py), and — found during this build —
the tune mirror ran `promote_ko_aware` / `boost_lethal` / `brief_preevo` OFF while the
agents shipped them ON, so every retest and score_diff run decided with different backstops
than the live agent.

**Decision.**
- **`common/runtime.py` is the composition root.** `PROFILE` is the ONE deployment truth —
  `{Pilot ctor flag: shipped value}`, ON entries A/B-cleared or user-decided, armed-off
  entries (`brief_engine`, `value_model`, `escalation`) dark until their evidence gates
  clear. `build_pilot(strategy, deck, …)` resolves each flag as
  `params.get(flag, PROFILE[flag])` — a deck's own params and the `AGENT_OVERLAY` A/B lever
  (ADR-0021) keep forcing any switch — and builds the engine-backed knowledge seams
  (provider warmed in the pregame window, Scout, Briefs) unless a caller injects them.
  `make_agent(STRATEGY)` is the whole shell and returns the harness contract: the 1-arg
  `agent(obs)` callable, with the built Pilot reachable as `agent.pilot` (probe surface).
- **`main.py` is ~5 lines**: import `STRATEGY`, `agent = make_agent(STRATEGY)`. Loader
  contract unchanged — every harness (grader, arena worker, check_agent, battle server)
  still execs `main.py` with cwd = the bundle dir and calls `module.agent(obs)`.
- **The Pilot ctor stays the raw-scoring layer** (features OFF, decided over the
  flip-defaults-ON alternative on first principles too): defaults-ON would retroactively
  inject every NEW flag into every bare-Pilot test and experiment (default creep), where the
  profile shape is monotone-safe — landing a flag changes nothing until PROFILE names it.
- **The wiring test inverts**: `test_runtime.py` pins PROFILE ↔ ctor signature BOTH ways
  (a new ctor flag fails CI until its shipped value is consciously added; a stale key fails
  when its param retires) and pins the shipped values as data. `test_agent_wiring.py` now
  asserts each main.py contains NO local wiring (one `make_agent` call, no `Pilot(...)`, no
  flag literals) and the fixture stays byte-identical to the shipped mega_starmie.
- **`tune._build_pilot` rides `build_pilot`** — the mirror is structurally dead
  (`retest_one` and score_diff ride it too). `lethal_probe`'s minimal bare-`Strategy()`
  Pilot is deliberately NOT migrated: it is a raw-layer probe, exactly what the raw ctor
  exists for.

**Considered options.** Pilot-factory-only / flags-table-only (rejected by the user: the
shell copies survive and non-flag wiring changes still fan out). Flipping ctor defaults ON
(rejected above). Redirecting the packaged-bundle probe through a module global (kept the
old `_pilot` shape) — rejected for `agent.pilot`: one public handle on the one public object.

**Consequences.** A new feature ships to every agent by adding one PROFILE entry; omitting
it fails CI instead of the grader. The tune-path drift fix moved score_diff 4/315 frames ×3
agents — verified 100% attributable (0/315 with the three flags forced OFF) — and baselines
are recaptured on the new truth. `check_agent mega_starmie` plays clean through the real
loader; the packaged-bundle system tests pass on the 5-line main.py. Deployment knowledge
now has exactly one home; per-agent `main.py` can never drift again.
