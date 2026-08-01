# ADR-0094 — A baseline re-capture may not move a frame's verdict without a ruling

**Status:** Accepted (grilled 2026-08-01, `/grill-with-docs` on Issue #259, wave-1 packet item 1).
**Build = Issue #259 (POC-T0). Scope: NOT in Issue #259's stated scope** — it rides with T0 because
T0 is the serial track and all five downstream lanes are graded against exactly these baselines.
Shipped as its own commit for that reason.
**Extends [ADR-0072](0072-two-gates-guard-the-decider-and-the-leaf.md)** (the Discrimination and
Decision Gates and their "never auto-recapture" rule — this rules on the one actor 0072 left
unguarded: the *capture* command itself) and
**[ADR-0092](0092-the-value-system-poc-builds-by-differencing-tracks-with-wave-rulings.md)**
(the POC's wave-ruling verification story, which this **enforces** — an earlier draft of this ADR
said "falsifies", on a claim the Context section below disproves).
Does **not** supersede anything.

⚠️ **Temp-named, not numbered.** Real number assigned at `/open-pr` rebase time. Cite the issue.

**Context issues:** Issue #259 (this grill / POC-T0), Issue #197 (whose re-capture `d5f7211` moved
the frame the first draft mis-attributed — legitimately, the frame being ruled), Issue #165 (holds
that frame out), Issue #228 / ADR-0093 (armed deny for real, and dissolved both of the flips this
ADR's first draft measured).

## Context

`CLAUDE.md` states the rule plainly: neither gate **ever** re-captures its baseline, because "a
baseline is a ruling record, and auto-recapture would make the gate vacuous — which is not
hypothetical, it is exactly how the old Decision Gate died."

The rule is documented. It is not **enforced**. `leaf_lab.py capture` / `decider_lab.py capture`
write whatever the current build produces, with no reference to the outgoing baseline and no
knowledge of which frames carry a ruling. Nothing distinguishes a re-capture that records a
*ruled* change from one that silently overwrites a verdict the user was still owed.

### Measured 2026-08-01 on this worktree, not recalled

⚠️ **This section was rewritten after its first draft asserted a defect that did not occur.** The
draft claimed `eec06b1` ("chore(gates): re-capture both baselines at a8da62d") had silently absorbed
an owed ruling. Tracing the frame across every commit that touched the baseline disproved it. The
correction is kept visible rather than edited away — an ADR that quietly repairs its own evidence is
worth less than one that shows what it got wrong.

**What is true.** Wave-1 packet item 1 asked the user to rule flip `84071010|0|decision|15` and
*then* re-capture, on the premise that the baseline "was captured at `e4c46ca`, so the baseline
predates that ruled pricing change." The premise is stale:

```
data/leaf_lab/baseline.json     git_rev = a8da62d      (NOT e4c46ca)
data/decider_lab/baseline.json  git_rev = a8da62d
src/common/runtime.py:186       "scaled_threat_rank": True,   armed-ON 2026-07-30
```

The frame's row in that baseline is **already a MISS** (`correct_rank: 2`,
`correct_is_top: false`, correct 107.675 vs top 7000), so it cannot flip `OK -> MISS` and the
packet's "rule it, then re-capture" has nothing to act on. Gate runs, deny as the only variable:

```
deny OFF (control):  Discrimination PASS 0 moved · Decision PASS 0 moved
deny ON:             Decision PASS 0 moved
                     Discrimination FAIL — 2 unruled OK -> MISS
                       82225643|1|decision|11   rank 1 -> 3   (packet item 2)
                       83686860|1|decision|13   rank 1 -> 2   (NOT in the packet)
                     + IMPROVED 82224509|1|decision|67  MISS -> OK
                     84071010|0|decision|15 does not appear
```

