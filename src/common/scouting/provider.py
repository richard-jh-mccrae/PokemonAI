"""Card-stat providers (see docs/scouting.md).

The Scout resolves opponent card ids to stats through a provider, so recognition stays
decoupled from the engine: runtime uses ``EngineCardStatProvider``; tests inject
``DictCardStatProvider`` (lib-free). ``.get(card_id)`` returns a ``CardStat`` or None.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class CardStat:
    cardId: int
    name: str = ""
    hp: int = 0
    ex: bool = False
    megaEx: bool = False
    aceSpec: bool = False              # ACE SPEC — one-per-deck, irreplaceable; read off CardStat for
                                       # 'protect the ACE SPEC' rules (e.g. Hero's Cape)
    hpBonus: int = 0                   # flat HP a Pokémon Tool grants its holder (e.g. Hero's Cape +100),
                                       # parsed from skill text — the engine has no structured field.
                                       # The primitive behind the general +HP-tool breakpoint model.
    recoil: int = 0                    # unconditional self-damage the card's HIGHEST-damage attack
                                       # deals to itself (e.g. Hariyama Wild Press 210 → recoil 70),
                                       # parsed from attack text — the engine has no structured field.
                                       # The central "sensible place" so Tactical survival math can ask
                                       # "does my nuke leave me a free KO?" without per-agent wiring.
    handSizeDamage: int = 0            # per-card damage of a "for each card in your hand" attack
                                       # (Alakazam's Powerful Hand: 2 counters/card = 20), parsed from
                                       # attack text — the printed `damage` is 0, so this is the only
                                       # way the forward-doom / Posture read sees the threat. ep82754875
    benchSnipeDamage: int = 0          # unconditional bench-snipe an attack also deals to ONE of the
                                       # opponent's Benched Pokémon (Jetting Blow → 50), parsed from
                                       # attack text — the opponent's incoming vs MY Bench (the Tool
                                       # survival-turns math reads it for a benched carrier; ADR-0028)
    maxDamage: int = 0
    maxDamageCost: int | None = None   # energy count of the HIGHEST-damage attack (None if unknown) —
                                       # the mirror of minAttackCost: "fully online" means enough Energy
                                       # for the big attack (e.g. Nebula Beam CCC=3), not just the cheap
                                       # one (Jetting Blow 1). The threshold behind `build-active-wincon`.
    minAttackCost: int | None = None   # energy count of the card's cheapest attack (None if unknown)
    minCostDamage: int = 0             # damage of the cheapest-cost attack (best damage among the
                                       # lowest-cost attacks) — for "does the cheap attack KO" gating
                                       # (e.g. Jetting Blow 120 at 1 energy, not Nebula Beam 210 at CCC)
    attacks: tuple = ()                # (attackId, …) of this card's attacks — the lethal-attach
                                       # lookahead reads each attack's cost/damage to ask "would
                                       # attaching this Energy unlock a KO this turn?" (e.g. Ignition →
                                       # CCC → Nebula Beam). Empty when unknown.
    weakness: int | None = None
    resistance: int | None = None
    energyType: int | None = None
    retreatCost: int = 0               # Energy to retreat (engine CardData.retreatCost) — the
                                       # defensive stall-gust strands an energyless high-retreat body
    cardType: int | None = None        # engine CardData.cardType (CardType enum: ITEM=1, TOOL=2,
                                       # SUPPORTER=3, …) — distinguishes a Supporter gust (costs the one
                                       # Supporter slot) from a free Item gust, so Supporter-economy rules
                                       # only fire on Supporters. ADR-0022 #12
    stage: str | None = None
    evolvesFrom: str | None = None


class DictCardStatProvider:
    """In-memory provider for tests and precomputed caches."""

    def __init__(self, stats: dict[int, CardStat]):
        self._stats = stats
        self._forward: _ForwardIndex | None = None

    def get(self, card_id: int) -> CardStat | None:
        return self._stats.get(card_id)

    def forward_max_damage(self, card_id: int) -> int:
        """Max damage the card's evolution line eventually reaches (see ``_ForwardIndex``)."""
        if self._forward is None:
            self._forward = _build_forward_index(self._stats)
        st = self._stats.get(card_id)
        return self._forward.max_forward_damage(st.name) if st else 0

    def forward_card_ids(self, card_id: int) -> frozenset[int]:
        """Card ids the card's evolution line evolves INTO (see ``_ForwardIndex.forward_card_ids``)."""
        if self._forward is None:
            self._forward = _build_forward_index(self._stats)
        st = self._stats.get(card_id)
        return self._forward.forward_card_ids(st.name) if st else frozenset()


