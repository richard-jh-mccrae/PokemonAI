"""Card-stat providers (docs/scouting.md): the Scout resolves opponent card ids to stats through
one, so recognition stays decoupled from the engine. Runtime uses ``EngineCardStatProvider``, tests
inject ``DictCardStatProvider``. This module owns the typed records and the adapters; text->facts
lives in ``card_text`` and the name-keyed indexes in ``forward_index`` (ADR-0054)."""
from __future__ import annotations

from dataclasses import dataclass

# Re-exports (ADR-0054): tests and tools import these through this module — keep every name bound.
from .card_text import (  # noqa: F401
    _parse_tool_attack_cost_reduction,
    _parse_tool_holder_family,
    _parse_tool_holder_no_rule_box,
    _parse_tool_hp_bonus,
    _parse_retreat_free_grant,
    _parse_tool_retreat_free_at_hp,
    _parse_tool_retreat_reduction,
    name_in_family,
    normalize_card_name,
    parse_attack_bench_requirement,
    parse_tool_damage_reduction,
    parse_attack_bench_snipe,
    parse_attack_bench_spread,
    parse_attack_damage_bounds,
    parse_attack_effect_damage,
    parse_attack_energy_recover,
    parse_attack_hidden_scale,
    parse_attack_ignores,
    parse_attack_ignores_active_effects,
    parse_attack_recoil,
    parse_attack_scaling,
    parse_attack_self_return,
    parse_attack_transients,
    parse_card_ability_energy,
    parse_card_damage_boost,
    parse_card_defense,
)
from .forward_index import _ForwardIndex, _build_forward_index, _name_index  # noqa: F401

# CardType enum codes (cg.api.CardType) mirrored as literals so the records stay lib-free.
_ITEM, _TOOL, _SUPPORTER, _STADIUM, _BASIC_ENERGY, _SPECIAL_ENERGY = 1, 2, 3, 4, 5, 6


def stage_from_card(c) -> str | None:
    """The card's printed evolution stage as the CANONICAL string — the ONE derivation (Issue #408),
    folding the engine's three ``CardData`` booleans. None for a card that is not a Pokémon body."""
    if getattr(c, "basic", False):
        return "basic"
    if getattr(c, "stage1", False):
        return "stage1"
    if getattr(c, "stage2", False):
        return "stage2"
    return None


