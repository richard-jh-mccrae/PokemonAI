"""Pure within-family scheduling records for bounded Bellman search."""
from __future__ import annotations

from dataclasses import dataclass
import math

from .algebra import Deterministic
from .options import LegalAction
from .pilot_profile import PilotProfile


ATTACK_AXIS_FAMILIES = frozenset({
    "board", "development", "energy_position", "multi_target_ko", "readiness",
})


@dataclass(frozen=True)
class FamilyCandidate:
    action: LegalAction
    family: str
    features: tuple[tuple[str, float], ...]
    contributions: tuple[tuple[str, float], ...]
    score: float | None
    gap: float | None
    wave: int
    status: str

    def diagnostic(self) -> dict:
        return {
            "action": str(self.action.identity), "family": self.family,
            "features": dict(self.features), "contributions": dict(self.contributions),
            "score": self.score, "gap": self.gap, "wave": self.wave, "status": self.status,
        }


@dataclass(frozen=True)
class FamilyRanking:
    candidates: tuple[FamilyCandidate, ...]
    ordered_actions: tuple[LegalAction, ...]
    first_wave: tuple[LegalAction, ...]


def _singleton(action: LegalAction) -> FamilyCandidate:
    return FamilyCandidate(action, f"unclassified:{action.identity}", (), (), None, None, 0,
                           "singleton")


def _is_energy_attachment(state, action, provider) -> bool:
    if action.identity.kind != "attach" or len(action.selection) != 1:
        return False
    stats = getattr(provider, "stats", None)
    if stats is None:
        return True
    options = (state.obs.get("select") or {}).get("option") or ()
    option_index = action.selection[0]
    if not 0 <= option_index < len(options):
        return False
    option = options[option_index]
    hand_index = option.get("index")
    current = state.obs.get("current") or {}
    seat = int(current.get("yourIndex", 0))
    players = current.get("players") or ()
    hand = (players[seat].get("hand") or ()) if 0 <= seat < len(players) else ()
    if not isinstance(hand_index, int) or not 0 <= hand_index < len(hand):
        return False
    stat = stats.get(hand[hand_index].get("id"))
    return bool(stat is not None and getattr(stat, "is_energy", False))


def _attachment_score(state, action, provider, oracle, profile: PilotProfile) -> FamilyCandidate:
    try:
        node = provider.transition(state, action)
        if not isinstance(node, Deterministic):
            return FamilyCandidate(action, "attachment", (), (), None, None, 0, "abstained")
        ledger = oracle.transition_ledger(state, node.state, action.identity)
        benefits = dict(ledger.benefits)
        attack_axis = max((benefits.get(name, 0.0) for name in ATTACK_AXIS_FAMILIES),
                          default=0.0)
        other = sum(value for name, value in ledger.benefits
                    if name not in ATTACK_AXIS_FAMILIES)
        costs = sum(value for _name, value in ledger.costs)
        scale = profile.get("attachment.value_scale")
        features = (("attack_axis", attack_axis), ("other_benefits", other), ("costs", costs))
        contributions = (("attack_axis", attack_axis * scale),
                         ("other_benefits", other * scale), ("costs", -costs * scale))
        score = sum(value for _name, value in contributions)
        if not math.isfinite(score):
            raise ValueError("non-finite attachment score")
        return FamilyCandidate(action, "attachment", features, contributions, score, 0.0, 0,
                               "scored")
    except (KeyError, TypeError, ValueError, AttributeError):
        return FamilyCandidate(action, "attachment", (), (), None, None, 0, "abstained")


def rank_actions(state, actions: tuple[LegalAction, ...], provider, oracle,
                 profile: PilotProfile) -> FamilyRanking:
    energy_actions = {action for action in actions
                      if _is_energy_attachment(state, action, provider)}
    attachment = [_attachment_score(state, action, provider, oracle, profile)
                  for action in actions if action in energy_actions]
    singletons = [_singleton(action) for action in actions if action not in energy_actions]
    scored = [candidate for candidate in attachment if candidate.score is not None]
    scored.sort(key=lambda candidate: (-float(candidate.score), candidate.action.identity))
    leader = scored[0].score if scored else None
    margin = profile.get("family.tie_margin")
    batch_size = max(1, int(profile.get("family.near_tie_batch_size")))
    ranked_attachment = []
    deferred_index = 0
    for candidate in scored:
        gap = float(leader) - float(candidate.score)
        if gap <= margin:
            wave = 0 if not ranked_attachment else 1 + ((len(ranked_attachment) - 1) // batch_size)
            status = "leader" if not ranked_attachment else "near_tie"
        else:
            deferred_index += 1
            wave = 2 + ((deferred_index - 1) // batch_size)
            status = "deferred"
        ranked_attachment.append(FamilyCandidate(
            candidate.action, candidate.family, candidate.features, candidate.contributions,
            candidate.score, gap, wave, status))
    abstained = [candidate for candidate in attachment if candidate.score is None]
    candidates = tuple(ranked_attachment + abstained + singletons)
    first = tuple(candidate.action for candidate in candidates
                  if candidate.wave == 0 or candidate.status in {"abstained", "singleton"})
    ordered = tuple(candidate.action for candidate in sorted(
        candidates, key=lambda row: (row.wave, row.action.identity)))
    return FamilyRanking(candidates, ordered, first)


__all__ = ("FamilyCandidate", "FamilyRanking", "rank_actions")
