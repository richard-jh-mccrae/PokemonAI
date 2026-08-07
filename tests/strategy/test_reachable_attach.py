"""Issue #137 Phase 0a — the self-side attach-affordability oracle (ADR-0067).

``CombatMath.attach_budget`` / ``reachable_attach`` / ``readiness_p``: the mirror of ADR-0064's
``reachable_incoming``, on a lib-free provider (the `test_reachable_incoming.py` seam).

Card facts VERIFIED at source (`data/EN_Card_Data.csv`, `src/common/card_functions.json`,
`tools/meta_tracker/effect_overrides.json`) — never recalled. Basic Energy card ids: 2 {R}, 5 {P},
7 {D}.
"""
from card_facts import ignition_tags                    # the committed Ignition Energy tags, ONE copy
from common.cards import CardFunctions
from common.effects import CardEffects
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy.combat import (DISCARD_SUPPLY, AttachUnit, Budget, CombatMath,
                                    _can_pay)

# EnergyType codes (cg.api.EnergyType)
COLORLESS, FIRE, PSYCHIC, FIGHTING, DARKNESS, DRAGON = 0, 2, 5, 6, 7, 9

DRAGAPULT = 121
JET_HEADBUTT, PHANTOM_DIVE = 9121, 9122          # attack ids for the two verified attacks
CRISPIN, GONG, HILDA, PATCH, ROSA = 1198, 1142, 1225, 1146, 1240
CINDERACE = 666
E_R, E_P, E_D = 2, 5, 7                          # Basic {R} / {P} / {D} Energy card ids

_STATS = {
    DRAGAPULT: CardStat(DRAGAPULT, synthetic=True, name='Dragapult ex', hp=320, ex=True, stage2=True,
                        evolvesFrom="Drakloak", energyType=DRAGON, maxDamage=200, maxDamageCost=2,
                        minAttackCost=1, minCostDamage=70,
                        attacks=(JET_HEADBUTT, PHANTOM_DIVE), cardType=0),
    CRISPIN: CardStat(CRISPIN, name="Crispin", cardType=3),          # Supporter
    GONG: CardStat(GONG, name="Fighting Gong", cardType=1),          # Item
    HILDA: CardStat(HILDA, name="Hilda", cardType=3),                # Supporter
    PATCH: CardStat(PATCH, name="Wondrous Patch", cardType=1),       # Item
    ROSA: CardStat(ROSA, name="Rosa's Encouragement", cardType=3),   # Supporter
    E_R: CardStat(E_R, name="Basic {R} Energy", cardType=5, energyType=FIRE),
    E_P: CardStat(E_P, name="Basic {P} Energy", cardType=5, energyType=PSYCHIC),
    E_D: CardStat(E_D, name="Basic {D} Energy", cardType=5, energyType=DARKNESS),
}
_ATTACKS = {
    JET_HEADBUTT: AttackStat(JET_HEADBUTT, damage=70, cost=1, energyTypes=(COLORLESS,)),
    PHANTOM_DIVE: AttackStat(PHANTOM_DIVE, damage=200, cost=2, energyTypes=(FIRE, PSYCHIC)),
}
_TAGS = {
    CRISPIN: ["energy_accel", "search", "tutor_energy"],
    GONG: ["search", "tutor_energy", "tutor_pokemon"],
    HILDA: ["search", "tutor_energy", "tutor_pokemon"],
    PATCH: ["energy_accel"],
    ROSA: ["energy_accel"],
}
_CLAUSES = {
    CRISPIN: [{"kind": "accel", "amount": 1, "source": "deck", "target": "any_pokemon",
               "energy": "basic", "to_hand": 1, "distinct_types": True}],
    GONG: [{"kind": "fetch", "target": "basic_energy", "zone": "deck", "energy_type": FIGHTING},
           {"kind": "fetch", "target": "basic_pokemon", "zone": "deck", "energy_type": FIGHTING}],
    HILDA: [{"kind": "fetch", "target": "evolution", "zone": "deck"},
            {"kind": "fetch", "target": "energy", "zone": "deck"}],
    PATCH: [{"kind": "accel", "amount": 1, "source": "discard", "target": "benched",
             "target_type": PSYCHIC, "energy": "basic", "energy_type": PSYCHIC}],
    ROSA: [{"kind": "accel", "amount": 2, "source": "discard", "target": "stage2",
            "energy": "basic", "condition": "more_prizes_remaining_than_opp"}],
}

DRAGAPULT_DECK_TYPES = frozenset({FIRE, PSYCHIC, DARKNESS})   # the shipped 3×{R}/3×{P}/2×{D} suite


def _combat(*, clauses=None, transients=None):
    return CombatMath(DictCardStatProvider(_STATS, attacks=_ATTACKS),
                      functions=CardFunctions(_TAGS),
                      transients=transients,
                      effects=CardEffects(_CLAUSES if clauses is None else clauses))


def _pult(*energies):
    """My Active Dragapult ex carrying ``energies`` (Basic Energy CARD ids)."""
    return {"id": DRAGAPULT, "hp": 320, "energies": list(energies), "serial": 1}


# ---- the f70 fixture: the primitive's reason to exist -----------------------------------------

