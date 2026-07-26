"""Issue #138 Phase 0b — the StateModel (ADR-0068).

The primary seam: a dict-backed Stat Provider and hand-built zone dicts, no Pilot and no engine boot
(the `test_reachable_incoming.py` / `test_reachable_attach.py` construction). Asserts external
behavior only — field values, the sharing guard's verdict, the epistemic legs, the channel's
contract — never memo internals.

Card facts VERIFIED at source (`data/EN_Card_Data.csv`, re-verified for this file) — never recalled:
  * Dragapult ex (121) Stage 2, HP 320 — Jet Headbutt ``●`` 70 / Phantom Dive ``{R}{P}`` 200.
  * Crispin (1198, Supporter): "Search your deck for up to 2 Basic Energy cards of DIFFERENT types,
    reveal them, and put 1 of them into your hand. Attach the other to 1 of your Pokémon."
  * Munkidori (112) Ability "Adrena-Brain": "Once during your turn, if this Pokémon has any {D}
    Energy attached, you may move up to 3 damage counters from 1 of your Pokémon to 1 of your
    opponent's Pokémon."  — the my-play-moves-THEIR-damage case.
  * Judge (1213, Supporter): "Each player shuffles their hand into their deck and draws 4 cards."
    — moves their ``handCount``/``deckCount`` and NOTHING a hand-picked fingerprint would list.
  * Boss's Orders (1182, Supporter): "Switch in 1 of your opponent's Benched Pokémon to the Active
    Spot." — moves WHICH of their bodies is Active and nothing else.
  * Riolu (677) Basic HP 80; Mega Lucario ex (678) — Aura Jab ``{F}`` 130 / Mega Brave ``{F}{F}`` 270.
  * Basic Energy card ids: 2 = {R}, 5 = {P}, 7 = {D}.
"""
import pytest

from common.cards import CardFunctions
from common.effects import CardEffects
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.state_model import (CarriedState, CountTriple, MySide, StateModel, TheirSide,
                               count_triple)
from common.strategy.combat import CombatMath

# EnergyType codes (cg.api.EnergyType)
COLORLESS, FIRE, PSYCHIC, FIGHTING, DARKNESS, DRAGON = 0, 2, 5, 6, 7, 9

DRAGAPULT, MUNKIDORI, RIOLU, MEGA_LUC = 121, 112, 677, 678
JET_HEADBUTT, PHANTOM_DIVE = 9121, 9122
AURA_JAB, MEGA_BRAVE = 982, 983
CRISPIN = 1198
E_R, E_P, E_D = 2, 5, 7

_STATS = {
    DRAGAPULT: CardStat(DRAGAPULT, name="Dragapult ex", hp=320, ex=True, stage2=True,
                        evolvesFrom="Drakloak", energyType=DRAGON, maxDamage=200, maxDamageCost=2,
                        minAttackCost=1, minCostDamage=70,
                        attacks=(JET_HEADBUTT, PHANTOM_DIVE), cardType=0),
    MUNKIDORI: CardStat(MUNKIDORI, name="Munkidori", hp=70, energyType=DARKNESS, cardType=0),
    RIOLU: CardStat(RIOLU, name="Riolu", hp=80, energyType=FIGHTING, minAttackCost=2,
                    maxDamage=30, attacks=(), cardType=0),
    MEGA_LUC: CardStat(MEGA_LUC, name="Mega Lucario ex", hp=340, megaEx=True, energyType=FIGHTING,
                       evolvesFrom="Riolu", maxDamage=270, minAttackCost=1, minCostDamage=130,
                       attacks=(AURA_JAB, MEGA_BRAVE), cardType=0),
    CRISPIN: CardStat(CRISPIN, name="Crispin", cardType=3),
    E_R: CardStat(E_R, name="Basic {R} Energy", cardType=5, energyType=FIRE),
    E_P: CardStat(E_P, name="Basic {P} Energy", cardType=5, energyType=PSYCHIC),
    E_D: CardStat(E_D, name="Basic {D} Energy", cardType=5, energyType=DARKNESS),
}
_ATTACKS = {
    JET_HEADBUTT: AttackStat(JET_HEADBUTT, damage=70, cost=1, energyTypes=(COLORLESS,)),
    PHANTOM_DIVE: AttackStat(PHANTOM_DIVE, damage=200, cost=2, energyTypes=(FIRE, PSYCHIC)),
    AURA_JAB: AttackStat(AURA_JAB, damage=130, cost=1, energyTypes=(FIGHTING,)),
    MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=2, energyTypes=(FIGHTING, FIGHTING)),
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


def _poke(cid, *, hp, energies=(), serial=1, damage=0):
    return {"id": cid, "hp": hp - damage, "energies": list(energies), "serial": serial}


