"""Prove a refactor MOVED code without changing it.

Snapshot the resolved method surface of a class before, compare after, and report any method
whose CODE changed rather than its address.

    python -m tools.move_equivalence snapshot --out .move.json
    python -m tools.move_equivalence verify --against .move.json

`Pilot` is a mixin composition, so walking `__mro__` yields the same method set wherever a
method sits — moving code between those files is invisible here by construction. Bodies compare
as normalized ASTs (`ast.dump` without attributes), so line numbers and comments are ignored.
Docstrings are stripped too: `inspect.getsource` reads them, so a documentation pass would
otherwise report every method as CHANGED. `--include-docstrings` compares the prose-sensitive
hash stored beside it."""
from __future__ import annotations

import argparse
import ast
import hashlib
import inspect
import json
import sys
import textwrap
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "src"))


CODE_ONLY, WITH_DOCSTRINGS = "hash", "hash_with_docstrings"
#: Snapshots before this key existed also carried a `hash` — a DIFFERENT normalization under the
#: same name, so presence cannot be the test. Verify refuses a snapshot that does not declare it.
HASHES = "hashes"
_DOCSTRING_OWNERS = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    """Drop every leading string-literal statement, in place. `Pass` stands in for a body that was
    nothing but prose, so the node stays a valid — and empty — piece of code."""
    for node in ast.walk(tree):
        if not isinstance(node, _DOCSTRING_OWNERS) or not node.body:
            continue
        head = node.body[0]
        if (isinstance(head, ast.Expr) and isinstance(head.value, ast.Constant)
                and isinstance(head.value.value, str)):
            node.body = node.body[1:] or [ast.Pass()]
    return tree


def _digest(tree: ast.AST) -> str:
    return hashlib.sha256(ast.dump(tree, include_attributes=False).encode("utf-8")).hexdigest()[:16]


def _body_hashes(func: types.FunctionType) -> dict[str, str] | None:
    """Both digests of a function — code-only and prose-sensitive — or None when its source cannot
    be read. Order matters: the prose-sensitive one is taken before the strip mutates the tree."""
    try:
        source = textwrap.dedent(inspect.getsource(func))
    except (OSError, TypeError):
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    with_docstrings = _digest(tree)
    return {CODE_ONLY: _digest(_strip_docstrings(tree)), WITH_DOCSTRINGS: with_docstrings}


def surface(cls: type) -> dict[str, dict[str, str]]:
    """`{method: {both hashes, "module"}}` for every function the class resolves, first-in-MRO winning."""
    out: dict[str, dict[str, str]] = {}
    for klass in cls.__mro__:
        if klass is object:
            continue
        for name, value in vars(klass).items():
            if name in out:
                continue
            func = value
            if isinstance(value, (staticmethod, classmethod)):
                func = value.__func__
            elif isinstance(value, property):
                func = value.fget
            if not isinstance(func, types.FunctionType):
                continue
            digests = _body_hashes(func)
            if digests is None:
                continue
            module = inspect.getsourcefile(func) or ""
            try:
                module = str(Path(module).resolve().relative_to(REPO)).replace("\\", "/")
            except ValueError:
                pass
            out[name] = {**digests, "module": module}
    return out


def load_target(dotted: str) -> type:
    module_name, _, class_name = dotted.rpartition(".")
    module = __import__(module_name, fromlist=[class_name])
    return getattr(module, class_name)


def compare(before: dict[str, dict[str, str]], after: dict[str, dict[str, str]],
            key: str = CODE_ONLY) -> dict[str, list]:
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed, moved = [], []
    for name in sorted(set(before) & set(after)):
        if before[name][key] != after[name][key]:
            changed.append(name)
        elif before[name]["module"] != after[name]["module"]:
            moved.append(f'{name}: {before[name]["module"]} -> {after[name]["module"]}')
    return {"added": added, "removed": removed, "changed": changed, "moved": moved}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("snapshot", "verify"))
    parser.add_argument("--target", default="common.pilot.Pilot")
    parser.add_argument("--out", type=Path, default=REPO / ".move_equivalence.json")
    parser.add_argument("--against", type=Path)
    parser.add_argument("--allow-changed", action="store_true",
                        help="report body changes without failing (use when a move is not pure by design)")
    parser.add_argument("--include-docstrings", action="store_true",
                        help="verify: count a docstring edit as a change (default: code only)")
    args = parser.parse_args(argv)

    current = surface(load_target(args.target))

    if args.action == "snapshot":
        payload = {"target": args.target, HASHES: [CODE_ONLY, WITH_DOCSTRINGS], "surface": current}
        args.out.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"snapshot: {len(current)} methods from {args.target} -> {args.out}")
        return 0

    key = WITH_DOCSTRINGS if args.include_docstrings else CODE_ONLY
    against = args.against or args.out
    saved = json.loads(against.read_text(encoding="utf-8"))
    if key not in saved.get(HASHES, []):
        print(f"{against} does not declare '{key}' — it predates the docstring split, and its 'hash' "
              f"means something else. Re-run `snapshot` on the pre-refactor tree.")
        return 2
    result = compare(saved["surface"], current, key)

    print(f"{len(saved['surface'])} methods before, {len(current)} after ({key})")
    print(f"  moved   : {len(result['moved'])}")
    print(f"  changed : {len(result['changed'])}")
    print(f"  added   : {len(result['added'])}")
    print(f"  removed : {len(result['removed'])}")
    for name in result["moved"]:
        print(f"    move    {name}")
    for name in result["changed"]:
        print(f"    CHANGED {name}")
    for name in result["added"]:
        print(f"    ADDED   {name}")
    for name in result["removed"]:
        print(f"    REMOVED {name}")

    fatal = result["changed"] * (not args.allow_changed) + result["added"] + result["removed"]
    if fatal:
        print("\nNOT a pure move — the surface changed, not just its addresses.")
        return 1
    print("\npure move: every method resolves to identical code.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
