"""Card-text parser battery: free-text card/attack effects in, typed facts out (ADR-0054).

Match ONLY the clean UNCONDITIONAL phrasing, so a conditional variant parses to 0/None —
under-crediting never over-credits. INVERTS for a COST (Gravity Gemstone: ``{C}`` MORE to retreat),
which therefore matches more readily. A holder gate is CARRIED when the pool lets us decide it about
a body in play (Issue #306/#345); a condition about a coin, a hidden zone or a board sweep is
refused. Split out of ``provider.py``, which re-exports every name.
"""
from __future__ import annotations

import re


# \u escapes, not literals: this file must read identically under any editor's default encoding.
_NAME_FAMILY = r"(?:[A-Z][\w.-]+ ){0,3}[A-Z][\w.-]*['" + "\u2019" + r"]s"

#: Apostrophes folded to ASCII — the pool mixes forms WITHIN one family, so normalise both sides.
_APOSTROPHES = str.maketrans({"\u2019": "'", "\u02bc": "'", "\u2018": "'"})

_HOLDER_FAMILY_RE = re.compile(
    r"\b[Tt]he (" + _NAME_FAMILY + r") Pok.mon this card is attached to")


def normalize_card_name(name: str) -> str:
    """A card name folded to one apostrophe form and one run of spaces — the name-family test's key."""
    return " ".join((name or "").translate(_APOSTROPHES).split())


def _parse_tool_holder_family(card) -> str | None:
    """The owner family a Tool restricts its modifiers to; ONE parse per card, whatever the modifier."""
    for text in _skill_texts(card):
        m = _HOLDER_FAMILY_RE.search(text.replace("\n", " "))
        if m:
            return m.group(1)
    return None


# WHOLE-SENTENCE: the boost must be the sentence's own subject. `.` = é, the convention throughout.
_HP_BONUS_RE = re.compile(
    r"^The (?:" + _NAME_FAMILY + r" )?Pok.mon this card is attached to gets \+(\d+) HP")


def _parse_tool_hp_bonus(card) -> int:
    """Flat HP a Tool grants its holder (``CardStat.hpBonus``); the engine has no such field."""
    for text in _skill_texts(card):
        for sent in _sentences(text):
            m = _HP_BONUS_RE.match(sent)
            if m:
                return int(m.group(1))
    return 0


_RETREAT_TOOL_RE = re.compile(
    r"\bThe Retreat Cost of the Pok.mon this card is attached to is ((?:\{C\})+) less")

# Gravity Gemstone is a COST: a NEGATIVE `retreatReduction`, matched without its Active-Spot rider
# because over-charging a retreat is the safe direction.
_RETREAT_TOOL_MORE_RE = re.compile(
    r"\bthe Retreat Cost of both Active Pok.mon is ((?:\{C\})+) more")


def _parse_tool_retreat_reduction(card) -> int:
    """NEGATIVE for a Tool that makes retreating dearer — do not assume this is non-negative."""
    for text in _skill_texts(card):
        m = _RETREAT_TOOL_RE.search(text)
        if m:
            return m.group(1).count("{C}")
        m = _RETREAT_TOOL_MORE_RE.search(text)
        if m:
            return -m.group(1).count("{C}")
    return 0


# Retreat-cost GRANTS (ADR-0100 §8), FAIL-CLOSED: an unmodelled grant charges the PRINTED cost.
_RETREAT_FREE_AT_HP_RE = re.compile(
    r"If that Pok.mon.s remaining HP is (\d+) or less, it has no Retreat Cost")

#: Board-level grants we can evaluate SOUNDLY; an unlisted predicate parses to None (N's Castle).
_RETREAT_FREE_GRANT_RES = (
    ("basic", re.compile(r"Your Basic Pok.mon in play have no Retreat Cost")),
    ("metal_attached", re.compile(
        r"All of your Pok.mon that have \{M\} Energy attached have no Retreat Cost")),
)


def _skill_texts(card):
    """Every skill text on ``card``, newlines folded to spaces, as every attack-level parser folds."""
    for s in (getattr(card, "skills", None) or []):
        text = getattr(s, "text", None)
        if text is None and isinstance(s, dict):
            text = s.get("text")
        if text:
            yield text.replace("\n", " ")


def _parse_tool_retreat_free_at_hp(card) -> int:
    """Remaining HP at or below which a Tool zeroes the Retreat Cost; separate from the flat leg."""
    for text in _skill_texts(card):
        m = _RETREAT_FREE_AT_HP_RE.search(text)
        if m:
            return int(m.group(1))
    return 0