def _player(*, active=None, bench=(), hand=(), discard=(), prize=4, hand_count=None,
            deck_count=20):
    """One side's engine ``PlayerState``-shaped dict. ``prize`` as an int = that many FACE-DOWN
    prizes (the pre-anchor state); a list is used verbatim."""
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
    return StateModel.build(_obs(me, opp, **kw), combat=_combat(), deck=DECK, probe=probe)


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
    assert m.turn == 5


def test_my_side_carries_cards_and_their_side_carries_only_a_count():
    """Asymmetry by information is the point: the engine gives the opponent's hand as None, so a
    contents read on their side must not exist at all rather than silently return empty."""
    m = _model(_player(active=_pult(), hand=[CRISPIN, E_R]),
               _player(active=_poke(RIOLU, hp=80), hand_count=7))
    assert m.mine.hand_ids == (CRISPIN, E_R)
    assert m.theirs.hand_size == 7
    assert not hasattr(m.theirs, "hand_ids")


def test_their_side_exposes_the_opponent_model_facade_rather_than_its_own_inference():
    sentinel = object()
    theirs = TheirSide(_player(active=_poke(RIOLU, hp=80)), combat=_combat(), opponent=sentinel)
    assert theirs.opponent is sentinel


# ── laziness ───────────────────────────────────────────────────────────────────────────────────

def test_build_computes_nothing_and_a_read_pays_only_for_what_it_touches():
    """The efficiency claim, asserted through the probe: constructing the model touches no field,
    and reading one field does not drag in the rest."""
    probe = set()
    m = _model(_player(active=_pult(energies=[E_R])), _player(active=_poke(RIOLU, hp=80)),
               probe=probe)
    assert probe == set()                                  # build computed nothing
    _ = m.mine.active.energy_count
    assert "mine.active" in probe                          # the bodies it had to resolve
    assert not any(f.startswith("theirs") for f in probe)  # their whole half untouched
    assert "mine.deck_energy_counts" not in probe          # nor any deck derivation


def test_a_probed_build_and_an_unprobed_build_agree():
    """Instrumentation must not change answers — otherwise the Leaf Profile measures a fiction."""
    args = (_player(active=_pult(energies=[E_R, E_P]), hand=[CRISPIN]),
            _player(active=_poke(RIOLU, hp=80)))
    assert (_model(*args, probe=set()).mine.deck_energy_counts
            == _model(*args).mine.deck_energy_counts)


# ── purity ─────────────────────────────────────────────────────────────────────────────────────

def test_two_builds_on_one_observation_agree_field_for_field():
    """Purity: same board in, same answer out. Without it neither side-sharing nor the cost pin is
    trustworthy — and the two hysteresis memories that USED to mutate during the Board build are
    exactly why this needs asserting."""
    me = _player(active=_pult(energies=[E_R]), hand=[CRISPIN], prize=4)
    opp = _player(active=_poke(RIOLU, hp=80, energies=[E_D]), prize=6)
    a, b = _model(me, opp), _model(me, opp)
    assert a.mine.deck_energy_counts == b.mine.deck_energy_counts
    assert a.mine.unseen_counts == b.mine.unseen_counts
    assert a.prize_race == b.prize_race
    assert a.opponent_fingerprint == b.opponent_fingerprint
    assert a.mine.famine == b.mine.famine


def test_reading_the_model_twice_is_stable():
    m = _model(_player(active=_pult(), hand=[CRISPIN]), _player(active=_poke(RIOLU, hp=80)))
    assert m.mine.famine is m.mine.famine
    assert m.mine.deck_energy_types == m.mine.deck_energy_types


def test_the_model_never_writes_the_carried_state_it_was_given():
    carried = CarriedState.of(phase_prev="RACE")
    m = StateModel.build(_obs(_player(active=_pult()), _player(active=_poke(RIOLU, hp=80))),
                         combat=_combat(), deck=DECK, carried=carried)
    _ = m.mine.famine, m.prize_race, m.opponent_fingerprint
    assert m.carried is carried and m.carried.get("phase_prev") == "RACE"


# ── the sharing guard: the wholesale fingerprint ────────────────────────────────────────────────
#
# Each MISS case is a real play of MINE that moves THEIR side. The hand-picked field list this
# replaced ("their bodies + damage + prizes + discard") caught only the third of them.

def _their_base():
    return _player(active=_poke(RIOLU, hp=80, serial=3),
                   bench=[_poke(MEGA_LUC, hp=340, serial=4)], hand_count=5, deck_count=20)


def _fp(opp, me=None):
    return _model(me or _player(active=_pult()), opp).opponent_fingerprint


