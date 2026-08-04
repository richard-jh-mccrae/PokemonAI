"""**The value stack, across the T1/T3 seam** — Issue #270's cross-track integration acceptance.

Issues #260 (the StateModel API) and #262 (`state_value`, which consumes it) were built in parallel
against one seam, and the hazard the issue exists for is the one neither PR's suite can see: a field
#260 returns and #262 reads, populated under different conditions than #262 assumes. A signature
freeze (Issue #259) promises shapes, not semantics.

Four groups, one per surviving scope item. The fifth — *"the bypass census as a test"* — was
**already built by #260 itself**, exactly as this issue predicted it might be, and is recorded here
as pre-discharged with a pointer rather than duplicated (:func:`test_the_bypass_census_this_issue_
asked_for_was_ALREADY_BUILT_by_issue_260` quotes the module rather than asserting the file exists,
because file existence is never evidence of file content).

**A — the ENUMERATION.** Nothing enumerated what `state_value` actually asks the model. The census
below does, by AST, and the table is the reviewed list: a new query added to `state_value` goes red
until somebody has looked at what that query returns when the fact behind it is ABSENT. Three of the
twenty-one are known **collapses** — ABSENT and ZERO arrive as the same integer — and those are RULED,
not asserted-and-forgotten: the tests here pin the collapse so that "fixing" one is a decision.

**B — threading equivalence.** #260's migration is only honest if the model route answers what the
bypass answered. Asserted on real corpus frames for the two reads `state_value` makes and #260's own
tests do not cover, each with a control showing the assertion could fail. The single highest-value
case is :func:`test_predicted_loss_makes_the_SAME_clock_call_as_the_incumbent_it_ports` — the
docstring at `state_value.py:1005-1010` claims a port; this is what checks it.

**C — end-to-end on real frames**, through `tools/train/value_lab.py`, #262's own named acceptance
instrument, which had zero test coverage while every sibling lab had a dedicated module.

**D — the ADR-0093 defect class**, structurally. `deny_relevance_best: float = 0.0` could not express
ABSENT, so a dataclass default read as a measured whiff and the fire rung declined strips worth
+22.50 and +74.50. Item 5 as the issue words it (*"no **Board** field consumed by `state_value`"*) is
literally empty — `state_value` reads no `Board` field at all, and
:func:`test_state_value_reads_NO_board_field_which_is_why_item_5_is_RE_POINTED` is the measurement
that says so — so it is re-pointed at the real exposure: the 23 numeric non-Optional defaults on
`Board` itself, plus the small StateModel surface.

**Every assertion here was mutation-checked**, because most of them are negative or equality results
and those are the ones that go vacuous without anyone noticing. Eleven mutants — a new unreviewed
model query, a `Board` field left to its default, an Optional field regaining a numeric default, the
threaded policy silently dropped, `prizes_remaining` learning to tell ABSENT from empty, the leaf
build threading a clock parameter, a family stubbed to 0.0, `state_value` naming `Board`, `_THREADED`
collapsing onto `None`, `PrizeRace` built with a defaulted count, the bypass allowlist emptied — and
each turned exactly the intended test red. One of them mattered immediately: the first draft of
:func:`test_no_family_is_SILENTLY_zero_across_the_whole_corpus_sample` excused any family listed in
`blind_spots()`, and since all six are listed it stayed GREEN under a stubbed `survival`. See that
test's docstring for what replaced it.

Cost: the whole module runs in a couple of seconds. Corpus reads go through `corpus_helpers`, THE
Corpus Reader (ADR-0087/0089); nothing here globs `data/corrections/`.
"""
from __future__ import annotations

import ast
import math
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
STATE_VALUE_SRC = REPO / "src" / "common" / "state_value.py"
PILOT_SRC = REPO / "src" / "common" / "pilot.py"
STATE_MODEL_SRC = REPO / "src" / "common" / "state_model.py"

#: How many committed corpus frames the corpus-backed groups run over. Matches
#: `test_state_value.py`'s `_corpus_models()` sample for the same reason it caps: the whole point is
#: boards nobody designed, and 40 is where the controls below still bite (measured: the policy-drop
#: control moves 3 `turns_to_ko_me` reads and 6 `reachable_incoming` reads across this sample).
SAMPLE = 40


