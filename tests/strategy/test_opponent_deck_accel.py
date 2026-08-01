"""Issue #257 — the opponent's own ON-EVOLVE deck-search Energy acceleration reaches the CHARGED
Threat-Clock budget.

`combat.incoming`'s charged policy assumed the opponent gets one manual attach per turn (plus the
Ignition-class colourless burst). Marnie's Grimmsnarl ex 648's Punk Up attaches **up to 5 Basic {D}
from the deck** when it is played to evolve — verified at `data/EN_Card_Data.csv` — and nothing in
the threat read saw it. The card was doubly invisible: `_ACCEL_TAGS` routes exclusively into the
*self-side* Attach Budget (Issue #137's charter), and `card_functions.json` had no entry for 648 at
all.

Three properties are pinned here, and the middle one is the point:

1. The credit lands, and it is TYPED — a {D} attack becomes payable, not merely countable.
2. It lands only on a form the opponent would EVOLVE INTO. The trigger is the hop; a body already in
   play has had its chance, and crediting it there would manufacture reach.
3. It is Effect-Clause-quantified and fails CLOSED — a tagged card the compendium says nothing about
   yields zero, which is ADR-0067's self-side rule mirrored. And it stays off the worst-case CEILING
   entirely: that policy already credits every attack a form can reach, so there is nothing to add.
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
        MORGREM: CardStat(MORGREM, name="Marnie's Morgrem", hp=90, energyType=DARK,
                          maxDamageCost=1, maxDamage=30, minAttackCost=1, attacks=()),
        GRIMMSNARL: CardStat(GRIMMSNARL, name="Marnie's Grimmsnarl ex", hp=340,
                             evolvesFrom="Marnie's Morgrem", energyType=DARK, maxDamageCost=2,
                             maxDamage=180, minAttackCost=2, attacks=(BIG,)),
        DARK_ENERGY: CardStat(DARK_ENERGY, name="Basic {D} Energy", energyType=DARK, cardType=5),
        1: CardStat(1, name="My Body", hp=200),
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
    """A bare Marnie's Morgrem evolves into Grimmsnarl ex and Punk Up pays for Shadow Bullet the same
    turn. Without the credit the charged read sees 0 attached + 1 manual attach against a {D}{D}
    cost and calls the line unaffordable — which is the under-read this issue names."""
    c = _combat()
    assert c.incoming(MY_BODY, [_morgrem(0)], 1, charged=CHARGED) == 180
    # ...and the credit is what does it: strip the clause and the same board reads nothing.
    assert _combat(clauses=False).incoming(MY_BODY, [_morgrem(0)], 1, charged=CHARGED) == 0


@pytest.mark.req("REQ-OPPACCEL-0002")
def test_the_credit_is_typed_not_merely_a_count():
    """Shadow Bullet costs {D}{D}, so two colourless units would satisfy the COUNT check and fail the
    colour check. Punk Up searches for Basic **{D}** specifically, so the clause carries the type and
    the credit pays the typed slots — the distinction the flat `+1` this replaces could never make."""
    c = _combat()
    etype, units = c._evolve_accel(c._card_stat(GRIMMSNARL))
    assert (etype, units) == (DARK, 5)
    assert c.attack_type_payable(BIG, _morgrem(0), extra_type=etype, extra_units=units) is True
    assert c.attack_type_payable(BIG, _morgrem(0), wild_units=0) is False   # the un-credited read


@pytest.mark.req("REQ-OPPACCEL-0003")
def test_a_form_already_in_play_earns_nothing():
    """The trigger IS the hop ("when you play this Pokémon from your hand to evolve"). A Grimmsnarl
    ex already standing on their board has had its Punk Up; crediting it again would manufacture
    reach out of a card that has already resolved."""
    c = _combat()
    standing = {"id": GRIMMSNARL, "hp": 340, "energies": []}
    assert c.incoming(MY_BODY, [standing], 1, charged=CHARGED) == 0
    # the same body one Energy short of {D}{D} still needs its own manual attach, nothing more
    assert c.incoming(MY_BODY, [dict(standing, energies=[DARK_ENERGY])], 1, charged=CHARGED) == 180


@pytest.mark.req("REQ-OPPACCEL-0004")
def test_it_fails_closed_without_a_tag_or_without_a_clause():
    """ADR-0067's rule, mirrored: the Function Tag only ROUTES, the clause quantifies. An untagged
    card is never inspected; a tagged card the compendium says nothing about yields ZERO rather than
    a guessed amount. Both matter — the tag alone cannot say 5, or {D}, or *when*."""
    assert _combat(tagged=False).incoming(MY_BODY, [_morgrem(0)], 1, charged=CHARGED) == 0
    assert _combat(clauses=False).incoming(MY_BODY, [_morgrem(0)], 1, charged=CHARGED) == 0
    blind = _combat()
    blind.effects = None
    assert blind._evolve_accel(blind._card_stat(GRIMMSNARL)) == (None, 0)


@pytest.mark.req("REQ-OPPACCEL-0005")
def test_the_ceiling_policies_are_untouched():
    """The worst-case readings already credit a form's biggest attack once it can pay its cheapest
    (ceiling) or unconditionally (the doom policy), so there is nothing for an accel to add — and an
    unnecessary credit on a catastrophe-grade boolean is exactly the kind of change that has to be
    ruled rather than absorbed. Byte-identical with and without the clause."""
    for policy in (None, UNCHARGED):
        with_clause = _combat().incoming(MY_BODY, [_morgrem(0)], 1, charged=policy)
        without = _combat(clauses=False).incoming(MY_BODY, [_morgrem(0)], 1, charged=policy)
        assert with_clause == without, f"policy {policy!r} moved"


@pytest.mark.req("REQ-OPPACCEL-0006")
def test_the_shipped_card_is_tagged_and_claused_at_source():
    """Issue #257's own acceptance item: 648 had NO entry in `card_functions.json`, so Punk Up was
    not merely unwired — it was untagged. Pinned against the shipped tables rather than a fixture, so
    a rebuild that drops either half fails here."""
    from pathlib import Path
    import json
    repo = Path(__file__).resolve().parents[2]
    tags = json.loads((repo / "src" / "common" / "card_functions.json").read_text(encoding="utf-8"))
    assert "energy_accel" in tags["648"]
    clause = next(c for c in CardEffects.load().clauses(648) if c["kind"] == "accel")
    assert clause["trigger"] == "on_evolve" and clause["source"] == "deck"
    assert clause["amount"] == 5 and clause["energy_type"] == DARK
