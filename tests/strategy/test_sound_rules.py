"""The typed sound-rule whitelist (`common/sound_rules.py`, POC-T0 / Issue #259, ADR-0099).

The whitelist decides which hand-authored rules survive the POC's purge. Its founding defect: ONE
board fact reached the draft list through THREE mechanisms at once, against T0's own "every board
fact enters through exactly ONE term family" rule, and nothing about writing prose prompted the check.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from common import sound_rules as sr

_PLAN = Path(__file__).resolve().parents[2] / "docs" / "plans" / "value-system-poc-plan.md"


def _doc_ids() -> list[str]:
    """The `id` column of §6's table, in order. Narrow on purpose: a reworded entry or changed reason
    cannot break the cross-check, but an added, removed or renamed ENTRY does."""
    out = []
    for line in _PLAN.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*`([a-z0-9-]+)`\s*\|", line)
        if m:
            out.append(m.group(1))
    return out


# ── the typing discipline ─────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-WHITELIST-0001")
def test_the_whitelist_is_valid():
    """ADR-0099 decision 1."""
    assert sr.validate() == []


@pytest.mark.req("REQ-WHITELIST-0001")
def test_a_provisional_entry_without_a_retirement_test_is_rejected():
    """Without the mandatory field, tagging something provisional would be a comment."""
    bad = sr.SoundRule(id="x", entry="e", type=sr.PROVISIONAL, fact="f", reason="r")
    problems = sr.validate([bad])
    assert any("retirement test" in p for p in problems)


@pytest.mark.req("REQ-WHITELIST-0001")
def test_an_authored_scaffold_without_a_reconciliation_is_rejected():
    """ADR-0078: two constants pricing the SAME object differently."""
    bad = sr.SoundRule(id="x", entry="e", type=sr.AUTHORED_SCAFFOLD, fact="f", reason="r")
    assert any("reconciliation" in p for p in sr.validate([bad]))


@pytest.mark.req("REQ-WHITELIST-0001")
def test_a_structural_entry_carrying_an_expiry_has_the_wrong_type():
    """`structural` means PERMANENT; an entry that knows how it retires is provisional."""
    bad = sr.SoundRule(id="x", entry="e", type=sr.STRUCTURAL, fact="f", reason="r",
                       retirement_test="after T1")
    assert any("type is wrong" in p for p in sr.validate([bad]))


@pytest.mark.req("REQ-WHITELIST-0001")
def test_an_entry_that_names_no_fact_is_rejected():
    """`fact` is what makes double-counting checkable against the WHITELIST, not only against
    `state_value`'s term families."""
    bad = sr.SoundRule(id="x", entry="e", type=sr.STRUCTURAL, fact="  ", reason="r")
    assert any("names no board fact" in p for p in sr.validate([bad]))


@pytest.mark.req("REQ-WHITELIST-0001")
def test_ids_are_unique():
    """`BY_ID` silently drops one of a duplicate pair."""
    assert sr.validate() == []
    assert len(sr.BY_ID) == len(sr.WHITELIST)


# ── the amendments this grill made, asserted as state rather than prose ───────────────────────────


@pytest.mark.req("REQ-WHITELIST-0002")
def test_keep_a_bench_is_not_on_the_whitelist():
    """Deleted by ADR-0096 decision 2 — it guarded nothing the filter did not already guarantee at
    MAIN, and it WAS the spare-body cliff."""
    entries = " ".join(r.entry for r in sr.WHITELIST).lower()
    assert "keep-a-bench" not in entries


@pytest.mark.req("REQ-WHITELIST-0002")
def test_the_empty_bench_filter_is_provisional_and_names_the_measurement_that_retires_it():
    """Unconditional (it guards a loss condition) but NOT permanent — ADR-0096 decision 1."""
    r = sr.BY_ID["empty-bench-filter"]
    assert r.type == sr.PROVISIONAL
    assert "reachable_incoming" in r.retirement_test and "both gates" in r.retirement_test


@pytest.mark.req("REQ-WHITELIST-0002")
def test_setup_never_bench_is_its_own_entry_not_bundled_with_the_in_game_guard():
    """Bundling a rulebook-dominant rule with a provisional workaround ratifies both as one thing."""
    r = sr.BY_ID["setup-never-bench"]
    assert r.type == sr.STRUCTURAL
    assert r.fact != sr.BY_ID["empty-bench-filter"].fact


@pytest.mark.req("REQ-WHITELIST-0002")
def test_the_sequencer_entry_names_the_boundary_rather_than_the_tiers():
    """Naming the tiers was unfalsifiable, and false in the free band where tier 0 conflated 'free'
    with 'informative'. A boundary is checkable."""
    r = sr.BY_ID["information-before-commitment"]
    assert "information" in r.entry.lower() and "commitment" in r.entry.lower()


@pytest.mark.req("REQ-WHITELIST-0002")
def test_the_two_entries_on_one_fact_really_do_share_one_fact():
    """One IDENTICAL `fact` string, or the coverage map reads two facts and the double-guard check
    passes vacuously. A differing READING belongs in `reason`."""
    filt, rung = sr.BY_ID["empty-bench-filter"], sr.BY_ID["predicted-loss"]
    assert filt.fact == rung.fact
    assert sr.facts_guarded()[filt.fact] == ["empty-bench-filter", "predicted-loss"]
    assert filt.type == sr.PROVISIONAL and rung.type == sr.STRUCTURAL
    assert "sole guard" in rung.reason.lower()


