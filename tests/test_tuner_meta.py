"""tuned.meta.json: the provenance sidecar for the Tuner's weights (ADR-0019)."""
import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from train.tuner.io import corrections_hash, write_meta


@pytest.mark.req("REQ-SUB-0008")
def test_write_meta_stamps_count_and_stable_corrections_hash(tmp_path):
    corrs = [SimpleNamespace(id="b"), SimpleNamespace(id="a"), SimpleNamespace(id="c")]
    path = write_meta(tmp_path / "tuned.meta.json", corrections=corrs,
                      when=datetime(2026, 6, 25, 14, 30, 5))

    meta = json.loads(path.read_text(encoding="utf-8"))
    assert meta["corrections_count"] == 3
    assert meta["tuned_at"].startswith("2026-06-25")
    assert len(meta["corrections_hash"]) == 12
    # the hash is order-independent (corrections sorted by id) so the same set always agrees
    assert meta["corrections_hash"] == corrections_hash([SimpleNamespace(id=i) for i in "cab"])
