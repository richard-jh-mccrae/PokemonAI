from __future__ import annotations

from dataclasses import dataclass

from .coverage import unowned_clause_kinds, unowned_observation_fields
from .evaluate import evaluate_snapshot
from .features import FEATURE_CATALOG
from .training import parameter_manifest


@dataclass(frozen=True, slots=True)
class WholeBoardCertification:
    observation_coverage: bool
    clause_coverage: bool
    role_free: bool
    parameter_coverage: bool
    incremental_parity: bool | None = None

    @property
    def passed(self) -> bool:
        checks = (self.observation_coverage, self.clause_coverage, self.role_free,
                  self.parameter_coverage)
        return all(checks) and self.incremental_parity is not False


def certify_contract() -> WholeBoardCertification:
    return WholeBoardCertification(
        not unowned_observation_fields(),
        not unowned_clause_kinds(),
        not any(key.startswith("role.") for key in FEATURE_CATALOG.priced_keys),
        tuple(item.key for item in parameter_manifest()) == FEATURE_CATALOG.priced_keys,
    )


def certify_incremental(parent, child, delta, ctx) -> WholeBoardCertification:
    root = evaluate_snapshot(parent, ctx)
    incremental = evaluate_snapshot(child, ctx, parent=root, delta=delta).valuation
    full = evaluate_snapshot(child, ctx).valuation
    contract = certify_contract()
    return WholeBoardCertification(
        contract.observation_coverage, contract.clause_coverage, contract.role_free,
        contract.parameter_coverage,
        incremental == full,
    )


__all__ = ("WholeBoardCertification", "certify_contract", "certify_incremental")
