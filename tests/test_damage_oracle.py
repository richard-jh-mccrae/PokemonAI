"""The damage oracle (ADR-0032 E1): ONE closed-form `compute_active_damage` every Tier-0 damage
estimate routes through — printed damage bent by the defender's Weakness/Resistance and
damage-prevention Ability, each pierced by the attack's own ignore flags. The motivating goldens:
Mega Starmie ex vs Crustle (prevent_ex_damage) — Nebula Beam lands 210 (ignores effects),
Jetting Blow lands 0 on the Active (its 50 bench rider is a separate, unaffected path).

Requirements: REQ-DMG-0004 (ex-damage prevention, pierced by ignoresEffects), REQ-DMG-0005
(Weakness x2 / Resistance -30, each pierced by its flag; W-then-R order; floor 0), REQ-DMG-0006
(fail-open degradation: missing stats/tags never invent a modifier).
"""
import pytest

from common.scouting.provider import AttackStat, CardStat
from common.strategy.damage import compute_active_damage

PSYCHIC, WATER, FIGHTING = 3, 2, 1   # arbitrary distinct energy-type ids, fixtures only

MEGA_STARMIE = CardStat(cardId=1031, name="Mega Starmie ex", hp=300, megaEx=True, energyType=PSYCHIC)
NON_EX = CardStat(cardId=50, name="Staryu", hp=70, energyType=PSYCHIC)
CRUSTLE = CardStat(cardId=345, name="Crustle", hp=140, energyType=FIGHTING)   # prevention lives in TAGS
CRUSTLE_TAGS = frozenset({"prevent_ex_damage"})

NEBULA = AttackStat(attackId=1488, damage=210, cost=3,
                    ignoresWeakness=True, ignoresResistance=True, ignoresEffects=True)
JETTING = AttackStat(attackId=1487, damage=120, cost=1, benchSnipe=50)


@pytest.mark.req("REQ-DMG-0004")
def test_nebula_beam_pierces_crustle_prevention():
    assert compute_active_damage(NEBULA, MEGA_STARMIE, CRUSTLE, CRUSTLE_TAGS) == 210


@pytest.mark.req("REQ-DMG-0004")
def test_jetting_blow_is_prevented_by_crustle():
    assert compute_active_damage(JETTING, MEGA_STARMIE, CRUSTLE, CRUSTLE_TAGS) == 0


@pytest.mark.req("REQ-DMG-0004")
def test_prevention_only_stops_ex_attackers():
    assert compute_active_damage(JETTING, NON_EX, CRUSTLE, CRUSTLE_TAGS) == 120


@pytest.mark.req("REQ-DMG-0005")
def test_weakness_doubles_unless_ignored():
    weak = CardStat(cardId=9, name="WeakToPsychic", hp=200, weakness=PSYCHIC, energyType=WATER)
    assert compute_active_damage(JETTING, MEGA_STARMIE, weak, frozenset()) == 240
    assert compute_active_damage(NEBULA, MEGA_STARMIE, weak, frozenset()) == 210   # ignoresWeakness


@pytest.mark.req("REQ-DMG-0005")
def test_resistance_subtracts_30_unless_ignored_and_floors_at_zero():
    resist = CardStat(cardId=10, name="ResistsPsychic", hp=200, resistance=PSYCHIC, energyType=WATER)
    assert compute_active_damage(JETTING, MEGA_STARMIE, resist, frozenset()) == 90
    assert compute_active_damage(NEBULA, MEGA_STARMIE, resist, frozenset()) == 210  # ignoresResistance
    chip = AttackStat(attackId=1, damage=20)
    assert compute_active_damage(chip, MEGA_STARMIE, resist, frozenset()) == 0      # never negative