def _parse_retreat_free_grant(card):
    """The PREDICATE name of a board-level no-Retreat-Cost grant; the caller evaluates it."""
    for text in _skill_texts(card):
        for name, pattern in _RETREAT_FREE_GRANT_RES:
            if pattern.search(text):
                return name
    return None


_RECOIL_RE = re.compile(r"This Pok.mon (?:also )?does (\d+) damage to itself\.?$")
_BENCH_SNIPE_RE = re.compile(
    r"This attack also does (\d+) damage to 1 of your opponent.s Benched Pok.mon\.?$")
_DAMAGE_PER_COUNTER = 10
# Bypasses a damage-PREVENTION Ability that combat math otherwise treats as an absolute wall.
_IGNORES_ACTIVE_EFFECTS_RE = re.compile(
    r"isn.t affected by[^.]*effects on your opponent.s Active Pok.mon")


def _sentences(text: str) -> list[str]:
    """Trimmed sentences, newlines folded — so a rider parser can require WHOLE-sentence phrasing."""
    return [s.strip() for s in re.split(r"(?<=\.)\s+", (text or "").replace("\n", " ")) if s.strip()]


def parse_attack_recoil(text: str) -> int:
    """Unconditional self-damage; conditional/variable → 0. Feeds the ADR-0022 #2 draw-guard."""
    for sent in _sentences(text):
        m = _RECOIL_RE.match(sent)
        if m:
            return int(m.group(1))
    return 0


def parse_attack_bench_snipe(text: str) -> int:
    """Unconditional single-target opp-bench damage; spreads and conditional riders → 0."""
    for sent in _sentences(text):
        m = _BENCH_SNIPE_RE.match(sent)
        if m:
            return int(m.group(1))
    return 0


def parse_attack_ignores_active_effects(text: str) -> bool:
    """It lands full damage THROUGH a damage-prevention Ability; anything else → False."""
    return bool(_IGNORES_ACTIVE_EFFECTS_RE.search((text or "").replace("\n", " ")))


_PREVENT_EX_RE = re.compile(
    r"Prevent all damage done to this Pok.mon by attacks from your opponent.s Pok.mon \{ex\}")
_PREVENT_BASIC_EX_RE = re.compile(
    r"Prevent all damage done to this Pok.mon by attacks from your opponent.s Basic Pok.mon \{ex\}")
_PREVENT_THRESHOLD_RE = re.compile(
    r"Prevent all damage done to this Pok.mon by attacks from your opponent.s Pok.mon if that "
    r"damage is (\d+) or more")
_TAKES_LESS_RE = re.compile(
    r"This Pok.mon takes (\d+) less damage from attacks \(after applying Weakness and Resistance\)")
_TAKES_LESS_TYPED_RE = re.compile(
    r"This Pok.mon takes (\d+) less damage from attacks from your opponent.s \{(\w)\}"
    r"(?: or \{(\w)\})? Pok.mon")
_TYPE_LETTER = {"G": 1, "R": 2, "W": 3, "L": 4, "P": 5,
                "F": 6, "D": 7, "M": 8, "N": 9}        # EnergyType enum ({N} = Dragon)


def parse_card_defense(card) -> tuple[str | None, int, int, tuple | None]:
    """The last element is None for an unconditional reduction, else the attacker types it scopes to."""
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


# Tool-granted damage reduction: the pool's three printed shapes, none matched by the
# Pokémon-body patterns above (PR #533 review). All apply AFTER Weakness and Resistance.
_TOOL_BERRY_REDUCTION_RE = re.compile(
    r"If the Pok.mon this card is attached to is damaged by an attack from your opponent.s "
    r"\{(\w)\} Pok.mon, it takes (\d+) less damage")
_TOOL_ABILITY_REDUCTION_RE = re.compile(
    r"The Pok.mon this card is attached to takes (\d+) less damage from attacks from your "
    r"opponent.s Pok.mon that have an Ability")
_TOOL_HOLDER_TYPED_REDUCTION_RE = re.compile(
    r"The \{(\w)\} Pok.mon this card is attached to takes (\d+) less damage from attacks from "
    r"your opponent.s ((?:\{\w\}(?:, | or |, or ))*\{\w\} )Pok.mon")


