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
  * Basic Energy card ids: 2 = {R}, 5 = {P}, 7 = {D}, and {F} is added here as 6 ({W} as 3).
  * Prize values: Mega ex 3, ex 2, else 1 (`docs/rules.md` §6).

Issue #281 adds four more, every field read off `data/EN_Card_Data.csv` (the numbers are Card IDs):
  * Mega Starmie ex (1031) Stage 1 *Mega Pokémon ex*, evolvesFrom **Staryu**, HP 330, {W},
    Weakness {L} — Jetting Blow ``{W}`` 120 (+50 to one Benched) / Nebula Beam ``●●●`` 210,
    whose text is *"isn't affected by Weakness or Resistance, or by any effects on your opponent's
    Active"* → `ignoresWeakness` + `ignoresResistance` + `ignoresEffects`.
  * Gouging Fire ex (46) Basic *Pokémon ex*, HP 230, {R}, **Weakness {W}** — Heat Blast ``{R}●``
    60 / Blaze Blitz ``{R}{R}●`` 260. The under-claim defender: Jetting Blow's printed 120 misses,
    its doubled 240 does not.
  * Crustle (345, DRI) Stage 1, HP 150, {G}, Weakness {R}, Ability *Mysterious Rock Inn*: *"Prevent
    all damage done to this Pokémon by attacks from your opponent's Pokémon {ex}"* →
    `preventsDamageFrom="ex"`. The over-claim defender.
  * Larry's Braviary (1008) Stage 1, HP 130, {C}, Weakness {L}, **Resistance {F}** — the −30
    defender (`docs/rules.md` §5: a uniform flat −30 in this set).

Issue #280 adds ONE, and it is the attacker the Damage Formula's context exists for:
  * Alakazam (743, MEG 56) Stage 2, evolvesFrom **Kadabra**, HP 140, {P}, Weakness {D},
    Resistance {F}, Retreat 1 — **Powerful Hand** ``{P}``, printed damage *n/a*:
    *"Place 2 damage counters on your opponent's Active Pokémon for each card in your hand."*
    Read through `card_text.parse_attack_scaling`, that sentence is
    ``("atk_hand", 20, True, None)`` — the Damage Formula scaler ``atk_hand`` at **20 per card**
    (2 counters), and the trailing ``True`` is *counter-placement*, which
    `provider.build_attack_stats` turns into ``ignoresWeakness/Resistance/Effects`` because
    counters are not damage. So this attacker's output is EXACTLY ``20 x hand`` with no
    Weakness/Resistance leg to disentangle, which is what makes it the clean instrument for a
    context test. Rank 2 by play-rate in the tracked meta (`docs/matchups/alakazam.md`).
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

