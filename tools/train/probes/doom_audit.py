"""Doom-relax replay AUDIT — ground-truth the `doom_matched_relax` boolean on fresh films.

The doom-shadow grill (2026-07-23) shipped `active_doomed`'s matched-Read RELAX-ONLY gate on a
15-frame ruling plus a wide-CI gauntlet A/B. This probe closes the loop empirically, with no human
labels and no ladder: a recorded film (gauntlet/selfplay `visualize` shape) contains what the
opponent ACTUALLY did, so for each of a seat's turns we can ask — did the body that faced the
opponent after a relaxed doom read survive their turn?

Per (game, seat): replay the seat's decision frames IN ORDER through that agent's real shipped
Pilot (ONE stateful pilot per game-seat — live-faithful, unlike the cross-game fresh-per-frame
sweeps) and read `Decision.threat_shadow`. Per turn, keep the LAST decision's shadow (the read
closest to facing the opponent), identify the body that actually started the opponent's next turn
in my Active (the film's next opposing frame), and detect death by its serial landing in my
discard by the end of their turn window (KO is the ONE common path from in-play to discard;
gust-to-bench-then-snipe and self-discard effects are accepted approximation noise, documented).

Cohorts (see `classify`): FALSE_RELAX / RELAX_OK (the relax's error/win), DOOM_HIT / DOOM_PHANTOM
(the standing doom's), SAFE_MISS / SAFE_OK (the WORST-CASE oracle's own blind spot, the baseline),
DODGED (the audited body was no longer Active when their turn began — counterfactual unobservable).

    python tools/train/probes/doom_audit.py                          # data/replays/gauntlet + selfplay
    python tools/train/probes/doom_audit.py --replays <dir> [...]    # explicit corpus roots

Offline and read-only.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(REPO / "tools"), str(REPO / "src")]

COHORTS = ("FALSE_RELAX", "RELAX_OK", "DOOM_HIT", "DOOM_PHANTOM", "SAFE_MISS", "SAFE_OK", "DODGED")


# ------------------------------------------------------------------------------ pure helpers
def seat_agent(team_name) -> str | None:
    """The agent dir name out of a recorder TeamName (`<stem>#<seat>-<agent>`); None when the
    marker is absent (a foreign film this audit cannot rebuild a Pilot for)."""
    if not team_name or "#" not in str(team_name):
        return None
    tail = str(team_name).split("#", 1)[1]                 # "<seat>-<agent>"
    if "-" not in tail:
        return None
    return tail.split("-", 1)[1] or None


def turn_player(turn: int, *, first_player: int) -> int:
    """The seat whose turn `turn` (1-based) is — firstPlayer takes the odd turns."""
    return (int(first_player) + int(turn) - 1) % 2


def classify(shadow: dict, *, died: bool) -> str:
    """The cohort of one audited turn: what the doom read decided × what actually happened."""
    if not shadow.get("doom_old"):
        return "SAFE_MISS" if died else "SAFE_OK"
    if shadow.get("doom_final"):
        return "DOOM_HIT" if died else "DOOM_PHANTOM"
    return "FALSE_RELAX" if died else "RELAX_OK"           # worst-case cried, the gate cleared it


def _film(replay: dict) -> list[dict]:
    steps = replay.get("steps") or []
    if not steps or not steps[0]:
        return []
    return steps[0][0].get("visualize") or []


def _cur(frame: dict) -> dict:
    return frame.get("current") or (frame.get("obs") or {}).get("current") or {}


def _active_serial(cur: dict, seat: int):
    players = cur.get("players") or []
    if not (0 <= seat < len(players)) or not players[seat]:
        return None
    active = next((p for p in (players[seat].get("active") or []) if p), None)
    return active.get("serial") if active else None


def _discard_serials(cur: dict, seat: int) -> set:
    players = cur.get("players") or []
    if not (0 <= seat < len(players)) or not players[seat]:
        return set()
    return {c.get("serial") for c in (players[seat].get("discard") or []) if c}


def audit_replay(replay: dict, *, seat: int, explain) -> list[dict]:
    """Audit one film for one seat: per turn of that seat, the LAST decision frame's shadow
    (via ``explain(obs) -> shadow-dict | None`` — inject the real Pilot or a test fake; called on
    every decision frame IN ORDER so a stateful pilot stays live-faithful) classified against the
    film's ground truth. Returns one row dict per audited turn."""
    film = _film(replay)
    episode = (replay.get("info") or {}).get("EpisodeId")
    turn_shadows: dict[int, list] = {}                     # my turn -> [(serial at frame, shadow)]
    for frame in film:
        cur = _cur(frame)
        if cur.get("yourIndex") != seat:
            continue
        select = frame.get("select")
        if not isinstance(select, dict) or not select.get("option"):
            continue                                        # not a decision prompt
        shadow = explain(frame.get("obs") or {"current": cur})
        turn = cur.get("turn")
        fp = cur.get("firstPlayer", 0) or 0
        if turn is None or turn_player(turn, first_player=fp) != seat:
            continue                                        # a mid-opponent-turn prompt — not my turn
        if shadow:
            turn_shadows.setdefault(turn, []).append((_active_serial(cur, seat), shadow))
    rows: list[dict] = []
    for turn, reads in sorted(turn_shadows.items()):
        serial, shadow = reads[-1]                          # the LAST read — closest to facing them
        if serial is None:
            continue
        # a relax ANYWHERE in the turn on the body that faced them (the relax's live value is
        # largely mid-turn — attach/retreat decisions — even when the last read re-doomed)
        touched = any(s == serial and sh.get("doom_old") and not sh.get("doom_final")
                      and sh.get("decided") for s, sh in reads)
        faced, died = _turn_outcome(film, seat=seat, my_turn=turn, serial=serial)
        if faced is None:
            continue                                        # their turn never observed (film ends)
        cohort = "DODGED" if faced != serial else classify(shadow, died=died)
        rows.append({"episode": episode, "seat": seat, "turn": turn, "serial": serial,
                     "cohort": cohort, "relax_touched": touched, "died": died, "shadow": shadow})
    return rows


