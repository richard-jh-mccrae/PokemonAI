"""Persistent identities for reproducible paired-seed experiment cases."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from ..engine import Engine
from ..rng import SeededRng
from .chance import CHANCE_SCHEMA_VERSION
from .parity import ExperimentParityManifest
from .snapshot import (_deck_identities, _digest, _encode, _state_payload,
                       ExperimentSnapshot, SnapshotCompatibilityError)


CASE_SCHEMA = "cgpy-paired-seed-case/v1"


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _identity(value) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _dumps_artifact(value) -> str:
    return _canonical(asdict(value)).decode("utf-8")


def _loads_artifact(encoded: str, cls, label: str, *, has_decks: bool = False):
    try:
        raw = json.loads(encoded)
        raw["methods"] = tuple(raw["methods"])
        raw["deck_identities"] = tuple(raw["deck_identities"])
        if has_decks:
            raw["decks"] = tuple(tuple(deck) for deck in raw["decks"])
        result = cls(**raw)
    except (KeyError, TypeError, ValueError) as exc:
        raise SnapshotCompatibilityError(f"invalid {label}: {exc}") from exc
    result._validate()
    return result


def _validate_artifact(value, schema: str, label: str) -> None:
    if value.schema != schema:
        raise SnapshotCompatibilityError(f"unsupported {label} schema")
    if value.chance_schema_version != CHANCE_SCHEMA_VERSION:
        raise SnapshotCompatibilityError("unsupported Chance Sample schema")
    if (not value.orientation or not value.baseline_identity or not value.methods
            or len(set(value.methods)) != len(value.methods)
            or any(not name for name in value.methods)):
        raise SnapshotCompatibilityError(f"invalid {label} identities")
    body = asdict(value)
    body.pop("case_id")
    if value.case_id != _identity(body):
        raise SnapshotCompatibilityError(f"{label} content digest mismatch")


def _guard_engine(engine: Engine, parity: ExperimentParityManifest, executed: list[str]) -> None:
    engine.gs.parity_manifest = parity
    engine.gs.executed_chains = executed


def _start_engine(decks, seed: int) -> Engine:
    engine, seat, error = Engine.start(
        list(decks[0]), list(decks[1]), rng=SeededRng(seed))
    if engine is None:
        raise SnapshotCompatibilityError(
            f"Paired-Seed Match deck {seat} failed validation with error {error}")
    return engine


def _setup_digest(engine: Engine) -> str:
    return _digest({"state": _state_payload(engine.gs),
                    "rng": _encode(engine.gs.rng.export_state())})


@dataclass(frozen=True, slots=True)
class PairedSeedCase:
    schema: str
    case_id: str
    experiment_seed: int
    orientation: str
    methods: tuple[str, ...]
    baseline_identity: str
    snapshot_id: str
    initial_setup_digest: str
    rng_digest: str
    deck_identities: tuple[str, str]
    parity_identity: str
    coverage_identity: str
    chance_schema_version: int

    @classmethod
    def create(cls, snapshot: ExperimentSnapshot, *, experiment_seed: int,
               orientation: str, methods, baseline_identity: str,
               parity: ExperimentParityManifest) -> "PairedSeedCase":
        names = tuple(str(method) for method in methods)
        body = {
            "schema": CASE_SCHEMA, "experiment_seed": int(experiment_seed),
            "orientation": str(orientation), "methods": names,
            "baseline_identity": str(baseline_identity),
            "snapshot_id": snapshot.snapshot_id,
            "initial_setup_digest": snapshot.initial_setup_digest,
            "rng_digest": snapshot.rng_digest,
            "deck_identities": snapshot.deck_identities,
            "parity_identity": parity.identity,
            "coverage_identity": parity.coverage_identity,
            "chance_schema_version": CHANCE_SCHEMA_VERSION,
        }
        result = cls(case_id=_identity(body), **body)
        result._validate()
        return result

    def dumps(self) -> str:
        return _dumps_artifact(self)

    @classmethod
    def loads(cls, encoded: str) -> "PairedSeedCase":
        return _loads_artifact(encoded, cls, "Paired-Seed Case")

    def fork_roots(self, snapshot: ExperimentSnapshot, *,
                   parity: ExperimentParityManifest):
        if snapshot.snapshot_id != self.snapshot_id:
            raise SnapshotCompatibilityError("Paired-Seed Case snapshot identity mismatch")
        if snapshot.initial_setup_digest != self.initial_setup_digest:
            raise SnapshotCompatibilityError("Paired-Seed Case setup identity mismatch")
        if snapshot.rng_digest != self.rng_digest:
            raise SnapshotCompatibilityError("Paired-Seed Case RNG identity mismatch")
        if snapshot.deck_identities != self.deck_identities:
            raise SnapshotCompatibilityError("Paired-Seed Case deck identities mismatch")
        if parity.identity != self.parity_identity:
            raise SnapshotCompatibilityError("Paired-Seed Case parity identity mismatch")
        if parity.coverage_identity != self.coverage_identity:
            raise SnapshotCompatibilityError("Paired-Seed Case coverage identity mismatch")
        roots = snapshot.fork_roots(self.methods)
        for engine in roots.values():
            _guard_engine(engine, parity, [])
        return roots

    def _validate(self) -> None:
        _validate_artifact(self, CASE_SCHEMA, "Paired-Seed Case")


MATCH_SCHEMA = "cgpy-paired-seed-match/v1"


@dataclass(slots=True)
class FullMatchRoot:
    method_identity: str
    initial_setup_digest: str
    engine: Engine
    executed_chains: list[str]


@dataclass(slots=True)
class FullMatchLaunch:
    initial_setup_digest: str
    deck_identities: tuple[str, str]
    roots: dict[str, FullMatchRoot]


@dataclass(frozen=True, slots=True)
class PairedSeedMatch:
    schema: str
    case_id: str
    experiment_seed: int
    orientation: str
    methods: tuple[str, ...]
    baseline_identity: str
    decks: tuple[tuple[int, ...], tuple[int, ...]]
    deck_identities: tuple[str, str]
    initial_setup_digest: str
    parity_identity: str
    coverage_identity: str
    chance_schema_version: int

    @classmethod
    def create(cls, deck0, deck1, *, experiment_seed: int, orientation: str,
               methods, baseline_identity: str,
               parity: ExperimentParityManifest) -> "PairedSeedMatch":
        decks = (tuple(map(int, deck0)), tuple(map(int, deck1)))
        names = tuple(map(str, methods))
        if not set().union(*map(set, decks)).issubset(parity.deck_card_ids):
            raise SnapshotCompatibilityError(
                "Paired-Seed Match decks are outside the parity manifest")
        setup = _setup_digest(_start_engine(decks, int(experiment_seed)))
        body = {
            "schema": MATCH_SCHEMA, "experiment_seed": int(experiment_seed),
            "orientation": str(orientation), "methods": names,
            "baseline_identity": str(baseline_identity), "decks": decks,
            "deck_identities": tuple(_deck_identities([list(deck) for deck in decks])),
            "initial_setup_digest": setup,
            "parity_identity": parity.identity,
            "coverage_identity": parity.coverage_identity,
            "chance_schema_version": CHANCE_SCHEMA_VERSION,
        }
        result = cls(case_id=_identity(body), **body)
        result._validate()
        return result

    @classmethod
    def seat_pair(cls, deck0, deck1, **kwargs) -> tuple["PairedSeedMatch", "PairedSeedMatch"]:
        return (
            cls.create(deck0, deck1, orientation="forward", **kwargs),
            cls.create(deck1, deck0, orientation="reverse", **kwargs),
        )

    def dumps(self) -> str:
        return _dumps_artifact(self)

    @classmethod
    def loads(cls, encoded: str) -> "PairedSeedMatch":
        return _loads_artifact(encoded, cls, "Paired-Seed Match", has_decks=True)

    def launch(self, *, parity: ExperimentParityManifest) -> FullMatchLaunch:
        if parity.identity != self.parity_identity:
            raise SnapshotCompatibilityError("Paired-Seed Match parity identity mismatch")
        if parity.coverage_identity != self.coverage_identity:
            raise SnapshotCompatibilityError("Paired-Seed Match coverage identity mismatch")
        roots = {}
        expected = None
        for method in self.methods:
            engine = _start_engine(self.decks, self.experiment_seed)
            setup = _setup_digest(engine)
            if setup != self.initial_setup_digest:
                raise SnapshotCompatibilityError(
                    "Paired-Seed Match initial setup identity mismatch")
            expected = setup
            executed: list[str] = []
            _guard_engine(engine, parity, executed)
            roots[method] = FullMatchRoot(method, setup, engine, executed)
        return FullMatchLaunch(expected, self.deck_identities, roots)

    def _validate(self) -> None:
        _validate_artifact(self, MATCH_SCHEMA, "Paired-Seed Match")
        identities = tuple(_deck_identities([list(deck) for deck in self.decks]))
        if identities != self.deck_identities:
            raise SnapshotCompatibilityError("Paired-Seed Match deck identities mismatch")


__all__ = (
    "CASE_SCHEMA", "FullMatchLaunch", "FullMatchRoot", "MATCH_SCHEMA", "PairedSeedCase",
    "PairedSeedMatch",
)
