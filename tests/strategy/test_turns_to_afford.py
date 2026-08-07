"""`CombatMath.turns_to_afford` — the deny-clock's energy/evolve model.

"Armed" = the line's biggest-attack COST is payable (NOT lethality), at the attach quota, in PARALLEL
with the forward hops (the MAX of the two legs, never the sum); `attaches_per_turn` parameterizes it.
Issue #204 credits a `discard_energy_recur` line's own discard reload at the `self_arming` scope.
Issue #286 adds the EXPIRING-Energy strip as a SIBLING at the model accessor — the oracle below is
untouched, so `pilot._opp_turns_to_ready` delegates to it byte-identically.
"""
from card_facts import ignition_tags                    # the committed Ignition Energy tags, ONE copy
from common.cards import CardFunctions
from common.effects import CardEffects
from common.strategy.combat import CombatMath
from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider

RIOLU = 677
MLUC = 678          # Mega Lucario ex — one hop from Riolu (rulebook Appendix 1)

#: **Ignition Energy** (verified at `data/EN_Card_Data.csv`): a Special Energy providing {C}, or
#: {C}{C}{C} on an Evolution, discarded at end of turn. The ONLY such card in the 1267-card pool.
IGNITION = 17
COLORLESS, FIGHTING = 0, 6


def _combat():
    stats = DictCardStatProvider({
        RIOLU: CardStat(RIOLU, synthetic=True, name='Riolu', hp=70, maxDamageCost=1, maxDamage=30, attacks=(11,)),
        MLUC: CardStat(MLUC, name="Mega Lucario ex", hp=340, megaEx=True, evolvesFrom="Riolu",
                       maxDamageCost=2, maxDamage=270, attacks=(21, 22)),
    }, attacks={11: AttackStat(11, damage=30, cost=1),
                21: AttackStat(21, damage=130, cost=1), 22: AttackStat(22, damage=270, cost=2)})
    return CombatMath(stats, functions=None, transients=None)


def _b(cid, n):
    return {"id": cid, "energies": [0] * n}


# REQ-TTR-0001 — the parallel lookahead: MAX(energy leg, forward-hop leg), matching _opp_turns_to_ready.
def test_parallel_lookahead_energy_and_evolve_legs():
    c = _combat()
    # Riolu 1 Energy: line max cost = max(1, 2) = 2, deficit 2-1 = 1; one hop to Mega Lucario ex →
    # max(ceil(1/1), 1) = 1.
    assert c.turns_to_afford(_b(RIOLU, 1)) == 1
    # Riolu 0 Energy: deficit 2, one hop → max(2, 1) = 2.
    assert c.turns_to_afford(_b(RIOLU, 0)) == 2
    # Mega Lucario ex with 2 Energy: no forward, deficit 0, 0 hops → armed NOW.
    assert c.turns_to_afford(_b(MLUC, 2)) == 0


# REQ-TTR-0002 — fail-closed None on an unknown body or no known biggest-attack cost.
def test_none_when_unknown_or_no_cost():
    c = _combat()
    assert c.turns_to_afford({"id": 424242, "energies": [0]}) is None
    assert c.turns_to_afford(None) is None


# REQ-TTR-0003 — the policy parameter: a faster attach rate shortens the ENERGY leg (rounding up).
def test_attaches_per_turn_scales_the_energy_leg():
    c = _combat()
    # Riolu 0 Energy: energy deficit 2. At 2 attaches/turn the energy leg is ceil(2/2)=1, so the
    # EVOLVE leg (1 hop) now co-dominates → 1; the slow default (1/turn) is 2.
    assert c.turns_to_afford(_b(RIOLU, 0), attaches_per_turn=2) == 1
    assert c.turns_to_afford(_b(RIOLU, 0), attaches_per_turn=1) == 2


