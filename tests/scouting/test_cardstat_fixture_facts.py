import ast
import csv
from dataclasses import fields
from pathlib import Path
from types import SimpleNamespace

from common.scouting.provider import (
    CardStat,
    _BASIC_ENERGY,
    _ITEM,
    _SPECIAL_ENERGY,
    _STADIUM,
    _SUPPORTER,
    _TOOL,
    _parse_tool_hp_bonus,
    _parse_tool_retreat_reduction,
)


ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "data" / "EN_Card_Data.csv"
TESTS_ROOT = ROOT / "tests"

TYPE_CODES = {
    "{C}": 0,
    "{G}": 1,
    "{R}": 2,
    "{W}": 3,
    "{L}": 4,
    "{P}": 5,
    "{F}": 6,
    "{D}": 7,
    "{M}": 8,
    "{N}": 9,
    "竜": 9,
}
CARD_TYPES = {
    "Item": _ITEM,
    "Pokémon Tool": _TOOL,
    "Supporter": _SUPPORTER,
    "Stadium": _STADIUM,
    "Basic Energy": _BASIC_ENERGY,
    "Special Energy": _SPECIAL_ENERGY,
}
COVERED_FIELDS = {
    "name",
    "hp",
    "energyType",
    "weakness",
    "resistance",
    "retreatCost",
    "evolvesFrom",
    "ex",
    "megaEx",
    "aceSpec",
    "tera",
    "stage",
    "cardType",
    "maxDamage",
    "minAttackCost",
    "maxDamageCost",
    "minCostDamage",
    "hpBonus",
    "retreatReduction",
}
UNCOVERED_FIELDS = sorted({f.name for f in fields(CardStat)} - COVERED_FIELDS - {"cardId", "synthetic"})
SYNTHETIC_SOURCE_NAME_SITES = {
    # These synthetic rows deliberately keep a source card name because the test exercises topology
    # or card-effect lookup keyed by that name. The row is still arbitrary: at least one other
    # declared source-covered fact differs from the CSV.
    ("tests/agents/test_mega_starmie_triggers.py", 42, 665),
    ("tests/scouting/test_retreat_cost_grants.py", 184, 1157),
    ("tests/scouting/test_retreat_cost_grants.py", 186, 184),
    ("tests/scouting/test_retreat_cost_grants.py", 188, 170),
    ("tests/scouting/test_scouting_provider.py", 97, 678),
    ("tests/scouting/test_tool_holder_facts.py", 459, 1173),
    ("tests/scouting/test_tool_holder_facts.py", 470, 1173),
    ("tests/scouting/test_tool_holder_facts.py", 607, 1166),
    ("tests/scouting/test_tool_holder_facts.py", 608, 1174),
    ("tests/sim/test_diff_attack_audit.py", 19, 1031),
    ("tests/sim/test_diff_attack_audit.py", 20, 345),
    ("tests/strategy/test_attach_decider.py", 70, 65),
    ("tests/strategy/test_board_cards.py", 41, 677),
    ("tests/strategy/test_combat.py", 275, 333),
    ("tests/strategy/test_combat.py", 277, 678),
    ("tests/strategy/test_damage_oracle.py", 18, 1031),
    ("tests/strategy/test_damage_oracle.py", 20, 345),
    ("tests/strategy/test_damage_oracle.py", 127, 330),
    ("tests/strategy/test_damage_oracle.py", 128, 83),
    ("tests/strategy/test_damage_oracle.py", 130, 158),
    ("tests/strategy/test_damage_oracle.py", 131, 383),
    ("tests/strategy/test_damage_oracle.py", 160, 158),
    ("tests/strategy/test_damage_oracle.py", 168, 383),
    ("tests/strategy/test_damage_oracle.py", 254, 723),
    ("tests/strategy/test_discard_keep_rows.py", 43, 666),
    ("tests/strategy/test_discard_recur_fuel.py", 27, 677),
    ("tests/strategy/test_discard_selection.py", 29, 666),
    ("tests/strategy/test_empty_bench_rung.py", 139, 677),
    ("tests/strategy/test_empty_bench_rung.py", 193, 677),
    ("tests/strategy/test_gust_target_slot_resolver.py", 55, 677),
    ("tests/strategy/test_incoming_curve.py", 35, 677),
    ("tests/strategy/test_lethal.py", 737, 345),
    ("tests/strategy/test_needs_deny_resolver.py", 87, 677),
    ("tests/strategy/test_opponent_deck_accel.py", 38, 647),
    ("tests/strategy/test_opponent_deck_accel.py", 40, 648),
    ("tests/strategy/test_posture_cardfacts.py", 37, 743),
    ("tests/strategy/test_predicted_loss_rung.py", 38, 677),
    ("tests/strategy/test_promote_preserve_wincon.py", 58, 190),
    ("tests/strategy/test_reachable_attach.py", 34, 121),
    ("tests/strategy/test_reachable_attach.py", 140, 121),
    ("tests/strategy/test_reachable_attach.py", 264, 163),
    ("tests/strategy/test_reachable_attach.py", 277, 163),
    ("tests/strategy/test_reachable_attach.py", 299, 677),
    ("tests/strategy/test_reachable_attach.py", 330, 121),
    ("tests/strategy/test_reachable_attach.py", 347, 163),
    ("tests/strategy/test_reachable_attach.py", 363, 163),
    ("tests/strategy/test_reachable_attach.py", 572, 678),
    ("tests/strategy/test_reachable_attach.py", 574, 677),
    ("tests/strategy/test_reachable_incoming.py", 29, 677),
    ("tests/strategy/test_reachable_incoming.py", 78, 677),
    ("tests/strategy/test_reachable_incoming.py", 105, 1031),
    ("tests/strategy/test_reachable_incoming.py", 122, 677),
    ("tests/strategy/test_reachable_incoming.py", 166, 120),
    ("tests/strategy/test_reachable_incoming.py", 168, 121),
    ("tests/strategy/test_snipe_threat_rank.py", 109, 64),
    ("tests/strategy/test_snipe_threat_rank.py", 147, 743),
    ("tests/strategy/test_state_model.py", 62, 121),
    ("tests/strategy/test_state_model.py", 66, 112),
    ("tests/strategy/test_state_model.py", 67, 677),
    ("tests/strategy/test_state_model.py", 69, 678),
    ("tests/strategy/test_state_model.py", 73, 676),
    ("tests/strategy/test_state_model.py", 76, 675),
    ("tests/strategy/test_state_model.py", 79, 216),
    ("tests/strategy/test_state_model.py", 82, 215),
    ("tests/strategy/test_state_model.py", 83, 217),
    ("tests/strategy/test_state_value.py", 148, 121),
    ("tests/strategy/test_state_value.py", 152, 112),
    ("tests/strategy/test_state_value.py", 157, 677),
    ("tests/strategy/test_state_value.py", 160, 678),
    ("tests/strategy/test_state_value.py", 165, 1031),
    ("tests/strategy/test_state_value.py", 169, 46),
    ("tests/strategy/test_state_value.py", 173, 345),
    ("tests/strategy/test_state_value.py", 177, 1008),
    ("tests/strategy/test_state_value.py", 182, 743),
    ("tests/strategy/test_state_value.py", 187, 163),
    ("tests/strategy/test_state_value.py", 199, 1030),
    ("tests/strategy/test_state_value.py", 202, 119),
    ("tests/strategy/test_state_value.py", 205, 120),
    ("tests/strategy/test_state_value.py", 217, 676),
    ("tests/strategy/test_state_value.py", 220, 675),
    ("tests/strategy/test_state_value.py", 223, 276),
    ("tests/strategy/test_state_value.py", 226, 43),
    ("tests/strategy/test_state_value.py", 241, 1031),
    ("tests/strategy/test_turns_to_afford.py", 45, 677),
    ("tests/strategy/test_turns_to_afford.py", 123, 190),
    ("tests/strategy/test_turns_to_afford.py", 162, 677),
}


