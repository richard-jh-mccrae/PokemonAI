# Search successor legal-view fix

Implementation specification, prepared 2026-09-02 against
`a02c74c5ef2039b77eae05b9dee33964630acda7`. Implemented on
`codex/fix-search-successor-legal-view`; final validation recorded below.

The exhaustive Within-Horizon Teacher and its timing gate were retired after bounded PUCT landed.
Teacher references below describe the historical investigation; the privacy boundary remains live
because native PUCT uses `LedgerNativeProvider`.

## Problem and scope

Search successors can contain the opponent's private information inside the focal player's
`ObservationState`. The native adapter hides hands but retains actor-view logs and prompts.
The direct CGPy one-ply adapter renders focal-view logs correctly but retains the opponent's prompt.
This violates the existing legal-view boundary even when the current evaluator ignores those fields.

Fix application-owned projection, forced-choice traversal, and record validation. Keep native and
CGPy one-ply observations consistent about visibility. Preserve each caller's current search horizon.
Do not modify native `cg` source/binaries, retune Ledger weights, change scouting predictions, or
rewrite correction expectations in this change.

The earlier statement that this was exclusively a native-adapter defect was too broad. There is also
a CGPy one-ply prompt leak. There is no demonstrated path from simulated successors back into live
opponent scouting, and no demonstrated ability to predict the real opponent's next card.

## Verified behavior before the fix

| Path | End successor | Opponent draw identity | Opponent prompt |
| --- | --- | --- | --- |
| Native `LedgerNativeProvider` | Next turn, after draw | Leaks through events | Retained |
| Direct `LedgerCgpyProvider` | Next turn, after draw | Correct reverse event, identity hidden | Retained |
| CGPy `TurnSearchEnvironment` | Before next `begin_turn` | No next-turn draw performed | Suppressed |

The ordinary CGPy engine does perform the next-turn draw. The environment's earlier stopping point is
an explicit environment hook, not the meaning of End throughout CGPy. Advancing a simulator past
a draw is legal; exposing the unseen identity to the other player's evaluation is the defect.

### Measurements

Investigation used Windows, Python 3.11.9, and the checked-in native DLL with SHA-256
`c7c87eb76513784b0089b02dcf9d57466a1b0b2217df4cfc9af8c74deda3969f`.
These are dated observations, not claims about all engines or all historical decisions.

1. With one unchanged native root token, substituting supplied opponent deck predictions consisting
   of card 3 versus card 6 changed the returned draw to 3 versus 6. `SearchBegin` used the supplied
   hypothetical world. This experiment does not establish disclosure of the live game's deck order.
2. Native End probes covered both focal seats. The adapter returned `HiddenHand` for the opponent,
   but retained `DRAW` with opponent `cardId=1031` and `serial`, plus six/eight opponent actions.
   Both `ObservationRecord` round trips and telemetry successor serialization preserved the draw.
3. Redacting the leaked draw changed `valuation_key`; deleting the menu changed `decision_key`.
   In these two cases, Ledger totals stayed `9.69087930515986` and `10.57214007352941` when the draw
   identities or menus were removed separately. A numeric scoring exploit was not demonstrated.
4. A CGPy scenario reproduced End retaining an opponent prompt while emitting identity-free
   `DRAW_REVERSE`. A separate constructed opponent deck-search prompt passed two private deck cards
   into typed `select.deck`; its `looking` field was correctly masked. This second probe exercises
   the production binding seam with a synthetic pending selection, not a completed live card effect.
5. A constructed native SWITCH prompt with source actor 0 and target card owner 1 made `_actor_seat`
   return 1. The native API explicitly defines option `playerIndex` as card ownership, and
   `current.yourIndex` as selection actor. Target ownership is not a valid actor detector.
6. Existing focused tests all passed despite these failures: **118 passed in 34.55 seconds**:

   ```text
   python -m pytest tests/common/test_native_engine.py tests/ledger/test_seam.py tests/observation tests/opponent tests/parity/test_turn_search_environment.py -q
   ```

