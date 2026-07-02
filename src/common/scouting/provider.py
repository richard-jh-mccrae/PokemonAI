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
    hasAbility: bool = False           # a Pokémon carrying an Ability (engine CardData.skills, hp > 0) —
                                       # e.g. Cinderace's Explosiveness. The structural basis for a
                                       # rush-evolve tutor's fetch-filter: Salvatore fetches only an
                                       # ability-LESS Evolution ("a card that has no Abilities and evolves
                                       # from 1 of your Pokémon"), so this excludes an ability-bearing
                                       # Evolution from its whiff/redundancy target set (cf _FETCH_FILTERS).
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
    tera: bool = False                 # engine CardData.tera: takes NO damage from attacks while
                                       # BENCHED (32 in pool) — a bench-snipe rider can never KO it
    # Defender-side damage facts (ADR-0032 G1), parsed from Ability text — the parametric fields the
    # boolean prevent_ex_damage tag can't carry (and Sylveon 330 shows the tag can silently miss):
    preventsDamageFrom: str | None = None   # "ex" (Crustle/Sylveon) | "basic_ex" (Farigiraf ex) —
                                            # zeroes a matching attacker's damage unless the attack
                                            # ignoresEffects (Nebula Beam)
    preventsDamageAtLeast: int = 0          # threshold prevention (Drednaw: damage >=200 -> 0); 0=off
    damageReduction: int = 0                # flat always-on "takes N less damage" AFTER W/R
                                            # (Mudsdale/Bouffalant ex/Mega Diancie ex -30)
    damageReductionTypes: tuple | None = None  # attacker EnergyTypes the reduction is scoped to
                                            # (Dewgong: {R}/{W} -> (2, 3)); None = all attackers


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
# An attack whose damage "isn't affected by ... any effects on your opponent's Active Pokémon" (Mega
# Starmie's Nebula Beam, Crustle's Superb Scissors). Such an attack bypasses a damage-PREVENTION Ability
# on the Active (Crustle's Mysterious Rock Inn), which the closed-form combat math otherwise treats as an
# absolute wall. `[^.]*` keeps the clause within one sentence; `.` covers the é / apostrophe (cross-platform).
_IGNORES_ACTIVE_EFFECTS_RE = re.compile(
    r"isn.t affected by[^.]*effects on your opponent.s Active Pok.mon")


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


def parse_attack_ignores_active_effects(text: str) -> bool:
    """True if this attack's damage IGNORES any effects on the opponent's Active Pokémon, e.g. Mega
    Starmie's Nebula Beam "This attack's damage isn't affected by Weakness or Resistance, or by any
    effects on your opponent's Active Pokémon." → True. Such an attack lands its full damage THROUGH a
    defender's damage-prevention Ability on the Active (Crustle's Mysterious Rock Inn, which zeroes
    ex-attack damage) — the ep83054602 f17 missed win. Any other attack → False (the SAFE direction:
    under-crediting never wrongly upgrades a whiff to a KO)."""
    return bool(_IGNORES_ACTIVE_EFFECTS_RE.search((text or "").replace("\n", " ")))


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


# Defender-side ability families (ADR-0032 G1). Pool-verified: 2 prevent-from-ex (Crustle 345,
# Sylveon 330 — Sylveon is UNTAGGED, the field closes that gap), 1 Basic-ex variant (Farigiraf ex),
# 1 threshold (Drednaw >=200), 3 unconditional -30 after W/R (Mudsdale/Bouffalant ex/Mega Diancie
# ex). Dewgong's attacker-TYPE-conditional -30 and the fossil's bench-only prevention parse to
# nothing (hand-review ledger); "Prevent all effects … (Damage is not an effect.)" is
# damage-irrelevant and must not match.
_PREVENT_EX_RE = re.compile(
    r"Prevent all damage done to this Pok.mon by attacks from your opponent.s Pok.mon \{ex\}")
_PREVENT_BASIC_EX_RE = re.compile(
    r"Prevent all damage done to this Pok.mon by attacks from your opponent.s Basic Pok.mon \{ex\}")
_PREVENT_THRESHOLD_RE = re.compile(
    r"Prevent all damage done to this Pok.mon by attacks from your opponent.s Pok.mon if that "
    r"damage is (\d+) or more")
