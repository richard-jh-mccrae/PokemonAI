"""Card-text parser battery: free-text card/attack effects in, typed facts out.

The ``parse_*`` functions (plus the Tool-skill helpers) read the engine's free-text
``Attack.text`` / ``CardData.skills`` and return plain typed facts — no engine import, no
record types. Shared doctrine: match ONLY the clean UNCONDITIONAL phrasing (whole-sentence
where a rider demands it), so a conditional variant parses to 0/None — under-crediting
never over-credits a claim the board might not honor. Split out of ``provider.py``
(ADR-0054); ``provider`` re-exports every name, so the historical import path stays valid.

**Two things the doctrine does not say, both added at Issue #306.** (1) An owner-family
qualifier in the subject ("the Cynthia's Pokémon this card is attached to") is not a
condition the parser has to refuse — it is a condition it can CARRY, in
``CardStat.holderNameFamily``, for the consumer to evaluate against the actual holder; the
amount and its gate are parsed together and travel together. (2) The doctrine is written
for BENEFITS, and the safe direction INVERTS for a cost: missing a penalty (Gravity
Gemstone's ``{C}`` MORE to retreat) makes a board look cheaper than it is, so a
cost-parser errs by matching MORE readily, not less. Both are called out where they apply.
"""
from __future__ import annotations

import re


# ── the owner / name-family holder gate (Issue #306) ──────────────────────────────────────────────
#
# Three Tools in the pool restrict their static modifier to a NAMED family of holders: Cynthia's
# Power Weight ("The Cynthia's Pokémon this card is attached to gets +70 HP"), Hop's Choice Band
# ("Attacks used by the Hop's Pokémon this card is attached to …") and Lillie's Pearl. Until
# Issue #306 they broke every subject-adjacent pattern and parsed to 0, which read as *"attaching
# this Tool is worth nothing"* — a plausible answer, and why it went unnoticed for Hop's Choice
# Band, the most-played Tool in the tracked meta.
#
# The family is EVALUABLE, unlike the board-level predicates `_RETREAT_FREE_GRANT_RES` deliberately
# refuses: `docs/rules.md` §9 records that the owner prefix IS part of the printed card name
# ("Iono's Tadbulb" != "Tadbulb"), so *"the Cynthia's Pokémon"* names exactly the cards printed
# `Cynthia's <species>` — and the HOLDER of a Tool is a body in play whose name we already have.
# That is a membership oracle over a known name, not a guess about a hidden zone. (N's Castle stays
# refused below for a different reason: its subject is every "N's Pokémon IN PLAY", both players'
# — a board sweep, not this card's one holder.)
#
# The gate is parsed ONCE per card, by `_parse_tool_holder_family`, and stored once, as
# `CardStat.holderNameFamily`. The value parsers accept the qualifier in the subject position but
# never re-read it, so the amount and its gate cannot drift apart the way two parsers for one fact
# always eventually do (Issue #213).
#
# Written with \u escapes, not literal characters, for the reason the `.` = é convention below
# exists: this file must read identically on either platform under any editor's default encoding.
_NAME_FAMILY = r"(?:[A-Z][\w.-]+ ){0,3}[A-Z][\w.-]*['" + "\u2019" + r"]s"

#: Every apostrophe the pool prints (U+2019 right single quote, U+02BC modifier letter, U+2018 left
#: single quote), folded to ASCII. The card records mix them WITHIN one family — `Hop's Phantump`
#: (878) is ASCII where `Hop's Silicobra` (288) is U+2019 — so a raw prefix comparison would answer
#: "no" for half the family. Normalise both sides, always.
_APOSTROPHES = str.maketrans({"\u2019": "'", "\u02bc": "'", "\u2018": "'"})

_HOLDER_FAMILY_RE = re.compile(
    r"\b[Tt]he (" + _NAME_FAMILY + r") Pok.mon this card is attached to")


def normalize_card_name(name: str) -> str:
    """A card name folded to one apostrophe form and one run of spaces — the comparable key both
    sides of a name-family test are measured in (see ``_APOSTROPHES``)."""
    return " ".join((name or "").translate(_APOSTROPHES).split())


