"""Seed ChainDefs for the FULL card pool → `src/cgpy/defs/generated_chains.json` (ADR-0050 M4).

The machine layer under `chain_overrides.json` (overrides WIN per chain key). Seed sources in
priority order:

(a) structured tables — textless ("vanilla") attacks and skill-less Pokémon get empty defs
    for free; basic energies likewise.
(b) sentence-anchored text rules (ids ``R-…``) over the formulaic effect texts: a chain is
    seeded ONLY when EVERY sentence of its text is consumed by a rule — one leftover
    sentence defers the whole chain (never guess half a card).
(c) everything unmatched → an explicit ``{"deferred": reason}`` entry plus a queue entry in
    ``reports/parity/unparsed_sentences.json`` grouped by template hash — the hand-authoring
    queue, ordered by meta play-rate when `data/meta` is present (count otherwise).

Every generated entry carries a ``_seed`` provenance key (rule ids / table source); the
loader ignores underscore keys. Regenerate wholesale — never hand-edit the output (that's
what `chain_overrides.json` is for).

    python tools/parity/seed_chains.py            # regenerate defs + report
    python tools/parity/seed_chains.py --stats    # print rollup only, write nothing
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from cgpy.schema import CardType, EnergyType, SpecialConditionType  # noqa: E402

DEFS = REPO / "src" / "cgpy" / "defs"
OUT = DEFS / "generated_chains.json"
REPORT = REPO / "reports" / "parity" / "unparsed_sentences.json"

_TYPE_LETTER = {"G": int(EnergyType.GRASS), "R": int(EnergyType.FIRE),
                "W": int(EnergyType.WATER), "L": int(EnergyType.LIGHTNING),
                "P": int(EnergyType.PSYCHIC), "F": int(EnergyType.FIGHTING),
                "D": int(EnergyType.DARKNESS), "M": int(EnergyType.METAL),
                "N": int(EnergyType.DRAGON), "C": int(EnergyType.COLORLESS)}

_COND = {"Poisoned": int(SpecialConditionType.POISON),
         "Burned": int(SpecialConditionType.BURN),
         "Asleep": int(SpecialConditionType.SLEEP),
         "Paralyzed": int(SpecialConditionType.PARALYZE),
         "Confused": int(SpecialConditionType.CONFUSE)}


# ---------------------------------------------------------------------------- text prep

def sentences(text: str) -> list[str]:
    """Effect text → trimmed sentences. The tables use NBSP/em-space glue around
    parentheticals; normalize every unicode space to ASCII before splitting."""
    t = re.sub(r"[   　]", " ", text or "").replace("\n", " ")
    t = re.sub(r"\s+", " ", t).strip()
    if not t:
        return []
    # Split after ./!/? followed by space — but never inside a parenthetical
    # ("(Pokémon {ex}, etc. have Rule Boxes.)" is ONE sentence).
    out: list[str] = []
    buf: list[str] = []
    depth = 0
    for ch in t:
        buf.append(ch)
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch in ".!?" and depth == 0:
            s = "".join(buf).strip()
            if s:
                out.append(s)
            buf = []
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    # "…damage.(Don't apply …)" arrives glued — split the paren off as its own sentence.
    final: list[str] = []
    for s in out:
        m = re.match(r"^(.*?\.)(\(.+\))$", s)
        if m:
            final += [m.group(1).strip(), m.group(2).strip()]
        else:
            final.append(s)
    return final


def template(s: str) -> str:
    t = re.sub(r"\d+", "N", s)
    t = re.sub(r"\{\w\}", "{X}", t)
    return t


# ---------------------------------------------------------------------------- search-spec grammar

_QTY_RE = re.compile(r"^(?:(a|an|1) |up to (\d+) |(any number of) )(.*)$")

# noun phrase → cgpy card filter (chain._card_matches vocabulary). Longest match wins.
_NOUN_FILTERS: list[tuple[re.Pattern, dict]] = [
    (re.compile(r"^Basic \{(\w)\} Energy cards?$"), {"basicEnergy": True, "energyType": None}),
    (re.compile(r"^Basic Energy cards?$"), {"basicEnergy": True}),
    (re.compile(r"^Basic Pok.mon with (\d+) HP or less$"),
     {"pokemon": True, "basic": True, "hpMax": None}),
    (re.compile(r"^Basic (\w+.s) Pok.mon$"),
     {"pokemon": True, "basic": True, "nameContains": None}),
    (re.compile(r"^Basic \{(\w)\} Pok.mon$"),
     {"pokemon": True, "basic": True, "energyType": None}),
    (re.compile(r"^Basic Pok.mon$"), {"pokemon": True, "basic": True}),
    (re.compile(r"^(\w+.s) Pok.mon$"),          # "Misty's Pokémon" (possessive family)
     {"pokemon": True, "nameContains": None}),
    (re.compile(r"^Pok.mon that have .(\w+). in their name$"),
     {"pokemon": True, "nameContains": None}),
    (re.compile(r"^Pok.mon with \{(\w)\} Resistance$"),
     {"pokemon": True, "resistanceType": None}),
    (re.compile(r"^Stage 1 Pok.mon$"), {"pokemon": True, "stage1": True}),
    (re.compile(r"^Stage 2 Pok.mon$"), {"pokemon": True, "stage2": True}),
    (re.compile(r"^Tera Pok.mon$"), {"pokemon": True, "tera": True}),
    (re.compile(r"^Pok.mon that don.t have a Rule Box$"),
     {"pokemon": True, "noRuleBox": True}),
    (re.compile(r"^\{(\w)\} Pok.mon$"), {"pokemon": True, "energyType": None}),
    (re.compile(r"^Pok.mon$"), {"pokemon": True}),
    (re.compile(r"^Mega Evolution Pok.mon$"), {"megaEx": True}),
    (re.compile(r"^Evolution Pok.mon$"), {"evolution": True}),
    (re.compile(r"^Item cards?$"), {"cardType": [int(CardType.ITEM)]}),
    (re.compile(r"^Supporter cards?$"), {"cardType": [int(CardType.SUPPORTER)]}),
    (re.compile(r"^Stadium cards?$"), {"cardType": [int(CardType.STADIUM)]}),
    (re.compile(r"^Pok.mon Tool cards?$"), {"cardType": [int(CardType.TOOL)]}),
    (re.compile(r"^Energy cards?$"),
     {"cardType": [int(CardType.BASIC_ENERGY), int(CardType.SPECIAL_ENERGY)]}),
]


_CSV_CATEGORIES: dict[str, list] | None = None


def _csv_categories() -> dict[str, list]:
    """Card-family tags (Future / Ancient / …) from the OFFICIAL card CSV's Category
    column — no native table carries them (sgc87_9300 f51 proves the engine filters
    by family). CSV Card ID == engine cardId (verified: 27 Iron Leaves, 87 Miraidon)."""
    global _CSV_CATEGORIES
    if _CSV_CATEGORIES is None:
        import csv as _csv
        out: dict[str, set] = {}
        with open(REPO / "data" / "EN_Card_Data.csv", encoding="utf-8-sig",
                  newline="") as f:
            for row in _csv.DictReader(f):
                out.setdefault(row["Category"], set()).add(int(row["Card ID"]))
        _CSV_CATEGORIES = {k: sorted(v) for k, v in out.items()}
    return _CSV_CATEGORIES


_CARD_NAMES: dict[str, set] | None = None


def _card_names() -> dict[str, set]:
    """Exact card-name sets from the snapshot tables (bare-species noun validation)."""
    global _CARD_NAMES
    if _CARD_NAMES is None:
        cards = json.loads((DEFS / "card_data.json").read_text(encoding="utf-8"))
        _CARD_NAMES = {
            "pokemon": {c["name"] for c in cards if c["cardType"] == 0},
            "all": {c["name"] for c in cards},
        }
    return _CARD_NAMES


def _noun_filter(noun: str) -> dict | None:
    for pat, proto in _NOUN_FILTERS:
        pm = pat.match(noun)
        if pm:
            flt = {k: v for k, v in proto.items() if v is not None}
            if "energyType" in proto and proto["energyType"] is None:
                letter = pm.group(1)
                if letter not in _TYPE_LETTER:
                    return None
                flt["energyType"] = [_TYPE_LETTER[letter]]
            if "resistanceType" in proto and proto["resistanceType"] is None:
                letter = pm.group(1)
                if letter not in _TYPE_LETTER:
                    return None
                flt["resistanceType"] = [_TYPE_LETTER[letter]]
            if "hpMax" in proto and proto["hpMax"] is None:
                flt["hpMax"] = int(pm.group(1))
            if "nameContains" in proto and proto["nameContains"] is None:
                flt["nameContains"] = pm.group(1)
            return flt
    # Bare exact-name nouns, DB-validated: "Froakie" (a Pokémon species) or
    # "Fennel cards" (copies of a named trainer). Unknown names never match.
    m = re.match(r"^(.+?) cards?$", noun)
    if m and m.group(1) in _card_names()["all"]:
        return {"name": m.group(1)}
    if noun in _card_names()["pokemon"]:
        return {"pokemon": True, "name": noun}
    return None


def parse_search_spec(spec: str) -> tuple[int, dict] | None:
    """"up to 2 Basic Pokémon with 70 HP or less" → ``(max_count, filter)`` or None.
    "any number of" quantifies as 60 (the op layer clamps to matches/bench room).
    "in any combination of X and Y" → an ``anyOf`` union filter."""
    m = _QTY_RE.match(spec.strip())
    if not m:
        return None
    n = 1 if m.group(1) else (int(m.group(2)) if m.group(2) else 60)
    noun = m.group(4).strip().rstrip(",")
    cm = re.match(r"^in any combination of (.+)$", noun)
    if cm:
        parts = [p.strip() for p in cm.group(1).split(" and ")]
        subs = [_noun_filter(p) for p in parts]
        if len(parts) < 2 or any(s is None for s in subs):
            return None
        return (n, {"anyOf": subs})
    flt = _noun_filter(noun)
    return (n, flt) if flt is not None else None


# ---------------------------------------------------------------------------- rule engine

class Frag:
    """One consumed fragment: ops (by phase) and/or def fields, with rule provenance."""

    def __init__(self, rule: str, *, pre: list | None = None, rider: list | None = None,
                 play: list | None = None, fields: dict | None = None,
                 legal: list | None = None):
        self.rule = rule
        self.pre = pre or []
        self.rider = rider or []
        self.play = play or []
        self.fields = fields or {}
        self.legal = legal or []


class Rules:
    """Ordered sentence-consuming rules. Each rule sees ``(sents, i)`` and returns
    ``(consumed_count, Frag)`` or None. First match wins; unmatched sentence at ``i``
    defers the whole chain."""

    def __init__(self):
        self.rules: list = []

    def rule(self, rid: str):
        def deco(fn):
            self.rules.append((rid, fn))
            return fn
        return deco

    def consume(self, text: str) -> tuple[list[Frag], list[str]]:
        """→ (fragments, unparsed sentences). Unparsed non-empty ⇒ defer."""
        sents = sentences(text)
        frags: list[Frag] = []
        unparsed: list[str] = []
        i = 0
        while i < len(sents):
            for rid, fn in self.rules:
                got = fn(sents, i)
                if got:
                    k, frag = got
                    if frag is not None:
                        frag.rule = rid
                        frags.append(frag)
                    i += k
                    break
            else:
                unparsed.append(sents[i])
                i += 1
        return frags, unparsed


def _s(pat: str):
    """Anchored single-sentence matcher."""
    rx = re.compile("^" + pat + "$")

    def m(sents, i):
        return rx.match(sents[i])
    return m


# ---------------------------------------------------------------------------- attack rules

ATK = Rules()

_NOISE = [
    r"\(Don.t apply Weakness and Resistance for Benched Pok.mon\.\)",   # cgpy bench damage
    r"\(Damage is not an effect\.\)",                                    # already skips W/R
    r"\(Pok.mon \{ex\}[^)]*have Rule Boxes\.\)",     # rule-box definition parenthetical
]
for _k, _pat in enumerate(_NOISE):
    @ATK.rule(f"R-N{_k:02d}")
    def _noise(sents, i, _m=_s(_pat)):
        return (1, Frag("")) if _m(sents, i) else None


@ATK.rule("R-A01")
def _ignore_wr(sents, i):
    m = _s(r"This attack.s damage isn.t affected by ([^.]+)\.")(sents, i)
    if not m:
        return None
    clause = m.group(1)
    fields = {}
    if "Weakness" in clause:
        fields["ignoreWeakness"] = True
    if "Resistance" in clause:
        fields["ignoreResistance"] = True
    if "effect" in clause:
        fields["ignoreDefenderEffects"] = True   # defender-mods seam (none modeled yet)
    if not fields:
        return None
    return (1, Frag("", fields=fields))


@ATK.rule("R-A05")
def _requires_bench(sents, i):
    m = _s(r"If you don.t have (.{2,60}?) on your Bench, this attack does nothing\.")(sents, i)
    if not m:
        return None
    names = [n.strip() for n in m.group(1).split(" and ") if n.strip()]
    return (1, Frag("", fields={"requiresBenchNamed": names if len(names) > 1 else names[0]}))


@ATK.rule("R-A06")
def _self_lock(sents, i):
    if _s(r"During your next turn, this Pok.mon can.t (?:attack|use attacks)\.")(sents, i):
        return (1, Frag("", fields={"selfLockAllNextTurn": True}))
    m = _s(r"During your next turn, this Pok.mon can.t use ([^.]+)\.")(sents, i)
    if m:
        return (1, Frag("", fields={"selfLockNextTurn": True, "_lockName": m.group(1).strip()}))
    return None


@ATK.rule("R-A14")
def _lock_defender_retreat(sents, i):
    if _s(r"During your opponent.s next turn, (?:the Defending|that) Pok.mon can.t "
          r"retreat\.")(sents, i):
        return (1, Frag("", fields={"lockDefenderRetreat": True}))
    return None


@ATK.rule("R-A19")
def _reduce_defender(sents, i):
    m = _s(r"During your opponent.s next turn, attacks used by the Defending Pok.mon "
           r"do (\d+) less damage \(before applying Weakness and Resistance\)\.")(sents, i)
    if m:
        return (1, Frag("", rider=[{"op": "xReduceDefenderNextTurn",
                                    "n": int(m.group(1))}]))
    return None


@ATK.rule("R-A20")
def _lock_defender_attacks(sents, i):
    if _s(r"During your opponent.s next turn, the Defending Pok.mon can.t use "
          r"attacks\.")(sents, i):
        return (1, Frag("", rider=[{"op": "xLockDefenderAttacks"}]))
    return None


@ATK.rule("R-A15")
def _take_less(sents, i):
    m = _s(r"During your opponent.s next turn, this Pok.mon takes (\d+) less damage from "
           r"attacks \(after applying Weakness and Resistance\)\.")(sents, i)
    if m:
        return (1, Frag("", rider=[{"op": "xTakeLessNextTurn", "n": int(m.group(1))}]))
    return None


@ATK.rule("R-A16")
def _allowed_first_turn(sents, i):
    if _s(r"If you go first, you can use this attack during your first turn\.")(sents, i):
        return (1, Frag("", fields={"allowedFirstTurn": True}))
    return None


@ATK.rule("R-A17")
def _lock_opp_items(sents, i):
    if _s(r"During your opponent.s next turn, they can.t play any Item cards from their "
          r"hand\.")(sents, i):
        return (1, Frag("", fields={"lockOpponentItems": True}))
    return None


_SCALE_SENT: list[tuple[str, str, int]] = [
    # (sentence pattern with one damage group, scaleVar, perUnit multiplier)
    (r"This attack does (\d+) (?:more )?damage for each card in your opponent.s hand\.",
     "def_hand", 1),
    (r"This attack does (\d+) (?:more )?damage for each card in your hand\.", "atk_hand", 1),
    (r"This attack does (\d+) (?:more )?damage for each Energy attached to your opponent.s "
     r"Active Pok.mon\.", "def_active_energy", 1),
    (r"This attack does (\d+) (?:more )?damage for each(?: basic)?(?: \{\w\})? Energy attached "
     r"to this Pok.mon\.", "atk_active_energy", 1),
    (r"This attack does (\d+) (?:more )?damage for each of your opponent.s Benched Pok.mon\.",
     "def_bench", 1),
    (r"This attack does (\d+) (?:more )?damage for each of your Benched Pok.mon\.",
     "atk_bench", 1),
    (r"This attack does (\d+) (?:more )?damage for each damage counter on this Pok.mon\.",
     "atk_self_counters", 1),
    (r"This attack does (\d+) (?:more )?damage for each damage counter on your opponent.s "
     r"Active Pok.mon\.", "def_counters", 1),
    (r"This attack does (\d+) (?:more )?damage for each Prize card you have (?:already )?taken\.",
     "atk_prizes_taken", 1),
    (r"This attack does (\d+) (?:more )?damage for each Prize card your opponent has "
     r"(?:already )?taken\.", "def_prizes_taken", 1),
    (r"This attack does (\d+) (?:more )?damage for each Pok.mon Tool attached to all "
     r"of your Pok.mon\.", "atk_tools_in_play", 1),
    (r"This attack does (\d+) (?:more )?damage for each of your Pok.mon in play\.",
     "atk_in_play", 1),
]


@ATK.rule("R-A08")
def _scaler(sents, i):
    for pat, var, mult in _SCALE_SENT:
        m = _s(pat)(sents, i)
        if m:
            more = " more damage" in sents[i]
            return (1, Frag("", fields={"scale": {"var": var, "per": int(m.group(1)) * mult,
                                                  "add": more}}))
    m = _s(r"This attack does (\d+) (?:more )?damage for each of your Pok.mon in play "
           r"that has the (\w[\w '’-]*?) attack\.")(sents, i)
    if m:
        return (1, Frag("", fields={"scale": {"var": "atk_named_attack",
                                              "attackName": m.group(2),
                                              "per": int(m.group(1)),
                                              "add": " more damage" in sents[i]}}))
    return None


_COND_BONUS: list[tuple[str, str]] = [
    (r"If your opponent.s Active Pok.mon is a Pok.mon \{ex\}, this attack does (\d+) more damage\.",
     "def_active_ex"),
    (r"If your opponent.s Active Pok.mon already has any damage counters on it, this attack does "
     r"(\d+) more damage\.", "def_active_damaged"),
    (r"If a Stadium is in play, this attack does (\d+) more damage\.", "stadium_in_play"),
    (r"If this Pok.mon moved from your Bench to the Active Spot this turn, this attack does "
     r"(\d+) more damage\.", "self_moved_this_turn"),
    (r"If any of your Pok.mon were Knocked Out by damage from an attack during your opponent.s "
     r"last turn, this attack does (\d+) more damage\.", "own_ko_last_turn"),
]


@ATK.rule("R-A09")
def _cond_bonus(sents, i):
    for pat, cond in _COND_BONUS:
        m = _s(pat)(sents, i)
        if m:
            return (1, Frag("", fields={"condBonus": {"cond": cond, "n": int(m.group(1))}}))
    m = _s(r"If your opponent.s Active Pok.mon is a \{(\w)\} Pok.mon, this attack does "
           r"(\d+) more damage\.")(sents, i)
    if m and m.group(1) in _TYPE_LETTER:
        return (1, Frag("", fields={"condBonus": {"cond": "def_active_type",
                                                  "energyType": _TYPE_LETTER[m.group(1)],
                                                  "n": int(m.group(2))}}))
    m = _s(r"If your opponent.s Active Pok.mon is Burned, this attack does (\d+) more "
           r"damage\.")(sents, i)
    if m:
        return (1, Frag("", fields={"condBonus": {"cond": "def_active_burned",
                                                  "n": int(m.group(1))}}))
    m = _s(r"If you have at least (\d+) \{(\w)\} Energy in play, this attack does (\d+) "
           r"more damage\.")(sents, i)
    if m and m.group(2) in _TYPE_LETTER:
        return (1, Frag("", fields={"condBonus": {"cond": "atk_energy_in_play_min",
                                                  "min": int(m.group(1)),
                                                  "energyType": _TYPE_LETTER[m.group(2)],
                                                  "n": int(m.group(3))}}))
    m = _s(r"If this Pok.mon has at least (\d+) extra Energy attached \(in addition to "
           r"this attack.s cost\), this attack does (\d+) more damage\.")(sents, i)
    if m:
        return (1, Frag("", fields={"condBonus": {"cond": "self_extra_energy_min",
                                                  "min": int(m.group(1)),
                                                  "n": int(m.group(2))}}))
    return None


@ATK.rule("R-B01")
def _recoil(sents, i):
    m = _s(r"This Pok.mon (?:also )?does (\d+) damage to itself\.")(sents, i)
    if m:
        return (1, Frag("", rider=[{"op": "xDamageSelf", "damage": int(m.group(1))}]))
    return None


@ATK.rule("R-B02")
def _bench_snipe(sents, i):
    m = _s(r"This attack also does (\d+) damage to (\d+) of your opponent.s Benched "
           r"Pok.mon\.")(sents, i)
    if m:
        return (1, Frag("", rider=[{"op": "xChooseBenchDamage", "damage": int(m.group(1)),
                                    "count": int(m.group(2))}]))
    return None


@ATK.rule("R-B03")
def _heal_self(sents, i):
    m = _s(r"Heal (\d+) damage from this Pok.mon\.")(sents, i)
    if m:
        return (1, Frag("", rider=[{"op": "xHealSelf", "amount": int(m.group(1))}]))
    return None


@ATK.rule("R-B04")
def _discard_own_energy(sents, i):
    m = _s(r"Discard (\d+|an?) Energy from this Pok.mon\.")(sents, i)
    if m:
        n = 1 if m.group(1) in ("a", "an") else int(m.group(1))
        return (1, Frag("", rider=[{"op": "xDiscardOwnEnergy", "n": n}]))
    if _s(r"Discard all Energy from this Pok.mon\.")(sents, i):
        return (1, Frag("", rider=[{"op": "xDiscardAllOwnEnergy"}]))
    return None


@ATK.rule("R-B06")
def _inflict(sents, i):
    m = _s(r"Your opponent.s Active Pok.mon is now (Poisoned|Burned|Asleep|Paralyzed|"
           r"Confused)\.")(sents, i)
    if m:
        return (1, Frag("", rider=[{"op": "xInflictConditionActive",
                                    "condition": _COND[m.group(1)]}]))
    return None


@ATK.rule("R-B07")
def _draw(sents, i):
    m = _s(r"Draw (\d+|a) cards?\.")(sents, i)
    if m:
        n = 1 if m.group(1) == "a" else int(m.group(1))
        return (1, Frag("", rider=[{"op": "effectDraw", "n": n}]))
    return None


@ATK.rule("R-B08")
def _switch_self(sents, i):
    if _s(r"Switch this Pok.mon with 1 of your Benched Pok.mon\.")(sents, i):
        return (1, Frag("", rider=[{"op": "effectSwitchMe"}]))
    return None


@ATK.rule("R-B09")
def _opp_switches(sents, i):
    if not _s(r"Switch out your opponent.s Active Pok.mon to the Bench\.")(sents, i):
        return None
    k = 1
    if i + 1 < len(sents) and _s(r"\(Your opponent chooses the new Active "
                                 r"Pok.mon\.\)")(sents, i + 1):
        k = 2
    return (k, Frag("", rider=[{"op": "xOpponentSwitches"}]))


# --- coin composites (order: specific pairs first, bare flip last) ------------------------

@ATK.rule("R-C01")
def _coin_fail(sents, i):
    if (i + 1 < len(sents) and _s(r"Flip a coin\.")(sents, i)
            and _s(r"If tails, this attack does nothing\.")(sents, i + 1)):
        return (2, Frag("", pre=[{"op": "coin"}, {"op": "xFailUnlessHeads"}]))
    return None


@ATK.rule("R-C02")
def _coin_bonus(sents, i):
    if i + 1 >= len(sents) or not _s(r"Flip a coin\.")(sents, i):
        return None
    m = _s(r"If heads, this attack does (\d+) more damage\.")(sents, i + 1)
    if m:
        return (2, Frag("", pre=[{"op": "coin"},
                                 {"op": "xBonusIfHeads", "n": int(m.group(1))}]))
    return None


@ATK.rule("R-C03")
def _coins_per_heads(sents, i):
    m0 = _s(r"Flip (\d+) coins\.")(sents, i)
    if not m0 or i + 1 >= len(sents):
        return None
    m = _s(r"This attack does (\d+) damage for each heads\.")(sents, i + 1)
    if m:
        return (2, Frag("", pre=[{"op": "xCoinsCount", "n": int(m0.group(1))},
                                 {"op": "xDamagePerHeads", "per": int(m.group(1))}]))
    m = _s(r"This attack does (\d+) more damage for each heads\.")(sents, i + 1)
    if m:
        return (2, Frag("", pre=[{"op": "xCoinsCount", "n": int(m0.group(1))},
                                 {"op": "xBonusPerHeads", "per": int(m.group(1))}]))
    return None


@ATK.rule("R-C05")
def _coins_until_tails(sents, i):
    if not _s(r"Flip a coin until you get tails\.")(sents, i) or i + 1 >= len(sents):
        return None
    m = _s(r"This attack does (\d+) damage for each heads\.")(sents, i + 1)
    if m:
        return (2, Frag("", pre=[{"op": "xCoinsUntilTails"},
                                 {"op": "xDamagePerHeads", "per": int(m.group(1))}]))
    m = _s(r"This attack does (\d+) more damage for each heads\.")(sents, i + 1)
    if m:
        return (2, Frag("", pre=[{"op": "xCoinsUntilTails"},
                                 {"op": "xBonusPerHeads", "per": int(m.group(1))}]))
    return None


@ATK.rule("R-C07")
def _coins_per_energy(sents, i):
    m0 = _s(r"Flip a coin for each(?: \{(\w)\})? Energy attached to this Pok.mon\.")(sents, i)
    if not m0 or i + 1 >= len(sents):
        return None
    et = None
    if m0.group(1):
        if m0.group(1) not in _TYPE_LETTER:
            return None
        et = _TYPE_LETTER[m0.group(1)]
    coin_op: dict = {"op": "xCoinsCount", "var": "atk_active_energy"}
    if et is not None:
        coin_op["energyType"] = et
    m = _s(r"This attack does (\d+) damage for each heads\.")(sents, i + 1)
    if m:
        return (2, Frag("", pre=[coin_op, {"op": "xDamagePerHeads", "per": int(m.group(1))}]))
    m = _s(r"This attack does (\d+) more damage for each heads\.")(sents, i + 1)
    if m:
        return (2, Frag("", pre=[coin_op, {"op": "xBonusPerHeads", "per": int(m.group(1))}]))
    return None


@ATK.rule("R-C09")
def _coin_protect(sents, i):
    if (i + 1 < len(sents) and _s(r"Flip a coin\.")(sents, i)
            and _s(r"If heads, during your opponent.s next turn, prevent all damage "
                   r"from and effects of attacks done to this Pok.mon\.")(sents, i + 1)):
        return (2, Frag("", rider=[{"op": "coin"}, {"op": "ifHeads", "skip": 1},
                                   {"op": "xProtectNextTurn"}]))
    return None


@ATK.rule("R-C06")
def _coin_rider(sents, i):
    """Flip a coin. If heads, <known rider clause>. — post-damage coin-gated rider."""
    if not _s(r"Flip a coin\.")(sents, i) or i + 1 >= len(sents):
        return None
    m = _s(r"If heads, your opponent.s Active Pok.mon is now (Poisoned|Burned|Asleep|"
           r"Paralyzed|Confused)\.")(sents, i + 1)
    if m:
        return (2, Frag("", rider=[{"op": "coin"}, {"op": "ifHeads", "skip": 1},
                                   {"op": "xInflictConditionActive",
                                    "condition": _COND[m.group(1)]}]))
    m = _s(r"If heads, discard an Energy from your opponent.s Active Pok.mon\.")(sents, i + 1)
    if m:
        return (2, Frag("", rider=[{"op": "coin"}, {"op": "ifHeads", "skip": 1},
                                   {"op": "trashEnergyEnemy", "activeOnly": True}]))
    return None


@ATK.rule("R-B10")
def _discard_opp_energy(sents, i):
    if _s(r"Discard an Energy from your opponent.s Active Pok.mon\.")(sents, i):
        return (1, Frag("", rider=[{"op": "trashEnergyEnemy", "activeOnly": True}]))
    return None


@ATK.rule("R-B12")
def _own_bench_each(sents, i):
    m = _s(r"This attack also does (\d+) damage to each of your Benched "
           r"Pok.mon\.")(sents, i)
    if m:
        return (1, Frag("", rider=[{"op": "xDamageOwnBenchEach", "damage": int(m.group(1))}]))
    return None


@ATK.rule("R-B13")
def _free_target_snipe(sents, i):
    m = _s(r"This attack does (\d+) damage to (\d+) of your opponent.s Pok.mon\.")(sents, i)
    if m:
        return (1, Frag("", rider=[{"op": "xChooseAnyDamage", "damage": int(m.group(1)),
                                    "count": int(m.group(2))}]))
    return None


@ATK.rule("R-B14")
def _self_condition(sents, i):
    m = _s(r"This Pok.mon is now (Poisoned|Burned|Asleep|Paralyzed|Confused)\.")(sents, i)
    if m:
        return (1, Frag("", rider=[{"op": "xInflictConditionSelf",
                                    "condition": _COND[m.group(1)]}]))
    return None


@ATK.rule("R-B15")
def _mill(sents, i):
    m = _s(r"Discard the top (\d+ )?cards? of your opponent.s deck\.")(sents, i)
    if m:
        return (1, Frag("", rider=[{"op": "xMill", "who": "opp",
                                    "n": int(m.group(1)) if m.group(1) else 1}]))
    m = _s(r"Discard the top (\d+ )?cards? of your deck\.")(sents, i)
    if m:
        return (1, Frag("", rider=[{"op": "xMill", "who": "self",
                                    "n": int(m.group(1)) if m.group(1) else 1}]))
    return None


@ATK.rule("R-B28")
def _opp_hand_discard_random(sents, i):
    """The hand-pick rng channel (Psych Out family): random discard from the
    opponent's hand, plain or until-N-left (Hand Trim)."""
    if _s(r"Discard a random card from your opponent.s hand\.")(sents, i):
        return (1, Frag("", rider=[{"op": "xOppHandDiscardRandom", "n": 1}]))
    m = _s(r"Discard random cards from your opponent.s hand until they have (\d+) "
           r"cards? in their hand\.")(sents, i)
    if m:
        n = int(m.group(1))
        # Menu-gated: the engine hides the attack until the opponent holds MORE than n
        # (pinned onboard1076a1554: 6 offers, 5 hides). Plain 1-card variants are NOT
        # gated — offered at oppHand 0 (onboard103a130_9901 f39 etc.).
        return (1, Frag("", rider=[{"op": "xOppHandDiscardRandom", "untilLeft": n}],
                        legal=[{"op": "oppHandAbove", "n": n}]))
    return None


