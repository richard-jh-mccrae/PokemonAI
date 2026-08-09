"""The Stadium HP-delta leg of `Pilot._boost_lethal_tactical` (Issue #424, Issue #433).

Gravity Mountain carries no `CardStat.damageBoost` — its whole effect is an `hp_delta` clause in
`card_effects.json` — so before this leg it exited at the boost guard and fell to one flat `assumed`
rung, which cannot tell a board where the −30 crosses a breakpoint from one where it does not.

Gravity Mountain poses no select of its own, so its decision is an ordinary MAIN `_PLAY` and the
regression bar is the MAIN bar in `data/decider_lab/baseline.json`; nothing here stands in for that
gate. These are the equation's own legs.
"""
from __future__ import annotations

import pytest

from common import board_delta
from common.strategy.context import KO_SCORE, _END, _MAIN, _PLAY
from pilot_helpers import make_select, opt, poke, state

# ── real cards, every fact read at source (data/EN_Card_Data.csv, src/common/card_effects.json) ──
GRAVITY_MOUNTAIN = 1252   # Stadium: "Each Stage 2 Pokémon in play (both yours and your opponent's)
                          # gets -30 HP." -> stadium_static / hp_delta / -30 / stage2 / symmetric
RISKY_RUINS = 1260        # Stadium: a `stadium_trigger` on `bench_play` — NO hp_delta at all, which
                          # is what makes it the trigger-filter control below
PREMIUM_POWER_PRO = 1141  # Item, +30 for a {F} attacker — the `damageBoost` leg's card
MEGA_LUCARIO_EX = 678     # Stage 1 (from Riolu), 340 HP; Mega Brave {F}{F} 270 — the attacker below
RIOLU, MAKUHITA, HARIYAMA, SOLROCK, LUNATONE, MEOWTH_EX = 677, 673, 674, 676, 675, 1071
F_ENERGY = 6              # Basic {F} Energy

#: Stage 2 bodies with NO weakness and NO resistance, so the crossing arithmetic below is the
#: Stadium's and nothing else's. Printed HP bounds a rendered `hp`: no body renders over max, Tool aside.
DRAGAPULT_EX = 121        # Stage 2, 320 HP, weakness n/a, resistance n/a
MEGA_DRAGONITE_EX = 904   # Stage 2, 370 HP, weakness n/a, resistance n/a

#: NON-Stage-2 controls, chosen so a wrongly-applied −30 would VISIBLY fire: each renders in
#: (270, 300], the window Mega Brave's 270 misses alone and would clear with the reduction.
ALOLAN_EXEGGUTOR_EX = 193   # Stage 1, 300 HP, weakness n/a, resistance n/a
MEGA_LATIAS_EX = 754        # Basic,   280 HP, weakness n/a, resistance n/a


def _real_pilot():
    """Not a stub: a fixture that declared the clause itself would prove only that the fixture was
    written correctly."""
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot("mega_lucario")
    return pilot


def _menu(opp_body, *, hand, stadium=None, energy=2):
    """`stadium` is the card ALREADY in play — the shared zone the engine renders both boards through."""
    cur = state(active=poke(MEGA_LUCARIO_EX, energy=energy, energy_card=F_ENERGY, hp=340),
                hand=list(hand), opp_active=opp_body, turn=6, prizes=6, opp_prizes=6)
    if stadium is not None:                      # the engine renders a Stadium as an ordinary card
        cur["stadium"] = [{"id": stadium, "serial": 900, "playerIndex": 1}]
    return make_select([opt(_PLAY, index=0), opt(_END)], context=_MAIN, current=cur)


def _term(pilot, obs) -> float:
    """The term ALONE, not the Tactical sum every other term contributes to."""
    select = obs["select"]
    board = pilot._board(obs, select)
    return pilot._boost_lethal_tactical(obs, select, board, select["option"][0])


# ── the crossing, on the retired rung's own worked numbers ────────────────────────────────────────

def test_gravity_mountain_crosses_a_300_hp_stage2_and_not_a_340():
    """The 340 case's positive control: the shift really is −30 there too, so its 0.0 means the
    reduction does not reach a knockout, not that the Stadium was never read."""
    pilot = _real_pilot()
    crosses = _menu(poke(DRAGAPULT_EX, hp=300), hand=[GRAVITY_MOUNTAIN])
    assert _term(pilot, crosses) >= KO_SCORE

    short = _menu(poke(MEGA_DRAGONITE_EX, hp=340), hand=[GRAVITY_MOUNTAIN])
    assert _term(pilot, short) == 0.0
    assert pilot._stadium_hp_shift(short, GRAVITY_MOUNTAIN,
                                   pilot.stats.get(MEGA_DRAGONITE_EX)) == -30


