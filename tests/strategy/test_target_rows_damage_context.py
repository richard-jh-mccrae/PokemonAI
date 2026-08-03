"""The opponent-target ladder threads the **THEIRS-direction Damage Formula context** (Issue #343).

`Pilot._opponent_target_rows` (the gust / deny target ladder) and `Pilot._strip_delta_terms` (the
Energy-strip Δ that orders the deny target pick) were the last two production consumers of the
Incoming family that ACCEPTED a `context` and were never GIVEN one. Every context-scaled term of the
Damage Formula therefore contributed exactly 0 on THEIR attack: an opponent holding twelve cards and
one holding two produced the same `turns_to_ko_me`, so the same gust target value and the same strip
price. This is Issue #280's defect one module over — `state_value` was fixed there, `pilot` here.

**Both legs of each Δ must be threaded or neither.** `survival_shift` and `strip_shift` are
DIFFERENCES of the clock; threading one leg and not the other would difference two different
questions, which is worse than leaving both blind.

Card facts verified at source (`data/EN_Card_Data.csv`, and re-read off the live provider that
`_build_pilot` hands the Pilot — never recalled):

* **Alakazam (743, MEG 56)** — Stage 2, Previous stage **Kadabra**, HP 140, {P}, Weakness {D},
  Resistance {F}, Retreat 1. **Powerful Hand**, Cost ``{P}``, printed Damage *n/a*: *"Place 2 damage
  counters on your opponent's Active Pokémon for each card in your hand."* The provider reads that
  as ``scaleVar='atk_hand', scalePerUnit=20`` (2 counters = 20 damage) with
  ``ignoresWeakness/Resistance/Effects`` set, because counters are not damage. So this attacker's
  output is EXACTLY ``20 x their hand`` with no Weakness/Resistance leg to disentangle — which is
  what makes it the clean instrument for a context test. With no context its printed damage is
  **0**: the flat axis this issue removes.
* **Dunsparce (305, JTG 120)** — Basic, HP 70, Retreat 1; **Ram** 20. A DIFFERENT evolution line
  from Alakazam's (`forward_card_ids(305)` is `{66, 306}`, and Alakazam is neither), which is
  load-bearing: an Abra Active would carry Alakazam as its own FORWARD form, so removing the benched
  Alakazam would remove no threat and the removal Δ would be structurally 0.
* **Basic {P} Energy** is card id **5**. Energy entries in an observation are card ids.

The board below is deliberately one where the two hands DIFFER, so a `mine`-direction context is a
test FAILURE rather than a plausible-looking number (Issue #280's direction-regression discipline).
"""
from __future__ import annotations

import ast
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

ALAKAZAM, DUNSPARCE, PSYCHIC = 743, 305, 5

#: `race_ahead` / `opp_prizes_remaining` only scale `value`; every Δ asserted here is a raw clock
#: difference and is independent of the phase.
BOARD = types.SimpleNamespace(race_ahead=-1.0, opp_prizes_remaining=3)


def _pilot():
    """The agent's real engine-backed Pilot, at the shipped runtime PROFILE (`_build_pilot`), so the
    deny switches are armed exactly as they ship rather than as a hand-maintained mirror."""
    from train.tune import _build_pilot
    p = _build_pilot("mega_lucario")[0]
    p._planning = False
    return p


def _obs(their_hand: int, *, my_hp: int = 200, my_hand: int = 1) -> dict:
    """Their **Dunsparce** Active and their **Alakazam** Bench, each holding one Basic {P} — exactly
    Powerful Hand's cost, so affordability is settled and the only thing moving between boards is
    the hand.

    Their hand is a COUNT with no contents, which is the engine's own shape for a hidden zone
    (`TheirSide.hand_size` reads ``handCount``, and the opponent's ``hand`` is never populated);
    mine is a count too but a DIFFERENT one, so the two directions of the Formula's hand variable
    are distinguishable on this board by construction."""
    return {"current": {"yourIndex": 0, "players": [
        {"active": [{"id": 999999, "hp": my_hp, "energies": []}], "bench": [],
         "handCount": my_hand, "hand": []},
        {"active": [{"id": DUNSPARCE, "hp": 70, "energies": [PSYCHIC]}],
         "bench": [{"id": ALAKAZAM, "hp": 140, "energies": [PSYCHIC]}],
         "handCount": their_hand},
    ]}}