@ATK.rule("R-B29")
def _opp_hand_shuffle_in_random(sents, i):
    """Astonish class: random pick from the opponent's hand, revealed, shuffled into
    their deck — two-sentence and comma-joined single-sentence prints."""
    if _s(r"Choose a random card from your opponent.s hand, and your opponent reveals "
          r"that card and shuffles it into their deck\.")(sents, i):
        return (1, Frag("", rider=[{"op": "xOppHandShuffleInRandom", "n": 1}]))
    if (_s(r"Choose a random card from your opponent.s hand\.")(sents, i)
            and i + 1 < len(sents)
            and _s(r"Your opponent reveals that card and shuffles it into their "
                   r"deck\.")(sents, i + 1)):
        return (2, Frag("", rider=[{"op": "xOppHandShuffleInRandom", "n": 1}]))
    return None


@ATK.rule("R-F01")
def _sand_attack_gate(sents, i):
    """Sand Attack: arm the defender-side attack-gate coin (the fire path lives in
    turn.py's attack flow; arming pinned cn139_9000)."""
    if (_s(r"During your opponent.s next turn, if the Defending Pok.mon tries to use "
           r"an attack, your opponent flips a coin\.")(sents, i)
            and i + 1 < len(sents)
            and _s(r"If tails, that attack doesn.t happen\.")(sents, i + 1)):
        return (2, Frag("", rider=[{"op": "xGateDefenderAttacksCoin"}]))
    return None