## Cause and existing owners

- [Native provider](../../src/common/native_engine.py): `transition` forces an opponent actor after
  End; `_actor_seat` also guesses from target ownership. `_observation` rewrites the viewer and masks
  hands/prizes, but copies logs, `looking`, and `select`. These are separate visibility channels.
- [CGPy provider](../../src/common/engine.py): `_state_from_engine` requests the focal viewer, then
  binds the result. [Rendering](../../src/cgpy/render.py) masks hands and looking and drains that
  viewer's log outbox, but `select_dict` renders the current pending selection regardless of viewer.
  The [CGPy compatibility API](../../src/cgpy/compat/api.py) instead returns an actor-view search
  result, so it also needs coverage through the native-style adapter.
- [Preview binding](../../src/common/ledger/seam.py): `PreviewBinding._bind` builds the typed child
  immediately. [Observation construction](../../src/common/observation/state.py) permits common
  event field names without checking event audience; it also accepts prompts without actor gating.
  Masking `them.hand` does not sanitize those other fields.
- [Provider state](../../src/common/observation/provider.py) correctly owns private engine metadata,
  but `legal_actions` currently forwards the focal observation's menu for every actor.
  [Preview traversal](../../src/common/ledger/preview.py) uses `board.select` both for evaluation
  input and forced-control flow. Simply deleting an opponent prompt would misclassify a forced
  continuation as MAIN and could incorrectly mark an unfinished action complete.
- [Records](../../src/common/observation/record.py) validate hand shape and frozen structure, not
  event visibility. [Telemetry](../../src/common/telemetry/core.py) consequently persists the leak.
  Valuation keys include events/actions, so the leak also changes cache identity before scoring.
- [Runtime](../../src/common/runtime.py) calls `_observe_matchup` on live observations.
  [Opponent evidence](../../src/common/opponent/model.py) scores revealed board/discard/attached
  cards; its timeline can copy event fields. Preview binding does not call this runtime update.
  Preserve that separation and test it, rather than changing scouting's inference algorithm.

Extend these owners. A small shared projection module under `common.observation` is appropriate;
it must be called by the existing builders/providers, not become a parallel observation system.

## Required information contract

The perspective remains the root seat throughout a search. Keep three facts distinct:
the focal seat, the source viewer of an engine printout, and the actor of a pending selection.

For native nonterminal search results, capture the original `current.yourIndex` before projection
as source viewer and selection actor. For direct CGPy results, the source viewer is the requested
viewer and the actor comes from `engine.select_seat`. Terminal results need no pending actor.
Missing or contradictory required metadata produces an explicit unavailable transition.
Remove actor guesses based on option owners, MAIN, turn parity, or the preceding action being End.
End can lead to intervening forced effects; it is not sufficient evidence of the next actor.

Private engine state, opaque search tokens, raw actor prompts, hidden-world signatures, and
unobserved cards remain inside provider-owned state/maps. They must not enter `ObservationState`,
`LegalKnowledge`, valuation inputs, public keys, continuation-policy keys, or persisted traces.

Given two successors whose legally observable facts are identical and whose only difference is
an unseen opponent card, their focal observations, public keys, serialized records, valuations,
and public candidate decisions must be identical. Private engine tokens may differ. This does not
require equality after a simulated effect actually reveals a card or changes a public outcome.

Hypothetical future information the focal player would legally acquire can be represented in that
simulated branch. It must never be promoted into the live root's knowledge or opponent evidence.

## Projection design

### One projection before construction

Project raw successors before `ObservationStateBuilder.advance`, knowledge reduction, action
enumeration, delta fingerprints, cache-key computation, or telemetry. Use the same event rules for
root construction and persisted-state validation where the necessary audience facts are available.
The projection is pure: do not mutate the parent, sibling observations, or engine search state.

