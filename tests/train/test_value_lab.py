"""`train.value_lab` — the MENU leg, which turns a leaf UNIT cost into a per-decision one
(Issue #291).

Two ways the number could be quietly wrong: the collapse must be ADR-0091's own
(`class_representatives`), not a second derivation, and the apply-seam term is ABSENT and must
say so — the derived figure is a LOWER BOUND, carried as a field rather than as prose."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
for sub in ("tools", "src"):
    path = str(REPO / sub)
    if path not in sys.path:
        sys.path.insert(0, path)

# `option_equivalence`'s own area numbers are imported rather than re-spelled — that module pins them
# to `cg.api.AreaType` with a test, and a second literal here would be a second unpinned copy.
from common.option_equivalence import (  # noqa: E402
    AREA_BENCH, AREA_DECK, AREA_HAND, class_representatives, option_equivalence,
)
from common.state_value import FAMILIES  # noqa: E402
from train.value_lab import (  # noqa: E402
    APPLY_SEAM_UNMEASURED, menu_profile, menu_report, value_lab_report,
)


def _energy(index, recipient_index):
    """An ATTACH — the shape naming TWO zones, where a body-only fingerprint would falsely merge."""
    return {"type": 7, "area": AREA_HAND, "index": index,
            "inPlayArea": AREA_BENCH, "inPlayIndex": recipient_index}


def _frame(bench_hp):
    """One seat, a hand of two identical Energy, a bench of bodies whose HP the caller sets."""
    return {"current": {"yourIndex": 0, "players": [{
        "hand": [{"id": 500, "serial": 1}, {"id": 500, "serial": 2}],
        "bench": [{"id": 900, "serial": 10 + i, "hp": hp} for i, hp in enumerate(bench_hp)],
    }]}}


def _correction(options, frame):
    """A record carrying the four fields `blunder.correction.identity_key` reads, so the profile's
    key comes from the ONE shared derivation (ADR-0087 decision 2) rather than a stub of it."""
    return SimpleNamespace(obs={**frame, "select": {"option": options}}, agent="mega_starmie",
                           episode_id="82225643", seat=1, scope="decision", subject=57)


# ── the collapse is ADR-0091's ────────────────────────────────────────────────────────────────────

def test_post_collapse_count_is_option_equivalences_own():
    """Asserted against `class_representatives`, not a hand-written integer, so the count moves with it."""
    frame = _frame([60, 60])
    options = [_energy(i, b) for i in (0, 1) for b in (0, 1)]
    prof = menu_profile(_correction(options, frame))
    expected = len(class_representatives(option_equivalence(options, frame), len(options)))
    assert prof["menu"] == 4
    assert prof["post_oec"] == expected
    assert prof["post_oec"] < prof["menu"], "identical siblings must collapse, or the seam is inert"


def test_a_menu_with_nothing_to_collapse_is_unchanged():
    """The positive control's negative half: a collapse that fired on everything would also pass above."""
    frame = _frame([60, 30])                       # different HP -> different class
    options = [_energy(0, 0), _energy(0, 1)]
    prof = menu_profile(_correction(options, frame))
    assert prof["menu"] == prof["post_oec"] == 2


def test_an_unfingerprintable_option_joins_no_class():
    """Blind implies conservative: an option the snapshot does not reveal must never merge."""
    frame = _frame([60])
    options = [{"type": 8, "area": AREA_DECK, "index": 0}, {"type": 8, "area": AREA_DECK, "index": 0}]
    prof = menu_profile(_correction(options, frame))
    assert prof["post_oec"] == 2, "the face-down deck exposes only a count — it must group with nothing"


# ── the fate split, and the absent term ───────────────────────────────────────────────────────────

_BUCKETS = ("terminal", "modelled", "refused", "engine", "unclassified")


def test_the_fate_split_counts_every_option_once():
    frame = _frame([60])
    options = [_energy(0, 0), {"type": 14}, {"type": 3, "area": 1, "index": 0}]
    prof = menu_profile(_correction(options, frame))
    assert sum(prof[b] for b in _BUCKETS) == prof["menu"]
    assert prof["terminal"] == 1


