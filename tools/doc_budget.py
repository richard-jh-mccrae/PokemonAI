"""Report every comment and docstring in this repo that exceeds the code-as-documentation budget.

The budget (`.claude/skills/code-as-docs/SKILL.md`): 2 lines for a `#` block, 2 for a function
or class docstring, 15 for a module docstring, 120 characters for any prose line.

    python -m tools.doc_budget [prefix] [--detail] [--json]

The scan set is `git ls-files`, never a filesystem walk: a walk pulls in `.venv/` and the live
worktrees under `.claude/worktrees/` and reports another branch's file as this tree's defect.
`src/cg/` is excluded — vendored, off-limits per CLAUDE.md."""
from __future__ import annotations

import argparse
import ast
import io
import json
import subprocess
import sys
import tokenize
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

MAX_LINE = 120
MAX_COMMENT_LINES = 2
MAX_DOCSTRING_LINES = 2
MAX_MODULE_DOC_LINES = 15

EXCLUDED = ("src/cg/", "deprecated/")


@dataclass
class Offence:
    path: str
    line: int
    kind: str
    lines: int
    longest: int
    limit: int

    def __str__(self) -> str:
        over = f"{self.lines}L" if self.lines > self.limit else f"{self.longest}ch"
        return f"{self.path}:{self.line}  {self.kind}  {over} (limit {self.limit}L/{MAX_LINE}ch)"


@dataclass
class Report:
    offences: list[Offence] = field(default_factory=list)
    files_scanned: int = 0

    def by_kind(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for offence in self.offences:
            counts[offence.kind] = counts.get(offence.kind, 0) + 1
        return counts

    def files_affected(self) -> int:
        return len({offence.path for offence in self.offences})


def python_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO, check=True, encoding="utf-8", text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    ).stdout
    return [
        rel for rel in (p.replace("\\", "/") for p in out.splitlines())
        if rel.endswith(".py") and (REPO / rel).is_file() and not rel.startswith(EXCLUDED)
    ]


def _comment_blocks(source: str, lines: list[str]) -> list[tuple[int, int, int]]:
    """Runs of consecutive own-line `#` comments, as (start, line_count, longest_line)."""
    blocks: list[tuple[int, int, int]] = []
    current: list[int] | None = None
    longest = 0
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return blocks
    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        row = token.start[0]
        trailing = bool(lines[row - 1][: token.start[1]].strip())
        if trailing or (current is not None and row != current[-1] + 1):
            if current is not None:
                blocks.append((current[0], len(current), longest))
            current, longest = (None, 0) if trailing else ([row], len(lines[row - 1]))
            continue
        if current is None:
            current, longest = [row], len(lines[row - 1])
        else:
            current.append(row)
            longest = max(longest, len(lines[row - 1]))
    if current is not None:
        blocks.append((current[0], len(current), longest))
    return blocks


def _docstrings(tree: ast.AST) -> list[tuple[str, int, int, int]]:
    """(kind, line, line_count, longest_line) for module, class and function docstrings."""
    found: list[tuple[str, int, int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Module):
            kind = "module docstring"
        elif isinstance(node, ast.ClassDef):
            kind = "class docstring"
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "function docstring"
        else:
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if not (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)):
            continue
        text = first.value.value.splitlines() or [""]
        found.append((kind, first.lineno, len(text), max(len(line) for line in text)))
    return found


def scan(paths: list[str] | None = None) -> Report:
    report = Report()
    for rel in paths if paths is not None else python_files():
        source = (REPO / rel).read_text(encoding="utf-8", errors="replace")
        lines = source.splitlines()
        report.files_scanned += 1
        for start, count, longest in _comment_blocks(source, lines):
            if count > MAX_COMMENT_LINES or longest > MAX_LINE:
                report.offences.append(Offence(rel, start, "comment block", count, longest, MAX_COMMENT_LINES))
        try:
            tree = ast.parse(source)
        except SyntaxError:
            continue
        for kind, line, count, longest in _docstrings(tree):
            limit = MAX_MODULE_DOC_LINES if kind == "module docstring" else MAX_DOCSTRING_LINES
            if count > limit or longest > MAX_LINE:
                report.offences.append(Offence(rel, line, kind, count, longest, limit))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("prefix", nargs="?", help="only scan paths starting with this prefix")
    parser.add_argument("--detail", action="store_true", help="list every offence")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    paths = [p for p in python_files() if not args.prefix or p.startswith(args.prefix)]
    report = scan(paths)

    if args.as_json:
        json.dump(
            {"files_scanned": report.files_scanned, "files_affected": report.files_affected(),
             "total": len(report.offences), "by_kind": report.by_kind(),
             "offences": [vars(o) for o in report.offences]},
            sys.stdout, indent=1,
        )
        return 0

    print(f"scanned {report.files_scanned} files; {len(report.offences)} offences "
          f"across {report.files_affected()} files")
    for kind, count in sorted(report.by_kind().items(), key=lambda kv: -kv[1]):
        print(f"  {count:6}  {kind}")
    if args.detail:
        print()
        for offence in report.offences:
            print(f"  {offence}")
    return 1 if report.offences else 0


if __name__ == "__main__":
    raise SystemExit(main())
