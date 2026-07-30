# Decision Gate rebuild — session handoff

**Status:** the instrument is BUILT and both gates pass. What follows is what the build did **not**
settle. Written 2026-07-30 at the end of Issue #188 / PR #227, for whoever picks this up **after that
merges**.

**Read first:** [ADR-0085](../adr/0085-snipe-is-a-categorical-relevance-instrument-and-the-fold-collapses-the-additive-stack.md)
Amendment I (the ruling and the measurements), `tools/train/decider_lab.py` (the instrument's own
docstring carries the reasoning), and the **Decider Lab** entry in `tools/train/CONTEXT.md`.

---

## What was wrong, in one paragraph

ADR-0072 defined the Decision Gate as *"the phase's `tools/train/probes/*_decider_sweep.py`"*, and
every one of those compared the shipped agent against its own kill-switch turned OFF. Correct at the
swap, when OFF **was** the incumbent rung pile. Then each phase DELETED its pile — tracker directive 1
requires exactly that — and nobody re-pointed the gates. With no incumbent, OFF is an empty scorer
whose argmax falls to option index, so all four sweeps compared their equation against *nothing* and
**could only ever report FIX**. They had been reporting `PASS` in that state for weeks.

Measured 2026-07-30: `baseline_promote` **0** rungs left (was 12), `baseline_energy` 3 (22),
`baseline_evolution` 2 (6), `baseline_snipe` 3 (9). `evolve_decider_sweep` → `4 FIX, 0 REGRESSION`;
`snipe_decider_sweep` → `12 FIX, 0 REGRESSION`.

**The lesson, which is the reusable part:** a gate must diff against a **recorded baseline**, never
against a live switch. The Discrimination Gate was never exposed to this precisely because it always
had one.

## What shipped

- `tools/train/decider_lab.py` — capture/diff over every replayable Correction, recording what the
  agent **decides**. `--context N` gates one phase's frames.
- `data/decider_lab/baseline.json` — 332 frames, `git_rev`-stamped. **A ruling record**: never
  auto-recapture it.
- `gates.decider_lab_diff` — beside `leaf_lab_diff` so the two gates cannot drift; keys through
  `frame_key_of` so one Held-out ruling holds a frame out of BOTH.
- The four `*_decider_sweep.py` are bannered **DIAGNOSTIC** and no longer title themselves the gate.

Verified by **mutation**, not by a green run: inverting the snipe ordering makes the new gate report
**12 REGRESSION and FAIL** on the same frames the old sweep called FIX.

---

## Owed work, highest value first

### 1. The baseline silently blesses 111 disagreements — this is the big one

The capture reads **220/331 agree with the human**. The other **111 frames are recorded as the
reference while disagreeing with a human ruling.** Nothing about that is hidden — but nothing about it
is *examined* either, and the gate will now defend those 111 wrong answers as vigorously as the 220
right ones. A build that FIXES one of them shows up as a `FIX` row, which is fine; the risk is the
opposite reading, that a green gate means the agent is right.

**Do not "fix" this by tightening the gate.** The gate's job is regression detection and it does that.
The owed work is a triage pass over the 111, ideally ranked by context, feeding the correction rounds
Issue #146 owns. Per-context agreement at capture time:

| ctx | name | agree | note |
|---|---|---|---|
| 0 | `MAIN` | 160/245 | the bulk; the Turn Planner's domain (Issue #165) |
| 7 | `TO_HAND` | 24/30 | |
| 15 | `DAMAGE` | **17/19** | snipe — matches its known record |
| 21 | `ATTACH_FROM` | 5/6 | |
| 8 | `DISCARD` | 1/12 | **see item 2 — this number is an artifact, not a defect** |
| 2 | `SETUP_BENCH_POKEMON` | 1/3 | Issue #197's territory |
| 3 | `SWITCH` | 2/4 | |
| 5 | `TO_BENCH` | 0/1 | |
| 34 | `SKILL_ORDER` | 0/1 | |

### 2. The agree RATE is not meaningful for multi-pick contexts

Found by reading the captured `DISCARD` rows rather than trusting the aggregate. The agent picks
`[2, 3]` where `correct` records `[2]` — because a Correction's `correct` names **the card the ruling
was about**, not the whole legal answer, while a multi-pick select legitimately returns every index it
must discard. Hence 1/12, which is a **vocabulary mismatch, not a regression**.

Already fixed: the diff now compares picks as **sets**, so a reordered multi-pick is no longer a false
`REGRESSION` (`test_decider_lab_diff_compares_a_multi_pick_as_a_set_not_a_sequence`). What is NOT
fixed, and is the owed decision: whether `correct ⊆ chosen` should count as agreement for multi-pick
contexts, or whether those Corrections should record the full answer. That is a **Corrections-schema
question** and belongs with ADR-0082's Claim vocabulary, not with this instrument.

### 3. Recapture the baseline at a `main` SHA, as a ruling act

It is currently pinned at `6328ab7` — a commit on a feature branch. After PR #227 merges, re-run
`capture` on `main` and commit it, **only once any flips between the two have been ruled**. If the
flip list is empty the recapture is bookkeeping; if it is not, each flip is a conversation before the
file moves. Mirror the wording `docs/ci.md` already uses for `data/leaf_lab/baseline.json`.

### 4. Decide whether the Decision Gate gets a `main` watchdog

`.github/workflows/leaf-gate-main.yml` runs the **Discrimination** Gate on every push to `main` and
fails on an unruled `OK → MISS` (CLAUDE.md records that as a deliberate, narrow widening of the
tests-only CI rule). The Decision Gate now has an equivalent instrument and no equivalent watchdog.
Arguments both ways, genuinely: it is the more end-to-end reading, so it deserves one; but it replays
332 frames through a full Pilot and is materially slower than the leaf diff, so measure the runtime
before proposing it. **The workflow must never recapture the baseline** — that is what would make it
vacuous, the same way the old sweeps went vacuous.

### 5. Decide the diagnostics' fate

The four `*_decider_sweep.py` are now diagnostics with real per-leg value. They also still carry an
OFF-vs-ON arm that means nothing post-deletion. Either strip that arm and keep the breakdowns, or
retire the ones whose breakdown `decider_lab` subsumes. Not urgent; do not do it blind — check which
still get run.

---

## Traps

- **`_build_pilot` per frame, never reused.** The Pilot is stateful (deck tracker, per-decision
  caches). `decider_lab` builds a fresh one per frame on purpose, following `needs_sweep` /
  `threat_sweep`. Reusing one to speed up the capture will silently leak a previous frame's board.
- **One unreplayable frame** is recorded with `error` rather than dropped. Keep it that way: a
  shrinking gated set must be visible.
- **`added` / `removed` are surfaced deliberately.** A baseline taken against a different corpus
  shape must be loud, not silently compared on the intersection.
- **A measured claim expires when the thing it measured moves.** Concrete instance from this build:
  ADR-0085's grill recorded that dropping `share` from `my_route` cost `82756021-57` (16/19). Re-run
  after the context fix, deletion pass and tiebreak, it changes **no decision at all**. Several of
  that ADR's numbers were taken on earlier builds; re-measure before citing one.
- **Cross-issue ownership.** This edits probes belonging to Issues #139, #140 and #141 (all closed).
  The alternative was leaving three known-vacuous gates on `main`.
