"""The **State Value** scalar (`common/state_value.py`, POC-T3 / Issue #262, ADR-0092 §4-T3).

T0 (Issue #259) froze the contract; T3 fills in the equations. So this file now has two jobs. The
first is unchanged from T0 — the coverage map, the double-counting rule, the unit basis — because
those are what stop the scalar from silently pricing one fact twice or no times.

    The two tests that matter most are `test_no_fact_is_priced_twice` and
    `test_no_fact_is_priced_by_nobody`. They are the executable form of T0's headline rule, and the
    rule earned its enforcement — an empty Bench under a knock-outable Active reached the draft
    sound-rule whitelist through THREE mechanisms simultaneously (a terminal rung, an order filter
    and a +60 weight), and nothing about writing that list prompted the question (ADR-0096).

The second job is T3's, and it is dominated by ONE class: **mid-turn monotonicity**. Issue #263's
composer orders every candidate by 1-ply differencing, so `state_value` is evaluated on half-finished
turns far more often than on finished ones. A term that quietly assumed a completed turn would not
crash — it would produce garbage orderings and prune good lines before the leaf could vindicate them,
which is invisible from any test that only ever scores end-of-turn boards.

Construction follows `test_state_model.py`: a dict-backed Stat Provider and hand-built zone dicts, no
Pilot and no engine boot. Card facts VERIFIED at source (`data/EN_Card_Data.csv`) — never recalled:
  * Riolu (677) Basic HP 80, {F}; Mega Lucario ex (678) Stage 1 HP 340, evolvesFrom **Riolu** —
    a SINGLE hop, with no intermediate Lucario in this set (`docs/rulebook.txt` Appendix 1).
    Aura Jab ``{F}`` 130 / Mega Brave ``{F}{F}`` 270.
  * Dragapult ex (121) Stage 2 HP 320, {N} — Jet Headbutt ``●`` 70 / Phantom Dive ``{R}{P}`` 200.
  * Munkidori (112) Basic HP 70, {D}.
  * Basic Energy card ids: 2 = {R}, 5 = {P}, 7 = {D}, and {F} is added here as 6.
  * Prize values: Mega ex 3, ex 2, else 1 (`docs/rules.md` §6).
"""
from __future__ import annotations

import pytest

from common import currency, state_value as sv
from common.card_worth import ROLE_TIER
from common.cards import CardFunctions
from common.effects import CardEffects
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.state_model import StateModel
from common.strategy.combat import CombatMath

# ── the fixture board ─────────────────────────────────────────────────────────────────────────────

COLORLESS, GRASS, FIRE, WATER, PSYCHIC, FIGHTING, DARKNESS, DRAGON = 0, 1, 2, 3, 5, 6, 7, 9
DRAGAPULT, MUNKIDORI, RIOLU, MEGA_LUC, MEGA_STARMIE = 121, 112, 677, 678, 1031
JET_HEADBUTT, PHANTOM_DIVE, AURA_JAB, MEGA_BRAVE = 9121, 9122, 982, 983
JETTING_BLOW, NEBULA_BEAM = 9131, 9132
E_R, E_P, E_F, E_D = 2, 5, 6, 7
#: The bench-GATED pair, and the ONE the shipped decks actually expose (Issue #287). Verified at
#: source: Solrock (676) Basic HP 110 {F}, weak {G}, retreat 1 — Cosmic Beam ``{F}`` 70, *"If you
#: don't have Lunatone on your Bench, this attack does nothing. This attack's damage isn't affected
#: by Weakness or Resistance."* — its only attack. Lunatone (675) Basic HP 110 {F}, weak {G},
#: retreat 1 — Ability Lunar Cycle, and Power Gem ``{F}{F}`` 50. `mega_lucario` runs 3x Solrock and
#: 2x Lunatone, and they are each other's enablers: Lunar Cycle needs Solrock in play, Cosmic Beam
#: needs Lunatone on the Bench.
SOLROCK, LUNATONE = 676, 675
COSMIC_BEAM, POWER_GEM = 9676, 9675
#: The conditional-BONUS shape, as opposed to the conditional-ZERO one above — Metagross (276)
#: Stage 2 HP 170 {P}, `evolvesFrom` Metang: Wrack Down ``{P}`` 60 and Conjoined Beams ``{P}{P}``
#: **130**, *"If Beldum and Metang are on your Bench, this attack does 150 more damage."* Verified
#: at source. `slowking` runs 2x and neither partner, so the bonus is unpayable for the whole match.
METAGROSS = 276
WRACK_DOWN, CONJOINED_BEAMS = 9276, 9277

_STATS = {
    DRAGAPULT: CardStat(DRAGAPULT, name="Dragapult ex", hp=320, ex=True, stage2=True,
                        evolvesFrom="Drakloak", energyType=DRAGON, maxDamage=200, maxDamageCost=2,
                        minAttackCost=1, minCostDamage=70,
                        attacks=(JET_HEADBUTT, PHANTOM_DIVE), cardType=0),
    MUNKIDORI: CardStat(MUNKIDORI, name="Munkidori", hp=70, energyType=DARKNESS, cardType=0),
    RIOLU: CardStat(RIOLU, name="Riolu", hp=80, energyType=FIGHTING, minAttackCost=2,
                    maxDamage=30, maxDamageCost=2, attacks=(), cardType=0),
    MEGA_LUC: CardStat(MEGA_LUC, name="Mega Lucario ex", hp=340, megaEx=True, energyType=FIGHTING,
                       evolvesFrom="Riolu", maxDamage=270, maxDamageCost=2, minAttackCost=1,
                       minCostDamage=130,
                       attacks=(AURA_JAB, MEGA_BRAVE), cardType=0),
    SOLROCK: CardStat(SOLROCK, name="Solrock", hp=110, energyType=FIGHTING, weakness=GRASS,
                      minAttackCost=1, maxDamage=70, maxDamageCost=1, minCostDamage=70,
                      attacks=(COSMIC_BEAM,), cardType=0),
    LUNATONE: CardStat(LUNATONE, name="Lunatone", hp=110, energyType=FIGHTING, weakness=GRASS,
                       minAttackCost=2, maxDamage=50, maxDamageCost=2, minCostDamage=50,
                       attacks=(POWER_GEM,), cardType=0),
    METAGROSS: CardStat(METAGROSS, name="Metagross", hp=170, stage2=True, evolvesFrom="Metang",
                        energyType=PSYCHIC, minAttackCost=1, maxDamage=130, maxDamageCost=2,
                        minCostDamage=60, attacks=(WRACK_DOWN, CONJOINED_BEAMS), cardType=0),
    E_R: CardStat(E_R, name="Basic {R} Energy", cardType=5, energyType=FIRE),
    E_P: CardStat(E_P, name="Basic {P} Energy", cardType=5, energyType=PSYCHIC),
    E_F: CardStat(E_F, name="Basic {F} Energy", cardType=5, energyType=FIGHTING),
    E_D: CardStat(E_D, name="Basic {D} Energy", cardType=5, energyType=DARKNESS),
    #: Added for ADR-0064 Amendment B's BENCH leg (Issue #283) — the only opponent in this fixture
    #: whose attack reaches my Bench at all. Verified at source, and carried WHOLE rather than
    #: trimmed to the one attack the test needs: Mega Starmie ex (1031) Stage 1 HP 330, {W},
    #: `Mega Pokémon ex` -> 3 prizes, evolvesFrom **Staryu**, Jetting Blow ``{W}`` 120 *"also does
    #: 50 damage to 1 of your opponent's Benched Pokémon"* and Nebula Beam ``●●●`` 210. A fixture
    #: that quietly drops the second attack would carry a `maxDamage` the real card contradicts.
    #: Referenced by exactly one test, so no existing assertion moves.
    MEGA_STARMIE: CardStat(MEGA_STARMIE, name="Mega Starmie ex", hp=330, megaEx=True,
                           energyType=WATER, evolvesFrom="Staryu", maxDamage=210, maxDamageCost=3,
                           minAttackCost=1, minCostDamage=120,
                           attacks=(JETTING_BLOW, NEBULA_BEAM), cardType=0),
}
_ATTACKS = {
    JET_HEADBUTT: AttackStat(JET_HEADBUTT, damage=70, cost=1, energyTypes=(COLORLESS,)),
    PHANTOM_DIVE: AttackStat(PHANTOM_DIVE, damage=200, cost=2, energyTypes=(FIRE, PSYCHIC)),
    AURA_JAB: AttackStat(AURA_JAB, damage=130, cost=1, energyTypes=(FIGHTING,)),
    MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=2, energyTypes=(FIGHTING, FIGHTING)),
    COSMIC_BEAM: AttackStat(COSMIC_BEAM, damage=70, cost=1, energyTypes=(FIGHTING,),
                            requiresBench=("Lunatone",), ignoresWeakness=True,
                            ignoresResistance=True),
    POWER_GEM: AttackStat(POWER_GEM, damage=50, cost=2, energyTypes=(FIGHTING, FIGHTING)),
    WRACK_DOWN: AttackStat(WRACK_DOWN, damage=60, cost=1, energyTypes=(PSYCHIC,)),
    # `damageMax` 280 is the +150 leg, exactly as the provider carries it: the bonus is REACHABLE
    # through the oracle's "max" bound and must not be reachable through this read.
    CONJOINED_BEAMS: AttackStat(CONJOINED_BEAMS, damage=130, cost=2,
                                energyTypes=(PSYCHIC, PSYCHIC), damageMax=280),
    JETTING_BLOW: AttackStat(JETTING_BLOW, damage=120, cost=1, energyTypes=(WATER,), benchSnipe=50),
    NEBULA_BEAM: AttackStat(NEBULA_BEAM, damage=210, cost=3, energyTypes=(COLORLESS,) * 3),
}
DECK = [E_F] * 6 + [RIOLU] * 3 + [MEGA_LUC] * 3 + [MUNKIDORI]
#: `mega_lucario`'s single-prize core beside the Mega line — the deck the Solrock cases score
#: against, so the deck-fetch leg of `readiness_p` sees the Energy the pair actually runs.
LUNAR_DECK = [E_F] * 6 + [RIOLU] * 3 + [MEGA_LUC] * 3 + [SOLROCK] * 3 + [LUNATONE] * 2