_TAKES_LESS_RE = re.compile(
    r"This Pok.mon takes (\d+) less damage from attacks \(after applying Weakness and Resistance\)")
# Dewgong's type-scoped variant: "takes 30 less damage from attacks from your opponent's {R} or
# {W} Pokémon (after applying …)" — the reduction applies only to attackers of the named types.
_TAKES_LESS_TYPED_RE = re.compile(
    r"This Pok.mon takes (\d+) less damage from attacks from your opponent.s \{(\w)\}"
    r"(?: or \{(\w)\})? Pok.mon")
_TYPE_LETTER = {"G": 1, "R": 2, "W": 3, "L": 4, "P": 5, "F": 6, "D": 7, "M": 8}  # EnergyType enum


def parse_card_defense(card) -> tuple[str | None, int, int, tuple | None]:
    """Defender-side damage facts read off a card's Ability text (ADR-0032 G1).

    Args:
        card: an engine ``CardData``-shaped record (``skills`` with ``text``).

    Returns:
        ``(preventsDamageFrom, preventsDamageAtLeast, damageReduction, damageReductionTypes)``
        — ``damageReductionTypes`` is None for an unconditional reduction, a tuple of attacker
        EnergyType ids for a type-scoped one (Dewgong {R}/{W} → ``(2, 3)``).
    """
    prevents, threshold, reduction, types = None, 0, 0, None
    for s in (getattr(card, "skills", None) or []):
        text = getattr(s, "text", None)
        if text is None and isinstance(s, dict):
            text = s.get("text")
        t = (text or "").replace("\n", " ")
        if _PREVENT_BASIC_EX_RE.search(t):
            prevents = "basic_ex"
        elif _PREVENT_EX_RE.search(t):
            prevents = "ex"
        m = _PREVENT_THRESHOLD_RE.search(t)
        if m:
            threshold = int(m.group(1))
        m = _TAKES_LESS_TYPED_RE.search(t)
        if m:
            reduction = int(m.group(1))
            types = tuple(_TYPE_LETTER[g] for g in (m.group(2), m.group(3))
                          if g and g in _TYPE_LETTER)
        else:
            m = _TAKES_LESS_RE.search(t)
            if m:
                reduction = int(m.group(1))
    return (prevents, threshold, reduction, types)


# The ignore-family (ADR-0032): "This attack's damage isn't affected by …" — the per-attack damage
# modifiers the card-level model can't express (Nebula Beam lands 210 through Crustle's ex-damage
# prevention because it ignores *effects*; Jetting Blow doesn't). Whole-sentence, damage-scoped:
# Conkeldurr's "ignore all Energy in this attack's cost" is a COST modifier and must not match.
# "This damage isn't affected by …" (Arboliva) and "effects on those Pokémon" (Iron Crown's snipe)
# are covered variants. Text is the SEED — the engine audit verifies/corrects via overrides.
_IGNORES_RE = re.compile(r"\bThis (?:attack.s )?damage isn.t affected by ([^.]+)\.")


def parse_attack_ignores(text: str) -> tuple[bool, bool, bool]:
    """Damage-modifier ignore flags read from attack text (ADR-0032).

    Args:
        text: the attack's free-text effect.

    Returns:
        ``(ignores_weakness, ignores_resistance, ignores_effects)`` — "effects" is the
        defender-side effect family (damage-prevention Abilities, damage-reduction attack
        effects). All-False when no damage-scoped ignore sentence is present.
    """
    w = r = e = False
    for m in _IGNORES_RE.finditer(text or ""):
        clause = m.group(1)
        w = w or "Weakness" in clause
        r = r or "Resistance" in clause
        e = e or "effects" in clause
    return (w, r, e)


