"""Deck-specific Strategy hypotheses for dragapult_ex (deck-genie Phase B, 2026-07-03).

Trigger tests through the Pilot's PUBLIC interface (`explain`): each deck hypothesis fires on its
intended decision and stays silent on an obvious counter-case. Loads the SHIPPED
`src/agents/dragapult_ex/strategy.py` (the real doctrine), not a fixture. Lib-free: observations
built by hand via `pilot_helpers`. (The Phantom Dive spread valuation/placement + the Munkidori
counter-move are GENERAL infra — covered by tests/strategy/test_attack_value.py.)
"""
import importlib.util
from pathlib import Path

import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from pilot_helpers import ACTIVE, BENCH, HAND, PLAY, make_select, opt, poke, state

_REAL = Path(__file__).resolve().parents[2] / "src" / "agents" / "dragapult_ex" / "strategy.py"
_spec = importlib.util.spec_from_file_location("dp_real_strategy", _REAL)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
STRATEGY = _mod.STRATEGY

DREEPY, DRAKLOAK, DRAGAPULT, MUNKIDORI, FEZANDIPITI = 119, 120, 121, 112, 140
CINDERACE, RISKY_RUINS = 666, 1260
FIRE, PSYCHIC, DRAGON = 2, 5, 9
JET, PHANTOM = 153, 154            # Dragapult ex attacks (C 70 / FP 200+spread)
EVOLVE = 9                         # OptionType.EVOLVE

_ATTACK_STATS = {
    JET: AttackStat(JET, damage=70, cost=1),
    PHANTOM: AttackStat(PHANTOM, damage=200, cost=2, benchSpread=60),
}
_STATS = DictCardStatProvider({
    DREEPY: CardStat(DREEPY, name="Dreepy", energyType=DRAGON, hp=70),
    DRAKLOAK: CardStat(DRAKLOAK, name="Drakloak", energyType=DRAGON, hp=90, evolvesFrom="Dreepy"),
    DRAGAPULT: CardStat(DRAGAPULT, name="Dragapult ex", energyType=DRAGON, hp=320, ex=True,
                        evolvesFrom="Drakloak", attacks=(JET, PHANTOM),
                        minAttackCost=1, maxDamage=200, maxDamageCost=2, minCostDamage=70),
    FEZANDIPITI: CardStat(FEZANDIPITI, name="Fezandipiti ex", energyType=7, hp=210, ex=True),
    MUNKIDORI: CardStat(MUNKIDORI, name="Munkidori", energyType=PSYCHIC, hp=110),
    CINDERACE: CardStat(CINDERACE, name="Cinderace", energyType=FIRE, hp=160),
    RISKY_RUINS: CardStat(RISKY_RUINS, hp=0, cardType=4),      # Stadium
}, attacks=_ATTACK_STATS)


def _pilot():
    return Pilot(STRATEGY, deck=[DREEPY] * 4 + [DRAKLOAK] * 4 + [DRAGAPULT] * 3 + [1] * 49,
                 general_strategy=GENERAL_STRATEGY, stats=_STATS, functions=CardFunctions({}))


def _fired(trace):
    return {h.id for h, _ in trace.fired}


# --- bench-the-comeback-drawer: bench Fezandipiti once we're racing (Flip the Script online) --------

@pytest.mark.req("REQ-DP-0001")
def test_bench_the_comeback_drawer_fires_in_race():
    """A PLAY of Fezandipiti ex with an online Dragapult (RACE) + bench room → the rule fires."""
    p = _pilot()
    obs = make_select([opt(PLAY, index=0)],
                      current=state(active=poke(DRAGAPULT, energy=2, hp=320, max_hp=320),  # online -> RACE
                                    bench=[poke(DREEPY, hp=70)], hand=[FEZANDIPITI]))
    assert "bench-the-comeback-drawer" in _fired(p.explain(obs).options[0])


@pytest.mark.req("REQ-DP-0001")
def test_bench_the_comeback_drawer_silent_in_setup():
    """SETUP (no online attacker) → the rule stays silent; dont-bench-multiprize keeps the 2-prizer off."""
    p = _pilot()
    obs = make_select([opt(PLAY, index=0)],
                      current=state(active=poke(DREEPY, hp=70), bench=[], hand=[FEZANDIPITI]))
    assert "bench-the-comeback-drawer" not in _fired(p.explain(obs).options[0])


