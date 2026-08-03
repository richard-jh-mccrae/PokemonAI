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
    Its **Category** column reads ``Tera(Dragon)`` and it prints a ``[Tera]`` ability — *"As long as
    this Pokémon is on your Bench, prevent all damage done to this Pokémon by attacks"* — so
    `CardStat.tera` is True. Verified twice, at `data/EN_Card_Data.csv` Card ID 121 and against the
    engine's own `CardData.tera` through `EngineCardStatProvider`. (The ``Rule`` column on that row
    is ``Pokémon ex``; the two are different columns and Issue #284's first draft of this line cited
    the wrong one.) Declared here from Issue #284, which is the first case that reads the flag: every
    board in this file before then had Dragapult ex ACTIVE, where it says nothing — `docs/rules.md`
    §11 scopes the immunity to a BENCHED body.
  * Munkidori (112) Basic HP **110**, **{P}**, Weakness {D}, Resistance {F}, Retreat 1. Corrected by
    Issue #284 from a fixture that had declared HP 70 / {D} — neither of which is what the row says,
    and the module header claims these are verified. No board moved: every `_poke` sets `hp`
    explicitly, so the stat's HP was never the number under test, and Munkidori declares no attacks
    here for a Weakness or Resistance to apply to.
  * Basic Energy card ids: 2 = {R}, 5 = {P}, 7 = {D}, and {F} is added here as 6 ({W} as 3).
  * Prize values: Mega ex 3, ex 2, else 1 (`docs/rules.md` §6).

Issue #285 adds the three PRE-EVOLUTIONS the denial credit is about, and the hop counts are the whole
point of declaring them — a fixture built on the mainline chains would silently test nothing:
  * Staryu (1030) Basic HP 70, {W}, Weakness {L}, Retreat 1 — Water Gun ``{W}`` 20, its only attack,
    so `maxDamage` 20. **Staryu → Mega Starmie ex is ONE hop**: 1031's ``Previous stage`` column reads
    ``Staryu``, and **1031 is the only card in the pool whose ``Previous stage`` is ``Staryu``** —
    swept, not recalled. (The pool DOES print a *Misty's* Starmie, id 361, but its ``Previous stage``
    is ``Misty's Staryu`` (360), a different line: the owner prefix is part of the printed name,
    `docs/rules.md` §9. An earlier draft of this line claimed the set prints no "Starmie" at all,
    which is false — the kind of from-memory mainline claim CLAUDE.md's verify-at-source rule exists
    to catch, found by review.)
  * Dreepy (119) Basic HP 70, Dragon, **no Weakness and no Resistance** — Petty Grudge ``{P}`` 10 /
    Bite ``{R}{P}`` 40, so `maxDamage` 40.
  * Drakloak (120) Stage 1, evolvesFrom **Dreepy**, HP 90, Dragon, no Weakness/Resistance, Retreat 1
    — Recon Directive (Ability) / Dragon Headbutt ``{R}{P}`` 70, so `maxDamage` 70.
  * So **Dreepy → Drakloak → Dragapult ex is TWO hops** and Drakloak → Dragapult ex is one, which is
    the pair that isolates the hop discount. Both chains verified in `data/EN_Card_Data.csv`'s
    ``Previous stage`` column, alongside the standing `Riolu → Mega Lucario ex` single hop above.

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
SUPER_PSY_BOLT = 214
JETTING_BLOW, NEBULA_BEAM, SUPERB_SCISSORS, CLUTCH = 91031, 91032, 9345, 91008
WATER_GUN = 91030          # Staryu's only attack (Issue #286)
HEAT_BLAST, BLAZE_BLITZ, POWERFUL_HAND = 946, 947, 9743
E_R, E_P, E_F, E_D, E_W = 2, 5, 6, 7, 3
IGNITION = 17               # Issue #286 — the pool's ONE `discard_eot` Energy
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
    DRAGAPULT: CardStat(DRAGAPULT, synthetic=True, name='Dragapult ex', hp=320, ex=True, stage2=True,
                        evolvesFrom="Drakloak", energyType=DRAGON, maxDamage=200, maxDamageCost=2,
                        minAttackCost=1, minCostDamage=70, tera=True,
                        attacks=(JET_HEADBUTT, PHANTOM_DIVE), cardType=0),
    MUNKIDORI: CardStat(MUNKIDORI, synthetic=True, name='Munkidori', hp=110, energyType=PSYCHIC,
                        weakness=DARKNESS, resistance=FIGHTING, retreatCost=1, cardType=0),
    RIOLU: CardStat(RIOLU, synthetic=True, name='Riolu', hp=80, energyType=FIGHTING, minAttackCost=2,
                    maxDamage=30, maxDamageCost=2, attacks=(), cardType=0),
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
    # ``attacks`` added by Issue #286: Water Gun ``{W}`` 20, Staryu's ONLY attack
    # (`data/EN_Card_Data.csv` Card ID 1030). Issue #285 introduced this row purely as a
    # forward-payoff pre-evolution and read only its `maxDamage`, so the attack was never declared.
    # It is load-bearing here: `readiness_p` must be able to ask whether a COLOURLESS unit pays a
    # ``{W}`` slot, and a body with no attacks answers 0.0 for the wrong reason.
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
    # Ignition Energy (17), verified at `data/EN_Card_Data.csv`: *Special Energy*, `Type` {C}{C}{C},
    # *"If this card is attached to 1 of your Pokémon, discard it at the end of your turn. … it
    # provides {C} Energy. If this card is attached to an Evolution Pokémon, it provides {C}{C}{C}
    # Energy instead."* `energyType` is COLORLESS — the units it supplies pay colourless slots only,
    # which is why it arms Nebula Beam ``{C}{C}{C}`` outright and does nothing at all for Mega
    # Brave ``{F}{F}``. `cardType=6` is SPECIAL_ENERGY (`cg.api.CardType`).
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
    MEGA_STARMIE: CardStat(MEGA_STARMIE, synthetic=True, name='Mega Starmie ex', hp=330, megaEx=True,
                           energyType=WATER, evolvesFrom="Staryu", maxDamage=210, maxDamageCost=3,
                           minAttackCost=1, minCostDamage=120,
                           attacks=(JETTING_BLOW, NEBULA_BEAM), cardType=0),
}
_ATTACKS = {
    JET_HEADBUTT: AttackStat(JET_HEADBUTT, damage=70, cost=1, energyTypes=(COLORLESS,)),
    PHANTOM_DIVE: AttackStat(PHANTOM_DIVE, damage=200, cost=2, energyTypes=(FIRE, PSYCHIC)),
    AURA_JAB: AttackStat(AURA_JAB, damage=130, cost=1, energyTypes=(FIGHTING,)),
    MEGA_BRAVE: AttackStat(MEGA_BRAVE, damage=270, cost=2, energyTypes=(FIGHTING, FIGHTING)),
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
    # Counter placement, so all three ignore flags are set — see the module docstring. Printed 0:
    # with no context this attack deals NOTHING, which is precisely the flat axis Issue #280 removes.
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
    # `damageMax` 280 is the +150 leg, exactly as the provider carries it: the bonus is REACHABLE
    # through the oracle's "max" bound and must not be reachable through this read.
    CONJOINED_BEAMS: AttackStat(CONJOINED_BEAMS, damage=130, cost=2,
                                energyTypes=(PSYCHIC, PSYCHIC), damageMax=280),
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
               MEGA_STARMIE: ROLE_TIER["win_condition"],
               SOLROCK: ROLE_TIER["secondary_attacker"], LUNATONE: ROLE_TIER["engine"],
               METAGROSS: ROLE_TIER["secondary_attacker"]}

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
POWER_PRO_ID = 1141
POWER_PRO = (30, FIGHTING, False)
#: Black Belt's Training (1211, **Supporter**), same source: *"During this turn, attacks used by your
#: Pokémon do 40 more damage to your opponent's Active Pokémon {ex} (before applying Weakness and
#: Resistance)."* — amount 40, no attacker-type gate, defender-{ex} gate. The {ex} scope INCLUDES a
#: Mega Evolution Pokémon ex (`docs/rulebook.txt` L337: *"Mega Evolution Pokémon ex are considered to
#: be Pokémon ex, so any card effects that affect Pokémon ex also affect Mega Evolution Pokémon ex"*).
BLACK_BELT = (40, None, True)