@ATK.rule("R-F02")
def _coin_single_composites(sents, i):
    """"Flip a coin." + one pinned follow-up clause (or two for the branch prints)."""
    if not _s(r"Flip a coin\.")(sents, i) or i + 1 >= len(sents):
        return None
    nxt = sents[i + 1]
    third = sents[i + 2] if i + 2 < len(sents) else None
    # Mystical Return / Reversing Gust: heads -> choose + shuffle-in (3 sentences)
    m = re.match(r"^If heads, choose 1 of your opponent.s (Benched )?Pok.mon\.$", nxt)
    if m and third is not None and re.match(
            r"^Shuffle that Pok.mon and all attached cards into their deck\.$", third):
        scope = "bench" if m.group(1) else "any"
        # the benched flavor is menu-gated on an opponent bench (pinned cn173_9000
        # f13: RETREAT where cgpy offered the attack); "any" always has the Active
        gate = [{"op": "oppBenchExists"}] if scope == "bench" else []
        return (3, Frag("", rider=[{"op": "coin"}, {"op": "ifHeads", "skip": 1},
                                   {"op": "xShuffleInPlayIntoDeckChoose",
                                    "scope": scope}], legal=gate))
    # Swinging Sphene: heads -> KO Active Basic / tails -> KO a Benched Basic
    # (ifHeads guards the HEADS branch: tails skips over it — pinned cn259_9000 f16)
    if (re.match(r"^If heads, Knock Out your opponent.s Active Basic Pok.mon\.$", nxt)
            and third is not None and re.match(
                r"^If tails, Knock Out 1 of your opponent.s Benched Basic "
                r"Pok.mon\.$", third)):
        return (3, Frag("", rider=[{"op": "coin"},
                                   {"op": "ifHeads", "skip": 2},
                                   {"op": "xKnockOutActive", "basicOnly": True},
                                   {"op": "xSkip", "n": 1},
                                   {"op": "xKnockOutChoose", "scope": "bench",
                                    "basicOnly": True}]))
    # Bemusing Aroma: heads -> Paralyzed+Poisoned / tails -> Confused (POISON logs
    # first on heads — pinned cn686_9000 f14)
    if (re.match(r"^If heads, your opponent.s Active Pok.mon is now Paralyzed and "
                 r"Poisoned\.$", nxt)
            and third is not None
            and re.match(r"^If tails, your opponent.s Active Pok.mon is now "
                         r"Confused\.$", third)):
        P = int(SpecialConditionType.POISON)
        PA = int(SpecialConditionType.PARALYZE)
        C = int(SpecialConditionType.CONFUSE)
        return (3, Frag("", rider=[{"op": "coin"},
                                   {"op": "ifHeads", "skip": 3},
                                   {"op": "xInflictConditionActive", "condition": P},
                                   {"op": "xInflictConditionActive", "condition": PA},
                                   {"op": "xSkip", "n": 1},
                                   {"op": "xInflictConditionActive", "condition": C}]))
    # Thump-Thump Boom's tail pair rides after R-B01's recoil: heads -> opp Active KO'd
    if re.match(r"^If heads, your opponent.s Active Pok.mon is Knocked Out\.$", nxt):
        return (2, Frag("", rider=[{"op": "coin"}, {"op": "ifHeads", "skip": 1},
                                   {"op": "xKnockOutActive"}]))
    # Cotton Wings / Iron Defense: heads -> prevent all DAMAGE next turn (damage-only
    # variant of the Dig-family protect; arming pinned cn1205_9600 f9)
    if re.match(r"^If heads, during your opponent.s next turn, prevent all damage done "
                r"to this Pok.mon by attacks\.$", nxt):
        return (2, Frag("", rider=[{"op": "coin"}, {"op": "ifHeads", "skip": 1},
                                   {"op": "xProtectNextTurn", "damageOnly": True}]))
    # Power Rush: tails -> this Pokémon can't attack next turn (pinned cn1125: rider
    # coin after the HP_CHANGE)
    if re.match(r"^If tails, during your next turn, this Pok.mon can.t use "
                r"attacks\.$", nxt):
        return (2, Frag("", rider=[{"op": "coin"}, {"op": "ifTails", "skip": 1},
                                   {"op": "xSelfLockAllNextTurn"}]))
    # Magical Leaf: heads -> +30 AND heal 30 (pre coin feeds the rider heal through
    # the inherited-vars threading; coin logs before HP — pinned cn1329)
    m = re.match(r"^If heads, this attack does (\d+) more damage, and heal (\d+) "
                 r"damage from this Pok.mon\.$", nxt)
    if m:
        return (2, Frag("", pre=[{"op": "coin"},
                                 {"op": "xBonusIfHeads", "n": int(m.group(1))}],
                        rider=[{"op": "ifHeads", "skip": 1},
                               {"op": "xHealSelf", "amount": int(m.group(2))}]))
    # Miraculous Paint: heads -> choose a Special Condition and inflict it (ctx 47
    # SPECIAL_CONDITION select — pinned cn1003_9701 f15)
    if (re.match(r"^If heads, choose a Special Condition\.$", nxt)
            and third is not None
            and re.match(r"^Your opponent.s Active Pok.mon is now affected by that "
                         r"Special Condition\.$", third)):
        return (3, Frag("", rider=[{"op": "coin"}, {"op": "ifHeads", "skip": 1},
                                   {"op": "xChooseConditionInflict"}]))
    return None


