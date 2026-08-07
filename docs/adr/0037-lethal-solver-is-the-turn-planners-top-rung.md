# ADR-0037: The Lethal Solver is the Turn Planner's sound top rung (one entry point, one generator family, verified locks replay)

**Status.** Accepted (grilled 2026-07-03, `/grill-with-docs`). **Built 2026-07-03 (`/tdd`), all three
stages, each gated as designed:** **Stage 1** (structural join — `plan_turn` the one entry,
`LethalMixin`/`LethalLine` deleted, `TurnLine(goal="win", kind, verified)`, telemetry split-by-goal)
proven byte-identical by the Score-Diff Gate in strict **scores** mode (206 corpus frames, 0
divergent) with the full suite green. **Stage 2** (`lethal_family` — the one generator family:
direct + attach + retreat + evolve + gust + energy-tutor, single+multi-develop, all `bound="min"`;
the tutor gated on `deck_definitely_has`; verify widened to every family lock, cascade cap 40;
turn-1 develop guard) gated by REQ-LETHAL-0015..0023 (incl. CRITICAL-shape parity + a live engine
smoke) and a 2000-game arena A/B — **51% (CI 49-54%), 0 crashes → default ON**. **Stage 3**
(`lethal_veto` — a verified lock materialises its confirmed cascade `{ctx, max, drive, chosen}` with
identity tuples `(type, attackId, cardId, inPlayArea, inPlayIndex, playerIndex)`; replay
identity-matches the live menu, policy-drives all-PRIZE `drive` entries, expires with the turn;
mismatch → lock cleared + sparse `lethal_lost` + re-derivation) gated by REQ-LETHAL-0024..0029 and a
2000-game A/B — **52% (CI 49-54%), 0 crashes → default ON**. Full suite 1113 green. One scope note
vs the design: veto recording rides only the family path (`lethal_family` presumed by `lethal_veto`),
and `Decision.lethal_lost` is a new sparse wire key (additive, no reader breakage). Design record
follows. Supersedes the split-system layout of
[ADR-0030](0030-winning-this-turn-is-an-eager-engine-verified-lethal-solver.md) /
[ADR-0031](0031-turn-planner-is-goal-directed-engine-simulated-tier1-search.md) and closes both of
ADR-0030's deferred TODOs (multi-step drive; strict execute-only) plus its deferred four-hook lethal
collapse. Terms updated in [src/common/CONTEXT.md](../../src/common/CONTEXT.md): *Lethal Solver* (now
the rung), *Lethal Line* (materialised replay), *Turn Planner* (the one entry point).

**Context.** ADR-0031 already *declared* "the Lethal Solver is the win-goal special case and the sound
top rung of the Planner" — but the code never caught up: two sibling mixins, two sequential entry
points in `_evaluate`, two Decision fields, two engine primitives with opposite coin regimes
(`_engine_confirms_win`: worst-coin verdict-driver, sound; `_simulate_line`: auto-coin board-ranker,
heuristic). The split causes a real capability gap: a win needing **two develops** (retreat AND attach
— the 7f48 shape, but game-winning) is invisible to `find_lethal_line` (its unlock rung only reads the
single-step KO_SCORE hook traces), so it falls through to the Planner, which commits it merely as a
*heuristic* line — no lock, no worst-coin check, no verify. Conversely gust wins are never locked at
all (a PLAY option; the unlock rung matches ATTACH/RETREAT only), and the hook-trace rungs inherit the
hooks' own vetoes — a suppressed hook score can hide a real win. Meanwhile the verify machinery
already generalises: the wiring-pass `_engine_confirms_win` drives MY cascade selects through the
policy to the engine's verdict — the exact "multi-step drive" ADR-0030 deferred.

**Decision.** Join the two systems: **the Turn Planner is the Pilot's one planning entry point, and
the Lethal Solver is its sound top rung.** Six sub-decisions, each a resolved trade-off:

1. **One module, one entry.** `planner.py` absorbs `lethal.py`; `LethalMixin` and `find_lethal_line`
   die; `plan_turn` runs the ladder: **win rung → stabilize-then-KO → layer-on-top gate → heuristic
   rungs**. The win rung preempts everything (no scalar competition — the hard-rung invariant is
   positional, not numeric). The mid-sim path (`_planning`) keeps the closed-form win rung, no verify,
   no cache — a sim's policy replay must still take wins.
2. **Unified type, preserved wire format.** `LethalLine` is deleted; `TurnLine` gains `kind` and
   `verified`, and the win rung emits `goal="win"`. The telemetry **wire format does not change**:
   `to_record` splits by goal — a win line serialises under the `lethal` key
   (`{step, kind, why, verified}`), everything else under `planned`; `lethal_refuted` unchanged. So
   tune.py `[LETHAL]`/`[PLANNED]`, propose.py, retest.py before/after lifts, and every historical
   correction's `live_trace` keep working unmodified; only telemetry.py, the blunder-shell hint text
   ("fix = planner.py — win rung vs heuristic rungs"), and the blunder-buster skill docs change.
