"""Deck-specific Strategy hypotheses for mega_lucario (deck-genie Phase B, tranche 1) + the
general rules / infra this build adds. Trigger tests through the Pilot's PUBLIC interface
(`decide`/`explain`): each rule fires on its intended decision and stays silent on an obvious
counter-case. Loads the SHIPPED `src/agents/mega_lucario/strategy.py`. Lib-free: observations built
by hand via `pilot_helpers`; the recoil-infra test exercises the provider transform directly.
"""
import importlib.util
from pathlib import Path

import pytest

from common.cards import CardFunctions
from common.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import CardStat, DictCardStatProvider, _build_cache, parse_attack_recoil
from pilot_helpers import (
    ACTIVE, DECK, HAND, PLAY, TO_HAND, card_opt, make_select, opt, poke, state,
)

# Load the shipped deck Strategy (pure data; imports only common.strategy).
_REAL = Path(__file__).resolve().parents[1] / "src" / "agents" / "mega_lucario" / "strategy.py"
_spec = importlib.util.spec_from_file_location("ml_real_strategy", _REAL)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
STRATEGY = _mod.STRATEGY

RIOLU, MEGA_LUCARIO_EX = 677, 678
SOLROCK, LUNATONE, MAKUHITA, HARIYAMA = 676, 675, 673, 674
LILLIES, JUDGE = 1227, 1213
FIGHTING = 6

_STATS = DictCardStatProvider({
    RIOLU: CardStat(RIOLU, energyType=FIGHTING, hp=80),
    MEGA_LUCARIO_EX: CardStat(MEGA_LUCARIO_EX, energyType=FIGHTING, megaEx=True, hp=340),
    SOLROCK: CardStat(SOLROCK, energyType=FIGHTING, hp=110),
    LUNATONE: CardStat(LUNATONE, energyType=FIGHTING, hp=110),
    LILLIES: CardStat(LILLIES, hp=0),
    JUDGE: CardStat(JUDGE, hp=0),
    FIGHTING: CardStat(FIGHTING, hp=0, energyType=FIGHTING),
})
# tags as shipped in card_functions.json for the cards under test.
_TAGS = CardFunctions({LILLIES: ["draw", "discard_hand"], JUDGE: ["draw", "hand_disruption", "discard_hand"]})


def _pilot(functions=_TAGS, stats=_STATS):
    return Pilot(STRATEGY, deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=stats, functions=functions)


def _fired(option_trace):
    return {h.id for h, _ in option_trace.fired}


# --- fetch-the-engine-first (DECK rule; reads the `engine` Role at a TO_HAND search) ---

@pytest.mark.req("REQ-ML-0001")
def test_fetch_the_engine_first_prefers_an_engine_piece_at_a_search():
    """At a setup search, the Solrock/Lunatone engine (engine Role) is preferred over the Riolu line
    piece — engine fuels Aura Jab + the early attacker."""
    p = _pilot()
    obs = make_select([card_opt(DECK, 0), card_opt(DECK, 1)], context=TO_HAND,
                      deck=[{"id": SOLROCK}, {"id": RIOLU}], current=state(hand=[]))
    opts = p.explain(obs).options
    assert "fetch-the-engine-first" in _fired(opts[0])        # Solrock — engine
    assert "fetch-the-engine-first" not in _fired(opts[1])    # Riolu — line piece, not engine


@pytest.mark.req("REQ-ML-0001")
def test_fetch_the_engine_first_silent_off_a_search():
    """The rule is about FETCHING (TO_HAND) — it must stay silent when simply playing a card."""
    p = _pilot()
    obs = make_select([opt(PLAY, area=HAND, index=0)], current=state(hand=[SOLROCK]))
    assert "fetch-the-engine-first" not in _fired(p.explain(obs).options[0])


# --- hold-wincon-dont-shuffle (GENERAL rule; discard_hand + wincon_in_hand) ---

@pytest.mark.req("REQ-ML-0002")
def test_hold_wincon_dont_shuffle_fires_with_the_mega_in_hand():
    """Playing Lillie's (shuffles your hand into the deck) while a usable Mega Lucario ex is in hand
    → penalise: don't shuffle the payoff back into the deck."""
    p = _pilot()
    obs = make_select([opt(PLAY, area=HAND, index=0)],
                      current=state(hand=[LILLIES, MEGA_LUCARIO_EX]))
    assert "hold-wincon-dont-shuffle" in _fired(p.explain(obs).options[0])


@pytest.mark.req("REQ-ML-0002")
def test_hold_wincon_dont_shuffle_fires_on_judge_too():
    """Judge also shuffles your hand into the deck (now tagged discard_hand) → same guard."""
    p = _pilot()
    obs = make_select([opt(PLAY, area=HAND, index=0)],
                      current=state(hand=[JUDGE, MEGA_LUCARIO_EX]))
    assert "hold-wincon-dont-shuffle" in _fired(p.explain(obs).options[0])


@pytest.mark.req("REQ-ML-0002")
def test_hold_wincon_dont_shuffle_silent_without_the_wincon_in_hand():
    """No win-condition in hand → shuffling away a dead/clogged hand is fine; the rule stays silent."""
    p = _pilot()
    obs = make_select([opt(PLAY, area=HAND, index=0)],
                      current=state(hand=[LILLIES, SOLROCK]))
    assert "hold-wincon-dont-shuffle" not in _fired(p.explain(obs).options[0])


# --- CardStat.recoil infra (lib-free: parser + _build_cache transform) ---

class _FakeAttack:
    def __init__(self, attackId, damage, energies, text):
        self.attackId, self.damage, self.energies, self.text = attackId, damage, energies, text


class _FakeCard:
    def __init__(self, cardId, name, attacks):
        self.cardId, self.name, self.attacks = cardId, name, attacks
        self.hp = 150
        self.ex = self.megaEx = False
        self.aceSpec = False
        self.weakness = self.resistance = self.energyType = None
        self.retreatCost = 0
        self.cardType = None
        self.evolvesFrom = None
        self.skills = []


def test_parse_attack_recoil_wild_press():
    assert parse_attack_recoil("This Pokémon also does 70 damage to itself.") == 70
    assert parse_attack_recoil("During your next turn, this Pokémon can't use Mega Brave.") == 0


def test_cardstat_recoil_flows_from_build_cache():
    """The highest-damage attack's unconditional recoil lands on CardStat.recoil (Wild Press 210/70)."""
    wild_press = _FakeAttack(1, 210, [6, 6, 6], "This Pokémon also does 70 damage to itself.")
    chip = _FakeAttack(2, 10, [6], "")
    card = _FakeCard(674, "Hariyama", [1, 2])
    cache = _build_cache([card], [wild_press, chip])
    assert cache[674].recoil == 70
    assert cache[674].maxDamage == 210
