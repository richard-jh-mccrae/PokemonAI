"""Issue #225 — the four remaining visible-state damage-scaler families are priced.

Four attacks in the pool scale on board state the **Damage Formula** did not measure, so each read at
its printed base. Attack 425 read at **zero damage**, which is not an under-read but a blind spot: an
attack the oracle says deals nothing is an attack no line ever considers.

| attack | card | printed text (verified, data/EN_Card_Data.csv + src/cgpy/defs/attack_data.json) | variable |
|---|---|---|---|
| 120 | 96 Teal Mask Ogerpon ex | "does 30 more damage for each Energy attached to **both Active Pokémon**" | `both_active_energy` |
| 390 | 283 Mamoswine ex | "does 40 more damage for each **Stage 2** Pokémon on your Bench" | `atk_bench_stage2` |
| 292 | 217 Azelf | "does 10 more damage for each damage counter on **all** of your opponent's Pokémon" | `def_counters_all` |
| 425 | 306 Dudunsparce ex | "does **60 damage for each** of your opponent's Pokémon {ex} in play" (printed `60×`, base 0) | `def_ex_in_play` |

**Provenance, stated plainly.** These four entries are TEXT-VERIFIED, not engine-fitted. ADR-0083 §2
requires that a *fit* may only claim a variable the sweep controls and records, and its Consequences
priced these four at "a sweep capability each"; the defect that rule exists to prevent is a REGEX
naming a plausible variable no measurement supports (Skeledirge's bench scaler fitted as `atk_hand`).
Neither half of that failure mode is in play here: each entry is one human reading one card's own
printed sentence into one `attackId`, which is the same seam and the same discipline
`effect_overrides.json` already uses for clauses the probe cannot reach. The measurement debt is
real and is recorded on the issue rather than hidden — what is NOT tolerable is leaving 425 priced at
zero while waiting for a defender-side sweep driver.

**Corpus status** (the issue's own bar — a corpus example or a recorded absence):
  * **96 Teal Mask Ogerpon ex** — live meta. 12 `artifact.json` dossiers at inclusion 1.0, and 32
    occurrences across two `mega_starmie` correction runs including in `active` and `bench`. Real.
  * **306 Dudunsparce ex** — 3 dossiers; in the corpus only in `deck`/`hand`, never on the board. So
    it is meta-real but has no frame in which its damage was ever priced.
  * **283 Mamoswine ex** and **217 Azelf** — **PROVABLY ABSENT** from every shipped deck, every
    dossier, every Brief and every correction frame. Their pricing rests on the card text alone and
    no corpus gate can see it. That is the situation ADR-0083 already recorded for Skeledirge, and it
    is stated here for the same reason: papering over it would make the gate look stronger than it is.
"""
import json
from pathlib import Path

import pytest

from common.scouting.provider import AttackStat, CardStat, DictCardStatProvider
from common.strategy.damage import compute_active_damage

REPO = Path(__file__).resolve().parents[2]

OGERPON, MAMOSWINE, AZELF, DUDUNSPARCE = 96, 283, 217, 306
LEAF, MARCH, NEURO, TAIL = 120, 390, 292, 425

#: attackId -> (scaleVar, per-unit) as shipped. Pinned so a rebuild that drops one fails HERE, where
#: the reason is written down, rather than as a quiet 10× under-read in a threat rank.
SHIPPED = {
    LEAF:  ("both_active_energy", 30),
    MARCH: ("atk_bench_stage2", 40),
    NEURO: ("def_counters_all", 10),
    TAIL:  ("def_ex_in_play", 60),
}


def _atk(aid, damage):
    """The attack record AS THE SHIPPED PROVIDER BUILDS IT — printed damage plus the override's
    scaler. `DictCardStatProvider` takes records directly and so does not run `build_attack_stats`'s
    override pass; stamping `SHIPPED` here keeps this fixture equal to production by construction,
    and `test_all_four_families_are_shipped_with_their_printed_per_unit` pins `SHIPPED` against the
    real table so the two cannot drift."""
    var, per_unit = SHIPPED[aid]
    return AttackStat(aid, damage=damage, cost=2, scaleVar=var, scalePerUnit=per_unit)


def _attacker(cid, energy_type=1):
    return CardStat(cid, name="Attacker", hp=200, energyType=energy_type)


def _defender(cid=1):
    """A defender with no Weakness, no Resistance and no prevention — so the assertions below read
    the SCALING term and nothing else."""
    return CardStat(cid, name="Defender", hp=300)


# ── the shipped table ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.req("REQ-SCALER-0001")
def test_all_four_families_are_shipped_with_their_printed_per_unit():
    overrides = json.loads((REPO / "src" / "common" / "attack_overrides.json").read_text(
        encoding="utf-8"))
    for aid, (var, per_unit) in SHIPPED.items():
        entry = overrides[str(aid)]
        assert entry["scaleVar"] == var and entry["scalePerUnit"] == per_unit, aid