Capture source viewer and control metadata before rewriting `yourIndex`. Preserve the existing
single-world preview policy, native session lifetime, and opaque per-successor token scheme.

### Hands, prizes, looking, and prompts

- Opponent hands expose counts only. Face-down prizes expose counts only. Never reconstruct them
  from predictions for the evaluator. Retain legally acquired own-prize knowledge separately.
- Preserve a faithful focal hand. When the actor-view printout hides it, carry the parent's known
  hand only when the action and available evidence establish it stayed unchanged, or apply a
  provable legal update. Equal hand counts alone do not prove equal contents. Do not infer a newly
  drawn identity from a predicted deck or a count delta. If a faithful view cannot be recovered,
  return unavailable instead of fabricating an empty, stale, or predicted hand.
- Preserve focal-view `looking`. For an opponent's private look, retain only its public count.
  Cross-view native data with no proven focal visibility must not disclose its cards. Public reveal
  support requires explicit engine/event evidence, not a guessed owner or a card's presence in a
  determinized world.
- `ObservationState.select` and `legal_actions` describe only a choice offered to the focal player.
  At an opponent selection, set them to `None` and `()`. This includes `select.deck`, `effect`,
  `contextCard`, action identities, option counts, and hand indices embedded in the prompt.
  Public played-card/effect facts remain available through public board/events.
- Preserve legitimate focal prompts exactly, including own deck searches and legally revealed
  opposing cards. A blanket ban on cards owned by the opponent would erase legal information.

### Events

Replace the broad common-field copier with explicit per-kind fields and audience-aware projection
based on the [engine log contract](../../src/cg/api.py). Keep the existing typed event classes.

- Convert an opponent `DRAW` to `DRAW_REVERSE`, with player identity but no card identity or serial.
  Focal draws retain legally observed identity. Reverse draw events never retain padded identities.
- Reverse movement events never expose identity. Public movement, attacks, damage, switches,
  attachments, evolution, statuses, turn markers, and results retain their documented public fields.
- Full movement visibility cannot be determined from card ownership alone. A revealed deck search
  may publicly move a card between otherwise hidden zones. Preserve it when the engine supplied
  a genuine focal-view event. For cross-view native events, preserve identity only with explicit
  public evidence, such as a face-up public source/destination. If a full hidden-zone movement's
  focal audience cannot be established, return unavailable; do not call it public or silently lose
  strategically relevant legal information. Explicit private movements can use the reverse form.
- Unknown event kinds retain only the unknown-kind marker, without arbitrary card fields or raw
  payloads. Keep existing conservative knowledge invalidation. Do not introduce a general
  field-name fallback that can admit private fields added by a future engine.
- Normalize absent/padded fields consistently between engine dialects. Do not remove identity from
  every event: positive tests must preserve legal public card reveals and the focal player's draws.

## Forced choices and boundaries

Keep raw pending control in the provider. Add a typed provider control descriptor containing actor,
selection context, and visibility classification. It is separate from `ObservationState` and never
serialized as a legal observation. Extend the existing provider seam to expose this descriptor;
providers continue to own action enumeration, without raw menu parsing in Ledger traversal.

Adapt `_PreviewWalk.deterministic` to distinguish these cases explicitly:

| Pending control | Required behavior |
| --- | --- |
| Focal choice | Existing focal menu traversal and continuation policy |
| Opponent MAIN at existing one-ply horizon | Evaluate sanitized leaf; mark turn ended |
| Supported public opponent forced choice | Resolve using public actions and existing opponent-choice policy |
| Private/unsupported opponent forced choice | `Unknown` -> `EvaluationStatus.UNAVAILABLE` |
| Real terminal result | Evaluate sanitized terminal outcome |
| Engine manual coin | Existing chance mechanism, processed before private-prompt rejection |

Initially support opponent active promotion (`TO_ACTIVE`) when every option resolves to an already
face-up public bench card and the roster is determined by public state. Other opponent forced
contexts require an explicit visibility rule and regression fixture before being supported; default
to unavailable. A public-looking subset of a private menu is not sufficient evidence that the full
roster, omitted options, or choice constraints are public.

