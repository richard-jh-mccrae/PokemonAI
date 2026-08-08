"""Issue #138 Phase 0b — the StateModel (ADR-0068).

The primary seam: a dict-backed Stat Provider and hand-built zone dicts, no Pilot and no engine boot.
Asserts external behavior only — field values, the sharing guard's verdict, the epistemic legs, the
channel's contract — never memo internals.

Every `CardStat` below is audited field-for-field against `data/EN_Card_Data.csv` by
`tests/scouting/test_cardstat_fixture_facts.py`, so an invented card fact fails the build.
"""
import copy

import pytest

from common.cards import CardFunctions
from common.effects import CardEffects
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.state_model import (CarriedState, CountTriple, MySide, StateModel, TheirSide,
                               count_triple)
from common.strategy.combat import CombatMath

# EnergyType codes (cg.api.EnergyType)
COLORLESS, GRASS, FIRE, PSYCHIC, FIGHTING, DARKNESS, DRAGON = 0, 1, 2, 5, 6, 7, 9

DRAGAPULT, MUNKIDORI, RIOLU, MEGA_LUC = 121, 112, 677, 678
JET_HEADBUTT, PHANTOM_DIVE = 9121, 9122
AURA_JAB, MEGA_BRAVE = 982, 983
#: Riolu's ONLY attack: Accelerating Stab `{F}` 30, `nextTurnSameAttackLock`.
ACCELERATING_STAB = 9677
#: An OFF-POOL body carrying the shape a PARTIALLY-KNOWN attack table produces — a `maxDamage`
#: roll-up with an empty `attacks` tuple. Deliberately no real id, so it can make no wrong card claim.
PARTIAL = 990001
CRISPIN = 1198
E_R, E_P, E_D, E_F = 2, 5, 7, 6
# The card set's only two bench-GATED attackers, so the payoff gate is tested on both shapes: a
# single named partner, and an "and" list that needs BOTH.
SOLROCK, LUNATONE = 676, 675
MESPRIT, UXIE, AZELF = 216, 215, 217
COSMIC_BEAM, POWER_GEM = 9676, 9675
FULL_HEART, GUARDIAN_BURST = 9216, 9217

_STATS = {
    DRAGAPULT: CardStat(DRAGAPULT, synthetic=True, name='Dragapult ex', hp=320, ex=True, stage2=True,
                        evolvesFrom="Drakloak", energyType=DRAGON, maxDamage=200, maxDamageCost=2,
                        minAttackCost=1, minCostDamage=70,
                        attacks=(JET_HEADBUTT, PHANTOM_DIVE), cardType=0),
    MUNKIDORI: CardStat(MUNKIDORI, synthetic=True, name='Munkidori', hp=70, energyType=DARKNESS, cardType=0),
    # `test_state_value.py` carries a sibling Riolu row; correcting one and not the other is how the
    # pair drifts.
    RIOLU: CardStat(RIOLU, synthetic=True, name='Riolu', hp=80, energyType=FIGHTING, minAttackCost=1,
                    maxDamage=30, maxDamageCost=1, minCostDamage=30,
                    attacks=(ACCELERATING_STAB,), cardType=0),
    MEGA_LUC: CardStat(MEGA_LUC, synthetic=True, name='Mega Lucario ex', hp=340, megaEx=True, energyType=FIGHTING,
                       evolvesFrom="Riolu", maxDamage=270, minAttackCost=1, minCostDamage=130,
                       attacks=(AURA_JAB, MEGA_BRAVE), cardType=0),
    CRISPIN: CardStat(CRISPIN, name="Crispin", cardType=3),
    SOLROCK: CardStat(SOLROCK, synthetic=True, name='Solrock', hp=110, energyType=FIGHTING, weakness=GRASS,
                      minAttackCost=1, maxDamage=70, maxDamageCost=1, minCostDamage=70,
                      attacks=(COSMIC_BEAM,), cardType=0),
    LUNATONE: CardStat(LUNATONE, synthetic=True, name='Lunatone', hp=110, energyType=FIGHTING, weakness=GRASS,
                       minAttackCost=2, maxDamage=50, maxDamageCost=2, minCostDamage=50,
                       attacks=(POWER_GEM,), cardType=0),
    MESPRIT: CardStat(MESPRIT, synthetic=True, name='Mesprit', hp=70, energyType=PSYCHIC, weakness=DARKNESS,
                      minAttackCost=1, maxDamage=160, maxDamageCost=2, minCostDamage=0,
                      attacks=(FULL_HEART, GUARDIAN_BURST), cardType=0),
    UXIE: CardStat(UXIE, synthetic=True, name='Uxie', hp=70, energyType=PSYCHIC, weakness=DARKNESS, cardType=0),
    AZELF: CardStat(AZELF, synthetic=True, name='Azelf', hp=70, energyType=PSYCHIC, weakness=DARKNESS, cardType=0),
    E_R: CardStat(E_R, name="Basic {R} Energy", cardType=5, energyType=FIRE),
    E_P: CardStat(E_P, name="Basic {P} Energy", cardType=5, energyType=PSYCHIC),
    E_D: CardStat(E_D, name="Basic {D} Energy", cardType=5, energyType=DARKNESS),
    E_F: CardStat(E_F, name="Basic {F} Energy", cardType=5, energyType=FIGHTING),
    PARTIAL: CardStat(PARTIAL, synthetic=True, name='Partial Table Body', hp=80,
                      energyType=FIGHTING, minAttackCost=2, maxDamage=30, attacks=(), cardType=0),
}
_ATTACKS = {
    JET_HEADBUTT: AttackStat(JET_HEADBUTT, damage=70, cost=1, energyTypes=(COLORLESS,)),
    # `nextTurnSameAttackLock` is NOT `nextTurnSelfLock`: Mega Brave's sentence names the ATTACK, so
    # the lock forbids one attack rather than the turn, and `strategy/sequence.py` prices them apart.
    PHANTOM_DIVE: AttackStat(PHANTOM_DIVE, damage=200, cost=2, energyTypes=(FIRE, PSYCHIC),
                             benchSpread=60),
    AURA_JAB: AttackStat(AURA_JAB, damage=130, cost=1, energyTypes=(FIGHTING,),
                         recoverN=3, recoverEnergyType=FIGHTING, recoverTarget="bench",
                         recoverSource="discard"),
    MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=2, energyTypes=(FIGHTING, FIGHTING),
                           nextTurnSameAttackLock=True),
    ACCELERATING_STAB: AttackStat(ACCELERATING_STAB, damage=30, cost=1, energyTypes=(FIGHTING,),
                                  nextTurnSameAttackLock=True),
    COSMIC_BEAM: AttackStat(COSMIC_BEAM, damage=70, cost=1, energyTypes=(FIGHTING,),
                            requiresBench=("Lunatone",), ignoresWeakness=True,
                            ignoresResistance=True),
    POWER_GEM: AttackStat(POWER_GEM, damage=50, cost=2, energyTypes=(FIGHTING, FIGHTING)),
    FULL_HEART: AttackStat(FULL_HEART, damage=0, cost=1, energyTypes=(COLORLESS,)),
    GUARDIAN_BURST: AttackStat(GUARDIAN_BURST, damage=160, cost=2,
                               energyTypes=(PSYCHIC, PSYCHIC),
                               requiresBench=("Uxie", "Azelf")),
}
_TAGS = {CRISPIN: ["energy_accel", "search", "tutor_energy"]}
_CLAUSES = {CRISPIN: [{"kind": "accel", "amount": 1, "source": "deck", "target": "any_pokemon",
                       "energy": "basic", "to_hand": 1, "distinct_types": True}]}