#: Ignition Energy's two committed records, as `CardFunctions` / `CardEffects` entries (Issue #286).
#: BOTH are needed and they answer different halves: the CLAUSE's ``rider`` says the card evaporates
#: (the parametric record, ADR-0032), the TAG's ``provides`` pair says how many units it supplies
#: (`CardFunctions.energy_provision`, the accessor the Attach Budget already sizes a hand attach
#: with). Restated here rather than loaded from disk for the same reason every other fact in this
#: file is: a fixture that read the shipped stores would move whenever they did.
_IGNITION_TAGS = {IGNITION: ["discard_eot", "provides:1", "provides_evo:3"]}
_IGNITION_CLAUSES = {IGNITION: [{"kind": "energy_provide", "amount": 1, "amount_on_evolution": 3,
                                 "type": "colorless", "rider": "discard_eot"}]}


def _combat():
    return CombatMath(DictCardStatProvider(_STATS, attacks=_ATTACKS),
                      functions=CardFunctions(_IGNITION_TAGS), transients=None,
                      effects=CardEffects(_IGNITION_CLAUSES))


def _poke(cid, *, hp, energies=(), serial=1, damage=0, tools=(), energy_cards=None):
    """One in-play body. ``tools`` is the raw ``tools`` key `_SideBase.tool_ids` reads (Issue #260's
    homed `attached_tools` zone) — the route by which a Tool's boost, unlike a Trainer's, reaches a
    snapshot as BOARD state rather than through the turn tracker. Defaults to empty, so every
    existing board in this file is byte-identical.

    ``energy_cards`` is the OTHER attached-Energy key (Issue #286) and it is separate from
    ``energies`` because the engine keeps them separate: ``energies`` is the ``EnergyType`` UNITS
    the attached cards PROVIDE, ``energyCards`` is the CARDS (`common/board_cards.py`). One Ignition
    on an Evolution is ``energy_cards=[17]`` and ``energies=[0, 0, 0]``. Omitted by default, which
    leaves every board that predates this issue byte-identical AND leaves the expiring-Energy strip
    making no claim about them — card identity is what a rider is read from."""
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
    """`TurnBoostTracker`'s one duck-typed method — the shape `StateModel.build` resolves per seat.

    A this-turn Trainer boost is a LOG fact, not a board one ("During this turn, attacks used by
    your … Pokémon do N more damage" leaves no trace in any zone once the card reaches the discard),
    so the tracker is how it reaches a snapshot at all. Side 0 is mine on every board in this file."""

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

    # …and end-to-end through the scalar on a board that is PRIZE-lethal rather than bench-empty
    # (ADR-0064 Amendment B) — the second case must inherit the same dominance, not merely the same
    # constant. Every positional family is free to be as favourable as this fixture allows; the
    # scalar still has to rank the lethal board below the identical board they cannot yet win on.
    lethal = _lucario_board(my_hp=60, bench=[_poke(RIOLU, hp=80, serial=2)], their_prizes=3)
    survivable = _lucario_board(my_hp=60, bench=[_poke(RIOLU, hp=80, serial=2)], their_prizes=4)
    assert sv.state_value(survivable) - sv.state_value(lethal) > sv.POSITIONAL_MAX


# ── the band's OTHER half, owed and unbuilt: the prize-denominated pair (Issue #330) ──────────────
#
# The test directly above is `ko-score-band`'s terminal half, and it is ONE-SIDED: it asserts that
# `LOSS_PRIZES` out-scales every other family, which is a bound on the term that is already derived
# to dominate. Nothing above it — and nothing anywhere else in this file — asserts the band on the
# pair the whitelist entry is actually owed a ruling about.
#
# `ko-score-band`'s `fact` reads *"a prize is worth more than any POSITIONAL term"*. `survival` is
# prize-denominated and deliberately uncapped, so the entry does not bind it, and the two tests
# below are that gap stated as the assertions that will pass the day it closes. Both use the
# strict-xfail TARGET idiom already established in this file at
# `test_threat_GRADES_by_what_the_target_yields_instead_of_saturating_into_one_bit` — green while
# the gap is open, and a red XPASS is the signal to delete the mark.


@pytest.mark.req("REQ-STATEVALUE-0006")
@pytest.mark.xfail(strict=True, reason="OPEN GAP (Issue #330), blocked on Issue #263's `attack_ev` "
                                       "wiring — see the test body for why it is xfail rather than "
                                       "a retune")
def test_a_line_that_banks_a_prize_outscores_one_that_declines_it():
    """**A banked prize is never declined** — `ko-score-band` made executable for the
    prize-denominated pair (`prize_race` against `survival`), which is the half the whitelist entry
    at `sound_rules.py` records as OWED A RULING.

    Taking a prize moves `prize_race` by exactly 1.0 — the unit slope that makes the whole scalar
    prize-denominated. Nothing bounds what `survival` may charge against the same line, so a line
    that banks a real prize can be out-scored by one that banks nothing and merely keeps a body
    safer. That is the defect Issue #330 measured, and Issue #190 named before `state_value` existed.

    **Why this is `xfail` rather than a fix here.** Making it pass means bounding `survival` per-play
    (Issue #330's option 2) or completing the composition the module header already claims — see
    lines 63-66, *"converting their exposure into a prize takes an ATTACK, and `attack_ev` prices
    that attack at the terminal action"* — which the developer ruled on 2026-08-02 belongs to
    Issue #263, not here. Hand-tuning either constant against the 12 corpus frames that exposed this
    would be fitting the equation to the corpus, which the post-POC learning phases exist to do
    against a held-out set.

    **The two paths are distinguishable, and that is deliberate.** This assertion is on the SHIPPED
    CONSTANTS of the end-board pair, so Issue #263's terminal-action wiring does not by itself move
    it: if `attack_ev` lands and this still xfails, that is the honest report that the wiring did not
    discharge the pair invariant and the per-play bound is still owed. The companion test below is
    the one the wiring moves directly."""
    # The whole of what banking one prize can add, on the side of the line that takes it.
    banked = (sv.prize_race(my_prizes_remaining=3, their_prizes_remaining=6)
              - sv.prize_race(my_prizes_remaining=4, their_prizes_remaining=6))
    assert banked >= 1.0, "the lead leg has lost its unit slope — this test is measuring the wrong thing"

    # The whole of what `survival` can charge against it. RANK-GRADED, so the bound is ~2x the worst
    # single body rather than `_MAX_BODIES` x `_MAX_PRIZE_VALUE`; computed from the equation rather
    # than transcribed, so moving the grading moves this test.
    worst_survival_charge = -sv.survival([sv.ExposedBody(sv._MAX_PRIZE_VALUE, 1)] * sv._MAX_BODIES)

    assert banked > worst_survival_charge

    # And in the shape a caller actually meets it: the line that banks the prize and exposes
    # everything must still outrank the line that banks nothing and is perfectly safe.
    takes_the_prize = (sv.prize_race(my_prizes_remaining=3, their_prizes_remaining=6)
                       + sv.survival([sv.ExposedBody(sv._MAX_PRIZE_VALUE, 1)] * sv._MAX_BODIES))
    declines_it = (sv.prize_race(my_prizes_remaining=4, their_prizes_remaining=6)
                   + sv.survival([]))
    assert takes_the_prize > declines_it


@pytest.mark.req("REQ-STATEVALUE-0006")
@pytest.mark.xfail(strict=True, reason="OPEN GAP (Issue #330), blocked on Issue #263's `attack_ev` "
                                       "wiring — the end board is the only thing scored today and "
                                       "it prices a non-lethal attack at <= `_THREAT_CAP`")
