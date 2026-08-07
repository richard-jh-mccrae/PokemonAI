"""Issue #257 — the opponent's own ON-EVOLVE deck-search Energy acceleration reaches the CHARGED
Threat-Clock budget.

`_ACCEL_TAGS` routes exclusively into the SELF-side Attach Budget (Issue #137's charter), so an
opponent's on-evolve accel was invisible to the threat read. The credit is typed, lands only on a
form they would EVOLVE INTO, and stays off the worst-case ceiling, which already credits everything.
"""
import pytest

from common.cards import CardFunctions
from common.effects import CardEffects
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy.combat import UNCHARGED, CombatMath

DARK = 7                       # EnergyType.DARKNESS (src/cg/api.py)
DARK_ENERGY = 71               # a Basic {D} Energy card id
MORGREM, GRIMMSNARL = 647, 648
BIG = 900                      # Shadow Bullet {D}{D} 180 (verified, data/EN_Card_Data.csv)

#: A charged policy in the shape `_board` threads: one manual attach, no burst.
CHARGED = {"base_attach": 1, "burst_on_evo": 0}


def _combat(*, tagged=True, clauses=True):
    stats = DictCardStatProvider({
        MORGREM: CardStat(MORGREM, synthetic=True, name="Marnie's Morgrem", hp=90, energyType=DARK,
                          maxDamageCost=1, maxDamage=30, minAttackCost=1, attacks=()),
        GRIMMSNARL: CardStat(GRIMMSNARL, synthetic=True, name="Marnie's Grimmsnarl ex", hp=340,
                             evolvesFrom="Marnie's Morgrem", energyType=DARK, maxDamageCost=2,
                             maxDamage=180, minAttackCost=2, attacks=(BIG,)),
        DARK_ENERGY: CardStat(DARK_ENERGY, synthetic=True, name="Basic {D} Energy", energyType=DARK, cardType=5),
        1: CardStat(1, synthetic=True, name="My Body", hp=200),
    }, attacks={BIG: AttackStat(BIG, damage=180, cost=2, energyTypes=(DARK, DARK))})
    return CombatMath(stats,
                      functions=CardFunctions({GRIMMSNARL: ["energy_accel"]} if tagged else {}),
                      transients=None,
                      effects=CardEffects.load() if clauses else None)


MY_BODY = {"id": 1, "hp": 200}


def _morgrem(energy=0):
    return {"id": MORGREM, "hp": 90, "energies": [DARK_ENERGY] * energy}


@pytest.mark.req("REQ-OPPACCEL-0001")
def test_punk_up_makes_the_evolved_form_affordable_under_the_charged_budget():
    """Without the credit the charged read sees 0 attached + 1 manual attach against a two-Energy
    cost and calls the line unaffordable."""
    c = _combat()
    assert c.incoming(MY_BODY, [_morgrem(0)], 1, charged=CHARGED) == 180
    # ...and the credit is what does it: strip the clause and the same board reads nothing.
    assert _combat(clauses=False).incoming(MY_BODY, [_morgrem(0)], 1, charged=CHARGED) == 0


@pytest.mark.req("REQ-OPPACCEL-0002")
def test_the_credit_is_typed_not_merely_a_count():
    """Two colourless units satisfy the COUNT check and fail the colour check, so the clause carries
    the searched TYPE and the credit pays typed slots."""
    c = _combat()
    etype, units = c._evolve_accel(c._card_stat(GRIMMSNARL))
    assert (etype, units) == (DARK, 5)
    assert c.attack_type_payable(BIG, _morgrem(0), extra_type=etype, extra_units=units) is True
    assert c.attack_type_payable(BIG, _morgrem(0), wild_units=0) is False   # the un-credited read


@pytest.mark.req("REQ-OPPACCEL-0003")
def test_a_form_already_in_play_earns_nothing():
    """The trigger IS the hop ("when you play this Pokémon from your hand to evolve"), so a form
    already standing has had its chance and crediting it again manufactures reach."""
    c = _combat()
    standing = {"id": GRIMMSNARL, "hp": 340, "energies": []}
    assert c.incoming(MY_BODY, [standing], 1, charged=CHARGED) == 0
    # the same body one Energy short of {D}{D} still needs its own manual attach, nothing more
    assert c.incoming(MY_BODY, [dict(standing, energies=[DARK_ENERGY])], 1, charged=CHARGED) == 180


@pytest.mark.req("REQ-OPPACCEL-0004")
def test_it_fails_closed_without_a_tag_or_without_a_clause():
    """ADR-0067 mirrored: the Function Tag only ROUTES and the clause QUANTIFIES, so a tagged card
    the compendium says nothing about yields zero rather than a guess."""
    assert _combat(tagged=False).incoming(MY_BODY, [_morgrem(0)], 1, charged=CHARGED) == 0
    assert _combat(clauses=False).incoming(MY_BODY, [_morgrem(0)], 1, charged=CHARGED) == 0
    blind = _combat()
    blind.effects = None
    assert blind._evolve_accel(blind._card_stat(GRIMMSNARL)) == (None, 0)


@pytest.mark.req("REQ-OPPACCEL-0005")
def test_the_ceiling_policies_are_untouched():
    """The worst-case readings already credit a form's biggest attack, so an accel has nothing to add
    and must not move a catastrophe-grade boolean."""
    for policy in (None, UNCHARGED):
        with_clause = _combat().incoming(MY_BODY, [_morgrem(0)], 1, charged=policy)
        without = _combat(clauses=False).incoming(MY_BODY, [_morgrem(0)], 1, charged=policy)
        assert with_clause == without, f"policy {policy!r} moved"


@pytest.mark.req("REQ-OPPACCEL-0006")
def test_the_shipped_card_is_tagged_and_claused_at_source():
    """Pinned against the SHIPPED tables rather than a fixture, so a rebuild dropping either half
    fails here."""
    from pathlib import Path
    import json
    repo = Path(__file__).resolve().parents[2]
    tags = json.loads((repo / "src" / "common" / "card_functions.json").read_text(encoding="utf-8"))
    assert "energy_accel" in tags["648"]
    clause = next(c for c in CardEffects.load().clauses(648) if c["kind"] == "accel")
    assert clause["trigger"] == "on_evolve" and clause["source"] == "deck"
    assert clause["amount"] == 5 and clause["energy_type"] == DARK