# The shipped dragapult Energy suite: 3×{R}, 3×{P}, 2×{D}.
DECK = [E_R] * 3 + [E_P] * 3 + [E_D] * 2 + [DRAGAPULT, CRISPIN]


def _combat():
    return CombatMath(DictCardStatProvider(_STATS, attacks=_ATTACKS),
                      functions=CardFunctions(_TAGS), transients=None,
                      effects=CardEffects(_CLAUSES))


def _poke(cid, *, hp, energies=(), attached_energy=None, serial=1, damage=0):
    """`energies=` is Basic-Energy SUGAR: card ids each providing one unit of their own id, right
    only because card 1-8 == EnergyType 1-8. Special Energy must go through `attached_energy=`."""
    if attached_energy is None:
        attached_energy = [(c, (c,)) for c in energies]
    return {"id": cid, "hp": hp - damage, "serial": serial,
            "energies": [u for _, units in attached_energy for u in units],
            "energyCards": [{"id": c, "serial": 0} for c, _ in attached_energy if c]}


def _player(*, active=None, bench=(), hand=(), discard=(), prize=4, hand_count=None,
            deck_count=20):
    """`prize` as an int = that many FACE-DOWN prizes (pre-anchor); a list is used verbatim."""
    return {
        "active": [active] if active else [],
        "bench": list(bench),
        "hand": [{"id": c} for c in hand],
        "handCount": len(hand) if hand_count is None else hand_count,
        "discard": [{"id": c} for c in discard],
        "prize": [None] * prize if isinstance(prize, int) else list(prize),
        "deckCount": deck_count,
        "poisoned": False, "burned": False, "asleep": False, "paralyzed": False, "confused": False,
    }


def _obs(me, opp, *, energy_attached=False, supporter_played=False, turn=5, own_prizes=None,
         stadium=()):
    obs = {"current": {"players": [me, opp], "yourIndex": 0, "turn": turn,
                       "energyAttached": energy_attached, "supporterPlayed": supporter_played,
                       "stadium": [{"id": s} for s in stadium]},
           "logs": []}
    if own_prizes is not None:
        obs["own_prizes"] = own_prizes
    return obs


def _model(me, opp, **kw):
    probe = kw.pop("probe", None)
    deck = kw.pop("deck", None)
    return StateModel.build(_obs(me, opp, **kw), combat=_combat(),
                            deck=DECK if deck is None else deck, probe=probe)


def _pult(**kw):
    return _poke(DRAGAPULT, hp=320, **kw)


# ── both sides read off one snapshot ───────────────────────────────────────────────────────────

def test_both_sides_are_read_from_one_snapshot():
    m = _model(_player(active=_pult(energies=[E_R]), bench=[_poke(MUNKIDORI, hp=70, serial=2)],
                       hand=[CRISPIN], prize=4),
               _player(active=_poke(RIOLU, hp=80, serial=3), bench=[_poke(MEGA_LUC, hp=340,
                                                                          serial=4)], prize=6))
    assert m.mine.active.card_id == DRAGAPULT
    assert m.mine.active.attached_types == {FIRE: 1}
    assert m.mine.active.energy_count == 1
    assert m.mine.hand_ids == (CRISPIN,)
    assert len(m.mine.bench) == 1 and m.mine.bodies[0] is m.mine.active
    assert m.theirs.active.card_id == RIOLU
    assert len(m.theirs.bodies) == 2
    assert m.mine.prizes_remaining == 4 and m.theirs.prizes_remaining == 6
    assert m.mine.turn == 5      # the turn's ONE home


def test_my_side_carries_cards_and_their_side_carries_only_a_count():
    """The engine gives the opponent's hand as None, so a contents read on their side must not EXIST
    rather than silently return empty."""
    m = _model(_player(active=_pult(), hand=[CRISPIN, E_R]),
               _player(active=_poke(RIOLU, hp=80), hand_count=7))
    assert m.mine.hand_ids == (CRISPIN, E_R)
    assert m.theirs.hand_size == 7
    assert not hasattr(m.theirs, "hand_ids")


def test_their_side_exposes_the_opponent_model_facade_rather_than_its_own_inference():
    sentinel = object()
    theirs = TheirSide(_player(active=_poke(RIOLU, hp=80)), combat=_combat(), opponent=sentinel)
    assert theirs.opponent is sentinel


# ── the discard is public in BOTH directions (POC-T0 / Issue #259) ─────────────────────────────

def test_the_full_discard_contents_are_readable_on_BOTH_sides():
    """A discard is public to both players, so the asymmetry governing `hand_ids` does not apply."""
    m = _model(_player(active=_pult(), discard=[CRISPIN, E_R]),
               _player(active=_poke(RIOLU, hp=80), discard=[MEGA_LUC, E_P, E_P]))
    assert m.mine.discard_ids == (CRISPIN, E_R)
    assert m.theirs.discard_ids == (MEGA_LUC, E_P, E_P)


def test_the_discard_read_is_ORDERED_and_keeps_duplicates():
    """A consumer reasoning about the most recently discarded card cannot recover that from
    `discard_energy_counts`, which is why the projection is not a substitute."""
    m = _model(_player(active=_pult()),
               _player(active=_poke(RIOLU, hp=80), discard=[E_P, MEGA_LUC, E_P]))
    assert m.theirs.discard_ids == (E_P, MEGA_LUC, E_P)


def test_the_discard_read_and_its_energy_projection_agree():
    """Two readings of one zone must not be able to disagree."""
    m = _model(_player(active=_pult()),
               _player(active=_poke(RIOLU, hp=80), discard=[E_P, MEGA_LUC, E_P, E_R]))
    assert m.theirs.discard_ids == (E_P, MEGA_LUC, E_P, E_R)
    assert m.theirs.discard_energy_counts == {PSYCHIC: 2, FIRE: 1}


def test_an_empty_discard_reads_as_empty_rather_than_unknown():
    """None for "nothing there" makes a sound read look like a missing one, and the fail-open
    callers then guess about a fact they can see."""
    m = _model(_player(active=_pult()), _player(active=_poke(RIOLU, hp=80)))
    assert m.theirs.discard_ids == () and m.mine.discard_ids == ()


# ── the new-in-play bit is readable off the SNAPSHOT, both sides (POC-T4/3 / Issue #391) ───────

def test_the_new_in_play_bit_is_readable_on_every_body_on_BOTH_sides():
    """`docs/rules.md` §4 — no evolving a body the turn it was put into play. The engine spells it
    `appearThisTurn` and carries it on the opponent's bodies too, so the fact is symmetric."""
    fresh = {**_poke(MUNKIDORI, hp=70, serial=2), "appearThisTurn": True}
    m = _model(_player(active=_pult(), bench=[fresh]),
               _player(active={**_poke(RIOLU, hp=80), "appearThisTurn": True},
                       bench=[_poke(MEGA_LUC, hp=340, serial=3)]))
    assert m.mine.active.new_in_play is False
    assert m.mine.bench[0].new_in_play is True
    assert m.theirs.active.new_in_play is True
    assert m.theirs.bench[0].new_in_play is False


