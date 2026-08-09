import ast
import csv
from collections import Counter
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
    stage_from_card,
)


ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "data" / "EN_Card_Data.csv"
TESTS_ROOT = ROOT / "tests"

#: The one CSV column carrying BOTH the Pokémon stage and the Trainer/Energy type, read twice
#: below — so the two facts are drawn from one source and cannot disagree.
STAGE_COLUMN = "Stage (Pokémon)/Type (Energy and Trainer)"

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
#: The Pokémon half of `STAGE_COLUMN` in the CANONICAL vocabulary production emits: the printed
#: label is what the audit MAPS, since `_build_cache` can never produce `stage="Basic Pokémon"`.
STAGE_LABELS = {
    "Basic Pokémon": "basic",
    "Stage 1 Pokémon": "stage1",
    "Stage 2 Pokémon": "stage2",
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
#: Fixture rows deliberately keeping a source card NAME while declaring `synthetic=True`. Keyed
#: `(path, enclosing def, cardId)` — POSITION-INDEPENDENT, and `(path, cardId)` alone collides.
SYNTHETIC_SOURCE_NAME_SITES = {
    ("tests/agents/test_mega_starmie_triggers.py", "<module>", 665),
    ("tests/scouting/test_retreat_cost_grants.py", "_pilot", 170),
    ("tests/scouting/test_retreat_cost_grants.py", "_pilot", 184),
    ("tests/scouting/test_retreat_cost_grants.py", "_pilot", 1157),
    ("tests/scouting/test_scouting_provider.py", "test_forward_max_damage_folds_max_over_same_name_printings", 678),
    ("tests/scouting/test_tool_holder_facts.py", "_gem_pilot", 1166),
    ("tests/scouting/test_tool_holder_facts.py", "_gem_pilot", 1174),
    ("tests/sim/test_diff_attack_audit.py", "<module>", 345),
    ("tests/sim/test_diff_attack_audit.py", "<module>", 1031),
    ("tests/strategy/test_attach_decider.py", "_stats", 65),
    ("tests/strategy/test_board_cards.py", "<module>", 677),
    ("tests/strategy/test_combat.py", "test_active_doomed_sees_the_forward_evolution_threat", 333),
    ("tests/strategy/test_combat.py", "test_active_doomed_sees_the_forward_evolution_threat", 678),
    ("tests/strategy/test_damage_oracle.py", "<module>", 83),
    ("tests/strategy/test_damage_oracle.py", "<module>", 158),
    ("tests/strategy/test_damage_oracle.py", "<module>", 330),
    ("tests/strategy/test_damage_oracle.py", "<module>", 345),
    ("tests/strategy/test_damage_oracle.py", "<module>", 383),
    ("tests/strategy/test_damage_oracle.py", "<module>", 1031),
    ("tests/strategy/test_damage_oracle.py", "test_flat_reduction_applies_after_weakness_and_is_pierced_by_ignores_effects", 383),
    ("tests/strategy/test_damage_oracle.py", "test_hidden_scaler_feeds_the_incoming_ceiling", 723),
    ("tests/strategy/test_damage_oracle.py", "test_threshold_prevention_zeroes_only_big_hits", 158),
    ("tests/strategy/test_discard_keep_rows.py", "_setup", 666),
    ("tests/strategy/test_discard_recur_fuel.py", "_combat", 677),
    ("tests/strategy/test_discard_selection.py", "_setup", 666),
    ("tests/strategy/test_empty_bench_rung.py", "test_the_guard_covers_the_PLANNER_branch_too", 677),
    ("tests/strategy/test_empty_bench_rung.py", "test_when_the_guard_overrides_the_planner_no_line_is_reported", 677),
    ("tests/strategy/test_gust_target_slot_resolver.py", "_setup", 677),
    ("tests/strategy/test_incoming_curve.py", "_combat", 677),
    ("tests/strategy/test_lethal.py", "test_ignore_effects_attack_bypasses_a_prevent_damage_ability_for_the_win", 345),
    ("tests/strategy/test_needs_deny_resolver.py", "_setup", 677),
    ("tests/strategy/test_opponent_deck_accel.py", "_combat", 647),
    ("tests/strategy/test_opponent_deck_accel.py", "_combat", 648),
    ("tests/strategy/test_posture_cardfacts.py", "_stats", 743),
    ("tests/strategy/test_promote_preserve_wincon.py", "_pilot", 190),
    ("tests/strategy/test_reachable_attach.py", "<module>", 121),
    ("tests/strategy/test_reachable_attach.py", "_special_combat", 677),
    ("tests/strategy/test_reachable_attach.py", "_special_combat", 678),
    ("tests/strategy/test_reachable_attach.py", "test_a_type_locked_accel_cannot_eat_a_colour_the_discard_lacks", 163),
    ("tests/strategy/test_reachable_attach.py", "test_crispin_units_must_take_distinct_types", 121),
    ("tests/strategy/test_reachable_attach.py", "test_rosa_never_funds_a_non_stage_2_body", 677),
    ("tests/strategy/test_reachable_attach.py", "test_the_discard_cap_binds_by_COLOUR_not_merely_by_count", 121),
    ("tests/strategy/test_reachable_attach.py", "test_two_discard_accelerators_share_one_pile", 163),
    ("tests/strategy/test_reachable_attach.py", "test_wondrous_patch_funds_a_benched_psychic_body", 163),
    ("tests/strategy/test_reachable_attach.py", "test_wondrous_patch_needs_the_energy_visible_in_the_discard", 163),
    ("tests/strategy/test_reachable_incoming.py", "_bench_combat", 120),
    ("tests/strategy/test_reachable_incoming.py", "_bench_combat", 121),
    ("tests/strategy/test_reachable_incoming.py", "_combat", 677),
    ("tests/strategy/test_reachable_incoming.py", "test_charged_burst_does_not_apply_to_a_basic_form", 677),
    ("tests/strategy/test_reachable_incoming.py", "test_charged_colorless_burst_pays_a_colorless_nuke_but_never_a_typed_cost", 1031),
    ("tests/strategy/test_reachable_incoming.py", "test_old_style_current_form_only_when_no_forward_exists", 677),
    ("tests/strategy/test_snipe_threat_rank.py", "test_forward_card_ids_collects_the_whole_descendant_line", 743),
    ("tests/strategy/test_snipe_threat_rank.py", "test_the_rank_generalises_to_a_scaler_no_function_tag_covers", 64),
    ("tests/strategy/test_state_model.py", "<module>", 112),
    ("tests/strategy/test_state_model.py", "<module>", 121),
    ("tests/strategy/test_state_model.py", "<module>", 215),
    ("tests/strategy/test_state_model.py", "<module>", 216),
    ("tests/strategy/test_state_model.py", "<module>", 217),
    ("tests/strategy/test_state_model.py", "<module>", 675),
    ("tests/strategy/test_state_model.py", "<module>", 676),
    ("tests/strategy/test_state_model.py", "<module>", 677),
    ("tests/strategy/test_state_model.py", "<module>", 678),
    ("tests/strategy/test_state_value.py", "<module>", 43),
    ("tests/strategy/test_state_value.py", "<module>", 46),
    ("tests/strategy/test_state_value.py", "<module>", 112),
    ("tests/strategy/test_state_value.py", "<module>", 119),
    ("tests/strategy/test_state_value.py", "<module>", 120),
    ("tests/strategy/test_state_value.py", "<module>", 121),
    ("tests/strategy/test_state_value.py", "<module>", 163),
    ("tests/strategy/test_state_value.py", "<module>", 276),
    ("tests/strategy/test_state_value.py", "<module>", 345),
    ("tests/strategy/test_state_value.py", "<module>", 675),
    ("tests/strategy/test_state_value.py", "<module>", 676),
    ("tests/strategy/test_state_value.py", "<module>", 677),
    ("tests/strategy/test_state_value.py", "<module>", 678),
    ("tests/strategy/test_state_value.py", "<module>", 743),
    ("tests/strategy/test_state_value.py", "<module>", 1008),
    ("tests/strategy/test_state_value.py", "<module>", 1030),
    ("tests/strategy/test_state_value.py", "<module>", 1031),
    ("tests/strategy/test_turns_to_afford.py", "_combat", 677),
    ("tests/strategy/test_turns_to_afford.py", "_recur_model", 190),
    ("tests/strategy/test_turns_to_afford.py", "test_the_clock_refuses_an_on_attack_bench_only_reload", 677),
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


def _stage_flags(stage_text, effect_texts):
    """The engine's three stage booleans, read off the CSV so the audit's ground truth stays
    INDEPENDENT. The Fossils print as `Item` yet are Basic, which the effect TEXT is read for."""
    canonical = STAGE_LABELS.get(stage_text)
    if canonical is None and any("as if it were" in t and "Basic" in t for t in effect_texts):
        canonical = "basic"
    return {"basic": canonical == "basic",
            "stage1": canonical == "stage1",
            "stage2": canonical == "stage2"}


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
        effect_texts = [_norm_text(row.get("Effect Explanation")) or "" for row in rows]
        fake_card = SimpleNamespace(
            name=_norm_text(first.get("Card Name")) or "",
            cardType=CARD_TYPES.get(_norm_text(first.get(STAGE_COLUMN))),
            # `.text`-carrying, because `card_text._skill_texts` reads `s.text`/`s["text"]` and skips
            # a bare string — as plain texts these derived BOTH Tool legs as 0 for EVERY Tool.
            skills=[{"text": text} for text in effect_texts],
            **_stage_flags(_norm_text(first.get(STAGE_COLUMN)), effect_texts),
        )
        truth[cid] = {
            "name": _norm_text(first.get("Card Name")) or "",
            "hp": None if _norm_text(first.get("HP")) is None else _norm_int(first.get("HP")) + hp_shift,
            "energyType": _energy_type(first.get("Type")),
            "weakness": _energy_type(first.get("Weakness")),
            "resistance": _energy_type(first.get("Resistance (Type)")),
            "retreatCost": _norm_int(first.get("Retreat")) if _norm_text(first.get("Retreat")) else None,
            "evolvesFrom": _norm_text(first.get("Previous stage")),
            "stage": stage_from_card(fake_card),
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


def _scopes(tree):
    """``{id(CardStat call node) -> dotted enclosing def/class path}``; module scope is
    ``"<module>"``. ``ast.walk`` flattens the tree and loses this, hence the explicit descent."""
    found = {}

    def descend(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                descend(child, prefix + (child.name,))
                continue
            if isinstance(child, ast.Call) and getattr(child.func, "id", None) == "CardStat":
                found[id(child)] = ".".join(prefix) or "<module>"
            descend(child, prefix)

    descend(tree, ())
    return found


def _cardstat_calls():
    """Yield ``(path, line, scope, cardId, kwargs)`` per literal ``CardStat(...)``. ``line`` is for
    HUMANS; ``scope`` is the LEDGER key, because a line number moves whenever anything above does."""
    for path in sorted(TESTS_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        constants = _constants(tree)
        scopes = _scopes(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or getattr(node.func, "id", None) != "CardStat":
                continue
            kwargs = {kw.arg: _literal(kw.value, constants) for kw in node.keywords if kw.arg}
            cid = _literal(node.args[0], constants) if node.args else None
            if cid is None and "cardId" in kwargs:
                cid = kwargs["cardId"]
            if isinstance(cid, int):
                yield path, node.lineno, scopes.get(id(node), "<module>"), cid, kwargs


def _site(path, scope, cid):
    """The ledger key for one fixture row — position-independent by construction."""
    return (path.relative_to(ROOT).as_posix(), scope, cid)


def _source_named_synthetic_rows(truth):
    """``[(site, line)]`` for every synthetic row that keeps its card's real CSV name."""
    rows = []
    for path, line, scope, cid, kwargs in _cardstat_calls():
        expected = truth.get(cid)
        if (expected is not None and kwargs.get("synthetic") is True
                and kwargs.get("name") == expected["name"]):
            rows.append((_site(path, scope, cid), line))
    return rows


def _audit(*, hp_shift=0):
    truth = _csv_truth(hp_shift=hp_shift)
    failures = []
    for path, line, scope, cid, kwargs in _cardstat_calls():
        expected = truth.get(cid)
        if expected is None:
            continue
        if kwargs.get("synthetic") is True:
            site = _site(path, scope, cid)
            if kwargs.get("name") == expected["name"] and site not in SYNTHETIC_SOURCE_NAME_SITES:
                failures.append(f"{path.relative_to(ROOT)}:{line} id={cid} synthetic row keeps "
                                f"real name {expected['name']!r}; use a non-pool name or record "
                                f"why the source name is required (ledger key: {site})")
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
    rows = _source_named_synthetic_rows(_csv_truth())
    assert {site for site, _line in rows} == SYNTHETIC_SOURCE_NAME_SITES


def test_the_ledger_key_identifies_exactly_one_row_each():
    """The ledger is a SET, so two rows sharing a key collapse and a new source-named row could
    hide behind an existing one. `name` adds nothing: a row is here BECAUSE its name matches."""
    rows = _source_named_synthetic_rows(_csv_truth())
    duplicated = sorted(k for k, n in Counter(site for site, _ in rows).items() if n > 1)
    assert duplicated == []
    assert len(rows) == len(SYNTHETIC_SOURCE_NAME_SITES)      # no row lost to set collapse


def test_the_ledger_key_survives_a_line_shift():
    """The property the old line-number key lacked: inserting a line above a listed row must not
    change its identity."""
    path = ROOT / "tests" / "scouting" / "test_tool_holder_facts.py"
    original = path.read_text(encoding="utf-8")
    shifted = "\n" * 5 + original

    def keys_and_lines(text):
        tree = ast.parse(text)
        constants, scopes = _constants(tree), _scopes(tree)
        out = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "CardStat":
                kwargs = {kw.arg: _literal(kw.value, constants) for kw in node.keywords if kw.arg}
                cid = _literal(node.args[0], constants) if node.args else kwargs.get("cardId")
                if isinstance(cid, int):
                    out.append(((scopes.get(id(node), "<module>"), cid), node.lineno))
        return sorted(out)

    before, after = keys_and_lines(original), keys_and_lines(shifted)
    assert [k for k, _ in before] == [k for k, _ in after]        # identity held
    assert [n for _, n in before] != [n for _, n in after]        # …and lines really did move


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