def _rows(their_hand: int, *, attacker_is_me: bool = False, **kw):
    """The ladder, with the per-decision context installed the way `_board` installs it.

    `Pilot._board` resolves `_opp_attack_context` and only then calls this ladder, so building it
    here reproduces the live sequencing without needing a full engine observation. (Stated as an
    ORDER between two named steps rather than as a line number — this issue exists because a number
    in a docstring rotted, and a line number rots faster than a count.)
    ``attacker_is_me=True`` installs the WRONG direction — the control."""
    p, obs = _pilot(), _obs(their_hand, **kw)
    p._snapshot(obs)
    p._opp_attack_context = p._damage_context(obs, attacker_is_me=attacker_is_me)
    _phase, rows = p._opponent_target_rows(obs, BOARD)
    return rows


# ── site 1: `_opponent_target_rows` — the gust target's whole score ───────────────────────────────

@pytest.mark.req("REQ-TARGETROWS-CTX-0001")
def test_the_removal_delta_follows_THEIR_hand():
    """`survival_shift` is the turns of survival bought by removing a body — the gust target's whole
    score, via `needs.opponent_target_value`. Their Active Dunsparce sets a 2-turn clock on my 200 HP
    Active (20/turn is `Ram`, but the ceiling policy credits its line's biggest reachable hit);
    removing it leaves the benched Alakazam alone, and how long THAT takes is `20 x their hand`.

    So the Δ is a ladder in their hand size, and the ladder is asserted value-by-value rather than as
    a trend — a trend alone would also pass on a term that moved for some other reason. Without the
    context Powerful Hand deals 0, the Alakazam never finishes inside the horizon, and every hand
    size answers the SAME 7: the flat axis this issue removes."""
    ladder = {1: 7, 2: 3, 3: 2, 4: 1, 6: 0}
    for hand, shift in ladder.items():
        rows = _rows(hand)
        active = next(r for r in rows if r["area"] == "active")
        assert active["survival_shift"] == shift, (
            f"their hand {hand} => Alakazam deals {20 * hand}/turn into my 200 HP, so removing "
            f"their Active buys {shift} turns")


@pytest.mark.req("REQ-TARGETROWS-CTX-0001")
def test_the_removal_delta_reads_THEIR_hand_and_never_MINE():
    """The direction regression. `atk_hand` is the ATTACKER's hand and Incoming's attacker is THEM,
    so a `mine`-direction dict prices this board backwards — and here it is worse than backwards, it
    is INDISTINGUISHABLE from the unfixed read: my hand is held at 1 on every board, so the wrong
    dict answers a flat 7 at every one of their hand sizes.

    There is no assignment of the mine-direction dict to this call site that passes the ladder
    above, which is what makes this a regression test rather than a restatement."""
    theirs = [_rows(h)[0]["survival_shift"] for h in (1, 2, 3, 4, 6)]
    mine = [_rows(h, attacker_is_me=True)[0]["survival_shift"] for h in (1, 2, 3, 4, 6)]
    assert theirs == [7, 3, 2, 1, 0]
    assert mine == [7, 7, 7, 7, 7], "the wrong direction cannot see their hand at all"


@pytest.mark.req("REQ-TARGETROWS-CTX-0001")
def test_threading_the_context_can_only_SHORTEN_a_clock():
    """A soundness property, not a value: a Damage Formula scaler only ever ADDS damage (a variable
    absent from the context contributes 0 — `strategy/damage.py`, and `SideFacts`' fail-closed
    defaults), so learning to price one can never make the opponent slower.

    Under-reading incoming damage is the one direction a survival estimate may never fail in, so
    this is asserted directly rather than inferred from the ladder — and over a range of hands and
    of my own HP, because a single board cannot distinguish "monotone" from "happened not to move".
    (Issue #343 also swept the whole corrections corpus for a counter-example and found none in 359
    frames; that measurement is recorded in the commit, not run here, because a corpus replay is not
    a unit test.)"""
    for their_hand in (1, 2, 3, 6, 12):
        for my_hp in (70, 140, 200, 340):
            p, obs = _pilot(), _obs(their_hand, my_hp=my_hp)
            p._snapshot(obs)
            model = p._state_model
            ma = obs["current"]["players"][0]["active"][0]
            theirs = obs["current"]["players"][1]
            bodies = theirs["active"] + theirs["bench"]
            clock = dict(bodies=bodies, charged=None, opp_active=bodies[0],
                         switch_enabler=p._opp_switch_enabler())
            blind = model.theirs.turns_to_ko_me(ma, **clock)
            seeing = model.theirs.turns_to_ko_me(
                ma, context=p._damage_context(obs, attacker_is_me=False), **clock)
            assert seeing <= blind, f"hand {their_hand}, my {my_hp} HP: {blind} -> {seeing}"


