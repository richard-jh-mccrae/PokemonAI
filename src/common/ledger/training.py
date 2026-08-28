from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass

from .configuration import ValuationConfiguration
from .features import FEATURE_CATALOG, FeatureCatalog


BOUND_MULTIPLIER = 4
DEFAULT_EPOCHS = 250
DEFAULT_LEARNING_RATE = 0.04
DEFAULT_L2 = 0.002
GROUP_BUCKETS = 10
TRAIN_BUCKETS = 8
VALIDATION_BUCKETS = 9
FIT_DIGEST_BYTES = 16
CALIBRATION_EPOCHS = 200


@dataclass(frozen=True, slots=True)
class ParameterSpec:
    key: str
    seed: float
    lower: float
    upper: float
    trainable: bool
    source: str = "feature_catalog"


@dataclass(frozen=True, slots=True)
class PairwiseExample:
    group: str
    positive: tuple[tuple[str, float], ...]
    negative: tuple[tuple[str, float], ...]

    @property
    def delta(self) -> dict[str, float]:
        values = dict(self.positive)
        for key, value in self.negative:
            values[key] = values.get(key, 0.0) - value
        return {key: value for key, value in values.items() if value}


def parameter_manifest(catalog: FeatureCatalog = FEATURE_CATALOG) -> tuple[ParameterSpec, ...]:
    fixed = {
        "active.terminal_liability",
        "function.ko.self_prize_liability",
        "prize.race",
        "result.win",
    }
    fixed_prefixes = ("continuation.", "action.")
    rows = []
    for spec in catalog.priced_specs:
        radius = max(1.0, abs(spec.default) * BOUND_MULTIPLIER)
        lower = 0.0 if spec.default > 0 else -radius
        upper = 0.0 if spec.default < 0 else radius
        trainable = spec.key not in fixed and not spec.key.startswith(fixed_prefixes)
        if not trainable:
            lower = upper = spec.default
        rows.append(ParameterSpec(
            spec.key, spec.default, lower, upper, trainable))
    return tuple(rows)


def examples_from_rows(rows) -> tuple[PairwiseExample, ...]:
    examples = []
    for row in rows:
        if not row.get("graded"):
            continue
        acceptable = {tuple(selection) for selection in row.get("acceptable", ())}
        candidates = tuple(row.get("candidates", ()))
        positive = tuple(candidate for candidate in candidates
                         if tuple(candidate.get("selection", ())) in acceptable
                         and candidate.get("status") == "complete")
        negative = tuple(candidate for candidate in candidates
                         if tuple(candidate.get("selection", ())) not in acceptable
                         and candidate.get("status") == "complete")
        group = str(row.get("episode_id") or row.get("key") or row.get("id"))
        for good in positive:
            for bad in negative:
                examples.append(PairwiseExample(
                    group,
                    tuple(sorted((str(key), float(value))
                                 for key, value in good.get("features", {}).items())),
                    tuple(sorted((str(key), float(value))
                                 for key, value in bad.get("features", {}).items())),
                ))
    return tuple(examples)


def split_examples(examples) -> dict[str, tuple[PairwiseExample, ...]]:
    splits = {"train": [], "validation": [], "test": []}
    for example in examples:
        bucket = int.from_bytes(hashlib.blake2b(
            example.group.encode("utf-8"), digest_size=1).digest()) % GROUP_BUCKETS
        name = ("train" if bucket < TRAIN_BUCKETS else
                "validation" if bucket < VALIDATION_BUCKETS else "test")
        splits[name].append(example)
    return {name: tuple(values) for name, values in splits.items()}


def fit_pairwise(examples, *, manifest=None, epochs=DEFAULT_EPOCHS,
                 learning_rate=DEFAULT_LEARNING_RATE, l2=DEFAULT_L2) -> dict[str, float]:
    manifest = parameter_manifest() if manifest is None else tuple(manifest)
    weights = {item.key: item.seed for item in manifest}
    constraints = {item.key: item for item in manifest}
    examples = tuple(examples)
    if not examples:
        return weights
    for _epoch in range(int(epochs)):
        gradient = {item.key: 0.0 for item in manifest if item.trainable}
        for example in examples:
            delta = example.delta
            margin = sum(weights.get(key, 0.0) * value for key, value in delta.items())
            multiplier = -_inverse_one_plus_exp(margin)
            for key, value in delta.items():
                if key in gradient:
                    gradient[key] += multiplier * value
        count = float(len(examples))
        for key in gradient:
            spec = constraints[key]
            regularized = gradient[key] / count + l2 * (weights[key] - spec.seed)
            weights[key] = min(spec.upper, max(
                spec.lower, weights[key] - learning_rate * regularized))
    return weights


def pairwise_metrics(examples, weights) -> dict[str, float | int]:
    examples = tuple(examples)
    margins = [sum(weights.get(key, 0.0) * value
                   for key, value in example.delta.items()) for example in examples]
    return {
        "examples": len(examples),
        "accuracy": (0.0 if not margins else
                     sum(margin > 0 for margin in margins) / len(margins)),
        "log_loss": (0.0 if not margins else
                     sum(_softplus(-margin) for margin in margins) / len(margins)),
    }


def fit_calibration(examples, weights) -> dict[str, float]:
    samples = []
    for example in examples:
        margin = sum(weights.get(key, 0.0) * value for key, value in example.delta.items())
        samples.extend(((margin, 1.0), (-margin, 0.0)))
    slope, intercept = 1.0, 0.0
    if samples:
        for _epoch in range(CALIBRATION_EPOCHS):
            slope_gradient = intercept_gradient = 0.0
            for margin, label in samples:
                error = _sigmoid(slope * margin + intercept) - label
                slope_gradient += error * margin
                intercept_gradient += error
            scale = DEFAULT_LEARNING_RATE / len(samples)
            slope = max(0.0, slope - scale * slope_gradient)
            intercept -= scale * intercept_gradient
    loss = (0.0 if not samples else sum(
        _softplus(-(slope * margin + intercept)) if label else
        _softplus(slope * margin + intercept)
        for margin, label in samples) / len(samples))
    return {"slope": slope, "intercept": intercept, "log_loss": loss}


def build_artifact(rows, weights, splits, metrics, calibration) -> dict:
    seed = ValuationConfiguration.general()
    payload = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "schema_version": 1,
        "catalog_identity": FEATURE_CATALOG.identity,
        "catalog_schema_version": FEATURE_CATALOG.schema_version,
        "seed_configuration_identity": seed.identity,
        "data_identity": hashlib.blake2b(
            payload, digest_size=FIT_DIGEST_BYTES).hexdigest(),
        "parameters": [asdict(item) for item in parameter_manifest()],
        "weights": dict(sorted((str(key), float(value)) for key, value in weights.items())),
        "splits": {name: sorted({example.group for example in examples})
                   for name, examples in splits.items()},
        "metrics": metrics,
        "calibration": calibration,
    }


def _inverse_one_plus_exp(value: float) -> float:
    if value >= 0:
        factor = math.exp(-value)
        return factor / (1.0 + factor)
    return 1.0 / (1.0 + math.exp(value))


def _sigmoid(value: float) -> float:
    return _inverse_one_plus_exp(-value)


def _softplus(value: float) -> float:
    return max(value, 0.0) + math.log1p(math.exp(-abs(value)))


__all__ = ("PairwiseExample", "ParameterSpec", "build_artifact", "examples_from_rows",
           "fit_calibration", "fit_pairwise", "pairwise_metrics", "parameter_manifest",
           "split_examples")
