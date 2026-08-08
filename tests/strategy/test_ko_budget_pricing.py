"""The KO oracle prices attachments as a TYPED Attach Budget — ADR-0075, Issue #177.

Refusal and ranking stay separate parameters: `budget=` decides WHETHER the KO is real, `attack_p=`
(ADR-0074, Issue #175) what it is worth, and the order is refuse-then-weight (ADR-0075 decision 7).
"""
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy.combat import AttachUnit, Budget, CombatMath

FIRE, PSYCHIC = 1, 7          # EnergyType codes (src/cg/api.py)

ATTACKER = 900
OPP = 901
PSY3 = 40                     # {P}{P}{P}, 200 dmg
COLORLESS3 = 41               # ●●●, 200 dmg
NO_RECORD = 42                # no AttackStat — slots do not resolve


def _combat(*attacks) -> CombatMath:
    """A KO needs only ONE payable attack, so leaving a colourless attack in scope would mask a
    typed refusal."""
    attacks = attacks or (PSY3,)
    records = {PSY3: AttackStat(attackId=PSY3, damage=200, cost=3, damageMax=200,
                                energyTypes=(PSYCHIC, PSYCHIC, PSYCHIC)),
               COLORLESS3: AttackStat(attackId=COLORLESS3, damage=200, cost=3, damageMax=200)}
    stats = DictCardStatProvider({
        ATTACKER: CardStat(synthetic=True, cardId=ATTACKER, name="attacker", hp=200, attacks=attacks),
        OPP: CardStat(synthetic=True, cardId=OPP, name="opp", hp=190),
    }, {aid: rec for aid, rec in records.items() if aid in attacks})
    return CombatMath(stats=stats, functions=None)


def _budget(*unit_types) -> Budget:
    """One play-set of units, each unit carrying the given type pool ({} = wild/any)."""
    return Budget(options=(tuple(AttachUnit(frozenset(t)) for t in unit_types),), caps={})


def _body():
    return {"id": ATTACKER, "energies": [], "energyCards": []}


def _ko(combat, budget, *, attacker_attacks=None) -> float:
    return combat.best_affordable_ko_value(
        {"id": OPP, "hp": 190}, ATTACKER, 0, body=_body(), budget=budget)


# ── refusal is TYPED: the whole point of the fold ────────────────────────────────────────────

def test_three_wrong_coloured_units_do_not_pay_a_typed_cost():
    combat = _combat()
    budget = _budget({FIRE}, {FIRE}, {FIRE})
    assert _ko(combat, budget) == 0.0


def test_three_right_coloured_units_do_pay_it():
    combat = _combat()
    budget = _budget({PSYCHIC}, {PSYCHIC}, {PSYCHIC})
    assert _ko(combat, budget) > 0.0


def test_wild_units_still_pay_a_typed_cost():
    """An empty type pool is ANY type (an unresolvable Energy card): `AttachUnit.types` stays
    fail-OPEN for a genuinely unknown unit."""
    combat = _combat()
    assert _ko(combat, _budget(set(), set(), set())) > 0.0


def test_colourless_slots_are_paid_by_any_colour():
    assert _combat(COLORLESS3).best_affordable_ko_value(
        {"id": OPP, "hp": 190}, ATTACKER, 0, body=_body(),
        budget=_budget({FIRE}, {FIRE}, {FIRE})) > 0.0


# ── the count gate is subsumed by _can_pay ───────────────────────────────────────────────────

def test_too_few_units_refuse_even_when_correctly_coloured():
    combat = _combat()
    assert _ko(combat, _budget({PSYCHIC}, {PSYCHIC})) == 0.0


def test_the_energy_argument_is_ignored_when_a_budget_is_supplied():
    combat = _combat()
    assert combat.best_affordable_ko_value(
        {"id": OPP, "hp": 190}, ATTACKER, 99, body=_body(),
        budget=_budget({FIRE}, {FIRE}, {FIRE})) == 0.0


# ── fail-CLOSED on an unresolvable cost ──────────────────────────────────────────────────────

def test_an_attack_with_no_resolvable_slots_makes_no_claim():
    """No card in EN_Card_Data.csv prints a blank/zero Cost, so this pins the DIRECTION — fail-CLOSED,
    opposite `attack_type_payable` — rather than a live behaviour change."""
    assert _combat(NO_RECORD).best_affordable_ko_value(
        {"id": OPP, "hp": 190}, ATTACKER, 0, body=_body(),
        budget=_budget(set(), set(), set())) == 0.0


def test_an_empty_budget_refuses_everything():
    combat = _combat()
    assert _ko(combat, Budget(options=((),), caps={})) == 0.0


# ── refuse-then-weight: the two mechanisms stay independent ──────────────────────────────────

def test_a_refused_attack_is_never_reached_by_the_probability_weight():
    combat = _combat()
    assert combat.best_affordable_ko_value(
        {"id": OPP, "hp": 190}, ATTACKER, 0, body=_body(),
        budget=_budget({FIRE}, {FIRE}, {FIRE}), attack_p=lambda _aid: 1.0) == 0.0


def test_the_weight_scales_a_payable_ko_without_refusing_it():
    combat = _combat()
    budget = _budget({PSYCHIC}, {PSYCHIC}, {PSYCHIC})
    full = _ko(combat, budget)
    weighted = combat.best_affordable_ko_value(
        {"id": OPP, "hp": 190}, ATTACKER, 0, body=_body(),
        budget=budget, attack_p=lambda _aid: 0.5)
    assert 0.0 < weighted < full


# ── the no-Budget leg is untouched ───────────────────────────────────────────────────────────

def test_omitting_the_budget_keeps_the_count_leg_intact():
    """No-Budget callers (the tactical retreat/gust lookaheads) still price by the count: the typed
    leg is ADDED, not a replacement."""
    combat = _combat()
    assert combat.best_affordable_ko_value({"id": OPP, "hp": 190}, ATTACKER, 3,
                                           body=_body()) > 0.0
    assert combat.best_affordable_ko_value({"id": OPP, "hp": 190}, ATTACKER, 2,
                                           body=_body()) == 0.0