# ── site 2: `_strip_delta_terms` — what an Energy strip is worth ──────────────────────────────────

@pytest.mark.req("REQ-TARGETROWS-CTX-0002")
def test_the_strip_delta_follows_THEIR_hand():
    """`strip_shift` is the turns bought by discarding ONE Energy off a body that STAYS — the deny
    instrument's slice, and the lexicographic tiebreak on the target pick (ADR-0084 decision 7).

    Their benched Alakazam holds exactly one {P}, which is exactly Powerful Hand's cost, so the strip
    disarms it outright and the Δ is "how much of my remaining life was that attacker accounting
    for" — again `20 x their hand`. Without the context it accounted for NOTHING, so the strip that
    disarms their real threat prices at 0 on every board."""
    ladder = {1: 0, 2: 4, 3: 5, 4: 6, 6: 7, 12: 8}
    for hand, shift in ladder.items():
        rows = _rows(hand)
        bench = next(r for r in rows if r["area"] == "bench")
        assert bench["strip_shift"] == shift, (
            f"their hand {hand} => stripping the Alakazam's only {{P}} removes {20 * hand}/turn")


@pytest.mark.req("REQ-TARGETROWS-CTX-0002")
def test_the_strip_delta_reads_THEIR_hand_and_never_MINE():
    """The same direction control on the second site. The deny Δ runs under `_DENY_CHARGED` rather
    than the ceiling, and the policy is untouched by this issue — what changes is only which hand
    the scaler reads."""
    theirs = [_rows(h)[1]["strip_shift"] for h in (1, 2, 3, 4, 6, 12)]
    mine = [_rows(h, attacker_is_me=True)[1]["strip_shift"] for h in (1, 2, 3, 4, 6, 12)]
    assert theirs == [0, 4, 5, 6, 7, 8]
    assert mine == [0, 0, 0, 0, 0, 0], "the wrong direction prices their best threat at nothing"