@pytest.mark.req("REQ-SCALER-0001")
def test_the_oracle_reads_each_variable_as_a_plain_context_key():
    """ADR-0083 §4's rule, held: every variable name IS a context key, so the oracle stays one dict
    lookup per scaler. The `atk_discard_energy` two-key special case is the ONE exception in the
    vocabulary and none of these four joins it — which is the whole reason the two FILTERED counts
    take flat names instead of growing a filtered-count form (see `src/common/CONTEXT.md`)."""
    dfn = _defender()
    for aid, (var, per_unit) in SHIPPED.items():
        stat = AttackStat(aid, damage=0, cost=2, scaleVar=var, scalePerUnit=per_unit)
        for units in (0, 1, 3):
            got = compute_active_damage(stat, _attacker(1), dfn, context={var: units})
            assert got == per_unit * units, f"{aid} at {units} units"
        # no context -> the term contributes 0 (a sound floor, a weak ceiling — ADR-0032)
        assert compute_active_damage(stat, _attacker(1), dfn, context=None) == 0


# ── each family, on a real board ──────────────────────────────────────────────────────────────────
def _pilot_ctx(pilot, obs, *, attacker_is_me=True):
    return pilot._damage_context(obs, attacker_is_me=attacker_is_me)


def _board(*, my_active=None, my_bench=(), opp_active=None, opp_bench=()):
    return {"current": {"yourIndex": 0, "players": [
        {"active": [my_active] if my_active else [], "bench": list(my_bench)},
        {"active": [opp_active] if opp_active else [], "bench": list(opp_bench)},
    ]}}


def _body(cid, *, energies=0, hp=100, max_hp=100):
    return {"id": cid, "energies": [0] * energies, "hp": hp, "maxHp": max_hp}


@pytest.fixture
def pilot():
    from common.cards import CardFunctions
    from common.strategy import Strategy
    from common.strategy.general_strategy import GENERAL_STRATEGY
    from common.pilot import Pilot
    stats = DictCardStatProvider({
        OGERPON: CardStat(OGERPON, name="Teal Mask Ogerpon ex", hp=210, ex=True, energyType=1,
                          attacks=(LEAF,)),
        MAMOSWINE: CardStat(MAMOSWINE, name="Mamoswine ex", hp=340, ex=True, stage2=True,
                            evolvesFrom="Piloswine", energyType=6, attacks=(MARCH,)),
        AZELF: CardStat(AZELF, name="Azelf", hp=70, energyType=5, attacks=(NEURO,)),
        DUDUNSPARCE: CardStat(DUDUNSPARCE, name="Dudunsparce ex", hp=270, ex=True,
                              evolvesFrom="Dunsparce", energyType=0, attacks=(TAIL,)),
        1: CardStat(1, name="Plain", hp=300),
        2: CardStat(2, name="Plain ex", hp=300, ex=True),
        3: CardStat(3, name="Plain Stage 2", hp=300, stage2=True),
    }, attacks={LEAF: _atk(LEAF, 30), MARCH: _atk(MARCH, 180),
                NEURO: _atk(NEURO, 10), TAIL: _atk(TAIL, 0)})
    return Pilot(Strategy(roles={}), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=stats, functions=CardFunctions({}))


@pytest.mark.req("REQ-SCALER-0002")
def test_both_active_energy_is_symmetric_across_the_two_Actives(pilot):
    """The second member of the `both_` direction class ADR-0083 §4 opened — and the card §4 named.
    The sum is direction-symmetric, so ONE key is right whichever side attacks: measured from my
    seat and from theirs it reads the same number, which is what makes the no-mirroring rule sound
    rather than merely convenient."""
    obs = _board(my_active=_body(OGERPON, energies=3), opp_active=_body(1, energies=2))
    mine = _pilot_ctx(pilot, obs)
    theirs = _pilot_ctx(pilot, obs, attacker_is_me=False)
    assert mine["both_active_energy"] == theirs["both_active_energy"] == 5
    # Myriad Leaf Shower: 30 printed + 30 x 5 = 180
    assert pilot.predicted_damage(OGERPON, LEAF, _body(1, hp=300), context=mine) == 180


@pytest.mark.req("REQ-SCALER-0003")
def test_atk_bench_stage2_counts_only_stage_2_bodies_and_only_mine(pilot):
    """A predicate over a zone, not a plain count — and both halves of the predicate bite: a
    non-Stage-2 bench body contributes nothing, and their bench never contributes at all."""
    obs = _board(my_active=_body(MAMOSWINE), my_bench=[_body(3), _body(3), _body(1)],
                 opp_active=_body(1), opp_bench=[_body(3), _body(3)])
    ctx = _pilot_ctx(pilot, obs)
    assert ctx["atk_bench_stage2"] == 2                 # two Stage 2s of mine; the plain one and
    assert ctx["atk_bench"] == 3                        # both of theirs do not count
    # Rumbling March: 180 printed + 40 x 2 = 260
    assert pilot.predicted_damage(MAMOSWINE, MARCH, _body(1, hp=300), context=ctx) == 260


