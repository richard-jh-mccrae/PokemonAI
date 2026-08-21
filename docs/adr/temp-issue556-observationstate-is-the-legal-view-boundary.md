# ADR-TEMP-556 — ObservationState is the legal-view boundary

The Observation State exposes a Position Key that excludes the current question and a Decision Key
that adds the exact question and legal actions. Search reuse therefore identifies equivalent
positions, while telemetry and replay cannot conflate different decisions presented there.

Cross-decision Legal Knowledge enters construction as one frozen record, separate from the engine
printout. The snapshot owns normalized immutable values; mutable trackers and provider-control
metadata never become part of its read surface.

Provider-control data travels in a private typed ProviderState beside the snapshot. Providers keep
engine payloads behind opaque tokens; Ledger evaluation and telemetry receive only the legal-view
snapshot, making the information boundary structural rather than conventional.

ObservationState is a deeply frozen value; a separate ObservationStateBuilder owns raw comparisons,
fingerprints, and piece reuse. Both root and incremental construction return the same value, with
equivalence pinned at the builder seam.

The builder also resolves the offered menu into canonical LegalActions once. Those actions feed the
Decision Key and every provider; no consumer reparses raw select dictionaries.

The canonical package is `common.observation`; the narrower `common.board.BoardState` name retires
without a permanent compatibility alias.

Static card facts, roles, and valuation parameters live in a separately versioned EvaluationModel.
ObservationState contains live card identities but no pinned card records or weights; replay and
telemetry pair the Decision Key with the Evaluation Model identity.

Telemetry and learning persist a versioned Observation Record, not an engine dictionary. Its codec
round-trips the legal state, knowledge, prompt, actions, and identities while making hidden zones
unrepresentable.

Raw observations are confined to observation construction, engine-provider internals,
deck-submission handling, and last-resort crash fallback. Runtime policy, scouting, deck tracking,
action enumeration, Ledger, and telemetry use typed state; an automated boundary gate enforces it.

Malformed boundary structure and incomplete in-play bodies raise a typed construction error caught
by the runtime fallback. Optional provider fields retain their documented neutral defaults.

Knowledge advancement is pure. The builder first returns an immutable base ObservationState;
deck, lock, and scouting reducers read that state and return the next LegalKnowledge; attaching it
produces the final state and identities. The base state never crosses the runtime boundary.

LegalKnowledge stores an immutable evidence-level OpponentBelief, not the current Ledger's resolved
roles or weights. Evaluation Models interpret the same evidence independently.

Construction is allow-list based: it copies only declared legal fields and never preserves a generic
raw subtree. Hostile full-truth inputs and Observation Record tests prove hidden opponent zones and
deck order are unrepresentable.

The migration is behavior-neutral on the valid observations pinned by the pre-existing suite and
Ledger corpus. Malformed inputs may instead take the explicit construction-error fallback;
valuation corrections become separate work.

Engine logs become a frozen union of validated Observation Event variants. An unknown future event
keeps only safe common metadata and invalidates affected Legal Knowledge; no raw log payload enters
state. The viewer remains fixed to the root player through simulated successors, while the acting
side stays in ProviderState.

Observation Events do not enter Position or Decision Keys after their consequences are reduced.
Observation Records retain them for audit, while versioned Transition Traces retain complete action
sequences for learning. Learned commutativity may order or propose branches; only exact state
equivalence or a symbolic independence proof authorizes pruning.

Tracking Serials remain in Observation Records and reducer inputs but never directly enter either
key. Semantic projections retain every consequence attached to an instance, such as a body-specific
attack lock or known-top card order, while ignoring arbitrary engine numbering.

Incremental construction returns an ObservationDelta beside the immutable state. Parent-relative
change metadata can guide later evaluator reuse and Transition Trace analysis but never enters state
equality, keys, or Observation Records; #583 owns consuming that optimization seam.

ObservationDelta reports typed hierarchical parts, including individual bodies, zones, allowances,
knowledge, and prompts. Consumers subscribe to semantic part families rather than raw engine fields.

Builders are stateless over branch-local provider capsules, and simulated successors run the same
pure knowledge reducers as roots. Keys include their semantic-schema version and hash canonical
actions independently of engine menu order.

Primary policy and value models are functions of ObservationState and EvaluationModel only. Any
history with strategic force must reduce into LegalKnowledge; Transition Trace models may propose
commutative ordering but never assign value or authorize pruning.

Legally hidden or unresolved carried knowledge uses domain-specific closed variants rather than
None, empty collections, or a generic unknown wrapper. Each variant preserves the exact knowledge
available, including legally known counts and partial or ordered knowledge.

OpponentBelief probabilities are canonical fixed-point values whose precision belongs to the
versioned state schema. Position Keys hash the complete canonical belief, and Evaluation Models
consume those same stored values; raw floats and key-only rounding are forbidden.

#556 defines the minimal Transition Trace vocabulary but does not emit traces. #583 owns emission
because it owns public action, successor, evaluator, and policy contracts; training and pruning are
later work.

Verification combines builder root/advance equivalence, deep-immutability and record round trips,
metamorphic key sensitivity/invariance, hostile hidden-zone inputs, a raw-access boundary gate, and
valid-corpus decision parity. Performance uses paired benchmark evidence plus structural reuse tests,
not flaky wall-clock CI assertions.

Implementation evidence on 2026-08-21: `python tools/observation_bench.py --steps 300`
reported 2.189 ms/root and 1.612 ms/incremental (1.4×), zero root/advance mismatches over
301 snapshots, and 1.600 changed semantic parts per edge. The benchmark is evidence only;
CI pins reuse, equivalence, and corpus behavior structurally.