Provider `actions(state)` may expose only focal actions or a certified public opponent roster.
Keep action-to-engine-selection mapping private. Public opponent choices use existing minimization
and budgets, with valuation from the focal view. They must not invoke focal hand-spend/opportunity
accounting on a fabricated opponent `board.select`, or populate the focal continuation-policy cache.
Only public identities may appear in their traces. Do not enumerate private opponent choices under
opaque labels: choice count and branch-conditioned scoring can themselves leak information.

Projection failure must preserve the existing explicit unavailable-candidate/fallback reporting;
it must not silently become a complete result, disappear from candidate accounting, or expose raw
payloads in error strings. A sanitized parent fallback is diagnostic, not a claimed successor value.

PUCT backend selection now aligns exact CGPy and native replay at the post-draw public turn boundary.

## Records, identities, and compatibility

Run the same legal-event validation from both `ObservationRecord.from_state` and `to_state`.
Reject a typed record containing a foreign full draw, sensitive fields on reverse events, or non-null
fields not allowed for that kind. Accept harmless legacy null padding without treating it as evidence.
Validate prompt audience at provider binding while actor metadata exists.
Also exercise direct record construction and telemetry; construction through the builder alone is
not sufficient coverage.

Keep the current structural observation schema version: this fix does not add persisted fields or
move actor/control metadata into the observation. Valid legacy records remain readable. Invalid
event-bearing records fail explicitly on legal ingestion; do not silently sanitize archived evidence.
Legacy records lack actor provenance, so their codec alone cannot certify whether an old retained
menu was private. Regenerate affected search outputs for use as corrected targets; do not claim all
historical records have been audited. Raw archival inspection remains a separate diagnostic activity.

Bump `LedgerNativeProvider.version` and `LedgerCgpyProvider.version` from 2 to 3, so existing provider
descriptors/behavior identities distinguish the fix. Preserve the EvaluationModel/weight identity.
Affected valuation and decision keys will change because their inputs are corrected; do not special
case the hashing to hide those changes. Keep private belief and search tokens out of public caches.

Capture an unchanged-weight correction replay before implementation and compare after the fix.
Classify changed decisions as visibility correction, actor/continuation correction, projection
coverage loss, or an implementation regression. Repair regressions in the implementation. Preserve
the correction gate and report unresolved expectation conflicts; do not edit expected decisions or
retune weights to make the gate green. Weight tuning, if later justified, is a separate task.

## Implementation order and acceptance tests

1. **Reproduce first.** Add engine-independent projection/record tests under `tests/observation` and
   provider integration cases alongside `tests/common/test_native_engine.py` and
   `tests/ledger/test_seam.py`. Keep helper tests outside modules that skip wholesale without native
   binaries. Do not commit live root tokens as universal fixtures; create valid native roots through
   the existing battle harness, with bounded setup, explicit failure, and guaranteed cleanup.
2. **Separate control.** Extend `ProviderState`, preview binding, and both providers. Capture actual
   source/actor metadata; remove target-owner/End overrides. Update traversal before removing menus,
   so private forced choices cannot accidentally count as completed turns.
3. **Project and validate.** Implement shared audience-aware projection and per-kind event rules;
   enforce them before construction and at record boundaries. Preserve source-specific public
   movement evidence; return explicit gaps where native data cannot support a faithful focal view.
4. **Exercise consumers.** Add end-to-end evaluator/cache/telemetry tests and the scouting-update spy.
   Bump provider versions. Keep packaging/import boundaries intact: shipped shared modules cannot
   import CGPy, and raw engine dictionaries cannot spread into Ledger or opponent-model consumers.
5. **Replay and document.** Run focused contracts, correction replay, then existing relevant CI gates.
   Record changed outcomes and remaining gaps. Update the existing boundary documentation to describe
   the enforcement and provider-only forced controls; use tests for the detailed visibility matrix.

