"""The Stadium HP-delta leg of `Pilot._boost_lethal_tactical` (Issue #424).

Two cards in the mega_lucario deck ask the identical question — *does playing this turn a knockout
that was not there before?* — and before this leg only one got an answer. Premium Power Pro and
Black Belt's Training carry `CardStat.damageBoost`, so the term priced their crossing by oracle
arithmetic. **Gravity Mountain carries no `damageBoost` at all**: its whole effect is the clause
``{"kind": "stadium_static", "effect": "hp_delta", "amount": -30, "applies_to": "stage2",
"symmetric": true}`` (`src/common/card_effects.json`, card 1252), so it exited at the boost guard and
the decision fell to one flat `assumed` rung, `gravity-mountain-vs-stage2` (+15) — whose own
rationale named the arithmetic it could not perform (*"the −30 crosses our breakpoints (Mega Brave
270 reaches a 300-HP Stage 2, Wild Press 210 a 240)"*). A flat weight cannot tell a board where that
crossing happens from one where it does not.

**Validation is BY CONSTRUCTION, and it is forced rather than chosen.** Gravity Mountain poses no
select of its own — measured over all 377 committed parity traces, card 1252 never appears as
``select.effect`` (positive control: the same sweep finds 3219 frames carrying a non-null effect
across 347 distinct source cards, so the instrument sees effects where they exist). Its decision is
therefore an ordinary MAIN `_PLAY`, and the bar is the MAIN bar: the 279 ruled context-0 frames in
`data/decider_lab/baseline.json` must not move. Nothing below stands in for that gate; these are the
equation's own legs.

## What each test is for

* the crossing, on the retired rung's OWN worked numbers (300-HP Stage 2 fires, 340 does not);
* **displacement** — playing a Stadium discards the one in play and ends its effects
  (`docs/rulebook.txt` L136), so the counterfactual is a DIFFERENCE of two readings and duplicating
  an in-play Gravity Mountain is worth exactly 0;
* the **sign**: `stadium_hp_delta` is signed and nothing branches on it, so an HP-*increasing*
  Stadium is priced as making a KO harder, never easier;
* the **symmetric leg**, which is structurally silent for this deck by the `applies_to` predicate
  rather than by assertion — with a Stage-2 positive control proving it is live and not dead;
* the `damageBoost` path, unchanged.
"""
from __future__ import annotations

import pytest

from common import board_delta
from common.cards import CardFunctions
from common.effects import CardEffects
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Strategy
from common.strategy.context import KO_SCORE, _END, _MAIN, _PLAY
from common.strategy.general_strategy import GENERAL_STRATEGY
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
FIGHTING = 6              # EnergyType.FIGHTING

#: Two real Stage 2 bodies with **no Weakness and no Resistance** (`data/EN_Card_Data.csv`), so the
#: crossing arithmetic below is the Stadium's and nothing else's. Their printed HP bounds what a
#: rendered `hp` may be: a body cannot render above its maximum without a Tool.
DRAGAPULT_EX = 121        # Stage 2, 320 HP, weakness n/a, resistance n/a
MEGA_DRAGONITE_EX = 904   # Stage 2, 370 HP, weakness n/a, resistance n/a

#: NON-Stage-2 controls, chosen so that a wrongly-applied −30 would VISIBLY fire: each renders in
#: (270, 300], the window Mega Brave's 270 misses by itself and would clear with the reduction. Both
#: are weakness/resistance-clean against a {F} attacker (`data/EN_Card_Data.csv`).
ALOLAN_EXEGGUTOR_EX = 193   # Stage 1, 300 HP, weakness n/a, resistance n/a
MEGA_LATIAS_EX = 754        # Basic,   280 HP, weakness n/a, resistance n/a

STADIUM_CARD_TYPE = 4     # CardType.STADIUM      (`common.scouting.provider`)
BASIC_ENERGY_CARD_TYPE = 5  # CardType.BASIC_ENERGY (same enum)


def _real_pilot():
    """The SHIPPED mega_lucario Pilot — real engine stats, real `CardFunctions`, real `CardEffects`.

    Not a hand-built stub, because this leg's whole point is that it reads Gravity Mountain's clause
    off the compendium rather than off a card id: a fixture that declared the clause itself would
    prove only that the fixture was written correctly."""
    from train.tune import _build_pilot
    pilot, _seeds = _build_pilot("mega_lucario")
    return pilot


