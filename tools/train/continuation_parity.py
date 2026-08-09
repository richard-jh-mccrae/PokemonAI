"""Bind seeded continuation observations to recorded native trace successors.

The binding is content-addressed: trace and frame digests name the recorded observation, while the
successor digest proves adjacency. No frame ordinal or menu-shape lookup can manufacture provenance.
"""
from __future__ import annotations

import argparse
import copy
import gzip
import hashlib
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "fixtures" / "continuation_parity"
FIXTURE = FIXTURES / "seeded_continuations.json"


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _load(path: Path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def trace_digest(path: Path | str) -> str:
    """Stable digest of a decoded trace, independent of gzip metadata."""
    return hashlib.sha256(_canonical(_load(Path(path)))).hexdigest()


def frame_digest(frame: dict) -> str:
    """Stable identity of one recorded trace frame."""
    return hashlib.sha256(_canonical(frame)).hexdigest()


def replay_digest(path: Path | str) -> str:
    """Stable decoded-replay identity, independent of compression metadata."""
    return hashlib.sha256(_canonical(_load(Path(path)))).hexdigest()


def observation_digest(obs: dict) -> str:
    """Stable identity of one complete seed-bearing replay observation."""
    return hashlib.sha256(_canonical(obs)).hexdigest()


def _unseeded(obs: dict) -> dict:
    return {key: value for key, value in obs.items() if key != "search_begin_input"}


@dataclass(frozen=True)
class Binding:
    record: dict
    trace: dict | None = None
    replay: dict | None = None
    frame: dict | None = None
    successor: dict | None = None
    reason: str | None = None


def bind_record(record: dict, *, trace_root: Path) -> Binding:
    """Resolve one explicit provenance record, refusing every broken link by its named cause."""
    provenance = record.get("provenance") or {}
    replay_ref = record.get("replay") or {}
    replay_path = trace_root / str(replay_ref.get("path") or "")
    if not replay_path.is_file():
        return Binding(record, reason="missing-replay")
    if replay_digest(replay_path) != replay_ref.get("sha256"):
        return Binding(record, reason="stale-replay")
    replay = _load(replay_path)
    steps = replay.get("steps") or []
    step = replay_ref.get("step")
    if not isinstance(step, int) or not 0 <= step < len(steps):
        return Binding(record, replay=replay, reason="missing-replay-step")
    replay_step = steps[step]
    replay_obs = replay_step.get("observation") if isinstance(replay_step, dict) else None
    if not isinstance(replay_obs, dict) or observation_digest(replay_obs) != replay_ref.get("observation_sha256"):
        return Binding(record, replay=replay, reason="mismatched-replay-observation")
    if replay_obs != (record.get("seed_observation") or {}):
        return Binding(record, replay=replay, reason="seed-observation-mismatch")
    if replay_step.get("choice") != record.get("selected"):
        return Binding(record, replay=replay, reason="selected-index-mismatch")
    path = trace_root / str(provenance.get("trace") or "")
    if not path.is_file():
        return Binding(record, replay=replay, reason="missing-trace")
    if trace_digest(path) != provenance.get("trace_sha256"):
        return Binding(record, replay=replay, reason="stale-trace")
    trace = _load(path)
    frames = trace.get("frames") or []
    matches = [i for i, frame in enumerate(frames)
               if frame_digest(frame) == provenance.get("frame_sha256")]
    if not matches:
        return Binding(record, trace=trace, replay=replay, reason="missing-frame")
    if len(matches) != 1:
        return Binding(record, trace=trace, replay=replay, reason="duplicate-frame")
    index = matches[0]
    frame = frames[index]
    if _unseeded(record.get("seed_observation") or {}) != (frame.get("obs") or {}):
        return Binding(record, trace=trace, replay=replay, reason="seed-observation-mismatch")
    if record.get("selected") != frame.get("choice"):
        return Binding(record, trace=trace, replay=replay, reason="selected-index-mismatch")
    if index + 1 >= len(frames) or frame_digest(frames[index + 1]) != provenance.get("successor_sha256"):
        return Binding(record, trace=trace, replay=replay, reason="reordered-successor")
    return Binding(record, trace=trace, replay=replay, frame=frame, successor=frames[index + 1])


def load_records(path: Path | str = FIXTURE) -> list[dict]:
    """Committed seed-paired continuations, in one versioned fixture document."""
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    if doc.get("schema") != "seeded-continuation/1":
        raise ValueError(f"{path}: unknown seeded continuation schema")
    return list(doc.get("records") or ())


def _normalise(value):
    if isinstance(value, dict):
        return {key: ([None] * len(item) if key == "prize" and isinstance(item, list)
                      else _normalise(item))
                for key, item in value.items()
                if item is not None and key not in {"playerIndex", "remainingOverageTime", "step",
                                                    "search_begin_input", "serial"}}
    if isinstance(value, list):
        return [_normalise(item) for item in value]
    return value


def observable_writes(obs: dict, writes: list[str]) -> dict:
    """The explicitly declared, public successor fields — hidden-zone identities never compare."""
    allowed = {"select", "current"}
    unknown = set(writes) - allowed
    if unknown:
        raise ValueError(f"undeclared observable write: {sorted(unknown)}")
    return {name: _normalise((obs or {}).get(name)) for name in writes}


def _seed_predictions(binding: Binding) -> tuple[list[int], list[int], list[int], list[int], list[int]] | None:
    """Exact hidden zones from the recorded native god frame; absence refuses reconstruction."""
    source = binding.record.get("seed_observation") or {}
    current = source.get("current") or {}
    god_players = ((binding.frame or {}).get("god") or {}).get("players") or []
    seat = int(current.get("yourIndex", -1))
    if not (0 <= seat < len(god_players) and 0 <= 1 - seat < len(god_players)):
        return None
    me, opp = god_players[seat], god_players[1 - seat]

    def ids(player: dict, zone: str) -> list[int]:
        return [int(card["id"]) for card in player.get(zone) or () if isinstance(card, dict) and "id" in card]

    return ids(me, "deck"), ids(me, "prize"), ids(opp, "deck"), ids(opp, "prize"), ids(opp, "hand")


def engine_successor(binding: Binding, *, search_api, token: str | None = None) -> dict | None:
    """Advance one recorded select through a fresh search session; None means the engine refused."""
    if binding.reason or not binding.trace:
        return None
    obs = copy.deepcopy(binding.record.get("seed_observation") or {})
    if token is not None:
        obs["search_begin_input"] = token
    seeds = _seed_predictions(binding)
    if not (obs.get("search_begin_input") and seeds):
        return None
    from common.apply_engine import _prune_none

    started = False
    try:
        state = search_api.search_begin(
            search_api.to_observation_class(obs),
            *seeds, [], manual_coin=False)
        started = True
        state = search_api.search_step(state.searchId, list(binding.record.get("selected") or ()))
        return _prune_none(asdict(state.observation))
    except Exception:  # noqa: BLE001 — a continuation lacking state is unmodellable, never guessed.
        return None
    finally:
        if started:
            try:
                search_api.search_end()
            except Exception:  # noqa: BLE001 — cleanup cannot turn a refusal into a crash.
                pass


@dataclass(frozen=True)
class Verification:
    backend: str
    reason: str | None = None


def verify_record(binding: Binding, *, search_api, backend: str, token: str | None = None) -> Verification:
    """Compare the backend successor with only this record's declared observable writes."""
    if binding.reason:
        return Verification(backend, f"provenance:{binding.reason}")
    after = engine_successor(binding, search_api=search_api, token=token)
    if after is None:
        return Verification(backend, "engine-refused")
    expected = (binding.successor or {}).get("obs") or {}
    writes = binding.record.get("writes") or []
    if observable_writes(after, writes) != observable_writes(expected, writes):
        return Verification(backend, "observable-mismatch")
    return Verification(backend)


@dataclass
class Report:
    population: Counter = field(default_factory=Counter)
    seeded: Counter = field(default_factory=Counter)
    refused: Counter = field(default_factory=Counter)
    verified: Counter = field(default_factory=Counter)
    backends: Counter = field(default_factory=Counter)

    def as_dict(self) -> dict:
        refused = {}
        for (context, reason), count in sorted(self.refused.items()):
            refused.setdefault(context, {})[reason] = count
        return {"population": dict(sorted(self.population.items())),
                "seeded": dict(sorted(self.seeded.items())),
                "refused": refused,
                "verified": dict(sorted(self.verified.items())),
                "backends": dict(sorted(self.backends.items()))}


def sweep(records: list[dict] | None = None, *, trace_root: Path = FIXTURES, search_api=None,
          backend: str = "recorded-native", token: str | None = None) -> Report:
    """Diagnostic census. Broken provenance and engine refusals are reported, never a gate verdict."""
    report = Report()
    for record in records if records is not None else load_records():
        context = int(record.get("context", -1))
        report.population[context] += 1
        binding = bind_record(record, trace_root=trace_root)
        if binding.reason:
            report.refused[(context, binding.reason)] += 1
            continue
        report.seeded[context] += 1
        if search_api is None:
            continue
        report.backends[backend] += 1
        verdict = verify_record(binding, search_api=search_api, backend=backend, token=token)
        if verdict.reason:
            report.refused[(context, verdict.reason)] += 1
        else:
            report.verified[context] += 1
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Report seeded continuation parity provenance.")
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--native", action="store_true", help="also run the native search API")
    parser.add_argument("--cgpy", action="store_true", help="also run the cgpy token-equivalent path")
    args = parser.parse_args(argv)
    if args.native and args.cgpy:
        parser.error("choose one engine backend")
    root = args.fixture.parent
    api = token = None
    backend = "recorded-native"
    if args.cgpy:
        sys.path[:0] = [str(REPO / "src")]
        from cgpy import alias
        alias.install()
        from cg import api as api  # noqa: PLC0415
        backend, token = "cgpy", "cgpy"
    elif args.native:
        sys.path[:0] = [str(REPO / "src")]
        from cg import api as api  # noqa: PLC0415
        backend = "native"
    try:
        print(json.dumps(sweep(load_records(args.fixture), trace_root=root, search_api=api,
                               backend=backend, token=token).as_dict(), sort_keys=True))
    finally:
        if args.cgpy:
            alias.uninstall()
    return 0


__all__ = ("Binding", "FIXTURE", "FIXTURES", "Report", "Verification", "bind_record",
           "engine_successor", "frame_digest", "load_records", "observation_digest",
           "observable_writes", "replay_digest", "sweep", "trace_digest", "verify_record")


if __name__ == "__main__":
    raise SystemExit(main())