# ══ A — the ENUMERATION: what `state_value` asks the model ════════════════════════════════════════
#
# Censused by AST rather than by grep, and the difference is not stylistic. `state_value` writes the
# names of model queries into its `blind_to` PROSE — "`transient_grants` (ADR-0033, homed
# `mine.active.grant` only)" at `state_value.py:821` is a sentence about a read this module does NOT
# make — and a grep counts those as reads. The AST cannot see inside a string literal, which is
# exactly the property being relied on (and `test_the_census_cannot_see_a_query_that_is_only_PROSE`
# is the control that proves it holds).

def _chain(node, aliases):
    """The dotted attribute chain ``node`` names, rooted at ``model``, or None.

    ``aliases`` maps a local name bound to a model chain (`mine, theirs = model.mine, model.theirs`)
    onto that chain, so a read through the local resolves to the query it really is."""
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
    """``{"model.mine.bodies", …}`` — every model read in ``src``, alias-resolved.

    Private names are dropped: `model._memoized` is the memo seam every family routes through, not a
    board fact, and a table of board facts that carried it would be describing plumbing."""
    tree = ast.parse(src)
    aliases: dict[str, list[str]] = {}
    # Alias binding is done over the whole module in source order before the reads are collected.
    # Two properties make that sound here rather than merely convenient: `state_value` binds each
    # local from a model chain exactly once per function, and no two functions bind the same name to
    # different chains at the same DEPTH -- `_predicted_loss`'s `mine` is `model.mine` while
    # `_threat`'s is `model.mine.active`, and the deeper one contributes no attribute reads at all.
    # A future binding this shortcut mis-resolves shows up as a name that is not in `CONSUMED`, which
    # is a RED test asking to be looked at rather than a silent mis-census -- resolution can only ADD
    # chains, never drop a read, because an unresolvable root contributes nothing.
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
        # Depth 3 for the two SIDES and the prize composite (`model.mine.bodies`), depth 2 for a
        # top-level query (`model.damage_context`). Deeper reads are on the BodyView/Payoff objects
        # those queries return, and are the returned object's contract rather than the model's.
        deep = len(chain) > 2 and chain[1] in ("mine", "theirs", "prize_race")
        found.add(".".join(chain[:3] if deep else chain[:2]))
    return found


