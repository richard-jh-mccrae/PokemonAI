"""`play_accel_lethal` — a PLAY-based energy accelerator (Crispin, id 1198) counts as +1 attach in the
`ko_for_prizes` KO budget, ON TOP of the manual attach (min-bound, cap 1).

Crispin (SCR, Supporter): "Search your deck for up to 2 Basic Energy cards of different types … put 1 into
your hand. ATTACH THE OTHER to 1 of your Pokémon." So a single Crispin play yields up to TWO attaches that
turn — its own on-play attach PLUS the manual attach of the fetched Energy — hence the +1 stacks on top of
the manual `extra`. It is the DETERMINISTIC deck-search-and-attach class, tagged BOTH `energy_accel` and
`tutor_energy` (data/EN_Card_Data.csv id 1198; src/common/card_functions.json).

SAFETY (default-ON lethal territory): every gate is min-bound / fail-closed. What is deliberately NOT
counted, to avoid a phantom KO:
  * an ATTACK-based accel — a Pokemon tagged `energy_accel` (Cinderace's Turbo Flare): using it IS the
    attack, so it can never stack with the KO attack;
  * a non-deterministic accel Trainer — Energy Coin (coin-flip), Waitress (top-6 dig), Rosa/Wondrous Patch
    (discard-source): none carry `tutor_energy`, so the `energy_accel`+`tutor_energy` gate drops them;
  * a Supporter accel whose slot is already spent or is claimed by the enabling step itself;
  * more than +1 (Crispin attaches exactly one), and anything when no Basic Energy is fetchable.
"""
from common.cards import CardFunctions as _CardFunctions
from common.pilot import Board, Pilot
from common.runtime import PROFILE
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from pilot_helpers import ACTIVE, HAND, make_select, opt, poke, state

EVOLVE = 9

CRISPIN = 1198       # Supporter: energy_accel + tutor_energy (the deterministic search-and-attach accel)
DRAKLOAK = 810       # my in-play pre-evo (evolves into the wincon)
DRAGAPULT = 910      # the evolution; Phantom Dive costs 2 Energy
WINCON3 = 911        # a costlier evolution (attack costs 3 Energy) — for the stacking/cap tests
OPP = 678            # opponent Active, 190 HP (KO-able by 200)
PHANTOM2 = 30        # attack: cost 2, 200 dmg
PHANTOM3 = 31        # attack: cost 3, 200 dmg
CINDERACE = 666      # a Pokemon tagged energy_accel — ATTACK-based, NEVER counted
ENERGY_COIN = 1135   # an Item tagged energy_accel but NOT tutor_energy (coin-flip) — NOT counted
DET_ITEM = 9500      # a hypothetical Item energy_accel + tutor_energy — counted even beside a Supporter enabler


def _stats():
    return DictCardStatProvider({
        DRAKLOAK: CardStat(cardId=DRAKLOAK, name="Drakloak", hp=90),
        DRAGAPULT: CardStat(cardId=DRAGAPULT, name="Dragapult ex", hp=280, ex=True,
                            evolvesFrom="Drakloak", attacks=(PHANTOM2,)),
        WINCON3: CardStat(cardId=WINCON3, name="Dragapult ex (3E)", hp=280, ex=True,
                          evolvesFrom="Drakloak", attacks=(PHANTOM3,)),
        OPP: CardStat(cardId=OPP, name="opp", hp=190, energyType=7),
        CRISPIN: CardStat(cardId=CRISPIN, cardType=3),               # Supporter
        CINDERACE: CardStat(cardId=CINDERACE, name="Cinderace", hp=170),   # a Pokemon (attack-based accel)
        ENERGY_COIN: CardStat(cardId=ENERGY_COIN, cardType=1),       # Item
        DET_ITEM: CardStat(cardId=DET_ITEM, cardType=1),            # Item
    }, {PHANTOM2: AttackStat(attackId=PHANTOM2, damage=200, cost=2, damageMax=200),
        PHANTOM3: AttackStat(attackId=PHANTOM3, damage=200, cost=3, damageMax=200)})


