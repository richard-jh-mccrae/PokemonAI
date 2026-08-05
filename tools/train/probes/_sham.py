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