def test_f70_crispin_reaches_the_two_cost_typed_attack_this_turn():
    """Crispin attaches one Basic by its effect AND hands a SECOND of a different type the manual
    attach plays → {R}{P} = Phantom Dive THIS turn. The famine read said 'can't attack'; FALSE."""
    c = _combat()
    budget = c.attach_budget(_pult(), [CRISPIN], deck_energy_types=DRAGAPULT_DECK_TYPES)
    assert c.reachable_attach(_pult(), PHANTOM_DIVE, budget=budget) is True
    assert c.reachable_attach(_pult(), JET_HEADBUTT, budget=budget) is True
    assert c.reachable_attach(_pult(), None, budget=budget) is True          # not a famine


def test_f70_is_a_famine_under_the_retired_plus_one_read():
    """The bug's shape: ONE attach (`_active_attack_payable_via_accel`'s `len(energies)+1`) reaches
    the cheapest {C} attack but never the 2-cost {R}{P} — the full budget is the whole point."""
    c = _combat()
    one_attach = c.attach_budget(_pult(), [], hand_energy_types=(FIRE,),
                                 deck_energy_types=DRAGAPULT_DECK_TYPES)
    assert c.reachable_attach(_pult(), JET_HEADBUTT, budget=one_attach) is True
    assert c.reachable_attach(_pult(), PHANTOM_DIVE, budget=one_attach) is False


def test_famine_is_provable_with_an_empty_hand_and_no_attach():
    c = _combat()
    spent = c.attach_budget(_pult(), [], energy_attached=True,
                            deck_energy_types=DRAGAPULT_DECK_TYPES)
    assert c.reachable_attach(_pult(), None, budget=spent) is False          # a PROVABLE famine


def test_attached_energy_alone_pays_without_any_budget():
    c = _combat()
    empty = c.attach_budget(_pult(E_R, E_P), [], energy_attached=True, deck_energy_types=())
    assert c.reachable_attach(_pult(E_R, E_P), PHANTOM_DIVE, budget=empty) is True


# ---- typed, per-slot affordability -------------------------------------------------------------

def test_typed_slots_are_not_paid_by_the_wrong_colour():
    """One {D} in hand + the manual attach reaches 1 unit — but {R}{P} needs those exact colours."""
    c = _combat()
    b = c.attach_budget(_pult(E_D), [], hand_energy_types=(DARKNESS,), deck_energy_types=())
    assert c.reachable_attach(_pult(E_D), PHANTOM_DIVE, budget=b) is False
    assert c.reachable_attach(_pult(E_D), JET_HEADBUTT, budget=b) is True    # {D} pays a COLOURLESS slot


def test_crispin_units_must_take_distinct_types():
    """Crispin's two Basic Energy are 'of different types' — so it can never pay a same-colour
    2-slot cost from scratch, even though it yields two units."""
    c = _combat()
    b = c.attach_budget(_pult(), [CRISPIN], deck_energy_types=DRAGAPULT_DECK_TYPES)
    same_colour = AttackStat(9999, damage=10, cost=2, energyTypes=(FIRE, FIRE))
    stats = DictCardStatProvider(
        {**_STATS, DRAGAPULT: CardStat(DRAGAPULT, synthetic=True, name='Dragapult ex', hp=320, minAttackCost=2,
                                       attacks=(9999,), cardType=0)},
        attacks={**_ATTACKS, 9999: same_colour})
    c2 = CombatMath(stats, functions=CardFunctions(_TAGS), effects=CardEffects(_CLAUSES))
    assert c2.reachable_attach(_pult(), 9999, budget=b) is False


def test_a_typed_fetch_needs_that_type_still_in_the_deck():
    """ADR-0067: deck presence fails OPEN (not-provably-empty) but a type the deck is PROVABLY
    empty of yields nothing — Crispin off a {D}-only deck can never reach {R}{P}."""
    c = _combat()
    b = c.attach_budget(_pult(), [CRISPIN], deck_energy_types=frozenset({DARKNESS}))
    assert c.reachable_attach(_pult(), PHANTOM_DIVE, budget=b) is False
    assert c.reachable_attach(_pult(), JET_HEADBUTT, budget=b) is True


def test_crispin_over_a_one_colour_deck_takes_the_fail_closed_reading():
    """No source settles whether Crispin's lone find is the put-in-hand half or the attach half.
    Ruled fail-closed (ADR-0067): the HAND half, so it needs the turn's manual attach."""
    c = _combat()
    one_colour = frozenset({DARKNESS})
    with_attach = c.attach_budget(_pult(), [CRISPIN], deck_energy_types=one_colour)
    assert with_attach.size == 1                     # one card, played by the manual attach
    assert c.reachable_attach(_pult(), JET_HEADBUTT, budget=with_attach) is True
    spent = c.attach_budget(_pult(), [CRISPIN], energy_attached=True, deck_energy_types=one_colour)
    assert spent.size == 0                           # the hand half has nothing to play it
    assert c.reachable_attach(_pult(), None, budget=spent) is False
    # Two colours left: the attach half is real again and survives a spent manual attach.
    two = c.attach_budget(_pult(), [CRISPIN], energy_attached=True,
                          deck_energy_types=frozenset({FIRE, PSYCHIC}))
    assert two.size == 1
    assert c.reachable_attach(_pult(), JET_HEADBUTT, budget=two) is True


def test_a_deck_with_no_basic_energy_yields_no_deck_fetch_budget():
    c = _combat()
    b = c.attach_budget(_pult(), [CRISPIN], deck_energy_types=frozenset())
    assert c.reachable_attach(_pult(), None, budget=b) is False


# ---- quotas ------------------------------------------------------------------------------------

