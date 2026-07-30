"""Deck-specific Strategy hypotheses for mega_lucario (deck-genie Phase B, re-baselined 2026-07-02).

Trigger tests through the Pilot's PUBLIC interface (`decide`/`explain`): each hypothesis fires on
its intended decision and stays silent on an obvious counter-case, plus the deck-shaped proofs of
the GENERAL pieces this doctrine leans on (the Tactical energy-recover credit + self-lock cost, the
`swap-out-the-locked-attacker` / `dont-promote-into-their-prize-reach` rules, and the ATTACH_FROM
concentrate routing that carries Aura Jab's bench load). Loads the SHIPPED
`src/agents/mega_lucario/strategy.py` (the real doctrine), not a fixture. Lib-free: observations
built by hand via `pilot_helpers`; the Heave-Ho ACTIVATE shape (bare YES/NO, owner on
`select.contextCard`) is the engine-probed shape (STRATEGY.md §9 T6').
"""
import importlib.util
from pathlib import Path

import pytest

from common.cards import CardFunctions
from common.strategy.general_strategy import GENERAL_STRATEGY
from common.pilot import Pilot
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from pilot_helpers import (
    ACTIVE, BENCH, HAND, MAIN, NO, PLAY, TO_HAND, YES,
    attack_opt, card_opt, make_select, opt, poke, state,
)

# Load the shipped deck Strategy (pure data; imports only common.strategy).
_REAL = Path(__file__).resolve().parents[2] / "src" / "agents" / "mega_lucario" / "strategy.py"
_spec = importlib.util.spec_from_file_location("ml_real_strategy", _REAL)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
STRATEGY = _mod.STRATEGY

RIOLU, MEGA_LUCARIO, SOLROCK, LUNATONE, MAKUHITA, HARIYAMA = 677, 678, 676, 675, 673, 674
POWER_PRO, BLACK_BELTS, GRAVITY_MOUNTAIN, MEOWTH_EX = 1141, 1211, 1252, 1071
BOSS_ORDERS, LILLIES = 1182, 1227     # supporter-tutor grab candidates (gust / draw)
JUDGE = 1213                          # a `hand_disruption` draw Supporter: no draw-need stand-down
F_ENERGY = 6                     # Basic Fighting Energy (cardType 5, energyType 6)
FIGHTING = 6                     # EnergyType.FIGHTING
STAB, AURA_JAB, MEGA_BRAVE, COSMIC_BEAM, WILD_PRESS = 981, 982, 983, 980, 978
TUCK_TAIL = 977                  # Meowth ex CCC-60: "Put this Pokémon and all attached cards into your hand"
WALL_HIT, BIG_HIT = 9101, 9102   # dummy attacks: 100-dmg (recoil-doom read) / 200-dmg (dooms Meowth 170)
WALL, STALLER, CHARGED = 9001, 9002, 9003   # opp dummies: fat wall / energyless staller / powered body
EX_WALL, STAGE2, C_ABILITY = 9004, 9005, 9006  # ex-Active (Belt gate) / Stage 2 / {C}-ability dummies
DOOMER = 9007                    # opp body whose 200-dmg attack KOs a 170-HP Meowth (Tuck-Tail escape read)
IS_FIRST = 41   # SelectContext.IS_FIRST — the coin toss
ACTIVATE = 43   # SelectContext.ACTIVATE — "use the Ability?" (owner on select.contextCard)
TO_ACTIVE = 4   # SelectContext.TO_ACTIVE — forced promote
ATTACH_FROM = 21  # SelectContext.ATTACH_FROM — an attack/ability's attach-recipient pick (Aura Jab)
EVOLVE, ABILITY, RETREAT, END = 9, 10, 12, 14   # OptionTypes

