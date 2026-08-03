"""Blunder round 2026-07-02 (mega_starmie) — the Salvatore search-whiff fix (/blunder-buster, ep83117367).

Salvatore is a rush-evolve tutor: "search your deck for a card that has no Abilities and evolves from
1 of your Pokémon, and put it onto that Pokémon to evolve it." Its only fetch target in this deck is
Mega Starmie ex (Staryu → Mega; Cinderace is excluded — it carries the Explosiveness Ability). So once
every Mega Starmie ex is prized/played, Salvatore whiffs even with a Staryu in play.

This round wires that into the SOUND deck-oracle: a `rush_evolve` fetch-filter (over the new
`CardStat.hasAbility`) so `dont-search-an-empty-deck` sees Salvatore, and a reachability gate on the
POSITIVE endorsements (`prefer-rush-evolve-tutor`, the deck's `tutor-the-wincon`) so the −60 whiff
penalty is no longer cancelled. Lib-free synthetic obs; one engine test pins the `hasAbility` mapping.
"""
import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Line, Strategy
from common.effects import CardEffects
from pilot_helpers import HAND, PLAY, make_select, opt, poke, state

# Salvatore's rush-evolve predicate now lives in the card representation: an `evolution` FETCH clause
# with `no_ability` (card_effects.json / ADR-0032, the tier that replaced `_FETCH_FILTERS`).
_SALVATORE_EFFECTS = CardEffects(
    {1189: [{"kind": "fetch", "target": "evolution", "zone": "deck", "no_ability": True}]})

END = 14
WINCON = 900       # ability-LESS Mega ex — Salvatore-fetchable (Staryu → Mega Starmie ex)
ABIL_EVO = 901     # an Evolution WITH an Ability (Cinderace-like) — NOT Salvatore-fetchable
PREEVO = 800       # a Basic pre-evolution (Staryu-like)
FILLER = 99        # non-Pokémon deck filler (absent from stats)
SALVATORE = 1189   # tags: search + rush_evolve


def _fired(o):
    return {h.id for h, _ in o.fired}


def _stats():
    return DictCardStatProvider({
        WINCON: CardStat(WINCON, synthetic=True, name="Mega Starmie ex", hp=330, megaEx=True, maxDamage=210,
                         maxDamageCost=3, minAttackCost=1, minCostDamage=120, attacks=(10, 11),
                         evolvesFrom="Staryu", hasAbility=False, energyType=3),
        ABIL_EVO: CardStat(ABIL_EVO, synthetic=True, name="Cinderace", hp=160, maxDamage=50, maxDamageCost=1,
                           minAttackCost=1, attacks=(12,), evolvesFrom="Raboot", hasAbility=True),
        PREEVO: CardStat(PREEVO, synthetic=True, name="Staryu", hp=70, maxDamage=20, maxDamageCost=1,
                         minAttackCost=1, attacks=(13,), evolvesFrom=None, hasAbility=False),
    }, attacks={10: AttackStat(10, damage=210, cost=3), 11: AttackStat(11, damage=120, cost=1),
                12: AttackStat(12, damage=50, cost=1), 13: AttackStat(13, damage=20, cost=1)})


def _pilot(deck):
    return Pilot(Strategy(roles={WINCON: ["win_condition", "primary_attacker"], SALVATORE: ["tutor"]},
                          lines=[Line(path=[PREEVO, WINCON], payoff=WINCON, role="win_condition")]),
                 deck=deck, general_strategy=GENERAL_STRATEGY, stats=_stats(),
                 functions=CardFunctions({SALVATORE: ["search", "rush_evolve"]}),
                 effects=_SALVATORE_EFFECTS)


def _ctx(pilot, obs, i):
    select = obs["select"]
    return pilot._context(obs, select, pilot._board(obs, select), select["option"][i])


# ---------------------------------------------------------------- the rush_evolve fetch clause
@pytest.mark.req("REQ-GEN-0032")
def test_rush_evolve_clause_takes_ability_less_evolutions_only():
    st = _stats()
    pilot = _pilot([WINCON])
    clause = {"kind": "fetch", "target": "evolution", "zone": "deck", "no_ability": True}
    assert pilot._fetch_target_matches(clause, st.get(WINCON)) is True   # ability-less Evolution
    assert pilot._fetch_target_matches(clause, st.get(ABIL_EVO)) is False  # has an Ability — excluded
    assert pilot._fetch_target_matches(clause, st.get(PREEVO)) is False    # a Basic — not an evolution