@pytest.mark.req("REQ-WHITELIST-0002")
def test_no_fact_is_guarded_twice_without_being_declared():
    """Two entries on one fact are allowed only when declared in `SCHEDULED_PAIRS`."""
    assert sr.undeclared_double_guarding() == {}


@pytest.mark.req("REQ-WHITELIST-0002")
def test_an_UNDECLARED_second_guard_on_a_fact_is_caught():
    """The positive control for the test above."""
    extra = sr.SoundRule(id="y", entry="another guard", type=sr.STRUCTURAL,
                         fact=sr.BY_ID["ko-score-band"].fact, reason="r")
    facts: dict = {}
    for r in list(sr.WHITELIST) + [extra]:
        facts.setdefault(r.fact, []).append(r.id)
    doubled = {f: ids for f, ids in facts.items()
               if len(ids) > 1 and frozenset(ids) not in {frozenset(p) for p in sr.SCHEDULED_PAIRS}}
    assert list(doubled) == [sr.BY_ID["ko-score-band"].fact]


# ── composed-into-the-leaf (Issue #263 ordering ruling, 2026-08-01) ───────────────────────────────


@pytest.mark.req("REQ-WHITELIST-0004")
def test_the_four_per_seam_equations_are_listed_as_composed_into_the_leaf():
    """They stop DECIDING but are neither deleted nor whitelisted, so a later track cannot read "no
    longer a decider" as licence to delete the math Issue #262 composes the leaf out of."""
    assert sr.COMPOSED_INTO_THE_LEAF == "composed-into-the-leaf"
    assert {r.id for r in sr.composed()} == {
        "attach-value-composed", "evolve-value-composed",
        "promote-retreat-value-composed", "deploy-value-composed"}


@pytest.mark.req("REQ-WHITELIST-0004")
def test_a_composed_entry_must_name_the_term_family_that_absorbs_it():
    """"Survives as an internal" with no named destination is indistinguishable from "kept out of
    sentiment", and the next track deletes it."""
    from common.state_value import REGISTRY
    families = {f.name for f in REGISTRY}
    for r in sr.composed():
        assert r.composed_into in families, (r.id, r.composed_into)

    bad = sr.SoundRule(id="x", entry="e", type=sr.COMPOSED_INTO_THE_LEAF, fact="f", reason="r")
    assert any("term" in p and "family" in p for p in sr.validate([bad]))


@pytest.mark.req("REQ-WHITELIST-0004")
def test_a_still_deciding_entry_may_not_claim_a_destination_family():
    """A `structural` rule naming a term family would be exempt from the one-guard-per-fact rule —
    the escape hatch the typing discipline exists to close."""
    bad = sr.SoundRule(id="x", entry="e", type=sr.STRUCTURAL, fact="f", reason="r",
                       composed_into="readiness")
    assert any("still decides" in p for p in sr.validate([bad]))


@pytest.mark.req("REQ-WHITELIST-0004")
def test_the_double_guard_detector_runs_over_the_deciders_only():
    """A decider GUARDS a fact; a composed equation PRICES one. One map would report the pair as a
    double guard."""
    assert len(sr.deciders()) + len(sr.composed()) == len(sr.WHITELIST)
    composed_ids = {r.id for r in sr.composed()}
    assert not (composed_ids & {i for ids in sr.facts_guarded().values() for i in ids})
    assert sr.undeclared_double_guarding() == {}


# ── the doc and the data cannot drift ─────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-WHITELIST-0003")
def test_the_doc_table_and_the_data_carry_the_same_entries_in_the_same_order():
    """Humans read the plan doc; tracks import `sound_rules.py`. Drift gives two answers to "may I
    delete this rung?"."""
    assert _doc_ids() == [r.id for r in sr.WHITELIST]


# ── an entry must name a symbol that still EXISTS ─────────────────────────────────────────────────


_ENTRY_SYMBOL = re.compile(r"`([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+)`")


def _entry_symbols():
    return [(r.id, s) for r in sr.WHITELIST for s in _ENTRY_SYMBOL.findall(r.entry)]


def _resolves(dotted: str) -> bool:
    """Walks attributes from the deepest importable `common.` prefix, so the caller need not know
    which parts of the dotted path are modules."""
    import importlib
    parts = dotted.split(".")
    for split in range(len(parts) - 1, 0, -1):
        try:
            obj = importlib.import_module("common." + ".".join(parts[:split]))
        except ImportError:
            continue
        for attr in parts[split:]:
            obj = getattr(obj, attr, None)
            if obj is None:
                return False
        return True
    return False


@pytest.mark.req("REQ-WHITELIST-0002")
def test_every_symbol_an_entry_names_still_resolves():
    """Deliberately narrow — only DOTTED paths. A bare `` `KO_SCORE` `` is prose about a band, not an
    address, and demanding it resolve would push entries toward jargon nobody can read."""
    unresolved = [(rid, s) for rid, s in _entry_symbols() if not _resolves(s)]
    assert unresolved == [], f"whitelist entries name symbols that no longer exist: {unresolved}"


@pytest.mark.req("REQ-WHITELIST-0002")
def test_the_symbol_check_actually_looks_at_something():
    """The positive control: the test above passes just as happily when the regex matches nothing."""
    assert len(_entry_symbols()) >= 5                       # the sweep is not looking at an empty set
    assert _resolves("state_value._predicted_loss") is True  # a live symbol resolves
    assert _resolves("strategy.planner._predicted_loss") is False   # the one POC-T4/5 deleted
    assert _resolves("state_value._no_such_symbol") is False
