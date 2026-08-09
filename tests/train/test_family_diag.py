"""`train.family_diag` — the columns that say WHOSE decision each one is (Issue #356).

This instrument renders the **leaf's argmax**. Issues #330/#331/#332 read that column as *what the
agent played*; on the twelve frames Issue #330 quotes the committed pick differs on 12 of 12.

So the output must STATE the distinction rather than imply it: the AGENT's committed pick is
rendered beside the leaf's and the two are explicitly compared; agreement is `gates.satisfies_human`
(ADR-0085 Amendment J's `correct ⊆ chosen`), never argmax equality; and a `--keys` list with no
declared source is REFUSED, because an unlabelled key list is the input that produced the claim.

Those columns are pure functions and were tested as such. The `_working` leg they render — the
`_simulate_line` → `state_value` round-trip — was not, and unpacked a stale 7-tuple from a 6-tuple
producer, so every invocation of the instrument died and its silence read as "no findings".
"""
from __future__ import annotations

import ast
import inspect
import sys
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]
for sub in ("tools", "src"):
    path = str(REPO / sub)
    if path not in sys.path:
        sys.path.insert(0, path)

from common.strategy.planning.leaf import LeafValueMixin  # noqa: E402
from train.family_diag import (  # noqa: E402
    LEAF_CAVEAT, SOURCE_CAVEAT, _working, agent_columns, diagnose, render,
)
from train.gates import keyed_corrections  # noqa: E402


def _correction(chosen, correct):
    return SimpleNamespace(chosen=chosen, correct=correct)


def _row(**over):
    row = {"key": "82225643|1|decision|57", "agent": "mega_starmie", "category": "sequencing_error",
           "ruled": "Play Ultra Ball", "leaf": "Retreat", "chosen": "Attack",
           "leaf_is_chosen": False, "agent_satisfies_ruled": False,
           "deltas": {"survival": -1.25, "threat": 0.10}, "line_delta": 0.0,
           "total_delta": -1.15, "decider": "survival"}
    row.update(over)
    return row


# ── the agent's pick is a column, not an inference ────────────────────────────────────────────────

def test_agent_columns_render_the_committed_pick():
    cols = agent_columns(_correction([12], [11]), 9, lambda i: f"opt{i}")
    assert cols["chosen"] == "opt12"
    assert cols["leaf_is_chosen"] is False
    assert cols["agent_satisfies_ruled"] is False


def test_a_multi_index_pick_renders_every_index():
    """A multi-pick select is one decision with several slots — dropping all but the first would
    reproduce this issue's defect in the new column."""
    cols = agent_columns(_correction([2, 3], [2]), 2, lambda i: f"opt{i}")
    assert cols["chosen"] == "opt2 + opt3"


def test_a_recorded_decline_is_named_not_blank():
    cols = agent_columns(_correction([], []), None, lambda i: f"opt{i}")
    assert cols["chosen"] == "(declined)"
    assert cols["agent_satisfies_ruled"] is True, "declining satisfies a DECLINE ruling"


def test_an_unreplayable_pick_is_a_question_mark_never_an_agreement():
    cols = agent_columns(_correction(None, [1]), 1, lambda i: f"opt{i}")
    assert cols["chosen"] == "?"
    assert cols["agent_satisfies_ruled"] is False


def test_leaf_is_chosen_is_reported_when_they_do_coincide():
    cols = agent_columns(_correction([4], [4]), 4, lambda i: f"opt{i}")
    assert cols["leaf_is_chosen"] is True
    assert cols["agent_satisfies_ruled"] is True


# ── agreement is `satisfies_human`, not equality (scope item 4) ────────────────────────────────────

def test_agreement_uses_satisfies_human_not_argmax_equality():
    """ADR-0085 Amendment J: `correct` is a CONSTRAINT, not the whole answer. A DISCARD ruled `[2]` is
    satisfied by the engine-required `[2, 3]`; equality scored that 1/12 where the honest number was 10/12."""
    cols = agent_columns(_correction([2, 3], [2]), 2, lambda i: f"opt{i}")
    assert cols["agent_satisfies_ruled"] is True

    partial = agent_columns(_correction([2], [2, 3]), 2, lambda i: f"opt{i}")
    assert partial["agent_satisfies_ruled"] is False, "a partial answer does not satisfy the ruling"


def test_equivalence_classes_widen_the_ruling_when_supplied():
    """Two indistinguishable options are one decision (ADR-0091); a ruling naming one is satisfied
    by the other. Threaded rather than recomputed, exactly as both gates thread it."""
    equiv = {1: frozenset({1, 2}), 2: frozenset({1, 2})}
    cols = agent_columns(_correction([2], [1]), 2, lambda i: f"opt{i}", equiv=equiv)
    assert cols["agent_satisfies_ruled"] is True
    assert agent_columns(_correction([2], [1]), 2, lambda i: f"opt{i}")["agent_satisfies_ruled"] is False


# ── the rendered table states the distinction ─────────────────────────────────────────────────────

def test_render_puts_chosen_beside_leaf_in_the_header_row():
    out = render([_row()], issue="#330", source="leaf")
    header = next(ln for ln in out.splitlines() if ln.startswith("| frame |"))
    assert "leaf" in header and "chosen" in header
    assert header.index("leaf") < header.index("chosen"), "chosen sits beside leaf, not at the end"


def test_render_says_which_object_each_column_is():
    out = render([_row()], issue="#330", source="leaf")
    assert LEAF_CAVEAT in out
    assert "_commit_best" in out, "the leaf is named as ONE rung feeding the committed decision"