def _menu(opp_body, *, hand, stadium=None, energy=2):
    """A MAIN menu offering the play of ``hand[0]``, with Mega Lucario ex Active on {F}{F}.

    ``stadium`` is the card ALREADY in play (the shared zone the engine renders both boards through).
    """
    cur = state(active=poke(MEGA_LUCARIO_EX, energy=energy, energy_card=F_ENERGY, hp=340),
                hand=list(hand), opp_active=opp_body, turn=6, prizes=6, opp_prizes=6)
    if stadium is not None:                      # the engine renders a Stadium as an ordinary card
        cur["stadium"] = [{"id": stadium, "serial": 900, "playerIndex": 1}]
    return make_select([opt(_PLAY, index=0), opt(_END)], context=_MAIN, current=cur)


def _term(pilot, obs) -> float:
    """`_boost_lethal_tactical` on option 0 — the term itself, so the numbers are exact rather than
    a sum every other Tactical term also contributes to."""
    select = obs["select"]
    board = pilot._board(obs, select)
    return pilot._boost_lethal_tactical(obs, select, board, select["option"][0])


# ── the crossing, on the retired rung's own worked numbers ────────────────────────────────────────

def test_gravity_mountain_crosses_a_300_hp_stage2_and_not_a_340():
    """Acceptance criterion 3, stated in the rung's own words: *"Mega Brave 270 reaches a 300-HP
    Stage 2"*. The −30 puts the bar at 270 and Mega Brave lands exactly on it; at 340 the bar is 310
    and the same attack is 40 short.

    The 340 case carries its own **positive control**: the shift really is −30 there too, so the
    0.0 is *"the reduction does not reach a knockout"* (G6 — sub-lethal Stadium play stays unpriced)
    and not *"the Stadium was never read"*."""
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
    """`applies_to: stage2` is evaluated by `board_delta._admits`, not by a branch in the Pilot — so
    a Basic or a Stage 1 defender contributes 0 structurally.

    Both boards are chosen to be **discriminating rather than merely quiet**: 300 and 280 each sit
    above Mega Brave's 270 and within 30 of it, so a −30 wrongly admitted here would cross and the
    term would claim a KO. The 0.0 is the predicate refusing, not the arithmetic missing."""
    pilot = _real_pilot()
    obs = _menu(poke(defender, hp=rendered), hand=[GRAVITY_MOUNTAIN])
    assert pilot._stadium_hp_shift(obs, GRAVITY_MOUNTAIN, pilot.stats.get(defender)) == 0
    assert _term(pilot, obs) == 0.0


def test_a_stadium_with_no_hp_delta_clause_never_claims_a_crossing():
    """Risky Ruins' only clause is a `stadium_trigger` on ``bench_play``. Under the ``static`` event
    every known trigger is filtered out, so the clause set is empty and the shift is 0 — the Stadium
    is read, and correctly found to move no HP."""
    pilot = _real_pilot()
    obs = _menu(poke(DRAGAPULT_EX, hp=300), hand=[RISKY_RUINS])
    assert pilot._stadium_hp_shift(obs, RISKY_RUINS, pilot.stats.get(DRAGAPULT_EX)) == 0
    assert _term(pilot, obs) == 0.0


def test_the_necessity_guard_holds_on_the_hp_side_too():
    """Identical semantics to the boost leg: if an affordable attack ALREADY knocks the defender out,
    the Stadium is not what wins the exchange and the term claims nothing — just attack."""
    pilot = _real_pilot()
    obs = _menu(poke(DRAGAPULT_EX, hp=260), hand=[GRAVITY_MOUNTAIN])   # Mega Brave 270 > 260
    assert _term(pilot, obs) == 0.0


# ── displacement: playing a Stadium ENDS the one in play (docs/rulebook.txt L136) ─────────────────