@pytest.mark.req("REQ-TARGETROWS-CTX-0002")
def test_both_legs_of_each_delta_are_threaded_together():
    """The one thing to get right. Each Δ differences two clocks; if only one leg carried the
    context the subtraction would compare two different questions and could even change SIGN.

    Asserted structurally, on the source, because a value test cannot distinguish "both legs
    threaded" from "neither leg threaded" on a board where the context happens not to bite."""
    src = (REPO / "src" / "common" / "pilot.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for fname in ("_opponent_target_rows", "_strip_delta_terms"):
        fn = next(n for n in ast.walk(tree)
                  if isinstance(n, ast.FunctionDef) and n.name == fname)
        calls = [c for c in ast.walk(fn)
                 if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                 and c.func.attr == "turns_to_ko_me"]
        assert calls, f"{fname}: no clock call found — this test's instrument is broken"
        for call in calls:
            assert _threads_context(call, fn), (
                f"{fname}:{call.lineno} differences a clock leg that carries no `context`")


def _threads_context(call: ast.Call, fn: ast.FunctionDef) -> bool:
    """True when ``call`` names ``context=``, directly or through a ``**name`` splat whose local
    ``dict(...)`` binding carries the key."""
    if any(k.arg == "context" for k in call.keywords if k.arg):
        return True
    bound = {t.targets[0].id: t.value for t in ast.walk(fn)
             if isinstance(t, ast.Assign) and len(t.targets) == 1
             and isinstance(t.targets[0], ast.Name)}
    for kw in call.keywords:
        if kw.arg is not None:
            continue
        seen, todo = set(), [kw.value]
        while todo:
            node = todo.pop()
            if isinstance(node, ast.Name) and node.id in bound and node.id not in seen:
                seen.add(node.id)
                todo.append(bound[node.id])
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "dict":
                if any(k.arg == "context" for k in node.keywords if k.arg):
                    return True
                todo.extend(node.args)
    return False


# ── the census, restated as a PROPERTY (Issue #343 acceptance) ────────────────────────────────────
#
# `combat.py`'s `doomed_incoming` docstring used to assert *"all six Incoming call sites thread the
# per-decision damage context"*. A COUNT rots — it was already wrong when Issue #343 was filed, and
# `docs/plans/term-sufficiency-audit.md` F2 cites that sentence as the invariant `state_value` broke.
# The fix the issue asks for is to state the property instead of the number, and a property stated in
# a docstring rots exactly as fast, so it is asserted here.

#: Modules that CONSUME the Incoming family. `state_model.py` and `combat.py` are excluded on
#: purpose: they are the delegation layers, and they forward whatever their caller supplies
#: (`incoming(my_body, 1, **kwargs)`), so they neither thread nor drop anything themselves.
CONSUMERS = ("src/common/pilot.py", "src/common/state_value.py", "src/common/strategy/planner.py")

#: Reads that funnel into `CombatMath.incoming` and accept a `context`.
INCOMING_FAMILY = frozenset({"incoming", "reachable_incoming", "doomed", "doomed_incoming",
                             "turns_to_ko_me"})

#: ``(enclosing function, method) -> why this consumer legitimately prices no context.`` EMPTY, and
#: that is the property: every live consumer threads it. An entry here is a decision, and adding one
#: without a reason is what this allowlist exists to make impossible.
CONTEXT_FREE: dict[tuple[str, str], str] = {}


def _incoming_sites():
    """``[(module, line, enclosing function, method, threads_context)]`` over the consumers."""
    out = []
    for rel in CONSUMERS:
        tree = ast.parse((REPO / rel).read_text(encoding="utf-8"))
        owner: dict[int, ast.FunctionDef] = {}

        class V(ast.NodeVisitor):
            def visit_FunctionDef(self, node):
                for sub in ast.walk(node):
                    if hasattr(sub, "lineno"):
                        owner[sub.lineno] = node
                self.generic_visit(node)

            visit_AsyncFunctionDef = visit_FunctionDef

        V().visit(tree)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr in INCOMING_FAMILY):
                continue
            fn = owner.get(node.lineno)
            if fn is None:
                continue
            out.append((rel, node.lineno, fn.name, node.func.attr, _threads_context(node, fn)))
    return out


@pytest.mark.req("REQ-TARGETROWS-CTX-0003")
def test_every_live_Incoming_consumer_threads_the_damage_context():
    """The property the rotted census was reaching for. A consumer that drops the context is not
    conservative — it is BLIND: every Damage Formula scaler contributes 0, so a Powerful Hand at 21
    cards reads as 0 damage rather than 420."""
    blind = [(mod, line, fn, m) for mod, line, fn, m, threaded in _incoming_sites()
             if not threaded and (fn, m) not in CONTEXT_FREE]
    assert not blind, (
        "Incoming consumer that prices no damage context — thread "
        "`self._opp_attack_context` (pilot/planner) or `model.damage_context(attacker=...)` "
        "(state_value), or add it to CONTEXT_FREE with the reason:\n"
        + "\n".join(f"  {mod}:{line}  {fn}() -> {m}()" for mod, line, fn, m in blind))


@pytest.mark.req("REQ-TARGETROWS-CTX-0003")
def test_the_census_instrument_is_not_silently_empty():
    """The positive control CLAUDE.md requires of any negative result: "found nothing" and "my
    instrument is broken" produce the same empty list. A rename of the family, of a module, or of
    `context=` would quietly turn the test above into a tautology, so the sweep has to prove it can
    still see the call sites it is grading — including the ones that thread through a `**clock`
    splat rather than by name."""
    sites = _incoming_sites()
    assert len(sites) >= 15, f"the sweep found only {len(sites)} Incoming call sites"
    assert {mod for mod, *_ in sites} == set(CONSUMERS), "a consumer module went unscanned"
    assert any(fn == "_promote_body" and threaded for _m, _l, fn, _c, threaded in sites), (
        "`_promote_body` threads its context through a `**clock` splat — a sweep that cannot see "
        "that one is grading by spelling, not by behaviour")


@pytest.mark.req("REQ-TARGETROWS-CTX-0003")
def test_every_context_free_entry_gives_a_reason():
    """An empty allowlist today. If one is ever added, a one-word entry is not a ruling."""
    for key, why in CONTEXT_FREE.items():
        assert len(why) > 40, f"{key}: the reason is too thin to be a ruling"