@dataclass
class CardStat:
    cardId: int
    name: str = ""
    hp: int = 0
    ex: bool = False
    megaEx: bool = False
    aceSpec: bool = False              # one per deck, irreplaceable
    hasAbility: bool = False
    hpBonus: int = 0                   # flat HP a Tool grants its holder (parsed; no engine field)
    retreatReduction: int = 0          # SIGNED: NEGATIVE when a Tool makes retreating DEARER
    attackCostReduction: int = 0       # NO LIVE CONSUMER YET, deliberately: affordability is
                                       # ATTACK-keyed, and a wrong credit manufactures a phantom KO
    holderNameFamily: str | None = None  # None = unconditional. Ask `applies_to_holder`, not this
    holderNoRuleBox: bool = False      # Brave Bangle only. Ask `applies_to_holder`, not this
    retreatFreeAtHp: int = 0           # the CONDITIONAL leg beside `retreatReduction` (ADR-0100 §8)
    retreatFreeGrant: str | None = None  # a BOARD-LEVEL Ability, as the predicate it scopes to
    recoil: int = 0                    # self-damage of the card's HIGHEST-damage attack
    handSizeDamage: int = 0            # printed damage is 0, so this is the only view of the threat
    benchSnipeDamage: int = 0
    maxDamage: int = 0
    maxDamageCost: int | None = None
    minAttackCost: int | None = None
    minCostDamage: int = 0             # best damage among the lowest-cost attacks
    attacks: tuple = ()                # (attackId, …)
    abilityEnergyTypes: tuple = ()     # a colour a body needs for its Ability, for no attack cost
    weakness: int | None = None
    resistance: int | None = None
    energyType: int | None = None
    retreatCost: int = 0
    cardType: int | None = None        # CardType enum (ITEM=1, TOOL=2, SUPPORTER=3…)
    stage: str | None = None           # CANONICAL vocabulary, written ONLY by `_build_cache`
    stage2: bool = False
    evolvesFrom: str | None = None
    tera: bool = False                 # takes NO damage from attacks while BENCHED
    # A multi-mode "Choose 1" boost card is fail-closed.
    damageBoost: int = 0                    # flat "+N to opp Active" BEFORE W/R
    damageBoostType: int | None = None      # attacker EnergyType gate; None = any
    damageBoostVsEx: bool = False           # defender "{ex}" gate — includes Mega ex (rulebook.txt:337)
    preventsDamageFrom: str | None = None   # "ex" | "basic_ex"; pierced by an ignoresEffects attack
    preventsDamageAtLeast: int = 0          # threshold prevention (damage >= N -> 0); 0 = off
    damageReduction: int = 0                # flat always-on, AFTER W/R
    damageReductionTypes: tuple | None = None  # None = all attackers
    damageReductionHolderTypes: tuple | None = None  # Tool: holder EnergyType gate; None = any
    damageReductionRequiresAbility: bool = False     # Tool: only attackers WITH an Ability
    synthetic: bool = False             # test-only: an arbitrary body on a convenient real id

    # --- single-card interpretation (ADR-0056): byte-faithful ports of retired call-site idioms.

    @property
    def is_ex_body(self) -> bool:
        """An ex-rule body (ex or Mega ex) — the multi-prize liability / boost-gate predicate."""
        return bool(self.ex or self.megaEx)

    @property
    def prize_value(self) -> int:
        """Prizes a knockout of this body yields — Mega ex 3, ex 2, else 1."""
        if self.megaEx:
            return 3
        return 2 if self.ex else 1

    @property
    def is_pokemon(self) -> bool:
        """A Pokémon (Trainers / Energy report hp 0)."""
        return self.hp > 0

    @property
    def is_item(self) -> bool:
        return self.cardType == _ITEM

    @property
    def is_tool(self) -> bool:
        return self.cardType == _TOOL

    @property
    def is_supporter(self) -> bool:
        return self.cardType == _SUPPORTER

    @property
    def is_stadium(self) -> bool:
        """A Stadium card — so the FETCH closure asks through ``CardStat`` like every other class."""
        return self.cardType == _STADIUM

    @property
    def is_basic_energy(self) -> bool:
        return self.cardType == _BASIC_ENERGY

    @property
    def is_special_energy(self) -> bool:
        """PROVISION is card text, not one unit of its own colour: read the amount off `provides:N`."""
        return self.cardType == _SPECIAL_ENERGY

    @property
    def is_energy(self) -> bool:
        return self.cardType in (_BASIC_ENERGY, _SPECIAL_ENERGY)

    @property
    def is_typed_basic_energy(self) -> bool:
        return self.cardType == _BASIC_ENERGY and self.energyType is not None

    def applies_to_holder(self, holder: "CardStat | None") -> bool:
        """Do THIS Tool's static modifiers reach ``holder``? The ONE place both holder gates are
        evaluated, ANDed — a gate added at three of the four consumers is one the fourth ignores."""
        # `getattr` with a True default rather than `holder.is_ex_body`: a holder we cannot
        # interrogate must fail BOTH gates the same way, and for a benefit that way is refuse.
        if self.holderNoRuleBox and (holder is None or getattr(holder, "is_ex_body", True)):
            return False
        return name_in_family(getattr(holder, "name", None), self.holderNameFamily)

    def can_pay_cheapest(self, energy: int) -> bool:
        """fail-CLOSED (``(minAttackCost or 99) <= energy``): an unknown cost reads unaffordable."""
        return (self.minAttackCost or 99) <= energy