#: The deck's DECLARED Roles as Worth (`card_worth.ROLE_TIER`), supplied through the model's
#: `role_worth=` resolver. Roles are declaration, not card data — `card_worth.role_value` says so
#: outright ("the Pilot supplies ``roles``") and `CardStat` carries no such field — so a fixture that
#: tried to put them on the stat would be testing an API that does not exist.
_ROLE_WORTH = {MEGA_LUC: ROLE_TIER["win_condition"], RIOLU: ROLE_TIER["win_condition_base"],
               MUNKIDORI: ROLE_TIER["engine"], DRAGAPULT: ROLE_TIER["primary_attacker"],
               SOLROCK: ROLE_TIER["secondary_attacker"], LUNATONE: ROLE_TIER["engine"],
               METAGROSS: ROLE_TIER["secondary_attacker"]}


def _combat():
    return CombatMath(DictCardStatProvider(_STATS, attacks=_ATTACKS),
                      functions=CardFunctions({}), transients=None, effects=CardEffects({}))


def _poke(cid, *, hp, energies=(), serial=1, damage=0):
    return {"id": cid, "hp": hp - damage, "energies": list(energies), "serial": serial}


def _player(*, active=None, bench=(), hand=(), discard=(), prize=4, deck_count=20):
    return {"active": [active] if active else [], "bench": list(bench),
            "hand": [{"id": c} for c in hand], "handCount": len(hand),
            "discard": [{"id": c} for c in discard], "prize": [None] * prize,
            "deckCount": deck_count,
            "poisoned": False, "burned": False, "asleep": False, "paralyzed": False,
            "confused": False}


def _model(me, opp, *, energy_attached=False, turn=5, needs=None, deck=None):
    obs = {"current": {"players": [me, opp], "yourIndex": 0, "turn": turn,
                       "energyAttached": energy_attached, "supporterPlayed": False,
                       "stadium": []}, "logs": []}
    return StateModel.build(obs, combat=_combat(), deck=DECK if deck is None else deck,
                            needs=needs, role_worth=_ROLE_WORTH.get)


def _lucario_board(*, my_energies=(), my_hp=340, bench=(), my_prizes=4, their_prizes=4,
                   their_active=None, hand=(), energy_attached=False):
    """MY Mega Lucario ex Active against THEIR Dragapult ex — the fixture every monotonicity case
    perturbs by exactly one fact."""
    return _model(
        _player(active=_poke(MEGA_LUC, hp=my_hp, energies=my_energies), bench=list(bench),
                hand=list(hand), prize=my_prizes),
        _player(active=their_active or _poke(DRAGAPULT, hp=320, energies=[E_R, E_P], serial=9),
                prize=their_prizes),
        energy_attached=energy_attached)


# ── the coverage map — T0's headline rule, executable ─────────────────────────────────────────────


@pytest.mark.req("REQ-STATEVALUE-0001")
def test_no_fact_is_priced_twice():
    """`every board fact enters through exactly ONE term family` (ADR-0092 §4-T0).

    A fact priced by two families is counted twice in the scalar, and the error is invisible: the
    number still looks plausible, which is precisely how the empty-Bench fact acquired three guards
    without anyone noticing while writing them down.

    T3 widened this to span BOTH registries, so `attack_ev` cannot re-price what `threat` already
    prices — which matters because `score(sequence)` literally adds the two together."""
    assert sv.double_counted() == []


@pytest.mark.req("REQ-STATEVALUE-0001")
def test_no_fact_is_priced_by_nobody():
    """The rule's other half. A play that changes state and that no family reads prices 0 — and a
    silent 0 is indistinguishable from a correct 0. `does_not_read` is what gives a gap an address:
    a fact one family disclaims and no family claims is a hole, reported here rather than discovered
    as a mis-priced decision three tracks later."""
    assert sv.registry_gaps() == []


@pytest.mark.req("REQ-STATEVALUE-0001")
def test_the_registry_holds_exactly_the_six_families_the_plan_names():
    """The families are ADR-0092 §4-T0's, and the set is the contract other tracks build against —
    T3 implements these and no others, and `working` carries exactly these keys."""
    assert [f.name for f in sv.REGISTRY] == [
        "prize_race", "survival", "threat", "readiness", "hand", "development"]
    assert set(sv.FAMILIES) == {f.name for f in sv.REGISTRY}


@pytest.mark.req("REQ-STATEVALUE-0001")
def test_the_terminal_term_is_a_SEPARATE_registry_not_a_seventh_family():
    """`attack_ev` prices an ACTION, the six price a BOARD, and `score = state_value(end) +
    EV(terminal)` adds one of each. Folding it into `REGISTRY` would make `state_value(model)`
    answerable only for models that arrived with an action attached — the provenance-dependence
    Issue #262 forbids in the same breath."""
    assert [f.name for f in sv.TERMINAL_REGISTRY] == ["attack_ev"]
    assert "attack_ev" not in sv.FAMILIES
    assert set(sv.TERMINAL_FAMILIES) == {"attack_ev"}


@pytest.mark.req("REQ-STATEVALUE-0001")
def test_every_family_states_what_it_refuses_as_well_as_what_it_prices():
    """A family declaring no `does_not_read` has opted out of the gap-detection above — it can never
    contribute a named hole, so the coverage map would silently weaken as families were added."""
    for f in sv.REGISTRY + sv.TERMINAL_REGISTRY:
        assert f.reads, f.name
        assert f.does_not_read, f.name
        assert f.composition.strip(), f.name


@pytest.mark.req("REQ-STATEVALUE-0005")
def test_every_family_publishes_an_ACTIONABLE_blind_spot_list():
    """Issue #263's ordering ruling makes this a deliverable, not documentation: its composer reads
    `blind_spots()` as its blind-spot checklist, because a play moving state no family reads prices
    at exactly 0 delta and at ordering time 0 means *never explored*.

    "Actionable" is asserted rather than trusted: every family contributes at least one entry, and
    every entry has to be long enough to name a dimension AND say who owns closing it — a bare word
    would be a checklist item nobody could act on."""
    spots = sv.blind_spots()
    assert set(spots) == {f.name for f in sv.REGISTRY + sv.TERMINAL_REGISTRY}
    for name, entries in spots.items():
        assert entries, name
        for entry in entries:
            assert len(entry) > 60, (name, entry)
            assert "—" in entry, (name, entry)


