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
    aceSpec: bool = False              # ACE SPEC — one/deck, irreplaceable; CardStat feeds
                                       # 'protect the ACE SPEC' rules (e.g. Hero's Cape)
    hasAbility: bool = False           # Pokémon w/ Ability (CardData.skills, hp>0). Salvatore's
                                       # fetch-filter excludes ability-bearing Evolution targets (cf _FETCH_FILTERS)
    hpBonus: int = 0                   # flat HP a Tool grants holder (e.g. Hero's Cape +100),
                                       # parsed from skill text — engine has no structured field.
                                       # Primitive behind the general +HP-tool breakpoint model.
    retreatReduction: int = 0          # Energy a Tool shaves off its holder's Retreat Cost (Air Balloon:
                                       # {C}{C} -> 2), parsed from skill text. The SECOND Tool class the
                                       # ADR-0028 doctrine never modelled: worthless on a body that will
                                       # never retreat, so it belongs on the Active (ml f87). 0 otherwise.
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


class DictCardStatProvider:
    """In-memory provider for tests and precomputed caches."""

    def __init__(self, stats: dict[int, CardStat]):
        self._stats = stats
        self._forward: _ForwardIndex | None = None
        self._name_ids: dict[str, frozenset[int]] | None = None

    def get(self, card_id: int) -> CardStat | None:
        return self._stats.get(card_id)

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


# Matches ONLY unconditional Tool phrasing "+N HP" (Hero's Cape); restricted variants ("The
# Cynthia's Pokémon…") break adjacency, parse to 0. `.` = é, no non-ASCII literal (cross-platform).
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


# Air Balloon: "The Retreat Cost of the Pokémon this card is attached to is {C}{C} less." The amount is
# written as repeated Colorless symbols, so count them rather than reading a digit.
_RETREAT_TOOL_RE = re.compile(
    r"\bThe Retreat Cost of the Pok.mon this card is attached to is ((?:\{C\})+) less")


def _parse_tool_retreat_reduction(card) -> int:
    """Energy a Pokémon Tool shaves off its holder's Retreat Cost (``CardStat.retreatReduction``),
    read from the card's skill text — the engine exposes no structured field. Unconditional phrasing
    only; anything else parses to 0 (under-credit never over-credits a retreat the body can't pay)."""
    for s in (getattr(card, "skills", None) or []):
        text = getattr(s, "text", None)
        if text is None and isinstance(s, dict):
            text = s.get("text")
        m = _RETREAT_TOOL_RE.search(text or "")
        if m:
            return m.group(1).count("{C}")
    return 0


# Attack-rider parsers (ADR-0022 #2/#14): recoil/bench-snipe amount lives only in free-text (no
# engine field). Whole-sentence UNCONDITIONAL match only; conditional riders parse to 0 (safe: under-credit never).
_RECOIL_RE = re.compile(r"This Pok.mon (?:also )?does (\d+) damage to itself\.?$")
_BENCH_SNIPE_RE = re.compile(
    r"This attack also does (\d+) damage to 1 of your opponent.s Benched Pok.mon\.?$")
# "For each card in hand" attacker (Powerful Hand): printed damage=0, invisible w/o text parse.
# Counter-placement = N×10, ignores W/R; rarer "does N dmg for each card" is direct damage.
_HAND_SIZE_COUNTERS_RE = re.compile(
    r"Place (\d+) damage counters? on your opponent.s Active Pok.mon for each card in your hand\.?$")
_HAND_SIZE_DAMAGE_RE = re.compile(r"does (\d+) (?:more )?damage for each card in your hand\.?$")
_DAMAGE_PER_COUNTER = 10
# Dmg "isn't affected by...effects on opponent's Active" (Nebula Beam) bypasses a damage-
# PREVENTION Ability (Mysterious Rock Inn) combat math otherwise treats as an absolute wall.
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


# Defender ability families (ADR-0032 G1). Pool-verified: 2 prevent-from-ex (Sylveon 330 was
# UNTAGGED, closes gap), 1 basic-ex (Farigiraf ex), 1 threshold (Drednaw>=200), 3 flat -30 after W/R.
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
# {W} Pokémon (after applying …)" — reduction applies only to attackers of named types.
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