#: **The reviewed list** — every query `state_value` consumes, and nothing else. Grouped as the
#: contract groups them: the two sides, the cross-side composite, and the top level.
#:
#: The bare handles (`model.mine`, `model.theirs`, `model.prize_race`) are here because the census
#: reports them; they are navigation, not facts. The twenty-three FACTS are everything below them
#: (13 + 6 + 2 + 2; Issue #384 added `theirs.active` and `attack_profile`, both reviewed in place).
CONSUMED = frozenset({
    "model.mine", "model.theirs", "model.prize_race",
    # ── MySide (13) ──
    "model.mine.active", "model.mine.bench", "model.mine.bodies", "model.mine.bench_raws",
    "model.mine.attack_payoff", "model.mine.readiness_p", "model.mine.turns_to_afford",
    "model.mine.role_worth", "model.mine.needs", "model.mine.forward_payoff",
    "model.mine.best_reachable_damage_vs", "model.mine.best_reachable_bench_damage",
    # `attack_blocked` joined at Issue #351 (`state_value._may_attack_now`, the legality leg
    # `readiness_p` does not have). REVIEWED, and it is NOT a `RULED_COLLAPSES` case — its absent
    # direction is the opposite hazard. Read at source: `MySide.attack_blocked` is
    # `self.turn <= 1 or bool(player.get("asleep") or player.get("paralyzed"))`, over
    # `self.turn = int(turn or 0)`. So an ABSENT turn reads 0, which is `<= 1`, which returns
    # True == BLOCKED — and a blocked body makes the now-leg claim NOTHING and fall back to the
    # forward clock. Absence therefore fails CLOSED here, where the three collapses below fail into
    # a value that reads like a measurement. The condition flags collapse the other way
    # (`.get()` -> None -> False), but they are unreachable on an absent-turn board because the
    # turn leg short-circuits first, and on a real observation the engine always states them.
    "model.mine.attack_blocked",
    # ── TheirSide (6) — the newly-threaded half ──
    "model.theirs.active_raw", "model.theirs.bodies", "model.theirs.turns_to_ko_me",
    "model.theirs.reachable_incoming", "model.theirs.forward_payoff",
    # `theirs.active` joined at Issue #384 (`attack_ev_legs`, which needs the DEFENDER's remaining
    # HP and prize value, not just the raw dict the clock reads). REVIEWED, and NOT a
    # `RULED_COLLAPSES` case. Read at source: `_SideBase.active` is
    # `next((p for p in (self.player.get("active") or []) if p), None)` wrapped in a `BodyView` —
    # so an ABSENT Active seat reads **None**, a value no live body can take, and the extractor
    # branches on it to price the target at 0 HP / 0 prizes. `attack_ev` then takes its own
    # documented unreadable-HP fallback, which is capped by `target_prizes` and so returns exactly
    # 0. Absence is therefore both DISTINGUISHABLE and fail-closed, which is the opposite of the
    # three collapses below.
    "model.theirs.active",
    # ── the cross-side composite (2) and the top level (2) ──
    "model.prize_race.my_prizes_remaining", "model.prize_race.opp_prizes_remaining",
    "model.damage_context",
    # `attack_profile` joined at Issue #384 — the ONE new accessor the terminal-action extractor
    # needed, because `attack_payoff` returns `(attack_id, damage)` and the model exposed no rider,
    # lock or economy field at all. REVIEWED: absence does not reach a number here. An unresolvable
    # attack and an absent body both return `_EMPTY_ATTACK_PROFILE`, whose `affordable` is False —
    # and `attack_ev_legs` FILTERS on that, so an unreadable attack produces no leg rather than a
    # zero-valued one. The candidate disappears instead of competing at 0, which is the strongest
    # fail-closed shape available to a query that answers in facts.
    "model.attack_profile",
})

#: The three reads whose ABSENT value is INDISTINGUISHABLE from a measured zero, and how each one
#: reaches `state_value`. A ruling, not an accident — pinning them is what makes "fixing" one a
#: decision rather than a tidy-up. See group A's collapse tests.
#:
#: **Only the first is a DIRECT query.** `hand_size` and `deck_count` are absent from
#: :data:`CONSUMED` because `state_value` never names them; they arrive inside the Damage Formula
#: context, gathered by `_SideBase.damage_facts` and consumed as scaler countables — which is what
#: `state_value.py:608` means by *"clocks now read `theirs.hand_size` through the Damage Formula"*.
#: Indirect is not exempt: a collapsed count still scales an attack's damage.
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
    """**The gap this issue names first.** Per-field semantics tests exist (`test_state_model.py`,
    `test_turns_to_afford.py`, `test_deny_relevance_consumer.py`); nothing enumerated the SET, so a
    query could join `state_value` without anyone asking what it returns when the fact is ABSENT.

    A new name here is not a failure — it is a prompt. Add it to :data:`CONSUMED` once you have
    answered that question for it, and to :data:`RULED_COLLAPSES` if the answer is *"absence and
    zero arrive as the same value."*"""
    censused = _model_queries(STATE_VALUE_SRC.read_text(encoding="utf-8"))

    assert censused == CONSUMED, (
        "the queries `state_value` makes have moved:\n"
        f"  NEW (unreviewed — what does this return when the fact is ABSENT?): "
        f"{sorted(censused - CONSUMED)}\n"
        f"  GONE (drop it from CONSUMED): {sorted(CONSUMED - censused)}")


