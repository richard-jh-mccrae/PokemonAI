"""Render ONE frame's complete board state as plain text — the diagnostic read-out.

Diagnosing a blunder always starts the same way: "pull up the full board state of `82756664-97`".
Done by hand that is slow and, worse, *inconsistent* — a different subset of the state each time,
formatted a different way, so two sittings on the same frame aren't comparable. This module is the
single deterministic answer: one frame key in, one fixed-order plain-text dump out.

**The key** is the repo's existing Anchor form ``<episode>-<frame>`` (`/blunder-buster` SKILL.md),
e.g. ``82756664-97``. ``82756664-f97`` and ``ep82756664 f97`` also parse — the forms that show up
in ADRs, fixture notes and chat.

**Two snapshot shapes, one output.** A frame reaches us as either

* the **full-information film** snapshot (``current`` from a replay's ``visualize`` film, or the
  copy a Correction embeds in ``decision.current``) — both decks, both hands, both prize piles are
  listed, and cards carry ``name``; enums are *strings* (``"Attach"``, ``"ToActive"``); or
* the per-seat **agent Observation** (``obs.current``, what a fixture pins) — opponent hand is
  ``None``, ``prize`` is a bare count, ``deck`` is absent entirely, cards carry only ``id``, and
  every enum is an *int*.

Both normalize into the same section order here, so the read-out never changes shape with the
source. Where the film shows more than the agent could see, the zone is labelled — see
`VISIBILITY`. The full-info deck/prize contents are a diagnostic aid, never evidence the agent had
them: reasoning "it should have known" off a `[hidden]` zone is the whole trap this labelling exists
to stop.

**The turn flags belong to the TURN PLAYER, not to whoever is being asked.** ``energyAttached`` /
``supporterPlayed`` / ``retreated`` / ``stadiumPlayed`` are properties of the turn in progress. A
seat is regularly prompted *out of turn* — the post-KO ``ToActive`` promotion is the common case —
and then those flags describe the **opponent's** turn. ``82756664-97`` is exactly that frame, which
is why the read-out names the turn player explicitly instead of implying "you". Turn player is
``(firstPlayer + turn - 1) % 2`` for ``turn >= 1`` (`train.probes.doom_audit.turn_player`); ``turn
0`` is the shared setup phase with no single actor (`tools/train/CONTEXT.md`).

Card enrichment (printed HP, type, weakness, retreat, attack names/costs, prize value) comes from
the committed pure-Python tables `cgpy.cards.CardDB` (`src/cgpy/defs/`) — no native engine, so this
runs on a bare clone. Enrichment is **fail-open**: without the tables you still get every zone, and
the header says enrichment is off. The state itself is never inferred.

Deliberately NOT computed: whether an attack is affordable. That is an *inference* over
`common.strategy` cost rules, not board state, and a subtly wrong affordability verdict is worse
than none. The read-out prints attached energy and each attack's printed cost side by side and
leaves the judgment to the reader.
"""
from __future__ import annotations

import gzip
import json
import re
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DEFAULT_CORRECTIONS = REPO / "data" / "corrections"
DEFAULT_REPLAYS = REPO / "data" / "replays"
DEFAULT_FIXTURES = REPO / "tests" / "fixtures" / "corrections"

VISIBILITY = (
    "[public] — both players can see it.",
    "[you see this] — the asked seat's own hand.",
    "[hidden from you] — the asked seat could NOT see it. It is listed only because the film is "
    "full-information; never read it as something the agent knew.",
    "A deck's multiset is legitimately derivable by deck-tracking; its ORDER is not — treat the "
    "recorded order as engine-internal.",
)

VISIBILITY_OBS = (
    "[public] — both players can see it.",
    "[you see this] — the asked seat's own hand.",
    "This snapshot is the agent's own Observation, so nothing hidden from it appears at all — a "
    "zone it could not see is either absent or listed as face-down placeholders.",
)

# --- engine enums (src/cg/api.py) ------------------------------------------------------------
# The film spells these as strings and the obs as ints, so every lookup takes either.

_AREA = {1: "DECK", 2: "HAND", 3: "DISCARD", 4: "ACTIVE", 5: "BENCH", 6: "PRIZE",
         7: "STADIUM", 8: "ENERGY", 9: "TOOL", 10: "PRE_EVOLUTION", 11: "PLAYER", 12: "LOOKING"}