def name_in_family(name: str | None, family: str | None) -> bool:
    """Does the card printed ``name`` belong to the owner family ``family``?

    Args:
        name: the holder's printed card name (``CardStat.name``).
        family: the owner qualifier a Tool's text restricts itself to ("Cynthia's"), or None.

    Returns:
        True when ``family`` is None — an ungated modifier reaches every holder — and otherwise
        only when the name carries the owner prefix, per ``docs/rules.md`` §9 ("Cynthia's" →
        "Cynthia's Garchomp ex", never "Garchomp"). An unknown name against a real gate is False:
        fail-CLOSED, so a modifier is never credited to a body we cannot identify.

    Note for Issue #301 (POC-A2.1/2), which met the same owner families in its `fetch` clauses and
    ruled *"do not invent a substring match on the card name — mark these four `partial`"*: this is
    not that. A substring test is what would claim `Amulet of Hope` for the `Hop's` family; this is a
    normalised PREFIX test, and it answers a different question — the holder of a Tool is one body
    already in play whose name we hold, where #301's four cards ask which cards in a hidden DECK
    satisfy the family. If #301 later wants the deck-side oracle, this is the string half of it, and
    what it still needs is a build-time index over `cards.json` keyed by family.
    """
    if not family:
        return True
    if not name:
        return False
    return normalize_card_name(name).startswith(normalize_card_name(family) + " ")


def _parse_tool_holder_family(card) -> str | None:
    """The owner family a Tool restricts its static modifiers to (``CardStat.holderNameFamily``),
    or None for an unrestricted Tool.

    ONE parse per card, whatever the modifier: Cynthia's Power Weight gates an ``hpBonus``, Hop's
    Choice Band gates a ``damageBoost`` *and* an ``attackCostReduction``, and one field carries all
    of them. A Tool that mixed a gated modifier with an ungated one would have both gated — the
    fail-closed direction (under-credit), and no card in the pool is that shape.
    """
    for text in _skill_texts(card):
        m = _HOLDER_FAMILY_RE.search(text.replace("\n", " "))
        if m:
            return m.group(1)
    return None


# Tool "+N HP" (Hero's Cape unrestricted; Cynthia's Power Weight gated on its owner family, whose
# qualifier `_parse_tool_holder_family` records separately). WHOLE-SENTENCE match: the boost must be
# the sentence's own subject, so a rider-gated variant ("As long as …, the Pokémon this card is
# attached to gets +30 HP") never reaches it. `.` = é, no non-ASCII literal (cross-platform).
_HP_BONUS_RE = re.compile(
    r"^The (?:" + _NAME_FAMILY + r" )?Pok.mon this card is attached to gets \+(\d+) HP")


def _parse_tool_hp_bonus(card) -> int:
    """Flat HP a Pokémon Tool grants its holder, read from the card's skill text — the engine exposes
    no structured field for it (see ``CardStat.hpBonus``). Matches only the UNCONDITIONAL sentence, so
    a rider-gated +HP Tool still parses to 0 (the breakpoint model must not over-credit HP a target
    might not actually get); an OWNER-family qualifier is accepted and its condition travels in
    ``CardStat.holderNameFamily``, which every consumer tests against the candidate holder. 0 when no
    skill matches / a card has no skills."""
    for text in _skill_texts(card):
        for sent in _sentences(text):
            m = _HP_BONUS_RE.match(sent)
            if m:
                return int(m.group(1))
    return 0


# Air Balloon: "The Retreat Cost of the Pokémon this card is attached to is {C}{C} less." The amount is
# written as repeated Colorless symbols, so count them rather than reading a digit.
_RETREAT_TOOL_RE = re.compile(
    r"\bThe Retreat Cost of the Pok.mon this card is attached to is ((?:\{C\})+) less")

