"""Shared end-to-end lethal verification helpers (ADR-0050 Phase 2D).

``engine_confirms(fixture, pilot)`` is the gate for multi-step lethal proposals: it drives a seeded
correction fixture's win line through the real engine cascade and returns the engine's verdict. A
closed-form-only line (recognition fires but real play doesn't complete it) returns False here even
though a seed-less unit retest would pass — turning a false-green into a true end-to-end gate.

See docs/adr/0050-multi-step-lethal-verification-tool.md.
"""
from __future__ import annotations


def has_cg() -> bool:
    """True when the committed native engine (``cg``) can be imported."""
    try:
        import cg  # noqa: F401
        return True
    except Exception:
        return False


def require_cg() -> None:
    """Skip the calling test when the native ``cg`` lib is absent (offline-suite safety, DoD #2)."""
    import pytest
    if not has_cg():
        pytest.skip("native cg engine not available")


def engine_confirms(fixture: dict, pilot, *, line=None, max_cascade: int = 40):
    """Verdict: ``True`` win end-to-end, ``False`` refuted, ``None`` undetermined / unseeded /
    no native lib. ``line`` is one select's picks OR a list-of-lists multi-step line, auto-detected."""
    obs = (fixture or {}).get("obs") or {}
    if not obs.get("search_begin_input"):
        return None
    step = line if line is not None else fixture.get("correct")
    if not step:
        return None
    line_steps = list(step) if isinstance(step[0], (list, tuple)) else [list(step)]
    return pilot._engine_confirms_win(obs, line_steps, max_cascade=max_cascade)


def engine_confirms_py(fixture: dict, pilot, *, line=None, max_cascade: int = 40):
    """``engine_confirms`` on the cgpy twin — DLL-free (ADR-0050 M3). A fixture with NO
    ``search_begin_input`` is still driven; one cgpy cannot reconstruct comes back ``None``."""
    from cgpy import alias

    obs = (fixture or {}).get("obs") or {}
    fx = dict(fixture,
              obs=dict(obs, search_begin_input=obs.get("search_begin_input") or "cgpy"))
    alias.install()
    try:
        return engine_confirms(fx, pilot, line=line, max_cascade=max_cascade)
    finally:
        alias.uninstall()