def test_a_body_with_no_appear_bit_reads_as_IN_PLAY_SINCE_LAST_TURN():
    """Absent reads False, matching every raw read in the tree; a real observation always carries the
    bit, so only a hand-built board reaches this."""
    body = _poke(RIOLU, hp=80)
    assert "appearThisTurn" not in body                # the positive control on the premise
    m = _model(_player(active=body), _player(active=_pult()))
    assert m.mine.active.new_in_play is False


# ── the survival clock carries what the bypasses carry (POC-T0 / Issue #259) ───────────────────

def test_the_survival_clock_accepts_the_kwargs_the_bypasses_carry():
    """A route that silently answers a DIFFERENT question than the bypass is worse than no route;
    defaults must reproduce the old behaviour exactly, so the widening moves no decision."""
    m = _model(_player(active=_pult(), bench=[_poke(MUNKIDORI, hp=70, serial=2)]),
               _player(active=_poke(MEGA_LUC, hp=340, serial=3, energies=[E_R, E_R])))
    body = m.mine.active.body

    plain = m.theirs.turns_to_ko_me(body)
    assert m.theirs.turns_to_ko_me(body, my_benched=False) == plain      # default == old behaviour
    # every kwarg is ACCEPTED — T1 migrates the callers, T0 freezes the shape
    m.theirs.turns_to_ko_me(body, my_benched=True, my_bench=m.mine.bench_raws,
                            key_ids=frozenset({DRAGAPULT}), opp_active=None,
                            switch_enabler=True, context=None)


def test_the_survival_clock_memo_keys_on_its_arguments():
    """Two callers passing different harvest readings must not share one answer. Counts consults of
    `survival_clock` — `turns_to_ko_me` is its `.turns` view (ADR-0117), so one memo serves both."""
    m = _model(_player(active=_pult(), bench=[_poke(MUNKIDORI, hp=70, serial=2)]),
               _player(active=_poke(MEGA_LUC, hp=340, serial=3, energies=[E_R, E_R])))
    body = m.mine.active.body

    calls = []
    real = m.theirs._combat.survival_clock

    def counting(*a, **kw):
        calls.append(kw.get("my_benched"))
        return real(*a, **kw)

    m.theirs._combat.survival_clock = counting
    m.theirs.turns_to_ko_me(body, my_benched=False)
    m.theirs.turns_to_ko_me(body, my_benched=False)          # memo hit — no second consult
    m.theirs.turns_to_ko_me(body, my_benched=True)           # different question — must re-consult
    assert calls == [False, True]


# ── laziness ───────────────────────────────────────────────────────────────────────────────────

def test_build_computes_nothing_and_a_read_pays_only_for_what_it_touches():
    probe = set()
    m = _model(_player(active=_pult(energies=[E_R])), _player(active=_poke(RIOLU, hp=80)),
               probe=probe)
    assert probe == set()                                  # build computed nothing
    _ = m.mine.active.energy_count
    assert "mine.active" in probe                          # the bodies it had to resolve
    assert not any(f.startswith("theirs") for f in probe)  # their whole half untouched
    assert "mine.deck_energy_counts" not in probe          # nor any deck derivation


def test_a_probed_build_and_an_unprobed_build_agree():
    """Otherwise the Leaf Profile measures a fiction."""
    args = (_player(active=_pult(energies=[E_R, E_P]), hand=[CRISPIN]),
            _player(active=_poke(RIOLU, hp=80)))
    assert (_model(*args, probe=set()).mine.deck_energy_counts
            == _model(*args).mine.deck_energy_counts)


# ── purity ─────────────────────────────────────────────────────────────────────────────────────

def test_two_builds_on_one_observation_agree_field_for_field():
    """Without purity neither side-sharing nor the cost measurement is trustworthy."""
    me = _player(active=_pult(energies=[E_R]), hand=[CRISPIN], prize=4)
    opp = _player(active=_poke(RIOLU, hp=80, energies=[E_D]), prize=6)
    a, b = _model(me, opp), _model(me, opp)
    assert a.mine.deck_energy_counts == b.mine.deck_energy_counts
    assert a.mine.unseen_counts == b.mine.unseen_counts
    assert a.prize_race == b.prize_race
    assert a.opponent_fingerprint == b.opponent_fingerprint
    assert a.mine.active_famine == b.mine.active_famine


def test_reading_the_model_twice_is_stable():
    m = _model(_player(active=_pult(), hand=[CRISPIN]), _player(active=_poke(RIOLU, hp=80)))
    assert m.mine.active_famine is m.mine.active_famine
    assert m.mine.deck_energy_types == m.mine.deck_energy_types


def test_the_model_never_writes_the_carried_state_it_was_given():
    carried = CarriedState.of(phase_prev="RACE")
    m = StateModel.build(_obs(_player(active=_pult()), _player(active=_poke(RIOLU, hp=80))),
                         combat=_combat(), deck=DECK, carried=carried)
    _ = m.mine.active_famine, m.prize_race, m.opponent_fingerprint
    assert m.carried is carried and m.carried.get("phase_prev") == "RACE"


# ── the sharing guard: the wholesale fingerprint ────────────────────────────────────────────────
# Each MISS case is a real play of MINE that moves THEIR side.

def _their_base():
    return _player(active=_poke(RIOLU, hp=80, serial=3),
                   bench=[_poke(MEGA_LUC, hp=340, serial=4)], hand_count=5, deck_count=20)


def _fp(opp, me=None):
    return _model(me or _player(active=_pult()), opp).opponent_fingerprint


def test_judge_moves_their_hand_and_deck_counts_so_reuse_must_miss():
    """Judge touches NOTHING an enumerated body/damage/prize/discard fingerprint would look at."""
    after = _their_base() | {"handCount": 4, "deckCount": 21}
    assert _fp(_their_base()) != _fp(after)


def test_a_gust_moves_which_body_is_active_so_reuse_must_miss():
    """A set-shaped fingerprint calls a gusted board unchanged, but every clock read keys off who is
    Active."""
    gusted = _player(active=_poke(MEGA_LUC, hp=340, serial=4),
                     bench=[_poke(RIOLU, hp=80, serial=3)], hand_count=5, deck_count=20)
    assert _fp(_their_base()) != _fp(gusted)


def test_adrena_brain_moving_damage_onto_their_body_makes_reuse_miss():
    damaged = _player(active=_poke(RIOLU, hp=80, serial=3, damage=30),
                      bench=[_poke(MEGA_LUC, hp=340, serial=4)], hand_count=5, deck_count=20)
    assert _fp(_their_base()) != _fp(damaged)


def test_stripping_their_energy_makes_reuse_miss():
    loaded = _player(active=_poke(RIOLU, hp=80, serial=3, energies=[E_D]),
                     bench=[_poke(MEGA_LUC, hp=340, serial=4)], hand_count=5, deck_count=20)
    assert _fp(_their_base()) != _fp(loaded)


def test_inflicting_a_condition_makes_reuse_miss():
    confused = _their_base() | {"confused": True}
    assert _fp(_their_base()) != _fp(confused)


