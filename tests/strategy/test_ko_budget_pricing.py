"""The KO oracle prices attachments as a TYPED Attach Budget (ADR-0075, #177).

Replaces `test_play_accel_lethal.py`, whose subject — `_play_accel_extra`'s flat wild `+1` and its
manual(1) + accel(1) = 2 ceiling — is deleted. What ships instead is
`best_affordable_ko_value(budget=...)`: affordability becomes `_can_pay` per SLOT over each Budget
option, the same predicate `reachable_attach` already asks, so a planned attach pays a
specific-type slot only when the cards really produce that colour.

These tests pin the three properties the swap turns on, at the oracle seam (a Budget object plus a
stat provider — no StateModel, no engine):

  * REFUSAL IS TYPED. Three wild units used to pay any `{P}{P}{P}`; a Budget of three {R} units
    does not. This is the phantom KO the fold exists to remove, and the reason the `+1` ceiling
    could not simply be raised (ADR-0075 context).
  * THE COUNT IS SUBSUMED. `_can_pay` refuses when there are fewer units than slots, so the
    retired `cost > energy` gate buys nothing on this leg.
  * IT FAILS CLOSED. An attack whose slots do not resolve is SKIPPED and makes no claim, opposite
    to `attack_type_payable`'s documented fail-open — the under-fire direction ADR-0030's eager
    solver requires (ADR-0075 decision 2).

Refusal and ranking stay separate parameters: `budget=` decides WHETHER the KO is real, `attack_p=`
(ADR-0074, #175) what it is worth, and the order is refuse-then-weight (ADR-0075 decision 7).
"""
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy.combat import AttachUnit, Budget, CombatMath

FIRE, PSYCHIC = 1, 7          # EnergyType codes (src/cg/api.py)

ATTACKER = 900
OPP = 901
PSY3 = 40                     # {P}{P}{P}, 200 dmg — three SPECIFIC-type slots
COLORLESS3 = 41               # ●●●, 200 dmg — three colourless slots
NO_RECORD = 42                # an attack id with no AttackStat — slots do not resolve


