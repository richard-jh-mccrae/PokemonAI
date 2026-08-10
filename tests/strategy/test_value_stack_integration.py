"""**The value stack, across the T1/T3 seam** — Issue #270's cross-track integration acceptance.

Issues #260 (the StateModel API) and Issue #262 (`state_value`) were built in parallel against one seam,
and a signature freeze promises shapes, not semantics. Four groups, one per surviving scope item:

* **A — the ENUMERATION.** An AST census of what `state_value` asks the model, against a reviewed
  list, so a new query goes red until somebody has answered what it returns when the fact is ABSENT.
  Three known collapses (ABSENT and ZERO arrive as one integer) are RULED and pinned, not fixed.
* **B — threading equivalence** on real corpus frames, for the two reads Issue #260's own tests miss.
* **C — end to end** through `tools/train/value_lab.py`, Issue #262's named acceptance instrument.
* **D — the ADR-0093 defect class**, structurally. Item 5 as worded is an empty intersection, so it
  is re-pointed at `Board`'s 23 numeric non-Optional defaults plus the small StateModel surface.

Corpus reads go through `corpus_helpers`, THE Corpus Reader (ADR-0087/0089).
"""
from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STATE_VALUE_SRC = REPO / "src" / "common" / "state_value.py"
PILOT_SRC = REPO / "src" / "common" / "pilot.py"          # the spine: where `StateModel.build` runs
BOARD_SRC = REPO / "src" / "common" / "deciders" / "facts.py"        # where the `Board` dataclass is DECLARED
BOARD_BUILD_SRC = REPO / "src" / "common" / "deciders" / "board_build.py"   # …and where it is CONSTRUCTED
STATE_MODEL_SRC = REPO / "src" / "common" / "state_model.py"

#: How many committed corpus frames the corpus-backed groups run over — capped where the controls
#: below still bite.
SAMPLE = 40


# ══ A — the ENUMERATION: what `state_value` asks the model ════════════════════════════════════════
# Censused by AST, not by grep: `state_value` names model queries inside its `blind_to` PROSE.