@pytest.mark.req("REQ-DMG-0005")
def test_weakness_applies_before_resistance():
    both = CardStat(cardId=11, name="WeakAndResist", hp=300,
                    weakness=PSYCHIC, resistance=PSYCHIC, energyType=WATER)
    # (120x2)-30, not (120-30)x2 — order per rules.md §5
    assert compute_active_damage(JETTING, MEGA_STARMIE, both, frozenset()) == 210


@pytest.mark.req("REQ-DMG-0006")
def test_missing_stats_degrade_to_printed_damage():
    assert compute_active_damage(JETTING, None, CRUSTLE, CRUSTLE_TAGS) == 120   # unknown attacker: no
    assert compute_active_damage(JETTING, MEGA_STARMIE, None, frozenset()) == 120  # modifiers invented
    assert compute_active_damage(None, MEGA_STARMIE, CRUSTLE, CRUSTLE_TAGS) == 0   # no attack record


@pytest.mark.req("REQ-DMG-0006")
def test_prevention_needs_the_tag_not_just_an_ex_attacker():
    assert compute_active_damage(JETTING, MEGA_STARMIE, CRUSTLE, frozenset()) == 120


BEST_PUNCH = AttackStat(attackId=142, damage=40, cost=1, damageMin=0, damageMax=40)
TUMBLING = AttackStat(attackId=114, damage=10, cost=1, damageMin=10, damageMax=30)
MIND_RULER = AttackStat(attackId=123, damage=0, cost=3, scaleVar="def_hand", scalePerUnit=30)
PSYCHIC_339 = AttackStat(attackId=339, damage=10, cost=1,
                         scaleVar="def_active_energy", scalePerUnit=50)
POWERFUL_HAND = AttackStat(attackId=1072, damage=0, cost=1, scaleVar="atk_hand", scalePerUnit=20,
                           ignoresWeakness=True, ignoresResistance=True, ignoresEffects=True)


@pytest.mark.req("REQ-DMG-0009")
def test_visible_state_scaling_is_exact_given_context():
    v = CardStat(cardId=9, name="Vanilla", hp=300, energyType=2)
    ctx = {"def_hand": 7, "def_active_energy": 3, "atk_hand": 5}
    assert compute_active_damage(MIND_RULER, NON_EX, v, frozenset(), context=ctx) == 210
    assert compute_active_damage(PSYCHIC_339, NON_EX, v, frozenset(), context=ctx) == 160
    # counters land THROUGH Crustle's prevention, un-doubled, from an ex attacker
    assert compute_active_damage(POWERFUL_HAND, MEGA_STARMIE, CRUSTLE, CRUSTLE_TAGS,
                                 context=ctx) == 100
    # no context -> scaling term contributes nothing (base only)
    assert compute_active_damage(MIND_RULER, NON_EX, v, frozenset()) == 0


@pytest.mark.req("REQ-DMG-0009")
def test_damage_type_scaling_is_weakness_adjusted():
    weak = CardStat(cardId=9, name="WeakToPsychic", hp=400, weakness=PSYCHIC, energyType=WATER)
    ctx = {"def_hand": 4}
    # (0+30x4)x2 — scaled DAMAGE still counts as damage: Weakness applies
    assert compute_active_damage(MIND_RULER, MEGA_STARMIE, weak, frozenset(), context=ctx) == 240


@pytest.mark.req("REQ-DMG-0008")
def test_bound_selects_floor_ceiling_or_printed():
    v = CardStat(cardId=9, name="Vanilla", hp=200, energyType=2)
    assert compute_active_damage(BEST_PUNCH, NON_EX, v, frozenset(), bound="min") == 0
    assert compute_active_damage(BEST_PUNCH, NON_EX, v, frozenset(), bound="max") == 40
    assert compute_active_damage(BEST_PUNCH, NON_EX, v, frozenset()) == 40          # exact = printed
    assert compute_active_damage(TUMBLING, NON_EX, v, frozenset(), bound="max") == 30
    # deterministic attack: bounds None -> every bound reads printed damage
    assert compute_active_damage(JETTING, MEGA_STARMIE, v, frozenset(), bound="min") == 120


