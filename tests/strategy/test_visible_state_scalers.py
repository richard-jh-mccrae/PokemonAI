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

**Provenance, stated plainly.** All four SHIPPED as TEXT-VERIFIED, not engine-fitted. ADR-0083 §2
requires that a *fit* may only claim a variable the sweep controls and records, and its Consequences
priced these four at "a sweep capability each"; the defect that rule exists to prevent is a REGEX
naming a plausible variable no measurement supports (Skeledirge's bench scaler fitted as `atk_hand`).
Neither half of that failure mode is in play here: each entry is one human reading one card's own
printed sentence into one `attackId`, which is the same seam and the same discipline
`effect_overrides.json` already uses for clauses the probe cannot reach. What is NOT tolerable is
leaving 425 priced at zero while waiting for a defender-side sweep driver.

**Two of the four are now ENGINE-FITTED** (Issue #275): 120 and 425 were measured on the widened
axes and both fits REPRODUCED the human reading exactly, so no shipped value moved — the debt was
paid, not overruled. `SHIPPED` below is unchanged for that reason, and `attack_overrides.json` came
back byte-identical from the regeneration. 390 and 292 remain text-verified, still owed by the two
DEFERRED axes; see the corpus-status note at the bottom for why measuring them buys nothing today.

**The debt has an OWNER: Issue #275** (ratified by the user 2026-08-01 — ship these, file the
measurement). It is not a TODO in a docstring: #275 builds the two axes that can actually separate
these variables, and it scopes them to the two cards a corpus could ever see. Two findings shape it,
recorded here because they are the reason the gap existed rather than an oversight:

  * **The harness as it stood would CONFIRM the wrong answer for 425 — but not the way POC-T1 wrote
    it down.** Its recorded claim was that the defender panel is `{ex}`-BLIND, so the attack
    measures 0 and fits nothing. Driving the engine says the opposite, and the real situation is
    worse: the panel is `{ex}`-**SATURATED**. `_panel_body` and `bench_fodder` both rank by highest HP, and the
    eight highest-HP eligible basics in the pool are all Mega Pokemon ex — which ARE Pokemon ex
    (`docs/rulebook.txt` Appendix 1, which is why `src/cgpy/damage.py` counts `ex or megaEx`). So
    `audit_attack(425)` deals **120**, not 0, against card 1056 Mega Zygarde ex, `def_ex_in_play` is
    perfectly COLLINEAR with `def_bench`, and a fit names `def_bench`/60 — 60 damage per ordinary
    Basic on the opponent's bench, invented. Separating them needs a MATCHED non-`{ex}` control at
    the same bench count (Issue #275, REQ-AUDIT-0021); the best non-`{ex}` eligible basic is 251
    Regigigas at 160 HP.
  * **120 is unfittable on the current axes at all.** With the defender holding no Energy,
    `both_active_energy` and `atk_active_energy` are indistinguishable under every point the sweep
    can produce; separating them needs the defender-attach axis ADR-0083 §3's joining rule assumes
    (REQ-AUDIT-0020).

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
    """The last line of defence for four HUMAN RULINGS, and the failure message has to say so.

    Each of these four was read off one card's own printed sentence and cross-checked against
    `data/EN_Card_Data.csv` and `src/cgpy/defs/attack_data.json`. Two of them — 120 and 425 — have
    since been MEASURED on Issue #275's widened axes and the engine agreed with the reading, so the
    values here are now corroborated twice rather than once.

    That does NOT relax this test, because both are still unfittable on the NARROW axes: the panel's
    vanilla defender is a Mega Pokemon ex, making `def_ex_in_play` collinear with `def_bench`, and it
    holds no Energy, making `both_active_energy` indistinguishable from `atk_active_energy`. A run
    that drops the matched non-{ex} control or the defender-attach sweep still derives the wrong
    variable for each.

    So if this goes red, the fix is essentially never to update `SHIPPED`. `merge_provenance`'s
    REQ-PROV-0008 guard exists to stop a contradicting fit — or a NARROWER run's overwrite — reaching
    the table at all; a red here means either that guard was bypassed (`--rule`) or the table was
    hand-edited, and in both cases the question to answer is which reading of the card is right — not
    which number makes the test green again.
    """
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
    """ADR-0083 §4's rule, held for these four: every variable name IS a context key, so the oracle
    stays one dict lookup per scaler.

    The vocabulary HAS since grown a filtered-count form (ADR-TEMP-361, Issue #361 — see
    `tests/strategy/test_filtered_count_scalers.py`), and this test is what says these four did not
    move onto it. The split is CLOSED vs OPEN predicates: a stage, a rule box and a damage counter
    are finite engine-known facts that a flat name states in full, while "has 'Koffing' in its name"
    takes an arbitrary argument that a name could only state by hardcoding a card list. Migrating
    these four is explicitly out of scope of that ruling — they work, they are corpus-ruled, and
    moving them would move the damage oracle for attacks Issue #361 was not about."""
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
    """Card ids across every committed correction FRAME.

    Read through `tests/corpus_helpers.corpus_index()` — THE Corpus Reader — never by globbing
    `data/corrections/*/corrections.jsonl` (ADR-0087 decision 1 / ADR-0089; enforced by
    `tests/train/test_corpus_readers.py`). Verified equivalent to the raw walk it replaces: both
    reach 372 records and the same 273 distinct card ids, including both positive controls.

    Both halves of a record are walked. `obs` is the board and `decision` is what the agent was
    offered, and a card that appears only in the offered options is still a card the corpus can see.
    """
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
    """Brief filenames whose text mentions ``name``.

    Briefs reference cards in PROSE, never by id — read at source rather than assumed:
    `src/common/scouting/briefs/*.json` carry `slug`, `covers`, `summary` and `threats[].card`, and
    every card reference in them is a printed NAME. An id walk over a Brief returns the EMPTY SET,
    so reusing the id search here would have made this half of the assertion vacuous while looking
    exactly like the half that works.
    """
    return [p.name for p in paths if name.lower() in p.read_text(encoding="utf-8").lower()]


#: Every store this test reads, as ``(label, paths, loader, controls)``: the loader turns the files
#: into whatever the store keys cards BY, and `controls` are the cards that MUST be found in it.
#: Stated as data so the docstring's claim and the assertion cannot drift apart again — the test
#: used to check `artifact.json` and `deck.csv` only while claiming "every Brief and every
#: correction frame" too (Issue #275). Every store carries its own positive control, because a
#: negative result read off an instrument nobody proved was working is not a negative result.
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
#: The Brief store, keyed by printed NAME. 96 Teal Mask Ogerpon ex is deliberately NOT the control
#: here: it appears in no Brief, so using it would be a control that cannot fire. 306 Dudunsparce ex
#: does (2 Briefs), which is what proves the search works before its silence is believed.
_BRIEF_NAMES = {OGERPON: "Teal Mask Ogerpon", DUDUNSPARCE: "Dudunsparce",
                MAMOSWINE: "Mamoswine", AZELF: "Azelf"}


@pytest.mark.req("REQ-SCALER-0007")
def test_the_corpus_status_of_each_card_is_what_the_issue_recorded():
    """The issue's bar is "a corpus example OR a recorded absence", so the absence is ASSERTED — a
    claim nobody re-checks is a claim that rots. If 283 or 217 ever enters a shipped deck, a
    dossier, a Brief or a correction frame this fails, which is exactly when "no gate can see it"
    stops being true.

    **Widened to match its own docstring** (Issue #275). It asserted `artifact.json` and `deck.csv`
    while claiming "every Brief and every correction frame" too: both halves were true, but only one
    was protected from rot — and the unprotected half is the one a meta shift moves first.

    The correction-frame half goes through `tests/corpus_helpers.corpus_index()` rather than a glob
    (ADR-0087 decision 1) — eleven near-identical private corpus walkers is the defect that contract
    exists to prevent, and `tests/train/test_corpus_readers.py` fails on a twelfth.

    Each store is checked with a POSITIVE CONTROL, and the controls are not interchangeable: the id
    stores are keyed on `cardId`/`id` while Briefs name cards in prose, so the same search over both
    would come back empty from the Brief half and read as a clean absence. 306 Dudunsparce ex is the
    Brief control precisely because 96 Teal Mask Ogerpon ex appears in NO Brief and so cannot fire
    one.
    """
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
