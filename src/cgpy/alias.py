"""Route ``import cg`` to the cgpy compat surface (ADR-0059 M3).

`install()` maps ``cgpy.compat`` (and its submodules) over ``sys.modules["cg"]``/
``cg.api``/``cg.game``/``cg.sim``/``cg.utils`` — a sys.modules mapping wins over the
path-based import, so ``src/cg/`` is never touched and the DLL never loads. Displaced
modules (a native ``cg`` already imported) are stashed and restored by `uninstall()`.

`install_if_enabled()` gates on the environment: ``CG_ENGINE=py`` installs, anything else
is a no-op — the wire-up call sites stay byte-identical to today when the variable is
unset.
"""
from __future__ import annotations

import os
import sys

_NAMES = ("cg", "cg.api", "cg.game", "cg.sim", "cg.utils")
_stash: dict[str, object] | None = None


def installed() -> bool:
    from . import compat
    return sys.modules.get("cg") is compat


def install() -> None:
    """Map the compat package over the ``cg`` module names (idempotent)."""
    global _stash
    from . import compat
    if installed():
        return
    _stash = {name: sys.modules[name] for name in _NAMES if name in sys.modules}
    sys.modules["cg"] = compat
    sys.modules["cg.api"] = compat.api
    sys.modules["cg.game"] = compat.game
    sys.modules["cg.sim"] = compat.sim
    sys.modules["cg.utils"] = compat.utils


def uninstall() -> None:
    """Undo `install()`, restoring any displaced native modules (idempotent)."""
    global _stash
    if not installed():
        return
    for name in _NAMES:
        orig = (_stash or {}).get(name)
        if orig is not None:
            sys.modules[name] = orig
        else:
            sys.modules.pop(name, None)
    _stash = None


def install_if_enabled() -> bool:
    """Install when ``CG_ENGINE=py``; returns whether the alias is active."""
    if os.environ.get("CG_ENGINE") != "py":
        return False
    install()
    return True