class DictCardStatProvider:
    """In-memory provider for tests and precomputed caches."""

    def __init__(self, stats: dict[int, CardStat], attacks: dict[int, "AttackStat"] | None = None):
        self._stats = stats
        self._attacks = attacks or {}       # attackId -> AttackStat
        self._forward: _ForwardIndex | None = None
        self._name_ids: dict[str, frozenset[int]] | None = None

    def get(self, card_id: int) -> CardStat | None:
        return self._stats.get(card_id)

    def attack(self, attack_id) -> "AttackStat | None":
        return self._attacks.get(attack_id)

    def warm(self) -> None:
        """Interface parity with the engine adapter's build hook — nothing to build."""

    def ids_for_name(self, name: str) -> frozenset[int]:
        """Card ids printed under ``name`` (names aren't unique); empty for an unknown name. The
        Matchup Brief consumer's name->id bridge (ADR-0027)."""
        if self._name_ids is None:
            self._name_ids = _name_index(self._stats)
        return self._name_ids.get(name, frozenset())

    def forward_max_damage(self, card_id: int) -> int:
        if self._forward is None:
            self._forward = _build_forward_index(self._stats)
        st = self._stats.get(card_id)
        return self._forward.max_forward_damage(st.name) if st else 0

    def forward_card_ids(self, card_id: int) -> frozenset[int]:
        if self._forward is None:
            self._forward = _build_forward_index(self._stats)
        st = self._stats.get(card_id)
        return self._forward.forward_card_ids(st.name) if st else frozenset()


@dataclass
class AttackStat:
    """Per-attack effect record (ADR-0032): the attack-keyed tier beside the card-keyed ``CardStat``.
    Parsed fields are SEEDS — the engine audit corrects them through ``build_attack_stats``."""
    attackId: int
    name: str = ""                     # PRINTED — the filtered count names an ATTACK, not a card
    damage: int = 0
    cost: int = 0                      # energy count
    energyTypes: tuple = ()            # per-slot EnergyType codes; 0 = colorless/any
    recoil: int = 0                    # unconditional self-damage (ADR-0022 #2)
    benchSnipe: int = 0                # unconditional opp-bench rider (ADR-0022 #14); ignores W/R
    benchSpread: int = 0               # spread TOTAL, so the counter count is benchSpread // 10
    ignoresWeakness: bool = False
    ignoresResistance: bool = False
    ignoresEffects: bool = False       # pierces defender-side effects incl. prevention Abilities
    damageMin: int | None = None       # sound FLOOR; None = deterministic
    damageMax: int | None = None       # the Lethal Solver reads the floor, Incoming the ceiling
    scaleVar: str | None = None        # damage = printed + scalePerUnit x count(scaleVar),
    scalePerUnit: int = 0              # attacker-relative and EXACT (every variable is visible)
    scaleEnergyType: int | None = None  # None = count EVERY Energy card in the attacker's discard
    scaleFilter: tuple | None = None   # the FILTERED-COUNT predicate ARGUMENT; None = the family
                                       # claims NOTHING (ADR-0115)
    hiddenPerUnit: int = 0             # HIDDEN-state deck-discard scaler: damage += perUnit x units
    hiddenSample: int = 0              # units unknowable closed-form: "max" assumes every sampled
                                       # card fuels, "min"/"exact" 0 without a deck-tracker read
    hiddenEnergyType: int | None = None  # Basic-{X} filter
    recoverN: int = 0                  # energy-accel rider: max cards attached
    recoverEnergyType: int | None = None   # None = any Basic Energy
    recoverTarget: str | None = None   # "self" / "bench" / "any"
    recoverSource: str | None = None   # "discard" or "deck"; None = no rider
    requiresBench: tuple | None = None  # ALL these names must be Benched; "max" keeps printed
    selfReturn: bool = False           # scoops its OWN Pokémon back to hand, denying the prize
    # Transient grants (ADR-0033), tracked match-scoped from ATTACK logs: an obs carries no effects.
    nextTurnReduction: int = 0         # defender-side: "takes N less damage" next turn
    nextTurnPreventAll: bool = False   # defender-side: "prevent all damage done to this Pokémon"
    nextTurnSelfLock: bool = False     # attacker-side: "this Pokémon can't attack / use attacks"
    nextTurnSameAttackLock: bool = False   # attacker-side: "can't use <THIS attack>" next turn
    nextTurnSelfBonus: int = 0         # attacker-side: this Pokémon's attack does +N next turn
    # NB "Defending Pokémon can't retreat" is deliberately NOT tracked: the engine ENFORCES the lock
    # by omitting RETREAT from the menu, so re-add a parse only alongside a real consumer.

    @property
    def is_deterministic(self) -> bool:
        """Byte-faithful: a record whose ``damageMax`` stays ``None`` does NOT read deterministic."""
        return bool(self.damageMax == self.damage and self.scaleVar is None
                    and not self.scalePerUnit and not self.hiddenPerUnit)

    @property
    def handSizeDamage(self) -> int:
        """DERIVED from the scaling term, so it cannot drift from it and honours overrides free."""
        return self.scalePerUnit if self.scaleVar == "atk_hand" else 0


