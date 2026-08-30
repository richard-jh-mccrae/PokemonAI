import copy
import gzip
import hashlib
import json
from pathlib import Path

import pytest

from common.api import ActionIdentity
from common.observation.nodes import HiddenHand
from cgpy.engine import Engine
from cgpy.experiment import (ChanceSampleKey, ExperimentParityManifest,
                             ExperimentSnapshot, PairedSeedCase, PairedSeedMatch,
                             SnapshotCompatibilityError)
from cgpy.rng import SeededRng
from cgpy.verify.trace import Trace


REPO = Path(__file__).resolve().parents[2]


def _digest(value) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def _write_document(path: Path, document: dict) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        json.dump(document, stream, sort_keys=True, separators=(",", ":"))


def _deck(name: str) -> list[int]:
    return [int(value) for value in (
        REPO / "src" / "agents" / name / "deck.csv"
    ).read_text(encoding="utf-8").split()[:60]]


def _start_of_turn(seed: int = 602) -> Engine:
    engine, error_player, error_type = Engine.start(
        _deck("mega_starmie"), _deck("mega_starmie"), rng=SeededRng(seed))
    assert engine is not None, (error_player, error_type)
    for _ in range(40):
        pending = engine.gs.pending
        assert pending is not None
        if engine.gs.phase == "TURN" and pending.context == 0:
            return engine
        engine.step(list(range(pending.min_count)))
    raise AssertionError("setup did not reach the first turn")


def test_saved_experiment_snapshot_recreates_the_full_root(tmp_path):
    source = _start_of_turn()
    snapshot = ExperimentSnapshot.capture(source, seat=source.select_seat)

    path = snapshot.save(tmp_path / "root.snapshot.json.gz")
    loaded = ExperimentSnapshot.load(path)
    restored = loaded.fork_engine()

    assert loaded.snapshot_id == snapshot.snapshot_id
    assert loaded.full_state_digest == snapshot.full_state_digest
    assert loaded.rng_digest == snapshot.rng_digest
    assert restored.god_frame() == source.god_frame()
    assert restored.observation(viewer=source.select_seat) == source.observation(
        viewer=source.select_seat)


def test_experiment_snapshot_artifact_is_filename_independent(tmp_path):
    snapshot = ExperimentSnapshot.capture(_start_of_turn(), seat=0)

    first = snapshot.save(tmp_path / "first.snapshot.json.gz")
    second = snapshot.save(tmp_path / "second.snapshot.json.gz")

    assert first.read_bytes() == second.read_bytes()


def test_snapshot_load_rejects_deck_identity_that_disagrees_with_engine(tmp_path):
    document = copy.deepcopy(ExperimentSnapshot.capture(
        _start_of_turn(), seat=0).document)
    document["identities"]["decks"][0] = "0" * 64
    document["initial_setup_digest"] = _digest({
        "state": document["state"], "decks": document["identities"]["decks"]})
    body = {key: value for key, value in document.items() if key != "snapshot_id"}
    document["snapshot_id"] = _digest(body)
    path = tmp_path / "forged.snapshot.json.gz"
    _write_document(path, document)

    with pytest.raises(SnapshotCompatibilityError, match="deck identities mismatch"):
        ExperimentSnapshot.load(path)


def test_snapshot_capture_rejects_an_invalid_hidden_zone_partition():
    engine = _start_of_turn()
    engine.gs.players[1].deck[0] = engine.gs.players[1].deck[1]

    with pytest.raises(SnapshotCompatibilityError, match="card zone partition"):
        ExperimentSnapshot.capture(engine, seat=0)


def test_snapshot_load_rejects_unknown_schema_with_a_diagnostic(tmp_path):
    document = copy.deepcopy(ExperimentSnapshot.capture(
        _start_of_turn(), seat=0).document)
    document["schema_version"] = 99
    body = {key: value for key, value in document.items() if key != "snapshot_id"}
    document["snapshot_id"] = _digest(body)
    path = tmp_path / "future.snapshot.json.gz"
    _write_document(path, document)

    with pytest.raises(SnapshotCompatibilityError, match="schema.*99"):
        ExperimentSnapshot.load(path)