# REQ-TTR-0004 — the Pilot deny-clock read DELEGATES to the SNAPSHOT's `theirs.turns_to_afford`,
# where the forward index, the discard and the energy policy already live.
def test_opp_turns_to_ready_delegates_to_the_snapshot_route():
    from train.tune import _build_pilot
    p = _build_pilot("mega_lucario")[0]
    obs = {"current": {"yourIndex": 0, "players": [
        {"active": [{"id": 999999, "hp": 100, "energies": []}]},
        {"active": [{"id": MLUC, "hp": 340, "energies": []}], "bench": []},
    ]}}
    model = p._snapshot(obs)
    for body in ({"id": RIOLU, "energies": [0]}, {"id": MLUC, "energies": [0, 0]},
                 {"id": 424242, "energies": []}, None):
        assert p._opp_turns_to_ready(body) == model.theirs.turns_to_afford(body)
    # …and WITHOUT a snapshot the read makes no claim, which is the same fail-closed answer an
    # unknown stat gives: the caller emits no deny slot rather than one graded off a guess.
    p._state_model = None
    assert p._opp_turns_to_ready({"id": RIOLU, "energies": [0]}) is None


# REQ-TTR-0005 (Issue #204) — the clock credits a `discard_energy_recur` line's own DISCARD reload:
# Assemble Alloy attaches 2 Basic {M} from the discard on evolving (data/EN_Card_Data.csv).
def _recur_model(pre_energy=0, discard=2):
    """A Duraludon → Archaludon ex line with {M} in their discard. The clock is asked about the
    PRE-EVOLUTION: Assemble Alloy fires as Duraludon evolves, on the very hop being counted."""
    from common.cards import CardFunctions
    from common.effects import CardEffects
    from common.state_model import StateModel
    DURA, ARCH, METAL, METAL_ENERGY = 189, 190, 8, 71
    stats = DictCardStatProvider({
        DURA: CardStat(DURA, synthetic=True, name="Duraludon", hp=110, maxDamageCost=1, maxDamage=30,
                       attacks=(30,), energyType=METAL),
        ARCH: CardStat(ARCH, synthetic=True, name='Archaludon ex', hp=280, evolvesFrom="Duraludon",
                       maxDamageCost=3, maxDamage=220, attacks=(31,), energyType=METAL),
        METAL_ENERGY: CardStat(METAL_ENERGY, synthetic=True, name="Basic {M} Energy", energyType=METAL,
                               cardType=5),
    }, attacks={30: AttackStat(30, damage=30, cost=1, energyTypes=(METAL,)),
                31: AttackStat(31, damage=220, cost=3, energyTypes=(METAL, METAL, METAL))})
    combat = CombatMath(stats, functions=CardFunctions({ARCH: ["discard_energy_recur"]}),
                        transients=None, effects=CardEffects.load())
    body = {"id": DURA, "energies": [METAL_ENERGY] * pre_energy}
    obs = {"current": {"yourIndex": 0, "players": [
        {"active": []},
        {"active": [body], "bench": [],
         "discard": [{"id": METAL_ENERGY}] * discard},
    ]}}
    return StateModel.build(obs, combat=combat), body


def test_the_clock_credits_an_on_evolve_discard_reload():
    # Duraludon on 1 {M}: the line's biggest attack is Metal Defender {M}{M}{M}, so the bare clock
    # owes 2 more attaches → 2 turns (the hop is 1, and the legs run in PARALLEL).
    model, body = _recur_model(pre_energy=1)
    assert model.theirs.turns_to_afford(body, fuelled=False) == 2
    # Assemble Alloy attaches up to 2 Basic {M} from the discard AS the evolution is played, and the
    # evolved body is itself {M}, so both land here: 1 + 2 = 3 → armed on the hop turn.
    assert model.theirs.turns_to_afford(body) == 1
    # An empty discard has nothing to reload — the credit is a read of a real zone, not an allowance.
    dry, dry_body = _recur_model(pre_energy=1, discard=0)
    assert dry.theirs.turns_to_afford(dry_body) == 2


