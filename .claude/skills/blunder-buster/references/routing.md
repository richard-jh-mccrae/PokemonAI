# Routing a correction — the leaf's rulebook

Each fan-out leaf follows this to route **one** correction: read the **scope**, then the **live
trace**; draft the `spec` against **live source, never memory**. Output the leaf return contract
(SKILL.md). A leaf that cannot confidently reach a terminal outcome returns `outcome: uncertain` with
a `question` — it does not guess.

## Scope first (ADR-0049 / ADR-0019)

Every record carries `scope` (`decision` | `turn` | `match`), `subject`, and a scope-aware `key`. Scope
is a **strong routing prior — never an auto-route** (routing is this skill's value; don't let `tune.py`
do it):

- **`scope: turn`** — a whole ply was misplayed. Prima facie **`target_layer: planner-code`** (the Turn
  Planner, `plan_turn`), `verification_contract: verifier` — the gate is `retest_span`, which re-drives
  the Span to its **first divergence**. *But check:* if the Span's `live_trace.planned` is `null`
  throughout, the Planner never committed there → the real gap is a **`general-hypothesis`**.
  *And, if it carries a `turn_plan` note → it is a **develop-rung** correction — route by the
  develop-rung rulebook below, not this generic turn prior.*
- **`scope: match`** — a whole game was misplayed. Read the Span's per-turn `game_plan` (ADR-0045). Wrong
  mode/goal → **`planner-code`** (`plan_match`); wrong opponent read → **`matchup-brief`**; a line that
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
  resequencer — a *sequencing* decision, `planner-code`, not an under-weighted attack), `needy`
  (equal-score attach tie-break), `grabbed` (multi-pick set). Don't author a rule to "fix" a by-design
  reorder.
- **`live_trace.lethal` (ADR-0030)** — the Lethal Solver short-circuits scoring → a lethal-shaped blunder
  is **`planner-code`**, never a weight/`when()`. `null`-but-a-win-existed → the generator missed a
  win-shape; non-null-but-rejected → it over-fired.
- **`live_trace.planned` (ADR-0031)** — the Turn Planner short-circuits → a this-turn multi-step-line
  blunder is **`planner-code`**. If the better line spans **>1 of my turns** → **capability-gap** (don't
  bolt multi-turn onto the closed-form Planner — `docs/todo/deferred-multi-turn-criticals.md`).
- **`live_trace.posture` (ADR-0041)** — a `posture_mismatch` (or a member sharing one
  `believed_archetype` with others) is a **matchup-doctrine** miss → **`matchup-brief`**, never a
  deck-agnostic `when()`. Right-read-wrong-counterplay → a Brief data/lever change. No Brief covers it →
  route to `/matchup-genie <slug>` (a named hand-off). Wrong *Read* (γ low) → a recognition gap →
  **capability-gap**.
- **Otherwise** (no layer flag) → **`general-hypothesis`**, `verification_contract: verifier` (the
  correction fixture is the re-measure gate).

`tune.py` tags lines `[TURN <n>]`/`[MATCH]`/`[LETHAL]`/`[PLANNED]`/`[POSTURE≠ <arch>]`; the snapshot
carries `scope`+`subject`+`key` and `lethal_locked`/`planner_committed`/`posture_mismatch`+
`believed_archetype`. Read the route off those; the `null`-but-should-have half is your rationale.

## Develop-rung `turn_plan` corrections (Phase 3)

A `scope: turn` correction carrying a `turn_plan` note is the human's ideal-line tag on a
setup/development turn — the input for retiring the whack-a-mole scoring rules the **develop rollout
rung** subsumes (`docs/plans/phase3-tooling.md`). **Do not eyeball it — the machine verdict is on the
proposal's `develop_class`** (`train.tuner.develop.classify_develop_correction`, from the live trace's
`plan_candidates` / `planned` / `opts[correct].fired`). Route by `develop_class.kind`:

