"""Issue #138 Phase 0b — the Board differential gate (ADR-0068 decision 3).

`Board` becomes an adapter ASSEMBLED FROM the StateModel: field by field, its kwargs stop calling a
bespoke helper and start reading a model field. A field may migrate only when

  (i)  a Phase-1 consumer needs the model's version anyway, and
  (ii) the model's derivation is verified EQUAL to the old helper's output.

This file IS criterion (ii), and it is the executable form of the phase's headline acceptance
criterion — ZERO behavior change. It runs over the real correction-fixture corpus, each fixture
carrying a full observation from a real game, and asserts that every migrated field agrees with the
helper it replaced.

The gate is only possible DURING this phase: nothing is deleted in 0b (deletions are 1d per 0a's
ratified supersession path), so both implementations are alive to be compared. When 1d removes the
helpers, the corresponding rows leave this file with them.

Prior art: the correction-corpus replay tests.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FIXTURES = sorted((REPO / "tests" / "fixtures" / "corrections").glob("*.json"))

#: (Board field, how the OLD helper computed it from the raw obs) for every field migrated in 0b.
#: Each entry is the pre-migration expression, kept verbatim so the comparison is against history
#: rather than against a paraphrase of it.
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
    """The fixture's agent, from its filename prefix (`dp_…` = dragapult_ex)."""
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
        if agent not in cache:                      # one Pilot per agent, not per fixture (the deck
            cache[agent] = _build_pilot(agent)[0]   # and stat tables are deck-fixed)
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
    """A differential over zero frames proves nothing — pin that the corpus is really there."""
    assert len(FIXTURES) >= 100


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda f: f.stem)
def test_every_migrated_board_field_matches_the_helper_it_replaced(fixture, build_pilot):
    """Criterion (ii) over one real frame: the Board the Pilot now assembles from the StateModel
    agrees, field for field, with what the hand-rolled helpers produced."""
    obs = json.loads(fixture.read_text(encoding="utf-8"))["obs"]
    pilot = build_pilot(_agent_of(fixture))
    board = pilot._board(obs, obs.get("select"), carried=pilot.carried())
    me, opp = _sides(pilot, obs)
    for field, old in MIGRATED.items():
        assert getattr(board, field) == old(pilot, me, opp), (
            f"{field} diverged from its pre-migration helper on {fixture.stem}")


@pytest.mark.parametrize("fixture", FIXTURES[:25], ids=lambda f: f.stem)
def test_the_board_build_is_reproducible_on_a_real_frame(fixture, build_pilot):
    """Purity at the Board level: two builds of the same frame, with the Carried State snapshot
    supplied, agree on every migrated field and leave the channel untouched. This is the property
    that replaced the two hand-written snapshot/restore guards."""
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
    """The sharing guard must not churn on a board that did not move — otherwise the cache it guards
    would never hit and the side-sharing design would be inert."""
    obs = json.loads(fixture.read_text(encoding="utf-8"))["obs"]
    pilot = build_pilot(_agent_of(fixture))
    pilot._board(obs, obs.get("select"), carried=pilot.carried())
    first = pilot._state_model
    pilot._board(obs, obs.get("select"), carried=pilot.carried())
    second = pilot._state_model
    assert second.opponent_fingerprint == first.opponent_fingerprint
    assert second.shares_opponent_with(first) is True
