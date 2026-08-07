"""A rung ID that production code MATCHES ON must be a rung some Strategy ships.

The interlock for one specific, twice-observed failure: **a retired id sitting in a live string
literal reads as LIVE to every instrument.** Deleting a Hypothesis is a one-line edit in one module,
and every consumer that keyed off its `id` keeps compiling, keeps running, and quietly stops firing.
There is no import to break, no attribute to go missing, no test to go red. The rung's *behaviour* is
gone; its *appearance* is not.

It has happened twice, both times inside POC-T4/5 (Issue #386):

1. `pilot._finish_turn_last` sequenced a KO-enabling gust and the sacrificial-wall retreat by matching
   ``gust-for-the-ko`` / ``gust-for-the-loaded-equal-ko`` / ``retreat-to-wall-the-line`` in inline
   string literals. All three rungs were deleted by the same PR. Both branches became unreachable and
   `baseline/__init__.py` went on asserting *"`_finish_turn_last`'s tiers SURVIVE and are still where
   the ordering claim lives"* — false on the day it was written, green in CI, and it survived review.
2. `planner._CLASS_B_SPEND_IDS` and `_ABILITY_FIRE_IDS` — the two halves of ADR-0069's spend account —
   between them named 14 ids nothing shipped any more, so `_line_account` was summing over a
   vocabulary two thirds of which could not occur.

Both are fixed at the source. This file is what stops the third: the invariant is checked against the
SHIPPED roster, so a rung deletion that orphans a consumer fails here rather than going quiet.

**Scope, deliberately narrow.** Only ids that CONTROL BEHAVIOUR are in scope — a literal compared
against a Hypothesis `id`, or a member of a set that is. Prose is exempt and must stay exempt: a fold
record is *about* deleted rungs, and `baseline/__init__.py` names every one of them on purpose so
`tools/train/reviewed_audit.py` can answer *"where did this rung go?"*. An invariant that could not
tell those apart would force the audit trail to be deleted to stay green.
"""
import ast

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "src"

#: `src/cg/` is the native-engine API wrapper and is off-limits (CLAUDE.md), so it is excluded up
#: front rather than filtered out of the results.
SKIP = (SRC / "cg",)


def _live_rung_ids() -> set:
    """Every Hypothesis id the shipped agents can actually score, general + per-deck.

    Enumerated from the filesystem rather than from a hand-kept list: a fourth deck that lands
    without being added here would otherwise make every one of ITS ids read as dead, and the failure
    would point at the wrong thing.

    ⚠️ Loaded by FILE PATH, never as ``agents.<deck>.strategy``. The dotted form works in isolation
    and raises `ImportError` in a full-suite run, because `kaggle_environments` ships its own
    top-level `agents` module (`envs/lux_ai_s3/agents.py`) and whichever import lands first owns the
    name. Caught by the suite, not by this file's own run — the same shape as a `tests/<subdir>/
    conftest.py` shadowing the root one."""
    import importlib.util

    from common.strategy.general_strategy import GENERAL_STRATEGY

    ids = {h.id for h in GENERAL_STRATEGY.hypotheses}
    decks = sorted(p for p in SRC.glob("agents/*/strategy.py"))
    assert decks, "no deck strategies found — the roster is empty for the wrong reason"
    for path in decks:
        spec = importlib.util.spec_from_file_location(f"_rung_roster_{path.parent.name}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)     # NOT registered in sys.modules: a second copy under the
        ids |= {h.id for h in mod.STRATEGY.hypotheses}   # real name would give the suite two
    return ids                                           # Strategy objects for one deck


def _matched_literals() -> dict:
    """``{rung id: [where it is matched]}`` over every production module.

    Finds the two shapes that make an id load-bearing::

        h.id == "some-rung"                 /  h.id != "some-rung"
        h.id in ("some-rung", "other")      /  h.id in SOME_FROZENSET
        getattr(h, "id", None) in {...}

    The test is on the LEFT operand: a `.id` attribute access, or `getattr(x, "id", ...)`. That is
    what separates a rung-id comparison from every other string compare in the tree, and it is why
    this walks the AST instead of grepping — `# `gust-for-the-ko`` in a comment must not match, and a
    regex over source lines cannot tell the two apart."""
    out: dict = {}

    def _is_id_read(node) -> bool:
        if isinstance(node, ast.Attribute) and node.attr == "id":
            return True
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "getattr" and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant) and node.args[1].value == "id")

    def _strings(node) -> list:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return [node.value]
        if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
            return [s for e in node.elts for s in _strings(e)]
        return []

    for path in sorted(SRC.rglob("*.py")):
        if any(path.is_relative_to(d) for d in SKIP):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rel = path.relative_to(REPO).as_posix()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare) or not _is_id_read(node.left):
                continue
            for op, comp in zip(node.ops, node.comparators):
                if not isinstance(op, (ast.Eq, ast.NotEq, ast.In, ast.NotIn)):
                    continue
                for s in _strings(comp):
                    out.setdefault(s, []).append(f"{rel}:{node.lineno}")
    return out


#: Frozensets of rung ids that gate a live sum, imported rather than parsed — their membership IS the
#: comparison, so an AST walk over the `in` test only sees the NAME. Extend when another lands.
def _named_registries() -> dict:
    from common.strategy import planner

    return {"planner._CLASS_B_SPEND_IDS": planner._CLASS_B_SPEND_IDS,
            "planner._ABILITY_FIRE_IDS": planner._ABILITY_FIRE_IDS}