# ── the unit basis ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-STATEVALUE-0002")
def test_the_worth_scaffold_is_reconciled_against_its_anchor_not_pinned_as_a_literal():
    """ADR-0097 decision 1: the rate is authored, but it must be STATED against the incumbents
    rather than dropped in beside them. Asserting the arithmetic instead of the number is what makes
    that binding — if `currency.py` re-derives `DEPLOY_BAND` or `DEPLOY_WORTH_SCALE`, this fails
    loudly instead of leaving a fourth silent rate behind.

    Modelled on `test_currency.py`, which recomputes `PRIZE_DAMAGE_RATE` from the CSV rather than
    asserting the literal, for exactly the same reason."""
    assert sv.POC_WORTH_PRIZE_RATE == pytest.approx(
        currency.DEPLOY_BAND / currency.DEPLOY_WORTH_SCALE / currency.PRIZE_DAMAGE_RATE)
    # Re-stated as damage-per-worth-point, the form ADR-0097 requires the reconciliation in.
    per_worth_damage = sv.POC_WORTH_PRIZE_RATE * currency.PRIZE_DAMAGE_RATE
    assert per_worth_damage == pytest.approx(25.0 / 30.0, rel=1e-6)
    # Inside the catalogued spread (deploy 0.83 .. energy 6.67), which is the honesty condition —
    # a value outside it would be evidence about the incumbents, per ADR-0078's own rule.
    assert 25.0 / 30.0 <= per_worth_damage <= (160.0 / 3.0) / 8.0


@pytest.mark.req("REQ-STATEVALUE-0002")
def test_the_worth_scaffold_SETTLES_the_gust_seams_disagreement_by_REFERENT_not_by_averaging():
    """`currency.py` names this constant as the one that must settle the ~39x prize↔worth
    disagreement ADR-0107 recorded. It settles it by showing the two rates answer DIFFERENT
    questions — neither moves.

    `GUST_TARGET_WORTH_RATE` converts a prize-equivalent INTO Worth so an opponent-target slot can be
    ranked inside a Worth-denominated DP against other slots. `POC_WORTH_PRIZE_RATE` converts a HELD
    CARD's Worth into prizes so spending it can be priced against a board. Same scale pair, opposite
    directions, different referents — the resolution the energy outlier already got.

    The reductio is the assertion that matters: adopt the gust seam's rate for the hand and a held
    win-condition prices at **more than the entire game**. That is not a constant needing a split, it
    is evidence that Worth is an ORDINAL priority scale inside the assignment rather than a quantity
    globally exchangeable with prizes — which is `currency.py`'s own reading ("that scale's whole
    range is 0–30 by construction … Pricing the hand ON ITS OWN SCALE is what the DP is for").

    Guards the tempting fix: averaging the two into one "general" rate would silently break both
    seams at once, and would manufacture the general Worth Damage Rate ADR-0080 ran a gate to
    establish does not exist."""
    from common.card_worth import ROLE_TIER

    mine_worth_per_prize = 1.0 / sv.POC_WORTH_PRIZE_RATE
    gust_worth_per_prize = currency.GUST_TARGET_WORTH_RATE
    assert mine_worth_per_prize / gust_worth_per_prize > 40.0, (
        "the disagreement is real and RECORDED — if it ever closes, say so deliberately")

    # My rate sits with the composed shipped legs (PRIZE_DAMAGE_RATE / ITEM_HOLD_WORTH_RATE = 100
    # worth per prize) — within 20%, the precision an authored POC scaffold can honestly claim.
    composed = currency.PRIZE_DAMAGE_RATE / currency.ITEM_HOLD_WORTH_RATE
    assert abs(mine_worth_per_prize - composed) / composed <= 0.20

    # The reductio. A held wincon is a quarter of a prize on this scaffold; on the gust seam's rate
    # it would be worth nearly twice the six prizes that END the match (`docs/rulebook.txt` L57).
    wincon = ROLE_TIER["win_condition"]
    assert wincon * sv.POC_WORTH_PRIZE_RATE == pytest.approx(0.25)
    assert wincon / gust_worth_per_prize > 6.0


@pytest.mark.req("REQ-STATEVALUE-0002")
def test_the_worth_scaffold_never_migrates_into_currency():
    """`common/currency.py`'s contract is "DERIVED and never tuned"; this constant is the opposite,
    and ADR-0080's underivability measurement stands as the historical record of what was true.

    Asserted rather than trusted to review, because the migration is the tempting one: a second
    consumer arrives, someone hoists it "where the other rates live", and the module that promises
    derivation is quietly holding an invention."""
    assert not hasattr(currency, "POC_WORTH_PRIZE_RATE")
    assert not hasattr(currency, "WORTH_DAMAGE_RATE"), (
        "ADR-0080 ran the anchor gate and it FAILED — the constant is absent BY DESIGN, not pending")


@pytest.mark.req("REQ-STATEVALUE-0004")
def test_the_worth_leg_is_scale_invariant():
    """THE test T0 owed, modelled on `test_deploy_value.py::test_the_worth_legs_are_dimensionless`:
    re-point the rate and assert what does and does not move.

    `hand` is LINEAR in the rate and every other family is INDEPENDENT of it. A regression
    reintroducing a raw Worth magnitude in another family — or a raw damage magnitude inside `hand` —
    would otherwise be silent, because the numbers would still look plausible."""
    legs = dict(assignment_coverage=30.0, re_access=4.0, hand_worth=2.0)
    base = sv.hand(**legs, worth_prize_rate=0.01)
    assert sv.hand(**legs, worth_prize_rate=0.02) == pytest.approx(2.0 * base)
    assert sv.hand(**legs, worth_prize_rate=0.0) == 0.0

    # The other families never see the rate at all — asserted by re-pointing the MODULE constant and
    # checking they are unmoved, which is stronger than checking their signatures.
    original = sv.POC_WORTH_PRIZE_RATE
    try:
        before = (sv.prize_race(my_prizes_remaining=3, their_prizes_remaining=5),
                  sv.survival([sv.ExposedBody(2.0, 2)]), sv.threat([1.0]),
                  sv.readiness([sv.ReadyBody(2.1, 0.5, 1.0)]),
                  sv.development(deploy_marginal=0.2, evolve_marginal=0.1,
                                 bench_slot_price=0.05, line_topology=0.0))
        sv.POC_WORTH_PRIZE_RATE = original * 7.0
        after = (sv.prize_race(my_prizes_remaining=3, their_prizes_remaining=5),
                 sv.survival([sv.ExposedBody(2.0, 2)]), sv.threat([1.0]),
                 sv.readiness([sv.ReadyBody(2.1, 0.5, 1.0)]),
                 sv.development(deploy_marginal=0.2, evolve_marginal=0.1,
                                bench_slot_price=0.05, line_topology=0.0))
        assert before == after
    finally:
        sv.POC_WORTH_PRIZE_RATE = original


@pytest.mark.req("REQ-STATEVALUE-0002")
def test_the_readiness_scale_is_the_planners_own_weight_carried_at_the_same_band():
    """Old Issue #145's seeding methodology, method 1 — *anchor to the retired predecessor's
    magnitude* (the currency-zone rule: replace at the same band, never stack).

    `_READINESS_W` cannot be imported from the planner at runtime (the planner's leaf imports this
    module, so the edge would be a cycle), which is exactly why the anchor has to be asserted here
    instead of expressed in code. Without this, a planner retune would silently leave the two
    readiness scales disagreeing."""
    from common.strategy.context import KO_SCORE
    from common.strategy.planner import _READINESS_ATTACK_W, _READINESS_SATURATED
    assert sv._READINESS_W == pytest.approx(
        _READINESS_ATTACK_W * currency.PRIZE_DAMAGE_RATE / KO_SCORE)
    # The repeated-utility-body discount is a straight carry-over, so it must stay equal, not merely
    # close: `planner._readiness_saturation` and `state_value._saturation` answer the same question
    # about the same board, and two different answers would be a divergence nothing reports.
    assert sv._SATURATED == _READINESS_SATURATED


# ── the bands, and the terminal dominance they support ────────────────────────────────────────────