def test_landing_an_attack_can_outprice_the_one_retreat_a_turn_allows():
    """**Attack vs retreat on an otherwise-equal board** — the leaf-picks-`Retreat` frames of
    Issue #330's table, stated as the class rather than as fixtures.

    **Scope, stated because it is narrower than the issue body's prose.** This asserts nothing about
    the AGENT's committed decision. Issue #356 established that `family_diag` ranks the LEAF's argmax
    and never reads `chosen`. Re-derived here rather than taken from that issue
    (`family_diag.py --source decider`, at this commit): the agent retreated on **none** of these
    frames — its picks are Play Harlequin, Jetting Blow, Nebula Beam, Play Lillie's Determination, an
    Ignition Energy attach, and Jetting Blow. A decision-scoped version of this test would therefore
    be vacuously green and would measure nothing the defect is about. What these frames genuinely
    show is a property of the equations, and that is what is written here.

    Two counts in the issue body do not survive that re-derivation, and are corrected here because a
    docstring repeating them would be the same defect one layer down. The body's prose says *"on five
    frames the leaf's pick is literally `Retreat`"*; its own table lists **six**
    (`82225643|57`, `83037962|49`, `83038055|51`, `85164131|31`, `82227388|43`, `83053965|6`). And
    `Δ prize_race` is `0.0000` on five of those six — **not** on `82225643|57`, which reads
    **+1.2500** and whose ruled option is a Trainer card rather than an attack. That frame is the
    banked-prize case and belongs to the test above; the five zero-delta frames are this one's.

    The class, on those five: the ruled play deals damage (or develops) without banking a prize, so
    the only end-board family that can credit it is `threat` — capped at `_THREAT_CAP` = 0.1 AND
    saturated to `{0.0, 0.1}` (see the strict-xfail target for `threat` below). Measured, the
    `Δ threat` column reads exactly `+0.1000` on five of the six and `+0.0000` on the last, never a
    value between, which is that saturation visible in the corpus. Against it, one retreat lengthens
    the clock on my most-exposed body and `survival` pays for it uncapped. A 210-damage Nebula Beam
    is worth at most 0.1 prizes to the leaf; shuffling a body out of the front is worth over two.

    Verified at source, because the "one retreat" bound is what makes this the whole of the defensive
    side rather than an arbitrary comparison: `docs/rules.md` §3 — *Retreat (manual): 1 per turn*,
    and *Attack: 1, and it ends the turn* (`[RULE: rulebook L105-148]`, `[ENGINE-LEGAL]`).

    **This is the test Issue #263's wiring moves directly.** `attack_ev` prices the terminal attack,
    which is exactly the credit missing on the left-hand side. Until it is wired, `threat` pays the
    cap's price for a double-count that no shipped code path performs."""
    # Offence, on the end board, for an attack that does NOT knock out: `threat` and nothing else.
    # Taken at `_MAX_PRIZE_VALUE` — their biggest possible body — so this is the ceiling, not a case.
    best_offence_the_end_board_prices = sv.threat([sv._MAX_PRIZE_VALUE])
    assert best_offence_the_end_board_prices == pytest.approx(sv._THREAT_CAP), (
        "the ceiling moved — re-derive it before trusting the comparison")

    # Defence, for the one retreat a turn allows: my worst-exposed body stops being reachable now.
    # Clock 1 -> 3 is the modest reading (a fresh Active in front of it), not the generous one.
    exposed = sv.survival([sv.ExposedBody(sv._MAX_PRIZE_VALUE, 1)])
    after_retreating = sv.survival([sv.ExposedBody(sv._MAX_PRIZE_VALUE, 3)])
    one_retreat_buys = after_retreating - exposed
    assert one_retreat_buys > 0.0, "the retreat is not moving `survival` — the comparison is void"

    assert best_offence_the_end_board_prices > one_retreat_buys


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


# ── Issue #286 — readiness's FORWARD leg must not count Energy that evaporates ────────────────────


def _expiring_board(cid, *, energies, energy_cards, hp):
    """MY body holding a chosen Energy set, the turn's manual attach already SPENT and my hand empty.

    Both are deliberate: with the attach spent and nothing in hand the Attach Budget adds nothing, so
    `readiness_p`'s answer is a fact about what is ON the body rather than about what the fixture's
    deck happens to hold. Their side is a bare Dragapult ex, the same defender every other board in
    this file uses."""
    return _model(
        _player(active=_poke(cid, hp=hp, energies=energies, energy_cards=energy_cards), prize=4),
        _player(active=_poke(DRAGAPULT, hp=320, energies=[E_R, E_P], serial=9), prize=4),
        energy_attached=True)


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_forward_clock_no_longer_counts_an_energy_that_will_be_DISCARDED():
    """Gouging Fire ex holds ONE Ignition. It is a **Basic**, so the card provides ``{C}`` — one
    colourless unit, which fills exactly the ``{C}`` slot of Blaze Blitz ``{R}{R}{C}`` and pays
    neither ``{R}``. So the payoff is unreachable THIS turn (the now-leg is an honest 0) and the
    whole of `readiness` here rides on the forward clock.

    The incumbent clock counted that unit and said *two more attaches*. It will not be there next
    turn — the rules discard it at the end of this one — so the honest answer is three, and the
    family must fall accordingly. The control below is the same board funded by a Basic {R}, where
    nothing expires and nothing may move."""
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
    """Issue #286's own T1-going-first test, on `mega_starmie`'s real cards — and the proof that the
    fix is live on a shipped deck rather than only on a fixture.

    The deck runs 3 Staryu and 4 Ignition. Staryu is a **Basic**, so an Ignition on it provides
    ``{C}`` — ONE unit — while the line's deepest payoff is Mega Starmie ex's Nebula Beam
    ``{C}{C}{C}``. That is a PARTIAL loan: the unit fills one colourless slot and the clock still
    owes two, so the incumbent read *two attaches away* and the honest answer is three.

    The now-leg reads 0.0 for a card-true reason and not a fixture accident: Staryu's only attack is
    Water Gun ``{W}``, and a colourless unit pays colourless slots ONLY (`combat.unit_colours`), so
    the Ignition arms nothing this turn. Which is exactly the doctrine's rule — *"Going first: attach
    Water (never Ignition — it'd discard unused)"* — and `docs/rules.md`'s worked example of a
    reason-only rule (correction ep81903490 f5).

    Both halves are asserted: the Water board must outscore the Ignition board (it did BEFORE this
    change too, so that alone would be a vacuous test), **and the gap must WIDEN**, which is the part
    only this change produces. The Ignition board lands exactly on the BARE-Staryu value — an
    evaporating Energy buys no forward readiness at all, which is the correction stated as a
    number."""
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
    # The part that is NEW: the Ignition board falls all the way to the bare board. Before this
    # change it sat strictly between the two, crediting a card that will be in the discard.
    assert ign["readiness"] == pytest.approx(bare["readiness"])
    assert bare["readiness"] < water["readiness"]


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_the_NOW_leg_keeps_the_evaporating_energy_and_therefore_MASKS_the_fix():
    """The measured finding, executable — Issue #286's fix is correct and, wherever the expiring
    Energy FULLY arms the body, invisible.

    `_readiness_odds` is ``max(now, halve(arm))`` and the two legs read the SAME attached Energy
    through the SAME matcher (`matched_slots` documents itself as *"the matcher `reachable_attach`
    uses"*). So whenever the expiring Energy is enough to zero the clock it is also enough to pin
    the now-leg at 1.0, and the ``max`` discards the forward leg entirely. Mega Starmie ex holding
    one Ignition is exactly that: ``{C}{C}{C}`` on an Evolution pays Nebula Beam ``{C}{C}{C}``
    outright.

    Swept over the committed corrections corpus (Issue #286, 2026-08-03): **25 of 1015** of my
    bodies hold a `discard_eot` Energy, the forward clock moves on **all 25**, and `_readiness_odds`
    moves on **none** — every one of them reads ``now == 1.0``, because every one of them sits on an
    EVOLUTION. The partial-loan case above is the deck's other half and is NOT masked; the corpus
    simply holds no frame of it.

    This test therefore asserts a gap, not a virtue. Its worst case is not the masking itself but
    what the masking rests on: `readiness_p` never asks whether the body may attack at all, so a
    BENCHED Mega Starmie ex reads 1.0 (corpus frame `83664991|…|43`). Issue #351 is the spec; Issue
    #263 owns *who is Active*. This turns red the day either lands, which is exactly when someone
    should read it again."""
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


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_a_basic_energy_is_never_stripped_from_the_forward_clock():
    """The regression guard the issue names. Nothing about a Basic Energy expires, so the flagged
    and unflagged clocks must return the SAME number on every board that holds only Basic Energy —
    including the boards this file was already built on, which carry no ``energyCards`` key at all
    and where the strip must therefore make no claim."""
    for board in (_expiring_board(GOUGING_FIRE, energies=[E_R], energy_cards=[E_R], hp=230),
                  _expiring_board(MEGA_STARMIE, energies=[E_W, E_W], energy_cards=[E_W, E_W],
                                  hp=330),
                  _lucario_board(my_energies=[E_F], energy_attached=True)):
        body = board.mine.active
        assert (board.mine.turns_to_afford(body)
                == board.mine.turns_to_afford(body, exclude_expiring=True))


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