def _turn_outcome(film, *, seat: int, my_turn: int, serial):
    """(faced_serial, died): which of my bodies started the opponent's next turn in my Active, and
    whether it reached my discard within their turn window (their turn `my_turn+1` through the
    start of my `my_turn+2`, terminal frame included — the game-losing KO has no later my-frame)."""
    faced = None
    died = False
    for frame in film:
        cur = _cur(frame)
        turn = cur.get("turn")
        if turn is None or turn <= my_turn:
            continue
        if turn > my_turn + 2:
            break
        if faced is None and turn == my_turn + 1:
            faced = _active_serial(cur, seat)
        if faced is not None and serial in _discard_serials(cur, seat):
            died = True
            break
    return faced, died


def tally(rows) -> dict:
    """Cohort counts over audit rows (every cohort keyed, zeros included)."""
    out = {c: 0 for c in COHORTS}
    for r in rows:
        c = r.get("cohort")
        if c in out:
            out[c] += 1
    return out


# ------------------------------------------------------------------------------ the real runner
def _tune():
    spec = importlib.util.spec_from_file_location("tune_mod", REPO / "tools" / "train" / "tune.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pilot_explain(tune, agent: str):
    """One stateful shipped Pilot for a (game, seat) — live-faithful within the game — wrapped to
    the audit's `explain` contract (obs -> threat_shadow dict | None; a frame the pilot cannot
    replay contributes no row rather than aborting the film)."""
    pilot = tune._build_pilot(agent)[0]

    def explain(obs):
        try:
            return getattr(pilot.explain(obs), "threat_shadow", None)
        except Exception:
            return None
    return explain


def main(argv=None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="Ground-truth audit of the doom matched relax on films")
    ap.add_argument("--replays", nargs="*", default=[str(REPO / "data" / "replays" / "gauntlet"),
                                                     str(REPO / "data" / "replays" / "selfplay")])
    ap.add_argument("--limit", type=int, default=0, help="max films to audit (0 = all)")
    args = ap.parse_args(argv)
    tune = _tune()
    agents = {p.name for p in (REPO / "src" / "agents").iterdir()
              if (p / "strategy.py").exists()}
    films = sorted(f for root in args.replays for f in Path(root).rglob("*.json"))
    if args.limit:
        films = films[:args.limit]
    rows: list[dict] = []
    audited = 0
    for path in films:
        replay = json.loads(path.read_text(encoding="utf-8"))
        team_names = (replay.get("info") or {}).get("TeamNames") or []
        for seat, name in enumerate(team_names[:2]):
            agent = seat_agent(name)
            if agent not in agents:
                continue
            rows.extend(audit_replay(replay, seat=seat, explain=_pilot_explain(tune, agent)))
            audited += 1
        print(f"  {path.name}: rows so far {len(rows)}", flush=True)
    t = tally(rows)
    total = sum(t.values())
    print(f"\nDOOM AUDIT: films={len(films)} game-seats={audited} turn-rows={total}")
    for c in COHORTS:
        print(f"  {c:<13} {t[c]}")
    relax_n = t["FALSE_RELAX"] + t["RELAX_OK"]
    doom_n = t["DOOM_HIT"] + t["DOOM_PHANTOM"]
    safe_n = t["SAFE_MISS"] + t["SAFE_OK"]
    if relax_n:
        print(f"  relax false rate: {t['FALSE_RELAX']}/{relax_n} = {t['FALSE_RELAX']/relax_n:.3f}")
    if doom_n:
        print(f"  doom phantom rate: {t['DOOM_PHANTOM']}/{doom_n} = {t['DOOM_PHANTOM']/doom_n:.3f}")
    if safe_n:
        print(f"  worst-case safe-miss rate: {t['SAFE_MISS']}/{safe_n} = {t['SAFE_MISS']/safe_n:.3f}")
    touched = [r for r in rows if r.get("relax_touched") and r["cohort"] != "DODGED"]
    touched_died = [r for r in touched if r.get("died")]
    print(f"  relax-touched turns (a relax fired on the facing body at ANY read of the turn): "
          f"{len(touched)}, of which died: {len(touched_died)}")
    for r in rows:
        flag = ("TOUCHED+DIED" if r.get("relax_touched") and r.get("died")
                and r["cohort"] not in ("FALSE_RELAX", "DODGED") else None)
        if r["cohort"] in ("FALSE_RELAX", "SAFE_MISS") or flag:
            s = r["shadow"]
            print(f"  {flag or r['cohort']}: ep {r['episode']} seat {r['seat']} turn {r['turn']} "
                  f"serial {r['serial']} (old={s.get('doom_old')} charged={s.get('doom_charged')} "
                  f"hp={s.get('my_hp')} matched={s.get('matched')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
