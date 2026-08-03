# Wave-3 packet — issue-sequence run (230, 299, 229, 251, 256, 238, 303, 304, 302)

Gate flips and pending rulings from this batch, for developer verdict. Nothing here has been
conformed into either baseline.json — a baseline is a ruling record, not something a sub-issue may
recapture on its own recognisance.

## Pending rulings

### R2 is RESOLVED — the developer reviewed and chose a third option, not R1 or R2 (2026-08-03)

**`85709280-m1` / `ee3191f7c3d6` is no longer `match` scope.** Reviewing this packet, the developer
caught two things this issue's own spec got wrong, and ruled a resolution neither R1 nor R2
anticipated:

1. **The spec's reason for rejecting a `decision`-scope re-tag was false.** It said re-scoping to
   `decision`/subject 51 *"invents a ruling the human never made (the rationale is a whole-match
   note)"*. Read in full, the rationale is entirely and specifically about ONE Main select — bench a
   2nd Solrock, or play Lillie's Determination to keep the last slot for Makuhita — with no
   whole-match language anywhere in it.
2. **But the record's `span` genuinely IS match-level content** — a full 16-turn `game_plan` trace
   (SETUP → RACE → STABILIZE → CLOSE, ADR-0045's Match Planner vocabulary), which no `decision`-scope
   record in the corpus otherwise carries. So this was never a simple mis-tag; it carried two
   genuinely different things under one scope.
3. **A hoped-for safety net turned out to be orphaned.** The same 2026-07-29 commit
   (`b6d7483a`, "ADR-0081 Amendment D") that hand-patched this record's `correct` also created
   `tests/fixtures/corrections/ml_dont_bench_redundant_solrock_f51.json`, a clean, separately-typed
   Decision Claim asserting the same ruling. It has no `frame_key` (required by
   `iter_keyed_fixtures` to opt into the Held-out Ledger / Claim Agreement) and no test references it
   by name — it does nothing today. It is NOT a backup for whatever happens to the raw record.

**Ruling: re-scope to `decision`, subject 51. Keep `correct: [0]`. Keep `span` as-is.** Nothing in
`build_correction` forbids a `decision`-scope record from carrying a `span` — it is simply the first
one that does. This is a strict improvement over both R1 (which would have ungraded a real, still-
live ruling) and R2 (which would have thrown the machine-checkable ruling away, since the orphaned
fixture does not preserve it). **Executed and committed** — see ADR-0113 Amendment A for the full
account, including the `reviewed.json` re-key this also required (`85709280-m1` → `85709280-51`,
restoring `gates.orphan_rulings() == []`) and the measured gate consequence below.

### R1 — a `match`-scope Correction should stop grading at its Anchor — now zero-instance, still open

Unchanged as a general policy question for a HYPOTHETICAL future `match`-scope record — nothing
forces an answer today, since the repair above means **the corpus currently holds zero `match`-scope
records** (`scope="match"` is theoretical vocabulary, not dead code). Original text preserved below
for whenever a future tag revives the question.

<details>
<summary>Original R1 text (no longer about a live record)</summary>

**Issue #256, ADR-0113 decision 1 — this section describes what a similar case USED to look like.**

**Ruled by the agent, NOT executed.** It removes a frame from both gates, which is a developer act
under ADR-0088's void-and-re-capture protocol.

**Why.** A `match` Correction is a claim about a whole Episode; both gates grade it at its **Anchor**,
the one Decision the human happened to be looking at. `build_correction` forbids a `match` record from
naming a `correct` option at all — *"no single `select` carries a whole-match verdict"* — so grading
one at an Anchor grades a field the schema says must not exist.

The sharper half, found by measuring rather than by argument: **the only `match`-scope shape the
constructor will produce is one `satisfies_human` reads as a DECLINE.** `build_correction` stores
`list(correct)`, so a legal match record carries `correct: []`, and `satisfies_human` grades `[]`
exactly — *"take none of these"*. A well-formed match Correction graded at its Anchor therefore
asserts the agent should have picked nothing at that select. Match scope and Anchor grading do not
compose in either direction.

**The exact change.** One clause, in the two places the corpus becomes rows:

```python
# tools/train/decider_lab.py, _records(): the keep predicate
def keep(c):
    return bool(c.obs and c.agent) and c.scope != "match" and (not agent or c.agent == agent)

# tools/train/leaf_lab.py, is_leaf_frame(): a guard ABOVE the disjunction, not inside one arm —
# `is_leaf_frame` is a two-arm OR and a `turn_plan` record qualifies on the first arm alone.
if getattr(c, "scope", None) == "match":
    return False
```

(An alternative one-liner is a `voided`-style hold-out, which needs no code at all — see *Note* below.)

**Measured gate consequence.** Today exactly ONE record is `match` scope repo-wide
(`85709280|1|match|`, id `ee3191f7c3d6`; corpus 372 = 353 `decision` / 18 `turn` / 1 `match`), so
this ruling is about that record alone.

| gate | today | after R1 |
|---|---|---|
| Decision Gate agree (live build) | 250 / 347 | **249 / 346** |
| Decision Gate agree (committed baseline) | 251 / 345 | 250 / 344 |
| Decision Gate verdict | PASS, 0 unruled REGRESSION | PASS — the frame leaves as `removed`, no REGRESSION row |
| Discrimination Gate `leaf_correct` (committed baseline) | 180 / 247 (277 rows) | **179 / 246** (276 rows) |
| Discrimination Gate verdict | PASS, 0 unruled OK→MISS | PASS — the frame leaves as `removed`, no `ok_to_miss` row |

The leaf numbers are the **committed baseline's**, because that is what a re-capture moves; the live
rate (131/249 shared-top) is dominated by the 67 *ruled* OK→MISS flips owned by other issues and is
not a stable reference. The row is `correct_is_top: True` in the capture and does **not** appear in
any flip list on this build (verified by grep, with a positive control on `85709280|1|decision|42`),
so it is an OK on both sides and R1 removes an OK either way.

⚠️ **The agree rate goes DOWN, not up.** The frame currently grades as an **AGREE** — the Decision
Gate scores the *fresh Pilot replay pick* (`[0]`) against `correct: [0]`, not the record's own
historical `chosen` field (`[2]`). Issue #256's spec claimed the opposite and concluded that ungrading
"raises the agree rate"; that is refuted (ADR-0113 *Claims verification refuted*). R1 removes a
**false success** and costs one point of agree rate. It is still the right ruling, but it is not free.

**A re-capture is owed after executing it** — both baselines, at a commit carrying the ruling but NOT
any change under test.

*Note:* if you would rather not touch either instrument for a population of one, the same effect is
available with **no code** by voiding the frame in `data/corrections/reviewed.json` (ADR-0088). That is
cheaper today and wrong tomorrow: a void is a statement about *this ruling*, and R1 is a statement
about the *scope*. A second `match` record would silently start grading again.

</details>

<details>
<summary>Original R2 text (superseded — the developer chose re-scope over strip-correct; kept for
the record, do NOT execute)</summary>

### R2 — re-rule `85709280-m1` to the shape the constructor accepts (Issue #256, ADR-0113 decision 3)

**Ruled by the agent, NOT executed.** It edits a committed record and moves a gate number.

**Why.** The record is `match` scope carrying `correct: [0]` — a shape `build_correction` refuses
outright. Its own rationale records a hand re-ruling on 2026-07-29 (Issue #197 / ADR-0081 build prep),
which is how it got past the writer; `Correction.from_dict` does not validate, so it has loaded and
graded ever since. Of the issue's three options, re-scoping to `decision` at frame 51 invents a ruling
the human never made (the rationale is a whole-match note), and leaving it alone preserves a forbidden
shape. So: keep `match`, drop `correct`, leave the intended line ("Play Lillie's Determination") in the
rationale — which is what the constructor's own error message prescribes, and where that record's
rationale already carries it.

**The exact change**, in `data/corrections/` for id `ee3191f7c3d6`:

```json
"correct": [],  "correct_label": ""
```

(`scope` is already `"match"`; nothing else moves.)

**⚠️ Do NOT execute R2 without R1.** Alone it makes the record *worse*. Its select is `minCount 1` — a
mandatory MAIN select — and the record's own rationale says the 2026-07-29 move `[] -> [0]` was made
*because* "the empty pick was degenerate at a minCount-1 Main select". Re-ruling back to `correct: []`
restores exactly that: `satisfies_human` grades `[]` as a DECLINE, so at a select where declining is
illegal **no legal pick can ever satisfy the record**. A permanently unsatisfiable disagreement is
worse than a false agreement. Executed *with* R1 the empty `correct` is inert, because the frame no
longer grades at all.

**Measured gate consequence** (R2 alone, for completeness — not the recommended path):

| gate | today | after R2 alone |
|---|---|---|
| Decision Gate agree (live build) | 250 / 347 | **249 / 347** (a standing DISAGREE) |
| Decision Gate verdict | PASS | PASS — no pick moved, so no REGRESSION row; it surfaces as a **RULING MOVED** line, `correct [0] -> []` |
| Discrimination Gate `leaf_correct` (committed baseline) | 180 / 247 | **179 / 246** — `is_leaf_frame` is False once `correct` is empty (the record carries no `turn_plan`), so the row leaves the lab as `removed` |

Executed **together with R1**, the totals are R1's row of the table above and nothing further moves.

**Prior art for the direction of these numbers**, already committed: `gates.ruling_moves`' docstring
records that this same record went `[] -> [0]` in `b6d7483` and *"moved the agree rate 230 -> 231 with
no decision changed"*. Reverting it is −1, symmetrically.

**A re-capture is owed after executing it.**

</details>

### Measured — what actually landed (the ruling above, executed 2026-08-03)

| gate | before | after | verdict |
|---|---|---|---|
| Discrimination Gate | PASS, 0 unruled OK→MISS, 67 ruled, 3 voided, **198 gated** | PASS, 0 unruled OK→MISS, 67 ruled, 3 voided, **197 gated** | unchanged; `CORPUS SHIFTED: +1 added, -1 removed` reported, does not gate |
| Decision Gate | PASS, agree **250/347**, 0 picks moved, 0 rulings moved, 24 voided | PASS, agree **250/347** (unchanged), 0 picks moved, 0 rulings moved, 24 voided | unchanged; `corpus shape moved: +1/-1` reported, does not gate |

Both `+1 added / -1 removed` pairs are this one record's identity change
(`85709280|1|match|` → `85709280|1|decision|51`) — confirmed by re-running both diffs with the edit
stashed: the numbers above match exactly except for that one key. Verified against **neither**
baseline moving (`git status --porcelain data/leaf_lab/ data/decider_lab/` empty).

**One additional repair the edit required, found by the diff itself, not anticipated by either
original option:** `data/corrections/reviewed.json` keys a `covered` disposition for this record as
`85709280-m1` (its match-scope review key). Re-scoping to `decision` orphaned that entry —
`gates.orphan_rulings()`, whose invariant a real test (`test_no_committed_ledger_entry_rules_on_
nothing`) asserts empty, started returning it. Re-keyed to `85709280-51` (the decision-scope
`review_key`/`anchor_form`), value untouched. The disposition itself is still live and correct — the
rule it cites, `dont-bench-a-redundant-engine-piece`, is still a shipped `Hypothesis` in
`src/agents/mega_lucario/strategy.py` — so this was a pure re-key, not a re-review.

## Flips

| frame | gate | issue | old | new | recommendation |
|---|---|---|---|---|---|

*(No gate flip has occurred in this batch. Issues #230, #299, #229, #251, #256, #238, #303, #304 and
#302 have all landed gate-neutral: both baselines byte-identical, Decision Gate PASS at agree 250/347
with 0 picks moved and 0 rulings moved, Discrimination Gate PASS with 0 unruled OK→MISS, 67 ruled, 3
voided, 198 frames gated. The table is kept so a later issue in the run has somewhere to put one.)*

*Worth recording because the parent epic #298 predicted otherwise: it warned that A2.1/2, /3, /5 and
/6 "**move live decisions the moment they land**", since `card_effects.json` is read on the hot path.
Measured after both #303 and #304, with a positive control on the same instrument, it does not — every
live `effects.clauses(...)` consumer filters on a specific `kind` string (`fetch` / `accel` / `heal` /
`draw` / `energy_recur`) and the two generic `kind = cl.get("kind")` switches are equality cascades an
unrecognised kind falls straight through. The prediction is right about the FILE and wrong about which
kinds are wired; a sub-issue that adds a NEW kind is inert until T4, while one that edits an existing
kind's clauses is not. #302 edits `draw`, which IS wired.*

### The `draw` half of that prediction is refuted too (Issue #302) — no ruling owed, recorded as a finding

The sentence above ends *"#302 edits `draw`, which IS wired."* Written before #302 was built, and
**wrong in the way that matters**. #302 rewrote the clause of 16 cards on the `draw` kind and both
gates stayed byte-identical. Three measurements, each with a positive control:

1. **There is exactly ONE `kind == "draw"` consumer in `src/`,** `planner._gamble_draw_engines`
   (`planner.py:2308`), and it additionally requires `condition: "once_per_turn_ability"` — the
   draw-ENGINE Abilities (Dudunsparce, Drakloak, Fezandipiti, Lunatone). No Trainer among the 16
   carries that condition, so none of them reaches it. An AST sweep of all 14 `effects.clauses(...)`
   call sites in `src/` (excluding `src/cg/`) resolves the kind filter in each: `fetch` 6, `heal` 2,
   `accel` 1, `energy_recur` 1, `draw` 1, and 3 whose filter sits one call deeper
   (`combat._attach_contribution` → `accel`/`fetch`; `planner._closure_clauses_of` → `fetch_closure`,
   `fetch`; `planner._supporter_energy_tutor_reaches`, an `if kind == "fetch" … elif kind == "accel"`
   cascade). The sweep finding those five kinds is the positive control for it finding nothing else.
2. **The live hand-refresh scorer never read the compendium.** The epic and Issue #302 both named
   `pilot.py`'s `_refresh_cycle` as a `draw`-clause consumer. It calls
   `common.strategy.refresh.net_change`, which reads that module's OWN hand-keyed `_REFRESH` table —
   and that table already carried the correct conditional counts and opponent legs for all five
   refreshes it covers (Judge 4/4, Harlequin's coin, Unfair Stamp 5/2, Lillie's 6-or-8-at-six-prizes,
   Lacey 4-or-8). **That is why four years of a wrong compendium never reached a decision**: the fact
   was stated twice and the live copy was the right one. `tests/strategy/test_refresh_swing.py`
   now asserts the two stores agree, so the next divergence fails a test instead of hiding.
3. **`apply_option()` raises `NotImplementedError`** (T0 freezes the contract, Issue #263 builds it),
   so the `_covers` verdicts this issue moved have no runtime consumer at all today — only the census.

**Nothing here needs a developer verdict.** It is filed in the packet because the epic's standing
prediction is now refuted on all four of its named sub-issues, and a later reader planning A2.1 work
should cost it as inert-until-T4 rather than as hot-path.