- **`rung-right`** — the rung committed the human's `correct` pick, reproducing what the tuned rules
  would. A **rule-retirement datum**: the rules in `leans_on_rule` are retire-candidates. But the
  telemetry alone **cannot prove** subsumption (the Catch-22: a strong rule makes greedy look confident,
  which suppresses the rung on that rule's own decisions — so a `rung-right` case is where the gate fired
  *despite* the rule). Cluster these by rule in the **join** (`develop_batch_report.retire_corroboration`)
  → one **`target_layer: rule-retirement`** proposal per rule (below), `verification_contract: seed-ladder`.
- **`leaf-misrank`, within-turn (`cross_turn: false`)** — the rung fired but ranked a board the human
  rejects above the human's. **`target_layer: planner-code`**: a leaf tune (`_board_development` /
  `_leaf_value` / `_engine_leaf_value`) or a gate tighten (`_develop_should_fire`) — say which in the
  `spec`. `verification_contract: verifier`.
- **`leaf-misrank`, cross-turn (`cross_turn: true`)** — the human's justification reaches beyond this turn
  (e.g. "save it — evolve next turn"), which the within-turn leaf **structurally cannot see**. The leaf
  can't be tuned to fix it; the honest read is that the rung **should not have overridden** here — a
  gate/horizon concern. Route **capability-gap** (`docs/todo/deferred-multi-turn-criticals.md`) and note
  the gate-tighten option (`_develop_should_fire` too permissive) in the four artifacts. If
  `overrode_greedy: true`, that is the strongest signal the augment-not-override gate over-fired.
- **`rung-inactive`** — no develop `planned` / no `plan_candidates`: the rung didn't fire (greedy or a
  higher rung drove it). Fall back to the **generic `scope: turn`** route above — the develop rung isn't
  the actor here.
- **`no-prescription`** — a prose-only turn tag (no `correct`). Route by its `rationale` like any turn
  correction; the develop-rung machinery has nothing to compare against.

**Rule-retirement proposal (removal, not addition).** One per candidate rule R:
`target_layer: rule-retirement`, `for: general` (or `deck:<deck>` if R is deck-scoped),
`candidate_signal: n/a`, `verification_contract: seed-ladder`. `spec` = R's id + its charter (why it is
within the rung's within-turn-development mandate; a rule that also fires on KO/lethal turns is a
**demote**, i.e. narrow its `when()`, not a retire) + the `retire_corroboration` count. **Proof is the
batched R-off ladder run** (`docs/plans/phase3-tooling.md`): `/update-strategy` zeroes the candidates'
`tuned.json` weights in ONE committed build (the grader ignores `AGENT_OVERLAY`), submits, and a
neutral-or-positive ladder delta confirms the whole batch (a regression bisects). Only then is R removed.
**Charter nomination is your judgment** — `Hypothesis` carries no charter field, so read R's `id`/
`rationale`/`when()` in `src/common/strategy/*.py`; the corrections only *corroborate* (the rung
reproduced R's pick on a real board), they don't nominate.

## Spec against live source

Write the mini-spec from **live source, never memory**: `src/common/pilot.py` (`Context`/`Board` fields),
`src/cg/api.py` (enums), `src/common/cards.py` + `card_functions.json` (tags), `baseline_*.py` +
`src/agents/<deck>/strategy.py` (style), and `lethal.py`/`planner.py` for planner-code routes. If the
sound fix needs a signal that doesn't exist, **say so in the `spec`** (`candidate_signal: "needs a new
signal"` + which layer) — `/update-strategy` builds it at apply time; that is **not** a capability-gap.

## Sibling hint — the leaf can't cluster

A leaf sees only its own correction, so it **cannot cluster** and must not try. If it suspects membership
in a cross-correction pattern — a posture miss likely shared with others of the same `believed_archetype`,
or a planner bug likely shared with the turn Correction that contains it — set `sibling_hint` to the
suspected cluster key. The **join** consumes it; the leaf **never** raises it in the intervention pass
(sibling-uncertainty is a join question, not a human one).