@pytest.mark.req("REQ-VALUESTACK-0001")
def test_the_census_cannot_see_a_query_that_is_only_PROSE():
    """**The control for the census, and a live correction it already made.**

    `state_value.py:821` contains the text ``mine.active.grant`` — inside a `blind_to` string, in a
    sentence saying that grant is NOT carried. A naive grep reads that as a read (this issue's own
    spec listed `active.grant` among the queries for exactly that reason); the AST cannot, because a
    string literal has no `Attribute` node. Proven both directions on synthetic source, so the
    instrument is shown working rather than assumed to be.
    """
    assert _model_queries("x = model.thing.here\n") == {"model.thing"}, "the instrument is dead"
    assert _model_queries('BLURB = "model.thing.here is not read"\n') == set()
    assert "model.mine.active.grant" not in CONSUMED, "the prose read got into the reviewed list"
    assert "mine.active.grant" in STATE_VALUE_SRC.read_text(encoding="utf-8"), \
        "the `blind_to` prose that motivates this control is gone — re-point it at another string, "\
        "or the control no longer proves the census can be fooled by one"


@pytest.mark.req("REQ-VALUESTACK-0002")
def test_the_three_ABSENT_as_ZERO_collapses_are_RULED_and_stay_collapsed():
    """The ADR-0093 shape, on the StateModel side: a fact whose ABSENCE arrives as a number that
    reads like a measurement. Three survive across everything `state_value` consumes, one reached
    directly and two through the Damage Formula context — see :data:`RULED_COLLAPSES` for the routes,
    which is a distinction this issue's spec did not draw and the census forced.

    Asserted by BUILDING both boards — one that states the fact as zero/empty, one that omits the key
    entirely — and requiring the model to answer identically. That is the collapse, made executable.
    A future change that teaches any of these to distinguish the two will fail here, which is the
    point: `state_value._predicted_loss` reads `opp_prizes_remaining` as a win-condition test and
    treats 0 as falsy *deliberately* (`state_value.py:1038`), so the distinction returning is a
    behaviour change at a terminal rung, not a bug fix.
    """
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
    """The positive control for the whole ABSENT-vs-ZERO group, and the proof the distinction is not
    merely unaffordable: the model already draws it — for the clock's *policy ARGUMENT*.

    `_THREADED` (`state_model.py:82`) exists so that ``charged=None`` passed explicitly can mean the
    worst-case CEILING, a real policy, distinct from *"the caller said nothing"* which takes the
    budget threaded at build (`_charged_policy`, `:1535`). Return VALUES have no such sentinel, which
    is the asymmetry :data:`RULED_COLLAPSES` records.
    """
    from common.state_model import _THREADED, TheirSide

    threaded = TheirSide.__new__(TheirSide)
    threaded._charged = {"sentinel": 1}

    assert threaded._charged_policy(_THREADED) == {"sentinel": 1}, "unset takes the threaded budget"
    assert threaded._charged_policy(None) is None, "an explicit None is the CEILING, not 'unset'"
    assert _THREADED is not None, "the sentinel collapsed onto None — the distinction is gone"


# ══ B — threading equivalence, and the `_predicted_loss` port ═════════════════════════════════════

