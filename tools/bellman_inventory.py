"""Generate the closed Mega Starmie mechanic inventory used by the Bellman build ledger.

The generator fails on an uncategorised effect operation.  That is the executable "no silent other"
contract: a card-table change must be named before the planner can claim complete coverage.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
DECK = REPO / "src" / "agents" / "mega_starmie" / "deck.csv"
DEFS = REPO / "src" / "cgpy" / "defs"
DEFAULT_OUTPUT = REPO / "docs" / "plans" / "mega-starmie-bellman-inventory.json"

MAIN_KINDS = ("PLAY", "ATTACH", "EVOLVE", "ABILITY", "RETREAT", "ATTACK", "END")
ALLOWANCES = ("supporter", "manual_attach", "retreat", "ability", "attack", "stadium")

OP_FAMILIES = {
    "costHandTrash": "discard_cost",
    "coin": "chance",
    "ifHeads": "chance",
    "trashEnergyEnemy": "denial_target",
    "effectDeckToBenchAndShuffle": "deck_search_bench",
    "effectTrashToHand": "discard_recovery",
    "effectDeckToHandAndShuffle": "deck_search_hand",
    "xLookTopMayTakeThenShuffle": "look_search",
    "xDeckEvolveInPlayAndShuffle": "deck_evolve",
    "effectSwitchEnemy": "opponent_switch",
    "xBothShuffleCoinDraw": "chance_refresh",
    "xDeckTakeSequenceAndShuffle": "sequential_search",
    "xOwnShuffleHandDraw": "self_refresh",
    "xHealMegaBounceEnergy": "heal_bounce",
    "xDeckEnergyAttachDistribute": "energy_distribution",
    "xChooseBenchDamage": "bench_damage_target",
}

CHANCE_OPS = frozenset({"coin", "ifHeads", "xLookTopMayTakeThenShuffle",
                        "xBothShuffleCoinDraw", "xOwnShuffleHandDraw"})
OPPONENT_OPS = frozenset({"trashEnergyEnemy", "effectSwitchEnemy"})
NESTED_CONTEXTS = {
    "discard_cost": ("DISCARD",),
    "denial_target": ("DISCARD_ENERGY",),
    "deck_search_bench": ("TO_BENCH",),
    "discard_recovery": ("TO_HAND",),
    "deck_search_hand": ("TO_HAND",),
    "look_search": ("TO_HAND",),
    "deck_evolve": ("EVOLVES_TO", "EVOLVE"),
    "opponent_switch": ("SWITCH",),
    "sequential_search": ("TO_HAND",),
    "heal_bounce": ("HEAL",),
    "energy_distribution": ("ATTACH_TO", "ATTACH_FROM"),
    "bench_damage_target": ("DAMAGE",),
}

PRIOR_ART = {
    "action_economics": ["common.card_worth", "common.action_cost", "ADR-TEMP-507"],
    "board_value": ["common.state_value", "ADR-0136", "ADR-0137"],
    "combat": ["common.strategy.combat", "common.state_model", "ADR-0137"],
    "engine_transition": ["cgpy.engine", "cgpy.turn", "ADR-0098"],
    "semantic_identity": ["common.state_model.semantic_state_key", "ADR-0138"],
    "causal_demand": ["common.needs", "common.deciders.needs", "ADR-0065", "ADR-0127"],
    "information": ["common.strategy.refresh", "ADR-0095", "ADR-0129", "ADR-0133"],
    "opponent_belief": ["common.scouting", "ADR-0047"],
    "setup": ["common.deciders.opening", "common.sound_rules", "ADR-0079", "ADR-0086"],
    "corpus_rulings": ["train.gates", "data/corrections/reviewed.json", "ADR-0088"],
}


def _load(path: str) -> dict:
    return json.loads((DEFS / path).read_text(encoding="utf-8"))


def generate() -> dict:
    deck = [int(x) for x in DECK.read_text(encoding="utf-8").split()]
    counts = Counter(deck)
    cards = {int(row["cardId"]): row for row in _load("card_data.json")}
    attacks = {int(row["attackId"]): row for row in _load("attack_data.json")}
    generated, overrides = _load("generated_chains.json"), _load("chain_overrides.json")

    rows, operations, uncategorised = [], [], []
    for card_id in sorted(counts):
        card = cards[card_id]
        definition = dict(generated.get(str(card_id)) or {})
        definition.update(overrides.get(str(card_id)) or {})
        card_ops = []
        for clause in definition.get("play") or ():
            op = clause.get("op")
            card_ops.append(op)
        attack_rows = []
        for attack_id in card.get("attacks") or ():
            attack_def = dict(generated.get(f"attack:{attack_id}") or {})
            attack_def.update(overrides.get(f"attack:{attack_id}") or {})
            rider_ops = [clause.get("op") for clause in attack_def.get("rider") or ()]
            card_ops.extend(rider_ops)
            attack_rows.append({
                "attack_id": attack_id,
                "name": attacks[attack_id].get("name"),
                "damage": attacks[attack_id].get("damage", 0),
                "cost": attacks[attack_id].get("energies") or [],
                "riders": rider_ops,
            })
        for op in card_ops:
            if op not in OP_FAMILIES:
                uncategorised.append({"card_id": card_id, "op": op})
            else:
                operations.append({"card_id": card_id, "op": op,
                                   "family": OP_FAMILIES[op]})
        rows.append({
            "card_id": card_id,
            "copies": counts[card_id],
            "name": card.get("name"),
            "card_type": card.get("cardType"),
            "play_operations": [op for op in card_ops if op not in {
                rider for attack in attack_rows for rider in attack["riders"]}],
            "attacks": attack_rows,
            "special": {key: definition[key] for key in
                        ("eotSelfDiscard", "provides", "providesOnEvolution", "tool")
                        if key in definition},
        })
    if uncategorised:
        raise SystemExit(f"uncategorised Mega Starmie operations: {uncategorised}")

    families = sorted({row["family"] for row in operations})
    contexts = sorted({context for family in families for context in NESTED_CONTEXTS.get(family, ())})
    return {
        "schema": 1,
        "deck": "mega_starmie",
        "deck_size": len(deck),
        "unique_cards": len(rows),
        "main_option_kinds": MAIN_KINDS,
        "allowances": ALLOWANCES,
        "cards": rows,
        "effect_operations": operations,
        "effect_families": families,
        "nested_select_contexts": contexts,
        "chance_sources": sorted({row["op"] for row in operations if row["op"] in CHANCE_OPS}),
        "opponent_response_sources": sorted({row["op"] for row in operations
                                             if row["op"] in OPPONENT_OPS}
                                            | {"forced_promotion"}),
        "unmodelled": [],
        "prior_art": PRIOR_ART,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    rendered = json.dumps(generate(), indent=2, ensure_ascii=False) + "\n"
    if args.check:
        if not args.output.exists() or args.output.read_text(encoding="utf-8") != rendered:
            raise SystemExit(f"stale Bellman inventory: run {Path(__file__).name}")
        return 0
    args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
