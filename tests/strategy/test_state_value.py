"""`common/state_value.py` — the State Value scalar (ADR-0092 §4-T3, Issue #262).

Two jobs: the coverage map (no fact priced twice or by nobody), and MID-TURN monotonicity, since the
composer differences half-finished turns far more often than finished ones. Construction follows
`test_state_model.py` — dict-backed Stat Provider, hand-built zones, no Pilot and no engine boot. Every
`CardStat` literal below is audited against `data/EN_Card_Data.csv` by `test_cardstat_fixture_facts.py`.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from card_facts import ignition_tags                    # the committed tags, ONE copy
from common import currency, needs as _needs, state_value as sv
from common.card_worth import ROLE_TIER, TAG_TIER
from common.cards import CardFunctions
from common.effects import CardEffects
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.state_model import StateModel
from common.strategy.combat import CombatMath

# ── the fixture board ─────────────────────────────────────────────────────────────────────────────

COLORLESS, GRASS, FIRE, WATER = 0, 1, 2, 3
LIGHTNING, PSYCHIC, FIGHTING, DARKNESS, DRAGON = 4, 5, 6, 7, 9
DRAGAPULT, MUNKIDORI, RIOLU, MEGA_LUC = 121, 112, 677, 678
MEGA_STARMIE, GOUGING_FIRE, CRUSTLE, BRAVIARY = 1031, 46, 345, 1008
ALAKAZAM = 743
SLOWKING, BRAVE_BANGLE = 163, 1175
STARYU, DREEPY, DRAKLOAK = 1030, 119, 120
JET_HEADBUTT, PHANTOM_DIVE, AURA_JAB, MEGA_BRAVE = 9121, 9122, 982, 983
#: Riolu's ONLY attack — Accelerating Stab ``{F}`` 30 with ``nextTurnSameAttackLock``, so it is the
#: cast's one body whose only affordable attack locks (Issue #384).
ACCELERATING_STAB = 9677
SUPER_PSY_BOLT = 214
JETTING_BLOW, NEBULA_BEAM, SUPERB_SCISSORS, CLUTCH = 91031, 91032, 9345, 91008
WATER_GUN = 91030          # Staryu's only attack
HEAT_BLAST, BLAZE_BLITZ, POWERFUL_HAND = 946, 947, 9743
E_R, E_P, E_F, E_D, E_W = 2, 5, 6, 7, 3
IGNITION = 17               # the pool's ONE `discard_eot` Energy
#: The bench-GATED pair (Issue #287): Cosmic Beam does nothing without Lunatone benched, and Lunar
#: Cycle needs Solrock — `mega_lucario` runs 3x Solrock / 2x Lunatone, so they enable each other.
SOLROCK, LUNATONE = 676, 675
COSMIC_BEAM, POWER_GEM = 9676, 9675
#: The conditional-BONUS shape, against the conditional-ZERO one above: Conjoined Beams prints 130 and
#: +150 more if Beldum and Metang are benched — `slowking` runs neither, so it is never payable.
METAGROSS = 276
WRACK_DOWN, CONJOINED_BEAMS = 9276, 9277
#: Issue #384's COIN attacker, a real card: Quick Attack parses to ``damageMin=20, damageMax=40`` with
#: NO flip count and no probability anywhere, which is why `attack_ev_legs` needs a declared bound.
EEVEE = 43
ASCENSION, QUICK_ATTACK = 9043, 9044

_STATS = {
    DRAGAPULT: CardStat(DRAGAPULT, synthetic=True, name='Dragapult ex', hp=320, ex=True, stage2=True,
                        evolvesFrom="Drakloak", energyType=DRAGON, maxDamage=200, maxDamageCost=2,
                        minAttackCost=1, minCostDamage=70, tera=True,
                        attacks=(JET_HEADBUTT, PHANTOM_DIVE), cardType=0),
    MUNKIDORI: CardStat(MUNKIDORI, synthetic=True, name='Munkidori', hp=110, energyType=PSYCHIC,
                        weakness=DARKNESS, resistance=FIGHTING, retreatCost=1, cardType=0),
    RIOLU: CardStat(RIOLU, synthetic=True, name='Riolu', hp=80, energyType=FIGHTING, minAttackCost=1,
                    maxDamage=30, maxDamageCost=1, minCostDamage=30,
                    attacks=(ACCELERATING_STAB,), cardType=0),
    MEGA_LUC: CardStat(MEGA_LUC, synthetic=True, name='Mega Lucario ex', hp=340, megaEx=True, energyType=FIGHTING,
                       evolvesFrom="Riolu", maxDamage=270, maxDamageCost=2, minAttackCost=1,
                       minCostDamage=130,
                       attacks=(AURA_JAB, MEGA_BRAVE), cardType=0),
    # ── Issue #281's damage-model cast: an attacker whose damage MOVES with the defender ──────
    MEGA_STARMIE: CardStat(MEGA_STARMIE, synthetic=True, name='Mega Starmie ex', hp=330, megaEx=True,
                           energyType=WATER, weakness=LIGHTNING, evolvesFrom="Staryu",
                           maxDamage=210, maxDamageCost=3, minAttackCost=1, minCostDamage=120,
                           benchSnipeDamage=50, attacks=(JETTING_BLOW, NEBULA_BEAM), cardType=0),
    GOUGING_FIRE: CardStat(GOUGING_FIRE, synthetic=True, name='Gouging Fire ex', hp=230, ex=True,
                           energyType=FIRE, weakness=WATER, maxDamage=260, maxDamageCost=3,
                           minAttackCost=2, minCostDamage=60,
                           attacks=(HEAT_BLAST, BLAZE_BLITZ), cardType=0),
    CRUSTLE: CardStat(CRUSTLE, synthetic=True, name='Crustle', hp=150, energyType=GRASS, weakness=FIRE,
                      evolvesFrom="Dwebble", preventsDamageFrom="ex", maxDamage=120,
                      maxDamageCost=3, minAttackCost=3, minCostDamage=120,
                      attacks=(SUPERB_SCISSORS,), cardType=0),
    BRAVIARY: CardStat(BRAVIARY, synthetic=True, name="Larry's Braviary", hp=130, energyType=COLORLESS,
                       weakness=LIGHTNING, resistance=FIGHTING, evolvesFrom="Larry's Rufflet",
                       maxDamage=50, maxDamageCost=2, minAttackCost=2, minCostDamage=50,
                       attacks=(CLUTCH,), cardType=0),
    # ── Issue #280's context cast: an attacker whose damage IS a context variable ──────────────
    ALAKAZAM: CardStat(ALAKAZAM, synthetic=True, name='Alakazam', hp=140, stage2=True, evolvesFrom="Kadabra",
                       energyType=PSYCHIC, weakness=DARKNESS, resistance=FIGHTING,
                       maxDamage=0, maxDamageCost=1, minAttackCost=1, minCostDamage=0,
                       handSizeDamage=20, attacks=(POWERFUL_HAND,), cardType=0),
    # ── Issue #345's cast: a boost that arrives ATTACHED, and a holder its gate can refuse ─────
    SLOWKING: CardStat(SLOWKING, synthetic=True, name='Slowking', hp=120, evolvesFrom="Slowpoke",
                       energyType=PSYCHIC, weakness=DARKNESS, resistance=FIGHTING, retreatCost=3,
                       maxDamage=120, maxDamageCost=3, minAttackCost=2, minCostDamage=0,
                       attacks=(SUPER_PSY_BOLT,), cardType=0),
    BRAVE_BANGLE: CardStat(BRAVE_BANGLE, name="Brave Bangle", cardType=2, damageBoost=30,
                           damageBoostVsEx=True, holderNoRuleBox=True),
    # ── Issue #285's cast: the PRE-EVOLUTIONS whose removal denies a forward payoff ────────────
    # Staryu's ``attacks`` is load-bearing: a body with no attacks answers `readiness_p` 0.0 wrongly.
    STARYU: CardStat(STARYU, synthetic=True, name='Staryu', hp=70, energyType=WATER, weakness=LIGHTNING,
                     retreatCost=1, maxDamage=20, maxDamageCost=1, minAttackCost=1,
                     minCostDamage=20, attacks=(WATER_GUN,), cardType=0),
    DREEPY: CardStat(DREEPY, synthetic=True, name='Dreepy', hp=70, energyType=DRAGON, retreatCost=1,
                     maxDamage=40, maxDamageCost=2, minAttackCost=1, minCostDamage=10,
                     cardType=0),
    DRAKLOAK: CardStat(DRAKLOAK, synthetic=True, name='Drakloak', hp=90, energyType=DRAGON,
                       evolvesFrom="Dreepy", retreatCost=1, maxDamage=70, maxDamageCost=2,
                       minAttackCost=2, minCostDamage=70, cardType=0),
    # ── Issue #286's one card: the Energy that is GONE at the end of the turn ─────────────────
    # `energyType` COLORLESS — it arms Nebula Beam ``{C}{C}{C}`` outright and nothing for ``{F}{F}``.
    IGNITION: CardStat(IGNITION, name="Ignition Energy", cardType=6, energyType=COLORLESS),
    E_W: CardStat(E_W, name="Basic {W} Energy", cardType=5, energyType=WATER),
    SOLROCK: CardStat(SOLROCK, synthetic=True, name='Solrock', hp=110, energyType=FIGHTING, weakness=GRASS,
                      minAttackCost=1, maxDamage=70, maxDamageCost=1, minCostDamage=70,
                      attacks=(COSMIC_BEAM,), cardType=0),
    LUNATONE: CardStat(LUNATONE, synthetic=True, name='Lunatone', hp=110, energyType=FIGHTING, weakness=GRASS,
                       minAttackCost=2, maxDamage=50, maxDamageCost=2, minCostDamage=50,
                       attacks=(POWER_GEM,), cardType=0),
    METAGROSS: CardStat(METAGROSS, synthetic=True, name='Metagross', hp=170, stage2=True, evolvesFrom="Metang",
                        energyType=PSYCHIC, minAttackCost=1, maxDamage=130, maxDamageCost=2,
                        minCostDamage=60, attacks=(WRACK_DOWN, CONJOINED_BEAMS), cardType=0),
    EEVEE: CardStat(EEVEE, synthetic=True, name='Eevee', hp=50, energyType=COLORLESS,
                    weakness=FIGHTING, retreatCost=1, maxDamage=20, maxDamageCost=3,
                    minAttackCost=1, minCostDamage=0, attacks=(ASCENSION, QUICK_ATTACK),
                    cardType=0),
    E_R: CardStat(E_R, name="Basic {R} Energy", cardType=5, energyType=FIRE),
    E_P: CardStat(E_P, name="Basic {P} Energy", cardType=5, energyType=PSYCHIC),
    E_F: CardStat(E_F, name="Basic {F} Energy", cardType=5, energyType=FIGHTING),
    E_D: CardStat(E_D, name="Basic {D} Energy", cardType=5, energyType=DARKNESS),
}
_ATTACKS = {
    JET_HEADBUTT: AttackStat(JET_HEADBUTT, damage=70, cost=1, energyTypes=(COLORLESS,)),
    # ── Issue #384: the riders and locks the fixture used to DROP ────────────────────────────
    # Mega Brave is `nextTurnSameAttackLock`, NOT `nextTurnSelfLock` — the two price differently.
    PHANTOM_DIVE: AttackStat(PHANTOM_DIVE, damage=200, cost=2, energyTypes=(FIRE, PSYCHIC),
                             benchSpread=60),
    AURA_JAB: AttackStat(AURA_JAB, damage=130, cost=1, energyTypes=(FIGHTING,),
                         recoverN=3, recoverEnergyType=FIGHTING, recoverTarget="bench",
                         recoverSource="discard"),
    MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=2, energyTypes=(FIGHTING, FIGHTING),
                           nextTurnSameAttackLock=True),
    JETTING_BLOW: AttackStat(JETTING_BLOW, damage=120, cost=1, energyTypes=(WATER,), benchSnipe=50),
    WATER_GUN: AttackStat(WATER_GUN, damage=20, cost=1, energyTypes=(WATER,)),
    NEBULA_BEAM: AttackStat(NEBULA_BEAM, damage=210, cost=3,
                            energyTypes=(COLORLESS, COLORLESS, COLORLESS),
                            ignoresWeakness=True, ignoresResistance=True, ignoresEffects=True),
    SUPERB_SCISSORS: AttackStat(SUPERB_SCISSORS, damage=120, cost=3,
                                energyTypes=(GRASS, COLORLESS, COLORLESS), ignoresEffects=True),
    CLUTCH: AttackStat(CLUTCH, damage=50, cost=2, energyTypes=(COLORLESS, COLORLESS)),
    HEAT_BLAST: AttackStat(HEAT_BLAST, damage=60, cost=2, energyTypes=(FIRE, COLORLESS)),
    BLAZE_BLITZ: AttackStat(BLAZE_BLITZ, damage=260, cost=3,
                            energyTypes=(FIRE, FIRE, COLORLESS)),
    # Counter placement, so all three ignore flags are set. Printed 0: with no context it deals NOTHING.
    POWERFUL_HAND: AttackStat(POWERFUL_HAND, damage=0, cost=1, energyTypes=(PSYCHIC,),
                              scaleVar="atk_hand", scalePerUnit=20,
                              ignoresWeakness=True, ignoresResistance=True, ignoresEffects=True),
    SUPER_PSY_BOLT: AttackStat(SUPER_PSY_BOLT, damage=120, cost=3,
                               energyTypes=(PSYCHIC, PSYCHIC, COLORLESS)),
    COSMIC_BEAM: AttackStat(COSMIC_BEAM, damage=70, cost=1, energyTypes=(FIGHTING,),
                            requiresBench=("Lunatone",), ignoresWeakness=True,
                            ignoresResistance=True),
    POWER_GEM: AttackStat(POWER_GEM, damage=50, cost=2, energyTypes=(FIGHTING, FIGHTING)),
    WRACK_DOWN: AttackStat(WRACK_DOWN, damage=60, cost=1, energyTypes=(PSYCHIC,)),
    # ``damageMax`` 280 is the +150 leg: reachable through the oracle's "max" bound, never through this.
    CONJOINED_BEAMS: AttackStat(CONJOINED_BEAMS, damage=130, cost=2,
                                energyTypes=(PSYCHIC, PSYCHIC), damageMax=280),
    ACCELERATING_STAB: AttackStat(ACCELERATING_STAB, damage=30, cost=1, energyTypes=(FIGHTING,),
                                  nextTurnSameAttackLock=True),
    ASCENSION: AttackStat(ASCENSION, damage=0, cost=1, energyTypes=(COLORLESS,)),
    QUICK_ATTACK: AttackStat(QUICK_ATTACK, damage=20, cost=3,
                             energyTypes=(COLORLESS, COLORLESS, COLORLESS),
                             damageMin=20, damageMax=40),
}
DECK = [E_F] * 6 + [RIOLU] * 3 + [MEGA_LUC] * 3 + [MUNKIDORI]
#: `mega_lucario`'s single-prize core, so the deck-fetch leg of `readiness_p` sees the pair's Energy.
LUNAR_DECK = [E_F] * 6 + [RIOLU] * 3 + [MEGA_LUC] * 3 + [SOLROCK] * 3 + [LUNATONE] * 2

#: The deck's DECLARED Roles as Worth, through the model's `role_worth=` resolver. Roles are
#: declaration, not card data — `CardStat` carries no such field.
_ROLE_WORTH = {MEGA_LUC: ROLE_TIER["win_condition"], RIOLU: ROLE_TIER["win_condition_base"],
               MUNKIDORI: ROLE_TIER["engine"], DRAGAPULT: ROLE_TIER["primary_attacker"],
               MEGA_STARMIE: ROLE_TIER["win_condition"],
               SOLROCK: ROLE_TIER["secondary_attacker"], LUNATONE: ROLE_TIER["engine"],
               METAGROSS: ROLE_TIER["secondary_attacker"]}

#: Issue #282's boosts as the ``(amount, attackerEnergyType|None, vsExOnly)`` triple `strategy/damage.py`
#: consumes — a boost reaches a snapshot through the tracker, never through a card in a zone.
POWER_PRO_ID = 1141
POWER_PRO = (30, FIGHTING, False)
#: Black Belt's Training: +40, no attacker gate, defender-{ex} gate. That {ex} scope INCLUDES a Mega
#: Evolution Pokémon ex (`docs/rulebook.txt` L337).
BLACK_BELT = (40, None, True)


#: Ignition's two committed records, and they answer different halves: the CLAUSE's ``rider`` says the
#: card evaporates, the TAG's ``provides`` pair says how many units it supplies.
_IGNITION_TAGS = {IGNITION: ignition_tags()}
_IGNITION_CLAUSES = {IGNITION: [{"kind": "energy_provide", "amount": 1, "amount_on_evolution": 3,
                                 "type": "colorless", "rider": "discard_eot"}]}


def _combat():
    return CombatMath(DictCardStatProvider(_STATS, attacks=_ATTACKS),
                      functions=CardFunctions(_IGNITION_TAGS), transients=None,
                      effects=CardEffects(_IGNITION_CLAUSES))


def _poke(cid, *, hp, energies=(), serial=1, damage=0, tools=(), energy_cards=None):
    """``tools`` is the raw `_SideBase.tool_ids` key. ``energy_cards`` is the attached CARDS while
    ``energies`` is the `EnergyType` UNITS they provide — the engine keeps the two separate."""
    body = {"id": cid, "hp": hp - damage, "energies": list(energies), "serial": serial}
    if tools:
        body["tools"] = [{"id": t} for t in tools]
    if energy_cards is not None:
        body["energyCards"] = [{"id": c} for c in energy_cards]
    return body


def _player(*, active=None, bench=(), hand=(), discard=(), prize=4, deck_count=20):
    return {"active": [active] if active else [], "bench": list(bench),
            "hand": [{"id": c} for c in hand], "handCount": len(hand),
            "discard": [{"id": c} for c in discard], "prize": [None] * prize,
            "deckCount": deck_count,
            "poisoned": False, "burned": False, "asleep": False, "paralyzed": False,
            "confused": False}


class _Boosts:
    """`TurnBoostTracker`'s one duck-typed method. A this-turn Trainer boost is a LOG fact and not a
    board one, so the tracker is how it reaches a snapshot at all. Side 0 is mine on every board here."""

    def __init__(self, boosts=()):
        self._boosts = tuple(boosts)

    def boosts_for(self, side):
        return self._boosts if side == 0 else ()


def _model(me, opp, *, energy_attached=False, turn=5, needs=None, boosts=None, deck=None):
    obs = {"current": {"players": [me, opp], "yourIndex": 0, "turn": turn,
                       "energyAttached": energy_attached, "supporterPlayed": False,
                       "stadium": []}, "logs": []}
    return StateModel.build(obs, combat=_combat(), deck=DECK if deck is None else deck,
                            needs=needs, role_worth=_ROLE_WORTH.get,
                            turn_boosts=None if boosts is None else _Boosts(boosts))


def _lucario_board(*, my_energies=(), my_hp=340, bench=(), my_prizes=4, their_prizes=4,
                   their_active=None, hand=(), energy_attached=False, boosts=None):
    """MY Mega Lucario ex against THEIR Dragapult ex — the fixture the monotonicity cases perturb."""
    return _model(
        _player(active=_poke(MEGA_LUC, hp=my_hp, energies=my_energies), bench=list(bench),
                hand=list(hand), prize=my_prizes),
        _player(active=their_active or _poke(DRAGAPULT, hp=320, energies=[E_R, E_P], serial=9),
                prize=their_prizes),
        energy_attached=energy_attached, boosts=boosts)


def _starmie_board(their_active, *, my_energies=(E_W,), boosts=None):
    """MY Mega Starmie ex, with the turn's Energy already spent so the Attach Budget adds nothing."""
    return _model(
        _player(active=_poke(MEGA_STARMIE, hp=330, energies=list(my_energies)), prize=4),
        _player(active=their_active, prize=4),
        energy_attached=True, boosts=boosts)