# Gravity Gemstone (1166) — the pool's only Tool whose retreat effect is a COST rather than a
# benefit: "As long as the Pokémon this card is attached to is in the Active Spot, the Retreat Cost
# of both Active Pokémon is {C} more." Recorded as a NEGATIVE `retreatReduction` rather than a
# second `retreatIncrease` field: ONE quantity deserves one field, and two fields for one quantity is
# how the sign gets dropped downstream. Every READER OF THIS FIELD was audited for the sign at
# Issue #306 — the four that subtract it now share `Pilot._attached_retreat_delta` and clamp at 0,
# the seven that look for an ENABLING Tool test `> 0` and correctly reject a surcharge. That is a
# narrower claim than "every retreat-cost reader": five sites read the PRINTED `retreatCost` and
# consult no Tool at all, and are enumerated in tests/scouting/test_retreat_cost_grants.py's KNOWN
# DIVERGENCE with their fail directions.
#
# The holder leg is EXACT despite the Active-Spot rider — a body only ever PAYS a Retreat Cost from
# the Active Spot, which is precisely when the clause is live. The symmetric leg (the OPPONENT's
# Active also pays {C} more) is NOT modelled: no per-card field on my Tool can carry a fact about
# their body.
#
# Note the fail-closed direction INVERTS for a cost. The battery's shared doctrine — match only the
# clean unconditional phrasing, because under-crediting never over-credits — is written for
# benefits; missing a PENALTY makes a retreat look cheaper than it is, which is the retreat-happy
# pathology `_effective_retreat_cost` exists to avoid. So this matches the core clause without
# requiring the Active-Spot rider: over-charging a retreat errs toward not retreating, the safe way.
_RETREAT_TOOL_MORE_RE = re.compile(
    r"\bthe Retreat Cost of both Active Pok.mon is ((?:\{C\})+) more")


def _parse_tool_retreat_reduction(card) -> int:
    """Energy a Pokémon Tool shaves off its holder's Retreat Cost (``CardStat.retreatReduction``),
    read from the card's skill text — the engine exposes no structured field. Unconditional phrasing
    only; anything else parses to 0 (under-credit never over-credits a retreat the body can't pay).

    NEGATIVE for a Tool that makes retreating dearer (Gravity Gemstone −1, i.e. ``{C}`` MORE) — the
    sign is the whole point, so consumers must not assume this is non-negative. All of them were
    audited at Issue #306: the three that subtract it clamp with ``max(0, cost)``, and the four that
    test ``>= need`` / ``> 0`` for an enabling Tool correctly reject a penalty."""
    for text in _skill_texts(card):
        m = _RETREAT_TOOL_RE.search(text)
        if m:
            return m.group(1).count("{C}")
        m = _RETREAT_TOOL_MORE_RE.search(text)
        if m:
            return -m.group(1).count("{C}")
    return 0


# Retreat-cost GRANTS beyond the flat Tool reduction (ADR-0100 §8). The flat read was Tool-only and
# unconditional, and under the convex build-delta cost a missed reduction is worth ~117 damage of
# PHANTOM cost on a 3-slot attacker — systematic on an archetype built around free-retreat pivoting.
# Both parsers are FAIL-CLOSED: an unreadable or unmodelled grant returns nothing, so the caller
# charges the PRINTED cost and errs toward not retreating, never toward the retreat-happy pathology.
#
# Scoped deliberately to the shapes our decks and the tracked meta run — NOT a general effects DSL.
# Verified against `data/EN_Card_Data.csv`: the set holds six retreat-grant texts beyond Air
# Balloon's flat one, and the deck scan puts Latias ex in `slowking` and Air Balloon in
# `grimmsnarl_ex`/`mega_lucario`.

# Rescue Board: "…is {C} less. If that Pokémon's remaining HP is 30 or less, it has no Retreat Cost."
# The flat leg is already `_RETREAT_TOOL_RE`'s; this is the CONDITIONAL second sentence.
_RETREAT_FREE_AT_HP_RE = re.compile(
    r"If that Pok.mon.s remaining HP is (\d+) or less, it has no Retreat Cost")

#: Board-level grant predicates we can evaluate SOUNDLY, by the phrase that introduces them. A
#: predicate not listed here parses to None even when the sentence clearly grants something — that is
#: the fail-closed direction, and it is why N's Castle ("N's Pokémon in play", a card-NAME family the
#: Pilot has no membership oracle for) is deliberately absent.
_RETREAT_FREE_GRANT_RES = (
    # Latias ex (Skyliner): "Your Basic Pokémon in play have no Retreat Cost." — slowking runs it.
    ("basic", re.compile(r"Your Basic Pok.mon in play have no Retreat Cost")),
    # Archaludon: "All of your Pokémon that have {M} Energy attached have no Retreat Cost."
    ("metal_attached", re.compile(
        r"All of your Pok.mon that have \{M\} Energy attached have no Retreat Cost")),
)


