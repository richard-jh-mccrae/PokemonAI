# Turn Planner — the missing "develop optimally" rung (within-turn rollout)

**Status: Phase 0 + Phase 1 BUILT + Phase 2 cost/safety MEASURED 2026-07-15; the rung is now armed-ON in the
shipped PROFILE (`develop_rollout: True`) for an in-place Kaggle-ladder A/B on the next submission. Phase 3
NOT started.** Grilled from the user's report that the Pilot "acts decision by decision with no
forethought." This doc is the investigation + the phased path.

> **Ladder A/B is LIVE-pending-submission (user decision 2026-07-15).** `develop_rollout` flipped to ON in
> `common.runtime.PROFILE` (+ the `test_runtime.py` pin), so the next `tools/submit/submit.py` ships the rung
> to every agent and the ladder score vs the prior flag-off submission IS the A/B. Kill-switch if weak. The
> ctor default stays `False`, so a Pilot built directly (tests, offline retests) is unaffected.

## Phase 1 BUILT (2026-07-15) — the develop rollout rung + telemetry

- **The rung** (`planner.py`): `_develop_rollout_line` is the new bottom rung of `plan_turn` — reached
  only when every higher rung returned None (no KO/gamble/escalate) AND `_develop_should_fire(traces)`
  (greedy weak: top score `< _DEVELOP_STRONG_SCORE`=30, or near-tied: margin `< _DEVELOP_TIE_MARGIN`=5 —
  augment-not-override, first-cut thresholds). It rolls out every candidate first action through the
  existing `_engine_leaf_value` sim (re-runs my policy to end-of-turn; no opponent model — the safe
  half), commits the highest-leaf option as `TurnLine(goal="develop", ranked_by="engine", diverged=…)`,
  and defers (None) when nothing is simmable. Gated behind `develop_rollout` (PROFILE + ctor,
  **default OFF**, pinned by `tests/agents/test_runtime.py`); byte-identical when off.
- **Telemetry** (`telemetry.py` + `Decision.plan_candidates`): a develop record emits the RANKING, not
  just the argmax — `planned.value` (sparse, keyed on goal=="develop"), and `plan_candidates` = top-K
  (`_DEVELOP_PLAN_K`=3) `{step,value,why,committed?,greedy?}` sorted desc, greedy always included so an
  override's value gap is readable. Sparse: absent off / non-develop → byte-identical (asserted).
- **Consumer** (`tools/train/tuner/propose.py`): `ProposedHypothesis.plan_candidates` surfaces the
  ranking so a `sequencing_error` correction lands next to the alternatives it out-scored.
- **Tests** (all red→green): `test_develop_rollout_rung.py` (ranking + gate, leaf stubbed),
  `test_develop_rollout_telemetry.py` (wire contract + byte-identity), `test_planner_engine.py`
  (engine-backed e2e — the rung engages on real mirror setup turns; flag-off commits no develop line),
  `test_blunder_planner_layer.py` (consumer). Full suite green.
- **Soundness guard (added when the PROFILE flip surfaced it).** The rollout is HEURISTIC (auto coins,
  predicted opponent zones), so a `KO_SCORE`-class leaf is an UNVERIFIED "win." On `ml f24` the rung
  committed such a phantom-win option, overriding the human's real lethal-enabling attach. Fix: the
  develop rung **defers (returns None) when its best rollout value is `>= KO_SCORE`** — sound wins are
  the win rung's exclusive job (it runs first and had already declined), and an unsound rollout-win must
  never override the tuned scoring. This keeps the rung strictly a NON-winning-development rung. Two
  `f24` regression tests drove the fix; full suite green after.