def test_moving_a_card_into_their_discard_makes_reuse_miss():
    """The wholesale hash earning its keep: `discard_ids` was ADDED and the guard needed no change,
    where a hand-picked fingerprint would have failed OPEN until someone extended it."""
    discarded = _their_base() | {"discard": [{"id": MEGA_LUC}]}
    assert _fp(_their_base()) != _fp(discarded)


def test_taking_a_prize_makes_reuse_miss():
    assert _fp(_their_base()) != _fp(_their_base() | {"prize": [None] * 3})


def test_a_stadium_change_makes_reuse_miss():
    """The stadium is SHARED, not side-scoped, yet it changes what their bodies effectively are."""
    me, opp = _player(active=_pult()), _their_base()
    assert (_model(me, opp).opponent_fingerprint
            != _model(me, opp, stadium=(1248,)).opponent_fingerprint)


@pytest.mark.parametrize("me_after", [
    pytest.param(_player(active=_pult(energies=[E_R])), id="i_attached_an_energy"),
    pytest.param(_player(active=_pult(), bench=[_poke(MUNKIDORI, hp=70, serial=2)]),
                 id="i_benched_a_body"),
    pytest.param(_player(active=_pult(), hand=[CRISPIN]), id="i_drew_a_card"),
    pytest.param(_player(active=_pult(), discard=[E_R]), id="i_discarded"),
])
def test_my_own_plays_leave_their_half_reusable(me_after):
    """The cache's value: their expensive clock derivations survive the selects of my turn."""
    opp = _their_base()
    before = _model(_player(active=_pult()), opp)
    after = _model(me_after, opp)
    assert before.opponent_fingerprint == after.opponent_fingerprint
    assert after.shares_opponent_with(before) is True


def test_shares_opponent_with_is_false_across_a_disruption_and_never_none_safe():
    opp_before, opp_after = _their_base(), _their_base() | {"handCount": 4}
    assert _model(_player(active=_pult()), opp_after).shares_opponent_with(
        _model(_player(active=_pult()), opp_before)) is False
    assert _model(_player(active=_pult()), opp_before).shares_opponent_with(None) is False


def test_a_reused_their_side_is_the_same_object():
    """Sharing is object reuse, not a re-derivation that happens to agree."""
    opp = _their_base()
    first = _model(_player(active=_pult()), opp)
    second = StateModel.build(_obs(_player(active=_pult(energies=[E_R])), opp),
                              combat=_combat(), deck=DECK, their_side=first.theirs)
    assert second.theirs is first.theirs


# ── the Count Triple ───────────────────────────────────────────────────────────────────────────

def test_pre_anchor_the_legs_diverge():
    m = _model(_player(active=_pult(), prize=4), _player(active=_poke(RIOLU, hp=80)))
    d = m.mine.deck_energy_counts[DARKNESS]
    assert d.floor == 0                      # both {D} could be prized
    assert 0.0 < d.expected < 2.0            # a fraction — never comparable to a cost
    assert d.ceiling == 2
    assert d.floor < d.ceiling and d.possible is True     # legs apart: not yet anchored


def test_anchored_all_three_legs_collapse_to_the_exact_count():
    """Anchored, the honest answer is an integer, so no consumer branches on the regime."""
    m = _model(_player(active=_pult(), prize=4), _player(active=_poke(RIOLU, hp=80)),
               own_prizes={E_R: 1, DRAGAPULT: 1})
    d = m.mine.deck_energy_counts[DARKNESS]
    assert (d.floor, d.expected, d.ceiling) == (2, 2.0, 2)
    assert d.floor == d.ceiling                           # legs collapsed: anchored


def test_the_pigeonhole_floor_is_sound_when_copies_outnumber_hidden_prizes():
    """`floor` is the only leg safe to compare against a cost."""
    m = _model(_player(active=_pult(), prize=2), _player(active=_poke(RIOLU, hp=80)))
    assert m.mine.deck_energy_counts[FIRE].floor >= 1


def test_seen_copies_leave_the_unseen_pool():
    m = _model(_player(active=_pult(energies=[E_P]), discard=[E_P], prize=4),
               _player(active=_poke(RIOLU, hp=80)))
    assert m.mine.deck_energy_counts[PSYCHIC].ceiling == 1


def test_the_ceiling_leg_reproduces_the_sound_type_set_gate():
    """The shipped gate is *not-provably-empty*; the triple must SUBSUME it, not add a third
    epistemic."""
    m = _model(_player(active=_pult(energies=[E_P, E_P]), discard=[E_P], prize=4),
               _player(active=_poke(RIOLU, hp=80)))
    possible = {t for t, c in m.mine.deck_energy_counts.items() if c.possible}
    assert possible == m.mine.deck_energy_types


def test_a_provably_exhausted_type_is_absent_from_both_reads():
    """Fail-CLOSED on yield is the direction; the triple must not soften it."""
    m = _model(_player(active=_pult(energies=[E_P, E_P]), discard=[E_P, E_R], prize=4),
               _player(active=_poke(RIOLU, hp=80)))
    assert m.mine.deck_energy_counts.get(PSYCHIC, CountTriple()).possible is False
    assert PSYCHIC not in m.mine.deck_energy_types


def test_count_triple_helper_fails_closed_on_unreadable_inputs():
    assert count_triple("?", 2, 10) == CountTriple()
    assert count_triple(2, 2, 0) == CountTriple()             # no deck left to hold anything


def test_probability_leg_tracks_the_depletion_ramp():
    """ADR-0074 / Issue #175: `p_any` is the honest middle the two boolean legs collapse — neither
    boolean distinguishes a free bet from a coin flip."""
    thin, deep = count_triple(1, 6, 40), count_triple(3, 6, 51)
    assert (thin.floor, thin.possible) == (0, True)           # booleans: identical readings...
    assert (deep.floor, deep.possible) == (0, True)
    assert round(1 - deep.p_any, 4) == 0.0007                 # ...but 0.07% vs 13% whiff
    assert round(1 - thin.p_any, 3) == 0.130


def test_probability_leg_collapses_with_the_others_once_anchored():
    """The weighting is a NO-OP on every anchored frame — Issue #175's no-regression guarantee."""
    assert count_triple(2, 0, 30).p_any == 1.0                # anchored: certainly present
    assert count_triple(0, 6, 40).p_any == 0.0                # provably empty: certainly absent
    assert count_triple(7, 6, 40).p_any == 1.0                # pigeonhole surplus: certainly present


def test_deck_energy_p_never_resurrects_a_type_the_sound_leg_dropped():
    """A probability sharpens the uncertain middle; it may never claim a type proven gone."""
    m = _model(_player(active=_pult(energies=[E_P, E_P]), discard=[E_P, E_R], prize=4),
               _player(active=_poke(RIOLU, hp=80)))
    assert m.mine.deck_energy_p.get(PSYCHIC, 0.0) == 0.0
    assert PSYCHIC not in m.mine.deck_energy_types            # agrees with the sound leg


def test_deck_energy_p_is_a_projection_of_the_one_derivation():
    m = _model(_player(active=_pult(energies=[E_R]), hand=[CRISPIN], prize=4),
               _player(active=_poke(RIOLU, hp=80)))
    for t, c in m.mine.deck_energy_counts.items():
        p = m.mine.deck_energy_p[t]
        assert (p > 0.0) == (t in m.mine.deck_energy_types)
        if t in m.mine.deck_energy_types_provable:
            assert p == 1.0