@dataclass
class AttackStat:
    """Per-attack effect record (ADR-0032 *Attack Effect*): the attack-keyed tier beside the
    card-keyed ``CardStat``. Folds the printed damage/cost with the rider parsers and the
    ignore-family flags so the damage oracle reads ONE record per attack. Parsed fields are
    seeds — the engine audit verifies and corrects them through ``build_attack_stats`` overrides."""
    attackId: int
    damage: int = 0
    cost: int = 0                      # energy count (efficiency tiebreaks, affordability)
    recoil: int = 0                    # unconditional self-damage (ADR-0022 #2)
    benchSnipe: int = 0                # unconditional opp-bench rider (ADR-0022 #14); ignores W/R
    handSizeDamage: int = 0            # per-card hand-size scaling (printed damage hides it)
    ignoresWeakness: bool = False
    ignoresResistance: bool = False
    ignoresEffects: bool = False       # pierces defender-side effects incl. damage-prevention
                                       # Abilities (Crustle) — the Nebula-Beam-vs-Crustle fact
    damageMin: int | None = None       # sound FLOOR of a conditional/coin attack ("If tails, this
                                       # attack does nothing" -> 0); None = deterministic. The
    damageMax: int | None = None       # Lethal Solver reads the floor (never lock a phantom win),
                                       # Incoming reads the ceiling (worst case). Text-seeded
                                       # (parse_attack_damage_bounds), audit-corrected (coin fork).
    scaleVar: str | None = None        # visible-state scaler (ADR-0032 Damage Formula): damage =
                                       # printed + scalePerUnit x count(scaleVar), attacker-relative
    scalePerUnit: int = 0              # vars: atk_hand / def_hand / def_active_energy /
                                       # atk_active_energy / atk_bench / def_bench /
                                       # atk_discard_energy. EXACT at decision time (all visible —
                                       # BOTH discard piles are open information); counter-placers
                                       # also carry all three ignore flags (counters aren't damage).
    scaleEnergyType: int | None = None  # atk_discard_energy's type filter (Riptide Basic {W} -> 3);
                                       # None = count EVERY Energy card in the attacker's discard
    hiddenPerUnit: int = 0             # HIDDEN-state scaler (deck-discard family: Hammer-lanche /
                                       # Misty's Lapras / Ground Burn): damage += perUnit x units,
    hiddenSample: int = 0              # units unknowable closed-form — bound "max" assumes every
                                       # sampled card fuels (perUnit x hiddenSample, the Incoming
                                       # ceiling); "min"/"exact" add 0 (sound floor) unless the
                                       # deck tracker supplies context["hidden_units"], OR exact
    hiddenEnergyType: int | None = None  # deck facts + this Basic-{X} filter let the oracle compute
                                       # the pigeonhole floor / hypergeometric EV itself.
    # Transient next-turn grants (ADR-0033): what USING this attack grants for one turn — tracked
    # match-scoped from ATTACK logs (common/transients.py), the obs exposes no effect state.
    nextTurnReduction: int = 0         # defender-side: "takes N less damage" next turn (Frost Barrier)
    nextTurnPreventAll: bool = False   # defender-side: "prevent all damage done to this Pokémon"
    nextTurnSelfLock: bool = False     # attacker-side: "this Pokémon can't attack / use attacks"
    nextTurnSameAttackLock: bool = False   # attacker-side: "can't use <THIS attack>" next turn
    nextTurnSelfBonus: int = 0         # attacker-side: this Pokémon's attack does +N next turn
    nextTurnDefenderRetreatLock: bool = False  # opponent-side: "the Defending Pokémon can't retreat"


# The conditional-damage families (ADR-0032 Damage Formula, the bounds half). Verified pool-wide:
# 26 "…, this attack does nothing" conditionals (11 coin-tails + 15 board conditions — Sawk, Cosmic
# Beam), 26 "If heads, +N more", 2 "You may do N more". A does-nothing clause floors the attack to
# 0; a bonus clause lifts the ceiling by N. Deterministic attacks parse to None (no bounds).
_DOES_NOTHING_RE = re.compile(r", this attack does nothing")
# Any conditional/optional flat bonus lifts the ceiling: coin heads, board conditions ("If your
# opponent's Active is a Pokémon {ex}, …"), optional pay-offs ("You may … to have this attack do
# N more"). A *for each* bonus is a SCALER, not a flat bonus — the lookahead rejects it.
_BONUS_RE = re.compile(
    r"(?:If [^.]{1,80}?, this attack does|You may do|to have this attack do) (\d+) more damage"
    r"(?! for each)")


