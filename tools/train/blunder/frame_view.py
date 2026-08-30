"""Render ONE frame's complete board state as plain text — one ``<episode>-<frame>`` key in, one
fixed-order dump out.

Two snapshot shapes normalize into one output: the full-information **film** (both decks, hands and
prize piles; enums as strings) and the per-seat agent **Observation** (opponent hand ``None``, no
deck, enums as ints). Film-only zones are labelled `[hid]` — never read one as agent knowledge.

The turn flags (``energyAttached`` / ``supporterPlayed`` / ``retreated`` / ``stadiumPlayed``) belong
to the TURN PLAYER, not the asked seat; a seat is regularly prompted out of turn (post-KO promote).

Card enrichment comes from `cgpy.cards.CardDB` and is FAIL-OPEN — no tables still yields every zone.
Attack affordability is deliberately NOT computed: that is an inference, not board state.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

from meta_tracker.parse import load_replay

from .store import jsonl_files          # the store owns where the correction logs live
from ..saved_moment import (
    DEFAULT_CORRECTIONS,
    DEFAULT_FIXTURES,
    DEFAULT_REPLAYS,
    FrameHit,
    _corrections_in,
    _note_keys,
    find_frame,
    parse_frame_key,
)

REPO = Path(__file__).resolve().parents[3]

# --- engine enums (src/cg/api.py) ------------------------------------------------------------
# The film spells these as strings and the obs as ints, so every lookup takes either.

_AREA = {1: "DECK", 2: "HAND", 3: "DISCARD", 4: "ACTIVE", 5: "BENCH", 6: "PRIZE",
         7: "STADIUM", 8: "ENERGY", 9: "TOOL", 10: "PRE_EVOLUTION", 11: "PLAYER", 12: "LOOKING"}

_CARD_TYPE = {0: "Pokemon", 1: "Item", 2: "Tool", 3: "Supporter", 4: "Stadium",
              5: "Basic Energy", 6: "Special Energy"}

# Verified against the Basic Energy card names in src/cgpy/defs/card_data.json. DRAGON/RAINBOW/
# TEAM_ROCKET have no Basic card to confirm a symbol, so they are named rather than invented.
_ENERGY = {0: "{C}", 1: "{G}", 2: "{R}", 3: "{W}", 4: "{L}", 5: "{P}", 6: "{F}", 7: "{D}",
           8: "{M}", 9: "Dragon", 10: "Rainbow(any)", 11: "TeamRocket(P+D)"}

_OPTION_TYPE = {0: "Number", 1: "Yes", 2: "No", 3: "Card", 4: "ToolCard", 5: "EnergyCard",
                6: "Energy", 7: "Play", 8: "Attach", 9: "Evolve", 10: "Ability", 11: "Discard",
                12: "Retreat", 13: "Attack", 14: "End", 15: "Skill", 16: "SpecialCondition"}

_SELECT_TYPE = {0: "Main", 1: "Card", 2: "AttachedCard", 3: "CardOrAttachedCard", 4: "Energy",
                5: "Skill", 6: "Attack", 7: "Evolve", 8: "Count", 9: "YesNo",
                10: "SpecialCondition"}

_CONTEXT = {
    0: ("Main", "the main turn menu"),
    1: ("SetupActivePokemon", "pick the Pokémon for your Active Spot during Set Up"),
    2: ("SetupBenchPokemon", "pick a Pokémon for your Bench during Set Up"),
    3: ("Switch", "pick the Pokémon to swap with your Active"),
    4: ("ToActive", "pick the Pokémon to put into your Active Spot"),
    5: ("ToBench", "pick the Pokémon to put onto your Bench"),
    6: ("ToField", "pick the Pokémon to put into play"),
    7: ("ToHand", "pick the card to add to your hand (a search)"),
    8: ("Discard", "pick the card to discard"),
    9: ("ToDeck", "pick the card to return to your deck"),
    10: ("ToDeckBottom", "pick the card to put on the bottom of your deck"),
    11: ("ToPrize", "pick the card to add to your prizes"),
    12: ("NotMove", "pick the card that stays where it is"),
    13: ("DamageCounter", "pick the Pokémon to place damage counters on"),
    14: ("DamageCounterAny", "pick the Pokémon to place damage counters on, as you like"),
    15: ("Damage", "pick the Pokémon to deal damage to (a snipe target)"),
    16: ("RemoveDamageCounter", "pick the Pokémon to remove damage counters from"),
    17: ("Heal", "pick the Pokémon to heal"),
    18: ("EvolvesFrom", "pick the Pokémon to evolve FROM"),
    19: ("EvolvesTo", "pick the Pokémon to evolve INTO"),
    20: ("Devolve", "pick the Pokémon to devolve"),
    21: ("AttachFrom", "pick the Pokémon to attach the card to"),
    22: ("AttachTo", "pick the card to attach to the Pokémon"),
    23: ("DetachFrom", "pick the Pokémon to remove the card from"),
    24: ("Look", "pick the card to look at"),
    25: ("EffectTarget", "pick the card to apply the effect to"),
    26: ("DiscardEnergyCard", "pick the Energy card to discard"),
    27: ("DiscardToolCard", "pick the Pokémon Tool to discard"),
    28: ("SwitchEnergyCard", "pick the Energy card to replace"),
    29: ("DiscardCardOrAttachedCard", "pick the card to discard"),
    30: ("DiscardEnergy", "pick the Energy to discard"),
    31: ("ToHandEnergy", "pick the Energy to return to your hand"),
    32: ("ToDeckEnergy", "pick the Energy to return to your deck"),
    33: ("SwitchEnergy", "pick the Energy to switch"),
    34: ("SkillOrder", "pick the order the effects activate in"),
    35: ("Attack", "pick the Attack to use"),
    36: ("DisableAttack", "pick the Attack to disable"),
    37: ("Evolve", "pick the evolution source and target"),
    38: ("DrawCount", "pick how many cards to draw"),
    39: ("DamageCounterCount", "pick how many damage counters to place"),
    40: ("RemoveDamageCounterCount", "pick how many damage counters to remove"),
    41: ("IsFirst", "would you like to go first?"),
    42: ("Mulligan", "would you like to redraw?"),
    43: ("Activate", "would you like to activate the effect?"),
    44: ("FirstEffect", "would you like to pick the first effect?"),
    45: ("MoreDevolve", "devolve it further?"),
    46: ("CoinHead", "call heads?"),
    47: ("AffectSpecialCondition", "pick the Special Condition to affect"),
    48: ("RecoverSpecialCondition", "pick the Special Condition to recover from"),
}

_CONDITIONS = ("asleep", "burned", "confused", "paralyzed", "poisoned")


def _enum_name(value, table: dict, prefix: str = "") -> str:
    """``value`` as a readable name, whether the source spelled it as an int or a string."""
    if value is None:
        return "?"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, int):
        return table.get(value, f"{prefix}{value}")
    return str(value)


def _context_name(value) -> tuple[str, str]:
    """``(name, plain-English meaning)`` for a SelectContext given as an int or a string."""
    if isinstance(value, int) and not isinstance(value, bool):
        return _CONTEXT.get(value, (f"context{value}", ""))
    name = str(value) if value is not None else "?"
    for n, meaning in _CONTEXT.values():
        if n.lower() == name.lower():
            return name, meaning
    return name, ""


def turn_player(turn, first_player) -> int | None:
    """The seat whose turn ``turn`` (1-based) is — ``firstPlayer`` takes the odd turns. ``None`` for
    turn 0 (the shared setup phase) or a missing input."""
    if turn is None or first_player is None:
        return None
    try:
        turn, first_player = int(turn), int(first_player)
    except (TypeError, ValueError):
        return None
    if turn < 1 or first_player < 0:
        return None
    return (first_player + turn - 1) % 2


# --- card enrichment (fail-open) --------------------------------------------------------------

class _Cards:
    """`cgpy.cards.CardDB` if the committed tables load, else a null object. Enrichment is never
    used to *infer* board state."""

    def __init__(self):
        self.db = None
        self.error = None
        try:                                              # src/ is not always on sys.path
            import sys
            src = str(REPO / "src")
            if src not in sys.path:
                sys.path.insert(0, src)
            from cgpy.cards import CardDB
            self.db = CardDB.load()
        except Exception as exc:                          # noqa: BLE001 - enrichment is optional
            self.error = f"{type(exc).__name__}: {exc}"

    @property
    def present(self) -> bool:
        return self.db is not None

    def card(self, card_id):
        if self.db is None or card_id is None:
            return None
        return self.db.cards.get(int(card_id))

    def attack(self, attack_id):
        if self.db is None or attack_id is None:
            return None
        return self.db.attacks.get(int(attack_id))


UNKNOWN_CARD = "(face down — identity not in this snapshot)"


def _card_name(card: dict | None, cards: _Cards) -> str:
    """A card's name — the film's own ``name``, else resolved from ``id``. A non-dict entry is a
    KNOWN unknown (an Observation spells an unseeable card as bare ``null``), not corrupt data."""
    if not isinstance(card, dict):
        return UNKNOWN_CARD
    name = card.get("name")
    if name:
        return str(name)
    stat = cards.card(card.get("id"))
    if stat is not None and getattr(stat, "name", None):
        return str(stat.name)
    return f"card#{card.get('id', '?')}"


def _category(card: dict | None, cards: _Cards) -> str:
    if not isinstance(card, dict):
        return "?"
    stat = cards.card(card.get("id"))
    if stat is None:
        return "?"
    return _CARD_TYPE.get(int(getattr(stat, "cardType", -1)), "?")


def _all_unknown(cards_list) -> bool:
    """True when a zone is present but every entry is face-down (an Observation's prize pile)."""
    return bool(cards_list) and all(not isinstance(c, dict) for c in cards_list)


def _energy_symbols(energies) -> str:
    """An energy multiset as ``{W}{W}{C}`` — the *provided* types, so Special Energy counts as
    whatever it provides."""
    if not energies:
        return "none"
    return "".join(_ENERGY.get(int(e), f"<{e}>") for e in energies)


def _prize_value(stat) -> tuple[int, str]:
    """Prizes a KO awards, per docs/rulebook.txt §6 (Mega ex 3, ex 2, otherwise 1)."""
    if stat is None:
        return 1, "1 prize (assumed — card table off)"
    if getattr(stat, "megaEx", False):
        return 3, "3 prizes (Mega ex)"
    if getattr(stat, "ex", False):
        return 2, "2 prizes (ex)"
    return 1, "1 prize"


def _stage(stat) -> str:
    if stat is None:
        return ""
    if getattr(stat, "stage2", False):
        return "Stage 2"
    if getattr(stat, "stage1", False):
        return "Stage 1"
    if getattr(stat, "basic", False):
        return "Basic"
    return ""


# --- rendering ---------------------------------------------------------------------------------
# Every line wraps to `WIDTH`, zone lists group by category.

WIDTH = 120
"""Default column width (owner's 2026-08-20 call); pass ``width=38`` for a phone-sized column."""

LABELS = (
    "[pub] both players can see it",
    "[you] the asked seat's own hand",
    "[hid] the asked seat could NOT see it. Listed only because the film is full-information — "
    "never read it as something the agent knew.",
    "a deck's multiset is derivable by deck-tracking; its ORDER is not — treat the recorded order "
    "as engine-internal.",
)

LABELS_OBS = (
    "[pub] both players can see it",
    "[you] the asked seat's own hand",
    "this snapshot is the agent's own Observation, so nothing hidden from it appears at all — a "
    "zone it could not see is absent or face-down.",
)

_CAT_SHORT = {"Pokemon": "Pkmn", "Item": "Item", "Tool": "Tool", "Supporter": "Supp",
              "Stadium": "Stadium", "Basic Energy": "Basic E", "Special Energy": "Spec E"}

_CAT_ORDER = ["Pokemon", "Basic Energy", "Special Energy", "Item", "Tool", "Supporter",
              "Stadium", "?"]


class _Out:
    """A width-bounded line accumulator."""

    def __init__(self, width: int = WIDTH):
        self.width = max(20, int(width))
        self.lines: list[str] = []

    def raw(self, text: str = "") -> None:
        self.lines.append(text)

    def rule(self, label: str = "") -> None:
        if not label:
            self.raw("-" * self.width)
            return
        head = f"-- {label} "
        if len(head) + 2 > self.width:
            self.add(f"-- {label}")
            return
        self.raw(head + "-" * (self.width - len(head)))

    def add(self, text, *, indent: int = 0, hang: int = 1, hard: bool = False) -> None:
        pad = " " * indent
        wrapped = textwrap.wrap(
            str(text), width=self.width, initial_indent=pad,
            subsequent_indent=" " * (indent + hang),
            break_long_words=hard, break_on_hyphens=False)
        self.lines.extend(wrapped or [pad + str(text)])

    def path(self, text: str, *, indent: int = 0) -> None:
        segments = [s + "/" for s in text.split("/")[:-1]] + [text.split("/")[-1]]
        pad, room = " " * indent, max(4, self.width - indent)
        line = ""
        for segment in segments:
            if len(segment) > room:
                if line:
                    self.raw(pad + line)
                    line = ""
                for chunk in textwrap.wrap(segment, width=room, break_long_words=True,
                                           break_on_hyphens=False):
                    self.raw(pad + chunk)
                continue
            if line and len(line) + len(segment) > room:
                self.raw(pad + line)
                line = segment
            else:
                line += segment
        if line:
            self.raw(pad + line)

    def text(self) -> str:
        return "\n".join(self.lines).rstrip() + "\n"


def _rel(path) -> str:
    if path is None:
        return ""
    try:
        return Path(path).resolve().relative_to(REPO).as_posix()
    except (ValueError, OSError):
        return str(path)


def _count_names(cards_list, cards: _Cards) -> list[str]:
    counts: dict[str, int] = {}
    for card in cards_list or ():
        name = _card_name(card, cards)
        counts[name] = counts.get(name, 0) + 1
    return [f"{n} x{k}" if k > 1 else n
            for n, k in sorted(counts.items(), key=lambda kv: kv[0].lower())]


def _zone(out: _Out, cards_list, cards: _Cards, *, indent: int = 0) -> None:
    if not cards_list:
        out.add("(empty)", indent=indent)
        return
    groups: dict[str, dict[str, int]] = {}
    unknown = 0
    for card in cards_list:
        if not isinstance(card, dict):
            unknown += 1
            continue
        cat = _category(card, cards)
        name = _card_name(card, cards)
        groups.setdefault(cat, {})
        groups[cat][name] = groups[cat].get(name, 0) + 1
    for cat in sorted(groups, key=lambda c: (_CAT_ORDER.index(c) if c in _CAT_ORDER else 99, c)):
        names = [f"{n} x{k}" if k > 1 else n
                 for n, k in sorted(groups[cat].items(), key=lambda kv: kv[0].lower())]
        out.add(f"{_CAT_SHORT.get(cat, cat)}: " + ", ".join(names), indent=indent, hang=1)
    if unknown:
        out.add(f"{unknown} card(s) face down", indent=indent)


def _pokemon(out: _Out, pk: dict | None, cards: _Cards, *, head: str, indent: int,
             detail: int, effects: bool = True) -> None:
    """One Pokémon in play: a head line, then its facts one short line at a time."""
    if not isinstance(pk, dict):
        # A face-down Active during Set Up (the Cinderace "Explosiveness" opener) reaches an
        # Observation as a bare null.
        out.add(f"{head} {UNKNOWN_CARD}", indent=indent)
        return
    stat = cards.card(pk.get("id"))
    out.add(f"{head} {_card_name(pk, cards)}", indent=indent)

    hp, max_hp = pk.get("hp"), pk.get("maxHp")
    if isinstance(hp, int) and isinstance(max_hp, int):
        damage = max_hp - hp
        out.add(f"{hp}/{max_hp} HP · " + (f"{damage} dmg taken" if damage else "undamaged"),
                indent=detail)
        printed = getattr(stat, "hp", None) if stat is not None else None
        if isinstance(printed, int) and printed and printed != max_hp:
            out.add(f"max {max_hp} vs printed {printed} "
                    f"({max_hp - printed:+d} from effects in play)", indent=detail)

    if stat is not None:
        head_bits = [b for b in (_stage(stat),) if b]
        etype = getattr(stat, "energyType", None)
        if etype is not None:
            head_bits.append(_ENERGY.get(int(etype), str(etype)))
        if head_bits:
            out.add(" · ".join(head_bits), indent=detail)

        weak = getattr(stat, "weakness", None)
        line = (f"weak {_ENERGY.get(int(weak), weak)} x2" if weak is not None else "no weakness")
        resist = getattr(stat, "resistance", None)
        if resist is not None:
            line += f" · resist {_ENERGY.get(int(resist), resist)}"
        retreat = getattr(stat, "retreatCost", None)
        if retreat is not None:
            line += f" · retreat {retreat}"
        out.add(line, indent=detail)
        out.add(f"KO gives {_prize_value(stat)[1]}", indent=detail)

    energies = pk.get("energies") or []
    ecards = pk.get("energyCards") or []
    if energies or ecards:
        out.add(f"energy {len(energies)}: {_energy_symbols(energies)}", indent=detail)
        if ecards:
            out.add(", ".join(_count_names(ecards, cards)), indent=detail + 1)
    else:
        out.add("energy: none", indent=detail)

    tools = pk.get("tools") or []
    out.add("tool: " + (", ".join(_count_names(tools, cards)) if tools else "none"), indent=detail)

    pre = pk.get("preEvolution") or []
    if pre:
        out.add("evolved from: " + ", ".join(_count_names(pre, cards)), indent=detail)

    if stat is not None:
        for attack_id in getattr(stat, "attacks", None) or ():
            atk = cards.attack(attack_id)
            if atk is None:
                out.add(f"atk id {attack_id} (not in card table)", indent=detail)
                continue
            dmg = f"{atk.damage} dmg" if atk.damage else "no dmg"
            out.add(f"atk {atk.name} · {_energy_symbols(atk.energies)} · {dmg}", indent=detail)
            if effects and atk.text:
                out.add(atk.text, indent=detail + 1)
        for name, stext in getattr(stat, "skills", None) or ():
            out.add(f"abil {name.strip()}", indent=detail)
            if effects and stext:
                out.add(stext, indent=detail + 1)

    if pk.get("appearThisTurn"):
        out.add("came into play THIS TURN (cannot evolve this turn)", indent=detail)


def _option_parts(idx: int, opt: dict, cur: dict, cards: _Cards, asked_seat) -> list[str]:
    """One offered option as a head line plus a line per thing it names."""
    otype = _enum_name(opt.get("type"), _OPTION_TYPE, "optionType")
    parts = [f"[{idx}] {otype}"]

    def _slot(player_index, area, index):
        """The Pokémon/card an (area, index) pair points at, named."""
        area_name = _enum_name(area, _AREA)
        if area_name == "STADIUM":
            # The Stadium is shared, so it hangs off the top-level state, not off a player.
            stadium = cur.get("stadium") or []
            if isinstance(index, int) and 0 <= index < len(stadium):
                return f"the STADIUM = {_card_name(stadium[index], cards)}"
            return "the STADIUM"
        players = cur.get("players") or []
        seat = player_index if isinstance(player_index, int) else asked_seat
        if not isinstance(seat, int) or not (0 <= seat < len(players)):
            return None
        zone = {"ACTIVE": "active", "BENCH": "bench", "HAND": "hand", "DISCARD": "discard",
                "DECK": "deck", "PRIZE": "prize", "LOOKING": "looking"}.get(area_name)
        if zone is None:
            # ENERGY / TOOL / PRE_EVOLUTION hang off a Pokémon rather than off a zone list, so
            # there is nothing to index into here — name the area and let the index stand.
            return f"s{seat} {area_name}{index}" if isinstance(index, int) else None
        entries = players[seat].get(zone)
        if not isinstance(entries, list) or not isinstance(index, int):
            return None
        if not (0 <= index < len(entries)):
            return None
        # ACTIVE is a single slot, so its index carries no information worth the characters.
        ref = f"s{seat} {area_name}" + ("" if area_name == "ACTIVE" else str(index))
        return f"{ref} = {_card_name(entries[index], cards)}"

    # A PLAY option carries a bare hand index and no `area` (`cgpy.options`); everything else that
    # points at a card says which area it means.
    area = opt.get("area")
    if area is None and otype == "Play":
        area = 2                                          # AreaType.HAND
    target = _slot(opt.get("playerIndex"), area, opt.get("index"))
    if target:
        parts.append(target)
    elif opt.get("index") is not None:
        parts.append(f"index {opt['index']}")

    if opt.get("inPlayArea") is not None:
        onto = _slot(opt.get("inPlayPlayerIndex", asked_seat), opt.get("inPlayArea"),
                     opt.get("inPlayIndex"))
        parts.append(f"onto {onto}" if onto else
                     f"onto {_enum_name(opt.get('inPlayArea'), _AREA)}"
                     f"{opt.get('inPlayIndex')}")

    if opt.get("attackId") is not None:
        atk = cards.attack(opt["attackId"])
        parts.append(f"{atk.name} · {_energy_symbols(atk.energies)} · {atk.damage} dmg"
                     if atk else f"attackId {opt['attackId']}")

    for extra in ("number", "specialCondition"):
        if opt.get(extra) is not None:
            parts.append(f"{extra} {opt[extra]}")
    return parts


def _option_summary(idx: int, opt: dict, cur: dict, cards: _Cards, asked_seat) -> str:
    """The same option on one line, index dropped — for echoing a choice or a ruling under a line
    that already carries it."""
    parts = _option_parts(idx, opt, cur, cards, asked_seat)
    if len(parts) > 1:
        return " · ".join(parts[1:])
    return parts[0].split("] ", 1)[-1]                    # "[3] Retreat" -> "Retreat"


def _side(out: _Out, seat: int, cur: dict, cards: _Cards, *, asked_seat, label: str,
          deck_order: bool, effects: bool) -> None:
    players = cur.get("players") or []
    out.raw("")
    out.rule(f"SEAT {seat} · {label}")
    if not (0 <= seat < len(players)):
        out.add("not in this snapshot")
        return
    pl = players[seat]
    you = (seat == asked_seat)
    mine = "[you]" if you else "[hid]"

    # prizes first: the clock every plan is measured against
    prize = pl.get("prize")
    if isinstance(prize, list):
        remaining = len(prize)
        out.add(f"PRIZES {remaining} of 6 left · {6 - remaining} taken")
        out.add("count is [pub] · the 6th taken wins", indent=1)
        if _all_unknown(prize):
            out.add("contents: face down, not in this snapshot", indent=1)
        else:
            out.add("contents [hid]:", indent=1)
            _zone(out, prize, cards, indent=2)
    elif isinstance(prize, int):
        out.add(f"PRIZES {prize} of 6 left · {6 - prize} taken")
        out.add("count is [pub] · the 6th taken wins", indent=1)
        out.add("contents: not in this snapshot", indent=1)
    else:
        out.add("PRIZES: not in this snapshot")

    active = pl.get("active") or []
    if active:
        for pk in active:
            _pokemon(out, pk, cards, head="ACTIVE", indent=0, detail=2, effects=effects)
    else:
        out.add("ACTIVE: EMPTY")
        out.add("no Active Pokémon — must promote one (if it cannot, it loses)", indent=2)
    conditions = [c for c in _CONDITIONS if pl.get(c)]
    out.add("conditions: " + (", ".join(conditions) if conditions else "none") + " [pub]",
            indent=2)

    bench = pl.get("bench") or []
    bench_max = pl.get("benchMax", 5)
    out.add(f"BENCH {len(bench)} of {bench_max} [pub]")
    if not bench:
        out.add("(empty)", indent=1)
    for i, pk in enumerate(bench):
        _pokemon(out, pk, cards, head=f"{i}.", indent=1, detail=4, effects=effects)

    hand = pl.get("hand")
    hand_count = pl.get("handCount", len(hand) if isinstance(hand, list) else None)
    if isinstance(hand, list):
        out.add(f"HAND {hand_count} {mine}"
                + ("" if you else " count is pub, contents are not"))
        _zone(out, hand, cards, indent=1)
    else:
        out.add(f"HAND {hand_count} · contents not in this snapshot [pub count]")

    deck = pl.get("deck")
    deck_count = pl.get("deckCount", len(deck) if isinstance(deck, list) else None)
    if isinstance(deck, list):
        out.add(f"DECK {deck_count} left [pub count · hid contents]")
        if you:
            out.add("(this multiset is derivable by deck-tracking; the order is not)", indent=1)
        _zone(out, deck, cards, indent=1)
        if deck_order:
            out.add("recorded order — engine-internal, NOT a legitimate top-of-deck read:",
                    indent=1)
            for i, card in enumerate(deck):
                out.add(f"{i}. {_card_name(card, cards)}", indent=2)
    else:
        out.add(f"DECK {deck_count} left · contents not in this snapshot [pub count]")

    discard = pl.get("discard")
    if isinstance(discard, list):
        out.add(f"DISCARD {len(discard)} [pub — both may look]")
        _zone(out, discard, cards, indent=1)
    else:
        out.add(f"DISCARD {discard} [pub]")


def render(hit: FrameHit, *, deck_order: bool = False, cards: _Cards | None = None,
           width: int = WIDTH, effects: bool = True) -> str:
    """The frame as a plain-text list — fixed section order, wrapped to ``width``. ``effects=False``
    drops attack/ability rule text; every zone, count and flag stays."""
    cards = cards or _Cards()
    cur = hit.current or {}
    out = _Out(width)
    asked = hit.asked_seat if hit.asked_seat is not None else cur.get("yourIndex")

    corr = hit.correction or {}
    agent = corr.get("agent")
    build = corr.get("agent_version") or corr.get("agent_build")

    # --- header --------------------------------------------------------------------------
    out.add(f"BOARD STATE {hit.episode_id}-{hit.frame}")
    out.add(f"ep {hit.episode_id} · frame {hit.frame} · turn {cur.get('turn')}")
    if agent or build:
        out.add(f"agent {agent or '?'}" + (f" ({build})" if build else ""))
    out.add(f"src {hit.source}")
    if hit.source_path:
        out.path(_rel(hit.source_path), indent=1)
    if not hit.full_info:
        out.add("NOTE this is the per-seat Observation, not the full-information film — the "
                "opponent's hand, both decks and both prize piles are simply absent.")
    if not cards.present:
        out.add(f"NOTE card enrichment is OFF ({cards.error}) — every zone below is still exact; "
                f"printed HP, types, weakness, retreat cost and attack names are omitted.")
    out.raw("")
    out.raw("LABELS")
    for note in (LABELS if hit.full_info else LABELS_OBS):
        out.add(note, indent=1)
    out.raw("")

    # --- what the engine is asking -------------------------------------------------------
    out.rule("DECISION")
    ctx_name, ctx_meaning = _context_name(hit.select_context)
    ours = agent is not None and asked == corr.get("seat")
    out.add(f"asked seat s{asked}" + (f" · us · {agent}" if ours else ""))
    out.add(f"context {ctx_name}")
    if ctx_meaning:
        out.add(ctx_meaning, indent=1)
    out.add(f"type {_enum_name(hit.select_type, _SELECT_TYPE, 'selectType')}")
    options = hit.options or []
    out.add(f"options ({len(options)}):")
    if not options:
        out.add("(none recorded at this frame)", indent=1)
    for i, opt in enumerate(options):
        for j, part in enumerate(_option_parts(i, opt, cur, cards, asked)):
            out.add(part, indent=1 if j == 0 else 5)

    def _echo(indices):
        for i in indices or []:
            if isinstance(i, int) and 0 <= i < len(options):
                out.add(_option_summary(i, options[i], cur, cards, asked), indent=1)
            else:
                out.add(f"[{i}] (out of range)", indent=1)

    if hit.chosen is not None:
        out.add(f"AGENT CHOSE {hit.chosen}")
        _echo(hit.chosen)
        if corr.get("chosen_label"):
            out.add(f"tag: {corr['chosen_label']}", indent=1)
    if corr.get("correct") is not None:
        out.add(f"RULED CORRECT {corr['correct']}")
        _echo(corr["correct"])
        if corr.get("correct_label"):
            out.add(f"tag: {corr['correct_label']}", indent=1)
    if corr.get("category"):
        out.add(f"category {corr['category']}")
    if corr.get("rationale"):
        out.add("rationale:")
        out.add(corr["rationale"], indent=1)
    if corr.get("live_trace"):
        out.add("agent trace:")
        out.add(json.dumps(corr["live_trace"], ensure_ascii=False), indent=1, hard=True)
    out.raw("")

    # --- turn state ----------------------------------------------------------------------
    turn = cur.get("turn")
    first = cur.get("firstPlayer")
    tp = turn_player(turn, first)
    out.rule("TURN")
    out.add(f"turn {turn} — one ply, a single seat's turn")
    out.add(f"first player s{first}" if first is not None else "first player unknown")
    if tp is None:
        out.add("turn player: none — turn 0 is the shared setup phase, both seats act in it")
    else:
        out.add(f"turn player s{tp}")
        if asked is not None and asked != tp:
            out.add(f"!! s{asked} is being asked OUT OF TURN — a forced select during s{tp}'s "
                    f"turn, e.g. promoting after a KO. The flags below are s{tp}'s, NOT yours.")
        else:
            out.add(f"s{asked} is the turn player — the flags below are your own")
    out.add(f"where s{tp if tp is not None else '?'} is in the turn:")

    def flag(key, label, yes, no):
        val = cur.get(key)
        if val is None:
            out.add(f"{label}: not recorded", indent=1)
            return
        out.add(f"{label}: {'YES' if val else 'NO'}", indent=1)
        out.add(yes if val else no, indent=3)

    flag("energyAttached", "energy attached from hand",
         "no manual attach left (card effects can still add energy)",
         "the 1 manual attach is still available")
    flag("supporterPlayed", "supporter played",
         "no second Supporter this turn",
         "the 1 Supporter is still available")
    flag("stadiumPlayed", "stadium played",
         "no second Stadium this turn",
         "one may be played if it differs from the one in play")
    flag("retreated", "retreated",
         "no second manual retreat (Switch-style effects still work)",
         "the 1 manual retreat is available, paying the Retreat cost")
    out.add(f"actions taken: {cur.get('turnActionCount')}", indent=1)
    out.add("attack: 1/turn, and it ENDS the turn", indent=1)
    if turn == 1 and tp is not None and first == tp:
        out.add("first player, turn 1: CANNOT attack and CANNOT play a Supporter "
                "(docs/rulebook.txt §2)", indent=1)

    stadium = cur.get("stadium")
    if isinstance(stadium, list) and stadium:
        for st in stadium:
            owner = st.get("playerIndex")
            out.add(f"stadium: {_card_name(st, cards)}"
                    + (f" (s{owner})" if owner is not None else "")
                    + " [pub, affects both]")
    else:
        out.add("stadium: none")

    looking = cur.get("looking")
    look_n = cur.get("lookingCount")
    if isinstance(looking, list) and looking:
        out.add(f"looking at ({len(looking)}): "
                + ", ".join(_count_names(looking, cards)))
    elif look_n:
        out.add(f"looking at: {look_n} (contents not in this snapshot)")
    else:
        out.add("looking at: none")

    result = cur.get("result")
    if result is None or result == -1:
        out.add("result: not decided yet")
    elif result == 2:
        out.add("result: DRAW")
    else:
        out.add(f"result: s{result} has WON")

    # --- both sides ----------------------------------------------------------------------
    players = cur.get("players") or []
    seats = list(range(len(players)))
    if asked in seats:
        seats = [asked] + [s for s in seats if s != asked]
    for seat in seats:
        if seat == asked:
            label = f"us · {agent}" if agent else "the asked seat · us"
        else:
            label = "the opponent" if agent else "the other seat"
        _side(out, seat, cur, cards, asked_seat=asked, label=label, deck_order=deck_order,
              effects=effects)

    if hit.obs_recorded:
        out.raw("")
        out.add("an agent Observation was recorded alongside this frame — the exact per-seat "
                "input the agent saw.")
    return out.text()


def dump(key: str, *, deck_order: bool = False, replay_path: Path | None = None,
         replays=DEFAULT_REPLAYS, corrections=DEFAULT_CORRECTIONS,
         fixtures=DEFAULT_FIXTURES, width: int = WIDTH, effects: bool = True) -> str:
    """``dump("82756664-97")`` -> the whole read-out as one plain-text string."""
    episode_id, frame = parse_frame_key(key)
    hit = find_frame(episode_id, frame, replays=replays, corrections=corrections,
                     fixtures=fixtures, replay_path=replay_path)
    return render(hit, deck_order=deck_order, width=width, effects=effects)



def available_frames(episode_id: int | None = None, *, corrections=DEFAULT_CORRECTIONS,
                     fixtures=DEFAULT_FIXTURES) -> list[str]:
    """Every ``<ep>-<frame>`` key resolvable from the committed stores, sorted — what a "not found"
    offers next, since with no replay on disk only tagged frames resolve."""
    keys: set[str] = set()
    corrections = Path(corrections) if corrections else None
    if corrections and corrections.exists():
        for path in jsonl_files(corrections):        # the store's layout, not ours
            for c in _corrections_in(path):        # constructed, not raw — see `find_frame`
                ep, fr = c.episode_id, (c.decision or {}).get("frame")
                if ep is None or fr is None:
                    continue
                if episode_id is None or ep == episode_id:
                    keys.add(f"{ep}-{fr}")
    fixtures = Path(fixtures) if fixtures else None
    if fixtures and fixtures.is_dir():
        for path in fixtures.glob("*.json"):
            try:
                rec = load_replay(path)
            except (OSError, ValueError):
                continue
            if not rec.get("obs"):
                continue
            for ep, fr in _note_keys(rec.get("note")):
                if episode_id is None or ep == episode_id:
                    keys.add(f"{ep}-{fr}")
    return sorted(keys, key=lambda k: tuple(int(p) for p in k.split("-")))


def main(argv=None) -> int:
    """``python -m train.blunder.frame_view <ep>-<frame>`` (with tools/ and src/ on PYTHONPATH)."""
    import argparse
    import sys

    if hasattr(sys.stdout, "reconfigure"):     # Windows consoles default to cp1252; ⚡ breaks it
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("key", help="frame key, e.g. 92645419-25")
    parser.add_argument("--width", type=int, default=WIDTH)
    parser.add_argument("--deck-order", action="store_true")
    args = parser.parse_args(argv)
    print(dump(args.key, deck_order=args.deck_order, width=args.width))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
