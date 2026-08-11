import json
from pathlib import Path

from train.bellman_adjudicate import CLASSES, adjudicate


REPO = Path(__file__).resolve().parents[2]


def test_every_unfiltered_mega_starmie_correction_has_one_rationale_led_disposition():
    baseline = json.loads((REPO / "docs" / "plans" /
                           "mega-starmie-live-corpus-baseline.json").read_text(encoding="utf-8"))
    result = adjudicate(baseline)
    assert baseline["excluded"] == result["excluded"] == 0
    assert baseline["records"] == result["records"] == 259
    assert result["unexplained"] == 0
    assert sum(result["counts"].values()) == 259
    assert set(result["counts"]) == CLASSES


def test_adjudication_artifact_is_current():
    baseline = json.loads((REPO / "docs" / "plans" /
                           "mega-starmie-live-corpus-baseline.json").read_text(encoding="utf-8"))
    authored = json.loads((REPO / "docs" / "plans" /
                           "mega-starmie-bellman-adjudication.json").read_text(encoding="utf-8"))
    assert authored == adjudicate(baseline)
