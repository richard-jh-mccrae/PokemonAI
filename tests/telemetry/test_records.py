from dataclasses import replace
from io import StringIO
import json
from pathlib import Path
import subprocess

from ledger_helpers import player, printout
import pytest

from common.api import ActionIdentity, RootDecision
from common.decision import (
    CandidateDisposition,
    CandidateRoster,
    ComputeConfiguration,
    ContinuationResult,
    DecisionDelta,
    DecisionFailure,
    DecisionFailureStage,
    DecisionReason,
    DecisionResult,
    EvaluationStatus,
    SearchResult,
    SearchTrace,
    StateValuation,
    SuccessorResult,
    ValueComponent,
    ValueScale,
    ValuedCandidate,
)
from common.observation import ObservationStateBuilder, TransitionTrace, VisibleHand
from common.options import LegalAction
from common.ledger import BehaviorIdentity, EvaluationModel, PrizeMap
from common.telemetry import (
    MAX_FRAME_BYTES,
    RecordAssembler,
    TelemetrySession,
    build_decision_record,
    build_episode_receipt,
    build_outcome_record,
    build_pregame_record,
    frame_record,
    episode_context,
    emit,
    migrate_record,
    runtime_provenance,
    validate_record,
)


def Action(identity, selection):
    return LegalAction(identity, selection, (selection,), ())


def _provider_configuration(identity="fixture-provider"):
    return {
        "identity": identity, "backend": "fixture", "factory": "tests.FixtureProvider",
        "version": 2, "kwargs": {}, "factory_kwargs": {},
    }


def test_runtime_provenance_accepts_manifested_source_identity(monkeypatch):
    expected = {
        "agent": "mega_starmie",
        "artifact": "correction-run/run-1",
        "code": "abc123",
        "data": {"deck_sha256": "deck", "strategy_sha256": "strategy"},
    }
    monkeypatch.setenv("AGENT_RUNTIME_PROVENANCE", json.dumps(expected))
    assert runtime_provenance(deck_name="ignored") == expected


def test_pregame_record_keeps_the_committed_equivalent_selection():
    state = ObservationStateBuilder().root(printout(turn=0))
    action = LegalAction(
        ActionIdentity("setup_active"), (0,), ((0,), (1,)), ())
    state = replace(state, legal_actions=(action,))

    record = build_pregame_record(
        RootDecision((1,), ActionIdentity("setup_active"), 0.0, True, {}), state,
        episode_key="pregame", decision_index=0, parent_decision_id=None,
        provenance={"agent": "test", "artifact": "fixture", "code": "abc", "data": {}},
        decision_seconds=0.0,
    )

    assert record["decision"]["selection"] == [1]
    assert record["actions"][0]["selection"] == [1]