_ATTACK_STATS = {
    STAB: AttackStat(STAB, damage=30, cost=1, nextTurnSameAttackLock=True),
    AURA_JAB: AttackStat(AURA_JAB, damage=130, cost=1,
                         recoverN=3, recoverEnergyType=FIGHTING, recoverTarget="bench"),
    MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=2, nextTurnSameAttackLock=True),
    COSMIC_BEAM: AttackStat(COSMIC_BEAM, damage=70, cost=1, ignoresWeakness=True,
                            ignoresResistance=True, damageMin=0, damageMax=70,
                            requiresBench=("Lunatone",)),
    WILD_PRESS: AttackStat(WILD_PRESS, damage=210, cost=3, recoil=70),
    WALL_HIT: AttackStat(WALL_HIT, damage=100, cost=1),
    BIG_HIT: AttackStat(BIG_HIT, damage=200, cost=1),
    TUCK_TAIL: AttackStat(TUCK_TAIL, damage=60, cost=3, selfReturn=True),
}
_STATS = DictCardStatProvider({
    RIOLU: CardStat(RIOLU, name="Riolu", energyType=FIGHTING, hp=80, attacks=(STAB,),
                    minAttackCost=1, maxDamage=30, maxDamageCost=1, minCostDamage=30),
    MEGA_LUCARIO: CardStat(MEGA_LUCARIO, name="Mega Lucario ex", energyType=FIGHTING, hp=340,
                           megaEx=True, evolvesFrom="Riolu", attacks=(AURA_JAB, MEGA_BRAVE),
                           minAttackCost=1, maxDamage=270, maxDamageCost=2, minCostDamage=130),
    SOLROCK: CardStat(SOLROCK, name="Solrock", energyType=FIGHTING, hp=110, attacks=(COSMIC_BEAM,),
                      minAttackCost=1, maxDamage=70, maxDamageCost=1, minCostDamage=70),
    LUNATONE: CardStat(LUNATONE, name="Lunatone", energyType=FIGHTING, hp=110),
    MAKUHITA: CardStat(MAKUHITA, name="Makuhita", energyType=FIGHTING, hp=80),
    HARIYAMA: CardStat(HARIYAMA, name="Hariyama", energyType=FIGHTING, hp=150,
                       evolvesFrom="Makuhita", attacks=(WILD_PRESS,), retreatCost=3,
                       minAttackCost=3, maxDamage=210, maxDamageCost=3, minCostDamage=210),
    F_ENERGY: CardStat(F_ENERGY, hp=0, energyType=FIGHTING, cardType=5),   # Basic {F} Energy
    WALL: CardStat(WALL, hp=400, attacks=(WALL_HIT,)),           # un-KO-able dummy (100-dmg attack)
    STALLER: CardStat(STALLER, hp=100, retreatCost=2),           # energyless, high-retreat
    CHARGED: CardStat(CHARGED, hp=100, retreatCost=0),           # powered opp body (energy set via poke)
    EX_WALL: CardStat(EX_WALL, hp=320, ex=True),                 # ex Active — the Belt +50 gate/target
    STAGE2: CardStat(STAGE2, hp=170, stage2=True),               # a Stage 2 (Gravity Mountain read)
    C_ABILITY: CardStat(C_ABILITY, hp=170, energyType=0, hasAbility=True),  # {C} ability body
    DOOMER: CardStat(DOOMER, hp=200, attacks=(BIG_HIT,), minAttackCost=1,   # 200-dmg -> dooms Meowth 170
                     maxDamage=200, maxDamageCost=1, minCostDamage=200),
    POWER_PRO: CardStat(POWER_PRO, hp=0, cardType=1,             # Item: +30 this turn, {F} attackers
                        damageBoost=30, damageBoostType=FIGHTING),
    BLACK_BELTS: CardStat(BLACK_BELTS, hp=0, cardType=3,          # Supporter: +40 vs an ex Active
                          damageBoost=40, damageBoostVsEx=True),  # (one/turn; replaced Maximum Belt)
    BOSS_ORDERS: CardStat(BOSS_ORDERS, hp=0, cardType=3),         # Supporter (gust) — grab candidate
    LILLIES: CardStat(LILLIES, hp=0, cardType=3),                 # Supporter (draw) — grab candidate
    MEOWTH_EX: CardStat(MEOWTH_EX, name="Meowth ex", energyType=0, hp=170, ex=True, retreatCost=1,
                        attacks=(TUCK_TAIL,), minAttackCost=3, maxDamage=60, maxDamageCost=3,
                        minCostDamage=60),
}, attacks=_ATTACK_STATS)


def _pilot():
    return Pilot(STRATEGY, deck=[RIOLU] * 3 + [MEGA_LUCARIO] * 3 + [SOLROCK] * 3 + [LUNATONE] * 2
                 + [MAKUHITA] * 2 + [HARIYAMA] * 2 + [F_ENERGY] * 12 + [1] * 33,
                 general_strategy=GENERAL_STRATEGY, stats=_STATS, functions=CardFunctions({}))


def _fired(option_trace):
    return {h.id for h, _ in option_trace.fired}


# --- deck: Solrock<->Lunatone pairing — fetch the MISSING engine half (replaces fetch-the-engine-first)

@pytest.mark.req("REQ-ML-0001")
def test_fetch_the_missing_engine_half_prefers_solrock_when_lunatone_is_down():
    """With a lone benched Lunatone, a search grabs the MISSING engine half (Solrock) to complete the
    co-dependent draw engine — over the Riolu line piece (ml f41)."""
    p = _pilot()
    obs = make_select([card_opt(1, 0), card_opt(1, 1)], context=TO_HAND,
                      deck=[{"id": SOLROCK}, {"id": RIOLU}],
                      current=state(active=poke(MAKUHITA, hp=80), bench=[poke(LUNATONE, hp=110)], hand=[]))
    opts = p.explain(obs).options
    assert "fetch-the-missing-engine-half" in _fired(opts[0])       # Solrock — completes the engine
    assert "fetch-the-missing-engine-half" not in _fired(opts[1])   # Riolu — a line piece, not an engine half


