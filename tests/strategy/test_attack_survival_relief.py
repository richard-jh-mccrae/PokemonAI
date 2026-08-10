"""Issue #507 Pattern 1: a terminal KO replaces exposure to the dying Active.

Corpus pins cover every named wasted-Hammer flip and the non-KO preservation set.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "tests")]

from common import composer as cp  # noqa: E402
from common import state_value as sv  # noqa: E402
from corpus_helpers import corpus_record  # noqa: E402
from train.tune import _build_pilot  # noqa: E402

HAMMER = 1120


def _frame(agent: str, episode: str, frame: int):
    """Build the production composer model for one committed correction."""
    record = corpus_record(episode, frame)
    obs = record.obs
    pilot = _build_pilot(agent)[0]
    pilot._board(obs, obs["select"])
    mine = int((obs.get("current") or {}).get("yourIndex") or 0)
    model = pilot._leaf_state_model(obs, mine)
    result = cp.compose(model, obs["select"]["option"], shed=pilot.cost_shed_indices)
    return obs, model, result


def _hand_card_id(obs: dict, option_index: int):
    """Resolve a root PLAY option to its held card id."""
    current = obs["current"]
    me = current["players"][current["yourIndex"]]
    option = obs["select"]["option"][option_index]
    return me["hand"][option["index"]]["id"]


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_survival_relief_is_ko_gated_and_probability_weighted():
    """No KO earns no relief; a coin KO earns the same fraction as its prize leg."""
    miss = sv.attack_ev(damage=90, target_hp=100, target_prizes=1, survival_relief=0.75)
    certain = sv.attack_ev(damage=100, target_hp=100, target_prizes=1, survival_relief=0.75)
    coin = sv.attack_ev(damage=100, target_hp=100, target_prizes=1,
                        survival_relief=0.75, ko_probability=0.5)
    assert miss.survival_relief == 0.0
    assert certain.survival_relief == pytest.approx(0.75)
    assert coin.survival_relief == pytest.approx(0.375)


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_the_opponent_promotes_the_worst_body_for_me():
    """The real Hariyama frame offers Riolu and Lunatone; forward Riolu is the honest promoter."""
    _obs, model, _result = _frame("mega_starmie", "82750161", 29)
    before = sv.survival(sv._exposed_bodies(model))
    survivors = model.theirs.bench_raws
    post = {body["id"]: sv._survival_against(model, survivors, body) for body in survivors}
    assert post[677] < post[675]
    assert sv._attack_survival_relief(model) == pytest.approx(min(post.values()) - before)


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_current_form_promoter_that_is_equally_lethal_adds_no_posture_relief():
    """Removing one lethal Active is no survival benefit when its honest promoter is also lethal."""
    active, promoter = object(), object()

    class Theirs:
        active_raw = active
        bench_raws = (promoter,)

        @staticmethod
        def turns_to_ko_me(_body, *, opp_active, **_kwargs):
            return 1 if opp_active in (active, promoter) else 9

    model = SimpleNamespace(
        mine=SimpleNamespace(active=SimpleNamespace(body={"hp": 300}, prize_value=3.0)),
        theirs=Theirs(), damage_context=lambda **_kwargs: {})

    assert sv._attack_posture_survival_relief(model) == 0.0


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_negative_replacement_delta_cannot_be_erased_by_a_less_negative_posture(monkeypatch):
    """A prior target manipulation's survival gain must cancel when the same target is KO'd."""
    model = object()
    monkeypatch.setattr(sv, "_attack_survival_relief", lambda _model: -1.40625)
    monkeypatch.setattr(sv, "_attack_posture_survival_relief", lambda _model: -0.28125)
    assert sv._terminal_attack_survival_relief(model) == -1.40625


@pytest.mark.req("REQ-CORPUS-0001")
def test_f59_wasted_hammer_loses_to_the_water_attach_in_the_full_pilot():
    """Hammer cannot bank survival against the Active that Jetting Blow removes this turn."""
    record = corpus_record("82523811", 59)
    pilot = _build_pilot("mega_starmie")[0]
    assert pilot.explain(record.obs).chosen == [1]


@pytest.mark.req("REQ-CORPUS-0001")
@pytest.mark.parametrize(
    ("agent", "episode", "frame", "hammer_index", "expected_first"),
    [
        ("mega_starmie", "82750161", 29, 0, 2),
        ("mega_starmie", "82748422", 26, 2, 4),
        ("mega_starmie", "83968638", 17, 1, 3),
        ("mega_starmie", "85163634", 41, 1, 0),
        ("dragapult_ex", "85046350", 32, 2, 1),
    ],
)
def test_wasted_hammer_lines_flip_across_decks(agent, episode, frame, hammer_index, expected_first):
    """Every Issue #507 KO frame rejects Hammer as its composed first action."""
    obs, _model, result = _frame(agent, episode, frame)
    assert _hand_card_id(obs, hammer_index) == HAMMER
    assert result.chosen is not None and result.chosen.first_index == expected_first
    assert result.chosen.first_index != hammer_index


@pytest.mark.req("REQ-CORPUS-0001")
@pytest.mark.parametrize(
    ("episode", "frame", "expected_first"),
    [
        ("82525101", 102, 2),
        ("82525101", 92, 3),
        ("82224509", 67, 2),
        ("82225643", 12, 4),
    ],
)
def test_non_ko_disruption_frames_preserve_their_composer_order(episode, frame, expected_first):
    """Pattern 1 contributes zero when the attacked body survives, leaving existing order intact."""
    _obs, model, result = _frame("mega_starmie", episode, frame)
    attacks = [sv.attack_ev(**leg.kwargs) for leg in sv.attack_ev_legs(model)]
    assert attacks and all(attack.survival_relief == 0.0 for attack in attacks)
    assert result.chosen is not None and result.chosen.first_index == expected_first