def test_decision_record_keeps_the_complete_typed_candidate_roster():
    state = ObservationStateBuilder().root(printout())
    scale = ValueScale("ledger-worth", 1)
    baseline = StateValuation(
        state.position_key,
        2.0,
        scale,
        state.seat,
        "ledger-linear-v1",
        (ValueComponent("prize_progress", 1.0, 2.0, 2.0, ("public-prizes",)),),
        evidence=PrizeMap(4, (101, 202), 4, 0),
    )
    action = Action(ActionIdentity("end_turn"), (0,))
    state = replace(state, legal_actions=(action,))
    candidate = ValuedCandidate(
        action,
        DecisionDelta(-0.25, scale, (
            ValueComponent("action_opportunity_cost", 1.0, -0.25, -0.25),
        )),
        CandidateDisposition.ENDS_TURN,
        EvaluationStatus.COMPLETE,
    )
    roster = CandidateRoster.from_legal_actions(state.legal_actions, (candidate,))
    search = SearchResult(baseline, roster, nodes_visited=3, stop_reason="complete")
    result = DecisionResult(
        action,
        baseline,
        roster,
        search,
        SearchTrace(3, "complete", (), action, ((action,),)),
        DecisionReason.BEST_TURN_ENDER,
        BehaviorIdentity("eval", "model", "search", "prior", "policy", "fail-safe",
                         "provider", "compute", "prize-plan"),
    )

    record = build_decision_record(
        result,
        state,
        episode_key="episode-7",
        decision_index=4,
        parent_decision_id="previous-id",
        selection=(0,),
        evaluation_model=EvaluationModel.build(),
        compute_configuration=ComputeConfiguration(),
        provider_configuration=_provider_configuration("provider"),
        provenance={"agent": "test", "artifact": "fixture", "code": "abc123",
                    "data": {"cards": "cards-v1"}},
        decision_seconds=0.125,
    )

    assert record["schema"] == "ledger.telemetry"
    assert record["schema_version"] == 2
    assert record["record_type"] == "decision"
    assert record["episode"]["key"] == "episode-7"
    assert record["decision"]["index"] == 4
    assert record["decision"]["variant"] == "ledger"
    assert record["decision"]["turn"] == state.turn.number
    assert record["decision"]["parent_id"] == "previous-id"
    assert record["decision"]["position_key"] == state.position_key
    assert record["decision"]["decision_key"] == state.decision_key
    assert record["decision"]["chosen_action_id"] == record["actions"][0]["id"]
    assert record["root"]["components"][0]["key"] == "prize_progress"
    assert record["root"]["evidence"]["kind"] == "prize_map"
    assert record["candidates"][0]["delta"]["components"][0]["value"] == -0.25
    assert record["search"] == {
        "nodes_visited": 3,
        "stop_reason": "complete",
        "frontier": [],
        "failure": None,
        "trace": {
            "nodes_visited": 3,
            "stop_reason": "complete",
            "frontier": [],
            "chosen_action_id": record["actions"][0]["id"],
            "action_paths": [[record["actions"][0]]],
        },
    }
    model = record["configuration"]["evaluation_model"]
    assert model["valuation"]["values"]["prize.race"] == 1.0
    assert model["identity"]
    assert model["card_store_identity"]
    assert record["configuration"]["compute"]["search"]["node_budget"] == 4096
    assert record["configuration"]["compute"]["identity"]
    assert record["provenance"]["code"] == "abc123"
    assert record["behavior_identity"]["provider"] == "provider"
    assert record["timing"]["decision_seconds"] == 0.125
    assert record["completeness"] == "complete"


@pytest.mark.parametrize(("stop_reason", "expected"), (
    ("cached_continuation", "complete"),
    ("complete", "unavailable"),
))
def test_cached_continuation_completeness_uses_the_committed_candidate(
        stop_reason, expected):
    state = ObservationStateBuilder().root(printout())
    scale = ValueScale("ledger-worth", 1)
    baseline = StateValuation(state.position_key, 0.0, scale, state.seat, "eval")
    chosen = Action(ActionIdentity("card", ("chosen",)), (0,))
    rejected = Action(ActionIdentity("card", ("rejected",)), (1,))
    state = replace(state, legal_actions=(chosen, rejected))
    candidates = (
        ValuedCandidate(
            chosen, DecisionDelta(0.0, scale), CandidateDisposition.FORCED,
            EvaluationStatus.COMPLETE, prior=1.0,
        ),
        ValuedCandidate(
            rejected, None, CandidateDisposition.FORCED, EvaluationStatus.UNAVAILABLE,
            gaps=("not selected by cached compound policy",), prior=0.0,
        ),
    )
    roster = CandidateRoster.from_legal_actions(
        state.legal_actions, candidates, forced=True)
    result = DecisionResult(
        chosen, baseline, roster, SearchResult(baseline, roster, stop_reason=stop_reason))

    record = build_decision_record(
        result, state, episode_key="cached-completeness", decision_index=0,
        parent_decision_id=None, selection=(0,),
        evaluation_model=EvaluationModel.build(),
        compute_configuration=ComputeConfiguration(),
        provider_configuration=_provider_configuration(),
        provenance={"agent": "test", "artifact": "fixture", "code": "abc", "data": {}},
        decision_seconds=0.01,
    )

    assert record["completeness"] == expected


