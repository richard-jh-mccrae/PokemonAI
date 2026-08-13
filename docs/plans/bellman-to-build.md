# Bellman build specification

Status: implemented and verified 2026-08-13.

## 1. Extract a clean, shared needs model — implemented

### Purpose

Give Bellman one deck-neutral representation of what the real board needs and which known cards can
satisfy each need. `src/common/refresh.py` currently owns a private immediate-needs representation;
the legacy top-level `needs.py` is reference material only and must never be moved into production
unchanged.

### Design

- Create `src/common/needs.py` with immutable need, coverage-edge, and resolved-assignment records.
- Move generic immediate-need discovery and maximum non-duplicated card-to-need assignment out of
  `refresh.py`.
- Derive demand only from observable board state, turn budgets, card stats/effects/functions, and
  deck-local declarations such as evolution lines and prize routes.
- Let direct cards and generic fetch effects cover needs. One card may satisfy at most one need in a
  chosen assignment unless its printed effect explicitly supplies multiple independent resources.
- Express all tunable values as descriptive module-level constants or existing value families.
- Keep probability calculations and the commit/decline decision in `refresh.py`; `needs.py` describes
  demand and coverage, not action policy.

### Migration rule

Use the top-level `needs.py` only as conceptual and test inspiration. Do not copy its deleted
`common.deciders` dependencies, bespoke gates, named-card assumptions, tuned legacy equations, or
hypothetical-grab logic. Remove the top-level file after every retained concept has an equivalent
test or has been deliberately rejected.

### Acceptance

- Existing immediate evolution, Energy, setup-body, direct-out, and fetch-out refresh tests pass.
- No card identity or deck-specific rule appears under `src/common/`.
- No hypothetical hand, draw order, or post-redraw continuation is constructed.
- Submission packaging includes the clean module and excludes the legacy file.

## 2. Add deterministic next-turn retained-hand needs — implemented

### Purpose

Price known cards that cannot be used now but will become usable and important next turn. Examples
include an evolution card held for a pre-evolution that entered play this turn, or an enabling
Supporter plus the evolution card it makes usable next turn.

### Design

- Derive next-turn eligibility from the real board and deterministic rule clocks: evolution age,
  reset turn budgets, declared evolution lines, printed card functions/effects, and prize routes.
- Create next-turn need slots and coverage edges for known cards already in hand.
- Value matched combinations jointly when every member is required; do not merely add unrelated
  static card Worth. A card cannot simultaneously fund two incompatible combinations.
- Discount next-turn value with one documented, descriptive factor in the common value currency.
- Add the resolved retained-option value to the cost of shuffling the known hand away.
- Recompute from the actual observation on every callback; never predict unknown card identities.

### Refresh comparison

The refresh decision remains expected benefit minus opportunity cost:

```text
exact hypergeometric value of immediate needs
+ deterministic printed refresh effects
- immediate and next-turn known-hand option value
```

There is no fixed probability threshold. The break-even probability remains a consequence of the
need value and the hand value at risk.

### Prohibited

- No sampled or representative future hands.
- No hypothetical shuffle, draw, or post-draw planning.
- No named-card or deck-specific common code.
- No rules ladder that directly instructs the pilot to keep, play, or shuffle a card.

### Acceptance

- An evolution card that becomes legal next turn has more retain value than an unrelated card with
  otherwise equal static Worth.
- A required Supporter/evolution combination receives joint value without double-counting either
  card.
- If the enabling board body is removed or the combination is already redundant, that joint value
  disappears.
- Immediate useful non-Supporters remain preferable before refresh when their real transition value
  warrants it.
- The same inputs always produce the same needs graph and value; no RNG or engine stepping occurs.
- Native bundle, Bellman, correction, and submission-boundary tests pass.

## 3. Final five-match parallel mirror validation — implemented and passed

### Purpose

Finish the build with a production-representative latency and stability gate using the exact native
submission bundle.

### Design

- Launch five independent mirror matches concurrently, with the candidate bundle controlling both
  seats in every match.
- Use isolated temporary extraction directories and native `cg` sessions for each match.
- Apply the normal 600-second timeout independently to each match rather than to the batch.
- Preserve each match result, failure reason, decision count, and elapsed wall-clock duration.
- After all workers finish, print every match duration followed by aggregate total, minimum,
  maximum, and arithmetic-average match time.
- Bound worker count to five and terminate/close every native session cleanly after success, failure,
  or timeout.

### Required output

```text
match 1: <status> <seconds>s
match 2: <status> <seconds>s
match 3: <status> <seconds>s
match 4: <status> <seconds>s
match 5: <status> <seconds>s
total: <seconds>s
min: <seconds>s
max: <seconds>s
avg: <seconds>s
```

`total` is the sum of the five individual match durations, not parallel batch wall time. The runner
should also print batch wall time separately so concurrency efficiency remains visible.

### Acceptance

- Exactly five matches start and each reports a terminal status.
- All five use the exact built artifact and native engine; no `cgpy` import or fallback is allowed.
- One match timing out or crashing does not suppress the other four results or aggregate report.
- Exit status is successful only when all five mirror matches pass.
- Tests cover aggregation, partial failure, timeout reporting, worker cleanup, and artifact identity.

### Final live result

Exact artifact: `mega_starmie_20260813_2461bb65-dirty.zip`
SHA-256: `d23e1a64f9406ad4cc54ac3a3062789b37a63f8e66c408120d9477e57d357448`

```text
match 1: PASSED 78.375s
match 2: PASSED 5.078s
match 3: PASSED 21.656s
match 4: PASSED 47.406s
match 5: PASSED 110.500s
total: 263.015s
min: 5.078s
max: 110.500s
avg: 52.603s
batch wall: 111.063s
```

All five matches used native `cg`, isolated extraction directories, and the exact SHA-identical
artifact. Callback average/minimum/maximum were 0.901/0.000/13.718 seconds.
