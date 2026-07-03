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
})
_ATTACK_STATS = {
    JET: AttackStat(JET, damage=70, cost=1),
    PHANTOM: AttackStat(PHANTOM, damage=200, cost=2, benchSpread=60),
}
_ATTACKS = {aid: st.damage for aid, st in _ATTACK_STATS.items()}
_COSTS = {aid: st.cost for aid, st in _ATTACK_STATS.items()}


def _pilot():
    return Pilot(STRATEGY, deck=[DREEPY] * 4 + [DRAKLOAK] * 4 + [DRAGAPULT] * 3 + [1] * 49,
                 general_strategy=GENERAL_STRATEGY, stats=_STATS, functions=CardFunctions({}),
                 attacks=_ATTACKS, attack_costs=_COSTS, attack_stats=_ATTACK_STATS)


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

@pytest.mark.req("REQ-DP-0002")
def test_hold_evolution_fires_when_body_lacks_fp():
    """EVOLVE Drakloak (1 energy < FP) -> Dragapult, my Active not doomed -> penalise (hold + keep Recon)."""
    p = _pilot()
    obs = make_select([opt(EVOLVE, area=HAND, index=0, inPlayArea=BENCH, inPlayIndex=0)],
                      current=state(active=poke(CINDERACE, hp=160),
                                    bench=[poke(DRAKLOAK, energy=1, hp=90)], hand=[DRAGAPULT]))
    assert "hold-evolution-until-attacker-ready" in _fired(p.explain(obs).options[0])


@pytest.mark.req("REQ-DP-0002")
def test_hold_evolution_silent_when_body_has_fp():
    """Body already carries 2 (FP) -> the evolved Dragapult can Phantom Dive -> no hold."""
    p = _pilot()
    obs = make_select([opt(EVOLVE, area=HAND, index=0, inPlayArea=BENCH, inPlayIndex=0)],
                      current=state(active=poke(CINDERACE, hp=160),
                                    bench=[poke(DRAKLOAK, energy=2, hp=90)], hand=[DRAGAPULT]))
    assert "hold-evolution-until-attacker-ready" not in _fired(p.explain(obs).options[0])


# --- play-risky-ruins-when-net-positive: play it with no Stadium up / to replace the opponent's -----

@pytest.mark.req("REQ-DP-0003")
def test_play_risky_ruins_fires_with_no_stadium():
    """No Stadium in play -> place Risky Ruins (chip the opp's Basic non-{D} bench-entries)."""
    p = _pilot()
    obs = make_select([opt(PLAY, index=0)],
                      current=state(active=poke(CINDERACE, hp=160), hand=[RISKY_RUINS]))
    assert "play-risky-ruins-when-net-positive" in _fired(p.explain(obs).options[0])


@pytest.mark.req("REQ-DP-0003")
def test_play_risky_ruins_silent_when_ours_is_up():
    """Our own Risky Ruins is already in play -> silent (nothing to gain; engine blocks a re-play anyway)."""
    p = _pilot()
    obs = make_select([opt(PLAY, index=0)],
                      current=state(active=poke(CINDERACE, hp=160), hand=[RISKY_RUINS]))
    obs["current"]["stadium"] = [{"id": RISKY_RUINS, "serial": 1, "playerIndex": 0}]   # ours (yourIndex 0)
    assert "play-risky-ruins-when-net-positive" not in _fired(p.explain(obs).options[0])