def test_decision_record_keeps_every_successor_and_continuation_component():
    state = ObservationStateBuilder().root(printout())
    scale = ValueScale("ledger-worth", 1)
    baseline = StateValuation(state.position_key, 1.0, scale, state.seat, "eval")
    action = Action(ActionIdentity("attach", ("water",)), (2,))
    state = replace(state, legal_actions=(action,))
    landing = StateValuation(
        state.position_key, 1.75, scale, state.seat, "eval",
        (ValueComponent("energy_progress", 1.0, 0.75, 0.75),),
    )
    successor = SuccessorResult(
        1.0,
        landing,
        False,
        state,
        TransitionTrace(1, state.position_key, (action.identity,), state.position_key),
        (action,),
    )
    continuation = ContinuationResult(
        0.75, -0.1, True,
        zones_created=("hand",),
        allowances_consumed=("energy_attachment",),
        opportunities_created=("attack",),
    )
    candidate = ValuedCandidate(
        action,
        DecisionDelta(0.65, scale, (
            ValueComponent("energy_progress", 1.0, 0.75, 0.75),
            ValueComponent("action_opportunity_cost", 1.0, -0.1, -0.1),
        )),
        CandidateDisposition.CONTINUES_TURN,
        EvaluationStatus.COMPLETE,
        (successor,),
        continuation=continuation,
        policy_evidence=PrizeMap(4, (101, 202), 4, 0),
    )
    roster = CandidateRoster.from_legal_actions(state.legal_actions, (candidate,))
    search = SearchResult(baseline, roster)
    result = DecisionResult(action, baseline, roster, search)

    record = build_decision_record(
        result,
        state,
        episode_key="episode-8",
        decision_index=0,
        parent_decision_id=None,
        selection=(2,),
        evaluation_model=EvaluationModel.build(),
        compute_configuration=ComputeConfiguration(),
        provider_configuration=_provider_configuration(),
        provenance={"agent": "test", "artifact": "fixture", "code": "abc123", "data": {}},
        decision_seconds=0.01,
    )

    saved = record["candidates"][0]
    assert saved["continuation"]["allowances_consumed"] == ["energy_attachment"]
    assert saved["continuation"]["opportunities_created"] == ["attack"]
    assert saved["successors"][0]["probability"] == 1.0
    assert saved["successors"][0]["valuation"]["total"] == 1.75
    assert saved["successors"][0]["action_path"][0]["identity"]["kind"] == "attach"
    assert saved["successors"][0]["observation"] == record["observation"]
    assert saved["successors"][0]["trace"]["schema_version"] == 1
    assert saved["policy_evidence"] == {
        "kind": "prize_map",
        "remaining": 4,
        "route": [101, 202],
        "printed_prizes": 4,
        "overrun": 0,
    }


def test_framing_is_bounded_deterministic_and_lossless_out_of_order():
    state = ObservationStateBuilder().root(printout())
    scale = ValueScale("ledger-worth", 1)
    baseline = StateValuation(state.position_key, 0.0, scale, state.seat, "eval")
    action = Action(ActionIdentity("end_turn"), (0,))
    state = replace(state, legal_actions=(action,))
    candidate = ValuedCandidate(
        action,
        DecisionDelta(0.0, scale),
        CandidateDisposition.ENDS_TURN,
        EvaluationStatus.COMPLETE,
    )
    roster = CandidateRoster.from_legal_actions(state.legal_actions, (candidate,))
    result = DecisionResult(action, baseline, roster, SearchResult(baseline, roster))
    record = build_decision_record(
        result,
        state,
        episode_key="large-episode",
        decision_index=0,
        parent_decision_id=None,
        selection=(0,),
        evaluation_model=EvaluationModel.build(),
        compute_configuration=ComputeConfiguration(),
        provider_configuration=_provider_configuration(),
        provenance={"agent": "test", "artifact": "fixture", "code": "abc123", "data": {
            "padding": "".join(f"{index:08x}" for index in range(20_000))
        }},
        decision_seconds=0.01,
    )

    frames = frame_record(record)

    assert len(frames) > 1
    assert frames == frame_record(record)
    assert all(len(frame.encode("utf-8")) <= MAX_FRAME_BYTES for frame in frames)
    assembler = RecordAssembler()
    completed = [saved for frame in reversed(frames)
                 if (saved := assembler.ingest(frame)) is not None]
    assert completed == [record]