def _alakazam_board(their_hand: int, *, my_active=None, my_hand=()):
    """THEIR Alakazam Active — the ``atk_hand`` attacker. Their hand is a bare COUNT (the engine's
    hidden-zone shape) and mine is real cards, so a direction error FAILS rather than looks plausible."""
    theirs = _player(active=_poke(ALAKAZAM, hp=140, energies=[E_P], serial=9), prize=4)
    theirs["hand"], theirs["handCount"] = [], int(their_hand)
    return _model(
        _player(active=my_active or _poke(MEGA_LUC, hp=340), hand=list(my_hand), prize=4),
        theirs)


# ── the coverage map — T0's headline rule, executable ─────────────────────────────────────────────


@pytest.mark.req("REQ-STATEVALUE-0001")
def test_no_fact_is_priced_twice():
    """Every board fact enters through exactly ONE term family (ADR-0092 §4-T0), across BOTH
    registries — `score(sequence)` literally adds `attack_ev` to `threat`."""
    assert sv.double_counted() == []


@pytest.mark.req("REQ-STATEVALUE-0001")
def test_no_fact_is_priced_by_nobody():
    """The rule's other half: a silent 0 is indistinguishable from a correct 0, so a gap needs an
    address rather than turning up as a mis-priced decision three tracks later."""
    assert sv.registry_gaps() == []


@pytest.mark.req("REQ-STATEVALUE-0001")
def test_the_registry_holds_exactly_the_six_families_the_plan_names():
    assert [f.name for f in sv.REGISTRY] == [
        "prize_race", "survival", "threat", "readiness", "hand", "development"]
    assert set(sv.FAMILIES) == {f.name for f in sv.REGISTRY}


@pytest.mark.req("REQ-STATEVALUE-0001")
def test_the_terminal_term_is_a_SEPARATE_registry_not_a_seventh_family():
    """`attack_ev` prices an ACTION and the six price a BOARD. Folding it in would make
    `state_value(model)` answerable only for models that arrived with an action attached."""
    assert [f.name for f in sv.TERMINAL_REGISTRY] == ["attack_ev"]
    assert "attack_ev" not in sv.FAMILIES
    assert set(sv.TERMINAL_FAMILIES) == {"attack_ev"}


@pytest.mark.req("REQ-STATEVALUE-0001")
def test_every_family_states_what_it_refuses_as_well_as_what_it_prices():
    """A family with no `does_not_read` can never contribute a named hole, so the coverage map would
    weaken silently as families were added."""
    for f in sv.REGISTRY + sv.TERMINAL_REGISTRY:
        assert f.reads, f.name
        assert f.does_not_read, f.name
        assert f.composition.strip(), f.name


@pytest.mark.req("REQ-STATEVALUE-0005")
def test_every_family_publishes_an_ACTIONABLE_blind_spot_list():
    """The composer reads `blind_spots()` as its checklist: a play no family reads prices at 0 delta,
    and at ordering time 0 means never explored. Length plus an em-dash is the actionable bar."""
    spots = sv.blind_spots()
    assert set(spots) == {f.name for f in sv.REGISTRY + sv.TERMINAL_REGISTRY}
    for name, entries in spots.items():
        assert entries, name
        for entry in entries:
            assert len(entry) > 60, (name, entry)
            assert "—" in entry, (name, entry)


# ── the unit basis ────────────────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-STATEVALUE-0002")
def test_worth_to_prizes_is_the_public_worth_currency_crossing():
    from common.card_worth import Worth

    assert sv.worth_to_prizes(Worth(0.0)) == 0.0
    assert sv.worth_to_prizes(Worth(30.0)) == pytest.approx(0.25)
    assert not hasattr(sv, "POC_WORTH_PRIZE_RATE")


@pytest.mark.req("REQ-STATEVALUE-0002")
def test_the_worth_scaffold_is_reconciled_against_its_anchor_not_pinned_as_a_literal():
    """ADR-0097 decision 1: the rate is authored but must be STATED against the incumbents. Asserting
    the arithmetic is what binds it — re-deriving `DEPLOY_BAND` fails here rather than silently."""
    from common.card_worth import Worth

    rate = sv.worth_to_prizes(Worth(1.0))
    assert rate == pytest.approx(
        currency.DEPLOY_BAND / currency.DEPLOY_WORTH_SCALE / currency.PRIZE_DAMAGE_RATE)
    per_worth_damage = rate * currency.PRIZE_DAMAGE_RATE
    assert per_worth_damage == pytest.approx(25.0 / 30.0, rel=1e-6)
    # Inside the catalogued spread (deploy 0.83 .. energy 6.67) — ADR-0078's own honesty condition.
    assert 25.0 / 30.0 <= per_worth_damage <= (160.0 / 3.0) / 8.0


@pytest.mark.req("REQ-STATEVALUE-0002")
def test_the_worth_scaffold_SETTLES_the_gust_seams_disagreement_by_REFERENT_not_by_averaging():
    """The two rates answer DIFFERENT questions, so neither moves: `GUST_TARGET_WORTH_RATE` converts a
    prize INTO Worth, `worth_to_prizes` a held card's Worth into prizes (ADR-0107)."""
    from common.card_worth import ROLE_TIER, Worth

    mine_worth_per_prize = 1.0 / sv.worth_to_prizes(Worth(1.0))
    gust_worth_per_prize = currency.GUST_TARGET_WORTH_RATE
    assert mine_worth_per_prize / gust_worth_per_prize > 40.0, (
        "the disagreement is real and RECORDED — if it ever closes, say so deliberately")

    # Within 20% of the composed shipped legs — the precision an authored POC scaffold can claim.
    composed = currency.PRIZE_DAMAGE_RATE / currency.ITEM_HOLD_WORTH_RATE
    assert abs(mine_worth_per_prize - composed) / composed <= 0.20

    # The reductio: on the gust seam's rate a held wincon outvalues the six prizes that END the match.
    wincon = ROLE_TIER["win_condition"]
    assert sv.worth_to_prizes(Worth(wincon)) == pytest.approx(0.25)
    assert wincon / gust_worth_per_prize > 6.0


@pytest.mark.req("REQ-STATEVALUE-0002")
def test_the_worth_scaffold_never_migrates_into_currency():
    """`currency.py`'s contract is DERIVED and never tuned; this constant is the opposite. The
    tempting migration is a second consumer arriving and someone hoisting it in beside the others."""
    assert not hasattr(currency, "POC_WORTH_PRIZE_RATE")
    assert not hasattr(currency, "WORTH_DAMAGE_RATE"), (
        "ADR-0080 ran the anchor gate and it FAILED — the constant is absent BY DESIGN, not pending")


@pytest.mark.req("REQ-STATEVALUE-0004")
def test_the_worth_leg_is_scale_invariant():
    """`hand` is LINEAR in the rate and every other family INDEPENDENT of it. A raw Worth magnitude
    elsewhere, or a raw damage magnitude inside `hand`, would otherwise be silent."""
    legs = dict(assignment_coverage=30.0, re_access=4.0, hand_worth=2.0)
    base = sv.hand(**legs, worth_prize_rate=0.01)
    assert sv.hand(**legs, worth_prize_rate=0.02) == pytest.approx(2.0 * base)
    assert sv.hand(**legs, worth_prize_rate=0.0) == 0.0

@pytest.mark.req("REQ-STATEVALUE-0002")
def test_the_readiness_scale_is_the_planners_own_weight_carried_at_the_same_band():
    """`_READINESS_W` cannot be imported from the planner (its leaf imports this module, so the edge
    would be a cycle), which is why the same-band anchor is asserted here instead of expressed."""
    from common.strategy.context import KO_SCORE
    from common.strategy.planner import _READINESS_ATTACK_W, _READINESS_SATURATED
    assert sv._READINESS_W == pytest.approx(
        _READINESS_ATTACK_W * currency.PRIZE_DAMAGE_RATE / KO_SCORE)
    # A straight carry-over, so it must stay EQUAL: two answers to one question is a silent divergence.
    assert sv._SATURATED == _READINESS_SATURATED


# ── the bands, and the terminal dominance they support ────────────────────────────────────────────


@pytest.mark.req("REQ-STATEVALUE-0006")
def test_a_predicted_loss_outscales_every_other_family_combined():
    """`ko-score-band`'s terminal half, and why `LOSS_PRIZES` is DERIVED: two families are
    prize-denominated and uncapped, so a transcribed −1.0 is out-scaled by two exposed ex bodies."""
    worst_survival = sv._MAX_BODIES * sv._MAX_PRIZE_VALUE
    worst_race = sv._PRIZES_START + sv._PROXIMITY_W
    assert sv.LOSS_PRIZES > worst_survival + worst_race + sv.POSITIONAL_MAX

    doomed = sv.survival([sv.ExposedBody(3.0, 1)], predicted_loss=True)
    merely_awful = sv.survival([sv.ExposedBody(3.0, 1)] * sv._MAX_BODIES)
    assert doomed < merely_awful

    # …and end-to-end on a PRIZE-lethal board (ADR-0064 Amendment B), which must inherit the dominance.
    lethal = _lucario_board(my_hp=60, bench=[_poke(RIOLU, hp=80, serial=2)], their_prizes=3)
    survivable = _lucario_board(my_hp=60, bench=[_poke(RIOLU, hp=80, serial=2)], their_prizes=4)
    assert sv.state_value(survivable) - sv.state_value(lethal) > sv.POSITIONAL_MAX


# ── the band's OTHER half, owed and unbuilt: the prize-denominated pair (Issue #369) ──────────────
# The two tests below are that gap as the assertions that pass the day it closes (strict-xfail).


@pytest.mark.req("REQ-STATEVALUE-0006")
@pytest.mark.xfail(strict=True, reason="OPEN GAP (Issue #369, split from #330), blocked on "
                                       "Issue #263's `attack_ev` "
                                       "wiring — see the test body for why it is xfail rather than "
                                       "a retune")
def test_a_line_that_banks_a_prize_outscores_one_that_declines_it():
    """A banked prize is never declined — `ko-score-band` for the prize-denominated pair. xfail rather
    than a fix: closing it means bounding `survival` per-play (Issue #369) or Issue #263's sum."""
    banked = (sv.prize_race(my_prizes_remaining=3, their_prizes_remaining=6)
              - sv.prize_race(my_prizes_remaining=4, their_prizes_remaining=6))
    assert banked >= 1.0, "the lead leg has lost its unit slope — this test is measuring the wrong thing"

    # What `survival` can charge against it, computed from the equation rather than transcribed.
    worst_survival_charge = -sv.survival([sv.ExposedBody(sv._MAX_PRIZE_VALUE, 1)] * sv._MAX_BODIES)

    assert banked > worst_survival_charge

    # …and in the shape a caller meets it: bank the prize and expose everything.
    takes_the_prize = (sv.prize_race(my_prizes_remaining=3, their_prizes_remaining=6)
                       + sv.survival([sv.ExposedBody(sv._MAX_PRIZE_VALUE, 1)] * sv._MAX_BODIES))
    declines_it = (sv.prize_race(my_prizes_remaining=4, their_prizes_remaining=6)
                   + sv.survival([]))
    assert takes_the_prize > declines_it


@pytest.mark.req("REQ-STATEVALUE-0006")
@pytest.mark.xfail(strict=True, reason="OPEN GAP (Issue #369, split from #330), blocked on "
                                       "Issue #263's `attack_ev` "
                                       "wiring — the end board is the only thing scored today and "
                                       "it prices a non-lethal attack at <= `_THREAT_CAP`")
def test_landing_an_attack_can_outprice_the_one_retreat_a_turn_allows():
    """Attack against retreat on an otherwise-equal board (Issue #330). Only `threat` can credit a
    play that banks no prize, at `_THREAT_CAP` 0.1, while one retreat moves uncapped `survival`."""
    # Offence on the end board for a non-KO attack: `threat` and nothing else, at their biggest body.
    best_offence_the_end_board_prices = sv.threat([sv._MAX_PRIZE_VALUE])
    assert best_offence_the_end_board_prices == pytest.approx(sv._THREAT_CAP), (
        "the ceiling moved — re-derive it before trusting the comparison")

    # Defence for the one retreat a turn allows; clock 1 -> 3 is the modest reading, not the generous.
    exposed = sv.survival([sv.ExposedBody(sv._MAX_PRIZE_VALUE, 1)])
    after_retreating = sv.survival([sv.ExposedBody(sv._MAX_PRIZE_VALUE, 3)])
    one_retreat_buys = after_retreating - exposed
    assert one_retreat_buys > 0.0, "the retreat is not moving `survival` — the comparison is void"

    assert best_offence_the_end_board_prices > one_retreat_buys


@pytest.mark.req("REQ-STATEVALUE-0006")
def test_an_achieved_WIN_outscales_every_board_the_families_can_express():
    """`ko-score-band`'s WIN half (Issue #362). `survival` is absent from the bound because it is
    non-positive by construction — swept below — so it can never push a board UP toward the band."""
    worst_race = sv._PRIZES_START + sv._PROXIMITY_W
    assert sv.WIN_PRIZES > worst_race + sv.POSITIONAL_MAX

    # The dropped summand, SWEPT rather than sampled: `survival` never returns a positive number.
    assert sv.survival([]) == 0.0
    for prize in (0.0, 1.0, 2.0, sv._MAX_PRIZE_VALUE):
        for clock in range(1, sv.HORIZON + 3):
            for count in range(1, sv._MAX_BODIES + 1):
                assert sv.survival([sv.ExposedBody(prize, clock)] * count) <= 0.0
    assert sv.survival([sv.ExposedBody(sv._MAX_PRIZE_VALUE, 1)] * sv._MAX_BODIES) < 0.0, (
        "non-vacuity: the sweep must contain a board the family actually charges for")

    # …and the literal, so a moved summand fails legibly rather than tautologically.
    assert sv.WIN_PRIZES == 10.9
    assert sv.WIN_PRIZES == pytest.approx(sv.LOSS_PRIZES - sv._MAX_BODIES * sv._MAX_PRIZE_VALUE), (
        "the two terminal constants are ONE construction differing by exactly the survival summand")


# ── case 1: prize lethality (ADR-0064 Amendment B, Issue #283) ────────────────────────────────────
# Every board below carries a NON-EMPTY Bench, so case 2 is structurally out of the picture.


#: Half the terminal charge — the epsilon that says a gap is the terminal term firing rather than
#: positional drift. Named because a bare `LOSS_PRIZES / 2.0` reads as arithmetic, not a THRESHOLD.
_TERMINAL_JUMP = sv.LOSS_PRIZES / 2.0


def _survival_of(me, opp) -> float:
    """The `survival` leg off a full `state_value` of the two player dicts. Read through `working`
    rather than by calling `sv.survival`, so the SCALAR is what every case below is testing."""
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
    """Identical body, identical clock, only THEIR prize count differs: a 3-prize Mega doomed at 60 HP
    ends the match at 3 remaining and is merely expensive at 6."""
    assert _survival_at(my_hp=60, their_prizes=3) < _survival_at(my_hp=60, their_prizes=6) - _TERMINAL_JUMP
    # The boundary is `>=`, not `>`: 3 prizes for a 3-prize body ends it, 4 does not.
    assert _survival_at(my_hp=60, their_prizes=4) == _survival_at(my_hp=60, their_prizes=6)


@pytest.mark.req("REQ-LOSSRUNG-0001")
def test_the_mega_lucario_prize_trade_shape_a_one_prize_body_is_not_a_loss():
    """`mega_lucario`'s interleave doctrine (its STRATEGY.md §4): a 1-prize body between Mega
    exposures. At 6 prizes the separation vanishes, so it is lethality and not a standing preference."""
    def _survival(active, their_prizes):
        return _survival_of(
            _player(active=active, bench=[_bench_riolu()], prize=4),
            _player(active=_poke(DRAGAPULT, hp=320, energies=[E_R, E_P], serial=9),
                    prize=their_prizes))

    mega, riolu = _poke(MEGA_LUC, hp=60), _poke(RIOLU, hp=60, serial=3)
    assert _survival(mega, 3) < _survival(riolu, 3) - _TERMINAL_JUMP
    assert _survival(mega, 6) - _survival(riolu, 6) > -_TERMINAL_JUMP


@pytest.mark.req("REQ-LOSSRUNG-0001")
def test_prize_lethality_is_BINARY_two_of_their_three_prizes_is_not_a_loss():
    """Issue #283's POC ruling and why `_predicted_loss` returns a BOOL: a 2-prize `ex` against 3
    remaining is worse than flat exposure but is not a loss. A graded form is the post-POC question."""
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
    """A predicted LOSS, not an exposure re-priced: at full HP the same Mega out-lives Phantom Dive."""
    assert _survival_at(my_hp=340, their_prizes=3) == _survival_at(my_hp=340, their_prizes=6)


@pytest.mark.req("REQ-LOSSRUNG-0001")
def test_prize_lethality_covers_a_BENCHED_body_through_the_snipe_rider():
    """§7 case 1 is about a BODY, not the Active Spot: their Jetting Blow's 50 bench rider reaches my
    chipped 3-prize Mega on the BENCH. The control is the same board one HP above the rider."""
    def _survival(bench_hp):
        return _survival_of(
            _player(active=_poke(RIOLU, hp=80),       # 1 prize — the ACTIVE leg cannot fire
                    bench=[_poke(MEGA_LUC, hp=bench_hp, serial=2)], prize=4),
            _player(active=_poke(MEGA_STARMIE, hp=330, energies=[WATER], serial=9), prize=3))

    assert _survival(50) < _survival(60) - _TERMINAL_JUMP


@pytest.mark.req("REQ-LOSSRUNG-0001")
def test_case_2_is_untouched_by_the_new_case_including_where_they_would_overlap():
    """The two cases share one function and a caller cannot see which fired. Three prize counts on one
    bench-empty doomed board: case 2 already charges `LOSS_PRIZES`, so all three read equal."""
    def _bench_empty(their_prizes):
        return _survival_of(_player(active=_poke(MEGA_LUC, hp=60), prize=4),
                            _player(active=_poke(DRAGAPULT, hp=320, energies=[E_R, E_P], serial=9),
                                    prize=their_prizes))

    assert _bench_empty(6) == _bench_empty(3) == _bench_empty(2)
    # positive control: the board IS carrying the case-2 charge.
    assert _survival_at(my_hp=60, their_prizes=6) > _bench_empty(6) + _TERMINAL_JUMP