# --- GENERAL: Meowth ex supporter-tutor re-model (grill 2026-07-03) ---------------------------
# The deck's own rules key off Roles/ids, so _pilot() runs tag-free; the Meowth re-model is GENERAL
# and keys off Function Tags, so these use a tag-aware Pilot.

def _tagged_pilot():
    return Pilot(STRATEGY, deck=[RIOLU] * 3 + [MEGA_LUCARIO] * 3 + [SOLROCK] * 3 + [LUNATONE] * 2
                 + [MAKUHITA] * 2 + [HARIYAMA] * 2 + [F_ENERGY] * 11 + [1] * 34,
                 general_strategy=GENERAL_STRATEGY, stats=_STATS,
                 functions=CardFunctions({MEOWTH_EX: ["search", "supporter_tutor"],
                                          BOSS_ORDERS: ["gust"], LILLIES: ["draw"]}))


def _deploy_ability_relevance(hand):
    """The Deploy Marginal's ABILITY leg for benching Meowth ex with `hand` held, on the REAL
    mega_lucario pilot. Real, not the `_tagged_pilot()` stub: since ADR-0081 the leg matches the need
    against the Supporters the DECK actually holds, and the stub's filler deck contains none — it
    would measure 0 for the wrong reason and pass either assertion."""
    from train.tune import _build_pilot
    p, _ = _build_pilot("mega_lucario")
    obs = make_select([opt(PLAY, index=0)], context=MAIN,
                      current=state(active=poke(MAKUHITA, hp=80), hand=hand))
    return p.explain(obs).options[0].deploy_working["ability_relevance"]


@pytest.mark.req("REQ-ML-0015")
def test_bench_the_supporter_tutor_when_supporterless_in_setup():
    """SETUP, Meowth ex in hand, no Supporter held: bench it to fetch one (the free-Ability grab).

    `bench-the-supporter-tutor` (+25) is DELETED — ADR-0081 decision 3 makes the bench-drop Ability a
    need-matched fetch yield, so what used to be a flat endorsement is now a priced leg."""
    assert _deploy_ability_relevance([MEOWTH_EX]) > 0


@pytest.mark.req("REQ-ML-0015")
def test_bench_the_supporter_tutor_stands_down_with_a_supporter_in_hand():
    """A Supporter already in hand -> no need to expose the 2-prize ex; the leg prices ZERO.

    This is the issue's own framing — "only bench it when we need a specific supporter" — and it is
    now arithmetic rather than a hand-written gate: the draw need is COVERED, so the yield is 0
    however certainly the deck still holds a Supporter."""
    assert _deploy_ability_relevance([MEOWTH_EX, LILLIES]) == 0


@pytest.mark.req("REQ-ML-0015")
def test_the_supporter_tutor_still_pays_when_the_held_supporter_is_not_a_draw_engine():
    """Soundness: the stand-down keys on the NEED, not on "any Supporter". Boss's Orders is a gust,
    not fuel — holding it leaves the draw need open, so benching Meowth to dig still prices > 0.
    Judge is likewise no stand-down (`hand_disruption`: a symmetric shuffle refills them too)."""
    assert _deploy_ability_relevance([MEOWTH_EX, BOSS_ORDERS]) > 0
    assert _deploy_ability_relevance([MEOWTH_EX, JUDGE]) > 0


@pytest.mark.req("REQ-ML-0016")
def test_grab_the_gust_supporter_when_a_gust_kos():
    """At the Last-Ditch TO_HAND grab, take Boss's (gust) when a gust would KO a benched body."""
    p = _tagged_pilot()
    cur = state(active=poke(MEGA_LUCARIO, energy=2, hp=340), opp_active=poke(WALL, hp=400),
                opp_bench=[poke(STALLER, hp=100)])          # Mega Brave 270 KOs the gusted 100
    obs = make_select([card_opt(1, 0)], context=TO_HAND, deck=[{"id": BOSS_ORDERS}], current=cur)
    assert "grab-a-gust-supporter-for-the-ko" in _fired(p.explain(obs).options[0])


@pytest.mark.req("REQ-ML-0016")
def test_grab_a_draw_supporter_in_setup_default():
    """No closing gust available: in SETUP the grab defaults to a draw Supporter (keep digging)."""
    p = _tagged_pilot()
    obs = make_select([card_opt(1, 0)], context=TO_HAND, deck=[{"id": LILLIES}],
                      current=state(active=poke(MAKUHITA, hp=80)))
    assert "grab-a-draw-supporter-in-setup" in _fired(p.explain(obs).options[0])


