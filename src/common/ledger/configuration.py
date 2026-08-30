from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from .features import FEATURE_CATALOG, FeatureCatalog
from common.decision import ComputeConfiguration


CONFIGURATION_ID_DIGEST_BYTES = 8
LEGACY_COMBAT_SCHEMA_VERSION = 19
COMBAT_REALIZATION_SCHEMA_VERSION = 20
HAND_LINE_SCHEMA_VERSION = 21
DAMAGED_ACTIVE_THREAT_SCHEMA_VERSION = 22
REALIZED_KO_RETIREMENT_SCHEMA_VERSION = 23
GUST_SPEND_SCHEMA_VERSION = 24
LEGACY_BODY_DEVELOPMENT_WEIGHT = 0.3


def _finite(key, value) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"valuation coefficient {key!r} must be finite, got {value!r}")
    return number


@dataclass(frozen=True, init=False)
class DeckOverlay:
    residuals: tuple[tuple[str, float], ...]

    def __init__(self, residuals: Mapping[str, float] | None = None):
        pairs = _coefficient_pairs(residuals or (), "deck overlay")
        unknown = {key for key, _value in pairs} - set(FEATURE_CATALOG.priced_keys)
        if unknown:
            raise KeyError(f"unknown valuation feature {sorted(unknown)[0]!r}")
        values = tuple(sorted((str(key), _finite(key, value))
                              for key, value in pairs))
        object.__setattr__(self, "residuals", values)

    @classmethod
    def complete(cls, values, catalog: FeatureCatalog = FEATURE_CATALOG):
        pairs = _coefficient_pairs(values, "complete deck overlay")
        keys = {key for key, _value in pairs}
        expected = set(catalog.priced_keys)
        if keys != expected:
            missing = sorted(expected - keys)
            unknown = sorted(keys - expected)
            detail = f"missing {missing[0]!r}" if missing else f"unknown {unknown[0]!r}"
            raise ValueError(f"complete deck overlay must cover exact catalog: {detail}")
        general = ValuationConfiguration.general(catalog)
        return cls({key: _finite(key, value) - general[key] for key, value in pairs})


