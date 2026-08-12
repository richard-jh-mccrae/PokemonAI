"""Public boundary for deck-neutral full-turn Bellman search.

The package is intentionally isolated from the legacy strategic selectors.  Neutral game facts may
cross this boundary; legacy scores and chosen actions may not.
"""

from .api import (
    END_VALUE,
    ActionIdentity,
    BellmanPlanner,
    BellmanUnavailable,
    PlanRequest,
    RootDecision,
)
from .algebra import Actor, Chance, Choice, Deterministic, Ledger, RevealChoice, RevealOutcome, Terminal, Unknown
from .options import LegalAction, enumerate_legal_actions
from .state import DecisionState, OpponentBelief, TurnBudgets
from .value import CardFacts, Potential, ValueOracle, ValueRegistry, WorthSeeds
from .solver import ProductionLimits, ProductionSolver, ReferenceSolver, SearchLimits, TransitionProvider
from .engine import CgpyTransitionProvider
from .information import (
    BellmanDeckProfile, DrawClass, OutcomeGroup, RevealSet, hypergeometric_classes,
    opponent_belief, reveal_sets,
)
from .runtime import BellmanTurnPlanner
from .potential import BoardPotential, UtilityScale

__all__ = (
    "END_VALUE",
    "ActionIdentity",
    "BellmanPlanner",
    "BellmanUnavailable",
    "PlanRequest",
    "RootDecision",
    "Actor",
    "Chance",
    "Choice",
    "DecisionState",
    "Deterministic",
    "Ledger",
    "LegalAction",
    "OpponentBelief",
    "RevealChoice",
    "RevealOutcome",
    "Terminal",
    "TurnBudgets",
    "Unknown",
    "enumerate_legal_actions",
    "CardFacts",
    "Potential",
    "ValueOracle",
    "ValueRegistry",
    "WorthSeeds",
    "ReferenceSolver",
    "ProductionLimits",
    "ProductionSolver",
    "SearchLimits",
    "TransitionProvider",
    "CgpyTransitionProvider",
    "BellmanDeckProfile",
    "DrawClass",
    "OutcomeGroup",
    "RevealSet",
    "hypergeometric_classes",
    "opponent_belief",
    "reveal_sets",
    "BellmanTurnPlanner",
    "BoardPotential",
    "UtilityScale",
)
