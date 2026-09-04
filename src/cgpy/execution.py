"""Context-local execution seams used by exact experimental traversal."""
from contextvars import ContextVar


after_begin_turn = ContextVar("cgpy_after_begin_turn", default=None)


__all__ = ("after_begin_turn",)
