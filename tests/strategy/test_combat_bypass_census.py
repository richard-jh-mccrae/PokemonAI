"""POC-T1 (Issue #260) acceptance — **zero undocumented CombatMath bypasses on model-covered
questions**, asserted by walking the call sites rather than by review.

The StateModel is the sole data supplier (ADR-0092's standing ruling). Until T1 that was aspiration:
every live clock consumer reached past the model to `CombatMath`, and the reason was structural —
without the threaded Read policy and the counterfactual-board argument the model route answered a
strictly narrower question than the bypass beside it. T1 closed the gap, and this is the test that
stops it re-opening, because a re-opened bypass looks exactly like a bypass that was never migrated.

**What makes a question "model-covered".** Not "the model happens to have a method for it" — the rule
is whether TWO READERS COULD DISAGREE. A read of BOARD STATE can: two derivations of "how fast is
that threat" drift the moment one of them grows a policy, which is the defect ADR-0087 charges for and
the f70 false-famine was an instance of. A pure function of its own arguments cannot — there is no
state to disagree about — which is why the three card-arithmetic adapters below are on the allowlist
rather than migrated to a route that would buy nothing.

**The allowlist is the deliberate list the issue asks for.** Each entry names the enclosing function,
the method, and WHY the bypass survives. A new entry is a decision; adding one without a reason is
the thing this test exists to make impossible.
"""
import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

#: Questions the StateModel covers — board reads where two derivations could drift apart.
#: `prize_value` and `attached_type_counts` are here even though they are pure card arithmetic,
#: because the model DOES memoize them per body and the issue named the sites that should route
#: through it; the generic adapters that answer them for a synthetic `{"id": …}` are allowlisted.
MODEL_COVERED = frozenset({
    "incoming", "reachable_incoming", "incoming_active_damage", "active_doomed", "doomed_incoming",
    "turns_to_ko_me", "turns_to_afford", "discard_recur_fuel",
    "attach_budget", "reachable_attach", "best_reachable_damage", "readiness_p",
    "attached_type_counts", "prize_value",
})

#: A GLOB, not a list: the Pilot is a mixin composition spread over `common/deciders/`, so a hand-kept
#: tuple silently narrows the moment a family moves. `tests/test_source_scan_coverage.py` grades this
#: by what it RESOLVES to, which is what lets a self-maintaining scan be credited for its real reach.
MODULES = ("src/common/pilot.py", "src/common/strategy/planner.py",
           *sorted(p.relative_to(REPO).as_posix()
                   for p in (REPO / "src" / "common" / "deciders").glob("*.py")
                   if p.name != "__init__.py"))