3. **One generator family** (stage 2): direct-KO + attach + retreat + evolve + energy-tutor + **gust**
   win shapes, covering single- AND multi-develop lines in one place. Every candidate is re-proved
   sound closed-form (`bound="min"` damage floors, worst-case coins, exact prize math / empty-bench)
   — the Planner's heuristic generators are NOT min-bound, so the win test is its own pass. The
   hook-trace rungs are deleted; the four legacy hooks (`_finish_turn_last` win tier, attach-lethal,
   retreat-lethal, gust-lethal) are demoted to pure Tactical scorers for the tuned path. This closes
   the two-develop-win gap and finishes the four-hook lethal collapse ADR-0030 deferred.
4. **Verify policy: refute drops, None locks.** `lethal_verify` widens from direct-only to **every
   family lock, any line length** — the cascade drive re-runs the policy on each intermediate state to
   the engine's own verdict (cap raised from 12 to ~40 steps, the `_simulate_line` scale). False =
   drop the candidate (+`lethal_refuted`); None (coin bail / engine absent / cap) = keep the
   min-bound closed-form lock. Rationale: a coin-attack win can NEVER verify True (the driver bails on
   COIN_HEAD by design), yet the min-bound floor already proved it under the worst flip — requiring
   True would drop sound wins forever. Step legality is not a closed-form blind spot (an option on the
   menu IS engine-vetted); verify buys the ability/status/timing blind spots whenever it can speak.
5. **Stage-3 veto: materialised replay + fallback.** A **verified** lock records the confirmed
   cascade's steps with per-select signatures and replays them for the rest of the turn:
   **id-matched** where identity matters (deck-fetch picks, gust/snipe targets — the seam re-derivation
   is weakest at, e.g. a fetch grabbing something other than the Energy the line needs),
   **policy-driven** where outcome-invariant (prize takes). Any signature mismatch or lost-sight →
   fall back to re-derivation + a sparse `lethal_lost` telemetry key — never strand, never blind-index.
   Unverified (None) locks have no confirmed cascade, so they keep per-decision re-derivation.
6. **Staircase.** Stage 1 (structural join + type unification + wire shim) lands **unswitched**,
   proven byte-identical by the Score-Diff Gate (choice mode over the correction corpus + films).
   Stage 2 (`lethal_family`) and stage 3 (`lethal_veto`) land kill-switched OFF (ADR-0021 pattern) →
   arena A/B (0 crashes, winrate neutral-or-better, divergence telemetry: lock rate vs old, verified
   True/None ratio, refute rate, `lethal_lost`) → default ON per-agent → the old paths deleted.
   `planner_engine_rank` / `planner_key_threat` are untouched (heuristic rungs unchanged).

**Considered options.**

- **Keep two Decision fields / two entry points** (provenance first-class in the types) — rejected:
  the wire shim preserves the provenance where tooling reads it; in-process, the goal string carries
  it. Two entry points is exactly the drift that opened the two-develop-win gap.
- **Unify the wire format too** (one `planned` key, `lethal` derived by readers) — rejected: touches
  four tools + the blunder-buster skill and breaks historical `live_trace` comparability in retest,
  for zero runtime win.
- **Add the family beside the hook-trace rungs** (smallest delta) — rejected: leaves gust unlocked,
  keeps two lethal-detection paths alive, and inherits hook vetoes into win detection.
- **Require verified=True for multi-develop locks** (ADR-0030's original stance) — rejected: drops
  sound coin-floor wins forever and loses all multi-step locks wherever the engine is absent; the
  min-bound floor is itself the soundness authority, the engine the blind-spot catcher.
- **Soft veto (assertion-only) / MAIN-only replay** — rejected: the fetch-pick seam is the one place
  re-derivation is genuinely weak, and it lives on non-MAIN selects; an assertion catches nothing it
  can act on. The fallback design removes the stranding risk that motivated softness.
- **Collapse the hooks' Tactical-scoring role too** — out of scope: the tuned path still needs their
  scores; only their *lethal-detection* role moves.

**Consequences.** One planning system; the glossary's "subsumes" becomes literal. The plan-cache now
covers the win rung: verify runs once per board fingerprint instead of once per decision (cheaper),
and `lethal_refuted` becomes per-plan rather than per-decision — a telemetry-note, not a schema
change. Single-step retreat/attach wins move from hook-scored tuned picks to verified locks — hook
vetoes can no longer hide a win, and every win lock gains the verify + (stage 3) replay benefits.
Blast radius is tight: `lethal.py` imports live only in pilot.py, planner.py, and the two lethal test
files; test_lethal.py / test_lethal_engine.py survive re-pointed at planner (REQ-LETHAL-#### ids
preserved), and the six CRITICAL regressions (`040c`/`c1e0`/`fd5c`, `7f48`/`0cbc`/`4298`) are the
blocking gate for every stage. Multi-turn planning stays out (`a21472`, `b4649` —
a since-deleted deferred-criticals note).