@pytest.mark.req("REQ-DMG-0008")
def test_bounds_are_modifier_adjusted_like_any_damage():
    weak = CardStat(cardId=9, name="WeakToPsychic", hp=200, weakness=PSYCHIC, energyType=WATER)
    tumbling_psy = AttackStat(attackId=1, damage=10, damageMin=10, damageMax=30)
    assert compute_active_damage(tumbling_psy, MEGA_STARMIE, weak, frozenset(), bound="max") == 60


SYLVEON = CardStat(cardId=330, name="Sylveon", hp=130, energyType=1, preventsDamageFrom="ex")
FARIGIRAF = CardStat(cardId=83, name="Farigiraf ex", hp=300, ex=True, energyType=3,
                     preventsDamageFrom="basic_ex")
DREDNAW = CardStat(cardId=158, name="Drednaw", hp=180, energyType=2, preventsDamageAtLeast=200)
MUDSDALE = CardStat(cardId=383, name="Mudsdale", hp=140, energyType=1, damageReduction=30)
BASIC_EX = CardStat(cardId=60, name="BasicEx", hp=200, ex=True, energyType=3)   # no evolvesFrom = Basic
STAGE1_EX = CardStat(cardId=61, name="Stage1Ex", hp=280, ex=True, energyType=3, evolvesFrom="Base")


@pytest.mark.req("REQ-DMG-0010")
def test_parsed_prevention_field_closes_the_untagged_sylveon_gap():
    # Sylveon has Crustle's ability but NO prevent_ex_damage tag — FIELD zeroes ex damage anyway
    assert compute_active_damage(JETTING, MEGA_STARMIE, SYLVEON, frozenset()) == 0
    assert compute_active_damage(NEBULA, MEGA_STARMIE, SYLVEON, frozenset()) == 210   # pierces
    assert compute_active_damage(JETTING, NON_EX, SYLVEON, frozenset()) == 120        # non-ex lands


@pytest.mark.req("REQ-DMG-0010")
def test_basic_ex_prevention_is_stage_scoped():
    assert compute_active_damage(JETTING, BASIC_EX, FARIGIRAF, frozenset()) == 0      # Basic ex: blocked
    assert compute_active_damage(JETTING, STAGE1_EX, FARIGIRAF, frozenset()) == 120   # evolved ex: lands
    assert compute_active_damage(JETTING, NON_EX, FARIGIRAF, frozenset()) == 120      # non-ex: lands


@pytest.mark.req("REQ-DMG-0010")
def test_threshold_prevention_zeroes_only_big_hits():
    big = AttackStat(attackId=2, damage=200)
    assert compute_active_damage(big, NON_EX, DREDNAW, frozenset()) == 0              # >=200: prevented
    assert compute_active_damage(JETTING, NON_EX, DREDNAW, frozenset()) == 120        # small: lands
    # ENGINE-VERIFIED 2026-07-02 (forced-defender audit): Blood Moon 240 (plain) vs Drednaw dealt 0;
    # Nebula Beam 210 dealt 210 — ignoresEffects pierces threshold prevention too
    assert compute_active_damage(NEBULA, MEGA_STARMIE, DREDNAW, frozenset()) == 210
    # Weakness pushes 120 over threshold: 120x2=240 >= 200 -> prevented
    weak_drednaw = CardStat(cardId=158, name="Drednaw", hp=180, weakness=PSYCHIC, energyType=2,
                            preventsDamageAtLeast=200)
    assert compute_active_damage(JETTING, MEGA_STARMIE, weak_drednaw, frozenset()) == 0