def test_outcome_record_links_the_exact_episode_decision_set():
    decisions = [
        {"record_type": "decision", "record_id": "d0", "episode": {"key": "episode-9"},
         "decision": {"seat": 0, "index": 0}},
        {"record_type": "decision", "record_id": "d1", "episode": {"key": "episode-9"},
         "decision": {"seat": 1, "index": 0}},
    ]

    receipt = build_episode_receipt(
        episode_key="episode-9", reservations=[{
            "record_id": decision["record_id"], "seat": decision["decision"]["seat"],
            "index": decision["decision"]["index"], "status": "delivered",
            "error_type": None,
        } for decision in decisions])
    record = build_outcome_record(
        episode_key="episode-9",
        decision_records=decisions,
        telemetry_receipt=receipt,
        winner=1,
        terminal_reason="prizes_taken",
        public_prizes={0: 2, 1: 0},
        rewards={0: -1.0, 1: 1.0},
        duration_seconds=31.5,
        external_episode_id="kaggle-44",
    )

    assert record == {
        "schema": "ledger.telemetry",
        "schema_version": 2,
        "record_type": "outcome",
        "record_id": record["record_id"],
        "episode": {"key": "episode-9", "external_id": "kaggle-44"},
        "decision_ids": ["d0", "d1"],
        "telemetry_receipt_id": receipt["record_id"],
        "result": {
            "winner": 1,
            "draw": False,
            "terminal_reason": "prizes_taken",
            "public_prizes": {"0": 2, "1": 0},
            "rewards": {"0": -1.0, "1": 1.0},
            "duration_seconds": 31.5,
        },
    }


def test_session_uses_owner_episode_key_and_tracks_parent_per_seat():
    with episode_context("shared-episode"):
        session = TelemetrySession()
        assert session.begin_episode() == "shared-episode"
    first = session.next_decision(seat=0)
    session.commit_decision(seat=0, record_id="seat-zero-first")
    other = session.next_decision(seat=1)
    second = session.next_decision(seat=0)

    assert first == {"episode_key": "shared-episode", "decision_index": 0,
                     "parent_decision_id": None}
    assert other == {"episode_key": "shared-episode", "decision_index": 0,
                     "parent_decision_id": None}
    assert second == {"episode_key": "shared-episode", "decision_index": 1,
                      "parent_decision_id": "seat-zero-first"}


def test_repeated_owner_episode_begin_preserves_earlier_reservations():
    session = TelemetrySession()
    with episode_context("shared-episode"):
        session.begin_episode()
        reservation = session.reserve_decision(
            seat=0, position_key="position", decision_key="decision")
        session.commit_decision(seat=0, record_id=reservation["record_id"])
        session.deliver_decision(record_id=reservation["record_id"])
        session.begin_episode()

    assert session.close_episode()["decision_ids"] == [reservation["record_id"]]


