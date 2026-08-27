from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from common.cards import card_clauses, card_store
from common.cards.card_facts import EnergyCard, PokemonCard, TrainerCard

from .coverage import (
    CLAUSE_VALUATION_CONTRACTS, clause_contract_findings, clause_parameter_findings,
    observation_contract_findings,
)
from .features import FEATURE_CATALOG, FeatureDisposition
from .sensitivity import (
    OBSERVATION_SENSITIVITY_WITNESSES, PARAMETER_SENSITIVITY_WITNESSES,
    SENSITIVITY_WITNESSES,
    card_clause_contribution, card_probe_contribution,
    run_observation_sensitivity, run_sensitivity_witness,
    run_clause_sensitivity, run_parameter_sensitivity,
)
from .worth import EvaluationModel


REPORT_SCHEMA_VERSION = 4


@dataclass(frozen=True, slots=True)
class ReadinessFinding:
    category: str
    subject: str
    detail: str

    def as_dict(self):
        return {
            "category": self.category,
            "subject": self.subject,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class LedgerReadinessReport:
    schema_version: int
    feature_dispositions: tuple[tuple[str, int], ...]
    feature_count: int
    clause_count: int
    card_count: int
    sensitivity_count: int
    observation_sensitivity_count: int
    parameter_sensitivity_count: int
    findings: tuple[ReadinessFinding, ...]
    warnings: tuple[ReadinessFinding, ...] = ()

    @property
    def passed(self):
        return not self.findings

    def as_dict(self):
        return {
            "schema_version": self.schema_version,
            "passed": self.passed,
            "counts": {
                "features": self.feature_count,
                "clauses": self.clause_count,
                "cards": self.card_count,
                "sensitivity_witnesses": self.sensitivity_count,
                "observation_sensitivity_witnesses": self.observation_sensitivity_count,
                "parameter_sensitivity_witnesses": self.parameter_sensitivity_count,
            },
            "feature_dispositions": dict(self.feature_dispositions),
            "findings": [finding.as_dict() for finding in self.findings],
            "warnings": [warning.as_dict() for warning in self.warnings],
        }


def audit_readiness(*, catalog=FEATURE_CATALOG,
                    contracts=CLAUSE_VALUATION_CONTRACTS,
                    witnesses=SENSITIVITY_WITNESSES,
                    observation_witnesses=OBSERVATION_SENSITIVITY_WITNESSES,
                    parameter_witnesses=PARAMETER_SENSITIVITY_WITNESSES,
                    cards=None):
    cards = card_store() if cards is None else cards
    findings = []
    warnings = []
    for spec in catalog.specs:
        if spec.disposition is FeatureDisposition.ACTIVE and spec.default == 0.0:
            findings.append(ReadinessFinding(
                "feature.zero_seed", spec.key, "active feature has zero seed"))
        if spec.disposition is FeatureDisposition.AWAITING_SEED:
            findings.append(ReadinessFinding(
                "feature.awaiting_seed", spec.key, "feature still awaits a seed"))

    findings.extend(ReadinessFinding(
        "clause.contract", value.split(":", 1)[-1].strip(), value)
        for value in clause_contract_findings(contracts=contracts))
    findings.extend(ReadinessFinding(
        "clause.parameter_contract", value.split(":", 1)[-1].strip(), value)
        for value in clause_parameter_findings())
    findings.extend(ReadinessFinding(
        "observation.contract", value.split(":", 1)[-1].strip(), value)
        for value in observation_contract_findings())

    active = {spec.key for spec in catalog.priced_specs}
    witnessed = {witness.feature for witness in witnesses.values()}
    for feature in sorted(active - witnessed):
        findings.append(ReadinessFinding(
            "sensitivity.missing", feature, "active feature has no sensitivity witness"))

    ctx = EvaluationModel.build()
    sensitivity_results = {}
    for identity, witness in sorted(witnesses.items()):
        try:
            result = run_sensitivity_witness(witness, ctx)
        except Exception as exc:
            findings.append(ReadinessFinding(
                "sensitivity.error", identity, f"{type(exc).__name__}: {exc}"))
            continue
        sensitivity_results[identity] = result
        if not result.passed:
            findings.append(ReadinessFinding(
                "sensitivity.zero_contribution", identity, result.reason or "failed"))

    for identity, witness in sorted(observation_witnesses.items()):
        try:
            result = run_observation_sensitivity(
                identity, witness.features, ctx,
                expected_nonzero=witness.expected_nonzero)
        except Exception as exc:
            findings.append(ReadinessFinding(
                "observation.sensitivity_error", identity,
                f"{type(exc).__name__}: {exc}"))
            continue
        if not result.passed:
            findings.append(ReadinessFinding(
                "observation.zero_delta", identity,
                f"field expectation failed for {result.features!r}"))

    for identity, witness in sorted(parameter_witnesses.items()):
        try:
            result = run_parameter_sensitivity(witness, ctx)
        except Exception as exc:
            findings.append(ReadinessFinding(
                "parameter.sensitivity_error", identity,
                f"{type(exc).__name__}: {exc}"))
            continue
        if not result.passed:
            findings.append(ReadinessFinding(
                "parameter.zero_delta", identity, result.reason or "failed"))

    for kind, contract in sorted(contracts.items()):
        try:
            result = run_clause_sensitivity(contract, ctx)
        except Exception as exc:
            findings.append(ReadinessFinding(
                "mechanic.probe_error", kind, f"{type(exc).__name__}: {exc}"))
            continue
        if not result.passed or result.contribution_delta == 0.0:
            findings.append(ReadinessFinding(
                "mechanic.no_contribution", kind, result.reason or "contributed zero"))

    for card_id in sorted(cards):
        facts = cards[card_id]
        try:
            contribution = card_probe_contribution(card_id, ctx)
        except Exception as exc:
            findings.append(ReadinessFinding(
                "card.probe_error", str(card_id), f"{type(exc).__name__}: {exc}"))
            continue
        if contribution == 0.0:
            findings.append(ReadinessFinding(
                "card.no_contribution", str(card_id),
                "card produced no nonzero contribution in its reachable zone probe"))
        for kind in sorted({clause.kind for clause in card_clauses(facts)}):
            try:
                contribution = card_clause_contribution(card_id, kind, ctx)
            except Exception as exc:
                findings.append(ReadinessFinding(
                    "card.mechanic_probe_error", f"{card_id}:{kind}",
                    f"{type(exc).__name__}: {exc}"))
                continue
            if contribution == 0.0:
                findings.append(ReadinessFinding(
                    "card.mechanic_no_contribution", f"{card_id}:{kind}",
                    "this card's typed mechanic produced zero under its reachable probe"))
        warnings.extend(_card_coverage_warnings(card_id, facts))

    dispositions = Counter(spec.disposition.value for spec in catalog.specs)
    return LedgerReadinessReport(
        REPORT_SCHEMA_VERSION, tuple(sorted(dispositions.items())),
        len(catalog.specs), len(contracts),
        len(cards), len(witnesses), len(observation_witnesses),
        len(parameter_witnesses),
        tuple(sorted(findings, key=lambda row: (
            row.category, row.subject, row.detail))),
        tuple(sorted(warnings, key=lambda row: (
            row.category, row.subject, row.detail))),
    )


def _card_coverage_warnings(card_id, facts):
    warnings = []
    if getattr(facts, "covers", None) == "partial":
        warnings.append(ReadinessFinding(
            "card.partial_coverage", str(card_id),
            "card is explicitly classified partial; untyped text remains"))
    untyped = []
    if isinstance(facts, TrainerCard) and facts.text.strip() and not facts.clauses:
        untyped.append(facts.name)
    elif isinstance(facts, EnergyCard) and facts.kind == "special_energy" \
            and facts.text.strip() and not facts.clauses:
        untyped.append(facts.name)
    elif isinstance(facts, PokemonCard):
        untyped.extend(
            f"ability {ability.name}" for ability in facts.abilities
            if ability.text.strip() and not ability.clauses)
        untyped.extend(
            f"attack {attack.name}" for attack in facts.attacks
            if attack.text.strip() and not attack.clauses)
    warnings.extend(ReadinessFinding(
        "card.untyped_mechanic", str(card_id),
        f"{label} is explicitly unruled and uses coverage.unknown_card")
        for label in untyped)
    return warnings


__all__ = (
    "LedgerReadinessReport", "ReadinessFinding", "audit_readiness",
)