COLORLESS, GRASS, FIRE, WATER = 0, 1, 2, 3
LIGHTNING, PSYCHIC, FIGHTING, DARKNESS, DRAGON = 4, 5, 6, 7, 9
DRAGAPULT, MUNKIDORI, RIOLU, MEGA_LUC = 121, 112, 677, 678
MEGA_STARMIE, GOUGING_FIRE, CRUSTLE, BRAVIARY = 1031, 46, 345, 1008
ALAKAZAM = 743
JET_HEADBUTT, PHANTOM_DIVE, AURA_JAB, MEGA_BRAVE = 9121, 9122, 982, 983
JETTING_BLOW, NEBULA_BEAM, SUPERB_SCISSORS, CLUTCH = 91031, 91032, 9345, 91008
HEAT_BLAST, BLAZE_BLITZ, POWERFUL_HAND = 946, 947, 9743
E_R, E_P, E_F, E_D, E_W = 2, 5, 6, 7, 3

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
    # ── Issue #281's damage-model cast: an attacker whose damage MOVES with the defender ──────
    MEGA_STARMIE: CardStat(MEGA_STARMIE, name="Mega Starmie ex", hp=330, megaEx=True,
                           energyType=WATER, weakness=LIGHTNING, evolvesFrom="Staryu",
                           maxDamage=210, maxDamageCost=3, minAttackCost=1, minCostDamage=120,
                           benchSnipeDamage=50, attacks=(JETTING_BLOW, NEBULA_BEAM), cardType=0),
    GOUGING_FIRE: CardStat(GOUGING_FIRE, name="Gouging Fire ex", hp=230, ex=True,
                           energyType=FIRE, weakness=WATER, maxDamage=260, maxDamageCost=3,
                           minAttackCost=2, minCostDamage=60,
                           attacks=(HEAT_BLAST, BLAZE_BLITZ), cardType=0),
    CRUSTLE: CardStat(CRUSTLE, name="Crustle", hp=150, energyType=GRASS, weakness=FIRE,
                      evolvesFrom="Dwebble", preventsDamageFrom="ex", maxDamage=120,
                      maxDamageCost=3, minAttackCost=3, minCostDamage=120,
                      attacks=(SUPERB_SCISSORS,), cardType=0),
    BRAVIARY: CardStat(BRAVIARY, name="Larry's Braviary", hp=130, energyType=COLORLESS,
                       weakness=LIGHTNING, resistance=FIGHTING, evolvesFrom="Larry's Rufflet",
                       maxDamage=50, maxDamageCost=2, minAttackCost=2, minCostDamage=50,
                       attacks=(CLUTCH,), cardType=0),
    # ── Issue #280's context cast: an attacker whose damage IS a context variable ──────────────
    ALAKAZAM: CardStat(ALAKAZAM, name="Alakazam", hp=140, stage2=True, evolvesFrom="Kadabra",
                       energyType=PSYCHIC, weakness=DARKNESS, resistance=FIGHTING,
                       maxDamage=0, maxDamageCost=1, minAttackCost=1, minCostDamage=0,
                       handSizeDamage=20, attacks=(POWERFUL_HAND,), cardType=0),
    E_W: CardStat(E_W, name="Basic {W} Energy", cardType=5, energyType=WATER),
    E_R: CardStat(E_R, name="Basic {R} Energy", cardType=5, energyType=FIRE),
    E_P: CardStat(E_P, name="Basic {P} Energy", cardType=5, energyType=PSYCHIC),
    E_F: CardStat(E_F, name="Basic {F} Energy", cardType=5, energyType=FIGHTING),
    E_D: CardStat(E_D, name="Basic {D} Energy", cardType=5, energyType=DARKNESS),
}
_ATTACKS = {
    JET_HEADBUTT: AttackStat(JET_HEADBUTT, damage=70, cost=1, energyTypes=(COLORLESS,)),
    PHANTOM_DIVE: AttackStat(PHANTOM_DIVE, damage=200, cost=2, energyTypes=(FIRE, PSYCHIC)),
    AURA_JAB: AttackStat(AURA_JAB, damage=130, cost=1, energyTypes=(FIGHTING,)),
    MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=2, energyTypes=(FIGHTING, FIGHTING)),
    JETTING_BLOW: AttackStat(JETTING_BLOW, damage=120, cost=1, energyTypes=(WATER,), benchSnipe=50),
    NEBULA_BEAM: AttackStat(NEBULA_BEAM, damage=210, cost=3,
                            energyTypes=(COLORLESS, COLORLESS, COLORLESS),
                            ignoresWeakness=True, ignoresResistance=True, ignoresEffects=True),
    SUPERB_SCISSORS: AttackStat(SUPERB_SCISSORS, damage=120, cost=3,
                                energyTypes=(GRASS, COLORLESS, COLORLESS), ignoresEffects=True),
    CLUTCH: AttackStat(CLUTCH, damage=50, cost=2, energyTypes=(COLORLESS, COLORLESS)),
    HEAT_BLAST: AttackStat(HEAT_BLAST, damage=60, cost=2, energyTypes=(FIRE, COLORLESS)),
    BLAZE_BLITZ: AttackStat(BLAZE_BLITZ, damage=260, cost=3,
                            energyTypes=(FIRE, FIRE, COLORLESS)),
    # Counter placement, so all three ignore flags are set — see the module docstring. Printed 0:
    # with no context this attack deals NOTHING, which is precisely the flat axis Issue #280 removes.
    POWERFUL_HAND: AttackStat(POWERFUL_HAND, damage=0, cost=1, energyTypes=(PSYCHIC,),
                              scaleVar="atk_hand", scalePerUnit=20,
                              ignoresWeakness=True, ignoresResistance=True, ignoresEffects=True),
}
DECK = [E_F] * 6 + [RIOLU] * 3 + [MEGA_LUC] * 3 + [MUNKIDORI]

