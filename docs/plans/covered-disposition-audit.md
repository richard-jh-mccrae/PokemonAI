# Covered-disposition audit — the worklist

> **GENERATED — do not hand-edit.** `python tools/train/reviewed_audit.py --emit-report`.
> Issue #238, ADR-0114 decision 4. Regenerate after any ledger or rung change.

A `reviewed.json` closure is a claim about the shipped agent. When the rule it names is
deleted the claim expires silently, because the ledger stores its justification as opaque
prose. Every row below is an entry whose justification names a rung that **no longer
exists**. A row is *not* a finding that the frame is misplayed — it is a finding that the
**stated reason for closing it is gone**, so the closure has never been re-examined.

## How to use this

Open the frame — `python tools/train/frame_view.py <ledger key>` — and rule it on its own
merits, independent of the vanished rung (Issue #238 items 1-3, which are a human ruling and
are deliberately NOT automated). Then either re-close it against a rule that exists
(`python tools/train/review_correction.py <key> covered "<why>"`) or route it through the
current taxonomy. Once it stops being flagged, delete its line from
`data/corrections/reviewed_audit_allowlist.json`. The *what it became* column is there to
make that ruling cheap: it is the fold map's own statement of what replaced the rung.

## Tally

* ledger entries: **133**
* entries naming a retired rung: **0**
* by disposition: (none)
* live rung vocabulary: **95** `Hypothesis(id=…)` in `src/` (+ **16** `SoundRule(id=…)`)
* retired rung vocabulary: **96**
* distinct rungs implicated: **0**
* tokens that resolved to NO rung (the vocabulary's blind spot): **168** distinct, **257** occurrences. Top: `attack-last` ×27, `w-route` ×8, `buddy-buddy` ×6, `end-of-turn` ×6, `forgo-ko` ×5, `bench-fill` ×4, `first-dev-differs` ×3, `tier-4` ×3

The blind-spot count is reported rather than suppressed. The most frequent unresolved token
is `attack-last`, which is not a rung at all — it is the Pilot's structural resequencing
(`_finish_turn_last`). A loose `[a-z-]+` scan would have flagged every note that mentions it.

## Reconciliation against Issue #238's own lists

Acceptance criterion 5. Every count below is derived from this run, not transcribed.

* **body, the 13** — flagged 0/13.
  Not flagged: `81903490-27`, `81903490-49`, `81904451-50`, `81904451-6`, `81905522-47`, `81906131-25`, `82524455-27`, `82750161-59`, `82752045-80`, `82752045-97`, `82756664-74`, `83007714-7`, `83116501-89`.
* **body, the 3 `refuted` re-reads** — flagged 0/3.
  Not flagged: `82525741-81`, `82867148-87`, `85058574-114`.
* **comment, the 14 (`<ep>|<seat>|decision|<frame>` → `<ep>-<frame>`)** — flagged 0/14.
  Not flagged: `82224509-29`, `82224509-40`, `82224509-71`, `82225643-11`, `82225643-57`, `82226116-70`, `82226759-64`, `82227388-22`, `82227388-30`, `82227388-43`, `82228640-25`, `82228640-48`, `82228640-53`, `82229122-33`.

The 14 unflagged entries from the comment's 14 are correct behaviour, not a miss —
**10 of 14** close on `attack-last`, which names no rung, live or dead. It is the
Pilot's structural resequencing, so *"the agent does the right thing, just in a different
order within the same turn"* is a different question (*is same-turn ordering a blunder at
all?*) — and the comment filing them says exactly that. Nothing about them expired; there
is no dead rule for them to have expired against.

Entries this audit surfaces that Issue #238 never named: **0**.

## Provenance

* rung vocabulary captured at `d38270208cba`
* rungs deleted since that capture, folded in without git: none
* positive control — the four decider sweeps' `RETIRED` lists: **45** names, every one present in the historical harvest

