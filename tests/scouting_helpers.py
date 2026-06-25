"""Lib-free builders for Scouting tests.

`make_obs` builds the raw observation *dict* the engine hands the agent (the same
shape `to_observation_class` consumes), so Scout tests never import `cg` and never
load the native lib. `tiny_artifact` is a minimal in-memory recognition artifact.
"""
from __future__ import annotations

from common.scouting.artifact import Artifact

SOLROCK, RIOLU, MEGA_LUCARIO = 676, 677, 678
KIRLIA, GARDEVOIR = 100, 101
SHARED = 200  # appears in both archetypes — ambiguous on its own


def _poke(cid: int) -> dict:
    return {"id": cid, "serial": 0, "playerIndex": 0,
            "energies": [], "energyCards": [], "tools": [], "preEvolution": []}


def _card(cid: int) -> dict:
    return {"id": cid, "serial": 0, "playerIndex": 0}


def _player(active=None, bench=(), discard=()) -> dict:
    return {
        "active": [_poke(active)] if active is not None else [],
        "bench": [_poke(c) for c in bench],
        "discard": [_card(c) for c in discard],
    }


def make_obs(*, your_index: int = 0, turn: int = 2,
             opp_active=None, opp_bench=(), opp_discard=(), logs=()) -> dict:
    """A minimal observation dict revealing the opponent's board."""
    opp = 1 - your_index
    players = [None, None]
    players[your_index] = _player(active=700)
    players[opp] = _player(active=opp_active, bench=opp_bench, discard=opp_discard)
    return {
        "select": {"context": 0},
        "logs": list(logs),
        "current": {"turn": turn, "yourIndex": your_index, "players": players},
    }


def tiny_artifact() -> Artifact:
    """Two archetypes where Solrock/Riolu mark Mega Lucario ex."""
    return Artifact(
        priors={"Mega Lucario ex": 0.5, "Gardevoir ex": 0.5},
        card_inclusion={
            "Mega Lucario ex": {SOLROCK: 0.95, RIOLU: 0.9, MEGA_LUCARIO: 1.0, SHARED: 0.5},
            "Gardevoir ex": {GARDEVOIR: 1.0, KIRLIA: 0.9, SHARED: 0.5},
        },
        background={SOLROCK: 0.05, RIOLU: 0.1, MEGA_LUCARIO: 0.05,
                    GARDEVOIR: 0.05, KIRLIA: 0.05, SHARED: 0.2},
        dossiers={
            "Mega Lucario ex": {
                "representative_build": [SOLROCK, RIOLU, MEGA_LUCARIO, SHARED],
                "evolution_lines": [[RIOLU, MEGA_LUCARIO]],
                "threats": [{"cardId": MEGA_LUCARIO, "role": "attacker"}],
                "targets": [{"cardId": RIOLU, "role": "fragile_preevo"}],
            },
        },
    )