#: The deck's DECLARED Roles as Worth (`card_worth.ROLE_TIER`), supplied through the model's
#: `role_worth=` resolver. Roles are declaration, not card data — `card_worth.role_value` says so
#: outright ("the Pilot supplies ``roles``") and `CardStat` carries no such field — so a fixture that
#: tried to put them on the stat would be testing an API that does not exist.
_ROLE_WORTH = {MEGA_LUC: ROLE_TIER["win_condition"], RIOLU: ROLE_TIER["win_condition_base"],
               MUNKIDORI: ROLE_TIER["engine"], DRAGAPULT: ROLE_TIER["primary_attacker"],
               MEGA_STARMIE: ROLE_TIER["win_condition"]}

#: Issue #282's two boost cards, as the ``(amount, attackerEnergyType|None, vsExOnly)`` triple
#: `CardStat.damageBoost` / `damageBoostType` / `damageBoostVsEx` carries and `strategy/damage.py`
#: consumes. Written as the triple rather than as a `CardStat` row because the boost reaches a
#: snapshot through the tracker, never through a card in a zone — and the triples themselves are
#: pinned against the REAL 1267-card pool one seam over
#: (`tests/scouting/test_tool_holder_facts.py`: `carriers("damageBoost") == {1141: 30, 1158: 50,
#: 1171: 30, 1211: 40}`), so these are a restatement of a parsed fact, not a second opinion about it.
#:
#: Premium Power Pro (1141, **Item**), verified at `data/EN_Card_Data.csv`: *"During this turn,
#: attacks used by your {F} Pokémon do 30 more damage to your opponent's Active Pokémon (before
#: applying Weakness and Resistance)."* — amount 30, attacker-type gate {F}, no defender gate.
POWER_PRO = (30, FIGHTING, False)
#: Black Belt's Training (1211, **Supporter**), same source: *"During this turn, attacks used by your
#: Pokémon do 40 more damage to your opponent's Active Pokémon {ex} (before applying Weakness and
#: Resistance)."* — amount 40, no attacker-type gate, defender-{ex} gate. The {ex} scope INCLUDES a
#: Mega Evolution Pokémon ex (`docs/rulebook.txt` L337: *"Mega Evolution Pokémon ex are considered to
#: be Pokémon ex, so any card effects that affect Pokémon ex also affect Mega Evolution Pokémon ex"*).
BLACK_BELT = (40, None, True)


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


class _Boosts:
    """`TurnBoostTracker`'s one duck-typed method — the shape `StateModel.build` resolves per seat.

    A this-turn Trainer boost is a LOG fact, not a board one ("During this turn, attacks used by
    your … Pokémon do N more damage" leaves no trace in any zone once the card reaches the discard),
    so the tracker is how it reaches a snapshot at all. Side 0 is mine on every board in this file."""

    def __init__(self, boosts=()):
        self._boosts = tuple(boosts)

    def boosts_for(self, side):
        return self._boosts if side == 0 else ()


def _model(me, opp, *, energy_attached=False, turn=5, needs=None, boosts=None):
    obs = {"current": {"players": [me, opp], "yourIndex": 0, "turn": turn,
                       "energyAttached": energy_attached, "supporterPlayed": False,
                       "stadium": []}, "logs": []}
    return StateModel.build(obs, combat=_combat(), deck=DECK, needs=needs,
                            role_worth=_ROLE_WORTH.get,
                            turn_boosts=None if boosts is None else _Boosts(boosts))


def _lucario_board(*, my_energies=(), my_hp=340, bench=(), my_prizes=4, their_prizes=4,
                   their_active=None, hand=(), energy_attached=False, boosts=None):
    """MY Mega Lucario ex Active against THEIR Dragapult ex — the fixture every monotonicity case
    perturbs by exactly one fact."""
    return _model(
        _player(active=_poke(MEGA_LUC, hp=my_hp, energies=my_energies), bench=list(bench),
                hand=list(hand), prize=my_prizes),
        _player(active=their_active or _poke(DRAGAPULT, hp=320, energies=[E_R, E_P], serial=9),
                prize=their_prizes),
        energy_attached=energy_attached, boosts=boosts)


