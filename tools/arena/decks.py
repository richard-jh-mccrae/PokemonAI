"""The Arena deck funnel: Deck Text -> 60 card ids, or a whole-deck rejection.

Deck Text = the Limitless "Copy as Text" export (tools/arena/CONTEXT.md). Resolution
and legality are ADR-0013's deck_convert, reused verbatim: hard-fail with every
problem listed, never a silently-partial deck.
"""
from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_TOOLS = Path(__file__).resolve().parents[1]
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from deck_convert import check_legality, resolve_deck  # noqa: E402
from meta_tracker.cards import load_cards  # noqa: E402


@dataclass(frozen=True)
class DeckResult:
    """A resolved Deck Text: 60 ids and no problems, or no ids and every problem."""

    ids: tuple[int, ...] = ()
    problems: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.problems


_MAX_LINE_COUNT = 60      # no single card line can exceed a whole deck
_MAX_TOTAL = 400          # generous slack over 60 so the error stays legality-shaped


def _count_guard(text: str) -> str | None:
    """Reject absurd counts BEFORE resolve_deck expands them (hostile-input guard)."""
    total = 0
    for raw in text.splitlines():
        toks = raw.split()
        if not toks or not toks[0].isdigit():
            continue
        if len(toks[0]) > 4:
            return f"count {toks[0][:12]}… is not a real card count"
        n = int(toks[0])
        if n > _MAX_LINE_COUNT:
            return f"{n}x of one card — a deck holds 60 cards total"
        total += n
    if total > _MAX_TOTAL:
        return f"{total} cards listed — a deck is exactly 60"
    return None


def resolve_deck_text(text: str) -> DeckResult:
    """Resolve a pasted/uploaded Deck Text; legality only checked once names resolve."""
    guard = _count_guard(text)
    if guard:
        return DeckResult(problems=(guard,))
    ids, problems = resolve_deck(text)
    if not problems:
        problems = check_legality(ids)
    if problems:
        return DeckResult(problems=tuple(problems))
    return DeckResult(ids=tuple(ids))


# --- builder: the pool catalog + id-list validation ---------------------------

# EnergyType ints as load_cards emits them (matches cg.api.EnergyType).
_ENERGY_NAME = {0: "Colorless", 1: "Grass", 2: "Fire", 3: "Water", 4: "Lightning",
                5: "Psychic", 6: "Fighting", 7: "Darkness", 8: "Metal", 9: "Dragon",
                10: "Rainbow", 11: "Team Rocket"}


@lru_cache(maxsize=1)
def pool_catalog() -> tuple[dict, ...]:
    """Every pool card, shaped for the in-app deck builder (cached once)."""
    out = []
    for cid, c in sorted(load_cards().items()):
        out.append({
            "id": cid,
            "name": c["name"],
            "category": c.get("category"),
            "stage": c.get("stage"),
            "hp": c.get("hp") or 0,
            "energy": c.get("energy"),
            "retreat": c.get("retreat") or 0,
            "ex": bool(c.get("ex")),
            "megaEx": bool(c.get("megaEx")),
            "aceSpec": bool(c.get("aceSpec")),
            "evolvesFrom": c.get("evolvesFrom"),
            "attacks": [{
                "name": a.get("name"),
                "damage": a.get("damage") or 0,
                "cost": [_ENERGY_NAME.get(e, "?") for e in a.get("energies") or ()],
                "text": a.get("text") or "",
            } for a in c.get("attacks") or ()],
            "effect": "\n".join(a.get("text") or "" for a in c.get("abilities") or ()),
        })
    return tuple(out)


def validate_ids(ids) -> DeckResult:
    """Validate a builder-made id list; the server-side authority for deck_ids."""
    ids = [int(i) for i in ids]
    if len(ids) > _MAX_TOTAL:
        return DeckResult(problems=(f"{len(ids)} cards listed — a deck is exactly 60",))
    cards = load_cards()
    unknown = sorted({i for i in ids if i not in cards})
    if unknown:
        return DeckResult(problems=tuple(f"unknown card id {i}" for i in unknown))
    problems = check_legality(ids)
    if problems:
        return DeckResult(problems=tuple(problems))
    return DeckResult(ids=tuple(ids))


def preset_cards(preset_id: str, root: Path | None = None) -> list[dict]:
    """A preset as {id, count} rows — the clone source the builder starts from."""
    res = load_preset(preset_id, root)
    if not res.ok:
        raise KeyError(preset_id)
    return [{"id": cid, "count": n} for cid, n in sorted(Counter(res.ids).items())]


# --- Preset gallery ---------------------------------------------------------

PRESETS_DIR = Path(__file__).resolve().parent / "presets"


@dataclass(frozen=True)
class Preset:
    id: str
    title: str
    path: Path


def list_presets(root: Path | None = None) -> list[Preset]:
    """The gallery: every preset that resolves to a playable deck, alphabetical. A broken preset file
    is excluded, never fatal — a bad drop-in must not take the deck screen down."""
    root = PRESETS_DIR if root is None else Path(root)
    out = []
    for path in sorted(root.glob("*.txt")):
        try:
            ok = resolve_deck_text(path.read_text(encoding="utf-8")).ok
        except (OSError, UnicodeDecodeError, ValueError):
            ok = False                      # a bad drop-in must not take the screen down
        if ok:
            out.append(Preset(id=path.stem, title=path.stem.replace("_", " "), path=path))
    return out


def load_preset(preset_id: str, root: Path | None = None) -> DeckResult:
    """Resolve one preset by id; unknown id is a KeyError (the server's 404)."""
    root = PRESETS_DIR if root is None else Path(root)
    path = root / f"{preset_id}.txt"
    if not path.is_file() or path.parent != root:
        raise KeyError(preset_id)
    try:
        return resolve_deck_text(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return DeckResult(problems=(f"preset {preset_id!r} is unreadable",))