The acceptance matrix must include all of the following:

- **End, both seats:** actual native and direct CGPy one-ply successors retain public next-turn/count
  effects while hiding the draw identity, opponent hand, and entire opponent menu. Repeat through
  the CGPy native-compatible API in its own process. No backend alias can silently satisfy a native test.
- **Hidden-world substitution:** same root and End, same public outcome, different supplied opponent
  draw identities. Compare full typed values, all public keys, record bytes, telemetry successors,
  evaluated values, candidate selection, and continuation-policy/trace output. Include a positive
  control where a genuinely public card change must change the appropriate value/key.
- **Private prompt injection:** hidden opponent deck listing, hand-index actions, looking cards,
  effect/context card fields, and malformed reverse logs. No identity, index, roster fingerprint,
  private choice count, or hidden-derived action label survives. Unsupported forced paths are unavailable.
- **Actor ownership:** focal gust targeting an opposing card remains a focal choice; opponent
  promotion remains an opponent choice. Cover End with an intervening forced choice and manual coin.
- **Public forced continuation:** promotion completes with the existing adversarial choice and
  budget behavior, no opponent prompt in the evaluator and no focal continuation-cache entry.
- **Legal information preservation:** own draws/searches, public played/discarded/revealed cards,
  publicly visible movements and promotion targets survive. Ambiguous cross-view hidden movement
  is unavailable. Equal-count focal hand replacement must not reuse the old hand.
- **Boundary/terminal cases:** attack-triggered turn completion, knockout/prize resolution, deck-out,
  and terminal result preserve public consequences. CGPy `TurnSearchEnvironment` executes the
  opponent draw, exposes public counts, and suppresses its identity and prompt.
- **Isolation and persistence:** siblings do not mutate each other; projection precedes incremental
  fingerprints; record ingress and egress reject illegal typed events; telemetry cannot bypass the
  validator. Failed projections still release native sessions and emit only safe diagnostics.
- **Scouting isolation:** searching does not increase live opponent-model update count, change its
  posterior/revealed cards/timeline, or replace root legal knowledge. Live public evidence still updates it.
- **Compatibility:** valid legacy records round-trip; roots unaffected by projection/event
  normalization stay stable. Account explicitly for benign normalization changes. Invalid legacy
  draw records fail; provider identities change; model identity stays fixed. Existing fallback,
  budgets, provider registration, and import-hygiene contracts remain covered.

## CI and completion criteria

Extend [.github/filters.yml](../../.github/filters.yml) so any newly covered opponent/telemetry test
paths route to the source job. Extend [.github/workflows/ci.yml](../../.github/workflows/ci.yml) to run
those tests and engine-independent projection contracts in the native and CGPy dispatch modes.
The current CGPy job covers only parity/Ledger; do not assume it already exercises all new tests.

Add a bounded native visibility smoke lane on Windows and Linux, loading the checked-in DLL/SO
explicitly and running actual native End/privacy regressions. Missing native support must fail that
required lane rather than pass through `importorskip`. Keep native sessions isolated per process and
close them in `finally`; do not share the native global search session across threads. General helper
tests remain runnable without either binary.

Use the existing correction gate with unchanged corpus and weights:

```text
python tools/train/ledger_correction_gate.py --workers 2 --output ledger-correction-gate.json
```

Run import hygiene, source reachability, record/telemetry contracts, doc links, and comment-budget
gates for touched code. Measure the focused native/CGPy End smoke before and after under identical
settings; projection must not add engine steps or bypass search budgets. No new benchmark system is needed.

Complete when the privacy regressions fail on the old implementation and pass on the new one, legal
positive controls and required CI pass, correction differences are explained without weakened gates,
and no unresolved public forced-choice or focal-view fidelity regression is represented as complete.

