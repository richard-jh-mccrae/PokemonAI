# ADR-0030: Winning this turn is an eager, engine-verified Lethal Solver (sound, shortest-line, execute-only)

**Status.** Accepted (grilled 2026-07-01, `/grill-with-docs`). **Superseded in layout by
[ADR-0037](0037-lethal-solver-is-the-turn-planners-top-rung.md) (2026-07-03): the Solver becomes the
Turn Planner's sound top rung — one entry point, one generator family; 0037 also closes this ADR's
two deferred TODOs (multi-step drive, strict execute-only) and the four-hook lethal collapse.** **Closed-form layer implemented
2026-07-01** (`/tdd`, TDD): the **Lethal Solver** (then `lethal.py` / `LethalMixin` composed into
the Pilot; **folded into the Turn Planner's `PlannerMixin` — [planner.py](../../src/common/strategy/planner.py) — by ADR-0037 stage 1, and both `lethal.py`/`LethalMixin` deleted**) — prize-out + empty-bench wins, attach / retreat / evolve
unlocks, shortest-first, with a **sound per-attack yield** check (`_attack_wins`, which caught and
fixed a real false-lethal: a snipe taking 1 of 2 needed prizes was locking). The three in-scope
CRITICALs (`040c`, `c1e0`, `fd5c`) are gated as regressions ([tests/strategy/test_lethal.py](../../tests/strategy/test_lethal.py),
`REQ-LETHAL-0001..0008`). The **Tier-1 Engine-Search backstop** primitive (`_engine_confirms_win`) is
shipped and proven to round-trip the native `search_begin` / `search_step` on a real observation and
read the engine's `result` ([tests/strategy/test_lethal_engine.py](../../tests/strategy/test_lethal_engine.py),
`REQ-LETHAL-0009`). **Wired 2026-07-02 (wiring pass): the backstop now guards DIRECT locks** behind
the `lethal_verify` kill-switch (`Strategy.params`, ADR-0021 pattern; **default ON** after the
arena A/B — 2000 games neutral, 0 crashes): before a 1-step direct KO locks, the engine confirms
it; a refute drops the candidate (never locks a phantom, counted in `Decision.lethal_refuted` → a
sparse `lethal_refuted` telemetry key), a `None` verdict (engine absent / unexpected coin) keeps
the sound closed-form lock, and the verdict rides on the line (`LethalLine.verified`, in the `@T`
`lethal.verified` key) — `REQ-LETHAL-0013/0014`. **The wiring pass also fixed the primitive
itself:** as originally shipped it read `result` straight after the line's steps, but a real
winning attack parks the search on MY cascade selects first (take the prize(s), pick a snipe
target) with `result` still −1 — measured live, EVERY genuine win read as a refute (its only
prior test proved the False path). `_engine_confirms_win` now drives MY OWN cascade selects
through the policy (under the `_planning` guard) to the engine's verdict, bails **None** on a
COIN_HEAD select (never choose the flip), and returns False only when the select passes to the
opponent unresolved; instrumented mirrors then showed 197/197 direct locks engine-CONFIRMED, 0
refutes. Scope note
the wiring made explicit: verify applies to direct locks ONLY — a 1-step engine sim of a
multi-step (`unlock`/`evolve`) line ends mid-turn with no `result` and would read as a false
refute, so those stay closed-form until the multi-step drive lands. This softens the original
"trivially-exact single-step KO needs no engine call" stance: the call costs ~a search_step
(≈0.1 ms, ADR-0031 phase 0) and buys the closed-form blind spots (abilities/status/timing), so
the fast-path exemption is retired behind the A/B'd switch. **Remaining follow-up:** driving a
full multi-step line to terminal *inside* the search (re-running the policy on each intermediate
`SearchState` — the Planner's `_simulate_line` is the machinery to reuse) and gating unlock/evolve
locks on it; and strict execute-only across the whole turn (a turn-scoped locked line). Extends
[ADR-0022](0022-gust-is-closed-form-lethal-lookahead.md) — it generalizes the gust closed-form lethal
into a whole-turn solver — and is the first concrete use of the **Tier-1 Search** seam named in
[ADR-0008](0008-pilot-is-a-layered-rules-pipeline.md). Terms in
[src/common/CONTEXT.md](../../src/common/CONTEXT.md): *Lethal*, *Lethal Line*, *Lethal Solver*,
*Engine Search*.

**Context.** "Take the win when it's there" is the single most-tagged theme in the correction corpus —
**48 of 192 corrections (25 %), 4 CRITICAL** — and the human tags demand it as a *hard rule*:
*"a hard rule that every single turn begins by analyzing"* (`a743…`), *"a complete scan"* (`519b…`),
*"always take that choice immediately"* (`9e53…`). Three of the four CRITICALs are a this-turn win the
agent threw away by developing first, and in each the pre-play *destroyed* the win: Wally's Compassion
stripped our own Energy so the KO no longer reached (`040c9b3ed145`, ep83037962); Boss's Orders dragged
up a benched mon we could no longer KO (`c1e0926abedb`, ep82751468); a retreat went into an unpowered
Cinderace instead of the powered Mega Starmie that had lethal (`fd5cdba0d5dc`, ep83007714). (The 4th
CRITICAL, `b4649ba9c304`, is *multi-turn* prize-math — "likely requires search" per its own tag — and
is out of scope here; see *Considered options*.)

The current agent detects lethality **emergently and piecemeal**: `_finish_turn_last` tiers a
game-winning KO first, and `_attach_lethal_tactical` / `_retreat_to_lethal_tactical` / the gust lethal
([pilot.py](../../src/common/pilot.py)) each score *one* single enabling action `KO_SCORE`-class.
There is **no `is_lethal()` and no place that computes the winning line** — so the structure cannot
express (a) a **multi-step** line (attach *and* retreat *then* KO — `077a…`; evolve Staryu→Mega *then*
attack — `a211…`), (b) **preserving** a win from a self-destructive but individually-positive play (the
three CRITICALs — the line-breaker out-scores nothing because nothing knows a line exists), or (c) the
**empty-bench** win (`_wins_now` checks only prize-out). Emergent lethality can also simply be out-voted
(a doomed-Active that wants to develop).

Engine facts established by reading `cg/api.py` + `cg/sim.py` (the [CLAUDE.md](../../CLAUDE.md)
verify-at-source rule):

- **The simulator exposes an agent-callable forward search** — `search_begin` / `search_step` /
  `search_end` / `search_release` ([api.py:517-639](../../src/cg/api.py)). `search_begin` forks an
  **independent** sim (`AgentStart()`, separate from the live `battle_ptr`) from the `search_begin_input`
  blob carried in *every* observation ([game.py:15](../../src/cg/game.py)) — the real game is untouched.
  `search_step` drives hypothetical selects exactly like `battle_select`; the returned `State.result` is
  the **win player index (−1 if unfinished)**. It is explicitly for agent use ("input the observation
  passed to your agent function exactly as is") and runs in-process, so it is available at grade time.
- **`manual_coin=True`** lets the searcher *choose* coin outcomes → a win can be demanded under the
  **worst** coin, making coin-flip / conditional-damage attacks soundly checkable.
- **The search needs *predicted* hidden zones** (my deck/prizes, the opponent's deck/hand/prizes/
  face-down Active). We cannot know them — so an engine verdict is trustworthy **only for outcomes
  invariant to those predictions.** A canonical this-turn lethal (attach known Energy → attack the
  opponent's *visible* Active for the last prize) draws nothing and gives the opponent no action, so the
  result is invariant → sound.
- **There is a per-match clock** (`obs.remainingOverageTime`; ≈10 min/match), so an unbounded per-turn
  search is not affordable.

**Decision.** Build a **Lethal Solver** — an eager, deck-agnostic Pilot routine that runs at the start of
every turn, *before* normal scoring.

- **Scope — this turn only.** A *guaranteed win on the current turn*. Multi-turn prize-math / tempo-denial
  (`b4649ba9c304`, `b57f…`) is split into a future **Prize-Race Planner** (fuzzy, opponent-modelled,
  non-committal — the wrong home for a lock).
- **Backward-chaining candidate generation (closed-form, Tier-0).** Enumerate every attack that would
  win — attacker × attack that KOs the Active for ≥ my remaining prizes (counting multi-prize ex via
  `_prize_value` + snipe prizes), or that leaves the opponent with **no Pokémon in play** (empty-bench).
  Regress each to its preconditions (Active? retreat? enough Energy? attach / accel? evolved? evo-piece
  in hand? right target? gust?); keep only lines reachable this turn from **known** resources with **no
  draw**. Generate **shortest-first** ("take exactly those decisions").
- **Hybrid-escalation confirmation.** A trivially-exact single-step KO is closed-form-confirmed (no
  engine call). Every other candidate is confirmed by **Engine Search** — step the line, coins forced
  worst-case, lock **only** when `result == my_index`. The engine also resolves what closed-form is blind
  to (abilities that cancel damage, status, Tera bench-immunity, evolution / turn-1 timing) and the
  **simultaneous-draw** rule for free (a draw is not reported as our win, so it never locks — this
  subsumes the `_is_simultaneous_draw` guard for locking).
- **Sound by construction.** Lock only a win **invariant to hidden predictions**; never on an unknown
  draw or an unforced coin. Invariant: **no false Lethal, ever** — completeness yields to soundness (a
  miss costs one turn; a phantom loses the game).
- **Strict execute-only.** Lock the shortest confirmed line as **turn-scoped** state; execute exactly its
  steps, in order, across the many per-decision calls; **veto** every option outside the line that turn
  (this is what kills the three CRITICALs). Overrides develop-first **only** on confirmed-win turns;
  normal turns keep [attack-last develop-first](0022-gust-is-closed-form-lethal-lookahead.md) untouched.
- **Layered, not a rewrite.** The Solver runs first and **owns** the turn when it locks; when it finds
  nothing, the existing green closed-form hooks give today's behavior unchanged. The four hooks collapse
  into the Solver as a later cleanup, once it is proven.
- **Failure → fall back, never commit-degraded.** Any search error, budget-timeout, or unconfirmed
  candidate → don't lock, defer to normal scoring.

**Considered options.**

- **Extend the emergent scoring** (more hooks / weights) — rejected: no single place *knows* a win
  exists, so multi-step lines and win-*preservation* stay structurally impossible and grow as an endless
  pile of per-card patches. The three CRITICALs are exactly preservation failures.
- **Closed-form only, no engine at runtime** — rejected: closed-form is blind to abilities / status /
  Tera / timing and is not the grading authority, so a "win" it asserts can be wrong; the human
  explicitly asked to *verify with the engine before carrying out the decisions*. (The engine remains the
  *test* oracle regardless of this choice.)
- **Engine-verify every candidate, including trivial KOs** — rejected as the default: pays a search
  against the clock for cases closed-form already proves exactly; retained only as a fallback if the
  fast-path proves fragile.
- **Include high-confidence probabilistic lethal** (commit on a likely draw) — rejected: re-introduces
  the catastrophic failure mode (commit the hand, whiff, lose) that motivated an *eager* solver;
  probabilistic reads stay a *soft bias* in normal scoring
  ([ADR-0029](0029-own-deck-content-is-sound-oracle-plus-probabilistic-estimate.md)), never a lock.
- **Subsume / refactor the four hooks now** — rejected for v1: a big-bang refactor of green,
  boundary-condition-laden code on a live submission; layer first, unify once proven.
- **Own multi-turn prize-math too** — rejected / deferred: it needs opponent-response search, is
  inherently fuzzy, and must *not* be locked-and-committed; it is a separate Prize-Race Planner (the 4th
  CRITICAL `b4649ba9c304`).

**Telemetry.** The Solver's verdict — the locked `step`, its `kind` (`direct` / `unlock` / `evolve`),
and the `rationale`, or `null` when no win was locked — rides in the per-decision **Decision Telemetry**
(`@T` stderr line, [ADR-0019](0019-submissions-are-traceable-and-tracked.md)) via the shared
`common.telemetry.to_record`. Because that one serializer feeds the live line, a blunder Correction's
`live_trace`, **and** the tuner's retest ([retest.py](../../tools/train/tuner/retest.py)), a correction
on a lethal decision carries the solver's data for analysis without extra plumbing — the field is always
present so corrections can filter on it (`REQ-LETHAL-0011`).

**Consequences.** The Pilot gains an eager, first-class **Lethal Solver** and its first use of **Tier-1
Engine Search**; the Tactical Evaluator's closed-form KO math is repurposed as the Solver's candidate
generator. The Pilot gains **turn-scoped committed-plan state** (a locked Lethal Line) beside its
existing match-scoped Scout / deck-tracker state — a new invalidation surface (cleared at turn end / on
any board divergence). Latency is bounded by the closed-form pre-filter + a candidate cap + a
`remainingOverageTime` guard, accepting **incompleteness under the clock** (a findable win may be missed
— sound, never wrong). A false-Lethal is the one catastrophic direction, so the test suite weights the
**negatives** heavily (don't-lock on unknown-draw / worst-coin-insufficient / draw-result; veto
Wally's / gust / shuffle line-breakers). Proof: TDD every win-shape + negative; the **three in-scope
CRITICALs** (`040c…`, `c1e0…`, `fd5c…`) a hard blocking gate; all 48 win-this-turn corrections replayed
through the real Pilot (fixed / covered / refuted); engine paths tested live in CI (the DLL / `.so` run
offline on Windows + Linux); REQ-LETHAL-#### traceability; ≥80 % coverage on the Solver. The design is
captured here; the build (generator, engine-driver, lock / execute / veto, turn-state, tests, docs) is
the follow-up task list.