**What is NOT true — the correction.** Tracing `84071010|0|decision|15` across all twelve commits
touching `data/leaf_lab/baseline.json` puts its `OK -> MISS` at **`d5f7211`** ("Issue #197:
re-capture the Discrimination Gate baseline at the pre-swap commit", 2026-07-30), not at `eec06b1`,
which moved **zero rows**. And that frame **carries two rulings**: `fixed` in `reviewed.json` (BUILT
2026-07-13, `retreat_enabler_lethal`) and `held_out` onto Issue #165. It was never an owed ruling.

Replaying **every** baseline transition against the Ruling Index closes the question:

```
151f441 -> 9750cf8   absorbed 3 OK->MISS   unruled 0
b30d06f -> d5f7211   absorbed 1 OK->MISS   unruled 0
d5f7211 -> ec64d68   absorbed 1 OK->MISS   unruled 0
```

**Three re-captures, five absorbed flips, zero unruled. The convention has held.**

So this ADR does not repair a breach and must not be read as one. What it removes is the *reliance
on discipline*: `CLAUDE.md`'s rule had no mechanism, the POC is a six-track parallel build in which
every track rebases against these baselines, and a re-capture is exactly the moment nobody re-reads
the writer. A guard that has never needed to fire is the cheapest insurance available — it costs one
diff of an artifact the command already reads.

**Item 1's actual resolution** falls out of the same trace, and is cleaner than the draft's "re-open
the frame": `84071010|0|decision|15` is **held out onto Issue #165**. It is owned, not owed. There is
nothing for wave 1 to rule.

## Decision

**1. `capture` is ruling-gated.** Both `leaf_lab.py capture` and `decider_lab.py capture` read the
outgoing baseline before writing. For every key present in both, if the frame's graded verdict
changes in the fail direction (`OK -> MISS` for the Discrimination Gate, `agree -> disagree` for
the Decision Gate), the capture **refuses to write** unless that key carries a ruling record.
Improvements and new keys write freely. The refusal names every offending key.

**2. A rebase re-stamp is metadata-only.** Four of the twelve committed re-captures moved nothing but
the recorded `git_rev` — a rebase had orphaned the SHA. Serving that through `capture` means
re-reading the build (the ruling-bearing operation) to achieve a metadata edit. A distinct `restamp`
path rewrites `git_rev` and nothing else, and never re-reads the build, so it *cannot* move a
verdict. The two stop being one command that does both.

**3. Ruling records are named through the existing resolver.** The gate already resolves a ruling
for a key ([ADR-0090](0090-a-ruling-names-its-record-through-a-resolver.md)); the capture gate
reuses that resolver rather than introducing a second notion of "is this frame ruled." A hand-built
second lookup is the defect [ADR-0087](0087-a-corpus-reader-constructs-corrections-and-keys-by-identity.md)
already paid for once.

**4. `84071010|0|decision|15` needs no wave-1 ruling.** The packet's item-1 recommendation is
withdrawn as resting on a stale premise (the baseline is at `a8da62d`, not `e4c46ca`), but the frame
itself is **held out onto Issue #165** and carries a `fixed` ruling besides. It is owned, not owed.
Nothing is re-opened.

## As built (2026-08-01)

`refuse_unruled_recapture` / `unruled_recapture_moves` / `fail_direction_keys` / `restamp_artifact`
live in `tools/train/gates.py` — the module BOTH labs already route through, so the guard is written
once. Each lab computes its own fail direction through **its own existing diff** (`leaf_lab_diff`'s
`ok_to_miss`, `decider_lab_diff`'s `REGRESSION`) rather than through a second classifier, which is
what stops the guard and the gate it protects drifting into two ideas of "worse".

Verified end-to-end on real corpus data, not only in unit tests: a baseline doctored so one genuinely
unruled frame reads as previously-agreeing causes `capture` to refuse, name the frame, exit 1, and
**leave the baseline byte-untouched**. A `restamp` of the real committed baseline changed `git_rev`
and nothing else.

Two things the build corrected in this ADR's own reasoning:

- The refusal message is **ASCII**. It reaches the operator on stderr, which neither lab reconfigures
  to UTF-8, so an em dash arrived as `?` on a Windows console (measured). A message that garbles on
  the box it is most likely to be read on is a message that gets ignored.
- The first end-to-end attempt appeared to show the guard failing. It did not: the frame chosen for
  the test (`81905522|0|decision|75`) is the known indistinguishable-options frame, so the agent's
  pick genuinely satisfies the ruling under ADR-0091 equivalence. The **test picker** was wrong, not
  the guard — a reminder that a "disagreement" computed without the equivalence map is not one.

## Consequences

- **No backlog is expected.** The first draft predicted the guard would surface further
  already-absorbed frames; the full-history replay says it will not, because there are none. A
  green first run is the *predicted* result, and reading it as "the guard works" would be reading a
  vacuous pass — the guard is exercised by its unit tests and by the doctored-baseline integration
  run, never by history.
- `capture` gains a dependency on the outgoing baseline and the ruling resolver, so it can now fail.
  That is the point: a capture that cannot fail is a capture that cannot protect a ruling.
- Scope cost, stated plainly: this was not in T0's budget. It adds this ADR and changes both capture
  tools plus a test asserting the refusal fires. T0 absorbs it because T0 is the serial track and
  every later track's flips are graded against exactly this mechanism.
- `CLAUDE.md`'s "neither gate ever re-captures its baseline" is unchanged in intent and now has an
  enforcing mechanism rather than only a convention.
