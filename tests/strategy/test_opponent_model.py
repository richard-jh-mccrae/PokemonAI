"""Opponent Model facade — `common.opponent_model.OpponentModel` (ADR-0047).

The umbrella `board.opponent` facade over the three knowledge subsystems: Identity (an injected Scout),
Resources (`OpponentResourceModel` + `copies_left_odds`), Dispositions (the matched Brief's
`opponent_properties`). Lib-free: a stub Scout is injected at the DI seam; the real `Read`/`Artifact`/
`Brief` dataclasses back the assertions. Every accessor FAILS OPEN — an unknown value never suppresses a
line (`copies_left_odds` defaults a card to 1.0, estimates to None, dispositions to the caller default).
"""
import pytest

from common.deck_odds import p_contains
from common.opponent_model import OpponentModel
from common.pilot import Pilot
from common.scouting.artifact import Artifact
from common.scouting.briefs import Brief
from common.scouting.read import Read
from common.strategy import Strategy
from pilot_helpers import make_select, opt


class _StubScout:
    """A Scout double at the DI seam: records the obs it saw and returns a preset Read."""
    def __init__(self, read):
        self._read = read
        self.saw = None

    def observe(self, obs):
        self.saw = obs
        return self._read


class _ThrowingScout:
    """A Scout that blows up — the facade must swallow it (Identity fails open, Resources still run)."""
    def observe(self, obs):
        raise RuntimeError("boom")


def _artifact(arch="crustle", build=()):
    return Artifact(priors={arch: 1.0}, card_inclusion={}, background={},
                    dossiers={arch: {"representative_build": list(build)}})


def _obs(opp, *, turn=2):
    me = {"prize": [None] * 6, "active": [], "bench": [], "discard": [], "handCount": 7, "deckCount": 40}
    return {"current": {"turn": turn, "yourIndex": 0, "players": [me, opp]},
            "select": {}, "logs": []}


def _opp(*, deck_count=30, hand_count=5, prizes_hidden=6, discard=(), bench=()):
    return {"active": [], "bench": [{"id": c, "energyCards": [], "tools": [], "preEvolution": []}
                                    for c in bench],
            "discard": [{"id": c} for c in discard], "prize": [None] * prizes_hidden,
            "handCount": hand_count, "deckCount": deck_count}


# ============================================================ observe fan-out
@pytest.mark.req("REQ-OPP-0010")
def test_observe_fans_out_to_identity_and_resources():
    read = Read(candidates=[("crustle", 0.9)], confidence=(0.9, 0.5))
    scout = _StubScout(read)
    om = OpponentModel(scout=scout, artifact=_artifact())
    out = om.observe(_obs(_opp(deck_count=41, hand_count=4)))
    assert out is read and om.read is read          # Identity: the injected Scout's Read is surfaced
    assert scout.saw is not None                    # the Scout was fed the obs
    assert om.deck_count == 41 and om.hand_size == 4  # Resources updated from the same obs


@pytest.mark.req("REQ-OPP-0010")
def test_observe_is_fail_open_when_the_scout_throws():
    om = OpponentModel(scout=_ThrowingScout())
    read = om.observe(_obs(_opp(deck_count=20)))    # a throwing Identity must not propagate
    assert isinstance(read, Read) and om.archetype is None   # degrades to an empty Read
    assert om.deck_count == 20                       # ...and Resources still updated


@pytest.mark.req("REQ-OPP-0011")
def test_facade_surfaces_resource_deltas_across_turns():
    om = OpponentModel(scout=_StubScout(Read()))
    om.observe(_obs(_opp(hand_count=5, discard=[1]), turn=2))
    om.observe(_obs(_opp(hand_count=9, discard=[1, 2, 3]), turn=4))
    assert om.hand_size_delta == 4                    # 9 - 5, surfaced through the facade
    assert om.last_turn_dumped is True               # discard grew by 2


# ============================================================ copies odds via the archetype prior
@pytest.mark.req("REQ-OPP-0011")
def test_copies_odds_use_the_confident_archetypes_representative_build():
    read = Read(candidates=[("crustle", 0.9)])
    om = OpponentModel(scout=_StubScout(read),
                       artifact=_artifact("crustle", build=[9, 9, 9, 9, 8, 8, 8]))
    om.observe(_obs(_opp(deck_count=30, hand_count=5, prizes_hidden=6, discard=[9])))
    # 4 copies of 9, 1 visible -> 3 unseen; hidden non-deck pool = 6 prizes + 5 hand = 11.
    assert om.copies_left_odds(9) == pytest.approx(p_contains(3, 11, 30))
    assert om.copies_left_odds(999) == 1.0          # unknown card -> fail-open "assume present"