_CARD_TYPE = {0: "Pokemon", 1: "Item", 2: "Tool", 3: "Supporter", 4: "Stadium",
              5: "Basic Energy", 6: "Special Energy"}

# Symbols verified against the Basic Energy card names in src/cgpy/defs/card_data.json
# (energyType 1 == "Basic {G} Energy", ...). DRAGON/RAINBOW/TEAM_ROCKET have no Basic card to
# confirm a symbol, so they are named rather than invented.
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
    """The seat whose turn ``turn`` (1-based) is — ``firstPlayer`` takes the odd turns.

    ``None`` for turn 0 (the shared setup phase, where both seats act) or when either input is
    missing. Mirrors `train.probes.doom_audit.turn_player`.
    """
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
    """`cgpy.cards.CardDB` if the committed tables load, else a null object.

    Enrichment is a convenience over the raw state; a bare environment that cannot import the
    tables still gets every zone (the header says so). Never used to *infer* board state.
    """

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
    """A card's name — from the film's own ``name``, else resolved from ``id``.

    A per-seat Observation spells a card the seat cannot see as a bare ``null`` (its prize pile is
    six of them), so a non-dict entry is a *known unknown*, not corrupt data.
    """
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
    """Prizes a KO on this Pokémon awards, per docs/rules.md §6 (megaEx 3 / ex 2 / else 1)."""
    if stat is None:
        return 1, "assumed 1 (card table unavailable)"
    if getattr(stat, "megaEx", False):
        return 3, "3 (Mega Evolution Pokémon ex)"
    if getattr(stat, "ex", False):
        return 2, "2 (Pokémon ex)"
    return 1, "1 (regular Pokémon)"


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


# --- locating a frame -------------------------------------------------------------------------

_KEY = re.compile(r"^\s*(?:ep)?(\d+)\s*[-_:\s]\s*f?(\d+)\s*$", re.IGNORECASE)

# The same pair spotted *inside* free text — fixture notes write it as "82756664-37" or
# "83686860 f29", so both separators count. The 6-digit floor on the episode is what keeps a bare
# "f82" and, more importantly, a date ("2026-07-13" -> ep 2026 frame 7) from scanning as a key;
# Kaggle episode ids run to 8 digits, well clear of it.
_KEY_IN_TEXT = re.compile(r"(?:ep)?(\d{6,})\s*[-_:\s]\s*f?(\d+)", re.IGNORECASE)


def _note_keys(note) -> set[tuple[int, int]]:
    """Every ``(episode, frame)`` pair a fixture's free-text ``note`` mentions."""
    return {(int(a), int(b)) for a, b in _KEY_IN_TEXT.findall(str(note or ""))}


def parse_frame_key(key: str) -> tuple[int, int]:
    """``"82756664-97"`` -> ``(82756664, 97)``. Also accepts ``82756664-f97``, ``ep82756664 f97``.

    Raises ``ValueError`` on anything else — including the *scoped* Correction keys
    (``<ep>-t<turn>s<seat>``, ``<ep>-m<seat>``), which name a Turn or a Match rather than one
    frame and so have no single board state to dump.
    """
    text = str(key).strip()
    m = _KEY.match(text)
    if not m:
        hint = ""
        if re.search(r"-\s*[tm]\d", text, re.IGNORECASE):
            hint = (" — that looks like a scoped Correction key (a Turn or a Match, not one "
                    "frame); pass the Anchor frame instead")
        raise ValueError(f"not an <episode>-<frame> key: {key!r}{hint}")
    return int(m.group(1)), int(m.group(2))


@dataclass
class FrameHit:
    """One located frame: its normalized snapshot plus wherever it came from."""
    episode_id: int
    frame: int
    current: dict
    source: str                       # human-readable provenance line
    source_path: Path | None = None
    full_info: bool = True            # film snapshot (both sides listed) vs per-seat obs
    select_context: int | str | None = None   # int in an obs, string in the film
    select_type: int | str | None = None
    options: list | None = None
    turn: int | None = None
    asked_seat: int | None = None
    chosen: list | None = None
    correction: dict | None = None    # the Correction tag, when the frame came from one
    obs_recorded: bool = False


