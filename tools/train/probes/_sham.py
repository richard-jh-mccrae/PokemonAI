"""The ONE sham-arm vocabulary an argmax probe reports against — ADR-0118's mandatory null.

The sibling of `_corpus.py`, and it exists for the same reason that one does. ADR-0118 (sham
control) makes a sham arm **mandatory** for every probe that reports argmax movement:

    A probe that reports argmax movement MUST report, in the same table, the movement produced by
    at least one sham leg — a term with no causal claim, scaled into the same magnitude band as the
    term under test.

A mandatory element with no shared home is a guarantee that the second implementation will differ
from the first in some detail nobody compares — and the whole point of a sham is that it is the
*same* arbitrary thing every time. `opponent_target_credit_sweep.py` and `fractional_clock_sweep.py`
had byte-similar copies of the leg expressions, the argmax tie convention, and the arm labels within
one change of each other; that is the drift `_corpus.py`'s docstring describes ("Five copies is five
places a defect can live"), caught before it reached five.

The tie convention lives here too, and deliberately. `argmax` is FIRST-wins on a tie, and under a
**Flat Tie** population that convention IS the answer on most frames — so two probes disagreeing
about it would silently be measuring two different questions.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

#: The sham arms, in report order. `position` is the degenerate case and is worth printing because a
#: leg that cannot beat LIST ORDER is not ordering anything — and list order is exactly what a Flat
#: Tie already falls back to. `cid`/`hp` are card-derived but causally EMPTY: a card's id modulo 7
#: has no claim on anything, which is the property being borrowed.
SHAMS = (("S_cid", "sham cid%7"), ("S_hp", "sham hp%70"), ("S_pos", "sham position"))


def argmax(values) -> int | None:
    """Index of the maximum, FIRST-wins on a tie.

    Stated rather than left to `max`'s default because with most equal-prize groups tied the tie
    convention is not an implementation detail — it is what decides the frame. A probe's null arm
    (an arm against itself, expecting 0) is what proves this is stable."""
    best_i, best_v = None, None
    for i, v in enumerate(values):
        if best_v is None or v > best_v + 1e-12:
            best_i, best_v = i, v
    return best_i


def legs(key: str, *, band: float, card_id, hp, index: int, of: int) -> float:
    """ONE sham arm's addend for ONE row, scaled into ``band``.

    ``band`` must be the measured magnitude of the term under test, not a guess: a sham an order of
    magnitude smaller loses trivially and proves nothing, which is the failure ADR-0118's
    band-matching rule exists to prevent. Each leg lands in ``[0, band)``.

    Fails to 0 on an unreadable input rather than raising — a sham has no causal claim to protect,
    so the conservative direction is simply to contribute nothing."""
    if key == "S_cid":
        return ((int(card_id or 0) % 7) / 7.0) * band
    if key == "S_hp":
        try:
            return ((float(hp or 0) % 70) / 70.0) * band
        except (TypeError, ValueError):
            return 0.0
    if key == "S_pos":
        return (index / max(1, of)) * band
    raise KeyError(f"unknown sham arm {key!r} — the arms are {[k for k, _ in SHAMS]}")


#: The closing note every argmax probe prints. Shared so the READING of the table cannot drift from
#: the table: beating a sham shows a leg DISCRIMINATES, never that it discriminates CORRECTLY, and
#: (ADR-0118's 2026-08-05 amendment) a leg well BELOW its sham has not been falsified —
#: leaving structurally-tied orderings alone is correct behaviour, not weakness.
READING = (
    "READ THE CANDIDATE ROWS AGAINST THE SHAM ROWS, NOT AGAINST ZERO. A candidate that MATCHES "
    "`sham cid%7` has discriminated nothing — it has broken flat ties, which any number of that "
    "size does. `sham position` is the floor: a leg below it loses to list order. A leg well BELOW "
    "its shams is a different case and is NOT thereby refuted — declining to break a Structural "
    "Zero is correct; ask a different question of it rather than reading a verdict off this table. "
    "And beating the shams shows a leg DISCRIMINATES, never that it discriminates CORRECTLY — the "
    "corpus rules chosen options, not internal orderings, so the decision test remains "
    "`decider_lab.py diff --baseline data/decider_lab/baseline.json` against a pre-registered "
    "prediction. This probe reports; it does not gate.")


def tune():
    """The `tune` module, loaded by path — every probe's route to `_build_pilot`.

    Loaded rather than imported because `tools/train/tune.py` is a script, not a package member.
    Shared here after the third copy appeared; the two sweeps in this directory had it byte-identical
    and `snipe_decider_sweep` has a fourth. New probes should call this one."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bench_subset(rows, scope: str):
    """The rows an argmax arm ranks, for ``"all"`` or ``"bench"``.

    BENCH is the real seam for a gust: the opponent's Active is never a legal gust target, and
    ranking both areas together lets the Active dominate the argmax — the mis-scoping that produced
    ADR-0118's founding false headline. ``value > 0`` drops rows a consumer would not offer."""
    return rows if scope == "all" else [r for r in rows if r["area"] == "bench" and r["value"] > 0]


def tie_population(rows) -> tuple[int, int, int]:
    """``(equal-prize groups, tied on VALUE, tied on survival_shift)`` — the **Flat Tie** count.

    Grouped on the row's OWN ``prize``, which is what an equal-prize group means; grouping on a
    derived ``prize_advance`` would let a leg look like it dissolved ties it had merely renamed.

    **The first count is the Flat Tie. The second is a strict SUB-population of it** — equal prize
    plus equal shift forces equal value, but not the converse, because `opponent_target_value` floors
    the shift at 0 and at ``phase == 0`` the survival term vanishes entirely. Reporting only the
    shift count was ADR-0117's instrument error and it biased BOTH directions at once: it understated
    the defect and overstated the fix. Both are returned so the gap stays visible."""
    by_prize: dict = {}
    for r in rows:
        by_prize.setdefault(r["prize"], []).append(r)
    groups = [g for g in by_prize.values() if len(g) >= 2]
    return (len(groups),
            sum(1 for g in groups if len({float(r["value"]) for r in g}) == 1),
            sum(1 for g in groups if len({float(r["survival_shift"]) for r in g}) == 1))


class ArmPatch:
    """Collapse a shipped model method to a pre-change reading for the duration of a block.

    Patches the MODEL route rather than reimplementing the old arithmetic: a hand-rebuilt "what it
    used to do" is the second oracle ADR-0117 was written to avoid, and it would drift from the real
    prior behaviour with nothing reporting it.

    Subclass and set ``target`` (the class), ``name`` (the method) and ``collapse`` (a callable
    taking the real bound method's result and returning the pre-change one). Class-level latch, so
    it is deliberately NOT re-entrant — a nested enter would capture the PATCHED function as the
    real one and never restore it, which is a silent corruption rather than a loud one."""

    target: type = None
    name: str = ""
    _real = None

    @classmethod
    def collapse(cls, value):
        raise NotImplementedError

    def __enter__(self):
        if type(self)._real is not None:
            raise RuntimeError(f"{type(self).__name__} is not re-entrant — a nested enter would "
                               f"capture the PATCHED function as the real one and never restore it")
        type(self)._real = real = getattr(self.target, self.name)
        collapse = type(self).collapse
        setattr(self.target, self.name, lambda side, *a, **kw: collapse(real(side, *a, **kw)))
        return self

    def __exit__(self, *exc):
        setattr(self.target, self.name, type(self)._real)
        type(self)._real = None
        return False              # never swallow — restore, then let the caller's own try see it
