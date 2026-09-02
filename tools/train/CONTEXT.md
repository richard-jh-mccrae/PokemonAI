# Training evidence and the Ledger's rounds

Human Corrections are the evidence base. The Ledger's manual training rounds (plan §7,
ADR-0147/0148) tune its closed Valuation Configuration against them; the quarantined Bellman teacher keeps them
as its frozen acceptance evidence (ADR-0149).

- `blunder/`: correction schema, replay decisions, labels, provenance, telemetry joins, and storage.
- `saved_moment.py`: shared episode/frame resolver across replay, Correction, and fixture storage;
  frame viewers and experiment tooling consume this seam instead of owning loaders.
- `bellman_corpus.py`: reruns Mega Starmie Corrections through the Bellman teacher
  (`deprecated.bellman.build_teacher_runtime`, ADR-0149).
- `bellman_adjudicate.py`: classifies the unfiltered corpus against written rationales.
- `ledger_corpus.py`: the Ledger's training dashboard — every deck's Corrections through the live
  runtime; per-deck agreement, the generality floor, misses with their rationales, gap census,
  regressions vs a prior baseline (ADR-0145); prize-anchor stamping + retired rulings (ADR-0147).
- `corpus/`: hashed Episode Bundles, immutable Canonical Corpus publication, and Training Views.
- `ledger_certify.py`, `ledger_baseline.py`: certify and freeze one three-Deck Ledger Baseline.
- `ledger_tune.py`: the §7 nudge / keep-best / adoption-gate loop over the Ledger's general
  Valuation Configuration; every trial lands in `docs/tuning/runs/`.

Deck behavior changes in shared runtime code or declarative deck Roles, not generated `tuned.json`.

## Language

**Corpus Decision**:
One agent choice point retained with its complete legal alternatives and a terminal label or explicit
exclusion. Action-level examples and diagnostic reports are derived views.
_Avoid_: Training Row, Action Sample, Episode Sample

**Atomic Decision Margin**:
The ruled candidate's Search Value minus the committed candidate's Search Value at one actual
Decision Record. It localizes a wrong play, discard, fetch, promotion, or other presented choice.
_Avoid_: Compound Decision Margin, outcome reward, agreement flag

**Compound Decision Margin**:
The ruled root candidate's Search Value minus the committed root candidate's after their complete
Action Paths are resolved. It grades whether beginning the whole action was strategically sound.
_Avoid_: Atomic Decision Margin, turn plan, hidden rollout value

**Pairwise Value Audit**:
A complete contrast between the ruled and committed candidates: Search Values, Decision Deltas,
resolved Action Paths, feature activations, coefficients, contribution differences, provenance, and
break-even sensitivity. It preserves the human ruling as a relative preference and classifies the
cause as transition, coverage, activation equation, coefficient seed, portfolio constraint, or
search completeness; it does not invent an absolute target score.
_Avoid_: score target, rank-only report, unexplained weight change

**Value Audit Artifact**:
The canonical machine-readable output of Pairwise Value Audits for a correction run. CLI reports
and the correction UI consume it; CI validates its contract and gates the underlying readiness
report rather than recomputing correction scores.
_Avoid_: UI-only audit, console-only audit, independently computed report

**Correction Severity**:
A reviewer-supplied triage signal used to order investigation and reports. It does not multiply the
pairwise training loss unless later evidence establishes a calibrated confidence model.
_Avoid_: preference strength, target margin, loss weight

**Correction Locus**:
The exact Decision Record on which the reviewer places a correction. It identifies where the
blunder is believed to occur: initiating action, discard, fetch, promotion, or another prompt. Its
preference label does not propagate backward to an earlier decision; downstream required choices
may still be resolved to value each candidate through its return to MAIN.
_Avoid_: inferred root correction, blame propagation, whole-turn label

**Ledger-Best Continuation**:
The highest-valued complete legal resolution from a corrected candidate through any remaining
required non-MAIN prompts to its first return to MAIN or turn end. A Pairwise Value Audit exposes
this path; later corrections do not silently replace it during grading.
_Avoid_: correction-forced continuation, hidden oracle path, independent MAIN continuation

**Calibration Proposal**:
A non-mutating recommendation derived from a Pairwise Value Audit. It identifies the smallest
equation or coefficient-seed change and its break-even range, but requires review before changing
Ledger behavior. Automatic fitting begins only with a sufficiently large, structurally clean corpus.
_Avoid_: automatic weight rewrite, unreviewed tuning, correction-specific patch

**Correction Non-Regression Constraint**:
An accepted pairwise preference that every Calibration Proposal must preserve. Conflicting
constraints are reported as a minimal conflicting set and require equation or feature work, or an
explicitly superseded correction; aggregate accuracy cannot conceal a flipped correction.
_Avoid_: soft historical example, silent regression, latest-correction-wins

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
publication consumes complete Episode Bundles and never mutates them during an Episode.
_Avoid_: Corpus Decision, Replay File, Live Corpus Row

**Correction Run**:
A bounded, manifested batch of Episodes with one focal Deck in every Episode and a reproducible
randomized opponent plan, produced for human Ledger review. It stages Episode Bundles but is
neither a Benchmark nor a Corpus Snapshot.
_Avoid_: Self-play Corpus, Strategy Benchmark, Corpus Run

**Correction Corpus Manifest**:
The immutable identity of the Human Corrections and their review dispositions used to compare
Ledger behavior across revisions.
_Avoid_: Correction Run, Corpus Snapshot, mutable corrections directory

**Baseline Candidate**:
One fixed Ledger behavior and evidence set awaiting review, held-out evaluation, and certification.
Any behavior change creates a new candidate.
_Avoid_: Ledger Baseline, working tree, latest Ledger

**Baseline Review**:
The complete reviewer verdict set covering every tuning Decision Record in a Baseline Candidate.
It references decision evidence without copying or replacing it.
_Avoid_: Correction count, corpus dashboard, Held-Out Evaluation

**Held-Out Partition**:
Episodes selected before a Correction Run starts and unavailable to tuning until its Baseline
Candidate locks. Reusing their findings for tuning requires a new candidate and fresh partition.
_Avoid_: deferred Correction, tuning split, hidden engine state

**Ledger Baseline**:
One immutable identity joining one-ply Ledger behavior, source and Deck definitions, Corrections
evidence, a held-out manifest, and the tests that certified them. Later experiments name this
identity; a newly found blunder never silently changes it. Freeze requires the current clean source
and all three authoritative Decks. During search experiments, new blunders are record-only; any
retune creates a new Baseline version.
_Avoid_: Commit Hash, Latest Ledger, Mutable Baseline

**Corpus Origin**:
The provenance boundary distinguishing evidence recorded during play from evidence reconstructed by
offline replay evaluation. Reconstructed output never claims to be historical runtime behavior.
_Avoid_: Source Type, Migrated Telemetry

**Corpus Exclusion**:
A valid Corpus Decision retained as evidence but ineligible for a named training view, with a stable
reason. It does not weaken corpus integrity.
_Avoid_: Rejection, Invalid Row

**Corpus Rejection**:
Source evidence that cannot safely enter the corpus because structure, identity, legal-view, or
mandatory replay certification is unresolved or invalid. Any rejection blocks publication.
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
