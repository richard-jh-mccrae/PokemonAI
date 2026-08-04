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