# --- GENERAL: Tuck Tail self-return escape (Tactical _SELF_RETURN_ESCAPE) ----------------------

def _tuck_tail_menu(opp):
    """Meowth ex Active (170, 2-prize) with 3 F, vs `opp`: Tuck Tail or End."""
    cur = state(active=poke(MEOWTH_EX, energy=3, hp=170), bench=[poke(SOLROCK, energy=1, hp=110)],
                opp_active=opp)
    return make_select([attack_opt(TUCK_TAIL), opt(END)], context=MAIN, current=cur)


@pytest.mark.req("REQ-ML-0017")
def test_tuck_tail_escapes_a_doomed_multiprize_active():
    """A doomed 2-prize Meowth (opp threatens 200 ≥ 170): Tuck Tail's tactical is lifted by the
    escape credit (2 × 50) — the bounce denies the 2-prize KO, and it beats End."""
    p = _pilot()
    doomed = p.explain(_tuck_tail_menu(poke(DOOMER, energy=1, hp=200)))
    assert doomed.options[0].tactical >= 100        # 60 − eff + 50×2 escape credit
    assert p.decide(_tuck_tail_menu(poke(DOOMER, energy=1, hp=200))) == [0]   # picks Tuck Tail over End


@pytest.mark.req("REQ-ML-0017")
def test_tuck_tail_not_credited_when_meowth_is_safe():
    """A safe Meowth (opp only threatens 100 < 170): no escape credit — Tuck Tail stays a weak
    60-chip and the agent doesn't scoop itself away for tempo."""
    tac = _pilot().explain(_tuck_tail_menu(poke(WALL, hp=400))).options[0].tactical
    assert tac < 100                                # just 60 − eff, no escape credit


# --- deck: spring-heave-ho-when-it-pays -------------------------------------------------------

def _evolve_hariyama(opp_bench):
    cur = state(active=poke(SOLROCK, energy=1, hp=110), bench=[poke(MAKUHITA, hp=80)],
                hand=[HARIYAMA], opp_active=poke(WALL, hp=400), opp_bench=opp_bench)
    return make_select([opt(EVOLVE, area=HAND, index=0, inPlayArea=BENCH, inPlayIndex=0)],
                       context=MAIN, current=cur)


@pytest.mark.req("REQ-ML-0002")
def test_spring_heave_ho_fires_when_a_stall_target_exists():
    """Evolving Hariyama is endorsed when its free gust has a payoff (an energyless high-retreat
    body to strand)."""
    obs = _evolve_hariyama([poke(STALLER, hp=100)])             # energyless, retreat 2
    assert "spring-heave-ho-when-it-pays" in _fired(_pilot().explain(obs).options[0])


@pytest.mark.req("REQ-ML-0002")
def test_spring_heave_ho_silent_without_any_gust_payoff():
    """No KO-able and no strandable benched body -> the evolve is not gust-endorsed."""
    obs = _evolve_hariyama([poke(CHARGED, energy=2, hp=100)])   # powered, un-KO-able (retreat 0)
    assert "spring-heave-ho-when-it-pays" not in _fired(_pilot().explain(obs).options[0])


# --- deck: the Heave-Ho ACTIVATE gate (engine-probed shape) -----------------------------------

def _heave_ho_activate(opp_bench):
    cur = state(active=poke(SOLROCK, energy=1, hp=110), bench=[poke(HARIYAMA, hp=150)],
                opp_active=poke(WALL, hp=400), opp_bench=opp_bench)
    obs = make_select([opt(YES), opt(NO)], context=ACTIVATE, current=cur)
    obs["select"]["contextCard"] = {"id": HARIYAMA, "serial": 7, "playerIndex": 0}
    return obs


@pytest.mark.req("REQ-ML-0003")
def test_heave_ho_declines_when_every_target_is_a_powered_gift():
    """Only a powered body on their bench: dragging it up is a free promote — decline the Ability."""
    p = _pilot()
    obs = _heave_ho_activate([poke(CHARGED, energy=2, hp=100)])
    assert "heave-ho-decline-without-payoff" in _fired(p.explain(obs).options[0])   # the YES option
    assert p.decide(obs) == [1]                                                     # picks NO


@pytest.mark.req("REQ-ML-0003")
def test_heave_ho_activates_onto_a_strandable_target():
    """An energyless high-retreat body to strand: use the free gust."""
    p = _pilot()
    obs = _heave_ho_activate([poke(STALLER, hp=100)])
    assert "heave-ho-gust-when-it-pays" in _fired(p.explain(obs).options[0])
    assert p.decide(obs) == [0]                                                     # picks YES


# --- GENERAL oracle: Cosmic Beam's bench-partner condition (replaces the retired deck rule) ----

def _cosmic_menu(bench, opp_hp=400):
    cur = state(active=poke(SOLROCK, energy=1, hp=110), bench=bench,
                opp_active=poke(WALL, hp=opp_hp))
    return make_select([attack_opt(COSMIC_BEAM), opt(END)], context=MAIN, current=cur)