@pytest.mark.req("REQ-DMG-0010")
def test_flat_reduction_applies_after_weakness_and_is_pierced_by_ignores_effects():
    assert compute_active_damage(JETTING, NON_EX, MUDSDALE, frozenset()) == 90        # 120-30
    weak_mud = CardStat(cardId=383, name="Mudsdale", hp=140, weakness=PSYCHIC, energyType=1,
                        damageReduction=30)
    assert compute_active_damage(JETTING, MEGA_STARMIE, weak_mud, frozenset()) == 210  # (120x2)-30
    assert compute_active_damage(NEBULA, MEGA_STARMIE, MUDSDALE, frozenset()) == 210   # ignoresEffects
    chip = AttackStat(attackId=3, damage=20)
    assert compute_active_damage(chip, NON_EX, MUDSDALE, frozenset()) == 0             # floors at 0


HAMMER = AttackStat(attackId=1046, damage=0, cost=2, hiddenPerUnit=100, hiddenSample=6,
                    hiddenEnergyType=3)


@pytest.mark.req("REQ-DMG-0018")
def test_hidden_scaler_uses_exact_deck_facts_when_known():
    v = CardStat(cardId=9, name="Vanilla", hp=700, energyType=2)
    # deck of 8 w/ 4 Basic {W}: discarding 6 MUST hit >= 6-(8-4) = 2 -> sound floor 200;
    # EV = 6 x 4/8 = 3 -> exact 300; ceiling capped by the 4 W actually left -> 400
    ctx = {"atk_deck_count": 8, "atk_deck_basic_by_type": {3: 4}}
    assert compute_active_damage(HAMMER, NON_EX, v, frozenset(), bound="min", context=ctx) == 200
    assert compute_active_damage(HAMMER, NON_EX, v, frozenset(), context=ctx) == 300
    assert compute_active_damage(HAMMER, NON_EX, v, frozenset(), bound="max", context=ctx) == 400
    # deck facts absent -> prior conservative behavior (floor 0, ceiling perUnit x sample)
    assert compute_active_damage(HAMMER, NON_EX, v, frozenset(), bound="min") == 0
    assert compute_active_damage(HAMMER, NON_EX, v, frozenset(), bound="max") == 600
RIPTIDE = AttackStat(attackId=1042, damage=0, cost=1, scaleVar="atk_discard_energy",
                     scalePerUnit=20, scaleEnergyType=3)
ANY_ENERGY_446 = AttackStat(attackId=446, damage=30, cost=2, scaleVar="atk_discard_energy",
                            scalePerUnit=20)


@pytest.mark.req("REQ-DMG-0017")
def test_discard_scaler_reads_typed_histogram_from_context():
    v = CardStat(cardId=9, name="Vanilla", hp=300, energyType=2)
    ctx = {"atk_discard_energy_total": 7, "atk_discard_basic_by_type": {3: 5, 1: 2}}
    # Riptide: 20 x 5 Basic {W} in ATTACKER's discard — exact, visible state
    assert compute_active_damage(RIPTIDE, NON_EX, v, frozenset(), context=ctx) == 100
    # 446: +20 x ALL 7 Energy cards (no type filter): 30+140
    assert compute_active_damage(ANY_ENERGY_446, NON_EX, v, frozenset(), context=ctx) == 170
    # no context -> conservative base only
    assert compute_active_damage(RIPTIDE, NON_EX, v, frozenset()) == 0


@pytest.mark.req("REQ-DMG-0011")
def test_hidden_state_scaler_bounds():
    v = CardStat(cardId=9, name="Vanilla", hp=400, energyType=2)
    # ceiling: every sampled card could be fuel — the Incoming threat model (600)
    assert compute_active_damage(HAMMER, NON_EX, v, frozenset(), bound="max") == 600
    # floor / exact: 0 without deck knowledge — sound (a Lethal never banks on hidden cards);
    # a supplied hidden_units context (deck tracker's pigeonhole/EV) overrides
    assert compute_active_damage(HAMMER, NON_EX, v, frozenset(), bound="min") == 0
    assert compute_active_damage(HAMMER, NON_EX, v, frozenset()) == 0
    assert compute_active_damage(HAMMER, NON_EX, v, frozenset(), bound="min",
                                 context={"hidden_units": 2}) == 200