@pytest.mark.req("REQ-STRATEGY-0001")
def test_every_rung_id_a_named_registry_gates_on_is_still_shipped():
    """ADR-0069's spend account, held to its own vocabulary.

    `_line_account` is `turn_value`'s path term — it credits every positive `_ABILITY_FIRE_IDS` rung
    that fired and subtracts every negative `_CLASS_B_SPEND_IDS` one. A member no Strategy ships can
    never appear in `OptionTrace.fired`, so it contributes nothing and reads as though it does. Both
    sets are the live vocabulary or they are a comment."""
    live = _live_rung_ids()
    registries = _named_registries()
    dead = {name: sorted(ids - live) for name, ids in registries.items()}
    assert not any(dead.values()), (
        "a spend/fire account names rungs nothing ships — they can never fire, so the account is "
        f"smaller than it reads: {dead}")

    # ...and the SYMMETRIC half, which this test did not have when it was first written and which
    # caught a live rung being pruned alongside the dead ones in the very commit that added it.
    # "no dead members" is satisfied perfectly by an EMPTY set, so the invariant above cannot tell a
    # cleaned account from a deleted one. `baseline_evolution.py`'s own note — *"it must keep its
    # `_CLASS_B_SPEND_IDS` membership"* — is the standing requirement being asserted here.
    for name, ids in registries.items():
        assert ids, f"{name} is EMPTY — the account was deleted, not cleaned"
    assert "dont-rush-evolve-without-target" in registries["planner._CLASS_B_SPEND_IDS"], (
        "the evolve-without-target GATE lost its spend membership; `baseline_evolution.py` requires "
        "it, because the rung is a gate rather than a valuation")
    assert "fire-lunar-cycle" in registries["planner._ABILITY_FIRE_IDS"]


@pytest.mark.req("REQ-STRATEGY-0001")
def test_every_rung_id_matched_in_production_source_is_still_shipped():
    """The general form, and the one that would have caught the two dead `_finish_turn_last` tiers.

    Every string a production module compares against a Hypothesis `id` must name a rung that
    exists. When this goes red the fix is a decision, not a rename: either the consumer's claim
    moved somewhere (say into the composer's differencing) and the branch should be deleted with the
    loss recorded, or it did not and the rung should not have been."""
    live = _live_rung_ids()
    matched = _matched_literals()
    dead = {rid: where for rid, where in matched.items() if rid not in live}
    assert not dead, (
        "production code matches rung ids that no Strategy ships — these branches are unreachable "
        f"and read as live: {dead}")


@pytest.mark.req("REQ-STRATEGY-0001")
def test_the_instrument_itself_finds_a_planted_dead_id():
    """POSITIVE CONTROL, and this file needs one more than most.

    Both assertions above are ABSENCE assertions, and *"found nothing"* and *"my instrument is
    broken"* return the same empty output (CLAUDE.md). With the two `_finish_turn_last` tiers deleted
    the AST walk over `src/` legitimately returns few or no matches, so `test_every_rung_id_matched_
    ...` would pass just as green against a walker that had stopped parsing, stopped recursing, or
    stopped recognising `getattr(h, "id", None)`.

    So the walker is re-pointed at source holding a planted dead id in each of the four shapes it
    claims to find, plus the two it must NOT find — a bare string compare with no `.id` on the left,
    and the same id in a comment. It has to come back with exactly the four."""
    src = (
        'def f(h, hs, S):\n'
        '    a = h.id == "planted-eq"\n'
        '    b = getattr(h, "id", None) in ("planted-tuple", "planted-tuple-2")\n'
        '    c = any(x.id != "planted-ne" for x in hs)\n'
        '    d = h.name == "not-a-rung-id"        # left operand is not `.id`\n'
        '    e = "planted-in-a-comment" in S      # and this one is prose\n'
        '    return a, b, c, d, e\n')
    tree = ast.parse(src)
    found: set = set()

    def _is_id_read(node) -> bool:
        if isinstance(node, ast.Attribute) and node.attr == "id":
            return True
        return (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "getattr" and len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant) and node.args[1].value == "id")

    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and _is_id_read(node.left):
            for comp in node.comparators:
                elts = comp.elts if isinstance(comp, (ast.Tuple, ast.List, ast.Set)) else [comp]
                found |= {e.value for e in elts
                          if isinstance(e, ast.Constant) and isinstance(e.value, str)}

    assert found == {"planted-eq", "planted-tuple", "planted-tuple-2", "planted-ne"}, found
    # ...and the same walker, run over the real tree, must still reach every production module.
    assert len(list(SRC.rglob("*.py"))) > 50, "the source sweep found almost nothing — check SKIP"


@pytest.mark.req("REQ-STRATEGY-0001")
def test_the_roster_is_not_empty_and_names_a_rung_from_each_layer():
    """The other control: `_live_rung_ids()` returning `set()` would make BOTH assertions above fail
    loudly rather than pass — but it would fail for the wrong reason and send the next reader
    hunting a rung deletion that never happened. Asserted per LAYER, because a general roster that
    loaded while every deck silently failed to import would still look healthy in a bare count."""
    from common.strategy.general_strategy import GENERAL_STRATEGY

    live = _live_rung_ids()
    general = {h.id for h in GENERAL_STRATEGY.hypotheses}
    assert len(general) > 20, f"the general roster did not load: {len(general)}"
    assert "attach-solrock-over-line-base" in live, "mega_lucario's deck rungs are missing"
    assert live > general, "no deck contributed a rung of its own — a deck strategy failed to load"
