"""CardDB — the engine's card/attack tables, read from `defs/{card_data,attack_data}.json` so cgpy
needs no native lib (ADR-0059). Codes and shapes are pinned by parity tests.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .schema import CardType

_DEFS = Path(__file__).resolve().parent / "defs"

# Native BattleStart errorType codes (probe-pinned).
ERR_NONE = 0
ERR_UNKNOWN_ID = 1
ERR_NAME_COPIES = 2
ERR_NO_BASIC = 3
ERR_ACE_SPEC = 4


@dataclass(frozen=True)
class CardData:
    cardId: int
    name: str
    cardType: int
    retreatCost: int
    hp: int
    weakness: int | None
    resistance: int | None
    energyType: int
    basic: bool
    stage1: bool
    stage2: bool
    ex: bool
    megaEx: bool
    tera: bool
    aceSpec: bool
    evolvesFrom: str | None
    skills: tuple
    attacks: tuple


@dataclass(frozen=True)
class Attack:
    attackId: int
    name: str
    text: str
    damage: int
    energies: tuple


class CardDB:
    def __init__(self, cards: list[dict], attacks: list[dict]):
        self.cards: dict[int, CardData] = {}
        for c in cards:
            self.cards[c["cardId"]] = CardData(
                cardId=c["cardId"], name=c["name"], cardType=c["cardType"],
                retreatCost=c.get("retreatCost", 0), hp=c.get("hp", 0),
                weakness=c.get("weakness"), resistance=c.get("resistance"),
                energyType=c.get("energyType", 0),
                basic=bool(c.get("basic")), stage1=bool(c.get("stage1")),
                stage2=bool(c.get("stage2")), ex=bool(c.get("ex")),
                megaEx=bool(c.get("megaEx")), tera=bool(c.get("tera")),
                aceSpec=bool(c.get("aceSpec")), evolvesFrom=c.get("evolvesFrom"),
                skills=tuple((s.get("name", ""), s.get("text", "")) for s in c.get("skills") or []),
                attacks=tuple(c.get("attacks") or []),
            )
        self.attacks: dict[int, Attack] = {
            a["attackId"]: Attack(a["attackId"], a.get("name", ""), a.get("text", ""),
                                  a.get("damage", 0), tuple(a.get("energies") or []))
            for a in attacks
        }

    @classmethod
    @lru_cache(maxsize=1)
    def load(cls) -> "CardDB":
        cards = json.loads((_DEFS / "card_data.json").read_text(encoding="utf-8"))
        attacks = json.loads((_DEFS / "attack_data.json").read_text(encoding="utf-8"))
        return cls(cards, attacks)

    def card(self, card_id: int) -> CardData:
        return self.cards[card_id]

    def is_pokemon(self, card_id: int) -> bool:
        return self.cards[card_id].cardType == CardType.POKEMON

    def is_basic_pokemon(self, card_id: int) -> bool:
        c = self.cards[card_id]
        return c.cardType == CardType.POKEMON and c.basic

    def is_setup_starter(self, card_id: int) -> bool:
        """Eligible for the setup Active Spot: a Basic, OR an Explosiveness-class ability — a Stage 2
        can legally open (pinned against the native engine)."""
        c = self.cards[card_id]
        if c.cardType != CardType.POKEMON:
            return False
        if c.basic:
            return True
        return any("setting up to play" in text and "Active Spot" in text
                   for _name, text in c.skills)

    def is_energy(self, card_id: int) -> bool:
        return self.cards[card_id].cardType in (CardType.BASIC_ENERGY, CardType.SPECIAL_ENERGY)

    def validate_deck(self, deck: list[int]) -> int:
        """The native BattleStart errorType for `deck`, ERR_NONE if legal. The 60-card length rule
        lives in the Python shim, not the native lib, so it is deliberately NOT enforced here."""
        for cid in deck:
            if cid not in self.cards:
                return ERR_UNKNOWN_ID
        names = Counter()
        for cid in deck:
            c = self.cards[cid]
            if c.cardType != CardType.BASIC_ENERGY:
                names[c.name] += 1
        if names and max(names.values()) > 4:
            return ERR_NAME_COPIES
        if not any(self.is_basic_pokemon(cid) for cid in deck):
            return ERR_NO_BASIC
        if sum(1 for cid in deck if self.cards[cid].aceSpec) > 1:
            return ERR_ACE_SPEC
        return ERR_NONE
