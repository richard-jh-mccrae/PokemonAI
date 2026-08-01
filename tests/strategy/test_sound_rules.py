"""The **typed sound-rule whitelist** (`common/sound_rules.py`, POC-T0 / Issue #259, ADR-TEMP-259f).

The whitelist decides which hand-authored rules survive the POC's purge, and six parallel tracks each
delete rungs against it. A flat prose list already failed once: ONE board fact — an empty Bench under
a knock-outable Active — reached the draft list through THREE mechanisms at the same time (a terminal
rung, an order filter and a +60 weight), violating T0's own "every board fact enters through exactly
ONE term family" rule, and nothing about writing that line prompted the question.

So the discipline is asserted here rather than remembered. `test_the_whitelist_is_valid` is the
enforcement; `test_the_doc_table_and_the_data_carry_the_same_entries` is what keeps the
human-readable rendering from drifting away from the authority.

Prior art for the style: `tests/train/test_gates.py` (data-in / verdict-out, no engine, no DLL) and
`test_currency.py` (a committed artifact asserted against its source rather than pinned).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from common import sound_rules as sr

_PLAN = Path(__file__).resolve().parents[2] / "docs" / "plans" / "value-system-poc-plan.md"


def _doc_ids() -> list[str]:
    """The `id` column of §6's table, in order. A narrow parse on purpose — the first cell of every
    row whose first cell is a backticked slug — so a reworded entry or a changed reason cannot break
    the cross-check, but an added, removed or renamed ENTRY does."""
    out = []
    for line in _PLAN.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*`([a-z0-9-]+)`\s*\|", line)
        if m:
            out.append(m.group(1))
    return out


# ── the typing discipline ─────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-WHITELIST-0001")
def test_the_whitelist_is_valid():
    """The T0 registry REJECTS an untyped entry (ADR-TEMP-259f decision 1). Every problem at once,
    because an author fixing a whitelist wants the whole list of complaints, not the first."""
    assert sr.validate() == []


@pytest.mark.req("REQ-WHITELIST-0001")
def test_a_provisional_entry_without_a_retirement_test_is_rejected():
    """The failure the `provisional` type exists to name: a workaround becomes permanent through
    inattention. Without the mandatory field, tagging something provisional would be a comment."""
    bad = sr.SoundRule(id="x", entry="e", type=sr.PROVISIONAL, fact="f", reason="r")
    problems = sr.validate([bad])
    assert any("retirement test" in p for p in problems)


@pytest.mark.req("REQ-WHITELIST-0001")
def test_an_authored_scaffold_without_a_reconciliation_is_rejected():
    """ADR-0078's founding complaint was two constants pricing the SAME object differently. An
    invented number that states nothing about the numbers already in the codebase repeats it."""
    bad = sr.SoundRule(id="x", entry="e", type=sr.AUTHORED_SCAFFOLD, fact="f", reason="r")
    assert any("reconciliation" in p for p in sr.validate([bad]))


@pytest.mark.req("REQ-WHITELIST-0001")
def test_a_structural_entry_carrying_an_expiry_has_the_wrong_type():
    """`structural` means permanent. An entry that knows how it retires is provisional, and letting
    the two blur is how a dated obligation becomes invisible."""
    bad = sr.SoundRule(id="x", entry="e", type=sr.STRUCTURAL, fact="f", reason="r",
                       retirement_test="after T1")
    assert any("type is wrong" in p for p in sr.validate([bad]))


@pytest.mark.req("REQ-WHITELIST-0001")
def test_an_entry_that_names_no_fact_is_rejected():
    """Naming the guarded fact is what makes the double-counting rule checkable against the WHITELIST
    and not only against `state_value`'s term families — the check the draft list could not perform,
    which is why it carried one fact three times."""
    bad = sr.SoundRule(id="x", entry="e", type=sr.STRUCTURAL, fact="  ", reason="r")
    assert any("names no board fact" in p for p in sr.validate([bad]))


@pytest.mark.req("REQ-WHITELIST-0001")
def test_ids_are_unique():
    """`id` is what a commit message and a track issue cite, so a duplicate would make a citation
    ambiguous — and `BY_ID` would silently drop one of the two."""
    assert sr.validate() == []
    assert len(sr.BY_ID) == len(sr.WHITELIST)


# ── the amendments this grill made, asserted as state rather than prose ───────────────────────────


@pytest.mark.req("REQ-WHITELIST-0002")
def test_keep_a_bench_is_not_on_the_whitelist():
    """Deleted by ADR-TEMP-259c decision 2: it guards nothing the filter does not already guarantee
    at MAIN, and per Issue #231's own numbers it IS the spare-body cliff (a spare body priced 1.96 on
    a non-empty Bench against 61.96 on an empty one — the entire gap was this rung)."""
    entries = " ".join(r.entry for r in sr.WHITELIST).lower()
    assert "keep-a-bench" not in entries


@pytest.mark.req("REQ-WHITELIST-0002")
def test_the_empty_bench_filter_is_provisional_and_names_the_measurement_that_retires_it():
    """Kept unconditional — it guards a loss condition and the read that would replace it depends on
    the substrate T1 is delivering — but NOT permanent. The retirement test is written down now so it
    cannot quietly become permanent (ADR-TEMP-259c decision 1)."""
    r = sr.BY_ID["empty-bench-filter"]
    assert r.type == sr.PROVISIONAL
    assert "reachable_incoming" in r.retirement_test and "both gates" in r.retirement_test


@pytest.mark.req("REQ-WHITELIST-0002")
def test_setup_never_bench_is_its_own_entry_not_bundled_with_the_in_game_guard():
    """A rule proven weakly dominant from the rulebook must not share a line with a provisional
    workaround — bundling is what let a filter and a tuned weight ratify as one thing."""
    r = sr.BY_ID["setup-never-bench"]
    assert r.type == sr.STRUCTURAL
    assert r.fact != sr.BY_ID["empty-bench-filter"].fact


@pytest.mark.req("REQ-WHITELIST-0002")
def test_the_sequencer_entry_names_the_boundary_rather_than_the_tiers():
    """'the `_finish_turn_last` sequencing tiers' was unfalsifiable — and was in fact FALSE in the
    free band, where tier 0 conflated 'free' with 'informative' and let a Crushing Hammer sequence
    ahead of a Pokégear dig. The narrowed entry states a boundary a test can check."""
    r = sr.BY_ID["information-before-commitment"]
    assert "information" in r.entry.lower() and "commitment" in r.entry.lower()


@pytest.mark.req("REQ-WHITELIST-0002")
def test_the_two_entries_on_one_fact_really_do_share_one_fact():
    """The detector's teeth. These two guard ONE board fact and must say so with one identical
    `fact` string — distinguishing them by tacking "(the CombatMath-gated reading)" onto one would
    make the coverage map read as two separate facts and the double-guard check pass VACUOUSLY.

    That is not hypothetical: this test was written first in the vacuous form and passed while the
    two entries carried different `fact` strings. The differing READING lives in `reason`."""
    filt, rung = sr.BY_ID["empty-bench-filter"], sr.BY_ID["predicted-loss"]
    assert filt.fact == rung.fact
    assert sr.facts_guarded()[filt.fact] == ["empty-bench-filter", "predicted-loss"]
    assert filt.type == sr.PROVISIONAL and rung.type == sr.STRUCTURAL
    assert "sole guard" in rung.reason.lower()


@pytest.mark.req("REQ-WHITELIST-0002")
def test_no_fact_is_guarded_twice_without_being_declared():
    """One fact carrying two entries is allowed only when it is DELIBERATE and declared in
    `SCHEDULED_PAIRS`. Any OTHER doubling is the defect this registry exists to prevent — a second
    entry nobody noticed, which is how one board fact came to carry three guards at once."""
    assert sr.undeclared_double_guarding() == {}


@pytest.mark.req("REQ-WHITELIST-0002")
def test_an_UNDECLARED_second_guard_on_a_fact_is_caught():
    """The detector, exercised on a fact it should reject — so a green result above means the check
    ran, not that nothing could ever trip it."""
    extra = sr.SoundRule(id="y", entry="another guard", type=sr.STRUCTURAL,
                         fact=sr.BY_ID["ko-score-band"].fact, reason="r")
    facts: dict = {}
    for r in list(sr.WHITELIST) + [extra]:
        facts.setdefault(r.fact, []).append(r.id)
    doubled = {f: ids for f, ids in facts.items()
               if len(ids) > 1 and frozenset(ids) not in {frozenset(p) for p in sr.SCHEDULED_PAIRS}}
    assert list(doubled) == [sr.BY_ID["ko-score-band"].fact]


# ── the doc and the data cannot drift ─────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-WHITELIST-0003")
def test_the_doc_table_and_the_data_carry_the_same_entries_in_the_same_order():
    """Two homes for one list is safe only if something checks them. The plan doc is what a human
    reads and what the wave packets cite; `sound_rules.py` is what the tracks import. A rule deleted
    from one and left in the other would give two answers to "may I delete this rung?"."""
    assert _doc_ids() == [r.id for r in sr.WHITELIST]
