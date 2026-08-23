"""Stable public types shared by runtime decision producers and protocol adapters."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, order=True)
class ActionIdentity:
    """Canonical public action label; engine-menu index is routing, never identity."""

    kind: str
    parts: tuple = ()


@dataclass(frozen=True)
class RootDecision:
    """One committed engine selection and its observable decision evidence."""

    chosen: tuple[int, ...]
    action: ActionIdentity
    value: float
    complete: bool
    diagnostics: Mapping


__all__ = (
    "ActionIdentity",
    "RootDecision",
)
