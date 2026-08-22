"""Strict loader for hand-authored opponent profile inputs."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


_DEFAULT = Path(__file__).resolve().parent / "briefs"
_FIELDS = frozenset({
    "authored", "covers", "key_cards", "label", "pokemon", "slug", "sources",
    "strategies", "traits",
})
_REQUIRED = frozenset({"covers", "key_cards", "pokemon", "slug", "traits"})


@dataclass
class Brief:
    slug: str
    label: str
    covers: list[str]
    traits: dict = field(default_factory=dict)
    pokemon: list[dict] = field(default_factory=list)
    key_cards: list[dict] = field(default_factory=list)


def _brief_from(raw: dict) -> Brief:
    if not isinstance(raw, dict) or _REQUIRED - set(raw) or set(raw) - _FIELDS:
        raise ValueError("opponent Brief does not match its top-level schema")
    slug, covers = raw["slug"], raw["covers"]
    if not isinstance(slug, str) or not slug or not isinstance(covers, list) or not covers:
        raise ValueError("opponent Brief requires a slug and non-empty covers")
    if not all(isinstance(value, str) for value in covers):
        raise ValueError("opponent Brief covers must be strings")
    if not isinstance(raw["traits"], dict):
        raise ValueError("opponent Brief traits must be an object")
    for field in ("pokemon", "key_cards"):
        if not isinstance(raw[field], list) or not all(isinstance(row, dict) for row in raw[field]):
            raise ValueError(f"opponent Brief {field} must be an array of objects")
    if any(set(row) - {"card", "roles"} or set(row) != {"card", "roles"}
           or not isinstance(row["card"], str) or not isinstance(row["roles"], list)
           or not all(isinstance(role, str) for role in row["roles"])
           for row in raw["pokemon"]):
        raise ValueError("opponent Brief Pokemon rows do not match their schema")
    if any(set(row) - {"card", "role", "enables"} or not {"card", "role"} <= set(row)
           or not isinstance(row["card"], str) or not isinstance(row["role"], str)
           for row in raw["key_cards"]):
        raise ValueError("opponent Brief key-card rows do not match their schema")
    return Brief(
        slug=slug, label=str(raw.get("label", slug)), covers=covers,
        traits=raw["traits"], pokemon=raw["pokemon"], key_cards=raw["key_cards"])


def load_briefs(path: str | Path | None = None, *, strict: bool = False) -> list[Brief]:
    directory = Path(path or _DEFAULT)
    if not directory.is_dir():
        if strict:
            raise FileNotFoundError(directory)
        return []
    briefs = []
    for source in sorted(directory.glob("*.json")):
        try:
            brief = _brief_from(json.loads(source.read_text(encoding="utf-8")))
        except Exception:
            if strict:
                raise
            brief = None
        if strict and brief is None:
            raise ValueError(f"invalid opponent Brief {source}")
        if brief is not None:
            briefs.append(brief)
    return briefs


__all__ = ("Brief", "load_briefs")