# Ignore-family (ADR-0032): per-attack dmg modifiers card-level model can't express (Nebula Beam
# ignores *effects* so lands through Crustle's prevention). Whole-sentence; Conkeldurr's cost-ignore excluded.
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
    energyTypes: tuple = ()            # the cost's per-slot Energy TYPE codes (EnergyType enum; 0 =
                                       # colorless/any) — e.g. Phantom Dive [Fire, Psychic]. Backs the
                                       # type-aware attach (attach the type the wincon still LACKS, not a redundant one)
    recoil: int = 0                    # unconditional self-damage (ADR-0022 #2)
    benchSnipe: int = 0                # unconditional opp-bench rider (ADR-0022 #14); ignores W/R
    benchSpread: int = 0               # distributable opp-bench counter spread total (Phantom Dive
                                       # "put N counters in any way you like" -> N*10); ignores W/R.
                                       # The placement policy distributes it; count = benchSpread // 10
    handSizeDamage: int = 0            # per-card hand-size scaling (printed damage hides it)
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
    recoverN: int = 0                  # energy-recover rider ("Attach up to N Basic {X} from discard"):
                                       # max cards re-attached (Aura Jab / Regi Charge; pool-verified 6)
    recoverEnergyType: int | None = None   # the rider's Basic-{X} filter (None = any Basic Energy)
    recoverTarget: str | None = None   # scope "self"/"bench"/"any" — Tactical credits
                                       # min(recoverN, matching discard fuel) as development
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


# Conditional-dmg families (ADR-0032 bounds half). Pool: 26 "does nothing" conditionals (coin-tails
# + board), 26 "If heads +N", 2 "You may +N". Does-nothing floors to 0; bonus lifts ceiling by N.
_DOES_NOTHING_RE = re.compile(r", this attack does nothing")
# Any conditional/optional flat bonus lifts ceiling (coin heads, board conditions, pay-offs).
# *For each* bonus is a SCALER not flat bonus — lookahead rejects it.
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


# Visible-state scaler families (ADR-0032 exact half). Pool: 1 own-hand counter-placer (Powerful
# Hand), 2 opp-hand, 8 opp-active-energy, 13 own-energy. Attacker-relative names -> Incoming reuses unchanged.
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
    # attacker's DISCARD pile — open info for BOTH players, so an opponent's Riptide
    # is exactly priceable from THEIR visible discard. Optional Basic-{X} type filter.
    (re.compile(r"Put (\d+) damage counters? on 1 of your opponent.s Pok.mon for each Basic "
                r"\{(\w)\} Energy card in your discard pile"), "atk_discard_energy", 10, True),
    (re.compile(r"does (\d+) (?:more )?damage for each(?: Basic)?(?: \{(\w)\})? Energy card[s]? "
                r"in your discard pile"), "atk_discard_energy", 1, False),
    # damage counters already on a body (maxHp − hp, both visible) — 8 self + 7 defender
    (re.compile(r"does (\d+) (?:more )?damage for each damage counter on this Pok.mon"),
     "atk_self_counters", 1, False),
    (re.compile(r"does (\d+) (?:more )?damage for each damage counter on your opponent.s Active "
                r"Pok.mon"), "def_counters", 1, False),
    # Prize cards taken so far (start − remaining, both visible) — 6 attacks, split by direction
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


# Fixed EFFECT damage (ADR-0032 ledger sweep): printed-0 attack, number lives in text — chosen-target
# dmg or counter-puts (N x 10, bypass W/R). Bench-only/ex-conditional targets are NOT this family.
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


# Distributable bench spread (ADR-0032 follow-up, dragapult_ex): "Put N damage counters on your
# opponent's Benched Pokémon in any way you like" (Dragapult ex Phantom Dive). The "in any way you
# like" marker = the player distributes the N counters across the opp Bench at will — distinct from
# the single-target `benchSnipe` rider and from a forced "each" spread.
_BENCH_SPREAD_RE = re.compile(
    r"Put (\d+) damage counters? on your opponent.s (?:Benched )?Pok.mon in any way you like")


def parse_attack_bench_spread(text: str) -> int:
    """Distributable opponent-bench counter spread → N*10 total damage; 0 otherwise.

    Args:
        text: the attack's free-text effect.

    Returns:
        e.g. Phantom Dive "Put 6 damage counters on your opponent's Benched Pokémon in any way you
        like" → ``60`` (6 counters). Counters ignore Weakness/Resistance. Single-target ("1 of"),
        own-bench, and forced ("each") riders → 0 — those aren't a chosen distribution.
    """
    m = _BENCH_SPREAD_RE.search((text or "").replace("\n", " "))
    return int(m.group(1)) * _DAMAGE_PER_COUNTER if m else 0