def test_expected_unions_additively_across_types():
    """ADR-0077 decision 2: every type's leg divides the same `(deck, prizes_hidden)`, so the sum
    over types IS the aggregate — never re-shape this into a per-type max or a parallel triple."""
    m = _model(_player(active=_pult(), prize=4), _player(active=_poke(RIOLU, hp=80)))
    mine = m.mine
    union = sum(c.expected for c in mine.deck_energy_counts.values())
    aggregate = count_triple(sum(n for cid, n in mine.unseen_counts.items()
                                 if _STATS[cid].is_typed_basic_energy),
                             mine.prizes_hidden, mine.deck_count).expected
    assert union == pytest.approx(aggregate)
    assert union > 0.0                                       # the suite is live — not a vacuous pass


def test_p_any_does_NOT_union_additively_the_way_expected_does():
    """Summing `p_any` over types can exceed 1.0, which is why the untyped union is licensed on
    `expected` ALONE. Asserted so the asymmetry is not mistaken for an oversight."""
    m = _model(_player(active=_pult(), prize=4), _player(active=_poke(RIOLU, hp=80)))
    assert sum(m.mine.deck_energy_p.values()) > 1.0          # not a probability — never sum these


def test_unseen_counts_is_one_derivation_over_every_visible_zone():
    m = _model(_player(active=_pult(energies=[E_R]), hand=[CRISPIN], discard=[E_P], prize=4),
               _player(active=_poke(RIOLU, hp=80)))
    unseen = m.mine.unseen_counts
    assert unseen[E_R] == 2 and unseen[E_P] == 2              # 3 each, one of each seen
    assert DRAGAPULT not in unseen                            # the only copy is in play


# ── the affordability family, read through the model ───────────────────────────────────────────

def test_f70_is_not_a_famine_when_read_off_the_model():
    """Dragapult ex at ZERO Energy, Crispin in hand, manual attach unspent — reaches {R}{P}."""
    m = _model(_player(active=_pult(), hand=[CRISPIN], prize=4),
               _player(active=_poke(RIOLU, hp=80)))
    assert m.mine.reachable_attach(m.mine.active, PHANTOM_DIVE) is True
    assert m.mine.active_famine is False


def test_a_provable_famine_still_fires():
    """Fail-closed stays fail-closed through the model: empty hand, manual attach spent."""
    m = _model(_player(active=_pult(), prize=4), _player(active=_poke(RIOLU, hp=80)),
               energy_attached=True)
    assert m.mine.active_famine is True


def test_the_budget_is_per_body_and_memoised_per_body():
    """A bench-restricted clause funds one body and not another, so the Budget is keyed per body."""
    m = _model(_player(active=_pult(), bench=[_poke(MUNKIDORI, hp=70, serial=2)], hand=[CRISPIN]),
               _player(active=_poke(RIOLU, hp=80)))
    assert m.mine.attach_budget(m.mine.active) is m.mine.attach_budget(m.mine.active)
    assert m.mine.attach_budget(m.mine.bench[0]) is not m.mine.attach_budget(m.mine.active)
    assert m.mine.attach_budget(None) is None


def test_reachable_attach_answers_for_any_body_not_just_the_active():
    m = _model(_player(active=_poke(MUNKIDORI, hp=70), bench=[_pult(serial=2)], hand=[CRISPIN]),
               _player(active=_poke(RIOLU, hp=80)))
    assert m.mine.reachable_attach(m.mine.bench[0], PHANTOM_DIVE) is True


def test_readiness_p_is_certain_when_the_budget_already_reaches_and_closed_without_an_enabler():
    m = _model(_player(active=_pult(), hand=[CRISPIN]), _player(active=_poke(RIOLU, hp=80)))
    # Crispin REACHES only through a deck fetch, which can whiff, so "already reaches" is not
    # certainty; `weighted=False` recovers the fail-open 1.0 (ADR-0074).
    assert 0.0 < m.mine.readiness_p(m.mine.active, PHANTOM_DIVE) < 1.0
    assert m.mine.readiness_p(m.mine.active, PHANTOM_DIVE, weighted=False) == 1.0
    dry = _model(_player(active=_pult()), _player(active=_poke(RIOLU, hp=80)),
                 energy_attached=True)
    assert dry.mine.readiness_p(dry.mine.active, PHANTOM_DIVE) == 0.0


def test_famine_makes_no_claim_without_an_active():
    m = _model(_player(), _player(active=_poke(RIOLU, hp=80)))
    assert m.mine.active_famine is False
    assert m.mine.reachable_attach(None) is False


# ── their clocks, read through the model ───────────────────────────────────────────────────────

def test_the_incoming_curve_is_memoised_per_turn_and_agrees_with_the_one_step_read():
    m = _model(_player(active=_pult(energies=[E_R])),
               _player(active=_poke(RIOLU, hp=80, energies=[E_D]),
                       bench=[_poke(MEGA_LUC, hp=340, serial=4, energies=[E_D])]))
    body = m.mine.active_raw
    assert m.theirs.reachable_incoming(body) == m.theirs.incoming(body, 1)
    assert m.theirs.incoming(body, 2) >= m.theirs.incoming(body, 1)


def test_their_discard_energy_is_a_sound_public_count():
    """Both discards are public, so this is a COUNT and never an estimate."""
    m = _model(_player(active=_pult()),
               _player(active=_poke(RIOLU, hp=80), discard=[E_D, E_D, CRISPIN]))
    assert m.theirs.discard_energy_counts == {DARKNESS: 2}


# ── the prize race ─────────────────────────────────────────────────────────────────────────────

def test_the_prize_race_is_one_cross_side_derivation():
    m = _model(_player(active=_pult(), prize=2),
               _player(active=_poke(RIOLU, hp=80, serial=3),
                       bench=[_poke(MEGA_LUC, hp=340, serial=4)], prize=5))
    race = m.prize_race
    assert (race.my_prizes_remaining, race.opp_prizes_remaining) == (2, 5)
    # The two counts ARE the composite; per-body prize YIELD is read off the BodyView instead.
    assert race.opp_prizes_remaining - race.my_prizes_remaining == 3     # positive = I am ahead
    assert {b.card_id: b.prize_value for b in m.theirs.bodies}[MEGA_LUC] == 3


def test_prize_yield_stays_card_knowledge_on_the_oracle():
    """The model holds the answer; the combat oracle owns the arithmetic (ADR-0052)."""
    m = _model(_player(active=_pult()), _player(active=_poke(MEGA_LUC, hp=340)))
    assert m.theirs.active.prize_value == _combat().prize_value({"id": MEGA_LUC})


# ── the Carried State channel ──────────────────────────────────────────────────────────────────

def test_the_channel_carries_declared_members_and_defaults_absent_ones():
    c = CarriedState.of(phase_prev="STABILIZE")
    assert c.get("phase_prev") == "STABILIZE"
    assert c.get("known_top") is None                        # fail-closed: absent ≠ confident
    assert c.get("known_top", "fallback") == "fallback"