- **Reproducibility guard (#178, 2026-07-27) — the guard above was necessary and not sufficient.**
  `ml f24` stayed a heisenbug for another week: the defer-on-phantom-win rule made the rung's *answer*
  depend on whether any candidate happened to roll a phantom win on that RNG stream, so it flipped
  `[5]`/`[3]` across processes and failed ~2 of 3 full-suite runs on `main`. The channel is the
  **shuffle**, not coins: `_seed_zones` seeds `search_begin` with a predicted MULTISET and the engine
  shuffles it, so every card the sim draws off it is a sample (f24's 13 candidates carry `SHUFFLE` +
  `DRAW` and **no COIN** — the earlier coin-only exclusion was a no-op there, and its docstring's claim
  that coin-free values are stream-invariant was false). Fix: `_simulate_line`'s 6th tuple element is
  now a general `stream` bit (coin, draw, top-N peek, mill, or face-down prize — a deck *search* is
  order-independent and does NOT count), and the rung defers **all-or-nothing** if ANY candidate rode
  it. Excluding only the offenders would select for lines that touch nothing (a bare END never draws)
  and on f24 would have committed the END. Cost: measured on live mirror drives, the rung now commits
  on roughly half its calls rather than nearly all of them. Ruled as ADR-0072 amendment C.
- **Not built:** the "hand quality" leaf dimension (undefined — a test would be phantom); the
  plan-once-materialize-replay cost optimization (receding-horizon per-frame is the shipped first cut).
  **Next = Phase 2:** flip `develop_rollout` on a Kaggle-ladder A/B (needs the live search token, so no
  offline gate) and measure setup-turn cost.

## Phase 0 progress (2026-07-15)

- **`_board_development` enriched + unit-tested.** It was role-blind (`10·bodies + 5·energy`). Now it
  also credits WIN-CONDITION bodies (`_PLANNER_WINCON_DEV_W`) and Energy attached to them
  (`_PLANNER_WINCON_ENERGY_W`), via the existing `_wincon_set()` — so at equal material a board that
  builds the win-condition, and one that puts Energy on the RIGHT body, out-develops junk. Changed from
  `@staticmethod` to an instance method (both call sites already used `self.`). Tests:
  `tests/strategy/test_leaf_development.py` (two red→green slices); full suite green (2918 passed).
  The hard-rung invariant holds: `_leaf_value` caps development at `_PLANNER_DEV_CAP`=100 ≪ KO_SCORE=1000,
  so a positional term can never outrank a real prize. The third dimension the scope names ("hand
  quality") is deliberately NOT built — it is undefined here, so a test for it would be a phantom.
- **BLOCKER — the correction-board proof cannot run offline on the native engine.** `_engine_leaf_value`
  → `_simulate_line` gates on `obs["search_begin_input"]`, a live native-engine state token set only
  during play (`src/cg/game.py:15`). **None of the 335 recorded corrections carry it** (their obs hold
  only `current`/`logs`/`select`/`remainingOverageTime`), so the native leaf sim returns `None` on every
  one. A cgpy-backed offline harness IS feasible — `cgpy.search.state_from_obs` structurally reseeds a
  MAIN-select board (100 of 104 sequencing corrections are Main-select; the parity suite injects a
  placeholder token, `tests/parity/test_search_api.py:244`) — but it is parity-limited (~298/434) and
  `_simulate_line` hardcodes native `cg`.
- **Decision (user, 2026-07-15): defer the real end-of-turn-board proof to the Phase-2 Kaggle-ladder A/B**
  (the only valid gain signal regardless), accepting the two unit slices as mechanism-level evidence.
  Leaf work stops here; the next build is the Phase-1 rollout rung + telemetry.

## Diagnosis — why the planner isn't planning

The Turn Planner was **designed** as a whole-turn optimizer (ADR-0031 title: *"a goal-directed,
engine-simulated whole-turn optimizer"*; Goal Ladder specified from *"win"* down to *"develop
optimally toward the win-condition"*). **Only the KO-reaching rungs were built.** The bottom rung —
the one that plans setup/development turns — was explicitly deferred (*"the develop-order fold-in /
full unification"*, ADR-0031 Remaining) and never implemented.

Consequences, verified in code:
- `_closed_form_candidates` (`planner.py:196`) returns `[]` when no KO is reachable. So on any turn
  without a KO to aim at, `plan_turn` returns `None` → the Pilot falls to `_finish_turn_last`, a fixed
  5-tier ordering heuristic (free-dev → supporter → attach → shuffle → attack) + independent per-option
  scoring. No forward search, no end-of-turn-board evaluation. This is the "greedy per-frame" the user
  observed.
- Only `goal="win"` lines are materialized + replayed as a committed sequence (`_win_lock_store` →
  `replay_locked_line`). Every other multi-step line (`ko_for_prizes`, `stabilize_then_ko`) yields a
  first step then **re-derives from scratch next frame** — re-derivation, not committed forethought.

## The honest nuance (do not overclaim "it's all broken")

Retested the worst sequencing corrections (incl. the ones literally saying *"we need a turn planner
system"*): **8 of 12 are already FIXED** — not by a planner, by per-frame RULES accrued over the
blunder rounds (`develop-the-accel-recipient`, `prefer-bench-fill-first`, `concentrate-energy-on-wincon`,
heal-first). The 4 still live are scoring nuances / target-selection / attack-choice, not clean planner
failures. **The real problem is whack-a-mole:** greedy has been patched spot-by-spot into imitating
planning on caught boards. It only gets the *current* step right, needs a rule per situation, and a
novel board falls back to raw greedy.

⚠️ **Process gotcha:** `train.tuner.retest.retest()` returns a **dict**, not an object. `getattr(r,
"fixed", None)` returns `None` for every row → a batch loop silently prints everything as "LIVE". Read
`r["fixed"]`, or cross-check against `tools/train/retest_one.py`. (This produced a false "all 12 live"
mid-investigation.)

## The infrastructure already exists, is ON, and is SAFE

- `_simulate_line` (`planner.py:2051`): forks an independent sim, takes a first action, **re-runs the
  policy to end-of-my-turn**, returns the real end-of-turn board. **UNBUDGETED** for my-own-turn
  (`planner.py:2086`).
- `_engine_leaf_value` (`planner.py:1988`): scores that board (prizes + Active-survival vs Incoming +
  `_board_development` + the parked ADR-0042 value term).
- `replay_locked_line`: materialize + replay a committed sequence across frames.
- These run every KO turn in production: `planner_engine_rank`, `lethal_verify`, `lethal_family` are
  all `True` and unbudgeted → the cost is proven affordable.
- **The one search that regressed (−12 pts, `escalation`, off) was the TWO-PLY opponent-reply tree** —
  it predicts the opponent's hand from *my* deck and uses *my* policy as their reply. A **within-my-turn
  rollout needs NO opponent model.** That is the safe half, and it is exactly the deferred rung.

## Locked scope (user, 2026-07-15)

1. **Leaf value first.** Enrich `_engine_leaf_value` / `_board_development` (wincon-line bodies vs junk;
   energy on the right body; hand quality) and PROVE on the tagged correction boards that it ranks the
   human's preferred end-board above the greedy one — BEFORE wiring any rollout. This is the bottleneck
   and the reason the rung was deferred. A rollout on a blind leaf regresses the cases the tuned rules
   currently handle.
2. **Within-turn only.** Plan the sequence to the best end-of-MY-turn board. Cross-turn ("attach now for
   a KO NEXT turn", the Category-C corrections) STAYS DEFERRED — it needs an opponent model + deeper
   search, the same class as the regressed escalation.
3. **Augment, expand as it proves out.** Fire the rollout only where greedy is weak/indifferent (no
   strong rule firing, options near-tied) — where it can only help — leaving the tuned rules in charge
   where they already decide. Expand the rollout's authority as ladder A/B confirms.

## Leaf lab — the offline measurement bench (BUILT 2026-07-16)

The armed-ON rung played setup turns badly ("almost drunk", user 2026-07-16). Root cause is the one the
plan always named: the **leaf is blind**. On a develop turn (no prizes/KO) `_engine_leaf_value` collapses
to `_board_development` ≈ raw body+energy count — no tempo, hold, sequencing, or cross-turn sense — so the
rung maximizes "play more stuff" and can't even break ties.

`tools/train/leaf_lab.py` (`evaluate_leaf_on_correction` / `leaf_lab_report`) re-scores a tagged
`turn_plan` correction's board through `_engine_leaf_value` **offline via cgpy** (the new injectable
`_simulate_line` seam `pilot._search_api`; inject a placeholder `search_begin_input`, cgpy rebuilds the
state from the MAIN-select board), and reports whether the leaf ranks the human's `correct` pick highest.
This makes ANY leaf version measurable without a ladder run. cgpy is parity-limited (~298/434) — VALUES
differ slightly from native, the RANKING is the signal; non-MAIN / unreseedable boards are skipped + counted.

**Baseline (2026-07-16, 4 dragapult turn_plan corrections, 2 scorable): leaf ranks `correct` highest
0/2 (0%), avg top-tie 2.5.** `ep86090164 correct=[0]` → rank 5/8 under a 4-way tie at 65; `correct=[1]` →
rank 5/27, top 1075 (a phantom heuristic-sim "win" the leaf hallucinates — the soundness guard correctly
keeps the rung out there live). This 0/2 is the target the leaf-enrichment work must move.

To harvest the corpus while it's armed, `_DEVELOP_PLAN_K` was raised to 50 so `plan_candidates` captures
the FULL menu ranking (the human's later `correct` pick is always in the trace with its leaf value).

## Phased path

- **Phase 0 — the leaf.** Enrich the end-of-turn leaf; validate ranking on the corrections (e.g.
  `Poffin→attach→attack` > `attack(empty bench)`; `keep-strong-hand` > `Lillie's-shuffle`). Measured,
  no behavior wired. This is the real work.
- **Phase 1 — the rollout rung.** New bottom rung of `plan_turn`, fires only when it currently returns
  `None` AND greedy is weak/indifferent. Receding-horizon (each frame: rollout each candidate first
  action, pick the best end-board) is the simplest first cut; plan-once-materialize-replay (reuse the
  win-lock template) is the cost optimization if per-frame cost bites. Gated behind a new PROFILE flag,
  default OFF, byte-identical when off. **Ships with the telemetry below — it is a Phase-1 acceptance
  criterion, not an afterthought: without it the ladder A/B in Phase 2 is un-analysable.**
- **Phase 2 — measure + A/B.** Cost on setup turns (a big multiplier vs KO-only today) and Kaggle-ladder
  A/B. Gauntlet is invalid; the ladder + user feedback are the only valid signal.

  **Cost + safety MEASURED 2026-07-15 (affordable, safe).** 30 mirror games/arm on the committed engine,
  `develop_rollout` OFF vs ON (`scratchpad/develop_cost.py`):
  - **~50-70 ms per develop-rung fire**; the rung fires ~16×/game → **~1.1 s/game of rung compute**.
  - Wall **0.32 s/game OFF → 1.46 s/game ON** (~4.6×; partly because games run longer with the rung).
  - Leaf sims ~50× (the rung sims every candidate on every develop turn — the expected "big multiplier").
  - **0 crashes across 60 games.** Grader budget is ~10 min/match ([[kaggle-execution-model]]); even at a
    large hardware slowdown the added seconds/match sit far under it. **Verdict: affordable, ship-safe.**
  - Finding: the augment-not-override gate is PERMISSIVE on mirror openings (fires often). Good A/B signal;
    if the ladder regresses, `_DEVELOP_STRONG_SCORE` / `_DEVELOP_TIE_MARGIN` are the first tuning knobs.

  **Ladder A/B — the gain gate, USER-run (external, ladder budget).** Local self-play win-rate is invalid
  ([[gauntlet-invalid-ladder-only]]); only the Kaggle ladder counts, and the grader ignores `AGENT_OVERLAY`
  (local-only). So the A arm must be a COMMITTED flag-on build: set `develop_rollout: True` in the deck's
  shipped params (or flip PROFILE), commit (submit refuses `-dirty`), `python tools/submit/submit.py`, and
  compare its ladder score vs the current flag-off submission. This is a Kaggle submission + a multi-day
  ladder wait — the user's call, not autonomously runnable.
- **Phase 3 — retire whack-a-mole.** Only after the rollout PROVES it subsumes them, retire the
  per-frame sequencing rules it replaces.

## Telemetry — the plan MUST be emitted for blunder-busting (Phase-1 requirement)

The pipeline already exists and is fully wired: `runtime.py:134` calls `telemetry.emit(decision)` per
decision → `to_record` (`src/common/telemetry.py`) serialises it to a `@T <json>` stderr line → the
grader captures it → every blunder Correction's `live_trace` **is** that record. The blunder-buster and
tuner already key off `live_trace.planned` (`tools/train/tuner/propose.py:106`, `tune.py:67`,
[[blunder-buster-planner-aware]]). So the develop rung plugs into the existing `emit()` — **no new
plumbing**, only new fields in `to_record` and a candidate-ranking carried on the `Decision`.

**A rollout that emits only its winning pick is un-debuggable** — a correction reader can't tell whether
the rung chose wrong or the *leaf value* mis-ranked. So it must emit the RANKING, not just the argmax.
Required `live_trace` shape on a develop-rollout decision (all fields SPARSE — absent when the rung is
off or didn't fire, so a non-develop record stays byte-identical to today):

```
"planned": {
    "step":  [i],
    "goal":  "develop",
    "why":   "<what this action sets up — the rationale that becomes the correction's cluster key>",
    "value": <leaf value of THIS plan's simmed end-of-turn board>,   # NEW: the number the pick turns on
    "ranked": "engine",                                              # it came from a real rollout
    "diverged": true|false                                          # differs from the greedy argmax
},
"plan_candidates": [                     # NEW sparse field: top-K (default 3), sorted by value desc.
    {"step":[i], "value":Va, "why":"…", "committed":true},          #   FREE to emit — the rung already
    {"step":[j], "value":Vb, "why":"…"},                            #   computed every candidate's leaf
    {"step":[g], "value":Vg, "greedy":true}                         #   to pick; just don't discard the
],                                                                  #   ranking. Flag the greedy pick.
```

Why each piece earns its place:
- **`planned.value`** — the leaf value is the whole basis of the pick; a correction that disagrees is
  really a claim about the *leaf*, and you can't see that without the number. (Today `planned` omits
  `value` entirely — add it.)
- **`plan_candidates` (top-3 with values)** — exactly the user's ask. Lets the analysis read "chose A
  (Va) over B (Vb), C (Vc)" and decide whether the rung mis-ranked or the leaf did. Emitting it is
  ~free: the rollout must value every candidate to pick the best, so this is keeping a sort it already
  did, not new sims.
- **`greedy` flag + `diverged`** — the scope is "augment where greedy is weak," so the single most
  important A/B signal is *when and by how much the rollout overrode greedy*. Flagging the greedy pick
  inside the candidate list (with its own rollout value Vg) makes every override measurable on the
  ladder: filter `diverged==true`, compare `value` vs the `greedy` candidate's `value`.

Mechanism: add a sparse `plan_candidates` field to `Decision` (populated by the develop rung, like
`objectives`/`game_plan`), add `value` to the `planned` block in `to_record`, and one round-trip test
(`emit`→`to_record`→parse) asserting: candidates present + sorted desc, the committed one flagged, the
greedy one flagged, and — when the rung is OFF — the record is byte-identical to today. Keep K
configurable (default 3); the value is a scalar so the wire cost is trivial.

Consumer follow-through (small, same phase): extend the blunder-buster's `planner_committed` read to
also surface `plan_candidates` in the inspector, so a `sequencing_error` correction lands next to the
plan it rejected and the alternatives it out-scored.

## Loose ends found in passing
- `match_planner_steer` and `forgo_ko` are `True` in `runtime.py` while their ADRs (0045) still say
  "default OFF" — a doc/code drift to reconcile.
- The multi-turn CRITICALs (`a21472`, `b4649`, and e.g. `85058574-109`'s full multi-turn KO plan) are a
  separate, harder problem (`docs/todo/deferred-multi-turn-criticals.md`).

Related: [[wroute-satisfied-not-fixed]] · [[tier-planner-t5-t6-fate]] · [[value-model-needs-nonmirror-gauntlet]] · [[match-planner-built]]