@pytest.fixture(scope="module")
def live_models():
    """``[(key, pilot, model, obs)]`` for a sample of corpus frames driven through the PRODUCTION
    path.

    `_board()` and not `_leaf_state_model()`, deliberately: the live path is the ONLY one that
    threads `charged`/`forward_ids` into `StateModel.build` (`pilot.py:7112`), so it is the only
    place a threading-equivalence assertion can be non-vacuous. What the leaf path threads instead is
    its own test, immediately below.
    """
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
    """`state_value.py:964` calls `theirs.turns_to_ko_me(...)` with **no `charged=`**, so it silently
    takes `TheirSide._charged` — the budget threaded at build. #260's migration is only honest if
    that route answers what the bypass beside it answered; #260's own suite covers `incoming`/
    `doomed` (`test_doom_pair_fold.py:142`) and not this.

    The control is the assertion's other half: dropping the policy to the explicit `None` ceiling
    must MOVE the read on at least one real frame. Without it the equality could hold because the
    policy never mattered, and the test would be reporting nothing.
    """
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
    """The sibling read (`state_value.py:1021`), and the harder one: it threads `charged` AND
    `forward_ids`, and a route that quietly dropped either would read a strictly narrower board while
    still returning an int. Same control, over both parameters at once."""
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
    """**A finding, recorded as a test so it cannot quietly change.**

    The two assertions above run on the live `_board()` model because that is where the threading
    exists. The board `state_value` is really called on is a different one: the planner's leaf builds
    its snapshot at `planner.py:3405` and passes **no `forward_ids` and no `charged`**. So on the leaf
    path both fall to `None` — for `charged` that is `_charged_policy`'s worst-case CEILING, the
    conservative direction a survival read must fail in, and for `forward_ids` it is `CombatMath`'s
    own default index.

    That is not a defect and this test does not call it one: the leaf scores a SIMULATED board, and
    the Read-derived per-decision budget belongs to the decision, not to a board that does not exist
    yet — the same reasoning `_leaf_state_model`'s docstring gives for withholding the turn-boost
    tracker. It is recorded because "the threading is tested" and "the threading is live where
    `state_value` runs" are different claims, and only the first is true.
    """
    def _sole_build(path: Path):
        """The ONE `StateModel.build(...)` in a module, as keyword names. Sole by assertion, not by
        `next()`: a second site would make "the live path threads X" a claim about whichever call the
        walker reached first, which is not a claim at all."""
        sites = [n for n in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                 if isinstance(n, ast.Call) and ast.unparse(n.func) == "StateModel.build"]
        assert len(sites) == 1, f"{path.name} now builds a StateModel in {len(sites)} places"
        return {k.arg for k in sites[0].keywords}

    assert {"forward_ids", "charged"} <= _sole_build(PILOT_SRC), (
        "the LIVE path stopped threading the clock parameters — the two equivalence tests above "
        "have gone vacuous and must be re-pointed, not deleted")

    leaf_kwargs = _sole_build(REPO / "src" / "common" / "strategy" / "planner.py")
    assert not ({"forward_ids", "charged"} & leaf_kwargs), (
        "the LEAF path now threads a clock parameter. That is a scoring change at every `survival` "
        "read, not a refactor — rule it, then update this test's finding.")


@pytest.mark.req("REQ-VALUESTACK-0004")
def test_predicted_loss_makes_the_SAME_clock_call_as_the_incumbent_it_ports(live_models):
    """**The named acceptance case** — the divergence this issue was written to find, resolved.

    `state_value._predicted_loss` claims in its own docstring (`state_value.py:1005-1010`) to be a
    port of `planner.Planner._predicted_loss` (`planner.py:3210`), *"the incumbent's rather than a
    fresh judgement"*. The two call sites do not LOOK the same, and it moves a terminal `−KO_SCORE`
    rung, so the resemblance was worth measuring rather than trusting. Three differences, each
    resolved:

    * **`context=`.** `state_value` passes `model.damage_context(attacker="theirs")`; the planner
      passes `self._opp_attack_context`. Already pinned key-for-key on corpus frames by
      `tests/strategy/test_damage_context.py:329` — the same dict, from the same one builder.
    * **`bodies=`.** The planner names the SIMULATED end board's opponent side explicitly because its
      `_state_model` describes the LIVE board; `state_value`'s model IS the board being scored, so
      the default (`TheirSide._bodies(None)` -> `body_raws`) already IS that list. Equivalent by
      construction — and asserted below rather than argued, because "by construction" is what the
      seam this issue guards has repeatedly turned out not to be.
    * **the `my_body` shape.** The planner passes a synthetic ``{"id", "hp"}`` projection;
      `state_value` passes the whole `BodyView.body`. Measured identical on every frame here.

    **Verdict: they AGREE.** The docstring's claim holds, so this pins the equivalence rather than
    recording a mismatch. The control below is what makes that a result: an emptied opponent board
    must move the read, or "equal" would only mean "both blind".
    """
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
    """``(report, rows)`` from `tools/train/value_lab.py` over the corpus sample.

    Issue #262's named acceptance instrument (*"a scoring harness (tools/train) dumps per-term
    workings"*) shipped with **zero** test coverage while every sibling lab had a dedicated module.
    An untested harness that reports coverage is precisely the shape that goes vacuous in silence —
    the failure `docs/ci.md` describes killing the old Decision Gate."""
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
    """T3's first acceptance line, executable: *"`state_value` scores every replayable corpus frame
    without error"*. A scalar that raises on 3% of real boards is not a scalar, and under Issue #263's
    1-ply ordering it is called once per candidate option per decision, so a raise is a forfeited
    grader match rather than a logged warning.

    Failures are NAMED, never counted — `score_frame` captures the exception precisely so the report
    can say which frame, and a test that asserted `failed == 0` without printing the keys would throw
    that away."""
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