@pytest.mark.parametrize("defender, rendered", [(ALOLAN_EXEGGUTOR_EX, 300), (MEGA_LATIAS_EX, 280)])
def test_a_stadium_that_does_not_reach_the_defender_is_zero_by_the_shipped_predicate(defender,
                                                                                     rendered):
    """Discriminating rather than merely quiet: 300 and 280 each sit above Mega Brave's 270 and
    within 30 of it, so a −30 wrongly admitted would cross and the term would claim a KO."""
    pilot = _real_pilot()
    obs = _menu(poke(defender, hp=rendered), hand=[GRAVITY_MOUNTAIN])
    assert pilot._stadium_hp_shift(obs, GRAVITY_MOUNTAIN, pilot.stats.get(defender)) == 0
    assert _term(pilot, obs) == 0.0


def test_a_stadium_with_no_hp_delta_clause_never_claims_a_crossing():
    """Risky Ruins' only clause is a `stadium_trigger`, filtered out under the `static` event."""
    pilot = _real_pilot()
    obs = _menu(poke(DRAGAPULT_EX, hp=300), hand=[RISKY_RUINS])
    assert pilot._stadium_hp_shift(obs, RISKY_RUINS, pilot.stats.get(DRAGAPULT_EX)) == 0
    assert _term(pilot, obs) == 0.0


def test_the_necessity_guard_holds_on_the_hp_side_too():
    """If an affordable attack ALREADY knocks the defender out, the Stadium is not what wins."""
    pilot = _real_pilot()
    obs = _menu(poke(DRAGAPULT_EX, hp=260), hand=[GRAVITY_MOUNTAIN])   # Mega Brave 270 > 260
    assert _term(pilot, obs) == 0.0


# ── displacement: playing a Stadium ENDS the one in play (docs/rulebook.txt L136) ─────────────────

def test_duplicating_the_stadium_already_in_play_is_worth_exactly_nothing():
    """⚠️ NOT a board the engine ever offers — same-name Stadium play is illegal (`docs/rulebook.txt`
    L137) — but the only construction that isolates a non-zero `delta_now`."""
    pilot = _real_pilot()
    stat = pilot.stats.get(DRAGAPULT_EX)

    # 290 vs 320 is the SAME Dragapult ex: the obs already renders the in-play Stadium into the body
    # it reports (`cgpy/render.py:pokemon_dict`). The empty zone below is the positive control.
    already_out = _menu(poke(DRAGAPULT_EX, hp=290), hand=[GRAVITY_MOUNTAIN],
                        stadium=GRAVITY_MOUNTAIN)
    assert pilot._stadium_hp_shift(already_out, GRAVITY_MOUNTAIN, stat) == 0

    empty_zone = _menu(poke(DRAGAPULT_EX, hp=320), hand=[GRAVITY_MOUNTAIN])
    assert pilot._stadium_hp_shift(empty_zone, GRAVITY_MOUNTAIN, stat) == -30


def test_replacing_a_quiet_stadium_still_earns_the_full_reduction():
    """Without the two-reading shape this and the case above would be indistinguishable."""
    pilot = _real_pilot()
    obs = _menu(poke(DRAGAPULT_EX, hp=300), hand=[GRAVITY_MOUNTAIN], stadium=RISKY_RUINS)
    assert pilot._stadium_hp_shift(obs, GRAVITY_MOUNTAIN, pilot.stats.get(DRAGAPULT_EX)) == -30
    assert _term(pilot, obs) >= KO_SCORE


# ── the symmetric leg: computed for this deck, not asserted away ──────────────────────────────────

def test_the_symmetric_half_is_zero_for_THIS_deck_by_the_predicate_not_by_a_branch():
    """This deck runs NO Stage 2, so the self-side delta is 0 *computed* by the same `applies_to`
    predicate. Without the Dragapult control, an accidentally silent leg looks the same."""
    pilot = _real_pilot()

    def delta(card_id):
        stat = pilot.stats.get(card_id)
        clauses = board_delta.stadium_clauses_of(pilot.combat, GRAVITY_MOUNTAIN,
                                                 event="static", stat=stat)
        return board_delta.stadium_hp_delta(clauses, stat)

    for own in (RIOLU, MEGA_LUCARIO_EX, MAKUHITA, HARIYAMA, SOLROCK, LUNATONE, MEOWTH_EX):
        assert delta(own) == 0, f"{own} took a self-penalty, but this deck runs no Stage 2"
    assert delta(DRAGAPULT_EX) == -30, "the symmetric leg is dead, not quiet"


