"""Structural obs diffing with JSON-path localization (ADR-0050).

`first_divergence(native, ours)` compares parsed JSON with NO normalization — array order is
compared as-is (options/logs/zones are ordered contracts), null vs absent is a real
difference — and returns the first differing path, or None when equal.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class Divergence:
    path: str
    native: Any
    ours: Any

    def __str__(self) -> str:
        def clip(v):
            s = repr(v)
            return s if len(s) <= 220 else s[:220] + "..."
        return f"at {self.path}\n  native: {clip(self.native)}\n  cgpy:   {clip(self.ours)}"


def first_divergence(native: Any, ours: Any, path: str = "$") -> Divergence | None:
    if isinstance(native, dict) and isinstance(ours, dict):
        for key in native:
            if key not in ours:
                return Divergence(f"{path}.{key}", native[key], "<absent>")
            d = first_divergence(native[key], ours[key], f"{path}.{key}")
            if d:
                return d
        extra = [k for k in ours if k not in native]
        if extra:
            return Divergence(f"{path}.{extra[0]}", "<absent>", ours[extra[0]])
        return None
    if isinstance(native, list) and isinstance(ours, list):
        for i, (a, b) in enumerate(zip(native, ours)):
            d = first_divergence(a, b, f"{path}[{i}]")
            if d:
                return d
        if len(native) != len(ours):
            i = min(len(native), len(ours))
            return Divergence(f"{path}[{i}]",
                              native[i] if i < len(native) else "<absent>",
                              ours[i] if i < len(ours) else "<absent>")
        return None
    # Scalars: bool-vs-int must not compare equal by accident (True == 1 in Python) —
    # the wire contract distinguishes them.
    if type(native) is not type(ours) and {type(native), type(ours)} == {bool, int}:
        return Divergence(path, native, ours)
    if native != ours:
        return Divergence(path, native, ours)
    return None