@ATK.rule("R-F03")
def _coin_multi_composites(sents, i):
    """"Flip N coins." / until-tails / per-mon flip composites."""
    m0 = _s(r"Flip (\d+) coins\.")(sents, i)
    until = _s(r"Flip a coin until you get tails\.")(sents, i)
    if (m0 or until) and i + 1 < len(sents):
        head_op = ({"op": "xCoinsCount", "n": int(m0.group(1))} if m0
                   else {"op": "xCoinsUntilTails"})
        nxt = sents[i + 1]
        third = sents[i + 2] if i + 2 < len(sents) else None
        shuffle_next = (third is not None
                        and re.match(r"^Then, shuffle your deck\.$", third))
        # Reckless Abandon: both tails -> recoil (pinned cn662)
        m = re.match(r"^If both of them are tails, this Pok.mon also does (\d+) "
                     r"damage to itself\.$", nxt)
        if m:
            return (2, Frag("", rider=[head_op, {"op": "xDamageSelfIfNoHeads",
                                                 "damage": int(m.group(1))}]))
        # Hyper Lariat: both heads -> more damage (pre — pinned cn1102)
        m = re.match(r"^If both of them are heads, this attack does (\d+) more "
                     r"damage\.$", nxt)
        if m:
            return (2, Frag("", pre=[head_op, {"op": "xBonusIfAllHeads",
                                               "n": int(m.group(1))}]))
        # Bellyful of Milk: both heads -> full-heal one of yours
        if re.match(r"^If both of them are heads, heal all damage from 1 of your "
                    r"Pok.mon\.$", nxt):
            return (2, Frag("", rider=[head_op,
                                       {"op": "xIfHeadsCountBelow", "n": 2, "skip": 1},
                                       {"op": "xHealChoose", "all": True}]))
        # Tri Kinesis: all heads -> KO 1 opponent Pokémon (choose)
        m = re.match(r"^If all of them are heads, Knock Out 1 of your opponent.s "
                     r"Pok.mon\.$", nxt)
        if m and m0:
            return (2, Frag("", rider=[head_op,
                                       {"op": "xIfHeadsCountBelow",
                                        "n": int(m0.group(1)), "skip": 1},
                                       {"op": "xKnockOutChoose", "scope": "any"}]))
        # per-heads riders: opp-energy discard (pinned-silent cn469/cn1037), opp mill
        # (cn1271), discard-pile picks / deck searches with heads-count caps
        if re.match(r"^For each heads, discard an Energy from your opponent.s Active "
                    r"Pok.mon\.$", nxt):
            return (2, Frag("", rider=[head_op, {"op": "trashEnergyEnemy",
                                                 "activeOnly": True,
                                                 "perHeads": True}]))
        if re.match(r"^For each heads, discard the top card of your opponent.s "
                    r"deck\.$", nxt):
            return (2, Frag("", rider=[head_op, {"op": "xMill", "who": "opp",
                                                 "nVar": "heads_count"}]))
        m = re.match(r"^Put a number of cards up to the number of heads from your "
                     r"discard pile into your hand\.$", nxt)
        if m:
            return (2, Frag("", rider=[head_op,
                                       {"op": "effectTrashToHand", "min": 0,
                                        "maxVar": "heads_count", "filter": {}}]))
        m = re.match(r"^Attach an amount of Basic Energy up to the number of heads "
                     r"from your discard pile to your Benched Pok.mon in any way you "
                     r"like\.$", nxt)
        if m:
            return (2, Frag("", rider=[head_op,
                                       {"op": "xDiscardEnergyAttachBench",
                                        "maxVar": "heads_count",
                                        "filter": {"basicEnergy": True}}]))
        m = re.match(r"^Search your deck for a number of cards up to the number of "
                     r"heads and put them into your hand\.$", nxt)
        if m and shuffle_next:
            return (3, Frag("", rider=[head_op,
                                       {"op": "effectDeckToHandAndShuffle", "min": 0,
                                        "maxVar": "heads_count", "filter": {},
                                        "reveal": False}]))
        m = re.match(r"^For each heads, search your deck for up to (\d+) Basic Energy "
                     r"cards and attach them to your Pok.mon in any way you like\.$",
                     nxt)
        if m and shuffle_next:
            # menu-gated on a nonempty deck (pinned trc_9001 f223: only the sibling
            # attack offered at deckCount 0)
            return (3, Frag("", rider=[head_op,
                                       {"op": "xDeckEnergyAttachDistribute",
                                        "buckets": [{"filter": {"basicEnergy": True},
                                                     "maxPerHeads": int(m.group(1))}],
                                        "mode": "anyWay"}],
                            legal=[{"op": "deckNotEmpty"}]))
        m = re.match(r"^Search your deck for an amount of Basic Energy up to the "
                     r"number of heads and attach it to this Pok.mon\.$", nxt)
        if m and shuffle_next:
            return (3, Frag("", rider=[head_op,
                                       {"op": "xDeckEnergyAttach",
                                        "maxVar": "heads_count", "target": "self",
                                        "filter": {"basicEnergy": True}}]))
    # Ruffians Attack: flip per own {X} mon, damage per heads (pre)
    m = _s(r"Flip a coin for each \{(\w)\} Pok.mon you have in play\.")(sents, i)
    if m and m.group(1) in _TYPE_LETTER and i + 1 < len(sents):
        t = re.match(r"^This attack does (\d+) damage for each heads\.$", sents[i + 1])
        if t:
            return (2, Frag("", pre=[{"op": "xCoinsCount", "var": "atk_in_play_type",
                                      "energyType": _TYPE_LETTER[m.group(1)]},
                                     {"op": "xDamagePerHeads",
                                      "per": int(t.group(1))}]))
    # Bench Manipulation: the OPPONENT flips per their benched mon; damage per tails
    # (pinned cn607_9000: COIN playerIndex = victim, zero-tails logs HP 0)
    if (_s(r"Your opponent flips a coin for each of their Benched Pok.mon\.")(sents, i)
            and i + 1 < len(sents)):
        t = re.match(r"^This attack does (\d+) damage to your opponent.s Active "
                     r"Pok.mon for each tails\.$", sents[i + 1])
        if t:
            return (2, Frag("", pre=[{"op": "xCoinsCount", "var": "def_bench",
                                      "owner": "opp"},
                                     {"op": "xDamagePerTails",
                                      "per": int(t.group(1))}]))
    # Nullifying Zero: per-opponent-mon flips, 150 to each mon on heads (pinned
    # cn1526_9000: attacker owns the flips; misses log nothing)
    if (_s(r"For each of your opponent.s Pok.mon, flip a coin\.")(sents, i)
            and i + 1 < len(sents)):
        t = re.match(r"^If heads, this attack does (\d+) damage to that Pok.mon\.$",
                     sents[i + 1])
        if t:
            return (2, Frag("", rider=[{"op": "xCoinDamageEachOpp",
                                        "damage": int(t.group(1))}]))
    return None