def parse_tool_damage_reduction(card) -> tuple[int, tuple | None, tuple | None, bool]:
    """``(amount, attacker types | None=any, holder types | None=any, attacker needs an Ability)``.
    A berry's discard-after-use still guards the next hit, which is all a one-turn forecast prices."""
    for text in _skill_texts(card):
        m = _TOOL_BERRY_REDUCTION_RE.search(text)
        if m and m.group(1) in _TYPE_LETTER:
            return int(m.group(2)), (_TYPE_LETTER[m.group(1)],), None, False
        m = _TOOL_ABILITY_REDUCTION_RE.search(text)
        if m:
            return int(m.group(1)), None, None, True
        m = _TOOL_HOLDER_TYPED_REDUCTION_RE.search(text)
        if m and m.group(1) in _TYPE_LETTER:
            attackers = tuple(_TYPE_LETTER[g] for g in re.findall(r"\{(\w)\}", m.group(3))
                              if g in _TYPE_LETTER)
            return int(m.group(2)), attackers or None, (_TYPE_LETTER[m.group(1)],), False
    return 0, None, None, False


# A colour a body needs for its ABILITY, never in an attack cost; energy routing must credit it.
_ABILITY_FUEL_RE = re.compile(r"this Pok.mon has (?:any )?\{(\w)\} Energy attached")


def parse_card_ability_energy(card) -> tuple:
    """EnergyType ids an Ability needs ATTACHED as fuel; de-duplicated, order-stable."""
    out: list[int] = []
    for s in (getattr(card, "skills", None) or []):
        text = getattr(s, "text", None)
        if text is None and isinstance(s, dict):
            text = s.get("text")
        for g in _ABILITY_FUEL_RE.findall((text or "").replace("\n", " ")):
            code = _TYPE_LETTER.get(g)
            if code is not None and code not in out:
                out.append(code)
    return tuple(out)


# Whole-sentence and damage-scoped; Conkeldurr's cost-ignore is deliberately excluded.
_IGNORES_RE = re.compile(r"\bThis (?:attack.s )?damage isn.t affected by ([^.]+)\.")


def parse_attack_ignores(text: str) -> tuple[bool, bool, bool]:
    """"effects" is the defender-side family: prevention Abilities and reduction effects."""
    w = r = e = False
    for m in _IGNORES_RE.finditer(text or ""):
        clause = m.group(1)
        w = w or "Weakness" in clause
        r = r or "Resistance" in clause
        e = e or "effects" in clause
    return (w, r, e)


_DOES_NOTHING_RE = re.compile(r", this attack does nothing")
# *For each* is a SCALER, not a flat bonus — the lookahead rejects it.
_BONUS_RE = re.compile(
    r"(?:If [^.]{1,80}?, this attack does|You may do|to have this attack do) (\d+) more damage"
    r"(?! for each)")


def parse_attack_damage_bounds(text: str, printed: int) -> tuple[int, int] | None:
    """Floor 0 on a does-nothing clause, ceiling ``printed + N`` on a bonus; None if deterministic."""
    t = (text or "").replace("\n", " ")
    lo, hi, found = printed, printed, False
    if _DOES_NOTHING_RE.search(t):
        lo, found = 0, True
    m = _BONUS_RE.search(t)
    if m:
        hi, found = printed + int(m.group(1)), True
    return (lo, hi) if found else None


# Attacker-relative names, so the Incoming reader reuses them unchanged (ADR-0032 exact half).
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
    # a DISCARD pile is open info for BOTH players, so an opponent's Riptide is exactly priceable.
    (re.compile(r"Put (\d+) damage counters? on 1 of your opponent.s Pok.mon for each Basic "
                r"\{(\w)\} Energy card in your discard pile"), "atk_discard_energy", 10, True),
    (re.compile(r"does (\d+) (?:more )?damage for each(?: Basic)?(?: \{(\w)\})? Energy card[s]? "
                r"in your discard pile"), "atk_discard_energy", 1, False),
    (re.compile(r"does (\d+) (?:more )?damage for each damage counter on this Pok.mon"),
     "atk_self_counters", 1, False),
    (re.compile(r"does (\d+) (?:more )?damage for each damage counter on your opponent.s Active "
                r"Pok.mon"), "def_counters", 1, False),
    (re.compile(r"does (\d+) (?:more )?damage for each Prize card you have (?:already )?taken"),
     "atk_prizes_taken", 1, False),
    (re.compile(r"does (\d+) (?:more )?damage for each Prize card your opponent has "
                r"(?:already )?taken"), "def_prizes_taken", 1, False),
)


