"""Generate the `src/common/cards/` card modules — one module per card in our decks' lists.

Printed facts come from the engine-twin defs (`src/cgpy/defs/*.json`), tags from the shipped
`card_functions.json`, effect clauses from the audited `card_effects.json` where present, and
the Clause tables below for the rest. Fails loud on any effect left un-encoded.

Usage:
    python tools/build_pokemon_cards.py"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

DECKS = ("dragapult_ex", "mega_lucario", "mega_starmie")
POKEMON_OUT = REPO / "src" / "common" / "cards" / "pokemon_cards"
TRAINER_OUT = REPO / "src" / "common" / "cards" / "trainer_cards"
ENERGY_OUT = REPO / "src" / "common" / "cards" / "energy_cards"

ENERGY_NAME = {0: "COLORLESS", 1: "GRASS", 2: "FIRE", 3: "WATER", 4: "LIGHTNING",
               5: "PSYCHIC", 6: "FIGHTING", 7: "DARKNESS", 8: "METAL", 9: "DRAGON"}
STAGE_NAME = {"basic": "BASIC", "stage1": "STAGE1", "stage2": "STAGE2"}
TRAINER_KIND = {1: "ITEM", 2: "TOOL", 3: "SUPPORTER", 4: "STADIUM"}
ENERGY_KIND = {5: "BASIC_ENERGY", 6: "SPECIAL_ENERGY"}

# Attack-borne effects, hand-encoded from the printed text; amounts are damage points.
ATTACK_CLAUSES: dict[int, tuple[dict, ...]] = {
    141: ({"kind": "confuse", "target": "opp_active"},),
    154: ({"kind": "bench_spread", "amount": 60, "target": "opp_bench"},),
    183: ({"kind": "bench_snipe", "amount": 100, "target": "opp_any"},),
    323: ({"kind": "item_lock", "duration": "opp_next_turn"},),
    423: ({"kind": "switch_self"},),
    965: ({"kind": "accel", "amount": 3, "zone": "deck", "target": "bench_only"},),
    978: ({"kind": "recoil", "amount": 70},),
    980: ({"kind": "requires_bench", "name": "Lunatone"}, {"kind": "ignores_wr"}),
    981: ({"kind": "same_attack_lock", "duration": "next_turn"},),
    982: ({"kind": "energy_recur", "amount": 3, "energy_type": 6, "zone": "discard",
           "target": "bench_only"},),
    983: ({"kind": "same_attack_lock", "duration": "next_turn"},),
    1487: ({"kind": "bench_snipe", "amount": 50, "target": "opp_bench"},),
    1488: ({"kind": "ignores_wr"}, {"kind": "ignores_effects"}),
    1546: ({"kind": "self_return", "dest": "hand"},),
}

# Ability clauses for Pokémon `card_effects.json` does not cover yet.
ABILITY_CLAUSES: dict[int, tuple[dict, ...]] = {
    112: ({"kind": "move_damage", "amount": 30, "condition": "dark_energy_attached",
           "condition_energy_type": 7, "zone": "own_any", "dest": "opp_any", "allowance": "body"},),
    666: ({"kind": "setup_active", "trigger": "setup"},),
}

# Each body's own job, read off its card text — never off its prize count. A deck that wants a
# different job for a body declares it in `src/agents/<deck>/strategy.py` and that wins.
DEFAULT_ROLES: dict[int, tuple[str, ...]] = {
    66: ("draw_engine",),
    112: ("backup_attacker", "counter_mover"),
    119: ("primary_attacker",),
    120: ("primary_attacker", "draw_engine"),
    121: ("primary_attacker", "sniper"),
    140: ("draw_engine",),
    235: ("item_locker",),
    305: ("draw_engine", "retreat_assist"),
    666: ("accel_source", "backup_attacker"),
    673: ("backup_attacker",),
    674: ("backup_attacker", "gust"),
    675: ("draw_engine",),
    676: ("backup_attacker",),
    677: ("primary_attacker",),
    678: ("primary_attacker", "accel_source"),
    1030: ("primary_attacker",),
    1031: ("primary_attacker", "sniper"),
    1071: ("supporter_tutor",),
}

# Bodies whose OWN text names another card to function. Symmetric, and asserted so.
SYNERGY: dict[int, tuple[str, ...]] = {
    675: ("Solrock",),          # Lunar Cycle draws only while Solrock is in play
    676: ("Lunatone",),         # Cosmic Beam does nothing without Lunatone benched
}

# Continuous Tool modifiers `card_effects.json` does not cover; amounts are damage points.
TOOL_CLAUSES: dict[int, tuple[dict, ...]] = {
    1159: ({"kind": "hp_bonus", "amount": 100},),
    1174: ({"kind": "retreat_reduction", "amount": 2},),
}


def _deck_ids() -> set[int]:
    ids: set[int] = set()
    for deck in DECKS:
        text = (REPO / "src" / "agents" / deck / "deck.csv").read_text(encoding="utf-8")
        ids.update(int(line) for line in text.splitlines() if line.strip())
    return ids


def _clause_src(clause: dict, needed: set) -> str:
    parts = [repr(clause["kind"])]
    for key, value in clause.items():
        if key == "kind":
            continue
        if key.endswith("energy_type"):
            needed.add(ENERGY_NAME[int(value)])
            parts.append(f"{key}={ENERGY_NAME[int(value)]}")
        else:
            parts.append(f"{key}={value!r}")
    return f"Clause({', '.join(parts)})"


def _clause_block(clauses, needed: set, indent: str) -> list[str]:
    needed.add("Clause")
    legs = ", ".join(_clause_src(c, needed) for c in clauses)
    return [f"{indent}clauses=({legs},)," if len(clauses) == 1 else
            f"{indent}clauses=({legs}),"]


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _module(card: dict, needed: set, lines: list[str], record: str) -> tuple[str, str]:
    imports = ", ".join(sorted(needed))
    body = (f'"""{card["name"]} (card {card["cardId"]}). Generated by '
            f'tools/build_pokemon_cards.py — edit there and rerun."""\n'
            f"from common.cards.card_facts import ({imports})\n\n"
            f"CARD = {record}(\n" + "\n".join(lines) + "\n)\n")
    return f"{_slug(card['name'])}_{card['cardId']}.py", body