@pytest.mark.req("REQ-SCALER-0004")
def test_def_counters_all_reads_every_body_not_the_Active_alone(pilot):
    """The variable that makes this a DIFFERENT family from `def_counters`: it sums damage counters
    across their whole board. A read that stopped at the Active would price Neurokinesis at a
    fraction of what it hits for on a chipped board."""
    obs = _board(my_active=_body(AZELF),
                 opp_active=_body(1, hp=70, max_hp=100),          # 3 counters
                 opp_bench=[_body(1, hp=50, max_hp=100),           # 5
                            _body(1, hp=100, max_hp=100)])         # 0
    ctx = _pilot_ctx(pilot, obs)
    assert ctx["def_counters"] == 3 and ctx["def_counters_all"] == 8
    # Neurokinesis: 10 printed + 10 x 8 = 90
    assert pilot.predicted_damage(AZELF, NEURO, _body(1, hp=300, max_hp=300),
                                  context=ctx) == 90


@pytest.mark.req("REQ-SCALER-0005")
def test_def_ex_in_play_prices_an_attack_that_read_as_ZERO(pilot):
    """The printed value is `60×` with a base of 0 — the engine record carries `damage: 0` and no
    parser in the tree reads a `×`-suffixed form (`parse_attack_damage_bounds` takes an int and its
    bonus regex carries an explicit `(?! for each)`). So before this entry Tenacious Tail computed to
    zero under EVERY bound, which is not an under-read: an attack the oracle says deals nothing is an
    attack no line ever considers."""
    obs = _board(my_active=_body(DUDUNSPARCE),
                 opp_active=_body(2), opp_bench=[_body(2), _body(1)])
    ctx = _pilot_ctx(pilot, obs)
    assert ctx["def_ex_in_play"] == 2                    # two {ex}; the plain body does not count
    # Tenacious Tail: base 0 + 60 x 2 = 120 — and 0 with an empty opposing board, which is the
    # printed truth rather than a fallback.
    assert pilot.predicted_damage(DUDUNSPARCE, TAIL, _body(2, hp=300), context=ctx) == 120
    empty = _pilot_ctx(pilot, _board(my_active=_body(DUDUNSPARCE), opp_active=_body(1)))
    assert pilot.predicted_damage(DUDUNSPARCE, TAIL, _body(1, hp=300), context=empty) == 0


@pytest.mark.req("REQ-SCALER-0006")
def test_the_filtered_counts_fail_closed_on_an_unresolvable_body(pilot):
    """`atk_bench_stage2` counts MY bench, so an over-read inflates MY damage — the direction that
    manufactures a phantom lethal, the one error the Lethal Solver may never make. An unknown card
    is therefore not counted. `def_ex_in_play` fails the same way for the same reason."""
    obs = _board(my_active=_body(MAMOSWINE), my_bench=[_body(999999), _body(3)],
                 opp_active=_body(999999), opp_bench=[_body(2)])
    ctx = _pilot_ctx(pilot, obs)
    assert ctx["atk_bench_stage2"] == 1                  # the unknown body claims nothing
    assert ctx["def_ex_in_play"] == 1


# ── corpus status, recorded rather than assumed ───────────────────────────────────────────────────
@pytest.mark.req("REQ-SCALER-0007")
def test_the_corpus_status_of_each_card_is_what_the_issue_recorded():
    """The issue's bar is "a corpus example OR a recorded absence", so the absence is ASSERTED — a
    claim nobody re-checks is a claim that rots. If 283 or 217 ever enters a shipped deck or a
    dossier this fails, which is exactly when "no gate can see it" stops being true."""
    artifact = (REPO / "src" / "common" / "scouting" / "artifact.json").read_text(encoding="utf-8")
    dossiers = json.loads(artifact)
    in_artifact = set()

    def _walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("cardId", "id") and isinstance(v, int):
                    in_artifact.add(v)
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)
    _walk(dossiers)

    deck_ids = set()
    for deck in (REPO / "src" / "agents").glob("*/deck.csv"):
        deck_ids.update(int(line.strip()) for line in deck.read_text(encoding="utf-8").splitlines()
                        if line.strip().isdigit())

    assert OGERPON in in_artifact, "96 was recorded as live meta — re-check the ruling"
    assert DUDUNSPARCE in in_artifact, "306 was recorded as meta-real — re-check the ruling"
    for absent in (MAMOSWINE, AZELF):
        assert absent not in in_artifact and absent not in deck_ids, (
            f"{absent} was recorded PROVABLY ABSENT from the pool as exercised; it no longer is, so "
            "its text-verified pricing now HAS a corpus that can check it — re-rule it")