def load_attack_overrides(path=None) -> dict:
    """Fail-safe: a missing or unreadable file -> {}, i.e. parsed seeds only."""
    import json
    from pathlib import Path
    p = Path(path) if path is not None else Path(__file__).resolve().parents[1] / "attack_overrides.json"
    try:
        return {int(k): v for k, v in json.loads(p.read_text(encoding="utf-8")).items()}
    except Exception:
        return {}


def build_attack_stats(attacks, overrides: dict | None = None) -> dict[int, AttackStat]:
    """Pure transform: engine ``Attack`` records → ``{attackId: AttackStat}`` (ADR-0032).
    ``overrides`` apply AFTER parsing and always beat a parsed value; unknown ids are ignored."""
    table: dict[int, AttackStat] = {}
    for a in attacks:
        text = getattr(a, "text", "") or ""
        w, r, e = parse_attack_ignores(text)
        printed = int(getattr(a, "damage", 0) or 0)
        bounds = parse_attack_damage_bounds(text, printed)
        scaling = parse_attack_scaling(text)
        hidden = parse_attack_hidden_scale(text)
        recover = parse_attack_energy_recover(text)
        requires_bench = parse_attack_bench_requirement(text)
        trans = parse_attack_transients(text, getattr(a, "name", "") or "")
        free_target_snipe = 0
        if printed == 0 and not scaling and not hidden:
            effect = parse_attack_effect_damage(text)   # fixed effect damage hides in text
            if effect and effect[1]:    # counter-put: counters bypass W/R and prevention
                printed = effect[0]
                w = r = e = True
            elif effect:                # free-target: it can KO ANY opp Pokémon incl the Bench, so
                free_target_snipe = effect[0]   # value it as a full-damage bench snipe
                w = r = e = True
        if scaling and scaling[2]:      # counter-placer: counters aren't damage — no W/R, no
            w = r = e = True            # prevention (Powerful Hand lands through Crustle)
        table[a.attackId] = AttackStat(
            attackId=a.attackId, name=getattr(a, "name", "") or "", damage=printed,
            cost=len(getattr(a, "energies", None) or []),
            energyTypes=tuple(getattr(a, "energies", None) or []),
            recoil=parse_attack_recoil(text),
            benchSnipe=parse_attack_bench_snipe(text) or free_target_snipe,
            benchSpread=parse_attack_bench_spread(text),
            ignoresWeakness=w, ignoresResistance=r, ignoresEffects=e,
            damageMin=(bounds[0] if bounds else None),
            damageMax=(bounds[1] if bounds else None),
            scaleVar=(scaling[0] if scaling else None),
            scalePerUnit=(scaling[1] if scaling else 0),
            scaleEnergyType=(scaling[3] if scaling else None),
            hiddenPerUnit=(hidden[0] if hidden else 0),
            hiddenSample=(hidden[1] if hidden else 0),
            hiddenEnergyType=(hidden[2] if hidden else None),
            recoverN=(recover[0] if recover else 0),
            recoverEnergyType=(recover[1] if recover else None),
            recoverTarget=(recover[2] if recover else None),
            recoverSource=(recover[3] if recover else None),
            requiresBench=requires_bench,
            selfReturn=parse_attack_self_return(text),
            nextTurnReduction=trans.get("reduction", 0),
            nextTurnPreventAll=trans.get("prevent_all", False),
            nextTurnSelfLock=trans.get("self_lock", False),
            nextTurnSameAttackLock=trans.get("same_lock", False),
            nextTurnSelfBonus=trans.get("self_bonus", 0),
        )
    for aid, fields in (overrides or {}).items():
        st = table.get(int(aid))
        if st is None:
            continue
        for k, v in fields.items():
            if hasattr(st, k):
                setattr(st, k, v)
    return table


