from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "src")]

from common.decision import EvaluationStatus
from common.ledger.baseline import AUTHORITATIVE_DECKS, require_baseline
from common.ledger.decision import LEDGER_VALUE_SCALE
from common.ledger.policy import (
    LedgerPolicyCalibration,
    LedgerPolicyConfiguration,
    LedgerPolicyDeckSmoke,
    normalize_ledger_priors,
)


TEMPERATURE_GRID = (0.25, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0)
UNIFORM_MIX_GRID = (0.01, 0.025, 0.05, 0.1, 0.2, 0.35, 0.5)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _selection(value) -> tuple:
    return tuple(value or ())


def _matches(candidate: dict, selections) -> bool:
    actual = {_selection(candidate.get("selection"))}
    actual.update(_selection(value) for value in candidate.get("equivalent_selections", ()))
    return bool(actual.intersection(selections))


def _priors(row: dict, temperature: float, uniform_mix: float) -> tuple[float, ...]:
    candidates = tuple(row.get("candidates") or ())
    if not candidates:
        return ()
    scores = tuple(
        float(candidate["decision_delta"])
        if isinstance(candidate.get("decision_delta"), (int, float)) else None
        for candidate in candidates)
    statuses = tuple(EvaluationStatus(candidate["status"]) for candidate in candidates)
    configuration = LedgerPolicyConfiguration(temperature, uniform_mix)
    return normalize_ledger_priors(scores, statuses, configuration).priors


def _eligible(row: dict) -> bool:
    selections = {_selection(value) for value in row.get("acceptable") or ()}
    return (row.get("graded") is True and len(row.get("candidates") or ()) > 1
            and selections and any(_matches(candidate, selections)
                                   for candidate in row["candidates"]))


def _loss(rows, temperature: float, uniform_mix: float) -> float:
    losses = []
    for row in rows:
        selections = {_selection(value) for value in row["acceptable"]}
        priors = _priors(row, temperature, uniform_mix)
        mass = math.fsum(prior for candidate, prior in zip(row["candidates"], priors)
                         if _matches(candidate, selections))
        losses.append(-math.log(mass))
    return math.fsum(losses) / len(losses)


def _deck_smoke(rows, configuration: LedgerPolicyConfiguration):
    result = []
    for deck in AUTHORITATIVE_DECKS:
        deck_rows = tuple(row for row in rows if row.get("deck") == deck)
        disagreements = []
        losses = []
        for row in deck_rows:
            priors = _priors(row, configuration.temperature, configuration.uniform_mix)
            if not priors or any(not math.isfinite(value) or value <= 0.0 for value in priors) \
                    or not math.isclose(math.fsum(priors), 1.0, abs_tol=1e-12):
                raise ValueError(f"policy smoke failed for {row.get('key')}")
            acceptable = {_selection(value) for value in row["acceptable"]}
            mass = math.fsum(prior for candidate, prior in zip(row["candidates"], priors)
                             if _matches(candidate, acceptable))
            losses.append(-math.log(mass))
            greatest = max(candidate["decision_delta"] for candidate in row["candidates"]
                           if isinstance(candidate.get("decision_delta"), (int, float)))
            top = tuple(candidate for candidate in row["candidates"]
                        if candidate.get("decision_delta") == greatest)
            chosen = {_selection(row.get("chosen"))}
            if not any(_matches(candidate, chosen) for candidate in top):
                disagreements.append(str(row.get("key") or row.get("id")))
        result.append(LedgerPolicyDeckSmoke(
            deck,
            len(deck_rows),
            math.fsum(losses) / len(losses),
            True,
            len(disagreements),
            tuple(disagreements[:5]),
        ))
    return tuple(result)


def calibrate(manifest_path: Path | str) -> LedgerPolicyCalibration:
    manifest_path = Path(manifest_path)
    manifest = require_baseline(manifest_path.parent.name, manifest_path)
    gates = manifest["certification"]["report"]["gates"]
    gate = next((item for item in gates if item["name"] == "historical_corrections"), None)
    if gate is None or gate.get("passed") is not True:
        raise ValueError("frozen historical Correction evidence did not pass")
    source_path = manifest_path.parent / gate["artifact_path"]
    if _sha256(source_path) != gate["artifact_sha256"]:
        raise ValueError("frozen historical Correction evidence hash mismatch")
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    rows = tuple(row for row in payload.get("rows", ()) if _eligible(row))
    if {row.get("deck") for row in rows} != set(AUTHORITATIVE_DECKS):
        raise ValueError("policy calibration lacks an authoritative deck root")
    scores = tuple(
        (_loss(rows, temperature, uniform_mix), temperature, uniform_mix)
        for temperature in TEMPERATURE_GRID for uniform_mix in UNIFORM_MIX_GRID)
    loss, temperature, uniform_mix = min(scores)
    configuration = LedgerPolicyConfiguration(temperature, uniform_mix)
    return LedgerPolicyCalibration(
        manifest["baseline_id"],
        LEDGER_VALUE_SCALE.identity,
        gate["artifact_path"],
        gate["artifact_sha256"],
        "frozen_historical_corrections_tuning",
        "mean_acceptable_action_negative_log_likelihood",
        TEMPERATURE_GRID,
        UNIFORM_MIX_GRID,
        configuration,
        loss,
        len(rows),
        _deck_smoke(rows, configuration),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    artifact = calibrate(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact.as_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
