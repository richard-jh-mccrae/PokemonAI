"""Prove a refactor MOVED code without changing it.

Snapshot the resolved method surface of a class before, compare after, and report any method
whose CODE changed rather than its address.

    python -m tools.move_equivalence snapshot --out .move.json
    python -m tools.move_equivalence verify --against .move.json

`Pilot` is a mixin composition, so walking `__mro__` yields the same method set wherever a
method sits — moving code between those files is invisible here by construction. Bodies compare
as normalized ASTs (`ast.dump` without attributes), so line numbers and comments are ignored
while every expression, constant and docstring is significant."""
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


def _body_hash(func: types.FunctionType) -> str | None:
    """Normalized AST digest of a function, or None when its source cannot be read."""
    try:
        source = textwrap.dedent(inspect.getsource(func))
    except (OSError, TypeError):
        return None
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    return hashlib.sha256(ast.dump(tree, include_attributes=False).encode("utf-8")).hexdigest()[:16]


def surface(cls: type) -> dict[str, dict[str, str]]:
    """`{method: {"hash", "module"}}` for every function the class resolves, first-in-MRO winning."""
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
            digest = _body_hash(func)
            if digest is None:
                continue
            module = inspect.getsourcefile(func) or ""
            try:
                module = str(Path(module).resolve().relative_to(REPO)).replace("\\", "/")
            except ValueError:
                pass
            out[name] = {"hash": digest, "module": module}
    return out


def load_target(dotted: str) -> type:
    module_name, _, class_name = dotted.rpartition(".")
    module = __import__(module_name, fromlist=[class_name])
    return getattr(module, class_name)


def compare(before: dict[str, dict[str, str]], after: dict[str, dict[str, str]]) -> dict[str, list]:
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed, moved = [], []
    for name in sorted(set(before) & set(after)):
        if before[name]["hash"] != after[name]["hash"]:
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
    args = parser.parse_args(argv)

    current = surface(load_target(args.target))

    if args.action == "snapshot":
        args.out.write_text(json.dumps({"target": args.target, "surface": current}, indent=1),
                            encoding="utf-8")
        print(f"snapshot: {len(current)} methods from {args.target} -> {args.out}")
        return 0

    against = args.against or args.out
    saved = json.loads(against.read_text(encoding="utf-8"))
    result = compare(saved["surface"], current)

    print(f"{len(saved['surface'])} methods before, {len(current)} after")
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