@pytest.mark.req("REQ-STATEVALUE-0006")
def test_the_bench_slot_price_escalates_so_the_last_slot_is_the_expensive_one():
    """Issue #232's spare-body cliff, priced instead of ruled: the marginal RISES with each slot
    consumed, and the LAST slot costs a full maximum-relevance deploy."""
    prices = [sv._bench_slot_price(k) for k in range(sv._BENCH_MAX + 1)]
    marginals = [b - a for a, b in zip(prices, prices[1:])]
    assert marginals == sorted(marginals), marginals
    assert marginals[-1] == pytest.approx(sv._DEPLOY_PRIZE_BAND)
    assert marginals[-1] > marginals[0] * 8


@pytest.mark.req("REQ-STATEVALUE-0006")
def test_no_positional_family_saturates_on_a_realistic_body():
    """A saturated term has zero derivative, so under 1-ply differencing every play touching it prices
    at 0 delta and is never explored. Mega Lucario ex is the strongest body in the fixture set."""
    payoff = 270.0 / currency.PRIZE_DAMAGE_RATE
    low = sv.readiness([sv.ReadyBody(payoff, 0.4, 1.0)])
    high = sv.readiness([sv.ReadyBody(payoff, 0.8, 1.0)])
    assert high > low, "readiness saturated: odds no longer move it"
    assert high < sv._READINESS_BODY_CAP, "the runaway guard is biting in normal play"


# ── the terminal-action term ──────────────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_attack_ev_prices_a_knockout_at_the_targets_prize_value():
    """The KO band: Mega Brave's 270 does not fell a 320 HP Dragapult ex; 340 does."""
    ko = sv.attack_ev(damage=340.0, target_hp=320.0, target_prizes=2.0)
    assert ko.knockout == pytest.approx(2.0) and ko.chip == 0.0
    chip = sv.attack_ev(damage=270.0, target_hp=320.0, target_prizes=2.0)
    assert chip.knockout == 0.0 and chip.chip == pytest.approx(2.0 * 270.0 / 320.0)


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_attack_ev_is_an_EXPECTATION_so_a_coin_attack_needs_no_archetype_branch():
    """Attack value is a random variable and printed fixed damage the degenerate certain case, which
    is what lets a coin attack and a copy attack plug in as damage MODELS with no branch."""
    certain = sv.attack_ev(damage=340.0, target_hp=320.0, target_prizes=2.0)
    coin = sv.attack_ev(damage=340.0, target_hp=320.0, target_prizes=2.0, ko_probability=0.5)
    assert coin.knockout == pytest.approx(certain.knockout / 2.0)


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_a_rider_can_beat_raw_damage_and_a_self_lock_can_lose_to_a_recycle():
    """Both trade-offs must be REPRESENTABLE at the term or the composer cannot express them: Aura Jab
    130 plus its recycle against Mega Brave 270 minus its lock, neither of them a Knock Out here."""
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


# ── the terminal-action term's EXTRACTOR (POC-T4/3, Issue #384) ───────────────────────────────────
# `attack_ev` takes seven plain floats; `attack_ev_legs` is the model->kwargs bridge that makes them.

def _starmie_rider_board(*, bench_hp=50):
    """MY Mega Starmie ex against their Dragapult ex with a 3-prize body on THEIR Bench: Jetting Blow
    120 plus a 50 rider against Nebula Beam 210 and no rider, neither of which knocks out 320 HP."""
    return _model(
        _player(active=_poke(MEGA_STARMIE, hp=330, energies=[E_W, E_W, E_W]), prize=4),
        _player(active=_poke(DRAGAPULT, hp=320, energies=[E_R, E_P], serial=9),
                bench=[_poke(MEGA_LUC, hp=bench_hp, serial=10)], prize=4),
        energy_attached=True)


def _dive_board(*, bench):
    """MY Dragapult ex against their Mega Lucario ex. Phantom Dive's 6 counters are a SHARED,
    distributable 60 budget; Jet Headbutt 70 is the rider-free alternative on the same body."""
    return _model(
        _player(active=_poke(DRAGAPULT, hp=320, energies=[E_R, E_P]), prize=4),
        _player(active=_poke(MEGA_LUC, hp=340, serial=9), bench=list(bench), prize=4),
        energy_attached=True)


def _eevee_board(*, their_hp):
    """MY Eevee against their Dragapult ex — the COIN fixture. Eevee is {C} and Dragapult prints
    neither Weakness nor Resistance, so the record's own 20/40 bounds reach the policy unmodified."""
    return _model(
        _player(active=_poke(EEVEE, hp=50, energies=[E_F, E_F, E_F]), prize=4),
        _player(active=_poke(DRAGAPULT, hp=their_hp, serial=9), prize=4),
        energy_attached=True)


def _leg(model, attack_id):
    """The one leg for ``attack_id``, or None."""
    return next((l for l in sv.attack_ev_legs(model) if l.attack_id == attack_id), None)


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_attack_ev_legs_produces_exactly_attack_evs_kwargs():
    """What comes out SPLATS into the term, asserted against the signature rather than a copied key
    list — so a kwarg added to `attack_ev` fails here instead of silently defaulting."""
    import inspect
    expected = set(inspect.signature(sv.attack_ev).parameters)
    legs = sv.attack_ev_legs(_lucario_board(my_energies=[E_F, E_F]))
    assert legs, "no legs on a board with an affordable attack — the extractor is inert"
    for leg in legs:
        assert set(leg.kwargs) == expected
        sv.attack_ev(**leg.kwargs)          # splats without a TypeError, which is the whole point


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_attack_ev_legs_covers_the_affordable_attacks_and_only_those():
    """Affordability is the shipped Attach Budget's answer (`threat.blind_to` forbids a raw
    energy-count second opinion), so an attack off the menu produces no leg."""
    both = {l.attack_id for l in sv.attack_ev_legs(_lucario_board(my_energies=[E_F, E_F]))}
    assert both == {AURA_JAB, MEGA_BRAVE}
    # One {F} with the turn's attach already spent: Aura Jab {F} is payable, Mega Brave {F}{F} is not.
    one = {l.attack_id for l in sv.attack_ev_legs(
        _model(_player(active=_poke(MEGA_LUC, hp=340, energies=[E_F]), prize=4),
               _player(active=_poke(DRAGAPULT, hp=320, serial=9), prize=4),
               energy_attached=True))}
    assert one == {AURA_JAB}


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_attack_ev_legs_is_empty_when_there_is_nothing_to_attack_with():
    """Fail-closed at both ends: no Active, and an Active the rules forbid an attack to. Turn 1 for
    the starting player is `attack_blocked`'s question rather than a cost."""
    assert sv.attack_ev_legs(
        _model(_player(prize=4), _player(active=_poke(DRAGAPULT, hp=320, serial=9), prize=4))) == ()
    assert sv.attack_ev_legs(
        _model(_player(active=_poke(MEGA_LUC, hp=340, energies=[E_F, E_F]), prize=4),
               _player(active=_poke(DRAGAPULT, hp=320, serial=9), prize=4), turn=1)) == ()


# ── acceptance fixture 1 — the rider beats raw damage ─────────────────────────────────────────────

@pytest.mark.req("REQ-STATEVALUE-0007")
def test_a_snipe_rider_outprices_the_bigger_straight_hit_on_a_real_board():
    """Issue #263 acceptance 1, end to end through the extractor. Nebula Beam is 90 damage bigger
    (0.5625 prizes of chip) while Jetting Blow's 50 rider finishes a benched 3-prize Mega Lucario ex."""
    m = _starmie_rider_board()
    jetting, nebula = _leg(m, JETTING_BLOW), _leg(m, NEBULA_BEAM)
    assert jetting is not None and nebula is not None
    assert jetting.kwargs["rider_value"] == pytest.approx(3.0)
    assert nebula.kwargs["rider_value"] == 0.0
    assert nebula.kwargs["damage"] > jetting.kwargs["damage"]          # the straight hit IS bigger
    assert sv.attack_ev(**jetting.kwargs).total > sv.attack_ev(**nebula.kwargs).total


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_a_snipe_rider_that_finishes_nothing_prices_as_a_FRACTION_not_a_prize():
    """Out of reach the rider is worth the fraction of the body it removes — the SAME band the core
    leg uses, ``prize_value x min(1, dmg/hp)``."""
    m = _starmie_rider_board(bench_hp=250)
    jetting = _leg(m, JETTING_BLOW)
    assert jetting.kwargs["rider_value"] == pytest.approx(3.0 * 50.0 / 250.0)
    assert jetting.kwargs["rider_value"] < 3.0


# ── acceptance fixture 2 — the bench-counter allocation ───────────────────────────────────────────

@pytest.mark.req("REQ-STATEVALUE-0007")
def test_a_bench_spread_is_priced_by_WHERE_the_counters_land():
    """`benchSpread` is a SHARED budget across their Bench, so which bodies it finishes is a knapsack
    (`CombatMath.spread_ko_prizes`): 3 prizes at 60 HP, 2 once that body has ten more."""
    reachable = _leg(_dive_board(bench=[_poke(RIOLU, hp=40, serial=10),
                                        _poke(STARYU, hp=20, serial=11),
                                        _poke(MEGA_LUC, hp=60, serial=12)]), PHANTOM_DIVE)
    assert reachable.kwargs["rider_value"] == pytest.approx(3.0)
    walled = _leg(_dive_board(bench=[_poke(RIOLU, hp=40, serial=10),
                                     _poke(STARYU, hp=20, serial=11),
                                     _poke(MEGA_LUC, hp=70, serial=12)]), PHANTOM_DIVE)
    assert walled.kwargs["rider_value"] == pytest.approx(2.0)
    # …and the rider-free alternative on the same body reads 0 on both boards.
    assert _leg(_dive_board(bench=[_poke(MEGA_LUC, hp=60, serial=12)]),
                JET_HEADBUTT).kwargs["rider_value"] == 0.0


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_a_bench_immune_body_is_no_rider_target_at_all():
    """`docs/rules.md` §11 — a Tera body takes NO damage from attacks while BENCHED, so a spread that
    could otherwise finish it credits nothing. A phantom bench prize is what locks a false lethal."""
    immune = _leg(_dive_board(bench=[_poke(DRAGAPULT, hp=30, serial=12)]), PHANTOM_DIVE)
    assert immune.kwargs["rider_value"] == 0.0


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_the_rider_converts_where_threat_only_stands_and_neither_pays_twice():
    """`threat` prices the STANDING position and never the CONVERSION, which is this term's. Walked at
    the registries as well as on a board, so the rule is executable rather than argued."""
    assert sv.double_counted() == []
    assert set(sv.TERMINAL_FAMILIES["attack_ev"].reads).isdisjoint(sv.FAMILIES["threat"].reads)
    assert "opponent_target_value" in sv.TERMINAL_FAMILIES["attack_ev"].does_not_read
    # The board scalar is a function of the board alone, not of the attack being priced.
    m = _dive_board(bench=[_poke(MEGA_LUC, hp=60, serial=12)])
    assert sv.state_value(m) == sv.state_value(m)


# ── acceptance fixture 3 — the economy rider against the next-turn lock ───────────────────────────

@pytest.mark.req("REQ-STATEVALUE-0007")
def test_a_recycle_rider_and_a_next_turn_lock_BOTH_appear_in_the_two_EVs():
    """Issue #263 acceptance 3: BOTH legs must be VISIBLE, not merely that the right attack wins. The
    lock forfeits the gap between the best lock-free follow-up (270) and the one it leaves (130)."""
    m = _model(_player(active=_poke(MEGA_LUC, hp=340, energies=[E_F, E_F]),
                       bench=[_poke(RIOLU, hp=80, serial=2)], discard=[E_F] * 4, prize=4),
               _player(active=_poke(DRAGAPULT, hp=320, energies=[E_R, E_P], serial=9), prize=4),
               energy_attached=True)
    jab, brave = _leg(m, AURA_JAB), _leg(m, MEGA_BRAVE)
    # Aura Jab: the economy rider APPEARS, and it carries no clock cost.
    assert jab.kwargs["economy_value"] == pytest.approx(2.0 * (160 / 3) / 100.0)
    assert jab.kwargs["next_turn_cost"] == 0.0
    # Mega Brave: the clock cost APPEARS, and it carries no economy.
    assert brave.kwargs["economy_value"] == 0.0
    assert brave.kwargs["next_turn_cost"] == pytest.approx(0.5 * (270.0 - 130.0) / 100.0)
    # ADR-0061's ruling through the composed term: fuelled Aura Jab beats bare Mega Brave.
    assert brave.kwargs["damage"] > jab.kwargs["damage"]
    assert sv.attack_ev(**jab.kwargs).total > sv.attack_ev(**brave.kwargs).total


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_the_recycle_rider_is_bounded_by_the_fuel_and_by_the_need():
    """The three closed-form bounds, each shown to BIND — Energy nobody can pay with is not
    development (ADR-0061)."""
    def jab_economy(*, discard, bench):
        m = _model(_player(active=_poke(MEGA_LUC, hp=340, energies=[E_F, E_F]),
                           bench=list(bench), discard=list(discard), prize=4),
                   _player(active=_poke(DRAGAPULT, hp=320, serial=9), prize=4),
                   energy_attached=True)
        return _leg(m, AURA_JAB).kwargs["economy_value"]

    riolu = [_poke(RIOLU, hp=80, serial=2)]
    rate = (160 / 3) / 100.0
    assert jab_economy(discard=[E_F] * 4, bench=riolu) == pytest.approx(2 * rate)   # NEED binds
    assert jab_economy(discard=[E_F], bench=riolu) == pytest.approx(1 * rate)       # FUEL binds
    assert jab_economy(discard=[E_F] * 4, bench=()) == 0.0            # no recipient in scope at all


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_a_lone_affordable_attack_is_never_charged_for_its_own_lock():
    """A lock forfeits the gap to the best LOCK-FREE pick, and with a single attack on the menu there
    is no such pick — so the gap would be the attack's own damage counted against it."""
    lone = _model(_player(active=_poke(RIOLU, hp=80, energies=[E_F]), prize=4),
                  _player(active=_poke(DRAGAPULT, hp=320, serial=9), prize=4),
                  energy_attached=True)
    stab = _leg(lone, ACCELERATING_STAB)
    assert stab is not None and stab.kwargs["next_turn_cost"] == 0.0
    two = _model(_player(active=_poke(MEGA_LUC, hp=340, energies=[E_F, E_F]), prize=4),
                 _player(active=_poke(DRAGAPULT, hp=320, serial=9), prize=4),
                 energy_attached=True)
    assert _leg(two, MEGA_BRAVE).kwargs["next_turn_cost"] == pytest.approx(0.5 * 140.0 / 100.0)


# ── the coin bound policy — DECLARED, because the record cannot recover the distribution ──────────

@pytest.mark.req("REQ-STATEVALUE-0007")
def test_a_coin_attacks_damage_is_the_MEAN_of_its_two_bounds():
    """The mean of the model's floor and ceiling is ADR-0039's shipped ranking convention. A
    DETERMINISTIC attack's bounds collapse, so the same expression returns its printed damage."""
    coin = _leg(_eevee_board(their_hp=320), QUICK_ATTACK)
    assert coin.kwargs["damage"] == pytest.approx(30.0)
    flat = _leg(_lucario_board(my_energies=[E_F, E_F]), MEGA_BRAVE)
    assert flat.kwargs["damage"] == pytest.approx(270.0)


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_the_ko_probability_is_1_when_the_FLOOR_already_kills():
    """Whatever the coin does the body falls, so a certain KO is not taxed for being printed on one."""
    leg = _leg(_eevee_board(their_hp=20), QUICK_ATTACK)
    assert leg.kwargs["ko_probability"] == 1.0
    assert sv.attack_ev(**leg.kwargs).knockout == pytest.approx(2.0)


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_the_ko_probability_is_the_DECLARED_bound_when_only_the_mean_kills():
    """`AttackStat` carries `damageMin` / `damageMax` and NOTHING about the distribution between them,
    so the equiprobable two-branch reading is a POLICY — declared in `attack_ev`'s `blind_to`."""
    leg = _leg(_eevee_board(their_hp=30), QUICK_ATTACK)
    assert leg.kwargs["ko_probability"] == sv._COIN_KO_BOUND == 0.5
    assert sv.attack_ev(**leg.kwargs).knockout == pytest.approx(1.0)


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_a_ceiling_only_knockout_UNDER_reads_and_that_is_the_declared_direction():
    """At 35 HP the ceiling would finish the body and the mean does not, so the Knock Out is never
    credited at all. That UNDER-read is the fail-closed direction for an offensive estimate."""
    leg = _leg(_eevee_board(their_hp=35), QUICK_ATTACK)
    ev = sv.attack_ev(**leg.kwargs)
    assert ev.knockout == 0.0
    assert ev.chip == pytest.approx(2.0 * 30.0 / 35.0)


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_the_coin_policy_and_the_recoil_gap_are_both_in_the_blind_spot_checklist():
    """A knowingly-uncovered dimension that is NOT written down is invisible to the checklist that
    exists to catch it. `AttackStat.recoil` is on no board and in no kwarg, so it prices exactly 0."""
    entries = " ".join(sv.blind_spots()["attack_ev"]).lower()
    assert "coin" in entries and "recoil" in entries
    assert sv.registry_gaps() == []


# ── the frozen shape asymmetry, and the inertness this issue must not break ───────────────────────

@pytest.mark.req("REQ-STATEVALUE-0007")
def test_a_consumer_must_read_total_and_never_the_working_dicts_sum():
    """`AttackEV.working()` is FROZEN in a shape that does not add up: it omits `total` and emits
    `next_turn_cost` POSITIVE while `total` SUBTRACTS it, so the dict sums to ``total + 2 x cost``."""
    m = _model(_player(active=_poke(MEGA_LUC, hp=340, energies=[E_F, E_F]),
                       bench=[_poke(RIOLU, hp=80, serial=2)], discard=[E_F] * 4, prize=4),
               _player(active=_poke(DRAGAPULT, hp=320, energies=[E_R, E_P], serial=9), prize=4),
               energy_attached=True)
    ev = sv.attack_ev(**_leg(m, MEGA_BRAVE).kwargs)
    assert ev.next_turn_cost > 0
    assert "total" not in ev.working()
    assert sum(ev.working().values()) == pytest.approx(ev.total + 2 * ev.next_turn_cost)
    assert sv.attack_ev_legs.__doc__ and "working()" in sv.attack_ev_legs.__doc__


