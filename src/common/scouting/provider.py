"""Card-stat providers (see docs/scouting.md).

The Scout resolves opponent card ids to stats through a provider, so recognition stays
decoupled from the engine: runtime uses ``EngineCardStatProvider``; tests inject
``DictCardStatProvider`` (lib-free). ``.get(card_id)`` returns a ``CardStat`` or None.

This module owns the typed records (``CardStat`` / ``AttackStat``), their builders, and
the two adapters. The text->facts layer lives in ``card_text``; the name-keyed indexes in
``forward_index`` (ADR-0054). Every historical name stays importable from here.
"""
from __future__ import annotations

from dataclasses import dataclass

# Re-exports (import stability, ADR-0054): tests and tools import the parser battery and
# the private builders through this module — keep every name bound here.
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


@dataclass
class CardStat:
    cardId: int
    name: str = ""
    hp: int = 0
    ex: bool = False
    megaEx: bool = False
    aceSpec: bool = False              # ACE SPEC — one/deck, irreplaceable; CardStat feeds
                                       # 'protect the ACE SPEC' rules (e.g. Hero's Cape)
    hasAbility: bool = False           # Pokémon w/ Ability (CardData.skills, hp>0). Salvatore's fetch
                                       # clause excludes ability-bearing Evolutions (`no_ability`, card_effects.json)
    hpBonus: int = 0                   # flat HP a Tool grants holder (e.g. Hero's Cape +100),
                                       # parsed from skill text — engine has no structured field.
                                       # Primitive behind the general +HP-tool breakpoint model.
    retreatReduction: int = 0          # Energy a Tool shaves off its holder's Retreat Cost (Air Balloon:
                                       # {C}{C} -> 2), parsed from skill text. The SECOND Tool class the
                                       # ADR-0028 doctrine never modelled: worthless on a body that will
                                       # never retreat, so it belongs on the Active (ml f87). 0 otherwise.
                                       # SIGNED (Issue #306): NEGATIVE for a Tool that makes retreating
                                       # DEARER (Gravity Gemstone "{C} more" -> -1). One quantity, one
                                       # field — two fields for one quantity is how the sign gets
                                       # dropped. Consumers must not assume non-negative.
    attackCostReduction: int = 0       # Energy a Tool shaves off its holder's ATTACK costs (Hop's
                                       # Choice Band "cost {C} less" -> 1) — the pool's only such
                                       # grant, and the engine has no field for it at all. Gated by
                                       # `holderNameFamily` like every other modifier this Tool grants.
                                       # NO LIVE CONSUMER YET, deliberately (Issue #306): affordability
                                       # is asked ~20 times as `_attack_cost(aid) <= energy`, all
                                       # ATTACK-keyed, and a body-keyed discount cannot be threaded
                                       # through them without a redesign this issue does not carry —
                                       # nor safely, since a wrong credit manufactures a KO_SCORE-class
                                       # phantom. It is a T4 `state_value` input (Issue #263), which
                                       # is what the whole POC-A2.1 track produces; the census report
                                       # names it as parsed-not-priced so it can't read as covered.
    holderNameFamily: str | None = None  # the OWNER family the holder must belong to for this Tool's
                                       # static modifiers (hpBonus / damageBoost / attackCostReduction)
                                       # to apply — "Cynthia's" (Power Weight), "Hop's" (Choice Band).
                                       # rules.md §9: the owner prefix IS part of the printed name, so
                                       # this is an exact membership test over a KNOWN holder, not a
                                       # guess. None = unconditional. Test it with `applies_to_holder`.
    holderNoRuleBox: bool = False      # this Tool's static modifiers reach ONLY a holder with no
                                       # Rule Box — Brave Bangle (1175), the pool's one such card
                                       # (Issue #345). The SECOND holder gate, and unlike the family
                                       # above it is a property of the holder's own rules text, not
                                       # of its name, which is why it needed a field of its own. Over
                                       # this pool the predicate is EXACT rather than approximate —
                                       # "has a Rule Box" and `is_ex_body` are the same 151 bodies,
                                       # swept in tests/scouting/test_tool_holder_facts.py, which
                                       # fails the day a Radiant / V / VSTAR card arrives. Never read
                                       # this field directly; ask `applies_to_holder`.
    retreatFreeAtHp: int = 0           # remaining HP at or below which an attached Tool zeroes the
                                       # holder's Retreat Cost outright (Rescue Board: 30) — the
                                       # CONDITIONAL leg the flat read above could not carry
                                       # (ADR-0100 §8). 0 = no such clause.
    retreatFreeGrant: str | None = None  # a BOARD-LEVEL Ability granting no Retreat Cost, as the
                                       # predicate it scopes to: "basic" (Latias ex's Skyliner —
                                       # `slowking` runs it), "metal_attached" (Archaludon). The
                                       # granting body is not the one retreating, so no per-card
                                       # field could hold it and the engine supplies nothing
                                       # (`retreatCost` is CardData-only and static). None = no
                                       # readable grant, and the caller then charges the PRINTED
                                       # cost — fail-CLOSED, erring toward not retreating.
    recoil: int = 0                    # self-damage of card's HIGHEST-dmg attack (Hariyama Wild Press 210 -> 70),
                                       # parsed from text (no engine field). Feeds "does my nuke leave a free KO?"
    handSizeDamage: int = 0            # per-card dmg of "for each card in hand" atk (Powerful Hand: 2ctr=20);
                                       # printed damage=0, only way forward-doom/Posture sees threat. ep82754875
    benchSnipeDamage: int = 0          # unconditional bench-snipe dmg to ONE opp Benched (Jetting Blow->50);
                                       # Tool survival-turns math reads for benched carrier (ADR-0028)
    maxDamage: int = 0
    maxDamageCost: int | None = None   # energy count of HIGHEST-dmg attack (None if unknown); mirror of
                                       # minAttackCost. "fully online" threshold behind `build-active-wincon`.
    minAttackCost: int | None = None   # energy count of card's cheapest attack (None if unknown)
    minCostDamage: int = 0             # damage of cheapest-cost attack (best damage among
                                       # lowest-cost attacks) — for "does cheap attack KO" gating
                                       # (e.g. Jetting Blow 120 at 1 energy, not Nebula Beam 210 at CCC)
    attacks: tuple = ()                # (attackId, …) — lethal-attach lookahead reads cost/dmg to ask
                                       # "would attaching this Energy unlock a KO?" (Ignition->CCC->Nebula Beam)
    abilityEnergyTypes: tuple = ()     # EnergyType codes the card's Ability needs ATTACHED as fuel
                                       # ("if this Pokémon has any {D} Energy attached" — Munkidori
                                       # Adrena-Brain -> (7,)). The energy-routing complement to an
                                       # attack cost: a colour a body needs solely for its Ability
    weakness: int | None = None
    resistance: int | None = None
    energyType: int | None = None
    retreatCost: int = 0               # Energy to retreat (engine CardData.retreatCost) —
                                       # defensive stall-gust strands an energyless high-retreat body
    cardType: int | None = None        # CardType enum (ITEM=1, TOOL=2, SUPPORTER=3…) — distinguishes
                                       # Supporter gust (costs the slot) from free Item gust. ADR-0022 #12
    stage: str | None = None
    stage2: bool = False               # engine CardData.stage2 — a Stage 2 Pokémon (Gravity Mountain's
                                       # −30 HP hits exactly these; the opp-board stadium-tech read)
    evolvesFrom: str | None = None
    tera: bool = False                 # engine CardData.tera: takes NO damage from attacks while
                                       # BENCHED (32 in pool) — bench-snipe rider can never KO it
    # Damage-boost Trainer facts (the OHKO-line model's card tier), parsed like hpBonus. Pool 4:
    # Power Pro (Item {F}+30, stacks), Max Belt (Tool +50-vs-ex), Black Belt's (+40-vs-ex); Kieran
    # ("Choose 1" multi-mode) fail-closed.
    damageBoost: int = 0                    # flat "+N to opp Active" before W/R: Item/Supporter = the
                                            # turn it's played; Tool = while attached to the attacker
    damageBoostType: int | None = None      # attacker EnergyType gate ("your {F} Pokémon" -> 6); None=any
    damageBoostVsEx: bool = False           # defender "{ex}" gate — includes Mega ex (rulebook.txt:337)
    # Defender-side dmg facts (ADR-0032 G1), from Ability text — parametric fields the boolean
    # prevent_ex_damage tag can't carry (Sylveon 330 shows the tag can silently miss).
    preventsDamageFrom: str | None = None   # "ex" (Crustle/Sylveon) | "basic_ex" (Farigiraf ex) —
                                            # zeroes matching attacker's damage unless attack
                                            # ignoresEffects (Nebula Beam)
    preventsDamageAtLeast: int = 0          # threshold prevention (Drednaw: damage >=200 -> 0); 0=off
    damageReduction: int = 0                # flat always-on "takes N less damage" AFTER W/R
                                            # (Mudsdale/Bouffalant ex/Mega Diancie ex -30)
    damageReductionTypes: tuple | None = None  # attacker EnergyTypes reduction scoped to
                                            # (Dewgong: {R}/{W} -> (2, 3)); None = all attackers
    synthetic: bool = False             # test-only marker: this row is an arbitrary body using a
                                       # convenient real id, not a source claim about that card.

    # --- single-card interpretation (ADR-0056): the questions consumers used to re-derive
    # from raw fields. Ports of the retired call-site idioms — byte-faithful, not redesigns.

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
        """A Stadium card. The last `CardType` with no predicate of its own — added for the FETCH
        clause target class `stadium` (Secret Box, Colress's Tenacity), so the closure asks the
        question through `CardStat` like every other class rather than re-spelling the enum code."""
        return self.cardType == _STADIUM

    @property
    def is_basic_energy(self) -> bool:
        return self.cardType == _BASIC_ENERGY

    @property
    def is_special_energy(self) -> bool:
        """A Special Energy — one whose PROVISION is card text rather than one unit of its own
        colour (Ignition Energy provides {C}{C}{C} on an Evolution). The Attach Budget reads the
        amount off the `provides:N` Function Tag; ``energyType`` still gives the colour."""
        return self.cardType == _SPECIAL_ENERGY

    @property
    def is_energy(self) -> bool:
        """Any Energy card (Basic or Special)."""
        return self.cardType in (_BASIC_ENERGY, _SPECIAL_ENERGY)

    @property
    def is_typed_basic_energy(self) -> bool:
        """A Basic Energy with a concrete type — the attach-type family's unit."""
        return self.cardType == _BASIC_ENERGY and self.energyType is not None

    def applies_to_holder(self, holder: "CardStat | None") -> bool:
        """Do THIS Tool's static modifiers (``hpBonus`` / ``damageBoost`` / ``attackCostReduction``)
        reach ``holder`` — the body it is (or would be) attached to?

        The one place EVERY holder gate is evaluated, so a consumer that reads any gated amount
        reads its conditions through the same test (Issue #306). True for every unrestricted Tool, so
        an ungated consumer's behaviour is unchanged. An unknown holder against a real gate is
        False: fail-CLOSED, never credit a body we cannot identify.

        Two gates today, ANDed, and adding the second (Issue #345) is why they are evaluated here
        rather than at the call sites. There are FOUR consumers — ``state_model._SideBase
        .damage_boosts``, ``Pilot._boost_lethal_tactical``, ``doctrine_tool._tool_reaches`` (the
        deploy picker) and ``planner._gamble_pump_ko_classes``'s ``_crosses`` — and none of them was
        touched when the second gate landed. A gate added at three of them is a gate the fourth
        silently ignores.

        * ``holderNameFamily`` — the owner NAME family ("the Hop's Pokémon this card is attached to").
        * ``holderNoRuleBox`` — the holder must have no Rule Box (Brave Bangle). Over this pool that
          is exactly ``is_ex_body``: `docs/rulebook.txt` names Pokémon ex (L337, Mega ex included),
          Radiant (L364) and V / V-UNION (L391-392) as the Rule-Box categories, and a sweep of all
          1061 bodies finds only the first — pinned, so the day that stops being true the test fails
          instead of the boost quietly over-crediting.
        """
        # `getattr` with a True default rather than `holder.is_ex_body`, to match the family leg's
        # defensive read one line down: a holder we cannot interrogate must fail the SAME way on
        # both gates, and for a benefit that way is "has a Rule Box" — refuse.
        if self.holderNoRuleBox and (holder is None or getattr(holder, "is_ex_body", True)):
            return False
        return name_in_family(getattr(holder, "name", None), self.holderNameFamily)

    def can_pay_cheapest(self, energy: int) -> bool:
        """Attached-Energy count covers the cheapest attack — the fail-CLOSED affordability
        idiom (``(minAttackCost or 99) <= energy``): unknown (and 0-cost, pinned quirk) costs
        read unaffordable, so a my-side claim is never assumed."""
        return (self.minAttackCost or 99) <= energy