@pytest.mark.req("REQ-ML-0004")
def test_cosmic_beam_scores_zero_without_lunatone_benched():
    """The oracle zeroes the does-nothing-without-Lunatone attack on the live board: passing (END)
    outranks declaring a 0-damage Cosmic Beam."""
    p = _pilot()
    obs = _cosmic_menu([])
    assert p.explain(obs).options[0].tactical <= 0        # 0 damage − efficiency
    assert p.decide(obs) == [1]                           # END over the wasted declaration


@pytest.mark.req("REQ-ML-0004")
def test_cosmic_beam_prices_full_with_lunatone_benched():
    p = _pilot()
    obs = _cosmic_menu([poke(LUNATONE, hp=110)])
    assert p.explain(obs).options[0].tactical > 60        # the real 70 chip
    assert p.decide(obs) == [0]


@pytest.mark.req("REQ-ML-0004")
def test_cosmic_beam_phantom_ko_suppressed_without_lunatone():
    """A 60-HP defender is NOT a Cosmic Beam KO when Lunatone is missing — the old phantom."""
    opts = _pilot().explain(_cosmic_menu([], opp_hp=60)).options
    assert opts[0].tactical < 1000                        # no KO_SCORE on a does-nothing attack
    with_partner = _pilot().explain(_cosmic_menu([poke(LUNATONE, hp=110)], opp_hp=60)).options
    assert with_partner[0].tactical >= 1000               # the real KO prices as one


# --- GENERAL tactical: the energy-recover credit + self-lock cost (Aura Jab vs Mega Brave) ----

def _attack_choice(discard, opp_hp):
    cur = state(active=poke(MEGA_LUCARIO, energy=2, hp=340), bench=[poke(RIOLU, hp=80)],
                discard=discard, opp_active=poke(WALL, hp=opp_hp))
    return make_select([attack_opt(AURA_JAB), attack_opt(MEGA_BRAVE)], context=MAIN, current=cur)


@pytest.mark.req("REQ-ML-0005")
def test_fueled_aura_jab_beats_mega_brave_on_a_non_ko_turn():
    """3 Basic {F} in the discard + a bench recipient: the recover credit (and Mega Brave's
    self-lock cost) makes Aura Jab the developing chip — the deck's confirmed engine."""
    assert _pilot().decide(_attack_choice([F_ENERGY] * 3, opp_hp=400)) == [0]


@pytest.mark.req("REQ-ML-0005")
def test_empty_discard_mega_brave_wins_the_chip():
    """No fuel -> Aura Jab is a bare 130; the 270 chip wins even paying the lock cost."""
    assert _pilot().decide(_attack_choice([], opp_hp=400)) == [1]


@pytest.mark.req("REQ-ML-0005")
def test_among_equal_ko_attacks_the_recover_attack_wins():
    """Both attacks KO a 100-HP Active: take the cheaper KO that ALSO develops (sub-prize credit,
    keeps Mega Brave off cooldown)."""
    assert _pilot().decide(_attack_choice([F_ENERGY] * 3, opp_hp=100)) == [0]


@pytest.mark.req("REQ-ML-0005")
def test_lone_locking_attack_is_never_charged_below_passing():
    """Riolu's only attack self-locks — the lock cost must NOT apply (chipping beats passing)."""
    cur = state(active=poke(RIOLU, energy=1, hp=80), opp_active=poke(WALL, hp=400))
    obs = make_select([attack_opt(STAB), opt(END)], context=MAIN, current=cur)
    assert _pilot().decide(obs) == [0]


# --- GENERAL: the dual-Mega swap, now a DECIDER claim (ADR-0073 §11) --------------------------
#
# `swap-out-the-locked-attacker` (+35) is DELETED. The doctrine is emergent from destination value
# minus retreat cost: a transient-locked attack scores LESS on its OWN option, and a fresh powered
# copy scores more as a destination, so the swap wins without a rung asserting it. These tests
# therefore assert the DECISION (is the pivot endorsed?) rather than a rung firing.

def _locked_board(bench_energy, logs):
    active = poke(MEGA_LUCARIO, energy=2, hp=340)
    active["serial"] = 42
    cur = state(active=active, bench=[poke(MEGA_LUCARIO, energy=bench_energy, hp=340)],
                opp_active=poke(WALL, hp=400))
    obs = make_select([opt(RETREAT), opt(END)], context=MAIN, current=cur)
    obs["logs"] = logs
    return obs


_MEGA_BRAVE_LOG = [{"type": 15, "playerIndex": 0, "attackId": MEGA_BRAVE, "serial": 42}]


