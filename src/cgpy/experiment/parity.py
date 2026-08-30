"""Pinned cgpy parity evidence for experiment deck unions and executed chains."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .snapshot import SnapshotCompatibilityError


_LEDGER = Path(__file__).resolve().parents[3] / "data" / "engine" / "coverage.json"
_STATUSES = frozenset({"verified", "derived", "seeded", "unprobed", "deferred"})


@dataclass(frozen=True, slots=True)
class ExperimentParityManifest:
    coverage_identity: str
    deck_card_ids: tuple[int, ...]
    chains: tuple[tuple[str, str], ...]

    @classmethod
    def capture(cls, decks, *, coverage_path: Path | str = _LEDGER):
        raw = Path(coverage_path).read_bytes()
        try:
            ledger = json.loads(raw.decode("utf-8"))
        except (UnicodeError, ValueError) as exc:
            raise SnapshotCompatibilityError(f"invalid cgpy coverage ledger: {exc}") from exc
        card_ids = tuple(sorted({int(card_id) for deck in decks for card_id in deck}))
        chains = {}
        for card_id in card_ids:
            card = (ledger.get("cards") or {}).get(str(card_id))
            if not isinstance(card, dict) or not isinstance(card.get("chains"), dict):
                raise SnapshotCompatibilityError(
                    f"cgpy coverage missing experiment card {card_id}")
            for chain, status in card["chains"].items():
                if status not in _STATUSES:
                    raise SnapshotCompatibilityError(
                        f"cgpy coverage has unknown status {status!r} for {chain}")
                chains[str(chain)] = str(status)
        return cls(hashlib.sha256(raw).hexdigest(), card_ids, tuple(sorted(chains.items())))

    @property
    def identity(self) -> str:
        payload = json.dumps({
            "coverage": self.coverage_identity,
            "cards": self.deck_card_ids,
            "chains": self.chains,
        }, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def require_verified(self, executed_chains) -> None:
        statuses = dict(self.chains)
        for chain in executed_chains:
            key = str(chain)
            status = statuses.get(key)
            if status is None:
                raise SnapshotCompatibilityError(
                    f"executed cgpy chain {key} is outside the experiment deck union")
            if status != "verified":
                raise SnapshotCompatibilityError(
                    f"executed cgpy chain {key} has parity status {status}")


__all__ = ("ExperimentParityManifest",)