def _emit_pokemon(card: dict, attacks: dict, tags: list, ability_clauses: tuple):
    needed = {"PokemonCard", STAGE_NAME[card["stage"]], ENERGY_NAME[card["energyType"]]}
    lines = [f"    card_id={card['cardId']},",
             f"    name={card['name']!r},",
             f"    hp={card['hp']},",
             f"    energy_type={ENERGY_NAME[card['energyType']]},",
             f"    stage={STAGE_NAME[card['stage']]},"]
    if card.get("evolvesFrom"):
        lines.append(f"    evolves_from={card['evolvesFrom']!r},")
    for flag in ("ex", "megaEx", "tera"):
        if card.get(flag):
            lines.append(f"    {'mega_ex' if flag == 'megaEx' else flag}=True,")
    for side in ("weakness", "resistance"):
        if card.get(side) is not None:
            needed.add(ENERGY_NAME[card[side]])
            lines.append(f"    {side}={ENERGY_NAME[card[side]]},")
    lines.append(f"    retreat_cost={card['retreatCost']},")
    lines.append(f"    tags=frozenset({sorted(tags)!r}),")
    lines.append(f"    default_roles={DEFAULT_ROLES[card['cardId']]!r},")
    if card["cardId"] in SYNERGY:
        lines.append(f"    synergy={SYNERGY[card['cardId']]!r},")
    if card.get("skills"):
        needed.add("Ability")
        lines.append("    abilities=(")
        for skill in card["skills"]:
            lines.append("        Ability(")
            lines.append(f"            name={skill['name'].strip()!r},")
            lines.append(f"            text={skill['text']!r},")
            if ability_clauses:
                lines.extend(_clause_block(ability_clauses, needed, " " * 12))
            lines.append("        ),")
        lines.append("    ),")
    if card.get("attacks"):
        needed.add("Attack")
        lines.append("    attacks=(")
        for attack_id in card["attacks"]:
            attack = attacks[str(attack_id)]
            cost = ", ".join(ENERGY_NAME[e] for e in attack["energies"])
            needed.update(ENERGY_NAME[e] for e in attack["energies"])
            comma = "," if len(attack["energies"]) == 1 else ""
            lines.append("        Attack(")
            lines.append(f"            attack_id={attack_id},")
            lines.append(f"            name={attack['name'].strip()!r},")
            lines.append(f"            cost=({cost}{comma}),")
            lines.append(f"            damage={attack['damage']},")
            if attack.get("text"):
                lines.append(f"            text={attack['text']!r},")
            if attack_id in ATTACK_CLAUSES:
                lines.extend(_clause_block(ATTACK_CLAUSES[attack_id], needed, " " * 12))
            lines.append("        ),")
        lines.append("    ),")
    return _module(card, needed, lines, "PokemonCard")


