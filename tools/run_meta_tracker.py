"""Entry point for the Windows Scheduled Task.

Keeps ``meta_tracker`` importable without installing it. Run:
    python tools/run_meta_tracker.py [--bands Elite High] [--cap 500]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # make `meta_tracker` importable

from meta_tracker.run_daily import main  # noqa: E402

if __name__ == "__main__":
    main()
