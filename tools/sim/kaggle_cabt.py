"""Import Kaggle Environment with only the competition's CABT environment registered.

Kaggle Environment 1.30.1 eagerly imports every bundled environment from its package
``__init__``.  The submission checker needs only CABT, so importing unrelated native
extensions (notably OpenSpiel) wastes time and can crash on Windows.
"""
from __future__ import annotations

import contextlib
import importlib
import importlib.util
import os
from pathlib import Path
import sys
import threading


CABT_ENVIRONMENT = "cabt"
_KAGGLE_PACKAGE = "kaggle_environments"
_IMPORT_LOCK = threading.Lock()


@contextlib.contextmanager
def _cabt_only_discovery():
    """Expose only CABT to Kaggle's import-time ``envs`` directory scan."""
    spec = importlib.util.find_spec(_KAGGLE_PACKAGE)
    if spec is None or spec.origin is None:
        raise ModuleNotFoundError(f"No module named '{_KAGGLE_PACKAGE}'")

    envs_path = (Path(spec.origin).resolve().parent / "envs").resolve()
    original_listdir = os.listdir

    def selected_listdir(path):
        try:
            requested = Path(path).resolve()
        except (OSError, TypeError, ValueError):
            return original_listdir(path)
        if requested == envs_path:
            return [CABT_ENVIRONMENT]
        return original_listdir(path)

    os.listdir = selected_listdir
    try:
        yield
    finally:
        os.listdir = original_listdir


def import_cabt_make():
    """Return Kaggle's ``make`` after registering CABT and no unrelated environments."""
    with _IMPORT_LOCK:
        loaded = sys.modules.get(_KAGGLE_PACKAGE)
        if loaded is None:
            with _cabt_only_discovery():
                loaded = importlib.import_module(_KAGGLE_PACKAGE)
        return loaded.make
