"""Parity-trace format: a recorded native game as an executable specification (ADR-0050).

A Trace stores, per select the native engine posed: the mover's full observation (verbatim
live-obs dict, int enums), the choice answered, and — when minted natively — the god-view frame
(`visualize_data` style, revealing decks/hands) aligned to the same select. The trace *is* the
native side of every differential replay, which is what makes the CI parity gate DLL-free.

Schema `parity-trace/1`:
{
  "schema": "parity-trace/1",
  "meta": {"created", "engine_sha", "decks": [[60 ids],[60 ids]], "policy", "purpose",
            "result": {"winner": int|-1|2, "steps": int}},
  "frames": [{"obs": {...live obs, search_begin_input stripped...},
              "choice": [int, ...] | null,          # null on the terminal frame
              "god": {...visualize frame current...} | null}],
}

Frame k's `choice` answers frame k's `obs.select` (no +1 offset; the visualize `selected`
convention is realigned at capture).
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
