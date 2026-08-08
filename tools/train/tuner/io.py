"""Read/write the per-deck ``tuned.json`` — the machine weight overrides the Pilot merges by id.

A plain ``{hyp_id: weight}`` map (the shape ``Pilot(overrides=...)`` expects). Lives at
``src/agents/<deck>/tuned.json``. Weights are rounded for legibility.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from train.blunder.reviewed import review_key        # scope-aware ledger/report id (ADR-0049)
from train.tuner.propose import believed_archetype   # posture belief off a Correction (ADR-0041)


def authored_seeds(general_strategy, strategy) -> dict:
    """The authored-EFFECTIVE baseline (ADR-0035) the fit starts from and `sparse_overrides` diffs
    against, so `tuned.json` holds exactly the learned deltas."""
    seeds = {h.id: h.weight for h in (*general_strategy.hypotheses, *strategy.hypotheses)}
    seeds.update(strategy.weight_overrides)
    return seeds


def sparse_overrides(weights: dict, seeds: dict) -> dict:
    """Differences only, so the file is not a full snapshot that no-ops against the defaults. A key
    absent from ``seeds`` is DROPPED — ``Pilot._weight`` would ignore it anyway."""
    return {k: round(float(v), 2) for k, v in weights.items()
            if round(float(v), 2) != round(float(seeds.get(k, v)), 2)}


def write_overrides(weights: dict, path: Path | str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    clean = {k: round(float(v), 2) for k, v in sorted(weights.items())}
    path.write_text(json.dumps(clean, indent=2), encoding="utf-8")
    return path


def corrections_hash(corrections) -> str:
    """Sorted by id, so two builds are comparable regardless of log order."""
    ids = sorted(c.id for c in corrections)
    return hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()[:12]


def write_meta(path: Path | str, *, corrections, when) -> Path:
    """A provenance SIDECAR (ADR-0019), so `tuned.json` stays a pure `{id: weight}` map and the
    runtime `overrides` contract is untouched."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {
        "tuned_at": when.isoformat(timespec="seconds"),
        "corrections_count": len(corrections),
        "corrections_hash": corrections_hash(corrections),
    }
    path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return path


def load_overrides(path: Path | str) -> dict:
    path = Path(path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_proposals(path: Path | str, deck: str, proposals, skipped, *, generated_at: str,
                    reviewed=None) -> Path:
    """The durable proposals snapshot (ADR-0018), overwritten each run. ``reviewed`` entries are
    recorded rather than dropped, so the snapshot shows WHY a blunder is not in ``open``."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    def _live(c, key):  # a layer verdict on the correction's live trace (ADR-0030/0031)
        return (c.live_trace or {}).get(key) is not None

    data = {
        "deck": deck,
        "generated_at": generated_at,
        "open": [
            {"id": p.id, "key": p.key, "scope": p.scope, "subject": p.subject, "seat": p.seat,
             "span_len": p.span_len, "attribution": p.attribution,
             "category": p.category, "episode_id": p.episode_id, "frame": p.frame,
             "seed_weight": p.seed_weight, "trigger_sketch": p.trigger_sketch,
             "rationale": p.rationale, "agent_build": p.agent_build, "built_at": p.built_at,
             "critical": p.critical, "planner_committed": p.planner_committed,
             "lethal_locked": p.lethal_locked, "posture_mismatch": p.posture_mismatch,
             "believed_archetype": p.believed_archetype}
            for p in proposals
        ],
        "skipped": [
            {"key": review_key(c), "scope": c.scope, "subject": c.subject,
             "episode_id": c.episode_id, "frame": c.decision.get("frame"), "reason": reason,
             "critical": c.is_critical, "planner_committed": _live(c, "planned"),
             "lethal_locked": _live(c, "lethal"),
             "posture_mismatch": bool(getattr(c, "posture_mismatch", False)),
             "believed_archetype": believed_archetype(c)}
            for c, reason in skipped
        ],
        "reviewed": [
            {"key": review_key(c), "scope": c.scope, "episode_id": c.episode_id,
             "frame": c.decision.get("frame"),
             "disposition": (entry or {}).get("disposition"), "reason": (entry or {}).get("reason")}
            for c, entry in (reviewed or [])
        ],
    }
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