def _survival_of_model(model) -> float:
    """The `survival` leg off an already-built model (Issue #280's context cases).

    A sibling of :func:`_survival_of`, which takes the two player dicts — these cases need the model
    itself because the board they perturb is built by `_alakazam_board`, not by `_player` pairs."""
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
    assert _survival_of_model(theirs_big) == pytest.approx(-3.0 * 0.5)
    assert _survival_of_model(mine_big) == pytest.approx(-3.0 / 256)
    assert _survival_of_model(theirs_big) < _survival_of_model(mine_big)


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

    assert _survival_of_model(doomed) <= -sv.LOSS_PRIZES
    assert _survival_of_model(safe) > -sv.LOSS_PRIZES


@pytest.mark.req("REQ-STATEVALUE-0009")
def test_more_cards_in_THEIR_hand_never_improves_survival():
    """The monotonicity class Issue #262 requires, on this issue's axis. Hands 1..12 keep the sweep
    clear of the bench-empty doom (340 HP needs a 17-card hand), so this is the POSITIONAL term
    alone."""
    values = [_survival_of_model(_alakazam_board(n)) for n in range(1, 13)]
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
# `damage_context`'s `atk_boosts` -> `strategy/damage.py` -> Issue #281's
# `best_reachable_damage_vs` -> `threat`, and every link of it shipped with Issue #279 and
# Issue #281 rather than with this one.
#
# What did NOT ship is any assertion that the whole path holds END TO END, at the scalar. Each link
# is covered in isolation — `test_damage_context.py` tests the context key,
# `test_tool_holder_facts.py` tests the parsed triples against the real pool,
# `test_damage_oracle.py` tests the oracle's gates — and a chain of separately-green links is
# exactly the shape that breaks silently in the middle. So these assert on `state_value` itself, and
# each one is built so that the GATE is the only thing standing between the fixture and a crossing:
# a broken gate is a failure here, not a plausible number.


def _boosts_of(model) -> tuple:
    return model.damage_context(attacker="mine")["atk_boosts"]


def _vs_dragapult_at(hp, *, boosts=None, hand=()):
    """MY funded Mega Lucario ex against a Dragapult ex chipped to ``hp`` — the one board every case
    below perturbs. `{F}{F}` attached with the turn's attach already spent, so Mega Brave's 270 is
    reachable and nothing the Attach Budget could add moves it."""
    return _lucario_board(my_energies=[E_F, E_F], energy_attached=True, hand=list(hand),
                          their_active=_poke(DRAGAPULT, hp=hp, serial=9), boosts=boosts)


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_a_live_boost_crosses_a_breakpoint_and_the_scalar_moves_for_it():
    """Premium Power Pro's +30 turns Mega Brave's 270 into the 300 that reaches a 300 HP Dragapult ex.

    The card leaving my hand is the only thing `_PLAY` structurally models, so without this the play
    is priced at a hand loss and nothing else. With it the boost enters through exactly ONE family —
    `threat`, whose reachability gate is Issue #281's `best_reachable_damage_vs` — which is asserted
    here as well as the total, because a fact that moved two families would be double-counted.

    Mega Lucario ex is {F} (`data/EN_Card_Data.csv`), so Power Pro's attacker-type gate is met;
    Dragapult ex carries no Weakness to {F} in this fixture, so 270 and 300 are the raw numbers with
    no W/R leg to disentangle."""
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
def test_PLAYING_the_boost_card_is_priced_as_a_gain_and_not_as_the_hand_loss():
    """**The issue's headline sentence, as an arithmetic claim about the whole transition.**

    The cases around this one hold the hand fixed and vary only the live boost, which shows the
    boost is READ but not that playing the card comes out ahead. This one models the actual
    `_PLAY`: before, Premium Power Pro is in hand and no boost is live; after, the card is gone and
    the boost is live. That is exactly what `apply_option` will difference, and it is the only
    arrangement in which the epic's failure mode can appear at all —
    *"a card whose effect no term reads prices at MINUS the hand value of the card spent"*.

    The hand leg has to be real for the claim to mean anything, so a `needs.Resolution` supplies the
    held card's latent Worth at `card_worth.TAG_TIER["gust"]` — the shipped tier for a situational
    Trainer, cited rather than invented (its own comment: *"reach (Boss's Orders) — the ladder's −10
    keep floor"*, the band this ladder gives a held utility Trainer). At `POC_WORTH_PRIZE_RATE` that
    is 1/12 of a prize the play gives up.

    The margin is deliberately narrow and is asserted in BOTH directions: the boost's `threat` gain
    must exceed the hold, so the play is a gain — and the hold must be genuinely non-zero, so the
    test would go negative the moment the boost stopped being priced. A wide margin here would pass
    on a board where the hand cost nothing, which is the vacuous version of this test."""
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
    assert total_after > total_before, (
        f"playing the boost scored as a mistake: {total_after} <= {total_before}")
    # and the failure mode, stated as the counterfactual: with the boost UNPRICED the same play is
    # a strict loss, which is what makes the assertion above a claim rather than a coincidence.
    assert total_before - sv.state_value(_vs_dragapult_at(300)) == pytest.approx(b["hand"])


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_a_live_boost_that_crosses_nothing_leaves_the_scalar_untouched():
    """The other half of the same claim, and the one that keeps `threat` a GATE rather than a slope.

    Against a 260 HP Dragapult ex, Mega Brave's 270 already reaches, so the boost buys nothing that
    this family prices — the extra damage above lethal is overkill, and converting the exposure is
    `attack_ev`'s job at the terminal action. The scalar must therefore be BIT-identical, not merely
    close: a boost that nudged the board value would be pricing overkill as position."""
    plain = _vs_dragapult_at(260)
    boosted = _vs_dragapult_at(260, boosts=[POWER_PRO])
    assert _reach(boosted)[1] == _reach(plain)[1] + 30, "the boost IS reaching the damage read"
    assert sv.state_value(boosted) == sv.state_value(plain)


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_the_attacker_TYPE_gate_refuses_a_boost_the_attacker_does_not_qualify_for():
    """*"attacks used by your {F} Pokémon"* — Premium Power Pro pays a {F} attacker and nobody else.

    The fixture is one gate away from a crossing on purpose: Mega Starmie ex reaches Jetting Blow's
    120 against Larry's Braviary's 130 HP, and 120 + 30 = 150 would cross. The control is the SAME
    amount on the SAME board with the gate re-pointed at the attacker's own {W} — a probe,
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


# ── an ATTACHED boost Tool, and the HOLDER gate that decides it (Issue #345) ──────────────────────
#
# Every case above supplies the boost through the turn tracker, which is how a Trainer PLAY reaches a
# snapshot. A Tool's boost takes the other route — it is board state, read off the holder — and it
# carries a condition the tracker's boosts never do: `applies_to_holder`. Brave Bangle (1175) is the
# card that makes that route load-bearing, because `slowking` runs it alongside five Rule-Box bodies
# it must NOT reach.
#
# Card text verified at `data/EN_Card_Data.csv`, Card ID 1175, WHT 80, Pokémon Tool: *"If the Pokémon
# this card is attached to doesn't have a Rule Box, the attacks it uses do 30 more damage to your
# opponent's Active Pokémon {ex} (before applying Weakness and Resistance). (Pokémon {ex}, Pokémon
# {V}, etc. have Rule Boxes.)"* — TWO gates on one +30: a HOLDER gate (no Rule Box) and the same
# defender-{ex} gate Black Belt's Training carries. Slowking (163, `slowking`'s own attacker, Stage 1
# from Slowpoke, HP 120, {P}) has no Rule Box, and its Super Psy Bolt `{P}{P}●` prints 120.


#: The two holders these cases straddle, each with the Energy that funds its own real attack —
#: Slowking has no Rule Box (Super Psy Bolt `{P}{P}●`), Mega Lucario ex has one (Aura Jab `{F}`).
#: Carried as data rather than branched on inside the board builder, so the only thing that differs
#: between the two arms is the holder itself.
_HOLDERS = {SLOWKING: (120, [E_P, E_P, E_P]), MEGA_LUC: (340, [E_F])}


def _slowking_board(their_active, *, bangle=True, holder=SLOWKING):
    """MY ``holder`` Active carrying Brave Bangle (or not) against ``their_active``, with the turn's
    attach already spent so reachability is exactly what is on the board."""
    hp, energies = _HOLDERS[holder]
    return _model(
        _player(active=_poke(holder, hp=hp, energies=energies,
                             tools=(BRAVE_BANGLE,) if bangle else ()), prize=4),
        _player(active=their_active, prize=4),
        energy_attached=True)


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_an_attached_boost_tool_crosses_the_breakpoint_its_holder_qualifies_for():
    """The end-to-end claim: a Tool's +30 reaches `threat` by the same path a played Trainer's does.

    120 is 30 short of a Mega Starmie ex chipped to 150 remaining HP (its printed HP is 330) and the
    Bangle is exactly 30 — so the Knock Out is there or it is not, with nothing in between for a
    partly-wired path to land on. The `{ex}` half of the gate is satisfied by `megaEx`
    (`docs/rulebook.txt` L337), which is the same reading
    `test_the_defender_ex_gate_counts_a_MEGA_ex_as_an_ex_and_a_plain_body_as_neither` pins for the
    tracker-supplied boost — the two suppliers must not disagree about one card's scope."""
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
    """The gate this issue exists for, as a ONE-FACT control: same Tool, same defender, same board —
    only whether the Bangle is attached changes — run on a holder that HAS a Rule Box.

    Mega Lucario ex is `megaEx`, so the card's condition is not met and the +30 must not appear. An
    ungated read would put a phantom 30 on precisely the deck's biggest attackers, which is a
    strictly worse error than the silent zero this issue replaced: it manufactures lethals rather
    than missing them — and this board is exactly that case, which is why it is the one chosen. With
    one `{F}` attached only Aura Jab is affordable, so the reach is 130 against 150 remaining HP: no
    Knock Out. Drop the holder gate and the Bangle lifts it to 160, claiming one that is not there."""
    defender = _poke(MEGA_STARMIE, hp=150, serial=9)
    ruled_out = _slowking_board(defender, holder=MEGA_LUC)
    without = _slowking_board(defender, holder=MEGA_LUC, bangle=False)
    assert _boosts_of(ruled_out) == (), "a Rule-Box holder gets nothing from this Tool"
    assert _reach(ruled_out) == _reach(without), "attaching it must move no number at all"
    assert sv.state_value(ruled_out) == sv.state_value(without)
    # …and the docstring's arithmetic, asserted rather than described: the board really is one the
    # gate decides. 130 falls short of 150, and the ungated 160 would not — so a build that dropped
    # the gate fails the reach assertion above, it does not merely score differently.
    assert _reach(ruled_out)[1] == 130 < 150 < 130 + 30
    assert _threat_of(ruled_out) == 0.0


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_the_attached_tools_defender_gate_is_read_too_so_both_conditions_must_hold():
    """The second gate on the same +30. Against Larry's Braviary — not an `{ex}` — the boost is in
    the context and still contributes nothing, so a build that honoured the holder gate while
    dropping the defender gate fails here rather than passing on the first case alone.

    Braviary's Resistance is {F} (`docs/rules.md` §5, a flat −30) and this attacker is {P}, so no
    Weakness/Resistance leg is in play to confuse the reading: 120 is 120."""
    plain = _slowking_board(_poke(BRAVIARY, hp=130, serial=9))
    assert _boosts_of(plain) == ((30, None, True),), "the boost IS present — the gate is what refuses"
    assert _reach(plain)[1] == 120, "the {ex} gate refuses the 30 against a non-{ex} defender"
    assert _threat_of(plain) == 0.0