def test_episode_receipt_accounts_for_every_reservation_before_outcome_certification():
    session = TelemetrySession()
    session.begin_episode("receipt-episode")
    reservation = session.reserve_decision(
        seat=0, position_key="position", decision_key="decision")
    session.commit_decision(seat=0, record_id=reservation["record_id"])
    session.deliver_decision(record_id=reservation["record_id"])

    receipt = session.close_episode()

    assert receipt["schema_version"] == 2
    assert receipt["record_type"] == "telemetry_receipt"
    assert receipt["certified"] is True
    assert receipt["reservations"] == [{
        "record_id": reservation["record_id"], "seat": 0, "index": 0,
        "status": "delivered", "error_type": None,
    }]


def test_failed_or_open_reservation_cannot_certify_an_outcome():
    session = TelemetrySession()
    session.begin_episode("failed-receipt")
    reservation = session.reserve_decision(
        seat=0, position_key="position", decision_key="decision")
    session.fail_decision(
        record_id=reservation["record_id"], phase="emission", error_type="ValueError")
    receipt = session.close_episode()

    assert receipt["certified"] is False
    with pytest.raises(ValueError, match="certified Episode Telemetry Receipt"):
        build_outcome_record(
            episode_key="failed-receipt", decision_records=[], telemetry_receipt=receipt,
            winner=None, terminal_reason="draw", public_prizes={0: 1, 1: 1},
            rewards={0: 0.0, 1: 0.0}, duration_seconds=1.0)


def _emittable_decision():
    state = ObservationStateBuilder().root(printout())
    scale = ValueScale("ledger-worth", 1)
    baseline = StateValuation(state.position_key, 0.0, scale, state.seat, "eval")
    action = Action(ActionIdentity("end_turn"), (0,))
    state = replace(state, legal_actions=(action,))
    candidate = ValuedCandidate(
        action, DecisionDelta(0.0, scale), CandidateDisposition.ENDS_TURN,
        EvaluationStatus.COMPLETE,
    )
    roster = CandidateRoster.from_legal_actions(state.legal_actions, (candidate,))
    result = DecisionResult(action, baseline, roster, SearchResult(baseline, roster))
    return state, RootDecision((0,), action.identity, 0.0, True, {}, result)


def test_emission_and_delivery_failures_preserve_choice_but_make_episode_uncertifiable():
    state, decision = _emittable_decision()
    common = {
        "seat": state.seat, "state": state,
        "evaluation_model": EvaluationModel.build(),
        "compute_configuration": ComputeConfiguration(),
        "provenance": {"agent": "test", "artifact": "fixture", "code": "abc", "data": {}},
    }
    emission = TelemetrySession()
    emission.begin_episode("emission-failure")
    invalid_provider = {**_provider_configuration(), "backend": None}
    with pytest.raises(ValueError, match="provider configuration"):
        emit(decision, session=emission, provider_configuration=invalid_provider,
             out=StringIO(), **common)
    emission_receipt = emission.close_episode()

    class BrokenTransport:
        def write(self, _value):
            raise OSError("transport down")

    delivery = TelemetrySession()
    delivery.begin_episode("delivery-failure")
    with pytest.raises(OSError, match="transport down"):
        emit(decision, session=delivery, provider_configuration=_provider_configuration(),
             out=BrokenTransport(), **common)
    delivery_receipt = delivery.close_episode()

    assert decision.chosen == (0,)
    assert emission_receipt["reservations"][0]["status"] == "emission_failed"
    assert delivery_receipt["reservations"][0]["status"] == "delivery_failed"
    assert not emission_receipt["certified"] and not delivery_receipt["certified"]


def test_decision_record_rejects_a_circular_unproven_candidate_roster():
    state, decision = _emittable_decision()
    candidate = decision.decision_result.roster.candidates[0]
    roster = CandidateRoster((candidate,))
    result = DecisionResult(
        candidate.action, decision.decision_result.baseline, roster,
        SearchResult(decision.decision_result.baseline, roster))

    with pytest.raises(ValueError, match="authoritative legal-action roster proof"):
        build_decision_record(
            result, state, episode_key="unproven", decision_index=0,
            parent_decision_id=None, selection=(0,),
            evaluation_model=EvaluationModel.build(),
            compute_configuration=ComputeConfiguration(),
            provider_configuration=_provider_configuration(),
            provenance={"agent": "test", "artifact": "fixture", "code": "abc", "data": {}},
            decision_seconds=0.01)


