"""Legal-view inputs handed from the experiment harness to decision algorithms."""
from __future__ import annotations

from dataclasses import dataclass

from common.observation import ObservationState


@dataclass(frozen=True, slots=True)
class PolicyRoot:
    method_identity: str
    snapshot_id: str
    observation: ObservationState


__all__ = ("PolicyRoot",)