def _chain(node, aliases):
    """The dotted attribute chain ``node`` names, rooted at ``model``, or None. ``aliases`` maps a local
    bound to a model chain onto that chain, so a read through it resolves to the query it really is."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return None                       # rooted in a call/subscript/literal — not a model query
    if node.id == "model":
        base = ["model"]
    elif node.id in aliases:
        base = list(aliases[node.id])
    else:
        return None
    return base + list(reversed(parts))


def _model_queries(src: str) -> set[str]:
    """Every model read in ``src``, alias-resolved. Private names are dropped: `model._memoized` is the
    memo seam every family routes through, not a board fact."""
    tree = ast.parse(src)
    aliases: dict[str, list[str]] = {}
    # Aliases are bound over the whole module in source order. Resolution can only ADD chains, never
    # drop a read, because an unresolvable root contributes nothing.
    for n in ast.walk(tree):
        if not isinstance(n, ast.Assign) or len(n.targets) != 1:
            continue
        target, value = n.targets[0], n.value
        pairs = ([(target, value)] if isinstance(target, ast.Name)
                 else list(zip(target.elts, value.elts))
                 if isinstance(target, ast.Tuple) and isinstance(value, ast.Tuple) else [])
        for t, v in pairs:
            chain = _chain(v, aliases)
            if isinstance(t, ast.Name) and chain:
                aliases[t.id] = chain

    found = set()
    for n in ast.walk(tree):
        if not isinstance(n, ast.Attribute):
            continue
        chain = _chain(n, aliases)
        if not chain or len(chain) < 2 or chain[1].startswith("_"):
            continue
        # Depth 3 for the two SIDES and the prize composite, depth 2 for a top-level query. Deeper
        # reads are the returned BodyView/Payoff object's contract, not the model's.
        deep = len(chain) > 2 and chain[1] in ("mine", "theirs", "prize_race")
        found.add(".".join(chain[:3] if deep else chain[:2]))
    return found


#: **The reviewed list** — every query `state_value` consumes, and nothing else. The bare handles
#: (`model.mine`, `model.theirs`, `model.prize_race`) are navigation, not facts.
CONSUMED = frozenset({
    "model.mine", "model.theirs", "model.prize_race",
    # ── MySide (13) ──
    "model.mine.active", "model.mine.bench", "model.mine.bodies", "model.mine.bench_raws",
    "model.mine.readiness_p", "model.mine.turns_to_afford",
    "model.mine.role_worth", "model.mine.needs", "model.mine.forward_payoff",
    "model.mine.best_reachable_damage_vs", "model.mine.best_reachable_bench_damage",
    # REVIEWED, and NOT a `RULED_COLLAPSES` case: `MySide.attack_blocked` reads an ABSENT turn as 0,
    # which is `<= 1`, which returns True == BLOCKED — so absence fails CLOSED, into no claim.
    "model.mine.attack_blocked",
    # ── TheirSide (7) — the newly-threaded half ──
    "model.theirs.active_raw", "model.theirs.bodies", "model.theirs.turns_to_ko_me",
    "model.theirs.reachable_incoming", "model.theirs.hand_size",
    # Issue #456: absent `handCount` intentionally equals an empty hand; the collapse test pins it.

    # `theirs.forward_payoff` LEFT at ADR-0119: the forward DAMAGE a removal denies is already inside
    # `survival`'s clock. REVIEWED: `forward_line_prize` floors at `own_prize`, so absence fails CLOSED.
    "model.theirs.forward_line_prize",
    # `theirs.active` joined at Issue #384. REVIEWED: an ABSENT Active seat reads **None**, a value no
    # live body can take, and `attack_ev` caps its fallback at `target_prizes` — fail-closed, not a 0.
    "model.theirs.active",
    # ── the cross-side composite (2) and the top level (2) ──
    "model.prize_race.my_prizes_remaining", "model.prize_race.opp_prizes_remaining",
    "model.damage_context",
    # `attack_profile` joined at Issue #384. REVIEWED: an unresolvable attack returns
    # `_EMPTY_ATTACK_PROFILE`, and `attack_ev_legs` FILTERS on `affordable` — no leg rather than a 0.
    "model.attack_profile",
    # Issue #495: the combat profile owns these reads. Empty zones enumerate empty tuples/maps;
    # absent bodies/stats return None and produce UNKNOWN/zero-compatible candidates.
    "model.card_stat", "model.combat", "model.mine.active_raw", "model.mine.bench_names",
    "model.mine.deck_energy_counts", "model.mine.forward_forms", "model.mine.view_of",
})

#: The three reads whose ABSENT value is INDISTINGUISHABLE from a measured zero — a ruling, not an
#: accident. Only the first is DIRECT; the other two arrive inside the Damage Formula context.
RULED_COLLAPSES = {
    "prizes_remaining": "DIRECT, via `model.prize_race`: an absent `prize` zone reads as an empty "
                        "list -> 0; `prizes_taken`'s docstring (`state_model.py`) records the fail "
                        "direction, and `state_value._predicted_loss` reasons about it at its own "
                        "call site (`state_value.py:1038`) while nothing pinned it until now",
    "hand_size": "INDIRECT, via `model.damage_context` -> `damage_facts`: "
                 "`int(self.player.get('handCount') or 0)` — an absent count is an empty hand",
    "deck_count": "INDIRECT, same route: `int(self.player.get('deckCount') or 0)`, same shape",
}


@pytest.mark.req("REQ-VALUESTACK-0001")
def test_the_queries_state_value_consumes_are_the_ENUMERATED_ones():
    """Nothing enumerated the SET, so a query could join `state_value` without anyone asking what it
    returns when the fact is ABSENT. A new name here is a prompt, not a failure."""
    censused = _model_queries(STATE_VALUE_SRC.read_text(encoding="utf-8"))

    assert censused == CONSUMED, (
        "the queries `state_value` makes have moved:\n"
        f"  NEW (unreviewed — what does this return when the fact is ABSENT?): "
        f"{sorted(censused - CONSUMED)}\n"
        f"  GONE (drop it from CONSUMED): {sorted(CONSUMED - censused)}")


@pytest.mark.req("REQ-VALUESTACK-0001")
def test_the_census_cannot_see_a_query_that_is_only_PROSE():
    """The control. `state_value` contains the text ``mine.active.grant`` inside a `blind_to` string
    saying that grant is NOT carried; a grep reads that as a read, the AST cannot."""
    assert _model_queries("x = model.thing.here\n") == {"model.thing"}, "the instrument is dead"
    assert _model_queries('BLURB = "model.thing.here is not read"\n') == set()
    assert "model.mine.active.grant" not in CONSUMED, "the prose read got into the reviewed list"
    assert "mine.active.grant" in STATE_VALUE_SRC.read_text(encoding="utf-8"), \
        "the `blind_to` prose that motivates this control is gone — re-point it at another string, "\
        "or the control no longer proves the census can be fooled by one"


@pytest.mark.req("REQ-VALUESTACK-0002")
def test_the_three_ABSENT_as_ZERO_collapses_are_RULED_and_stay_collapsed():
    """Asserted by BUILDING both boards — one stating the fact as zero/empty, one omitting the key —
    and requiring identical answers. Teaching any of these to distinguish them is a ruling."""
    from common.cards import CardFunctions
    from common.state_model import StateModel
    from common.strategy.combat import CombatMath
    from common.scouting.provider import DictCardStatProvider

    # Empty boards: no body means no card fact is ever consulted, so a stat-blind oracle is enough
    # and the three reads under test (`handCount`, `deckCount`, the `prize` zone) never touch it.
    combat = CombatMath(DictCardStatProvider({}, attacks={}), CardFunctions({}))

    def _side(**over):
        base = {"active": [], "bench": [], "hand": [], "discard": [],
                "handCount": 0, "deckCount": 0, "prize": []}
        base.update(over)
        return base

    def _built(me, opp):
        obs = {"current": {"players": [me, opp], "yourIndex": 0, "turn": 3}, "logs": []}
        return StateModel.build(obs, combat=combat)

    stated = _built(_side(), _side())
    # The same board with the three keys REMOVED — absence, not a stated zero.
    absent = _built({k: v for k, v in _side().items() if k not in ("handCount", "deckCount", "prize")},
                    {k: v for k, v in _side().items() if k not in ("handCount", "deckCount", "prize")})

    assert absent.theirs.hand_size == stated.theirs.hand_size == 0, RULED_COLLAPSES["hand_size"]
    assert absent.theirs.deck_count == stated.theirs.deck_count == 0, RULED_COLLAPSES["deck_count"]
    assert (absent.prize_race.opp_prizes_remaining
            == stated.prize_race.opp_prizes_remaining == 0), RULED_COLLAPSES["prizes_remaining"]
    assert (absent.prize_race.my_prizes_remaining
            == stated.prize_race.my_prizes_remaining == 0), RULED_COLLAPSES["prizes_remaining"]

    # The control: the instrument CAN tell two boards apart, so the equalities above are readings
    # rather than a build that quietly failed and answered 0 to everything.
    assert _built(_side(handCount=7, deckCount=31, prize=[None] * 4),
                  _side(handCount=5, deckCount=29, prize=[None] * 6)).theirs.hand_size == 5


@pytest.mark.req("REQ-VALUESTACK-0002")
def test_ABSENT_is_expressible_where_the_model_CHOSE_to_express_it():
    """The positive control: the model already draws the ABSENT/ZERO distinction, for the clock's policy
    ARGUMENT (`_THREADED`). Return VALUES have no such sentinel."""
    from common.state_model import _THREADED, TheirSide

    threaded = TheirSide.__new__(TheirSide)
    threaded._charged = {"sentinel": 1}

    assert threaded._charged_policy(_THREADED) == {"sentinel": 1}, "unset takes the threaded budget"
    assert threaded._charged_policy(None) is None, "an explicit None is the CEILING, not 'unset'"
    assert _THREADED is not None, "the sentinel collapsed onto None — the distinction is gone"


# ══ B — threading equivalence, and the `_predicted_loss` port ═════════════════════════════════════

@pytest.fixture(scope="module")
def live_models():
    """``[(key, pilot, model, obs)]`` for a sample of corpus frames through the PRODUCTION path.
    `_board()` and not `_leaf_state_model()`: only the live path threads `charged`/`forward_ids`."""
    from corpus_helpers import corpus_index
    from train.tune import _build_pilot
    out, built = [], {}
    for (episode, frame), rec in sorted(corpus_index().items())[:SAMPLE]:
        if rec.agent not in built:
            try:
                built[rec.agent] = _build_pilot(rec.agent)[0]
            except Exception:                    # an unbuildable agent is skipped, never fatal
                built[rec.agent] = None
        pilot = built[rec.agent]
        if pilot is None:
            continue
        try:
            pilot._turn_boosts.observe(rec.obs)
            pilot._board(rec.obs, rec.obs.get("select"), carried=pilot.carried())
        except Exception:
            continue
        model = pilot._state_model
        if model is not None and model.mine.active is not None:
            out.append((f"{episode}|{frame}", pilot, model, rec.obs))
    if len(out) < 10:
        pytest.skip("no replayable corrections corpus in this checkout")
    return out


@pytest.mark.req("REQ-VALUESTACK-0003")
def test_the_model_routed_turns_to_ko_me_equals_the_direct_call_under_the_SAME_policy(live_models):
    """`state_value` calls `theirs.turns_to_ko_me(...)` with no `charged=`, so it takes the budget
    threaded at build. Control: dropping the policy to the explicit `None` ceiling must MOVE a frame."""
    checked = moved = 0
    for key, pilot, model, _obs in live_models:
        theirs, active = model.theirs, model.mine.active
        context = model.damage_context(attacker="theirs")
        routed = theirs.turns_to_ko_me(active.body, context=context)
        direct = pilot.combat.turns_to_ko_me(active.body, theirs.body_raws,
                                             charged=theirs._charged, context=context)
        assert routed == direct, (
            f"{key}: the model route answers a DIFFERENT question than the direct call — "
            f"{routed} vs {direct}. A migrated consumer silently reverted to another policy.")
        moved += theirs.turns_to_ko_me(active.body, charged=None, context=context) != routed
        checked += 1

    assert checked >= 10, "the parity corpus went missing"
    assert moved, ("CONTROL FAILED: dropping the energy policy to the worst-case ceiling moved no "
                   "frame, so the equality above is not evidence the policy is threaded at all")


@pytest.mark.req("REQ-VALUESTACK-0003")
def test_the_model_routed_reachable_incoming_equals_the_direct_call_with_BOTH_kwargs(live_models):
    """The sibling read, and the harder one: it threads `charged` AND `forward_ids`, and a route that
    dropped either would read a strictly narrower board while still returning an int."""
    checked = moved = 0
    for key, pilot, model, _obs in live_models:
        theirs, active = model.theirs, model.mine.active
        context = model.damage_context(attacker="theirs")
        routed = theirs.reachable_incoming(active.body, evo_min_energy=1, context=context)
        direct = pilot.combat.reachable_incoming(
            active.body, theirs.body_raws, forward_ids=theirs._forward_ids,
            charged=theirs._charged, evo_min_energy=1, context=context)
        assert routed == direct, (
            f"{key}: model-routed Incoming {routed} != direct {direct} under the same policy and "
            f"forward index — the threaded read is not the read it replaced")
        stripped = pilot.combat.reachable_incoming(
            active.body, theirs.body_raws, forward_ids=None, charged=None,
            evo_min_energy=1, context=context)
        moved += stripped != routed
        checked += 1

    assert checked >= 10, "the parity corpus went missing"
    assert moved, ("CONTROL FAILED: dropping both threaded parameters moved no frame, so the "
                   "equality above cannot show they are threaded")


@pytest.mark.req("REQ-VALUESTACK-0003")
def test_the_LEAF_board_state_value_actually_scores_threads_NEITHER_clock_parameter():
    """A FINDING, recorded as a test: the planner's leaf builds its snapshot with NO `forward_ids` and
    NO `charged`, so both fall to `None`. Not a defect — the leaf scores a SIMULATED board."""
    def _sole_build(path: Path):
        """The ONE `StateModel.build(...)` in a module, as keyword names. Sole by assertion, not by
        `next()`: a second site would make the claim about whichever call the walker reached first."""
        sites = [n for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                 if isinstance(n, ast.Call) and ast.unparse(n.func) == "StateModel.build"]
        assert len(sites) == 1, f"{path.name} now builds a StateModel in {len(sites)} places"
        return {k.arg for k in sites[0].keywords}

    assert {"forward_ids", "charged"} <= _sole_build(PILOT_SRC), (
        "the LIVE path stopped threading the clock parameters — the two equivalence tests above "
        "have gone vacuous and must be re-pointed, not deleted")

    leaf_kwargs = _sole_build(REPO / "src" / "common" / "strategy" / "planning" / "leaf.py")
    assert not ({"forward_ids", "charged"} & leaf_kwargs), (
        "the LEAF path now threads a clock parameter. That is a scoring change at every `survival` "
        "read, not a refactor — rule it, then update this test's finding.")


@pytest.mark.req("REQ-VALUESTACK-0004")
def test_predicted_loss_makes_the_SAME_clock_call_as_the_incumbent_it_ports(live_models):
    """`state_value._predicted_loss` claims to be a port of `planner.Planner._predicted_loss`, and it
    moves a terminal −KO_SCORE rung, so the resemblance is measured. Verdict: they AGREE."""
    checked = moved = 0
    for key, pilot, model, _obs in live_models:
        theirs, active = model.theirs, model.mine.active
        context = model.damage_context(attacker="theirs")

        # `state_value._predicted_loss`'s `_doomed`, verbatim in its arguments.
        as_state_value = theirs.reachable_incoming(
            active.body, evo_min_energy=1, my_benched=not active.is_active, context=context)

        # `planner._predicted_loss`'s call, verbatim: synthetic body, explicit `bodies=`, and the
        # `my_benched` default (its body is the Active, so `not is_active` is False there too).
        players = (_obs.get("current") or {}).get("players") or []
        opponent = players[1 - model.my_index] if len(players) > 1 else {}
        opp_bodies = (opponent.get("active") or []) + (opponent.get("bench") or [])
        as_planner = theirs.reachable_incoming(
            {"id": active.card_id, "hp": active.hp_remaining}, bodies=opp_bodies,
            evo_min_energy=1, context=context)

        assert as_state_value == as_planner, (
            f"{key}: the PORT and the INCUMBENT read different Incoming — {as_state_value} vs "
            f"{as_planner}. `state_value._predicted_loss`'s docstring claims it is the incumbent's "
            f"judgement; at a terminal -KO_SCORE rung, that claim has to be true or withdrawn.")

        moved += theirs.reachable_incoming(
            active.body, bodies=(), evo_min_energy=1, my_benched=not active.is_active,
            context=context) != as_state_value
        checked += 1

    assert checked >= 10, "the parity corpus went missing"
    assert moved, ("CONTROL FAILED: emptying the opponent board moved no frame, so the two spellings "
                   "agreeing shows only that both read nothing")


# ══ C — end to end on real frames, through `value_lab` ════════════════════════════════════════════

@pytest.fixture(scope="module")
def value_lab_rows():
    """``(report, rows)`` from `tools/train/value_lab.py` over the corpus sample — Issue #262's named
    acceptance instrument, which shipped with no test coverage while every sibling lab had some."""
    from corpus_helpers import corpus_index
    from train.tune import _build_pilot
    from train.value_lab import value_lab_report

    built: dict = {}

    def pilot_for(agent):
        if agent not in built:
            try:
                built[agent] = _build_pilot(agent)[0]
            except Exception:
                built[agent] = None
        return built[agent]

    corrections = [c for _key, c in sorted(corpus_index().items())[:SAMPLE]]
    if not corrections:
        pytest.skip("no replayable corrections corpus in this checkout")
    report = value_lab_report(pilot_for, corrections)
    return report, report["rows"]


@pytest.mark.req("REQ-VALUESTACK-0005")
def test_value_lab_scores_every_replayable_corpus_frame_with_every_term_finite(value_lab_rows):
    """`state_value` is called once per candidate option per decision, so a raise is a forfeited grader
    match rather than a logged warning. Failures are NAMED, never counted."""
    report, rows = value_lab_rows
    from common.state_value import FAMILIES

    broken = [(r["key"], r["error"]) for r in rows if r["error"] is not None]
    assert not broken, "`state_value` raised on replayable frames:\n" + "\n".join(
        f"  {key:<28} {err}" for key, err in broken)
    assert report["scored"] >= 10, "the replayable corpus went missing"

    for row in rows:
        assert set(row["working"]) == set(FAMILIES), (
            f"{row['key']}: `working` covers {sorted(row['working'])}, the registry declares "
            f"{sorted(FAMILIES)} — a term that emits no working is invisible to the ruling packet")
        assert math.isfinite(row["value"]), f"{row['key']}: total is {row['value']}"
        for name, contribution in row["working"].items():
            assert math.isfinite(contribution), f"{row['key']}: {name} = {contribution}"


#: Families RULED to read exactly 0.0 on every board of the corpus sample, with the ruling. Empty,
#: and it must stay hard to add to: an entry retires a term's whole contribution from the scalar.
RULED_ALWAYS_ZERO: dict[str, str] = {}


@pytest.mark.req("REQ-VALUESTACK-0005")
def test_no_family_is_SILENTLY_zero_across_the_whole_corpus_sample(value_lab_rows):
    """*"No silent zeros"* asserted per FAMILY, never per frame: a term pricing a fact the board does
    not carry SHOULD read zero. `blind_spots()` cannot exempt — all six families appear in it."""
    from common.state_value import FAMILIES, blind_spots

    scored = [r for r in value_lab_rows[1] if r["error"] is None]
    assert len(scored) >= 10, "the replayable corpus went missing"

    always_zero = sorted(name for name in FAMILIES
                         if all(row["working"][name] == 0.0 for row in scored))
    assert not [n for n in always_zero if n not in RULED_ALWAYS_ZERO], (
        f"{always_zero} contributed exactly 0.0 on all {len(scored)} corpus frames — a term that is "
        "structurally dead rather than merely quiet. Either it reads a field the model never fills "
        "(the coverage drift this issue exists for), or the board shape genuinely cannot feed it, in "
        "which case that is a RULING: record the dimension in the family's `blind_to` so "
        "`blind_spots()` reports it to the 1-ply composer, and name it in RULED_ALWAYS_ZERO here "
        "with the ruling. Do not relax this assertion.")

    assert any(row["working"]["hand"] != 0.0 for row in scored), (
        "`hand` is zero on every LIVE corpus frame too. Issue #331's ruling covers the LEAF path — a "
        "board whose turn has passed and whose hand is therefore hidden — and does not reach here.")

    # The control: the instrument can see a zero at all, so the emptiness above is a reading and not
    # a comparison that never fires.
    assert any(row["working"][name] == 0.0 for row in scored for name in FAMILIES), \
        "no term read zero anywhere — the zero detector is not detecting zeros"
    assert set(blind_spots()) >= set(FAMILIES), \
        "a family stopped declaring any blind spot — the registry channel this test defers to is gone"


@pytest.mark.req("REQ-VALUESTACK-0005")
def test_value_lab_reports_the_tail_issue_263_has_to_size_its_beam_against(value_lab_rows):
    """`value_lab_report` reports the P95 beside the median because the composer calls `state_value`
    once per candidate, so the TAIL decides whether a wide menu fits the grader budget."""
    report, rows = value_lab_rows
    from common.state_value import FAMILIES

    assert report["n"] == len(rows) and report["scored"] + report["failed"] == report["n"]
    assert report["median_ms"] is not None and math.isfinite(report["median_ms"])
    assert math.isfinite(report["p95_ms"]) and report["p95_ms"] >= report["median_ms"]
    assert set(report["term_means"]) == set(FAMILIES)
    assert all(math.isfinite(mean) for mean in report["term_means"].values())


# ══ D — the ADR-0093 defect class, structurally ═══════════════════════════════════════════════════

def _annotated_numeric(src: str, class_name: str):
    """``([(field, default)] non-Optional numeric, [(field, default)] Optional numeric)`` for a
    dataclass's annotated attributes."""
    cls = next(n for n in ast.parse(src).body
               if isinstance(n, ast.ClassDef) and n.name == class_name)
    plain, optional = [], []
    for statement in cls.body:
        if not isinstance(statement, ast.AnnAssign) or statement.value is None:
            continue
        annotation = ast.unparse(statement.annotation)
        entry = (statement.target.id, ast.unparse(statement.value))
        if annotation in ("int", "float"):
            plain.append(entry)
        elif "None" in annotation and ("int" in annotation or "float" in annotation):
            optional.append(entry)
    return plain, optional


