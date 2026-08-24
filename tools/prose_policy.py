"""Validate live tracked prose against retirement and reference policy."""
from __future__ import annotations

import argparse
import ast
import importlib.util
import io
import re
import subprocess
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ROOTS = ("src/", "tools/", "tests/", "docs/")
RETIRED_IDENTIFIERS = (
    "Pilot",
    "StateModel",
    "MatchupPlan",
    "deck-align",
    "deck-genie",
    "matchup-genie",
    "update-strategy",
)
EXCLUDED_PREFIXES = ("deprecated/", "src/cg/")
EXCLUDED_FILES = ("docs/plans/ledger-corpus-dashboard.md",)

_PATH = re.compile(
    r"(?<![\w./-])(?:src|tools|tests|docs)/[A-Za-z0-9_.-]+"
    r"(?:/[A-Za-z0-9_.-]+)*(?::\d+)?"
)
_MODULE_COMMAND = re.compile(r"\bpython(?:3)?\s+-m\s+([A-Za-z_][\w.]*)")
_SCRIPT_COMMAND = re.compile(r"\bpython(?:3)?\s+((?:src|tools|tests|docs)/[\w./-]+\.py)")


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    kind: str
    value: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}  {self.kind}: {self.value}"


def excluded(path: str) -> bool:
    path = path.replace("\\", "/")
    parts = path.split("/")
    return (
        path.startswith(EXCLUDED_PREFIXES)
        or path in EXCLUDED_FILES
        or (path.startswith("docs/adr/") and path != "docs/adr/README.md")
        or "fixtures" in parts
    )


def tracked_prose_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO, check=True, capture_output=True, text=True, encoding="utf-8",
    )
    paths = (line.replace("\\", "/") for line in result.stdout.splitlines())
    return [
        path for path in paths
        if path.startswith(ROOTS) and path.endswith((".py", ".md"))
        and (REPO / path).is_file() and not excluded(path)
    ]


def _python_prose(source: str) -> list[tuple[int, str]]:
    prose: list[tuple[int, str]] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT:
                prose.append((token.start[0], token.string.lstrip("#").strip()))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return prose
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", ())
        if not body or not isinstance(body[0], ast.Expr):
            continue
        value = body[0].value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            prose.extend(
                (body[0].lineno + offset, line)
                for offset, line in enumerate(value.value.splitlines())
            )
    return prose


def _module_resolves(module: str) -> bool:
    relative = Path(*module.split("."))
    candidates = (REPO / relative, REPO / "tools" / relative, REPO / "src" / relative)
    if any(path.with_suffix(".py").is_file() or (path / "__init__.py").is_file()
           for path in candidates):
        return True
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _path_resolves(value: str) -> bool:
    bare = re.sub(r":\d+$", "", value).rstrip(".,;:")
    path = REPO / bare
    return path.exists() or (not path.suffix and path.with_suffix(".py").is_file())


def scan_text(path: str, text: str) -> list[Violation]:
    path = path.replace("\\", "/")
    if excluded(path):
        return []
    prose = _python_prose(text) if path.endswith(".py") else list(enumerate(text.splitlines(), 1))
    violations: list[Violation] = []
    for line, value in prose:
        if path != "docs/adr/README.md":
            for retired in RETIRED_IDENTIFIERS:
                if re.search(rf"(?<![\w-]){re.escape(retired)}(?![\w-])", value):
                    violations.append(Violation(path, line, "retired identifier", retired))
        for match in (() if path == "docs/adr/README.md" else _PATH.finditer(value)):
            target = match.group(0)
            if not _path_resolves(target):
                violations.append(Violation(path, line, "missing path", target))
        for match in _MODULE_COMMAND.finditer(value):
            module = match.group(1)
            if module != "pytest" and not _module_resolves(module):
                violations.append(Violation(path, line, "missing command", f"python -m {module}"))
        for match in _SCRIPT_COMMAND.finditer(value):
            script = match.group(1)
            if not _path_resolves(script):
                violations.append(Violation(path, line, "missing command", f"python {script}"))
    return violations


def scan_tracked() -> list[Violation]:
    violations: list[Violation] = []
    for path in tracked_prose_files():
        text = (REPO / path).read_text(encoding="utf-8", errors="replace")
        violations.extend(scan_text(path, text))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    violations = scan_tracked()
    for violation in violations:
        print(violation)
    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