@ATK.rule("R-E01")
def _opp_reveals_hand(sents, i):
    """Reveal-hand family (pinned rvl73/297/786/284/800): plain reveal /
    discard-all-Items+Tools rider / per-Trainer|Energy damage scalers."""
    if not _s(r"Your opponent reveals their hand\.")(sents, i):
        return None
    # The plain and discard-all scripts are menu-gated on a nonempty opponent hand
    # (pinned rvl297_9000 f50 / rvlitems284_9102 f68: only the sibling attack offered
    # at oppHand 0); the choose script is NOT (rvl995_9001 f53 offers 995 at 0).
    gate = [{"op": "oppHandAbove", "n": 0}]
    if i + 1 < len(sents):
        if _s(r"Discard all Item cards and Pok.mon Tool cards you find "
              r"there\.")(sents, i + 1):
            return (2, Frag("", rider=[{"op": "xOppHandReveal",
                                        "discardFilter": {"cardType": [
                                            int(CardType.ITEM), int(CardType.TOOL)]}}],
                            legal=gate))
        m = _s(r"This attack does (\d+) damage for each (Trainer|Energy) card you "
               r"find there\.")(sents, i + 1)
        if m:
            flt = ({"cardType": [int(CardType.ITEM), int(CardType.TOOL),
                                 int(CardType.SUPPORTER), int(CardType.STADIUM)]}
                   if m.group(2) == "Trainer" else
                   {"cardType": [int(CardType.BASIC_ENERGY),
                                 int(CardType.SPECIAL_ENERGY)]})
            return (2, Frag("", pre=[{"op": "xOppHandReveal", "countFilter": flt},
                                     {"op": "xDamagePerRevealed",
                                      "per": int(m.group(1))}]))
    return (1, Frag("", rider=[{"op": "xOppHandReveal"}], legal=gate))


@ATK.rule("R-E02")
def _opp_reveals_hand_choose(sents, i):
    """Comma-joined reveal prints: attacker picks one revealed card (discard /
    deck-bottom — pinned rvl995/rvl401) or a per-Energy scaler (Energy Straw)."""
    if _s(r"Your opponent reveals their hand, and you discard a card you find "
          r"there\.")(sents, i):
        return (1, Frag("", rider=[{"op": "xOppHandRevealChoose", "to": "discard"}]))
    if _s(r"Your opponent reveals their hand, and you choose a card you find there "
          r"and put it on the bottom of their deck\.")(sents, i):
        return (1, Frag("", rider=[{"op": "xOppHandRevealChoose",
                                    "to": "deckBottom"}]))
    m = _s(r"Your opponent reveals their hand, and this attack does (\d+) damage "
           r"for each Energy card you find there\.")(sents, i)
    if m:
        return (1, Frag("", pre=[{"op": "xOppHandReveal",
                                  "countFilter": {"cardType": [
                                      int(CardType.BASIC_ENERGY),
                                      int(CardType.SPECIAL_ENERGY)]}},
                                 {"op": "xDamagePerRevealed",
                                  "per": int(m.group(1))}]))
    return None


_DISC_SCALE_HEAD = re.compile(
    r"^(?:You may )?[Dd]iscard (all|any amount of|any number of|up to (\d+)) "
    r"(Basic )?(?:\{(\w)\} )?(Energy(?: cards?)?|Supporter cards that have .Team Rocket. "
    r"in their name) from (this Pok.mon|your Pok.mon|among your Pok.mon|"
    r"your Benched Pok.mon|your hand)(.*)$")
_DISC_SCALE_TAIL = re.compile(
    r"^[Tt]his attack does (\d+) (more )?damage for each card you discarded "
    r"in this way\.$")


@ATK.rule("R-D01")
def _discard_count_scaled(sents, i):
    """Steel-Burst class: discard own energy/hand cards, damage scales per card
    discarded — two-sentence and comma-joined single-sentence prints."""
    m = _DISC_SCALE_HEAD.match(sents[i])
    if not m:
        return None
    amount, upto, basic, letter, what, scope, rest = m.groups()
    rest = rest.strip()
    if rest.startswith(", and "):
        t = _DISC_SCALE_TAIL.match(rest[6:])
        k = 1
    elif rest in ("", ".") and i + 1 < len(sents):
        t = _DISC_SCALE_TAIL.match(sents[i + 1])
        k = 2
    else:
        return None
    if not t:
        return None
    per, more = int(t.group(1)), bool(t.group(2))
    if what.startswith("Supporter"):
        flt: dict = {"cardType": [3], "nameContains": "Team Rocket"}   # SUPPORTER
    elif basic:
        flt = {"basicEnergy": True}
    elif letter:
        if letter not in _TYPE_LETTER:
            return None
        flt = {"energy": True, "energyType": [_TYPE_LETTER[letter]]}
    else:
        flt = {"energy": True}
    if scope == "your hand":
        d_op: dict = {"op": "xDiscardHandCountScaled", "filter": flt}
        if upto:
            d_op["max"] = int(upto)
    else:
        d_op = {"op": "xDiscardEnergyCountScaled", "filter": flt,
                "scope": ("self" if scope.startswith("this") else
                          "bench" if "Benched" in scope else "own")}
        if amount == "all":
            d_op["all"] = True
        elif upto:
            d_op["max"] = int(upto)
    dmg_op = {"op": "xBonusPerDiscarded" if more else "xDamagePerDiscarded", "per": per}
    return (k, Frag("", pre=[d_op, dmg_op]))


@ATK.rule("R-D02")
def _gust_switch_in(sents, i):
    """Pull / Drag Off: the attacker chooses the defender's new Active; optional flat
    damage to the new Active (pinned cnt_dragoff_9980 f8/f9)."""
    if not _s(r"Switch in 1 of your opponent.s Benched Pok.mon to the Active "
              r"Spot\.")(sents, i):
        return None
    op: dict = {"op": "effectSwitchEnemy"}
    k = 1
    if i + 1 < len(sents):
        m = _s(r"This attack does (\d+) damage to the new Active Pok.mon\.")(sents, i + 1)
        if m:
            op["damageNew"] = int(m.group(1))
            k = 2
    return (k, Frag("", rider=[op]))


@ATK.rule("R-D03")
def _discard_stadium_rider(sents, i):
    if _s(r"Then, discard that Stadium\.")(sents, i):
        return (1, Frag("", rider=[{"op": "xDiscardStadium"}]))
    return None


@ATK.rule("R-C10")
def _coins_until_tails_hand_shuffle_in(sents, i):
    """Horrifying Bite: until-tails flips drive per-heads random shuffle-ins (the
    flips are effect-only — printed damage stands, so the coins ride post-damage)."""
    if (_s(r"Flip a coin until you get tails\.")(sents, i)
            and i + 2 < len(sents)
            and _s(r"For each heads, choose a random card from your opponent.s "
                   r"hand\.")(sents, i + 1)
            and _s(r"Your opponent reveals those cards and shuffles them into their "
                   r"deck\.")(sents, i + 2)):
        return (3, Frag("", rider=[{"op": "xCoinsUntilTails"},
                                   {"op": "xOppHandShuffleInRandom",
                                    "perHeads": True}]))
    return None


@ATK.rule("R-B16")
def _may_switch_self(sents, i):
    if _s(r"You may switch this Pok.mon with 1 of your Benched Pok.mon\.")(sents, i):
        return (1, Frag("", rider=[{"op": "xMayAsk",
                                    "requires": [{"op": "benchExists"}],
                                    "program": [{"op": "effectSwitchMe"}]}]))
    return None


@ATK.rule("R-B17")
def _search_hand_rider(sents, i):
    """Deck→hand searches: revealed and unrevealed prints, optional "You may" (a real
    YES_NO ask — pinned sg33_9000 f18), unfiltered counts ("a card" = min 1, pinned
    sg1093_9000 f14; "up to N cards" = min 0) and the benched-count cap (Nab 'n'
    Dash → maxVar, pinned sg1_9000 f34 min 0)."""
    m = _s(r"(You may )?[Ss]earch your deck for (.+?)(, reveal (?:it|them),)? and put "
           r"(?:it|them) into your hand\.")(sents, i)
    if not m:
        return None
    may, spec_s, reveal = m.group(1), m.group(2), bool(m.group(3))
    op: dict = {"op": "effectDeckToHandAndShuffle"}
    legal: list = []
    if spec_s == "a number of cards up to the number of your Benched Pokémon":
        op.update(min=0, maxVar="atk_bench", filter={})
        legal = [{"op": "benchExists"}]   # menu-gated benchless (pinned sg1_9000 f9)
    elif spec_s == "a card":
        op.update(min=1, max=1, filter={})
    elif (m2 := re.match(r"^up to (\d+) cards$", spec_s)):
        op.update(min=0, max=int(m2.group(1)), filter={})
    else:
        spec = parse_search_spec(spec_s)
        if spec is None:
            return None
        op.update(min=0, max=spec[0], filter=spec[1])
    if not reveal:
        op["reveal"] = False
    k = 1
    if i + 1 < len(sents) and _s(r"Then, shuffle your deck\.")(sents, i + 1):
        k = 2
    if may:
        return (k, Frag("", rider=[{"op": "xMayAsk",
                                    "requires": [{"op": "deckNotEmpty"}],
                                    "program": [op]}], legal=legal))
    return (k, Frag("", rider=[op], legal=legal))


@ATK.rule("R-E03")
def _search_bench_rider(sents, i):
    """Deck→bench searches ("put them onto your Bench"): Flock / Geo Gate / Roto Call
    class — ctx TO_BENCH min 0, bench-room clamp inside the op (pinned sg23_9000 f9);
    "You may" wraps the same YES_NO ask as the hand flavor."""
    m = _s(r"(You may )?[Ss]earch your deck for (.+?) and put (?:it|them) onto your "
           r"Bench\.")(sents, i)
    if not m:
        return None
    spec = parse_search_spec(m.group(2))
    if spec is None:
        return None
    n, flt = spec
    if not (flt.get("pokemon") or "name" in flt):
        return None                       # bench puts place Pokémon
    op = {"op": "effectDeckToBenchAndShuffle", "min": 0, "max": n, "filter": flt}
    k = 1
    if i + 1 < len(sents) and _s(r"Then, shuffle your deck\.")(sents, i + 1):
        k = 2
    if m.group(1):
        return (k, Frag("", rider=[{"op": "xMayAsk",
                                    "requires": [{"op": "deckNotEmpty"}],
                                    "program": [op]}]))
    return (k, Frag("", rider=[op]))


