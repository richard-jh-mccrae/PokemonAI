# Training evidence and the Ledger's rounds

Human Corrections are the evidence base. The Ledger's manual training rounds (plan §7,
ADR-0147/0148) tune its closed Valuation Configuration against them; the quarantined Bellman teacher keeps them
as its frozen acceptance evidence (ADR-0149).

- `blunder/`: correction schema, replay decisions, labels, provenance, telemetry joins, and storage.
- `bellman_corpus.py`: reruns Mega Starmie Corrections through the Bellman teacher
  (`deprecated.bellman.build_teacher_runtime`, ADR-0149).
- `bellman_adjudicate.py`: classifies the unfiltered corpus against written rationales.
- `ledger_corpus.py`: the Ledger's training dashboard — every deck's Corrections through the live
  runtime; per-deck agreement, the generality floor, misses with their rationales, gap census,
  regressions vs a prior baseline (ADR-0145); prize-anchor stamping + retired rulings (ADR-0147).
- `corpus/`: hashed Episode Bundles, immutable Canonical Corpus publication, and Training Views.
- `ledger_tune.py`: the §7 nudge / keep-best / adoption-gate loop over the Ledger's general
  Valuation Configuration; every trial lands in `docs/tuning/runs/`.

Deck behavior changes in shared runtime code or declarative deck Roles, not generated `tuned.json`.

## Language

**Corpus Decision**:
One agent choice point retained with its complete legal alternatives and a terminal label or explicit
exclusion. Action-level examples and diagnostic reports are derived views.
_Avoid_: Training Row, Action Sample, Episode Sample

**Canonical Corpus**:
The immutable, manifested collection of complete Corpus Decisions from which every Training View can
be rebuilt. It favors reproducibility over direct analytical speed.
_Avoid_: Training View, Dashboard, Working Dataset

**Corpus Snapshot**:
One published identity of the Canonical Corpus. It references immutable evidence shards and may
reuse unchanged shards from earlier snapshots without changing them.
_Avoid_: Corpus Run, Mutable Dataset, Latest Corpus

**Episode Bundle**:
A closed, hashed staging unit containing one Episode's replay and authoritative telemetry. Corpus
publication consumes complete Episode Bundles and never mutates them during a match.
_Avoid_: Corpus Decision, Replay File, Live Corpus Row

**Corpus Origin**:
The provenance boundary distinguishing evidence recorded during play from evidence reconstructed by
offline replay evaluation. Reconstructed output never claims to be historical runtime behavior.
_Avoid_: Source Type, Migrated Telemetry

**Corpus Exclusion**:
A valid Corpus Decision retained as evidence but ineligible for a named training view, with a stable
reason. It does not weaken corpus integrity.
_Avoid_: Rejection, Invalid Row

**Corpus Rejection**:
Source evidence that cannot safely enter the corpus because its structure, identity, or legal-view
boundary is invalid. Any rejection blocks publication.
_Avoid_: Exclusion, Skipped Row

**Corpus Migration**:
A validated lossless transformation between consecutive corpus schema versions. It preserves source
identity and never invents evidence missing from the older record.
_Avoid_: Compatibility Parser, Best-effort Upgrade

**Supervision Channel**:
The declared authority for an action label: episode behavior, a pinned Ledger evaluation, or a
Human Correction. Channels remain separate even when they select the same action.
_Avoid_: Correct Action, Target Precedence

**Training View**:
A versioned projection of Corpus Decisions for one learning or audit purpose. It owns its
Supervision Channel, targets, and Corpus Exclusions without changing canonical evidence.
_Avoid_: Corpus, Global Eligibility

**Replay Certificate**:
Machine-checkable proof of which evidence in a Corpus Decision reconstructs under its recorded
identities. Evaluation reproduction and full-choice reproduction are certified separately.
_Avoid_: Replay Test, Agreement Flag

**Replay Drift**:
Any change in certified evaluation evidence under matching recorded identities. It is a
reproducibility defect, independent of whether the original valuation was strategically good.
_Avoid_: Evaluation Mismatch, Outcome Error

**Policy Inconsistency**:
A committed Ledger action outside the choice set permitted by its recorded candidate values,
statuses, and Policy Configuration. Forced and fail-safe policy remain explicit permitted cases.
_Avoid_: Replay Drift, Bad Outcome

**Outcome Residual**:
A statistical relationship between Ledger valuation evidence and later Terminal Targets across
comparable Corpus Decisions. One surprising Episode is evidence, never a correctness verdict.
_Avoid_: Wrong Decision, Replay Drift, Loss

**Triage Finding**:
A deterministically ranked pointer to an exact diagnostic defect or a repeated Outcome Residual with
its supporting evidence. It is never a Human Correction or training label.
_Avoid_: Correction, Mismatch Row, Automated Ruling

**Performance Profile**:
A cached detailed timing analysis of one hotspot Corpus Decision under matching recorded identities.
It must preserve the decision's Replay Certificate and is not canonical evidence.
_Avoid_: Decision Timing, Telemetry Span, Benchmark Result

**Terminal Target**:
The complete public Episode result projected to a Corpus Decision's acting seat. Training Views may
derive scalar labels from it without changing the recorded outcome.
_Avoid_: Reward, Target Value, Outcome Join

**Integrity Gate**:
A zero-tolerance invariant deciding whether evidence can enter a Corpus Snapshot. Failure means the
evidence is structurally unsafe, not merely strategically poor.
_Avoid_: Quality Threshold, Health Metric

**Quality Signal**:
A measured property of valid agent evidence, such as disagreement or latency. It becomes unhealthy
only relative to a named Health Profile.
_Avoid_: Integrity Error, Invalid Evidence

**Health Profile**:
A versioned set of Quality Signal thresholds for one experiment or Training View. It controls
readiness or promotion without redefining Canonical Corpus validity.
_Avoid_: Corpus Validator, Global Thresholds

**Off-policy Correction**:
A Correction whose observed decision would not exist after an already-adjudicated correct
predecessor, so it cannot grade the live policy.
_Avoid_: Refuted Correction, wrong ruling