def test_the_clock_refuses_an_on_attack_bench_only_reload():
    """Aura Jab is an ATTACK reloading the BENCH, never the attacker (data/EN_Card_Data.csv), so
    crediting it toward arming that same body would be circular — `self_arming` reads 0."""
    from common.cards import CardFunctions
    from common.effects import CardEffects
    FIGHTING, F_ENERGY = 6, 6
    stats = DictCardStatProvider({
        RIOLU: CardStat(RIOLU, synthetic=True, name='Riolu', hp=70, maxDamageCost=1, maxDamage=30, attacks=(11,),
                        energyType=FIGHTING),
        MLUC: CardStat(MLUC, name="Mega Lucario ex", hp=340, megaEx=True, evolvesFrom="Riolu",
                       maxDamageCost=2, maxDamage=270, attacks=(21, 22), energyType=FIGHTING),
        F_ENERGY: CardStat(F_ENERGY, name="Basic {F} Energy", energyType=FIGHTING, cardType=5),
    }, attacks={11: AttackStat(11, damage=30, cost=1, energyTypes=(FIGHTING,)),
                21: AttackStat(21, damage=130, cost=1, energyTypes=(FIGHTING,)),
                22: AttackStat(22, damage=270, cost=2, energyTypes=(FIGHTING, FIGHTING))})
    combat = CombatMath(stats, functions=CardFunctions({MLUC: ["discard_energy_recur"]}),
                        transients=None, effects=CardEffects.load())
    body, discard = _b(RIOLU, 0), {FIGHTING: 3}
    assert combat.discard_recur_fuel(body, discard) == 3                    # the caution reading
    assert combat.discard_recur_fuel(body, discard, scope="self_arming") == 0   # the clock reading


def test_the_arming_scope_fails_closed_without_a_clause():
    """A tagged line the Effect-Clause compendium says nothing about yields NOTHING — ADR-0067's rule
    that the tag ROUTES and the clause QUANTIFIES, one zone over."""
    from common.cards import CardFunctions
    from common.effects import CardEffects
    UNKNOWN, FIGHTING = 990001, 6
    stats = DictCardStatProvider({
        UNKNOWN: CardStat(UNKNOWN, name="Untabulated", hp=100, maxDamageCost=3, maxDamage=200,
                          attacks=(41,), energyType=FIGHTING),
    }, attacks={41: AttackStat(41, damage=200, cost=3)})
    combat = CombatMath(stats, functions=CardFunctions({UNKNOWN: ["discard_energy_recur"]}),
                        transients=None, effects=CardEffects.load())
    body = {"id": UNKNOWN, "energies": []}
    assert combat.discard_recur_fuel(body, {FIGHTING: 3}) == 3
    assert combat.discard_recur_fuel(body, {FIGHTING: 3}, scope="self_arming") == 0


# ── Issue #286 — the EXPIRING-Energy strip ───────────────────────────────────────────────────────
# An Energy the rules discard at the end of THIS turn cannot answer "how many turns until armed?".

STARYU, MSTAR = 1030, 1031      # Staryu → Mega Starmie ex: ONE hop, no "Starmie" in this line
WATER_GUN, JETTING_BLOW, NEBULA_BEAM = 1486, 1487, 1488
WATER = 3


def _ignition_combat():
    """A Staryu → Mega Starmie ex line plus the two Energy cards the strip must tell apart. Every field
    verified at `data/EN_Card_Data.csv`."""
    stats = DictCardStatProvider({
        STARYU: CardStat(STARYU, name="Staryu", hp=70, energyType=WATER, maxDamageCost=1,
                         maxDamage=20, attacks=(WATER_GUN,)),
        MSTAR: CardStat(MSTAR, name="Mega Starmie ex", hp=330, megaEx=True, evolvesFrom="Staryu",
                        energyType=WATER, maxDamageCost=3, maxDamage=210,
                        attacks=(JETTING_BLOW, NEBULA_BEAM)),
        IGNITION: CardStat(IGNITION, name="Ignition Energy", cardType=6, energyType=COLORLESS),
        WATER: CardStat(WATER, name="Basic {W} Energy", cardType=5, energyType=WATER),
    }, attacks={WATER_GUN: AttackStat(WATER_GUN, damage=20, cost=1, energyTypes=(WATER,)),
                JETTING_BLOW: AttackStat(JETTING_BLOW, damage=120, cost=1, energyTypes=(WATER,)),
                NEBULA_BEAM: AttackStat(NEBULA_BEAM, damage=210, cost=3,
                                        energyTypes=(COLORLESS, COLORLESS, COLORLESS))})
    return CombatMath(stats,
                      functions=CardFunctions({IGNITION: ignition_tags()}),
                      transients=None,
                      effects=CardEffects({IGNITION: [{"kind": "energy_provide", "amount": 1,
                                                       "amount_on_evolution": 3,
                                                       "type": "colorless",
                                                       "rider": "discard_eot"}]}))