@pytest.mark.req("REQ-DMG-0017")
def test_incoming_sees_the_opponents_discard_scaler():
    # THE P1 hole: opp's Kyogre w/ 5 Basic {W} in THEIR (visible) discard threatens
    # Riptide 20x5=100 — Board's incoming/doomed math must price it, not read 0.
    from common.cards import CardFunctions
    from common.pilot import Pilot
    from common.scouting.provider import DictCardStatProvider
    from common.strategy import Strategy
    from pilot_helpers import make_select, opt, poke, state

    W_ENERGY, KYOGRE, MYMON = 3, 721, 50
    stats = DictCardStatProvider({
        KYOGRE: CardStat(cardId=KYOGRE, name="Kyogre", hp=150, energyType=3,
                         attacks=(1042,), minAttackCost=1),
        MYMON: CardStat(cardId=MYMON, name="Mine", hp=90, energyType=2),
        W_ENERGY: CardStat(cardId=W_ENERGY, name="Basic {W} Energy", cardType=5, energyType=3),
    })
    p = Pilot(Strategy(), deck=[1] * 60, stats=stats, functions=CardFunctions({}),
              attacks={1042: 0}, attack_costs={1042: 1}, attack_stats={1042: RIPTIDE})
    board = state(active=poke(MYMON, energy=1, hp=90),
                  opp_active=poke(KYOGRE, energy=1, hp=150),
                  opp_discard=[W_ENERGY] * 5, prizes=2, opp_prizes=2)
    obs = make_select([opt(14)], current=board)
    b = p._board(obs)
    assert b.incoming_active_damage == 100          # 20 x 5 visible {W} in their discard
    assert b.active_doomed                          # 100 >= my 90 HP — threat is priced


@pytest.mark.req("REQ-DMG-0011")
def test_hidden_scaler_feeds_the_incoming_ceiling():
    # opp's Mega Abomasnow ex threatens the CEILING via _predicted_max_damage
    p = _pilot(attack_stats={1046: HAMMER})
    abom = CardStat(cardId=723, name="Mega Abomasnow ex", hp=350, megaEx=True, energyType=2,
                    attacks=(1046,), minAttackCost=2, maxDamage=0)
    assert p._predicted_max_damage(abom, {"id": 9}) == 600


@pytest.mark.req("REQ-DMG-0016")
def test_tera_benched_body_is_never_a_snipe_ko():
    # Tera Pokémon take NO damage from attacks while benched (engine CardData.tera) — bench-snipe
    # rider must not claim the KO/prize (32 Tera bodies in pool; a phantom snipe-prize could lock a
    # false Lethal). A non-Tera body at same HP still credits.
    p = _pilot()
    p.stats._stats[70] = CardStat(cardId=70, name="Tera ex", hp=40, ex=True, tera=True)
    p.stats._stats[71] = CardStat(cardId=71, name="Plain", hp=40)
    assert p._snipe_ko_prizes(((70, 40),), rider=50) == 0      # Tera bench: untouchable
    assert p._snipe_ko_prizes(((71, 40),), rider=50) == 1      # plain bench: a real prize


# --- Pilot wrapper: resolves ids -> stats/tags, then delegates to the pure oracle ---

def _pilot(attack_stats=None):
    from common.cards import CardFunctions
    from common.pilot import Pilot
    from common.scouting.provider import DictCardStatProvider
    from common.strategy import Line, Strategy

    stats = DictCardStatProvider({
        1031: MEGA_STARMIE, 50: NON_EX, 345: CRUSTLE,
        9: CardStat(cardId=9, name="Vanilla", hp=40, energyType=2),
    })
    strat = Strategy(lines=[Line(path=[50, 1031], payoff=1031, role="win_condition")],
                     roles={1031: ["win_condition"]})
    return Pilot(strat, deck=[1] * 60, stats=stats,
                 functions=CardFunctions({345: ["prevent_ex_damage"]}),
                 attacks={1487: 120, 1488: 210, 142: 40},
                 attack_costs={1487: 1, 1488: 3, 142: 1},
                 bench_snipe={1487: 50}, attack_stats=attack_stats)