def test_a_supporter_tutor_and_the_manual_attach_co_occur():
    """The f70 legality: Crispin (Supporter) PLUS the unspent manual attach is ONE Supporter and
    ONE attach — legal. That co-occurrence is exactly what the retired read missed."""
    c = _combat()
    b = c.attach_budget(_pult(), [CRISPIN], deck_energy_types=DRAGAPULT_DECK_TYPES)
    assert b.size == 2


def test_two_supporters_never_co_occur():
    """Two Supporters in hand is still ONE this turn. Asserted on the option CONTENTS: two 2-unit
    alternatives and one 2-unit sum look identical from `size` alone."""
    c = _combat()
    b = c.attach_budget(_pult(), [CRISPIN, ROSA], deck_energy_types=DRAGAPULT_DECK_TYPES,
                        discard_energy_counts={FIRE: 1, PSYCHIC: 1}, more_prizes_than_opp=True)
    assert b.size == 2
    assert max(len(option) for option in b.options) == 2
    # Every option is drawn from ONE Supporter: Rosa's units are discard-sourced, Crispin's are not.
    for option in b.options:
        sources = {DISCARD_SUPPLY in unit.groups for unit in option}
        assert len(sources) <= 1, f"an option mixes both Supporters' units: {option}"


def test_the_supporter_quota_being_spent_zeroes_a_supporter_tutor():
    c = _combat()
    b = c.attach_budget(_pult(), [CRISPIN], supporter_played=True,
                        deck_energy_types=DRAGAPULT_DECK_TYPES)
    assert b.size == 0
    assert c.reachable_attach(_pult(), None, budget=b) is False


def test_an_item_tutor_is_unaffected_by_a_spent_supporter_quota():
    """Fighting Gong is an ITEM — the spent Supporter slot does not gate it."""
    c = _combat()
    b = c.attach_budget(_pult(), [GONG], supporter_played=True,
                        deck_energy_types=frozenset({FIGHTING}))
    assert b.size == 1


def test_hand_yield_cards_compete_for_the_single_manual_attach():
    """Gong and Hilda both only put an Energy in HAND — two cards, still ONE manual attach."""
    c = _combat()
    b = c.attach_budget(_pult(), [GONG, HILDA],
                        deck_energy_types=frozenset({FIGHTING, FIRE, PSYCHIC}))
    assert b.size == 1


def test_a_spent_manual_attach_zeroes_a_hand_yield_card():
    c = _combat()
    b = c.attach_budget(_pult(), [GONG], energy_attached=True,
                        deck_energy_types=frozenset({FIGHTING}))
    assert b.size == 0


def test_crispin_keeps_its_effect_attach_when_the_manual_attach_is_spent():
    """The effect-attach leg is INDEPENDENT of the turn's one manual attach — it survives."""
    c = _combat()
    b = c.attach_budget(_pult(), [CRISPIN], energy_attached=True,
                        deck_energy_types=DRAGAPULT_DECK_TYPES)
    assert b.size == 1
    assert c.reachable_attach(_pult(), JET_HEADBUTT, budget=b) is True
    assert c.reachable_attach(_pult(), PHANTOM_DIVE, budget=b) is False


# ---- target restrictions and conditions --------------------------------------------------------

def test_wondrous_patch_never_funds_the_active():
    """Its clause targets a BENCHED {P} Pokémon — nothing it does reaches my Active."""
    c = _combat()
    b = c.attach_budget(_pult(), [PATCH], energy_attached=True,
                        discard_energy_counts={PSYCHIC: 1}, deck_energy_types=())
    assert b.size == 0


def test_wondrous_patch_funds_a_benched_psychic_body():
    c = _combat()
    slowking = {"id": 163, "hp": 120, "energies": []}
    stats = DictCardStatProvider({**_STATS,
                                  163: CardStat(163, synthetic=True, name='Slowking', hp=120, energyType=PSYCHIC,
                                                evolvesFrom="Slowpoke", cardType=0)},
                                 attacks=_ATTACKS)
    c = CombatMath(stats, functions=CardFunctions(_TAGS), effects=CardEffects(_CLAUSES))
    b = c.attach_budget(slowking, [PATCH], energy_attached=True, target_benched=True,
                        discard_energy_counts={PSYCHIC: 1}, deck_energy_types=())
    assert b.size == 1


def test_wondrous_patch_needs_the_energy_visible_in_the_discard():
    c = _combat()
    slowking = {"id": 163, "hp": 120, "energies": []}
    stats = DictCardStatProvider({**_STATS,
                                  163: CardStat(163, synthetic=True, name='Slowking', hp=120, energyType=PSYCHIC,
                                                evolvesFrom="Slowpoke", cardType=0)},
                                 attacks=_ATTACKS)
    c = CombatMath(stats, functions=CardFunctions(_TAGS), effects=CardEffects(_CLAUSES))
    b = c.attach_budget(slowking, [PATCH], energy_attached=True, target_benched=True,
                        discard_energy_counts={}, deck_energy_types=())
    assert b.size == 0


def test_rosa_funds_a_stage_2_only_while_ahead_on_prizes():
    """Rosa's Encouragement is prize-gated ('only if you have MORE Prize cards remaining')."""
    c = _combat()
    ahead = c.attach_budget(_pult(), [ROSA], energy_attached=True, more_prizes_than_opp=True,
                            discard_energy_counts={FIRE: 1, PSYCHIC: 1}, deck_energy_types=())
    behind = c.attach_budget(_pult(), [ROSA], energy_attached=True, more_prizes_than_opp=False,
                             discard_energy_counts={FIRE: 1, PSYCHIC: 1}, deck_energy_types=())
    assert ahead.size == 2 and behind.size == 0
    assert c.reachable_attach(_pult(), PHANTOM_DIVE, budget=ahead) is True