# --- hold-evolution-until-attacker-ready: don't evolve Drakloak->Dragapult before the FP is on it ---
def test_hold_evolution_silent_when_body_has_fp():
    """Body already carries 2 (FP) -> the evolved Dragapult can Phantom Dive -> no hold."""
    p = _pilot()
    obs = make_select([opt(EVOLVE, area=HAND, index=0, inPlayArea=BENCH, inPlayIndex=0)],
                      current=state(active=poke(CINDERACE, hp=160),
                                    bench=[poke(DRAKLOAK, energy=2, hp=90)], hand=[DRAGAPULT]))
    assert "hold-evolution-until-attacker-ready" not in _fired(p.explain(obs).options[0])


def _stadium_delta(pilot, obs):
    """The composer's own 1-ply delta for the Stadium play — the number the deleted rung stood in
    for. Today it is a hard 0.0, which is why the two tests below are strict xfails."""
    from common import composer as cp
    sel = obs["select"]
    pilot._board(obs, sel)
    model = pilot._leaf_state_model(obs, int((obs.get("current") or {}).get("yourIndex") or 0))
    res = cp.compose(model, sel["option"], shed=pilot.cost_shed_indices)
    assert not list(res.gaps), (
        "the Stadium play is REFUSED, not priced-at-zero — that is a different (and more visible) "
        f"gap than the one this test pins: {list(res.gaps)[:1]}")
    return dict(res.order).get(0)


# --- play-risky-ruins-when-net-positive: net-value gated (wincon in play) / opp-stadium denial ------

@pytest.mark.req("REQ-DP-0003")
@pytest.mark.xfail(strict=True, reason=(
    "POC-T4/5 UNPRICED FAMILY (Issue #386): `play-risky-ruins-when-net-positive` (+15) is "
    "deleted and NOTHING took the family over. `state_value.development` names the gap in its "
    "own `blind_to`: *\"the STADIUM — `model.stadium` has a supplier and no reader, so playing "
    "or replacing one prices exactly 0.\"* Measured here: the composer MODELS the Stadium play "
    "(no coverage gap) and prices it at exactly 0.0, which is worse than a refusal because it "
    "reads as a considered valuation. Strict, so this goes RED the day `development` grows the "
    "read — which is when the deck note in `src/agents/dragapult_ex/strategy.py` needs "
    "revisiting too"))
def test_play_risky_ruins_fires_with_no_stadium_once_wincon_online():
    """No Stadium up AND our win-condition is in play -> place Risky Ruins (past our fragile-basic
    development, the 320-HP body shrugs the symmetric chip while it bleeds the opponent)."""
    p = _pilot()
    obs = make_select([opt(PLAY, index=0)],
                      current=state(active=poke(DRAGAPULT, energy=2, hp=320, max_hp=320),  # wincon in play
                                    hand=[RISKY_RUINS]))
    assert _stadium_delta(p, obs) > 0.0, (
        "the Stadium play still prices at nothing; `state_value` has no reader for `model.stadium`")


@pytest.mark.req("REQ-DP-0003")
@pytest.mark.xfail(strict=True, reason=(
    "POC-T4/5 UNPRICED FAMILY (Issue #386): `play-risky-ruins-when-net-positive` (+15) is "
    "deleted and NOTHING took the family over. `state_value.development` names the gap in its "
    "own `blind_to`: *\"the STADIUM — `model.stadium` has a supplier and no reader, so playing "
    "or replacing one prices exactly 0.\"* Measured here: the composer MODELS the Stadium play "
    "(no coverage gap) and prices it at exactly 0.0, which is worse than a refusal because it "
    "reads as a considered valuation. Strict, so this goes RED the day `development` grows the "
    "read — which is when the deck note in `src/agents/dragapult_ex/strategy.py` needs "
    "revisiting too"))
def test_play_risky_ruins_replaces_opponent_stadium_even_pre_wincon():
    """An OPPONENT Stadium is up -> fire regardless of our wincon: replacing it denies them, an
    independent reason from the self-chip net-value."""
    p = _pilot()
    obs = make_select([opt(PLAY, index=0)],
                      current=state(active=poke(CINDERACE, hp=160), hand=[RISKY_RUINS]))
    obs["current"]["stadium"] = [{"id": 999, "serial": 1, "playerIndex": 1}]   # opponent's Stadium
    assert _stadium_delta(p, obs) > 0.0, (
        "replacing THEIR Stadium prices at nothing; the transition applies the replacement but no "
        "term reads what it changed")