class DictCardStatProvider:
    """In-memory provider for tests and precomputed caches."""

    def __init__(self, stats: dict[int, CardStat], attacks: dict[int, "AttackStat"] | None = None):
        self._stats = stats
        self._attacks = attacks or {}       # attackId -> AttackStat (the attack-record half, ADR-0056)
        self._forward: _ForwardIndex | None = None
        self._name_ids: dict[str, frozenset[int]] | None = None

    def get(self, card_id: int) -> CardStat | None:
        return self._stats.get(card_id)

    def attack(self, attack_id) -> "AttackStat | None":
        """The per-attack effect record (ADR-0032 *Attack Effect*), or None for an unknown attack."""
        return self._attacks.get(attack_id)

    def warm(self) -> None:
        """Interface parity with the engine adapter's pregame-window build hook — nothing to build."""

    def ids_for_name(self, name: str) -> frozenset[int]:
        """Card ids printed under ``name`` — the reverse of ``CardStat.name`` (names aren't unique).
        The Matchup Brief consumer's name->id bridge (ADR-0027, ``briefs.resolve_brief_cards``);
        empty for an unknown name."""
        if self._name_ids is None:
            self._name_ids = _name_index(self._stats)
        return self._name_ids.get(name, frozenset())

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


@dataclass
class AttackStat:
    """Per-attack effect record (ADR-0032 *Attack Effect*): the attack-keyed tier beside the
    card-keyed ``CardStat``. Folds the printed damage/cost with the rider parsers and the
    ignore-family flags so the damage oracle reads ONE record per attack. Parsed fields are
    seeds — the engine audit verifies and corrects them through ``build_attack_stats`` overrides."""
    attackId: int
    damage: int = 0
    cost: int = 0                      # energy count (efficiency tiebreaks, affordability)
    energyTypes: tuple = ()            # the cost's per-slot Energy TYPE codes (EnergyType enum; 0 =
                                       # colorless/any) — e.g. Phantom Dive [Fire, Psychic]. Backs the
                                       # type-aware attach (attach the type the wincon still LACKS, not a redundant one)
    recoil: int = 0                    # unconditional self-damage (ADR-0022 #2)
    benchSnipe: int = 0                # unconditional opp-bench rider (ADR-0022 #14); ignores W/R
    benchSpread: int = 0               # distributable opp-bench counter spread total (Phantom Dive
                                       # "put N counters in any way you like" -> N*10); ignores W/R.
                                       # The placement policy distributes it; count = benchSpread // 10
    ignoresWeakness: bool = False
    ignoresResistance: bool = False
    ignoresEffects: bool = False       # pierces defender-side effects incl. damage-prevention
                                       # Abilities (Crustle) — Nebula-Beam-vs-Crustle fact
    damageMin: int | None = None       # sound FLOOR of conditional/coin attack ("If tails, this
                                       # attack does nothing" -> 0); None = deterministic.
    damageMax: int | None = None       # Lethal Solver reads floor (never lock phantom win),
                                       # Incoming reads ceiling (worst case). Text-seeded
                                       # (parse_attack_damage_bounds), audit-corrected (coin fork).
    scaleVar: str | None = None        # visible-state scaler (ADR-0032 Damage Formula): damage =
                                       # printed + scalePerUnit x count(scaleVar), attacker-relative
    scalePerUnit: int = 0              # vars: atk/def_hand, atk/def_active_energy, atk/def_bench,
                                       # atk_discard_energy — EXACT (all visible incl. both discards)
    scaleEnergyType: int | None = None  # atk_discard_energy's type filter (Riptide Basic {W} -> 3);
                                       # None = count EVERY Energy card in attacker's discard
    hiddenPerUnit: int = 0             # HIDDEN-state scaler (deck-discard family: Hammer-lanche /
                                       # Misty's Lapras / Ground Burn): damage += perUnit x units,
    hiddenSample: int = 0              # units unknowable closed-form — "max" assumes every sampled card
                                       # fuels (Incoming ceiling); "min"/"exact" 0 unless deck tracker has hidden_units
    hiddenEnergyType: int | None = None  # deck facts + Basic-{X} filter -> oracle computes pigeonhole floor/EV
    recoverN: int = 0                  # energy-accel rider ("Attach up to N Basic {X} from ZONE"):
                                       # max cards attached (Aura Jab discard / Turbo Flare deck)
    recoverEnergyType: int | None = None   # the rider's Basic-{X} filter (None = any Basic Energy)
    recoverTarget: str | None = None   # scope "self"/"bench"/"any" — Tactical credits
                                       # min(recoverN, matching zone fuel, recipient need) as development
    recoverSource: str | None = None   # the rider's fuel zone: "discard" (visible pile — Aura Jab) or
                                       # "deck" (whole-deck search — Turbo Flare); None = no rider.
                                       # The fuel bound branches on this (`_recover_units`)
    requiresBench: tuple | None = None  # attack does NOTHING unless ALL these names sit on attacker's
                                       # Bench (Cosmic Beam/Lunatone, Guardian Burst/Uxie+Azelf;
                                       # pool 2). Oracle zeroes exact/min on the live board; "max"
                                       # keeps printed (Incoming: they can bench the partner first)
    selfReturn: bool = False           # attack scoops its OWN Pokémon (+ attached) back to hand
                                       # (Meowth ex Tuck Tail). The escape/KO-deny fact: a doomed
                                       # multi-prize Active can bounce to deny the prize (Tactical _SELF_RETURN_ESCAPE)
    # Transient next-turn grants (ADR-0033): what USING this attack grants for one turn — tracked
    # match-scoped from ATTACK logs (common/transients.py), obs has no effect state.
    nextTurnReduction: int = 0         # defender-side: "takes N less damage" next turn (Frost Barrier)
    nextTurnPreventAll: bool = False   # defender-side: "prevent all damage done to this Pokémon"
    nextTurnSelfLock: bool = False     # attacker-side: "this Pokémon can't attack / use attacks"
    nextTurnSameAttackLock: bool = False   # attacker-side: "can't use <THIS attack>" next turn
    nextTurnSelfBonus: int = 0         # attacker-side: this Pokémon's attack does +N next turn
    # NB the pool's 22 "Defending Pokémon can't retreat" attacks are deliberately NOT tracked: the
    # engine ENFORCES the lock by omitting RETREAT from the locked side's menu (probed 2026-07-02,
    # tests/sim/test_retreat_lock_engine.py), so a menu-driven this-turn Pilot gains nothing from a
    # field — re-add a parse only alongside a real consumer (ADR-0033).

    @property
    def is_deterministic(self) -> bool:
        """Damage is fixed once any ``requiresBench`` condition holds — no coin fork, no
        visible/hidden scaling (``damageMax == damage`` with every scaling term zero). The
        precondition for reading ``bound="exact"`` where ``bound="min"`` would be vacuously 0.
        Port of ``Pilot._attack_is_deterministic`` (ADR-0056), comparison kept byte-faithful:
        a record whose ``damageMax`` stays ``None`` does NOT read deterministic."""
        return bool(self.damageMax == self.damage and self.scaleVar is None
                    and not self.scalePerUnit and not self.hiddenPerUnit)

    @property
    def handSizeDamage(self) -> int:
        """Per-card damage of a hand-size-scaling attack (Powerful Hand: 2 counters = 20), 0
        otherwise — the threat the printed damage (0) hides.

        DERIVED from the Damage Formula's scaling term rather than stored (Issue #213). It used
        to be parsed by its own regex pair over the very sentence `_SCALE_FAMILIES` already
        matches, so one card fact had two parsers that were free to disagree; and because a
        stored field is fixed at parse time, an engine-fitted `atk_hand` override would have
        moved the scaler while leaving this behind. As a property it cannot drift from the
        scaler and it honours overrides for free.
        """
        return self.scalePerUnit if self.scaleVar == "atk_hand" else 0