def test_rosa_never_funds_a_non_stage_2_body():
    riolu = {"id": 677, "hp": 80, "energies": []}
    stats = DictCardStatProvider({**_STATS, 677: CardStat(677, synthetic=True, name='Riolu', hp=80, cardType=0)},
                                 attacks=_ATTACKS)
    c = CombatMath(stats, functions=CardFunctions(_TAGS), effects=CardEffects(_CLAUSES))
    b = c.attach_budget(riolu, [ROSA], energy_attached=True, more_prizes_than_opp=True,
                        discard_energy_counts={FIRE: 1}, deck_energy_types=())
    assert b.size == 0


# ---- the visible discard is a SUPPLY, not just a palette --------------------------------------

def test_rosa_is_capped_by_what_the_discard_actually_holds():
    """"Attach up to 2 Basic Energy from your discard pile" over a discard holding ONE is ONE
    attach — the pile is public, so its supply is exact and the yield may not outrun it."""
    c = _combat()
    one = c.attach_budget(_pult(), [ROSA], energy_attached=True, more_prizes_than_opp=True,
                          discard_energy_counts={FIRE: 1}, deck_energy_types=())
    assert one.size == 1
    assert c.reachable_attach(_pult(), PHANTOM_DIVE, budget=one) is False   # {R}{P} needs both
    two = c.attach_budget(_pult(), [ROSA], energy_attached=True, more_prizes_than_opp=True,
                          discard_energy_counts={FIRE: 1, PSYCHIC: 1}, deck_energy_types=())
    assert two.size == 2


def test_the_discard_cap_binds_by_COLOUR_not_merely_by_count():
    """A cap that counted units without tracking which colour each consumed would call {P}{P} payable
    off a {R:1, P:1} pile — two legal units, jointly impossible (the ADR-0067 catastrophic direction)."""
    c = _combat()
    b = c.attach_budget(_pult(), [ROSA], energy_attached=True, more_prizes_than_opp=True,
                        discard_energy_counts={FIRE: 1, PSYCHIC: 1}, deck_energy_types=())
    assert c.reachable_attach(_pult(), PHANTOM_DIVE, budget=b) is True         # {R}{P}: one each
    same_colour = {**_STATS, DRAGAPULT: CardStat(DRAGAPULT, synthetic=True, name='Dragapult ex', hp=320,
                                                 minAttackCost=2, attacks=(9998,), cardType=0)}
    c2 = CombatMath(DictCardStatProvider(same_colour,
                                         attacks={9998: AttackStat(9998, damage=10, cost=2,
                                                                   energyTypes=(PSYCHIC, PSYCHIC))}),
                    functions=CardFunctions(_TAGS), effects=CardEffects(_CLAUSES))
    assert c2.reachable_attach(_pult(), 9998, budget=b) is False               # {P}{P}: only one {P}
    richer = c.attach_budget(_pult(), [ROSA], energy_attached=True, more_prizes_than_opp=True,
                             discard_energy_counts={PSYCHIC: 2}, deck_energy_types=())
    assert c2.reachable_attach(_pult(), 9998, budget=richer) is True           # two {P} in the pile


def test_two_discard_accelerators_share_one_pile():
    """Two Wondrous Patches over a single {P} in the discard is ONE attach, not two — every
    discard-drawing effect this turn competes for the same public pile."""
    slowking = {"id": 163, "hp": 120, "energies": []}
    stats = DictCardStatProvider({**_STATS,
                                  163: CardStat(163, synthetic=True, name='Slowking', hp=120, energyType=PSYCHIC,
                                                evolvesFrom="Slowpoke", cardType=0)},
                                 attacks=_ATTACKS)
    c = CombatMath(stats, functions=CardFunctions(_TAGS), effects=CardEffects(_CLAUSES))
    scarce = c.attach_budget(slowking, [PATCH, PATCH], energy_attached=True, target_benched=True,
                             discard_energy_counts={PSYCHIC: 1}, deck_energy_types=())
    assert scarce.size == 1
    stocked = c.attach_budget(slowking, [PATCH, PATCH], energy_attached=True, target_benched=True,
                              discard_energy_counts={PSYCHIC: 2}, deck_energy_types=())
    assert stocked.size == 2


def test_a_type_locked_accel_cannot_eat_a_colour_the_discard_lacks():
    """Wondrous Patch is {P}-locked: a discard full of {R} supplies it nothing."""
    slowking = {"id": 163, "hp": 120, "energies": []}
    stats = DictCardStatProvider({**_STATS,
                                  163: CardStat(163, synthetic=True, name='Slowking', hp=120, energyType=PSYCHIC,
                                                evolvesFrom="Slowpoke", cardType=0)},
                                 attacks=_ATTACKS)
    c = CombatMath(stats, functions=CardFunctions(_TAGS), effects=CardEffects(_CLAUSES))
    b = c.attach_budget(slowking, [PATCH], energy_attached=True, target_benched=True,
                        discard_energy_counts={FIRE: 3}, deck_energy_types=())
    assert b.size == 0


# ---- fail-closed -------------------------------------------------------------------------------

