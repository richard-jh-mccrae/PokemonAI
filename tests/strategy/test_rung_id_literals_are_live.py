"""A rung ID that production code MATCHES ON must be a rung some Strategy ships.

**A retired id sitting in a live string literal reads as LIVE to every instrument.** Deleting a
Hypothesis breaks no import and fails no test; the consumer keeps compiling and quietly stops firing.
It happened twice inside Issue #386 — `_finish_turn_last`'s tiers, and the two halves of ADR-0069's
spend account.

Scope is deliberately narrow: only ids that CONTROL BEHAVIOUR (a literal compared against a
Hypothesis `id`, or a member of a set that is). PROSE is exempt and must stay exempt — a fold record
is *about* deleted rungs, and an invariant that could not tell those apart would force the audit
trail to be deleted to stay green.
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
    """Every Hypothesis id the shipped agents can score, general + per-deck. Loaded by FILE PATH,
    never as ``agents.<deck>.strategy`` — that collides with `kaggle_environments`' own `agents`."""
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
    """``{rung id: [where it is matched]}``. The test is on the LEFT operand — a `.id` access or
    `getattr(x, "id", ...)` — which is why this walks the AST: a regex cannot exempt a comment."""
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
    """A member no Strategy ships can never appear in `OptionTrace.fired`, so it contributes nothing
    and reads as though it does. Both sets are the live vocabulary or they are a comment (ADR-0069)."""
    live = _live_rung_ids()
    registries = _named_registries()
    dead = {name: sorted(ids - live) for name, ids in registries.items()}
    assert not any(dead.values()), (
        "a spend/fire account names rungs nothing ships — they can never fire, so the account is "
        f"smaller than it reads: {dead}")

    # The SYMMETRIC half: "no dead members" is satisfied perfectly by an EMPTY set, so the invariant
    # above cannot tell a cleaned account from a deleted one.
    for name, ids in registries.items():
        assert ids, f"{name} is EMPTY — the account was deleted, not cleaned"
    assert registries["planner._CLASS_B_SPEND_IDS"] == {"dont-search-an-empty-deck"}
    assert registries["planner._ABILITY_FIRE_IDS"] == {
        "bench-the-comeback-drawer"}


@pytest.mark.req("REQ-STRATEGY-0001")
def test_every_rung_id_matched_in_production_source_is_still_shipped():
    """Every string a production module compares against a Hypothesis `id` must name a rung that
    exists. When this goes red the fix is a DECISION — delete the branch, or restore the rung."""
    live = _live_rung_ids()
    matched = _matched_literals()
    dead = {rid: where for rid, where in matched.items() if rid not in live}
    assert not dead, (
        "production code matches rung ids that no Strategy ships — these branches are unreachable "
        f"and read as live: {dead}")


@pytest.mark.req("REQ-STRATEGY-0001")
def test_the_instrument_itself_finds_a_planted_dead_id():
    """POSITIVE CONTROL: both assertions above are ABSENCE assertions, and the walk over `src/`
    legitimately returns few matches, so a broken walker would pass them just as green."""
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
    """An empty `_live_rung_ids()` fails the assertions above for the WRONG reason. Asserted per
    LAYER: a general roster that loaded while every deck failed to import still looks healthy."""
    from common.strategy.general_strategy import GENERAL_STRATEGY

    live = _live_rung_ids()
    general = {h.id for h in GENERAL_STRATEGY.hypotheses}
    assert general == {"dont-search-an-empty-deck", "keep-a-startable-hand", "honor-preferred-start"}
    assert "attach-solrock-over-line-base" in live, "mega_lucario's deck rungs are missing"
    assert live > general, "no deck contributed a rung of its own — a deck strategy failed to load"