# ── the SIGN: an HP-increasing Stadium makes a KO harder, never easier ────────────────────────────

LIVELY_STADIUM = 1251     # Stadium: "Each Basic Pokémon in play (both yours and your opponent's)
                          # gets +30 HP." -> stadium_static / hp_delta / +30 / basic / symmetric.


@pytest.mark.parametrize("stadium, defender, amount", [(GRAVITY_MOUNTAIN, DRAGAPULT_EX, -30),
                                                       (LIVELY_STADIUM, MEGA_LATIAS_EX, +30)])
def test_the_shift_carries_the_clauses_sign(stadium, defender, amount):
    """The pairing is forced by the cards: Gravity Mountain's −30 reaches only a Stage 2 and Lively
    Stadium's +30 only a Basic, so each defender is the class its Stadium names."""
    pilot = _real_pilot()
    obs = _menu(poke(defender, hp=300), hand=[stadium])
    assert pilot._stadium_hp_shift(obs, stadium, pilot.stats.get(defender)) == amount


def test_an_hp_increasing_stadium_makes_the_ko_harder_never_easier():
    """One expression, `dmg >= opp_hp + hp_shift`, serves both signs with no branch. 280 sits within
    30 of Mega Brave's 270, so an inverted shift would put the bar at 250 and claim a KO."""
    pilot = _real_pilot()
    obs = _menu(poke(MEGA_LATIAS_EX, hp=280), hand=[LIVELY_STADIUM])
    assert pilot._stadium_hp_shift(obs, LIVELY_STADIUM, pilot.stats.get(MEGA_LATIAS_EX)) == 30
    assert _term(pilot, obs) == 0.0


def test_DISPLACING_lively_stadium_is_itself_a_lethal_play():
    """The one LEGAL board with a non-zero `delta_now`: Lively renders a Basic 30 over its printed
    max and any other Stadium ends that lift. A one-sided add ignoring `delta_now` reads this as 0."""
    pilot = _real_pilot()
    stat = pilot.stats.get(MEGA_LATIAS_EX)

    crosses = _menu(poke(MEGA_LATIAS_EX, hp=300), hand=[RISKY_RUINS], stadium=LIVELY_STADIUM)
    assert pilot._stadium_hp_shift(crosses, RISKY_RUINS, stat) == -30
    assert _term(pilot, crosses) >= KO_SCORE

    short = _menu(poke(MEGA_LATIAS_EX, hp=320), hand=[RISKY_RUINS], stadium=LIVELY_STADIUM)
    assert pilot._stadium_hp_shift(short, RISKY_RUINS, stat) == -30
    assert _term(pilot, short) == 0.0


# ── the damageBoost path, unchanged ───────────────────────────────────────────────────────────────

def test_the_damage_boost_leg_still_prices_its_own_crossing():
    """Both defenders are deliberately NON-Stage-2, so no Stadium reading can be what makes this
    pass."""
    pilot = _real_pilot()
    crosses = _menu(poke(ALOLAN_EXEGGUTOR_EX, hp=290), hand=[PREMIUM_POWER_PRO])
    assert _term(pilot, crosses) >= KO_SCORE                    # 270 + 30 = 300 >= 290
    short = _menu(poke(MEGA_LUCARIO_EX, hp=310), hand=[PREMIUM_POWER_PRO])
    assert _term(pilot, short) == 0.0                           # 300 < 310 — the mirror's 340 body


# ── the rung this replaces ────────────────────────────────────────────────────────────────────────

def test_the_flat_gravity_mountain_rung_is_retired():
    """Read off `Pilot.strategy` — the object the agent decides with — so a Strategy that failed to
    reach the Pilot cannot pass. The last two asserts are the positive control for the absence."""
    ids = {h.id for h in _real_pilot().strategy.hypotheses}
    assert "gravity-mountain-vs-stage2" not in ids
    assert len(ids) >= 5, "the deck Strategy did not load — the absence above proves nothing"
    assert "grab-lunar-cycle-fuel" in ids, "a surviving sibling rung: the instrument sees real ids"