@pytest.mark.req("REQ-STATEVALUE-0006")
def test_a_predicted_loss_outscales_every_other_family_combined():
    """`ko-score-band`'s terminal half, and the reason `LOSS_PRIZES` is DERIVED rather than
    transcribed. The incumbent rung returned a flat −KO_SCORE and leaned on a positional band of
    590 < 1000; two of these families are prize-denominated and uncapped, so a transcribed −1.0
    would be out-scaled by two exposed ex bodies and the agent would walk into a loss to save a
    Pokémon.

    The bound is computed from the same constants the equations use, so moving any of them moves
    this test rather than silently breaking the invariant."""
    worst_survival = sv._MAX_BODIES * sv._MAX_PRIZE_VALUE
    worst_race = sv._PRIZES_START + sv._PROXIMITY_W
    assert sv.LOSS_PRIZES > worst_survival + worst_race + sv.POSITIONAL_MAX

    # And in the shape a caller actually meets it: a doomed board still ranks below a board that has
    # simply lost every body it owns.
    doomed = sv.survival([sv.ExposedBody(3.0, 1)], predicted_loss=True)
    merely_awful = sv.survival([sv.ExposedBody(3.0, 1)] * sv._MAX_BODIES)
    assert doomed < merely_awful

    # …and end-to-end through the scalar on a board that is PRIZE-lethal rather than bench-empty
    # (ADR-0064 Amendment B) — the second case must inherit the same dominance, not merely the same
    # constant. Every positional family is free to be as favourable as this fixture allows; the
    # scalar still has to rank the lethal board below the identical board they cannot yet win on.
    lethal = _lucario_board(my_hp=60, bench=[_poke(RIOLU, hp=80, serial=2)], their_prizes=3)
    survivable = _lucario_board(my_hp=60, bench=[_poke(RIOLU, hp=80, serial=2)], their_prizes=4)
    assert sv.state_value(survivable) - sv.state_value(lethal) > sv.POSITIONAL_MAX


# ── case 1: prize lethality (ADR-0064 Amendment B, Issue #283) ────────────────────────────────────
#
# `docs/rules.md` §7 case 1 — *they take their last prize card*. The positional families price "they
# are at 3 and my Active is a 3-prize Mega" identically to "they are at 6": `survival` owns
# `prize_at_risk`, `prize_race` owns the counts, and the double-counting rule forbids the two of
# them to form the product between them. The terminal term is the one licensed to.
#
# Every board below carries a NON-EMPTY Bench, so case 2 is structurally out of the picture and only
# case 1 can be moving the number. The doomed reading is the fixture's own: my Mega Lucario ex at 60
# HP under a fully-funded Phantom Dive 200.


#: Half of the terminal charge — the epsilon every assertion below uses to say *"this gap is the
#: terminal term firing, not positional drift"*. Named rather than repeated inline because a bare
#: `LOSS_PRIZES / 2.0` reads as arithmetic when what it means is a THRESHOLD, and the whole point of
#: `LOSS_PRIZES` being DERIVED is that no positional sum can cross it.
_TERMINAL_JUMP = sv.LOSS_PRIZES / 2.0


def _survival_of(me, opp) -> float:
    """The `survival` leg alone, off a full `state_value` evaluation of the two player dicts.

    Read through `working` rather than by calling `sv.survival` directly, deliberately: the point of
    every case below is what the SCALAR does with the board, and a test that composed the family by
    hand could pass while `_terms` fed it something else."""
    working: dict = {}
    sv.state_value(_model(me, opp), working=working)
    return working["survival"]


def _bench_riolu(serial=2):
    """A benched 1-prize soak — it removes case 2 from the picture and can never fire case 1."""
    return _poke(RIOLU, hp=80, serial=serial)


def _survival_at(**kw) -> float:
    """`survival` on the `_lucario_board` fixture with a Bench, varied by `my_hp` / `their_prizes`."""
    working: dict = {}
    sv.state_value(_lucario_board(bench=[_bench_riolu()], **kw), working=working)
    return working["survival"]


@pytest.mark.req("REQ-LOSSRUNG-0001")
def test_the_same_doomed_body_is_a_LOSS_at_three_prizes_and_merely_exposed_at_six():
    """The headline: identical body, identical clock, only THEIR prize count differs.

    My Mega Lucario ex is worth 3 prizes (`megaEx`, `docs/rules.md` §6) and is doomed at 60 HP. At 3
    prizes remaining that Knock Out yields exactly the 3 they need and the match ends; at 6 it is an
    expensive body and no more. Before this term the two scored the same."""
    assert _survival_at(my_hp=60, their_prizes=3) < _survival_at(my_hp=60, their_prizes=6) - _TERMINAL_JUMP
    # The boundary is `>=`, not `>`: 3 prizes for a 3-prize body ends it, 4 does not.
    assert _survival_at(my_hp=60, their_prizes=4) == _survival_at(my_hp=60, their_prizes=6)


@pytest.mark.req("REQ-LOSSRUNG-0001")
def test_the_mega_lucario_prize_trade_shape_a_one_prize_body_is_not_a_loss():
    """`mega_lucario`'s CRITICAL doctrine (its STRATEGY.md §4, user-ruled 2026-06-29): interleave a
    1-prize body between Mega exposures, because *"Solrock → Lucario → Lucario"* hands them 7 and
    loses while *"Solrock → Lucario → Hariyama → Lucario"* buys the turn that wins.

    Same clock, same 3 prizes remaining: the 3-prize Mega Active is a predicted loss and a 1-prize
    Riolu Active is not. **Exactly when** is the other half of the doctrine and is asserted too — at
    6 prizes the separation vanishes, so the interleave is not a standing preference this term
    manufactures. It appears only once their count makes the Mega's loss lethal."""
    def _survival(active, their_prizes):
        return _survival_of(
            _player(active=active, bench=[_bench_riolu()], prize=4),
            _player(active=_poke(DRAGAPULT, hp=320, energies=[E_R, E_P], serial=9),
                    prize=their_prizes))

    mega, riolu = _poke(MEGA_LUC, hp=60), _poke(RIOLU, hp=60, serial=3)
    assert _survival(mega, 3) < _survival(riolu, 3) - _TERMINAL_JUMP
    # …and the separation is a LETHALITY effect, not a preference: at 6 it is only the prize values.
    assert _survival(mega, 6) - _survival(riolu, 6) > -_TERMINAL_JUMP


@pytest.mark.req("REQ-LOSSRUNG-0001")
def test_prize_lethality_is_BINARY_two_of_their_three_prizes_is_not_a_loss():
    """Issue #283's explicit POC ruling, and the reason `_predicted_loss` returns a BOOL: a 2-prize
    `ex` against 3 remaining is worse than the flat exposure above, but it is not a loss and the
    terminal term must not claim it is. A graded form is the named post-POC question, recorded in
    `survival`'s `blind_to` so the composer sees the margin as a named zero rather than an accident.

    Dragapult ex is a real 2-prize body (`data/EN_Card_Data.csv` id 121, Rule "Pokémon ex", 320 HP)
    — a fabricated prize value would contradict `docs/rules.md` §6 in the one test whose whole
    subject is a prize value."""
    def _survival(their_prizes):
        return _survival_of(
            _player(active=_poke(DRAGAPULT, hp=60), bench=[_bench_riolu()], prize=4),
            _player(active=_poke(MEGA_LUC, hp=340, energies=[E_F, E_F], serial=9),
                    prize=their_prizes))

    stat = DictCardStatProvider(_STATS, attacks=_ATTACKS).get(DRAGAPULT)
    assert stat.prize_value == 2                      # positive control: the body IS worth 2
    assert _survival(3) == _survival(4)               # 2 < 3 — no terminal claim
    assert _survival(2) < _survival(3) - _TERMINAL_JUMP     # 2 >= 2 ends the match


@pytest.mark.req("REQ-LOSSRUNG-0001")
def test_prize_lethality_needs_the_CLOCK_and_not_only_the_count():
    """It is a predicted LOSS, not an exposure re-priced. At full 340 HP the same 3-prize Mega
    out-lives Phantom Dive's 200, so their being at 3 prizes claims nothing — and the guard is
    ADR-0064's own `evo_min_energy=1`, shared with case 2 verbatim rather than re-derived."""
    assert _survival_at(my_hp=340, their_prizes=3) == _survival_at(my_hp=340, their_prizes=6)