def _norm_text(value):
    if value is None:
        return None
    text = str(value).strip()
    return None if not text or text.lower() == "n/a" else text


def _norm_int(value):
    text = _norm_text(value)
    if text is None:
        return None
    return int(text)


def _energy_type(value):
    text = _norm_text(value)
    if text is None:
        return None
    return TYPE_CODES.get(text[:3])


def _cost_count(value):
    text = _norm_text(value)
    return None if text is None else text.count("{") + text.count("●")


def _damage(value):
    text = _norm_text(value)
    if text is None:
        return 0
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits) if digits else 0


def _literal(node, constants):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        value = _literal(node.operand, constants)
        return -value if isinstance(value, int) else None
    return None


def _constants(tree):
    values = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target, value = node.targets[0], node.value
        if isinstance(target, ast.Name):
            values[target.id] = _literal(value, values)
        elif isinstance(target, ast.Tuple) and isinstance(value, ast.Tuple):
            for lhs, rhs in zip(target.elts, value.elts):
                if isinstance(lhs, ast.Name):
                    values[lhs.id] = _literal(rhs, values)
    return values


def _csv_truth(*, hp_shift=0):
    by_id = {}
    rows_by_id = {}
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            cid_text = _norm_text(row.get("Card ID"))
            if cid_text is None:
                continue
            cid = int(cid_text)
            rows_by_id.setdefault(cid, []).append(row)
            by_id.setdefault(cid, row)
    truth = {}
    for cid, first in by_id.items():
        rows = rows_by_id[cid]
        damages = [_damage(row.get("Damage")) for row in rows]
        costs = [_cost_count(row.get("Cost")) for row in rows]
        known_costs = [cost for cost in costs if cost is not None]
        max_damage = max(damages, default=0)
        min_cost = min(known_costs) if known_costs else None
        min_cost_damage = max((damage for damage, cost in zip(damages, costs) if cost == min_cost),
                              default=0) if min_cost is not None else 0
        max_damage_costs = [cost for damage, cost in zip(damages, costs)
                            if cost is not None and damage == max_damage]
        fake_card = SimpleNamespace(
            name=_norm_text(first.get("Card Name")) or "",
            cardType=CARD_TYPES.get(_norm_text(first.get("Stage (Pokémon)/Type (Energy and Trainer)"))),
            skills=[_norm_text(row.get("Effect Explanation")) or "" for row in rows],
        )
        truth[cid] = {
            "name": _norm_text(first.get("Card Name")) or "",
            "hp": None if _norm_text(first.get("HP")) is None else _norm_int(first.get("HP")) + hp_shift,
            "energyType": _energy_type(first.get("Type")),
            "weakness": _energy_type(first.get("Weakness")),
            "resistance": _energy_type(first.get("Resistance (Type)")),
            "retreatCost": _norm_int(first.get("Retreat")) if _norm_text(first.get("Retreat")) else None,
            "evolvesFrom": _norm_text(first.get("Previous stage")),
            "stage": _norm_text(first.get("Stage (Pokémon)/Type (Energy and Trainer)")),
            "ex": "Pokémon ex" in (first.get("Rule") or ""),
            "megaEx": "Mega Pokémon ex" in (first.get("Rule") or ""),
            "aceSpec": "ACE SPEC" in (first.get("Rule") or ""),
            "tera": (_norm_text(first.get("Category")) or "").startswith("Tera("),
            "cardType": fake_card.cardType,
            "maxDamage": max_damage,
            "minAttackCost": min_cost,
            "maxDamageCost": min(max_damage_costs) if max_damage_costs else None,
            "minCostDamage": min_cost_damage,
            "hpBonus": _parse_tool_hp_bonus(fake_card),
            "retreatReduction": _parse_tool_retreat_reduction(fake_card),
        }
    return truth