def _emit_energy(card: dict, tags: list, clauses: tuple):
    kind = ENERGY_KIND[card["cardType"]]
    needed = {"EnergyCard", kind, ENERGY_NAME[card["energyType"]]}
    skills = card.get("skills") or []
    lines = [f"    card_id={card['cardId']},",
             f"    name={card['name']!r},",
             f"    kind={kind},",
             f"    provides={ENERGY_NAME[card['energyType']]},"]
    if skills:
        lines.append(f"    text={skills[0]['text']!r},")
    lines.append(f"    tags=frozenset({sorted(tags)!r}),")
    if clauses:
        lines.extend(_clause_block(clauses, needed, " " * 4))
    return _module(card, needed, lines, "EnergyCard")


def _emit_trainer(card: dict, tags: list, clauses: tuple):
    kind = TRAINER_KIND[card["cardType"]]
    needed = {"TrainerCard", kind}
    skills = card.get("skills") or []
    text = skills[0]["text"] if skills else ""
    lines = [f"    card_id={card['cardId']},",
             f"    name={card['name']!r},",
             f"    kind={kind},",
             f"    text={text!r},"]
    if card.get("aceSpec"):
        lines.append("    ace_spec=True,")
    lines.append(f"    tags=frozenset({sorted(tags)!r}),")
    lines.extend(_clause_block(clauses, needed, " " * 4))
    return _module(card, needed, lines, "TrainerCard")


def main() -> None:
    cards = {c["cardId"]: c for c in
             json.loads((REPO / "src" / "cgpy" / "defs" / "card_data.json").read_text("utf-8"))}
    attacks = {str(a["attackId"]): a for a in
               json.loads((REPO / "src" / "cgpy" / "defs" / "attack_data.json").read_text("utf-8"))}
    functions = json.loads((REPO / "src" / "common" / "card_functions.json").read_text("utf-8"))
    effects = json.loads((REPO / "src" / "common" / "card_effects.json").read_text("utf-8"))
    deck_ids = _deck_ids()
    pokemon = sorted(i for i in deck_ids if cards[i]["cardType"] == 0)
    trainers = sorted(i for i in deck_ids if cards[i]["cardType"] in TRAINER_KIND)
    energies = sorted(i for i in deck_ids if cards[i]["cardType"] in ENERGY_KIND)

    emitted: list[tuple[Path, str, str]] = []
    for card_id in pokemon:
        card = cards[card_id]
        card["stage"] = ("stage2" if card["stage2"] else "stage1" if card["stage1"] else "basic")
        if not DEFAULT_ROLES.get(card_id):
            raise SystemExit(f"pokemon {card_id} ({card['name']}) has no authored default role")
        ability_clauses = ()
        if card.get("skills"):
            source = effects.get(str(card_id)) or ABILITY_CLAUSES.get(card_id)
            if not source:
                raise SystemExit(f"card {card_id} has an Ability with no clause encoding")
            ability_clauses = tuple(source)
        for attack_id in card.get("attacks") or []:
            if attacks[str(attack_id)].get("text") and attack_id not in ATTACK_CLAUSES:
                raise SystemExit(f"attack {attack_id} has effect text with no clause encoding")
        name, body = _emit_pokemon(card, attacks, functions.get(str(card_id), []),
                                   ability_clauses)
        emitted.append((POKEMON_OUT, name, body))

    for card_id in trainers:
        card = cards[card_id]
        source = effects.get(str(card_id)) or TOOL_CLAUSES.get(card_id)
        if not source:
            raise SystemExit(f"trainer {card_id} has no clause encoding")
        name, body = _emit_trainer(card, functions.get(str(card_id), []), tuple(source))
        emitted.append((TRAINER_OUT, name, body))

    for card_id in energies:
        card = cards[card_id]
        source = effects.get(str(card_id)) or ()
        if card["cardType"] == 6 and not source:
            raise SystemExit(f"special energy {card_id} has no clause encoding")
        name, body = _emit_energy(card, functions.get(str(card_id), []), tuple(source))
        emitted.append((ENERGY_OUT, name, body))

    for out in (POKEMON_OUT, TRAINER_OUT, ENERGY_OUT):
        for stale in out.glob("*.py"):
            if stale.name != "__init__.py":
                stale.unlink()
    for out, name, body in emitted:
        with open(out / name, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(body)
        print(f"wrote {out.name}/{name}")


if __name__ == "__main__":
    main()