@pytest.mark.req("REQ-STATEVALUE-0011")
def test_with_no_boost_in_play_the_context_is_EMPTY_and_the_scalar_is_unmoved():
    """The regression half: an EMPTY tracker must be indistinguishable from no tracker at all, so a
    board with no live boost is scored by the same arithmetic it always was.

    This is the in-tree half of the claim; the cross-COMMIT half — that Issue #281's shipped numbers
    did not move — is the byte-identical gate A/B recorded in
    `docs/plans/issue-sequence-281-wave3-packet.md`, because no assertion inside one commit can
    reach a value from another.

    Bit-identical rather than approximate, and over the whole per-family breakdown rather than the
    total, because the failure being guarded is a term that quietly gained a boost-shaped leg — which
    a total could hide by cancellation."""
    no_tracker = _vs_dragapult_at(320)
    empty_tracker = _vs_dragapult_at(320, boosts=[])
    assert _boosts_of(no_tracker) == () == _boosts_of(empty_tracker)

    without, empty = {}, {}
    assert sv.state_value(no_tracker, working=without) == sv.state_value(empty_tracker,
                                                                        working=empty)
    assert without == empty


# ── standing chip on THEIR bench is an asset (Issue #284) ─────────────────────────────────────────
#
# `_reachable_target_values` used to return AT MOST ONE element — their Active — so damage already
# standing on their Bench was invisible between turns. `dragapult_ex`'s win plan is exactly that
# asset: *"Phantom Dive pre-loads benched mons with softening chip you cash into prizes on LATER
# turns"*, and the board carrying six counters scored identically to a fresh one.
#
# The bench leg is a DIFFERENT damage route from the Active leg and not a wider version of it. An
# attack's printed damage lands on the Active; a benched body is reachable only through the attack's
# snipe RIDER, which ignores Weakness and Resistance by rule (ADR-0022, and `damage.py`'s own module
# note), so it never routes through `predicted_damage` — `combat.py`'s oracle says so outright:
# *"Jetting Blow is zeroed (its bench rider is a separate path)"*.
#
# Card facts verified at `data/EN_Card_Data.csv`:
#   * Mega Starmie ex (1031) Jetting Blow ``{W}`` 120 — *"This attack also does 50 damage to 1 of
#     your opponent's Benched Pokémon."*  The fixture's only bench route.
#   * Mega Lucario ex (678) Aura Jab / Mega Brave — no rider of any kind. The negative control.
#   * Dragapult ex (121) is **Tera(Dragon)**: no attack damage while Benched (`docs/rules.md` §11).


UNREADABLE_CARD = 909909          # deliberately absent from `_STATS` — the fail-closed case


def _bench_board(their_bench, *, my_active=None, my_energies=(E_W,), their_active=None):
    """MY Mega Starmie ex Active — the fixture's one bench rider — against THEIR chosen Bench.

    Their Active defaults to a 320-HP Dragapult ex, which Jetting Blow's exact 120 cannot reach, so
    the ACTIVE leg contributes nothing and every non-zero `threat` on these boards is the BENCH leg.
    The turn's Energy is already spent (`energy_attached=True`), so the Attach Budget adds nothing
    and reachability is a fact about the fixture rather than about the deck's colours."""
    return _model(
        _player(active=my_active or _poke(MEGA_STARMIE, hp=330, energies=list(my_energies)),
                prize=4),
        _player(active=their_active or _poke(DRAGAPULT, hp=320, energies=[E_R, E_P], serial=9),
                bench=list(their_bench), prize=4),
        energy_attached=True)


@pytest.mark.req("REQ-STATEVALUE-0012")
def test_counters_standing_on_their_benched_body_are_worth_something_to_me():
    """The headline. Two boards identical but for the counters on ONE benched body, and the chipped
    one must score better for me.

    Six counters is Phantom Dive's payload exactly (*"Put 6 damage counters on your opponent's
    Benched Pokémon in any way you like"* — 60 damage, `data/EN_Card_Data.csv` row 121), and a
    70-HP Munkidori carrying them sits at 10 HP, inside Jetting Blow's 50. Fresh, it is not: 50 does
    not reach 70, so the family reads exactly 0 and the whole scalar cannot tell the boards apart."""
    fresh = _bench_board([_poke(MUNKIDORI, hp=70, serial=11)])
    chipped = _bench_board([_poke(MUNKIDORI, hp=70, damage=60, serial=11)])

    assert _threat_of(fresh) == 0.0, "50 of rider does not reach a fresh 70 HP"
    assert _threat_of(chipped) > 0.0, "…and does reach the 10 HP the chip leaves"
    assert sv.state_value(chipped) > sv.state_value(fresh)