@pytest.mark.req("REQ-VALUESTACK-0006")
def test_state_value_reads_NO_board_field_which_is_why_item_5_is_RE_POINTED():
    """Item 5 as worded describes an EMPTY intersection: `state_value` takes a StateModel and reads
    nothing else, so it touches no `Board` field. Measured, because the re-pointing rests on it."""
    source = STATE_VALUE_SRC.read_text(encoding="utf-8")
    assert "Board" in source, "the prose that makes this measurement worth making is gone"

    tree = ast.parse(source)
    referenced = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    imported = {alias.name for n in ast.walk(tree)
                if isinstance(n, (ast.Import, ast.ImportFrom)) for alias in n.names}
    assert "Board" not in referenced | imported, (
        "`state_value` now names `Board`. It has a second data supplier, which the sole-supplier "
        "ruling forbids — and item 5's literal scope has stopped being empty, so re-point it back.")

    # The control: the instrument DOES find the dataclass where it really lives.
    facts_tree = ast.parse(BOARD_SRC.read_text(encoding="utf-8"))
    assert any(isinstance(n, ast.ClassDef) and n.name == "Board" for n in ast.walk(facts_tree))


#: ``(enclosing function, field) -> why ABSENT is unreachable`` for a `Board(...)` site allowed to
#: leave a numeric field on its dataclass default. Keyed by function, not line. Empty is the finding.
DELIBERATE_BOARD_DEFAULTS: dict[tuple[str, str], str] = {}