#: Families RULED to read exactly 0.0 on every board of the corpus sample, with the ruling. **Empty,
#: and it must stay hard to add to**: an entry here retires a term's whole contribution from the
#: scalar, which is a decision about what the agent values — not a test-maintenance step.
RULED_ALWAYS_ZERO: dict[str, str] = {}


@pytest.mark.req("REQ-VALUESTACK-0005")
def test_no_family_is_SILENTLY_zero_across_the_whole_corpus_sample(value_lab_rows):
    """The issue's *"no silent zeros"* clause — and it **cannot** be asserted per frame.

    A per-frame `!= 0` would be wrong twice over. `prize_race` reads 0.0 on 28 of these 40 boards and
    `threat` on 29, correctly: a term that prices a fact the board does not carry SHOULD read zero.
    And on the LEAF path `hand` reads a structural 0.0 on every turn-passed simulated board —
    measured 22-for-22 and **developer-ruled 2026-08-02 to stand** (Issue #331). A flat per-frame
    assertion would go red on a ruled omission and get "fixed" by weakening it, which is how a test
    stops meaning anything.

    So the clause becomes a per-FAMILY one: a term that reads exactly 0.0 on **every** board in the
    sample is dead, and dead is the coverage drift this issue exists for — a term reading a field the
    model never fills looks exactly like a term whose fact is simply absent, one board at a time.

    **Why there is no blind-spot exemption here**, though `blind_spots()` is the registry channel for
    declared blindness. Its entries are *dimensions*, not families, and all six families declare at
    least one — so excusing any family that appears in it excuses all six, and the test passes
    unconditionally. Confirmed by mutation: stubbing `survival` to `return 0.0` left an exemption
    version of this test GREEN. `blind_spots()` is therefore where a ruling gets RECORDED and
    :data:`RULED_ALWAYS_ZERO` is where it gets honoured — an empty dict today, so nothing is excused.

    This sample is LIVE corpus observations, where the Issue #331 `hand` zero does not arise (it is a
    property of a board whose turn has passed, not of the term); the assertion below on `hand`
    specifically is what keeps the two propositions from being confused.
    """
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
    """The harness's other job. `value_lab_report` reports the P95 alongside the median because the
    composer calls `state_value` once per candidate option per decision, so the TAIL is what decides
    whether a wide menu fits the 2-vCPU grader budget. A report whose aggregate went None or NaN
    while the rows stayed fine would mislead exactly the sizing decision it exists to inform."""
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
    """Item 5 as this issue words it — *"no `Board`/StateModel field consumed by `state_value` uses a
    non-Optional numeric default"* — describes an **empty intersection**, and a test written to the
    letter would pass by saying nothing.

    `state_value` takes a StateModel and reads nothing else; that is the sole-supplier ruling, and it
    means it touches no `Board` field at all. Measured here rather than asserted, because the whole
    re-pointing rests on it. The four occurrences of the word are prose: a comment about *Board
    facts*, a reference to the *Board-signal map*, and two docstrings.
    """
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
    pilot_tree = ast.parse(PILOT_SRC.read_text(encoding="utf-8"))
    assert any(isinstance(n, ast.Name) and n.id == "Board" for n in ast.walk(pilot_tree))