@pytest.mark.req("REQ-ML-0006")
def test_the_swap_is_endorsed_when_a_fresh_powered_mega_is_ready():
    """The dual-Mega cadence: with Mega Brave transient-locked on the Active and a second POWERED
    Mega on the Bench, the pivot is priced positive — the destination reaches real damage while the
    locked body does not."""
    obs = _locked_board(bench_energy=2, logs=_MEGA_BRAVE_LOG)
    row = _pilot().explain(obs).options[0].promote_retreat_working
    assert row is not None and row["site"] == "whether"
    assert row["my_yield"] > 0 and row["total"] > 0


@pytest.mark.req("REQ-ML-0006")
def test_the_swap_is_declined_when_the_benched_mega_is_bare():
    """The discrimination that matters: a BARE second Mega reaches nothing, so pivoting into it
    buys no damage and still pays exposure — the pivot prices negative. This is the half the deleted
    rung expressed as its `bench_wincon_ready` gate, now measured rather than gated."""
    obs = _locked_board(bench_energy=0, logs=_MEGA_BRAVE_LOG)
    row = _pilot().explain(obs).options[0].promote_retreat_working
    assert row["my_yield"] == 0.0 and row["total"] < 0


# --- GENERAL: the prize-reach brake, now EMERGENT from Exposure (ADR-0073 §4/§7) ---------------
#
# `dont-promote-into-their-prize-reach` (−20) is DELETED. Exposing a body costs `prizes x 100`
# graded by the clock, so the 3-prize Mega is charged three times what the 1-prize Hariyama is —
# a continuous per-body price where the rung was a flag with a boolean stand-down.

def _promote(opp_prizes):
    cur = state(active=None, bench=[poke(MEGA_LUCARIO, hp=340), poke(HARIYAMA, hp=150)],
                opp_active=poke(WALL, hp=400), prizes=4, opp_prizes=opp_prizes)
    return make_select([card_opt(BENCH, 0), card_opt(BENCH, 1)], context=TO_ACTIVE, current=cur)


@pytest.mark.req("REQ-ML-0007")
def test_the_three_prize_mega_is_charged_three_times_the_one_prize_body():
    """Opponent at 3 prizes: promoting the 3-prize Mega risks handing them the match, so it carries
    strictly more Exposure than the 1-prize Hariyama on the identical board — and the cheap body is
    promoted. Per-body, which is the defect §4 fixes: the retired read resolved ONE body's verdict
    and applied it to every candidate."""
    opts = _pilot().explain(_promote(opp_prizes=3)).options
    mega, hariyama = opts[0].promote_retreat_working, opts[1].promote_retreat_working
    assert mega["exposure"] == pytest.approx(3 * hariyama["exposure"])
    assert hariyama["total"] > mega["total"]


@pytest.mark.req("REQ-ML-0007")
def test_exposure_scales_with_their_remaining_prizes_without_a_goal_band():
    """§7b: the near-goal escalation needs no `_NEAR_GOAL`/`_GOAL_BAND` weighting. Exposure itself is
    prize-count-blind — it prices what a Knock Out YIELDS — and the endgame enters through the fatal
    step's condition alone, so the same board reads the same exposure at 3 prizes and at 4."""
    at_three = _pilot().explain(_promote(opp_prizes=3)).options[0].promote_retreat_working
    at_four = _pilot().explain(_promote(opp_prizes=4)).options[0].promote_retreat_working
    assert at_three["exposure"] == pytest.approx(at_four["exposure"])


# --- GENERAL covered-as-is proof: Aura Jab's ATTACH_FROM load routes to the 2nd Mega ----------

@pytest.mark.req("REQ-ML-0008")
def test_aura_jab_load_concentrates_on_the_benched_second_mega():
    """At the ATTACH_FROM recipient pick, the concentrate rule routes the recovered Energy to the
    benched (Line) Mega short of Mega Brave's FF — not the needy off-line Hariyama."""
    cur = state(active=poke(SOLROCK, energy=1, hp=110),
                bench=[poke(MEGA_LUCARIO, energy=1, hp=340), poke(HARIYAMA, energy=2, hp=150)],
                opp_active=poke(WALL, hp=400))
    obs = make_select([card_opt(BENCH, 0), card_opt(BENCH, 1)], context=ATTACH_FROM, current=cur)
    p = _pilot()
    opts = p.explain(obs).options
    # `concentrate-accel-on-one-line-body` is DELETED (#139, ADR-0069 §7): concentration falls out of
    # the CONVEX typed build, so the body closest to its payoff simply out-builds the bare ones.
    assert opts[0].score == max(o.score for o in opts)
    assert "concentrate-accel-on-one-line-body" not in _fired(opts[1])   # Hariyama — off-Line
    assert p.decide(obs) == [0]


# --- GENERAL covered-as-is proof: go-first declaration -----------------------------------------

