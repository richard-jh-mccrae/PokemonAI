# ADR-0068: The StateModel is a lazy, pure snapshot; reuse is by side, never by patch

**Status.** Accepted (grilled 2026-07-24, `/grill-with-docs` on issue #138 — seven locked
decisions, one per agenda item). Build: #138 (Phase 0b of the Value System, tracker #136).
Companion vocabulary: **StateModel · SideState · Carried State · Count Triple · Leaf Profile**
in the Agent Runtime [`CONTEXT.md`](../../src/common/CONTEXT.md); the self-side affordability
family this model holds is ADR-0067/#137 (0a); the opponent-side twin is ADR-0064.

## Context

Every value read today re-derives its own slice of the board at its own fidelity: three
attack-payability approximations, doom vs threat-clock re-expressions, four hand-rolled
`Counter(deck) − visible` sites, and a 129-field `Board` dataclass assembled eagerly per
`decide()` (`pilot._board`, one bespoke helper per field). #138's charter: ONE enriched
two-sided snapshot every equation READS, with a HARD requirement of incremental evaluation —
the planner leaf is the heaviest future consumer (`develop_rollout` forks every menu option;
#145's `state_value` differencing and #150's K≈16–24 belief samples multiply leaf count; the
grader is 2 vCPUs × ~10 min/match).

Facts that shaped the rulings (verified 2026-07-24):

- **No leaf builds a `Board` today.** `_board()` has two callers: once per real `decide()`
  (`pilot.py:1330`) and `_board_hypothetical` — whose only consumer is the armed-OFF Tier-5
  value model. The leaf's live terms (`_readiness`, `_incoming_worst`, `_predicted_loss`) are
  one-sided and cheap. The 2-vCPU pressure is the cost #145 will ADD, not one the leaf pays now.
- **The engine hands leaves a complete end-of-turn obs** (`_simulate_line`). A Python
  `apply(action)` delta path would re-predict what the native engine already computed — a second
  rules engine, with ADR-0059's trace-verification bill as the measured price of keeping one honest.
- **The my-side dependency graph is all-or-nothing under its commonest action** (0a build note):
  Budgets are per-body; ONE manual attach flips `energy_attached`, changes a body's attached
  Energy, and may spend the Supporter quota — invalidating every cached Budget at once. A
  fine-grained delta would bookkeep per-field invalidation and then invalidate everything anyway.
- **Two derivations already carry cross-decision memory as a side effect**: the phase hysteresis
  (`_phase_prev`, `objectives._derive_phase`) and Prize-Path stickiness (`_my_path_prev`,
  `_sticky_path`) MUTATE Pilot state during `_board`, defended by hand-written snapshot/restore
  at two planner sites (`planner.py:3050`, `:3473`). #138's "known_top is the ONE exception to
  pure per-obs derivation" undercounted — there were already two.
- **The engine already delivers per-select events**: `Observation.logs` — "events since the last
  selection" — including `SHUFFLE`, `DRAW` (id + serial), and area moves (`api.py:441`, `:189`).
- **0a shipped the sound typed type-set gate** (`Pilot._basic_energy_types_in_deck`,
  not-provably-empty, ADR-0067); what 0b owes is per-type COUNTS — the epistemically harder half.

## Decision

### 1. Lazy field graph + measured Leaf Profile; `apply(action)` is REJECTED for v1

`StateModel.build(obs, stats, functions, read)` returns immediately; every derived field is a
memoized lazy property, so a consumer pays exactly for what it reads and an unread field costs
zero. The memo graph IS the field dependency graph #138 demands (a field can only read fields
below it). The incremental-eval hard requirement is satisfied by the **cheap-leaf-profile**
branch of #138's own either/or: the Leaf Profile — the field subset a leaf evaluation touches —
is measured on Linux, reported **per side**, and **CI-pinned as a field-SET snapshot** (never
wall-clock — timing asserts are flaky across the two CI OSes): a leaf that starts reading a new
field fails the pin and forces a deliberate re-measure. Laziness is also what makes "maximal
model, nothing speculative" compatible: an offered-but-unread field is free, so the field list
is set by consumers, not by build cost. `apply(action)` make/unmake is rejected on three legs:
the engine already supplies post-action obs at leaves; the my-side graph invalidates wholesale
under an attach anyway; and its failure mode (silent drift from engine semantics) corrupts every
downstream equation invisibly, where lazy-rebuild's failure mode (a slow leaf) is measurable and
benign. #149's virtual known-top application remains the one admitted narrow exception — one
belief field, never a general action applier.