def parse_attack_damage_bounds(text: str, printed: int) -> tuple[int, int] | None:
    """Sound (floor, ceiling) damage bounds of a conditional attack, from its text (ADR-0032).

    Args:
        text: the attack's free-text effect.
        printed: the attack's printed damage.

    Returns:
        ``(min, max)`` — floor 0 when a does-nothing clause exists, ceiling ``printed + N`` when a
        coin/optional bonus exists — or None for a deterministic attack (no conditional clause).
    """
    t = (text or "").replace("\n", " ")
    lo, hi, found = printed, printed, False
    if _DOES_NOTHING_RE.search(t):
        lo, found = 0, True
    m = _BONUS_RE.search(t)
    if m:
        hi, found = printed + int(m.group(1)), True
    return (lo, hi) if found else None


# The visible-state scaler families (ADR-0032 Damage Formula, the exact half). Pool-verified: 1
# own-hand counter-placer (Powerful Hand), 2 opp-hand damage (Mind Ruler), 8 opp-active-energy,
# 13 own-energy. Attacker-relative var names, so Incoming reuses the same record unchanged.
_SCALE_FAMILIES = (
    (re.compile(r"Place (\d+) damage counters? on your opponent.s Active Pok.mon for each card in "
                r"your hand"), "atk_hand", 10, True),
    (re.compile(r"does (\d+) (?:more )?damage for each card in your opponent.s hand"),
     "def_hand", 1, False),
    (re.compile(r"does (\d+) (?:more )?damage for each card in your hand"), "atk_hand", 1, False),
    (re.compile(r"does (\d+) (?:more )?damage for each Energy attached to your opponent.s Active "
                r"Pok.mon"), "def_active_energy", 1, False),
    (re.compile(r"does (\d+) (?:more )?damage for each(?: basic)?(?: \{\w\})? Energy attached to "
                r"this Pok.mon"), "atk_active_energy", 1, False),
    (re.compile(r"does (\d+) (?:more )?damage for each of your opponent.s Benched Pok.mon"),
     "def_bench", 1, False),
    (re.compile(r"does (\d+) (?:more )?damage for each of your Benched Pok.mon"),
     "atk_bench", 1, False),
    # the attacker's DISCARD pile — open information for BOTH players, so an opponent's Riptide
    # is exactly priceable from THEIR visible discard. Optional Basic-{X} type filter.
    (re.compile(r"Put (\d+) damage counters? on 1 of your opponent.s Pok.mon for each Basic "
                r"\{(\w)\} Energy card in your discard pile"), "atk_discard_energy", 10, True),
    (re.compile(r"does (\d+) (?:more )?damage for each(?: Basic)?(?: \{(\w)\})? Energy card[s]? "
                r"in your discard pile"), "atk_discard_energy", 1, False),
    # damage counters already sitting on a body (maxHp − hp, both visible) — 8 self + 7 defender
    (re.compile(r"does (\d+) (?:more )?damage for each damage counter on this Pok.mon"),
     "atk_self_counters", 1, False),
    (re.compile(r"does (\d+) (?:more )?damage for each damage counter on your opponent.s Active "
                r"Pok.mon"), "def_counters", 1, False),
    # Prize cards taken so far (start − remaining, both visible) — 6 attacks, direction-split
    (re.compile(r"does (\d+) (?:more )?damage for each Prize card you have (?:already )?taken"),
     "atk_prizes_taken", 1, False),
    (re.compile(r"does (\d+) (?:more )?damage for each Prize card your opponent has "
                r"(?:already )?taken"), "def_prizes_taken", 1, False),
)


def parse_attack_scaling(text: str) -> tuple[str, int, bool, int | None] | None:
    """Visible-state damage scaling read from attack text (ADR-0032 Damage Formula).

    Args:
        text: the attack's free-text effect.

    Returns:
        ``(scaleVar, perUnit, isCounters, energyType)`` — perUnit in DAMAGE (a counter is 10);
        ``energyType`` only for the discard family's Basic-{X} filter (None = untyped / not a
        discard scaler) — or None when the attack doesn't scale on a supported visible variable.
    """
    t = (text or "").replace("\n", " ")
    for pat, var, mult, counters in _SCALE_FAMILIES:
        m = pat.search(t)
        if m:
            etype = None
            if pat.groups >= 2 and m.group(2):
                etype = _TYPE_LETTER.get(m.group(2))
            return (var, int(m.group(1)) * mult, counters, etype)
    return None


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