def test_judge_moves_their_hand_and_deck_counts_so_reuse_must_miss():
    """Judge shuffles both hands away and draws 4 — it touches NOTHING an enumerated body/damage/
    prize/discard fingerprint would look at. This is the case that killed the enumerated design."""
    after = _their_base() | {"handCount": 4, "deckCount": 21}
    assert _fp(_their_base()) != _fp(after)


def test_a_gust_moves_which_body_is_active_so_reuse_must_miss():
    """Boss's Orders swaps their Active with a benched body. A set-shaped fingerprint calls that
    board unchanged, while every clock read keys off who is Active."""
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


def test_taking_a_prize_makes_reuse_miss():
    assert _fp(_their_base()) != _fp(_their_base() | {"prize": [None] * 3})


def test_a_stadium_change_makes_reuse_miss():
    """The stadium is shared rather than side-scoped, yet it can change what their bodies
    effectively are — so it is folded into the fingerprint even though it is not in their record."""
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
    """The cache's value: the ordinary majority of my plays cannot touch their side, so their
    expensive clock derivations survive across the selects of my turn."""
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
    """4 hidden prizes, the 3×{R}/3×{P}/2×{D} suite untouched: nothing about {D} is provable, the
    expectation is a fraction of a card, and the ceiling is the full unseen count."""
    m = _model(_player(active=_pult(), prize=4), _player(active=_poke(RIOLU, hp=80)))
    d = m.mine.deck_energy_counts[DARKNESS]
    assert d.floor == 0                      # both {D} could be prized
    assert 0.0 < d.expected < 2.0            # a fraction — never comparable to a cost
    assert d.ceiling == 2
    assert d.anchored is False and d.possible is True


def test_anchored_all_three_legs_collapse_to_the_exact_count():
    """Once a deck-revealing search resolves the prizes, the honest answer is an integer — so no
    consumer ever has to branch on the regime."""
    m = _model(_player(active=_pult(), prize=4), _player(active=_poke(RIOLU, hp=80)),
               own_prizes={E_R: 1, DRAGAPULT: 1})
    d = m.mine.deck_energy_counts[DARKNESS]
    assert (d.floor, d.expected, d.ceiling) == (2, 2.0, 2)
    assert d.anchored is True


def test_the_pigeonhole_floor_is_sound_when_copies_outnumber_hidden_prizes():
    """3×{R} against 2 hidden prizes: at least one {R} is PROVABLY in the deck, so the floor — the
    only leg safe to compare against a cost — rises above zero without the prizes being resolved."""
    m = _model(_player(active=_pult(), prize=2), _player(active=_poke(RIOLU, hp=80)))
    assert m.mine.deck_energy_counts[FIRE].floor >= 1


def test_seen_copies_leave_the_unseen_pool():
    """One {P} attached and one discarded: the ceiling drops to the copy that could still be there."""
    m = _model(_player(active=_pult(energies=[E_P]), discard=[E_P], prize=4),
               _player(active=_poke(RIOLU, hp=80)))
    assert m.mine.deck_energy_counts[PSYCHIC].ceiling == 1


def test_the_ceiling_leg_reproduces_the_sound_type_set_gate():
    """0a's shipped gate is *not-provably-empty*; the triple must subsume it rather than introduce a
    third epistemic — so ``possible`` and the type set agree, by construction."""
    m = _model(_player(active=_pult(energies=[E_P, E_P]), discard=[E_P], prize=4),
               _player(active=_poke(RIOLU, hp=80)))
    possible = {t for t, c in m.mine.deck_energy_counts.items() if c.possible}
    assert possible == m.mine.deck_energy_types


def test_a_provably_exhausted_type_is_absent_from_both_reads():
    """All three {P} accounted for outside the deck: no leg claims a copy, and the sound gate drops
    the type. Fail-closed on YIELD is 0a's direction and the triple must not soften it."""
    m = _model(_player(active=_pult(energies=[E_P, E_P]), discard=[E_P, E_R], prize=4),
               _player(active=_poke(RIOLU, hp=80)))
    assert m.mine.deck_energy_counts.get(PSYCHIC, CountTriple()).possible is False
    assert PSYCHIC not in m.mine.deck_energy_types


def test_count_triple_helper_fails_closed_on_unreadable_inputs():
    assert count_triple("?", 2, 10) == CountTriple()
    assert count_triple(2, 2, 0) == CountTriple()             # no deck left to hold anything


def test_unseen_counts_is_one_derivation_over_every_visible_zone():
    m = _model(_player(active=_pult(energies=[E_R]), hand=[CRISPIN], discard=[E_P], prize=4),
               _player(active=_poke(RIOLU, hp=80)))
    unseen = m.mine.unseen_counts
    assert unseen[E_R] == 2 and unseen[E_P] == 2              # 3 each, one of each seen
    assert DRAGAPULT not in unseen                            # the only copy is in play


