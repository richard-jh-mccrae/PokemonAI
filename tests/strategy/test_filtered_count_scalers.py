"""Issue #361 — the FILTERED-COUNT family: two per-unit attacks that were frozen at one board's count.

Two shipped `unaudited` overrides priced a per-unit attack as a flat constant:

| attack | card | printed text (verified: `data/EN_Card_Data.csv`, `src/cgpy/defs/attack_data.json`) |
|---|---|---|
| 651 | 462 Team Rocket's Weezing | *"This attack does 40 damage for each Pokémon in play that has "Koffing" or "Weezing" in its name (both yours and your opponent's)."* |
| 708 | 501 Palpitoad | *"This attack does 40 damage for each of your Pokémon in play that has the Round attack."* |

Both print `damage: 0` in the engine record, so the override was the ONLY source of the number, and
that number was `80` — 40 × 2, one board's count, frozen. On the common board where the attacker is
the single matching Pokémon the engine deals 40 and the oracle promised 80: an `over_prediction`,
the soundness class `tools/sim/ci_audit_gate.py` exists to fail, invisible only because neither
attack is on its `_GATE_ATTACKS` list.

**The ruling (developer, 2026-08-03, Issue #361) was to GROW THE VOCABULARY**, not to drop the two
entries to the printed 0. So the vocabulary gains a *filtered-count FORM*: a family name in
`scaleVar` plus the predicate's argument in a new `AttackStat.scaleFilter`, resolved against raw
material the context supplies (`both_in_play_names`, `atk_in_play_attack_names`) rather than a
pre-reduced integer. `ADR-TEMP-361` records why Issue #225's decision to flatten its three filtered
counts into atoms does not govern here: those predicates are CLOSED (a stage, a rule box, a damage
counter), these are OPEN (an arbitrary name substring, an arbitrary attack name), and flattening an
open predicate means hardcoding card names into the vocabulary.

The three Issue #225 flat names are deliberately NOT migrated — see `tests/strategy/
test_visible_state_scalers.py`, which still owns them.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy.damage import compute_active_damage
from common.strategy.damage_context import SideFacts, damage_context

REPO = Path(__file__).resolve().parents[2]

TR_KOFFING, TR_WEEZING = 461, 462
TYMPOLE, PALPITOAD, SEISMITOAD = 500, 501, 502
LEAKING_GAS, EXPLODE = 650, 651
ROUND_707, ROUND_708, ROUND_710, WAVE_SPLASH = 707, 708, 710, 709

#: attackId -> (scaleVar, per-unit, filter) as SHIPPED. Pinned here so a regeneration that drops one
#: — or restores the frozen `{"damage": 80}` — fails where the reason is written down, rather than
#: as a silent 2× over-prediction inside a threat rank.
SHIPPED = {
    EXPLODE:  ("both_in_play_named", 40, ["Koffing", "Weezing"]),
    ROUND_708: ("atk_in_play_with_attack", 40, ["Round"]),
}


def _defender(cid=1):
    """No Weakness, no Resistance, no prevention — so every assertion reads the SCALING term."""
    return CardStat(cid, synthetic=True, name="Defender", hp=300)


# ── the shipped table ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.req("REQ-SCALER-0007")
def test_the_two_entries_ship_a_board_dependent_scaler_and_no_frozen_constant():
    """The defect, at its source. `{"damage": 80}` is not an under-specified value — it is a WRONG
    one on every board whose count is not exactly 2, and it carries no `scaleVar` at all, so nothing
    downstream can tell it is board-dependent."""
    overrides = json.loads((REPO / "src" / "common" / "attack_overrides.json").read_text(
        encoding="utf-8"))
    for aid, (var, per_unit, filt) in SHIPPED.items():
        entry = overrides[str(aid)]
        assert "damage" not in entry, (
            f"attack {aid} ships a flat `damage` again. Its printed record is `damage: 0` and its "
            f"own sentence says 'for each' — a constant here is one board's count, frozen.")
        assert (entry["scaleVar"], entry["scalePerUnit"], entry["scaleFilter"]) \
            == (var, per_unit, filt), f"attack {aid}: shipped scaler is not the ruled one"


@pytest.mark.req("REQ-SCALER-0007")
def test_the_provenance_sidecar_records_the_ruling_and_no_longer_says_unaudited():
    """REQ-PROV-0001/0003/0004: the two rows move OFF `unaudited` (the debt shrinks), record the
    exact shipped fields, and name the issue that owes the measurement."""
    sidecar = json.loads((REPO / "src" / "common" / "attack_overrides.provenance.json").read_text(
        encoding="utf-8"))["entries"]
    table = json.loads((REPO / "src" / "common" / "attack_overrides.json").read_text(
        encoding="utf-8"))
    for aid in SHIPPED:
        row = sidecar[str(aid)]
        assert row["method"] == "text_verified", f"attack {aid}: still {row['method']}"
        assert row["fields"] == table[str(aid)], f"attack {aid}: sidecar and table disagree"
        assert row.get("owner") and row.get("note")


# ── the oracle, on raw material ───────────────────────────────────────────────────────────────────
@pytest.mark.req("REQ-SCALER-0008")
def test_one_matching_pokemon_in_play_reads_40_not_80():
    """**The defect, expressed as a test.** The attacker alone matches — the common board — so the
    engine deals 40 and the oracle must say 40."""
    stat = AttackStat(EXPLODE, damage=0, cost=2, scaleVar="both_in_play_named",
                      scalePerUnit=40, scaleFilter=("Koffing", "Weezing"))
    ctx = {"both_in_play_names": ("Team Rocket's Weezing", "Regigigas", "Snorlax")}
    assert compute_active_damage(stat, CardStat(TR_WEEZING, name="Team Rocket's Weezing",
                                                energyType=7), _defender(), context=ctx) == 40


@pytest.mark.req("REQ-SCALER-0008")
@pytest.mark.parametrize("names,expected", [
    ((), 0),
    (("Regigigas",), 0),
    (("Team Rocket's Weezing",), 40),
    (("Team Rocket's Weezing", "Team Rocket's Koffing"), 80),
    (("Team Rocket's Weezing", "Team Rocket's Koffing", "Koffing", "Weezing"), 160),
])
def test_both_in_play_named_counts_every_matching_name_on_either_side(names, expected):
    """A NAME-SUBSTRING predicate over both seats. `Team Rocket's Koffing` matches "Koffing" —
    the owner prefix is part of the printed name (`docs/rules.md` §9), and the card's sentence asks
    only that the name CONTAIN the word."""
    stat = AttackStat(EXPLODE, damage=0, cost=2, scaleVar="both_in_play_named",
                      scalePerUnit=40, scaleFilter=("Koffing", "Weezing"))
    got = compute_active_damage(stat, CardStat(TR_WEEZING, name="Team Rocket's Weezing",
                                               energyType=7), _defender(),
                                context={"both_in_play_names": names})
    assert got == expected


@pytest.mark.req("REQ-SCALER-0009")
@pytest.mark.parametrize("per_body,expected", [
    ((), 0),
    ((("Wave Splash",),), 0),
    ((("Round", "Wave Splash"),), 40),
    ((("Round", "Wave Splash"), ("Round",)), 80),
])
def test_atk_in_play_with_attack_counts_bodies_that_HAVE_the_named_attack(per_body, expected):
    """An ATTACK-NAME predicate over the attacker's own in-play bodies. The material is one entry
    per body — a flat list of attack names could not tell two Round-havers from one body with two
    copies of the name."""
    stat = AttackStat(ROUND_708, damage=0, cost=2, scaleVar="atk_in_play_with_attack",
                      scalePerUnit=40, scaleFilter=("Round",))
    got = compute_active_damage(stat, CardStat(PALPITOAD, name="Palpitoad", energyType=3),
                                _defender(), context={"atk_in_play_attack_names": per_body})
    assert got == expected


@pytest.mark.req("REQ-SCALER-0010")
def test_a_missing_context_key_contributes_ZERO_rather_than_a_guess():
    """The oracle's standing rule (`strategy/damage.py`): a variable absent from the context
    contributes 0 — a sound floor and a weak ceiling. Never the old behaviour, which was to promise
    a number no board established."""
    for aid, (var, per_unit, filt) in SHIPPED.items():
        stat = AttackStat(aid, damage=0, cost=2, scaleVar=var, scalePerUnit=per_unit,
                          scaleFilter=tuple(filt))
        assert compute_active_damage(stat, CardStat(1, synthetic=True, name="A", energyType=1),
                                     _defender(), context=None) == 0
        assert compute_active_damage(stat, CardStat(1, synthetic=True, name="A", energyType=1),
                                     _defender(), context={}) == 0


@pytest.mark.req("REQ-SCALER-0010")
def test_a_family_with_no_filter_claims_nothing():
    """`scaleFilter` IS the predicate. A family name with no argument is not a weaker claim, it is
    no claim at all — counting every body in play would be a wild over-read."""
    stat = AttackStat(EXPLODE, damage=0, cost=2, scaleVar="both_in_play_named", scalePerUnit=40)
    ctx = {"both_in_play_names": ("Team Rocket's Weezing", "Team Rocket's Koffing")}
    assert compute_active_damage(stat, CardStat(TR_WEEZING, name="Team Rocket's Weezing",
                                                energyType=7), _defender(), context=ctx) == 0


# ── the context builder ───────────────────────────────────────────────────────────────────────────
@pytest.mark.req("REQ-SCALER-0011")
def test_both_in_play_names_is_direction_SYMMETRIC_like_every_other_both_key():
    """The `both_` class's contract (ADR-0083 §4): one key is correct whichever side attacks, so
    there is no mirroring to get wrong. Order may differ; the multiset may not."""
    mine = SideFacts(in_play_names=("Team Rocket's Weezing", "Team Rocket's Koffing"))
    theirs = SideFacts(in_play_names=("Regigigas",))
    a = damage_context(mine, theirs)["both_in_play_names"]
    b = damage_context(theirs, mine)["both_in_play_names"]
    assert sorted(a) == sorted(b) == ["Regigigas", "Team Rocket's Koffing", "Team Rocket's Weezing"]


@pytest.mark.req("REQ-SCALER-0011")
def test_atk_in_play_attack_names_is_the_ATTACKER_seat_only():
    """The other half of the family is `atk_`-directional: *"each of YOUR Pokémon in play"*. A
    defender's Round-haver must never inflate the attacker's number."""
    mine = SideFacts(in_play_attack_names=(("Round", "Wave Splash"), ("Round",)))
    theirs = SideFacts(in_play_attack_names=(("Round",), ("Round",), ("Round",)))
    assert damage_context(mine, theirs)["atk_in_play_attack_names"] == \
        (("Round", "Wave Splash"), ("Round",))
    assert damage_context(theirs, mine)["atk_in_play_attack_names"] == \
        (("Round",), ("Round",), ("Round",))


# ── the whole path, on a real board through the live supplier ─────────────────────────────────────
def _board(*, my_active=None, my_bench=(), opp_active=None, opp_bench=()):
    return {"current": {"yourIndex": 0, "players": [
        {"active": [my_active] if my_active else [], "bench": list(my_bench)},
        {"active": [opp_active] if opp_active else [], "bench": list(opp_bench)},
    ]}}


def _body(cid, *, hp=100, max_hp=100):
    return {"id": cid, "energies": [], "hp": hp, "maxHp": max_hp}


@pytest.fixture
def pilot():
    from common.cards import CardFunctions
    from common.strategy import Strategy
    from common.strategy.general_strategy import GENERAL_STRATEGY
    from common.pilot import Pilot
    stats = DictCardStatProvider({
        TR_KOFFING: CardStat(TR_KOFFING, name="Team Rocket's Koffing", hp=70, energyType=7,
                             weakness=6, attacks=(LEAKING_GAS,)),
        TR_WEEZING: CardStat(TR_WEEZING, name="Team Rocket's Weezing", hp=130, energyType=7,
                             weakness=6, evolvesFrom="Team Rocket's Koffing", attacks=(EXPLODE,)),
        TYMPOLE: CardStat(TYMPOLE, name="Tympole", hp=60, energyType=3, attacks=(ROUND_707,)),
        PALPITOAD: CardStat(PALPITOAD, name="Palpitoad", hp=90, energyType=3,
                            evolvesFrom="Tympole", attacks=(ROUND_708, WAVE_SPLASH)),
        SEISMITOAD: CardStat(SEISMITOAD, name="Seismitoad", hp=170, energyType=3,
                             evolvesFrom="Palpitoad", attacks=(ROUND_710,)),
        1: CardStat(1, synthetic=True, name="Plain", hp=300),
    }, attacks={
        EXPLODE: AttackStat(EXPLODE, name="Explode Together Now", damage=0, cost=2,
                            scaleVar="both_in_play_named", scalePerUnit=40,
                            scaleFilter=("Koffing", "Weezing")),
        LEAKING_GAS: AttackStat(LEAKING_GAS, name="Leaking Gas", damage=0, cost=1),
        ROUND_707: AttackStat(ROUND_707, name="Round", damage=0, cost=1,
                              scaleVar="atk_in_play_with_attack", scalePerUnit=20,
                              scaleFilter=("Round",)),
        ROUND_708: AttackStat(ROUND_708, name="Round", damage=0, cost=2,
                              scaleVar="atk_in_play_with_attack", scalePerUnit=40,
                              scaleFilter=("Round",)),
        ROUND_710: AttackStat(ROUND_710, name="Round", damage=0, cost=2,
                              scaleVar="atk_in_play_with_attack", scalePerUnit=60,
                              scaleFilter=("Round",)),
        WAVE_SPLASH: AttackStat(WAVE_SPLASH, name="Wave Splash", damage=60, cost=3),
    })
    return Pilot(Strategy(roles={}), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=stats, functions=CardFunctions({}))


@pytest.mark.req("REQ-SCALER-0012")
def test_explode_together_now_is_priced_off_the_LIVE_board_not_a_constant(pilot):
    """The whole path: observation → `SideFacts` → `damage_context` → the oracle. Lone attacker 40,
    a filled board 160 — the two answers the frozen 80 could never both be."""
    lone = _board(my_active=_body(TR_WEEZING), opp_active=_body(1))
    ctx = pilot._damage_context(lone)
    assert ctx["both_in_play_names"] == ("Team Rocket's Weezing", "Plain")
    assert pilot.predicted_damage(TR_WEEZING, EXPLODE, _body(1, hp=300, max_hp=300),
                                  context=ctx) == 40

    full = _board(my_active=_body(TR_WEEZING), my_bench=[_body(TR_KOFFING), _body(1)],
                  opp_active=_body(TR_KOFFING), opp_bench=[_body(TR_WEEZING), _body(1)])
    ctx = pilot._damage_context(full)
    assert pilot.predicted_damage(TR_WEEZING, EXPLODE, _body(1, hp=300, max_hp=300),
                                  context=ctx) == 160


@pytest.mark.req("REQ-SCALER-0012")
def test_round_counts_my_own_Round_havers_and_never_theirs(pilot):
    """"each of YOUR Pokémon in play that has the Round attack" — an opposing Seismitoad with the
    same attack contributes nothing, and an in-play body counts whether Active or Benched — the
    Bench IS in play (`docs/rulebook.txt` L559: *"Your deck, your discard pile, and your Prize cards
    are not in play, but your Benched Pokémon are."*)."""
    obs = _board(my_active=_body(PALPITOAD), my_bench=[_body(TYMPOLE), _body(1)],
                 opp_active=_body(1), opp_bench=[_body(SEISMITOAD), _body(TYMPOLE)])
    ctx = pilot._damage_context(obs)
    assert ctx["atk_in_play_attack_names"] == (("Round", "Wave Splash"), ("Round",), ())
    assert pilot.predicted_damage(PALPITOAD, ROUND_708, _body(1, hp=300, max_hp=300),
                                  context=ctx) == 80


@pytest.mark.req("REQ-SCALER-0012")
def test_the_filtered_count_fails_CLOSED_on_an_unresolvable_body(pilot):
    """An unknown card claims nothing. `both_in_play_named` and `atk_in_play_with_attack` both
    scale MY damage, so an over-read is the direction that manufactures a phantom lethal — the one
    error the Lethal Solver may never make."""
    obs = _board(my_active=_body(TR_WEEZING), my_bench=[_body(999999)],
                 opp_active=_body(999999))
    ctx = pilot._damage_context(obs)
    assert ctx["both_in_play_names"] == ("Team Rocket's Weezing", "", "")
    assert pilot.predicted_damage(TR_WEEZING, EXPLODE, _body(1, hp=300, max_hp=300),
                                  context=ctx) == 40

    obs = _board(my_active=_body(PALPITOAD), my_bench=[_body(999999)], opp_active=_body(1))
    ctx = pilot._damage_context(obs)
    assert ctx["atk_in_play_attack_names"] == (("Round", "Wave Splash"), ())