# Fixed EFFECT damage (ADR-0032 ledger sweep): a printed-0 attack whose number lives in the text —
# chosen-target damage ("This attack does N damage to 1/2/each of your opponent's Pokémon") or
# counter-puts ("Put N damage counters on … your opponent's Pokémon", = N x 10, counters bypass
# W/R and prevention). Bench-only riders ("… Benched Pokémon") and defender-conditional targets
# ("… Pokémon {ex}") are NOT this family. The Active is always a choosable target, so the amount
# is the attack's Active damage.
_EFFECT_DMG_RE = re.compile(
    r"This attack does (\d+) damage to (?:\d+|each) of your opponent.s Pok.mon(?! \{)(?! for each)")
_COUNTER_PUT_RE = re.compile(
    r"Put (\d+) damage counters? on (?:\d+ of |each of )?your opponent.s Pok.mon(?! \{)(?! for each)")


def parse_attack_effect_damage(text: str) -> tuple[int, bool] | None:
    """Fixed effect damage of a printed-0 attack: ``(active_damage, is_counters)`` or None.

    Args:
        text: the attack's free-text effect.

    Returns:
        e.g. "does 100 damage to 1 of your opponent's Pokémon" → ``(100, False)``;
        "Put 4 damage counters on your opponent's Pokémon in any way you like" → ``(40, True)``.
    """
    t = (text or "").replace("\n", " ")
    m = _EFFECT_DMG_RE.search(t)
    if m:
        return (int(m.group(1)), False)
    m = _COUNTER_PUT_RE.search(t)
    if m:
        return (int(m.group(1)) * _DAMAGE_PER_COUNTER, True)
    return None


# The hidden-state deck-discard scalers (ADR-0032 Damage Formula, class C). Pool-verified: exactly
# 3 — Hammer-lanche (top 6 own), Misty's Lapras (top 7 own), Ground Burn (top 1 of EACH deck → a
# 2-card sample). The units are hidden card order, so only bounds are closed-form.
_HIDDEN_SCALE_RE = re.compile(
    r"Discard the top (\d+ )?cards? of (your|each player.s) deck.{0,60}?does (\d+) (?:more )?damage "
    r"for each(?: Basic \{(\w)\} Energy card)?", re.S)


def parse_attack_hidden_scale(text: str) -> tuple[int, int, int | None] | None:
    """Hidden-state deck-discard scaling: ``(per_unit, sampled_count, basicEnergyType|None)``.

    Args:
        text: the attack's free-text effect.

    Returns:
        e.g. Hammer-lanche → ``(100, 6, 3)`` (Basic {W} filter — with exact deck facts the
        oracle computes a pigeonhole floor/EV); Ground Burn → ``(140, 2, None)``. None when the
        attack isn't a deck-discard scaler.
    """
    m = _HIDDEN_SCALE_RE.search((text or "").replace("\n", " "))
    if not m:
        return None
    n = int(m.group(1)) if m.group(1) else 1
    if m.group(2).startswith("each"):
        n *= 2                                       # one card off EACH player's deck
    etype = _TYPE_LETTER.get(m.group(4)) if m.group(4) else None
    return (int(m.group(3)), n, etype)


# Transient next-turn families (ADR-0033). Pool-verified: 17 defender takes-less, 6 prevent-all,
# 23 self-locks ("can't attack" / "can't use attacks"), 18 self-referential named locks, 2 self
# next-turn bonuses, 22 Defending-can't-retreat. Coin-gated variants ("Flip a coin. If heads,
# during…") are NOT parsed — the flip isn't knowable, and under-crediting a possible shield is the
# safe direction. Named locks are captured only when the named attack IS this attack (self-
# referential); a cross-attack lock stays on the ledger.
_T_REDUCTION_RE = re.compile(
    r"During your opponent.s next turn, this Pok.mon takes (\d+) less damage")
_T_PREVENT_RE = re.compile(
    r"During your opponent.s next turn, prevent all damage done to this Pok.mon")
_T_SELF_LOCK_RE = re.compile(
    r"During your next turn, this Pok.mon can.t (?:attack|use attacks)\.")
_T_NAMED_LOCK_RE = re.compile(r"During your next turn, this Pok.mon can.t use ([^.]+)\.")
_T_SELF_BONUS_RE = re.compile(
    r"During your next turn, (?:this Pok.mon.s )?[^.]{0,40}?attack does (\d+) more damage")