def _film(replay: dict) -> list:
    steps = replay.get("steps") or []
    if not steps or not steps[0]:
        return []
    return steps[0][0].get("visualize") or []


def _read_json(path: Path) -> dict:
    if str(path).endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    return json.loads(path.read_text(encoding="utf-8"))


def _hit_from_correction(rec: dict, path: Path) -> FrameHit:
    dec = rec.get("decision") or {}
    cur = dec.get("current") or {}
    hit = FrameHit(
        episode_id=rec.get("episode_id"),
        frame=dec.get("frame"),
        current=cur,
        source=f"Correction log (embedded full-information snapshot) — {path}",
        source_path=path,
        full_info=True,
        turn=dec.get("turn"),
        asked_seat=cur.get("yourIndex", rec.get("seat")),
        chosen=rec.get("chosen"),
        correction=rec,
        obs_recorded=bool(rec.get("obs")),
    )
    hit.select_context = dec.get("select_context")
    hit.select_type = dec.get("select_type")
    hit.options = dec.get("options") or []
    return hit


def _hit_from_film(replay: dict, path: Path, episode_id: int, frame: int) -> FrameHit | None:
    film = _film(replay)
    if not (0 <= frame < len(film)):
        return None
    entry = film[frame] or {}
    cur = entry.get("current") or {}
    select = entry.get("select") if isinstance(entry.get("select"), dict) else {}
    nxt = film[frame + 1] if frame + 1 < len(film) else None
    hit = FrameHit(
        episode_id=episode_id,
        frame=frame,
        current=cur,
        source=f"Replay film, frame {frame} of {len(film)} (full information) — {path}",
        source_path=path,
        full_info=True,
        turn=cur.get("turn"),
        asked_seat=cur.get("yourIndex"),
        chosen=(nxt or {}).get("selected"),
        obs_recorded=bool((nxt or {}).get("obs")),
    )
    hit.select_context = (select or {}).get("context")
    hit.select_type = (select or {}).get("type")
    hit.options = (select or {}).get("option") or []
    return hit


def _hit_from_fixture(rec: dict, path: Path, episode_id: int, frame: int) -> FrameHit:
    obs = rec.get("obs") or {}
    cur = obs.get("current") or {}
    select = obs.get("select") if isinstance(obs.get("select"), dict) else {}
    hit = FrameHit(
        episode_id=episode_id,
        frame=frame,
        current=cur,
        source=f"Test fixture (per-seat agent Observation — opponent hand, both decks and both "
               f"prize piles are NOT in this snapshot) — {path}",
        source_path=path,
        full_info=False,
        turn=cur.get("turn"),
        asked_seat=cur.get("yourIndex"),
        chosen=None,
        correction={"correct": rec.get("correct"), "rationale": rec.get("note")}
        if rec.get("correct") is not None or rec.get("note") else None,
        obs_recorded=True,
    )
    hit.select_context = (select or {}).get("context")
    hit.select_type = (select or {}).get("type")
    hit.options = (select or {}).get("option") or []
    return hit


