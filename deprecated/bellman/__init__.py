"""The Bellman search brain and its value stack, as they shipped before ADR-0145/0149.

Re-exports the surface `src/common/__init__.py` used to carry for these modules, so a
teacher-side consumer rewrites `from common import X` to `from deprecated.bellman import X`.
"""

from .activation import (
    ActivatedStrategy,
    GENERAL_STRATEGIES,
    ResolvedStrategies,
    StrategySnapshot,
    activate_strategies,
    general_card_strategies,
    resolve_strategies,
)
from .belief import BellmanDeckProfile, opponent_belief
from .budget_prototype import DecisionClock, FairBudgetPrototype
from .demand import (
    ActionFocus,
    CoverageEdge,
    DemandSlot,
    StrategyBeam,
    DemandModel,
    ResolvedAssignment,
    RetainedAssignment,
    RetainedOption,
    access_probability,
)
from .pilot_profile import DEFAULT_PILOT_PROFILE, DEFINITIONS, PilotProfile
from .planner import BellmanTurnPlanner
from .potential import BoardPotential, UtilityScale
from .providers import BellmanCgpyProvider, BellmanNativeProvider, bellman_provider_factory
from .refresh_evaluator import RefreshEvaluator
from .runtime import BellmanTeacherRuntime, build_teacher_runtime
from .state import DecisionState, OpponentBelief, TurnBudgets
from .solver import (
    ProductionLimits,
    ProductionSolver,
    ReferenceSolver,
    SearchLimits,
    TransitionProvider,
)
from .terminal import ProofStep, TerminalLimits, TerminalProof, TerminalProver
from .value import CardFacts, Potential, ValueOracle, ValueRegistry, WorthSeeds

__all__ = (
    "ActionFocus", "ActivatedStrategy", "BellmanCgpyProvider", "BellmanDeckProfile", "BellmanNativeProvider",
    "BellmanTeacherRuntime", "BellmanTurnPlanner", "BoardPotential", "CardFacts",
    "CoverageEdge", "DEFAULT_PILOT_PROFILE", "DEFINITIONS", "DecisionClock", "DemandModel",
    "DecisionState", "DemandSlot", "FairBudgetPrototype", "GENERAL_STRATEGIES", "OpponentBelief", "PilotProfile", "Potential", "ProductionLimits",
    "ProductionSolver", "ProofStep", "ReferenceSolver", "RefreshEvaluator",
    "ResolvedAssignment", "RetainedAssignment", "RetainedOption", "SearchLimits",
    "ResolvedStrategies", "StrategyBeam", "StrategySnapshot", "TerminalLimits", "TerminalProof", "TerminalProver",
    "TransitionProvider", "TurnBudgets", "UtilityScale", "ValueOracle", "ValueRegistry", "WorthSeeds",
    "access_probability", "activate_strategies", "bellman_provider_factory", "build_teacher_runtime",
    "general_card_strategies", "resolve_strategies",
    "opponent_belief",
)
