"""THE CRUX PROBE (ply-1 grill spec): under full within-MY-turn search, how many genuinely DISTINCT
end-of-turn boards / leaf values are reachable per turn? High distinct => exhaustive search breaks the
greedy-manufactured ties (premise holds). Mostly-transpositions => the ties are real equivalences =>
we need depth, not within-turn search (premise flips).

Walk the tree of MY deterministic legal moves via cgpy (transposition table keyed on board+hand+option-
signature; hand-shuffle-DRAW cards = chance HORIZON, skipped; searches are decisions, explored). Record
every reachable end-of-turn board's leaf value. Budget-capped; a capped frame = "diverges a lot".

    python tools/train/probes/transposition_probe.py            # smoke: one frame
    python tools/train/probes/transposition_probe.py --all       # all 37
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

CAP = 4000            # max distinct non-terminal states explored per frame before we call it "diverges"


def develop_frames(sub="lucario"):
    return [c for c in load_corrections(REPO / "data" / "corrections", dedup=False)
            if sub in (c.agent or "") and c.obs and c.correct
            and (c.obs.get("select") or {}).get("context") == 0]


def _bodykey(p):
    return (p.get("id"), len(p.get("energies") or []),
            tuple(sorted((t.get("id") for t in (p.get("tools") or []) if t))))


def board_key(me):
    return (tuple(_bodykey(p) for p in (me.get("active") or []) if p),
            tuple(sorted(_bodykey(p) for p in (me.get("bench") or []) if p)),
            len(me.get("prize") or []), me.get("handCount"))


def state_key(obs, mi):
    players = (obs.get("current") or {}).get("players") or []
    me = players[mi] if 0 <= mi < len(players) and players[mi] else {}
    hand = tuple(sorted((c.get("id") for c in (me.get("hand") or []) if c)))
    opts = tuple(sorted((o.get("type"), o.get("index")) for o in ((obs.get("select") or {}).get("option") or [])))
    return (board_key(me), hand, opts)


def probe_frame(pilot, c):
    cgapi = pilot._search_api
    obs = {**c.obs, "search_begin_input": c.obs.get("search_begin_input") or _PLACEHOLDER_SBI}
    cur = obs.get("current") or {}
    mi = cur.get("yourIndex", 0)
    players = cur.get("players") or []
    me = players[mi] if 0 <= mi < len(players) and players[mi] else {}
    opp = players[1 - mi] if 0 <= 1 - mi < len(players) and players[1 - mi] else {}
    start_prizes = len(me.get("prize") or [])
    opp_prizes = len(opp.get("prize") or [])
    yd, yp, od, op_, oh = pilot._seed_zones(obs, me, opp)

    def begin_replay(prefix):                              # prefix = list of STEPS, each step a list[int]
        ob = cgapi.to_observation_class(obs)
        st = cgapi.search_begin(ob, yd, yp, od, op_, oh, [], manual_coin=False)
        for step in prefix:
            st = cgapi.search_step(st.searchId, step)
        o = _prune_none(asdict(st.observation))
        res = st.observation.current.result if st.observation.current else None
        cgapi.search_end()
        return o, res

    def leaf_of(end_obs, res):
        pl = (end_obs.get("current") or {}).get("players") or []
        m = pl[mi] if 0 <= mi < len(pl) and pl[mi] else {}
        if res == mi:
            # IMPORTED, not re-derived (Issue #362): the win short-circuit is the derived
            # `WIN_PRIZES` band, while the non-win branch below is still the retired `_leaf_value`.
            return KO_SCORE * WIN_PRIZES, ("WIN",)
        taken = max(0, start_prizes - len(m.get("prize") or []))
        act = next((p for p in (m.get("active") or []) if p), None)
        surv = False
        if act and act.get("hp"):
            o2 = pl[1 - mi] if 0 <= 1 - mi < len(pl) and pl[1 - mi] else {}
            bodies = (o2.get("active") or []) + (o2.get("bench") or [])
            surv = pilot._incoming_worst(act.get("id"), act.get("hp", 0), bodies) < act.get("hp", 0)
        val = pilot._leaf_value(prizes=taken, active_survives=surv,
                                development=pilot._board_development(m), value=0.0)
        return val, board_key(m)

    visited = set()
    end_vals = {}          # end_board_key -> leaf value
    stats = {"nodes": 0, "terminals": 0, "capped": False, "refresh_pruned": 0}
    pilot._planning = True

    def dfs(prefix, node_obs):
        if stats["capped"]:
            return
        k = state_key(node_obs, mi)
        if k in visited:
            return
        if len(visited) >= CAP:
            stats["capped"] = True
            return
        visited.add(k)
        stats["nodes"] += 1
        sel = node_obs.get("select") or {}
        opts = sel.get("option") or []
        players = (node_obs.get("current") or {}).get("players") or []
        node_me = players[mi] if 0 <= mi < len(players) and players[mi] else {}
        hand = node_me.get("hand") or []
        # branch only on single-pick selects (the "which action/card" decisions); greedy-resolve a
        # multi-pick sub-select (discard-N, choose-targets) via decide — one continuation, no branch.
        if sel.get("maxCount", 1) == 1:
            steps = []
            for i, o in enumerate(opts):
                if o.get("type") == 7 and o.get("index") is not None and o["index"] < len(hand):
                    cid = hand[o["index"]].get("id")
                    if refresh_branches(cid, len(node_me.get("prize") or []), opp_prizes) is not None:
                        stats["refresh_pruned"] += 1
                        continue                                # chance horizon — do not expand
                steps.append([i])
        else:
            try:
                steps = [list(pilot.decide(node_obs))]
            except Exception:
                steps = []
        for step in steps:
            child, res = begin_replay(prefix + [step])
            ccur = child.get("current") or {}
            terminal = (not child.get("select")) or ccur.get("result", -1) != -1 or ccur.get("yourIndex") != mi
            if terminal:
                stats["terminals"] += 1
                v, ek = leaf_of(child, res)
                end_vals[ek] = v
            else:
                dfs(prefix + [step], child)

    try:
        root, _ = begin_replay([])
        dfs([], root)
    finally:
        pilot._planning = False
    vals = list(end_vals.values())
    return {"episode": c.episode_id, "n_opts0": len((obs.get("select") or {}).get("option") or []),
            "nodes": stats["nodes"], "capped": stats["capped"], "terminals": stats["terminals"],
            "refresh_pruned": stats["refresh_pruned"],
            "distinct_end_boards": len(end_vals), "distinct_leaf_values": len(set(vals)),
            "value_spread": (max(vals) - min(vals)) if vals else 0.0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    build = _cgpy_pilot_builder()
    frames = develop_frames("lucario")
    if not args.all:
        frames = frames[:1]
    print(f"probing {len(frames)} frame(s), CAP={CAP}\n")
    hdr = f"{'episode':10}{'opts':>5}{'nodes':>8}{'ends':>6}{'leafvals':>9}{'spread':>9}{'capped':>8}{'sec':>7}"
    print(hdr); print("-" * len(hdr))
    rows = []
    for c in frames:
        pilot = build(c.agent)
        if pilot is None:
            continue
        t0 = time.perf_counter()
        r = probe_frame(pilot, c)
        r["sec"] = time.perf_counter() - t0
        rows.append(r)
        print(f"{str(r['episode']):10}{r['n_opts0']:>5}{r['nodes']:>8}{r['distinct_end_boards']:>6}"
              f"{r['distinct_leaf_values']:>9}{r['value_spread']:>9.0f}{str(r['capped']):>8}{r['sec']:>7.1f}")
    if rows:
        import statistics as st
        print("\n=== summary ===")
        print(f"  frames: {len(rows)}   capped: {sum(r['capped'] for r in rows)}")
        print(f"  distinct end-boards  : median {st.median(r['distinct_end_boards'] for r in rows):.0f}"
              f"  mean {st.mean(r['distinct_end_boards'] for r in rows):.1f}"
              f"  max {max(r['distinct_end_boards'] for r in rows)}")
        print(f"  distinct leaf-values : median {st.median(r['distinct_leaf_values'] for r in rows):.0f}"
              f"  mean {st.mean(r['distinct_leaf_values'] for r in rows):.1f}"
              f"  max {max(r['distinct_leaf_values'] for r in rows)}")
        print(f"  frames with <=1 distinct leaf value (leaf-blind even to full search): "
              f"{sum(r['distinct_leaf_values'] <= 1 for r in rows)}/{len(rows)}")


if __name__ == "__main__":
    main()
