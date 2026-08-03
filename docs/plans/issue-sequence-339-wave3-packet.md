# Wave-3 packet — issue-sequence run (339, ...)

Gate flips from this batch, pending developer ruling. None conformed into either baseline.json —
a baseline is a ruling record, not something a sub-issue may recapture on its own recognisance.

## Flips

| frame | gate | issue | old | new | recommendation |
|---|---|---|---|---|---|
| `81906755\|1\|decision\|9` | leaf (Discrimination) | #339 | OK | MISS | **Rule it with the developer.** NOT caused by Issue #339 — see the attribution note below. Either fix the code or hold the frame out via its fixture's Decision-Claim `owner`. Never re-capture to absorb it |

## Attribution — this flip is PRE-EXISTING on the batch base, not a product of Issue #339

Issue #339 changed two files: `docs/ci.md` (prose) and `tests/test_baseline_provenance.py` (new).
Neither is on a scoring path, so the flip cannot be attributable to it. That is the claim, and it was
**measured rather than asserted**, because "my change is only docs" is exactly the kind of premise
this repo has been burned by:

```
# with the change applied
GATE: FAIL  (rule: zero unruled OK->MISS; 1 unruled, 65 ruled, 3 voided)
  gated on 199 frame(s), held out 65, voided 3

# git stash push -u   ->  clean base tree (81000e1), same command
GATE: FAIL  (rule: zero unruled OK->MISS; 1 unruled, 65 ruled, 3 voided)
  gated on 199 frame(s), held out 65, voided 3
```

The two summaries are byte-identical, including the `could not build SkiChu` line and the
`277 leaf frames (268 scorable, 9 unscorable, 1 agent-skip, 19 voided)` header. The Discrimination
Gate was **already red at `81000e1`**, the commit this batch branched from.

The sibling **Decision Gate is clean**: `GATE: PASS (0 unruled, 0 ruled, 0 voided)`,
`agree 250/347 -> 250/347 (0 picks moved, 0 rulings moved)`. It emits a non-failing
`⚠️ corpus shape moved: +1 / -1 frames` warning, which by `docs/ci.md` warns rather than fails.

## Why nothing was conformed

`CLAUDE.md` and ADR-0094 both say the same thing and this packet exists to obey it: a flip is
**ruled**, never conformed. No `capture` and no `restamp` was run against either
`data/leaf_lab/baseline.json` or `data/decider_lab/baseline.json` during this batch — the issue that
opened it is *about* the record of those baselines and its own "Out of scope" section forbids
touching them. Auto-recapture is how the old Decision Gate died; it would make this gate vacuous the
same way.

## End-of-batch re-verification (after Issue #275, the last item)

Both gates were re-run on the complete batch tree — all seven issues applied — and the picture is
unchanged. Recorded here rather than only in the PR body, because this packet is what goes to the
developer:

```
Decision Gate:        PASS  (0 unruled, 0 ruled, 0 voided);  agree 250/347 -> 250/347
Discrimination Gate:  FAIL  (1 unruled, 65 ruled, 3 voided); gated on 199, held out 65, voided 3
  the single unruled flip is `81906755|1|decision|9`, the SAME frame as at the batch base
```

**No new flip was introduced by any of the seven issues, and neither baseline moved.** Byte-identity
was proven with `md5sum -c`, not by eye:

```
ed12a86760d42c9178a51ff2b0fc260d  data/leaf_lab/baseline.json      : OK
bcc5c07433d733333155d4a5f0e51d5e  data/decider_lab/baseline.json   : OK
```

Issue #275 is the item that could most plausibly have moved a gate — it regenerates
`src/common/attack_overrides.json`, which feeds the damage oracle and therefore `state_value`'s
`threat` and `survival` terms. It did not, and that is measured rather than assumed: the regenerated
table came back **byte-identical** (`md5 5daa38a9fed7c2b74ab94220f11a9e7b`, unchanged), because both
engine fits REPRODUCED the human ruling they were owed against. Only
`attack_overrides.provenance.json` changed, and provenance is not on any scoring path.