@ATK.rule("R-E05")
def _search_energy_attach_distribute(sents, i):
    """The search-and-attach family (ctx ATTACH_TO pick + ATTACH_FROM placement —
    pinned sg965/sg328/sg242/sg208/sg1463). Family-noun targets ("your Future
    Pokémon") stay unmatched: the Future/Ancient tag exists in no extracted table
    (sgc87_9300 f51 proves the native filters by it), so those defer loudly."""
    k = 1
    if i + 1 < len(sents) and _s(r"Then, shuffle your deck\.")(sents, i + 1):
        k = 2
    # Jolting Charge: two typed buckets, any-way placement over all your mons.
    m = _s(r"Search your deck for up to (\d+) Basic \{(\w)\} Energy cards and up to "
           r"(\d+) Basic \{(\w)\} Energy cards and attach them to your Pok.mon in any "
           r"way you like\.")(sents, i)
    if m:
        if m.group(2) not in _TYPE_LETTER or m.group(4) not in _TYPE_LETTER:
            return None
        buckets = [{"filter": {"basicEnergy": True,
                               "energyType": [_TYPE_LETTER[m.group(2)]]},
                    "max": int(m.group(1))},
                   {"filter": {"basicEnergy": True,
                               "energyType": [_TYPE_LETTER[m.group(4)]]},
                    "max": int(m.group(3))}]
        return (k, Frag("", rider=[{"op": "xDeckEnergyAttachDistribute",
                                    "buckets": buckets, "mode": "anyWay"}]))
    # Single bucket: "up to N Basic [{X}] Energy cards [of different types] and
    # attach them to <target>."
    m = _s(r"Search your deck for (an?|up to \d+) (Basic )?(?:\{(\w)\} )?Energy cards?"
           r"( of different types)? and attach (?:it|them) to (.+?)\.")(sents, i)
    if not m:
        return None
    qty, basic, letter, distinct, target = m.groups()
    n = 1 if qty in ("a", "an") else int(qty.split()[-1])
    flt: dict = {}
    if basic:
        flt["basicEnergy"] = True
    else:
        flt["energy"] = True
    if letter:
        if letter not in _TYPE_LETTER:
            return None
        flt["energyType"] = [_TYPE_LETTER[letter]]
    bucket = [{"filter": flt, "max": n}]
    if distinct:
        # distinct-types cap on the pick (pinned sg321_9001 f9: max 1 over 12
        # same-type candidates)
        bucket[0]["distinctTypes"] = True
    op: dict = {"op": "xDeckEnergyAttachDistribute", "buckets": bucket}
    if target == "your Pokémon in any way you like":
        op["mode"] = "anyWay"
    elif target == "your Benched Pokémon in any way you like":
        op.update(mode="anyWay", benchOnly=True)
    elif target == "1 of your Pokémon":
        if letter:
            return None   # typed single-target prints belong to R-B18's pinned
                          # xDeckEnergyAttach shape (contextCard = the energy)
        op["mode"] = "oneTarget"          # Burning Charge (pinned sg328: listing kept)
    elif target == "1 of your Benched Pokémon":
        op.update(mode="oneTarget", benchOnly=True, targetListing=False)
        # menu-gated benchless (pinned sg242_9000 f7: END offered, no ATTACK)
        return (k, Frag("", rider=[op], legal=[{"op": "benchExists"}]))
    elif target == "your Tera Pokémon in any way you like":
        # Prism Charge: no Tera in play → the picked cards stay in the deck
        # (pinned sg321_9001 f9-f10).
        op.update(mode="anyWay", targets={"pokemon": True, "tera": True})
    elif (fm := re.match(r"^your (Future|Ancient) Pok.mon in any way you like$",
                         target)):
        # Family targets come from the official CSV Category column (the native
        # filters by family — pinned sgc87_9300 f51: fodder excluded, Miraidons kept).
        ids = _csv_categories().get(fm.group(1), [])
        if not ids:
            return None
        op.update(mode="anyWay", targets={"cardIdIn": ids})
    else:
        tm = re.match(r"^1 of your Benched \{(\w)\} Pok.mon$", target)
        if not tm or tm.group(1) not in _TYPE_LETTER:
            return None                     # family-noun / unknown targets defer
        # Send Flowers: benched-{X} targets; an empty bench still poses the pick and
        # the picked card stays in the deck (pinned sg1463_9000 f9-f10).
        op.update(mode="anyWay", benchOnly=True,
                  targets={"pokemon": True, "energyType": [_TYPE_LETTER[tm.group(1)]]})
    return (k, Frag("", rider=[op]))


@ATK.rule("R-E06")
def _per_bench_loops(sents, i):
    """"For each of your Benched Pokémon, search your deck for …" loops (pinned
    sg1078_9000 f37 attach / sg740_9000 f48-f49 evolve)."""
    k = 1
    if i + 1 < len(sents) and _s(r"Then, shuffle your deck\.")(sents, i + 1):
        k = 2
    gate = [{"op": "benchExists"}]   # menu-gated benchless (pinned sg1078_9000 f10)
    m = _s(r"For each of your Benched Pok.mon, search your deck for a Basic \{(\w)\} "
           r"Energy card and attach it to that Pok.mon\.")(sents, i)
    if m and m.group(1) in _TYPE_LETTER:
        return (k, Frag("", rider=[{"op": "xDeckAttachPerBench",
                                    "filter": {"basicEnergy": True,
                                               "energyType": [_TYPE_LETTER[m.group(1)]]}}],
                        legal=gate))
    if _s(r"For each of your Benched Pok.mon, search your deck for a card that evolves "
          r"from that Pok.mon and put it onto that Pok.mon to evolve it\.")(sents, i):
        return (k, Frag("", rider=[{"op": "xDeckEvolvePerBench"}], legal=gate))
    return None


@ATK.rule("R-E07")
def _evolve_choose_from_deck(sents, i):
    if not _s(r"Search your deck for a card that evolves from 1 of your Pok.mon and "
              r"put it onto that Pok.mon to evolve it\.")(sents, i):
        return None
    k = 1
    if i + 1 < len(sents) and _s(r"Then, shuffle your deck\.")(sents, i + 1):
        k = 2
    return (k, Frag("", rider=[{"op": "xDeckEvolveChooseAndShuffle"}]))


@ATK.rule("R-E08")
def _distinct_energy_to_hand(sents, i):
    m = _s(r"Search your deck for up to (\d+) Basic Energy cards of different types, "
           r"reveal them, and put them into your hand\.")(sents, i)
    if not m:
        return None
    k = 1
    if i + 1 < len(sents) and _s(r"Then, shuffle your deck\.")(sents, i + 1):
        k = 2
    return (k, Frag("", rider=[{"op": "xDeckDistinctBasicEnergyToHand",
                                "n": int(m.group(1))}]))


@ATK.rule("R-B18")
def _deck_energy_attach_self(sents, i):
    m = _s(r"Search your deck for (a|up to \d+) Basic \{(\w)\} Energy cards? and attach "
           r"(?:it|them) to (this Pok.mon|1 of your Pok.mon)\.")(sents, i)
    if not m:
        return None
    k = 1
    if i + 1 < len(sents) and _s(r"Then, shuffle your deck\.")(sents, i + 1):
        k = 2
    n = 1 if m.group(1) == "a" else int(m.group(1).split()[-1])
    if m.group(2) not in _TYPE_LETTER:
        return None
    target = "self" if m.group(3).startswith("this") else "choose"
    return (k, Frag("", rider=[{"op": "xDeckEnergyAttach", "max": n, "target": target,
                                "filter": {"basicEnergy": True,
                                           "energyType": [_TYPE_LETTER[m.group(2)]]}}]))


@ATK.rule("R-B27")
def _evolve_self_from_deck(sents, i):
    m = _s(r"Search your deck for a card that evolves from this Pok.mon and put it "
           r"onto this Pok.mon to evolve it\.")(sents, i)
    if not m:
        return None
    k = 1
    if i + 1 < len(sents) and _s(r"Then, shuffle your deck\.")(sents, i + 1):
        k = 2
    return (k, Frag("", rider=[{"op": "xDeckEvolveSelfAndShuffle"}]))


@ATK.rule("R-B26")
def _hand_energy_attach(sents, i):
    m = _s(r"Attach a Basic(?: \{(\w)\})? Energy card from your hand to 1 of your "
           r"Pok.mon\.")(sents, i)
    if not m:
        return None
    flt: dict = {"basicEnergy": True}
    if m.group(1):
        if m.group(1) not in _TYPE_LETTER:
            return None
        flt["energyType"] = [_TYPE_LETTER[m.group(1)]]
    return (1, Frag("", rider=[{"op": "xHandEnergyAttachChoose", "filter": flt}]))


@ATK.rule("R-B19")
def _discard_energy_attach_self(sents, i):
    m = _s(r"Attach (?:up to (\d+) |a )Basic(?: \{(\w)\})? Energy cards? from your discard "
           r"pile to this Pok.mon\.")(sents, i)
    if not m:
        return None
    n = int(m.group(1)) if m.group(1) else 1
    flt: dict = {"basicEnergy": True}
    if m.group(2):
        if m.group(2) not in _TYPE_LETTER:
            return None
        flt["energyType"] = [_TYPE_LETTER[m.group(2)]]
    return (1, Frag("", rider=[{"op": "xDiscardEnergyAttachSelf", "max": n,
                                "filter": flt}]))


@ATK.rule("R-B20")
def _heal_each_rider(sents, i):
    m = _s(r"Heal (\d+) damage from each of your Pok.mon\.")(sents, i)
    if m:
        return (1, Frag("", rider=[{"op": "xHealEach", "amount": int(m.group(1))}]))
    return None


@ATK.rule("R-B21")
def _self_return(sents, i):
    if _s(r"Put this Pok.mon and all attached cards (?:back )?into your hand\.")(sents, i):
        return (1, Frag("", rider=[{"op": "xSelfReturnToHand"}]))
    return None


@ATK.rule("R-B22")
def _bench_spread(sents, i):
    m = _s(r"Put (\d+) damage counters on your opponent.s Benched Pok.mon in any way you "
           r"like\.")(sents, i)
    if m:
        return (1, Frag("", rider=[{"op": "xDistributeCounters",
                                    "counters": int(m.group(1))}]))
    return None


@ATK.rule("R-B23")
def _inflict_two(sents, i):
    m = _s(r"Your opponent.s Active Pok.mon is now (Poisoned|Burned|Asleep|Paralyzed|"
           r"Confused) and (Poisoned|Burned|Asleep|Paralyzed|Confused)\.")(sents, i)
    if m:
        # Condition-ENUM order, not text order: "Asleep and Poisoned" logs POISONED(17)
        # then ASLEEP(19) (pinned micro_onboard780a1128); "Burned and Confused" logs
        # BURNED(18) then CONFUSED(21) (pinned micro_onboard409a573) — ascending in
        # SpecialConditionType/LogType for both.
        conds = sorted(_COND[m.group(g)] for g in (1, 2))
        return (1, Frag("", rider=[{"op": "xInflictConditionActive", "condition": c}
                                   for c in conds]))
    return None


@ATK.rule("R-B24")
def _discard_hand_draw_rider(sents, i):
    m = _s(r"Discard your hand and draw (\d+) cards?\.")(sents, i)
    if m:
        return (1, Frag("", rider=[{"op": "xDiscardHandDraw", "n": int(m.group(1))}]))
    return None


@ATK.rule("R-B25")
def _may_draw_until(sents, i):
    m = _s(r"You may draw cards until you have (\d+) cards in your hand\.")(sents, i)
    if m:
        n = int(m.group(1))
        return (1, Frag("", rider=[{"op": "xMayAsk",
                                    "requires": [{"op": "handBelow", "n": n},
                                                 {"op": "deckNotEmpty"}],
                                    "program": [{"op": "effectDrawUntil", "n": n}]}]))
    return None


@ATK.rule("R-B11")
def _search_bench(sents, i):
    m = _s(r"Search your deck for (up to \d+|an?|1) Basic Pok.mon and put (?:them|it) onto "
           r"your Bench\.")(sents, i)
    if not m:
        return None
    k = 1
    if i + 1 < len(sents) and _s(r"Then, shuffle your deck\.")(sents, i + 1):
        k = 2
    q = m.group(1)
    n = 1 if q in ("a", "an", "1") else int(q.split()[-1])
    return (k, Frag("", rider=[{"op": "effectDeckToBenchAndShuffle", "min": 0, "max": n,
                                "filter": {"pokemon": True, "basic": True}}]))


