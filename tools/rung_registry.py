from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fold:
    adr: str
    symbol: str
    note: str


FOLDED = {
    "tools/sim/selfplay.py": Fold(
        "0057", "sim.correction_run:main",
        "Focal review Episodes now use the manifested Correction Run."),
    "tools/sim/corpus.py": Fold(
        "0057", "train.corpus:build_snapshot",
        "Corpus publication now consumes complete Episode Bundles."),
}
