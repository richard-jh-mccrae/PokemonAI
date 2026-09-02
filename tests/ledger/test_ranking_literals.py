import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RANKING_MODULES = tuple(path for path in sorted(
    (ROOT / "src" / "common" / "ledger").glob("*.py"))
    if path.name != "sensitivity.py") + (
        ROOT / "src" / "common" / "decision" / "coordinator.py",)

APPROVED_DECLARATIONS = {
    "src/common/decision/coordinator.py": {"LOTTERY_DIGEST_BYTES"},
    "src/common/ledger/baseline.py": {"SCHEMA_VERSION"},
    "src/common/ledger/activation.py": {"DAMAGE_UNIT_HP", "SYMMETRIC_STADIUM_FIT"},
    "src/common/ledger/chance.py": {
        "DIRECT_REFRESH_CARD_GAIN", "DIRECT_REFRESH_MAX_RETAINED",
        "MIN_ADAPTIVE_SAMPLES", "PLAYER_COUNT", "SAMPLE_SEED_BITS",
        "SAMPLES_PER_OUTCOME", "SEED_DIGEST_BYTES"},
    "src/common/ledger/capabilities.py": {
        "ACTIVE_AREA", "ANCIENT_POKEMON_IDS", "ATTACHED_ENERGY_MATERIAL_UNIT",
        "ATTACK_EVENT_KIND", "BOUNCE_ENERGY_HAND_UNIT", "CARD_PLAY_EVENT_KIND",
        "CLAUSE_COST_UNITS",
        "COMEBACK_PRIZE_THRESHOLD", "COMPLETION_EXPONENT",
        "DAMAGE_COUNTER_HP", "DAMAGE_PROTECTION_THRESHOLD_HP", "DAMAGE_TRANSFER_SIDES",
        "DAMAGE_RANGE_BOUND_COUNT",
        "DEPENDENCY_REACH_DEPTH",
        "FUTURE_EVOLUTION_DEPTH",
        "DAMAGE_UNIT_HP", "DEFAULT_PRIZE_COUNT", "DISCARD_AREA", "EVOLUTION_HOP_DISCOUNT",
        "CONFUSION_SELF_DAMAGE",
        "FUTURE_HEAL_EXPOSURE", "HEAL_TARGET_HP", "ITEM_LOCK_BASE_UNITS", "ITEM_LOCK_HAND_UNIT",
        "COIN_HEADS_PROBABILITY", "ENERGY_COUNT_THRESHOLD", "IN_PLAY_AREAS",
        "LOW_REMAINING_HP_THRESHOLD", "MIN_SELF_DAMAGE_COUNTERS",
        "KNOCKOUT_EVENT_KINDS", "RESISTANCE_REDUCTION", "RIDER_COST_UNITS",
        "SWITCH_EVENT_KIND", "TEAM_ROCKET_ENERGY_CARD_ID", "TERMINAL_LOSS_UNITS",
        "WEAKNESS_MULTIPLIER", "STAGE_RANK",
    },
    "src/common/ledger/configuration.py": {
        "ATTACHMENT_TARGET_SCHEMA_VERSION",
        "COMBAT_REALIZATION_SCHEMA_VERSION", "CONFIGURATION_ID_DIGEST_BYTES",
        "DAMAGED_ACTIVE_THREAT_SCHEMA_VERSION",
        "DUPLICATE_BODY_SCHEMA_VERSION",
        "EVOLUTION_TARGET_SCHEMA_VERSION",
        "GUST_SPEND_SCHEMA_VERSION",
        "HAND_LINE_SCHEMA_VERSION", "LEGACY_BODY_DEVELOPMENT_WEIGHT",
        "LEGACY_COMBAT_SCHEMA_VERSION", "REALIZED_KO_RETIREMENT_SCHEMA_VERSION"},
    "src/common/ledger/decider.py": {"PROVIDER_ID_DIGEST_BYTES"},
    "src/common/ledger/decision.py": {"EVALUATOR_ID_DIGEST_BYTES"},
    "src/common/ledger/evaluate.py": {
        "BENCH_REALIZATION_DISCOUNT", "BURN_STATUS_SEVERITY",
        "BODY_DEVELOPMENT_SCALE", "DRAW_RESULT_CODE",
        "HAND_LINE_CHILD_INDEX", "HAND_LINE_PARENT_INDEX",
        "POISON_STATUS_SEVERITY"},
    "src/common/ledger/features.py": {
        "CATALOG_ID_DIGEST_BYTES", "FEATURE_CATALOG", "_BELIEF_DEFAULTS",
        "_KIND_DEFAULTS", "CLAUSE_PARAMETER_QUALIFIERS",
        "OPTION_DEFAULTS", "OPTION_DEPTH_DEFAULTS",
        "_PLACEMENT_FACTORS", "_SCALAR_DEFAULTS",
    },
    "src/common/ledger/preview.py": {
        "BODY_SOURCE_PREFIX_GROUP", "CONSUMED_OPPORTUNITY_INDEX",
        "EVOLUTION_SOURCE_CARD_GROUP", "FORCED_FOOTPRINT_SLOT",
        "LOTTERY_DIGEST_BYTES", "OPPORTUNITY_SOURCE_CARD_GROUP",
        "OPPORTUNITY_SOURCE_KIND_GROUP", "PRIZE_AREA"},
    "src/common/ledger/prizes.py": {"PRIZE_ROUTE_CACHE_SIZE"},
    "src/common/ledger/portfolio.py": {"HAND_POKEMON_REALIZATION_DISCOUNT"},
    "src/common/ledger/portfolio_solver.py": {
        "DEFAULT_TURN_PORTFOLIO_MEMO_ENTRIES", "DOMINANCE_FRONTIER_ENTRIES",
        "EXECUTION_GUARD_CHECK_INTERVAL"},
    "src/common/ledger/policy.py": {"POLICY_CONFIG_ID_DIGEST_BYTES"},
    "src/common/ledger/readiness.py": {"REPORT_SCHEMA_VERSION"},
    "src/common/ledger/search.py": {
        "LOTTERY_DIGEST_BYTES", "MIN_COMPARATIVE_RETREAT_ATTACHMENTS"},
    "src/common/ledger/seam.py": {"version"},
    "src/common/ledger/training.py": {
        "BOUND_MULTIPLIER", "CALIBRATION_EPOCHS", "DEFAULT_EPOCHS", "DEFAULT_L2",
        "DEFAULT_LEARNING_RATE", "FIT_DIGEST_BYTES", "GROUP_BUCKETS", "TRAIN_BUCKETS",
        "VALIDATION_BUCKETS",
    },
    "src/common/ledger/worth.py": {
        "BACKUP_BODY_CAPACITY", "CONTENT_ID_DIGEST_BYTES", "MODEL_ID_DIGEST_BYTES",
        "FUTURE_TURN_DISCOUNT", "MULTI_PROVISION_UNITS", "POKEMON_COPY_CAPACITY",
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