def test_an_unmodelled_card_contributes_zero():
    """ADR-0067: yield fails CLOSED. A tagged accel card with no Effect-Clause row is worth NOTHING
    — the oracle never guesses a yield it cannot read at source."""
    c = _combat(clauses={})                      # every clause row removed; tags unchanged
    b = c.attach_budget(_pult(), [CRISPIN, GONG, ROSA], deck_energy_types=DRAGAPULT_DECK_TYPES,
                        discard_energy_counts={FIRE: 1, PSYCHIC: 1}, more_prizes_than_opp=True)
    assert b.size == 0
    assert c.reachable_attach(_pult(), None, budget=b) is False


def test_an_untagged_card_is_never_inspected():
    c = _combat()
    b = c.attach_budget(_pult(), [CINDERACE], deck_energy_types=DRAGAPULT_DECK_TYPES)
    assert b.size == 0


def test_an_unknown_body_fails_closed():
    c = _combat()
    b = c.attach_budget(_pult(), [CRISPIN], deck_energy_types=DRAGAPULT_DECK_TYPES)
    assert c.reachable_attach({"id": 999999, "hp": 100, "energies": []}, None, budget=b) is False
    assert c.reachable_attach(None, None, budget=b) is False


def test_an_unknown_attack_record_makes_no_claim():
    c = _combat()
    b = c.attach_budget(_pult(), [CRISPIN], deck_energy_types=DRAGAPULT_DECK_TYPES)
    assert c.reachable_attach(_pult(), 424242, budget=b) is False


def test_a_stat_blind_oracle_fails_closed():
    c = CombatMath(None, functions=None, effects=None)
    b = c.attach_budget(_pult(), [CRISPIN], deck_energy_types=DRAGAPULT_DECK_TYPES)
    assert b.size == 0
    assert c.reachable_attach(_pult(), PHANTOM_DIVE, budget=b) is False


# ---- transient attack locks (ADR-0033) ---------------------------------------------------------

class _Transients:
    def __init__(self, grant):
        self._grant = grant

    def grant_for_serial(self, serial):
        return self._grant if serial == 1 else None


def test_a_self_locked_body_can_never_attack_however_rich_the_budget():
    c = _combat(transients=_Transients({"self_lock": True}))
    b = c.attach_budget(_pult(E_R, E_P), [], energy_attached=True, deck_energy_types=())
    assert c.reachable_attach(_pult(E_R, E_P), None, budget=b) is False


def test_a_same_locked_attack_is_skipped_but_its_sibling_still_counts():
    c = _combat(transients=_Transients({"same_lock": PHANTOM_DIVE}))
    b = c.attach_budget(_pult(E_R, E_P), [], energy_attached=True, deck_energy_types=())
    assert c.reachable_attach(_pult(E_R, E_P), PHANTOM_DIVE, budget=b) is False
    assert c.reachable_attach(_pult(E_R, E_P), JET_HEADBUTT, budget=b) is True
    assert c.reachable_attach(_pult(E_R, E_P), None, budget=b) is True       # not a famine


# ---- readiness_p (the EV variant) --------------------------------------------------------------

def test_readiness_is_certain_when_the_budget_already_reaches():
    c = _combat()
    b = c.attach_budget(_pult(), [CRISPIN], deck_energy_types=DRAGAPULT_DECK_TYPES)
    assert c.readiness_p(_pult(), PHANTOM_DIVE, budget=b) == 1.0


def test_readiness_is_zero_with_no_enabler_to_draw():
    c = _combat()
    b = c.attach_budget(_pult(), [], energy_attached=True, deck_energy_types=DRAGAPULT_DECK_TYPES)
    assert c.readiness_p(_pult(), PHANTOM_DIVE, budget=b) == 0.0


def test_readiness_prices_a_still_in_deck_enabler_hypergeometrically():
    """The probabilistic MIDDLE `_promote_fetch_p` never had: the enabler is not in hand, but the
    turn's dig can still find it — 4 copies among 40 cards over 6 draws."""
    c = _combat()
    now = c.attach_budget(_pult(), [], deck_energy_types=DRAGAPULT_DECK_TYPES)
    with_enabler = c.attach_budget(_pult(), [CRISPIN], deck_energy_types=DRAGAPULT_DECK_TYPES)
    p = c.readiness_p(_pult(), PHANTOM_DIVE, budget=now, enabler_budget=with_enabler,
                      copies=4, pool=40, draws=6)
    assert 0.0 < p < 1.0
    from common.deck_odds import draw_hit_probability
    assert p == draw_hit_probability(4, 40, 6)


def test_readiness_is_certain_when_the_enabler_is_already_in_hand():
    """The 'deck-certain / in-hand' branch: an enabler I HOLD is not a draw — it is 1.0, and the
    hypergeometric arguments are ignored rather than diluting a certainty."""
    c = _combat()
    held = c.attach_budget(_pult(), [CRISPIN], deck_energy_types=DRAGAPULT_DECK_TYPES)
    assert c.readiness_p(_pult(), PHANTOM_DIVE, budget=held, copies=1, pool=40, draws=1) == 1.0


def test_readiness_is_zero_when_even_the_enabler_would_not_reach():
    """Fail-closed: drawing a card that still cannot pay the attack is worth 0, not its draw odds."""
    c = _combat()
    now = c.attach_budget(_pult(), [], energy_attached=True, deck_energy_types=frozenset())
    with_enabler = c.attach_budget(_pult(), [CRISPIN], energy_attached=True,
                                   deck_energy_types=frozenset())
    assert c.readiness_p(_pult(), PHANTOM_DIVE, budget=now, enabler_budget=with_enabler,
                         copies=4, pool=40, draws=6) == 0.0


