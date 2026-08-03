"""Prize-economy promote: the interpose doctrine, now EMERGENT (ADR-0100 §11, #141).

When my Active is Knocked Out and both a cheap 1-prize attacker (Cinderace) and a higher-prize
win-condition (Mega Starmie ex) sit on the Bench with Energy, the forced promote is a prize-race
decision, not "promote the best attacker". Leading with the 3-prize Mega feeds the opponent the game
if they can Knock it Out; interposing the 1-prize Cinderace soaks the hit for a single prize and
keeps the fresh finisher on the Bench.

**The rung is gone.** `interpose-the-cheap-attacker-to-preserve-the-wincon` (+50) and its penalty
complement `dont-promote-into-their-prize-reach` (−20) are DELETED; ADR-0100 §11 rules the doctrine
EMERGENT from prize **Exposure** (`prizes x 100 x halve(turns_to_ko - 1)`) plus the fatal step. So
these tests assert the DECISION, never a rung firing — ADR-0072's rewrite of f29 from a score claim
to a decision claim is the prior art.

That change makes the doctrine CONDITIONAL where the rung was categorical, and deliberately so. The
rung fired on three board FLAGS (Weakness / an under-built finisher / a shown gust) without ever
asking whether the opponent could actually punish the wincon — the boolean `opp_cannot_punish_wincon`
was its only brake, and ADR-0100 §4 retires it as a 300-damage cliff read off the WRONG BODY. The
equation asks the clock instead, per body. Two consequences are tested below: interpose FIRES hard
when they can take the 3-prize Knock Out next turn (exposure 300 vs 100, the ADR's own arithmetic),
and STANDS DOWN when the wincon is actually the safer body — a case the flag-driven rung got wrong.

Fixtures carry real `AttackStat` records on BOTH sides. They have to: the decider reads damage and
the threat clock through attack records, and ADR-0052 retired the card-level `minCostDamage` scalar
fallback ("no record, no claim"), so a fixture without records prices every body at zero and asserts
nothing about the decider. Card facts per `data/EN_Card_Data.csv`: Mega Starmie ex (1031) 330 HP,
3 prizes; Cinderace (666) 160 HP, 1 prize, Turbo Flare ● 50 + "search your deck for up to 3 Basic
Energy cards and attach them to your Benched Pokémon".
"""
import pytest

from common.cards import CardFunctions
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy import Line, Strategy
from common.strategy.context import _BASIC_ENERGY
from common.strategy.general_strategy import GENERAL_STRATEGY

TO_ACTIVE = 4
FIRE, WATER, LIGHTNING, METAL = 2, 3, 4, 6
MEGA, STARYU, CINDERACE = 1031, 1030, 666
ARCHALUDON, NEUTRAL, SLUGGER = 190, 999, 998
WATER_ENERGY, BOSS_ORDERS = 3, 1182

# attack ids — the records the decider actually reads
A_JET, A_NEB, A_TURBO, A_ARCH, A_NEUT, A_SLUG = 41, 42, 43, 44, 45, 46


