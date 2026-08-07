"""Issue #225 — the four remaining visible-state damage-scaler families are priced.

Four attacks scale on board state the Damage Formula did not measure, so each read at its printed
base; attack 425 read at ZERO, a blind spot rather than an under-read. The four, by attackId:
120 Teal Mask Ogerpon ex `both_active_energy`, 390 Mamoswine ex `atk_bench_stage2`,
292 Azelf `def_counters_all`, 425 Dudunsparce ex `def_ex_in_play` (printed `60×`, base 0).

All four shipped TEXT-VERIFIED against `data/EN_Card_Data.csv`; 120 and 425 were later ENGINE-FITTED
(Issue #275) and both fits reproduced the human reading exactly, so no shipped value moved. 390 and
292 stay unfittable on the current axes, and 283/217 are provably absent from every shipped deck,
dossier, Brief and correction frame — their pricing rests on the card text alone.
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
    """The attack record AS THE SHIPPED PROVIDER BUILDS IT — printed damage plus the override's scaler.
    `DictCardStatProvider` takes records directly, so it never runs `build_attack_stats`'s override pass."""
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
    """The last line of defence for four HUMAN RULINGS. If this goes red the fix is essentially never to
    update `SHIPPED`: re-read the card, then fix whatever wrote the table."""
    overrides = json.loads((REPO / "src" / "common" / "attack_overrides.json").read_text(
        encoding="utf-8"))
    for aid, (var, per_unit) in SHIPPED.items():
        entry = overrides[str(aid)]
        assert (entry["scaleVar"], entry["scalePerUnit"]) == (var, per_unit), (
            f"attack {aid}: the shipped table says {entry['scaleVar']}/{entry['scalePerUnit']}, "
            f"this ruling says {var}/{per_unit}.\n"
            f"Do NOT conform this test to the table. These four are human rulings read off the "
            f"printed card; 120 and 425 are UNFITTABLE on the audit's current axes and a "
            f"regeneration derives a wrong variable for each (Issue #355 — `def_ex_in_play` is "
            f"collinear with `def_bench` on the audit panel, `both_active_energy` with "
            f"`atk_active_energy`). Re-read the card, then fix whatever wrote the table: "
            f"`merge_provenance`'s REQ-PROV-0008 contradiction guard in "
            f"tools/sim/generate_attack_overrides.py is what should have stopped this.")


@pytest.mark.req("REQ-SCALER-0001")
def test_the_oracle_reads_each_variable_as_a_plain_context_key():
    """ADR-0083 §4: every variable name IS a context key, so the oracle stays one dict lookup per
    scaler. These four did not move onto ADR-0115's filtered-count form — explicitly out of its scope."""
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
        1: CardStat(1, synthetic=True, name="Plain", hp=300),
        2: CardStat(2, synthetic=True, name="Plain ex", hp=300, ex=True),
        3: CardStat(3, synthetic=True, name="Plain Stage 2", hp=300, stage2=True),
    }, attacks={LEAF: _atk(LEAF, 30), MARCH: _atk(MARCH, 180),
                NEURO: _atk(NEURO, 10), TAIL: _atk(TAIL, 0)})
    return Pilot(Strategy(roles={}), deck=[1] * 60, general_strategy=GENERAL_STRATEGY,
                 stats=stats, functions=CardFunctions({}))