_T_RETREAT_LOCK_RE = re.compile(
    r"During your opponent.s next turn, (?:the )?(?:Defending Pok.mon|your opponent.s Active "
    r"Pok.mon) can.t retreat")
_T_COIN_GATE_RE = re.compile(r"Flip a coin\.[^.]*\bIf heads, during")


def parse_attack_transients(text: str, attack_name: str) -> dict:
    """The transient next-turn grants an attack's text declares (ADR-0033).

    Args:
        text: the attack's free-text effect.
        attack_name: the attack's own name (for the self-referential named-lock check).

    Returns:
        A dict of the fields to set — ``reduction`` / ``prevent_all`` / ``self_lock`` /
        ``same_lock`` / ``self_bonus`` / ``retreat_lock`` — empty when the attack grants
        nothing trackable (incl. coin-gated variants, which aren't knowable).
    """
    t = (text or "").replace("\n", " ")
    if _T_COIN_GATE_RE.search(t):
        return {}
    out: dict = {}
    m = _T_REDUCTION_RE.search(t)
    if m:
        out["reduction"] = int(m.group(1))
    if _T_PREVENT_RE.search(t):
        out["prevent_all"] = True
    if _T_SELF_LOCK_RE.search(t):
        out["self_lock"] = True
    else:
        m = _T_NAMED_LOCK_RE.search(t)
        if m and m.group(1).strip() == (attack_name or "").strip():
            out["same_lock"] = True
    m = _T_SELF_BONUS_RE.search(t)
    if m:
        out["self_bonus"] = int(m.group(1))
    if _T_RETREAT_LOCK_RE.search(t):
        out["retreat_lock"] = True
    return out


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
        trans = parse_attack_transients(text, getattr(a, "name", "") or "")
        if printed == 0 and not scaling and not hidden:
            effect = parse_attack_effect_damage(text)   # fixed effect damage hides in the text
            if effect:
                printed = effect[0]
                if effect[1]:           # counter-put: counters bypass W/R and prevention
                    w = r = e = True
        if scaling and scaling[2]:      # counter-placer: counters aren't damage — no W/R, no
            w = r = e = True            # prevention (Powerful Hand lands through Crustle)
        table[a.attackId] = AttackStat(
            attackId=a.attackId, damage=printed,
            cost=len(getattr(a, "energies", None) or []),
            recoil=parse_attack_recoil(text),
            benchSnipe=parse_attack_bench_snipe(text),
            handSizeDamage=parse_attack_hand_size(text),
            ignoresWeakness=w, ignoresResistance=r, ignoresEffects=e,
            damageMin=(bounds[0] if bounds else None),
            damageMax=(bounds[1] if bounds else None),
            scaleVar=(scaling[0] if scaling else None),
            scalePerUnit=(scaling[1] if scaling else 0),
            scaleEnergyType=(scaling[3] if scaling else None),
            hiddenPerUnit=(hidden[0] if hidden else 0),
            hiddenSample=(hidden[1] if hidden else 0),
            hiddenEnergyType=(hidden[2] if hidden else None),
            nextTurnReduction=trans.get("reduction", 0),
            nextTurnPreventAll=trans.get("prevent_all", False),
            nextTurnSelfLock=trans.get("self_lock", False),
            nextTurnSameAttackLock=trans.get("same_lock", False),
            nextTurnSelfBonus=trans.get("self_bonus", 0),
            nextTurnDefenderRetreatLock=trans.get("retreat_lock", False),
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
        prevents_from, prevents_at_least, dmg_reduction, reduction_types = parse_card_defense(c)
        cache[c.cardId] = CardStat(
            cardId=c.cardId, name=c.name, hp=int(c.hp),
            ex=bool(c.ex), megaEx=bool(c.megaEx), aceSpec=bool(getattr(c, "aceSpec", False)),
            hasAbility=bool(int(c.hp) > 0 and getattr(c, "skills", None)),   # a Pokémon with an Ability skill
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
            tera=bool(getattr(c, "tera", False)),
            preventsDamageFrom=prevents_from,
            preventsDamageAtLeast=prevents_at_least,
            damageReduction=dmg_reduction,
            damageReductionTypes=reduction_types,
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