# ---- the Pilot's typed deck-fuel gate (ADR-0067's fail-OPEN leg) -------------------------------

def _pilot_with_energy_deck(**kw):
    from common.pilot import Pilot
    from common.strategy import Strategy
    return Pilot(Strategy(), deck=[E_R, E_R, E_R, E_P, E_P, E_P, E_D, E_D, DRAGAPULT],
                 stats=DictCardStatProvider(_STATS, attacks=_ATTACKS),
                 functions=CardFunctions(_TAGS), **kw)


def test_typed_deck_fuel_reports_every_type_not_provably_empty():
    """The shipped dragapult suite (3×{R} / 3×{P} / 2×{D}) with nothing exhausted."""
    assert _pilot_with_energy_deck()._basic_energy_types_in_deck(frozenset()) == DRAGAPULT_DECK_TYPES


def test_typed_deck_fuel_drops_a_provably_exhausted_type():
    p = _pilot_with_energy_deck()
    assert p._basic_energy_types_in_deck(frozenset({E_R})) == frozenset({PSYCHIC, DARKNESS})
    assert p._basic_energy_types_in_deck(frozenset({E_R, E_P, E_D})) == frozenset()


def test_typed_deck_fuel_ignores_non_energy_cards():
    assert DRAGON not in _pilot_with_energy_deck()._basic_energy_types_in_deck(frozenset())


def test_typed_deck_fuel_is_empty_without_stats():
    from common.pilot import Pilot
    from common.strategy import Strategy
    blind = Pilot(Strategy(), deck=[E_R], stats=None, functions=None)
    assert blind._basic_energy_types_in_deck(frozenset()) == frozenset()


# ---- the payment matcher, cross-checked against brute force ------------------------------------

def test_the_typed_matcher_agrees_with_an_exhaustive_reference():
    """`_can_pay` is a pruned search, checked against an exhaustive reference: a silent over-count
    would hand a consumer a false 'can attack' (the ADR-0067 catastrophic direction)."""
    import itertools
    import random

    from common.strategy.combat import AttachUnit as _U
    from common.strategy.combat import _can_pay

    def brute(slots, units, caps):
        """Try every injective slot->unit assignment and every concrete type per used unit."""
        if len(units) < len(slots):
            return False
        for perm in itertools.permutations(range(len(units)), len(slots)):
            pools = []
            for slot, j in zip(slots, perm):
                u = units[j]
                if slot not in (0, None):
                    pools.append([slot] if (not u.types or slot in u.types) else [])
                else:
                    pools.append(sorted(u.types) or [None])
            for picks in itertools.product(*pools) if all(pools) else ():
                spent = {}
                for (slot, j), chosen in zip(zip(slots, perm), picks):
                    for g in units[j].groups:
                        spent[(g, chosen)] = spent.get((g, chosen), 0) + 1
                if all(n <= caps.get(g, {}).get(t, 0) for (g, t), n in spent.items()):
                    return True
        return False

    rng = random.Random(137)
    types = [FIRE, PSYCHIC, FIGHTING, DARKNESS]
    for _ in range(3000):
        slots = tuple(rng.choice([COLORLESS] + types) for _ in range(rng.randint(1, 3)))
        caps = {g: {t: rng.randint(0, 2) for t in types} for g in ("A", "B")}
        units = tuple(
            _U(rng.choice([frozenset(), frozenset({rng.choice(types)}),
                           frozenset(rng.sample(types, rng.randint(2, 3)))]),
               rng.choice([(), (), ("A",), ("B",), ("A", "B")]))
            for _ in range(rng.randint(0, 4)))
        assert _can_pay(slots, units, caps) is brute(slots, units, caps), (slots, units, caps)


# ── hand SPECIAL Energy provision (Issue #142) ────────────────────────────────────────────────
# Ignition (17) and Boomerang (9) both report energyType 0 (colourless); Telepath Psychic (19) {P}.

IGNITION, BOOMERANG = 17, 9
MEGA_LUC, RIOLU = 678, 677                       # the single-hop line: Riolu (Basic) -> Mega Lucario ex
MEGA_BRAVE, RIOLU_BIG = 983, 984                 # attack ids


def _special_combat(tags):
    stats = {
        MEGA_LUC: CardStat(MEGA_LUC, synthetic=True, name='Mega Lucario ex', hp=340, energyType=FIGHTING,
                           evolvesFrom="Riolu", attacks=(MEGA_BRAVE,), cardType=0),
        RIOLU: CardStat(RIOLU, synthetic=True, name='Riolu', hp=80, energyType=FIGHTING, attacks=(RIOLU_BIG,),
                        cardType=0),
        IGNITION: CardStat(IGNITION, name="Ignition Energy", cardType=6, energyType=0),
        BOOMERANG: CardStat(BOOMERANG, name="Boomerang Energy", cardType=6, energyType=0),
    }
    attacks = {MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=3, energyTypes=(0, 0, 0)),
               RIOLU_BIG: AttackStat(RIOLU_BIG, damage=30, cost=3, energyTypes=(0, 0, 0))}
    return CombatMath(DictCardStatProvider(stats, attacks=attacks),
                      functions=CardFunctions(tags), transients=None, effects=CardEffects({}))


