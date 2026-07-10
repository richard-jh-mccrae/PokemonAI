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
    """Drive ``fixture``'s win line through the engine cascade and return the verdict:

    - ``True``  — the engine declares the win end-to-end (real play completes the line),
    - ``False`` — refuted (a closed-form-only line lands here),
    - ``None``  — undetermined / no seed on the fixture / native lib absent (keep closed-form).

    ``line`` defaults to the fixture's ``correct``. It is EITHER a single select's picks (``[1]`` — the
    common case: drive that one explicit step, then ``decide()`` completes the cascade) OR a full
    explicit multi-step line, a list-of-lists (``[[5],[1],[2],...]`` — drive every listed select, then
    ``decide()`` handles only the trailing pure cascades). The shape is auto-detected (mirrors
    ``tools/sim/lethal_probe.py``): a first element that is itself a list means a multi-step line.

    The multi-step form is the gate for a lethal whose ``decide()`` follow-up hooks are UNBUILT: its
    ``[correct]``-only form can't be confirmed (``decide()`` won't steer the retreat/promote/tool line),
    so the target win is proven by driving the whole line explicitly (ADR-0050 DoD#3, ml f24). Once the
    Phase-3 hooks exist, the single-step form goes green on its own — that is the fix's gate.

    A no-op returning ``None`` when the fixture carries no ``search_begin_input`` (or an empty line), so
    it never needs the engine on an unseeded fixture."""
    obs = (fixture or {}).get("obs") or {}
    if not obs.get("search_begin_input"):
        return None
    step = line if line is not None else fixture.get("correct")
    if not step:
        return None
    line_steps = list(step) if isinstance(step[0], (list, tuple)) else [list(step)]
    return pilot._engine_confirms_win(obs, line_steps, max_cascade=max_cascade)