@dataclass(frozen=True, init=False)
class ValuationConfiguration(Mapping[str, float]):
    schema_version: int
    values: tuple[tuple[str, float], ...]
    _lookup: Mapping[str, float] = field(repr=False, compare=False)
    _identity: str = field(repr=False, compare=False)

    def __init__(self, values: Mapping[str, float], *, schema_version: int):
        version = int(schema_version)
        if version != FEATURE_CATALOG.schema_version:
            raise ValueError("valuation schema version does not match feature catalog")
        pairs = _coefficient_pairs(values, "valuation configuration")
        keys = {key for key, _value in pairs}
        expected = set(FEATURE_CATALOG.priced_keys)
        if keys != expected:
            missing = sorted(expected - keys)
            unknown = sorted(keys - expected)
            detail = f"missing {missing[0]!r}" if missing else f"unknown {unknown[0]!r}"
            raise ValueError(f"valuation configuration must cover exact catalog: {detail}")
        object.__setattr__(self, "schema_version", version)
        normalized = tuple(sorted(
            (str(key), _finite(key, value)) for key, value in pairs))
        object.__setattr__(self, "values", normalized)
        object.__setattr__(self, "_lookup", MappingProxyType(dict(normalized)))
        payload = {"schema_version": version, "values": normalized}
        blob = json.dumps(payload, sort_keys=True).encode("utf-8")
        object.__setattr__(self, "_identity", hashlib.blake2b(
            blob, digest_size=CONFIGURATION_ID_DIGEST_BYTES).hexdigest())

    @classmethod
    def general(cls, catalog: FeatureCatalog = FEATURE_CATALOG):
        return cls({key: catalog[key].default for key in catalog.priced_keys},
                   schema_version=catalog.schema_version)

    @classmethod
    def from_recorded(cls, values, *, schema_version: int,
                      catalog: FeatureCatalog = FEATURE_CATALOG):
        if int(schema_version) == catalog.schema_version:
            return cls(values, schema_version=schema_version)
        version = int(schema_version)
        if (version not in {LEGACY_COMBAT_SCHEMA_VERSION,
                            COMBAT_REALIZATION_SCHEMA_VERSION,
                            HAND_LINE_SCHEMA_VERSION,
                            DAMAGED_ACTIVE_THREAT_SCHEMA_VERSION,
                            REALIZED_KO_RETIREMENT_SCHEMA_VERSION}
                or catalog.schema_version != GUST_SPEND_SCHEMA_VERSION):
            raise ValueError("unsupported recorded valuation schema version")
        migrated = dict(_coefficient_pairs(values, "recorded valuation configuration"))
        if version == LEGACY_COMBAT_SCHEMA_VERSION:
            realization = migrated.pop("combat.prize_phase_fit", 1.0)
            for key in (
                    "combat.attack_now", "combat.attack_progress", "combat.attack_future",
                    "combat.bench_reach", "combat.active_threat", "combat.line_potential"):
                migrated.pop(key, None)
            migrated["body.development"] = migrated.pop(
                "bench.developed_body", LEGACY_BODY_DEVELOPMENT_WEIGHT)
            migrated["combat.realization"] = realization
        if version < HAND_LINE_SCHEMA_VERSION:
            migrated["development.feasible_hand_link"] = catalog[
                "development.feasible_hand_link"].default
            migrated["development.basic_hand_link"] = catalog[
                "development.basic_hand_link"].default
            migrated["development.reserve_hand_link"] = catalog[
                "development.reserve_hand_link"].default
        if version < DAMAGED_ACTIVE_THREAT_SCHEMA_VERSION:
            migrated["context.damaged_active_threat"] = catalog[
                "context.damaged_active_threat"].default
        migrated.pop("combat.realized_ko", None)
        if version < GUST_SPEND_SCHEMA_VERSION:
            migrated["action.gust_spend"] = catalog["action.gust_spend"].default
        return cls(migrated, schema_version=catalog.schema_version)

    def resolve(self, overlay: DeckOverlay,
                catalog: FeatureCatalog = FEATURE_CATALOG) -> "ValuationConfiguration":
        if self.schema_version != catalog.schema_version:
            raise ValueError("valuation schema version does not match feature catalog")
        values = dict(self.values)
        if set(values) != set(catalog.priced_keys):
            raise ValueError("valuation configuration must cover the exact priced catalog")
        for key, residual in overlay.residuals:
            if key not in catalog:
                raise KeyError(f"unknown valuation feature {key!r}")
            values[key] += residual
        return type(self)(values, schema_version=self.schema_version)

    def with_values(self, replacements: Mapping[str, float],
                    catalog: FeatureCatalog = FEATURE_CATALOG) -> "ValuationConfiguration":
        unknown = set(replacements) - set(catalog.priced_keys)
        if unknown:
            raise KeyError(f"unknown valuation feature {sorted(unknown)[0]!r}")
        values = dict(self.values)
        values.update((str(key), _finite(key, value)) for key, value in replacements.items())
        return type(self)(values, schema_version=self.schema_version).resolve(DeckOverlay(), catalog)

    def __getitem__(self, key: str) -> float:
        try:
            return self._lookup[str(key)]
        except KeyError:
            raise KeyError(f"unknown valuation feature {key!r}") from None

    def __iter__(self) -> Iterator[str]:
        return iter(key for key, _ in self.values)

    def __len__(self) -> int:
        return len(self.values)

    @property
    def identity(self) -> str:
        return self._identity


@dataclass(frozen=True, slots=True)
class BehaviorIdentity:
    evaluator: str
    evaluation_model: str
    search: str
    policy_model: str
    decision_policy: str
    fail_safe_policy: str
    provider: str
    compute: str
    prize_plan: str


def _coefficient_pairs(values, label: str) -> list[tuple[str, float]]:
    pairs = list(values.items() if isinstance(values, Mapping) else values)
    normalized = [(str(key), value) for key, value in pairs]
    keys = [key for key, _value in normalized]
    duplicate = next((key for index, key in enumerate(keys) if key in keys[:index]), None)
    if duplicate is not None:
        raise ValueError(f"{label} contains duplicate feature {duplicate!r}")
    return normalized


__all__ = ("BehaviorIdentity", "ComputeConfiguration", "DeckOverlay",
           "ValuationConfiguration")
