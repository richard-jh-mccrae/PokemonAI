from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ValuedCandidate:
    action: object
    delta: object | None
    disposition: object
    status: object
    successors: tuple[object, ...] = ()
    gaps: tuple[str, ...] = ()
    continuation: object | None = None
    search_value: object | None = None
    prior: float | None = None
    policy_tie_break: tuple[object, ...] = ()
    policy_evidence: object | None = None
    puct: object | None = None


@dataclass(frozen=True, slots=True)
class CandidateRoster:
    candidates: tuple[ValuedCandidate, ...]
    forced: bool = False


__all__ = ("CandidateRoster", "ValuedCandidate")