#: ``(enclosing function, field) -> why ABSENT is unreachable`` for a `Board(...)` construction site
#: allowed to leave a numeric field on its dataclass default. Keyed by function and not by line, so
#: an unrelated edit above cannot silently retire an entry — the same key
#: `test_combat_bypass_census.DELIBERATE` uses, for the same reason.
#:
#: **Empty, and that is the finding**: measured 2026-08-03, `pilot.py` builds a `Board` in exactly
#: ONE place and passes all 23 numeric non-Optional fields explicitly, so no default is ever read as
#: a measurement. An entry here is a decision.
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
    """**ADR-0093's defect class, made structurally impossible** — the same instrument and the same
    discipline as `test_combat_bypass_census.py`, which is why the issue grouped the two.

    The defect was not that `deny_relevance_best: float = 0.0` was a bad default. It was that the
    default was READ — mid-sim absence was routine, nobody set the field, and 0.0 came back looking
    like a measured whiff, so the fire rung declined strips worth +22.50 and +74.50. ADR-0093 fixed
    that one field by making it Optional. The generalisation is cheaper and covers the other 22: if
    every numeric field is EXPLICITLY passed everywhere a `Board` is built, no default can be read as
    a measurement, whatever its type.

    A new numeric field wired into the dataclass but not into `_board()` fails here, at the moment it
    is added, rather than as a silently wrong decision several tracks later.
    """
    source = PILOT_SRC.read_text(encoding="utf-8")
    numeric, _optional = _annotated_numeric(source, "Board")
    assert len(numeric) >= 20, f"the Board census found only {len(numeric)} numeric fields"

    sites = _construction_sites(source, "Board")
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
    """ADR-0093's own fix, pinned. `deny_relevance_best` is `float | None = None` because *"`None`
    means ABSENT, not zero"* — Issue #228 measured that a `0.0` there was indistinguishable from a
    measured whiff. A field that gains an `| None` annotation and keeps a numeric default has the
    worst of both: the type says absence is expressible, the default guarantees it never is."""
    _numeric, optional = _annotated_numeric(PILOT_SRC.read_text(encoding="utf-8"), "Board")
    assert ("deny_relevance_best", "None") in optional, \
        "ADR-0093's own field is no longer Optional-with-a-None-default"

    numeric_defaulted = [(field, default) for field, default in optional if default != "None"]
    assert not numeric_defaulted, (
        "an Optional-numeric `Board` field defaults to a NUMBER, so ABSENT can never be observed "
        f"even though the type says it can: {numeric_defaulted}")


@pytest.mark.req("REQ-VALUESTACK-0006")
def test_the_StateModel_numeric_defaults_are_the_two_RULED_collapses():
    """The small StateModel surface the same defect class reaches: `CountTriple` (4 numeric zeros)
    and `PrizeRace` (2). Both collapse ABSENT onto zero, and both are ruled — differently.

    * `PrizeRace` is built in ONE place and both fields are always passed
      (`state_model.py`), so nothing reads its defaults. The collapse is one level down, in
      `prizes_remaining`, and :func:`test_the_three_ABSENT_as_ZERO_collapses_are_RULED_and_stay_
      collapsed` pins it.
    * `CountTriple()` bare IS constructed — *"unreadable inputs claim nothing (fail-closed)"* — so
      here ABSENT genuinely arrives as the all-zero triple. That is the SAFE direction by
      construction: `possible` is `ceiling > 0`, so an unreadable input answers "not possible" to a
      presence gate rather than claiming a card is there.
    """
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
    """Scope item 4 — *"pin the bypass census as an executable test"* — **was already built**, by
    #260 itself, in `tests/strategy/test_combat_bypass_census.py`. The prediction being right is the
    finding, so it is recorded with a pointer rather than silently dropped or duplicated.

    What is asserted is the module's CONTENT, not its existence: a file that exists proves nothing
    about what it enforces, and a pointer test that checked only the path would keep passing after
    the census was gutted. So this imports it, requires a populated `MODEL_COVERED`/`DELIBERATE`, and
    requires its AST walker to still find call sites — the three things that make it a census.

    What is deliberately NOT asserted is the census VERDICT. That module owns it; re-asserting it
    here would be a second copy of one ruling, which is the drift both files exist to prevent.
    """
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
