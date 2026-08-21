"""Pure within-family scheduling records for bounded Bellman search."""
from __future__ import annotations

from dataclasses import dataclass
import math

from common.algebra import Deterministic
from common.card_worth import ENERGY_TIER
from common.options import LegalAction
from .pilot_profile import PilotProfile
from .value_equations import SCORERS


FAMILIES = tuple(SCORERS)


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
    shadow: bool = True

    def diagnostic(self) -> dict:
        return {
            "action": str(self.action.identity), "family": self.family,
            "features": dict(self.features), "contributions": dict(self.contributions),
            "score": self.score, "gap": self.gap, "wave": self.wave, "status": self.status,
            "shadow": self.shadow,
        }


@dataclass(frozen=True)
class FamilyRanking:
    candidates: tuple[FamilyCandidate, ...]
    ordered_actions: tuple[LegalAction, ...]
    first_wave: tuple[LegalAction, ...]


def _singleton(action: LegalAction) -> FamilyCandidate:
    return FamilyCandidate(action, f"unclassified:{action.identity}", (), (), None, None, 0,
                           "singleton", False)


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


def _is_deployment_action(state, action, provider) -> bool:
    if action.identity.kind != "play" or len(action.selection) != 1:
        return False
    stats = getattr(provider, "stats", None)
    if stats is None:
        return False
    options = (state.obs.get("select") or {}).get("option") or ()
    option_index = action.selection[0]
    if not 0 <= option_index < len(options):
        return False
    hand_index = options[option_index].get("index")
    mine, _opponent = _players(state.obs)
    hand = mine.get("hand") or ()
    if not isinstance(hand_index, int) or not 0 <= hand_index < len(hand):
        return False
    stat = stats.get((hand[hand_index] or {}).get("id"))
    return bool(stat is not None and getattr(stat, "is_pokemon", False))


def _players(obs):
    current = obs.get("current") or {}
    players = current.get("players") or ()
    seat = int(current.get("yourIndex", 0))
    mine = players[seat] if 0 <= seat < len(players) and players[seat] else {}
    opponent = players[1 - seat] if 0 <= 1 - seat < len(players) and players[1 - seat] else {}
    return mine, opponent


def _active_marker(player):
    active = next((body for body in (player.get("active") or ()) if body), None)
    if active is None:
        return None
    return active.get("serial", active.get("id"))


def _bench_health(player) -> float:
    return sum(float(body.get("hp", 0.0) or 0.0)
               for body in (player.get("bench") or ()) if body)


def _family(state, action, after, provider) -> str | None:
    if _is_energy_attachment(state, action, provider):
        return "attachment"
    if action.identity.kind == "evolve":
        return "evolution"
    if action.identity.kind == "retreat":
        return "promote_retreat"
    if _is_deployment_action(state, action, provider):
        return "deployment"
    if after is None or not hasattr(after, "obs"):
        return None
    before_mine, before_opponent = _players(state.obs)
    after_mine, after_opponent = _players(after.obs)
    if _active_marker(before_mine) != _active_marker(after_mine):
        return "promote_retreat"
    if len(after_mine.get("bench") or ()) > len(before_mine.get("bench") or ()):
        return "deployment"
    if _bench_health(after_opponent) < _bench_health(before_opponent):
        return "snipe"
    return None


def _attachment_resource_premium(state, action, oracle) -> float:
    registry = getattr(oracle, "registry", None)
    if registry is None or len(action.selection) != 1:
        return 0.0
    options = (state.obs.get("select") or {}).get("option") or ()
    index = action.selection[0]
    if not 0 <= index < len(options):
        return 0.0
    hand_index = options[index].get("index")
    mine, _opponent = _players(state.obs)
    hand = mine.get("hand") or ()
    if not isinstance(hand_index, int) or not 0 <= hand_index < len(hand):
        return 0.0
    card_id = (hand[hand_index] or {}).get("id")
    return max(0.0, float(registry.worth(card_id)) - ENERGY_TIER) if card_id is not None else 0.0