@pytest.mark.req("REQ-LOSSRUNG-0001")
def test_prize_lethality_covers_a_BENCHED_body_through_the_snipe_rider():
    """§7 case 1 is about a BODY, not the Active Spot. Their Mega Starmie ex's Jetting Blow carries a
    50 bench-snipe rider (verified at source), so my chipped 3-prize Mega on the BENCH is reachable
    and its Knock Out takes their last 3 prizes.

    The area is declared to the clock (`my_benched=`), which is what keeps the read honest: the
    printed 120 lands on the Active only, and the rider is what reaches the Bench. The control is
    the same board one HP higher — 60 > the 50 rider, so nothing is reachable there and the count
    alone must claim nothing.

    Their attached ``{W}`` is the right type code for Jetting Blow but is NOT what makes the attack
    reachable: the ceiling energy policy credits an attack a body can pay under ``attached + 1``
    attach, and this one costs 1. Said here rather than implied, because a reader would otherwise
    take the Energy for the load-bearing part and a later change to the policy would look like a
    change to this test."""
    def _survival(bench_hp):
        return _survival_of(
            _player(active=_poke(RIOLU, hp=80),       # 1 prize — the ACTIVE leg cannot fire
                    bench=[_poke(MEGA_LUC, hp=bench_hp, serial=2)], prize=4),
            _player(active=_poke(MEGA_STARMIE, hp=330, energies=[WATER], serial=9), prize=3))

    assert _survival(50) < _survival(60) - _TERMINAL_JUMP


@pytest.mark.req("REQ-LOSSRUNG-0001")
def test_case_2_is_untouched_by_the_new_case_including_where_they_would_overlap():
    """Issue #283's third test bullet — *"Case 2 (bench-empty) behaviour unchanged"* — asserted
    rather than left to the pre-existing fixtures, because the two cases now share one function and
    a caller cannot see which of them fired.

    Three readings of the SAME bench-empty doomed board, at prize counts that respectively cannot
    fire case 1 (6), sit exactly on its boundary (3) and are inside it (2). Case 2 already charges
    `LOSS_PRIZES`, the charge is a bool, and so the board scores identically at all three — the new
    case can neither double-charge nor mask the old one. The `>` control is the same board with a
    Bench, which must NOT carry the charge at 6."""
    def _bench_empty(their_prizes):
        return _survival_of(_player(active=_poke(MEGA_LUC, hp=60), prize=4),
                            _player(active=_poke(DRAGAPULT, hp=320, energies=[E_R, E_P], serial=9),
                                    prize=their_prizes))

    assert _bench_empty(6) == _bench_empty(3) == _bench_empty(2)
    # positive control: the board IS carrying the case-2 charge, so the equality above is not
    # three readings of an inert term.
    assert _survival_at(my_hp=60, their_prizes=6) > _bench_empty(6) + _TERMINAL_JUMP


@pytest.mark.req("REQ-STATEVALUE-0006")
def test_the_bench_slot_price_escalates_so_the_last_slot_is_the_expensive_one():
    """Issue #232's spare-body cliff, priced instead of ruled. The deleted flat +60 `keep-a-bench`
    rung read 1.96 on a non-empty Bench against 61.96 on an empty one — the entire gap was the rung.

    Two properties: the marginal RISES with each slot consumed, and the LAST slot costs a full
    maximum-relevance deploy, so filling it with a spare Basic is a measured loss rather than a
    free action."""
    prices = [sv._bench_slot_price(k) for k in range(sv._BENCH_MAX + 1)]
    marginals = [b - a for a, b in zip(prices, prices[1:])]
    assert marginals == sorted(marginals), marginals
    assert marginals[-1] == pytest.approx(sv._DEPLOY_PRIZE_BAND)
    assert marginals[-1] > marginals[0] * 8


@pytest.mark.req("REQ-STATEVALUE-0006")
def test_no_positional_family_saturates_on_a_realistic_body():
    """The failure that made the incumbent caps un-transcribable. A saturated term has zero
    derivative, so under 1-ply differencing every play touching it prices at exactly 0 delta and is
    never explored — pruning-by-cap, arriving where a missing equation would have.

    Mega Lucario ex is the strongest body in the fixture set (270 printed damage, win_condition
    role), so if the caps do not bite here they do not bite anywhere in it."""
    payoff = 270.0 / currency.PRIZE_DAMAGE_RATE
    low = sv.readiness([sv.ReadyBody(payoff, 0.4, 1.0)])
    high = sv.readiness([sv.ReadyBody(payoff, 0.8, 1.0)])
    assert high > low, "readiness saturated: odds no longer move it"
    assert high < sv._READINESS_BODY_CAP, "the runaway guard is biting in normal play"


# ── the terminal-action term ──────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_attack_ev_prices_a_knockout_at_the_targets_prize_value():
    """The KO band. Mega Brave (270) against a 320 HP Dragapult ex does NOT knock out; Phantom Dive
    territory does. Both card facts verified at source in this file's header."""
    ko = sv.attack_ev(damage=340.0, target_hp=320.0, target_prizes=2.0)
    assert ko.knockout == pytest.approx(2.0) and ko.chip == 0.0
    chip = sv.attack_ev(damage=270.0, target_hp=320.0, target_prizes=2.0)
    assert chip.knockout == 0.0 and chip.chip == pytest.approx(2.0 * 270.0 / 320.0)


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_attack_ev_is_an_EXPECTATION_so_a_coin_attack_needs_no_archetype_branch():
    """Old Issue #145 amendment B: attack value is a random variable, and printed fixed damage is
    the degenerate certain case. A half-odds Knock Out is worth half the prize — the same equation,
    no branch, which is what lets a coin attack and a copy attack plug in as damage MODELS."""
    certain = sv.attack_ev(damage=340.0, target_hp=320.0, target_prizes=2.0)
    coin = sv.attack_ev(damage=340.0, target_hp=320.0, target_prizes=2.0, ko_probability=0.5)
    assert coin.knockout == pytest.approx(certain.knockout / 2.0)


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_a_rider_can_beat_raw_damage_and_a_self_lock_can_lose_to_a_recycle():
    """Issue #263's acceptance shapes, at the term level: both trade-offs must be REPRESENTABLE
    here, or the composer cannot express them however good its search is.

    Mega Lucario ex is the worked case (card facts at source): Aura Jab ``{F}`` 130 with its
    energy-recycle rider against Mega Brave ``{F}{F}`` 270 with a next-turn self-lock. Neither
    attack knocks out a 320 HP Dragapult ex, so the comparison is chip + riders vs chip − lock —
    exactly the two legs the ruling requires to appear in both EVs."""
    aura_jab = sv.attack_ev(damage=130.0, target_hp=320.0, target_prizes=2.0, economy_value=0.4)
    mega_brave = sv.attack_ev(damage=270.0, target_hp=320.0, target_prizes=2.0, next_turn_cost=0.9)
    assert aura_jab.total > mega_brave.total
    assert mega_brave.working()["next_turn_cost"] == 0.9  # the cost APPEARS, it is not folded away

    # And a snipe rider outranking a bigger straight hit (the Mega Starmie shape).
    snipe = sv.attack_ev(damage=90.0, target_hp=320.0, target_prizes=2.0, rider_value=1.4)
    straight = sv.attack_ev(damage=200.0, target_hp=320.0, target_prizes=2.0)
    assert snipe.total > straight.total


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_attack_ev_working_decomposes_the_total_rather_than_narrating_it():
    """Same contract `state_value`'s `working` carries: the breakdown must BE the decomposition."""
    ev = sv.attack_ev(damage=340.0, target_hp=320.0, target_prizes=3.0, rider_value=0.2,
                      economy_value=0.1, next_turn_cost=0.5)
    w = ev.working()
    assert sum(w.values()) - 2 * w["next_turn_cost"] == pytest.approx(ev.total)


# ── the scalar over a real StateModel ─────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-STATEVALUE-0004")
def test_the_working_breakdown_sums_to_the_returned_scalar():
    """The contract `state_value`'s docstring states. Unassertable at T0 because the entry point
    raised by design; now it is the check that the breakdown is the DECOMPOSITION and not a parallel
    narrative about it — a debugging surface that disagreed with the number it explains would send
    wave-3 triage after the wrong term."""
    model = _lucario_board(my_energies=[E_F], bench=[_poke(RIOLU, hp=80, serial=2)])
    working: dict = {}
    total = sv.state_value(model, working=working)
    assert set(working) == set(sv.FAMILIES)
    assert sum(working.values()) == pytest.approx(total)


@pytest.mark.req("REQ-STATEVALUE-0004")
def test_passing_no_working_dict_returns_the_same_number():
    """The out-parameter is a diagnostic, never a mode. A caller on the planner's hot path pays
    nothing for it and must not get a different answer for not asking."""
    model = _lucario_board(my_energies=[E_F])
    assert sv.state_value(model) == pytest.approx(sv.state_value(model, working={}))


