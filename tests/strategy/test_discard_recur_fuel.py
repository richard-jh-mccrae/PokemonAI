"""Threat-Clock unification S2 — the discard-recur FUEL primitive (design:
docs/plans/ADR-0078).

`CombatMath.discard_recur_fuel` reads the opponent's DISCARD as a fuel/recovery pool for a
`discard_energy_recur` line — the Threat Clock's first NET-NEW input. Verified card facts
(EN_Card_Data.csv): Mega Lucario ex (678) Aura Jab attaches up to 3 Basic {F} FROM ITS DISCARD to
its Bench; Archaludon ex (190) Assemble Alloy attaches up to 2 Basic {M} from its discard to its {M}
Pokémon. So a refueler taps its own discard as an extra energy reservoir beyond the 1 manual
attach/turn — faster (lower turns_to_afford) and more dangerous (higher incoming). The fuel is the
capped discard count of the LINE's own type. The primitive is pure; the live threat reads are
UNCHANGED (S2 is shadow-only — the shadow feeds a fuel-augmented body, deciding nothing).
"""
from common.cards import CardFunctions
from common.strategy.combat import CombatMath
from common.scouting.provider import CardStat, DictCardStatProvider

FIGHTING = 6
COLORLESS = 0
RIOLU = 677
MLUC = 678          # Mega Lucario ex — discard_energy_recur ({F}), one hop from Riolu
F_ENERGY_CARD = 6   # Basic {F} Energy, the CARD id (EnergyType.FIGHTING is also 6 —
                    # a coincidence in the data, never a rule; see pilot_helpers.poke)


def _combat(tags):
    stats = DictCardStatProvider({
        RIOLU: CardStat(RIOLU, synthetic=True, name='Riolu', hp=70, energyType=FIGHTING, maxDamageCost=1, attacks=()),
        MLUC: CardStat(MLUC, name="Mega Lucario ex", hp=340, evolvesFrom="Riolu",
                       energyType=FIGHTING, maxDamageCost=2, attacks=()),
    })
    return CombatMath(stats, functions=CardFunctions(tags), transients=None)


# REQ-RECUR-0001 — the fuel is the capped discard count of the LINE's own type (read off any form).
def test_fuel_is_the_capped_discard_count_of_the_line_type():
    c = _combat({MLUC: ["discard_energy_recur"]})
    # Read off the Riolu pre-evo: its LINE (→ Mega Lucario ex) carries the tag; 5 {F} in discard,
    # capped at the verified max reload (3) → 3.
    assert c.discard_recur_fuel({"id": RIOLU}, {FIGHTING: 5}) == 3
    assert c.discard_recur_fuel({"id": RIOLU}, {FIGHTING: 2}) == 2       # min(2, cap) = 2
    assert c.discard_recur_fuel({"id": MLUC}, {FIGHTING: 2}) == 2        # read off the recur body itself


# REQ-RECUR-0002 — zero without the tag, without fuel, on the wrong type, or on an unknown body.
def test_fuel_zero_without_tag_or_fuel_or_wrong_type():
    c = _combat({MLUC: ["discard_energy_recur"]})
    assert c.discard_recur_fuel({"id": RIOLU}, {FIGHTING: 0}) == 0       # nothing in discard
    assert c.discard_recur_fuel({"id": RIOLU}, {COLORLESS: 5}) == 0      # wrong type ({C}, not {F})
    assert c.discard_recur_fuel({"id": RIOLU}, {}) == 0                  # empty discard
    assert c.discard_recur_fuel(None, {FIGHTING: 5}) == 0
    assert c.discard_recur_fuel({"id": 99999}, {FIGHTING: 5}) == 0       # unknown body
    untagged = _combat({})
    assert untagged.discard_recur_fuel({"id": RIOLU}, {FIGHTING: 5}) == 0  # line carries no tag


# REQ-RECUR-0003 — fuel-blind (no functions/stats) fails open to 0.
def test_fuel_blind_fails_open():
    stats = DictCardStatProvider({MLUC: CardStat(MLUC, name="Mega Lucario ex", energyType=FIGHTING)})
    assert CombatMath(stats, functions=None).discard_recur_fuel({"id": MLUC}, {FIGHTING: 3}) == 0
