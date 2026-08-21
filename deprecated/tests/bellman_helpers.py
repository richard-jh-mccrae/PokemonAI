"""Shared constructors for the Bellman teacher runtime."""
from __future__ import annotations

from agent_helpers import deck, strategy
from deprecated.bellman import build_teacher_runtime

__all__ = ("deck", "runtime", "strategy")


def runtime(name: str = "mega_starmie"):
    """The TEACHER runtime: every consumer of this helper pins Bellman's own behavior
    (ADR-0145/0149); the offline cgpy provider gains its search hooks inside the teacher."""
    from common.engine import CgpyTransitionProvider
    return build_teacher_runtime(strategy(name), deck(name),
                                 provider_factory=CgpyTransitionProvider)