def test_duplicating_the_stadium_already_in_play_is_worth_exactly_nothing():
    """Acceptance criterion 2. *"Only one Stadium can be in play at a time—if a new one comes into
    play, discard the old one and end its effects"* (`docs/rulebook.txt` L136), which
    `board_delta._play`'s Stadium branch models. So the counterfactual is a DIFFERENCE of two
    readings: with the same effect already on the same defender the delta does not move, and the
    gain is 0 rather than a phantom −30.

    ⚠️ **This board is not one the engine ever offers**, and saying so is the point rather than an
    apology: *"You can't play a Stadium card if a Stadium with the same name is already in play"*
    (`docs/rulebook.txt` L137, enforced at `src/cgpy/options.py`). The issue's own motivating
    example — *"replacing an opponent's Gravity Mountain with our own"* — is therefore illegal, and
    this test exercises the ARITHMETIC of the difference, not a reachable position. It is kept
    because it is the only construction that isolates ``delta_now``: no legal board can currently
    produce a non-zero one (see `_stadium_hp_shift`'s note), so without this the subtraction would
    be wholly untested.

    The empty-zone reading is the **positive control** — same defender, same card, same call, −30 —
    so the 0 above is displacement and not a dead probe. (The engine's obs already renders the
    in-play Stadium into the body it reports, `cgpy/render.py:pokemon_dict`, which is why the
    defender is at 290 in the first board and 320 in the second: the same Dragapult ex.)"""
    pilot = _real_pilot()
    stat = pilot.stats.get(DRAGAPULT_EX)

    already_out = _menu(poke(DRAGAPULT_EX, hp=290), hand=[GRAVITY_MOUNTAIN],
                        stadium=GRAVITY_MOUNTAIN)
    assert pilot._stadium_hp_shift(already_out, GRAVITY_MOUNTAIN, stat) == 0

    empty_zone = _menu(poke(DRAGAPULT_EX, hp=320), hand=[GRAVITY_MOUNTAIN])
    assert pilot._stadium_hp_shift(empty_zone, GRAVITY_MOUNTAIN, stat) == -30


def test_replacing_a_quiet_stadium_still_earns_the_full_reduction():
    """The other side of the difference: Risky Ruins moves no HP, so displacing it with Gravity
    Mountain is worth the whole −30. Without the two-reading shape this and the case above would be
    indistinguishable."""
    pilot = _real_pilot()
    obs = _menu(poke(DRAGAPULT_EX, hp=300), hand=[GRAVITY_MOUNTAIN], stadium=RISKY_RUINS)
    assert pilot._stadium_hp_shift(obs, GRAVITY_MOUNTAIN, pilot.stats.get(DRAGAPULT_EX)) == -30
    assert _term(pilot, obs) >= KO_SCORE


# ── the symmetric leg: computed for this deck, not asserted away ──────────────────────────────────

def test_the_symmetric_half_is_zero_for_THIS_deck_by_the_predicate_not_by_a_branch():
    """Acceptance criterion 4 / ruling G5. Gravity Mountain hits *"Each Stage 2 Pokémon in play (both
    yours and your opponent's)"*, and this deck runs **no Stage 2** — Makuhita→Hariyama and
    Riolu→Mega Lucario ex are both single-hop Basic→Stage 1 (`data/EN_Card_Data.csv`; the Riolu hop
    is stated outright in `docs/rulebook.txt` Appendix 1). So the self-side delta is 0 *computed*,
    by the same `applies_to` predicate that decides the opponent's side — no deck-specific branch,
    and a deck that did run a Stage 2 would get the correct self-penalty from the same call.

    That last clause is the **positive control**, and it is the point of the test: without it, a
    symmetric leg that had gone accidentally silent would look identical to one that is correctly
    quiet on this deck."""
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

DROP, LIFT = 9603, 9604   # two synthetic Stadiums differing ONLY in the sign of `amount`
SLUGGER, TOWER = 9601, 9602
HAYMAKER = 9701


