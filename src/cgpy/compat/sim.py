"""``cg.sim`` twin (ADR-0059 M3).

Exposes the loader-level names consumers might touch. ``lib_path`` is the sentinel
``"cgpy"`` so tooling can tell the twin from the native engine; there is deliberately no
``lib`` — anything reaching for raw ctypes entry points needs the real DLL and must fail
loudly under the alias.
"""
from ..game import Battle, StartData  # noqa: F401

lib_path = "cgpy"

__all__ = ["Battle", "StartData", "lib_path"]
