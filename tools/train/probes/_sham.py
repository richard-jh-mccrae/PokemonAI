"""The ONE sham-arm vocabulary an argmax probe reports against — ADR-0118's mandatory null.

A probe that reports argmax movement MUST report, in the same table, the movement produced by at
least one sham leg: a term with no causal claim, scaled into the same magnitude band as the term
under test. Shared, because the point of a sham is that it is the *same* arbitrary thing every time.
The tie convention lives here too: `argmax` is FIRST-wins, and under a **Flat Tie** that IS the answer.
"""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

#: The sham arms, in report order. `position` is the degenerate case: a leg that cannot beat LIST
#: ORDER is not ordering anything. `cid`/`hp` are card-derived but causally EMPTY.
SHAMS = (("S_cid", "sham cid%7"), ("S_hp", "sham hp%70"), ("S_pos", "sham position"))


def argmax(values) -> int | None:
    """Index of the maximum, FIRST-wins on a tie. Stated rather than left to `max` because with most
    equal-prize groups tied the tie convention is not a detail — it is what decides the frame."""
    best_i, best_v = None, None
    for i, v in enumerate(values):
        if best_v is None or v > best_v + 1e-12:
            best_i, best_v = i, v
    return best_i


def legs(key: str, *, band: float, card_id, hp, index: int, of: int) -> float:
    """ONE sham arm's addend for ONE row, landing in ``[0, band)``. ``band`` must be the MEASURED
    magnitude of the term under test: a smaller sham loses trivially. Fails to 0, never raises."""
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
#: the table itself.
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
    """The `tune` module loaded by path — `tools/train/tune.py` is a script, not a package member."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def bench_subset(rows, scope: str):
    """The rows an argmax arm ranks, for ``"all"`` or ``"bench"``. BENCH is the real gust seam: the
    opponent's Active is never a legal target, and ranking both lets the Active dominate the argmax."""
    return rows if scope == "all" else [r for r in rows if r["area"] == "bench" and r["value"] > 0]


def tie_population(rows) -> tuple[int, int, int]:
    """``(equal-prize groups, tied on VALUE, tied on survival_shift)`` — the **Flat Tie** count. The
    third is a strict SUB-population of the second; reporting only it was ADR-0117's instrument error."""
    by_prize: dict = {}
    for r in rows:
        by_prize.setdefault(r["prize"], []).append(r)
    groups = [g for g in by_prize.values() if len(g) >= 2]
    return (len(groups),
            sum(1 for g in groups if len({float(r["value"]) for r in g}) == 1),
            sum(1 for g in groups if len({float(r["survival_shift"]) for r in g}) == 1))


class ArmPatch:
    """Collapse a shipped model method to a pre-change reading for a block, by patching the MODEL route
    rather than rebuilding the arithmetic. Class-level latch, so deliberately NOT re-entrant."""

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