def test_the_fate_split_bins_by_the_seams_own_constants():
    """Matched by EQUALITY against the exported fates, so a rename fails instead of mis-binning."""
    from common.apply_option import MODELLED, REFUSED, fate

    frame = _frame([60])
    modelled_opt, refused_opt = _energy(0, 0), {"type": 3, "area": 1, "index": 0}
    assert fate(modelled_opt) == MODELLED and fate(refused_opt) == REFUSED   # positive control
    prof = menu_profile(_correction([modelled_opt, refused_opt], frame))
    assert (prof["modelled"], prof["refused"]) == (1, 1)


def test_an_unclassifiable_option_is_its_own_bucket_never_refused():
    """An instrument failure must not be laundered into a seam verdict; `refused` is a fate acted on."""
    frame = _frame([60])
    prof = menu_profile(_correction([{"type": "not-an-int-kind"}], frame))
    assert prof["menu"] == 1
    assert prof["unclassified"] == 1
    assert prof["refused"] == 0


def test_the_report_names_the_apply_seam_as_UNMEASURED():
    """The honesty field. `apply_option` raises for every MODELLED fate at this commit, so the derived
    per-decision figure is a LOWER BOUND and must be readable as one from the artifact alone."""
    rpt = menu_report([{"menu": 4, "post_oec": 3, "terminal": 1, "modelled": 3,
                        "refused": 0, "engine": 0, "key": "82225643|1|decision|57"}], leaf_p95_ms=6.93)
    assert rpt["apply_option_ms"] is None
    assert rpt["per_decision_p95_ms_is_lower_bound"] is True
    assert APPLY_SEAM_UNMEASURED in rpt["apply_option_note"]


def test_the_leaf_report_carries_max_beside_the_tail():
    """Issue #291 §3a asks for leaf P50, P95 and max by name, and max is not recoverable from a
    percentile. Driven through a stub scorer — the field under test is the aggregation."""
    class _Pilot:
        def __init__(self, ms): self.ms = ms
        def _leaf_state_model(self, obs, my_index):
            return object()

    def _score(model):
        time.sleep(0.020)
        return 0.0

    breakdown = SimpleNamespace(
        total=0.0, registry_identity="state-value/1:test",
        families=tuple(SimpleNamespace(family=name, value_prizes=0.0,
                                       status=SimpleNamespace(value="known")) for name in FAMILIES),
        as_dict=lambda: {})
    with mock.patch("train.value_lab.state_value", side_effect=_score), \
            mock.patch("train.value_lab.value_breakdown", return_value=breakdown):
        rpt = value_lab_report(lambda agent: _Pilot(20), [_correction([], _frame([60]))])
    assert rpt["max_ms"] is not None
    assert rpt["max_ms"] >= rpt["p95_ms"], "max can never sit below the tail it is reported beside"
    assert rpt["max_ms"] >= 20.0, "the scorer slept 20ms; only scalar evaluation belongs in timing"


def test_an_empty_corpus_reports_max_as_None_not_a_crash():
    """The same fail-shape the other aggregates already have — `max()` on empty raises, and this
    module's whole doctrine is that it REPORTS rather than gates."""
    rpt = value_lab_report(lambda agent: None, [])
    assert (rpt["max_ms"], rpt["p95_ms"], rpt["median_ms"]) == (None, None, None)


def test_the_derived_per_decision_figure_is_the_tail_not_the_mean():
    """P95 menu x P95 leaf. A mean-sized decision is not what overruns a budget, and Issue #263 sizes
    its beam against the tail for the same reason `value_lab` already reports P95 beside median."""
    rows = [{"menu": 2, "post_oec": 2, "terminal": 0, "modelled": 2, "refused": 0, "engine": 0,
             "key": f"f{i}"} for i in range(18)]
    rows += [{"menu": 40, "post_oec": 40, "terminal": 0, "modelled": 40, "refused": 0,
              "engine": 0, "key": f"the-tail-{i}"} for i in range(2)]
    rpt = menu_report(rows, leaf_p95_ms=10.0)
    assert rpt["post_oec_p50"] == 2, "the median must stay unmoved by the tail"
    assert rpt["post_oec_p95"] == 40
    assert rpt["per_decision_p95_ms"] == 400.0        # NOT the mean width (5.8) x the leaf
    assert rpt["widest"][0]["post_oec"] == 40
