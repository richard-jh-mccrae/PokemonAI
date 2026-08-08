"""`_opponent_target_rows` and `_strip_delta_terms` thread the THEIRS-direction damage context (Issue #343).

Both legs of each Δ must carry `context` or neither: `survival_shift` and `strip_shift` are clock
DIFFERENCES, so threading one leg differences two different questions. Board: their Dunsparce (305)
Active and their benched Alakazam (743), each on one Basic {P} (id 5). Alakazam's Powerful Hand is
exactly ``20 x THEIR hand`` with no Weakness/Resistance leg, and my hand is held at a DIFFERENT count,
so a `mine`-direction context fails here rather than producing a plausible-looking number.
"""
from __future__ import annotations

import ast
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

ALAKAZAM, DUNSPARCE, PSYCHIC = 743, 305, 5

#: These only scale `value`; every Δ asserted here is a raw clock difference, independent of the phase.
BOARD = types.SimpleNamespace(race_ahead=-1.0, opp_prizes_remaining=3)


def _pilot():
    """At the shipped runtime PROFILE, so the deny switches are armed as they ship, not as a mirror."""
    from train.tune import _build_pilot
    p = _build_pilot("mega_lucario")[0]
    p._planning = False
    return p


def _obs(their_hand: int, *, my_hp: int = 200, my_hand: int = 1) -> dict:
    """Each body holds exactly Powerful Hand's cost, so the only thing moving between boards is the hand.
    Their hand is a bare ``handCount`` (the engine's hidden-zone shape) and mine is a DIFFERENT count."""
    return {"current": {"yourIndex": 0, "players": [
        {"active": [{"id": 999999, "hp": my_hp, "energies": []}], "bench": [],
         "handCount": my_hand, "hand": []},
        {"active": [{"id": DUNSPARCE, "hp": 70, "energies": [PSYCHIC]}],
         "bench": [{"id": ALAKAZAM, "hp": 140, "energies": [PSYCHIC]}],
         "handCount": their_hand},
    ]}}


def _rows(their_hand: int, *, attacker_is_me: bool = False, **kw):
    """`_board` resolves `_opp_attack_context` and only then calls this ladder; that order is what is
    reproduced here. ``attacker_is_me=True`` installs the WRONG direction — the control."""
    p, obs = _pilot(), _obs(their_hand, **kw)
    p._snapshot(obs)
    p._opp_attack_context = p._damage_context(obs, attacker_is_me=attacker_is_me)
    _phase, rows = p._opponent_target_rows(obs, BOARD)
    return rows


# ── site 1: `_opponent_target_rows` — the gust target's whole score ───────────────────────────────

@pytest.mark.req("REQ-TARGETROWS-CTX-0001")
def test_the_removal_delta_follows_THEIR_hand():
    """The ladder is re-derived by hand in ADR-0117: base crossing ``1 + (200-150)/150 = 4/3``, and
    removing their Active leaves ``20 x hand``/turn. Blind, every hand size answers the same value."""
    ladder = {1: 23 / 3, 2: 11 / 3, 3: 2.0, 4: 7 / 6, 6: 1 / 3}
    for hand, shift in ladder.items():
        rows = _rows(hand)
        active = next(r for r in rows if r["area"] == "active")
        assert active["survival_shift"] == pytest.approx(shift), (
            f"their hand {hand} => Alakazam deals {20 * hand}/turn into my 200 HP, so removing "
            f"their Active buys {shift:.4f} turns")


@pytest.mark.req("REQ-TARGETROWS-CTX-0001")
def test_the_removal_delta_reads_THEIR_hand_and_never_MINE():
    """`atk_hand` is the ATTACKER's hand and Incoming's attacker is THEM, so the wrong direction is
    INDISTINGUISHABLE from the unfixed read: my hand is 1 on every board, hence the flat ``9 - 4/3``."""
    theirs = [_rows(h)[0]["survival_shift"] for h in (1, 2, 3, 4, 6)]
    mine = [_rows(h, attacker_is_me=True)[0]["survival_shift"] for h in (1, 2, 3, 4, 6)]
    assert theirs == pytest.approx([23 / 3, 11 / 3, 2.0, 7 / 6, 1 / 3])
    assert mine == pytest.approx([23 / 3] * 5), "the wrong direction cannot see their hand at all"


@pytest.mark.req("REQ-TARGETROWS-CTX-0001")
def test_threading_the_context_can_only_SHORTEN_a_clock():
    """A scaler only ever ADDS damage (an absent variable contributes 0), so pricing one can never
    make the opponent slower — and under-reading incoming damage is the one direction that is unsound."""
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
    """`strip_shift` = turns bought by discarding ONE Energy off a body that STAYS; the lexicographic
    tiebreak on the deny target pick (ADR-0084 decision 7). One {P} is all Powerful Hand costs."""
    ladder = {1: 0, 2: 4, 3: 5, 4: 6, 6: 7, 12: 8}
    for hand, shift in ladder.items():
        rows = _rows(hand)
        bench = next(r for r in rows if r["area"] == "bench")
        assert bench["strip_shift"] == shift, (
            f"their hand {hand} => stripping the Alakazam's only {{P}} removes {20 * hand}/turn")