def find_frame(episode_id: int, frame: int, *, replays=DEFAULT_REPLAYS,
               corrections=DEFAULT_CORRECTIONS, fixtures=DEFAULT_FIXTURES,
               replay_path: Path | None = None) -> FrameHit:
    """Locate ``episode-frame`` in the best source available, richest first.

    1. ``replay_path`` when given, else any replay under ``replays`` whose ``info.EpisodeId``
       matches — the full film, so *any* frame resolves, not only tagged ones.
    2. the Correction tree — the frames a human tagged, each carrying its own embedded
       full-information snapshot plus the ruling.
    3. ``tests/fixtures/corrections`` — the per-seat Observation a test pins, matched on the
       ``<ep>-<frame>`` key in its ``note``.

    Raises ``LookupError`` naming every place searched when nothing matches.
    """
    searched: list[str] = []

    if replay_path is not None:
        replay_path = Path(replay_path)
        hit = _hit_from_film(_read_json(replay_path), replay_path, episode_id, frame)
        if hit is None:
            raise LookupError(f"{replay_path} has no frame {frame}")
        return hit

    replays = Path(replays) if replays else None
    if replays and replays.is_dir():
        searched.append(f"{replays}/**/*.json[.gz]")
        for path in sorted(replays.rglob("*.json")) + sorted(replays.rglob("*.json.gz")):
            try:
                replay = _read_json(path)
            except (OSError, ValueError):
                continue
            if (replay.get("info") or {}).get("EpisodeId") != episode_id:
                continue
            hit = _hit_from_film(replay, path, episode_id, frame)
            if hit is not None:
                return hit
    elif replays:
        searched.append(f"{replays} (absent — raw replays are not committed, ADR-0002)")

    corrections = Path(corrections) if corrections else None
    if corrections and corrections.exists():
        searched.append(f"{corrections}/**/corrections.jsonl")
        for path in sorted(corrections.rglob("corrections.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("episode_id") != episode_id:
                    continue
                if (rec.get("decision") or {}).get("frame") != frame:
                    continue
                return _hit_from_correction(rec, path)

    fixtures = Path(fixtures) if fixtures else None
    if fixtures and fixtures.is_dir():
        searched.append(f"{fixtures}/*.json")
        for path in sorted(fixtures.glob("*.json")):
            try:
                rec = _read_json(path)
            except (OSError, ValueError):
                continue
            if rec.get("obs") and (episode_id, frame) in _note_keys(rec.get("note")):
                return _hit_from_fixture(rec, path, episode_id, frame)

    raise LookupError(
        f"frame {episode_id}-{frame} not found. Searched: " + "; ".join(searched or ["nothing"]) +
        ". A replay makes any frame resolvable — pass --replay <file> if you have the episode's "
        "film (raw replays are not committed).")


# --- rendering --------------------------------------------------------------------------------

def _pokemon_lines(pk: dict | None, cards: _Cards, *, slot: str, indent: str = "") -> list[str]:
    """One Pokémon in play, as an indented plain-text block."""
    if not isinstance(pk, dict):
        # A face-down Active during Set Up (the Cinderace "Explosiveness" opener) reaches an
        # Observation as a bare null.
        return [f"{indent}{slot}: {UNKNOWN_CARD}"]
    stat = cards.card(pk.get("id"))
    name = _card_name(pk, cards)
    hp, max_hp = pk.get("hp"), pk.get("maxHp")
    damage = (max_hp - hp) if isinstance(hp, int) and isinstance(max_hp, int) else None
    head = f"{indent}{slot}: {name}"
    if isinstance(hp, int) and isinstance(max_hp, int):
        head += f" — {hp} of {max_hp} HP left"
        head += f" ({damage} damage on it)" if damage else " (undamaged)"
    lines = [head]
    sub = indent + "  "

    printed = getattr(stat, "hp", None) if stat is not None else None
    if isinstance(printed, int) and isinstance(max_hp, int) and printed and printed != max_hp:
        delta = max_hp - printed
        lines.append(f"{sub}max HP is {max_hp}, printed HP is {printed} "
                     f"({delta:+d} from effects in play, e.g. a Tool or the Stadium)")

    facts = []
    stage = _stage(stat)
    if stage:
        facts.append(stage)
    if stat is not None:
        etype = getattr(stat, "energyType", None)
        if etype is not None:
            facts.append(f"type {_ENERGY.get(int(etype), etype)}")
        weak = getattr(stat, "weakness", None)
        facts.append(f"weakness {_ENERGY.get(int(weak), weak)} (takes x2)" if weak is not None
                     else "no weakness")
        resist = getattr(stat, "resistance", None)
        if resist is not None:
            facts.append(f"resistance {_ENERGY.get(int(resist), resist)}")
        retreat = getattr(stat, "retreatCost", None)
        if retreat is not None:
            facts.append(f"retreat cost {retreat}")
        prizes, why = _prize_value(stat)
        facts.append(f"KO here gives the opponent {why}")
    if facts:
        lines.append(f"{sub}{' · '.join(facts)}")

    energies = pk.get("energies") or []
    ecards = pk.get("energyCards") or []
    if energies or ecards:
        names = ", ".join(_card_name(c, cards) for c in ecards) if ecards else "?"
        unit = "unit" if len(energies) == 1 else "units"
        lines.append(f"{sub}energy attached: {len(energies)} {unit} providing "
                     f"{_energy_symbols(energies)} — cards: {names}")
    else:
        lines.append(f"{sub}energy attached: none")

    tools = pk.get("tools") or []
    lines.append(f"{sub}tool attached: {', '.join(_card_name(t, cards) for t in tools)}"
                 if tools else f"{sub}tool attached: none")

    pre = pk.get("preEvolution") or []
    if pre:
        lines.append(f"{sub}evolved from (underneath): "
                     f"{', '.join(_card_name(c, cards) for c in pre)}")

    if stat is not None and getattr(stat, "attacks", None):
        for aid in stat.attacks:
            atk = cards.attack(aid)
            if atk is None:
                lines.append(f"{sub}attack: id {aid} (not in the card table)")
                continue
            dmg = f"{atk.damage} damage" if atk.damage else "no listed damage"
            lines.append(f"{sub}attack: {atk.name} — costs {_energy_symbols(atk.energies)} "
                         f"({len(atk.energies)} energy) — {dmg}")
            if atk.text:
                lines.append(f"{sub}  effect: {atk.text}")
    if stat is not None and getattr(stat, "skills", None):
        for sname, stext in stat.skills:
            lines.append(f"{sub}ability: {sname.strip()} — {stext}")

    if pk.get("appearThisTurn"):
        lines.append(f"{sub}came into play THIS TURN (so it cannot evolve this turn)")
    return lines


def _group_cards(cards_list, cards: _Cards) -> list[str]:
    """A zone as ``name x N — Category`` lines, ordered by category then name."""
    counts: dict[tuple[str, str], int] = {}
    for card in cards_list:
        key = (_category(card, cards), _card_name(card, cards))
        counts[key] = counts.get(key, 0) + 1
    order = {name: i for i, name in enumerate(
        ["Pokemon", "Basic Energy", "Special Energy", "Item", "Tool", "Supporter", "Stadium", "?"])}
    out = []
    for (cat, name), n in sorted(counts.items(), key=lambda kv: (order.get(kv[0][0], 99),
                                                                kv[0][1].lower())):
        if name == UNKNOWN_CARD:
            out.append(f"{n} card(s) {UNKNOWN_CARD}")
            continue
        out.append(f"{name} x{n} — {cat}" if n > 1 else f"{name} — {cat}")
    return out


def _option_line(idx: int, opt: dict, cur: dict, cards: _Cards, asked_seat) -> str:
    """One offered option, resolved to the thing it actually names."""
    otype = _enum_name(opt.get("type"), _OPTION_TYPE, "optionType")
    bits = [f"[{idx}] {otype}"]

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
            return f"seat {seat} {area_name} index {index}" if isinstance(index, int) else None
        entries = players[seat].get(zone)
        if not isinstance(entries, list) or not isinstance(index, int):
            return None
        if not (0 <= index < len(entries)):
            return None
        return f"seat {seat} {zone.upper()} index {index} = {_card_name(entries[index], cards)}"

    # A PLAY option carries a bare hand index and no `area` — see the engine's own builder
    # (`cgpy.options`: {"type": PLAY, "index": i} over the hand). Everything else that points at a
    # card says which area it means.
    area = opt.get("area")
    if area is None and otype == "Play":
        area = 2                                          # AreaType.HAND
    target = _slot(opt.get("playerIndex"), area, opt.get("index"))
    if target:
        bits.append(target)
    elif opt.get("index") is not None:
        bits.append(f"index {opt['index']}")

    if opt.get("inPlayArea") is not None:
        onto = _slot(opt.get("inPlayPlayerIndex", asked_seat), opt.get("inPlayArea"),
                     opt.get("inPlayIndex"))
        bits.append(f"onto {onto}" if onto else
                    f"onto {_enum_name(opt.get('inPlayArea'), _AREA)} "
                    f"index {opt.get('inPlayIndex')}")

    if opt.get("attackId") is not None:
        atk = cards.attack(opt["attackId"])
        bits.append(f"{atk.name} — costs {_energy_symbols(atk.energies)} — {atk.damage} damage"
                    if atk else f"attackId {opt['attackId']}")

    for extra in ("number", "specialCondition"):
        if opt.get(extra) is not None:
            bits.append(f"{extra} {opt[extra]}")
    return " · ".join(bits)


def _side_lines(seat: int, cur: dict, cards: _Cards, *, asked_seat,
                label: str, deck_order: bool) -> list[str]:
    players = cur.get("players") or []
    if not (0 <= seat < len(players)):
        return [f"seat {seat}: not in this snapshot"]
    pl = players[seat]
    you = (seat == asked_seat)
    mine = "[you see this]" if you else "[hidden from you]"
    lines = [f"--- SEAT {seat} — {label} ---"]

    # prizes first: the clock every plan is measured against
    prize = pl.get("prize")
    if isinstance(prize, list):
        remaining = len(prize)
        lines.append(f"prizes remaining: {remaining} of 6 — {6 - remaining} already taken "
                     f"(taking the 6th wins the game) [public count]")
        if _all_unknown(prize):
            lines.append("prize cards: face down, identities not in this snapshot "
                         "(the agent cannot see them)")
        else:
            lines.append("prize cards, face down [hidden from you]:")
            for line in _group_cards(prize, cards):
                lines.append(f"  {line}")
    elif isinstance(prize, int):
        lines.append(f"prizes remaining: {prize} of 6 — {6 - prize} already taken "
                     f"(taking the 6th wins the game) [public count]")
        lines.append("prize cards: not in this snapshot (the agent cannot see them)")
    else:
        lines.append("prizes: not in this snapshot")

    active = pl.get("active") or []
    if active:
        for pk in active:
            lines.extend(_pokemon_lines(pk, cards, slot="ACTIVE"))
    else:
        lines.append("ACTIVE: EMPTY — this seat has no Active Pokémon and must promote one "
                     "(if it cannot, it loses)")

    conditions = [c for c in _CONDITIONS if pl.get(c)]
    lines.append("  special conditions on the Active: "
                 + (", ".join(conditions) if conditions else "none") + " [public]")

    bench = pl.get("bench") or []
    bench_max = pl.get("benchMax", 5)
    lines.append(f"BENCH: {len(bench)} of {bench_max} filled [public]")
    if not bench:
        lines.append("  (empty)")
    for i, pk in enumerate(bench):
        lines.extend(_pokemon_lines(pk, cards, slot=f"bench {i}", indent="  "))

    hand = pl.get("hand")
    hand_count = pl.get("handCount", len(hand) if isinstance(hand, list) else None)
    if isinstance(hand, list):
        lines.append(f"HAND: {hand_count} cards {mine}"
                     + ("" if you else " — the count is public, the contents are not"))
        for line in _group_cards(hand, cards):
            lines.append(f"  {line}")
    else:
        lines.append(f"HAND: {hand_count} cards — contents not in this snapshot "
                     f"[hidden from you; the count is public]")

    deck = pl.get("deck")
    deck_count = pl.get("deckCount", len(deck) if isinstance(deck, list) else None)
    if isinstance(deck, list):
        why = ("hidden from you — but this multiset is derivable by deck-tracking" if you
               else "hidden from you")
        lines.append(f"DECK: {deck_count} cards left [count is public; contents {why}]")
        for line in _group_cards(deck, cards):
            lines.append(f"  {line}")
        if deck_order:
            lines.append("  deck order as recorded in the film (engine-internal — NOT a legitimate "
                         "top-of-deck read):")
            for i, card in enumerate(deck):
                lines.append(f"    {i}. {_card_name(card, cards)}")
    else:
        lines.append(f"DECK: {deck_count} cards left — contents not in this snapshot "
                     f"[count is public]")

    discard = pl.get("discard")
    if isinstance(discard, list):
        lines.append(f"DISCARD: {len(discard)} cards [public — both players may look]")
        if not discard:
            lines.append("  (empty)")
        for line in _group_cards(discard, cards):
            lines.append(f"  {line}")
    else:
        lines.append(f"DISCARD: {discard} cards [public]")
    return lines


def render(hit: FrameHit, *, deck_order: bool = False, cards: _Cards | None = None) -> str:
    """The frame as a plain-text list — fixed section order, no tables."""
    cards = cards or _Cards()
    cur = hit.current or {}
    out: list[str] = []
    asked = hit.asked_seat if hit.asked_seat is not None else cur.get("yourIndex")

    corr = hit.correction or {}
    agent = corr.get("agent")
    build = corr.get("agent_build") or corr.get("agent_version")

    out.append(f"BOARD STATE — FRAME {hit.episode_id}-{hit.frame}")
    out.append(f"episode {hit.episode_id} · frame {hit.frame} · turn {cur.get('turn')}")
    out.append(f"source: {hit.source}")
    if agent or build:
        out.append(f"our agent: {agent or '?'} (build {build or '?'})")
    if not hit.full_info:
        out.append("NOTE: this is the per-seat Observation, not the full-information film — the "
                   "opponent's hand, both decks and both prize piles are simply absent.")
    if not cards.present:
        out.append(f"NOTE: card enrichment is OFF ({cards.error}) — every zone below is still "
                   f"exact; printed HP, types, weakness, retreat cost and attack names are "
                   f"omitted.")
    out.append("how to read the visibility labels:")
    for note in (VISIBILITY if hit.full_info else VISIBILITY_OBS):
        out.append(f"  {note}")
    out.append("")

    # --- what the engine is asking -------------------------------------------------------
    ctx_name, ctx_meaning = _context_name(hit.select_context)
    out.append("--- THE DECISION (what the engine is asking for) ---")
    ours = agent is not None and asked == corr.get("seat")
    out.append(f"asked seat: {asked}" + (f" (our agent {agent})" if ours else ""))
    out.append(f"select context: {ctx_name}" + (f" — {ctx_meaning}" if ctx_meaning else ""))
    out.append(f"select type: {_enum_name(hit.select_type, _SELECT_TYPE, 'selectType')}")
    options = hit.options or []
    out.append(f"options offered: {len(options)}")
    for i, opt in enumerate(options):
        out.append(f"  {_option_line(i, opt, cur, cards, asked)}")
    if not options:
        out.append("  (none recorded at this frame)")

    def _labels(indices):
        picked = []
        for i in indices or []:
            if isinstance(i, int) and 0 <= i < len(options):
                picked.append(_option_line(i, options[i], cur, cards, asked))
            else:
                picked.append(f"[{i}] (out of range)")
        return picked

    if hit.chosen is not None:
        out.append(f"the agent chose: {hit.chosen}")
        for line in _labels(hit.chosen):
            out.append(f"  {line}")
        if corr.get("chosen_label"):
            out.append(f"  tagged label: {corr['chosen_label']}")
    if corr.get("correct") is not None:
        out.append(f"human ruling — the correct choice was: {corr['correct']}")
        for line in _labels(corr["correct"]):
            out.append(f"  {line}")
        if corr.get("correct_label"):
            out.append(f"  tagged label: {corr['correct_label']}")
    if corr.get("category"):
        out.append(f"blunder category: {corr['category']}")
    if corr.get("rationale"):
        out.append(f"rationale: {corr['rationale']}")
    if corr.get("live_trace"):
        trace = json.dumps(corr["live_trace"], ensure_ascii=False)
        out.append(f"agent trace at this frame: {trace}")
    out.append("")

    # --- turn state ----------------------------------------------------------------------
    turn = cur.get("turn")
    first = cur.get("firstPlayer")
    tp = turn_player(turn, first)
    out.append("--- TURN STATE ---")
    out.append(f"turn {turn} (one ply — a single seat's turn)")
    out.append(f"first player: seat {first}" if first is not None else "first player: unknown")
    if tp is None:
        out.append("turn player: none — turn 0 is the shared setup phase, both seats act in it")
    else:
        out.append(f"turn player: seat {tp} — the per-turn flags below are SEAT {tp}'s")
        if asked is not None and asked != tp:
            out.append(f"!! seat {asked} is being asked OUT OF TURN (a forced select during seat "
                       f"{tp}'s turn, e.g. promoting after a KO). The flags below are NOT yours.")
        else:
            out.append(f"seat {asked} is the turn player — these are your own flags")

    def flag(key, label, yes, no):
        val = cur.get(key)
        if val is None:
            return f"  {label}: not recorded in this snapshot"
        return f"  {label}: {'YES' if val else 'NO'} — {yes if val else no}"

    out.append(f"where seat {tp if tp is not None else '?'} is in the turn:")
    out.append(flag("energyAttached", "energy attached from hand",
                    "energy already attached from hand this turn — no manual attach left "
                    "(card effects can still add energy)",
                    "no energy attached from hand yet — the 1 manual attach is still available"))
    out.append(flag("supporterPlayed", "supporter played",
                    "a Supporter has been played this turn — no second Supporter",
                    "no Supporter played yet — the 1 Supporter is still available"))
    out.append(flag("stadiumPlayed", "stadium played",
                    "a Stadium has been played this turn — no second Stadium",
                    "no Stadium played yet — one may be played if it differs from the one in play"))
    out.append(flag("retreated", "retreated",
                    "already retreated manually this turn — no second manual retreat "
                    "(Switch-style effects still work)",
                    "has not retreated yet — the 1 manual retreat is available, paying the "
                    "Retreat cost"))
    out.append(f"  actions taken this turn: {cur.get('turnActionCount')}")
    out.append("  attacking is once per turn and ENDS the turn")
    if turn == 1 and tp is not None and first == tp:
        out.append("  first player, turn 1: CANNOT attack and CANNOT play a Supporter this turn "
                   "(docs/rules.md §2)")

    stadium = cur.get("stadium")
    if isinstance(stadium, list) and stadium:
        for st in stadium:
            owner = st.get("playerIndex")
            out.append(f"stadium in play: {_card_name(st, cards)}"
                       + (f" (played by seat {owner})" if owner is not None else "")
                       + " [public — it affects both sides]")
    else:
        out.append("stadium in play: none")

    looking = cur.get("looking")
    look_n = cur.get("lookingCount")
    if isinstance(looking, list) and looking:
        out.append(f"cards being looked at right now ({len(looking)}): "
                   + ", ".join(_card_name(c, cards) for c in looking))
    elif look_n:
        out.append(f"cards being looked at right now: {look_n} (contents not in this snapshot)")
    else:
        out.append("cards being looked at right now: none")

    result = cur.get("result")
    if result is None or result == -1:
        out.append("match result: not decided yet")
    elif result == 2:
        out.append("match result: DRAW")
    else:
        out.append(f"match result: seat {result} has WON")
    out.append("")

    # --- both sides ----------------------------------------------------------------------
    players = cur.get("players") or []
    seats = list(range(len(players)))
    if asked in seats:
        seats = [asked] + [s for s in seats if s != asked]
    for seat in seats:
        label = ("the asked seat — us" if seat == asked else "the other seat")
        if seat == asked and agent:
            label = f"the asked seat — us, {agent}"
        elif seat != asked and agent:
            label = "the other seat — the opponent"
        out.extend(_side_lines(seat, cur, cards, asked_seat=asked,
                               label=label, deck_order=deck_order))
        out.append("")

    if hit.obs_recorded:
        out.append("an agent Observation was recorded alongside this frame (the exact per-seat "
                   "input the agent saw).")
    return "\n".join(out).rstrip() + "\n"


def dump(key: str, *, deck_order: bool = False, replay_path: Path | None = None,
         replays=DEFAULT_REPLAYS, corrections=DEFAULT_CORRECTIONS,
         fixtures=DEFAULT_FIXTURES) -> str:
    """``dump("82756664-97")`` -> the whole read-out as one plain-text string."""
    episode_id, frame = parse_frame_key(key)
    hit = find_frame(episode_id, frame, replays=replays, corrections=corrections,
                     fixtures=fixtures, replay_path=replay_path)
    return render(hit, deck_order=deck_order)


def available_frames(episode_id: int | None = None, *, corrections=DEFAULT_CORRECTIONS,
                     fixtures=DEFAULT_FIXTURES) -> list[str]:
    """Every ``<ep>-<frame>`` key resolvable from the committed stores, sorted.

    What a "not found" should offer next: with no replay on disk only tagged frames resolve, so
    naming them beats a bare failure.
    """
    keys: set[str] = set()
    corrections = Path(corrections) if corrections else None
    if corrections and corrections.exists():
        for path in corrections.rglob("corrections.jsonl"):
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                ep = rec.get("episode_id")
                fr = (rec.get("decision") or {}).get("frame")
                if ep is None or fr is None:
                    continue
                if episode_id is None or ep == episode_id:
                    keys.add(f"{ep}-{fr}")
    fixtures = Path(fixtures) if fixtures else None
    if fixtures and fixtures.is_dir():
        for path in fixtures.glob("*.json"):
            try:
                rec = _read_json(path)
            except (OSError, ValueError):
                continue
            if not rec.get("obs"):
                continue
            for ep, fr in _note_keys(rec.get("note")):
                if episode_id is None or ep == episode_id:
                    keys.add(f"{ep}-{fr}")
    return sorted(keys, key=lambda k: tuple(int(p) for p in k.split("-")))
