"""GATE 0 — does exhaustive within-turn search + the readiness leaf beat the 1-ply rung?

Apples-to-apples, per first-action option (chance/refresh first-actions excluded from BOTH columns). BOTH
columns grade the SAME turn_value = readiness(end) + Σ ability-fire credits − Σ spend costs (the readiness
leaf + the line account) — only the SEARCH differs:
  1-ply       : greedy continuation to end-of-turn, scored by `_engine_leaf_value` (spend_account on) — the rung.
  exhaustive  : MAX turn_value over ALL deterministic continuations (memoized best-value DP; cgpy clone-per-
                step; hand-shuffle-DRAW = chance horizon). The line account folds in as a per-edge term —
                `best(state) = max_step[line(step) + best(child)]`, terminal = readiness — sound to memoize
                by state since a step's line cost depends only on that state's chosen options, not the path.
Verdict per column = the honest SOLE-top (correct is the SOLE max) + shared-top + top-tie, vs the human pick.
(Historical note: on the pre-readiness `_board_development` leaf this A/B was a wash — deeper search over a
coarse leaf found as many leaf-mistakes as it fixed. The readiness leaf is what the search needed to pay.)

    python tools/train/probes/gate0_ab.py            # smoke: 1 frame
    python tools/train/probes/gate0_ab.py --all
"""
from __future__ import annotations
import argparse, sys, time
from dataclasses import asdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]   # tools/train/probes/x.py -> repo root
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]
from train.leaf_lab import _cgpy_pilot_builder, _PLACEHOLDER_SBI    # noqa: E402
from train.blunder.store import load_corrections                    # noqa: E402
from common.strategy.context import KO_SCORE                         # noqa: E402
from common.state_value import WIN_PRIZES                            # noqa: E402
from common.strategy.planner import _prune_none                      # noqa: E402
from common.strategy.refresh import refresh_branches                 # noqa: E402

CAP = 12000
NEG = float("-inf")


def frames(sub="lucario"):
    return [c for c in load_corrections(REPO / "data" / "corrections", dedup=False)
            if sub in (c.agent or "") and c.obs and c.correct
            and (c.obs.get("select") or {}).get("context") == 0]


def verdict(values, correct):
    scored = [v for v in values if v is not None]
    cvals = [values[i] for i in correct if 0 <= i < len(values) and values[i] is not None]
    if not scored or not cvals:
        return None
    top, best = max(scored), max(cvals)
    tie = sum(1 for v in scored if v == top)
    return {"is_top": best >= top, "unique_top": best >= top and tie == 1, "tie": tie,
            "rank": sum(1 for v in scored if v > best) + 1, "n": len(scored)}