def test_snapshot_load_rejects_a_tampered_legal_view(tmp_path):
    document = ExperimentSnapshot.capture(_start_of_turn(), seat=0).document
    document["observation"]["events"] = []
    body = {key: value for key, value in document.items() if key != "snapshot_id"}
    document["snapshot_id"] = _digest(body)
    path = tmp_path / "tampered-view.snapshot.json.gz"
    _write_document(path, document)

    with pytest.raises(SnapshotCompatibilityError, match="legal-view Observation"):
        ExperimentSnapshot.load(path)


def test_snapshot_document_access_cannot_mutate_the_artifact():
    snapshot = ExperimentSnapshot.capture(_start_of_turn(), seat=0)
    exposed = snapshot.document
    exposed["seat"] = 1

    assert snapshot.document["seat"] == 0
    assert snapshot.fork_engine().select_seat == 0


def test_experiment_roots_begin_identical_and_evolve_independently():
    snapshot = ExperimentSnapshot.capture(_start_of_turn(), seat=0)

    roots = snapshot.fork_roots(("A", "B", "C", "D"))
    before = roots["B"].observation(viewer=0)
    end = next(index for index, option in enumerate(roots["A"].gs.pending.options)
               if option["type"] == 14)
    roots["A"].step([end])

    assert tuple(roots) == ("A", "B", "C", "D")
    assert len({id(engine.gs) for engine in roots.values()}) == 4
    assert len({id(engine.gs.rng) for engine in roots.values()}) == 4
    assert roots["B"].observation(viewer=0) == before
    assert roots["A"].god_frame() != roots["B"].god_frame()


def test_policy_roots_expose_only_the_legal_view():
    snapshot = ExperimentSnapshot.capture(_start_of_turn(), seat=0)

    roots = snapshot.policy_roots(("uniform", "ledger"))

    assert roots["uniform"].observation == snapshot.observation
    assert isinstance(roots["uniform"].observation.them.hand, HiddenHand)
    for forbidden in ("engine", "rng", "document", "full_state_key"):
        assert not hasattr(roots["uniform"], forbidden)


def test_chance_samples_do_not_depend_on_traversal_order():
    actions = (ActionIdentity("play", ("alpha",)), ActionIdentity("play", ("beta",)))

    forward = {
        (action, index): ChanceSampleKey(
            602, "root", "node", action, index).seed
        for action in actions for index in range(3)
    }
    reverse = {
        (action, index): ChanceSampleKey(
            602, "root", "node", action, index).seed
        for action in reversed(actions) for index in reversed(range(3))
    }

    assert forward == reverse
    baseline = ChanceSampleKey(602, "root", "node", actions[0], 0).seed
    variants = {
        ChanceSampleKey(603, "root", "node", actions[0], 0).seed,
        ChanceSampleKey(602, "other-root", "node", actions[0], 0).seed,
        ChanceSampleKey(602, "root", "other-node", actions[0], 0).seed,
        ChanceSampleKey(602, "root", "node", actions[1], 0).seed,
        ChanceSampleKey(602, "root", "node", actions[0], 1).seed,
        ChanceSampleKey(602, "root", "node", actions[0], 0, schema_version=2).seed,
    }
    assert baseline not in variants
    assert len(variants) == 6


