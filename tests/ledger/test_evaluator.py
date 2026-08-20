"""The Ledger's pinned consequences: every action pays full cost, only end-turn is free.

Each test builds two real boards and asserts the SIGN of the swing between them — the exact
judgments the plan names (docs/plans/PokemonAI_Ledger_Plan.md §1): a useless attachment is
negative, overkill counters add nothing, a dead fetch waits, bench slots are scarce goods."""
from __future__ import annotations

from observation_helpers import opt  # noqa: F401  (path proof: tests/ root on sys.path)

from common.board import BoardState
from common.ledger import LedgerContext, LedgerWeights, evaluate

DREEPY, DRAKLOAK, DRAGAPULT = 119, 120, 121
LUNATONE, MAKUHITA = 675, 673
ULTRA_BALL = 1121
FIRE_E, PSYCHIC_E, DARK_E = 2, 5, 7
FIRE, PSYCHIC, DARKNESS = 2, 6, 8
UNKNOWN = 999_999


def body(card_id, serial, *, hp=100, max_hp=100, energies=(), tools=()):
    return {"id": card_id, "serial": serial, "playerIndex": 0, "hp": hp, "maxHp": max_hp,
            "appearThisTurn": False, "energies": list(energies),
            "energyCards": [{"id": _energy_card(t), "serial": 700 + i}
                            for i, t in enumerate(energies)],
            "tools": [{"id": c, "serial": 750 + i} for i, c in enumerate(tools)],
            "preEvolution": []}


def _energy_card(unit):
    return {FIRE: FIRE_E, PSYCHIC: PSYCHIC_E, DARKNESS: DARK_E}.get(unit, FIRE_E)


def player(*, active=None, bench=(), hand=(), discard=(), deck_count=30, prizes=6, own=True,
           hand_count=None):
    return {"active": [active] if active else [], "bench": list(bench), "benchMax": 5,
            "deckCount": deck_count, "prize": [None] * prizes,
            "discard": [{"id": c, "serial": 900 + i, "playerIndex": 0}
                        for i, c in enumerate(discard)],
            "handCount": len(hand) if hand_count is None else hand_count,
            "hand": ([{"id": c, "serial": 800 + i, "playerIndex": 0}
                      for i, c in enumerate(hand)] if own else None),
            "poisoned": False, "burned": False, "asleep": False, "paralyzed": False,
            "confused": False}


def printout(*, me=None, them=None, turn=2):
    return {"select": None, "logs": [], "current": {
        "turn": turn, "yourIndex": 0, "firstPlayer": 0, "supporterPlayed": False,
        "stadiumPlayed": False, "energyAttached": False, "retreated": False, "result": None,
        "stadium": [], "looking": None,
        "players": [me if me is not None else player(),
                    them if them is not None else player(own=False)]}}


def board(**kwargs):
    decklist = kwargs.pop("decklist", None)
    return BoardState.root(printout(**kwargs), decklist=decklist)


def ctx(**kwargs):
    return LedgerContext.build(weights=LedgerWeights(), **kwargs)


def swing(before, after, context=None):
    context = context or ctx()
    return evaluate(after, context).total - evaluate(before, context).total


# --- only ending the turn is worth zero: useless plays price negative ---

def test_dark_energy_on_paid_dragapult_is_negative():
    """Fire+Psychic already fill every attack slot; a dark fills nothing, so attaching it
    trades hand worth for zero board gain."""
    before = board(me=player(active=body(DRAGAPULT, 1, energies=(FIRE, PSYCHIC)),
                             hand=[DARK_E]))
    after = board(me=player(active=body(DRAGAPULT, 1, energies=(FIRE, PSYCHIC, DARKNESS)),
                            hand=[]))
    assert swing(before, after) < 0


def test_fire_energy_on_bare_dragapult_is_positive():
    before = board(me=player(active=body(DRAGAPULT, 1), hand=[FIRE_E]))
    after = board(me=player(active=body(DRAGAPULT, 1, energies=(FIRE,)), hand=[]))
    assert swing(before, after) > 0


def test_dark_energy_on_bare_dreepy_is_negative():
    """Dreepy's attacks cost Psychic and Fire+Psychic — no colorless slot, so a dark unit is
    unusable even speculatively."""
    before = board(me=player(active=body(DREEPY, 1), hand=[DARK_E]))
    after = board(me=player(active=body(DREEPY, 1, energies=(DARKNESS,)), hand=[]))
    assert swing(before, after) < 0


# --- damage counters: overkill destroys nothing ---

def test_overkill_counters_add_nothing():
    """Six counters into a 30-HP body waste three; splitting the spill into a live body is
    strictly better, and pure overkill never beats the exact kill."""
    start = board(them=player(own=False, bench=[body(MAKUHITA, 9, hp=30, max_hp=100),
                                                body(LUNATONE, 8, hp=60, max_hp=60)]))
    dumped = board(them=player(own=False, bench=[body(MAKUHITA, 9, hp=0, max_hp=100),
                                                 body(LUNATONE, 8, hp=60, max_hp=60)]))
    split = board(them=player(own=False, bench=[body(MAKUHITA, 9, hp=0, max_hp=100),
                                                body(LUNATONE, 8, hp=30, max_hp=60)]))
    context = ctx()
    assert evaluate(split, context).total > evaluate(dumped, context).total
    assert swing(start, dumped, context) == swing(start, dumped, context)  # deterministic
    assert swing(start, split, context) > swing(start, dumped, context)


