"""Cross-deck gauntlet corpus generator (grilled 2026-07-05, Tier-5 finish plan).

The seed value model was trained on a MIRROR-only self-play corpus, so favorability — the model's
matchup signal — never varied and it never learned to use it. This drives our real agents against
EACH OTHER through `battle.play_match` + `record.MatchRecorder` (process isolation dodges the
in-process two-deck `sys.modules` collision) and writes the games as cabt-`visualize` films under
``data/replays/gauntlet/`` — a corpus `tools/train/value/train.py --replays data/replays/gauntlet`
mines with no new reader. Games are seat-balanced (ADR-0021) so each deck's decisions are captured
from both the first- and second-player seat.
"""
from __future__ import annotations

import json
from pathlib import Path


def pairings(agents: list[str], *, include_mirror: bool = True) -> list[tuple[str, str]]:
    """Every unordered cross pair, plus each mirror when ``include_mirror``. Pair order is the given
    agent order; seat balancing at run time puts each deck in both engine seats regardless."""
    out: list[tuple[str, str]] = []
    for i, a in enumerate(agents):
        for b in agents[i:]:
            if a == b and not include_mirror:
                continue
            out.append((a, b))
    return out


def pair_stem(a: str, b: str, when, sha: str) -> str:
    """The corpus stem for one pairing — ``<a>__<b>_<YYYYMMDD-HHMMSS>_<sha>-gauntlet``. Distinct per
    pairing so a pairing's games file under their own folder (and never collide with a selfplay run)."""
    return f"{a}__{b}_{when:%Y%m%d-%H%M%S}_{sha}-gauntlet"


def generate_gauntlet(agents, n, *, agents_root, out_root, when, sha, extra_syspath=(),
                      include_mirror: bool = True):
    """Run ``n`` seat-balanced games per pairing, writing each clean game as a tagged replay -> the
    gauntlet root. Crashed games are SKIPPED: an unclean policy game would poison the corpus."""
    from sim.battle import AgentServer, play_match, read_deck
    from sim.record import MatchRecorder
    from sim.selfplay import episode_id

    run_root = Path(out_root) / "gauntlet"
    agents_root = Path(agents_root)
    for a, b in pairings(agents, include_mirror=include_mirror):
        stem = pair_stem(a, b, when, sha)
        run_dir = run_root / stem
        run_dir.mkdir(parents=True, exist_ok=True)
        dir_a, dir_b = agents_root / a, agents_root / b
        deck_a, deck_b = read_deck(dir_a), read_deck(dir_b)
        sa = AgentServer(dir_a, extra_syspath)
        sb = AgentServer(dir_b, extra_syspath)
        try:
            for i in range(n):
                if not sa.alive():                       # a prior crash killed the server -> respawn
                    sa = AgentServer(dir_a, extra_syspath)
                if not sb.alive():
                    sb = AgentServer(dir_b, extra_syspath)
                rec = MatchRecorder()
                if i % 2 == 0:                           # deck a in engine seat 0
                    result = play_match(sa, sb, deck_a, deck_b, recorder=rec)
                    names = [f"{stem}#0-{a}", f"{stem}#1-{b}"]
                else:                                    # swap decks between seats (seat balance)
                    result = play_match(sb, sa, deck_b, deck_a, recorder=rec)
                    names = [f"{stem}#0-{b}", f"{stem}#1-{a}"]
                if result.crashed:                       # unclean game -> don't write it
                    continue
                eid = episode_id(stem, i)
                replay = rec.replay(episode_id=eid, team_names=names)
                (run_dir / f"{eid}.json").write_text(json.dumps(replay, ensure_ascii=False),
                                                     encoding="utf-8")
        finally:
            sa.close()
            sb.close()
    return run_root


def main(argv=None) -> int:
    import argparse
    import sys
    from datetime import datetime

    repo = Path(__file__).resolve().parents[2]
    sys.path[:0] = [str(repo / "tools"), str(repo / "src")]
    from sim.battle import _git_short

    ap = argparse.ArgumentParser(
        description="Generate the cross-deck gauntlet corpus for the Automatic Value Model (ADR-0042 "
                    "finish plan): our real agents played against each other so favorability varies.")
    ap.add_argument("agents", nargs="+", help="agents under src/agents/ to cross (e.g. mega_starmie "
                                              "mega_lucario dragapult_ex)")
    ap.add_argument("-n", "--games", type=int, default=150, help="games per pairing (default 150)")
    ap.add_argument("--no-mirror", action="store_true", help="cross pairings only (drop the mirrors)")
    ap.add_argument("--agents-root", default=str(repo / "src" / "agents"))
    ap.add_argument("--out", default=str(repo / "data" / "replays"),
                    help="corpus root (the run lands under <out>/gauntlet/<stem>/)")
    args = ap.parse_args(argv)

    run_root = generate_gauntlet(args.agents, args.games, agents_root=args.agents_root,
                                 out_root=args.out, when=datetime.now(), sha=_git_short(),
                                 include_mirror=not args.no_mirror, extra_syspath=[repo / "src"])
    saved = len(list(Path(run_root).rglob("*.json")))
    print(f"Gauntlet corpus: {saved} games across "
          f"{len(pairings(args.agents, include_mirror=not args.no_mirror))} pairings -> {run_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
