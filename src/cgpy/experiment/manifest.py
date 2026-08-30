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
        return _canonical(asdict(self)).decode("utf-8")

    @classmethod
    def loads(cls, encoded: str) -> "PairedSeedCase":
        try:
            raw = json.loads(encoded)
            raw["methods"] = tuple(raw["methods"])
            raw["deck_identities"] = tuple(raw["deck_identities"])
            result = cls(**raw)
        except (KeyError, TypeError, ValueError) as exc:
            raise SnapshotCompatibilityError(f"invalid Paired-Seed Case: {exc}") from exc
        result._validate()
        return result

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
        return snapshot.fork_roots(self.methods)

    def _validate(self) -> None:
        if self.schema != CASE_SCHEMA:
            raise SnapshotCompatibilityError("unsupported Paired-Seed Case schema")
        if self.chance_schema_version != CHANCE_SCHEMA_VERSION:
            raise SnapshotCompatibilityError("unsupported Chance Sample schema")
        if (not self.orientation or not self.baseline_identity or not self.methods
                or len(set(self.methods)) != len(self.methods)
                or any(not name for name in self.methods)):
            raise SnapshotCompatibilityError("invalid Paired-Seed Case identities")
        body = asdict(self)
        body.pop("case_id")
        if self.case_id != _identity(body):
            raise SnapshotCompatibilityError("Paired-Seed Case content digest mismatch")


MATCH_SCHEMA = "cgpy-paired-seed-match/v1"


@dataclass(slots=True)
class FullMatchRoot:
    method_identity: str
    initial_setup_digest: str
    engine: Engine


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
        body = {
            "schema": MATCH_SCHEMA, "experiment_seed": int(experiment_seed),
            "orientation": str(orientation), "methods": names,
            "baseline_identity": str(baseline_identity), "decks": decks,
            "deck_identities": tuple(_deck_identities([list(deck) for deck in decks])),
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
        return _canonical(asdict(self)).decode("utf-8")

    @classmethod
    def loads(cls, encoded: str) -> "PairedSeedMatch":
        try:
            raw = json.loads(encoded)
            raw["methods"] = tuple(raw["methods"])
            raw["decks"] = tuple(tuple(deck) for deck in raw["decks"])
            raw["deck_identities"] = tuple(raw["deck_identities"])
            result = cls(**raw)
        except (KeyError, TypeError, ValueError) as exc:
            raise SnapshotCompatibilityError(f"invalid Paired-Seed Match: {exc}") from exc
        result._validate()
        return result

    def launch(self, *, parity: ExperimentParityManifest) -> FullMatchLaunch:
        if parity.identity != self.parity_identity:
            raise SnapshotCompatibilityError("Paired-Seed Match parity identity mismatch")
        if parity.coverage_identity != self.coverage_identity:
            raise SnapshotCompatibilityError("Paired-Seed Match coverage identity mismatch")
        roots = {}
        expected = None
        for method in self.methods:
            engine, seat, error = Engine.start(
                list(self.decks[0]), list(self.decks[1]), rng=SeededRng(self.experiment_seed))
            if engine is None:
                raise SnapshotCompatibilityError(
                    f"Paired-Seed Match deck {seat} failed validation with error {error}")
            setup = _digest({"state": _state_payload(engine.gs),
                             "rng": _encode(engine.gs.rng.export_state())})
            if expected is not None and setup != expected:
                raise SnapshotCompatibilityError("Paired-Seed Match setup was not reproducible")
            expected = setup
            roots[method] = FullMatchRoot(method, setup, engine)
        return FullMatchLaunch(expected, self.deck_identities, roots)

    def _validate(self) -> None:
        if self.schema != MATCH_SCHEMA:
            raise SnapshotCompatibilityError("unsupported Paired-Seed Match schema")
        if self.chance_schema_version != CHANCE_SCHEMA_VERSION:
            raise SnapshotCompatibilityError("unsupported Chance Sample schema")
        if (not self.orientation or not self.baseline_identity or not self.methods
                or len(set(self.methods)) != len(self.methods)
                or any(not name for name in self.methods)):
            raise SnapshotCompatibilityError("invalid Paired-Seed Match identities")
        identities = tuple(_deck_identities([list(deck) for deck in self.decks]))
        if identities != self.deck_identities:
            raise SnapshotCompatibilityError("Paired-Seed Match deck identities mismatch")
        body = asdict(self)
        body.pop("case_id")
        if self.case_id != _identity(body):
            raise SnapshotCompatibilityError("Paired-Seed Match content digest mismatch")


__all__ = (
    "CASE_SCHEMA", "FullMatchLaunch", "FullMatchRoot", "MATCH_SCHEMA", "PairedSeedCase",
    "PairedSeedMatch",
)
