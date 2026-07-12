"""Pin the native engine's undocumented determinism facts (ADR-0050, milestone M0).

The cgpy reimplementation needs several facts the docs don't state and the API doesn't
guarantee. Each probe here answers one empirically against the live DLL; the findings are
transcribed into `docs/pyeng/determinism.md` and pinned by `tests/parity/` engine tests.

Probes:
  serials    — how card serial numbers map to (seat, submitted deck position); whether the
               god-view frame-0 deck order is the submitted order or already shuffled
  options    — raw option-list ordering per select context (rule-fitting evidence)
  selectdeck — whether a search select's `deck` listing preserves true deck order or is
               canonicalized (decides how the RevealOracle binds hidden identities)
  fork       — whether search_begin consumes `your_deck` order as-is (draws follow it) and
               whether the fork is deterministic across identical calls
  mulligan   — the exact setup/mulligan/DrawCount prompt + log sequence

Usage:  python tools/parity/pin_determinism.py [--probe NAME] [--games N]
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

DEFS = REPO / "src" / "cgpy" / "defs"


def _tables():
    cards = json.loads((DEFS / "card_data.json").read_text(encoding="utf-8"))
    return cards


def _distinct_name_deck(cards: list, *, skip: set[int] = frozenset(), want_basics: int = 8) -> list[int]:
    """A legal 60-card deck of 60 DISTINCT names (one id per name), several Basics up front."""
    seen_names, deck = set(), []
    basics = [c for c in cards
              if c.get("basic") and c["cardType"] == 0 and c["cardId"] not in skip]
    for c in basics:
        if c["name"] not in seen_names:
            deck.append(c["cardId"])
            seen_names.add(c["name"])
        if len(deck) >= want_basics:
            break
    for c in cards:
        if len(deck) >= 60:
            break
        if c["cardId"] in skip or c["name"] in seen_names:
            continue
        if c["cardType"] == 5 or c.get("aceSpec"):  # energy names repeat; >1 ACE SPEC is illegal
            continue
        deck.append(c["cardId"])
        seen_names.add(c["name"])
    assert len(deck) == 60, f"only {len(deck)} distinct-name cards found"
    return deck


def _drive_random(obs, battle_select, rng, steps):
    """Advance `steps` random-legal selections (or stop at result/no-select)."""
    for _ in range(steps):
        cur = obs.get("current") or {}
        if cur.get("result", -1) not in (-1, None):
            break
        sel = obs.get("select")
        if sel is None:
            break
        k = sel["minCount"] if sel["minCount"] > 0 else (1 if sel["maxCount"] >= 1 else 0)
        pick = rng.sample(range(len(sel["option"])), min(k, len(sel["option"]))) if sel["option"] else []
        obs = battle_select([int(i) for i in pick])
    return obs


# ---------------------------------------------------------------- serials

def probe_serials(games: int = 3) -> None:
    from cg.game import battle_start, battle_select, battle_finish, visualize_data

    cards = _tables()
    deck0 = _distinct_name_deck(cards)
    deck1 = _distinct_name_deck(cards, skip=set(deck0))
    pos0 = {cid: i for i, cid in enumerate(deck0)}
    pos1 = {cid: i for i, cid in enumerate(deck1)}

    print("== serials ==")
    for g in range(games):
        obs, start = battle_start(deck0, deck1)
        assert start.errorPlayer == -1, f"probe deck illegal: {start.errorType}"
        v = json.loads(visualize_data())
        f0 = v[0]["current"]["players"]
        rows = []
        for seat, pos in ((0, pos0), (1, pos1)):
            zone = f0[seat]["deck"]
            # (submitted position -> serial); ids are unique per seat so this is exact
            m = {pos[c["id"]]: c["serial"] for c in zone if c["id"] in pos}
            in_submitted_order = [c["id"] for c in zone] == (deck0 if seat == 0 else deck1)
            serial_by_pos = [m.get(i) for i in range(60)]
            linear = all(s is not None for s in serial_by_pos) and all(
                serial_by_pos[i + 1] - serial_by_pos[i] == serial_by_pos[1] - serial_by_pos[0]
                for i in range(len(serial_by_pos) - 2))
            rows.append((seat, in_submitted_order, serial_by_pos[:6], linear))
        battle_finish()
        for seat, in_order, head, linear in rows:
            print(f" game{g} seat{seat}: f0-deck-in-submitted-order={in_order} "
                  f"serial(pos0..5)={head} linear={linear}")


# ---------------------------------------------------------------- options

def probe_options(games: int = 2) -> None:
    from cg.game import battle_start, battle_select, battle_finish

    cards = _tables()
    agents = REPO / "src" / "agents"
    deck = [int(x) for x in (agents / "mega_starmie" / "deck.csv").read_text(encoding="utf-8").split()[:60]]

    print("== options ==")
    rng = random.Random(5)
    shown: Counter = Counter()
    for g in range(games):
        obs, _ = battle_start(deck, deck)
        for _ in range(300):
            cur = obs.get("current") or {}
            if cur.get("result", -1) not in (-1, None):
                break
            sel = obs.get("select")
            if sel is None:
                break
            ctx, opts = sel["context"], sel["option"]
            if ctx == 0 and shown["MAIN"] < 3 and len({o["type"] for o in opts}) >= 3:
                shown["MAIN"] += 1
                print(f" MAIN raw order: {[(o['type'], o.get('index'), o.get('area'), o.get('attackId')) for o in opts]}")
            if ctx in (7, 5) and opts and opts[0].get("area") is not None and shown[f"ctx{ctx}"] < 2:
                shown[f"ctx{ctx}"] += 1
                print(f" ctx{ctx} CARD order: {[(o.get('area'), o.get('index'), o.get('playerIndex')) for o in opts]}")
            k = sel["minCount"] if sel["minCount"] > 0 else (1 if sel["maxCount"] >= 1 else 0)
            pick = rng.sample(range(len(opts)), min(k, len(opts))) if opts else []
            obs = battle_select([int(i) for i in pick])
        battle_finish()


# ---------------------------------------------------------------- selectdeck

def probe_selectdeck(tries: int = 20) -> None:
    from cg.game import battle_start, battle_select, battle_finish, visualize_data

    agents = REPO / "src" / "agents"
    deck = [int(x) for x in (agents / "mega_starmie" / "deck.csv").read_text(encoding="utf-8").split()[:60]]

    print("== selectdeck ==")
    rng = random.Random(9)
    for t in range(tries):
        obs, _ = battle_start(deck, deck)
        hit = False
        for _ in range(400):
            cur = obs.get("current") or {}
            if cur.get("result", -1) not in (-1, None):
                break
            sel = obs.get("select")
            if sel is None:
                break
            if sel.get("deck"):
                v = json.loads(visualize_data())
                seat = cur["yourIndex"]
                god_deck = [(c["id"], c["serial"]) for c in v[-1]["current"]["players"][seat]["deck"]]
                sel_deck = [(c["id"], c["serial"]) for c in sel["deck"]]
                same_order = sel_deck == god_deck
                sorted_by_id = sel_deck == sorted(sel_deck, key=lambda x: (x[0], x[1]))
                sorted_by_serial = sel_deck == sorted(sel_deck, key=lambda x: x[1])
                print(f" try{t}: select.deck n={len(sel_deck)} same-as-god-order={same_order} "
                      f"sorted-by-id={sorted_by_id} sorted-by-serial={sorted_by_serial}")
                print(f"   head sel: {sel_deck[:5]}")
                print(f"   head god: {god_deck[:5]}")
                hit = True
                break
            k = sel["minCount"] if sel["minCount"] > 0 else (1 if sel["maxCount"] >= 1 else 0)
            pick = rng.sample(range(len(sel["option"])), min(k, len(sel["option"]))) if sel["option"] else []
            obs = battle_select([int(i) for i in pick])
        battle_finish()
        if hit:
            return
    print(" no deck-revealing select reached")


# ---------------------------------------------------------------- fork

def probe_fork() -> None:
    from cg import api
    from cg.game import battle_start, battle_select, battle_finish, visualize_data

    agents = REPO / "src" / "agents"
    deck = [int(x) for x in (agents / "mega_starmie" / "deck.csv").read_text(encoding="utf-8").split()[:60]]

    print("== fork ==")
    rng = random.Random(3)
    # Retry until the chaos game lands on a plain MAIN select: fork determinism holds
    # only there — mid-effect forks reshuffle differently call-to-call (determinism.md §4).
    for _ in range(20):
        obs, _ = battle_start(deck, deck)
        obs = _drive_random(obs, battle_select, rng, 12)  # past setup, into the turn loop
        sel = obs.get("select")
        if sel is not None and (obs.get("current") or {}).get("result", -1) in (-1, None) \
                and (sel.get("type"), sel.get("context")) == (0, 0):
            break
        battle_finish()
    else:
        print(" no plain-MAIN state reached in 20 games; rerun")
        return

    v = json.loads(visualize_data())
    seat = obs["current"]["yourIndex"]
    me, opp = v[-1]["current"]["players"][seat], v[-1]["current"]["players"][1 - seat]
    my_deck_true = [c["id"] for c in me["deck"]]
    my_prize_true = [c["id"] for c in me["prize"]]
    opp_deck_true = [c["id"] for c in opp["deck"]]
    opp_prize_true = [c["id"] for c in opp["prize"]]
    opp_hand_true = [c["id"] for c in opp["hand"]]

    # A distinctive order: reverse of truth. If the fork consumes the list as-is, draws come
    # in exactly this order; if it reshuffles, they won't (repeatedly).
    my_deck_given = list(reversed(my_deck_true))

    o = api.to_observation_class(obs)

    def run_fork():
        st = api.search_begin(o, my_deck_given, my_prize_true, opp_deck_true,
                              opp_prize_true, opp_hand_true, [], manual_coin=True)
        drawn, sid = [], st.searchId
        for _ in range(30):
            ob = st.observation
            if ob.current and ob.current.result != -1:
                break
            if ob.select is None:
                break
            drawn += [l.cardId for l in ob.logs
                      if l.type == api.LogType.DRAW and l.playerIndex == seat and l.cardId]
            end_i = next((i for i, op in enumerate(ob.select.option)
                          if op.type == api.OptionType.END), None)
            st = api.search_step(st.searchId, [end_i if end_i is not None else 0])
        api.search_end()
        return drawn

    d1, d2 = run_fork(), run_fork()
    expect = my_deck_given[: len(d1)]
    print(f" fork draws follow given order: {d1 == expect}  (n={len(d1)})")
    print(f" fork deterministic across identical calls: {d1 == d2}")
    print(f"   given head: {my_deck_given[:6]}")
    print(f"   drawn:      {d1[:6]}")
    battle_finish()


# ---------------------------------------------------------------- mulligan

def probe_mulligan(tries: int = 30) -> None:
    from cg.game import battle_start, battle_select, battle_finish, visualize_data

    cards = _tables()
    basic = next(c["cardId"] for c in cards if c.get("basic") and c["cardType"] == 0)
    other_basics = [c["cardId"] for c in cards if c.get("basic") and c["cardType"] == 0][1:5]
    energy = next(c["cardId"] for c in cards if c["cardType"] == 5)
    thin = [basic] + [energy] * 59                      # 1 Basic -> P(mulligan) ~ .88
    rich = [b for b in other_basics] * 4 + [energy] * 44  # mulligan-proof opponent

    print("== mulligan ==")
    rng = random.Random(2)
    for t in range(tries):
        obs, start = battle_start(thin, rich)
        if start.errorPlayer >= 0:
            print(f" probe decks illegal: {start.errorType}")
            battle_finish()
            return
        obs = _drive_random(obs, battle_select, rng, 8)
        v = json.loads(visualize_data())
        mull_frames = [i for i, fr in enumerate(v)
                       if (fr.get("select") or {}).get("context") == "Mulligan"]
        if mull_frames:
            for i in range(0, min(len(v), mull_frames[-1] + 3)):
                fr = v[i]
                s = fr.get("select") or {}
                logs = [(l["type"], l.get("playerIndex"), l.get("hasBasicPokemon"))
                        for l in (fr.get("logs") or [])]
                logs_c = Counter(f"{a}:p{b}" + (f":{c}" if c is not None else "")
                                 for a, b, c in logs)
                print(f" f{i:02d} ctx={s.get('context')} type={s.get('type')} min={s.get('minCount')} "
                      f"max={s.get('maxCount')} nopts={len(s.get('option') or [])} "
                      f"sel={fr.get('selected')} logs={dict(logs_c)}")
            battle_finish()
            return
        battle_finish()
    print(" no mulligan observed; raise tries")


PROBES = {
    "serials": probe_serials,
    "options": probe_options,
    "selectdeck": probe_selectdeck,
    "fork": probe_fork,
    "mulligan": probe_mulligan,
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pin native-engine determinism facts.")
    ap.add_argument("--probe", choices=sorted(PROBES), help="run one probe (default: all)")
    args = ap.parse_args(argv)
    for name, fn in PROBES.items():
        if args.probe and name != args.probe:
            continue
        fn()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