def _cardstat_calls():
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = _constants(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or getattr(node.func, "id", None) != "CardStat":
                continue
            kwargs = {kw.arg: _literal(kw.value, constants) for kw in node.keywords if kw.arg}
            cid = _literal(node.args[0], constants) if node.args else None
            if cid is None and "cardId" in kwargs:
                cid = kwargs["cardId"]
            if isinstance(cid, int):
                yield path, node.lineno, cid, kwargs


def _audit(*, hp_shift=0):
    truth = _csv_truth(hp_shift=hp_shift)
    failures = []
    for path, line, cid, kwargs in _cardstat_calls():
        expected = truth.get(cid)
        if expected is None:
            continue
        if kwargs.get("synthetic") is True:
            site = (path.relative_to(ROOT).as_posix(), line, cid)
            if kwargs.get("name") == expected["name"] and site not in SYNTHETIC_SOURCE_NAME_SITES:
                failures.append(f"{path.relative_to(ROOT)}:{line} id={cid} synthetic row keeps "
                                f"real name {expected['name']!r}; use a non-pool name or record "
                                "why the source name is required")
            continue
        declared = {field: value for field, value in kwargs.items() if field in COVERED_FIELDS}
        if not declared:
            continue
        actual_name = declared.get("name")
        if actual_name is not None and actual_name != expected["name"]:
            failures.append(f"{path.relative_to(ROOT)}:{line} id={cid} name={actual_name!r} "
                            f"CSV={expected['name']!r}; mark synthetic=True or use source facts")
            continue
        for field, value in declared.items():
            if field == "name":
                continue
            if field == "hp" and value == 0 and expected[field] is None:
                continue
            if value != expected[field]:
                failures.append(f"{path.relative_to(ROOT)}:{line} id={cid} {field}={value!r} "
                                f"CSV={expected[field]!r}; mark synthetic=True or use source facts")
    return failures


def test_cardstat_fixture_source_claims_match_card_data():
    assert _audit() == []


def test_source_named_synthetic_site_ledger_matches_live_rows():
    live = set()
    truth = _csv_truth()
    for path, line, cid, kwargs in _cardstat_calls():
        expected = truth.get(cid)
        if (expected is not None and kwargs.get("synthetic") is True
                and kwargs.get("name") == expected["name"]):
            live.add((path.relative_to(ROOT).as_posix(), line, cid))
    assert live == SYNTHETIC_SOURCE_NAME_SITES


def test_cardstat_fixture_audit_has_positive_control():
    shifted = _audit(hp_shift=7)
    assert len(shifted) >= 100


def test_cardstat_fixture_fact_coverage_is_explicit():
    assert COVERED_FIELDS == {
        "name",
        "hp",
        "energyType",
        "weakness",
        "resistance",
        "retreatCost",
        "evolvesFrom",
        "ex",
        "megaEx",
        "aceSpec",
        "tera",
        "stage",
        "cardType",
        "maxDamage",
        "minAttackCost",
        "maxDamageCost",
        "minCostDamage",
        "hpBonus",
        "retreatReduction",
    }
    assert UNCOVERED_FIELDS == [
        "abilityEnergyTypes",
        "attackCostReduction",
        "attacks",
        "benchSnipeDamage",
        "damageBoost",
        "damageBoostType",
        "damageBoostVsEx",
        "damageReduction",
        "damageReductionTypes",
        "handSizeDamage",
        "hasAbility",
        "holderNameFamily",
        "holderNoRuleBox",
        "preventsDamageAtLeast",
        "preventsDamageFrom",
        "recoil",
        "retreatFreeAtHp",
        "retreatFreeGrant",
        "stage2",
    ]