@pytest.mark.req("REQ-STATEVALUE-0008")
def test_the_scalar_is_PROVENANCE_AGNOSTIC_over_two_models_of_one_board():
    """Ruled 2026-08-01. Issue #259 §3b's apply-seam has three fates, two of which yield a model —
    MODELLED (closed-form) and ENGINE-RESOLVED (an engine readback for a clause-vocabulary gap) —
    and `state_value` must not be able to tell them apart.

    Asserted as the property that actually matters: two INDEPENDENTLY CONSTRUCTED models of the same
    board content score identically. §3c's completeness audit is what guarantees the two paths
    produce the same content; this is the guard that nothing in the scoring reads identity, object
    ordering or construction history on top of it."""
    def board():
        return _lucario_board(my_energies=[E_F, E_F], bench=[_poke(MUNKIDORI, hp=70, serial=3)],
                              hand=[E_F, RIOLU])
    one, two = board(), board()
    assert one is not two
    w1, w2 = {}, {}
    assert sv.state_value(one, working=w1) == pytest.approx(sv.state_value(two, working=w2))
    assert w1 == pytest.approx(w2)


@pytest.mark.req("REQ-STATEVALUE-0010")
def test_state_value_returns_a_BIT_IDENTICAL_float_on_every_call():
    """Issue #262's fourth amendment, and the only half of old Issue #145's amendment D this track
    owns — *"the actual amendment D rule moved to Issue #263, this track only owns the function's own
    determinism"*.

    The spec's words: *"for a fixed StateModel, `state_value` returns a BIT-IDENTICAL float on every
    call — fixed term-iteration order (never dict/set iteration that could reorder), no clock/random/
    hidden global state read by any term."* Bit-identical, not approximately equal: floating-point
    addition is not associative, so a term order that varied would move the last bits, and a
    selection key built on a value whose last bits wobble is not a fix.

    Asserted on a model that exercises every family — two bodies, a bench, a hand, both sides
    populated — because a term that read a global would most likely be one the empty board skips."""
    model = _lucario_board(my_energies=[E_F], bench=[_poke(RIOLU, hp=80, serial=2)],
                           hand=[MEGA_LUC, E_F])
    values = [sv.state_value(model) for _ in range(32)]
    assert len(set(values)) == 1
    # Bit-identical, asserted through the repr so a difference below `==`'s notice would still show.
    assert len({repr(v) for v in values}) == 1

    # And a FRESHLY built model of the same board agrees bit-for-bit, so the answer is a function of
    # the board rather than of the memo's fill order.
    fresh = _lucario_board(my_energies=[E_F], bench=[_poke(RIOLU, hp=80, serial=2)],
                           hand=[MEGA_LUC, E_F])
    assert repr(sv.state_value(fresh)) == repr(values[0])


@pytest.mark.req("REQ-STATEVALUE-0010")
def test_the_term_iteration_order_is_FIXED_not_a_set_or_a_dict_scan():
    """The mechanism behind the test above, asserted directly rather than inferred from one board.

    `working`'s keys must come out in the registry's declared order every time. A term set assembled
    by iterating a `set` — or by a comprehension over anything unordered — would still produce a
    stable answer inside one interpreter run and could reorder across runs, which is precisely the
    failure a same-process repeat test cannot see."""
    model = _lucario_board(my_energies=[E_F])
    working: dict = {}
    sv.state_value(model, working=working)
    assert list(working) == [f.name for f in sv.REGISTRY]


# ── MID-TURN MONOTONICITY — the class Issue #263's ordering ruling requires ────────────────────────
#
# Every case below perturbs the SAME fixture board by exactly ONE beneficial fact and asserts the
# scalar moves in the obvious direction. They are deliberately cheap and deliberately obvious: the
# failure they catch is not a wrong number, it is a term that implicitly assumed a completed turn and
# therefore prices a half-finished board at zero. That failure is invisible to any test that only
# ever scores end-of-turn boards, and its consequence is a good line pruned before the leaf sees it.


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_an_attach_toward_an_attack_cost_raises_readiness_MID_TURN():
    """The headline case from the ruling, set up as the real transition rather than as two boards:
    BEFORE is the live mid-turn board with the manual attach still available and one {F} down;
    AFTER is that board with the attach SPENT and the second {F} on the body. Mega Brave costs
    ``{F}{F}`` (verified at source), so before the attach the payoff is one Energy away.

    A half-built attacker must score PARTIAL readiness — not zero, which would prune the attach
    before the leaf ever saw it, and not full, which would make the second Energy free."""
    before, after = {}, {}
    sv.state_value(_lucario_board(my_energies=[E_F]), working=before)
    sv.state_value(_lucario_board(my_energies=[E_F, E_F], energy_attached=True), working=after)
    assert after["readiness"] > before["readiness"]
    assert 0.0 < before["readiness"] < after["readiness"], "a half-built attacker scored 0 or full"


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_readiness_survives_the_turns_one_manual_attach_being_spent():
    """The failure mode `_readiness_odds` exists for, asserted directly. `readiness_p` is a
    THIS-TURN probability and fails closed at 0.0, so once the attach is spent every body one Energy
    short of its payoff reads 0 and the whole mid-turn board goes flat — and a flat term prunes
    every subsequent play in the sequence, which is the failure the ordering ruling names.

    The forward clock (`turns_to_afford`, graded by the same `halve` `EvolveBody.p_arrive` uses) is
    what keeps the term alive: one Energy from the payoff still beats a bare body."""
    spent, richer = {}, {}
    sv.state_value(_lucario_board(my_energies=[E_F], energy_attached=True), working=spent)
    sv.state_value(_lucario_board(my_energies=[E_F, E_F], energy_attached=True), working=richer)
    assert spent["readiness"] > 0.0, "the spent attach flattened readiness to zero"
    assert richer["readiness"] > spent["readiness"]


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_a_heal_above_the_incoming_raises_survival():
    """The second case the ruling names, and the family that motivated differencing in the first
    place: a heal has no bespoke equation anywhere in the codebase, so if the survival delta does
    not move, T4's heal family prices at 0 and is never played."""
    hurt, whole = {}, {}
    sv.state_value(_lucario_board(my_hp=60), working=hurt)
    sv.state_value(_lucario_board(my_hp=340), working=whole)
    assert whole["survival"] > hurt["survival"]


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_benching_a_body_raises_development_and_lifts_the_bench_empty_doom():
    """A deploy is priced by two facts at once and both must move: the body itself is development,
    and a Bench that is no longer empty removes the `_predicted_loss` terminal term (ADR-0064,
    `docs/rules.md` §7 case 2). The doomed board is constructed to BE doomed — a 60 HP Active under
    a fully-funded Phantom Dive — so the second half is exercised rather than assumed."""
    alone, benched = {}, {}
    sv.state_value(_lucario_board(my_hp=60), working=alone)
    sv.state_value(_lucario_board(my_hp=60, bench=[_poke(RIOLU, hp=80, serial=2)]), working=benched)
    assert benched["development"] > alone["development"]
    assert benched["survival"] > alone["survival"] + _TERMINAL_JUMP, (
        "the bench-empty doom did not lift when a body arrived to soak the Knock Out")


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_taking_a_prize_moves_the_scalar_by_a_full_prize():
    """The dominance anchor. `prize_race`'s lead leg has unit slope, which is what preserves the
    incumbent leaf's `KO_SCORE * prizes_taken` term across the swap and what makes `ko-score-band`
    hold: no amount of board shape reaches a whole prize."""
    before = sv.state_value(_lucario_board(my_prizes=4))
    after = sv.state_value(_lucario_board(my_prizes=3))
    assert after - before > 1.0                       # the lead, plus proximity sharpening
    assert after - before < 1.0 + sv._PROXIMITY_W


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_holding_a_useful_card_is_worth_something_but_less_than_playing_it_is():
    """The `POC_WORTH_PRIZE_RATE` sanity the whole ADR-0097 argument rests on. Pricing the hand at
    zero makes every free Item strictly worth playing (the defect `_DENIAL_ITEM_COST` patches);
    pricing it too high makes the agent hoard. With no Needs resolution supplied the hand leg is a
    real zero — there are no slots for a card to cover — and that is asserted here rather than left
    to be discovered as a mystery in wave-3 triage."""
    model = _lucario_board(hand=[MEGA_LUC, E_F])
    working: dict = {}
    sv.state_value(model, working=working)
    assert working["hand"] == 0.0, (
        "no Needs resolution was supplied, so there are no slots to cover — a real zero")

    resolved = _lucario_board(hand=[MEGA_LUC, E_F])
    resolved.mine._needs = _resolution_for_one_wincon_slot()
    resolved_working: dict = {}
    sv.state_value(resolved, working=resolved_working)
    assert resolved_working["hand"] > 0.0
    assert resolved_working["hand"] < 1.0, "a hand may never be worth a whole prize"