@pytest.mark.req("REQ-STATEVALUE-0007")
def test_attack_ev_is_called_by_the_COMPOSER_and_by_nothing_else():
    """The terminal leg has EXACTLY ONE consumer; a second would be a second opinion on one prize.
    Asserted by (file, enclosing function): `terminal_ev` and `continuation_ev` (ADR-0129)."""
    import ast
    from pathlib import Path

    def _called(tree, name):
        """``[(enclosing def name or <module>, lineno)]`` for every CALL of ``name``, resolved by
        descending the def tree rather than by line-number arithmetic."""
        out = []

        def walk(node, where):
            for child in ast.iter_child_nodes(node):
                inner = (child.name if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                         else where)
                if isinstance(child, ast.Call) and (getattr(child.func, "id", None) == name
                                                    or getattr(child.func, "attr", None) == name):
                    out.append((where, child.lineno))
                walk(child, inner)

        walk(tree, "<module>")
        return out

    root = Path(__file__).resolve().parents[2]
    hits, controls = [], []
    for base in ("src", "tools"):
        for path in sorted((root / base).rglob("*.py")):
            rel = path.relative_to(root).as_posix()
            if rel.startswith("src/cg/"):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            hits += [(rel, fn, n) for fn, n in _called(tree, "attack_ev")]
            controls += [(rel, fn, n) for fn, n in _called(tree, "survival")]
    assert controls, "positive control silent: the scan is broken, not the tree"
    assert sorted({(f, fn) for f, fn, _n in hits}) == [
        ("src/common/composer.py", "continuation_ev"),
        ("src/common/composer.py", "terminal_ev"),
    ], (f"`attack_ev` must have exactly ONE consumer — the composer's terminal sum, read at its two "
        f"mutually-exclusive seams (`terminal_ev` for a line that ENDED, `continuation_ev` for one "
        f"that was CUT). Found: {sorted(hits)}")


# ── the scalar over a real StateModel ─────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-STATEVALUE-0004")
def test_the_working_breakdown_sums_to_the_returned_scalar():
    """The breakdown must BE the decomposition and not a parallel narrative about it — one that
    disagreed with the number it explains would send wave-3 triage after the wrong term."""
    model = _lucario_board(my_energies=[E_F], bench=[_poke(RIOLU, hp=80, serial=2)])
    working: dict = {}
    total = sv.state_value(model, working=working)
    assert set(working) == set(sv.FAMILIES)
    assert sum(working.values()) == pytest.approx(total)


@pytest.mark.req("REQ-STATEVALUE-0004")
def test_passing_no_working_dict_returns_the_same_number():
    """The out-parameter is a diagnostic, never a mode."""
    model = _lucario_board(my_energies=[E_F])
    assert sv.state_value(model) == pytest.approx(sv.state_value(model, working={}))


@pytest.mark.req("REQ-STATEVALUE-0008")
def test_the_scalar_is_PROVENANCE_AGNOSTIC_over_two_models_of_one_board():
    """MODELLED and ENGINE-RESOLVED both yield a model and `state_value` may not tell them apart, so
    two INDEPENDENTLY CONSTRUCTED models of one board must score identically."""
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
    """Bit-identical, not approximately equal: float addition is not associative, so a varying term
    order moves the last bits, and a selection key built on wobbling last bits is not a fix."""
    model = _lucario_board(my_energies=[E_F], bench=[_poke(RIOLU, hp=80, serial=2)],
                           hand=[MEGA_LUC, E_F])
    values = [sv.state_value(model) for _ in range(32)]
    assert len(set(values)) == 1
    # Bit-identical, asserted through the repr so a difference below `==`'s notice would still show.
    assert len({repr(v) for v in values}) == 1

    # …and a FRESHLY built model agrees bit-for-bit, so the answer is not the memo's fill order.
    fresh = _lucario_board(my_energies=[E_F], bench=[_poke(RIOLU, hp=80, serial=2)],
                           hand=[MEGA_LUC, E_F])
    assert repr(sv.state_value(fresh)) == repr(values[0])


@pytest.mark.req("REQ-STATEVALUE-0010")
def test_the_term_iteration_order_is_FIXED_not_a_set_or_a_dict_scan():
    """A term set assembled by iterating a `set` is stable within one interpreter run and can reorder
    across runs — precisely the failure a same-process repeat test cannot see."""
    model = _lucario_board(my_energies=[E_F])
    working: dict = {}
    sv.state_value(model, working=working)
    assert list(working) == [f.name for f in sv.REGISTRY]


# ── MID-TURN MONOTONICITY — the class Issue #263's ordering ruling requires ───────────────────────
# Each case perturbs ONE beneficial fact. The failure caught is a term that assumed a completed turn.


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_an_attach_toward_an_attack_cost_raises_readiness_MID_TURN():
    """The real transition rather than two boards: BEFORE still has the manual attach available. A
    half-built attacker scores PARTIAL — 0 prunes the attach, full makes the second Energy free."""
    before, after = {}, {}
    sv.state_value(_lucario_board(my_energies=[E_F]), working=before)
    sv.state_value(_lucario_board(my_energies=[E_F, E_F], energy_attached=True), working=after)
    assert after["readiness"] > before["readiness"]
    assert 0.0 < before["readiness"] < after["readiness"], "a half-built attacker scored 0 or full"


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_readiness_survives_the_turns_one_manual_attach_being_spent():
    """`readiness_p` is a THIS-TURN probability that fails closed at 0.0, so once the attach is spent
    the forward clock is what keeps the term alive rather than flat — and a flat term prunes."""
    spent, richer = {}, {}
    sv.state_value(_lucario_board(my_energies=[E_F], energy_attached=True), working=spent)
    sv.state_value(_lucario_board(my_energies=[E_F, E_F], energy_attached=True), working=richer)
    assert spent["readiness"] > 0.0, "the spent attach flattened readiness to zero"
    assert richer["readiness"] > spent["readiness"]


# ── Issue #286 — readiness's FORWARD leg must not count Energy that evaporates ────────────────────


def _expiring_board(cid, *, energies, energy_cards, hp, benched=False, turn=5):
    """MY body holding a chosen Energy set, the turn's attach SPENT and my hand empty, so `readiness_p`
    answers about what is ON it. ``benched`` and ``turn`` are the two legality facts (Issue #351)."""
    body = _poke(cid, hp=hp, energies=energies, energy_cards=energy_cards)
    mine = (_player(active=_poke(STARYU, hp=70, serial=4), bench=[body], prize=4) if benched
            else _player(active=body, prize=4))
    return _model(
        mine,
        _player(active=_poke(DRAGAPULT, hp=320, energies=[E_R, E_P], serial=9), prize=4),
        energy_attached=True, turn=turn)


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_forward_clock_no_longer_counts_an_energy_that_will_be_DISCARDED():
    """Gouging Fire ex is a Basic, so one Ignition provides ``{C}``: it fills Blaze Blitz's colourless
    slot and neither ``{R}``, the now-leg is an honest 0, and the family rides the forward clock."""
    loan, real = {}, {}
    sv.state_value(_expiring_board(GOUGING_FIRE, energies=[COLORLESS], energy_cards=[IGNITION],
                                   hp=230), working=loan)
    sv.state_value(_expiring_board(GOUGING_FIRE, energies=[E_R], energy_cards=[E_R], hp=230),
                   working=real)
    board = _expiring_board(GOUGING_FIRE, energies=[COLORLESS], energy_cards=[IGNITION], hp=230)
    body = board.mine.active
    assert board.mine.readiness_p(body, board.mine.attack_payoff(body).attack_id) == 0.0, "the now-leg must be the 0 here"
    assert board.mine.turns_to_afford(body) == 2                      # the incumbent, unmoved
    assert board.mine.turns_to_afford(body, exclude_expiring=True) == 3
    assert loan["readiness"] < real["readiness"], (
        "an evaporating Energy still prices as a permanent one")
    # …and the drop is the halve() step the forward leg is graded by, not some other number.
    assert loan["readiness"] == pytest.approx(real["readiness"] / 2.0)


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_going_first_shape_an_IGNITION_onto_a_BASIC_now_buys_nothing_forward():
    """On `mega_starmie`'s real cards: an Ignition on a Basic Staryu provides one ``{C}``, which pays
    no part of Water Gun ``{W}``. The Ignition board must land exactly on the BARE-Staryu value."""
    ign, water, bare = {}, {}, {}
    sv.state_value(_expiring_board(STARYU, energies=[COLORLESS], energy_cards=[IGNITION], hp=70),
                   working=ign)
    sv.state_value(_expiring_board(STARYU, energies=[E_W], energy_cards=[E_W], hp=70), working=water)
    sv.state_value(_expiring_board(STARYU, energies=[], energy_cards=[], hp=70), working=bare)
    board = _expiring_board(STARYU, energies=[COLORLESS], energy_cards=[IGNITION], hp=70)
    body = board.mine.active
    assert board.mine.readiness_p(body, board.mine.attack_payoff(body).attack_id) == 0.0, (
        "a colourless unit must not read as paying Water Gun's {W}")
    assert board.mine.turns_to_afford(body) == 2                       # the incumbent, unmoved
    assert board.mine.turns_to_afford(body, exclude_expiring=True) == 3
    assert ign["readiness"] < water["readiness"]
    # The NEW part: before this change the Ignition board sat strictly between the two.
    assert ign["readiness"] == pytest.approx(bare["readiness"])
    assert bare["readiness"] < water["readiness"]


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_NOW_leg_keeps_the_evaporating_energy_and_therefore_MASKS_the_fix():
    """`_readiness_odds` is ``max(now, halve(arm))`` and both legs read the same attached Energy, so
    where it fully arms an ACTIVE body the mask is CORRECT — 1.0 is a true statement about it."""
    board = _expiring_board(MEGA_STARMIE, energies=[COLORLESS] * 3, energy_cards=[IGNITION], hp=330)
    body = board.mine.active
    assert board.mine.readiness_p(body, board.mine.attack_payoff(body).attack_id) == 1.0
    assert board.mine.turns_to_afford(body) == 0                       # armed, by a loan
    assert board.mine.turns_to_afford(body, exclude_expiring=True) == 3    # the seam DOES move
    loan, real = {}, {}
    sv.state_value(board, working=loan)
    sv.state_value(_expiring_board(MEGA_STARMIE, energies=[E_W, E_W, E_W],
                                   energy_cards=[E_W, E_W, E_W], hp=330), working=real)
    assert loan["readiness"] == real["readiness"], (
        "the now-leg no longer masks the forward leg — re-read the packet line, this is the unlock")


# ── Issue #351 — the NOW leg may not credit a body the rules will not let attack ──────────────────
# `readiness_p` has NO legality leg: nothing on its path reads the AREA, the turn, or the first-player ban.


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_a_BENCHED_body_is_not_READY_to_attack_however_much_energy_it_holds():
    """A benched Pokémon cannot attack, so the now-leg's claim is false for it whatever its Energy
    says. The SAME body in both spots, so the only difference is the area; the Active is control."""
    benched = _expiring_board(MEGA_STARMIE, energies=[COLORLESS] * 3, energy_cards=[IGNITION],
                              hp=330, benched=True)
    body = benched.mine.bench[0]
    aid = benched.mine.attack_payoff(body).attack_id
    assert body.is_active is False
    assert benched.mine.attack_blocked is False, "turn 5 — the RULES allow an attack; area is the fact"

    # The incumbent oracle is UNTOUCHED and still says 1.0 — the fix is a gate in the caller.
    assert benched.mine.readiness_p(body, aid) == 1.0

    # …and the composed answer rides the forward clock, which already drops the evaporating Energy.
    assert sv._readiness_odds(benched, body, aid) < 1.0

    # The ACTIVE control: same body, same Energy, in the spot where 1.0 is true.
    active = _expiring_board(MEGA_STARMIE, energies=[COLORLESS] * 3, energy_cards=[IGNITION], hp=330)
    a_body = active.mine.active
    assert sv._readiness_odds(active, a_body,
                              active.mine.attack_payoff(a_body).attack_id) == 1.0


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_now_leg_is_zero_when_the_RULES_forbid_an_attack_at_all():
    """The first player on turn 1. `MySide.attack_blocked` carries all three rule facts — Asleep,
    Paralyzed, ``turn <= 1`` — and this body is ACTIVE, so it is independent of the area gate."""
    board = _expiring_board(MEGA_STARMIE, energies=[COLORLESS] * 3, energy_cards=[IGNITION], hp=330,
                            turn=1)
    body = board.mine.active
    aid = board.mine.attack_payoff(body).attack_id
    assert body.is_active is True, "the AREA is fine here — the RULES are what forbid the attack"
    assert board.mine.attack_blocked is True

    assert board.mine.readiness_p(body, aid) == 1.0        # the oracle, still legality-blind
    assert sv._readiness_odds(board, body, aid) < 1.0      # the composed answer, no longer

    # Non-vacuity: the SAME board on a turn the rules allow reads the full 1.0.
    allowed = _expiring_board(MEGA_STARMIE, energies=[COLORLESS] * 3, energy_cards=[IGNITION],
                              hp=330, turn=5)
    a_body = allowed.mine.active
    assert sv._readiness_odds(allowed, a_body,
                              allowed.mine.attack_payoff(a_body).attack_id) == 1.0


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_legality_gate_UNMASKS_issue_286s_forward_leg_on_a_benched_body():
    """On a body that cannot attack the now-leg is gone, so `exclude_expiring` finally reaches the
    family. The Basic-Energy control makes it a statement about evaporation, not about the gate."""
    ign, water, bare = {}, {}, {}
    sv.state_value(_expiring_board(MEGA_STARMIE, energies=[COLORLESS] * 3, energy_cards=[IGNITION],
                                   hp=330, benched=True), working=ign)
    sv.state_value(_expiring_board(MEGA_STARMIE, energies=[E_W] * 3, energy_cards=[E_W] * 3,
                                   hp=330, benched=True), working=water)
    sv.state_value(_expiring_board(MEGA_STARMIE, energies=[], energy_cards=[], hp=330,
                                   benched=True), working=bare)
    assert ign["readiness"] == pytest.approx(bare["readiness"]), (
        "an evaporating Energy still buys forward readiness on a body that cannot cash it")
    assert bare["readiness"] < water["readiness"], (
        "non-vacuity: real Energy must still buy readiness, or the equality above is trivial")


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_legality_gate_fails_CLOSED_on_a_board_that_states_no_turn():
    """`attack_blocked` reads `self.turn <= 1` over `int(turn or 0)`, so a board stating no turn reads
    0 and is blocked — the SAFE direction. Both spellings of absent are asserted."""
    for missing in (None, 0):
        board = _expiring_board(MEGA_STARMIE, energies=[COLORLESS] * 3, energy_cards=[IGNITION],
                                hp=330, turn=missing)
        body = board.mine.active
        assert board.mine.attack_blocked is True, f"turn={missing!r} must fail CLOSED"
        assert sv._may_attack_now(board, body) is False
        assert sv._readiness_odds(board, body, board.mine.attack_payoff(body).attack_id) < 1.0


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_gate_leaves_readiness_p_ITSELF_byte_identical():
    """`readiness_p` is shared, and `promote_retreat_value` (ADR-0073) needs it area-BLIND — which is
    the argument for gating in `_readiness_odds` rather than in the oracle."""
    for board, benched, turn in ((_expiring_board(MEGA_STARMIE, energies=[COLORLESS] * 3,
                                                  energy_cards=[IGNITION], hp=330), False, 5),
                                 (_expiring_board(MEGA_STARMIE, energies=[COLORLESS] * 3,
                                                  energy_cards=[IGNITION], hp=330,
                                                  benched=True), True, 5),
                                 (_expiring_board(MEGA_STARMIE, energies=[COLORLESS] * 3,
                                                  energy_cards=[IGNITION], hp=330,
                                                  turn=1), False, 1),
                                 (_expiring_board(MEGA_STARMIE, energies=[E_W] * 3,
                                                  energy_cards=[E_W] * 3, hp=330,
                                                  benched=True), True, 5)):
        body = board.mine.bench[0] if benched else board.mine.active
        assert board.mine.readiness_p(body, board.mine.attack_payoff(body).attack_id) == 1.0, (
            f"the shared oracle moved (benched={benched}, turn={turn}) — the gate belongs in the "
            f"caller, not in `readiness_p`")


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_a_basic_energy_is_never_stripped_from_the_forward_clock():
    """Nothing about a Basic Energy expires, so both clocks must agree — including on the boards that
    carry no ``energyCards`` key at all, where the strip must make no claim."""
    for board in (_expiring_board(GOUGING_FIRE, energies=[E_R], energy_cards=[E_R], hp=230),
                  _expiring_board(MEGA_STARMIE, energies=[E_W, E_W], energy_cards=[E_W, E_W],
                                  hp=330),
                  _lucario_board(my_energies=[E_F], energy_attached=True)):
        body = board.mine.active
        assert (board.mine.turns_to_afford(body)
                == board.mine.turns_to_afford(body, exclude_expiring=True))


# ── Issue #332 — readiness must not fund a body the opponent removes next turn ────────────────────
# On the corpus frame `readiness` was the SOLE decider and it funded a doomed Active over its successor.

#: A deck the Starmie line can fund from, so `turns_to_afford`'s deck-fetch leg has {W} to find. The
#: default `DECK` holds only {F}, which reads "unknown" for a reason unrelated to the fact tested.
STARMIE_DECK = [E_W] * 6 + [STARYU] * 3 + [MEGA_STARMIE] * 3


def _successor_board(*, active_energies=(), bench_energies=(), active_damage=0):
    """MY Mega Starmie ex Active with the Staryu that becomes its successor benched behind it, the
    turn's attach SPENT. ``active_damage`` is the ONE fact the doomed and safe boards differ by."""
    return _model(
        _player(active=_poke(MEGA_STARMIE, hp=330, damage=active_damage,
                             energies=list(active_energies)),
                bench=[_poke(STARYU, hp=70, energies=list(bench_energies), serial=2)], prize=4),
        _player(active=_poke(DRAGAPULT, hp=320, energies=[E_R, E_P], serial=9), prize=4),
        energy_attached=True, deck=STARMIE_DECK)


