"""Turn a 60-card decklist into evolution lines, main/sub lines, and an archetype.

The decklist is the only signal (play-by-play is discarded), so "main line" is
defined structurally — see CONTEXT.md (Main-line Pokémon, Archetype).

Key rule: a deck may contain a top-stage Pokémon *without* its pre-evolutions
(e.g. Cinderace with no Raboot), so a line's attacker is the highest stage
actually present, never an assumed full chain.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from . import config
from .cards import is_attacker, is_exclass, is_pokemon, load_cards, stage_rank


@dataclass
class Line:
    """One evolution line present in a deck."""
    top_id: int          # highest-stage card present (the attacker)
    top_name: str
    members: list[int]   # all card ids in the line, present in the deck
    investment: int      # copies of the top-stage card
    stage_rank: int      # 0/1/2
    exclass: bool        # top is ex / Mega-ex
    attacker: bool       # top has a printed damaging attack
    damage: int          # top card's max printed damage (0 = attacks via ability/effect)


@dataclass
class Archetype:
    name: str                       # canonical key, e.g. "Cinderace / Mega Starmie ex"
    main_lines: list[str]           # up to MAX_MAIN_LINES, in investment order
    sub_lines: list[str]            # other Pokémon line tops
    energy: list[str] = field(default_factory=list)  # basic-energy types in deck


def _find(parent: dict[int, int], x: int) -> int:
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def evolution_lines(deck_counts: dict[int, int], cards: dict[int, dict] | None = None) -> list[Line]:
    """Group the Pokémon in ``deck_counts`` ({card_id: copies}) into evolution lines."""
    cards = cards or load_cards()
    pokes = [cid for cid in deck_counts if is_pokemon(cards.get(cid, {}))]
    if not pokes:
        return []

    # Union cards linked by evolvesFrom (by name), among those present.
    name_to_ids: dict[str, list[int]] = {}
    for cid in pokes:
        name_to_ids.setdefault(cards[cid]["name"], []).append(cid)
    parent = {cid: cid for cid in pokes}
    for cid in pokes:
        ef = cards[cid].get("evolvesFrom")
        for pre in name_to_ids.get(ef, []):
            parent[_find(parent, cid)] = _find(parent, pre)

    comps: dict[int, list[int]] = {}
    for cid in pokes:
        comps.setdefault(_find(parent, cid), []).append(cid)

    lines: list[Line] = []
    for members in comps.values():
        top = max(members, key=lambda c: (stage_rank(cards[c]), cards[c].get("maxDamage", 0),
                                          deck_counts[c]))
        tc = cards[top]
        lines.append(Line(
            top_id=top, top_name=tc["name"], members=sorted(members),
            investment=deck_counts[top], stage_rank=stage_rank(tc),
            exclass=is_exclass(tc), attacker=is_attacker(tc), damage=tc.get("maxDamage", 0),
        ))
    return lines


def _rank_key(line: Line) -> tuple:
    # Higher investment, then higher stage, then ex-class, then more printed damage.
    return (line.investment, line.stage_rank, int(line.exclass), line.damage)


def is_engine(name: str) -> bool:
    """A curated consistency/tech Pokémon that should never name an archetype."""
    return any(name == e or name.startswith(e + " ") for e in config.ENGINE_POKEMON)


def classify(deck_ids: list[int], cards: dict[int, dict] | None = None) -> Archetype:
    """Classify a full 60-card decklist (list of card ids, repeats allowed)."""
    cards = cards or load_cards()
    counts = Counter(deck_ids)
    lines = evolution_lines(dict(counts), cards)

    # Main candidates = non-engine lines ranked by investment (a win-condition may
    # deal 0 printed damage and attack via an ability/effect, e.g. Alakazam).
    candidates = sorted((l for l in lines if not is_engine(l.top_name)), key=_rank_key, reverse=True)
    mains = [l for l in candidates if l.investment >= config.MAIN_LINE_MIN_COPIES][:config.MAX_MAIN_LINES]
    if not mains:  # never produce a nameless archetype
        mains = candidates[:1] or sorted(lines, key=_rank_key, reverse=True)[:1]

    main_ids = {l.top_id for l in mains}
    main_names = [l.top_name for l in mains]
    sub_names = sorted(l.top_name for l in lines if l.top_id not in main_ids)

    energy = sorted({cards[cid]["energy"] for cid in counts
                     if cards.get(cid, {}).get("category") == "basic_energy"})

    name = " / ".join(sorted(main_names)) if main_names else "Unknown"
    return Archetype(name=name, main_lines=main_names, sub_lines=sub_names, energy=energy)