# ---------------------------------------------------------------------------- trainer rules

TRN = Rules()


@TRN.rule("R-T08")
def _discard_cost(sents, i):
    m = _s(r"You can use this card only if you discard (\d+|another) (?:other )?cards? from "
           r"your hand\.")(sents, i)
    if m:
        n = 1 if m.group(1) == "another" else int(m.group(1))
        return (1, Frag("", legal=[{"op": "handOthers", "n": n}],
                        play=[{"op": "costHandTrash", "n": n}]))
    return None


@TRN.rule("R-T01")
def _search_to_hand(sents, i):
    m = _s(r"Search your deck for (.+?), reveal (?:it|them), and put (?:it|them) into your "
           r"hand\.")(sents, i)
    if not m:
        return None
    spec = parse_search_spec(m.group(1))
    if spec is None:
        return None
    k = 1
    if i + 1 < len(sents) and _s(r"Then, shuffle your deck\.")(sents, i + 1):
        k = 2
    n, flt = spec
    return (k, Frag("", legal=[{"op": "deckNotEmpty"}],
                    play=[{"op": "effectDeckToHandAndShuffle", "min": 0, "max": n,
                           "filter": flt}]))


@TRN.rule("R-T02")
def _search_to_bench(sents, i):
    m = _s(r"Search your deck for (.+?) and put (?:it|them) onto your Bench\.")(sents, i)
    if not m:
        return None
    spec = parse_search_spec(m.group(1))
    if spec is None or not spec[1].get("basic"):
        return None
    k = 1
    if i + 1 < len(sents) and _s(r"Then, shuffle your deck\.")(sents, i + 1):
        k = 2
    n, flt = spec
    return (k, Frag("", legal=[{"op": "benchSpace"}, {"op": "deckNotEmpty"}],
                    play=[{"op": "effectDeckToBenchAndShuffle", "min": 0, "max": n,
                           "filter": flt}]))


@TRN.rule("R-T03")
def _tr_draw(sents, i):
    m = _s(r"Draw (\d+|a) cards?\.")(sents, i)
    if m:
        n = 1 if m.group(1) == "a" else int(m.group(1))
        return (1, Frag("", play=[{"op": "effectDraw", "n": n}]))
    return None


@TRN.rule("R-T04")
def _tr_draw_until(sents, i):
    m = _s(r"Draw cards until you have (\d+) cards in your hand\.")(sents, i)
    if m:
        return (1, Frag("", play=[{"op": "effectDrawUntil", "n": int(m.group(1))}]))
    return None


@TRN.rule("R-T05")
def _tr_switch(sents, i):
    if _s(r"Switch your Active Pok.mon with 1 of your Benched Pok.mon\.")(sents, i):
        return (1, Frag("", legal=[{"op": "benchExists"}], play=[{"op": "effectSwitchMe"}]))
    return None


@TRN.rule("R-T06")
def _tr_gust(sents, i):
    if _s(r"Switch in 1 of your opponent.s Benched Pok.mon to the Active Spot\.")(sents, i):
        return (1, Frag("", legal=[{"op": "oppBenchExists"}],
                        play=[{"op": "effectSwitchEnemy"}]))
    return None


@TRN.rule("R-T07")
def _tr_heal(sents, i):
    m = _s(r"Heal (\d+) damage from 1 of your Pok.mon\.")(sents, i)
    if m:
        return (1, Frag("", legal=[{"op": "selfDamaged"}],
                        play=[{"op": "xHealChoose", "amount": int(m.group(1))}]))
    return None


@TRN.rule("R-T09")
def _tr_shuffle_draw(sents, i):
    if (i + 1 < len(sents) and _s(r"Each player shuffles their hand into their deck\.")(sents, i)):
        m = _s(r"Then, you draw (\d+) cards?, and your opponent draws (\d+) cards?\.")(sents, i + 1)
        if m:
            return (2, Frag("", play=[{"op": "xBothShuffleHandDraw", "n": int(m.group(1)),
                                       "nOpp": int(m.group(2))}]))
        m = _s(r"Then, each player draws (\d+) cards?\.")(sents, i + 1)
        if m:
            return (2, Frag("", play=[{"op": "xBothShuffleHandDraw", "n": int(m.group(1))}]))
    if (i + 1 < len(sents) and _s(r"Shuffle your hand into your deck\.")(sents, i)):
        m = _s(r"(?:Then, )?[Dd]raw (\d+) cards?\.")(sents, i + 1)
        if m:
            return (2, Frag("", play=[{"op": "xOwnShuffleHandDraw", "n": int(m.group(1))}]))
    return None


@TRN.rule("R-T12")
def _tr_discard_hand_draw(sents, i):
    m = _s(r"Discard your hand and draw (\d+) cards?\.")(sents, i)
    if m:
        return (1, Frag("", play=[{"op": "xDiscardHandDraw", "n": int(m.group(1))}]))
    return None


@TRN.rule("R-T13")
def _tr_heal_each(sents, i):
    m = _s(r"Heal (\d+) damage from each of your Pok.mon\.")(sents, i)
    if m:
        return (1, Frag("", legal=[{"op": "selfDamaged"}],
                        play=[{"op": "xHealEach", "amount": int(m.group(1))}]))
    return None


@TRN.rule("R-T11")
def _tr_look_top(sents, i):
    m = _s(r"Look at the top (\d+) cards of your deck and put (?:up to )?(\d+) of them into "
           r"your hand\.")(sents, i)
    if not m or i + 1 >= len(sents):
        return None
    if _s(r"Shuffle the other cards back into your deck\.")(sents, i + 1):
        optional = "up to" in sents[i]
        return (2, Frag("", legal=[{"op": "deckNotEmpty"}],
                        play=[{"op": "xLookTopMayTakeThenShuffle", "n": int(m.group(1)),
                               "min": 0 if optional else int(m.group(2)),
                               "max": int(m.group(2)), "filter": {}}]))
    return None


@TRN.rule("R-T14")
def _tr_trash_to_hand(sents, i):
    m = _s(r"Put (.+?) from your discard pile into your hand\.")(sents, i)
    if not m:
        return None
    spec = parse_search_spec(m.group(1))
    if spec is None:
        return None
    n, flt = spec
    # Imperative "Put up to N …" is still min 1 (pinned micro_onboard1118 f41:
    # Energy Retrieval poses min=1 max=2); only a "You may …" wording drops to 0.
    return (1, Frag("", legal=[{"op": "discardHas", "filter": flt}],
                    play=[{"op": "effectTrashToHand", "min": 1, "max": n,
                           "filter": flt}]))


@TRN.rule("R-T15")
def _tr_look_reveal_take(sents, i):
    m0 = _s(r"Look at the top (\d+) cards of your deck\.")(sents, i)
    if not m0 or i + 2 >= len(sents):
        return None
    m1 = _s(r"You may reveal (.+?) you find there and put (?:it|them) into your "
            r"hand\.")(sents, i + 1)
    if not m1 or not _s(r"Shuffle the other cards back into your deck\.")(sents, i + 2):
        return None
    spec = parse_search_spec(m1.group(1))
    if spec is None:
        return None
    n_take, flt = spec
    return (3, Frag("", legal=[{"op": "deckNotEmpty"}],
                    play=[{"op": "xLookTopMayTakeThenShuffle", "n": int(m0.group(1)),
                           "min": 0, "max": n_take, "filter": flt}]))


@TRN.rule("R-T16")
def _tr_coin_gust(sents, i):
    if (i + 1 < len(sents) and _s(r"Flip a coin\.")(sents, i)
            and _s(r"If heads, switch in 1 of your opponent.s Benched Pok.mon to the "
                   r"Active Spot\.")(sents, i + 1)):
        return (2, Frag("", legal=[{"op": "oppBenchExists"}],
                        play=[{"op": "coin"}, {"op": "ifHeads", "skip": 1},
                              {"op": "effectSwitchEnemy"}]))
    return None


@TRN.rule("R-T18")
def _tr_search_any_cards(sents, i):
    m = _s(r"Search your deck for (a card|up to (\d+) cards) and put (?:it|them) into "
           r"your hand\.")(sents, i)
    if not m:
        return None
    k = 1
    if i + 1 < len(sents) and _s(r"Then, shuffle your deck\.")(sents, i + 1):
        k = 2
    n = 1 if m.group(1) == "a card" else int(m.group(2))
    return (k, Frag("", legal=[{"op": "deckNotEmpty"}],
                    play=[{"op": "effectDeckToHandAndShuffle", "min": 0, "max": n,
                           "filter": {}}]))


@TRN.rule("R-T20")
def _tr_inflict_two(sents, i):
    m = _s(r"Your opponent.s Active Pok.mon is now (Poisoned|Burned|Asleep|Paralyzed|"
           r"Confused) and (Poisoned|Burned|Asleep|Paralyzed|Confused)\.")(sents, i)
    if m:
        conds = sorted(_COND[m.group(g)] for g in (1, 2))   # enum order (R-B23 pin)
        return (1, Frag("", play=[{"op": "xInflictConditionActive", "condition": c}
                                  for c in conds]))
    return None


@TRN.rule("R-T21")
def _tr_self_mill(sents, i):
    m = _s(r"Discard the top (\d+) cards of your deck\.")(sents, i)
    if m:
        return (1, Frag("", legal=[{"op": "deckNotEmpty"}],
                        play=[{"op": "xMill", "who": "self", "n": int(m.group(1))}]))
    return None


@TRN.rule("R-T22")
def _tr_move_energy(sents, i):
    if _s(r"Move a Basic Energy from 1 of your Pok.mon to another of your "
          r"Pok.mon\.")(sents, i):
        return (1, Frag("", legal=[{"op": "ownBasicEnergyExists"},
                                   {"op": "benchExists"}],
                        play=[{"op": "xMoveEnergyOwn"}]))
    return None


@TRN.rule("R-T23")
def _tr_heal_active(sents, i):
    m = _s(r"Heal (\d+) damage from your Active(?: \{(\w)\})? Pok.mon\.")(sents, i)
    if m:
        legal = [{"op": "activeDamaged"}]
        if m.group(2):
            if m.group(2) not in _TYPE_LETTER:
                return None
            legal.append({"op": "activeIs",
                          "filter": {"energyType": [_TYPE_LETTER[m.group(2)]]}})
        return (1, Frag("", legal=legal,
                        play=[{"op": "xHealActive", "amount": int(m.group(1))}]))
    m = _s(r"Heal (\d+) damage from your Active Pok.mon that has (\d+) or more Energy "
           r"attached\.")(sents, i)
    if m:
        return (1, Frag("", legal=[{"op": "activeDamaged"},
                                   {"op": "activeEnergyMin", "n": int(m.group(2))}],
                        play=[{"op": "xHealActive", "amount": int(m.group(1))}]))
    return None


@TRN.rule("R-T25")
def _tr_discard_opp_special(sents, i):
    if _s(r"Discard a Special Energy from 1 of your opponent.s Pok.mon\.")(sents, i):
        flt = {"cardType": [int(CardType.SPECIAL_ENERGY)]}
        return (1, Frag("", legal=[{"op": "oppEnergyHas", "filter": flt}],
                        play=[{"op": "trashEnergyEnemy", "filter": flt}]))
    return None


@TRN.rule("R-T26")
def _tr_turn_ends(sents, i):
    if _s(r"Your turn ends\.")(sents, i):
        return (1, Frag("", play=[{"op": "xEndTurnAfterPlay"}]))
    return None


