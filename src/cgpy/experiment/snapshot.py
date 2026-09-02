"""Persistent exact roots for deterministic cgpy experiments (ADR-0195)."""
from __future__ import annotations

import gzip
import hashlib
import json
import platform
from copy import deepcopy
from dataclasses import dataclass, field, fields, is_dataclass
from pathlib import Path

from common.observation import ObservationStateBuilder
from common.observation.record import ObservationRecord

from ..cards import CardDB
from ..engine import Engine
from ..rng import SeededRng
from ..search import export_token
from ..state import (CardInstance, EffectFrame, GameState, PendingSelect, PlayerBoard,
                     PokemonInPlay, SERIAL_BASE)


SCHEMA = "cgpy-experiment-snapshot"
SCHEMA_VERSION = 2
RNG_SCHEMA = "python-random/v1"
_ENGINE_MODULES = (
    "cards.py", "chain.py", "damage.py", "engine.py", "execution.py", "options.py",
    "render.py", "rng.py", "schema.py", "search.py", "state.py", "turn.py",
)
_STATE_TYPES = {item.__name__: item for item in (
    CardInstance, EffectFrame, PendingSelect, PlayerBoard, PokemonInPlay,
)}
_GAME_FIELDS = (
    "cards", "players", "turn", "turn_action_count", "first_player",
    "supporter_played", "stadium_played", "energy_attached", "retreated",
    "result", "result_reason", "stadium", "turn_markers", "ko_turn",
    "attach_seq", "attach_tick", "looking", "looking_owner", "pending",
    "frames", "pending_triggers", "last_posed", "outbox", "outbox_god",
    "phase", "phase_data", "manual_coin",
)


class SnapshotCompatibilityError(ValueError):
    pass


def _encode(value):
    if is_dataclass(value) and not isinstance(value, type):
        return {"$type": type(value).__name__,
                "fields": [[field.name, _encode(getattr(value, field.name))]
                           for field in fields(value)]}
    if isinstance(value, dict):
        return {"$dict": [[_encode(key), _encode(child)]
                          for key, child in value.items()]}
    if isinstance(value, tuple):
        return {"$tuple": [_encode(child) for child in value]}
    if isinstance(value, list):
        return [_encode(child) for child in value]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"unsupported snapshot value {type(value).__name__}")


