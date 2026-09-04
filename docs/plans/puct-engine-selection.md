# PUCT engine selection

Implementation specification, prepared 2026-09-04 after bounded PUCT merged.

## Current state

`PuctSearch` already consumes a provider rather than an engine. Both
`NativeTurnSearchProvider` and CGPy's `TurnSearchEnvironment` satisfy the operational shape used by
the search: root, legal actions, chance plans, transitions or worker jobs, Ledger state, reuse, and
cleanup. Native PUCT reaches the legal-view projection through `LedgerNativeProvider`; CGPy's exact
environment owns an independent fixed-seat renderer.

This is not yet runtime-selectable. `AgentRuntime` always constructs `LedgerDecider`, the PUCT
coordinator accepts a caller-written provider identity, and its two provider constructors require
different inputs. Native replay accepts a legal observation. The exact CGPy environment requires an
owned engine or snapshot. The existing `CG_ENGINE=py` alias can make the replay adapter execute
through CGPy's compatible `cg.api`, but the provider identity and runtime configuration do not record
that choice.

The providers also stop at different End states. Native replay observes the opponent's next-turn draw
before returning a projected turn-boundary leaf. CGPy's exact environment stops before `begin_turn`.
Both hide the card identity, but their public deck and hand counts differ. PUCT evaluates boundary
leaves, so this difference can change a decision.

## Required design

Add a typed engine choice with values `native-cg` and `cgpy`. Resolve it once when the agent process
starts. Unsupported values and unavailable engines fail explicitly. The choice, adapter identity,
and engine implementation identity become part of the PUCT behavior identity and every decision
record.

Define the provider protocol in `common.decision.turn`. It must name the operations PUCT actually
uses, including ownership and cleanup. `PuctSearch` should depend on this protocol instead of probing
for optional methods. If direct and worker-backed execution remain distinct, model them as two typed
protocol variants and reject incomplete implementations at construction.

Use one observation-root replay adapter for live decisions. Replace the provider's implicit
`from cg import api` with a serializable backend descriptor containing the API module path and
implementation identity. Put that descriptor on every transition and refresh `ProviderJob`.
Spawned workers must resolve the descriptor before importing an engine; parent-process
`sys.modules` aliases do not cross the `spawn` boundary. The native choice names the checked-in
native API. The CGPy process entry point supplies its compatibility API module path without adding a
CGPy import or literal dependency to shipped `common` source. Derive provider identity from the
resolved descriptor and reject a mismatched module identity. This keeps root reconstruction,
hidden-zone predictions, projection, horizon, worker accounting, and failure behavior identical
across engines. Preserve `TurnSearchEnvironment` for exact CGPy roots, snapshots, parity, and offline
tests; it does not reconstruct a live observation.

Make the post-`begin_turn` projected observation the canonical End boundary, matching native engine
behavior. CGPy must execute the draw, then project the result to the fixed focal seat before exposing
the boundary node. The opponent card identity, private prompt, hidden hand, and actor-only events must
never enter the observation, keys, evaluator, priors, or record. Public hand and deck counts must match
native behavior.

Add an immutable `DecisionSearchConfiguration` passed through `build_runtime` into `AgentRuntime`.
It contains `route` (`ledger` or `puct`), `puct_backend` (`native-cg` or `cgpy`), `prior_mode`, the
named PUCT profile and limits, and the Ledger baseline identity, manifest path, and calibration path.
Validate the complete PUCT configuration at runtime construction. `make_agent` reads
`AGENT_DECISION_ROUTE` and `PUCT_ENGINE_BACKEND`; defaults are `ledger` and `native-cg`. Artifact and
profile inputs come from the deck's checked-in runtime configuration, with environment overrides
reserved for tests and tools. `CG_ENGINE=py` continues to select the surrounding simulation engine;
it never implies or overrides `PUCT_ENGINE_BACKEND`. Production rejects `puct_backend=cgpy` when the
CGPy package is absent.

The PUCT route owns one persistent `PuctSearch` for verified reuse, creates the selected provider
from each raw observation and typed `ObservationState`, converts the coordinator's chosen
`TurnAction.selection` to `RootDecision`, emits the PUCT decision record, and resets retained trees
at match boundaries and failures. The existing one-ply route remains separately identified until
PUCT becomes the default.

Do not silently fall back between engines, from PUCT to one-ply, or from direct CGPy state to replay
reconstruction. Each failure must identify its stage and selected backend. Existing PUCT policy and
value configuration stays engine-independent.

## Acceptance

- A shared provider contract suite passes for native replay, CGPy compatibility replay, and the exact
  CGPy environment where their root inputs overlap.
- The same observation, seed, configuration, and public chance outcomes produce the same legal root
  roster, End boundary, action, and backend-independent PUCT evidence on native and CGPy.
- Changing only the opponent's drawn card identity or private prompt leaves every focal observation
  key, valuation input, prior input, chosen action, and serialized public record unchanged.
- End executes the opponent draw in both engines, exposes matching public counts, and exposes no card
  identity or opponent menu.
- Engine selection, identity, unavailable-backend failure, cleanup, chance sampling, and tree reuse
  have focused tests. Transition and refresh jobs prove that each spawned worker loads the selected
  backend. Full native and CGPy match tests exercise the runtime route.
- Existing correction expectations and Ledger weights remain unchanged. Any choice regression is
  investigated as a search or parity change rather than absorbed by retuning.