def _fns():
    return _CardFunctions({
        CRISPIN: ["energy_accel", "search", "tutor_energy"],
        CINDERACE: ["energy_accel"],
        ENERGY_COIN: ["energy_accel"],
        DET_ITEM: ["energy_accel", "tutor_energy"],
    })


def _pilot(**kw) -> Pilot:
    return Pilot(Strategy(), deck=[1] * 60, stats=_stats(), functions=_fns(), **kw)


def _board(*, hand, energy=1, reusable=False, basic_in_deck=True, supporter_played=False) -> Board:
    return Board(my_active_id=DRAKLOAK, my_active_energy=energy, hand_ids=frozenset(hand),
                 basic_energy_in_deck=basic_in_deck, supporter_played=supporter_played,
                 reusable_energy_in_hand=reusable, energy_attached=False, opp_bench=())


# ═══════════════════════════ flag plumbing ═══════════════════════════

def test_flag_is_armed_on_in_the_profile():
    assert PROFILE.get("play_accel_lethal") is True


def test_flag_defaults_off_at_the_ctor():
    assert _pilot().play_accel_lethal is False


# ═══════════════════════════ _play_accel_extra — the min-bound gates ═══════════════════════════

def test_crispin_counts_as_one_extra_attach_when_all_gates_pass():
    pilot = _pilot(play_accel_lethal=True)
    board = _board(hand=(CRISPIN,))
    assert pilot._play_accel_extra(None, board, None, None, enabler_consumes_supporter=False) == 1


def test_inert_when_flag_off():
    pilot = _pilot()                                              # default OFF
    board = _board(hand=(CRISPIN,))
    assert pilot._play_accel_extra(None, board, None, None, enabler_consumes_supporter=False) == 0


def test_refused_when_crispin_not_in_hand():
    pilot = _pilot(play_accel_lethal=True)
    board = _board(hand=())
    assert pilot._play_accel_extra(None, board, None, None, enabler_consumes_supporter=False) == 0


def test_refused_when_no_basic_energy_in_deck():
    # Min-bound: with no Basic Energy fetchable the search-and-attach whiffs → do not count (under-fire).
    pilot = _pilot(play_accel_lethal=True)
    board = _board(hand=(CRISPIN,), basic_in_deck=False)
    assert pilot._play_accel_extra(None, board, None, None, enabler_consumes_supporter=False) == 0


def test_refused_when_the_supporter_slot_is_already_spent():
    pilot = _pilot(play_accel_lethal=True)
    board = _board(hand=(CRISPIN,), supporter_played=True)
    assert pilot._play_accel_extra(None, board, None, None, enabler_consumes_supporter=False) == 0


def test_refused_when_the_enabler_itself_claims_the_supporter_slot():
    # Salvatore (rush_evolve Supporter) / an energy-tutor Supporter enabler spends the one slot — Crispin,
    # also a Supporter, can't ALSO be played this turn. This is the enabler_consumes_supporter=True path.
    pilot = _pilot(play_accel_lethal=True)
    board = _board(hand=(CRISPIN,))
    assert pilot._play_accel_extra(None, board, None, None, enabler_consumes_supporter=True) == 0


def test_attack_based_accel_pokemon_is_never_counted():
    # Cinderace is a Pokemon tagged energy_accel — its accel IS an attack (Turbo Flare). It can never
    # stack with the KO attack, so it is dropped by the is_item/is_supporter (Trainer-only) gate.
    pilot = _pilot(play_accel_lethal=True)
    board = _board(hand=(CINDERACE,))
    assert pilot._play_accel_extra(None, board, None, None, enabler_consumes_supporter=False) == 0


def test_non_deterministic_accel_trainer_is_not_counted():
    # Energy Coin is an Item tagged energy_accel but its attach is coin-conditional (double-heads) — it is
    # NOT tagged tutor_energy, so the energy_accel+tutor_energy soundness gate excludes it. No phantom KO.
    pilot = _pilot(play_accel_lethal=True)
    board = _board(hand=(ENERGY_COIN,))
    assert pilot._play_accel_extra(None, board, None, None, enabler_consumes_supporter=False) == 0