def _skill_texts(card):
    """Every skill text on ``card``, newlines folded to spaces — the shape the card-level parsers
    walk. Folding matches what every attack-level parser does to its own input (``.replace("\\n",
    " ")``), so a phrase the engine happened to wrap cannot silently miss its pattern."""
    for s in (getattr(card, "skills", None) or []):
        text = getattr(s, "text", None)
        if text is None and isinstance(s, dict):
            text = s.get("text")
        if text:
            yield text.replace("\n", " ")


def _parse_tool_retreat_free_at_hp(card) -> int:
    """Remaining HP at or below which an attached Tool zeroes its holder's Retreat Cost entirely
    (``CardStat.retreatFreeAtHp``) — Rescue Board's 30. 0 when the card carries no such clause.

    Separate from ``retreatReduction`` because the two legs of Rescue Board are different facts: the
    flat ``{C}`` always applies, the zeroing only below the threshold."""
    for text in _skill_texts(card):
        m = _RETREAT_FREE_AT_HP_RE.search(text)
        if m:
            return int(m.group(1))
    return 0


def _parse_retreat_free_grant(card):
    """The PREDICATE name of a board-level Ability granting no Retreat Cost
    (``CardStat.retreatFreeGrant``), or None.

    Board-level because the granting body is not the one retreating — the engine cannot supply this
    at all: ``retreatCost`` exists only on ``CardData`` as the static PRINTED value, and the in-play
    ``Pokemon`` carries no effective-cost field. The caller evaluates the predicate against the body
    that wants to retreat."""
    for text in _skill_texts(card):
        for name, pattern in _RETREAT_FREE_GRANT_RES:
            if pattern.search(text):
                return name
    return None


# Attack-rider parsers (ADR-0022 #2/#14): recoil/bench-snipe amount lives only in free-text (no
# engine field). Whole-sentence UNCONDITIONAL match only; conditional riders parse to 0 (safe: under-credit never).
_RECOIL_RE = re.compile(r"This Pok.mon (?:also )?does (\d+) damage to itself\.?$")
_BENCH_SNIPE_RE = re.compile(
    r"This attack also does (\d+) damage to 1 of your opponent.s Benched Pok.mon\.?$")
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


# Ability-FUEL energy (ADR-0032): a Pokémon Ability gated on the Pokémon's OWN attached Energy of a
# specific colour ("if this Pokémon has any {D} Energy attached" — Munkidori's Adrena-Brain). That
# colour is a REQUIRED energy for the body even though it is never one of its attack costs, so the
# energy-routing signals must credit it. Anchored on "this Pokémon has … attached" so an
# accelerator's "attach a {X} Energy" action (a different phrasing) never matches.
_ABILITY_FUEL_RE = re.compile(r"this Pok.mon has (?:any )?\{(\w)\} Energy attached")


def parse_card_ability_energy(card) -> tuple:
    """Energy-type codes a card's Ability requires ATTACHED to itself as fuel (ADR-0032).

    Args:
        card: an engine ``CardData``-shaped record (``skills`` with ``text``).

    Returns:
        The EnergyType ids the card's Ability is gated on (Munkidori Adrena-Brain → ``(7,)`` for
        {D}); empty when no Ability references its own attached Energy. De-duplicated, order-stable.
        The routing complement to ``AttackStat.energyTypes`` — an attack-cost-only credit misses a
        colour a body needs solely to switch its Ability on.
    """
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

# The DECK-source accel sibling ("Search your deck for … Energy … and attach …" — Turbo Flare,
# the Kaguras, Burning/Humming Charge, Energy Gift; pool-verified 2026-07-18: 21 deck-attach
# attacks, 13 in this standard shape). The fuel pool differs (hidden deck, not the visible
# discard) but the mechanic — attack + accelerate — is the same family. Deliberately UNMATCHED
# (endorser under-counts, never over-credits): scope-locked targets ("your Future/Tera Pokémon",
# "your Benched {G} Pokémon" — a scope the parser can't verify), the per-bench form ("For each
# of your Benched Pokémon, search…"), multi-type twin clauses (Jolting Charge), and — via the
# coin guard below — flip-gated variants (Kaleidowaltz, Gormandizer).
_DECK_ACCEL_RE = re.compile(
    r"Search your deck for (?:up to (\d+) |an? )Basic(?: \{(\w)\})? Energy cards? and attach "
    r"(?:them|it) to (this Pok.mon|(?:1 of )?your Benched Pok.mon|(?:1 of )?your Pok.mon)")