def exhaustive_values(pilot, c):
    """best_value[i] = max leaf reachable starting with first-action i (None for a chance first-action).
    Returns (values, capped)."""
    cgapi = pilot._search_api
    obs = {**c.obs, "search_begin_input": c.obs.get("search_begin_input") or _PLACEHOLDER_SBI}
    cur = obs.get("current") or {}
    mi = cur.get("yourIndex", 0)
    pls = cur.get("players") or []
    me0 = pls[mi] if 0 <= mi < len(pls) and pls[mi] else {}
    opp0 = pls[1 - mi] if 0 <= 1 - mi < len(pls) and pls[1 - mi] else {}
    start_prizes = len(me0.get("prize") or [])
    opp_prizes = len(opp0.get("prize") or [])
    yd, yp, od, op_, oh = pilot._seed_zones(obs, me0, opp0)

    def leaf_val(o):
        pl = (o.get("current") or {}).get("players") or []
        m = pl[mi] if 0 <= mi < len(pl) and pl[mi] else {}
        res = (o.get("current") or {}).get("result", -1)
        if res == mi:
            # IMPORTED, not re-derived (Issue #362): the shipped short-circuit's magnitude moved from
            # `KO_SCORE * (start_prizes + 1)` to the derived `WIN_PRIZES` band, and a probe carrying
            # its own copy of a constant is exactly the drift ADR-0087 charges for. NOTE the honest
            # limit of that: this probe's NON-win branch is still the RETIRED hand-composed
            # `_leaf_value`, so both its columns have graded a leaf the agent stopped using at the
            # POC-T3 swap (Issue #262). Only the win magnitude is current.
            return KO_SCORE * WIN_PRIZES
        taken = max(0, start_prizes - len(m.get("prize") or []))
        act = next((p for p in (m.get("active") or []) if p), None)
        surv = False
        if act and act.get("hp"):
            o2 = pl[1 - mi] if 0 <= 1 - mi < len(pl) and pl[1 - mi] else {}
            surv = pilot._incoming_worst(act.get("id"), act.get("hp", 0),
                                         (o2.get("active") or []) + (o2.get("bench") or [])) < act.get("hp", 0)
        return pilot._leaf_value(prizes=taken, active_survives=surv,
                                 readiness=pilot._readiness(m), value=0.0)

    def is_terminal(o):
        cc = o.get("current") or {}
        return (not o.get("select")) or cc.get("result", -1) != -1 or cc.get("yourIndex") != mi

    def skey(o):
        pl = (o.get("current") or {}).get("players") or []
        m = pl[mi] if 0 <= mi < len(pl) and pl[mi] else {}
        bk = lambda p: (p.get("id"), len(p.get("energies") or []),
                        tuple(sorted(t.get("id") for t in (p.get("tools") or []) if t)))
        return ((tuple(bk(p) for p in (m.get("active") or []) if p),
                 tuple(sorted(bk(p) for p in (m.get("bench") or []) if p))),
                tuple(sorted(x.get("id") for x in (m.get("hand") or []) if x)),
                tuple(sorted((op.get("type"), op.get("index")) for op in ((o.get("select") or {}).get("option") or []))))

    def child_steps(o):
        sel = o.get("select") or {}
        opts = sel.get("option") or []
        pl = (o.get("current") or {}).get("players") or []
        m = pl[mi] if 0 <= mi < len(pl) and pl[mi] else {}
        hand = m.get("hand") or []
        if sel.get("maxCount", 1) != 1:
            try:
                return [list(pilot.decide(o))]
            except Exception:
                return []
        steps = []
        for i, op in enumerate(opts):
            if op.get("type") == 7 and op.get("index") is not None and op["index"] < len(hand):
                if refresh_branches(hand[op["index"]].get("id"), len(m.get("prize") or []), opp_prizes) is not None:
                    continue
            steps.append([i])
        return steps

    memo, inprog, capped = {}, set(), [False]
    pilot._planning = True

    def line_of(o, step):
        """The signed line account (`turn_value`'s path term) of taking `step` at node `o` — the ACTION's
        ability-fire credit / spend cost off `o`'s own option traces. Folded into the DP as a per-edge
        term: `bestleaf(state) = max_step [line(step) + bestleaf(child)]`, terminal = readiness. Sound to
        memoize by state — a step's line cost depends ONLY on that state's chosen options, not the path."""
        try:
            return pilot._line_account(pilot._evaluate(o).options, step)
        except Exception:
            return 0.0

    def bestleaf(sid, o):
        if is_terminal(o):
            return leaf_val(o)
        k = skey(o)
        if k in memo:
            return memo[k]
        if k in inprog or len(memo) >= CAP:
            capped[0] = capped[0] or len(memo) >= CAP
            return NEG
        inprog.add(k)
        best = NEG
        for step in child_steps(o):
            ch = cgapi.search_step(sid, step)
            v = line_of(o, step) + bestleaf(ch.searchId, _prune_none(asdict(ch.observation)))
            cgapi.search_release(ch.searchId)
            if v > best:
                best = v
        inprog.discard(k)
        memo[k] = best
        return best

    st = cgapi.search_begin(cgapi.to_observation_class(obs), yd, yp, od, op_, oh, [], manual_coin=False)
    root = _prune_none(asdict(st.observation))
    opts = (root.get("select") or {}).get("option") or []
    hand0 = me0.get("hand") or []
    values = [None] * len(opts)
    try:
        for i, op in enumerate(opts):
            if op.get("type") == 7 and op.get("index") is not None and op["index"] < len(hand0):
                if refresh_branches(hand0[op["index"]].get("id"), start_prizes, opp_prizes) is not None:
                    continue                                    # chance first-action — excluded
            ch = cgapi.search_step(st.searchId, [i])
            values[i] = line_of(root, [i]) + bestleaf(ch.searchId, _prune_none(asdict(ch.observation)))
            cgapi.search_release(ch.searchId)
    finally:
        cgapi.search_end()
        pilot._planning = False
    return values, capped[0], len(memo)