def _resolution_for_one_wincon_slot():
    """A minimal `needs.Resolution`: one Line slot at the win-condition tier, covered by the held
    Mega Lucario ex. The Pilot's `_resolve_needs` is what builds these in production; this is the
    smallest one that exercises the `hand` family's spine."""
    from common import needs
    return needs.Resolution(
        slots=(needs.Slot("line", 30.0, 99, "wincon"),),
        eligibility=(frozenset({0}), frozenset()),
        resupply=(0.0,),
        hand_ids=(MEGA_LUC, E_F),
        latent_worth=0.0)


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_evolution_topology_credits_a_line_that_can_still_arrive_over_one_that_cannot():
    """`development`'s `line_topology` leg. Riolu evolves to Mega Lucario ex in a SINGLE hop with no
    intermediate Lucario in this set (`docs/rulebook.txt` Appendix 1) — the worked example CLAUDE.md
    uses for verify-don't-recall — so a Riolu on the board owes 270 − 30 damage of forward payoff.

    Burying every Mega Lucario ex in the discard makes that line topologically dead however well
    funded the base is, and the term has to notice: `unseen_counts` is the sound read of "not
    provably gone" the rest of the snapshot already uses."""
    live = _model(_player(active=_poke(RIOLU, hp=80), prize=4), _player(prize=4))
    dead = _model(_player(active=_poke(RIOLU, hp=80), discard=[MEGA_LUC] * 3, prize=4),
                  _player(prize=4))
    live_w, dead_w = {}, {}
    sv.state_value(live, working=live_w)
    sv.state_value(dead, working=dead_w)
    assert live_w["development"] > dead_w["development"]


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_a_reachable_knockout_on_their_active_raises_threat_but_never_by_a_prize():
    """`threat`'s two properties in one case. It must MOVE when their Active becomes reachable —
    otherwise nothing prices pressure — and it must stay inside its cap, because the prize for
    converting the exposure belongs to `attack_ev` at the terminal action and
    `score = state_value(end) + EV(terminal)` would otherwise pay for one Knock Out twice."""
    safe, exposed = {}, {}
    sv.state_value(_lucario_board(my_energies=[E_F, E_F]), working=safe)
    sv.state_value(_lucario_board(my_energies=[E_F, E_F],
                                  their_active=_poke(MUNKIDORI, hp=70, serial=9)), working=exposed)
    assert exposed["threat"] > safe["threat"]
    assert exposed["threat"] <= sv._THREAT_CAP < 1.0


@pytest.mark.req("REQ-STATEVALUE-0009")
@pytest.mark.xfail(strict=True, reason="OPEN DEFECT, diagnosed and parked — see the test body and "
                                       "`threat`'s `blind_to` entry 'SATURATION INTO ONE BIT'")
def test_threat_GRADES_by_what_the_target_yields_instead_of_saturating_into_one_bit():
    """A strict-xfail **TARGET** (the `test_hyperclosure_corpus.py` idiom): a defect stated as the
    assertion that will pass the day it is fixed, so the fix cannot land silently and the defect
    cannot rot into scenery. Green while `threat` is still broken; a red XPASS is the signal to
    delete this mark.

    `threat`'s inputs are `needs.opponent_target_value`, which at the fail-closed
    ``survival_shift=0`` this module passes returns the target's PRIZE value essentially unscaled —
    1, 2 or 3 (`docs/rules.md` §6, verified at source: regular / ex / Mega ex). Against a 0.1-prize
    cap with no weight in front of it, `min(cap, sum)` binds on **every** non-empty input, so the
    family answers one bit — *is their Active reachable at all* — and a 1-prize Basic prices the
    same as a 3-prize Mega ex. Measured on Issue #262's 22 gating Discrimination-Gate frames:
    `threat` read 0.0 on 20 and exactly the cap on 2, never a value between.

    **Why the fix is not applied**, since it is derived rather than authored
    (`_THREAT_CAP / _MAX_PRIZE_VALUE`) and leaves the positional band untouched: measured on the
    corpus, its only effect is negative — the Discrimination Gate goes 65 -> 68 unruled and loses
    two `MISS -> OK` improvements. Five frames were winning by a margin smaller than the 0.067
    prizes of threat advantage the saturation handed them. Removing a windfall is correct AND costs
    rulings, and this module does not get to write them; the fix is parked with the other
    calibration findings for the post-POC fit (Issues #146-#148).

    The assertion is STRICT monotonicity, which is exactly what the saturated form cannot satisfy,
    plus the two band properties any fix must preserve."""
    assert sv.threat([1.0]) < sv.threat([2.0]) < sv.threat([3.0])
    assert sv.threat([sv._MAX_PRIZE_VALUE]) == pytest.approx(sv._THREAT_CAP)
    assert sv.threat([3.0, 3.0]) == pytest.approx(sv._THREAT_CAP)
    assert sv.threat(()) == 0.0


# ── inertness is over; the seam is not ────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-STATEVALUE-0003")
def test_the_per_body_inputs_are_NAMED_so_a_frozen_contract_cannot_be_transposed():
    """`survival` and `readiness` take three-and-two-field records, not anonymous tuples. This is a
    contract T3 implemented against months after T0 wrote it: a transposed `(payoff, odds,
    relevance)` would still type-check, still run, and price the board wrong in a direction nobody
    would look."""
    body = sv.ExposedBody(prize_at_risk=2.0, turns_to_ko_me=1)
    assert (body.prize_at_risk, body.turns_to_ko_me) == (2.0, 1)

    ready = sv.ReadyBody(payoff=3.0, readiness_odds=0.25, role_relevance=1.0)
    assert (ready.payoff, ready.readiness_odds, ready.role_relevance) == (3.0, 0.25, 1.0)

    # Still tuples, so an implementation may unpack positionally without ceremony.
    assert tuple(ready) == (3.0, 0.25, 1.0)


@pytest.mark.req("REQ-STATEVALUE-0003")
def test_the_module_reaches_for_no_engine_no_obs_and_no_pilot():
    """The seam, asserted at import: `state_value` takes a StateModel and the families take plain
    numbers, so nothing here may pull in the Pilot, the native engine or cgpy. A value equation that
    can reach for the board it was handed facts about stops being testable with numbers."""
    import inspect
    src = inspect.getsource(sv)
    for forbidden in ("from cg import", "import cgpy", "from common.pilot", "import pilot"):
        assert forbidden not in src, forbidden


# ── the SAME monotonicity, on REAL corpus frames ──────────────────────────────────────────────────
#
# Issue #262's ordering-ruling amendment asks for this class "on a handful of CORPUS frames", and the
# synthetic cases above are not a substitute: a fixture board is one I chose, and the failure mode
# being guarded — a term that quietly assumes a completed turn — is likeliest on the boards nobody
# designed. These perturb a real frame by exactly one beneficial fact and assert the direction.
#
# Asserted as `>=` per frame with at least one STRICT move required across the corpus. A real board
# can be genuinely indifferent to one more Energy (the attacker is already maxed) or to a heal (the
# clock does not move a whole turn), and demanding `>` everywhere would fail on correct behaviour.
# The "at least one strict" floor is what stops the whole class from passing vacuously.

def _corpus_models():
    """`(key, pilot, obs)` for a sample of replayable corpus frames, through THE Corpus Reader."""
    from corpus_helpers import corpus_index
    from train.tune import _build_pilot
    out, built = [], {}
    for (episode, frame), rec in sorted(corpus_index().items())[:40]:
        if rec.agent not in built:
            try:
                built[rec.agent] = _build_pilot(rec.agent)[0]
            except Exception:                       # an unbuildable agent is skipped, never fatal
                built[rec.agent] = None
        if built[rec.agent] is not None:
            out.append((f"{episode}|{frame}", built[rec.agent], rec.obs))
    return out


@pytest.fixture(scope="module")
def corpus_models():
    models = _corpus_models()
    if not models:
        pytest.skip("no replayable corrections corpus in this checkout")
    return models


def _my_active(obs):
    cur = (obs or {}).get("current") or {}
    players = cur.get("players") or []
    me = players[cur.get("yourIndex", 0)] if players else {}
    return next((b for b in (me.get("active") or []) if b), None)


