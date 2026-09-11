# ADR-TEMP-676 — Component compatibility is declared and validated

Each evaluator, policy model, search algorithm, and decision policy exposes an immutable Component
Contract declaring inputs, outputs, configuration, value semantics, and optional capabilities. The
Decision Coordinator rejects static incompatibility at assembly and validates dynamic identity, scale,
perspective, roster, coverage, and evidence claims at request/result boundaries; the accepted cost is
additional descriptor types and coordinated conformance tests.

Lifecycle, snapshot, and reuse remain granular opt-in capability protocols. Core component contracts
stay usable by stateless implementations without placeholder methods or fabricated retained state.

Each Search Algorithm declares required and optional collaborators, and the Decision Coordinator injects
only compatible dependencies through the existing composition seam. Algorithms do not receive no-op policy,
provider, or lifecycle objects; #557 and #677 retain ownership of their detailed capability boundaries.

Dedicated strict static checking covers neutral contracts, the coordinator, representative Ledger/PUCT
adapters, and an independent conformance implementation. Runtime tests cover value-dependent invariants;
`Any`, bare `object`, and permissive import skipping cannot stand in for compatibility at this seam.

The conformance implementation is a test-only executable search: it consumes Observation State and a typed
evaluator, constructs the proven roster and candidate evidence, and exercises permitting and non-permitting
outcomes through the coordinator without Policy Model, provider, lifecycle, or PUCT dependencies.

Neutral contracts split by ownership inside `common/decision/`: identity, values, outcomes, statistics,
components, and results. `contracts.py` and package exports remain compatibility facades; import gates keep
algorithm packages out of neutral modules and no parallel `decision/v2` model exists.

The Issue #611 legacy contract module is retired from shipped source. Test-only comparison fixtures remain
outside the package while downstream parity coverage finishes; active runtime imports no projection facade,
neutral modules neither expose old fields nor accept old objects, and import gates prevent re-entry.

Lifecycle, reuse, snapshot, and cleanup are separate opt-in capability protocols. Retained state stays opaque
outside its owner and carries typed Reuse Provenance over every behavior-affecting semantic input; the owner
returns an explicit verdict, and missing capability or proof always selects fresh execution. #677 and #562
retain ownership of lifecycle mechanics and saved-root provenance respectively.

Components declare stable identities and accepted configuration identities. Runtime supplies a typed resolved
Behavior Identity aggregate, which the coordinator verifies against actual injection and carries into results
and reuse provenance. Missing optional policy models, providers, fail-safe policies, and prize plans use explicit
namespaced absence identities rather than empty strings; #678 retains ownership of canonical recipe construction
and resolution.