### 2. One PURE StateModel per `decide()`; reuse is by SIDE, guarded by a wholesale fingerprint

Built fresh at the top of every `decide()` (replacing `_board()`'s slot); an executed action
arrives as the next obs, so mid-turn invalidation does not exist as a concept. The model is
pure — same obs in, same answer out, writes nothing. The two hysteresis memories move OUT into
the declared **Carried State** channel (below), and both planner snapshot/restore dances are
deleted rather than copied a third time. The one cross-select cache is the **opponent
`SideState`** (they cannot act during my turn), guarded by a wholesale fingerprint —
`hash(their entire PlayerState) + stadium + transient-grant generation` — NEVER a hand-picked
field list: `PlayerState` is a closed 13-field record, so hashing all of it catches Judge
(handCount/deckCount), a gust (active/bench identity), a Hammer (attached energy), Adrena-Brain
(damage), and the next disruption card nobody thought of; enumeration fails OPEN silently, the
one direction this codebase never accepts. Over-hashing costs a spurious rebuild (slower, still
correct); under-hashing serves a stale opponent into every equation. The SAME fingerprint guards
planner-leaf side-sharing (a leaf inside my turn reuses the opponent SideState; a leaf whose
line touched their side — gust, Judge, damage transfer — misses and rebuilds), and #150's
K sampled worlds reuse MY SideState symmetrically. A my-side cross-select cache is explicitly
NOT built (decision-1's invalidation fact makes it near-worthless).

### 3. `Board` becomes an eager adapter ASSEMBLED FROM the model; migration is field-by-field

`Board` keeps its dataclass shape and all names (the doctrine's `when=` lambdas, telemetry, and
`features_from_board`'s 17 pinned feature names stay untouched); its kwargs progressively become
reads off the StateModel. A field migrates only when **(i)** a Phase-1 consumer needs the
model's version anyway, and **(ii)** the model's derivation is verified EQUAL to the old
helper's output on the existing fixtures — richer-but-dearer derivations do not migrate in 0b
(the phase is ZERO behavior change). New consumers from 1a on read the model directly. The
129-property lazy facade and all deletions are deferred: deletions to 1d (0a's ratified
supersession path), the facade question to Phase 2. The ~100 bespoke doctrine flags are NOT
StateModel fields in v1 — the model is substrate for value equations, not a new home for every
Board boolean.

### 4. Homes by epistemic nature; typed deck counts are a Count Triple that collapses at anchor

A fact lives at the layer whose lifetime matches it: per-body prize yield stays on `CombatMath`
(card knowledge, ADR-0052); per-side `prizes_remaining` on each SideState; the cross-side race
composite (prize map, prizes-to-win, `race_ahead`) is ONE top-level StateModel derivation the
scattered win-with-this-KO snippets migrate onto. `mine.unseen_counts` (one lazy
`Counter(deck) − visible`) absorbs the four duplicate sites. Typed deck counts live on MY
SideState as `deck_energy_counts`, a **Count Triple** — floor (pigeonhole-sound, safe for `>=`),
expected (hypergeometric prize split, EV only), ceiling (fail-open; 0a's type-set gate is
`ceiling > 0`) — whose legs diverge pre-anchor and collapse to the exact integer once the first
deck-revealing search anchors the prizes (`deck_known_counts` regime): one interface, two
regimes, no consumer branching, and naming the leg you read makes ADR-0067's
estimate-into-sound-math contamination ungrammatical. The 0a Pilot gate stays put until 1d;
the model field delegates.

### 5. The v1 field inventory is exactly the 1a–1e consumption union

Mine: bodies (typed attached Energy, typed per-slot costs, HP/damage, forward line),
`attach_budget` + per-body `reachable_attach`/`readiness_p` (0a's family — the model HOLDS
results, `CombatMath` computes them), hand cards + Needs coverage, `unseen_counts` +
`deck_energy_types`/`deck_energy_counts`, `prizes_remaining`, typed discard counts. Theirs:
bodies, the clock family (`incoming(t)`, `reachable_incoming`, `turns_to_afford`,
`turns_to_ko_me`, `active_doomed`/`doomed_incoming`), `discard_recur_fuel` + typed discard,
hand size, the Read/Brief/`matchup_plan`/γ/favorability cluster, `prizes_remaining`. Top-level:
the race composite, turn/quota facts, the opponent fingerprint. Additions arrive at the phase
that consumes them (laziness makes additions free to everyone else); 1b (evolve) is the least
pre-scoped and is expected to add ability-income fields at its own grill.

### 6. Opponent hand inference in v1 is size + the ADR-0047 facade — nothing new

`theirs.hand` exposes `size` (obs-exact) and the Opponent Model facade handle; the
strip-exposure class of read stays deck-odds over the matched Read's rep build
(`opp_hand_strip_odds` pattern). Event-derived hand knowledge (refresh draws, revealed fetches)
is REJECTED for v1: it is new Carried State with an invalidation table and no 1a–1e consumer.
Probabilistic hand modeling waits for its own phase and attaches behind the same named seam.

### 7. Carried State is one declared channel; `known_top` is architected-to-admit, built by #149

A channel member is `(name, value, update(prev_value, obs) -> new_value)`, updated once per
`decide()` at the top — BEFORE `StateModel.build` — reading `obs.logs` for events since the
last select; the update RETURNS, the Pilot stores (no derivation mutates state as a side
effect). v1 members: `_phase_prev` and `_my_path_prev`, their update functions being today's
logic relocated. The StateModel reads a frozen snapshot of the channel as a build input and
never writes it. #149 adds `known_top` as a third member whose update watches
`SHUFFLE`/`DRAW`/deck-area moves on MY deck and fails CLOSED to None (consumers fall back to
the hypergeometric-unknown) on any unrecognized event touching the deck — but the belief itself
builds in #149, AFTER its gating fork-order verification, with its card-by-card invalidation
table ruled at that grill. No generic event-subscription framework (zero v1 users).

## Consequences

- **0b delivers:** `src/common/state_model.py` (StateModel/SideState, lazy memo graph), the
  Carried State channel + the relocation of both hysteresis memories (both planner
  snapshot/restore sites deleted), the opponent-SideState fingerprint cache, the race-composite
  and deck-count fields, `Board` assembled from the model with the criteria-(i)/(ii) migrations,
  the Leaf Profile measurement + CI field-set pin, and the 1a integration test (`_attach_value`
  inputs off the model). ZERO behavior change; suite green both OS.
- **Profiling is reported per side** (my Needs/budget cluster vs their clock/read cluster) —
  the split that keeps the side-sharing rationale falsifiable — with the leaf path measured
  separately from the per-decision build (#145/#150 size against these numbers).
- **The fingerprint cache's honest hit profile:** it misses on every play that touches their
  side (gust, Judge, damage transfer, denial) and hits on the majority that don't (attach,
  evolve, bench, search, draw, retreat). Correctness never depends on the hit rate.
- **Deferred:** the 129-property facade + Board deletions (Phase 2 / 1d); `known_top` (#149);
  probabilistic opponent-hand modeling (its own phase); any my-side cross-select cache
  (rejected on the invalidation fact, revisit only with profiling evidence).
- Standing #136 directives apply: no shadows, TDD, corpus re-ruled never auto-conformed,
  paired A/B before any decider swap merges (0b swaps no decider).