# ── the affordability family, read through the model ───────────────────────────────────────────

def test_f70_is_not_a_famine_when_read_off_the_model():
    """The bug this whole arc exists to kill, now asked of the snapshot: Active Dragapult ex at 0
    Energy with Crispin in hand and the manual attach unspent reaches {R}{P} Phantom Dive 200."""
    m = _model(_player(active=_pult(), hand=[CRISPIN], prize=4),
               _player(active=_poke(RIOLU, hp=80)))
    assert m.mine.reachable_attach(m.mine.active, PHANTOM_DIVE) is True
    assert m.mine.famine is False


def test_a_provable_famine_still_fires():
    """Fail-closed stays fail-closed through the model: empty hand, manual attach spent."""
    m = _model(_player(active=_pult(), prize=4), _player(active=_poke(RIOLU, hp=80)),
               energy_attached=True)
    assert m.mine.famine is True


def test_the_budget_is_per_body_and_memoised_per_body():
    """The Budget genuinely differs by target (a bench-restricted clause funds one body, not
    another), which is why it is keyed per body — and the same body must hand back one object."""
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
    assert m.mine.readiness_p(m.mine.active, PHANTOM_DIVE) == 1.0
    dry = _model(_player(active=_pult()), _player(active=_poke(RIOLU, hp=80)),
                 energy_attached=True)
    assert dry.mine.readiness_p(dry.mine.active, PHANTOM_DIVE) == 0.0


def test_famine_makes_no_claim_without_an_active():
    m = _model(_player(), _player(active=_poke(RIOLU, hp=80)))
    assert m.mine.famine is False
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
    """Both discards are public, so this is a count and never an estimate — it is the recursion-fuel
    input that makes a KO'd threat's line persistent."""
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
    assert race.prize_diff == 3                              # positive = I am ahead
    assert dict(race.prize_map)[MEGA_LUC] == 3               # a Mega ex yields three
    assert race.ko_wins_now(2) is True and race.ko_wins_now(1) is False


def test_prize_yield_stays_card_knowledge_on_the_oracle():
    """The model holds the answer; the combat oracle owns the arithmetic (ADR-0052) — so a body's
    yield agrees with the oracle asked directly."""
    m = _model(_player(active=_pult()), _player(active=_poke(MEGA_LUC, hp=340)))
    assert m.theirs.active.prize_value == _combat().prize_value({"id": MEGA_LUC})


# ── the Carried State channel ──────────────────────────────────────────────────────────────────

def test_the_channel_carries_declared_members_and_defaults_absent_ones():
    c = CarriedState.of(phase_prev="STABILIZE")
    assert c.get("phase_prev") == "STABILIZE"
    assert c.get("known_top") is None                        # fail-closed: absent ≠ confident
    assert c.get("known_top", "fallback") == "fallback"


def test_the_channel_rejects_undeclared_members():
    """Narrow BY CONSTRUCTION rather than by convention — the whole point of declaring the channel."""
    with pytest.raises(ValueError):
        CarriedState.of(some_new_memory=1)
    with pytest.raises(ValueError):
        CarriedState().with_("some_new_memory", 1)


def test_an_update_returns_a_new_snapshot_and_never_mutates_the_old():
    """A member is read in and handed back — the caller stores it. Nothing mutates as a side effect
    of being computed, which is what keeps the model pure."""
    before = CarriedState.of(phase_prev="RACE")
    after = before.with_("phase_prev", "STABILIZE")
    assert before.get("phase_prev") == "RACE"
    assert after.get("phase_prev") == "STABILIZE"
    assert before is not after


def test_known_top_is_declared_so_149_attaches_without_reshaping_the_channel():
    """#138 architects for the ordered-zone belief without building it: the seat exists, the belief
    does not, and an unset member reads as the ordinary unknown."""
    assert "known_top" in CarriedState.MEMBERS
    assert CarriedState.of(known_top=(163,)).get("known_top") == (163,)
    assert CarriedState().get("known_top") is None


# ── my armed-clock: the mirror of TheirSide's deny read (ADR-0070 §6) ──────────────────────────

def test_my_turns_to_afford_is_the_hop_aware_armed_clock():
    """**The Two Clocks**, my half: the earliest turn MY line is armed, MAX of the energy-deficit
    leg and the FORWARD-HOP leg (never the sum). The same primitive `TheirSide` uses for the deny
    clock, exposed for my own bodies — the evolve decider needs it to price what a hop buys."""
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