def _decode(value):
    if isinstance(value, list):
        return [_decode(child) for child in value]
    if not isinstance(value, dict):
        return value
    if "$dict" in value:
        return {_decode(key): _decode(child) for key, child in value["$dict"]}
    if "$tuple" in value:
        return tuple(_decode(child) for child in value["$tuple"])
    name = value.get("$type")
    cls = _STATE_TYPES.get(name)
    if cls is None:
        raise SnapshotCompatibilityError(f"unsupported snapshot state type {name!r}")
    return cls(**{key: _decode(child) for key, child in value["fields"]})


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _digest(value) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _file_identity(paths, *, base: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(map(Path, paths)):
        name = path.relative_to(base).as_posix().encode("utf-8")
        raw = Path(path).read_bytes()
        hasher.update(len(name).to_bytes(8, "big"))
        hasher.update(name)
        hasher.update(len(raw).to_bytes(8, "big"))
        hasher.update(raw)
    return hasher.hexdigest()


def _identities() -> dict:
    root = Path(__file__).resolve().parents[1]
    repo = root.parents[1]
    definitions = root / "defs"
    return {
        "engine": _file_identity((root / name for name in _ENGINE_MODULES), base=repo),
        "snapshot": _file_identity((Path(__file__),), base=repo),
        "legal_view": _file_identity((repo / "src" / "common" / "api.py",
                                      *(repo / "src" / "common" / "observation").rglob("*.py")),
                                     base=repo),
        "card_tables": _file_identity((definitions / name for name in (
            "card_data.json", "attack_data.json", "tables_meta.json")), base=repo),
        "chain_definitions": _file_identity((definitions / name for name in (
            "chain_overrides.json", "generated_chains.json")), base=repo),
        "rng": RNG_SCHEMA,
    }


def _decks(gs: GameState) -> list[list[int]]:
    return [[gs.card_id(SERIAL_BASE[seat] + index) for index in range(60)]
            for seat in (0, 1)]


def _deck_identities(decks: list[list[int]]) -> list[str]:
    return [_digest(deck) for deck in decks]


def _assert_card_partition(gs: GameState) -> None:
    locations: list[tuple[int, int | None]] = []
    for seat, board in enumerate(gs.players):
        for zone in (board.deck, board.hand, board.discard, board.prize):
            locations.extend((serial, seat) for serial in zone)
        for pokemon in ([board.active] if board.active else []) + board.bench:
            for zone in (pokemon.stack, pokemon.energy, pokemon.tools):
                locations.extend((serial, seat) for serial in zone)
    locations.extend((serial, None) for serial in gs.stadium)
    locations.extend((serial, None) for serial in (gs.looking or ()))
    serials = [serial for serial, _seat in locations]
    cards = set(gs.cards)
    if set(serials) != cards or len(serials) != len(cards):
        raise SnapshotCompatibilityError("Experiment Snapshot card zone partition is invalid")
    for serial, seat in locations:
        card = gs.cards.get(serial)
        if card is None or card.serial != serial or (seat is not None and card.owner != seat):
            raise SnapshotCompatibilityError("Experiment Snapshot card zone partition is invalid")


def _state_payload(gs: GameState) -> dict:
    excluded = {"db", "rng", "parity_manifest", "executed_chains"}
    actual = tuple(field.name for field in fields(GameState) if field.name not in excluded)
    if actual != _GAME_FIELDS:
        raise SnapshotCompatibilityError("GameState field inventory changed")
    return {name: _encode(getattr(gs, name)) for name in _GAME_FIELDS}


def _restore_state(payload: dict, rng_state) -> GameState:
    if set(payload) != set(_GAME_FIELDS):
        raise SnapshotCompatibilityError("snapshot GameState fields do not match this engine")
    values = {name: _decode(payload[name]) for name in _GAME_FIELDS}
    return GameState(db=CardDB.load(), rng=SeededRng.from_state(_decode(rng_state)), **values)


def _assert_root(gs: GameState, seat: int) -> None:
    pending = gs.pending
    if (gs.phase != "TURN" or pending is None or pending.seat != seat
            or pending.type != 0 or pending.context != 0 or gs.turn_action_count != 1
            or gs.supporter_played or gs.stadium_played or gs.energy_attached or gs.retreated
            or gs.frames or gs.pending_triggers or gs.turn_markers):
        raise ValueError("Experiment Snapshot requires the first Main decision of a turn")


def _observation_record(engine: Engine, seat: int, deck: list[int]) -> ObservationRecord:
    raw = engine.observation(viewer=seat, sbi_token=export_token(engine.gs))
    return ObservationRecord.from_state(ObservationStateBuilder(deck).root(raw))


@dataclass(frozen=True, slots=True, init=False)
class ExperimentSnapshot:
    _document: dict = field(repr=False)

    def __init__(self, document: dict):
        object.__setattr__(self, "_document", deepcopy(document))

    @property
    def document(self) -> dict:
        return deepcopy(self._document)

    @classmethod
    def capture(cls, engine: Engine, *, seat: int | None,
                provenance: dict | None = None) -> "ExperimentSnapshot":
        if not isinstance(engine.gs.rng, SeededRng):
            raise ValueError("Experiment Snapshot requires SeededRng")
        if seat not in (0, 1):
            raise ValueError("Experiment Snapshot seat must be 0 or 1")
        _assert_root(engine.gs, seat)
        _assert_card_partition(engine.gs)
        decks = _decks(engine.gs)
        state = _state_payload(engine.gs)
        rng = _encode(engine.gs.rng.export_state())
        observation = json.loads(_observation_record(engine, seat, decks[seat]).dumps())
        observed = ObservationRecord.loads(json.dumps(observation)).to_state()
        body = {
            "schema": SCHEMA, "schema_version": SCHEMA_VERSION,
            "identities": {**_identities(), "decks": _deck_identities(decks)},
            "producer": {"python": platform.python_version()},
            "provenance": _encode(provenance or {}),
            "seat": seat, "turn": engine.gs.turn,
            "position_key": observed.position_key,
            "decision_key": observed.decision_key,
            "observation": observation, "state": state, "rng_state": rng,
            "full_state_digest": _digest(state), "rng_digest": _digest(rng),
            "initial_setup_digest": _digest({
                "state": state, "decks": _deck_identities(decks)}),
        }
        return cls({**body, "snapshot_id": _digest(body)})

    @classmethod
    def from_trace(cls, trace, *, frame: int, experiment_seed: int,
                   provenance: dict | None = None) -> "ExperimentSnapshot":
        from ..verify.replayer import replay

        if not 0 <= frame < len(trace.frames):
            raise SnapshotCompatibilityError(f"trace frame {frame} does not exist")
        if not isinstance(trace.frames[frame].get("god"), dict):
            raise SnapshotCompatibilityError(
                f"trace frame {frame} has no full-information god frame")
        captured = []

        def collect(index, engine):
            if index == frame:
                engine.gs.rng = SeededRng(experiment_seed)
                captured.append(engine)

        report = replay(trace, on_frame=collect)
        if not report.clean:
            raise SnapshotCompatibilityError(f"trace did not verify: {report}")
        if not captured:
            raise SnapshotCompatibilityError(f"trace frame {frame} was not replayed")
        metadata = dict(provenance or {})
        metadata.update({
            "trace_frame": int(frame),
            "trace_engine": trace.meta.get("engine_sha"),
            "randomness_epoch_seed": int(experiment_seed),
        })
        return cls.capture(captured[0], seat=captured[0].select_seat,
                           provenance=metadata)

    @property
    def snapshot_id(self) -> str:
        return str(self._document["snapshot_id"])

    @property
    def full_state_digest(self) -> str:
        return str(self._document["full_state_digest"])

    @property
    def rng_digest(self) -> str:
        return str(self._document["rng_digest"])

    @property
    def initial_setup_digest(self) -> str:
        return str(self._document["initial_setup_digest"])

    @property
    def deck_identities(self) -> tuple[str, str]:
        return tuple(self._document["identities"]["decks"])

    @property
    def provenance(self) -> dict:
        return _decode(self._document["provenance"])

    @property
    def observation(self):
        self._validate()
        self._restore_engine()
        raw = self._document["observation"]
        return ObservationRecord.loads(json.dumps(raw, sort_keys=True)).to_state()

    def save(self, path: Path | str) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".tmp")
        with temporary.open("wb") as raw:
            with gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as stream:
                stream.write(_canonical(self._document))
        temporary.replace(target)
        return target

    @classmethod
    def load(cls, path: Path | str) -> "ExperimentSnapshot":
        try:
            with gzip.open(Path(path), "rb") as stream:
                document = json.loads(stream.read().decode("utf-8"))
        except (OSError, UnicodeError, ValueError) as exc:
            raise SnapshotCompatibilityError(f"invalid Experiment Snapshot: {exc}") from exc
        snapshot = cls(document)
        snapshot._validate()
        snapshot._restore_engine()
        return snapshot

    def fork_engine(self) -> Engine:
        self._validate()
        return self._restore_engine()

    def _restore_engine(self) -> Engine:
        document = self._document
        engine = Engine(_restore_state(document["state"], document["rng_state"]))
        _assert_card_partition(engine.gs)
        if _deck_identities(_decks(engine.gs)) != list(self.deck_identities):
            raise SnapshotCompatibilityError("Experiment Snapshot deck identities mismatch")
        seat = int(document["seat"])
        _assert_root(engine.gs, seat)
        observed = _observation_record(
            engine, seat, _decks(engine.gs)[seat])
        observed_raw = json.loads(observed.dumps())
        observed_state = observed.to_state()
        if observed_raw != document["observation"]:
            raise SnapshotCompatibilityError("snapshot legal-view Observation mismatch")
        if observed_state.position_key != document["position_key"]:
            raise SnapshotCompatibilityError("snapshot Position Key mismatch")
        if observed_state.decision_key != document["decision_key"]:
            raise SnapshotCompatibilityError("snapshot Decision Key mismatch")
        if engine.gs.turn != document["turn"] or engine.select_seat != seat:
            raise SnapshotCompatibilityError("snapshot turn or seat metadata mismatch")
        return engine

    def fork_roots(self, methods) -> dict[str, Engine]:
        names = tuple(str(method) for method in methods)
        if not names or any(not name for name in names) or len(set(names)) != len(names):
            raise ValueError("Experiment Root method identities must be unique and non-empty")
        return {name: self.fork_engine() for name in names}

    def policy_roots(self, methods):
        from .roots import PolicyRoot

        names = tuple(str(method) for method in methods)
        if not names or any(not name for name in names) or len(set(names)) != len(names):
            raise ValueError("Policy Root method identities must be unique and non-empty")
        observation = self.observation
        return {name: PolicyRoot(name, self.snapshot_id, observation) for name in names}

    def _validate(self) -> None:
        document = self._document
        if document.get("schema") != SCHEMA or document.get("schema_version") != SCHEMA_VERSION:
            raise SnapshotCompatibilityError(
                f"unsupported Experiment Snapshot schema "
                f"{document.get('schema')!r}/{document.get('schema_version')!r}")
        identities = document.get("identities")
        if not isinstance(identities, dict):
            raise SnapshotCompatibilityError("Experiment Snapshot identities are missing")
        for name, expected in _identities().items():
            if identities.get(name) != expected:
                raise SnapshotCompatibilityError(
                    f"Experiment Snapshot {name} identity mismatch")
        decks = identities.get("decks")
        if (not isinstance(decks, list) or len(decks) != 2
                or any(not isinstance(item, str) or len(item) != 64 for item in decks)):
            raise SnapshotCompatibilityError("Experiment Snapshot deck identities are invalid")
        body = {key: value for key, value in document.items() if key != "snapshot_id"}
        if document.get("snapshot_id") != _digest(body):
            raise SnapshotCompatibilityError("Experiment Snapshot content digest mismatch")
        if document.get("full_state_digest") != _digest(document.get("state")):
            raise SnapshotCompatibilityError("Experiment Snapshot full-state digest mismatch")
        if document.get("rng_digest") != _digest(document.get("rng_state")):
            raise SnapshotCompatibilityError("Experiment Snapshot RNG digest mismatch")
        expected_setup = _digest({"state": document.get("state"), "decks": decks})
        if document.get("initial_setup_digest") != expected_setup:
            raise SnapshotCompatibilityError("Experiment Snapshot setup digest mismatch")


__all__ = ("ExperimentSnapshot", "SnapshotCompatibilityError")