# Matches ONLY the unconditional Tool phrasing "The Pokémon this card is attached to gets +N HP"
# (Hero's Cape). A restricted variant inserts a qualifier — "The Cynthia's Pokémon …", "The {G}
# Pokémon …" — so "The Pok.mon" is no longer adjacent and the pattern won't match, parsing those to
# 0. The `.` matches the é without putting a non-ASCII literal in source (cross-platform safe).
_HP_BONUS_RE = re.compile(r"\bThe Pok.mon this card is attached to gets \+(\d+) HP")


def _parse_tool_hp_bonus(card) -> int:
    """Flat HP a Pokémon Tool grants its holder, read from the card's skill text — the engine exposes
    no structured field for it (see ``CardStat.hpBonus``). Matches only the UNCONDITIONAL boost, so a
    conditionally-restricted +HP Tool parses to 0 (the breakpoint model must not over-credit HP a
    target might not actually get). 0 when no skill matches / a card has no skills."""
    for s in (getattr(card, "skills", None) or []):
        text = getattr(s, "text", None)
        if text is None and isinstance(s, dict):
            text = s.get("text")
        m = _HP_BONUS_RE.search(text or "")
        if m:
            return int(m.group(1))
    return 0


# Attack-rider parsers (ADR-0022 #2/#14). The amount of a self-damage (recoil) or a benched-Pokémon
# snipe lives only in the free-text `Attack.text` — the engine exposes no structured field (mirror
# `_parse_tool_hp_bonus`). Both match ONLY the clean UNCONDITIONAL phrasing as a whole sentence, so a
# conditional rider ("You may …", "If you do, …", coin-flip, "for each …") parses to 0. Under-crediting
# is the SAFE direction: a recoil we miss never wrongly downgrades a real win to a draw, and a snipe we
# miss never inflates an attack's value. `.` stands in for the é / apostrophe (cross-platform, no
# non-ASCII literal in source).
_RECOIL_RE = re.compile(r"This Pok.mon (?:also )?does (\d+) damage to itself\.?$")
_BENCH_SNIPE_RE = re.compile(
    r"This attack also does (\d+) damage to 1 of your opponent.s Benched Pok.mon\.?$")
# A "for each card in your hand" attacker (Alakazam's Powerful Hand): its printed `damage` is 0, so the
# threat is invisible without parsing the text. Counter-placement ("Place N damage counters …") is N×10
# damage and ignores Weakness/Resistance; the rarer "does N damage for each card …" is direct damage.
_HAND_SIZE_COUNTERS_RE = re.compile(
    r"Place (\d+) damage counters? on your opponent.s Active Pok.mon for each card in your hand\.?$")
_HAND_SIZE_DAMAGE_RE = re.compile(r"does (\d+) (?:more )?damage for each card in your hand\.?$")
_DAMAGE_PER_COUNTER = 10


def _sentences(text: str) -> list[str]:
    """Split attack text into trimmed sentences (newlines folded to spaces) so a rider parser can
    require its phrasing to be a WHOLE sentence — the cheap guard that rejects conditional riders
    (which begin with "If you do, …" / "You may …" and so never start their sentence with "This …")."""
    return [s.strip() for s in re.split(r"(?<=\.)\s+", (text or "").replace("\n", " ")) if s.strip()]


def parse_attack_recoil(text: str) -> int:
    """Unconditional self-damage (recoil) an attack deals to its OWN Pokémon, e.g. "This Pokémon also
    does 50 damage to itself." → 50. Conditional / variable recoil ("You may …", "If you do …", coin-flip,
    "… for each damage counter …") → 0. Feeds the #2 draw-guard: a lethal whose forced recoil self-KOs me
    and simultaneously gives the opponent their last prize is a DRAW, not a win (ADR-0022)."""
    for sent in _sentences(text):
        m = _RECOIL_RE.match(sent)
        if m:
            return int(m.group(1))
    return 0