def oneply_values(pilot, c):
    """1-ply rung value per option = greedy continuation leaf; None for a chance/refresh first-action
    (excluded, to match the exhaustive column)."""
    obs = {**c.obs, "search_begin_input": c.obs.get("search_begin_input") or _PLACEHOLDER_SBI}
    cur = obs.get("current") or {}
    mi = cur.get("yourIndex", 0)
    pls = cur.get("players") or []
    me0 = pls[mi] if 0 <= mi < len(pls) and pls[mi] else {}
    opp_prizes = len(pls[1 - mi].get("prize") or []) if len(pls) > 1 and pls[1 - mi] else 0
    hand0 = me0.get("hand") or []
    opts = (obs.get("select") or {}).get("option") or []
    out = [None] * len(opts)
    for i, op in enumerate(opts):
        if op.get("type") == 7 and op.get("index") is not None and op["index"] < len(hand0):
            if refresh_branches(hand0[op["index"]].get("id"), len(me0.get("prize") or []), opp_prizes) is not None:
                continue
        pilot._planning = True
        try:
            # full turn_value (spend_account=True): readiness(end) + the greedy line's line account, so both
            # columns grade the SAME turn_value (`readiness + Σ ability-fire − Σ spend`) — apples-to-apples,
            # only the SEARCH differs (greedy continuation here vs the best-completion DP in exhaustive).
            out[i] = pilot._engine_leaf_value(obs, [i], spend_account=True)
        except Exception:
            out[i] = None
        finally:
            pilot._planning = False
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    build = _cgpy_pilot_builder()
    fr = frames()
    if not args.all:
        fr = fr[:1]
    agg = {"1ply": {"sole": 0, "shared": 0, "tie": 0, "n": 0},
           "exhaustive": {"sole": 0, "shared": 0, "tie": 0, "n": 0}}
    print(f"{len(fr)} frames\n")
    hd = f"{'episode':10}{'correct':8}{'1ply':>22}{'exhaustive':>24}{'cap':>5}{'states':>8}{'sec':>7}"
    print(hd); print("-" * len(hd))
    for c in fr:
        pilot = build(c.agent)
        if pilot is None:
            continue
        t0 = time.perf_counter()
        one = oneply_values(pilot, c)
        ev, capped, nstates = exhaustive_values(pilot, c)
        sec = time.perf_counter() - t0
        v1, ve = verdict(one, c.correct), verdict(ev, c.correct)

        def cell(v):
            if v is None:
                return "unscorable"
            return f"{'SOLE' if v['unique_top'] else ('shr' if v['is_top'] else 'MISS')} r{v['rank']}/{v['n']} t{v['tie']}"
        for name, v in (("1ply", v1), ("exhaustive", ve)):
            if v:
                a = agg[name]; a["n"] += 1
                a["sole"] += v["unique_top"]; a["shared"] += v["is_top"]; a["tie"] += v["tie"]
        print(f"{str(c.episode_id):10}{str(c.correct):8}{cell(v1):>22}{cell(ve):>24}"
              f"{('Y' if capped else ''):>5}{nstates:>8}{sec:>7.1f}")
    print("\n=== aggregate (honest SOLE-top) ===")
    for name in ("1ply", "exhaustive"):
        a = agg[name]
        n = a["n"] or 1
        print(f"  {name:11} SOLE-top {a['sole']:2}/{a['n']:2} ({a['sole']/n:.0%})   "
              f"shared-top {a['shared']:2}/{a['n']:2} ({a['shared']/n:.0%})   avg-tie {a['tie']/n:.2f}")


if __name__ == "__main__":
    main()
