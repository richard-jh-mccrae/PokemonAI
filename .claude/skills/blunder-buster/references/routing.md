# Routing a correction — the leaf's rulebook

Each fan-out leaf follows this to route **one** correction: read the **scope**, then the **live
trace**; draft the `spec` against **live source, never memory**. Output the leaf return contract
(SKILL.md). A leaf that cannot confidently reach a terminal outcome returns `outcome: uncertain` with
a `question` — it does not guess.

## Scope first (ADR-0049 / ADR-0019)

Every record carries `scope` (`decision` | `turn` | `match`), `subject`, and a scope-aware `key`. Scope
is a **strong routing prior — never an auto-route** (routing is this skill's value; don't let `tune.py`
do it):

- **`scope: turn`** — a whole ply was misplayed. Prima facie **`target_layer: turn-sequencer`** (the
  Composer's sequence search and `plan_turn` hand-off), `verification_contract: composer-retest` — the
  gate is `retest_span`, which re-drives the Span to its **first divergence**. A null `planned` verdict
  does not re-open rule authoring: it is a `composer-differencer` coverage/transition investigation.
  *A `turn_plan` note adds the human's ideal line as evidence for this prior; it no longer selects a
  different rulebook (below).*
- **`scope: match`** — a whole game was misplayed. Read the Span's per-turn `game_plan` (ADR-0045). Wrong
  mode/goal → **`turn-sequencer`** (`plan_match`/sequence hand-off); wrong opponent read → **`matchup-brief`**; a line that
  needs cross-turn search → **capability-gap**. `verification_contract: seed-ladder` either way (a match
  Correction embeds no `obs` and is never re-driven).
- A scoped record's `seed_weight` is `0` and its `attribution` (when present) is *information only* — it
  never reached the weight fit. **Never author a `when()`/weight for a scoped blunder.**
- **Cluster across scopes when the fix is one fix.** A turn Correction and the decision Corrections inside
  that turn often describe the same planner bug; the join merges them, provenance lists all. A leaf that
  suspects this sets `sibling_hint` (below).

## Then the live trace

Each Correction embeds `live_trace` — the `@T` telemetry the shipped agent emitted
(`opts[].score/tac/fired`, `chosen`, `margin`, `lethal`, `planned`, `posture`). For a **decision-scope**
blunder this read **determines `target_layer` + `verification_contract`**:

- **Reorder markers first** (when `chosen` isn't top-`score`): `reordered`+`deferred` (attack-last
  resequencer — a *sequencing* decision, `turn-sequencer`, not an under-weighted attack), `needy`
  (equal-score attach tie-break), `grabbed` (multi-pick set). Don't author a rule to "fix" a by-design
  reorder.
- **`live_trace.lethal` (ADR-0030)** — the Lethal Solver short-circuits scoring → a lethal-shaped blunder
  is **`lethal-solver`**, never a weight/`when()`. `null`-but-a-win-existed → the generator missed a
  win-shape; non-null-but-rejected → it over-fired.
- **`live_trace.planned` (ADR-0031)** — the Turn Planner short-circuits → a this-turn multi-step-line
  blunder is **`turn-sequencer`**. If the better line spans **>1 of my turns** → **capability-gap** (don't
  bolt multi-turn onto the closed-form Planner — ADR-0040).
- **`live_trace.posture` (ADR-0041)** — a `posture_mismatch` (or a member sharing one
  `believed_archetype` with others) is a **matchup-doctrine** miss → **`matchup-brief`**, never a
  deck-agnostic `when()`. Right-read-wrong-counterplay → a Brief data/lever change. No Brief covers it →
  route to `/matchup-genie <slug>` (a named hand-off). Wrong *Read* (γ low) → a recognition gap →
  **capability-gap**.
- **Otherwise** (no layer flag) → **`composer-differencer`**, `verification_contract: composer-retest`.
  Read `live_trace.composer.root.terms`, `differencing`, `ranked`, and `candidates`: missing/refused
  transition, pruned first step, or wrong continuation/order belongs to the Composer/differencer. Route
  to **`value-equation`** only if those complete traces show the competing transitions are covered and
  the correction depends on a specific `state_value` family producing the wrong ordering. The spec must
  name that family and the before/after terms; otherwise it is not an equation proposal.

`tune.py` tags lines `[TURN <n>]`/`[MATCH]`/`[LETHAL]`/`[PLANNED]`/`[POSTURE≠ <arch>]`; the snapshot
carries `scope`+`subject`+`key` and `lethal_locked`/`planner_committed`/`posture_mismatch`+
`believed_archetype`. Read the route off those; the `null`-but-should-have half is your rationale.

## `turn_plan` corrections and rule retirement

A `scope: turn` correction carrying a `turn_plan` note is the human's ideal-line tag on a
setup/development turn. It carries **no machine verdict**: the develop rollout rung that classified
one died with the rung ladder (Issue #386), and `common.composer` publishes no per-alternative
ranking to rebuild an equivalent from. Route these by the **generic `scope: turn`** rule above, and
read the ideal line against `opts[correct].fired` for the rules the human's pick already fires —
those are the retire-candidates the verdict used to nominate.

**Rule-retirement proposal (removal, not addition).** One per candidate rule R:
`target_layer: rule-retirement`, `for: general` (or `deck:<deck>` if R is deck-scoped),
`candidate_signal: n/a`, `verification_contract: seed-ladder`. `spec` = R's id + its charter (a rule
that also fires on KO/lethal turns is a **demote**, i.e. narrow its `when()`, not a retire) + the
corrections corroborating it. **Proof is the
batched R-off ladder run**: `/update-strategy` zeroes the candidates'
`tuned.json` weights in ONE committed build (the grader ignores `AGENT_OVERLAY`), submits, and a
neutral-or-positive ladder delta confirms the whole batch (a regression bisects). Only then is R removed.
**Charter nomination is your judgment** — `Hypothesis` carries no charter field, so read R's `id`/
`rationale`/`when()` in `src/common/strategy/*.py`; the corrections only *corroborate*, they don't
nominate.

## Spec against live source

Write the mini-spec from **live source, never memory**: `src/common/pilot.py` (`Context`/`Board` fields),
`src/cg/api.py` (enums), `src/common/cards.py` + `card_functions.json` (tags), `baseline_*.py` +
`src/agents/<deck>/strategy.py` (style), and `composer.py`/`state_value.py`/`planner.py` for sequence
routes. If the
sound fix needs a signal that doesn't exist, **say so in the `spec`** (`candidate_signal: "needs a new
signal"` + which layer) — `/update-strategy` builds it at apply time; that is **not** a capability-gap.

## Sibling hint — the leaf can't cluster

A leaf sees only its own correction, so it **cannot cluster** and must not try. If it suspects membership
in a cross-correction pattern — a posture miss likely shared with others of the same `believed_archetype`,
or a planner bug likely shared with the turn Correction that contains it — set `sibling_hint` to the
suspected cluster key. The **join** consumes it; the leaf **never** raises it in the intervention pass
(sibling-uncertainty is a join question, not a human one).