def _construction_sites(src: str, class_name: str):
    """``[(enclosing function, {kwarg names})]`` for every ``ClassName(...)`` call in ``src``."""
    sites, stack = [], []

    class Visitor(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            stack.append(node.name)
            self.generic_visit(node)
            stack.pop()

        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id == class_name:
                sites.append((stack[-1] if stack else "<module>",
                              {k.arg for k in node.keywords if k.arg}))
            self.generic_visit(node)

    Visitor().visit(ast.parse(src))
    return sites


@pytest.mark.req("REQ-VALUESTACK-0006")
def test_every_numeric_board_field_is_SET_at_every_construction_site():
    """ADR-0093's defect class made structurally impossible: if every numeric field is EXPLICITLY passed
    wherever a `Board` is built, no default can be read as a measurement, whatever its type."""
    numeric, _optional = _annotated_numeric(BOARD_SRC.read_text(encoding="utf-8"), "Board")
    assert len(numeric) >= 20, f"the Board census found only {len(numeric)} numeric fields"

    sites = _construction_sites(BOARD_BUILD_SRC.read_text(encoding="utf-8"), "Board")
    assert sites, "no `Board(...)` construction found — the census instrument is broken"

    unset = [(where, field) for where, passed in sites for field, _default in numeric
             if field not in passed and (where, field) not in DELIBERATE_BOARD_DEFAULTS]
    assert not unset, (
        "a numeric `Board` field falls to its dataclass default at a construction site, so ABSENT "
        "arrives as a number that reads like a measurement (ADR-0093). Pass it explicitly, make it "
        "Optional, or add it to DELIBERATE_BOARD_DEFAULTS with why absence is unreachable:\n"
        + "\n".join(f"  pilot.py  {where}() -> Board(… {field} unset)" for where, field in unset))
    assert all(reason.strip() for reason in DELIBERATE_BOARD_DEFAULTS.values()), \
        "an allowlisted default carries no reason, which is what this allowlist exists to forbid"


@pytest.mark.req("REQ-VALUESTACK-0006")
def test_the_optional_numeric_board_fields_still_default_to_None():
    """ADR-0093's own fix, pinned. A field that gains an `| None` annotation and keeps a numeric default
    has the worst of both: the type says absence is expressible, the default guarantees it is not."""
    _numeric, optional = _annotated_numeric(BOARD_SRC.read_text(encoding="utf-8"), "Board")
    assert ("deny_relevance_best", "None") in optional, \
        "ADR-0093's own field is no longer Optional-with-a-None-default"

    numeric_defaulted = [(field, default) for field, default in optional if default != "None"]
    assert not numeric_defaulted, (
        "an Optional-numeric `Board` field defaults to a NUMBER, so ABSENT can never be observed "
        f"even though the type says it can: {numeric_defaulted}")


@pytest.mark.req("REQ-VALUESTACK-0006")
def test_the_StateModel_numeric_defaults_are_the_two_RULED_collapses():
    """`PrizeRace` (2 numeric zeros) is never built with a default; bare `CountTriple()` IS constructed,
    and its all-zero triple answers "not possible" to a presence gate — the SAFE direction."""
    from common.state_model import CountTriple

    source = STATE_MODEL_SRC.read_text(encoding="utf-8")
    prize_numeric, _ = _annotated_numeric(source, "PrizeRace")
    triple_numeric, _ = _annotated_numeric(source, "CountTriple")
    assert len(prize_numeric) == 2 and len(triple_numeric) == 4, \
        f"the StateModel numeric surface moved: {prize_numeric} / {triple_numeric}"
    assert all(default in ("0", "0.0") for _f, default in prize_numeric + triple_numeric)

    for name, fields in (("PrizeRace", prize_numeric), ("CountTriple", triple_numeric)):
        sites = _construction_sites(source, name)
        assert sites, f"no `{name}(...)` construction found — the instrument is broken"
        defaulted = sorted({where for where, passed in sites
                            if any(field not in passed for field, _ in fields)})
        if name == "PrizeRace":
            assert not defaulted, (
                f"`PrizeRace` is now built with a defaulted count, in {defaulted}. Its fields feed "
                "`state_value`'s terminal prize-lethality rung, where 0 is read as falsy on purpose "
                "— a default arriving there is a silent win-condition test.")
        else:
            assert defaulted, ("`CountTriple()` bare is no longer constructed — the fail-CLOSED "
                               "collapse this test documents is gone; re-read the ruling first")

    assert CountTriple().possible is False, \
        "the all-zero triple now claims a card is POSSIBLE — the collapse stopped failing closed"


# ══ E — item 4, recorded as pre-discharged ════════════════════════════════════════════════════════

@pytest.mark.req("REQ-VALUESTACK-0007")
def test_the_bypass_census_this_issue_asked_for_was_ALREADY_BUILT_by_issue_260():
    """Scope item 4 was ALREADY BUILT by Issue #260, in `test_combat_bypass_census.py`. Its CONTENT is
    asserted, never its existence; the census VERDICT is deliberately not re-asserted here."""
    import test_combat_bypass_census as census

    assert len(census.MODEL_COVERED) >= 10, "the model-covered question set was emptied"
    assert "reachable_incoming" in census.MODEL_COVERED and \
           "turns_to_ko_me" in census.MODEL_COVERED, \
        "the two clock reads `state_value` makes are no longer census-covered"
    assert census.DELIBERATE, "the deliberate allowlist was emptied — every entry is a decision"
    assert all(reason.strip() for reason in census.DELIBERATE.values()), \
        "an allowlisted bypass carries no reason, which is what the census exists to forbid"
    assert census._bypasses(), \
        "the AST walker finds no call sites at all — the census has gone vacuous"
