"""The shipped meta artifact (docs/scouting.md): recognition priors/likelihoods and per-Archetype
Dossiers, cards by id. Card *stats* are NOT here — they come from the engine at runtime.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT = Path(__file__).resolve().parent / "artifact.json"


@dataclass
class Artifact:
    priors: dict[str, float]                       # band-balanced, recency-weighted
    card_inclusion: dict[str, dict[int, float]]    # archetype -> {cardId: P(card|A)}
    background: dict[int, float]                    # cardId -> P(card present overall)
    dossiers: dict[str, dict] = field(default_factory=dict)
    meta: dict = field(default_factory=dict)        # schema_version, compiled_at, ...


def _empty() -> Artifact:
    return Artifact(priors={}, card_inclusion={}, background={}, dossiers={}, meta={})


def load_artifact(path: str | Path | None = None, *, strict: bool = False) -> Artifact:
    """Re-ints the string card-id keys and lifts `card_inclusion` to the top level. Any error
    degrades to an EMPTY Artifact, so the Scout still runs on observed-only intel."""
    try:
        raw = json.loads(Path(path or _DEFAULT).read_text(encoding="utf-8"))
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
