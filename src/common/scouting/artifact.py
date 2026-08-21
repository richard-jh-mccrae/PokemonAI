"""The shipped meta artifact (docs/scouting.md): recognition priors/likelihoods and per-Archetype
Dossiers, cards by id. Card *stats* are NOT here — they come from the engine at runtime.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parent / "artifact.json"
_TOP_FIELDS = frozenset({"meta", "priors", "background", "dossiers"})
_DOSSIER_FIELDS = frozenset({
    "card_inclusion", "evolution_lines", "matchups", "representative_build",
    "signatures", "targets", "threats", "win_n", "win_rate",
})


@dataclass
class Artifact:
    priors: dict[str, float]                       # band-balanced, recency-weighted
    card_inclusion: dict[str, dict[int, float]]    # archetype -> {cardId: P(card|A)}
    background: dict[int, float]                    # cardId -> P(card present overall)
    dossiers: dict[str, dict] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)        # schema_version, compiled_at, ...


def _empty() -> Artifact:
    return Artifact(priors={}, card_inclusion={}, background={}, dossiers={}, meta={})


def _validate(raw):
    if not isinstance(raw, dict) or set(raw) != _TOP_FIELDS:
        raise ValueError("opponent artifact does not match its top-level schema")
    if not all(isinstance(raw[field], dict) for field in _TOP_FIELDS):
        raise ValueError("opponent artifact fields must be objects")
    if raw["meta"].get("schema_version") != 2:
        raise ValueError("unsupported opponent artifact schema")
    for dossier in raw["dossiers"].values():
        if not isinstance(dossier, dict) or set(dossier) != _DOSSIER_FIELDS:
            raise ValueError("opponent artifact dossier does not match its schema")
        if not isinstance(dossier["card_inclusion"], dict):
            raise ValueError("opponent artifact card inclusion must be an object")
        if not all(isinstance(dossier[field], list) for field in (
                "evolution_lines", "representative_build", "signatures", "targets", "threats")):
            raise ValueError("opponent artifact dossier arrays are invalid")
        if not isinstance(dossier["matchups"], dict):
            raise ValueError("opponent artifact matchups must be an object")
        if any(not isinstance(row, dict) or set(row) != {"cardId", "lift"}
               or not isinstance(row["cardId"], int)
               or not isinstance(row["lift"], (int, float))
               for row in dossier["signatures"]):
            raise ValueError("opponent artifact signatures are invalid")
        for field in ("targets", "threats"):
            if any(not isinstance(row, dict) or set(row) != {"cardId", "role"}
                   or not isinstance(row["cardId"], int)
                   or not isinstance(row["role"], str) for row in dossier[field]):
                raise ValueError(f"opponent artifact {field} rows are invalid")
        if (not all(isinstance(card_id, int) for card_id in dossier["representative_build"])
                or not all(isinstance(line, list)
                           and all(isinstance(card_id, int) for card_id in line)
                           for line in dossier["evolution_lines"])):
            raise ValueError("opponent artifact deck lists are invalid")
        if any(not isinstance(row, dict) or set(row) != {"win_rate", "n"}
               or not all(isinstance(row[key], (int, float)) for key in row)
               for row in dossier["matchups"].values()):
            raise ValueError("opponent artifact matchup rows are invalid")


def load_artifact(path: str | Path | None = None, *, strict: bool = False) -> Artifact:
    """Re-ints the string card-id keys and lifts `card_inclusion` to the top level. Any error
    degrades to an EMPTY Artifact, so the Scout still runs on observed-only intel."""
    try:
        raw = json.loads(Path(path or _DEFAULT).read_text(encoding="utf-8"))
        _validate(raw)
        priors = {a: float(p) for a, p in (raw.get("priors") or {}).items()}
        background = {int(c): float(p) for c, p in (raw.get("background") or {}).items()}
        card_inclusion: dict[str, dict[int, float]] = {}
        dossiers: dict[str, dict] = {}
        for arch, d in (raw.get("dossiers") or {}).items():
            ci = {int(c): float(p) for c, p in (d.get("card_inclusion") or {}).items()}
            card_inclusion[arch] = ci
            dossiers[arch] = {
                "card_inclusion": ci,
                "signatures": d.get("signatures") or [],
                "representative_build": [int(c) for c in (d.get("representative_build") or [])],
                "evolution_lines": [[int(c) for c in ln] for ln in (d.get("evolution_lines") or [])],
                "threats": d.get("threats") or [],
                "targets": d.get("targets") or [],
                "win_rate": float(d.get("win_rate", 0.5)),       # marginal, vs the field
                "win_n": float(d.get("win_n", 0.0)),             # weighted decisive games
                "matchups": {opp: {"win_rate": float(v.get("win_rate", 0.5)),
                                   "n": float(v.get("n", 0.0))}
                             for opp, v in (d.get("matchups") or {}).items()},
            }
        return Artifact(priors=priors, card_inclusion=card_inclusion, background=background,
                        dossiers=dossiers, meta=raw.get("meta") or {})
    except Exception:
        if strict:
            raise
        return _empty()
