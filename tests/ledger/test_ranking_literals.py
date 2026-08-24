import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RANKING_MODULES = tuple(sorted(
    (ROOT / "src" / "common" / "ledger").glob("*.py"))) + (
        ROOT / "src" / "common" / "decision" / "coordinator.py",)

APPROVED_DECLARATIONS = {
    "src/common/decision/coordinator.py": {"LOTTERY_DIGEST_BYTES"},
    "src/common/ledger/activation.py": {"DAMAGE_UNIT_HP"},
    "src/common/ledger/chance.py": {"PLAYER_COUNT", "SEED_DIGEST_BYTES"},
    "src/common/ledger/configuration.py": {"CONFIGURATION_ID_DIGEST_BYTES"},
    "src/common/ledger/decider.py": {"PROVIDER_ID_DIGEST_BYTES"},
    "src/common/ledger/decision.py": {"EVALUATOR_ID_DIGEST_BYTES"},
    "src/common/ledger/evaluate.py": {"DRAW_RESULT_CODE"},
    "src/common/ledger/features.py": {
        "CATALOG_ID_DIGEST_BYTES", "FEATURE_CATALOG", "_BELIEF_DEFAULTS",
        "_KIND_DEFAULTS", "_PLACEMENT_FACTORS", "_ROLE_DEFAULTS", "_SCALAR_DEFAULTS",
    },
    "src/common/ledger/preview.py": {"LOTTERY_DIGEST_BYTES"},
    "src/common/ledger/search.py": {"LOTTERY_DIGEST_BYTES"},
    "src/common/ledger/seam.py": {"version"},
    "src/common/ledger/worth.py": {
        "CONTENT_ID_DIGEST_BYTES", "MODEL_ID_DIGEST_BYTES", "MULTI_PROVISION_UNITS",
        "RESISTANCE_REDUCTION", "WEAKNESS_MULTIPLIER", "_DEMAND_PRIORITY",
    },
}


def _assignment_name(node, parents):
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, ast.Assign):
            names = [target.id for target in current.targets if isinstance(target, ast.Name)]
            return names[0] if len(names) == 1 else None
        if isinstance(current, ast.AnnAssign) and isinstance(current.target, ast.Name):
            return current.target.id
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return None
    return None


def _unclassified_literals(path: Path, source: str):
    tree = ast.parse(source)
    parents = {child: parent for parent in ast.walk(tree)
               for child in ast.iter_child_nodes(parent)}
    try:
        relative = path.relative_to(ROOT).as_posix()
    except ValueError:
        relative = ""
    approved = APPROVED_DECLARATIONS.get(relative, set())
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or isinstance(node.value, bool) \
                or not isinstance(node.value, (int, float)) \
                or abs(node.value) in {0, 1}:
            continue
        declaration = _assignment_name(node, parents)
        if declaration not in approved:
            found.append((node.lineno, node.value, declaration))
    return found


def test_ranking_numbers_are_explicit_rules_conversions_or_configuration():
    offenses = {
        path.relative_to(ROOT).as_posix(): _unclassified_literals(
            path, path.read_text(encoding="utf-8"))
        for path in RANKING_MODULES
    }

    assert not {path: rows for path, rows in offenses.items() if rows}


def test_literal_classifier_catches_fractions_and_unapproved_named_thresholds(tmp_path):
    source = tmp_path / "ranking.py"

    assert _unclassified_literals(source, "def rank(value):\n    return value * .25\n") == [
        (2, 0.25, None)]
    assert _unclassified_literals(
        source, "HAND_TARGET = 7\ndef rank(value):\n    return HAND_TARGET - value\n") == [
            (1, 7, "HAND_TARGET")]