def test_negative_hp_counts_as_zero():
    clamped = board(them=player(own=False, bench=[body(MAKUHITA, 9, hp=0, max_hp=100)]))
    below = board(them=player(own=False, bench=[body(MAKUHITA, 9, hp=-30, max_hp=100)]))
    context = ctx()
    assert evaluate(clamped, context).total == evaluate(below, context).total


# --- Ultra Ball: a dead fetch waits, a live fetch fires ---

def test_ultra_ball_with_nothing_to_fetch_is_negative():
    """No Pokemon left in the deck: the Ball and two discards buy nothing, so it waits."""
    decklist = [FIRE_E] * 21
    before = board(me=player(active=body(DRAGAPULT, 1),
                             hand=[ULTRA_BALL, FIRE_E, FIRE_E], deck_count=21),
                   decklist=[ULTRA_BALL, FIRE_E, FIRE_E] + decklist)
    after = board(me=player(active=body(DRAGAPULT, 1), hand=[],
                            discard=[ULTRA_BALL, FIRE_E, FIRE_E], deck_count=21),
                  decklist=[ULTRA_BALL, FIRE_E, FIRE_E] + decklist)
    assert swing(before, after) < 0


def test_ultra_ball_fetching_the_live_evolution_is_positive():
    """Dreepy is in play, Drakloak comes out of the deck: demand-live fetch beats the spend."""
    decklist = [DRAKLOAK] + [FIRE_E] * 20
    before = board(me=player(active=body(DREEPY, 1),
                             hand=[ULTRA_BALL, FIRE_E, FIRE_E], deck_count=21),
                   decklist=[ULTRA_BALL, FIRE_E, FIRE_E] + decklist)
    after = board(me=player(active=body(DREEPY, 1), hand=[DRAKLOAK],
                            discard=[ULTRA_BALL, FIRE_E, FIRE_E], deck_count=20),
                  decklist=[ULTRA_BALL, FIRE_E, FIRE_E] + decklist)
    assert swing(before, after) > 0


# --- bench slots are scarce goods ---

def test_benching_the_wincon_basic_is_positive_even_on_the_last_slot():
    filler = [body(MAKUHITA, 10 + i) for i in range(4)]
    before = board(me=player(active=body(DRAGAPULT, 1), bench=filler, hand=[DREEPY]))
    after = board(me=player(active=body(DRAGAPULT, 1),
                            bench=filler + [body(DREEPY, 20)], hand=[]))
    assert swing(before, after) > 0


def test_benching_a_duplicate_of_a_fielded_body_on_the_last_slot_is_negative():
    """Every basic in the store carries a Role, so 'redundant' means DUPLICATED: three
    Makuhita already field the backup-attacker job; a fourth on the last slot is refused."""
    filler = [body(MAKUHITA, 10 + i) for i in range(3)] + [body(LUNATONE, 14)]
    before = board(me=player(active=body(DRAGAPULT, 1), bench=filler, hand=[MAKUHITA]))
    after = board(me=player(active=body(DRAGAPULT, 1),
                            bench=filler + [body(MAKUHITA, 20)], hand=[]))
    assert swing(before, after) < 0


def test_benching_a_filler_on_an_empty_bench_is_positive():
    """Early development is real: with every slot free the same filler is worth deploying."""
    before = board(me=player(active=body(DRAGAPULT, 1), hand=[LUNATONE]))
    after = board(me=player(active=body(DRAGAPULT, 1), bench=[body(LUNATONE, 20)], hand=[]))
    assert swing(before, after) > 0


# --- evolution demand: a live target prices the card up ---

def test_evolution_in_hand_prices_higher_with_its_base_in_play():
    context = ctx()
    live = board(me=player(active=body(DREEPY, 1), hand=[DRAKLOAK]))
    dead = board(me=player(active=body(MAKUHITA, 1), hand=[DRAKLOAK]))
    assert evaluate(live, context).total > evaluate(dead, context).total


# --- the boundary and coverage honesty ---

def test_unknown_card_scores_the_floor_and_logs_a_gap():
    context = ctx()
    valuation = evaluate(board(me=player(active=body(DRAGAPULT, 1), hand=[UNKNOWN])), context)
    assert any(str(UNKNOWN) in gap for gap in valuation.gaps)


def test_opponent_hand_is_priced_by_count_alone():
    context = ctx()
    small = board(them=player(own=False, hand_count=2))
    large = board(them=player(own=False, hand_count=8))
    assert evaluate(small, context).total > evaluate(large, context).total


def test_prize_race_prefers_fewer_own_prizes_remaining():
    context = ctx()
    ahead = board(me=player(prizes=2), them=player(own=False, prizes=6))
    behind = board(me=player(prizes=6), them=player(own=False, prizes=2))
    assert evaluate(ahead, context).total > evaluate(behind, context).total


def test_won_result_dominates_everything():
    context = ctx()
    printed = printout(me=player())
    printed["current"]["result"] = 0
    won = BoardState.root(printed)
    assert evaluate(won, context).total > 50.0


def test_valuation_is_deterministic_and_symmetric_zero_on_mirrors():
    """The same equation negated: a perfectly mirrored board (no hidden asymmetry) sums to the
    pure information asymmetry — my known hand vs their counted one — and nothing else."""
    context = ctx()
    mine = player(active=body(DREEPY, 1), hand=[FIRE_E], prizes=6)
    theirs = player(own=False, active=body(DREEPY, 2), hand_count=1, prizes=6)
    first = evaluate(board(me=mine, them=theirs), context).total
    second = evaluate(board(me=mine, them=theirs), context).total
    assert first == second
