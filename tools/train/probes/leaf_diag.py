"""Empirical leaf diagnostic — dump what the develop-rung leaf sees, per option, on real
correction frames. Reseeds each MAIN-select (ctx==0) frame with a non-empty `correct` via cgpy,
sims every option to end-of-turn, and decomposes the leaf value so we can design discriminating
features from actual boards rather than guesses.

    python tools/train/probes/leaf_diag.py                 # lucario develop frames w/ a correct pick
    python tools/train/probes/leaf_diag.py --agent dragapult_ex
"""
from __future__ import annotations
import argparse, csv, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]   # tools/train/probes/x.py -> repo root
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

from train.leaf_lab import _cgpy_pilot_builder, _PLACEHOLDER_SBI  # noqa: E402
from train.blunder.store import load_corrections            # noqa: E402


def card_names() -> dict:
    names = {}
    with (REPO / "data" / "EN_Card_Data.csv").open(encoding="utf-8") as f:
        r = csv.DictReader(f)
        idc, namec = r.fieldnames[0], r.fieldnames[1]
        for row in r:
            names[str(row[idc])] = row.get(namec, "")
    return names


NAMES = card_names()


def nm(cid):
    return NAMES.get(str(cid), f"#{cid}")


def scorable_develop_frames(agent_sub):
    """Turn/decision corrections at a MAIN (ctx==0) select with a non-empty `correct` + obs."""
    out = []
    for c in load_corrections(REPO / "data" / "corrections", dedup=False):
        if agent_sub not in (c.agent or ""):
            continue
        if not (c.obs and c.correct):
            continue
        sel = (c.obs.get("select") or {})
        if sel.get("context") != 0:
            continue
        out.append(c)
    return out


def board_bodies(me):
    return [p for p in ((me.get("active") or []) + (me.get("bench") or [])) if p]


def dump_frame(pilot, c):
    obs = {**c.obs, "search_begin_input": c.obs.get("search_begin_input") or _PLACEHOLDER_SBI}
    options = (obs.get("select") or {}).get("option") or []
    wincon = pilot._wincon_set()
    print(f"\n===== ep{c.episode_id} {c.scope} subj{getattr(c,'subject','')} "
          f"chosen={c.chosen} correct={c.correct} =====")
    print(f"  rationale: {c.rationale!r}")
    print(f"  wincon set ids: {sorted(wincon)}  ({', '.join(nm(x) for x in sorted(wincon))})")
    rows = []
    for i, o in enumerate(options):
        # what the option plays (hand index for type-7 plays)
        played = ""
        if o.get("type") == 7 and o.get("index") is not None:
            hand = ((obs.get("current") or {}).get("players") or [{}])
            mi = (obs.get("current") or {}).get("yourIndex", 0)
            h = (hand[mi].get("hand") if mi < len(hand) and hand[mi] else []) or []
            if o["index"] < len(h):
                played = nm(h[o["index"]].get("id"))
        pilot._planning = True
        try:
            sim = pilot._simulate_line(obs, [i])
            val = pilot._engine_leaf_value(obs, [i])
        except Exception as e:  # noqa: BLE001
            sim, val = None, f"ERR {type(e).__name__}"
        finally:
            pilot._planning = False
        if sim is None:
            rows.append((i, val, played, "NO-SIM", None))
            continue
        end, mi2, sp, result, *_rest = sim              # tail: line account (+ the engine-RNG bit)
        players = (end.get("current") or {}).get("players") or []
        me = players[mi2] if 0 <= mi2 < len(players) and players[mi2] else {}
        bodies = board_bodies(me)
        dev = pilot._board_development(me)
        prizes_taken = max(0, sp - len(me.get("prize") or []))
        bodystr = ", ".join(
            f"{nm(b.get('id'))}[E{len(b.get('energies') or [])}]"
            + ("*" if b.get("id") in wincon else "")
            for b in bodies)
        handn = me.get("handCount")
        rows.append((i, val, played, f"D={dev:.0f} prizes={prizes_taken} hc={handn} "
                     f"disc={len(me.get('discard') or [])} result={result}", bodystr))
    # rank
    scored = [(i, v) for i, v, *_ in rows if isinstance(v, (int, float))]
    scored.sort(key=lambda t: t[1], reverse=True)
    rank = {i: r + 1 for r, (i, _) in enumerate(scored)}
    top = scored[0][1] if scored else None
    for i, val, played, meta, bodystr in rows:
        tag = []
        if i in (c.chosen or []):
            tag.append("CHOSEN")
        if i in (c.correct or []):
            tag.append("CORRECT")
        r = rank.get(i)
        vs = f"{val:7.1f}" if isinstance(val, (int, float)) else f"{val:>7}"
        star = "<<<" if r == 1 else ""
        print(f"  opt{i:<2} {vs} rank{str(r):>3}/{len(scored)} {star:3} "
              f"{('play ' + played) if played else 'END/pass':28} | {meta}")
        if bodystr:
            print(f"         board: {bodystr}")
    if c.correct:
        cvals = [v for i, v, *_ in rows if i in c.correct and isinstance(v, (int, float))]
        if cvals:
            cr = min(rank[i] for i in c.correct if i in rank)
            tt = sum(1 for _, v in scored if v == top)
            print(f"  --> CORRECT ranks {cr}/{len(scored)}  (top_tie={tt}, "
                  f"correct_is_top={max(cvals) >= top})")
        else:
            print("  --> CORRECT unscorable (no sim)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", default="lucario")
    args = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    build = _cgpy_pilot_builder()
    frames = scorable_develop_frames(args.agent)
    print(f"{len(frames)} scorable develop frames for '{args.agent}'")
    for c in frames:
        pilot = build(c.agent)
        if pilot is None:
            print(f"  (skip {c.episode_id}: no pilot for {c.agent})")
            continue
        dump_frame(pilot, c)


if __name__ == "__main__":
    main()