def parse_attack_scaling(text: str) -> tuple[str, int, bool, int | None] | None:
    """perUnit is in DAMAGE (a counter is 10); ``energyType`` only for the discard family's filter."""
    t = (text or "").replace("\n", " ")
    for pat, var, mult, counters in _SCALE_FAMILIES:
        m = pat.search(t)
        if m:
            etype = None
            if pat.groups >= 2 and m.group(2):
                etype = _TYPE_LETTER.get(m.group(2))
            return (var, int(m.group(1)) * mult, counters, etype)
    return None


# Printed-0 attack whose number lives in text. Bench-only / ex-conditional targets are NOT this family.
_EFFECT_DMG_RE = re.compile(
    r"This attack does (\d+) damage to (?:\d+|each) of your opponent.s Pok.mon(?! \{)(?! for each)")
_COUNTER_PUT_RE = re.compile(
    r"Put (\d+) damage counters? on (?:\d+ of |each of )?your opponent.s Pok.mon(?! \{)(?! for each)")


def parse_attack_effect_damage(text: str) -> tuple[int, bool] | None:
    """``(active_damage, is_counters)``: "Put 4 damage counters …" → ``(40, True)``."""
    t = (text or "").replace("\n", " ")
    m = _EFFECT_DMG_RE.search(t)
    if m:
        return (int(m.group(1)), False)
    m = _COUNTER_PUT_RE.search(t)
    if m:
        return (int(m.group(1)) * _DAMAGE_PER_COUNTER, True)
    return None


# "in any way you like" = the player DISTRIBUTES the counters, unlike the single-target rider.
_BENCH_SPREAD_RE = re.compile(
    r"Put (\d+) damage counters? on your opponent.s (?:Benched )?Pok.mon in any way you like")


def parse_attack_bench_spread(text: str) -> int:
    """N*10 total damage; counters ignore W/R. Single-target, own-bench and forced riders → 0."""
    m = _BENCH_SPREAD_RE.search((text or "").replace("\n", " "))
    return int(m.group(1)) * _DAMAGE_PER_COUNTER if m else 0


# Hidden card ORDER, so the oracle gets bounds only (ADR-0032 class C).
_HIDDEN_SCALE_RE = re.compile(
    r"Discard the top (\d+ )?cards? of (your|each player.s) deck.{0,60}?does (\d+) (?:more )?damage "
    r"for each(?: Basic \{(\w)\} Energy card)?", re.S)


def parse_attack_hidden_scale(text: str) -> tuple[int, int, int | None] | None:
    """``(per_unit, sampled_count, basicEnergyType|None)``, None if not a deck-discard scaler."""
    m = _HIDDEN_SCALE_RE.search((text or "").replace("\n", " "))
    if not m:
        return None
    n = int(m.group(1)) if m.group(1) else 1
    if m.group(2).startswith("each"):
        n *= 2                                       # one card off EACH player's deck
    etype = _TYPE_LETTER.get(m.group(4)) if m.group(4) else None
    return (int(m.group(3)), n, etype)


# Coin-gated grants are NOT parsed — unknowable, so the safe under-credit (ADR-0033).
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
    """Empty when nothing is trackable. Retreat-locks carry no field — the engine omits the option."""
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


# Attacking IS the acceleration for these decks, so the recoverable fuel counts as development.
_RECOVER_RE = re.compile(
    r"Attach (?:up to (\d+) |a )Basic(?: \{(\w)\})? Energy cards? from your discard pile to "
    r"(this Pok.mon|(?:1 of )?your Benched Pok.mon|(?:1 of )?your Pok.mon)")

# The DECK-source sibling. Scope-locked targets, per-bench forms and twin clauses stay UNMATCHED,
# so the endorser under-counts rather than over-credits.
_DECK_ACCEL_RE = re.compile(
    r"Search your deck for (?:up to (\d+) |an? )Basic(?: \{(\w)\})? Energy cards? and attach "
    r"(?:them|it) to (this Pok.mon|(?:1 of )?your Benched Pok.mon|(?:1 of )?your Pok.mon)")
_COIN_GUARD_RE = re.compile(r"[Ff]lip .*coin")   # a coin-gated accel is not an unconditional credit


