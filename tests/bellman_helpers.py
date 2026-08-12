"""Shared constructors for the deployed Bellman runtime."""
from __future__ import annotations

from functools import lru_cache
import importlib.util
from pathlib import Path

from common.runtime import build_runtime


REPO = Path(__file__).resolve().parents[1]


@lru_cache(maxsize=None)
def strategy(name: str):
    path = REPO / "src" / "agents" / name / "strategy.py"
    spec = importlib.util.spec_from_file_location(f"_test_{name}_strategy", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.STRATEGY


@lru_cache(maxsize=None)
def deck(name: str) -> tuple[int, ...]:
    return tuple(int(value) for value in
                 (REPO / "src" / "agents" / name / "deck.csv").read_text().splitlines()
                 if value.strip())


def runtime(name: str = "mega_starmie"):
    return build_runtime(strategy(name), deck(name))