def _perturbed(obs, mutate):
    """A deep-enough copy of ``obs`` with ``mutate`` applied to MY Active. The original is shared
    across the whole test session (`corpus_index` caches it), so mutating in place would corrupt
    every later test — the helper's own docstring says so."""
    import copy
    fresh = copy.deepcopy(obs)
    active = _my_active(fresh)
    if active is not None:
        mutate(active)
    return fresh


def _score(pilot, obs, term):
    my_index = ((obs.get("current") or {}).get("yourIndex")) or 0
    working: dict = {}
    sv.state_value(pilot._leaf_state_model(obs, my_index), working=working)
    return working[term]


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_on_real_frames_one_more_energy_never_lowers_readiness(corpus_models):
    """An attach toward an attack cost raises readiness — the ruling's first named case, on boards
    nobody designed for it."""
    strict = 0
    for key, pilot, obs in corpus_models:
        active = _my_active(obs)
        if not active or not (active.get("energies") or []):
            continue                                # nothing to duplicate; the attach is unmodelled
        extra = (active.get("energies") or [])[0]
        before = _score(pilot, obs, "readiness")
        after = _score(pilot, _perturbed(obs, lambda b: b["energies"].append(extra)), "readiness")
        assert after >= before - 1e-9, f"{key}: an extra Energy LOWERED readiness"
        strict += after > before + 1e-9
    assert strict, "no corpus frame moved at all — the class would pass on a constant term"


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_on_real_frames_healing_my_active_never_lowers_survival(corpus_models):
    """A heal above the incoming raises survival — the ruling's second named case, and the family
    that motivated differencing: a heal has no bespoke equation anywhere, so if this term does not
    move, T4's heal family prices at 0 and is never played."""
    strict = 0
    for key, pilot, obs in corpus_models:
        active = _my_active(obs)
        if not active or not active.get("maxHp") or active.get("hp") is None:
            continue
        if active["hp"] >= active["maxHp"]:
            continue                                # already whole; nothing to heal
        before = _score(pilot, obs, "survival")
        after = _score(pilot, _perturbed(obs, lambda b: b.__setitem__("hp", b["maxHp"])), "survival")
        assert after >= before - 1e-9, f"{key}: a full heal LOWERED survival"
        strict += after > before + 1e-9
    assert strict, "no corpus frame moved at all — the class would pass on a constant term"


# ── a companion-GATED payoff (Issue #287) ─────────────────────────────────────────────────────────
#
# `readiness` prices *what this body achieves once it is online*. Read off `CardStat.maxDamage` that
# number is PRINTED, and a printed number cannot carry a board condition — so a Solrock with no
# Lunatone benched scored exactly the Solrock that had one, and losing the Lunatone moved nothing.
#
# The repair is composition, not vocabulary: `AttackStat.requiresBench` already parses Cosmic Beam's
# own sentence and `strategy/damage.py` already zeroes the attack when the partner is absent, so the
# term asks the damage oracle (through `StateModel.payoff`) instead of forming a second opinion.


def _lunar_board(*, bench=(), solrock_energies=(E_F,), energy_attached=False):
    """MY Solrock Active against THEIR Dragapult ex, with a caller-chosen Bench — the one fact the
    gated payoff turns on. One {F} is already down, so Cosmic Beam's ``{F}`` cost is PAID and the
    only thing standing between this body and its 70 is the Bench."""
    return _model(
        _player(active=_poke(SOLROCK, hp=110, energies=solrock_energies),
                bench=list(bench), prize=4),
        _player(active=_poke(DRAGAPULT, hp=320, energies=[E_R, E_P], serial=9), prize=4),
        energy_attached=energy_attached, deck=LUNAR_DECK)


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_a_companion_gated_attacker_is_not_ready_without_its_companion():
    """The symptom, asserted at the term. Cosmic Beam is Solrock's ONLY attack, so with no Lunatone
    on the Bench this body achieves nothing — and `readiness` must say so rather than price the
    printed 70 it will never deal."""
    bare, paired = {}, {}
    sv.state_value(_lunar_board(bench=[_poke(RIOLU, hp=80, serial=2)]), working=bare)
    sv.state_value(_lunar_board(bench=[_poke(LUNATONE, hp=110, serial=2)]), working=paired)
    assert paired["readiness"] > bare["readiness"], "the gate never fired: printed damage priced"


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_benching_the_companion_is_what_raises_readiness():
    """The play the old reading could not see. Dropping Lunatone onto an EMPTY Bench is exactly the
    develop that arms the attacker, and under 1-ply differencing a play no term reads prices at 0
    delta — which at ordering time means never explored, not merely undervalued."""
    empty, benched = {}, {}
    sv.state_value(_lunar_board(bench=[]), working=empty)
    sv.state_value(_lunar_board(bench=[_poke(LUNATONE, hp=110, serial=2)]), working=benched)
    assert benched["readiness"] > empty["readiness"]


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_losing_the_companion_lowers_readiness():
    """The mirror, and the half that makes the term a defence: their Boss's Orders on my Lunatone —
    or a Knock Out that removes it — has to cost me something, or the agent will trade the enabler
    away for free."""
    with_luna, without = {}, {}
    sv.state_value(_lunar_board(bench=[_poke(LUNATONE, hp=110, serial=2)]), working=with_luna)
    sv.state_value(_lunar_board(bench=[]), working=without)
    assert without["readiness"] < with_luna["readiness"]


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_an_UNGATED_body_reads_exactly_its_printed_roll_up():
    """The regression half. The gate is a new REASON to price 0, never a new number on a card that
    carries no condition — so on every body of a board holding no conditional attack the new read
    must return `CardStat.maxDamage` exactly, which is the value the retired printed path produced.

    Asserted against `maxDamage` rather than against `state_value` called twice: comparing the
    scalar to itself would pass on any implementation whatsoever (it is a determinism check, and
    `test_state_value_is_BIT_IDENTICAL...` already owns that question). `maxDamage` is the number
    this change replaced, so it is the only honest witness to "nothing moved"."""
    model = _lucario_board(my_energies=[E_F, E_F],
                           bench=[_poke(RIOLU, hp=80, energies=[E_F], serial=2),
                                  _poke(MUNKIDORI, hp=70, serial=3)])
    priced = 0
    for body in model.mine.bodies:
        assert model.mine.attack_payoff(body).damage == float(body.stat.maxDamage), body.stat.name
        priced += 1
    assert priced == 3, "the fixture stopped exercising every area"
    working = {}
    sv.state_value(model, working=working)
    assert working["readiness"] > 0.0


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_a_conditional_BONUS_is_not_credited_by_the_payoff_read():
    """The bound this read takes, pinned — and the other half of Issue #287's refutation.

    Metagross's Conjoined Beams is *"130 … If Beldum and Metang are on your Bench, this attack does
    150 more damage"* (verified at source, id 276), which the provider carries as ``damage=130`` with
    ``damageMax=280``. `slowking` runs the card and neither partner, so the +150 can never be paid —
    and it never was, because `CardStat.maxDamage` is the printed number. That is why the issue's
    Metagross scope item was retired as already-true.

    Retired is not the same as safe. The bonus IS reachable through this read, on one character: at
    ``bound="max"`` the oracle returns ``damageMax`` and readiness would price 280 for a body that
    can land 130. So the exact bound gets a test rather than a comment."""
    model = _model(_player(active=_poke(METAGROSS, hp=170, energies=[E_P, E_P]), prize=4),
                   _player(active=_poke(DRAGAPULT, hp=320, serial=9), prize=4),
                   deck=[METAGROSS, E_P, E_P])
    paying = model.mine.attack_payoff(model.mine.active)
    assert paying == (CONJOINED_BEAMS, 130.0), "the conditional +150 leaked into the payoff"
    assert model.mine.active.stat.maxDamage == 130     # it was never in the roll-up either


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_the_gated_bodys_odds_are_asked_about_the_attack_that_actually_pays():
    """Payoff and odds must name the SAME attack. Pairing one attack's damage with another's
    probability is the saturation defect the payoff read was split out to avoid, and the gate makes
    it reachable for the first time: a body whose max-damage attack is dead still has the lesser
    one, and its cost is what the odds leg owes an answer about."""
    model = _lunar_board(bench=[_poke(LUNATONE, hp=110, serial=2)])
    assert model.mine.attack_payoff(model.mine.active).attack_id == COSMIC_BEAM
