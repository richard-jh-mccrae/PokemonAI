from pathlib import Path
import json
import subprocess
import sys

from common.ledger.features import FeatureCatalog, FeatureDisposition, FeatureSpec
from common.ledger.readiness import audit_readiness


ROOT = Path(__file__).resolve().parents[2]


def test_readiness_audit_passes_and_is_deterministic():
    first = audit_readiness()
    second = audit_readiness()

    assert first.passed
    assert first.as_dict() == second.as_dict()


def test_readiness_audit_reports_zero_awaiting_and_missing_witnesses():
    catalog = FeatureCatalog((
        FeatureSpec("active.zero", 0.0),
        FeatureSpec("classified.alias", 0.0, disposition=FeatureDisposition.ALIAS,
                    replacement="active.zero"),
        FeatureSpec("classified.legal", 0.0,
                    disposition=FeatureDisposition.LEGALITY_ONLY),
        FeatureSpec("classified.conditional", 0.0,
                    disposition=FeatureDisposition.CONDITIONAL),
        FeatureSpec("classified.retired", 0.0,
                    disposition=FeatureDisposition.RETIRED),
        FeatureSpec("classified.awaiting", 0.0,
                    disposition=FeatureDisposition.AWAITING_SEED),
    ), schema_version=99)

    report = audit_readiness(
        catalog=catalog, contracts={}, witnesses={}, cards={})
    categories = {finding.category for finding in report.findings}

    assert "feature.zero_seed" in categories
    assert "feature.awaiting_seed" in categories
    assert "sensitivity.missing" in categories
    assert dict(report.feature_dispositions) == {
        "active": 1, "alias": 1, "awaiting-seed": 1,
        "conditional": 1, "legality-only": 1, "retired": 1,
    }


def test_readiness_cli_is_a_machine_readable_gate():
    completed = subprocess.run(
        [sys.executable, "tools/train/ledger_readiness.py", "--json"],
        cwd=ROOT, check=True, capture_output=True, text=True)
    payload = json.loads(completed.stdout)

    assert payload["passed"] is True
    assert payload["findings"] == []
    assert payload["warnings"]


def test_deployed_deck_cli_treats_every_warning_as_an_error():
    completed = subprocess.run(
        [sys.executable, "tools/train/ledger_readiness.py", "--json",
         "--warnings-as-errors", "--decks", "mega_starmie", "mega_lucario",
         "dragapult_ex"],
        cwd=ROOT, check=True, capture_output=True, text=True)
    payload = json.loads(completed.stdout)

    assert payload["passed"] is True
    assert payload["warnings"] == []