def parse_attack_bench_snipe(text: str) -> int:
    """Unconditional bench-snipe damage an attack also deals to ONE of the opponent's Benched Pokémon,
    e.g. Jetting Blow "This attack also does 50 damage to 1 of your opponent's Benched Pokémon." → 50.
    Spreads ("each …"), multi-target ("2 of …"), restricted ("… {ex}"), own-bench, and conditional riders
    → 0. Feeds the #14 bench-value bonus: among equal-cost KO attacks, prefer the one that also snipes a
    worthwhile benched target (ADR-0022)."""
    for sent in _sentences(text):
        m = _BENCH_SNIPE_RE.match(sent)
        if m:
            return int(m.group(1))
    return 0


def parse_attack_hand_size(text: str) -> int:
    """Per-card DAMAGE of a 'for each card in your hand' attack — the threat the printed `damage` (0)
    hides. Alakazam's Powerful Hand "Place 2 damage counters … for each card in your hand" → 2×10 = 20;
    a direct "does N damage for each card in your hand" → N. Counter placement ignores Weakness/
    Resistance (counters are not 'damage'). 0 for any other attack. The forward-doom / Posture read
    multiplies this by the opponent's hand size (ep82754875 f52).

    Args:
        text: the attack's free-text effect.

    Returns:
        The per-card damage (counter count × 10, or direct damage), else 0.
    """
    for sent in _sentences(text):
        m = _HAND_SIZE_COUNTERS_RE.match(sent)
        if m:
            return int(m.group(1)) * _DAMAGE_PER_COUNTER
        m = _HAND_SIZE_DAMAGE_RE.search(sent)
        if m:
            return int(m.group(1))
    return 0


def _build_cache(card_data, attacks) -> dict[int, CardStat]:
    """Pure transform: engine card/attack records -> ``{cardId: CardStat}``.

    Kept separate from the engine import so it is testable lib-free.
    """
    dmg: dict[int, int] = {}
    cost: dict[int, int] = {}
    recoil_by_aid: dict[int, int] = {}
    hand_size_by_aid: dict[int, int] = {}
    bench_snipe_by_aid: dict[int, int] = {}
    for a in attacks:
        dmg.setdefault(a.attackId, a.damage)
        cost.setdefault(a.attackId, len(getattr(a, "energies", None) or []))
        recoil_by_aid.setdefault(a.attackId, parse_attack_recoil(getattr(a, "text", "") or ""))
        hand_size_by_aid.setdefault(a.attackId, parse_attack_hand_size(getattr(a, "text", "") or ""))
        bench_snipe_by_aid.setdefault(a.attackId, parse_attack_bench_snipe(getattr(a, "text", "") or ""))
    cache: dict[int, CardStat] = {}
    for c in card_data:
        max_dmg = max((dmg.get(aid, 0) for aid in c.attacks), default=0)
        costs = [cost[aid] for aid in c.attacks if aid in cost]   # energy-count of each known attack
        min_cost = min(costs) if costs else None
        cheap_dmg = (max((dmg.get(aid, 0) for aid in c.attacks if cost.get(aid) == min_cost),
                         default=0) if min_cost is not None else 0)
        # cost of the highest-damage attack (min cost among attacks tying for max damage — the
        # cheapest way to reach the big hit); None when no attack's cost is known.
        max_dmg_costs = [cost[aid] for aid in c.attacks if aid in cost and dmg.get(aid, 0) == max_dmg]
        max_dmg_cost = min(max_dmg_costs) if max_dmg_costs else None
        # recoil of the highest-damage attack (the nuke most likely to self-KO): max over attacks
        # tying for max damage. 0 when no attack has unconditional recoil.
        recoil = max((recoil_by_aid.get(aid, 0) for aid in c.attacks if dmg.get(aid, 0) == max_dmg),
                     default=0)
        cache[c.cardId] = CardStat(
            cardId=c.cardId, name=c.name, hp=int(c.hp),
            ex=bool(c.ex), megaEx=bool(c.megaEx), aceSpec=bool(getattr(c, "aceSpec", False)),
            hpBonus=_parse_tool_hp_bonus(c),
            recoil=int(recoil),
            handSizeDamage=int(max((hand_size_by_aid.get(aid, 0) for aid in c.attacks), default=0)),
            benchSnipeDamage=int(max((bench_snipe_by_aid.get(aid, 0) for aid in c.attacks), default=0)),
            maxDamage=int(max_dmg), maxDamageCost=max_dmg_cost,
            attacks=tuple(c.attacks),
            minAttackCost=(min(costs) if costs else None), minCostDamage=int(cheap_dmg),
            weakness=(int(c.weakness) if c.weakness is not None else None),
            resistance=(int(c.resistance) if c.resistance is not None else None),
            energyType=(int(c.energyType) if c.energyType is not None else None),
            retreatCost=int(getattr(c, "retreatCost", 0) or 0),
            cardType=(int(c.cardType) if getattr(c, "cardType", None) is not None else None),
            evolvesFrom=c.evolvesFrom,
        )
    return cache