def _held(cid, cards, units):
    """A body holding ``cards`` (CARD ids on ``energyCards``) providing ``units`` (EnergyType codes on
    ``energies``): one Ignition on an Evolution is ONE `energyCards` entry and THREE in `energies`."""
    return {"id": cid, "energies": list(units), "energyCards": [{"id": c} for c in cards]}


# REQ-TTR-0006 (Issue #286) — the strip removes the UNITS a `discard_eot` card provides, sized by
# the holder's stage, and leaves everything else exactly where it was.
def test_the_strip_removes_an_expiring_cards_units_and_nothing_else():
    c = _ignition_combat()
    # On an EVOLUTION Ignition provides {C}{C}{C}: three units leave, the card leaves, nothing stays.
    evo = _held(MSTAR, [IGNITION], [COLORLESS] * 3)
    assert c.without_expiring_energy(evo) == {"id": MSTAR, "energies": [], "energyCards": []}
    # On a BASIC it provides {C}: one unit leaves. Same card, different holder, different size — the
    # provision is a function of the HOLDER's stage, which is why the strip may not assume a count.
    basic = _held(STARYU, [IGNITION], [COLORLESS])
    assert c.without_expiring_energy(basic) == {"id": STARYU, "energies": [], "energyCards": []}
    # A Basic Energy beside it SURVIVES — the regression the issue names.
    mixed = _held(MSTAR, [WATER, IGNITION], [WATER, COLORLESS, COLORLESS, COLORLESS])
    assert c.without_expiring_energy(mixed) == {"id": MSTAR, "energies": [WATER],
                                               "energyCards": [{"id": WATER}]}


# REQ-TTR-0006 — a body with nothing expiring is returned UNCHANGED **by identity**: the strip runs
# on every `readiness` call, so "unchanged" must mean no allocation and no re-keying.
def test_a_body_with_nothing_expiring_is_returned_UNCHANGED():
    c = _ignition_combat()
    plain = _held(MSTAR, [WATER, WATER], [WATER, WATER])
    assert c.without_expiring_energy(plain) is plain
    assert c.without_expiring_energy(None) is None
    # No `energyCards` key at all makes NO claim — card identity is what the rider is read from, so
    # without it nothing is provably expiring. Fail-closed.
    bare = {"id": MSTAR, "energies": [COLORLESS] * 3}
    assert c.without_expiring_energy(bare) is bare
    # An unresolvable HOLDER is the same refusal: the provision is stage-dependent, so an unknown
    # stage cannot size the removal.
    unknown = _held(424242, [IGNITION], [COLORLESS] * 3)
    assert c.without_expiring_energy(unknown) is unknown


# REQ-TTR-0006 — the RIDER is read from the CLAUSE, not the Function Tag: ADR-0032's split is that
# the tag ROUTES while the clause QUANTIFIES.
def test_the_strip_reads_the_CLAUSE_not_the_TAG():
    stats = DictCardStatProvider({
        MSTAR: CardStat(MSTAR, name="Mega Starmie ex", hp=330, evolvesFrom="Staryu",
                        maxDamageCost=3, maxDamage=210, attacks=(NEBULA_BEAM,)),
        IGNITION: CardStat(IGNITION, name="Ignition Energy", cardType=6, energyType=COLORLESS),
    }, attacks={NEBULA_BEAM: AttackStat(NEBULA_BEAM, damage=210, cost=3,
                                        energyTypes=(COLORLESS,) * 3)})
    body = _held(MSTAR, [IGNITION], [COLORLESS] * 3)
    tags = CardFunctions({IGNITION: ["discard_eot", "provides_evo:3"]})
    tag_only = CombatMath(stats, functions=tags, transients=None, effects=CardEffects({}))
    assert tag_only.without_expiring_energy(body) is body, "the TAG alone must not strip"
    # ...and with no clause compendium at all the strip makes no claim either (fail-CLOSED, ADR-0067).
    blind = CombatMath(stats, functions=tags, transients=None, effects=None)
    assert blind.without_expiring_energy(body) is body