_IGNITION_TAGS = {IGNITION: ignition_tags(),
                  BOOMERANG: ["provides:1"]}


def test_an_ignition_arms_an_evolution_from_zero():
    """The false famine this closes: Mega Lucario ex is an Evolution, so one Ignition provides three
    colourless — Mega Brave's whole cost — from an empty body."""
    c = _special_combat(_IGNITION_TAGS)
    body = {"id": MEGA_LUC, "energies": []}
    budget = c.attach_budget(body, [IGNITION])
    assert budget.size == 3
    assert c.reachable_attach(body, MEGA_BRAVE, budget=budget) is True


def test_the_same_ignition_provides_one_on_a_basic():
    """"...to an Evolution Pokemon... instead" — a Basic gets the plain {C}, so the identical hand
    reaches nothing on Riolu."""
    c = _special_combat(_IGNITION_TAGS)
    body = {"id": RIOLU, "energies": []}
    budget = c.attach_budget(body, [IGNITION])
    assert budget.size == 1
    assert c.reachable_attach(body, RIOLU_BIG, budget=budget) is False


def test_a_colourless_provision_cannot_pay_a_typed_slot():
    """Ignition reports energyType 0, so its units are coloured exactly as an ATTACHED Ignition is —
    colourless-only. A {F}{F}{F} cost is NOT reachable off it."""
    c = _special_combat(_IGNITION_TAGS)
    typed = {MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=3,
                                    energyTypes=(FIGHTING, FIGHTING, FIGHTING))}
    c.stats = DictCardStatProvider(dict(c.stats._stats), attacks=typed)
    body = {"id": MEGA_LUC, "energies": []}
    assert c.reachable_attach(body, MEGA_BRAVE,
                              budget=c.attach_budget(body, [IGNITION])) is False


def test_the_manual_attach_plays_one_special_energy_not_both():
    """Two Specials in hand are two ALTERNATIVE sources for the single manual attach, never a sum."""
    c = _special_combat(_IGNITION_TAGS)
    body = {"id": MEGA_LUC, "energies": []}
    assert c.attach_budget(body, [IGNITION, BOOMERANG]).size == 3


def test_a_spent_manual_attach_zeroes_a_hand_special_energy():
    c = _special_combat(_IGNITION_TAGS)
    body = {"id": MEGA_LUC, "energies": []}
    assert c.attach_budget(body, [IGNITION], energy_attached=True).size == 0


def test_an_untagged_special_energy_provides_nothing():
    """Fail-CLOSED (ADR-0067): no `provides:N` row, no units — never a guessed one. The coverage
    gate is what stops a shipped deck reaching this state silently."""
    c = _special_combat({IGNITION: ["discard_eot"]})
    body = {"id": MEGA_LUC, "energies": []}
    assert c.attach_budget(body, [IGNITION]).size == 0


# ── the Probability Leg on the Budget (ADR-0074 / #175) ───────────────────────────────────────

def test_realising_p_is_1_when_the_cost_is_paid_from_certain_units():
    """The dependency, not the pantry: a cost paid by units that are already certain scores exactly
    1.0 even when a deck-sourced unit sits in the same option on a depleted type."""
    certain = AttachUnit(frozenset({1}))                      # in hand / attached — no source
    thin = AttachUnit(frozenset({2}), source="deck")          # deck-sourced, type 2 nearly gone
    b = Budget(options=((certain, thin),))
    assert b.realising_p((1,), {2: 0.05}) == 1.0              # slot {1} taken by the certain unit


def test_realising_p_prices_a_deck_sourced_unit_the_cost_actually_needs():
    thin = AttachUnit(frozenset({2}), source="deck")
    b = Budget(options=((thin,),))
    assert round(b.realising_p((2,), {2: 0.87}), 10) == 0.87


def test_realising_p_prices_distinct_deck_types_once_each():
    """Two distinct deck-sourced colours compound; the SAME colour twice is priced once (P(>=1))."""
    r = AttachUnit(frozenset({1}), source="deck")
    p = AttachUnit(frozenset({2}), source="deck")
    p2 = AttachUnit(frozenset({2}), source="deck")
    assert round(Budget(options=((r, p),)).realising_p((1, 2), {1: 0.9, 2: 0.8}), 10) == 0.72
    assert round(Budget(options=((p, p2),)).realising_p((2, 2), {2: 0.8}), 10) == 0.8


def test_realising_p_is_zero_when_nothing_pays():
    """A Budget that cannot pay scores 0.0 — never a probability for an unpayable cost."""
    unit = AttachUnit(frozenset({1}), source="deck")
    assert Budget(options=((unit,),)).realising_p((2,), {1: 1.0, 2: 1.0}) == 0.0
    assert Budget(options=((unit,),)).realising_p((1, 1), {1: 1.0}) == 0.0   # too few units


def test_realising_p_takes_the_best_assignment_not_the_first():
    """Two ways to pay a colourless slot; the maximiser must choose the certain one."""
    certain = AttachUnit(frozenset({1}))
    thin = AttachUnit(frozenset({1}), source="deck")
    b = Budget(options=((thin, certain),))                    # deck unit listed FIRST
    assert b.realising_p((0,), {1: 0.1}) == 1.0