def _build_cache(card_data, attacks) -> dict[int, CardStat]:
    """Kept separate from the engine import so it is testable lib-free."""
    dmg: dict[int, int] = {}
    cost: dict[int, int] = {}
    recoil_by_aid: dict[int, int] = {}
    hand_size_by_aid: dict[int, int] = {}
    bench_snipe_by_aid: dict[int, int] = {}
    for a in attacks:
        dmg.setdefault(a.attackId, a.damage)
        cost.setdefault(a.attackId, len(getattr(a, "energies", None) or []))
        recoil_by_aid.setdefault(a.attackId, parse_attack_recoil(getattr(a, "text", "") or ""))
        # ONE parse of the sentence (Issue #213): the roll-up reads the Damage Formula's own term.
        _scale = parse_attack_scaling(getattr(a, "text", "") or "")
        hand_size_by_aid.setdefault(a.attackId,
                                    _scale[1] if _scale and _scale[0] == "atk_hand" else 0)
        bench_snipe_by_aid.setdefault(a.attackId, parse_attack_bench_snipe(getattr(a, "text", "") or ""))
    cache: dict[int, CardStat] = {}
    for c in card_data:
        max_dmg = max((dmg.get(aid, 0) for aid in c.attacks), default=0)
        costs = [cost[aid] for aid in c.attacks if aid in cost]   # energy-count of each known attack
        min_cost = min(costs) if costs else None
        cheap_dmg = (max((dmg.get(aid, 0) for aid in c.attacks if cost.get(aid) == min_cost),
                         default=0) if min_cost is not None else 0)
        # the cheapest way to reach the big hit; None when no attack's cost is known.
        max_dmg_costs = [cost[aid] for aid in c.attacks if aid in cost and dmg.get(aid, 0) == max_dmg]
        max_dmg_cost = min(max_dmg_costs) if max_dmg_costs else None
        # recoil of the highest-damage attack — the nuke most likely to self-KO.
        recoil = max((recoil_by_aid.get(aid, 0) for aid in c.attacks if dmg.get(aid, 0) == max_dmg),
                     default=0)
        prevents_from, prevents_at_least, dmg_reduction, reduction_types = parse_card_defense(c)
        # A Tool's reduction wording is disjoint from the body patterns; nonzero wins the slot.
        tool_red, tool_types, tool_holders, tool_ability = parse_tool_damage_reduction(c)
        if tool_red:
            dmg_reduction, reduction_types = tool_red, tool_types
        boost, boost_type, boost_vs_ex = parse_card_damage_boost(c)
        cache[c.cardId] = CardStat(
            cardId=c.cardId, name=c.name, hp=int(c.hp),
            ex=bool(c.ex), megaEx=bool(c.megaEx), aceSpec=bool(getattr(c, "aceSpec", False)),
            hasAbility=bool(int(c.hp) > 0 and getattr(c, "skills", None)),
            hpBonus=_parse_tool_hp_bonus(c),
            retreatReduction=_parse_tool_retreat_reduction(c),
            attackCostReduction=_parse_tool_attack_cost_reduction(c),
            holderNameFamily=_parse_tool_holder_family(c),
            holderNoRuleBox=_parse_tool_holder_no_rule_box(c),
            retreatFreeAtHp=_parse_tool_retreat_free_at_hp(c),
            retreatFreeGrant=_parse_retreat_free_grant(c),
            stage=stage_from_card(c),
            stage2=bool(getattr(c, "stage2", False)),
            damageBoost=boost, damageBoostType=boost_type, damageBoostVsEx=boost_vs_ex,
            recoil=int(recoil),
            handSizeDamage=int(max((hand_size_by_aid.get(aid, 0) for aid in c.attacks), default=0)),
            benchSnipeDamage=int(max((bench_snipe_by_aid.get(aid, 0) for aid in c.attacks), default=0)),
            maxDamage=int(max_dmg), maxDamageCost=max_dmg_cost,
            attacks=tuple(c.attacks),
            abilityEnergyTypes=parse_card_ability_energy(c),
            minAttackCost=(min(costs) if costs else None), minCostDamage=int(cheap_dmg),
            weakness=(int(c.weakness) if c.weakness is not None else None),
            resistance=(int(c.resistance) if c.resistance is not None else None),
            energyType=(int(c.energyType) if c.energyType is not None else None),
            retreatCost=int(getattr(c, "retreatCost", 0) or 0),
            cardType=(int(c.cardType) if getattr(c, "cardType", None) is not None else None),
            evolvesFrom=c.evolvesFrom,
            tera=bool(getattr(c, "tera", False)),
            preventsDamageFrom=prevents_from,
            preventsDamageAtLeast=prevents_at_least,
            damageReduction=dmg_reduction,
            damageReductionTypes=reduction_types,
            damageReductionHolderTypes=tool_holders if tool_red else None,
            damageReductionRequiresAbility=bool(tool_red and tool_ability),
        )
    return cache