def _pilot(deck_has_basic=True):
    stats = DictCardStatProvider({
        MEGA: CardStat(MEGA, name="Mega Starmie ex", hp=330, megaEx=True, minAttackCost=1,
                       minCostDamage=120, maxDamage=210, maxDamageCost=3, energyType=WATER,
                       weakness=LIGHTNING, evolvesFrom="Staryu", attacks=(A_JET, A_NEB)),
        STARYU: CardStat(STARYU, name="Staryu", hp=70, minAttackCost=1, minCostDamage=20),
        CINDERACE: CardStat(CINDERACE, name="Cinderace", hp=160, minAttackCost=1, minCostDamage=50,
                            maxDamage=50, maxDamageCost=1, energyType=FIRE, weakness=WATER,
                            attacks=(A_TURBO,)),
        ARCHALUDON: CardStat(ARCHALUDON, synthetic=True, name='Archaludon ex', hp=300, ex=True, energyType=METAL,
                             weakness=FIRE, minAttackCost=2, minCostDamage=160, maxDamage=160,
                             maxDamageCost=2, attacks=(A_ARCH,)),
        NEUTRAL: CardStat(NEUTRAL, synthetic=True, name="Neutral Wall", hp=300, energyType=METAL, weakness=LIGHTNING,
                          minAttackCost=2, minCostDamage=170, maxDamage=170, maxDamageCost=2,
                          attacks=(A_NEUT,)),
        # A body that OHKOs the 330 HP Mega — the premise the exposure gap needs to be real.
        SLUGGER: CardStat(SLUGGER, synthetic=True, name="Slugger", hp=300, energyType=METAL, weakness=LIGHTNING,
                          minAttackCost=2, minCostDamage=340, maxDamage=340, maxDamageCost=2,
                          attacks=(A_SLUG,)),
        WATER_ENERGY: CardStat(WATER_ENERGY, synthetic=True, name="Water Energy", hp=0, energyType=WATER,
                               cardType=_BASIC_ENERGY),
    }, attacks={A_JET: AttackStat(A_JET, damage=120, cost=1, benchSnipe=50),
                A_NEB: AttackStat(A_NEB, damage=210, cost=3),
                A_TURBO: AttackStat(A_TURBO, damage=50, cost=1, recoverN=3, recoverSource="deck"),
                A_ARCH: AttackStat(A_ARCH, damage=160, cost=2),
                A_NEUT: AttackStat(A_NEUT, damage=170, cost=2),
                A_SLUG: AttackStat(A_SLUG, damage=340, cost=2)})
    strat = Strategy(lines=[Line(path=[STARYU, MEGA], payoff=MEGA, role="win_condition")],
                     roles={MEGA: ["win_condition", "primary_attacker"],
                            CINDERACE: ["accel_source", "starter"], STARYU: ["starter"]})
    deck = ([WATER_ENERGY] * 8 + [1] * 52) if deck_has_basic else [1] * 60
    return Pilot(strat, deck=deck, general_strategy=GENERAL_STRATEGY, stats=stats,
                 functions=CardFunctions({CINDERACE: ["opener"], BOSS_ORDERS: ["gust"]}))


def _obs(bench, opp_active, opp_prizes, opp_discard=()):
    me = {"active": [None], "bench": bench, "hand": [], "prize": [None] * 6, "discard": []}
    opp = {"active": [opp_active], "bench": [], "prize": [None] * opp_prizes,
           "discard": [{"id": c} for c in opp_discard]}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": 8},
            "select": {"context": TO_ACTIVE, "minCount": 1, "maxCount": 1,
                       "option": [{"type": 3, "area": 5, "index": i, "playerIndex": 0}
                                  for i in range(len(bench))]}}


# idx0 = cheap 1-prize attacker (Cinderace); idx1 = the 3-prize finisher (Mega Starmie ex)
def _bench(cinderace_energy=1, mega_energy=3):
    return [{"id": CINDERACE, "energies": [1] * cinderace_energy, "hp": 160},
            {"id": MEGA, "energies": [1] * mega_energy, "hp": 330}]


def _terms(pilot, obs):
    return [t.promote_retreat_working for t in pilot.explain(obs).options]


@pytest.mark.req("REQ-GEN-0054")
def test_interpose_emerges_when_they_can_take_the_three_prize_knockout():
    """ADR-0100 §11's emergence claim, in its own arithmetic: exposing the 3-prize finisher to a body
    that Knocks it Out NEXT TURN costs 300 damage, while the 1-prize soaker costs 100 — a 200-damage
    gap that swamps the finisher's 160-damage attack advantage. No rung required."""
    p = _pilot()
    obs = _obs(_bench(mega_energy=3), {"id": SLUGGER, "hp": 300, "energies": [1, 1]}, opp_prizes=3)
    cheap, wincon = _terms(p, obs)
    assert wincon["exposure"] == pytest.approx(300.0)      # 3 prizes x 100, they take it next turn
    assert cheap["exposure"] == pytest.approx(100.0)       # 1 prize x 100
    assert p.decide(obs) == [0]                            # Cinderace, not the second Mega