@pytest.mark.req("REQ-DMG-0004")
def test_pilot_wrapper_resolves_stats_and_tags():
    p = _pilot(attack_stats={1487: JETTING, 1488: NEBULA})
    crustle = {"id": 345, "hp": 140}
    assert p.predicted_damage(1031, 1488, crustle) == 210    # Nebula pierces
    assert p.predicted_damage(1031, 1487, crustle) == 0      # Jetting prevented
    assert p.predicted_damage(50, 1487, crustle) == 120      # non-ex attacker unaffected


def _lethal_obs(attack_id):
    """MAIN menu, my LAST prize, opp Active 40 HP: a 40-damage KO wins — iff it's guaranteed."""
    me = {"active": [{"id": 50, "energies": [1], "hp": 70}], "bench": [], "hand": [],
          "prize": [None]}                                     # one prize left — a KO wins
    opp = {"active": [{"id": 9, "energies": [], "hp": 40}],
           "bench": [{"id": 9, "hp": 100}], "prize": [None] * 6}
    return {"current": {"players": [me, opp], "yourIndex": 0, "turn": 8},
            "select": {"context": 0, "minCount": 1, "maxCount": 1,
                       "option": [{"type": 13, "attackId": attack_id}, {"type": 14}]}}


@pytest.mark.req("REQ-DMG-0008")
def test_coin_attack_never_locks_a_phantom_lethal():
    # Best Punch: printed 40 would "KO" the 40-HP last-prize defender — but tails does NOTHING.
    # Lethal Solver must read sound floor (0) and refuse the lock (ADR-0030: a phantom
    # lethal is the one catastrophic error). A deterministic 120 still locks.
    p = _pilot(attack_stats={142: BEST_PUNCH, 1487: JETTING})
    assert p.explain(_lethal_obs(142)).lethal is None          # coin floor 0 -> no guaranteed win
    assert p.explain(_lethal_obs(1487)).lethal is not None     # deterministic KO -> locked


@pytest.mark.req("REQ-DMG-0009")
def test_hand_size_lethal_is_exact_and_lockable():
    # Class-A scalers are EXACT (every variable visible): 2 cards in hand -> 40 counters KOs the
    # 40-HP last-prize defender — a sound, lockable Lethal the printed damage (0) hid completely.
    p = _pilot(attack_stats={1072: POWERFUL_HAND})
    obs = _lethal_obs(1072)
    obs["current"]["players"][0]["hand"] = [{"id": 1}, {"id": 1}]
    obs["current"]["players"][0]["handCount"] = 2
    assert p.explain(obs).lethal is not None
    lean = _lethal_obs(1072)                                   # 1 card -> 20 counters, no KO
    lean["current"]["players"][0]["hand"] = [{"id": 1}]
    lean["current"]["players"][0]["handCount"] = 1
    assert p.explain(lean).lethal is None


@pytest.mark.req("REQ-DMG-0006")
def test_pilot_wrapper_degrades_to_legacy_dicts_without_attack_stats():
    # No attack_stats wired: wrapper synthesizes a flagless record from legacy dicts,
    # reproducing OLD behavior exactly (prevention zeroes EVERY ex attack, incl. Nebula).
    p = _pilot(attack_stats=None)
    crustle = {"id": 345, "hp": 140}
    assert p.predicted_damage(1031, 1488, crustle) == 0      # flagless -> old conservative zero
    assert p.predicted_damage(50, 1487, crustle) == 120
    assert p.predicted_damage(1031, 99, crustle) == 0        # unknown attack -> no damage