@pytest.mark.req("REQ-TARGETROWS-CTX-0002")
def test_the_strip_delta_reads_THEIR_hand_and_never_MINE():
    """The same control on the second site; this Δ runs under `_DENY_CHARGED` rather than the ceiling."""
    theirs = [_rows(h)[1]["strip_shift"] for h in (1, 2, 3, 4, 6, 12)]
    mine = [_rows(h, attacker_is_me=True)[1]["strip_shift"] for h in (1, 2, 3, 4, 6, 12)]
    assert theirs == [0, 4, 5, 6, 7, 8]
    assert mine == [0, 0, 0, 0, 0, 0], "the wrong direction prices their best threat at nothing"


@pytest.mark.req("REQ-TARGETROWS-CTX-0002")
def test_both_legs_of_each_delta_are_threaded_together():
    """Asserted on the source because a value test cannot tell both legs threaded from neither on a
    board where the context does not bite. BOTH clock names count — `survival_clock` too (ADR-0117)."""
    # Located BY NAME across the whole Pilot surface, not out of one hard-coded module.
    trees = {rel: ast.parse((REPO / rel).read_text(encoding="utf-8")) for rel in PILOT_SURFACE}
    clocks = {"turns_to_ko_me", "survival_clock"}
    for fname in ("_opponent_target_rows", "_strip_delta_terms"):
        found = [n for tree in trees.values() for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == fname]
        assert len(found) == 1, f"{fname}: found in {len(found)} modules, expected exactly 1"
        fn = found[0]
        calls = [c for c in ast.walk(fn)
                 if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                 and c.func.attr in clocks]
        assert calls, f"{fname}: no clock call found — this test's instrument is broken"
        for call in calls:
            assert _threads_context(call, fn), (
                f"{fname}:{call.lineno} differences a clock leg that carries no `context`")


def _threads_context(call: ast.Call, fn: ast.FunctionDef) -> bool:
    """True when ``call`` names ``context=``, directly or via a ``**name`` splat bound to a ``dict(...)``."""
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

#: Modules that CONSUME the Incoming family. `state_model.py` / `combat.py` are excluded: they only
#: forward their caller's kwargs. Named one by one — a glob makes the instrument test vacuous.
CONSUMERS = ("src/common/state_value.py", "src/common/strategy/planning/leaf.py",
             "src/common/deciders/board_build.py", "src/common/deciders/deny.py",
             "src/common/deciders/doom.py", "src/common/deciders/evolve.py",
             "src/common/deciders/hand.py", "src/common/deciders/heal.py",
             "src/common/deciders/lines.py", "src/common/deciders/promote.py",
             "src/common/deciders/snipe.py")

#: Reads that funnel into `CombatMath.incoming` and accept a `context`.
INCOMING_FAMILY = frozenset({"incoming", "reachable_incoming", "doomed", "doomed_incoming",
                             "turns_to_ko_me"})

#: ``(enclosing function, method) -> why this consumer legitimately prices no context.`` EMPTY, and
#: that is the property; an entry is a decision, which is why the reason is graded below.
CONTEXT_FREE: dict[tuple[str, str], str] = {}


#: Every module a `Pilot` method can live in — the scans look a method UP, not down a fixed list.
PILOT_SURFACE = ("src/common/pilot.py",
                 *sorted(q.relative_to(REPO).as_posix()
                         for q in (REPO / "src" / "common" / "deciders").glob("*.py")
                         if q.name != "__init__.py"))


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
    """A consumer that drops the context is not conservative but BLIND: every scaler contributes 0."""
    blind = [(mod, line, fn, m) for mod, line, fn, m, threaded in _incoming_sites()
             if not threaded and (fn, m) not in CONTEXT_FREE]
    assert not blind, (
        "Incoming consumer that prices no damage context — thread "
        "`self._opp_attack_context` (pilot/planner) or `model.damage_context(attacker=...)` "
        "(state_value), or add it to CONTEXT_FREE with the reason:\n"
        + "\n".join(f"  {mod}:{line}  {fn}() -> {m}()" for mod, line, fn, m in blind))


@pytest.mark.req("REQ-TARGETROWS-CTX-0003")
def test_the_census_instrument_is_not_silently_empty():
    """The positive control CLAUDE.md requires: found-nothing and instrument-broken give the same
    empty list. A rename of the family, a module or `context=` would make the test above a tautology."""
    sites = _incoming_sites()
    assert len(sites) >= 15, f"the sweep found only {len(sites)} Incoming call sites"
    assert {mod for mod, *_ in sites} == set(CONSUMERS), "a consumer module went unscanned"
    assert any(fn == "_promote_body" and threaded for _m, _l, fn, _c, threaded in sites), (
        "`_promote_body` threads its context through a `**clock` splat — a sweep that cannot see "
        "that one is grading by spelling, not by behaviour")


@pytest.mark.req("REQ-TARGETROWS-CTX-0003")
def test_every_context_free_entry_gives_a_reason():
    for key, why in CONTEXT_FREE.items():
        assert len(why) > 40, f"{key}: the reason is too thin to be a ruling"