@pytest.mark.req("REQ-ML-0009")
def test_preferred_start_first_takes_the_coin_toss():
    """Setup-heavy evolution deck declares preferred_start="first": at the coin toss, go first."""
    p = _pilot()
    obs = make_select([opt(YES), opt(NO)], context=IS_FIRST, current=state())
    assert p.decide(obs) == [0]                                          # YES = go first
    assert "honor-preferred-start" in _fired(p.explain(obs).options[1])  # fired on the NO option


# --- GENERAL: the damage-boost OHKO-line model (Power Pro / Black Belt's Training) -------------

def _boost_menu(hand, opp, extra_logs=(), active_tools=()):
    active = poke(MEGA_LUCARIO, energy=2, hp=340)
    active["tools"] = [{"id": t} for t in active_tools]
    cur = state(active=active, hand=hand, opp_active=opp)
    obs = make_select([opt(PLAY, index=0), attack_opt(MEGA_BRAVE), opt(END)],
                      context=MAIN, current=cur)
    obs["logs"] = list(extra_logs)
    return obs


@pytest.mark.req("REQ-ML-0010")
def test_power_pro_play_is_lethal_class_when_it_crosses_the_ko_line():
    """Mega Brave 270 vs a 300-HP wall: one Power Pro (+30, {F} attacker) crosses — the play is
    KO_SCORE-class and sequences ahead of the attack it enables."""
    p = _pilot()
    obs = _boost_menu([POWER_PRO], poke(WALL, hp=300))
    assert p.explain(obs).options[0].tactical >= 1000
    assert p.decide(obs) == [0]                              # play the boost first


@pytest.mark.req("REQ-ML-0010")
def test_power_pro_stacking_crosses_with_two_copies_but_not_one():
    """320-HP wall needs +50: one +30 copy can't cross (no lethal-class play); two copies can."""
    p = _pilot()
    assert p.explain(_boost_menu([POWER_PRO], poke(WALL, hp=320))).options[0].tactical < 1000
    assert p.explain(_boost_menu([POWER_PRO, POWER_PRO],
                                 poke(WALL, hp=320))).options[0].tactical >= 1000


@pytest.mark.req("REQ-ML-0010")
def test_power_pro_not_wasted_when_the_attack_already_kos():
    """The boost fires only when NECESSARY: vs a 270-HP wall Mega Brave already KOs — the play
    stays flat and the attack is taken."""
    p = _pilot()
    obs = _boost_menu([POWER_PRO], poke(WALL, hp=270))
    assert p.explain(obs).options[0].tactical < 1000
    assert p.decide(obs) == [1]                              # just attack


@pytest.mark.req("REQ-ML-0011")
def test_played_power_pro_boosts_the_attack_itself():
    """After the Power Pro PLAY log lands (this turn), the attack's own tactical prices 270+30 ≥
    300 — the boosted KO is visible, not just the play."""
    p = _pilot()
    played = [{"type": 10, "playerIndex": 0, "cardId": POWER_PRO}]
    obs = _boost_menu([], poke(WALL, hp=300), extra_logs=played)
    assert p.explain(obs).options[1].tactical >= 1000        # Mega Brave now KOs
    no_log = _pilot().explain(_boost_menu([], poke(WALL, hp=300))).options[1]
    assert no_log.tactical < 1000                            # without the play it's a 270 chip


@pytest.mark.req("REQ-ML-0012")
def test_black_belts_play_is_lethal_class_vs_an_ex_at_the_breakpoint():
    """Black Belt's Training (Supporter, +40 vs an ex Active): playing it crosses 270→310 on a
    310-HP ex. Silent vs a non-ex wall (the defender gate). Replaced Maximum Belt as the ex-boost;
    now a PLAY (one/turn), not a Tool ATTACH."""
    p = _pilot()
    ex = _boost_menu([BLACK_BELTS], poke(EX_WALL, hp=310))
    assert p.explain(ex).options[0].tactical >= 1000                     # the Black Belt's PLAY
    non_ex = _boost_menu([BLACK_BELTS], poke(WALL, hp=310))
    assert _pilot().explain(non_ex).options[0].tactical < 1000           # defender not an ex → gated


@pytest.mark.req("REQ-ML-0012")
def test_played_black_belts_boosts_the_attack_vs_the_ex():
    """After the Black Belt's PLAY log lands, the attack itself prices 270+40 ≥ 310 vs the ex —
    the boosted KO is visible on Mega Brave; gated off vs a non-ex defender."""
    p = _pilot()
    played = [{"type": 10, "playerIndex": 0, "cardId": BLACK_BELTS}]
    obs = _boost_menu([], poke(EX_WALL, hp=310), extra_logs=played)
    assert p.explain(obs).options[1].tactical >= 1000                    # Mega Brave now KOs the ex
    non_ex = _boost_menu([], poke(WALL, hp=310), extra_logs=played)
    assert _pilot().explain(non_ex).options[1].tactical < 1000           # vs-ex gate holds