#: ``(enclosing function, CombatMath method) -> why this bypass is deliberate.``
#: Three families, each named by the issue or derived from a doctrine already in the tree.
DELIBERATE = {
    # ── 1. HYPOTHETICAL enabler Budgets. The Budget is built for a body the board does not carry in
    #       that configuration — an evolved form, a promote candidate holding an option's provision.
    #       Its arguments are all model reads (`mine.hand_ids`, `mine.hand_energy_types`, the quota
    #       flags); what the model cannot supply is the HYPOTHETICAL target itself, and inventing a
    #       `MySide` method per hypothetical would move the assembly, not remove it.
    ("_evolve_income_delta", "attach_budget"):
        "hypothetical enabler Budget — the evolve income leg's target is a form not in play",
    ("_promote_closure", "attach_budget"):
        "hypothetical enabler Budget — the promote income leg's target is a body not yet Active",

    # ── 2. The EMPTY-Budget second leg (the #142 idiom). A counterfactual pair "what can this body
    #       do with what it holds RIGHT NOW" vs "…under its full Budget"; the model route always
    #       carries the full Budget, so the empty leg has no model expression by construction.
    ("_attach_value", "best_reachable_damage"):
        "#142 empty-Budget leg — 'with what is attached right now', the baseline of the counterfactual",
    ("_active_arm_available", "reachable_attach"):
        "#142 empty-Budget leg — the biggest attack is NOT payable on the empty budget but IS on the full one",

    # ── 3. ONE-FACT-SOURCE. A read whose whole point is that exactly one function owns the fact.
    ("_recur_fueled_oa", "discard_recur_fuel"):
        "one-fact-source (ADR-0076 S2): the doom relax's `fueled` gate and this augmentation must "
        "read the SAME discard, or the relax could fire on a read that never counted its own fuel",

    # ── 4. PURE CARD ARITHMETIC over a body dict. No board state, so two readers cannot disagree —
    #       and every caller here passes a SYNTHETIC `{"id": cid}` or a simulated body that is not
    #       on the board at all, so a `view_of` route would build a throwaway view for nothing.
    ("_prize_value", "prize_value"):
        "card knowledge, constant all game — `PrizeRace`'s own docstring keeps per-body prize YIELD "
        "on the oracle and only the RACE on the model (ADR-0052)",
    ("_attached_type_counts", "attached_type_counts"):
        "pure typed arithmetic over a body's own `energies` — the generic adapter, called with "
        "synthetic bodies",
    # ("_payable_energy", "attached_type_counts") was here until POC-T4/5 (Issue #386) deleted
    # the planner rollout that made the call. Removed rather than kept "just in case": this
    # test exists because an entry whose call site is gone is a licence nobody revoked, and
    # the next function to take that name inherits it silently.
}


def _bypasses():
    """``[(module, line, enclosing function, method)]`` for every direct `self.combat.<m>(...)` on a
    model-covered question."""
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
    """T1's acceptance criterion. A bypass that is not listed is either an unmigrated consumer or a
    re-opened one, and from the outside those are the same thing."""
    undocumented = [(mod, line, fn, m) for mod, line, fn, m in _bypasses()
                    if (fn, m) not in DELIBERATE]
    assert not undocumented, (
        "undocumented CombatMath bypass on a model-covered question — migrate it onto the snapshot, "
        "or add it to DELIBERATE with the reason it survives:\n"
        + "\n".join(f"  {mod}:{line}  {fn}() -> combat.{m}()" for mod, line, fn, m in undocumented))


@pytest.mark.req("REQ-T1-CENSUS-0001")
def test_the_deliberate_list_has_no_stale_entries():
    """The allowlist shrinks with the code. An entry whose call site is gone is a licence nobody
    revoked — and the next function to take that name inherits it silently."""
    live = {(fn, m) for _mod, _line, fn, m in _bypasses()}
    stale = sorted(set(DELIBERATE) - live)
    assert not stale, f"DELIBERATE names bypasses that no longer exist: {stale}"


@pytest.mark.req("REQ-T1-CENSUS-0001")
def test_every_deliberate_entry_gives_a_reason():
    """A one-word entry is not a ruling. Each reason has to name the doctrine or the mechanism, which
    is the difference between a documented bypass and a tolerated one."""
    for key, why in DELIBERATE.items():
        assert len(why) > 40, f"{key}: the reason is too thin to be a ruling"


@pytest.mark.req("REQ-T1-CENSUS-0001")
def test_the_clock_family_has_no_bypass_at_all():
    """The strongest slice, stated separately so it cannot be weakened by an allowlist edit made for
    an unrelated family: the Threat-Clock reads — the ones carrying the Read's energy policy and the
    forward-availability gate — have ZERO surviving bypasses. Those are precisely the questions where
    a bypass was strictly BETTER than the model route before T1 threaded it, so a regression here
    means the threading came undone."""
    clock = {"incoming", "reachable_incoming", "incoming_active_damage", "active_doomed",
             "doomed_incoming", "turns_to_ko_me", "turns_to_afford"}
    offenders = [(mod, line, fn, m) for mod, line, fn, m in _bypasses() if m in clock]
    assert not offenders, "\n".join(
        f"  {mod}:{line}  {fn}() -> combat.{m}()" for mod, line, fn, m in offenders)