# Hidden-state deck-discard scalers (ADR-0032 class C). Pool: exactly 3 — Hammer-lanche (top 6
# own), Misty's Lapras (top 7), Ground Burn (top 1 EACH deck). Hidden card order -> bounds only.
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


# Transient next-turn families (ADR-0033). Pool: 17 takes-less, 6 prevent-all, 23 self-locks, 18
# named locks, 2 self-bonus, 22 retreat-lock. Coin-gated NOT parsed (unknowable, safe under-credit).
_T_REDUCTION_RE = re.compile(
    r"During your opponent.s next turn, this Pok.mon takes (\d+) less damage")
_T_PREVENT_RE = re.compile(
    r"During your opponent.s next turn, prevent all damage done to this Pok.mon")
_T_SELF_LOCK_RE = re.compile(
    r"During your next turn, this Pok.mon can.t (?:attack|use attacks)\.")
_T_NAMED_LOCK_RE = re.compile(r"During your next turn, this Pok.mon can.t use ([^.]+)\.")
_T_SELF_BONUS_RE = re.compile(
    r"During your next turn, (?:this Pok.mon.s )?[^.]{0,40}?attack does (\d+) more damage")
_T_COIN_GATE_RE = re.compile(r"Flip a coin\.[^.]*\bIf heads, during")