def test_the_channel_rejects_undeclared_members():
    """Narrow BY CONSTRUCTION rather than by convention."""
    with pytest.raises(ValueError):
        CarriedState.of(some_new_memory=1)


def test_an_update_returns_a_new_snapshot_and_never_mutates_the_old():
    """Nothing mutates as a side effect of being computed; the caller stores what it is handed."""
    before = CarriedState.of(phase_prev="RACE")
    after = CarriedState.of(phase_prev="STABILIZE")
    assert before.get("phase_prev") == "RACE"
    assert after.get("phase_prev") == "STABILIZE"
    assert before is not after


def test_known_top_is_declared_so_149_attaches_without_reshaping_the_channel():
    """The seat exists, the belief does not — an unset member reads as the ordinary unknown."""
    assert "known_top" in CarriedState.MEMBERS
    assert CarriedState.of(known_top=(163,)).get("known_top") == (163,)
    assert CarriedState().get("known_top") is None


# ── my armed-clock: the mirror of TheirSide's deny read (ADR-0070 §6) ──────────────────────────

def test_my_turns_to_afford_is_the_hop_aware_armed_clock():
    """The earliest turn MY line is armed: MAX of the energy-deficit leg and the FORWARD-HOP leg,
    never their sum."""
    m = _model(_player(active=_pult(energies=[E_R, E_P]), bench=[], prize=4),
               _player(active=_poke(RIOLU, hp=80, serial=3), bench=[], prize=6))
    # Dragapult ex already pays Phantom Dive's {R}{P} -> armed now, no hops owed.
    assert m.mine.turns_to_afford(m.mine.active) == 0


def test_my_armed_clock_counts_the_energy_deficit():
    m = _model(_player(active=_pult(energies=[]), bench=[], prize=4),
               _player(active=_poke(RIOLU, hp=80, serial=3), bench=[], prize=6))
    # 0 attached against Phantom Dive's 2-cost, one attach a turn -> 2 turns.
    assert m.mine.turns_to_afford(m.mine.active) == 2


def test_my_armed_clock_is_none_for_an_unknown_body():
    m = _model(_player(active=_pult(energies=[]), bench=[], prize=4),
               _player(active=_poke(RIOLU, hp=80, serial=3), bench=[], prize=6))
    assert m.mine.turns_to_afford(None) is None


# ── the Provable Budget and the famine read (Issue #142, ADR-0067 amendment) ─────────────────────────

def _f70_shape(**kw):
    """Active Dragapult ex at ZERO Energy, Crispin the only hand card, the Energy suite in deck."""
    return _model(_player(active=_pult(energies=[]), hand=[CRISPIN], prize=4),
                  _player(active=_poke(RIOLU, hp=80, serial=3), prize=6), **kw)


def test_the_provable_deck_leg_is_empty_pre_anchor_on_a_thin_suite():
    """`floor = max(0, unseen - prizes_hidden)`, so a 3-copy type against 4 hidden prizes proves
    nothing — which is why the famine premise keeps the OPEN leg (ADR-0067)."""
    m = _f70_shape()
    assert m.mine.deck_energy_types == frozenset({FIRE, PSYCHIC, DARKNESS})
    assert m.mine.deck_energy_types_provable == frozenset()


def test_the_provable_deck_leg_fills_once_the_prizes_are_anchored():
    """Anchored, the two Budget legs stop differing — the regime ADR-0067 says no consumer branches
    on."""
    m = _f70_shape(own_prizes={MUNKIDORI: 4})
    assert m.mine.deck_energy_types_provable == m.mine.deck_energy_types
    assert FIRE in m.mine.deck_energy_types_provable


def test_the_famine_read_dissolves_on_the_f70_shape():
    """Crispin attaches one Basic AND hands a second of a DIFFERENT type that the unspent manual
    attach then plays, so Dragapult ex reaches {R}{P} from zero."""
    assert _f70_shape().mine.active_famine is False


def test_the_provable_leg_still_reads_the_f70_shape_as_unreachable():
    """Nothing about that deck fetch is PROVABLE pre-anchor, so a consumer about to spend a card
    that expires unused gets the conservative answer."""
    m = _f70_shape()
    assert m.mine.reachable_attach(m.mine.active) is True
    assert m.mine.reachable_attach(m.mine.active, provable=True) is False


def test_the_two_legs_agree_once_the_prizes_are_anchored():
    m = _f70_shape(own_prizes={MUNKIDORI: 4})
    assert m.mine.reachable_attach(m.mine.active, provable=True) is True


def test_a_provable_famine_is_a_famine_on_both_legs():
    """An empty hand and no attach reaches nothing however the deck leg is read."""
    m = _model(_player(active=_pult(energies=[]), hand=[], prize=4),
               _player(active=_poke(RIOLU, hp=80, serial=3), prize=6), energy_attached=True)
    assert m.mine.active_famine is True
    assert m.mine.reachable_attach(m.mine.active, provable=True) is False


def test_paralysis_is_a_famine_however_rich_the_budget():
    """`rulebook.txt` L206: a Paralyzed Pokemon "cannot attack or retreat". The Energy math says
    Phantom Dive is paid; famine must agree with the RULES, not the math."""
    me = _player(active=_pult(energies=[E_R, E_P]), hand=[CRISPIN], prize=4)
    me["paralyzed"] = True
    m = _model(me, _player(active=_poke(RIOLU, hp=80, serial=3), prize=6))
    assert m.mine.reachable_attach(m.mine.active) is True      # the oracle stays a COST question
    assert m.mine.attack_blocked is True
    assert m.mine.active_famine is True


def test_sleep_is_a_famine_however_rich_the_budget():
    """`rulebook.txt` L190: "If a Pokemon is Asleep, it cannot attack or retreat.\""""
    me = _player(active=_pult(energies=[E_R, E_P]), prize=4)
    me["asleep"] = True
    m = _model(me, _player(active=_poke(RIOLU, hp=80, serial=3), prize=6))
    assert m.mine.active_famine is True


def test_a_rotating_condition_that_does_not_block_attacking_is_not_a_famine():
    """Only Asleep and Paralyzed stop a Pokemon attacking (`rulebook.txt` L215); Confused flips a
    coin, it does not forbid the attack."""
    me = _player(active=_pult(energies=[E_R, E_P]), prize=4)
    me["confused"], me["poisoned"], me["burned"] = True, True, True
    m = _model(me, _player(active=_poke(RIOLU, hp=80, serial=3), prize=6))
    assert m.mine.attack_blocked is False
    assert m.mine.active_famine is False


def test_the_first_player_cannot_attack_on_turn_one():
    """`rules.md` §first-turn / rulebook L152. `turn <= 1` is the idiom every other site uses."""
    m = _model(_player(active=_pult(energies=[E_R, E_P]), prize=4),
               _player(active=_poke(RIOLU, hp=80, serial=3), prize=6), turn=1)
    assert m.mine.attack_blocked is True
    assert m.mine.active_famine is True


def test_a_body_less_side_makes_no_famine_claim_rather_than_crashing():
    """Fail-OPEN, the opposite of the oracle underneath: `reachable_attach` returns False for "I
    cannot tell", and negating that turns silence into a PROVABLE famine and fires the stall."""
    m = _model(_player(prize=4), _player(active=_poke(RIOLU, hp=80, serial=3), prize=6))
    assert m.mine.active_famine is False