class EngineCardStatProvider:
    """Lazily build a ``{cardId: CardStat}`` cache from the native engine (runtime only)."""

    def __init__(self):
        self._cache: dict[int, CardStat] | None = None
        self._attack_stats: dict[int, AttackStat] | None = None
        self._forward: _ForwardIndex | None = None
        self._name_ids: dict[str, frozenset[int]] | None = None

    def _ensure_cache(self) -> None:
        """The single build site for all three tables, so they never diverge (ADR-0056)."""
        if self._cache is None:
            from cg.api import all_attack, all_card_data  # runtime only
            attacks = all_attack()
            self._cache = _build_cache(all_card_data(), attacks)
            self._attack_stats = build_attack_stats(attacks, load_attack_overrides())
            self._forward = _build_forward_index(self._cache)

    def warm(self) -> None:
        """Explicit pregame-window build — the lazy build, forced now. Idempotent."""
        self._ensure_cache()

    def get(self, card_id: int) -> CardStat | None:
        self._ensure_cache()
        return self._cache.get(card_id)

    def attack(self, attack_id) -> AttackStat | None:
        self._ensure_cache()
        return self._attack_stats.get(attack_id)

    def forward_max_damage(self, card_id: int) -> int:
        self._ensure_cache()
        st = self._cache.get(card_id)
        return self._forward.max_forward_damage(st.name) if st else 0

    def forward_card_ids(self, card_id: int) -> frozenset[int]:
        self._ensure_cache()
        st = self._cache.get(card_id)
        return self._forward.forward_card_ids(st.name) if st else frozenset()

    def ids_for_name(self, name: str) -> frozenset[int]:
        self._ensure_cache()
        if self._name_ids is None:
            self._name_ids = _name_index(self._cache)
        return self._name_ids.get(name, frozenset())