def _sign_pilot():
    """A pilot over two Stadiums identical but for the sign of their `hp_delta`.

    Synthetic — but NOT because the pool has no HP-increasing Stadium. It has exactly one:
    **Lively Stadium (1251)**, *"Each Basic Pokémon in play (both yours and your opponent's) gets
    +30 HP"*, which parses to ``amount: +30`` with ``applies_to: "basic"``. It cannot be used here
    because `board_delta._APPLIES_TO` carries no resolver for ``basic``, so every reader in that
    module REFUSES under it (fail-closed, and its own gap — see that constant's note). The synthetic
    pair is what lets the SIGN be tested while it is unpriceable, and holding everything but
    `amount` constant is what makes the sign the only variable."""
    def stadium(cid, amount):
        return [{"kind": "stadium_static", "effect": "hp_delta", "amount": amount,
                 "applies_to": "stage2", "symmetric": True}]

    stats = DictCardStatProvider({
        SLUGGER: CardStat(SLUGGER, synthetic=True, name="Slugger", energyType=FIGHTING, hp=340,
                          stage="basic", attacks=(HAYMAKER,), minAttackCost=2, maxDamage=270,
                          maxDamageCost=2, minCostDamage=270),
        TOWER: CardStat(TOWER, synthetic=True, name="Tower", hp=400, stage="stage2", stage2=True),
        DROP: CardStat(DROP, synthetic=True, name="Drop Tower", hp=0, cardType=STADIUM_CARD_TYPE),
        LIFT: CardStat(LIFT, synthetic=True, name="Lift Tower", hp=0, cardType=STADIUM_CARD_TYPE),
        F_ENERGY: CardStat(F_ENERGY, hp=0, energyType=FIGHTING,
                           cardType=BASIC_ENERGY_CARD_TYPE),                   # Basic {F} Energy
    }, attacks={HAYMAKER: AttackStat(HAYMAKER, damage=270, cost=2)})
    effects = CardEffects({str(DROP): stadium(DROP, -30), str(LIFT): stadium(LIFT, +30)})
    return Pilot(Strategy(), deck=[F_ENERGY] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=stats, functions=CardFunctions({}), effects=effects)


def _sign_menu(stadium_card):
    cur = state(active=poke(SLUGGER, energy=2, energy_card=F_ENERGY, hp=340),
                hand=[stadium_card], opp_active=poke(TOWER, hp=280),
                turn=6, prizes=6, opp_prizes=6)
    return make_select([opt(_PLAY, index=0), opt(_END)], context=_MAIN, current=cur)


@pytest.mark.parametrize("card, amount", [(DROP, -30), (LIFT, 30)])
def test_the_shift_carries_the_clauses_sign(card, amount):
    pilot = _sign_pilot()
    obs = _sign_menu(card)
    assert pilot._stadium_hp_shift(obs, card, pilot.stats.get(TOWER)) == amount


def test_an_hp_increasing_stadium_makes_the_ko_harder_never_easier():
    """Acceptance criterion 5 / ruling G2. One expression serves both signs::

        dmg >= opp_hp + hp_shift

    A 280-HP Stage 2 is out of a 270-damage attack's reach. The −30 Stadium lowers the bar to 250
    and the crossing fires; the +30 Stadium raises it to 310 and it does not — priced as making the
    knockout harder, for free, with no branch on the sign anywhere in the term."""
    pilot = _sign_pilot()
    assert _term(pilot, _sign_menu(DROP)) >= KO_SCORE
    assert _term(pilot, _sign_menu(LIFT)) == 0.0


# ── the damageBoost path, unchanged ───────────────────────────────────────────────────────────────

def test_the_damage_boost_leg_still_prices_its_own_crossing():
    """Acceptance criterion 1. The boost leg's gates and arithmetic are untouched — only the side of
    the crossing differs — so Premium Power Pro (+30, `{F}` attacker gate) still lifts Mega Brave's
    270 over a 290-HP defender and still declines a 310-HP one. Both defenders are deliberately
    NON-Stage-2, so no Stadium reading can be what makes this pass."""
    pilot = _real_pilot()
    crosses = _menu(poke(ALOLAN_EXEGGUTOR_EX, hp=290), hand=[PREMIUM_POWER_PRO])
    assert _term(pilot, crosses) >= KO_SCORE                    # 270 + 30 = 300 >= 290
    short = _menu(poke(MEGA_LUCARIO_EX, hp=310), hand=[PREMIUM_POWER_PRO])
    assert _term(pilot, short) == 0.0                           # 300 < 310 — the mirror's 340 body


# ── the rung this replaces ────────────────────────────────────────────────────────────────────────

def test_the_flat_gravity_mountain_rung_is_retired():
    """Acceptance criterion 6. The `assumed` +15 is gone, and no other rung is touched.

    The two assertions after the first are the **positive control**: the shipped deck Strategy really
    did load and really does still carry its other hypotheses, so the absence above is a retirement
    rather than an empty list. Read off `Pilot.strategy` — the object the agent actually decides
    with — rather than by re-importing the module, so a Strategy that failed to reach the Pilot
    could not pass this."""
    ids = {h.id for h in _real_pilot().strategy.hypotheses}
    assert "gravity-mountain-vs-stage2" not in ids
    assert len(ids) >= 5, "the deck Strategy did not load — the absence above proves nothing"
    assert "fire-lunar-cycle" in ids, "a surviving sibling rung: the instrument sees real ids"