# ── the payoff a body can actually reach — the bench-partner gate (Issue #287) ─────────────────
# Mesprit is pool-only, carried for the shape Solrock cannot test: an "and" list on a 2-attack body.


def test_a_bench_gated_payoff_is_zero_without_its_partner():
    """`CardStat.maxDamage` is a PRINTED roll-up and no printed number carries a board condition, so
    the payoff read asks the damage oracle, which owns the `requiresBench` gate."""
    m = _model(_player(active=_poke(SOLROCK, hp=110, energies=[]),
                       bench=[_poke(RIOLU, hp=80, serial=2)], prize=4),
               _player(active=_pult(serial=3), prize=6))
    assert m.mine.active.stat.maxDamage == 70, "fixture drift: the PRINTED roll-up is the bug"
    assert m.mine.attack_payoff(m.mine.active).damage == 0.0


def test_benching_the_partner_restores_the_gated_payoff():
    """The half that makes the term MOVE, so the play enabling the attacker is visible to any
    consumer that differences this read."""
    m = _model(_player(active=_poke(SOLROCK, hp=110),
                       bench=[_poke(LUNATONE, hp=110, serial=2)], prize=4),
               _player(active=_pult(serial=3), prize=6))
    assert m.mine.attack_payoff(m.mine.active) == (COSMIC_BEAM, 70.0)


def test_the_partner_must_be_BENCHED_not_merely_in_play():
    """Card text is "on your Bench", so a Lunatone in the ACTIVE spot does not satisfy it — the
    distinction a "Lunatone in play" reading silently loses."""
    m = _model(_player(active=_poke(LUNATONE, hp=110),
                       bench=[_poke(SOLROCK, hp=110, serial=2)], prize=4),
               _player(active=_pult(serial=3), prize=6))
    assert m.mine.attack_payoff(m.mine.bench[0]).damage == 0.0


def test_an_AND_list_needs_every_named_partner():
    """A gate that credited the 160 on a partial bench would price a phantom."""
    def _mesprit_with(*bench):
        return _model(_player(active=_poke(MESPRIT, hp=70),
                              bench=[_poke(c, hp=70, serial=i + 2) for i, c in enumerate(bench)],
                              prize=4),
                      _player(active=_pult(serial=9), prize=6))
    half = _mesprit_with(UXIE)
    assert half.mine.attack_payoff(half.mine.active).damage == 0.0
    both = _mesprit_with(UXIE, AZELF)
    assert both.mine.attack_payoff(both.mine.active) == (GUARDIAN_BURST, 160.0)


def test_a_gated_maximum_falls_back_to_the_best_UNGATED_attack():
    """Attack id included: the odds leg is asked about THAT attack, and a payoff paired with another
    attack's probability is the saturation defect `payoff` exists to avoid."""
    m = _model(_player(active=_poke(MESPRIT, hp=70), bench=[_poke(UXIE, hp=70, serial=2)],
                       prize=4),
               _player(active=_pult(serial=9), prize=6))
    assert m.mine.attack_payoff(m.mine.active).attack_id == FULL_HEART


def test_an_UNGATED_body_reads_exactly_its_printed_roll_up():
    """The payoff read is matchup-FREE, so no Weakness/Resistance from the defender leaks in."""
    m = _model(_player(active=_poke(MEGA_LUC, hp=340), bench=[], prize=4),
               _player(active=_pult(serial=3), prize=6))
    assert m.mine.attack_payoff(m.mine.active) == (MEGA_BRAVE, 270.0)
    assert m.mine.attack_payoff(m.mine.active).damage == float(m.mine.active.stat.maxDamage)


def test_the_payoff_of_an_unreadable_CARD_makes_no_claim():
    """Fail-CLOSED: no attack id, rather than a zero a consumer could mistake for a priced body."""
    m = _model(_player(active=_poke(9999, hp=80), prize=4),
               _player(active=_pult(serial=3), prize=6))
    assert m.mine.attack_payoff(m.mine.active) == (None, 0.0)      # card 9999 has no CardStat
    assert m.mine.attack_payoff(None) == (None, 0.0)


def test_an_UNRESOLVABLE_attack_table_degrades_to_the_card_level_roll_up():
    """A partial provider must not silently zero a real attacker. The bench gate is a new REASON to
    price 0, never a new way to reach one — a missing record is an unreadable condition, not a fail."""
    m = _model(_player(active=_poke(PARTIAL, hp=80), prize=4),
               _player(active=_pult(serial=3), prize=6))
    assert m.mine.active.stat.maxDamage == 30 and not m.mine.active.stat.attacks
    assert m.mine.attack_payoff(m.mine.active) == (None, 30.0)


def test_both_sides_can_be_asked_for_a_payoff():
    """The gate is a fact about the ATTACKER's own bench, so the question lives on the side base."""
    m = _model(_player(active=_pult(), prize=4),
               _player(active=_poke(SOLROCK, hp=110, serial=3),
                       bench=[_poke(LUNATONE, hp=110, serial=4)], prize=6))
    assert m.theirs.attack_payoff(m.theirs.active) == (COSMIC_BEAM, 70.0)


def test_bench_names_is_the_bench_and_only_the_bench():
    """One home for the fact the gate reads: two comprehensions over `self.bench` is the drift the
    ONE-context ruling (Issue #279) exists to prevent."""
    m = _model(_player(active=_poke(SOLROCK, hp=110),
                       bench=[_poke(LUNATONE, hp=110, serial=2), _poke(RIOLU, hp=80, serial=3)],
                       prize=4),
               _player(active=_pult(serial=9), prize=6))
    assert m.mine.bench_names == ("Lunatone", "Riolu")
    assert m.mine.damage_facts.bench_names == m.mine.bench_names


# ── the ATTACK PROFILE — Issue #384's ONE new accessor ─────────────────────────────────────────
# A SIBLING of `attack_payoff`, not a widening: it answers about ONE named attack, on BOTH sides.

#: My Mega Lucario ex line, so `forward_index` sees Riolu -> Mega Lucario ex (a SINGLE hop) and the
#: recover rider's recipient-need leg has a forward form to measure against.
LUC_DECK = [E_F] * 4 + [RIOLU] * 3 + [MEGA_LUC] * 3


def _luc_model(*, my_energies=(E_F, E_F), bench=(), discard=(), their_active=None,
               their_bench=(), energy_attached=True):
    """`energy_attached=True` by default, so the Attach Budget adds nothing and affordability is a
    fact about what is ATTACHED rather than about what the deck might still supply."""
    return _model(
        _player(active=_poke(MEGA_LUC, hp=340, energies=list(my_energies)), bench=list(bench),
                discard=list(discard), prize=4),
        _player(active=their_active or _pult(serial=9), bench=list(their_bench), prize=4),
        deck=LUC_DECK, energy_attached=energy_attached)


