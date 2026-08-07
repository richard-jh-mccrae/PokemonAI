"""Extract the source text and docstring literals that the SUITE asserts, so a cleanup cannot delete them.

The 2026-08-07 audit found the suite reads source *text* in dozens of places — `inspect.getsource`,
`__doc__`, `read_text()` — and asserts substrings over it. A comment reduction that treats all prose
as free-to-cut turns those red. Worse, the hazard runs BOTH ways:

* **REQUIRED** — `assert "working()" in sv.attack_ev_legs.__doc__`. The literal must survive.
* **FORBIDDEN** — `assert "off_policy" not in inspect.getsource(gates.decision_gate_verdict)`.
  Deleting prose is safe; a REWRITE that introduces the word turns the suite red for no code change.

Derived rather than hand-listed, so it cannot drift: a hand-copied roster would be a second source of
truth about the tests, which is the failure this whole effort exists to end.

    python -m tools.asserted_text            # human-readable
    python -m tools.asserted_text --json     # for the reduction pass

Detection is a local dataflow inside each test function: variables bound from a source-reading call
are tracked, then every `in` / `not in` comparison against one of them (or against such a call
directly) contributes its string literal.
"""
from __future__ import annotations

import argparse
import ast
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

_SOURCE_CALLS = ("getsource", "read_text")


def _is_source_expr(node: ast.AST) -> bool:
    """A call yielding SOURCE text: `getsource`, `__doc__`, or `read_text` on a committed `.py`.
    Generated artifacts are excluded — HTML written into `tmp_path` is not something a cleanup can break."""
    if isinstance(node, ast.Attribute) and node.attr == "__doc__":
        return True
    if isinstance(node, ast.BoolOp):
        return any(_is_source_expr(v) for v in node.values)
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if not (isinstance(func, ast.Attribute) and func.attr in _SOURCE_CALLS):
        return False
    if func.attr == "getsource":
        return True
    rendered = _describe(node)
    return ".py" in rendered and "tmp_path" not in rendered


def _describe(node: ast.AST) -> str:
    try:
        return ast.unparse(node)[:120]
    except Exception:  # pragma: no cover
        return "<unparseable>"


def _scan_function(fn: ast.AST) -> list[tuple[str, str, str]]:
    """`[(kind, target, literal)]` for one function body."""
    bound: dict[str, str] = {}
    out: list[tuple[str, str, str]] = []

    looped: dict[str, list[str]] = {}
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and _is_source_expr(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    bound[target.id] = _describe(node.value)
        elif isinstance(node, ast.For) and isinstance(node.target, ast.Name) \
                and isinstance(node.iter, (ast.Tuple, ast.List, ast.Set)):
            values = [e.value for e in node.iter.elts
                      if isinstance(e, ast.Constant) and isinstance(e.value, str)]
            if values:
                looped[node.target.id] = values

    def resolve(node: ast.AST) -> str | None:
        """The source target a comparison's right-hand side names, unwrapping `.lower()` and locals."""
        if _is_source_expr(node):
            return _describe(node)
        if isinstance(node, ast.Name) and node.id in bound:
            return bound[node.id]
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr in ("lower", "upper", "strip"):
            return resolve(node.func.value)
        return None

    for node in ast.walk(fn):
        if isinstance(node, ast.Assert) and _is_source_expr(node.test):
            out.append(("NONEMPTY", _describe(node.test), ""))
        if not isinstance(node, ast.Compare) or len(node.ops) != 1:
            continue
        op = node.ops[0]
        if not isinstance(op, (ast.In, ast.NotIn)):
            continue
        target = resolve(node.comparators[0])
        if target is None:
            continue
        left = node.left
        literals = []
        if isinstance(left, ast.Constant) and isinstance(left.value, str):
            literals = [left.value]
        elif isinstance(left, ast.Name) and left.id in looped:
            literals = looped[left.id]
        elif isinstance(left, (ast.Tuple, ast.List, ast.Set)):
            literals = [e.value for e in left.elts
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)]
        for literal in literals:
            out.append(("FORBIDDEN" if isinstance(op, ast.NotIn) else "REQUIRED", target, literal))
    return out


def collect() -> dict[str, list[dict[str, str]]]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO, check=True, encoding="utf-8", text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout
    found: dict[str, list[dict[str, str]]] = defaultdict(list)
    for rel in (p.replace("\\", "/") for p in out.splitlines()):
        # `--cached` still lists a file deleted from disk but not yet committed, so `is_file` is load-bearing.
        if not (rel.startswith("tests/") and rel.endswith(".py") and (REPO / rel).is_file()):
            continue
        try:
            tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for kind, target, literal in _scan_function(node):
                found[rel].append({"kind": kind, "test": node.name, "target": target,
                                   "literal": literal})
    return dict(found)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    found = collect()
    flat = [dict(file=rel, **row) for rel, rows in found.items() for row in rows]
    if args.as_json:
        json.dump(flat, sys.stdout, indent=1)
        return 0

    required = [r for r in flat if r["kind"] == "REQUIRED"]
    forbidden = [r for r in flat if r["kind"] == "FORBIDDEN"]
    print(f"{len(flat)} asserted literals across {len(found)} test files "
          f"({len(required)} REQUIRED, {len(forbidden)} FORBIDDEN)\n")
    for rel in sorted(found):
        print(f"--- {rel}")
        for row in found[rel]:
            print(f"    {row['kind']:9} {row['literal'][:58]!r:62} <- {row['target'][:52]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
