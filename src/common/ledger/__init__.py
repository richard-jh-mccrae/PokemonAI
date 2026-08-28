"""The Ledger: additive feature valuation over observable positions and continuations."""
from importlib import import_module
from typing import TYPE_CHECKING

from .decider import LedgerDecider, LedgerUnavailable
from .decision import LEDGER_VALUE_SCALE, LedgerValueEvaluator
from .configuration import (BehaviorIdentity, ComputeConfiguration, DeckOverlay,
                            ValuationConfiguration)
from .activation import ActivationCompiler, ActivationEnvironment
from .baseline import (AUTHORITATIVE_DECKS, BLUNDER_POLICY, load_baseline,
                       require_baseline, validate_baseline, validate_certification)
from .certification import (WholeBoardCertification, certify_contract,
                            certify_incremental)
from .evaluate import (EvaluationSnapshot, FeatureActivation, FeatureContribution, Valuation,
                       evaluate, evaluate_snapshot)
from .features import (
    ActivationRule, FEATURE_CATALOG, FeatureCatalog, FeatureDisposition, FeatureSpec,
)
from .preview import ContinuationFootprint
from .prizes import PrizeMap, derive_prize_map
from .seam import (LedgerNativeProvider, PreviewState, preview_provider_factory,
                   register_preview_variant)
from .search import GreedyDecisionPolicy, LedgerOnePlySearch, UniformPolicyModel
from .worth import EvaluationModel, OpponentProfile

if TYPE_CHECKING:
    from .readiness import (LedgerReadinessReport, ReadinessFinding,
                            audit_readiness)


_READINESS_EXPORTS = frozenset({
    "LedgerReadinessReport", "ReadinessFinding", "audit_readiness",
})


def __getattr__(name):
    if name in _READINESS_EXPORTS:
        value = getattr(import_module(f"{__name__}.readiness"), name)
        globals()[name] = value
        return value
    raise AttributeError(name)

__all__ = ("AUTHORITATIVE_DECKS", "ActivationCompiler", "ActivationEnvironment", "ActivationRule",
           "BLUNDER_POLICY",
           "BehaviorIdentity", "ComputeConfiguration",
           "ContinuationFootprint", "DeckOverlay",
           "FEATURE_CATALOG",
           "FeatureActivation", "FeatureCatalog", "FeatureContribution",
           "FeatureDisposition", "FeatureSpec",
           "EvaluationModel", "EvaluationSnapshot", "LEDGER_VALUE_SCALE", "LedgerDecider",
           "LedgerNativeProvider",
           "LedgerReadinessReport", "LedgerUnavailable", "LedgerValueEvaluator",
           "GreedyDecisionPolicy", "LedgerOnePlySearch", "UniformPolicyModel",
           "PreviewState", "PrizeMap", "ReadinessFinding", "Valuation",
           "OpponentProfile", "ValuationConfiguration", "WholeBoardCertification",
           "audit_readiness", "certify_contract", "certify_incremental", "derive_prize_map", "evaluate",
           "evaluate_snapshot",
           "load_baseline", "preview_provider_factory", "require_baseline",
           "validate_baseline", "validate_certification",
           "register_preview_variant")