@pytest.mark.req("REQ-GEN-0054")
def test_interpose_stands_down_when_the_wincon_is_the_safer_body():
    """The rung fired on board FLAGS and never asked whether the opponent could actually punish the
    wincon. Here they cannot one-shot the 330 HP Mega but they DO one-shot the 160 HP Cinderace, so
    the cheap body is the one that dies for nothing — and the equation leads with the finisher.

    This is a deliberate BEHAVIOUR CHANGE, not a preserved rung: the flag-driven interpose got this
    shape wrong, and the corpus sweep records zero regressions from the deletion."""
    p = _pilot()
    obs = _obs(_bench(mega_energy=3), {"id": ARCHALUDON, "hp": 300, "energies": [1, 1]}, opp_prizes=3)
    cheap, wincon = _terms(p, obs)
    assert cheap["exposure"] > wincon["exposure"]          # the SOAKER is the fragile one here
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GEN-0054")
def test_the_accelerator_is_promoted_when_its_rider_actually_lands():
    """§3b: the dividend is MEASURED (`_recover_units`), not asserted from an `accel_source` role tag.
    With an under-built finisher and Basic Energy still in the deck, Turbo Flare's real rider loads
    the Bench and the accelerator out-yields promoting the 1-Energy finisher directly."""
    p = _pilot()
    obs = _obs(_bench(mega_energy=1), {"id": NEUTRAL, "hp": 300, "energies": [1, 1]}, opp_prizes=3)
    cheap, wincon = _terms(p, obs)
    assert cheap["my_yield"] > wincon["my_yield"]          # 50 damage + the rider beats a bare 120
    assert p.decide(obs) == [0]


@pytest.mark.req("REQ-GEN-0054")
def test_no_accelerator_credit_when_the_rider_would_whiff():
    """The same under-built finisher, but no Basic Energy left in the deck, so Turbo Flare's
    deck-search rider finds nothing. `_recover_units` bounds the dividend by the FUEL in the rider's
    source zone, so the credit is exactly zero and the finisher leads — the "firing blanks" gate,
    now a measurement rather than a `basic_energy_in_deck` board flag."""
    p = _pilot(deck_has_basic=False)
    obs = _obs(_bench(mega_energy=1), {"id": NEUTRAL, "hp": 300, "energies": [1, 1]}, opp_prizes=3)
    cheap, _wincon = _terms(p, obs)
    assert cheap["my_yield"] == pytest.approx(50.0)        # bare attack damage, no dividend
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GEN-0054")
def test_a_promote_that_hands_them_the_match_is_dominated():
    """§7a: when the body's own prize value covers the opponent's remaining count and the clock says
    they can take it, Knocking it out ENDS the match — subtracted at `KO_SCORE`, a finite dominance
    band rather than a veto. The 3-prize Mega into an opponent on 3 prizes is exactly that."""
    from common.strategy.context import KO_SCORE
    p = _pilot()
    obs = _obs(_bench(mega_energy=3), {"id": SLUGGER, "hp": 300, "energies": [1, 1]}, opp_prizes=3)
    _cheap, wincon = _terms(p, obs)
    assert wincon["fatal"] == KO_SCORE
    assert p.decide(obs) == [0]


@pytest.mark.req("REQ-GEN-0054")
def test_lead_the_strongest_body_when_the_opponent_needs_one_prize():
    """With the opponent on a single prize ANY Knock Out wins for them, so interposing a 1-prize body
    just hands it over — lead with the strongest body, which might survive or Knock Out back.

    Emergent from the fatal step's own condition (`prizes >= opp_prizes_remaining >= 2`): at one
    prize remaining the step cannot fire on any body, so nothing suppresses the finisher and its
    damage decides. §7b's argument that the near-goal escalation needs no second mechanism."""
    p = _pilot()
    obs = _obs(_bench(mega_energy=3), {"id": ARCHALUDON, "hp": 300, "energies": [1, 1]}, opp_prizes=1)
    _cheap, wincon = _terms(p, obs)
    assert wincon["fatal"] == 0.0
    assert p.decide(obs) == [1]


@pytest.mark.req("REQ-GEN-0054")
def test_no_interpose_when_the_finisher_is_powered_and_unthreatened():
    """The proven default holds: with a fully-powered finisher and an opponent who cannot take it
    next turn, promote the win-condition. Guards against the exposure term over-firing."""
    p = _pilot()
    obs = _obs(_bench(mega_energy=3), {"id": NEUTRAL, "hp": 300, "energies": [1, 1]}, opp_prizes=3)
    assert p.decide(obs) == [1]