@pytest.mark.req("REQ-STATEVALUE-0012")
def test_the_bench_leg_still_stops_short_of_a_prize():
    """The cap, on the worst board the widened loop can be handed: every one of their six bodies
    chipped to 10 HP and every one of them a 3-prize Mega Evolution Pokémon ex.

    Six bodies is the maximum — *"Each player may have up to 5 Pokemon on the Bench at any one
    time"* (`docs/rulebook.txt` L75) plus the Active — so this is the largest sum the family can be
    asked for. It must stay under one prize: converting any of these takes an ATTACK, `attack_ev`
    prices that at the terminal action, and `score = state_value(end) + EV(terminal)` adds the two.
    Widening the loop is exactly the change that could have broken the two-band argument.

    **The cap is asserted to BITE, not merely to hold.** ``threat`` is `min(_THREAT_CAP, sum)`, so
    `threat <= _THREAT_CAP` is true of every board ever built and asserting it alone would be a
    tautology — the test would pass against a bench leg that had been deleted. What has to be shown
    is that the RAW sum this widening produces genuinely exceeds a prize, i.e. that the bound is what
    stops it rather than the inputs being small. That is the `raw > 1.0` line."""
    bench = [_poke(MEGA_STARMIE, hp=330, damage=320, serial=11 + i) for i in range(5)]
    board = _bench_board(bench, their_active=_poke(MEGA_STARMIE, hp=330, damage=320, serial=9))

    raw = sum(sv._reachable_target_values(board))
    assert len(sv._reachable_target_values(board)) == 6, "all six bodies reachable — the worst case"
    assert raw > 1.0, "…and their uncapped sum really does exceed one prize, so the cap is load-bearing"
    assert 0.0 < _threat_of(board) <= sv._THREAT_CAP < 1.0


@pytest.mark.req("REQ-STATEVALUE-0012")
def test_a_TERA_body_on_their_bench_contributes_nothing_however_damaged():
    """Bench immunity, failing CLOSED. *"Tera Pokémon ex take NO attack damage while Benched"*
    (`docs/rules.md` §11, `[RULE: Appendix 6]`), so a Dragapult ex one counter from death is not a
    target at all — and the same card in the ACTIVE seat is, which is what makes this a fact about
    the seat rather than about the card.

    The control is a body at the SAME 10 HP that is not Tera. Without it, a bench leg that had
    quietly stopped firing altogether would pass this test."""
    tera = _bench_board([_poke(DRAGAPULT, hp=320, damage=310, serial=11)])
    plain = _bench_board([_poke(MEGA_STARMIE, hp=330, damage=320, serial=11)])

    assert _threat_of(tera) == 0.0
    assert _threat_of(plain) > 0.0, "the control: a non-Tera body at the same 10 HP DOES price"

    # …and the immunity is scoped to the BENCH. The same Tera body Active is reachable, through the
    # Active leg's own damage read (Jetting Blow's exact 120 against 10 HP).
    active = _bench_board([], their_active=_poke(DRAGAPULT, hp=320, damage=310, serial=9))
    assert _threat_of(active) > 0.0


@pytest.mark.req("REQ-STATEVALUE-0012")
def test_an_UNREADABLE_benched_body_contributes_nothing():
    """The other half of failing closed, and the one the rules cannot help with. `CardStat` has **no
    immunity field** beyond `tera` (`docs/rules.md` §11's own ⚠️, ADR-0020), so a body whose card
    does not resolve could be an Antique Plume Fossil or a Misty's Magikarp — both carry
    unconditional prevent-all-while-Benched. A body that makes no claim is not credited.

    Note the direction: an unknown card's `hp` is still on the board and `prize_value` fails open at
    1, so WITHOUT the guard this board would price as a reachable 1-prize Knock Out."""
    unknown = _bench_board([_poke(UNREADABLE_CARD, hp=10, serial=11)])
    known = _bench_board([_poke(MUNKIDORI, hp=70, damage=60, serial=11)])

    assert _threat_of(unknown) == 0.0
    assert _threat_of(known) > 0.0, "the control: a resolvable body at the same reach DOES price"


@pytest.mark.req("REQ-STATEVALUE-0012")
def test_without_a_bench_RIDER_their_bench_prices_at_nothing_however_soft():
    """The gate is a snipe ROUTE, not proximity to death. Mega Lucario ex prints no rider on either
    attack, so a 10-HP body on their bench is untouchable by it this turn and the family must say
    so — otherwise the widened loop would credit every deck with a bench route it does not have.

    Both boards carry the identical bench; only my Active differs, and Mega Brave's 270 misses their
    320-HP Active on both, so the Active leg is silent either way."""
    bench = [_poke(MUNKIDORI, hp=70, damage=60, serial=11)]
    riderless = _bench_board(bench, my_active=_poke(MEGA_LUC, hp=340, energies=[E_F, E_F]))
    rider = _bench_board(bench)

    assert _threat_of(riderless) == 0.0
    assert _threat_of(rider) > 0.0, "the control: the same bench under an attacker that CAN reach it"


@pytest.mark.req("REQ-STATEVALUE-0012")
def test_the_bench_rider_never_leaks_into_the_ACTIVE_reachability_read():
    """The two legs stay separate. Their Active at 170 HP is out of Jetting Blow's exact 120 and
    would be inside 120 + the 50 rider — but the rider does not land on the Active, and the oracle
    that prices the Active already zeroes it (`combat.predicted_damage`).

    A widening that reached for one damage number per body, rather than one per SEAT, fails here."""
    board = _bench_board([], their_active=_poke(DRAGAPULT, hp=320, damage=150, serial=9))
    assert board.theirs.active.hp_remaining == 170
    assert _threat_of(board) == 0.0

    # …and the control, so a bench leg that reached nothing at all cannot pass: at 120 it does.
    reachable = _bench_board([], their_active=_poke(DRAGAPULT, hp=320, damage=200, serial=9))
    assert _threat_of(reachable) > 0.0


@pytest.mark.req("REQ-STATEVALUE-0012")
def test_the_dragapult_cross_turn_shape_is_priced_BEFORE_the_gust_and_not_only_after():
    """`dragapult_ex`'s doctrine, as two boards a turn apart: *"Phantom Dive is the turn-ender, so
    Munkidori / Boss's / Cruel Arrow resolve BEFORE it and convert **prior-turn** chip."*

    The AFTER half was never the gap — once the gust puts the chipped body in the Active seat, the
    Active leg reads its remaining HP and has done since Issue #281. The BEFORE half is this issue:
    while the body is still benched, the chip is an asset the board carries between turns, and
    nothing priced it. Both halves are asserted so the distinction is executable rather than
    argued."""
    pre_fresh = _bench_board([_poke(MUNKIDORI, hp=70, serial=11)])
    pre_chipped = _bench_board([_poke(MUNKIDORI, hp=70, damage=60, serial=11)])
    post_fresh = _bench_board([], their_active=_poke(MUNKIDORI, hp=70, serial=9))
    post_chipped = _bench_board([], their_active=_poke(MUNKIDORI, hp=70, damage=60, serial=9))

    assert _threat_of(post_fresh) > 0.0 and _threat_of(post_chipped) > 0.0, (
        "after the gust BOTH are reachable — Jetting Blow's 120 covers a fresh 70 HP")
    assert _threat_of(pre_fresh) == 0.0
    assert _threat_of(pre_chipped) > 0.0