# ---------------------------------------------------------------------------- tools / energy

TOOL = Rules()


@TOOL.rule("R-O01")
def _tool_hp(sents, i):
    m = _s(r"The Pok.mon this card is attached to gets \+(\d+) HP\.")(sents, i)
    if m:
        return (1, Frag("", fields={"tool": {"hpBonus": int(m.group(1))}}))
    return None


@TOOL.rule("R-O02")
def _tool_retreat(sents, i):
    m = _s(r"The Retreat Cost of the Pok.mon this card is attached to is ((?:\{\w\})+) "
           r"less\.")(sents, i)
    if m:
        n = len(re.findall(r"\{\w\}", m.group(1)))
        return (1, Frag("", fields={"tool": {"retreatBonus": -n}}))
    return None


ENERGY_PROVIDES = re.compile(
    r"^As long as this card is attached to a Pok.mon, it provides \{(\w)\} Energy\.$")


# ---------------------------------------------------------------------------- assembly

def assemble(frags: list[Frag], *, is_attack: bool) -> dict | None:
    """Compose fragments into one ChainDef entry; None when they conflict."""
    out: dict = {}
    pre: list = []
    rider: list = []
    play: list = []
    legal: list = []
    rules: list[str] = []
    for f in frags:
        if not f.rule:      # noise fragments carry nothing
            continue
        rules.append(f.rule)
        pre += f.pre
        rider += f.rider
        play += f.play
        legal += f.legal
        for k, v in f.fields.items():
            if k in out and out[k] != v:
                return None                       # conflicting fields — never guess
            out[k] = v
    out.pop("_lockName", None)
    if is_attack:
        if play:
            return None
        if legal:
            out["legal"] = legal   # engine menu-gates conditional attacks (options.py)
        if pre:
            out["pre"] = pre
        if rider:
            out["rider"] = rider
    else:
        if pre or rider:
            return None
        if "tool" not in out:
            out["play"] = play
            out["legal"] = legal
    if rules:
        out["_seed"] = {"rules": sorted(set(rules))}
    return out


# ---------------------------------------------------------------------------- seeding

def seed_pool(cards: list[dict], attacks: list[dict], overrides: dict) -> tuple[dict, list]:
    """→ (generated defs keyed like chain_overrides, unparsed queue entries)."""
    gen: dict = {}
    queue: list[dict] = []

    # Sentence templates the engine MENU-GATES (the attack is unoffered until its board
    # condition holds — pinned mill_9200 f33, Terminal Period). Deferred attacks matching
    # one get menuOffer=false; every other deferred attack stays offered (Phantom-Dive
    # class pin) and raises UnsupportedCard on use.
    menu_gated = [re.compile(r"^If your opponent.s Active Pok.mon has exactly \d+ damage "
                             r"counters on it, that Pok.mon is Knocked Out\.$")]

    def defer(key: str, name: str, kind: str, reason: str, unparsed: list[str]):
        entry: dict = {"name": name, "deferred": reason}
        if kind == "attack" and any(g.match(s) for s in unparsed for g in menu_gated):
            entry["menuOffer"] = False
        if unparsed:
            entry["_seed"] = {"unparsed": unparsed[:6]}
        gen[key] = entry
        for s in unparsed:
            queue.append({"kind": kind, "key": key, "name": name, "sentence": s})

    # --- attacks -------------------------------------------------------------------------
    for a in attacks:
        key = f"attack:{a['attackId']}"
        if key in overrides:
            continue                              # hand-authored chain wins; nothing to seed
        name = a.get("name", "")
        text = a.get("text") or ""
        if not text.strip():
            gen[key] = {"name": name, "_seed": {"source": "vanilla"}}
            continue
        frags, unparsed = ATK.consume(text)
        if unparsed:
            defer(key, name, "attack", "unparsed effect text", unparsed)
            continue
        entry = assemble(frags, is_attack=True)
        if entry is None:
            defer(key, name, "attack", "fragments would not compose", sentences(text))
            continue
        # A 0-damage attack whose whole effect needs a resource is MENU-GATED by the
        # engine on that resource (pinned earthquake_9710 f6: Abundant Harvest unoffered
        # with an empty discard; same class as the Terminal-Period gate).
        if not a.get("damage"):
            for op in entry.get("rider") or []:
                if op["op"] == "xDiscardEnergyAttachSelf":
                    entry["legal"] = [{"op": "discardHas", "filter": op.get("filter", {})}]
                elif op["op"] == "xHandEnergyAttachChoose":   # Lucky Attachment class:
                    entry["legal"] = [{"op": "handHas",       # offered only with hand
                                       "filter": op.get("filter", {})}]   # fuel (pinned
                    # micro_happyswitch_9950 f28: offered with energies in hand)
        entry["name"] = name
        gen[key] = entry

    # --- cards ---------------------------------------------------------------------------
    for c in cards:
        key = str(c["cardId"])
        if key in overrides:
            continue
        name = c.get("name", "")
        ct = c["cardType"]
        skills = [s for s in (c.get("skills") or [])]
        text = " ".join(s.get("text", "") for s in skills).strip()

        if ct == int(CardType.POKEMON):
            if not skills:
                gen[key] = {"name": name, "_seed": {"source": "plain-pokemon"}}
            elif len(skills) == 1 and re.match(
                    r"^Prevent all damage done to this Pok.mon by attacks from your "
                    r"opponent.s Pok.mon \{ex\}\.$",
                    " ".join(sentences(skills[0].get("text", "")))):
                # Crustle-template defense passive (R-P01): audit prevent_ex-verified.
                gen[key] = {"name": name, "defense": {"preventDamageFromEx": True},
                            "_seed": {"rules": ["R-P01"]}}
            else:
                defer(key, name, "ability",
                      f"ability unpinned: {skills[0].get('name', '?')}", [])
            continue

        if ct == int(CardType.BASIC_ENERGY):
            gen[key] = {"name": name, "_seed": {"source": "basic-energy"}}
            continue

        if ct == int(CardType.SPECIAL_ENERGY):
            sents = sentences(text)
            if len(sents) == 1:
                m = ENERGY_PROVIDES.match(sents[0])
                if m and m.group(1) in _TYPE_LETTER:
                    gen[key] = {"name": name, "provides": [_TYPE_LETTER[m.group(1)]],
                                "_seed": {"rules": ["R-E01"]}}
                    continue
            defer(key, name, "special-energy", "special energy unpinned", sents)
            continue

        if ct == int(CardType.TOOL):
            frags, unparsed = TOOL.consume(text)
            entry = assemble(frags, is_attack=False) if not unparsed else None
            if entry and "tool" in entry:
                entry["name"] = name
                gen[key] = entry
            else:
                defer(key, name, "tool", "tool passive unpinned", unparsed or sentences(text))
            continue

        if ct == int(CardType.STADIUM):
            defer(key, name, "stadium", "stadium passive unpinned", sentences(text))
            continue

        # ITEM / SUPPORTER
        frags, unparsed = TRN.consume(text)
        if unparsed:
            defer(key, name, "trainer", "unparsed effect text", unparsed)
            continue
        entry = assemble(frags, is_attack=False)
        if entry is None or not entry.get("play"):
            defer(key, name, "trainer", "fragments would not compose", sentences(text))
            continue
        entry["name"] = name
        gen[key] = entry

    return gen, queue


# ---------------------------------------------------------------------------- report

def usage_rank() -> dict[str, float]:
    """cardId(str) -> meta play-rate weight; empty when data/meta is absent."""
    try:
        sys.path.insert(0, str(REPO / "tools"))
        from meta_tracker.meta_usage import usage_table  # type: ignore
        return {str(k): float(v) for k, v in usage_table().items()}
    except Exception:
        return {}


def build_report(queue: list[dict], attacks_by_id: dict, cards: list[dict]) -> dict:
    """Group unparsed sentences by template hash; order groups by count (meta rank folds
    in when available)."""
    # attackId -> carrying cardIds (for play-rate attribution)
    owners: dict[str, list[int]] = {}
    for c in cards:
        for aid in (c.get("attacks") or []):
            owners.setdefault(str(aid), []).append(c["cardId"])
    rank = usage_rank()
    groups: dict[str, dict] = {}
    for q in queue:
        tpl = template(q["sentence"])
        h = hashlib.sha1(tpl.encode("utf-8")).hexdigest()[:10]
        g = groups.setdefault(h, {"template": tpl, "count": 0, "playRate": 0.0,
                                  "examples": []})
        g["count"] += 1
        cids = ([int(q["key"])] if q["kind"] != "attack" else
                owners.get(q["key"].split(":")[1], []))
        g["playRate"] += max((rank.get(str(cid), 0.0) for cid in cids), default=0.0)
        if len(g["examples"]) < 8:
            g["examples"].append({k: q[k] for k in ("kind", "key", "name", "sentence")})
    ordered = dict(sorted(groups.items(),
                          key=lambda kv: (-kv[1]["playRate"], -kv[1]["count"])))
    return {"_meta": {"tool": "seed_chains.py",
                      "note": "the hand-authoring queue: each group is one sentence "
                              "template no rule consumes (M4 item 1c)"},
            "groups": ordered}


# ---------------------------------------------------------------------------- main

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Seed pool-wide ChainDefs (ADR-0050 M4).")
    ap.add_argument("--stats", action="store_true", help="print rollup only, write nothing")
    args = ap.parse_args(argv)

    cards = json.loads((DEFS / "card_data.json").read_text(encoding="utf-8"))
    attacks = json.loads((DEFS / "attack_data.json").read_text(encoding="utf-8"))
    overrides = json.loads((DEFS / "chain_overrides.json").read_text(encoding="utf-8"))

    gen, queue = seed_pool(cards, attacks, overrides)

    n_att = sum(1 for k in gen if k.startswith("attack:"))
    att_def = sum(1 for k, v in gen.items() if k.startswith("attack:") and "deferred" in v)
    n_card = sum(1 for k in gen if not k.startswith("attack:") and not k.startswith("_"))
    card_def = sum(1 for k, v in gen.items()
                   if not k.startswith("attack:") and not k.startswith("_")
                   and "deferred" in v)
    print(f"attacks: {n_att} generated ({n_att - att_def} live, {att_def} deferred) "
          f"+ {sum(1 for k in overrides if k.startswith('attack:'))} overridden")
    print(f"cards:   {n_card} generated ({n_card - card_def} live, {card_def} deferred) "
          f"+ {sum(1 for k in overrides if not k.startswith('attack:') and k != '_comment')} "
          f"overridden")
    print(f"unparsed sentences queued: {len(queue)}")
    if args.stats:
        by_kind = Counter(q["kind"] for q in queue)
        print(f"queue by kind: {dict(by_kind)}")
        return 0

    body = {"_meta": {"tool": "tools/parity/seed_chains.py",
                      "note": "machine-seeded layer; chain_overrides.json wins per key; "
                              "regenerate wholesale, never hand-edit"}}
    body.update({k: gen[k] for k in sorted(gen, key=lambda x: (x.startswith("attack:"),
                                                               x.split(":")[-1].zfill(6)))})
    OUT.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")

    report = build_report(queue, {str(a['attackId']): a for a in attacks}, cards)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8")
    print(f"wrote {REPORT} ({len(report['groups'])} template groups)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