# The oracle adds the boost BEFORE the W/R step; a multi-mode "Choose 1" card is fail-closed.
_BOOST_TURN_RE = re.compile(
    r"During this turn, attacks used by your (?:\{(\w)\} )?Pok.mon do (\d+) more damage to your "
    r"opponent.s Active Pok.mon( \{ex\})?")
# The Tool leg also swallows the attack-cost clause preceding the damage clause in one sentence;
# that second, independent fact is `_parse_tool_attack_cost_reduction`'s.
_BOOST_TOOL_RE = re.compile(
    r"Attacks used by the (?:" + _NAME_FAMILY + r" )?Pok.mon this card is attached to "
    r"(?:cost (?:\{C\})+ less and )?do (\d+) more damage to your "
    r"opponent.s Active Pok.mon( \{ex\})?")

# `_NO_RULE_BOX_GATE` is CONCATENATED into the value regex, so no text matches the amount alone.
_NO_RULE_BOX_GATE = r"If the Pok.mon this card is attached to doesn.t have a Rule Box,"
_HOLDER_NO_RULE_BOX_RE = re.compile(_NO_RULE_BOX_GATE)
_BOOST_TOOL_NO_RULE_BOX_RE = re.compile(
    _NO_RULE_BOX_GATE + r" the attacks it uses do (\d+) more damage to your "
    r"opponent.s Active Pok.mon( \{ex\})?")


def _parse_tool_holder_no_rule_box(card) -> bool:
    """A card merely MENTIONING a Rule Box does not match: the subject must be the attached-to body."""
    for text in _skill_texts(card):
        if _HOLDER_NO_RULE_BOX_RE.search(text):
            return True
    return False


# WHOLE-SENTENCE anchored (`^`), unlike the damage leg above, which is left byte-compatible.
_ATTACK_COST_TOOL_RE = re.compile(
    r"^Attacks used by the (?:" + _NAME_FAMILY + r" )?Pok.mon this card is attached to "
    r"cost ((?:\{C\})+) less")


def _parse_tool_attack_cost_reduction(card) -> int:
    """Unconditional phrasing only; under-crediting is the safe direction on both sides."""
    for text in _skill_texts(card):
        for sent in _sentences(text):
            m = _ATTACK_COST_TOOL_RE.match(sent)
            if m:
                return m.group(1).count("{C}")
    return 0


def parse_card_damage_boost(card) -> tuple[int, int | None, bool]:
    """``(amount, attackerEnergyType|None, vsExOnly)``; a holder condition never suppresses it."""
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
    m = _BOOST_TOOL_NO_RULE_BOX_RE.search(text)
    if m:
        return (int(m.group(1)), None, bool(m.group(2)))
    return (0, None, False)


# The does-nothing parser already floors these to 0; this names the partner(s) for live scoring.
_REQUIRES_BENCH_RE = re.compile(
    r"If you don.t have ([^,]{2,60}?) on your Bench, this attack does nothing")


def parse_attack_bench_requirement(text: str) -> tuple[str, ...] | None:
    """An "and" list means ALL must be benched (Guardian Burst → ``("Uxie", "Azelf")``)."""
    m = _REQUIRES_BENCH_RE.search((text or "").replace("\n", " "))
    if not m:
        return None
    return tuple(n.strip() for n in m.group(1).split(" and ") if n.strip())


_SELF_RETURN_RE = re.compile(
    r"Put this Pok.mon (?:and all attached cards )?(?:back )?into your hand")


def parse_attack_self_return(text: str) -> bool:
    """The escape fact: a doomed multi-prize Active can bounce to deny the opponent the prize."""
    return bool(_SELF_RETURN_RE.search((text or "").replace("\n", " ")))


def parse_attack_energy_recover(text: str) -> tuple[int, int | None, str, str] | None:
    """``(n, basicEnergyType|None, target, source)``; a coin-gated deck accel is NOT parsed."""
    t = (text or "").replace("\n", " ")
    m = _RECOVER_RE.search(t)
    source = "discard"
    if not m and not _COIN_GUARD_RE.search(t):
        m = _DECK_ACCEL_RE.search(t)
        source = "deck"
    if not m:
        return None
    n = int(m.group(1)) if m.group(1) else 1
    etype = _TYPE_LETTER.get(m.group(2)) if m.group(2) else None
    tgt = m.group(3)
    target = "self" if "this" in tgt else ("bench" if "Benched" in tgt else "any")
    return (n, etype, target, source)
