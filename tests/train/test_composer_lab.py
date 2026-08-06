"""The **Composer Lab**'s reading of the ruling record (`tools/train/composer_lab.py`, Issue #385).

The lab itself is not a gate and grades nothing on `main` — what IS worth locking is where it gets
each of its three columns from, because one of them was wrong in a way that inverted a conclusion.

**The defect these tests exist for.** A re-ruling never rewrites the `data/corrections/` record —
`gates.ruling_index` says so outright (*"Read-only. No Correction record is rewritten."*) — it lands
in the fixture store as a `claims.decision` block. So a re-ruled frame reads TWO ways, and the
store's way is the stale one. The lab read the store, and the frame it got wrong was **f32**, one of
Issue #263's three named acceptance targets: the store says `correct: [1]` (an `_EVOLVE`), the
fixture re-rules it to `[3]` (the `_RETREAT`, *"Retreat Dreepy → promote Budew"*). Grading the
acceptance criterion against the superseded option made a session conclude that Issue #392's blocking
premise was false when it is true.

No engine, no Pilot, no DLL — these read committed JSON only, so they run on both platforms.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from train.composer_lab import ACCEPTANCE, COLUMN_CAVEAT, fixture_rulings, ideal_index

REPO = Path(__file__).resolve().parents[2]
F32_KEY = "85046350|0|decision|32"
F32_FIXTURE = REPO / "tests" / "fixtures" / "corrections" / "dragapult_hammer_over_develop_f32.json"


@pytest.mark.req("REQ-COMPOSERLAB-0001")
def test_the_ruling_comes_from_the_FIXTURE_where_a_frame_was_re_ruled():
    """f32's authoritative ruling is the fixture's `[3]`, not the store's `[1]`.

    Asserted against the fixture's own bytes rather than against a remembered number, and with the
    superseded value named so a future reader can tell the two apart instead of assuming the lab is
    off by one."""
    fixture = json.loads(F32_FIXTURE.read_text(encoding="utf-8"))
    assert fixture["claims"]["decision"]["correct"] == [3]
    assert fixture["correct_label"].startswith("Retreat Dreepy")
    assert fixture_rulings()[F32_KEY] == [3]


@pytest.mark.req("REQ-COMPOSERLAB-0001")
def test_the_fixture_ruling_actually_DISAGREES_with_the_stored_correction():
    """**The positive control.** If the two stores agreed everywhere, the override would be untested
    machinery and the test above would pass whether or not it worked. This asserts the disagreement
    is real and that f32 is inside it — which is what makes reading the right store load-bearing
    rather than tidy."""
    from train.gates import keyed_corrections

    stored = {key: list(c.correct or []) for key, c in keyed_corrections()}
    ruled = fixture_rulings()
    disagreements = {k: (stored[k], v) for k, v in ruled.items()
                     if k in stored and stored[k] != v}
    assert disagreements, "no frame disagrees — the override cannot be exercised, so it is untested"
    assert disagreements.get(F32_KEY) == ([1], [3])


@pytest.mark.req("REQ-COMPOSERLAB-0001")
def test_every_acceptance_target_has_an_authoritative_ruling():
    """Issue #263's three named targets are what the composer grades itself against, so each must
    resolve to a ruling this lab can read. A target that silently fell back to the store is the
    failure above, one frame over."""
    ruled = fixture_rulings()
    missing = [k for k in ACCEPTANCE if k not in ruled]
    assert missing == [], f"acceptance targets with no fixture ruling: {missing}"


@pytest.mark.req("REQ-COMPOSERLAB-0002")
def test_the_column_caveat_names_all_three_columns_and_the_override():
    """The `family_diag` lesson (Issue #356): the disambiguating sentence has to be in the OUTPUT,
    because the misreading happened to a session that had read the surrounding docs. Asserted on the
    rendered string rather than on a paraphrase of it."""
    for needle in ("composer", "chosen", "ruled", "DARK", "ruled_from"):
        assert needle in COLUMN_CAVEAT


@pytest.mark.req("REQ-COMPOSERLAB-0003")
def test_issue_291s_index_is_CONSUMED_not_re_derived():
    """§3c's classification rule (*"a `sequence` when the developer's line names two or more ordered
    actions"*) is a ruling recorded in `wave3-rulings.md`. This lab parses that table; it must not
    re-implement the rule.

    **41 entries** is Issue #291's own total and the parse must hit it exactly — an unscoped sweep of
    the file returned 48, silently folding in the closeout batch's owner tables, and an instrument
    that over-collects still looks like it works. Three pure pointers, likewise stated and matched."""
    index = ideal_index()
    assert len(index) == 41
    kinds = [row["kind"] for row in index.values()]
    assert sum(1 for k in kinds if k.startswith("pointer")) == 3
    assert all(row["agent"] in ("mega_starmie", "dragapult_ex") for row in index.values())
    # Issue #291's own concentration finding, re-derived from the table it delivered.
    assert sum(1 for r in index.values() if r["agent"] == "mega_starmie") == 38


@pytest.mark.req("REQ-COMPOSERLAB-0003")
def test_the_sequence_vs_verdict_split_DISAGREES_with_the_prose_total_by_one():
    """⚠️ **An open discrepancy, recorded rather than conformed** — the convention
    `wave3-rulings.md` carries in its own words: *"where a developer line and the printed card text
    disagree, record both rather than quietly adopting or quietly correcting."*

    Issue #291's prose states **22 sequences + 3 pointers + 16 verdict-only**. Reading the table it
    delivered, a prefix split gives **23 / 3 / 15**. The single row that moves is
    `82227388|0|decision|50`, labelled ``**sequence** (pointer + its own ordering)`` — it satisfies
    BOTH halves of the stated rule, so the prose total and the table are each internally consistent
    and disagree by exactly that entry.

    Pinned here so the next reader meets it as a known ambiguity instead of assuming the parser is
    broken, and so nobody "fixes" the parser to match a prose total by special-casing one frame. It
    changes nothing this lab does: `kind` is a display column, and the counts are not load-bearing.
    (This file has form for exactly this class of slip — Issue #370's prose said five overlap frames
    where the store held six.)"""
    kinds = [row["kind"] for row in ideal_index().values()]
    assert sum(1 for k in kinds if k.startswith("sequence")) == 23
    assert sum(1 for k in kinds if k.startswith("verdict-only")) == 15
    assert ideal_index()["82227388|0|decision|50"]["kind"] == "sequence (pointer + its own ordering)"


# ── the off-policy exposure (§S10.2, Issue #412) ─────────────────────────────────────────────────


@pytest.mark.req("REQ-COMPOSERLAB-0004")
def test_the_off_policy_detector_is_CONSUMED_not_re_implemented():
    """Issue #412's detector is **context-agnostic** — only `grab_sweep._ctx7` is scoped to
    `_TO_HAND` selects — so pointing it at the MAIN population is a change of POPULATION, not of
    instrument. A second implementation here would be the drift ADR-0087 charges for one store over,
    and it would drift silently: both copies would stay internally consistent while disagreeing.

    The detector MOVED to `train/blunder/off_policy.py` when this lab became its second consumer;
    this lab reaching across to import a sibling *sweep's* private helper was the extract signal.
    Both this lab and `grab_sweep` now delegate, which is the property asserted — not which module
    happens to hold the code today.

    Asserted structurally, because "did you reuse it" is not visible in a count."""
    import inspect

    from train import composer_lab, grab_sweep
    from train.blunder import off_policy

    assert "off_policy" in inspect.getsource(composer_lab.off_policy_reasons)
    # The ORIGINAL home delegates too, so the ctx-7 sweep and this lab cannot answer differently.
    assert "_off_policy_mod.reasons" in inspect.getsource(grab_sweep._off_policy)
    # The detector really is unscoped: its own signature takes no context, and `_ctx7` is where the
    # ctx-7 narrowing lives. If that ever inverts, this lab's MAIN reading is unsound.
    assert list(inspect.signature(grab_sweep._off_policy).parameters) == ["c", "by_ep"]
    assert list(inspect.signature(off_policy.reasons).parameters) == ["correction", "by_ep"]


@pytest.mark.req("REQ-COMPOSERLAB-0004")
def test_the_off_policy_control_fires_on_the_population_it_was_RULED_on():
    """**A negative result needs a positive control.** *"Found nothing"* and *"my instrument is
    broken"* return the same empty output, so a MAIN-context off-policy count is worth nothing on its
    own. Issue #412 measured 15 of 30 ctx-7 frames flagged; this asserts the same detector still
    fires there, which is what licenses reading the MAIN number at all."""
    from train.blunder.store import DEFAULT_ROOT, load_corrections
    from train.composer_lab import off_policy_control

    control = off_policy_control(load_corrections(DEFAULT_ROOT))
    assert control["population"] >= 30, "the ctx-7 base Issue #412 ruled on must still be readable"
    assert control["healthy"], (
        "the off-policy detector fires on NO ctx-7 frame — the instrument is broken, so any MAIN "
        "count it reports is an artifact rather than a finding")
    assert control["flagged"] >= 14


@pytest.mark.req("REQ-COMPOSERLAB-0004")
def test_the_lab_REPORTS_off_policy_frames_and_never_FILTERS_them():
    """§S10.2's actual requirement, and the one a reader is most likely to get backwards.

    Extending Issue #412's doctrine from *follow-up select* to *MAIN → MAIN within a turn* is a
    **generalisation the developer has not ruled on**. Silently excluding those frames would be
    conforming to an unruled premise — the thing this track exists to forbid — and it would do it
    invisibly, by making the denominator smaller.

    So the column must be present AND the population must be untouched: every row keeps its
    `off_policy` list, and the frame count is the whole store."""
    import ast
    import inspect
    import textwrap

    from train import composer_lab

    source = inspect.getsource(composer_lab.composer_lab_report)
    assert "off_policy" in source, "the column must be reported at all"
    assert "REPORTED, NOT filtered" in inspect.getsource(composer_lab._print_report)

    # Parsed, not grepped. The AGGREGATION lines legitimately read `if r["off_policy"]` inside a
    # generator that COUNTS — that is the column doing its job. What must not exist is an
    # off-policy test on the ROW-BUILDING loop, which is the one that decides the denominator.
    fn = ast.parse(textwrap.dedent(source)).body[0]
    loops = [n for n in ast.walk(fn)
             if isinstance(n, ast.For) and getattr(n.iter, "id", None) == "corrections"]
    assert loops, "positive control: the row-building loop over `corrections` must be findable"
    for loop in loops:
        names = {n.value for n in ast.walk(loop) if isinstance(n, ast.Constant)
                 and isinstance(n.value, str)}
        assert "off_policy" not in names, (
            "the row-building loop reads the off-policy column — §S10.2 forbids filtering on an "
            "unruled generalisation; report it as a column and leave the population whole")