def _starmie_board(their_active, *, my_energies=(E_W,), boosts=None):
    """MY Mega Starmie ex Active against a chosen defender, with the turn's Energy already spent so
    the Attach Budget adds nothing — the board is exactly what is attached, and reachability is
    therefore a fact about the fixture rather than about the deck's colours."""
    return _model(
        _player(active=_poke(MEGA_STARMIE, hp=330, energies=list(my_energies)), prize=4),
        _player(active=their_active, prize=4),
        energy_attached=True, boosts=boosts)


def _alakazam_board(their_hand: int, *, my_active=None, my_hand=()):
    """THEIR Alakazam Active — the ``atk_hand`` attacker — against a chosen body of mine.

    Their hand is a COUNT with no contents, which is the engine's own shape for a hidden zone
    (`TheirSide.hand_size` reads ``handCount``, and the opponent's ``hand`` is never populated);
    mine is real cards. So the two directions of the Damage Formula's hand variable are
    DISTINGUISHABLE on this board by construction — which is what lets a direction error be a test
    failure rather than a plausible-looking number.

    One {P} is attached, which is exactly Powerful Hand's cost, so affordability is settled and the
    only thing moving between boards is the hand."""
    theirs = _player(active=_poke(ALAKAZAM, hp=140, energies=[E_P], serial=9), prize=4)
    theirs["hand"], theirs["handCount"] = [], int(their_hand)
    return _model(
        _player(active=my_active or _poke(MEGA_LUC, hp=340), hand=list(my_hand), prize=4),
        theirs)


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
    assert benched["survival"] > alone["survival"] + sv.LOSS_PRIZES / 2.0, (
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


# ── `threat`'s reachability gate asks the DAMAGE MODEL, not the printed number (Issue #281) ───────
#
# The gate is a STEP, so a wrong reading of it is not a mis-scaling — it is the difference between
# the family answering and the family returning `()`. It was wrong in BOTH directions at once,
# because the printed number knows nothing about who is being hit.


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
    """The UNDER-claim, and `mega_starmie`'s own doctrine: *lead Jetting Blow when the Active is
    Water-weak with <= 240 HP*. Jetting Blow prints 120 and Gouging Fire ex has 230 HP, so the
    printed gate says "cannot reach" — while the rules say Weakness doubles it to 240 and the
    Knock Out is there (`docs/rules.md` §5; S&V prints x2, not +N).

    TWO controls, because the gate must be shown to still say NO:

    * ``out_of_reach`` — **the same card**, chipped to 250 rather than 230. One fact differs
      (remaining HP), and 240 does not reach it. This is the honest one-fact control.
    * ``not_weak`` — a different defender at the same 230 HP that is not {W}-weak. More than the
      Weakness type differs between the two cards, so this one is a sanity check on the direction
      rather than a controlled comparison, and is labelled as such."""
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
    """The OVER-claim, from `docs/matchups/crustle.md` Seam 1: *a pure-ex deck cannot damage an
    active Crustle at all*. Mega Lucario ex is a Pokémon {ex} (`docs/rulebook.txt` L337 — a Mega
    Evolution Pokémon ex IS an {ex}), Crustle's *Mysterious Rock Inn* prevents all damage from
    attacks by opponent {ex}, and Mega Brave carries no ignore flag. Printed 270 against 150 HP
    reads as pressure; the real damage is 0.

    Nebula Beam is the standing proof that this is a per-ATTACK fact and not a per-card one — it
    *"isn't affected by ... any effects on your opponent's Active"* and lands its 210 through the
    same wall — so it is asserted here rather than left to the oracle's own tests."""
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
    """Resistance is a uniform flat −30 in this set (`docs/rules.md` §5, project-verified over 47
    cards), and it is enough on its own to turn an exact-lethal into a miss: Aura Jab prints 130
    into Larry's Braviary's 130 HP, and Braviary resists {F}."""
    board = _lucario_board(my_energies=[E_F], energy_attached=True,
                           their_active=_poke(BRAVIARY, hp=130, serial=9))
    printed, modelled = _reach(board)
    assert printed == 130, "Aura Jab's printed damage — the incumbent's answer, unchanged"
    assert modelled == 100, "130 − 30 Resistance"
    assert _threat_of(board) == 0.0


@pytest.mark.req("REQ-STATEVALUE-0010")
def test_the_new_read_keeps_the_incumbents_BUDGET_affordability_filter():
    """The sibling swaps the damage read and NOTHING else — the affordability filter is the
    incumbent's, unchanged. With one {W} attached and the turn's attach already spent, the
    three-Energy Nebula Beam is not reachable and may not enter EITHER read; fund it and it enters
    both.

    This is why `can_ko_affordable` was NOT composed for the gate — it asks affordability of the
    *attached* Energy, while this family's reachability has always been the Attach BUDGET. Two
    opinions about affordability inside one family is what the sole-supplier ruling forbids."""
    starved = _starmie_board(_poke(CRUSTLE, hp=150, serial=9), my_energies=(E_W,))
    printed, modelled = _reach(starved)
    assert printed == 120, "only Jetting Blow is reachable on one Energy"
    assert modelled == 0.0, "and Jetting Blow's Active damage is prevented — its bench rider is a "\
                            "separate path and belongs to `attack_ev`"

    funded = _starmie_board(_poke(CRUSTLE, hp=150, serial=9), my_energies=(E_W, E_W, E_W))
    assert _reach(funded)[0] == 210, "three Energy reaches Nebula Beam, so the printed max moves"


# ── `survival` threads the DAMAGE CONTEXT into its clocks (Issue #280) ────────────────────────────
#
# `survival` takes two damage reads — the `turns_to_ko_me` clock and `_predicted_loss`'s Incoming —
# and both took a `context` nobody gave them, so every context-scaled term of the Damage Formula
# contributed 0 on THEIR attack: an opponent holding twelve cards and one holding two produced the
# same `turns_to_ko_me`. The direction is THEIRS — their attack on my body — and getting it
# backwards reads MY hand as THEIR damage scaler, which is silently plausible. So every case below
# is built on a board whose two hands DIFFER.


def _survival_of(model) -> float:
    working: dict = {}
    sv.state_value(model, working=working)
    return working["survival"]


@pytest.mark.req("REQ-STATEVALUE-0010")
def test_survivals_clock_shortens_as_THEIR_hand_grows():
    """Powerful Hand deals ``20 x hand`` and nothing else (module docstring, verified at source), so
    against my Mega Lucario ex's 340 HP the ACCUMULATING clock (ADR-0071 decision 4) is exactly
    ``ceil(340 / (20 x hand))``, answering ``max_t + 1 = 9`` beyond the 8-turn horizon.

    Without the context that scaler contributes 0, Powerful Hand's PRINTED damage is 0, and every
    hand size answers 9 — the flat axis this issue exists to remove. The ladder is asserted
    value-by-value rather than as a trend because the trend alone would also pass on a term that
    moved for some other reason."""
    ladder = {1: 9, 2: 9, 3: 6, 4: 5, 5: 4, 6: 3, 9: 2, 17: 1}
    for hand, turns in ladder.items():
        exposed = sv._exposed_bodies(_alakazam_board(hand))
        assert len(exposed) == 1, "one Active, empty Bench — the ladder is about one body's clock"
        assert exposed[0].turns_to_ko_me == turns, (
            f"their hand {hand} => {20 * hand}/turn into 340 HP => turn {turns}")


@pytest.mark.req("REQ-STATEVALUE-0010")
def test_the_survival_clock_reads_THEIR_hand_and_never_MINE():
    """The direction regression the issue asks for, stated as a pair of boards that a single shared
    context would price EXACTLY BACKWARDS rather than merely differently.

    Both boards hold the same twelve-and-two hands; they differ only in who holds which. With
    ``attacker="theirs"`` the clock follows THEIR hand (12 cards => 240/turn => turn 2; 2 cards =>
    40/turn => the body survives the horizon). With ``attacker="mine"`` the two answers swap. There
    is no assignment of one dict to both directions that passes this."""
    theirs_big = _alakazam_board(12, my_hand=[E_F, E_F])
    mine_big = _alakazam_board(2, my_hand=[E_F] * 12)

    ctx = theirs_big.damage_context(attacker="theirs")
    assert ctx["atk_hand"] == theirs_big.theirs.hand_size == 12, "the ATTACKER here is theirs"
    assert ctx["def_hand"] == theirs_big.mine.hand_size == 2, "my hand is the DEFENDER's hand"

    assert sv._exposed_bodies(theirs_big)[0].turns_to_ko_me == 2
    assert sv._exposed_bodies(mine_big)[0].turns_to_ko_me == 9
    # Mega Lucario ex yields 3 prizes (`docs/rules.md` §6), and one body ranks first, so `survival`
    # is `-(3 x halve(t - 1))` on both boards.
    assert _survival_of(theirs_big) == pytest.approx(-3.0 * 0.5)
    assert _survival_of(mine_big) == pytest.approx(-3.0 / 256)
    assert _survival_of(theirs_big) < _survival_of(mine_big)


@pytest.mark.req("REQ-STATEVALUE-0010")
def test_the_bench_empty_doom_reads_their_SCALED_damage_too():
    """`_predicted_loss` is the second call site and the more consequential one: it is a TERMINAL
    term at `-LOSS_PRIZES`, so damage it cannot see is a game loss it cannot see.

    Munkidori's 70 HP sits between a three-card hand (60) and a four-card hand (80), so one card
    decides the rung. The third board is the direction control: twelve cards in MY hand is
    ``def_hand`` here and must move nothing at all."""
    safe = _alakazam_board(3, my_active=_poke(MUNKIDORI, hp=70, serial=3))
    doomed = _alakazam_board(4, my_active=_poke(MUNKIDORI, hp=70, serial=3))
    my_hand_big = _alakazam_board(3, my_active=_poke(MUNKIDORI, hp=70, serial=3),
                                  my_hand=[E_F] * 12)

    assert sv._predicted_loss(safe) is False, "60 damage does not fell a 70 HP Active"
    assert sv._predicted_loss(doomed) is True, "80 does, and my Bench is empty (rules.md §7 case 2)"
    assert sv._predicted_loss(my_hand_big) is False, "MY hand is `def_hand` — it is not their damage"

    assert _survival_of(doomed) <= -sv.LOSS_PRIZES
    assert _survival_of(safe) > -sv.LOSS_PRIZES


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_more_cards_in_THEIR_hand_never_improves_survival():
    """The monotonicity class Issue #262 requires, on this issue's axis. Hands 1..12 keep the sweep
    clear of the bench-empty doom (340 HP needs a 17-card hand), so this is the POSITIONAL term
    alone."""
    values = [_survival_of(_alakazam_board(n)) for n in range(1, 13)]
    assert all(after <= before for before, after in zip(values, values[1:])), values
    assert values[-1] < values[0], "the axis is flat — the context is not reaching the clock"


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


# ── a live Trainer damage-BOOST reaches the scalar, gates and all (Issue #282) ────────────────────
#
# The class this guards is the epic's headline: *an unpriced effect is worse than a no-op*. `_PLAY`
# is modelled as "the card leaves hand" (`apply_option.KIND_COVERAGE`), so a boost card whose effect
# no term reads prices at MINUS the hand value of the card spent — playing Premium Power Pro would
# score as a mistake. The path that stops that is `_SideBase.damage_boosts` -> `SideFacts` ->
# `damage_context`'s `atk_boosts` -> `strategy/damage.py` -> #281's `best_reachable_damage_vs` ->
# `threat`, and every link of it shipped with Issues #279 and #281 rather than with this one.
#
# What did NOT ship is any assertion that the whole path holds END TO END, at the scalar. Each link
# is pinned in isolation — `test_damage_context.py` pins the context key, `test_tool_holder_facts.py`
# pins the parsed triples against the real pool, `test_damage_oracle.py` pins the oracle's gates —
# and a chain of separately-green links is exactly the shape that breaks silently in the middle. So
# these assert on `state_value` itself, and each one is built so that the GATE is the only thing
# standing between the fixture and a crossing: a broken gate is a failure here, not a plausible
# number.


def _boosts_of(model) -> tuple:
    return model.damage_context(attacker="mine")["atk_boosts"]


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_a_live_boost_crosses_a_breakpoint_and_the_scalar_moves_for_it():
    """Premium Power Pro's +30 turns Mega Brave's 270 into the 300 that reaches a 300 HP Dragapult ex.

    The card leaving my hand is the only thing `_PLAY` structurally models, so without this the play
    is priced at a hand loss and nothing else. With it the boost enters through exactly ONE family —
    `threat`, whose reachability gate is #281's `best_reachable_damage_vs` — which is asserted here
    as well as the total, because a fact that moved two families would be double-counted.

    Mega Lucario ex is {F} (`data/EN_Card_Data.csv`), so Power Pro's attacker-type gate is met;
    Dragapult ex carries no Weakness to {F} in this fixture, so 270 and 300 are the raw numbers with
    no W/R leg to disentangle."""
    plain = _lucario_board(my_energies=[E_F, E_F], energy_attached=True,
                           their_active=_poke(DRAGAPULT, hp=300, serial=9))
    boosted = _lucario_board(my_energies=[E_F, E_F], energy_attached=True,
                             their_active=_poke(DRAGAPULT, hp=300, serial=9), boosts=[POWER_PRO])

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
def test_a_live_boost_that_crosses_nothing_leaves_the_scalar_untouched():
    """The other half of the same claim, and the one that keeps `threat` a GATE rather than a slope.

    Against a 260 HP Dragapult ex, Mega Brave's 270 already reaches, so the boost buys nothing that
    this family prices — the extra damage above lethal is overkill, and converting the exposure is
    `attack_ev`'s job at the terminal action. The scalar must therefore be BIT-identical, not merely
    close: a boost that nudged the board value would be pricing overkill as position."""
    plain = _lucario_board(my_energies=[E_F, E_F], energy_attached=True,
                           their_active=_poke(DRAGAPULT, hp=260, serial=9))
    boosted = _lucario_board(my_energies=[E_F, E_F], energy_attached=True,
                             their_active=_poke(DRAGAPULT, hp=260, serial=9), boosts=[POWER_PRO])
    assert _reach(boosted)[1] == _reach(plain)[1] + 30, "the boost IS reaching the damage read"
    assert sv.state_value(boosted) == sv.state_value(plain)


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_the_attacker_TYPE_gate_refuses_a_boost_the_attacker_does_not_qualify_for():
    """*"attacks used by your {F} Pokémon"* — Premium Power Pro pays a {F} attacker and nobody else.

    The fixture is one gate away from a crossing on purpose: Mega Starmie ex reaches Jetting Blow's
    120 against Larry's Braviary's 130 HP, and 120 + 30 = 150 would cross. The control is the SAME
    amount on the SAME board with the gate re-pointed at the attacker's own {W} — a synthetic probe,
    not a card, and labelled as one — so the only difference between passing and failing is the gate
    itself rather than two different boards being compared."""
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
    """*"do 40 more damage to your opponent's Active Pokémon {ex}"* — Black Belt's Training, and the
    rulebook-337 case the `{ex}` scope exists to get right.

    `docs/rulebook.txt` L337: *"Mega Evolution Pokémon ex are considered to be Pokémon ex, so any
    card effects that affect Pokémon ex also affect Mega Evolution Pokémon ex."* Mega Starmie ex
    carries `megaEx` and not `ex`, so a gate written as `stat.ex` would read it as an ordinary
    Pokémon and silently drop 40 damage against the single biggest target in the format — which is
    asserted below rather than assumed, because that is the whole content of the case.

    The non-ex control is the same attacker, the same boost, and a defender the boost WOULD have
    crossed: Aura Jab's 130 against Larry's Braviary is 100 after its flat −30 {F} Resistance
    (`docs/rules.md` §5), and 130 + 40 − 30 = 140 reaches its 130 HP. It stays at 100 because
    Braviary is not an {ex}."""
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


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_with_no_boost_in_play_the_context_is_EMPTY_and_the_scalar_is_unmoved():
    """The regression half: a board with no live boost must score exactly as it did before any of
    this, and an EMPTY tracker must be indistinguishable from no tracker at all.

    Bit-identical rather than approximate, and over the whole per-family breakdown rather than the
    total, because the failure being guarded is a term that quietly gained a boost-shaped leg — which
    a total could hide by cancellation."""
    no_tracker = _lucario_board(my_energies=[E_F, E_F], energy_attached=True)
    empty_tracker = _lucario_board(my_energies=[E_F, E_F], energy_attached=True, boosts=[])
    assert _boosts_of(no_tracker) == () == _boosts_of(empty_tracker)

    without, empty = {}, {}
    assert sv.state_value(no_tracker, working=without) == sv.state_value(empty_tracker,
                                                                        working=empty)
    assert without == empty


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


@pytest.mark.req("REQ-STATEVALUE-0010")
def test_on_real_frames_the_incumbent_printed_read_still_returns_a_PRINTED_number(corpus_models):
    """Issue #281's *incumbent untouched* guard, and the reason it is stated on the corpus rather
    than on a fixture: `best_reachable_damage` is the counterfactual leg of the attach marginal
    (ADR-0069 §2) and `attach_value` is corpus-RULED, so the claim that matters is about the boards
    the rulings were made on.

    Two properties rather than a re-implementation of the read (which would be a tautological join
    — ADR-0088), and BOTH halves of the incumbent's contract are covered:

    * the DAMAGE read — the value must be exactly the biggest number the attacks `reachable_attach`
      admits actually PRINT. A Weakness-doubled, Resistance-reduced or prevention-zeroed value is
      not, so the incumbent quietly acquiring the damage model fails here;
    * the AFFORDABILITY filter — the expected value is built from ``MySide.reachable_attach``, the
      model's own shipped accessor for that question, so a filter that silently widened (or
      narrowed to the cheapest attack) fails too. Composed from a different public accessor rather
      than a private re-derivation, which is what keeps it a check and not a copy.

    The last assertion is the positive control the negative claim needs (CLAUDE.md): on the same
    frames the NEW sibling must diverge from the incumbent somewhere. If it never did, everything
    above would be passing because nothing changed at all."""
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
    """Issue #280's wiring and fail-direction guard, on boards nobody designed for it.

    Three properties, all about the clock `survival` actually reads:

    * **The extractor asks the threaded question.** ``_exposed_bodies``' clock must equal the clock
      the model gives for the same body WITH their context. Composed from the model's own public
      accessor rather than re-derived, which is what keeps it a check and not a copy (Issue #281's
      incumbent guard has the same shape one side over).
    * **The direction is theirs.** ``atk_hand`` must be THEIR hand and ``def_hand`` MINE, asserted
      per frame with a positive control that the two actually differ somewhere — on a board where
      the hands happen to be equal, the assertion cannot fail however wrong the direction is.
    * **Monotone the safe way.** Every clock read reaches the oracle at ``bound="max"`` and every
      Damage Formula scaler the parser can emit ADDS, so threading the context can shorten a clock
      and never lengthen one. On a SURVIVAL read a longer clock is the one direction that must
      never appear from better information (ADR-0064's bounded pessimism).

      That monotonicity is PARSER-contingent rather than rule-contingent, and is asserted here
      rather than assumed for exactly that reason: `data/EN_Card_Data.csv` does contain
      *reducing* scaler text (*"does 30 less damage for each {C} in your opponent's Active
      Pokémon's Retreat Cost"*, *"does 60 less damage for each Energy attached to your opponent's
      Active Pokémon"*), and `card_text._SCALE_FAMILIES` has no pattern for either, so today they
      parse to no scaler at all and contribute 0. The day one does parse, this assertion is the
      thing that says so.

    The strict-shortening count is the positive control the first property needs (CLAUDE.md): where
    the blind and threaded clocks agree, "the extractor is threaded" and "the extractor is not"
    produce identical evidence.

    This sample carries no `handSizeDamage` attacker — measured, not assumed — so the issue's own
    archetype is covered by the sibling below, which scans the whole corpus for it."""
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
    """``(key, pilot, obs, my_index)`` for every corpus frame with a `handSizeDamage` attacker
    across the table — Issue #280's named archetype (`docs/matchups/alakazam.md`, rank 2 by
    play-rate), FOUND rather than assumed.

    Scans the whole index rather than reusing `corpus_models`' 40-frame sample, because the
    archetype is absent from that sample; the scan itself is card-id lookups against an
    already-built Stat Provider, not model builds, and measures ~0.6 s over the full corpus."""
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
    """Issue #280's headline case, on the boards it was filed about rather than on a fixture:
    *"an opponent holding twelve cards and one holding two produce the same `turns_to_ko_me`"*.

    Their hand is a COUNT and nothing else (`TheirSide.hand_size` reads ``handCount``), so the
    perturbation is exactly one integer — which is what makes this a controlled comparison on a real
    board rather than a second synthetic fixture wearing a corpus costume.

    Asserted as monotone non-increasing PER FRAME with at least one strict move across the set: a
    frame can be genuinely indifferent (my Active already falls on turn 1, or the scaling attacker
    is Benched behind a shut promotion gate), and demanding strictness everywhere would fail on
    correct behaviour. Measured: 8 frames carry the archetype and 3 of them move."""
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