Relevant accepted boundaries:
[legal observation](../adr/0154-observationstate-is-the-legal-view-boundary.md),
[opponent snapshots](../adr/0175-opponent-model-emits-immutable-decision-snapshots.md),
[opponent evidence](../adr/0180-opponent-evidence-stays-in-observation.md),
[engine truth versus policy view](../adr/0196-search-state-separates-engine-truth-from-policy-view.md),
[hypothetical chance](../adr/0197-chance-resolution-simulates-future-randomness.md), and
[retired Teacher target design](../adr/0198-teacher-targets-are-complete-contingent-policies.md).

## Implementation verification, 2026-09-02

The shared projection, provider-only controls, record validation, and provider version 3 are built.
Native and direct one-ply CGPy End retain their original horizons. Native binaries, Evaluation Models, weights,
scouting inference, and correction expectations are unchanged. Both code reviews completed without
outstanding findings after fixing event type validation, hidden-zone movement evidence, and budget
accounting for unavailable nodes.

Final full suite: **3,127 passed, 1 skipped** in 718.38 seconds. The skip requires an absent local
Limitless decklist fixture; native privacy coverage ran. No test failures remain.

The actual native privacy tests fail three ways on the original commit: both seats retain the
opponent menu, and hidden draw substitution changes the valuation key. Direct CGPy and its
compatibility adapter fail the four corresponding seat/backend cases. All seven pass after the fix.
The final focused native/snapshot/projection run passed 118 tests; the separate CGPy visibility,
observation, opponent, and telemetry process passed 140. Documentation/import/packaging gates passed 34.

Unchanged-weight correction replay passes all 231 entries, including 121 evaluated frames.
Every chosen action remains unchanged. Seven frames have changed candidate metadata:

- Three refresh candidates change sampled values because legal public coin `head` fields, previously
  dropped, now enter the existing valuation key and deterministic sample seed. Direct before/after
  seed probes confirm this cause. No weights or sampling algorithm changed.
- One older frame (`48825669905379548-65`) loses grading eligibility because an attack requires an
  unsupported private opponent choice. It is explicitly unavailable, with no successor; the existing
  correction gate remains unchanged and passes.
- Remaining differences are sanitized successor identities and corrected continuation traces.

There is a material coverage cost: a real CGPy compatibility-adapter Correction Run at seed 601
cannot recover some focal hands after hidden prize movement. Its strict audit correctly rejects and
quarantines the episode. The process-worker regression now verifies that rejection, safe diagnostics,
and absence of fabricated successors or a completed bundle. Unknown private outcomes remain unsupported.

Paired local End measurements used identical roots/configuration, five warmups and 100 timed repeats:

| Provider | Before median | After median | Engine steps |
| --- | ---: | ---: | ---: |
| Native | 1.006 ms | 1.385 ms | 105 / 105 transitions in both |
| Direct CGPy | 0.795 ms | 1.000 ms | 105 / 105 transitions in both |

These are Windows/Python 3.11.9 smoke measurements, not throughput claims. Projection adds no engine
steps. Tests also verify that failed projections consume the existing global budget.

Historical exhaustive-search checks produced identical targets and work counters before and after the
privacy change: 27 searches took 74.219 s / 73.687 s, and the later ten-root run took 152.862 s /
153.849 s. Those generated corpora and baselines were removed with the retired Teacher timing gate;
Git history retains the exact artifacts.

The rebased CI run exposed a full-game test assumption: every random native match had to be
correction-gradeable. Local reproduction also reached a forced menu whose alternatives all required
private opponent choices; strict mode aborted on its empty comparable roster. The smoke test now uses
normal gameplay recovery and permits only the documented private-choice and hidden-hand coverage gaps.
It verifies no successors exist for those candidates and requires the unchanged Correction Run audit
to reject those episodes. All other decisions remain individually audited. A deterministic audit
regression also rejects a private alternative when the chosen action itself is priced.
Follow-up validation passed three native full games, 11 correction-audit contracts, 12 native/provider
privacy contracts, and 12 documentation gates. Runtime, correction-audit code, and weights are unchanged.