def parse_attack_transients(text: str, attack_name: str) -> dict:
    """The transient next-turn grants an attack's text declares (ADR-0033).

    Args:
        text: the attack's free-text effect.
        attack_name: the attack's own name (for the self-referential named-lock check).

    Returns:
        A dict of the fields to set — ``reduction`` / ``prevent_all`` / ``self_lock`` /
        ``same_lock`` / ``self_bonus`` — empty when the attack grants nothing trackable
        (incl. coin-gated variants, which aren't knowable; retreat-locks, which the engine
        enforces by omitting the RETREAT option, so no field carries them).
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
    return out


# The energy-recover rider family (attach-from-discard). Pool-verified: exactly 6 — Aura Jab
# (up to 3 Basic {F} → Benched), Pick and Stick (up to 2 Basic, any of your Pokémon), 3x Regi
# Charge + Abundant Harvest (self). Attacking IS the acceleration for these decks, so the
# Tactical layer credits the recoverable fuel as development value.
_RECOVER_RE = re.compile(
    r"Attach (?:up to (\d+) |a )Basic(?: \{(\w)\})? Energy cards? from your discard pile to "
    r"(this Pok.mon|(?:1 of )?your Benched Pok.mon|(?:1 of )?your Pok.mon)")


# The damage-boost Trainer families (the OHKO-line model's card facts). An Item/Supporter grants
# "During this turn, attacks used by your [{X}] Pokémon do N more damage to your opponent's Active
# Pokémon [{ex}]"; a Tool grants it while attached. Both "(before applying Weakness and
# Resistance)" — the oracle adds the boost BEFORE the W/R step. Multi-mode cards ("Choose 1" —
# Kieran) are fail-closed: the boost is only one of their modes, so no flat fact is sound.
_BOOST_TURN_RE = re.compile(
    r"During this turn, attacks used by your (?:\{(\w)\} )?Pok.mon do (\d+) more damage to your "
    r"opponent.s Active Pok.mon( \{ex\})?")
_BOOST_TOOL_RE = re.compile(
    r"Attacks used by the Pok.mon this card is attached to do (\d+) more damage to your "
    r"opponent.s Active Pok.mon( \{ex\})?")


def parse_card_damage_boost(card) -> tuple[int, int | None, bool]:
    """Flat damage-boost a Trainer grants: ``(amount, attackerEnergyType|None, vsExOnly)``.

    Args:
        card: an engine ``CardData`` record (skills carry the free text).

    Returns:
        e.g. Premium Power Pro → ``(30, 6, False)``; Maximum Belt → ``(50, None, True)``;
        Black Belt's Training → ``(40, None, True)``; anything else (incl. the multi-mode
        Kieran) → ``(0, None, False)``.
    """
    text = " ".join((s.text or "") for s in (getattr(card, "skills", None) or ())).replace("\n", " ")
    if not text or "Choose 1" in text:
        return (0, None, False)
    m = _BOOST_TURN_RE.search(text)
    if m:
        return (int(m.group(2)), _TYPE_LETTER.get(m.group(1)) if m.group(1) else None,
                bool(m.group(3)))
    m = _BOOST_TOOL_RE.search(text)
    if m:
        return (int(m.group(1)), None, bool(m.group(2)))
    return (0, None, False)


# The bench-partner condition family ("If you don't have <X> on your Bench, this attack does
# nothing"). Pool-verified: exactly 2 — Cosmic Beam (Lunatone), Guardian Burst (Uxie AND Azelf).
# The generic does-nothing bounds parser already floors these to damageMin=0 (the Lethal guard);
# this names the partner(s) so SCORING can zero the attack on the live board too.
_REQUIRES_BENCH_RE = re.compile(
    r"If you don.t have ([^,]{2,60}?) on your Bench, this attack does nothing")


def parse_attack_bench_requirement(text: str) -> tuple[str, ...] | None:
    """Bench-partner names an attack requires, or None (Cosmic Beam → ``("Lunatone",)``;
    Guardian Burst → ``("Uxie", "Azelf")`` — an "and" list means ALL must be benched).

    Args:
        text: the attack's free-text effect.

    Returns:
        The required names tuple, or None when the attack carries no bench condition.
    """
    m = _REQUIRES_BENCH_RE.search((text or "").replace("\n", " "))
    if not m:
        return None
    return tuple(n.strip() for n in m.group(1).split(" and ") if n.strip())


_SELF_RETURN_RE = re.compile(
    r"Put this Pok.mon (?:and all attached cards )?(?:back )?into your hand")


def parse_attack_self_return(text: str) -> bool:
    """True if the attack scoops its OWN Pokémon (and attached cards) back into the owner's hand —
    Meowth ex Tuck Tail ("Put this Pokémon and all attached cards into your hand"). The escape fact:
    a doomed multi-prize Active can bounce to deny the opponent the prize (and re-arm a bench-drop
    Ability). Subject is "this Pokémon" (self), distinct from an opponent-facing return.

    Args:
        text: the attack's free-text effect.

    Returns:
        True when the attack returns its own Pokémon to hand.
    """
    return bool(_SELF_RETURN_RE.search((text or "").replace("\n", " ")))


def parse_attack_energy_recover(text: str) -> tuple[int, int | None, str] | None:
    """Energy-recover rider read from attack text: ``(n, basicEnergyType|None, target)``.

    Args:
        text: the attack's free-text effect.

    Returns:
        e.g. Aura Jab → ``(3, 6, "bench")``; Regi Charge → ``(2, 3, "self")``; Pick and
        Stick → ``(2, None, "any")``. None when the attack recovers nothing.
    """
    m = _RECOVER_RE.search((text or "").replace("\n", " "))
    if not m:
        return None
    n = int(m.group(1)) if m.group(1) else 1
    etype = _TYPE_LETTER.get(m.group(2)) if m.group(2) else None
    tgt = m.group(3)
    target = "self" if "this" in tgt else ("bench" if "Benched" in tgt else "any")
    return (n, etype, target)


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
            recoverN=(recover[0] if recover else 0),
            recoverEnergyType=(recover[1] if recover else None),
            recoverTarget=(recover[2] if recover else None),
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
        hand_size_by_aid.setdefault(a.attackId, parse_attack_hand_size(getattr(a, "text", "") or ""))
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
            stage2=bool(getattr(c, "stage2", False)),
            damageBoost=boost, damageBoostType=boost_type, damageBoostVsEx=boost_vs_ex,
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


def _name_index(cache: dict[int, CardStat]) -> dict[str, frozenset[int]]:
    """Reverse index ``card name -> frozenset of ids printed under it`` (names aren't unique — folds
    every printing). The Matchup Brief consumer's name->id bridge (ADR-0027). Pure/lib-free."""
    idx: dict[str, set[int]] = {}
    for cid, st in cache.items():
        if st.name:
            idx.setdefault(st.name, set()).add(cid)
    return {name: frozenset(ids) for name, ids in idx.items()}


class EngineCardStatProvider:
    """Lazily build a ``{cardId: CardStat}`` cache from the native engine (runtime only)."""

    def __init__(self):
        self._cache: dict[int, CardStat] | None = None
        self._forward: _ForwardIndex | None = None
        self._name_ids: dict[str, frozenset[int]] | None = None

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

    def ids_for_name(self, name: str) -> frozenset[int]:
        """Card ids printed under ``name`` (see ``DictCardStatProvider.ids_for_name``)."""
        self._ensure_cache()
        if self._name_ids is None:
            self._name_ids = _name_index(self._cache)
        return self._name_ids.get(name, frozenset())
