"""Issue #138 Phase 0b (ADR-0068) — over the correction-fixture corpus, every `Board` field migrated
to the StateModel equals the helper it replaced.

The gate is only possible while both implementations are alive; Phase 1d deletes the helpers and the
corresponding `MIGRATED` rows leave with them.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


def _has_obs(fixture: Path) -> bool:
    return "obs" in json.loads(fixture.read_text(encoding="utf-8"))


FIXTURES = [f for f in sorted((REPO / "tests" / "fixtures" / "corrections").glob("*.json"))
            if _has_obs(f)]

#: Board field -> the OLD helper's expression, kept VERBATIM: paraphrasing a lambda here makes the
#: differential compare the model against itself.
MIGRATED = {
    "my_prizes_remaining": lambda p, me, opp: len(me.get("prize") or []),
    "opp_prizes_remaining": lambda p, me, opp: len(opp.get("prize") or []),
    "my_discard_basic_energy": lambda p, me, opp: p._discard_energy_counts(
        me.get("discard") or [])[1],
    "opp_discard_energy": lambda p, me, opp: p._discard_energy_counts(opp.get("discard") or [])[1],
    "hand_ids": lambda p, me, opp: frozenset(
        c.get("id") for c in (me.get("hand") or []) if c and c.get("id") is not None),
    "hand_basic_energy": lambda p, me, opp: p._hand_basic_energy(me.get("hand") or []),
}


def _agent_of(fixture: Path) -> str:
    stem = fixture.name
    if stem.startswith("dp_"):
        return "dragapult_ex"
    if stem.startswith("ml_"):
        return "mega_lucario"
    if stem.startswith("ms_"):
        return "mega_starmie"
    return "dragapult_ex"


@pytest.fixture(scope="module")
def build_pilot():
    sys.path.insert(0, str(REPO / "tools"))
    from train.tune import _build_pilot
    cache: dict = {}

    def get(agent: str):
        if agent not in cache:
            cache[agent] = _build_pilot(agent)[0]
        return cache[agent]
    return get


def _sides(pilot, obs):
    state = obs.get("current") or {}
    players = state.get("players") or []
    yi = state.get("yourIndex", 0)
    me = players[yi] if 0 <= yi < len(players) and players[yi] else {}
    opp = players[1 - yi] if 0 <= 1 - yi < len(players) and players[1 - yi] else {}
    return me, opp


def test_the_corpus_is_present_so_the_gate_is_not_vacuously_green():
    assert len(FIXTURES) >= 100


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.stem)
def test_every_migrated_board_field_matches_the_helper_it_replaced(fixture, build_pilot):
    obs = json.loads(fixture.read_text(encoding="utf-8"))["obs"]
    pilot = build_pilot(_agent_of(fixture))
    board = pilot._board(obs, obs.get("select"), carried=pilot.carried())
    me, opp = _sides(pilot, obs)
    for field, old in MIGRATED.items():
        assert getattr(board, field) == old(pilot, me, opp), (
            f"{field} diverged from its pre-migration helper on {fixture.stem}")


@pytest.mark.parametrize("fixture", FIXTURES[:25], ids=lambda f: f.stem)
def test_the_board_build_is_reproducible_on_a_real_frame(fixture, build_pilot):
    obs = json.loads(fixture.read_text(encoding="utf-8"))["obs"]
    pilot = build_pilot(_agent_of(fixture))
    before = pilot.carried()
    first = pilot._board(obs, obs.get("select"), carried=before)
    second = pilot._board(obs, obs.get("select"), carried=before)
    for field in MIGRATED:
        assert getattr(first, field) == getattr(second, field)
    assert pilot.carried() == before


@pytest.mark.parametrize("fixture", FIXTURES[:25], ids=lambda f: f.stem)
def test_the_opponent_fingerprint_is_stable_within_a_frame(fixture, build_pilot):
    """A fingerprint that churns on a still board makes the cache it guards never hit."""
    obs = json.loads(fixture.read_text(encoding="utf-8"))["obs"]
    pilot = build_pilot(_agent_of(fixture))
    pilot._board(obs, obs.get("select"), carried=pilot.carried())
    first = pilot._state_model
    pilot._board(obs, obs.get("select"), carried=pilot.carried())
    second = pilot._state_model
    assert second.opponent_fingerprint == first.opponent_fingerprint
    assert second.shares_opponent_with(first) is True