def load_attack_overrides(path=None) -> dict:
    """The engine-derived override table (``attack_overrides.json``, generated by the audit —
    tools/sim/generate_attack_overrides.py) as ``{int attackId: {field: value}}`` for
    ``build_attack_stats``. Fail-safe: missing/unreadable file -> {} (parsed seeds only)."""
    import json
    from pathlib import Path
    p = Path(path) if path is not None else Path(__file__).resolve().parents[1] / "attack_overrides.json"
    try:
        return {int(k): v for k, v in json.loads(p.read_text(encoding="utf-8")).items()}
    except Exception:
        return {}


def build_attack_stats(attacks, overrides: dict | None = None) -> dict[int, AttackStat]:
    """Pure transform: engine ``Attack`` records → ``{attackId: AttackStat}`` (ADR-0032).

    Args:
        attacks: engine ``Attack`` records (``attackId``/``damage``/``energies``/``text``).
        overrides: ``{attackId: {field: value}}`` hand-authored/audit-generated corrections,
            applied AFTER parsing (an override always beats a parsed value). Unknown attack
            ids are ignored — overrides never invent attacks.

    Returns:
        The attack-stat table. Lib-free (testable without the engine).
    """
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
            elif effect:                # free-target "does N damage to 1 of your opponent's Pokémon"
                free_target_snipe = effect[0]   # (Cruel Arrow) — it can KO ANY opp Pokémon incl the Bench,
                w = r = e = True                # so value it as a full-damage bench snipe (ignores W/R on bench)
        if scaling and scaling[2]:      # counter-placer: counters aren't damage — no W/R, no
            w = r = e = True            # prevention (Powerful Hand lands through Crustle)
        table[a.attackId] = AttackStat(
            attackId=a.attackId, damage=printed,
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
        # ONE parse of the sentence (Issue #213): the card-level roll-up reads the Damage
        # Formula's scaling term, exactly as AttackStat.handSizeDamage does.
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
        # cost of highest-damage attack (min cost among attacks tying for max damage —
        # cheapest way to reach the big hit); None when no attack's cost known.
        max_dmg_costs = [cost[aid] for aid in c.attacks if aid in cost and dmg.get(aid, 0) == max_dmg]
        max_dmg_cost = min(max_dmg_costs) if max_dmg_costs else None
        # recoil of highest-damage attack (nuke most likely to self-KO): max over attacks
        # tying for max damage. 0 when no attack has unconditional recoil.
        recoil = max((recoil_by_aid.get(aid, 0) for aid in c.attacks if dmg.get(aid, 0) == max_dmg),
                     default=0)
        prevents_from, prevents_at_least, dmg_reduction, reduction_types = parse_card_defense(c)
        boost, boost_type, boost_vs_ex = parse_card_damage_boost(c)
        cache[c.cardId] = CardStat(
            cardId=c.cardId, name=c.name, hp=int(c.hp),
            ex=bool(c.ex), megaEx=bool(c.megaEx), aceSpec=bool(getattr(c, "aceSpec", False)),
            hasAbility=bool(int(c.hp) > 0 and getattr(c, "skills", None)),   # Pokémon w/ Ability skill
            hpBonus=_parse_tool_hp_bonus(c),
            retreatReduction=_parse_tool_retreat_reduction(c),
            attackCostReduction=_parse_tool_attack_cost_reduction(c),
            holderNameFamily=_parse_tool_holder_family(c),
            holderNoRuleBox=_parse_tool_holder_no_rule_box(c),
            retreatFreeAtHp=_parse_tool_retreat_free_at_hp(c),
            retreatFreeGrant=_parse_retreat_free_grant(c),
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
        """Build the stat cache + attack-record table + forward index together, once. The single
        build site so the three never diverge — ``get``, ``attack`` and ``forward_max_damage`` all
        go through here. The attack table folds the shipped audit overrides (ADR-0032), so the
        adapter — not each agent's main.py — owns the one attack-fact build (ADR-0056)."""
        if self._cache is None:
            from cg.api import all_attack, all_card_data  # runtime only
            attacks = all_attack()
            self._cache = _build_cache(all_card_data(), attacks)
            self._attack_stats = build_attack_stats(attacks, load_attack_overrides())
            self._forward = _build_forward_index(self._cache)

    def warm(self) -> None:
        """Explicit pregame-window build (the agents call this at import, replacing their own
        eager table builds) — just the lazy build, forced now. Idempotent."""
        self._ensure_cache()

    def get(self, card_id: int) -> CardStat | None:
        self._ensure_cache()
        return self._cache.get(card_id)

    def attack(self, attack_id) -> AttackStat | None:
        """The per-attack effect record (ADR-0032 *Attack Effect*), audit-overridden; None for an
        unknown attack id."""
        self._ensure_cache()
        return self._attack_stats.get(attack_id)

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

    def ids_for_name(self, name: str) -> frozenset[int]:
        """Card ids printed under ``name`` (see ``DictCardStatProvider.ids_for_name``)."""
        self._ensure_cache()
        if self._name_ids is None:
            self._name_ids = _name_index(self._cache)
        return self._name_ids.get(name, frozenset())