class _ForwardIndex:
    """Generic, deck-agnostic forward-evolution map (ADR-0020).

    Inverts ``CardStat.evolvesFrom`` (a *name*) over the stat cache so we can read, off any benched
    pre-evolution, the damage its line eventually reaches — the **Evolving Threat** signal (e.g.
    Riolu -> Mega Lucario ex = 270). Keyed by name; folds MAX over every printing of a name (names
    are not unique). Distinct from the Read's opponent-specific ``EvoPath``.
    """

    def __init__(self, cache: dict[int, CardStat]):
        self._maxdmg: dict[str, int] = {}        # name -> max printed damage over all its printings
        self._children: dict[str, set[str]] = {}  # parent name -> child names (evolvesFrom == parent)
        self._name_ids: dict[str, set[int]] = {}  # name -> every card id printed under it
        for st in cache.values():
            if not st.name:
                continue
            self._name_ids.setdefault(st.name, set()).add(st.cardId)
            if st.maxDamage > self._maxdmg.get(st.name, 0):
                self._maxdmg[st.name] = st.maxDamage
            if st.evolvesFrom:
                self._children.setdefault(st.evolvesFrom, set()).add(st.name)

    def _descendant_names(self, name: str | None) -> set[str]:
        """The forms ``name`` can evolve INTO (descendants only, multi-hop). Cycle-guarded."""
        seen, stack = set(), list(self._children.get(name or "", ()))
        while stack:
            child = stack.pop()
            if child in seen:
                continue
            seen.add(child)
            stack.extend(self._children.get(child, ()))
        return seen

    def max_forward_damage(self, name: str | None) -> int:
        """Max printed damage over the forms ``name`` can evolve INTO (descendants only, multi-hop);
        0 if it is a dead end. Cycle-guarded, so a malformed line can't loop."""
        if not name:
            return 0
        return max((self._maxdmg.get(d, 0) for d in self._descendant_names(name)), default=0)

    def forward_card_ids(self, name: str | None) -> frozenset[int]:
        """Every card id of every form ``name`` can evolve INTO (descendants only, multi-hop, all
        printings) — so a consumer can ask whether a benched pre-evolution's line eventually reaches
        an ``ex`` / a card carrying a given Function Tag (e.g. a hand-size attacker). Empty for a dead
        end. Cycle-guarded (delegates to ``_descendant_names``)."""
        ids: set[int] = set()
        for d in self._descendant_names(name):
            ids |= self._name_ids.get(d, set())
        return frozenset(ids)


def _build_forward_index(cache: dict[int, CardStat]) -> _ForwardIndex:
    """Pure transform: ``{cardId: CardStat}`` -> forward-evolution index. Kept lib-free for tests."""
    return _ForwardIndex(cache)


class EngineCardStatProvider:
    """Lazily build a ``{cardId: CardStat}`` cache from the native engine (runtime only)."""

    def __init__(self):
        self._cache: dict[int, CardStat] | None = None
        self._forward: _ForwardIndex | None = None

    def _ensure_cache(self) -> None:
        """Build the stat cache + forward index together, once. The single build site so the two
        never diverge — ``get`` and ``forward_max_damage`` both go through here."""
        if self._cache is None:
            from cg.api import all_attack, all_card_data  # runtime only
            self._cache = _build_cache(all_card_data(), all_attack())
            self._forward = _build_forward_index(self._cache)

    def get(self, card_id: int) -> CardStat | None:
        self._ensure_cache()
        return self._cache.get(card_id)

    def forward_max_damage(self, card_id: int) -> int:
        """Max damage the card's evolution line eventually reaches (see ``_ForwardIndex``)."""
        self._ensure_cache()
        st = self._cache.get(card_id)
        return self._forward.max_forward_damage(st.name) if st else 0

    def forward_card_ids(self, card_id: int) -> frozenset[int]:
        """Card ids the card's evolution line evolves INTO (see ``_ForwardIndex.forward_card_ids``)."""
        self._ensure_cache()
        st = self._cache.get(card_id)
        return self._forward.forward_card_ids(st.name) if st else frozenset()
