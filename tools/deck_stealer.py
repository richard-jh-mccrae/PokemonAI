"""Copy a team's exact 60-card deck out of a replay into a new submission dir.

Given a downloaded replay (full-information: both teams' decks live in the
agent-0-only ``visualize`` frame, see ADR-0001) and a team name, write that team's
exact decklist to ``src/agents/<name>/deck.csv``. The replay is the unit
of choice -- picking *which* replay to download is itself the disambiguation when a
team runs more than one deck (ADR-0005). Offline; no Kaggle token needed.

Usage:
    python tools/deck_stealer.py <replay.json|.json.gz> <team-name> <dir-name> [--force]
    python tools/deck_stealer.py data/replays/starmie_keidroid.json keidroid mega_starmie
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))  # make `meta_tracker` importable

from meta_tracker.parse import parse_replay  # noqa: E402

AGENTS = REPO / "src" / "agents"


class StealError(RuntimeError):
    """A steal that can't proceed (bad path, team not in replay, dir exists, ...)."""


def steal(replay: str | Path, team: str, name: str, *,
          force: bool = False, dest_root: Path = AGENTS) -> dict:
    """Write ``team``'s exact deck from ``replay`` to ``dest_root/name/deck.csv``.

    Returns a provenance dict (dest, archetype, opponent, episode_id, result). The
    deck is sorted by card id so re-stealing the same list from any replay is
    byte-identical. Raises ``StealError`` on any precondition failure.
    """
    path = Path(replay)
    if not path.exists():
        raise StealError(f"replay not found: {path}")

    rec = parse_replay(path, sampled_team=team)
    names = [rec.team0, rec.team1]
    if team not in names:
        raise StealError(f"team {team!r} not in replay; teams are {names!r}")
    idx = names.index(team)

    deck = rec.deck0 if idx == 0 else rec.deck1
    if len(deck) != 60:
        raise StealError(f"expected a 60-card deck for {team!r}, got {len(deck)}")

    dest = Path(dest_root) / name
    if dest.exists() and not force:
        raise StealError(f"{dest} already exists; pass --force to overwrite")
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "deck.csv").write_text("\n".join(str(c) for c in sorted(deck)) + "\n",
                                   encoding="utf-8")

    winner = rec.winner_index
    result = "won" if winner == idx else "lost" if winner is not None else "drew"
    return {
        "dest": dest,
        "archetype": rec.arch0 if idx == 0 else rec.arch1,
        "opponent": rec.team1 if idx == 0 else rec.team0,
        "episode_id": rec.episode_id,
        "result": result,
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("replay", help="path to a downloaded replay (.json or .json.gz)")
    ap.add_argument("team", help="exact TeamName whose deck to copy (quote if it has spaces)")
    ap.add_argument("name", help="new directory name under src/agents/")
    ap.add_argument("--force", action="store_true", help="overwrite if the dir already exists")
    args = ap.parse_args()

    try:
        p = steal(args.replay, args.team, args.name, force=args.force)
    except StealError as e:
        raise SystemExit(f"deck_stealer: {e}")

    print(f"stole {args.team}'s {p['archetype']} "
          f"(episode {p['episode_id']}, {p['result']} vs {p['opponent']}) "
          f"-> {p['dest'] / 'deck.csv'}")


if __name__ == "__main__":
    main()
