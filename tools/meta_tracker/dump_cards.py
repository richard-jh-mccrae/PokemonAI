"""Dump the engine's card pool to a portable JSON cache.

Loads card + attack tables from the native `cg` engine (in `my_submissions/cg`)
and writes `cards.json` next to this file. The rest of meta_tracker reads that
JSON, so the pipeline and tests never need the native library at runtime.

Re-run whenever the competition updates the legal card pool.

Usage:
    python tools/meta_tracker/dump_cards.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / "cards.json"

# CardType / EnergyType enum value -> label (see my_submissions/cg/api.py).
CATEGORY = {0: "pokemon", 1: "item", 2: "tool", 3: "supporter",
            4: "stadium", 5: "basic_energy", 6: "special_energy"}
ENERGY = {0: "colorless", 1: "grass", 2: "fire", 3: "water", 4: "lightning",
          5: "psychic", 6: "fighting", 7: "darkness", 8: "metal", 9: "dragon",
          10: "rainbow", 11: "team_rocket"}


def stage_of(c) -> str | None:
    if c.basic:
        return "basic"
    if c.stage1:
        return "stage1"
    if c.stage2:
        return "stage2"
    return None


def main() -> None:
    sys.path.insert(0, str(REPO / "my_submissions"))
    from cg.api import all_attack, all_card_data  # noqa: E402

    attacks_by_id = {a.attackId: {"name": a.name, "damage": int(a.damage),
                                  "energies": [int(e) for e in a.energies], "text": a.text}
                     for a in all_attack()}

    cards: dict[str, dict] = {}
    for c in all_card_data():
        attacks = [attacks_by_id.get(aid, {"attackId": aid}) for aid in c.attacks]
        max_damage = max((a.get("damage", 0) for a in attacks), default=0)
        cards[str(c.cardId)] = {
            "name": c.name,
            "category": CATEGORY.get(int(c.cardType), str(int(c.cardType))),
            "stage": stage_of(c),
            "ex": bool(c.ex),
            "megaEx": bool(c.megaEx),
            "tera": bool(c.tera),
            "aceSpec": bool(c.aceSpec),
            "evolvesFrom": c.evolvesFrom,
            "energy": ENERGY.get(int(c.energyType), str(int(c.energyType))),
            "hp": int(c.hp),
            "retreat": int(c.retreatCost),
            # Enrichment for the Scouting compiler (backward-compatible; regenerate to fill).
            "weakness": (int(c.weakness) if c.weakness is not None else None),
            "resistance": (int(c.resistance) if c.resistance is not None else None),
            "maxDamage": int(max_damage),
            "attackCount": len(c.attacks),
            "abilities": [{"name": s.name, "text": s.text} for s in c.skills],
            "attacks": attacks,
        }

    OUT.write_text(json.dumps(cards, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"wrote {len(cards)} cards -> {OUT}")


if __name__ == "__main__":
    main()