def test_paired_seed_case_relaunches_the_declared_roots():
    snapshot = ExperimentSnapshot.capture(_start_of_turn(), seat=0)
    parity = ExperimentParityManifest.capture((
        _deck("mega_starmie"), _deck("mega_starmie")))
    case = PairedSeedCase.create(
        snapshot, experiment_seed=602, orientation="starmie-seat0",
        methods=("A", "B", "C", "D"), baseline_identity="baseline-1",
        parity=parity)

    loaded = PairedSeedCase.loads(case.dumps())
    roots = loaded.fork_roots(snapshot, parity=parity)
    swapped = PairedSeedCase.create(
        snapshot, experiment_seed=602, orientation="starmie-seat1",
        methods=("A", "B", "C", "D"), baseline_identity="baseline-1",
        parity=parity)

    assert loaded == case
    assert tuple(roots) == ("A", "B", "C", "D")
    assert loaded.snapshot_id == snapshot.snapshot_id
    assert loaded.initial_setup_digest == snapshot.initial_setup_digest
    assert loaded.rng_digest == snapshot.rng_digest
    assert loaded.parity_identity == parity.identity
    assert swapped.case_id != case.case_id


def test_paired_seed_full_matches_relaunch_and_swap_seats_reproducibly():
    deck0, deck1 = _deck("dragapult_ex"), _deck("mega_starmie")
    parity = ExperimentParityManifest.capture((deck0, deck1))
    forward, reverse = PairedSeedMatch.seat_pair(
        deck0, deck1, experiment_seed=602, methods=("A", "B", "C", "D"),
        baseline_identity="baseline-1", parity=parity)

    first = forward.launch(parity=parity)
    again = PairedSeedMatch.loads(forward.dumps()).launch(parity=parity)
    swapped = reverse.launch(parity=parity)

    assert first.initial_setup_digest == again.initial_setup_digest
    assert forward.initial_setup_digest == first.initial_setup_digest
    assert len({root.initial_setup_digest for root in first.roots.values()}) == 1
    assert all(root.engine.god_frame() == first.roots["A"].engine.god_frame()
               for root in first.roots.values())
    assert tuple(swapped.deck_identities) == tuple(reversed(first.deck_identities))
    assert forward.case_id != reverse.case_id

    with pytest.raises(SnapshotCompatibilityError, match=r"attack:424.*derived"):
        first.roots["A"].engine.gs.execution_guard("attack:424")


def test_verified_native_trace_root_starts_a_new_randomness_epoch():
    path = REPO / "tests" / "fixtures" / "parity" / "alakazam_9000.trace.json.gz"
    trace = Trace.load(path)
    frame = next(index for index, row in enumerate(trace.frames)
                 if (row["obs"].get("select") or {}).get("context") == 0
                 and (row["obs"].get("current") or {}).get("turnActionCount") == 1)

    snapshot = ExperimentSnapshot.from_trace(
        trace, frame=frame, experiment_seed=9900,
        provenance={"episode": "alakazam_9000"})
    root = snapshot.fork_engine()

    assert isinstance(root.gs.rng, SeededRng)
    assert snapshot.provenance == {
        "episode": "alakazam_9000", "trace_frame": frame,
        "trace_engine": trace.meta["engine_sha"], "randomness_epoch_seed": 9900,
    }
    assert root.observation(viewer=root.select_seat)["current"] == \
        trace.frames[frame]["obs"]["current"]


def test_experiment_parity_rejects_an_executed_unverified_effect():
    manifest = ExperimentParityManifest.capture((
        _deck("mega_lucario"), _deck("mega_starmie")))

    manifest.require_verified(("1030", "attack:1486"))
    with pytest.raises(SnapshotCompatibilityError,
                       match=r"attack:978.*seeded"):
        manifest.require_verified(("attack:978",))

    assert len(manifest.coverage_identity) == 64
    assert set(manifest.deck_card_ids) == set(
        _deck("mega_lucario") + _deck("mega_starmie"))


def test_experiment_parity_declares_the_selected_three_deck_union():
    decks = tuple(_deck(name) for name in (
        "dragapult_ex", "mega_lucario", "mega_starmie"))

    manifest = ExperimentParityManifest.capture(decks)

    assert set(manifest.deck_card_ids) == set().union(*map(set, decks))