def _candidate(state, action, provider, oracle, profile: PilotProfile) -> FamilyCandidate:
    known_family = ("attachment" if _is_energy_attachment(state, action, provider) else
                    "evolution" if action.identity.kind == "evolve" else
                    "promote_retreat" if action.identity.kind == "retreat" else
                    "deployment" if _is_deployment_action(state, action, provider) else None)
    family = known_family
    if (known_family is None and action.identity.kind not in {"card", "play"}
            and getattr(provider, "stats", None) is not None):
        return _singleton(action)
    try:
        node = provider.transition(state, action)
        if not isinstance(node, Deterministic):
            unresolved = known_family or f"unclassified:{action.identity}"
            return FamilyCandidate(action, unresolved, (), (), None, None, 0, "abstained")
        family = _family(state, action, node.state, provider) or family
        if family is None:
            return _singleton(action)
        if profile.get(f"family.{family}_shadow") < 0.5:
            return FamilyCandidate(action, family, (), (), None, None, 0, "shadow_disabled")
        ledger = oracle.transition_ledger(state, node.state, action.identity)
        kwargs = ({"resource_premium": _attachment_resource_premium(state, action, oracle)}
                  if family == "attachment" else {})
        result = SCORERS[family](ledger, profile, **kwargs)
        if not math.isfinite(result.score):
            raise ValueError("non-finite family score")
        shadow = not any(profile.get(f"family.{family}_{mode}") >= 0.5
                         for mode in ("ordering", "widening"))
        return FamilyCandidate(action, family, result.features, result.contributions,
                               result.score, 0.0, 0, "scored", shadow)
    except (KeyError, TypeError, ValueError, AttributeError):
        if family is None:
            return _singleton(action)
        return FamilyCandidate(action, family, (), (), None, None, 0, "abstained")


def rank_actions(state, actions: tuple[LegalAction, ...], provider, oracle,
                 profile: PilotProfile) -> FamilyRanking:
    raw = [_candidate(state, action, provider, oracle, profile) for action in actions]
    margin = profile.get("family.tie_margin")
    batch_size = max(1, int(profile.get("family.near_tie_batch_size")))
    ranked = []
    for family in FAMILIES:
        scored = [candidate for candidate in raw
                  if candidate.family == family and candidate.score is not None]
        scored.sort(key=lambda candidate: (-float(candidate.score), candidate.action.identity))
        leader = scored[0].score if scored else None
        deferred_index = 0
        for index, candidate in enumerate(scored):
            gap = float(leader) - float(candidate.score)
            if gap <= margin:
                wave = 0 if index == 0 else 1 + ((index - 1) // batch_size)
                status = "leader" if index == 0 else "near_tie"
            else:
                deferred_index += 1
                wave = 2 + ((deferred_index - 1) // batch_size)
                status = "deferred"
            ranked.append(FamilyCandidate(
                candidate.action, family, candidate.features, candidate.contributions,
                candidate.score, gap, wave, status, candidate.shadow))
    untouched = [candidate for candidate in raw if candidate.score is None]
    candidates = tuple(ranked + untouched)
    first = tuple(candidate.action for candidate in candidates
                  if candidate.wave == 0 or candidate.status in {
                      "abstained", "singleton", "shadow_disabled"})
    by_action = {candidate.action: candidate for candidate in candidates}
    queues = {}
    for family in FAMILIES:
        family_actions = [candidate.action for candidate in candidates
                          if candidate.family == family]
        family_actions.sort(key=lambda action: (by_action[action].wave, action.identity))
        queues[family] = iter(family_actions)
    ordered = []
    for action in actions:
        family = by_action[action].family
        ordered.append(next(queues[family]) if family in queues else action)
    ordered = tuple(ordered)
    return FamilyRanking(candidates, ordered, first)


def apply_family_ordering(actions: tuple[LegalAction, ...], ranking: FamilyRanking,
                          profile: PilotProfile) -> tuple[LegalAction, ...]:
    """Apply enabled within-family proposals without moving any family across another."""
    by_action = {candidate.action: candidate for candidate in ranking.candidates}
    enabled = {family for family in FAMILIES
               if profile.get(f"family.{family}_ordering") >= 0.5}
    queues = {family: iter(action for action in ranking.ordered_actions
                           if by_action[action].family == family)
              for family in enabled}
    return tuple(next(queues[by_action[action].family])
                 if by_action[action].family in enabled else action for action in actions)


__all__ = ("FAMILIES", "FamilyCandidate", "FamilyRanking", "apply_family_ordering",
           "rank_actions")