# --- GENERAL: Wild Press recoil-doom charge ----------------------------------------------------

def _wild_press_menu(opp):
    cur = state(active=poke(HARIYAMA, energy=3, hp=150), opp_active=opp)
    return make_select([attack_opt(WILD_PRESS), opt(END)], context=MAIN, current=cur)


@pytest.mark.req("REQ-ML-0013")
def test_wild_press_charged_when_recoil_flips_a_safe_body_doomed():
    """150-HP Hariyama vs a 100-damage wall: safe now (100<150) but 80 after recoil — the non-KO
    chip is charged below its raw 210."""
    tac = _pilot().explain(_wild_press_menu(poke(WALL, hp=400))).options[0].tactical
    assert 0 < tac < 150                                     # 210 − eff − _RECOIL_DOOM


@pytest.mark.req("REQ-ML-0013")
def test_wild_press_unchanged_when_the_recoil_keeps_it_safe():
    """A 60-damage defender can't reach the post-recoil 80 — no charge, full 210 chip."""
    weak = poke(CHARGED, energy=1, hp=400)                   # CHARGED has no attacks -> incoming 0
    tac = _pilot().explain(_wild_press_menu(weak)).options[0].tactical
    assert tac > 200


@pytest.mark.req("REQ-ML-0013")
def test_wild_press_ko_is_never_charged():
    """Trading the body FOR a prize is the accepted deal: a 200-HP KO prices KO_SCORE-class even
    though the recoil dooms Hariyama."""
    tac = _pilot().explain(_wild_press_menu(poke(WALL, hp=200))).options[0].tactical
    assert tac >= 1000


# --- deck: stadium tech reads ------------------------------------------------------------------

@pytest.mark.req("REQ-ML-0014")
def test_gravity_mountain_endorsed_vs_a_stage2_board():
    p = _pilot()
    cur = state(active=poke(SOLROCK, energy=1, hp=110), hand=[GRAVITY_MOUNTAIN],
                opp_active=poke(WALL, hp=400), opp_bench=[poke(STAGE2, hp=170)])
    obs = make_select([opt(PLAY, index=0)], context=MAIN, current=cur)
    assert "gravity-mountain-vs-stage2" in _fired(p.explain(obs).options[0])
    no_s2 = state(active=poke(SOLROCK, energy=1, hp=110), hand=[GRAVITY_MOUNTAIN],
                  opp_active=poke(WALL, hp=400))
    obs2 = make_select([opt(PLAY, index=0)], context=MAIN, current=no_s2)
    assert "gravity-mountain-vs-stage2" not in _fired(_pilot().explain(obs2).options[0])


# (test_watchtower_* REMOVED 2026-07-03 — Team Rocket's Watchtower was cut from the deck and the
# `watchtower-vs-colorless-abilities` rule retired. Gravity Mountain is now the sole Stadium.)


# --- deck: the Lunar Cycle pair (fire it aggressively; never strand the last F) ----------------

def _lunar_menu(hand, energy_attached=False):
    cur = state(active=poke(SOLROCK, energy=0, hp=110), bench=[poke(LUNATONE, hp=110)],
                hand=hand, opp_active=poke(WALL, hp=400))
    cur["energyAttached"] = energy_attached
    return make_select([opt(ABILITY, area=BENCH, index=0), opt(END)], context=MAIN, current=cur)


@pytest.mark.req("REQ-ML-0015")
def test_fire_lunar_cycle_with_surplus_f_in_hand():
    """Two F in hand: the draw-3 fires (and outranks passing)."""
    p = _pilot()
    obs = _lunar_menu([F_ENERGY, F_ENERGY])
    assert "fire-lunar-cycle" in _fired(p.explain(obs).options[0])
    assert p.decide(obs) == [0]


@pytest.mark.req("REQ-ML-0015")
def test_lunar_cycle_guard_holds_the_last_attachable_f():
    """ONE F in hand, attach still pending, a body can absorb it: the guard fires and the fire-rule
    stands down — hold the F for the attach (the ability re-fires after it)."""
    opts = _pilot().explain(_lunar_menu([F_ENERGY])).options
    assert "dont-lunar-cycle-away-the-last-attachable-f" in _fired(opts[0])
    assert "fire-lunar-cycle" not in _fired(opts[0])


@pytest.mark.req("REQ-ML-0015")
def test_lunar_cycle_fires_once_the_turns_attach_is_done():
    """Same single F but the Energy is already attached this turn: the guard stands down."""
    opts = _pilot().explain(_lunar_menu([F_ENERGY], energy_attached=True)).options
    assert "dont-lunar-cycle-away-the-last-attachable-f" not in _fired(opts[0])
    assert "fire-lunar-cycle" in _fired(opts[0])