@pytest.mark.req("REQ-OPP-0011")
def test_copies_odds_are_silent_when_the_archetype_is_not_confidently_recognized():
    read = Read(candidates=[("crustle", 0.4)])       # below the 0.6 recognition threshold
    om = OpponentModel(scout=_StubScout(read),
                       artifact=_artifact("crustle", build=[9, 9, 9, 9]))
    om.observe(_obs(_opp(discard=[9])))
    assert om.archetype is None
    assert om.copies_left_odds() == {}               # γ-gated: no confident Read -> no estimate map
    assert om.copies_left_odds(9) == 1.0             # ...and a specific card fails open to present


# ============================================================ dispositions (asserted tier)
@pytest.mark.req("REQ-OPP-0012")
def test_dispositions_come_from_the_noted_brief():
    om = OpponentModel(scout=_StubScout(Read()))
    assert om.disposition("opp_is_engine_dependent", False) is False   # no brief -> caller default
    om.note_brief(Brief(slug="crustle", label="Crustle", covers=["crustle"],
                        opponent_properties={"opp_is_engine_dependent": True}))
    assert om.disposition("opp_is_engine_dependent", False) is True
    assert om.disposition("opp_no_pivot", False) is False              # unasserted key -> default
    om.note_brief(None)                              # posture off / no cover -> cleared
    assert om.disposition("opp_is_engine_dependent", False) is False


# ============================================================ fail-open construction
@pytest.mark.req("REQ-OPP-0013")
def test_facade_fails_open_with_no_scout_and_no_artifact():
    om = OpponentModel(scout=None, artifact=None)    # degenerate wiring must never crash or fabricate
    read = om.observe(_obs(_opp(deck_count=33)))
    assert isinstance(read, Read) and om.archetype is None
    assert om.deck_count == 33                        # Resources still works off the raw obs
    assert om.deckout_in_turns is None
    assert om.copies_left_odds() == {} and om.copies_left_odds(1) == 1.0
    assert om.disposition("anything", "d") == "d"


# ============================================================ S4: Board integration (behavior-neutral)
@pytest.mark.req("REQ-OPP-0014")
def test_real_pilot_board_exposes_the_facade_and_resources_via_the_fan_out():
    pilot = Pilot(Strategy(), deck=[1, 2, 3])
    me = {"active": [], "bench": [], "hand": [], "handCount": 0, "discard": [], "prize": [None] * 6}
    opp = {"active": [], "bench": [], "hand": None, "handCount": 4, "discard": [],
           "prize": [None] * 6, "deckCount": 37}
    obs = make_select([opt()], current={"turn": 2, "yourIndex": 0, "players": [me, opp]})
    obs["logs"] = [
        {"type": 2, "playerIndex": 1},
        {"type": 6, "playerIndex": 0, "fromArea": 5, "toArea": 3},
        {"type": 2, "playerIndex": 0},
    ]
    board = pilot._board(obs, obs["select"])
    assert board.opponent is pilot.opponent                 # the single facade rides on the Board
    assert board.opponent.deck_count == 37                  # Resources tracked via _board's fan-out
    # Dispositions delegate: no Scout wired -> no Brief -> opp_property returns the caller default,
    # now routed through the facade (behavior-neutral with the pre-facade direct-Brief read).
    assert board.opp_property("opp_is_engine_dependent", False) is False
    assert pilot.opponent.my_pokemon_koed_last_turn is True
    assert pilot._state_model.my_pokemon_koed_last_turn is True
    assert board.my_pokemon_koed_last_turn is True


@pytest.mark.req("REQ-OPP-0014")
def test_board_opp_property_delegates_the_truthy_path_and_still_falls_back():
    from common.pilot import Board
    # An asserted property must survive the fold (delegation to the facade), not just the default.
    om = OpponentModel(scout=_StubScout(Read()))
    om.note_brief(Brief(slug="crustle", label="Crustle", covers=["crustle"],
                        opponent_properties={"opp_is_engine_dependent": True}))
    assert Board(opponent=om).opp_property("opp_is_engine_dependent", False) is True
    # And a Board built WITHOUT the facade (direct construction) keeps the legacy Brief read.
    legacy = Board(brief=Brief(slug="c", label="c", covers=["c"],
                               opponent_properties={"opp_is_engine_dependent": True}))
    assert legacy.opp_property("opp_is_engine_dependent", False) is True