def test_realising_p_agrees_with_can_pay_on_feasibility():
    """`realising_p > 0` iff the boolean matcher would have paid — one matcher, two readings."""
    units = (AttachUnit(frozenset({1}), source="deck"), AttachUnit(frozenset({2})))
    b = Budget(options=(units,))
    for slots in ((1,), (2,), (1, 2), (0, 0), (1, 1), (3,)):
        payable = _can_pay(slots, units, b.caps)
        assert (b.realising_p(slots, {1: 0.5, 2: 1.0}) > 0.0) is bool(payable)


def test_realising_p_of_a_free_cost_is_certain():
    assert Budget(options=((),)).realising_p((), {}) == 1.0


# ── Issue #175, ADR-0074 decision 7: the TAIL fixture alone cannot distinguish per-assignment from
# per-Budget weighting; the COMPLEMENT falsifies the wrong design, DEGENERACY discharges regression.

def _thin_deck_p(p_thin):
    """A probability map for a deck depleted to its last {P}: {R} plentiful, {P} nearly gone."""
    return {FIRE: 0.999, PSYCHIC: p_thin}


def test_tail_a_deck_sourced_ko_is_discounted_at_low_unseen():
    """FAMILY 1 (the tail): the composed line's KO rides a {P} fetch with one copy unseen, so the
    cost's realising probability tracks the depletion ramp instead of reading 1.0."""
    deck_r = AttachUnit(frozenset({FIRE}), source="deck")
    deck_p = AttachUnit(frozenset({PSYCHIC}), source="deck")
    budget = Budget(options=((deck_r, deck_p),))
    # Phantom Dive's {R}{P}: both slots ride the deck, so both colours are priced.
    assert round(budget.realising_p((FIRE, PSYCHIC), _thin_deck_p(0.87)), 6) == round(
        0.999 * 0.87, 6)


def test_complement_the_same_frame_pays_from_hand_at_full_value():
    """FAMILY 2 (the complement): SAME depleted deck, cost paid from hand. Per-assignment pricing
    reads 1.0; the rejected per-Budget weighting would discount it for the thin fetch beside it."""
    in_hand_r = AttachUnit(frozenset({FIRE}))                 # certain — no source
    in_hand_p = AttachUnit(frozenset({PSYCHIC}))              # certain
    thin_fetch = AttachUnit(frozenset({PSYCHIC}), source="deck")
    budget = Budget(options=((in_hand_r, in_hand_p, thin_fetch),))
    assert budget.realising_p((FIRE, PSYCHIC), _thin_deck_p(0.05)) == 1.0


def test_degeneracy_an_anchored_deck_is_byte_identical_to_the_unweighted_read():
    """FAMILY 3 (degeneracy): once a search anchors the prizes every `p_any` is exactly 1.0, so the
    weighted read equals the unweighted one — this is what discharges Issue #175's no-regression claim."""
    deck_r = AttachUnit(frozenset({FIRE}), source="deck")
    deck_p = AttachUnit(frozenset({PSYCHIC}), source="deck")
    budget = Budget(options=((deck_r, deck_p),))
    anchored = {FIRE: 1.0, PSYCHIC: 1.0}
    assert budget.realising_p((FIRE, PSYCHIC), anchored) == 1.0
    # and a type the sound oracle proved gone is exactly 0 — never a small positive claim
    assert budget.realising_p((FIRE, PSYCHIC), {FIRE: 1.0, PSYCHIC: 0.0}) == 0.0


def test_weighting_reorders_a_shaky_two_prize_line_below_a_certain_one_prize_line():
    """ADR-0074 decision 4: a capped positional score could never express this, which is why the
    hard-rung invariant had to be restated in expectation."""
    from common.strategy.planner import _composed_rank
    shaky_two = (2.0, False, 0.40)                            # 2 prizes, 40% to land
    certain_one = (1.0, False, 1.0)                           # 1 prize, certain
    assert _composed_rank(certain_one) > _composed_rank(shaky_two)
    # …and a merely-slightly-shaky 2-prize line still beats it (no threshold anywhere)
    assert _composed_rank((2.0, False, 0.87)) > _composed_rank(certain_one)


# ── #175 decision-6 extension: the POKEMON-presence leg is weighted too ───────────────────────

def test_pokemon_presence_weight_composes_with_the_energy_weight():
    """A composed line whiffs two independent ways, and `_composed_rank` sees ONE probability — so
    the two must be multiplied into it, not chosen between."""
    from common.strategy.planner import _composed_rank
    energy_only = (2.0, False, 0.87)                          # Energy 87%, Pokemon certain
    both = (2.0, False, 0.87 * 0.90)                          # …and the evolution 90% present
    assert _composed_rank(both) < _composed_rank(energy_only)
    # EV, not pessimism: 2 prizes at 0.783 is worth 1.57 and still BEATS a certain 1-prize line…
    assert _composed_rank(both) > _composed_rank((1.0, False, 1.0))
    # …it is only once the compounded odds drop below half that the certain single prize wins.
    assert _composed_rank((2.0, False, 0.87 * 0.50)) < _composed_rank((1.0, False, 1.0))


def test_no_threshold_survives_anywhere_in_the_ranked_ladder():
    """The retired `deck_contains_probability(cid) <= 0.5` cut-off is the shape ADR-0074 decision 1
    rejects. Ranking must be strictly monotone in the odds — no cliff at any value."""
    from common.strategy.planner import _composed_rank
    ladder = [_composed_rank((1.0, False, p)) for p in (0.05, 0.49, 0.51, 0.75, 0.99, 1.0)]
    assert ladder == sorted(ladder)
    assert len(set(ladder)) == len(ladder)                    # strictly increasing: no flat cliff
