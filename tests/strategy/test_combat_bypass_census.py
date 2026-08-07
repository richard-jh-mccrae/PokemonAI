"""Zero undocumented CombatMath bypasses on model-covered questions (Issue #260), asserted by walking
the call sites rather than by review.

A question is MODEL-COVERED when TWO READERS COULD DISAGREE — a board read can, a pure function of
its own arguments cannot, which is why the card-arithmetic adapters are allowlisted rather than
migrated. Each `DELIBERATE` entry names the function, the method, and WHY the bypass survives.
"""
import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: Board reads where two derivations could drift apart. `prize_value` / `attached_type_counts` are
#: here despite being pure arithmetic because the model memoizes them per body.
MODEL_COVERED = frozenset({
    "incoming", "reachable_incoming", "incoming_active_damage", "active_doomed", "doomed_incoming",
    "turns_to_ko_me", "turns_to_afford", "discard_recur_fuel",
    "attach_budget", "reachable_attach", "best_reachable_damage", "readiness_p",
    "attached_type_counts", "prize_value",
})

#: A GLOB, not a list: the Pilot is a mixin composition, so a hand-kept tuple narrows when a family
#: moves. `tests/test_source_scan_coverage.py` grades this by what it RESOLVES to.
MODULES = ("src/common/pilot.py", "src/common/strategy/planner.py",
           *sorted(p.relative_to(REPO).as_posix()
                   for p in (REPO / "src" / "common" / "deciders").glob("*.py")
                   if p.name != "__init__.py"))

#: ``(enclosing function, CombatMath method) -> why this bypass is deliberate.``
DELIBERATE = {
    # ── 1. HYPOTHETICAL enabler Budgets: the model cannot supply a target that is not in play, and a
    #       `MySide` method per hypothetical would move the assembly rather than remove it.
    ("_evolve_income_delta", "attach_budget"):
        "hypothetical enabler Budget — the evolve income leg's target is a form not in play",
    ("_promote_closure", "attach_budget"):
        "hypothetical enabler Budget — the promote income leg's target is a body not yet Active",

    # ── 2. The EMPTY-Budget second leg: the model route always carries the FULL Budget, so the
    #       counterfactual's "with what it holds right now" leg has no model expression.
    ("_attach_value", "best_reachable_damage"):
        "#142 empty-Budget leg — 'with what is attached right now', the baseline of the counterfactual",
    ("_active_arm_available", "reachable_attach"):
        "#142 empty-Budget leg — the biggest attack is NOT payable on the empty budget but IS on the full one",

    # ── 3. ONE-FACT-SOURCE. A read whose whole point is that exactly one function owns the fact.
    ("_recur_fueled_oa", "discard_recur_fuel"):
        "one-fact-source (ADR-0076 S2): the doom relax's `fueled` gate and this augmentation must "
        "read the SAME discard, or the relax could fire on a read that never counted its own fuel",

    # ── 4. PURE CARD ARITHMETIC over a SYNTHETIC body dict: no board state to disagree about, and a
    #       `view_of` route would build a throwaway view for nothing.
    ("_prize_value", "prize_value"):
        "card knowledge, constant all game — `PrizeRace`'s own docstring keeps per-body prize YIELD "
        "on the oracle and only the RACE on the model (ADR-0052)",
    ("_attached_type_counts", "attached_type_counts"):
        "pure typed arithmetic over a body's own `energies` — the generic adapter, called with "
        "synthetic bodies",
    # ("_payable_energy", "attached_type_counts") was deleted with its call site (Issue #386) rather
    # than kept "just in case" — see `test_the_deliberate_list_has_no_stale_entries`.
}


def _bypasses():
    """``[(module, line, function, method)]`` for every direct `self.combat.<m>(...)` bypass."""
    found = []
    for rel in MODULES:
        tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
        stack = []

        class V(ast.NodeVisitor):
            def visit_FunctionDef(self, node):
                stack.append(node.name)
                self.generic_visit(node)
                stack.pop()

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Call(self, node):
                f = node.func
                if (isinstance(f, ast.Attribute) and f.attr in MODEL_COVERED
                        and isinstance(f.value, ast.Attribute) and f.value.attr == "combat"):
                    found.append((rel, node.lineno, stack[-1] if stack else "<module>", f.attr))
                self.generic_visit(node)

        V().visit(tree)
    return found


@pytest.mark.req("REQ-T1-CENSUS-0001")
def test_every_surviving_bypass_is_on_the_deliberate_list():
    """An unmigrated consumer and a RE-OPENED one look identical from the outside."""
    undocumented = [(mod, line, fn, m) for mod, line, fn, m in _bypasses()
                    if (fn, m) not in DELIBERATE]
    assert not undocumented, (
        "undocumented CombatMath bypass on a model-covered question — migrate it onto the snapshot, "
        "or add it to DELIBERATE with the reason it survives:\n"
        + "\n".join(f"  {mod}:{line}  {fn}() -> combat.{m}()" for mod, line, fn, m in undocumented))


@pytest.mark.req("REQ-T1-CENSUS-0001")
def test_the_deliberate_list_has_no_stale_entries():
    """An entry whose call site is gone is a licence nobody revoked, and the next function to take
    that name inherits it silently."""
    live = {(fn, m) for _mod, _line, fn, m in _bypasses()}
    stale = sorted(set(DELIBERATE) - live)
    assert not stale, f"DELIBERATE names bypasses that no longer exist: {stale}"


@pytest.mark.req("REQ-T1-CENSUS-0001")
def test_every_deliberate_entry_gives_a_reason():
    """A one-word entry is not a ruling: a reason must name the doctrine or the mechanism."""
    for key, why in DELIBERATE.items():
        assert len(why) > 40, f"{key}: the reason is too thin to be a ruling"


@pytest.mark.req("REQ-T1-CENSUS-0001")
def test_the_clock_family_has_no_bypass_at_all():
    """Stated separately so an allowlist edit for an unrelated family cannot weaken it: these are the
    reads carrying the Read's energy policy and the forward-availability gate."""
    clock = {"incoming", "reachable_incoming", "incoming_active_damage", "active_doomed",
             "doomed_incoming", "turns_to_ko_me", "turns_to_afford"}
    offenders = [(mod, line, fn, m) for mod, line, fn, m in _bypasses() if m in clock]
    assert not offenders, "\n".join(
        f"  {mod}:{line}  {fn}() -> combat.{m}()" for mod, line, fn, m in offenders)