def test_attack_profile_carries_the_rider_and_lock_fields_attack_payoff_drops():
    """`attack_payoff` returns `(attack_id, damage)` alone, but every rider and lock field is an
    input `attack_ev` takes — without them `state_value` must reach past the model (Issue #384)."""
    m = _luc_model()
    jab = m.attack_profile(m.mine.active, AURA_JAB)
    brave = m.attack_profile(m.mine.active, MEGA_BRAVE)
    assert jab.attack_id == AURA_JAB and brave.attack_id == MEGA_BRAVE
    assert jab.recover_n == 3                                   # Aura Jab: the recycle rider…
    assert (jab.self_lock, jab.same_attack_lock) == (False, False)      # …and no lock
    assert brave.recover_n == 0                                 # Mega Brave: no rider…
    assert (brave.self_lock, brave.same_attack_lock) == (False, True)   # …and a SAME-ATTACK lock


def test_attack_profile_prices_damage_against_their_active_at_all_three_bounds():
    """A DETERMINISTIC attack reads printed under every bound, so floor == exact == ceiling and the
    caller's coin policy needs no branch for the degenerate case."""
    m = _luc_model()
    jab = m.attack_profile(m.mine.active, AURA_JAB)
    assert (jab.damage, jab.damage_floor, jab.damage_ceiling) == (130.0, 130.0, 130.0)
    brave = m.attack_profile(m.mine.active, MEGA_BRAVE)
    assert (brave.damage, brave.damage_floor, brave.damage_ceiling) == (270.0, 270.0, 270.0)


def test_attack_profile_carries_a_matchup_free_printed_read_beside_the_matchup_one():
    """`damage` asks against the body in front of me, so Weakness/Resistance/prevention reach it;
    `printed` is matchup-FREE and is what the horizon-2 leg must use — that defender is not this one."""
    m = _luc_model(their_active=_poke(LUNATONE, hp=110, serial=9))
    jab = m.attack_profile(m.mine.active, AURA_JAB)
    assert jab.damage == 130.0 and jab.printed == 130.0


def test_attack_profile_affordability_is_the_attach_budgets_answer():
    """`threat.blind_to` forbids a second opinion about affordability outright."""
    m = _luc_model(my_energies=(E_F,))
    assert m.attack_profile(m.mine.active, AURA_JAB).affordable is True        # {F}: paid
    assert m.attack_profile(m.mine.active, MEGA_BRAVE).affordable is False     # {F}{F}: not


def test_attack_profile_recover_units_is_the_min_of_the_three_closed_form_bounds():
    """The three bounds are the printed ceiling, the SOURCE zone's matching fuel, and the recipients'
    NEED — measured against the FORWARD form, so a Riolu counts what its Mega Brave will cost."""
    m = _luc_model(bench=[_poke(RIOLU, hp=80, serial=2)], discard=[E_F] * 4)
    assert m.attack_profile(m.mine.active, AURA_JAB).recover_units == 2.0


def test_attack_profile_recover_units_binds_on_the_fuel_when_the_discard_is_thin():
    """The SOURCE-zone bound, isolated: Aura Jab sources from the PUBLIC discard, so a sound count."""
    m = _luc_model(bench=[_poke(RIOLU, hp=80, serial=2)], discard=[E_F])
    assert m.attack_profile(m.mine.active, AURA_JAB).recover_units == 1.0


def test_attack_profile_recover_units_is_zero_with_no_recipient_in_scope():
    """Aura Jab's `recoverTarget` is "bench", so an empty Bench attaches nothing however full the
    discard is."""
    m = _luc_model(discard=[E_F] * 4)
    assert m.attack_profile(m.mine.active, AURA_JAB).recover_units == 0.0


def test_attack_profile_recover_units_is_zero_for_an_attack_with_no_rider():
    m = _luc_model(bench=[_poke(RIOLU, hp=80, serial=2)], discard=[E_F] * 4)
    assert m.attack_profile(m.mine.active, MEGA_BRAVE).recover_units == 0.0


def test_attack_profile_reports_their_reachable_bench_and_the_riders_own_allocation():
    """`rider_targets` is the (hp, prize) of their benched bodies a rider can reach;
    `spread_ko_prizes` is the shipped knapsack's answer about WHERE the counters land."""
    m = _model(
        _player(active=_pult(energies=[E_R, E_P]), prize=4),
        _player(active=_poke(RIOLU, hp=80, serial=9),
                bench=[_poke(RIOLU, hp=40, serial=10), _poke(MEGA_LUC, hp=60, serial=11)],
                prize=4),
        deck=DECK, energy_attached=True)
    dive = m.attack_profile(m.mine.active, PHANTOM_DIVE)
    assert dive.bench_spread == 60 and dive.bench_snipe == 0
    assert sorted(dive.rider_targets) == [(40, 1), (60, 3)]
    # 60 counters: Mega Lucario ex alone (cost 60, 3 prizes) beats Riolu alone (cost 40, 1 prize).
    assert dive.spread_ko_prizes == 3
    assert dive.snipe_ko_prizes == 0


def test_attack_profile_fails_closed_on_an_attack_that_does_not_resolve():
    """A profile is still RETURNED, so the caller has no None branch to forget."""
    m = _luc_model()
    ghost = m.attack_profile(m.mine.active, 999999)
    assert ghost.attack_id == 999999 and ghost.affordable is False
    assert (ghost.damage, ghost.damage_floor, ghost.damage_ceiling, ghost.printed) == (0.0,) * 4
    assert (ghost.bench_snipe, ghost.bench_spread, ghost.recover_n,
            ghost.recover_units) == (0, 0, 0, 0.0)


def test_attack_profile_fails_closed_on_a_body_that_is_not_there():
    m = _luc_model()
    empty = m.attack_profile(None, AURA_JAB)
    assert empty.affordable is False and empty.damage == 0.0 and empty.rider_targets == ()


# ── the Needs supplier is BOARD-BOUND, so a hypothetical resolves its OWN hand (Issue #400 P2) ────


def test_a_board_bound_needs_supplier_is_REBOUND_by_rebuilt_not_inherited():
    """The supplier takes `(obs, my_index)` and `build` binds it to the board it is BUILDING, so
    re-binding is a property of the type rather than of every caller remembering (Issue #400 P2)."""
    asked = []

    def supplier(obs, my_index):
        seat = ((obs.get("current") or {}).get("players") or [{}])[my_index] or {}
        asked.append(tuple(c["id"] for c in (seat.get("hand") or ())))
        return None

    first = _obs(_player(active=_pult(), hand=[CRISPIN], prize=4),
                 _player(active=_poke(RIOLU, hp=80, serial=3), prize=4))
    model = StateModel.build(first, combat=_combat(), deck=DECK, needs=supplier)
    assert model.mine.needs is None
    assert asked == [(CRISPIN,)], "the supplier was asked about the board it was built on"

    second = copy.deepcopy(first)
    second["current"]["players"][0]["hand"] = []
    assert model.rebuilt(second).mine.needs is None
    assert asked[-1] == (), (
        "the rebuild inherited the ORIGINAL board's hand — this is the Issue #400 Phase 2 defect, "
        "and it is what made `state_value`'s `hand` family constant across a compose() call")


def test_a_resolution_passed_directly_is_still_taken_verbatim():
    """The widening must not be read as "needs must be callable": an already-resolved `Resolution`
    is carried through untouched and never called."""
    sentinel = object()
    model = StateModel.build(
        _obs(_player(active=_pult(), hand=[CRISPIN], prize=4),
             _player(active=_poke(RIOLU, hp=80, serial=3), prize=4)),
        combat=_combat(), deck=DECK, needs=sentinel)
    assert model.mine.needs is sentinel
