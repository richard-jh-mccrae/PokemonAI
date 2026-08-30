"""Context-local execution seams used by exact experimental traversal."""
from contextvars import ContextVar


before_begin_turn = ContextVar("cgpy_before_begin_turn", default=None)


__all__ = ("before_begin_turn",)