def _clock(model, body):
    """The body's survival clock as `survival` itself reads it — through the ONE shared call."""
    return sv._survival_clock(model, body)


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_doomed_active_and_the_safe_one_differ_by_EXACTLY_the_clock():
    """The fixture's own control: if the two boards did not differ in `turns_to_ko_me`, the tests
    below would pass or fail for a reason that has nothing to do with survivability."""
    doomed = _successor_board(active_energies=[E_W], bench_energies=[E_W], active_damage=130)
    safe = _successor_board(active_energies=[E_W], bench_energies=[E_W])
    assert _clock(doomed, doomed.mine.active) == 1, "the damaged Active is not actually doomed"
    assert _clock(safe, safe.mine.active) == 2, "the undamaged Active is not actually safe"
    # …and the SUCCESSOR is the same body on both, so nothing else can be doing the work.
    assert _clock(doomed, doomed.mine.bench[0]) == _clock(safe, safe.mine.bench[0])


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_energy_on_a_DOOMED_body_no_longer_outbids_the_successor_behind_it():
    """Same two Energy, differing only in WHICH body carries the second, with the Active one the
    opponent removes next turn. A LATER-turn payoff cannot be spent by a body that is gone."""
    funded_active, funded_successor = {}, {}
    sv.state_value(_successor_board(active_energies=[E_W, E_W], active_damage=130),
                   working=funded_active)
    sv.state_value(_successor_board(active_energies=[E_W], bench_energies=[E_W], active_damage=130),
                   working=funded_successor)
    assert funded_successor["readiness"] > funded_active["readiness"], (
        "readiness still prefers funding a body the opponent removes next turn")


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_SAFE_board_still_prefers_funding_the_active_wincon():
    """The discount is a survivability read, not a blanket preference for the Bench. Without this
    half, zeroing `readiness` outright would pass the doomed case too."""
    funded_active, funded_successor = {}, {}
    sv.state_value(_successor_board(active_energies=[E_W, E_W]), working=funded_active)
    sv.state_value(_successor_board(active_energies=[E_W], bench_energies=[E_W]),
                   working=funded_successor)
    assert funded_active["readiness"] > funded_successor["readiness"], (
        "the discount inverted a board where funding the Active is right")


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_survivability_discount_is_GRADED_rather_than_a_gate():
    """``1 - halve(turns_to_ko_me - 1)``, the exact complement of `survival`'s grade on the same
    clock. Graded because a term with no derivative is never explored under 1-ply differencing."""
    assert sv._survives_to_spend.__doc__                      # the argument lives on the function
    board = _successor_board(active_energies=[E_W], bench_energies=[E_W], active_damage=130)
    assert sv._survives_to_spend(board, board.mine.active) == 0.0
    for clock, expected in ((2, 0.5), (3, 0.75), (5, 0.9375)):
        assert 1.0 - sv.halve(clock - 1) == pytest.approx(expected)
    # strictly increasing in the clock, and never above 1 however far out the Knock Out is
    grades = [1.0 - sv.halve(t - 1) for t in range(1, sv.HORIZON + 1)]
    assert grades == sorted(grades) and grades[-1] < 1.0
    assert len(set(grades)) == len(grades), "the grade collapsed — a clock read that discriminates 1 bit"


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_survival_and_readiness_read_ONE_clock_and_cannot_disagree():
    """The sole-supplier half, and why `_survival_clock` was extracted rather than the call copied:
    two independently-written argument lists is how two families come to disagree about one clock."""
    board = _successor_board(active_energies=[E_W], bench_energies=[E_W], active_damage=130)
    exposed = {round(b.prize_at_risk): b.turns_to_ko_me for b in sv._exposed_bodies(board)}
    for body in board.mine.bodies:
        clock = exposed[round(float(body.prize_value))]
        assert sv._survives_to_spend(board, body) == pytest.approx(1.0 - sv.halve(clock - 1))


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_NOW_leg_takes_NO_survivability_discount():
    """A body that fires its payoff THIS turn attacks before their turn happens at all, so its clock
    says nothing about whether the potential is spendable — `readiness_p` stays the answer."""
    doomed, safe = {}, {}
    sv.state_value(_successor_board(active_energies=[E_W] * 3, active_damage=130), working=doomed)
    sv.state_value(_successor_board(active_energies=[E_W] * 3), working=safe)
    board = _successor_board(active_energies=[E_W] * 3, active_damage=130)
    body = board.mine.active
    assert board.mine.readiness_p(body, board.mine.attack_payoff(body).attack_id) == 1.0
    assert sv._survives_to_spend(board, body) == 0.0, "the fixture's Active is not doomed"
    assert doomed["readiness"] == pytest.approx(safe["readiness"]), (
        "the survivability discount reached the now-leg — a body attacking THIS turn was charged "
        "for a Knock Out that happens after it swings")


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_clock_consultation_is_not_a_second_claim_on_a_priced_fact():
    """The clock is an INPUT to `readiness_odds` exactly as `turns_to_afford` is, and the two families
    price two different CONSEQUENCES of it — `survival`'s own `_predicted_loss` precedent."""
    assert sv.double_counted() == []
    assert sv.registry_gaps() == []
    assert sv.FAMILIES["readiness"].reads == ("body_payoff", "readiness_odds", "role_relevance")
    assert "turns_to_ko_me" in sv.FAMILIES["survival"].reads
    assert "turns_to_ko_me" not in sv.FAMILIES["readiness"].reads
    # the argument is RECORDED where a reader of the tuples will look for it, not only in a packet
    assert "turns_to_ko_me" in sv.FAMILIES["readiness"].composition
    # …and the consultation is REAL: otherwise the contract describes something that never happens.
    board = _successor_board(active_energies=[E_W], bench_energies=[E_W], active_damage=130)
    body = board.mine.active
    attack = board.mine.attack_payoff(body).attack_id
    arm = board.mine.turns_to_afford(body, exclude_expiring=True)
    assert arm is not None and board.mine.readiness_p(body, attack) == 0.0
    assert sv._readiness_odds(board, body, attack) < sv.halve(arm), (
        "the forward leg is not actually consulting the clock the composition claims it does")


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_ADR_0069_attach_decider_is_STRUCTURALLY_unable_to_move_under_this_module():
    """`pilot.py` cannot READ this module at all — parsed rather than substring-searched, because it
    mentions the name in prose. The control points the same instrument at two deciders it does use."""
    import ast
    from pathlib import Path

    src = Path(sv.__file__).with_name("pilot.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[-1] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[-1])
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    assert {"evolve_value", "promote_retreat_value"} <= names, (
        "the instrument found neither shipped decider — it is broken, not the codebase")
    assert "state_value" not in names, (
        "pilot.py grew a `state_value` reader — the ADR-0069 attach decider is no longer insulated "
        "from this module and `attach_value unmoved` stops holding by construction")


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_a_heal_above_the_incoming_raises_survival():
    """A heal has no bespoke equation anywhere, so if this delta does not move, T4's heal family
    prices at 0 and is never played."""
    hurt, whole = {}, {}
    sv.state_value(_lucario_board(my_hp=60), working=hurt)
    sv.state_value(_lucario_board(my_hp=340), working=whole)
    assert whole["survival"] > hurt["survival"]


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_an_ON_LINE_body_outdevelops_an_off_line_one_by_TOPOLOGY_not_by_role():
    """This family is role-BLIND by design, so the ordering holds through `line_topology` and the
    evolve marginal instead: Riolu is my Active's pre-evolution, Crustle is simply a body."""
    line_piece, off_line = {}, {}
    sv.state_value(_lucario_board(bench=[_poke(RIOLU, hp=80, serial=2)]), working=line_piece)
    sv.state_value(_lucario_board(bench=[_poke(CRUSTLE, hp=140, serial=2)]), working=off_line)
    assert line_piece["development"] > off_line["development"], (
        "the pre-evolution of my own Active no longer outdevelops an unrelated body — `line_topology` "
        "was the successor to the role-keyed term and it has stopped carrying it")


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_benching_a_body_raises_development_and_lifts_the_bench_empty_doom():
    """A deploy moves two facts and both must show: the body is development, and a Bench that is no
    longer empty removes the `_predicted_loss` term (ADR-0064, `docs/rules.md` §7 case 2)."""
    alone, benched = {}, {}
    sv.state_value(_lucario_board(my_hp=60), working=alone)
    sv.state_value(_lucario_board(my_hp=60, bench=[_poke(RIOLU, hp=80, serial=2)]), working=benched)
    assert benched["development"] > alone["development"]
    assert benched["survival"] > alone["survival"] + _TERMINAL_JUMP, (
        "the bench-empty doom did not lift when a body arrived to soak the Knock Out")


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_taking_a_prize_moves_the_scalar_by_a_full_prize():
    """`prize_race`'s lead leg has unit slope, which is what makes `ko-score-band` hold: no amount of
    board shape reaches a whole prize."""
    before = sv.state_value(_lucario_board(my_prizes=4))
    after = sv.state_value(_lucario_board(my_prizes=3))
    assert after - before > 1.0                       # the lead, plus proximity sharpening
    assert after - before < 1.0 + sv._PROXIMITY_W


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_holding_a_useful_card_is_worth_something_but_less_than_playing_it_is():
    """The claim is about the MARGINAL, not the level: the family is a LEDGER (held supply minus unmet
    demand), so a hand exactly covering the position's only need nets to 0 (Issue #400 Phase 2)."""
    model = _lucario_board(hand=[MEGA_LUC, E_F])
    working: dict = {}
    sv.state_value(model, working=working)
    assert working["hand"] == 0.0, (
        "no Needs resolution was supplied, so there are no slots to cover — a real zero")

    resolved = _lucario_board(hand=[MEGA_LUC, E_F])
    resolved.mine._needs = _resolution_for_one_wincon_slot()
    resolved_working: dict = {}
    sv.state_value(resolved, working=resolved_working)

    without = _lucario_board(hand=[E_F])
    without.mine._needs = _resolution_for_one_wincon_slot(covered=False)
    without_working: dict = {}
    sv.state_value(without, working=without_working)

    held = resolved_working["hand"] - without_working["hand"]
    assert held > 0.0, (
        "holding the card that covers the position's only Need must beat not holding it — the "
        "ADR-0097 sanity, read as the marginal the ledger actually expresses")
    assert held < 1.0, "a hand may never be worth a whole prize"
    assert resolved_working["hand"] == pytest.approx(0.0), (
        "a hand that exactly covers the only live slot nets to zero deficit — the LEVEL, which is "
        "not what the sanity above is about")


def _resolution_for_one_wincon_slot(*, covered: bool = True):
    """The smallest `needs.Resolution` that exercises the `hand` family's spine. ``covered=False`` is
    the same position with the covering card gone — the SLOT stays, which is the demand half."""
    from common import needs
    if not covered:
        return needs.Resolution(
            slots=(needs.Slot("line", 30.0, 99, "wincon"),),
            eligibility=(frozenset(),), resupply=(0.0,), hand_ids=(E_F,), latent_worth=0.0)
    return needs.Resolution(
        slots=(needs.Slot("line", 30.0, 99, "wincon"),),
        eligibility=(frozenset({0}), frozenset()),
        resupply=(0.0,),
        hand_ids=(MEGA_LUC, E_F),
        latent_worth=0.0)


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_evolution_topology_credits_a_line_that_can_still_arrive_over_one_that_cannot():
    """`development`'s `line_topology` leg: burying every Mega Lucario ex in the discard makes the line
    topologically dead however well funded the base is. `unseen_counts` is the sound read."""
    live = _model(_player(active=_poke(RIOLU, hp=80), prize=4), _player(prize=4))
    dead = _model(_player(active=_poke(RIOLU, hp=80), discard=[MEGA_LUC] * 3, prize=4),
                  _player(prize=4))
    live_w, dead_w = {}, {}
    sv.state_value(live, working=live_w)
    sv.state_value(dead, working=dead_w)
    assert live_w["development"] > dead_w["development"]


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_a_reachable_knockout_on_their_active_raises_threat_but_never_by_a_prize():
    """`threat` must MOVE when their Active becomes reachable and must stay inside its cap: the prize
    for CONVERTING the exposure belongs to `attack_ev` at the terminal action."""
    safe, exposed = {}, {}
    sv.state_value(_lucario_board(my_energies=[E_F, E_F]), working=safe)
    sv.state_value(_lucario_board(my_energies=[E_F, E_F],
                                  their_active=_poke(MUNKIDORI, hp=70, serial=9)), working=exposed)
    assert exposed["threat"] > safe["threat"]
    assert exposed["threat"] <= sv._THREAT_CAP < 1.0


# ── `threat`'s reachability gate asks the DAMAGE MODEL, not the printed number (Issue #281) ───────
# The gate is a STEP, and it was wrong in BOTH directions: a printed number knows nothing about who is hit.


def _threat_of(model) -> float:
    working: dict = {}
    sv.state_value(model, working=working)
    return working["threat"]


def _reach(model):
    """``(incumbent printed read, new damage-model read)`` for MY Active against THEIR Active."""
    mine, theirs = model.mine.active, model.theirs.active
    return (model.mine.best_reachable_damage(mine),
            model.mine.best_reachable_damage_vs(mine, theirs,
                                                context=model.damage_context(attacker="mine")))


@pytest.mark.req("REQ-STATEVALUE-0010")
def test_a_weakness_knockout_the_printed_number_calls_unreachable_now_prices():
    """The UNDER-claim: Jetting Blow prints 120 into 230 HP and Weakness doubles it to 240
    (`docs/rules.md` §5, x2 not +N). ``out_of_reach`` is the one-fact control, ``not_weak`` a sanity check."""
    weak = _starmie_board(_poke(GOUGING_FIRE, hp=230, serial=9))
    out_of_reach = _starmie_board(_poke(GOUGING_FIRE, hp=250, serial=9))
    not_weak = _starmie_board(_poke(DRAGAPULT, hp=230, serial=9))

    printed, modelled = _reach(weak)
    assert printed == 120, "the INCUMBENT must still read the printed number — `attach_value` rests on it"
    assert modelled == 240, "Weakness is x2 on the defender's type (`docs/rules.md` §5)"

    assert _threat_of(weak) > 0.0, "a reachable Knock Out that only Weakness makes reachable"
    assert _threat_of(out_of_reach) == 0.0, "240 doubled damage does not reach 250 HP"
    assert _threat_of(not_weak) == 0.0, "120 printed, no Weakness, 230 HP — genuinely out of reach"


@pytest.mark.req("REQ-STATEVALUE-0010")
def test_a_knockout_the_defender_PREVENTS_no_longer_prices_as_pressure():
    """The OVER-claim: Crustle's Mysterious Rock Inn prevents all damage from {ex} attacks and Mega
    Brave carries no ignore flag. Nebula Beam is the proof this is a per-ATTACK and not per-card fact."""
    board = _lucario_board(my_energies=[E_F, E_F], energy_attached=True,
                           their_active=_poke(CRUSTLE, hp=150, serial=9))
    printed, modelled = _reach(board)
    assert printed == 270, "the INCUMBENT still reads Mega Brave's printed damage"
    assert modelled == 0.0, "every attack Mega Lucario ex can reach is prevented outright"
    assert _threat_of(board) == 0.0

    pierces = _starmie_board(_poke(CRUSTLE, hp=150, serial=9), my_energies=(E_W, E_W, E_W))
    assert _reach(pierces)[1] == 210, "Nebula Beam ignores effects on the Active — it lands"
    assert _threat_of(pierces) > 0.0


@pytest.mark.req("REQ-STATEVALUE-0010")
def test_resistance_takes_its_flat_30_off_the_reachability_read():
    """Resistance is a uniform flat −30 in this set (`docs/rules.md` §5), enough on its own to turn an
    exact-lethal into a miss: Aura Jab prints 130 into Larry's Braviary's 130 HP."""
    board = _lucario_board(my_energies=[E_F], energy_attached=True,
                           their_active=_poke(BRAVIARY, hp=130, serial=9))
    printed, modelled = _reach(board)
    assert printed == 130, "Aura Jab's printed damage — the incumbent's answer, unchanged"
    assert modelled == 100, "130 − 30 Resistance"
    assert _threat_of(board) == 0.0


@pytest.mark.req("REQ-STATEVALUE-0010")
def test_the_new_read_keeps_the_incumbents_BUDGET_affordability_filter():
    """The sibling swaps the damage read and NOTHING else. `can_ko_affordable` was NOT composed here:
    it asks affordability of the ATTACHED Energy, while this family has always used the BUDGET."""
    starved = _starmie_board(_poke(CRUSTLE, hp=150, serial=9), my_energies=(E_W,))
    printed, modelled = _reach(starved)
    assert printed == 120, "only Jetting Blow is reachable on one Energy"
    assert modelled == 0.0, "and Jetting Blow's Active damage is prevented — its bench rider is a "\
                            "separate path and belongs to `attack_ev`"

    funded = _starmie_board(_poke(CRUSTLE, hp=150, serial=9), my_energies=(E_W, E_W, E_W))
    assert _reach(funded)[0] == 210, "three Energy reaches Nebula Beam, so the printed max moves"


# ── `survival` threads the DAMAGE CONTEXT into its clocks (Issue #280) ────────────────────────────
# The direction is THEIRS; backwards reads MY hand as THEIR scaler, so both hands DIFFER on every board.


def _survival_of_model(model) -> float:
    """The `survival` leg off an already-built model — the sibling of `_survival_of`, which takes the
    two player dicts."""
    working: dict = {}
    sv.state_value(model, working=working)
    return working["survival"]


@pytest.mark.req("REQ-STATEVALUE-0010")
def test_survivals_clock_shortens_as_THEIR_hand_grows():
    """Powerful Hand deals ``20 x hand`` and nothing else, so the ACCUMULATING clock (ADR-0071
    decision 4) is ``ceil(340 / (20 x hand))``. Blind, every hand size answers the same 9."""
    ladder = {1: 9, 2: 9, 3: 6, 4: 5, 5: 4, 6: 3, 9: 2, 17: 1}
    for hand, turns in ladder.items():
        exposed = sv._exposed_bodies(_alakazam_board(hand))
        assert len(exposed) == 1, "one Active, empty Bench — the ladder is about one body's clock"
        assert exposed[0].turns_to_ko_me == turns, (
            f"their hand {hand} => {20 * hand}/turn into 340 HP => turn {turns}")


@pytest.mark.req("REQ-STATEVALUE-0010")
def test_the_survival_clock_reads_THEIR_hand_and_never_MINE():
    """Both boards hold the same twelve-and-two hands and differ only in who holds which, so a single
    shared context prices them EXACTLY BACKWARDS rather than merely differently."""
    theirs_big = _alakazam_board(12, my_hand=[E_F, E_F])
    mine_big = _alakazam_board(2, my_hand=[E_F] * 12)

    ctx = theirs_big.damage_context(attacker="theirs")
    assert ctx["atk_hand"] == theirs_big.theirs.hand_size == 12, "the ATTACKER here is theirs"
    assert ctx["def_hand"] == theirs_big.mine.hand_size == 2, "my hand is the DEFENDER's hand"

    assert sv._exposed_bodies(theirs_big)[0].turns_to_ko_me == 2
    assert sv._exposed_bodies(mine_big)[0].turns_to_ko_me == 9
    # Mega Lucario ex yields 3 prizes and one body ranks first, so `survival` is -(3 x halve(t - 1)).
    assert _survival_of_model(theirs_big) == pytest.approx(-3.0 * 0.5)
    assert _survival_of_model(mine_big) == pytest.approx(-3.0 / 256)
    assert _survival_of_model(theirs_big) < _survival_of_model(mine_big)


@pytest.mark.req("REQ-STATEVALUE-0010")
def test_the_bench_empty_doom_reads_their_SCALED_damage_too():
    """`_predicted_loss` is TERMINAL at `-LOSS_PRIZES`, so damage it cannot see is a game loss it
    cannot see. Munkidori's 70 HP sits between a three-card hand (60) and a four-card one (80)."""
    safe = _alakazam_board(3, my_active=_poke(MUNKIDORI, hp=70, serial=3))
    doomed = _alakazam_board(4, my_active=_poke(MUNKIDORI, hp=70, serial=3))
    my_hand_big = _alakazam_board(3, my_active=_poke(MUNKIDORI, hp=70, serial=3),
                                  my_hand=[E_F] * 12)

    assert sv._predicted_loss(safe) is False, "60 damage does not fell a 70 HP Active"
    assert sv._predicted_loss(doomed) is True, "80 does, and my Bench is empty (rules.md §7 case 2)"
    assert sv._predicted_loss(my_hand_big) is False, "MY hand is `def_hand` — it is not their damage"

    assert _survival_of_model(doomed) <= -sv.LOSS_PRIZES
    assert _survival_of_model(safe) > -sv.LOSS_PRIZES


@pytest.mark.req("REQ-STATEVALUE-0010")
def test_the_bench_empty_doom_stands_down_on_a_phantom_and_on_an_empty_board():
    """The two FAIL-DIRECTION cases: no Active at all is mid-promotion rather than a loss, and a bare
    zero-Energy pre-evolution is not doom, or a lone Active reads as a turn-2 loss off unseen cards."""
    empty = _model(_player(active=None, bench=[], prize=4),
                   _player(active=_poke(DRAGAPULT, hp=320, energies=[E_R, E_P], serial=9), prize=4))
    assert sv._predicted_loss(empty) is False
    assert sv.state_value(empty) == 0.0                  # no board, no claim — in either direction

    phantom = _lucario_board(my_hp=270, their_active=_poke(RIOLU, hp=110, energies=[], serial=9))
    assert sv._predicted_loss(phantom) is False
    assert sv.state_value(phantom) > -sv.LOSS_PRIZES, (
        "a bare zero-Energy pre-evolution triggered the terminal loss term — the rung is pricing an "
        "evolution and an attach nobody has seen")


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_more_cards_in_THEIR_hand_never_improves_survival():
    """Hands 1..12 keep the sweep clear of the bench-empty doom (340 HP needs a 17-card hand), so this
    is the POSITIONAL term alone."""
    values = [_survival_of_model(_alakazam_board(n)) for n in range(1, 13)]
    assert all(after <= before for before, after in zip(values, values[1:])), values
    assert values[-1] < values[0], "the axis is flat — the context is not reaching the clock"


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_threat_GRADES_by_what_the_target_yields_instead_of_saturating_into_one_bit():
    """Issue #329: against a 0.1 cap with no weight in front of it, `min(cap, sum)` bound on every
    non-empty input and the family answered one bit. `_THREAT_W` goes in FRONT of the cap."""
    assert sv.threat([1.0]) < sv.threat([2.0]) < sv.threat([3.0])
    assert sv.threat([sv._MAX_PRIZE_VALUE]) == pytest.approx(sv._THREAT_W * sv._MAX_PRIZE_VALUE)
    assert sv.threat([sv._MAX_PRIZE_VALUE]) < sv._THREAT_CAP, (
        "a single maximum-prize target is BELOW the band — the divisor is the single-target ceiling "
        "3.9, and only a sum over several targets can reach it")
    assert sv.threat(()) == 0.0


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_threat_anchor_is_DERIVED_from_the_two_shipped_constants():
    """`_THREAT_W` is a quotient of constants both modules already verify at source, asserted against
    the operands. The third assertion is what stops a defined-but-unused anchor from passing."""
    assert sv._THREAT_W == sv._THREAT_CAP / _needs.TARGET_VALUE_CEILING
    assert _needs.TARGET_VALUE_CEILING == pytest.approx(3.9)
    assert sv.threat([1.0]) == pytest.approx(sv._THREAT_W), (
        "…and the equation actually READS it — a defined-but-unused anchor would pass the two "
        "assertions above")


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_anchor_went_in_FRONT_of_the_cap_so_the_terminal_band_never_moved():
    """`LOSS_PRIZES` is derived from `POSITIONAL_MAX`, so folding the anchor INTO `_THREAT_CAP` would
    have moved the terminal band silently. Pinned as literals so the failure is legible."""
    assert sv._THREAT_CAP == 0.1
    assert sv.POSITIONAL_MAX == 3.4
    assert sv.LOSS_PRIZES == 28.9


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_runaway_guard_still_guards_a_multi_target_SUM():
    """`threat` sums over up to six targets while `TARGET_VALUE_CEILING` is ONE target's ceiling — the
    cap BINDS on 7.3% of non-empty corpus inputs, so it is load-bearing, not decoration."""
    ceiling = _needs.TARGET_VALUE_CEILING
    assert sv.threat([ceiling]) == pytest.approx(sv._THREAT_CAP), "at the edge, the guard binds"
    assert sv.threat([ceiling - 0.1]) < sv._THREAT_CAP, "…and just below it, it does not"
    assert sum([3.0, 2.0]) >= ceiling
    assert sv.threat([3.0, 2.0]) == pytest.approx(sv._THREAT_CAP), (
        "a reachable 3-prize Mega ex AND a 2-prize body is 5.0, past the edge")
    assert sv.threat([sv._MAX_PRIZE_VALUE] * 6) == pytest.approx(sv._THREAT_CAP)


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_no_legal_input_drives_the_family_outside_its_BAND():
    """Swept rather than sampled: 1..`_MAX_BODIES` targets, each in ``[1.0, TARGET_VALUE_CEILING]``,
    must stay inside ``[0, _THREAT_CAP]`` and be monotone in every argument."""
    ladder = [1.0, 2.0, 3.0, _needs.TARGET_VALUE_CEILING]
    assert sv.threat(()) == 0.0
    for v in ladder:
        for n in range(1, sv._MAX_BODIES + 1):
            got = sv.threat([v] * n)
            assert 0.0 < got <= sv._THREAT_CAP, f"{n} x {v} left the band at {got}"
            assert got >= sv.threat([v] * (n - 1)), f"a {n}th target of {v} LOWERED the answer"
    for a, b in zip(ladder, ladder[1:]):
        assert sv.threat([a]) <= sv.threat([b]), "a more valuable target scored less"


@pytest.mark.req("REQ-STATEVALUE-0012")
def test_threat_grades_the_COUNT_of_reachable_targets_not_merely_their_existence():
    """While the cap bound on every non-empty input a second reachable body added exactly 0, so a
    chipped bench under a reachable Active scored identically to a fresh one."""
    assert sv.threat([1.0]) < sv.threat([1.0, 1.0]) < sv.threat([1.0, 1.0, 1.0])
    assert sv.threat([1.0, 1.0, 1.0]) < sv._THREAT_CAP, "three 1-prize bodies is not an extreme board"


# ── a live Trainer damage-BOOST reaches the scalar, gates and all (Issue #282) ────────────────────
# Each link ships covered in isolation, and a chain of separately-green links breaks in the middle.


def _boosts_of(model) -> tuple:
    return model.damage_context(attacker="mine")["atk_boosts"]


def _vs_dragapult_at(hp, *, boosts=None, hand=()):
    """MY funded Mega Lucario ex against a Dragapult ex chipped to ``hp``, the attach already spent so
    Mega Brave's 270 is reachable and nothing the Attach Budget could add moves it."""
    return _lucario_board(my_energies=[E_F, E_F], energy_attached=True, hand=list(hand),
                          their_active=_poke(DRAGAPULT, hp=hp, serial=9), boosts=boosts)


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_a_live_boost_crosses_a_breakpoint_and_the_scalar_moves_for_it():
    """Premium Power Pro's +30 turns Mega Brave's 270 into the 300 that reaches a 300 HP Dragapult ex.
    Asserted per-family too, because a fact that moved two families would be double-counted."""
    plain = _vs_dragapult_at(300)
    boosted = _vs_dragapult_at(300, boosts=[POWER_PRO])

    assert _boosts_of(plain) == () and _boosts_of(boosted) == (POWER_PRO,)
    assert _reach(plain)[1] == 270, "Mega Brave's own damage — the breakpoint is 30 short"
    assert _reach(boosted)[1] == 300, "+30 before Weakness and Resistance"

    before, after = {}, {}
    total_before = sv.state_value(plain, working=before)
    total_after = sv.state_value(boosted, working=after)
    assert after["threat"] > before["threat"] == 0.0
    assert total_after > total_before
    moved = {k for k in before if after[k] != before[k]}
    assert moved == {"threat"}, f"a boost must enter through ONE family, moved: {sorted(moved)}"


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_PLAYING_the_boost_card_is_priced_as_the_BOOST_and_not_as_the_hand_loss():
    """The `_PLAY` transition itself: before, the card is in hand and no boost is live; after, it is
    gone and the boost is live. `threat` prices the exposure STANDING, `attack_ev` the conversion."""
    from common import needs

    def _held(worth):
        return needs.Resolution(slots=(), eligibility=(frozenset(), frozenset()), resupply=(),
                                hand_ids=(POWER_PRO_ID,), latent_worth=worth)

    before = _vs_dragapult_at(300, hand=[POWER_PRO_ID])
    before.mine._needs = _held(TAG_TIER["gust"])
    after = _vs_dragapult_at(300, boosts=[POWER_PRO])
    after.mine._needs = _held(0.0)                       # the card is in the discard now

    b, a = {}, {}
    total_before = sv.state_value(before, working=b)
    total_after = sv.state_value(after, working=a)

    assert b["hand"] > 0.0 and a["hand"] == 0.0, "the hand loss must be REAL, or this passes vacuously"
    assert a["threat"] > b["threat"] == 0.0, "the boost must be what crosses the breakpoint"
    assert total_after - total_before == pytest.approx(a["threat"] - b["hand"]), (
        "the positional half of the transition is the boost's gain against the card's hold, and "
        "nothing else — no third family may move")
    assert a["threat"] == pytest.approx(sv._THREAT_W * 2.0), (
        "Dragapult ex is a 2-prize body (`docs/rules.md` §6), priced at the anchor and not at the "
        "band — asserting the operand is what makes the arithmetic above a claim about the anchor")

    # `unpriced` is the SAME post-play board scored as though no term read the boost, which is what
    # the failure mode actually is — so the two identities below hold at any scale of the anchor.
    unpriced = sv.state_value(_vs_dragapult_at(300))     # boost gone from BOTH hand and board
    assert total_after - unpriced == pytest.approx(a["threat"]), (
        "priced, the played boost is worth exactly the exposure it creates")
    assert total_before - unpriced == pytest.approx(b["hand"]), (
        "…and unpriced it is worth nothing, so the play would score at MINUS the whole hand value "
        "of the card spent — the epic's failure mode, stated as the counterfactual")

    # …and on the sequence score the planner ranks, the play is a gain outright: the terminal leg the
    # boost unlocks dwarfs the positional half either equation produces.
    ko = sv.attack_ev(damage=300.0, target_hp=300.0, target_prizes=2.0)
    no_ko = sv.attack_ev(damage=270.0, target_hp=300.0, target_prizes=2.0)
    assert ko.knockout == pytest.approx(2.0) and no_ko.knockout == 0.0
    assert total_after + ko.total > total_before + no_ko.total


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_a_live_boost_that_crosses_nothing_leaves_the_scalar_untouched():
    """The half that keeps `threat` a GATE rather than a slope: 270 already reaches a 260 HP body, so
    the extra is overkill. BIT-identical, or the scalar would be pricing overkill as position."""
    plain = _vs_dragapult_at(260)
    boosted = _vs_dragapult_at(260, boosts=[POWER_PRO])
    assert _reach(boosted)[1] == _reach(plain)[1] + 30, "the boost IS reaching the damage read"
    assert sv.state_value(boosted) == sv.state_value(plain)


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_the_attacker_TYPE_gate_refuses_a_boost_the_attacker_does_not_qualify_for():
    """Premium Power Pro pays a {F} attacker and nobody else. The control is the SAME amount on the
    SAME board with the gate re-pointed at {W} — a probe, not a card — so only the gate differs."""
    unqualified = _starmie_board(_poke(BRAVIARY, hp=130, serial=9), boosts=[POWER_PRO])
    assert _boosts_of(unqualified) == (POWER_PRO,), "the boost IS in the context — it is the gate "\
                                                    "that must refuse it, not a missing supplier"
    assert _reach(unqualified)[1] == 120, "Jetting Blow, unlifted: Mega Starmie ex is {W}, not {F}"
    assert _threat_of(unqualified) == 0.0

    requalified = _starmie_board(_poke(BRAVIARY, hp=130, serial=9), boosts=[(30, WATER, False)])
    assert _reach(requalified)[1] == 150, "the same 30, gated on {W} — the fixture does cross"
    assert _threat_of(requalified) > 0.0


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_the_defender_ex_gate_counts_a_MEGA_ex_as_an_ex_and_a_plain_body_as_neither():
    """`docs/rulebook.txt` L337: a Mega Evolution Pokémon ex IS a Pokémon ex, so a gate written as
    `stat.ex` would silently drop 40 damage against the biggest target in the format."""
    from common.scouting.provider import CardStat as _CardStat
    starmie = _STATS[MEGA_STARMIE]
    assert (starmie.megaEx, starmie.ex) == (True, False), "the fixture must BE the rulebook-337 case"
    assert _CardStat(MEGA_STARMIE, megaEx=True).is_ex_body, "a Mega ex IS an {ex} for a card effect"

    mega_ex_defender = _lucario_board(my_energies=[E_F], energy_attached=True,
                                      their_active=_poke(MEGA_STARMIE, hp=170, serial=9),
                                      boosts=[BLACK_BELT])
    unboosted = _lucario_board(my_energies=[E_F], energy_attached=True,
                               their_active=_poke(MEGA_STARMIE, hp=170, serial=9))
    assert _reach(unboosted)[1] == 130, "Aura Jab alone is 40 short of 170"
    assert _reach(mega_ex_defender)[1] == 170, "+40 against a Mega Evolution Pokémon ex"
    assert _threat_of(unboosted) == 0.0 < _threat_of(mega_ex_defender)

    plain_defender = _lucario_board(my_energies=[E_F], energy_attached=True,
                                    their_active=_poke(BRAVIARY, hp=130, serial=9),
                                    boosts=[BLACK_BELT])
    assert _boosts_of(plain_defender) == (BLACK_BELT,)
    assert _reach(plain_defender)[1] == 100, "130 − 30 Resistance, and the {ex} gate refuses the 40"
    assert _threat_of(plain_defender) == 0.0


# ── an ATTACHED boost Tool, and the HOLDER gate that decides it (Issue #345) ──────────────────────
# Brave Bangle carries TWO gates on one +30: a HOLDER gate (no Rule Box) and the defender-{ex} gate.


#: The two holders these cases straddle, each with the Energy that funds its own attack — Slowking has
#: no Rule Box, Mega Lucario ex has one. Data rather than a branch, so only the holder differs.
_HOLDERS = {SLOWKING: (120, [E_P, E_P, E_P]), MEGA_LUC: (340, [E_F])}


def _slowking_board(their_active, *, bangle=True, holder=SLOWKING):
    """MY ``holder`` Active carrying Brave Bangle (or not), with the turn's attach already spent so
    reachability is exactly what is on the board."""
    hp, energies = _HOLDERS[holder]
    return _model(
        _player(active=_poke(holder, hp=hp, energies=energies,
                             tools=(BRAVE_BANGLE,) if bangle else ()), prize=4),
        _player(active=their_active, prize=4),
        energy_attached=True)


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_an_attached_boost_tool_crosses_the_breakpoint_its_holder_qualifies_for():
    """A Tool's +30 reaches `threat` by the same path a played Trainer's does, and the two suppliers
    must not disagree about one card's {ex} scope. 120 is exactly 30 short of 150 remaining HP."""
    defender = _poke(MEGA_STARMIE, hp=150, serial=9)
    bare = _slowking_board(defender)
    bare_no_tool = _slowking_board(defender, bangle=False)
    assert _boosts_of(bare_no_tool) == (), "no Tool attached, no boost in the context"
    assert _boosts_of(bare) == ((30, None, True),), "the Tool's triple, gate included"
    assert _reach(bare_no_tool)[1] == 120, "Super Psy Bolt alone is 30 short of 150"
    assert _reach(bare)[1] == 150, "+30 before Weakness and Resistance"
    assert _threat_of(bare_no_tool) == 0.0 < _threat_of(bare)


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_the_HOLDER_gate_refuses_the_same_tool_on_a_body_that_has_a_Rule_Box():
    """Mega Lucario ex is `megaEx`, so the card's condition is not met. An ungated read manufactures
    lethals rather than missing them, which is strictly worse than the zero this issue replaced."""
    defender = _poke(MEGA_STARMIE, hp=150, serial=9)
    ruled_out = _slowking_board(defender, holder=MEGA_LUC)
    without = _slowking_board(defender, holder=MEGA_LUC, bangle=False)
    assert _boosts_of(ruled_out) == (), "a Rule-Box holder gets nothing from this Tool"
    assert _reach(ruled_out) == _reach(without), "attaching it must move no number at all"
    assert sv.state_value(ruled_out) == sv.state_value(without)
    # The board really is one the gate decides: 130 falls short of 150 and the ungated 160 would not.
    assert _reach(ruled_out)[1] == 130 < 150 < 130 + 30
    assert _threat_of(ruled_out) == 0.0


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_the_attached_tools_defender_gate_is_read_too_so_both_conditions_must_hold():
    """The second gate on the same +30: against a non-{ex} defender the boost is in the context and
    still contributes nothing. This attacker is {P}, so no Weakness leg confuses the reading."""
    plain = _slowking_board(_poke(BRAVIARY, hp=130, serial=9))
    assert _boosts_of(plain) == ((30, None, True),), "the boost IS present — the gate is what refuses"
    assert _reach(plain)[1] == 120, "the {ex} gate refuses the 30 against a non-{ex} defender"
    assert _threat_of(plain) == 0.0


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_with_no_boost_in_play_the_context_is_EMPTY_and_the_scalar_is_unmoved():
    """An EMPTY tracker must be indistinguishable from no tracker at all. Bit-identical over the whole
    per-family breakdown, because a term that gained a boost-shaped leg could hide in the total."""
    no_tracker = _vs_dragapult_at(320)
    empty_tracker = _vs_dragapult_at(320, boosts=[])
    assert _boosts_of(no_tracker) == () == _boosts_of(empty_tracker)

    without, empty = {}, {}
    assert sv.state_value(no_tracker, working=without) == sv.state_value(empty_tracker,
                                                                        working=empty)
    assert without == empty


# ── standing chip on THEIR bench is an asset (Issue #284) ─────────────────────────────────────────
# A DIFFERENT damage route: a snipe RIDER ignores W/R and never routes through `predicted_damage`.


UNREADABLE_CARD = 909909          # deliberately absent from `_STATS` — the fail-closed case


def _bench_board(their_bench, *, my_active=None, my_energies=(E_W,), their_active=None):
    """MY Mega Starmie ex — the fixture's one bench rider. Their Active defaults to a 320-HP Dragapult
    ex that Jetting Blow's exact 120 cannot reach, so every non-zero `threat` here is the BENCH leg."""
    return _model(
        _player(active=my_active or _poke(MEGA_STARMIE, hp=330, energies=list(my_energies)),
                prize=4),
        _player(active=their_active or _poke(DRAGAPULT, hp=320, energies=[E_R, E_P], serial=9),
                bench=list(their_bench), prize=4),
        energy_attached=True)


@pytest.mark.req("REQ-STATEVALUE-0012")
def test_counters_standing_on_their_benched_body_are_worth_something_to_me():
    """Two boards identical but for the counters on ONE benched body. Six counters is Phantom Dive's
    payload, and a 70-HP Munkidori carrying them sits at 10 HP, inside Jetting Blow's 50 rider."""
    fresh = _bench_board([_poke(MUNKIDORI, hp=70, serial=11)])
    chipped = _bench_board([_poke(MUNKIDORI, hp=70, damage=60, serial=11)])

    assert _threat_of(fresh) == 0.0, "50 of rider does not reach a fresh 70 HP"
    assert _threat_of(chipped) > 0.0, "…and does reach the 10 HP the chip leaves"
    assert sv.state_value(chipped) > sv.state_value(fresh)


@pytest.mark.req("REQ-STATEVALUE-0012")
def test_the_bench_leg_still_stops_short_of_a_prize():
    """The worst board the widened loop can be handed: six 3-prize bodies at 10 HP. The cap is asserted
    to BITE — `threat <= _THREAT_CAP` alone is a tautology — which is the ``raw > 1.0`` line."""
    bench = [_poke(MEGA_STARMIE, hp=330, damage=320, serial=11 + i) for i in range(5)]
    board = _bench_board(bench, their_active=_poke(MEGA_STARMIE, hp=330, damage=320, serial=9))

    raw = sum(sv._reachable_target_values(board))
    assert len(sv._reachable_target_values(board)) == 6, "all six bodies reachable — the worst case"
    assert raw > 1.0, "…and their uncapped sum really does exceed one prize, so the cap is load-bearing"
    assert 0.0 < _threat_of(board) <= sv._THREAT_CAP < 1.0


@pytest.mark.req("REQ-STATEVALUE-0012")
def test_a_TERA_body_on_their_bench_contributes_nothing_however_damaged():
    """Bench immunity, failing CLOSED (`docs/rules.md` §11). The control is a body at the SAME 10 HP
    that is not Tera, without which a bench leg that had stopped firing entirely would pass."""
    tera = _bench_board([_poke(DRAGAPULT, hp=320, damage=310, serial=11)])
    plain = _bench_board([_poke(MEGA_STARMIE, hp=330, damage=320, serial=11)])

    assert _threat_of(tera) == 0.0
    assert _threat_of(plain) > 0.0, "the control: a non-Tera body at the same 10 HP DOES price"

    # …and the immunity is scoped to the BENCH: the same Tera body Active is reachable.
    active = _bench_board([], their_active=_poke(DRAGAPULT, hp=320, damage=310, serial=9))
    assert _threat_of(active) > 0.0


@pytest.mark.req("REQ-STATEVALUE-0012")
def test_an_UNREADABLE_benched_body_contributes_nothing():
    """`CardStat` has no immunity field beyond `tera`, so a body whose card does not resolve is not
    credited. Direction: `hp` is on the board and `prize_value` fails OPEN at 1."""
    unknown = _bench_board([_poke(UNREADABLE_CARD, hp=10, serial=11)])
    known = _bench_board([_poke(MUNKIDORI, hp=70, damage=60, serial=11)])

    assert _threat_of(unknown) == 0.0
    assert _threat_of(known) > 0.0, "the control: a resolvable body at the same reach DOES price"


@pytest.mark.req("REQ-STATEVALUE-0012")
def test_without_a_bench_RIDER_their_bench_prices_at_nothing_however_soft():
    """The gate is a snipe ROUTE, not proximity to death. Both boards carry the identical bench and
    Mega Brave misses their 320-HP Active on both, so the Active leg is silent either way."""
    bench = [_poke(MUNKIDORI, hp=70, damage=60, serial=11)]
    riderless = _bench_board(bench, my_active=_poke(MEGA_LUC, hp=340, energies=[E_F, E_F]))
    rider = _bench_board(bench)

    assert _threat_of(riderless) == 0.0
    assert _threat_of(rider) > 0.0, "the control: the same bench under an attacker that CAN reach it"


@pytest.mark.req("REQ-STATEVALUE-0012")
def test_the_bench_rider_never_leaks_into_the_ACTIVE_reachability_read():
    """A widening that reached for one damage number per BODY rather than per SEAT fails here: 170 HP
    is outside Jetting Blow's exact 120 and inside 120 plus the 50 rider."""
    board = _bench_board([], their_active=_poke(DRAGAPULT, hp=320, damage=150, serial=9))
    assert board.theirs.active.hp_remaining == 170
    assert _threat_of(board) == 0.0

    # …and the control, so a bench leg that reached nothing at all cannot pass: at 120 it does.
    reachable = _bench_board([], their_active=_poke(DRAGAPULT, hp=320, damage=200, serial=9))
    assert _threat_of(reachable) > 0.0


@pytest.mark.req("REQ-STATEVALUE-0012")
def test_the_dragapult_cross_turn_shape_is_priced_BEFORE_the_gust_and_not_only_after():
    """The AFTER half was never the gap — the Active leg reads a gusted body's remaining HP. The
    BEFORE half is this issue: while it is still benched, the chip is an asset carried between turns."""
    pre_fresh = _bench_board([_poke(MUNKIDORI, hp=70, serial=11)])
    pre_chipped = _bench_board([_poke(MUNKIDORI, hp=70, damage=60, serial=11)])
    post_fresh = _bench_board([], their_active=_poke(MUNKIDORI, hp=70, serial=9))
    post_chipped = _bench_board([], their_active=_poke(MUNKIDORI, hp=70, damage=60, serial=9))

    assert _threat_of(post_fresh) > 0.0 and _threat_of(post_chipped) > 0.0, (
        "after the gust BOTH are reachable — Jetting Blow's 120 covers a fresh 70 HP")
    assert _threat_of(pre_fresh) == 0.0
    assert _threat_of(pre_chipped) > 0.0


# ── sniping a pre-evolution denies a forward payoff (Issue #285) ──────────────────────────────────
# ADR-0119 re-pointed the credit from forward DAMAGE (already inside `survival`) to the LINE's PRIZE.


def _target_values(model) -> tuple:
    """The UNCAPPED per-target values `threat` is handed — the seam the denial credit changes."""
    return sv._reachable_target_values(model)


def _credit_for(model, card_id: int) -> float:
    """The denial credit for the body carrying ``card_id`` — how much MORE than its own prize its LINE
    is worth. Read off the SHIPPED primitives, since a re-derivation agrees with a broken build."""
    body = next(b for b in model.theirs.bodies if b.card_id == card_id)
    best, hops = model.theirs.forward_line_prize(card_id)
    own = float(body.prize_value)
    return _needs.line_prize_advance(own_prize=own, max_line_prize=best, hops=hops) - own


def _their_hops(model, card_id: int) -> int:
    return model.theirs.forward_payoff(card_id).hops


@pytest.mark.req("REQ-STATEVALUE-0013")
def test_a_pre_evolution_prices_above_an_identical_body_that_evolves_into_nothing():
    """Two 1-prize bodies at the same HP in the same seat, differing only in what their line becomes.
    Munkidori evolves into nothing, so a credit that fired on EVERY body would fail here."""
    staryu = _starmie_board(_poke(STARYU, hp=70, serial=9))
    dead_end = _starmie_board(_poke(MUNKIDORI, hp=110, damage=40, serial=9))

    assert len(_target_values(staryu)) == len(_target_values(dead_end)) == 1, "both reachable"
    assert _credit_for(dead_end, MUNKIDORI) == 0.0, "the control: a line that goes nowhere owes 0"
    assert _credit_for(staryu, STARYU) > 0.0
    assert _target_values(staryu)[0] > _target_values(dead_end)[0]
    # …and the credit really is what got there, rather than something else moving the value.
    assert _target_values(dead_end) == (1.0,)
    assert _target_values(staryu) == pytest.approx((1.0 + _credit_for(staryu, STARYU),))


@pytest.mark.req("REQ-STATEVALUE-0013")
def test_a_two_hop_base_prices_below_a_one_hop_base_on_the_SAME_terminal_payoff():
    """Both lines end at Dragapult ex and both bases are 1-prize, so the only difference is
    `halve(hops)`. Equal gaps pass under ANY monotone discount, so the exact values carry that."""
    dreepy = _starmie_board(_poke(DREEPY, hp=70, serial=9))
    drakloak = _starmie_board(_poke(DRAKLOAK, hp=90, serial=9))

    assert _their_hops(dreepy, DREEPY) == 2 and _their_hops(drakloak, DRAKLOAK) == 1
    assert _credit_for(dreepy, DREEPY) > 0.0 and _credit_for(drakloak, DRAKLOAK) > 0.0
    assert _credit_for(drakloak, DRAKLOAK) > _credit_for(dreepy, DREEPY), (
        "one hop from the same terminal form must price above two — the discount, doing work")

    # A 1-prize base whose line reaches a 2-prize ex is owed a gap of exactly 1, discounted by hops.
    assert _credit_for(drakloak, DRAKLOAK) == pytest.approx(1 * 0.5)
    assert _credit_for(dreepy, DREEPY) == pytest.approx(1 * 0.25)


@pytest.mark.req("REQ-STATEVALUE-0013")
def test_the_hop_counts_are_THIS_SETS_and_a_mainline_chain_would_fail_here():
    """A mainline three-stage chain would still produce a plausible credit, just a wrongly-discounted
    one, so the hop counts are asserted by number. Dreepy → Dragapult ex is a genuine two."""
    board = _starmie_board(_poke(MUNKIDORI, hp=110, serial=9))
    assert _their_hops(board, RIOLU) == 1, "Riolu → Mega Lucario ex, no intermediate Lucario"
    assert _their_hops(board, STARYU) == 1, "Staryu → Mega Starmie ex, no intermediate Starmie"
    assert _their_hops(board, DREEPY) == 2, "Dreepy → Drakloak → Dragapult ex"
    assert _their_hops(board, DRAKLOAK) == 1
    assert _their_hops(board, MEGA_LUC) == 0, "a body already in its best form owes no hop"


@pytest.mark.req("REQ-STATEVALUE-0013")
def test_reachability_fails_OPEN_on_their_side_and_CLOSED_on_mine():
    """`MySide` proves a line dead from `unseen_counts`; their deck is untracked, so `TheirSide` fails
    OPEN. Asserted on ONE card, so a stub hardcoding True for both sides would fail here."""
    board = _model(
        _player(active=_poke(MEGA_STARMIE, hp=330, energies=[E_W]),
                discard=[MEGA_LUC, MEGA_LUC, MEGA_LUC], prize=4),
        _player(active=_poke(RIOLU, hp=80, serial=9), prize=4),
        energy_attached=True)

    assert board.mine.forward_payoff(RIOLU).reachable is False, (
        "the control: my side CAN prove this line dead — all three copies are in my discard")
    assert board.theirs.forward_payoff(RIOLU).reachable is True
    assert board.theirs.forward_payoff(RIOLU).owed_damage > 0.0
    # The PRIZE leg inherits the same fail-OPEN by construction: same closure, no reachability gate.
    assert board.theirs.forward_line_prize(RIOLU) == (3, 1), "Riolu → Mega Lucario ex, one hop"
    assert _credit_for(board, RIOLU) > 0.0, "…and the credit survives: we cannot prove otherwise"


@pytest.mark.req("REQ-STATEVALUE-0013")
def test_a_body_already_in_its_best_form_gets_no_credit():
    """A credit here would pay twice for one card. It cannot bite on the guard it looks like it
    covers — what it catches is an unconditional credit, or a lost `owed_damage` floor at 0."""
    board = _starmie_board(_poke(MEGA_STARMIE, hp=330, damage=220, serial=9))

    assert _target_values(board) == (3.0,), "exactly its prize count, with nothing added"
    assert _credit_for(board, MEGA_STARMIE) == 0.0


@pytest.mark.req("REQ-STATEVALUE-0013")
def test_the_credit_reaches_a_BENCHED_pre_evolution_which_is_where_they_actually_sit():
    """The seat that matters: a pre-evolution sits on their Bench. The 50 rider does not cover a fresh
    70-HP Staryu, so the board carries the two counters that bring it inside."""
    board = _bench_board([_poke(STARYU, hp=70, damage=20, serial=11)])

    assert len(_target_values(board)) == 1, "the benched Staryu, reached by the rider alone"
    assert _credit_for(board, STARYU) > 0.0
    assert _target_values(board) == pytest.approx((1.0 + _credit_for(board, STARYU),))


@pytest.mark.req("REQ-STATEVALUE-0013")
def test_the_two_forward_payoff_suppliers_agree_and_diverge_only_where_the_DECKLIST_does():
    """Two implementations of one quantity: a DFS over my decklist against the pool closure. On Riolu
    they must agree; on Staryu they must NOT, which is the over-read `threat.blind_to` names."""
    board = _starmie_board(_poke(RIOLU, hp=80, serial=9))

    mine, theirs = board.mine.forward_payoff(RIOLU), board.theirs.forward_payoff(RIOLU)
    assert (mine.owed_damage, mine.hops) == (theirs.owed_damage, theirs.hops) != (0.0, 0), (
        "one line, one number, from two implementations")

    assert board.mine.forward_payoff(STARYU) == (0.0, 0, True), "my decklist runs no Staryu line"
    assert board.theirs.forward_payoff(STARYU).owed_damage > 0.0, (
        "…and theirs credits it regardless, because the pool index is deck-agnostic")


@pytest.mark.req("REQ-STATEVALUE-0013")
def test_the_denial_credit_REACHES_the_family_once_the_anchor_is_in_front_of_the_cap():
    """With `_THREAT_W` in front of the cap the seam's discrimination survives into the family. The
    product is SMALL, which is why this is a strict inequality and not a magnitude claim."""
    staryu = _starmie_board(_poke(STARYU, hp=70, serial=9))
    dead_end = _starmie_board(_poke(MUNKIDORI, hp=110, damage=40, serial=9))

    assert _target_values(staryu)[0] > _target_values(dead_end)[0], "the seam DOES discriminate"
    assert _threat_of(staryu) > _threat_of(dead_end) > 0.0, (
        "…and the family now carries that discrimination instead of flattening it")
    assert _threat_of(staryu) < sv._THREAT_CAP, "one 1-prize target is nowhere near the guard"
    assert _threat_of(staryu) - _threat_of(dead_end) == pytest.approx(
        sv._THREAT_W * (_target_values(staryu)[0] - _target_values(dead_end)[0])), (
        "the gap the family shows IS the seam's gap, scaled by the anchor and nothing else")
    # Not asserted on `state_value`: these boards differ in their Active's own attacks, so `survival`
    # moves between them for a reason that has nothing to do with this credit.


# ── inertness is over; the seam is not ────────────────────────────────────────────────────────────


@pytest.mark.req("REQ-STATEVALUE-0003")
def test_the_per_body_inputs_are_NAMED_so_a_frozen_contract_cannot_be_transposed():
    """A transposed ``(payoff, odds, relevance)`` would still type-check, still run, and price the
    board wrong in a direction nobody would look."""
    body = sv.ExposedBody(prize_at_risk=2.0, turns_to_ko_me=1)
    assert (body.prize_at_risk, body.turns_to_ko_me) == (2.0, 1)

    ready = sv.ReadyBody(payoff=3.0, readiness_odds=0.25, role_relevance=1.0)
    assert (ready.payoff, ready.readiness_odds, ready.role_relevance) == (3.0, 0.25, 1.0)

    # Still tuples, so an implementation may unpack positionally without ceremony.
    assert tuple(ready) == (3.0, 0.25, 1.0)


@pytest.mark.req("REQ-STATEVALUE-0003")
def test_the_module_reaches_for_no_engine_no_obs_and_no_pilot():
    """The seam, asserted at import. A value equation that can reach for the board it was handed facts
    about stops being testable with numbers."""
    import inspect
    src = inspect.getsource(sv)
    for forbidden in ("from cg import", "import cgpy", "from common.pilot", "import pilot"):
        assert forbidden not in src, forbidden


# ── the SAME monotonicity, on REAL corpus frames ──────────────────────────────────────────────────
# `>=` per frame with at least one STRICT move: a real board can be genuinely indifferent to a fact.

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
    across the session (`corpus_index` caches it), so mutating in place would corrupt later tests."""
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
    """The ruling's first named case, on boards nobody designed for it."""
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


@pytest.mark.req("REQ-STATEVALUE-0010")
def test_on_real_frames_the_incumbent_printed_read_still_returns_a_PRINTED_number(corpus_models):
    """`best_reachable_damage` is the counterfactual leg of the corpus-RULED attach marginal (ADR-0069
    §2). Two properties — the printed DAMAGE and the AFFORDABILITY filter — plus a positive control."""
    diverged, compared = 0, 0
    for key, pilot, obs in corpus_models:
        my_index = ((obs.get("current") or {}).get("yourIndex")) or 0
        model = pilot._leaf_state_model(obs, my_index)
        mine, theirs = model.mine.active, model.theirs.active
        if mine is None or mine.stat is None:
            continue
        expected = max((float(pilot.combat.attack_damage(aid))
                        for aid in (mine.stat.attacks or ())
                        if model.mine.reachable_attach(mine, aid)), default=0.0)
        incumbent = float(model.mine.best_reachable_damage(mine))
        assert incumbent == expected, (
            f"{key}: `best_reachable_damage` returned {incumbent}, not the printed maximum "
            f"{expected} over the attacks `reachable_attach` admits — the incumbent moved, and "
            f"`attach_value`'s corpus rulings rest on it not moving")
        if theirs is None or not theirs.hp_remaining:
            continue
        compared += 1
        modelled = float(model.mine.best_reachable_damage_vs(
            mine, theirs, context=model.damage_context(attacker="mine")))
        diverged += abs(modelled - incumbent) > 1e-9
    assert compared, "no corpus frame offered both Actives — the class would pass vacuously"
    assert diverged, ("positive control FAILED: the damage-model read never once differed from the "
                      "printed read, so the instrument is not measuring what this issue changed")


@pytest.mark.req("REQ-STATEVALUE-0010")
def test_on_real_frames_their_context_only_ever_SHORTENS_the_survival_clock(corpus_models):
    """Three properties: the extractor asks the threaded question, the direction is THEIRS, and a
    scaler only ADDS — so threading can shorten a clock and never lengthen one. Controls asserted."""
    shortened, hands_differ, bodies = 0, 0, 0
    for key, pilot, obs in corpus_models:
        my_index = ((obs.get("current") or {}).get("yourIndex")) or 0
        model = pilot._leaf_state_model(obs, my_index)
        ctx = model.damage_context(attacker="theirs")
        assert ctx["atk_hand"] == model.theirs.hand_size, f"{key}: the ATTACKER is theirs"
        assert ctx["def_hand"] == model.mine.hand_size, f"{key}: the DEFENDER is mine"
        hands_differ += ctx["atk_hand"] != ctx["def_hand"]
        bench_raws, opp_active = model.mine.bench_raws, model.theirs.active_raw
        exposed = sv._exposed_bodies(model)
        assert len(exposed) == len(model.mine.bodies)
        for body, read in zip(model.mine.bodies, exposed):
            bodies += 1
            clock = dict(my_benched=not body.is_active, my_bench=bench_raws, opp_active=opp_active)
            blind = int(model.theirs.turns_to_ko_me(body.body, **clock))
            threaded = int(model.theirs.turns_to_ko_me(body.body, context=ctx, **clock))
            assert threaded <= blind, (
                f"{key}: body {body.card_id}'s clock LENGTHENED from {blind} to {threaded} once "
                f"their damage context was threaded — a scaler can only add damage")
            assert read.turns_to_ko_me == threaded, (
                f"{key}: `survival` read body {body.card_id}'s clock as {read.turns_to_ko_me}; "
                f"their damage context says {threaded}")
            shortened += threaded < blind
    assert bodies, "no corpus frame offered a body of mine — the class would pass vacuously"
    assert hands_differ, ("positive control FAILED: no frame had asymmetric hands, so the direction "
                          "assertions above could not have caught a swapped context")
    assert shortened, ("positive control FAILED: their damage context never once shortened a clock, "
                       "so the instrument is not measuring what this issue changed")


def _hand_scaler_frames():
    """``(key, pilot, obs, my_index)`` for every corpus frame with a `handSizeDamage` attacker across
    the table. Scans the whole index, because the archetype is absent from `corpus_models` sample."""
    from corpus_helpers import corpus_index
    from train.tune import _build_pilot
    out, built = [], {}
    for (episode, frame), rec in sorted(corpus_index().items()):
        if rec.agent not in built:
            try:
                built[rec.agent] = _build_pilot(rec.agent)[0]
            except Exception:                       # an unbuildable agent is skipped, never fatal
                built[rec.agent] = None
        pilot = built[rec.agent]
        if pilot is None or pilot.stats is None:
            continue
        cur = (rec.obs or {}).get("current") or {}
        players = cur.get("players") or []
        my_index = cur.get("yourIndex", 0)
        if len(players) < 2:
            continue
        opp = players[1 - my_index] or {}
        ids = [(b or {}).get("id")
               for b in ((opp.get("active") or []) + (opp.get("bench") or [])) if b]
        if any(getattr(pilot.stats.get(i), "handSizeDamage", 0) for i in ids if i is not None):
            out.append((f"{episode}|{frame}", pilot, rec.obs, my_index))
    return out


@pytest.fixture(scope="module")
def hand_scaler_frames():
    frames = _hand_scaler_frames()
    if not frames:
        pytest.skip("no corpus frame carries a `handSizeDamage` attacker opposite")
    return frames


@pytest.mark.req("REQ-STATEVALUE-0010")
def test_on_real_frames_a_hand_size_attacker_shortens_the_clock_as_their_hand_grows(
        hand_scaler_frames):
    """Their hand is a COUNT and nothing else, so the perturbation is exactly one integer. Monotone
    per frame with at least one strict move: a frame can be genuinely indifferent."""
    import copy
    hands = (1, 3, 6, 10, 20)
    strict = 0
    for key, pilot, obs, my_index in hand_scaler_frames:
        ladder = []
        for hand in hands:
            board = copy.deepcopy(obs)          # `corpus_index` caches obs — never mutate in place
            board["current"]["players"][1 - my_index]["handCount"] = hand
            model = pilot._leaf_state_model(board, my_index)
            ladder.append(tuple(b.turns_to_ko_me for b in sv._exposed_bodies(model)))
        for (before, after), (h0, h1) in zip(zip(ladder, ladder[1:]), zip(hands, hands[1:])):
            assert all(y <= x for x, y in zip(before, after)), (
                f"{key}: their hand {h0} -> {h1} LENGTHENED a survival clock, {before} -> {after}")
        strict += ladder[0] != ladder[-1]
    assert strict, ("positive control FAILED: no frame's clock moved between a 1-card and a 20-card "
                    "opponent hand, so the monotonicity above is being asserted over constants")


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_on_real_frames_healing_my_active_never_lowers_survival(corpus_models):
    """The ruling's second named case: a heal has no bespoke equation anywhere in the codebase."""
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


# ── the LEAF PATH's `hand` zero, asserted as RULED rather than merely documented (Issue #331) ─────
# A DIFFERENT zero from the one asserted above: this one's cause lives one module over, in `planner`.


def _leaf_end_boards(want_blind: int = 20, want_live: int = 2):
    """``(key, pilot, my_index, end)`` for corpus frames forward-simulated to my end-of-turn board,
    split into ``blind`` (my turn passed over) and ``live`` (the line ENDED THE GAME)."""
    from cgpy.compat import api as cgpy_api
    from corpus_helpers import corpus_index
    from train.leaf_lab import _PLACEHOLDER_SBI
    from train.tune import _build_pilot
    blind, live, built = [], [], {}
    for (episode, frame), rec in sorted(corpus_index().items()):
        if len(blind) >= want_blind and len(live) >= want_live:
            break
        if not ((rec.obs or {}).get("select") or {}).get("option"):
            continue                                # nothing to take as a first step
        if rec.agent not in built:
            try:
                pilot, _ = _build_pilot(rec.agent)
                pilot._search_api = cgpy_api        # the seam: simulate offline via cgpy, not native
                built[rec.agent] = pilot
            except Exception:                       # an unbuildable agent is skipped, never fatal
                built[rec.agent] = None
        pilot = built[rec.agent]
        if pilot is None:
            continue
        obs = {**rec.obs,
               "search_begin_input": rec.obs.get("search_begin_input") or _PLACEHOLDER_SBI}
        try:
            sim = pilot._simulate_line(obs, [0])
        except Exception:                           # a board cgpy cannot reseed is skipped, counted
            sim = None
        if sim is None:
            continue
        end, my_index, result = sim[0], sim[1], sim[3]
        (live if result != -1 else blind).append((f"{episode}|{frame}", pilot, my_index, end))
    return blind, live


@pytest.fixture(scope="module")
def leaf_end_boards():
    blind, live = _leaf_end_boards()
    if not blind or not live:
        pytest.skip("no offline-simulatable corpus frame of both shapes in this checkout")
    return blind, live


def _my_side(end, my_index):
    players = (end.get("current") or {}).get("players") or []
    return players[my_index] if 0 <= my_index < len(players) and players[my_index] else {}


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_leaf_paths_hand_zero_is_the_RULED_one_and_says_so_when_it_stops_being(leaf_end_boards):
    """The leaf path prices `hand` at exactly 0.0 and that is RULED (Issue #331): the simulated end
    board is opponent-perspective, so `_leaf_needs_resolution` returns None. `live` is the control."""
    blind, live = leaf_end_boards

    for key, pilot, my_index, end in blind:
        me = _my_side(end, my_index)
        assert not me.get("hand"), (
            f"{key}: the simulated end board carries MY hand. The leaf is no longer hand-blind — "
            f"re-read Issue #331's ruling and re-measure its 15 held-out frames before changing "
            f"this test")
        if not me.get("handCount"):
            continue                                # an emptied hand prices zero for another reason
        assert pilot._leaf_needs_resolution(end, my_index) is None, (
            f"{key}: `_leaf_needs_resolution` resolved a hand the end observation does not carry")
        working: dict = {}
        sv.state_value(pilot._leaf_state_model(end, my_index), working=working)
        assert working["hand"] == 0.0, (
            f"{key}: the leaf priced `hand` at {working['hand']}, not the structural 0.0 that "
            f"`hand.blind_to` records and Issue #331 ruled")

    for key, pilot, my_index, end in live:
        me = _my_side(end, my_index)
        assert me.get("hand"), f"{key}: a game-ending line's board should still be my perspective"
        assert pilot._leaf_needs_resolution(end, my_index) is not None, (
            f"{key}: a board WITH my hand resolved no Needs — the instrument is broken, not the leaf")
        working = {}
        sv.state_value(pilot._leaf_state_model(end, my_index), working=working)
        assert working["hand"] > 0.0, (
            f"{key}: positive control FAILED — `hand` read {working['hand']} on a board that DOES "
            f"carry my hand, so the zeros above prove nothing about the ruling")


# ── a companion-GATED payoff (Issue #287) ─────────────────────────────────────────────────────────
# A PRINTED `maxDamage` cannot carry a board condition, so the term asks the damage oracle instead.


def _lunar_board(*, bench=(), solrock_energies=(E_F,), energy_attached=False):
    """MY Solrock Active against THEIR Dragapult ex with a caller-chosen Bench — the one fact the
    gated payoff turns on. One {F} is already down, so Cosmic Beam's ``{F}`` cost is PAID."""
    return _model(
        _player(active=_poke(SOLROCK, hp=110, energies=solrock_energies),
                bench=list(bench), prize=4),
        _player(active=_poke(DRAGAPULT, hp=320, energies=[E_R, E_P], serial=9), prize=4),
        energy_attached=energy_attached, deck=LUNAR_DECK)


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_a_companion_gated_attacker_is_not_ready_without_its_companion():
    """Cosmic Beam is Solrock's ONLY attack, so with no Lunatone benched this body achieves nothing
    and `readiness` must say so rather than price the printed 70 it will never deal."""
    bare, paired = {}, {}
    sv.state_value(_lunar_board(bench=[_poke(RIOLU, hp=80, serial=2)]), working=bare)
    sv.state_value(_lunar_board(bench=[_poke(LUNATONE, hp=110, serial=2)]), working=paired)
    assert paired["readiness"] > bare["readiness"], "the gate never fired: printed damage priced"


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_benching_the_companion_is_what_raises_readiness():
    """The play the old reading could not see: under 1-ply differencing a play no term reads prices at
    0 delta, which at ordering time means never explored rather than merely undervalued."""
    empty, benched = {}, {}
    sv.state_value(_lunar_board(bench=[]), working=empty)
    sv.state_value(_lunar_board(bench=[_poke(LUNATONE, hp=110, serial=2)]), working=benched)
    assert benched["readiness"] > empty["readiness"]


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_losing_the_companion_lowers_readiness():
    """The mirror, and the half that makes the term a defence: losing the enabler has to cost me
    something, or the agent trades it away for free."""
    with_luna, without = {}, {}
    sv.state_value(_lunar_board(bench=[_poke(LUNATONE, hp=110, serial=2)]), working=with_luna)
    sv.state_value(_lunar_board(bench=[]), working=without)
    assert without["readiness"] < with_luna["readiness"]


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_an_UNGATED_body_reads_exactly_its_printed_roll_up():
    """The gate is a new REASON to price 0, never a new number. Asserted against `maxDamage` — the
    value this change replaced — because comparing the scalar to itself passes on any build."""
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
    """Conjoined Beams prints 130 with ``damageMax=280``, and the bonus IS reachable through this read
    on one character: at ``bound="max"`` readiness would price 280 for a body that lands 130."""
    model = _model(_player(active=_poke(METAGROSS, hp=170, energies=[E_P, E_P]), prize=4),
                   _player(active=_poke(DRAGAPULT, hp=320, serial=9), prize=4),
                   deck=[METAGROSS, E_P, E_P])
    paying = model.mine.attack_payoff(model.mine.active)
    assert paying == (CONJOINED_BEAMS, 130.0), "the conditional +150 leaked into the payoff"
    assert model.mine.active.stat.maxDamage == 130     # it was never in the roll-up either


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_the_gated_bodys_odds_are_asked_about_the_attack_that_actually_pays():
    """Payoff and odds must name the SAME attack: pairing one attack's damage with another attack's
    probability is the saturation defect the payoff read was split out to avoid."""
    model = _lunar_board(bench=[_poke(LUNATONE, hp=110, serial=2)])
    assert model.mine.attack_payoff(model.mine.active).attack_id == COSMIC_BEAM


# ── the `hand` LEDGER: supply against demand (Issue #400 Phase 2) ────────────────────────────────


def _fund_attack_resolution(*, slots, covering_card: bool):
    """``slots`` live `fund_attack` slots, optionally covered by one held Energy — minimised to the
    two facts the ledger reads: how much the position NEEDS and how much the hand COVERS."""
    from common import needs
    return needs.Resolution(
        slots=tuple(needs.Slot("fund_attack", 8.0, n, f"active:unit{n}") for n in range(slots)),
        eligibility=(frozenset(range(slots)),) if covering_card else (),
        resupply=(0.0,) * slots,
        hand_ids=(E_F,) if covering_card else (),
        latent_worth=0.0)


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_attaching_an_energy_that_retires_two_fund_slots_is_a_GAIN_not_a_loss():
    """Two `fund_attack` slots are 16 Worth of DEMAND and one held Energy 8 of SUPPLY, so attaching it
    is worth +8. Supply alone read -8 — the sign inversion of Issue #400 Phase 2."""
    before = sv.hand(**_hand_legs_of(_fund_attack_resolution(slots=2, covering_card=True)))
    after = sv.hand(**_hand_legs_of(_fund_attack_resolution(slots=0, covering_card=False)))
    from common.card_worth import Worth
    assert after - before == pytest.approx(sv.worth_to_prizes(Worth(8.0))), (
        "attaching the Energy retires 16 Worth of demand at a cost of 8 Worth of supply")
    assert after > before, "the attach must be a GAIN — this is the whole defect"


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_a_play_that_retires_no_need_is_still_charged_its_hold():
    """The ADR-0097 counterweight, preserved: a card that covers and retires nothing still costs its
    latent Worth to play, so the demand leg cannot be read as every play being free now."""
    from common import needs
    holding = needs.Resolution(slots=(), eligibility=(), resupply=(), hand_ids=(E_F,),
                               latent_worth=9.0)
    spent = needs.Resolution(slots=(), eligibility=(), resupply=(), hand_ids=(), latent_worth=0.0)
    from common.card_worth import Worth
    assert (sv.hand(**_hand_legs_of(spent)) - sv.hand(**_hand_legs_of(holding))
            == pytest.approx(-sv.worth_to_prizes(Worth(9.0))))


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_demand_half_excludes_FUEL_because_the_supply_half_does():
    """`needs._keep_slot_dp` assigns over the non-pitch slots only, so counting a fuel slot as demand
    would credit its retirement against a supply that never credited holding the fuel."""
    from common import needs
    with_fuel = needs.Resolution(
        slots=(needs.Slot("fund_attack", 8.0, 0, "active:unit0"),
               needs.Slot("fuel", 8.0, 99, "fuel", supplied_by_pitch=True)),
        eligibility=(), resupply=(0.0, 0.0), hand_ids=(), latent_worth=0.0)
    without = needs.Resolution(
        slots=(needs.Slot("fund_attack", 8.0, 0, "active:unit0"),),
        eligibility=(), resupply=(0.0,), hand_ids=(), latent_worth=0.0)
    assert (_hand_legs_of(with_fuel)["slot_demand"]
            == _hand_legs_of(without)["slot_demand"] == 8.0)


def _hand_legs_of(resolution):
    """`_hand_legs` over a bare Resolution — the extractor reads `model.mine.needs` and nothing else."""
    return sv._hand_legs(SimpleNamespace(mine=SimpleNamespace(needs=resolution)))


def _hand_reading_supplier():
    """A board-bound `needs` supplier whose Resolution is a pure function of MY HAND: one
    `fund_attack` slot per held Energy, so its legs cannot coincide across two different hands."""
    def supplier(obs, my_index):
        seat = ((obs.get("current") or {}).get("players") or [{}])[my_index] or {}
        hand = list(seat.get("hand") or ())
        energy = [c for c in hand if c.get("id") == E_F]
        # DEMAND tracks the Energy; latent Worth tracks the WHOLE hand. With `eligibility=()` there is
        # no assignment, so a non-Energy card is a clean gain — a property of this stub, not of `hand`.
        return _needs.Resolution(
            slots=tuple(_needs.Slot("fund_attack", 8.0, i, f"active:unit{i}")
                        for i in range(len(energy))),
            eligibility=(), resupply=(0.0,) * len(energy),
            hand_ids=tuple(c["id"] for c in hand),
            latent_worth=float(len(hand)))
    return supplier


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_hand_legs_MOVE_when_the_hand_moves_across_a_rebuild():
    """Under the pinned build every hypothetical inherited the ROOT board's Resolution, so these
    numbers were CONSTANT across a whole `compose()` call. It-changed would pass on that build too."""
    import copy
    me = _player(active=_poke(MEGA_LUC, hp=340), hand=[E_F, E_F], prize=4)
    opp = _player(active=_poke(DRAGAPULT, hp=320, serial=9), prize=4)
    model = _model(me, opp, needs=_hand_reading_supplier())

    full = sv._hand_legs(model)
    assert full["slot_demand"] == 16.0 and full["hand_worth"] == 2.0

    emptied = copy.deepcopy(model.source_obs)
    emptied["current"]["players"][0]["hand"] = []
    bare = sv._hand_legs(model.rebuilt(emptied))

    assert bare != full, (
        "`_hand_legs` is identical on a board with an EMPTY hand — the resolution was inherited "
        "from the originating board, which is the Issue #400 Phase 2 defect")
    assert bare["slot_demand"] == 0.0 and bare["hand_worth"] == 0.0


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_a_hand_ONLY_difference_moves_the_LEAF_so_a_fetch_can_never_difference_to_zero():
    """Two boards differing in nothing but my hand must produce different scalars, or a fetch prices
    at exactly 0.0 — and a 0 delta is never explored, not merely undervalued."""
    import copy
    me = _player(active=_poke(MEGA_LUC, hp=340), hand=[E_F, E_F], prize=4)
    opp = _player(active=_poke(DRAGAPULT, hp=320, serial=9), prize=4)
    model = _model(me, opp, needs=_hand_reading_supplier())

    # A NON-Energy card, so the fetch is pure latent Worth and books no new demand.
    drawn = copy.deepcopy(model.source_obs)
    drawn["current"]["players"][0]["hand"] = (
        drawn["current"]["players"][0]["hand"] + [{"id": MEGA_LUC, "serial": 4242,
                                                   "playerIndex": 0}])
    drawn["current"]["players"][0]["handCount"] = 3

    before, after = float(sv.state_value(model)), float(sv.state_value(model.rebuilt(drawn)))
    assert after != before, (
        "a board differing ONLY in my hand scored identically — every fetch differences to exactly "
        "0.0 and the beam never explores one")
    # Direction as well as movement: movement alone would be satisfied by a sign error.
    assert after > before
    assert sv._hand_legs(model.rebuilt(drawn))["slot_demand"] == 16.0, (
        "the control: demand is UNCHANGED, so the whole delta is the Worth of the fetched card")
