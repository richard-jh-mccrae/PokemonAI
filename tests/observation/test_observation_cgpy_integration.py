"""ObservationState over cgpy's own renders: engine state -> render -> typed pieces -> card functions.

Custom boards built with the suite's one hand-built builder, rendered by the offline twin in the
same dialect the deployed engine speaks; a seeded chaos game then runs the advance chain over a
whole live game."""
from __future__ import annotations

from observation_builders import build_observation, advance_observation

import random
from pathlib import Path

from cgpy_state_helpers import make_state
from cgpy.chain import def_for, is_deferred
from cgpy.engine import Engine
from cgpy.render import god_frame, observation
from cgpy.rng import SeededRng

from common.observation import HiddenHand, ObservationState, VisibleHand
from common.cards import card_store
from common.cards.card_facts import WATER
from common.cards.functions.damage import compute_active_damage
from common.cards.functions.energy import (
    payment_fraction, provision_units, unmet_cost_slots)

REPO = Path(__file__).resolve().parents[2]

MEGA_STARMIE, STARYU, IGNITION, CINDERACE = 1031, 1030, 17, 666
MUNKIDORI, DUDUNSPARCE, AIR_BALLOON, GRAVITY_MOUNTAIN = 112, 66, 1174, 1252


def _obs(gs, viewer):
    return observation(gs, viewer)


def _rich_state():
    return make_state(
        MEGA_STARMIE, CINDERACE,
        attacker_bench=[MUNKIDORI], defender_bench=[DUDUNSPARCE],
        attacker_tools=[AIR_BALLOON], stadium=GRAVITY_MOUNTAIN,
        attacker_energy=[IGNITION], attacker_under=STARYU,
        attacker_hand=[DUDUNSPARCE, IGNITION], attacker_discard=[STARYU],
        attacker_deck=[CINDERACE] * 4, attacker_prizes=[MUNKIDORI] * 3,
        defender_hand=[CINDERACE] * 5)


def test_a_custom_cgpy_board_arrives_as_typed_truth():
    board = build_observation(_obs(_rich_state(), 0))
    active = board.me.active
    assert active.card.card_id == MEGA_STARMIE
    assert card_store()[active.card.card_id] is card_store()[MEGA_STARMIE]
    assert [card.card_id for card in active.pre_evolution] == [STARYU]
    assert [card.card_id for card in active.tools] == [AIR_BALLOON]
    assert [card.card_id for card in active.energy_cards] == [IGNITION]
    # The engine expands Ignition-on-an-evolution to three units; the record must agree.
    assert len(active.energies) == provision_units(card_store()[IGNITION], evolved=True) == 3
    assert board.me.hand.count(IGNITION) == 1 and board.me.discard.count(STARYU) == 1
    assert board.me.deck_count == 4 and board.me.prize_count == 3
    assert isinstance(board.them.hand, HiddenHand) and board.them.hand_count == 5
    assert [card.card_id for card in board.stadium] == [GRAVITY_MOUNTAIN]
    assert [b.card.card_id for b in board.them.bench] == [DUDUNSPARCE]


def test_both_viewers_get_masked_boards_with_distinct_keys():
    gs = _rich_state()
    mine = build_observation(_obs(gs, 0))
    theirs = build_observation(_obs(gs, 1))
    assert isinstance(mine.me.hand, VisibleHand) and isinstance(mine.them.hand, HiddenHand)
    assert theirs.me.active.card.card_id == CINDERACE
    assert theirs.me.hand.count(CINDERACE) == 5 and isinstance(theirs.them.hand, HiddenHand)
    assert mine.key != theirs.key


def test_a_god_frame_dies_at_the_boundary_and_keys_like_the_live_view():
    gs = _rich_state()
    live = build_observation(_obs(gs, 0))
    god = build_observation({"select": None, "logs": [], "current": god_frame(gs)})
    assert isinstance(god.them.hand, HiddenHand) and god.them.hand_count == 5
    assert god.them.prize_count == live.them.prize_count
    # Everything the god frame reveals beyond the legal view must die at construction.
    assert god.key == live.key


def test_affordability_reads_straight_off_the_board_nodes():
    board = build_observation(_obs(_rich_state(), 0))
    active = board.me.active
    attacks = {attack.attack_id: attack for attack in card_store()[active.card.card_id].attacks}
    jetting_blow, nebula_beam = attacks[1487], attacks[1488]
    # Three colorless units pay Nebula Beam's {C}{C}{C} but never Jetting Blow's {W}.
    assert unmet_cost_slots(active.energies, nebula_beam.cost) == ()
    assert payment_fraction(active.energies, nebula_beam.cost) == 1.0
    assert unmet_cost_slots(active.energies, jetting_blow.cost) == ((0, WATER),)


def test_damage_prices_off_the_pinned_facts():
    board = build_observation(_obs(_rich_state(), 0))
    attacker = card_store()[board.me.active.card.card_id]
    defender = card_store()[board.them.active.card.card_id]
    attacks = {attack.attack_id: attack for attack in attacker.attacks}
    assert defender.weakness == WATER
    assert compute_active_damage(attacks[1487], attacker, defender) == 240   # 120 doubled
    assert compute_active_damage(attacks[1488], attacker, defender) == 210   # pierces W/R


def _deck(agent):
    path = REPO / "src" / "agents" / agent / "deck.csv"
    return [int(x) for x in path.read_text(encoding="utf-8").split()[:60]]


def _choose(sel, rng):
    opts = sel.options
    legal = list(range(len(opts)))
    if sel.context == 0:                        # MAIN: never pick a deferred attack
        legal = [i for i in legal
                 if opts[i].get("type") != 13
                 or not is_deferred(def_for(f"attack:{opts[i]['attackId']}"))]
        non_end = [i for i in legal if opts[i].get("type") != 14]
        if non_end and rng.random() < 0.8:
            return [rng.choice(non_end)]
        return [legal[-1]]
    lo, hi = sel.min_count, sel.max_count
    k = min(rng.randint(lo, hi) if hi >= lo else lo, len(legal))
    return rng.sample(legal, k) if k else []


def test_a_seeded_chaos_game_keeps_the_advance_chain_true():
    """A whole live cgpy game: every step, both seats' advance equals a fresh build and the
    boundary holds. The mirror pool has no self-locking attack, so extras stay path-free."""
    deck = _deck("mega_starmie")
    rng = random.Random(424242)
    eng, err_player, err_type = Engine.start(deck, deck, rng=SeededRng(424242))
    assert eng is not None, f"deck rejected: seat {err_player} errorType {err_type}"
    chains = {seat: build_observation(_obs(eng.gs, seat), decklist=deck) for seat in (0, 1)}
    steps = 0
    while eng.gs.result == -1 and steps < 120:
        eng.step(_choose(eng.gs.pending, rng))
        steps += 1
        for seat in (0, 1):
            obs = _obs(eng.gs, seat)
            chains[seat] = advance_observation(chains[seat], obs)
            board = chains[seat]
            fresh = build_observation(obs, decklist=deck)
            assert board == fresh and board.key == fresh.key, f"seat {seat} step {steps}"
            assert isinstance(board.them.hand, HiddenHand)
            assert isinstance(board.me.hand, VisibleHand) and len(board.me.hand) == board.me.hand_count
    assert steps > 20, "the chaos game stalled before exercising the chain"
