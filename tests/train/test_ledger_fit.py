from __future__ import annotations

from common.ledger import FEATURE_CATALOG, ValuationConfiguration
from common.ledger.training import (examples_from_rows, fit_calibration, fit_pairwise,
                                    pairwise_metrics, parameter_manifest, split_examples)
from train.ledger_fit import fit_rows


def rows():
    return [{
        "episode_id": "match-a",
        "id": "frame-a",
        "acceptable": [[0]],
        "candidates": [
            {"selection": [0], "status": "complete",
             "features": {"zone.in_hand": 2.0}},
            {"selection": [1], "status": "complete",
             "features": {"zone.in_hand": -1.0}},
        ],
    }]


def test_parameter_manifest_seeds_every_catalog_feature_with_constraints():
    manifest = parameter_manifest()

    assert tuple(item.key for item in manifest) == FEATURE_CATALOG.priced_keys
    assert {item.key: item.seed for item in manifest} == dict(
        ValuationConfiguration.general().values)
    assert all(item.lower <= item.seed <= item.upper for item in manifest)
    assert next(item for item in manifest if item.key == "result.win").trainable is False
    assert all(not item.trainable for item in manifest
               if item.key.startswith(("continuation.", "action.")))


def test_match_group_split_never_leaks_frames_across_partitions():
    examples = examples_from_rows(rows() + [{**rows()[0], "id": "frame-b"}])
    splits = split_examples(examples)

    locations = [name for name, values in splits.items()
                 if any(example.group == "match-a" for example in values)]
    assert len(locations) == 1


def test_constrained_pairwise_fit_moves_a_zero_seed_and_improves_loss():
    examples = examples_from_rows(rows())
    seed = dict(ValuationConfiguration.general().values)
    before = pairwise_metrics(examples, seed)
    weights = fit_pairwise(examples)
    after = pairwise_metrics(examples, weights)

    assert weights["zone.in_hand"] > 0.0
    assert after["log_loss"] < before["log_loss"]
    assert weights["context.damaged_attached"] <= 0.0
    assert fit_calibration(examples, weights)["slope"] >= 0.0


def test_fit_artifact_is_reproducible_and_self_identifying():
    first = fit_rows(rows())
    second = fit_rows(rows())

    assert first == second
    assert first["catalog_identity"] == FEATURE_CATALOG.identity
    assert first["data_identity"]
    assert set(first["metrics"]) == {"train", "validation", "test"}