def _combat(*attacks) -> CombatMath:
    """A CombatMath whose attacker knows exactly ``attacks`` — the set matters, because a KO only
    needs ONE payable attack, so leaving a colourless attack in scope would mask a typed refusal."""
    attacks = attacks or (PSY3,)
    records = {PSY3: AttackStat(attackId=PSY3, damage=200, cost=3, damageMax=200,
                                energyTypes=(PSYCHIC, PSYCHIC, PSYCHIC)),
               COLORLESS3: AttackStat(attackId=COLORLESS3, damage=200, cost=3, damageMax=200)}
    stats = DictCardStatProvider({
        ATTACKER: CardStat(cardId=ATTACKER, name="attacker", hp=200, attacks=attacks),
        OPP: CardStat(cardId=OPP, name="opp", hp=190),
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
    """Three {R} units cannot pay {P}{P}{P}. Under the retired flat `+1` these arrived as WILD —
    `attack_type_payable`'s "each able to cover any one specific slot (fail-open)" — so raising the
    ceiling without typing them would have MANUFACTURED the phantom KO the fold removes."""
    combat = _combat()
    budget = _budget({FIRE}, {FIRE}, {FIRE})
    assert _ko(combat, budget) == 0.0


def test_three_right_coloured_units_do_pay_it():
    combat = _combat()
    budget = _budget({PSYCHIC}, {PSYCHIC}, {PSYCHIC})
    assert _ko(combat, budget) > 0.0


def test_wild_units_still_pay_a_typed_cost():
    """An empty type pool is ANY type (an unresolvable Energy card) — fail-OPEN is preserved for a
    genuinely unknown unit, matching `AttachUnit.types`' documented contract. The fold narrows what
    is CLAIMED to be typed, it does not make unknown Energy unusable."""
    combat = _combat()
    assert _ko(combat, _budget(set(), set(), set())) > 0.0


def test_colourless_slots_are_paid_by_any_colour():
    """The mirror of the refusal test: ●●● has no specific-type slot, so three {R} units pay it.
    Guards against over-narrowing — a typed refusal must not leak into colourless costs."""
    assert _combat(COLORLESS3).best_affordable_ko_value(
        {"id": OPP, "hp": 190}, ATTACKER, 0, body=_body(),
        budget=_budget({FIRE}, {FIRE}, {FIRE})) > 0.0


# ── the count gate is subsumed by _can_pay ───────────────────────────────────────────────────

def test_too_few_units_refuse_even_when_correctly_coloured():
    """`_can_pay` returns False when there are fewer units than slots, so the retired
    `cost > energy` check adds nothing on this leg (ADR-0075 decision 2)."""
    combat = _combat()
    assert _ko(combat, _budget({PSYCHIC}, {PSYCHIC})) == 0.0


def test_the_energy_argument_is_ignored_when_a_budget_is_supplied():
    """`energy` is not consulted on the Budget leg — the Budget is the whole affordability truth.
    A generous count cannot rescue a Budget that does not pay."""
    combat = _combat()
    assert combat.best_affordable_ko_value(
        {"id": OPP, "hp": 190}, ATTACKER, 99, body=_body(),
        budget=_budget({FIRE}, {FIRE}, {FIRE})) == 0.0


# ── fail-CLOSED on an unresolvable cost ──────────────────────────────────────────────────────

def test_an_attack_with_no_resolvable_slots_makes_no_claim():
    """`_attack_slots` returns () for an unresolvable record; the Budget leg SKIPS it rather than
    counting it, matching `reachable_attach` and opposite to `attack_type_payable`'s fail-open.
    Verified inert on real data — no card in EN_Card_Data.csv prints a blank/zero Cost — so this
    pins the DIRECTION, not a live behaviour change."""
    assert _combat(NO_RECORD).best_affordable_ko_value(
        {"id": OPP, "hp": 190}, ATTACKER, 0, body=_body(),
        budget=_budget(set(), set(), set())) == 0.0


def test_an_empty_budget_refuses_everything():
    combat = _combat()
    assert _ko(combat, Budget(options=((),), caps={})) == 0.0


# ── refuse-then-weight: the two mechanisms stay independent ──────────────────────────────────

def test_a_refused_attack_is_never_reached_by_the_probability_weight():
    """ADR-0075 decision 7: refusal is unconditional and happens FIRST, so an unpayable attack is
    skipped rather than multiplied to zero. A weight of 1.0 cannot resurrect it."""
    combat = _combat()
    assert combat.best_affordable_ko_value(
        {"id": OPP, "hp": 190}, ATTACKER, 0, body=_body(),
        budget=_budget({FIRE}, {FIRE}, {FIRE}), attack_p=lambda _aid: 1.0) == 0.0


def test_the_weight_scales_a_payable_ko_without_refusing_it():
    """The other half of the separation: a real KO stays real and is priced DOWN by the weight."""
    combat = _combat()
    budget = _budget({PSYCHIC}, {PSYCHIC}, {PSYCHIC})
    full = _ko(combat, budget)
    weighted = combat.best_affordable_ko_value(
        {"id": OPP, "hp": 190}, ATTACKER, 0, body=_body(),
        budget=budget, attack_p=lambda _aid: 0.5)
    assert 0.0 < weighted < full


# ── the no-Budget leg is untouched ───────────────────────────────────────────────────────────

def test_omitting_the_budget_keeps_the_count_leg_intact():
    """Callers with no Budget (the tactical retreat/gust lookaheads) still price by the count, so
    the typed leg is an ADDED path rather than a replacement."""
    combat = _combat()
    assert combat.best_affordable_ko_value({"id": OPP, "hp": 190}, ATTACKER, 3,
                                           body=_body()) > 0.0
    assert combat.best_affordable_ko_value({"id": OPP, "hp": 190}, ATTACKER, 2,
                                           body=_body()) == 0.0
