"""Entry point for the meta-tracker deck export (ADR-0027).

Keeps ``meta_tracker`` importable without installing it. Reads the existing
meta.db (no scrape) and writes data/meta/decks/<slug>/ + index.json. Run:
    python tools/export_meta_decks.py [--top N] [--out DIR] [--db PATH]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # make `meta_tracker` importable

from meta_tracker.export_decks import main  # noqa: E402

if __name__ == "__main__":
    main()