# REQ-TTR-0006 — the strip DETECTS through `card_effects.json` and SIZES through
# `card_functions.json`, so a drift between the two committed stores strips the wrong unit count.
def test_the_clause_and_the_tag_agree_about_every_expiring_cards_provision():
    functions, effects = CardFunctions.load(), CardEffects.load()
    checked = 0
    for cid in range(1, 1300):
        for clause in (effects.clauses(cid) or ()):
            if clause.get("rider") != "discard_eot":
                continue
            checked += 1
            assert functions.energy_provision(cid, evolution=False) == clause["amount"]
            assert functions.energy_provision(cid, evolution=True) == clause["amount_on_evolution"]
    assert checked == 1, ("the pool's discard_eot population changed — re-read the new card and "
                          "re-check the strip, do not just bump this number")


def _starmie_model(units, cards, *, cid=MSTAR):
    from common.state_model import StateModel
    body = _held(cid, cards, units)
    obs = {"current": {"yourIndex": 0, "energyAttached": True, "players": [
        {"active": [body], "bench": [], "hand": [], "handCount": 0, "discard": [],
         "prize": [None] * 4, "deckCount": 20},
        {"active": [], "bench": [], "prize": [None] * 4, "deckCount": 20},
    ]}}
    return StateModel.build(obs, combat=_ignition_combat()), body


# REQ-TTR-0007 (Issue #286) — the INCUMBENT read did not move: this adds a SIBLING reading, and
# `pilot._opp_turns_to_ready` delegates to the same oracle byte-identically.
def test_the_incumbent_turns_to_afford_read_is_BYTE_IDENTICAL():
    oracle = _ignition_combat()
    for units, cards in (([COLORLESS] * 3, [IGNITION]),          # armed by an evaporating Energy
                         ([WATER, COLORLESS], [WATER, IGNITION]),
                         ([WATER, WATER], [WATER, WATER]),       # nothing expiring
                         ([], [])):
        model, body = _starmie_model(units, cards)
        assert model.mine.turns_to_afford(model.mine.active) == oracle.turns_to_afford(
            body, attaches_per_turn=1, typed=True), (units, cards)
        # explicitly False is the same read as omitting it — no hidden default drift
        assert (model.mine.turns_to_afford(model.mine.active, exclude_expiring=False)
                == model.mine.turns_to_afford(model.mine.active))


# REQ-TTR-0007 — and the flagged read is a DIFFERENT number exactly where something expires.
def test_exclude_expiring_lengthens_the_clock_only_where_something_expires():
    # Mega Starmie ex armed for Nebula Beam by ONE Ignition: armed NOW on the incumbent read, three
    # attaches away once the card that armed it is priced as the loan it is.
    model, _ = _starmie_model([COLORLESS] * 3, [IGNITION])
    assert model.mine.turns_to_afford(model.mine.active) == 0
    assert model.mine.turns_to_afford(model.mine.active, exclude_expiring=True) == 3
    # The same body funded by real Water: nothing expires, so the two readings are the same number.
    plain, _ = _starmie_model([WATER, WATER, WATER], [WATER, WATER, WATER])
    assert plain.mine.turns_to_afford(plain.mine.active) == 0
    assert plain.mine.turns_to_afford(plain.mine.active, exclude_expiring=True) == 0
    # A PARTIAL loan: Staryu holds one Ignition ({C} on a Basic) toward Nebula Beam {C}{C}{C} — the
    # incumbent counts the unit and reads two attaches; without it the deficit is the full three.
    staryu, _ = _starmie_model([COLORLESS], [IGNITION], cid=STARYU)
    assert staryu.mine.turns_to_afford(staryu.mine.active) == 2
    assert staryu.mine.turns_to_afford(staryu.mine.active, exclude_expiring=True) == 3