def test_schema_rejects_unknown_fields_versions_and_bellman_migration():
    receipt = build_episode_receipt(episode_key="episode-10", reservations=[])
    record = build_outcome_record(
        episode_key="episode-10",
        decision_records=[],
        telemetry_receipt=receipt,
        winner=None,
        terminal_reason="draw",
        public_prizes={0: 1, 1: 1},
        rewards={0: 0.0, 1: 0.0},
        duration_seconds=5.0,
    )
    assert validate_record(record) is record
    assert migrate_record(record) is record

    with_unknown = {**record, "result": {**record["result"], "secret": "no"}}
    with pytest.raises(ValueError, match="unknown outcome result fields"):
        validate_record(with_unknown)
    with pytest.raises(ValueError, match="unsupported telemetry schema version"):
        validate_record({**record, "schema_version": 1})
    with pytest.raises(ValueError, match="unsupported telemetry schema version"):
        validate_record({**record, "schema_version": 3})
    with pytest.raises(ValueError, match="diagnostic-only"):
        migrate_record({**record, "schema_version": 1})
    with pytest.raises(ValueError, match="diagnostic-only"):
        migrate_record({"bellman": True, "chosen": [0]})
    with pytest.raises(ValueError, match="record id"):
        validate_record({**record, "record_id": "tampered"})
    with pytest.raises(ValueError, match="outcome duration"):
        negative_receipt = build_episode_receipt(
            episode_key="negative-duration", reservations=[])
        build_outcome_record(
            episode_key="negative-duration", decision_records=[], winner=None,
            telemetry_receipt=negative_receipt,
            terminal_reason="draw", public_prizes={0: 1, 1: 1},
            rewards={0: 0.0, 1: 0.0}, duration_seconds=-1.0,
        )


def test_runtime_provenance_separates_real_source_artifact_and_data_identities():
    provenance = runtime_provenance(
        deck_name="fixture", opponent_knowledge_identity="opponent-data")
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=Path(__file__).resolve().parents[2],
        check=True, capture_output=True, text=True).stdout.strip()

    assert provenance["code"] == commit
    assert len(provenance["artifact"]) == 64
    assert provenance["artifact"] != provenance["code"]
    assert provenance["data"]["cards"]
    assert provenance["data"]["opponent_knowledge"] == "opponent-data"


def test_successor_observation_rejects_a_visible_opponent_hand():
    state = ObservationStateBuilder().root(printout())
    leaked = replace(state, them=replace(state.them, hand=VisibleHand(())))
    scale = ValueScale("ledger-worth", 1)
    baseline = StateValuation(state.position_key, 0.0, scale, state.seat, "eval")
    action = Action(ActionIdentity("end_turn"), (0,))
    state = replace(state, legal_actions=(action,))
    successor = SuccessorResult(
        1.0, baseline, True, leaked,
        TransitionTrace(1, state.position_key, (action.identity,), state.position_key),
        (action,),
    )
    candidate = ValuedCandidate(
        action, DecisionDelta(0.0, scale), CandidateDisposition.ENDS_TURN,
        EvaluationStatus.COMPLETE, (successor,),
    )
    roster = CandidateRoster.from_legal_actions(state.legal_actions, (candidate,))

    with pytest.raises(ValueError, match="opponent hand must be hidden"):
        build_decision_record(
            DecisionResult(action, baseline, roster, SearchResult(baseline, roster)), state,
            episode_key="hidden-successor", decision_index=0, parent_decision_id=None,
            selection=(0,), evaluation_model=EvaluationModel.build(),
            compute_configuration=ComputeConfiguration(),
            provider_configuration=_provider_configuration(),
            provenance={"agent": "test", "artifact": "fixture", "code": "abc123", "data": {}},
            decision_seconds=0.01,
        )