@pytest.mark.req("REQ-SCALER-0002")
def test_both_active_energy_is_symmetric_across_the_two_Actives(pilot):
    """The sum is direction-symmetric, so ONE key is right whichever side attacks — which is what makes
    the no-mirroring rule sound rather than merely convenient."""
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
    across their whole board, not the Active alone."""
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
    """The printed value is `60×` with a base of 0 and no parser in the tree reads a `×`-suffixed form,
    so before this entry Tenacious Tail computed to zero under EVERY bound."""
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
    """`atk_bench_stage2` counts MY bench, so an over-read manufactures a phantom lethal — the one error
    the Lethal Solver may never make. `def_ex_in_play` fails the same way for the same reason."""
    obs = _board(my_active=_body(MAMOSWINE), my_bench=[_body(999999), _body(3)],
                 opp_active=_body(999999), opp_bench=[_body(2)])
    ctx = _pilot_ctx(pilot, obs)
    assert ctx["atk_bench_stage2"] == 1                  # the unknown body claims nothing
    assert ctx["def_ex_in_play"] == 1


# ── corpus status, recorded rather than assumed ───────────────────────────────────────────────────
def _card_ids_in(payload) -> set[int]:
    """Every `cardId`/`id` integer anywhere in a decoded JSON tree."""
    found: set[int] = set()

    def _walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("cardId", "id") and isinstance(v, int):
                    found.add(v)
                _walk(v)
        elif isinstance(node, list):
            for v in node:
                _walk(v)
    _walk(payload)
    return found


def _ids_in_json(paths) -> set[int]:
    return set().union(set(), *(_card_ids_in(json.loads(p.read_text(encoding="utf-8")))
                                for p in paths))


def _ids_in_corrections(_paths=()) -> set[int]:
    """Card ids across every committed correction FRAME, through `corpus_helpers.corpus_index()` — THE
    Corpus Reader. Both halves of a record are walked: the board `obs` and the offered `decision`."""
    from corpus_helpers import corpus_index

    found: set[int] = set()
    for c in corpus_index().values():
        found |= _card_ids_in(c.obs) | _card_ids_in(c.decision)
    return found


def _deck_ids(paths) -> set[int]:
    """A shipped `deck.csv` is one card id per line."""
    found: set[int] = set()
    for p in paths:
        found.update(int(line.strip()) for line in p.read_text(encoding="utf-8").splitlines()
                     if line.strip().isdigit())
    return found


def _briefs_naming(paths, name: str) -> list[str]:
    """Brief filenames whose text mentions ``name``. Briefs reference cards in PROSE, never by id, so an
    id walk over a Brief returns the EMPTY SET — reusing the id search here would be vacuous."""
    return [p.name for p in paths if name.lower() in p.read_text(encoding="utf-8").lower()]


#: Every store this test reads, as ``(label, paths, loader, controls)``. Stated as data so the
#: docstring's claim and the assertion cannot drift apart; every store carries its own control.
_BRIEFS = tuple(sorted((REPO / "src" / "common" / "scouting" / "briefs").glob("*.json")))
_ID_STORES = (
    ("artifact.json", (REPO / "src" / "common" / "scouting" / "artifact.json",), _ids_in_json,
     (OGERPON, DUDUNSPARCE)),
    ("deck.csv", tuple(sorted((REPO / "src" / "agents").glob("*/deck.csv"))), _deck_ids,
     (OGERPON,)),
    # `paths` is a sentinel here, not a glob: the Corpus Reader owns the walk, so this store's
    # "did anything match" guard is the record count the reader returns, asserted below.
    ("correction frames", (REPO / "data" / "corrections",), _ids_in_corrections,
     (OGERPON, DUDUNSPARCE)),
)
#: The Brief store, keyed by printed NAME. Dudunsparce ex is the control rather than Ogerpon ex:
#: Ogerpon appears in no Brief, so it would be a control that cannot fire.
_BRIEF_NAMES = {OGERPON: "Teal Mask Ogerpon", DUDUNSPARCE: "Dudunsparce",
                MAMOSWINE: "Mamoswine", AZELF: "Azelf"}


@pytest.mark.req("REQ-SCALER-0007")
def test_the_corpus_status_of_each_card_is_what_the_issue_recorded():
    """The issue's bar is "a corpus example OR a recorded absence", so the absence is ASSERTED. Each
    store carries a POSITIVE CONTROL, and the controls are not interchangeable across keyspaces."""
    found: dict[str, set[int]] = {}
    for label, paths, load, controls in _ID_STORES:
        assert controls, f"{label}: declares no positive control, so its silence proves nothing"
        assert paths, f"{label}: no files matched — this store would then assert nothing"
        ids = load(paths)
        assert ids, f"{label}: matched {len(paths)} file(s) but read no card ids"
        for control in controls:
            assert control in ids, (
                f"{label}: positive control {control} is missing, so this store's silence about "
                f"283/217 proves nothing — fix the search before trusting the absence")
        found[label] = ids

    assert _BRIEFS, "no Brief matched — the Brief half would assert nothing"
    assert _briefs_naming(_BRIEFS, _BRIEF_NAMES[DUDUNSPARCE]), (
        "Briefs: positive control 'Dudunsparce' matched nothing, so the name search is broken and "
        "its silence about Mamoswine/Azelf proves nothing")

    assert OGERPON in found["artifact.json"], "96 was recorded as live meta — re-check the ruling"
    assert DUDUNSPARCE in found["artifact.json"], "306 was recorded as meta-real — re-check it"

    for absent in (MAMOSWINE, AZELF):
        hits = sorted(label for label, ids in found.items() if absent in ids)
        hits += [f"Briefs ({b})" for b in _briefs_naming(_BRIEFS, _BRIEF_NAMES[absent])]
        assert hits == [], (
            f"{absent} was recorded PROVABLY ABSENT from the pool as exercised; it now appears in "
            f"{hits}, so its text-verified pricing HAS a corpus that can check it — re-rule it")
