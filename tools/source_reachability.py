from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path


DYNAMIC_CARD_PACKAGES = (
    "common.cards.energy_cards.",
    "common.cards.pokemon_cards.",
    "common.cards.trainer_cards.",
)
OFFLINE_MODULES = frozenset({"common.engine", "common.information"})
PUBLIC_API_MODULES = frozenset({"common.puct.native", "common.puct.runtime", "common.puct.record"})
EXTERNAL_FUNCTIONS = frozenset({
    "common.cards.pokemon_default_roles",
    "common.ledger.__getattr__",
    "common.ledger.certification.certify_incremental",
    "common.ledger.seam.register_preview_variant",
    "common.telemetry.core.migrate_record",
})


@dataclass(frozen=True)
class ReachabilityReport:
    unreachable_modules: tuple[str, ...]
    unreachable_functions: tuple[str, ...]
    dynamic_modules: tuple[str, ...]


def _module_name(src: Path, path: Path) -> str:
    relative = path.relative_to(src).with_suffix("")
    parts = relative.parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def _shipped_modules(root: Path) -> dict[str, Path]:
    src = root / "src"
    paths = [*sorted((src / "common").rglob("*.py")),
             *sorted((src / "cg").rglob("*.py")),
             *sorted((src / "agents").glob("*/*.py"))]
    modules = {_module_name(src, path): path for path in paths}
    return {name: path for name, path in modules.items() if name not in OFFLINE_MODULES}


def _import_target(current: str, node: ast.ImportFrom, packages: set[str]) -> str:
    if not node.level:
        return node.module or ""
    package = current.split(".") if current in packages else current.split(".")[:-1]
    if node.level > 1:
        package = package[:-(node.level - 1)]
    return ".".join((*package, *((node.module or "").split(".") if node.module else ())))


def _edges(module: str, tree: ast.AST, modules: dict[str, Path],
           packages: set[str]) -> set[str]:
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = _import_target(module, node, packages)
            names = [base, *(f"{base}.{alias.name}" for alias in node.names)]
        else:
            continue
        for name in names:
            parts = name.split(".")
            found.update(candidate for index in range(1, len(parts) + 1)
                         if (candidate := ".".join(parts[:index])) in modules)
    if module.startswith("agents.") and module.endswith(".main"):
        sibling = f"{module.rsplit('.', 1)[0]}.strategy"
        if sibling in modules:
            found.add(sibling)
    return found


def _referenced_functions(trees, reachable, definitions, packages):
    referenced = set()
    exports = {}
    for module, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                base = _import_target(module, node, packages)
                for alias in node.names:
                    exports[(module, alias.asname or alias.name)] = (base, alias.name)

    def resolve(symbol):
        seen = set()
        while symbol in exports and symbol not in seen:
            seen.add(symbol)
            symbol = exports[symbol]
        return symbol

    for module in trees:
        tree = trees[module]
        imports = {}
        imported_modules = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    local = alias.asname or alias.name.split(".")[0]
                    imported_modules[local] = alias.name if alias.asname else local
            elif isinstance(node, ast.ImportFrom):
                base = _import_target(module, node, packages)
                for alias in node.names:
                    imports[alias.asname or alias.name] = (base, alias.name)
                    imported = f"{base}.{alias.name}"
                    if imported in trees:
                        imported_modules[alias.asname or alias.name] = imported
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                local = (module, node.id)
                if local in definitions:
                    referenced.add(local)
                imported = resolve(imports.get(node.id))
                if imported in definitions:
                    referenced.add(imported)
            elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
                parts = []
                value = node
                while isinstance(value, ast.Attribute):
                    parts.append(value.attr)
                    value = value.value
                if isinstance(value, ast.Name) and parts:
                    target = imported_modules.get(value.id)
                    if target is not None:
                        candidate = (".".join((target, *reversed(parts[1:]))), parts[0])
                        candidate = resolve(candidate)
                        if candidate in definitions:
                            referenced.add(candidate)
    return referenced


def analyze(root: Path) -> ReachabilityReport:
    modules = _shipped_modules(Path(root))
    trees = {name: ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
             for name, path in modules.items()}
    tools = [
        *sorted((Path(root) / "tools" / "sim").glob("*.py")),
        *sorted((Path(root) / "tools" / "submit").glob("*.py")),
        *sorted((Path(root) / "tools" / "train" / "corpus").glob("*.py")),
        *sorted((Path(root) / "tools" / "train" / "blunder").glob("*.py")),
        Path(root) / "tools" / "train" / "ledger_corpus.py",
        Path(root) / "tools" / "train" / "ledger_fit.py",
        Path(root) / "tools" / "train" / "ledger_readiness.py",
    ]
    trees.update({
        f"approved.{index}": ast.parse(
            path.read_text(encoding="utf-8-sig"), filename=str(path))
        for index, path in enumerate(tools) if path.is_file()
    })
    packages = {name for name, path in modules.items() if path.name == "__init__.py"}
    dynamic = {name for name in modules if name.startswith(DYNAMIC_CARD_PACKAGES)}
    roots = {name for name in modules
             if name.startswith("agents.") and name.endswith(".main")}
    roots.add("cg.game")
    roots.update(PUBLIC_API_MODULES)
    reachable = set(roots)
    pending = list(roots)
    while pending:
        module = pending.pop()
        for target in _edges(module, trees[module], modules, packages) - reachable:
            reachable.add(target)
            pending.append(target)
    reachable.update(dynamic)
    definitions = {
        (module, node.name): node
        for module in reachable
        for node in trees[module].body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    referenced = _referenced_functions(trees, reachable, definitions, packages)
    for module in roots:
        referenced.update((module, node.name) for node in trees[module].body
                          if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                          and not node.name.startswith("_"))
    functions = tuple(sorted(
        f"{module}.{name}:{node.lineno}"
        for (module, name), node in definitions.items()
        if (module, name) not in referenced
        and f"{module}.{name}" not in EXTERNAL_FUNCTIONS
    ))
    return ReachabilityReport(
        tuple(sorted(set(modules) - reachable)), functions, tuple(sorted(dynamic)))


__all__ = ("DYNAMIC_CARD_PACKAGES", "EXTERNAL_FUNCTIONS", "OFFLINE_MODULES",
           "ReachabilityReport", "analyze")