def test_decision_record_rejects_a_selection_outside_its_chosen_action():
    state, decision = _emittable_decision()
    record = build_decision_record(
        decision.decision_result, state,
        episode_key="selection-mismatch", decision_index=0,
        parent_decision_id=None, selection=(0,),
        evaluation_model=EvaluationModel.build(),
        compute_configuration=ComputeConfiguration(),
        provider_configuration=_provider_configuration(),
        provenance={"agent": "test", "artifact": "fixture", "code": "abc", "data": {}},
        decision_seconds=0.01)
    record = json.loads(json.dumps(record))
    record["decision"]["selection"] = [999]

    with pytest.raises(ValueError, match="selection differs"):
        validate_record(record)


def test_hidden_opponent_hand_truth_cannot_change_a_decision_record():
    legal = printout(them=player(own=False, hand_count=2))
    hostile = printout(them=player(own=False, hand_count=2))
    hostile["current"]["players"][1]["hand"] = [
        {"id": 777_001, "serial": 90}, {"id": 777_002, "serial": 91},
    ]

    def record_for(raw):
        state = ObservationStateBuilder().root(raw)
        scale = ValueScale("ledger-worth", 1)
        baseline = StateValuation(state.position_key, 0.0, scale, state.seat, "eval")
        action = Action(ActionIdentity("end_turn"), (0,))
        state = replace(state, legal_actions=(action,))
        candidate = ValuedCandidate(
            action, DecisionDelta(0.0, scale), CandidateDisposition.ENDS_TURN,
            EvaluationStatus.COMPLETE,
        )
        roster = CandidateRoster.from_legal_actions(state.legal_actions, (candidate,))
        return build_decision_record(
            DecisionResult(action, baseline, roster, SearchResult(baseline, roster)),
            state,
            episode_key="hidden-sentinel",
            decision_index=0,
            parent_decision_id=None,
            selection=(0,),
            evaluation_model=EvaluationModel.build(),
            compute_configuration=ComputeConfiguration(),
            provider_configuration=_provider_configuration(),
            provenance={"agent": "test", "artifact": "fixture", "code": "abc123", "data": {}},
            decision_seconds=0.01,
        )

    assert record_for(hostile) == record_for(legal)


def test_failure_telemetry_keeps_codes_but_drops_exception_text():
    state = ObservationStateBuilder().root(printout())
    scale = ValueScale("ledger-worth", 1)
    baseline = StateValuation(state.position_key, 0.0, scale, state.seat, "eval")
    action = Action(ActionIdentity("end_turn"), (0,))
    state = replace(state, legal_actions=(action,))
    candidate = ValuedCandidate(
        action, None, CandidateDisposition.FORCED, EvaluationStatus.UNAVAILABLE,
    )
    roster = CandidateRoster.from_legal_actions(state.legal_actions, (candidate,))
    failure = DecisionFailure(
        DecisionFailureStage.PROVIDER,
        "PrivateProviderError",
        "SECRET-HAND-CONTENT",
        "SECRET-TRACEBACK",
    )
    result = DecisionResult(
        action, baseline, roster, SearchResult(baseline, roster, failure=failure),
    )

    record = build_decision_record(
        result,
        state,
        episode_key="failure",
        decision_index=0,
        parent_decision_id=None,
        selection=(0,),
        evaluation_model=EvaluationModel.build(),
        compute_configuration=ComputeConfiguration(),
        provider_configuration=_provider_configuration(),
        provenance={"agent": "test", "artifact": "fixture", "code": "abc123", "data": {}},
        decision_seconds=0.01,
    )

    assert record["search"]["failure"] == {
        "stage": "provider", "error_type": "PrivateProviderError",
    }
    assert "SECRET" not in json.dumps(record)