_COIN_GUARD_RE = re.compile(r"[Ff]lip .*coin")   # a coin-gated accel is not an unconditional credit


# The damage-boost Trainer families (the OHKO-line model's card facts). An Item/Supporter grants
# "During this turn, attacks used by your [{X}] Pokémon do N more damage to your opponent's Active
# Pokémon [{ex}]"; a Tool grants it while attached. Both "(before applying Weakness and
# Resistance)" — the oracle adds the boost BEFORE the W/R step. Multi-mode cards ("Choose 1" —
# Kieran) are fail-closed: the boost is only one of their modes, so no flat fact is sound.
_BOOST_TURN_RE = re.compile(
    r"During this turn, attacks used by your (?:\{(\w)\} )?Pok.mon do (\d+) more damage to your "
    r"opponent.s Active Pok.mon( \{ex\})?")
# The Tool leg accepts BOTH widenings Hop's Choice Band needs (Issue #306): an owner-family
# qualifier in the subject (recorded by `_parse_tool_holder_family`, never re-read here) and the
# attack-cost clause that precedes the damage clause in the same sentence — "Attacks used by the
# Hop's Pokémon this card is attached to cost {C} less AND do 30 more damage …". The cost leg is a
# second, independent fact; `_parse_tool_attack_cost_reduction` reads it.
_BOOST_TOOL_RE = re.compile(
    r"Attacks used by the (?:" + _NAME_FAMILY + r" )?Pok.mon this card is attached to "
    r"(?:cost (?:\{C\})+ less and )?do (\d+) more damage to your "
    r"opponent.s Active Pok.mon( \{ex\})?")

# The Tool-granted ATTACK-COST discount (`CardStat.attackCostReduction`). Hop's Choice Band is the
# only card in the pool that grants one and no CardStat field could express it before Issue #306 —
# justified on its 0.80 meta-weighted copies (the single most-played Tool we face), not on
# generality. Amount is written as repeated Colorless symbols, so count them, as Air Balloon's is.
# WHOLE-SENTENCE anchored (`^`), unlike the damage leg above, which shipped unanchored and is left
# byte-compatible. A new fact gets the stricter guard: a discount that is the sentence's own subject
# is unconditional, while "Flip a coin. If heads, attacks used by … cost {C} less" is not, and an
# over-credited discount is what manufactures a phantom affordable attack.
_ATTACK_COST_TOOL_RE = re.compile(
    r"^Attacks used by the (?:" + _NAME_FAMILY + r" )?Pok.mon this card is attached to "
    r"cost ((?:\{C\})+) less")


def _parse_tool_attack_cost_reduction(card) -> int:
    """Energy a Pokémon Tool shaves off its holder's ATTACK costs (``CardStat.attackCostReduction``)
    — Hop's Choice Band's ``{C}`` → 1; 0 for every other card in the pool.

    Unconditional phrasing only (an owner-family qualifier is allowed and travels in
    ``CardStat.holderNameFamily``). Under-crediting is the safe direction here in both readings: on
    MY side an unread discount only means an attack looks less affordable than it is, and on the
    opponent's it only means their clock reads slower — never that a KO we cannot pay for is
    claimed."""
    for text in _skill_texts(card):
        for sent in _sentences(text):
            m = _ATTACK_COST_TOOL_RE.match(sent)
            if m:
                return m.group(1).count("{C}")
    return 0


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


def parse_attack_energy_recover(text: str) -> tuple[int, int | None, str, str] | None:
    """Energy-accel rider read from attack text: ``(n, basicEnergyType|None, target, source)``.

    Both zone families of the attach-rider mechanic: ``source == "discard"`` (the recover
    family — Aura Jab) and ``source == "deck"`` (the search-attach family — Turbo Flare,
    the Kaguras). A coin-gated deck accel (Kaleidowaltz) is NOT parsed — the credit must
    stay unconditional.

    Args:
        text: the attack's free-text effect.

    Returns:
        e.g. Aura Jab → ``(3, 6, "bench", "discard")``; Turbo Flare → ``(3, None, "bench",
        "deck")``; Regi Charge → ``(2, 3, "self", "discard")``. None when the attack
        attaches nothing.
    """
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
