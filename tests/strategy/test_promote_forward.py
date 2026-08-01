"""Promote with forward search (the b7e483a promote blunders) — now DECIDER claims (ADR-0100, #141).

The three doctrines these frames encode all survive the rung deletion as EMERGENT properties of the
promote/retreat decider, so every test asserts the DECISION and none asserts a rung firing:

* bring up an accelerator that can Knock the Active Out over the win-condition itself — emergent from
  `my_yield`, where §3b makes the accel dividend a MEASURED `_recover_units` count at `ENERGY_RECOVER`
  rather than a flat `+50` on an `accel_source` role tag. The Knock-Out half is `_promote_ko_tactical`
  (§11), which fires on BOTH bodies here and therefore cancels — so the residual decides, which is
  exactly the layer split §1 rules.
* don't promote a BARE pre-evolution to evolve a dead 0-Energy win-condition — emergent, because a
  bare body reaches no damage at all and a body that can act does.
* promote the most-built copy, at a forced promote and at a SWITCH alike — emergent from reachable
  damage, which is what retires `is_best_promote_target` and its `+5` tie-break bonus (§3, and the
  f104 fix becomes a damage fact).

The accelerator fixture carries Turbo Flare's REAL rider (`recoverN=3, recoverSource="deck"`, per
`data/EN_Card_Data.csv`: "search your deck for up to 3 Basic Energy cards and attach them to your
Benched Pokémon"). It has to: the rung read the role TAG, the decider reads the card, and a fixture
without the record measures a different claim than the one this frame is about.
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Line, Strategy
from common.strategy.general_strategy import GENERAL_STRATEGY

TO_ACTIVE = 4
SWITCH = 3
MEGA, STARYU, CINDERACE = 1031, 1030, 666


def _fired(t):
    return {h.id for h, _ in t.fired}


def _pilot(hand_ids=(), energy=20):
    # Every attacker's cheapest attack is a real record (the card-level minCostDamage KO
    # fallback is retired, ADR-0052) — same damage/cost the fallback used to read.
    A_MEGA, A_STAR, A_CIND, A_NEBULA = 31, 32, 33, 34
    stats = DictCardStatProvider({
        3: CardStat(3, name="Water Energy", cardType=5, energyType=3),
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, minAttackCost=1,
                       minCostDamage=120, maxDamageCost=3, evolvesFrom="Staryu",
                       attacks=(A_MEGA, A_NEBULA)),
        STARYU: CardStat(STARYU, name="Staryu", hp=70, minAttackCost=1, minCostDamage=20,
                         attacks=(A_STAR,)),
        CINDERACE: CardStat(CINDERACE, name="Cinderace", hp=160, minAttackCost=1, minCostDamage=50,
                            attacks=(A_CIND,)),
        678: CardStat(678, name="Mega Lucario ex", hp=340, megaEx=True),
        # Both of Mega Starmie ex's attacks are recorded, not just the cheap one. The DEARER attack is
        # load-bearing: `_recover_recipient_need` measures a recipient against `max(costs)` over its own
        # and its FORWARD form's attacks, so omitting Nebula Beam made a bare Staryu (whose forward Mega
        # needs {C}{C}{C}) report a need of 1 instead of 3 — and the accel dividend it gates was
        # measuring a different claim than the one these frames are about.
    }, attacks={A_MEGA: AttackStat(A_MEGA, damage=120, cost=1),        # Jetting Blow {W}
                A_NEBULA: AttackStat(A_NEBULA, damage=210, cost=3),    # Nebula Beam {C}{C}{C}
                A_STAR: AttackStat(A_STAR, damage=20, cost=1),         # Water Gun {W}
                # Turbo Flare as PRINTED (`data/EN_Card_Data.csv`): "Search your deck for up to 3 Basic
                # Energy cards and attach them to your BENCHED Pokémon" — the target scope is part of
                # the record, and the need gate reads it.
                A_CIND: AttackStat(A_CIND, damage=50, cost=1, recoverN=3, recoverSource="deck",
                                   recoverTarget="bench")})
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA, role="win_condition")],
                     roles={MEGA: ["win_condition", "primary_attacker"],
                            CINDERACE: ["accel_source", "starter"], STARYU: ["starter"]})
    # The deck holds real Basic Energy so the deck-search rider has fuel to find (`_recover_units`
    # bounds the dividend by the fuel in its source zone). `energy` thins the suite for the
    # ADR-0077 frames, where the point is a suite the PIGEONHOLE FLOOR cannot see behind the prizes.
    deck = [3] * energy + [STARYU] * 10 + [MEGA] * 10 + [CINDERACE] * 10 + [1] * (30 - energy)
    return Pilot(strat, deck=deck, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({CINDERACE: ["opener"]}))


def _obs(bench, opp_active, hand=(), ctx=TO_ACTIVE, active=None, prize=0):
    """``prize`` = that many FACE-DOWN prizes — the pre-anchor state the pigeonhole floor collapses in.
    0 (the default) leaves every existing frame in the anchored regime it was written for."""
    me = {"active": [active], "bench": bench, "hand": [{"id": c} for c in hand],
          "prize": [None] * prize}
    opp = {"active": [opp_active], "bench": []}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": 8},
            "select": {"context": ctx, "minCount": 1, "maxCount": 1,
                       "option": [{"type": 3, "area": 5, "index": i, "playerIndex": 0}
                                  for i in range(len(bench))]}}


@pytest.mark.req("REQ-GEN-0026")
def test_promote_the_accelerator_that_kos_over_the_wincon():
    # Opp Active = 20-HP Mega Lucario ex. Both Cinderace (50) and benched Mega (120) KO it; promote
    # CINDERACE — takes the prize AND its Turbo Flare loads the Mega for next turn.
    p = _pilot()
    bench = [{"id": CINDERACE, "energies": [3], "hp": 160},      # idx0: accelerator, can KO
             {"id": MEGA, "energies": [3], "hp": 330},           # idx1: ready wincon, can KO
             {"id": STARYU, "energies": [], "hp": 70}]           # idx2: the rider's recipient (NEEDS Energy)
    obs = _obs(bench, {"id": 678, "hp": 20, "energies": [1, 1, 1]})
    dec = p.explain(obs)
    # Both bodies take the Knock Out, so `_promote_ko_tactical` cancels and the RESIDUAL decides —
    # the layer split ADR-0100 §1 rules. The accelerator wins on its measured rider, not a role tag.
    acc, wincon = dec.options[0].promote_retreat_working, dec.options[1].promote_retreat_working
    assert acc["my_yield"] > wincon["my_yield"]
    assert p.decide(obs) == [0]                                  # accelerator, not the wincon


@pytest.mark.req("REQ-GEN-0026")
def test_promote_the_staller_over_a_bare_preevo_even_with_the_payoff_in_hand():
    # Mega in hand, but only benched pre-evolution (Staryu) is BARE — evolving it exposes a dead
    # 0-Energy Mega. Promote Cinderace (staller that can act) instead.
    p = _pilot(hand_ids=[MEGA])
    bench = [{"id": CINDERACE, "energies": [1], "hp": 160},      # idx0: staller, 1 Energy
             {"id": STARYU, "energies": [], "hp": 70}]           # idx1: bare pre-evolution
    obs = _obs(bench, {"id": 678, "hp": 140, "energies": [1]}, hand=[MEGA])
    assert not p._board(obs, obs["select"]).evolve_to_ready_wincon_available
    dec = p.explain(obs)
    # EMERGENT (§6a): a disposable staller decomposes with no remainder into terms the equation
    # already builds — its own damage, and the LOW exposure that IS "disposable".
    assert dec.options[0].promote_retreat_working["my_yield"] > 0
    assert dec.options[1].promote_retreat_working["my_yield"] == 0    # a bare pre-evo reaches nothing
    assert p.decide(obs) == [0]                                  # staller, not the bare Staryu


# ---- ADR-0077: the deck-fuel leg is an EXPECTATION, so the dividend survives a thin suite --------

@pytest.mark.req("REQ-GEN-0026")
def test_the_accel_dividend_survives_a_suite_the_pigeonhole_floor_zeroes():
    """Issue #172 / ADR-0077, the f97 shape. 4 Basic {W} in the decklist, 2 of them VISIBLE on the
    board, 5 face-down prizes: the provable pigeonhole floor is `max(0, 2 - 5)` = 0, so the shipped
    read claimed no fuel at all and the accel dividend died — on a deck that still holds Water with
    near-certainty.

    Both bodies Knock the 20-HP Active Out, so `_promote_ko_tactical` cancels and the residual
    decides (ADR-0100 §1). The wincon out-reaches the accelerator on raw damage (120 vs 50), so the
    ONLY thing that can carry Cinderace is the dividend — which is exactly zero under the floor and
    real under `CountTriple.expected`. This frame therefore fails closed on the defect and green on
    the fix, without asserting any score."""
    p = _pilot(energy=4)
    bench = [{"id": CINDERACE, "energies": [3], "hp": 160},      # idx0: accelerator (1 visible {W})
             {"id": MEGA, "energies": [3], "hp": 330},           # idx1: ready wincon (1 visible {W})
             {"id": STARYU, "energies": [], "hp": 70}]           # idx2: the rider's recipient
    obs = _obs(bench, {"id": 678, "hp": 20, "energies": [1, 1, 1]}, prize=5)
    board = p._board(obs, obs["select"])
    # The premise: nothing is PROVABLE here — the sound floor sees no fuel behind five prizes.
    water = p._state_model.mine.deck_energy_counts[3]
    assert water.floor == 0 and water.expected > 0.0
    dec = p.explain(obs)
    acc, wincon = dec.options[0].promote_retreat_working, dec.options[1].promote_retreat_working
    assert acc["my_yield"] > wincon["my_yield"]
    assert p.decide(obs) == [0]                                  # accelerator, not the wincon


@pytest.mark.req("REQ-GEN-0026")
def test_an_anchored_board_scores_the_dividend_exactly_as_before():
    """The degeneracy guarantee (ADR-0077 verification). With no face-down prizes the Count Triple's
    legs collapse to one integer, so `expected` IS the old exact count and the dividend is unmoved —
    which is what separates "thin-Energy frames moved" from "everything moved"."""
    p = _pilot(energy=4)
    bench = [{"id": CINDERACE, "energies": [3], "hp": 160},
             {"id": MEGA, "energies": [3], "hp": 330},
             {"id": STARYU, "energies": [], "hp": 70}]
    obs = _obs(bench, {"id": 678, "hp": 20, "energies": [1, 1, 1]}, prize=0)
    p._board(obs, obs["select"])
    water = p._state_model.mine.deck_energy_counts[3]
    assert water.anchored is True                                # legs collapsed …
    assert water.expected == float(water.floor) == float(water.ceiling)   # … to the one integer
    assert p.decide(obs) == [0]


@pytest.mark.req("REQ-GEN-0025")
def test_best_promote_slot_picks_the_most_built_ready_wincon():
    # Three Mega Starmie ex on the Bench: bare (0), online (1 Energy), most-built (3 Energy). Best
    # body to promote is the 3-Energy one — closest to its payoff hit (ep83007714 f104).
    p = _pilot()
    bench = [{"id": MEGA, "energies": [], "hp": 330},            # idx0: bare, not ready
             {"id": MEGA, "energies": [3, 3, 3], "hp": 430},     # idx1: most-built ready wincon
             {"id": MEGA, "energies": [3], "hp": 330}]           # idx2: online but less built
    obs = _obs(bench, {"id": 678, "hp": 200, "energies": [1]})
    dec = p.explain(obs)
    rows = [t.promote_retreat_working for t in dec.options]
    assert rows[0]["my_yield"] == 0                              # bare copy reaches nothing …
    assert rows[1]["my_yield"] > 0                               # … the built copies reach damage
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GEN-0025")
def test_promote_the_ready_wincon_fires_at_switch_too():
    # The new-Active pick on RETREAT (SWITCH) must also bring up the built wincon, not bench-slot-0
    # (ep83007714 f92: a bare Cinderace at slot 0, the 3-Energy Mega at slot 1).
    p = _pilot()
    bench = [{"id": CINDERACE, "energies": [], "hp": 160},       # idx0: bare off-line body (slot 0)
             {"id": MEGA, "energies": [3, 3, 3], "hp": 430}]     # idx1: the powered wincon
    obs = _obs(bench, {"id": 678, "hp": 200, "energies": [1]}, ctx=SWITCH, active={"id": MEGA})
    dec = p.explain(obs)
    # ONE evaluator across both pick contexts (§9), so the SWITCH destination is ranked by the same
    # arithmetic as a forced promote — which is what makes the two sites unable to diverge.
    assert dec.options[1].promote_retreat_working["site"] == "pick"
    assert p.decide(obs) == [1]                                  # not bench-slot-0 Cinderace
