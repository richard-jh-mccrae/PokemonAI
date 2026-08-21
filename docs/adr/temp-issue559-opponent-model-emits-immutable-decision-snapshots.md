# ADR-TEMP-559 — The Opponent Model emits immutable decision snapshots

Status: Accepted and BUILT (2026-08-22).

ADR-0047's match-scoped Opponent Model remains the single owner and write seam for opponent
knowledge. It updates from each observation and emits an immutable `OpponentSnapshot` for that
decision; runtime, Ledger, and telemetry consume only that snapshot, never the mutable owner.

This extends ADR-0047 for the Ledger architecture and subsumes ADR-0148's `OpponentLayer`. A single
mutable facade was rejected because update timing would become part of every consumer contract.
Expanding `OpponentLayer` while leaving Scout and Brief state in runtime was rejected because it
would preserve the scattered write ownership that ADR-0047 forbids.

The model owns knowledge only. Ledger coefficients remain under Issue #582, runtime routing under
Issue #584, and telemetry schema/emission under Issue #585.

The unread `opponent_properties.json` bag does not survive. Each key is classified: mechanics
derivable from card data become card facts, prescriptive claims become Opponent Strategy, obsolete
claims are deleted, and only non-derivable archetype beliefs become typed `OpponentTrait` values in
the snapshot's belief channel. Generic string lookup and untyped property mappings are retired.

The snapshot preserves every bounded Scout candidate as a candidate-conditioned `ArchetypeBelief`,
plus unknown mass. Each candidate keeps its probability and compiled descriptive claims. The model
does not collapse to the leading candidate, pre-aggregate feature probabilities, apply a confidence
threshold, or emit `posture_gamma`; Issue #582's canonical configuration owns how belief changes
valuation. Candidate conditioning preserves correlations and makes telemetry reproducible.

Hidden information is blocked before the model. A typed `OpponentEvidence` is built from the public
`BoardState` fields and an allowlisted projection of public events; hidden hand contents and deck
order are unrepresentable. Scout and Opponent Model consume this type, never a raw observation.
Snapshot serialization therefore starts from legal-view data, while Issue #585 still owns the final
telemetry schema and leak gates.

Configuration and knowledge artifacts validate eagerly: invalid schemas, vocabulary, probabilities,
or canonical configuration fail startup and tests. A live observation failure instead yields a typed
degraded snapshot containing every unaffected observed fact plus explicit subsystem failures; failed
belief claims are absent. Strict offline/test mode re-raises the same failure. Broad exception-to-empty
conversion and silently skipped Briefs are rejected because they hide defects and corrupt training.

An Archetype Belief may attach only the one canonical, descriptive `PokemonRole` vocabulary owned by
Issue #582. The vocabulary is shared by both sides and carries no coefficients in the snapshot.
Target directives such as `disruption_target` and `avoid` are Opponent Strategy; intrinsic mechanics
such as gust and snipe are Card Functions. Keeping one expansive role soup or separate own/opponent
role vocabularies was rejected because both preserve the semantic and weighting mismatches this work
must remove.

The legacy property audit retains only irreducible qualitative beliefs: tempo, opening fragility,
heal-wall behaviour, setup dependencies, and deck-out vulnerability. Engine and acceleration
dependency collapse into one relation parameterized by canonical `PokemonRole`. Claims about
immunity, damage caps, piercing, hand-size attacks, prize class, energy composition, mobility,
spread, Item lock, and comeback cards derive from the candidate deck and Card Functions instead of
being authored twice. Prescriptive consequences remain Opponent Strategy.

The model folds public log deltas into a bounded, typed current/previous-turn event timeline.
Snapshots expose current public resource counts, exact interval deltas, KOs, and visible movements
with provenance. Heuristic labels and rates such as `last_turn_dumped` and `deckout_in_turns` do not
masquerade as observations; probabilistic resource claims stay candidate-conditioned beliefs.

The owner has a true match lifetime: the protocol match-start constructs a fresh `OpponentModel`
from an immutable, eagerly validated knowledge base. Turn rollback is not a reset heuristic. The
snapshot exposes canonical, deterministically ordered public data and an identity hash; Issue #585
owns the versioned wire schema and JSON emission rather than the model serializing itself.

ADR-0149 keeps the Bellman teacher frozen behind the one-way `deprecated/` boundary. Its legacy
`resolve_scouted_role_worth`/`opponent_role_worth` path and shared Worth currency move into that
quarantine through Issue #555; no Bellman compatibility resolver remains in live `src/`, and the
teacher does not widen the live snapshot contract.

The mutable Scouting `Read` retires. Scout becomes an internal inference subsystem whose output is
normalized immediately into candidate-conditioned Archetype Beliefs; `OpponentSnapshot` is the only
public read surface. Runtime `last_read`/`last_brief`, `posture_gamma`, top-only Brief matching, and
telemetry's separate `read=` hand-off retire with it.

Issue #582's canonical role/configuration contract lands before Issue #559. Issue #559 then builds
directly on final vocabulary and threshold types; it does not mint provisional adapters. Issue #555
retires displaced legacy code, followed by Issue #584's complete routing and Issue #585's wire schema.

An immutable, validated knowledge base compiles archetype profiles once. Snapshots hold immutable
profile values for their bounded candidates, so Ledger has one read surface without copying static
profile data or performing a second ID-to-profile lookup. Canonical output identifies the knowledge
base/profile version and hash.