# ── sniping a pre-evolution denies a forward payoff (Issue #285) ──────────────────────────────────
#
# `_reachable_target_values` priced a target by `prize_value` alone — what the body yields NOW — so
# killing a Staryu scored exactly as much as killing any other 1-prize body, while the doctrine's
# whole point is that it erases three. Seven of the eight matchup docs make this their primary or
# secondary lever (*"snipe/gust a Staryu before it rush-evolves … to trade 1 prize for a denied 3"*).
#
# The credit is `development.evolve_marginal`'s own expression — `_READINESS_W x (owed_damage /
# PRIZE_DAMAGE_RATE) x halve(hops)` — against `TheirSide.forward_payoff`. No new constant.
#
# **These assertions are made at `_reachable_target_values`, not at `threat`, and that is deliberate
# rather than a convenience.** Every appended target carries `prize_advance >= 1.0` (`prize_value` is
# 1, 2 or 3), so `min(_THREAT_CAP, sum)` with `_THREAT_CAP` 0.1 binds on every frame the loop touches
# and the largest credit measured anywhere on the corpus — 0.054 prizes, Riolu (30) → Mega Lucario ex
# (270) — is invisible in the capped family by construction.
# `test_the_denial_credit_is_INVISIBLE_once_the_cap_binds` asserts exactly that, so the choice of seam
# is itself a claim under test rather than an unexamined one.


def _target_values(model) -> tuple:
    """The UNCAPPED per-target values `threat` is handed — the seam the denial credit changes."""
    return sv._reachable_target_values(model)


def _credit_for(model, card_id: int) -> float:
    """The denial credit for the body carrying ``card_id``, off the SHIPPED helper.

    Read rather than re-derived on purpose: a test that recomputed `_READINESS_W x (owed /
    PRIZE_DAMAGE_RATE) x halve(hops)` would agree with a broken implementation as readily as with a
    correct one. That the credit actually reaches `prize_advance` is a separate claim, asserted
    against `_target_values` on boards with exactly one reachable target."""
    body = next(b for b in model.theirs.bodies if b.card_id == card_id)
    return sv._denied_forward_payoff(model, body)


def _their_hops(model, card_id: int) -> int:
    return model.theirs.forward_payoff(card_id).hops


@pytest.mark.req("REQ-STATEVALUE-0013")
def test_a_pre_evolution_prices_above_an_identical_body_that_evolves_into_nothing():
    """The headline. Two 1-prize bodies at the same 70 HP in the same seat, both inside Jetting
    Blow's 120, differing only in what their line becomes.

    Staryu (1030) evolves into Mega Starmie ex — ONE hop, and 1031 is the only card in the pool whose
    `Previous stage` is ``Staryu`` (Misty's Starmie 361 evolves from Misty's *Staryu*, a different
    line). Munkidori (112) is a Basic that evolves into nothing at all, so it is the control the
    comparison needs: without it a credit that fired on *every* body would pass this test just as
    happily."""
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
    """The hop discount, isolated by a pair that INVERTS without it.

    Both bodies' lines terminate on the same card — Dragapult ex, `maxDamage` 200 — but Dreepy is two
    hops from it and Drakloak is one (`data/EN_Card_Data.csv`: 120's `Previous stage` is ``Dreepy``,
    121's is ``Drakloak``). Dreepy's own printed damage is LOWER (40 against Drakloak's 70), so it is
    owed MORE: 160 against 130. Undiscounted, Dreepy would therefore price ABOVE Drakloak. The only
    thing that can reverse that ordering is `halve(hops)`, which is why this pair is the test and a
    same-owed pair would not be — a same-owed pair passes under any monotone discount, including one
    applied to the wrong quantity."""
    dreepy = _starmie_board(_poke(DREEPY, hp=70, serial=9))
    drakloak = _starmie_board(_poke(DRAKLOAK, hp=90, serial=9))

    assert _their_hops(dreepy, DREEPY) == 2 and _their_hops(drakloak, DRAKLOAK) == 1
    assert _credit_for(dreepy, DREEPY) > 0.0 and _credit_for(drakloak, DRAKLOAK) > 0.0
    assert _credit_for(drakloak, DRAKLOAK) > _credit_for(dreepy, DREEPY), (
        "the two-hop base is owed MORE damage and must still price LESS — the discount, doing work")

    owed_dreepy = dreepy.theirs.forward_payoff(DREEPY).owed_damage
    owed_drakloak = drakloak.theirs.forward_payoff(DRAKLOAK).owed_damage
    assert owed_dreepy > owed_drakloak, (
        "the premise of the inversion: without it this test would pass on the owed damage alone")


@pytest.mark.req("REQ-STATEVALUE-0013")
def test_the_hop_counts_are_THIS_SETS_and_a_mainline_chain_would_fail_here():
    """The card-fact guard the issue asks for, executable.

    The mainline TCG runs Riolu → Lucario → Mega Lucario and Staryu → Starmie → Mega Starmie; this set
    runs neither, and `docs/rulebook.txt` Appendix 1 says so outright — *"Mega Lucario ex doesn't
    evolve from Lucario or Lucario ex—just Riolu"*. A fixture carrying the three-stage chain would
    still produce a plausible credit, just a wrongly-discounted one, so the hop counts are asserted by
    number rather than left implied by the fixture's shape.

    Dreepy → Drakloak → Dragapult ex is the counter-example that keeps this from being a test that
    everything is one hop: it is a genuine two."""
    board = _starmie_board(_poke(MUNKIDORI, hp=110, serial=9))
    assert _their_hops(board, RIOLU) == 1, "Riolu → Mega Lucario ex, no intermediate Lucario"
    assert _their_hops(board, STARYU) == 1, "Staryu → Mega Starmie ex, no intermediate Starmie"
    assert _their_hops(board, DREEPY) == 2, "Dreepy → Drakloak → Dragapult ex"
    assert _their_hops(board, DRAKLOAK) == 1
    assert _their_hops(board, MEGA_LUC) == 0, "a body already in its best form owes no hop"


@pytest.mark.req("REQ-STATEVALUE-0013")
def test_reachability_fails_OPEN_on_their_side_and_CLOSED_on_mine():
    """The one leg of the mirror that cannot be computed, and the direction it degrades in.

    `MySide.forward_payoff` proves a line dead from `unseen_counts` — every copy of the forward form
    visible outside the deck — and `development.line_topology` then CANCELS the credit. Their deck is
    untracked and their hand is a count, so the same proof is unavailable and `TheirSide` fails OPEN.

    Asserted as an asymmetry on ONE card with all three Mega Lucario ex in my discard, so both sides
    answer about the same line on the same board. A test that only checked `reachable is True` on
    their side would pass against a stub that hardcoded True for both sides, which is exactly the
    mistake this shape rules out."""
    board = _model(
        _player(active=_poke(MEGA_STARMIE, hp=330, energies=[E_W]),
                discard=[MEGA_LUC, MEGA_LUC, MEGA_LUC], prize=4),
        _player(active=_poke(RIOLU, hp=80, serial=9), prize=4),
        energy_attached=True)

    assert board.mine.forward_payoff(RIOLU).reachable is False, (
        "the control: my side CAN prove this line dead — all three copies are in my discard")
    assert board.theirs.forward_payoff(RIOLU).reachable is True
    assert board.theirs.forward_payoff(RIOLU).owed_damage > 0.0
    assert _credit_for(board, RIOLU) > 0.0, "…and the credit survives: we cannot prove otherwise"


@pytest.mark.req("REQ-STATEVALUE-0013")
def test_a_body_already_in_its_best_form_gets_no_credit():
    """Mega Starmie ex is the end of its own line, so removing it denies nothing beyond the three
    prizes it already yields — a credit that fired here would pay twice for the same card, once as
    the payoff and once as the denial of itself.

    **This is a NEGATIVE assertion and it cannot bite on the guard it looks like it covers.** Review
    established the accounting: it survives deleting the `hops > 0 and owed_damage > 0` guard, and it
    survives deleting the whole credit — both leave the credit at 0, which is what it asserts. What
    it DOES catch is the regression it is named for: a credit that fired unconditionally, or one
    whose `owed_damage` floor at 0 was lost so a softer forward form read negative-then-credited. Its
    positive control is the sibling above, where the same helper must return a non-zero number on a
    body that IS a pre-evolution; `_forward_credit`'s own docstring records that the guard is a
    defensive no-op today, so nothing here reads as tested when it is not."""
    board = _starmie_board(_poke(MEGA_STARMIE, hp=330, damage=220, serial=9))

    assert _target_values(board) == (3.0,), "exactly its prize count, with nothing added"
    assert _credit_for(board, MEGA_STARMIE) == 0.0


