"""Parity-trace format: a recorded native game as an executable specification (ADR-0059).

Per select the engine posed, a Trace stores the mover's verbatim live obs, the choice answered, and
— when minted natively — the aligned god-view frame. Being the native side of every differential
replay is what makes the CI parity gate DLL-free.

Frame k's `choice` answers frame k's `obs.select` — NO +1 offset. It is null on the terminal frame.
"""
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass, field
from pathlib import Path

SCHEMA = "parity-trace/1"


@dataclass
class Trace:
    meta: dict
    frames: list[dict] = field(default_factory=list)

    @property
    def decks(self) -> tuple[list[int], list[int]]:
        d = self.meta["decks"]
        return list(d[0]), list(d[1])

    def save(self, path: Path | str) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {"schema": SCHEMA, "meta": self.meta, "frames": self.frames}
        raw = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        with open(path, "wb") as raw_fh:
            with gzip.GzipFile(fileobj=raw_fh, mode="wb", mtime=0) as fh:  # mtime=0: git-stable
                fh.write(raw)
        return path

    @classmethod
    def load(cls, path: Path | str) -> "Trace":
        with gzip.open(Path(path), "rb") as fh:
            body = json.loads(fh.read().decode("utf-8"))
        if body.get("schema") != SCHEMA:
            raise ValueError(f"{path}: unknown trace schema {body.get('schema')!r}")
        return cls(meta=body["meta"], frames=body["frames"])


def strip_obs(obs: dict) -> dict:
    """A trace-storable copy of a live obs: the opaque engine-instance blob dropped."""
    out = dict(obs)
    out.pop("search_begin_input", None)
    out.pop("remainingOverageTime", None)  # cabt-sourced obs carry this; not engine state
    out.pop("step", None)                  # ditto
    return out