@pytest.mark.req("REQ-GEN-0032")
def test_search_deck_set_for_salvatore_is_the_ability_less_evolution_only():
    # Deck holds BOTH ability-less Mega and ability-bearing Cinderace; Salvatore reaches only
    # the former — ability-bearing one isn't a legal rush-evolve target.
    pilot = _pilot([WINCON] * 3 + [ABIL_EVO] * 4 + [PREEVO] * 3 + [FILLER] * 50)
    assert pilot._search_deck_set(SALVATORE) == {WINCON}


# ---------------------------------------------------------------- dont-search-an-empty-deck on Salvatore
@pytest.mark.req("REQ-GEN-0032")
def test_salvatore_stands_down_when_its_evolution_is_gone_from_the_deck():
    # 3 Mega ex (Salvatore's only target), all accounted OUTSIDE deck (discard) -> Salvatore whiffs,
    # even w/ a Staryu in play to evolve. The ep83117367 shape.
    pilot = _pilot([WINCON] * 3 + [PREEVO] * 3 + [FILLER] * 54)
    play_salv = opt(PLAY, area=HAND, index=0)
    gone = state(active=poke(PREEVO, hp=70), bench=[poke(PREEVO, hp=70)],
                 discard=[WINCON, WINCON, WINCON], hand=[SALVATORE], prizes=6)
    obs = make_select([play_salv, opt(END)], current=gone)
    c = _ctx(pilot, obs, 0)
    assert c.search_targets_exhausted
    fired = _fired(pilot.explain(obs).options[0])
    assert "dont-search-an-empty-deck" in fired          # sound whiff guard fires
    assert "prefer-rush-evolve-tutor" not in fired        # positive endorsement gated off
    assert pilot.decide(obs) == [1]                       # End beats guaranteed-whiff Salvatore


@pytest.mark.req("REQ-GEN-0032")
def test_salvatore_is_endorsed_while_a_copy_could_still_be_in_the_deck():
    # Only 2 of 3 Mega ex accounted; 3rd could sit in the 6 hidden prizes -> NOT a certain whiff.
    # Rush-evolve tutor keeps its endorsement (sound: never suppress a plausibly-present target).
    pilot = _pilot([WINCON] * 3 + [PREEVO] * 3 + [FILLER] * 54)
    play_salv = opt(PLAY, area=HAND, index=0)
    maybe = state(active=poke(PREEVO, hp=70), bench=[poke(PREEVO, hp=70)],
                  discard=[WINCON, WINCON], hand=[SALVATORE], prizes=6)
    obs = make_select([play_salv, opt(END)], current=maybe)
    c = _ctx(pilot, obs, 0)
    assert not c.search_targets_exhausted
    fired = _fired(pilot.explain(obs).options[0])
    assert "dont-search-an-empty-deck" not in fired
    assert "prefer-rush-evolve-tutor" in fired            # reachable target -> still preferred


# ---------------------------------------------------------------- own_prizes str-key coercion (JSON obs)
@pytest.mark.req("REQ-GEN-0032")
def test_own_prizes_string_keys_are_coerced_to_ints():
    # A Correction's obs is JSON, so own_prizes keys are STRINGS ("900"), while decklist is
    # int-keyed. Pilot must coerce, else resolved prize never matches and oracle is blind.
    pilot = _pilot([WINCON] * 3 + [FILLER] * 57)
    st = state(active=poke(WINCON, energy=1, hp=330), discard=[WINCON], hand=[SALVATORE],
               prizes=6, deck_count=53)                   # 2 of 3 Mega seen; 3rd is prized
    obs = make_select([opt(PLAY, area=HAND, index=0), opt(END)], current=st)
    obs["own_prizes"] = {str(WINCON): 1}                  # JSON string key (as on disk)
    board = pilot._board(obs, obs["select"])
    assert board.deck_definitely_empty_of(WINCON)         # 3 − 2 seen − 1 prized == 0


# ---------------------------------------------------------------- hasAbility provider mapping (engine)
@pytest.mark.req("REQ-GEN-0032")
def test_cardstat_has_ability_is_set_from_engine_skills():
    try:
        from common.scouting.provider import EngineCardStatProvider
        stats = EngineCardStatProvider()
        cinderace = stats.get(666)
    except Exception as e:                                # native engine unavailable in this env
        pytest.skip(f"engine card data unavailable: {e}")
    assert cinderace is not None and cinderace.hasAbility is True    # Cinderace — Explosiveness
    assert stats.get(1031).hasAbility is False                       # Mega Starmie ex — no Ability
    assert stats.get(1030).hasAbility is False                       # Staryu — a Basic, no Ability