def test_deterministic_item_accel_counts_beside_a_supporter_enabler():
    # A play-based accel that is an ITEM (not a Supporter) is NOT gated by the Supporter slot, so it counts
    # even when the enabling step is itself a Supporter (enabler_consumes_supporter=True).
    pilot = _pilot(play_accel_lethal=True)
    board = _board(hand=(DET_ITEM,))
    assert pilot._play_accel_extra(None, board, None, None, enabler_consumes_supporter=True) == 1


def test_fails_closed_without_stats_or_functions():
    board = _board(hand=(CRISPIN,))
    assert Pilot(Strategy(), deck=[1] * 60, play_accel_lethal=True)._play_accel_extra(
        None, board, None, None, enabler_consumes_supporter=False) == 0


# ═══════════════════════════ end-to-end through _ko_for_prizes_lines ═══════════════════════════

def _evolve_lines(pilot, board, evolved_id):
    """Drive the real dispatch: my Active is a Drakloak (`energy` Energy) that evolves into a Dragapult ex
    which needs one MORE Energy than the manual attach supplies. Crispin sits in hand (not on the option
    menu, to isolate the accel term from the existing tutor_energy `_supporter_ko_candidate` path)."""
    active = poke(DRAKLOAK, energy=board.my_active_energy, hp=90)
    evolve = opt(EVOLVE, area=HAND, index=0, inPlayArea=ACTIVE, inPlayIndex=0)
    obs = make_select([evolve], current=state(active=active, opp_active=poke(OPP, hp=190),
                                              turn=2, hand=[evolved_id, CRISPIN], prizes=2, opp_prizes=2))
    return pilot._ko_for_prizes_lines(obs, obs["select"], board, obs["select"]["option"], None)


def test_evolve_ko_line_found_with_flag_on_and_not_off():
    # Dragapult ex needs 2 Energy for Phantom Dive; the Active carries 1 and no reusable Energy is in hand
    # (base manual attach = 0). Crispin's on-play attach supplies the missing 1 → the KO line appears.
    board = _board(hand=(DRAGAPULT, CRISPIN), energy=1, reusable=False)

    on = _pilot(play_accel_lethal=True)
    lines_on = _evolve_lines(on, board, DRAGAPULT)
    assert any(ln.goal == "ko_for_prizes" for ln in lines_on)

    off = _pilot(play_accel_lethal=False)
    assert _evolve_lines(off, board, DRAGAPULT) == []


def test_evolve_ko_line_absent_when_crispin_not_in_hand():
    # Same board, Crispin gone from hand → no accel attach → the KO stays out of reach even with the flag on.
    board = _board(hand=(DRAGAPULT,), energy=1, reusable=False)
    on = _pilot(play_accel_lethal=True)
    assert _evolve_lines(on, board, DRAGAPULT) == []


def test_accel_stacks_on_top_of_the_manual_attach():
    # A 3-Energy attack, Active at 1 Energy: the manual attach (a reusable Energy in hand) supplies +1 and
    # Crispin supplies +1 → 1 + 1 + 1 = 3 → the KO line appears. Proves the accel term is ADDED to `extra`.
    board = _board(hand=(WINCON3, CRISPIN), energy=1, reusable=True)
    on = _pilot(play_accel_lethal=True)
    assert any(ln.goal == "ko_for_prizes" for ln in _evolve_lines(on, board, WINCON3))


def test_accel_is_capped_at_one_not_two():
    # Same 3-Energy attack and 1-Energy Active, but NO reusable Energy in hand (manual attach = 0). Crispin
    # adds exactly +1 (not +2), so 1 + 1 = 2 < 3 → no phantom KO line.
    board = _board(hand=(WINCON3, CRISPIN), energy=1, reusable=False)
    on = _pilot(play_accel_lethal=True)
    assert _evolve_lines(on, board, WINCON3) == []