def test_render_states_the_comparison_rather_than_leaving_it_to_the_reader():
    def data_row(text):
        return next(ln for ln in text.splitlines() if ln.startswith("| `82225643"))

    assert "DIFFERS" in data_row(render([_row(leaf_is_chosen=False)], issue="#330", source="leaf"))
    same = data_row(render([_row(leaf_is_chosen=True)], issue="#330", source="leaf"))
    assert "DIFFERS" not in same and "same" in same


def test_render_counts_how_many_frames_the_leaf_and_the_agent_disagree_on():
    """The headline number Issues #330/#331/#332 needed and did not have."""
    out = render([_row(), _row(key="k2", leaf_is_chosen=True)], issue="#330", source="leaf")
    assert "1 of 2" in out


def test_an_errored_row_still_reports_the_agent_pick():
    """`_working` failing is a LEAF failure; what the agent played is read off the corpus and is
    still known. Blanking it would hide the one column this issue exists to add."""
    out = render([{"key": "k", "agent": "a", "category": "c", "error": "sim unavailable",
                   "ruled": "Play Ultra Ball", "leaf": "?", "chosen": "Attack",
                   "leaf_is_chosen": False, "agent_satisfies_ruled": False}],
                 issue="#330", source="leaf")
    assert "Attack" in out


def test_a_frame_missing_from_the_corpus_asserts_no_comparison():
    """`not in corpus` knows neither pick. Falling through to `DIFFERS`/`disagrees` would assert a
    comparison nothing performed — this issue's own defect, one column over."""
    out = render([{"key": "k", "error": "not in corpus"}], issue="#330", source="leaf")
    row = next(ln for ln in out.splitlines() if ln.startswith("| `k`"))
    assert "DIFFERS" not in row and "disagrees" not in row
    assert row.count("—") >= 3
    assert "0 of 0 frames" in out, "an uncomparable row is out of the divergence denominator"


# ── `--keys` fails closed on an undeclared source ─────────────────────────────────────────────────

def test_keys_without_a_source_is_refused(tmp_path):
    from train.family_diag import main

    keys = tmp_path / "keys.txt"
    keys.write_text("82225643|1|decision|57\n", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["--keys", str(keys), "--out", str(tmp_path / "out.md")])
    assert exc.value.code == 2, "argparse usage error — refused, not diagnosed"


def test_a_decider_sourced_run_carries_the_matching_caveat():
    out = render([_row()], issue="#330", source="decider")
    assert SOURCE_CAVEAT["decider"] in out
    assert SOURCE_CAVEAT["leaf"] not in out


def test_a_leaf_sourced_run_carries_the_leaf_caveat():
    out = render([_row()], issue="#330", source="leaf")
    assert SOURCE_CAVEAT["leaf"] in out
    assert SOURCE_CAVEAT["decider"] not in out


def test_an_unknown_source_is_rejected_rather_than_rendered_unlabelled():
    with pytest.raises(ValueError):
        render([_row()], issue="#330", source="somewhere")


# ── the `_simulate_line` leg runs at all ──────────────────────────────────────────────────────────

def _tuple_return_widths(func) -> set:
    return {len(n.value.elts) for n in ast.walk(ast.parse(textwrap.dedent(inspect.getsource(func))))
            if isinstance(n, ast.Return) and isinstance(n.value, ast.Tuple)}


def _unpack_widths(func, name) -> set:
    return {len(t.elts) for n in ast.walk(ast.parse(textwrap.dedent(inspect.getsource(func))))
            if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Tuple)
            and isinstance(n.value, ast.Name) and n.value.id == name}


def test_working_unpacks_exactly_what_simulate_line_returns():
    """The producer's width is READ off its own `return`, never re-spelled here — a literal 6 would be
    a second copy of the contract and would drift the same way the caller's 7 did."""
    produced = _tuple_return_widths(LeafValueMixin._simulate_line)
    consumed = _unpack_widths(_working, "sim")
    # Positive control: the probe is AST-shaped, so a renamed local or a refactored `return` would
    # leave it matching nothing and reporting agreement between two empty sets.
    assert produced and consumed, "the AST probe matched nothing — the probe is broken, not the code"
    assert produced == consumed, f"_simulate_line returns {produced}, _working unpacks {consumed}"


def test_the_instrument_diagnoses_real_corpus_frames_end_to_end():
    """The smoke the arity bug walked past: every other test here feeds `render` a hand-built row, so
    nothing exercised a pilot, and the tool crashed on its first line of real work."""
    keyed = dict(keyed_corrections(None))
    assert keyed, "the committed corrections store is empty — this test has nothing to run on"
    # A WINDOW, not a key: most corpus frames reseed offline but some cannot, and any single key can
    # be voided out of the store, so the claim is that the leg works — not that a given frame scores.
    window = list(keyed)[:12]
    rows = diagnose(window, corrections=keyed)
    scored = [r for r in rows if "deltas" in r]
    assert scored, f"no frame of {len(window)} scored: {sorted({r.get('error') for r in rows})}"
    assert any(abs(v) > 0.0 for r in scored for v in r["deltas"].values()), (
        "every family flat on every frame — `state_value`'s `working` dict never populated")
    report = render(rows, issue="#330", source="decider")
    keyed_cell = window[0].replace("|", "\\|")     # a frame key is pipe-separated; `render` escapes it
    assert f"`{keyed_cell}`" in report, "the scored rows reach the Markdown"