@pytest.mark.req("REQ-STATEVALUE-0013")
def test_the_credit_reaches_a_BENCHED_pre_evolution_which_is_where_they_actually_sit():
    """The seat that matters. The doctrine is *snipe the pre-evo* — a pre-evolution is on their
    Bench, not in front of me — and before Issue #284 this loop never saw a benched body at all.

    Jetting Blow's 50 rider does not cover a fresh 70-HP Staryu, so the board carries the two counters
    that bring it inside. Their Active is a 320-HP Dragapult ex the 120 cannot reach, so the Active
    leg contributes nothing and every value here is the bench leg's."""
    board = _bench_board([_poke(STARYU, hp=70, damage=20, serial=11)])

    assert len(_target_values(board)) == 1, "the benched Staryu, reached by the rider alone"
    assert _credit_for(board, STARYU) > 0.0
    assert _target_values(board) == pytest.approx((1.0 + _credit_for(board, STARYU),))


@pytest.mark.req("REQ-STATEVALUE-0013")
def test_the_two_forward_payoff_suppliers_agree_and_diverge_only_where_the_DECKLIST_does():
    """The word "mirror" made executable — because two implementations of one quantity is exactly the
    shape that drifts, and `MySide._forward_payoff` (a DFS over my decklist's children map, no hop
    cap) and `CombatMath.forward_payoff_terms` (the pool closure plus `_forward_hop_depths`, capped
    at 3) really are two implementations.

    On Riolu both are computable and must agree: `DECK` runs 3 Riolu and 3 Mega Lucario ex, so my
    decklist index and the pool closure see the same single hop to the same card.

    On Staryu they must NOT agree, and that is the deck-agnostic over-read `threat.blind_to` names:
    my side runs no Staryu line, so `MySide.forward_index` has no ``Staryu`` key and the my-side
    reading is the fail-closed `(0.0, 0)` — while their side credits Mega Starmie ex anyway, because
    the pool index cannot know what they run. Asserting BOTH halves is what makes this a test of the
    divergence rather than of the agreement alone."""
    board = _starmie_board(_poke(RIOLU, hp=80, serial=9))

    mine, theirs = board.mine.forward_payoff(RIOLU), board.theirs.forward_payoff(RIOLU)
    assert (mine.owed_damage, mine.hops) == (theirs.owed_damage, theirs.hops) != (0.0, 0), (
        "one line, one number, from two implementations")

    assert board.mine.forward_payoff(STARYU) == (0.0, 0, True), "my decklist runs no Staryu line"
    assert board.theirs.forward_payoff(STARYU).owed_damage > 0.0, (
        "…and theirs credits it regardless, because the pool index is deck-agnostic")


@pytest.mark.req("REQ-STATEVALUE-0013")
def test_the_denial_credit_is_INVISIBLE_once_the_cap_binds():
    """The ceiling on what this issue can deliver, asserted rather than described.

    `threat` is `min(_THREAT_CAP, sum)` and `_THREAT_CAP` is 0.1, while every appended target carries
    `prize_advance >= 1.0` because `prize_value` is 1, 2 or 3 and never less. So the cap binds on
    every frame this loop touches, while the largest credit measured anywhere on the corrections
    corpus is 0.054 prizes. It cannot move the family — on ANY board, not merely on already-firing
    ones.

    This is the same wall Issue #284 measured from the other side, and the unlock is the same parked
    `_THREAT_CAP / _MAX_PRIZE_VALUE` scale anchor, which this track was told not to move. Recorded as
    a test so the next reader meets it as a measurement rather than as a surprise — and so that the
    day the anchor lands, this test fails and points at the packet line."""
    staryu = _starmie_board(_poke(STARYU, hp=70, serial=9))
    dead_end = _starmie_board(_poke(MUNKIDORI, hp=110, damage=40, serial=9))

    assert _target_values(staryu)[0] > _target_values(dead_end)[0], "the seam DOES discriminate"
    assert _threat_of(staryu) == _threat_of(dead_end) == sv._THREAT_CAP, (
        "…and the capped family cannot: both boards saturate at exactly the cap")
    # Not asserted on `state_value` itself: these two boards differ in their Active's own attacks, so
    # `survival` moves between them for a reason that has nothing to do with this credit. The claim
    # under test is about `threat`, and it is made about `threat`.


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
# cases above are not a substitute: a fixture board is one I chose, and the failure mode
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
    board rather than a second fixture wearing a corpus costume.

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


# ── the LEAF PATH's `hand` zero, asserted as RULED rather than merely documented (Issue #331) ──────
#
# `test_holding_a_useful_card_is_worth_something_but_less_than_playing_it_is` above already asserts a
# `hand` zero, but a DIFFERENT one: it scores a hand-built model with no Needs resolution passed in,
# at the `state_value` layer. The zero below is the LEAF PATH's, and its cause lives one module over
# in `planner`. The two propositions are independent, and until Issue #331 only the first was tested.


def _leaf_end_boards(want_blind: int = 20, want_live: int = 2):
    """``(key, pilot, my_index, end)`` for corpus frames FORWARD-SIMULATED to my end-of-turn board,
    split into the two shapes the sim actually produces: ``blind`` (my turn passed to the opponent)
    and ``live`` (the line ENDED THE GAME, so the board never changed perspective).

    Driven through the leaf lab's own offline seam rather than a second harness — `_search_api` +
    `train.leaf_lab._PLACEHOLDER_SBI` are exactly what `leaf_lab.board_leaf_values` injects to
    re-score a correction board without the native engine, so this reads the same leaf the
    Discrimination Gate grades. cgpy is deterministic (`SeededRng(0)`), so the split is stable.

    Stops as soon as both shapes are stocked (measured: ~4 s, against ~11 s for the whole corpus);
    the caps are floors on the sample, not an assumption about where in the corpus each shape sits."""
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
    """The leaf path prices `hand` at exactly 0.0, and that is **RULED, not broken** — Issue #331,
    developer ruling 2026-08-02 (option 1 of three: leave the ruling, let Issue #263 absorb it).

    The chain, asserted link by link rather than assumed, because each link is the one a future
    change would break silently:

      1. `_simulate_line` stops when the select passes to the opponent, so the end observation is
         **opponent-perspective** and my hand is hidden — `handCount` survives, the `hand` list does
         not. That is the substrate fact `planner._simulate_line`'s comment block records, and it is
         why `leaf_hand_value` (the capture that works around it) stays off in every production path.
      2. `planner._leaf_needs_resolution` therefore returns **None** (`if not me.get("hand")`).
      3. `_hand_legs` returns all zeros for a `None` resolution, so the family prices `0.0` — the
         REAL zero `state_value.REGISTRY`'s `hand.blind_to` names in as many words: *"MY HAND on a
         simulated end board — the whole family prices 0 there."*

    **Why this test exists.** Issue #331 is held open for a re-measurement once Issue #263's 1-ply
    ordering scores boards where `hand` is expected to be live, and 15 gate frames are held out
    against exactly that expectation. Until now the ruled zero was documented in three places
    (`planner.py`'s comment block, `hand.blind_to`, the hold-out ledger's `why` strings) and asserted
    in none — and documentation is not a regression guard. If Issue #263 makes `hand` live on this
    path, or a change flips `leaf_hand_value`'s default, or `_leaf_needs_resolution` starts returning
    a resolution, this test fails LOUDLY and names the ruling instead of letting the 15 held-out
    frames quietly stop measuring what they were held out to measure.

    The `handCount` assertion is what stops the zero from being read off an empty hand — a hand with
    no cards in it prices zero for a reason that has nothing to do with this ruling. And the second
    loop is the positive control the negative claim needs (CLAUDE.md): a line that ENDS THE GAME never
    hands the select over, so its end board stays MY perspective, carries a real `hand`, resolves, and
    prices strictly above zero. Same instrument, same leaf-built model, non-zero answer — so the zeros
    above are a measurement rather than a broken reader. Measured on the full corpus: 282 frames blind
    and 19 game-over, and the two sets partition exactly on `result != -1`."""
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
