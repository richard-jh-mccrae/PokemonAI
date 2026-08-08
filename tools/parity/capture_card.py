"""Per-card micro-trace capture (ADR-0050 M4 item 2, needs the DLL).

Records 1..N native games per TARGET card under a target-biased policy that reuses the audit
drive-shell heuristics (`tools/sim/audit_attacks.py`): attack targets fire the target attack and
keep a chaos tail running; trainer / tool / energy targets are played whenever offered; ability
targets take the ABILITY option. Each game is written as a standard `parity-trace/1`, so
`replay_diff.py` and the CI parity gate consume micro-traces exactly like match traces.

    python tools/parity/capture_card.py 674 -n 2                 # card id, 2 seeds
    python tools/parity/capture_card.py 674 --attack 1301        # one specific attack
    python tools/parity/capture_card.py 1105 --out tests/fixtures/parity --prefix heal"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "tools" / "sim"))

from audit_attacks import (_ENERGY_CARD, _SetupMiss, _drive_to_attack,  # noqa: E402
                           _find_attach, _find_attack_opt, _find_bench_play,
                           _find_evolve, _hand, _missing_typed, _setup_pick,
                           _sub_select, bench_fodder, build_side_deck, evolution_chain)
from capture_match import chaos_choice  # noqa: E402  (same dir on sys.path)
from cgpy.cards import CardDB  # noqa: E402
from cgpy.schema import CardType, OptionType, SelectContext  # noqa: E402

_MAX_STEPS = 1200
_TAIL_STEPS = 60          # post-goal chaos steps: checkup ticks, promotions, EOT flows


def _plain_pool(db: CardDB) -> dict[int, dict]:
    return {cid: {"name": c.name, "pokemon": c.cardType == int(CardType.POKEMON),
                  "basic": c.basic, "hp": c.hp, "energyType": int(c.energyType),
                  "weakness": c.weakness, "resistance": c.resistance,
                  "hasAbility": bool(c.skills), "tera": c.tera, "ex": c.ex,
                  "megaEx": c.megaEx, "evolvesFrom": c.evolvesFrom}
            for cid, c in db.cards.items()}


def _live_pool(db: CardDB) -> dict[int, dict]:
    """The plain pool minus bodies carrying any deferred/undefined attack — chaos tails
    that wander into an unmodeled attack would poison the micro-trace."""
    from cgpy.chain import def_for, is_deferred
    pool = _plain_pool(db)
    out = {}
    for cid, c in pool.items():
        atks = db.card(cid).attacks
        defs = [def_for(f"attack:{aid}") for aid in atks]
        if all(d is not None and not is_deferred(d) for d in defs):
            out[cid] = c
    return out


def build_decks(db: CardDB, card_id: int,
                body_id: int | None = None) -> tuple[list[int], list[int], list[int]]:
    """(own deck, opponent deck, own evolution chain) for a target card. Fodder and the opponent body
    come from the LIVE pool, so the chaos tail cannot poison the trace with an unmodeled attack."""
    pool = _plain_pool(db)
    live = _live_pool(db)
    card = db.card(card_id)
    if card.cardType == int(CardType.POKEMON):
        chain = evolution_chain(card_id, pool)
        cost_types: list[int] = []
        for aid in card.attacks:
            cost_types += [int(e) or int(card.energyType) or 3
                           for e in db.attacks[aid].energies]
        fodder = bench_fodder(live, set(chain))
        # 1 copy each, not 4: an off-chain Basic can win the setup Active and strand the line, which
        # `_drive_to_attack` reports as `_SetupMiss` and this module retries.
        own = build_side_deck(chain, cost_types or [int(card.energyType) or 3], fodder,
                              fodder_copies=1)
    else:
        # Trainer/energy target: a sturdy basic line carries the game; 4x target rides
        # (1x for an ACE SPEC — the deck rule caps those at one copy).
        copies = 1 if db.card(card_id).aceSpec else 4
        if body_id is not None:
            chain = evolution_chain(body_id, pool)
            fodder = bench_fodder(live, set(chain), n=2)
            own = [card_id] * copies
            for cid in chain:
                own += [cid] * 4
            own += [fodder[0]] * 4
            etype = int(db.card(chain[0]).energyType) or 3
        else:
            body = bench_fodder(live, set(), n=3)
            chain = [body[0]]
            own = [card_id] * copies + [body[0]] * 4 + [body[1]] * 4 + [body[2]] * 4
            etype = int(db.card(body[0]).energyType) or 3
        own += [_ENERGY_CARD.get(etype, 3)] * (60 - len(own))
    opp_body = bench_fodder(live, set(chain), n=2)
    opp = build_side_deck([opp_body[0]], [0], opp_body[1:])
    return own, opp, chain


def target_policy(db: CardDB, card_id: int, chain: list[int],
                  attack_ids: list[int], rng: random.Random):
    """A choice policy biased to exercise the target card, chaos elsewhere."""
    card = db.card(card_id)
    is_pokemon = card.cardType == int(CardType.POKEMON)
    attacks_left = list(attack_ids)

    def choose(obs: dict) -> list[int]:
        sel = obs.get("select") or {}
        cur = obs.get("current") or {}
        seat = cur.get("yourIndex", 0)
        opts = sel.get("option") or []
        ctx = sel.get("context")
        if ctx == int(SelectContext.SETUP_ACTIVE_POKEMON) and seat == 0:
            return [_setup_pick(obs, seat, chain[0])]
        if seat == 0 and ctx in (int(SelectContext.TO_ACTIVE),
                                 int(SelectContext.SWITCH)):
            # keep the target line in the Active Spot (promotions after KOs, retreats)
            players = cur.get("players") or []
            bench = [b for b in ((players[0] or {}).get("bench") or []) if b]
            for i, o in enumerate(opts):
                idx = o.get("index")
                if idx is not None and idx < len(bench) \
                        and bench[idx].get("id") in chain:
                    return [i]
            return chaos_choice(sel, rng)
        if ctx != int(SelectContext.MAIN):
            return chaos_choice(sel, rng)
        if seat != 0:
            return chaos_choice(sel, rng)

        hand = _hand(obs, seat)

        # 1. climb the target line on the Active
        act = next((a for a in ((cur.get("players") or [{}])[0].get("active") or [])
                    if a), None)
        if is_pokemon and act is not None and act.get("id") in chain:
            nxt = chain.index(act["id"]) + 1
            if nxt < len(chain):
                eo = _find_evolve(obs, seat, chain[nxt])
                if eo is not None:
                    return [eo]

        # 2. play / attach / use the target card when the menu offers it
        for i, o in enumerate(opts):
            t = o.get("type")
            if t in (int(OptionType.PLAY), int(OptionType.ATTACH),
                     int(OptionType.EVOLVE)):
                idx = o.get("index")
                if idx is not None and idx < len(hand) \
                        and hand[idx].get("id") == card_id:
                    return [i]
            if t == int(OptionType.ABILITY) and o.get("area") == 7:
                stad = next(iter(cur.get("stadium") or []), None) or {}
                if stad.get("id") == card_id:
                    return [i]   # the target STADIUM's per-turn activated effect
            elif t == int(OptionType.ABILITY) and is_pokemon:
                players = cur.get("players") or []
                me = players[0] or {}
                area = o.get("area")
                pod = None
                if area == 4:
                    pod = next((a for a in (me.get("active") or []) if a), None)
                else:
                    bench = [b for b in (me.get("bench") or []) if b]
                    if o.get("index") is not None and o["index"] < len(bench):
                        pod = bench[o["index"]]
                if pod and pod.get("id") == card_id:
                    return [i]

        # 3. fire a target attack once payable
        if attacks_left:
            ao = _find_attack_opt(obs, attacks_left[0])
            if ao is not None:
                attacks_left.pop(0)
                return [ao]
            # bank energy toward it on the Active
            aid = attacks_left[0]
            cost = [int(e) for e in db.attacks[aid].energies]
            attached = [int(e) for e in ((act or {}).get("energies") or [])]
            if act is not None and not cur.get("energyAttached"):
                prefer = _missing_typed(cost, attached)
                ao2 = _find_attach(obs, seat, prefer=prefer)
                if ao2 is not None and (prefer or len(attached) < len(cost)):
                    return [ao2]

        # 4. bench spares, else chaos
        bo = _find_bench_play(obs, seat, _plain_pool(db))
        if bo is not None and rng.random() < 0.8:
            return [bo]
        return chaos_choice(sel, rng)

    return choose


class _Recorder:
    """Wraps `battle_select`, pairing each observation with the choice answered on it —
    drop-in for the audit drive-shell's `battle_select` parameter."""

    def __init__(self, select_fn, first_obs):
        from capture_match import strip_obs
        self._strip = strip_obs
        self._select = select_fn
        self.obs = first_obs
        self.frames: list[dict] = []

    def __call__(self, choice: list[int]):
        self.frames.append({"obs": self._strip(self.obs),
                            "choice": [int(i) for i in choice], "god": None})
        self.obs = self._select([int(i) for i in choice])
        return self.obs

    def seal(self):
        self.frames.append({"obs": self._strip(self.obs), "choice": None, "god": None})


def _finish_trace(db: CardDB, frames: list[dict], own, opp, card_id, seed, winner):
    import hashlib
    import json as _json

    from cg.game import visualize_data
    from cgpy.verify.trace import Trace
    viz = _json.loads(visualize_data())
    n = min(len(frames), len(viz))
    for k in range(n):
        frames[k]["god"] = viz[k]["current"]
        sel_next = viz[k + 1].get("selected") if k + 1 < len(viz) else None
        if frames[k]["choice"] is not None and sel_next is not None:
            assert frames[k]["choice"] == sel_next, (
                f"visualize selected misalignment at frame {k}")
        frames[k]["god_logs"] = viz[k].get("logs") or []
    lib = REPO / "src" / "cg" / "libcg.so"
    meta = {"engine_sha": hashlib.sha256(lib.read_bytes()).hexdigest()[:16],
            "decks": [list(own), list(opp)],
            "policy": f"card-target:{card_id}:seed={seed}",
            "purpose": f"micro-trace for card {card_id} ({db.card(card_id).name})",
            "result": {"winner": winner, "steps": n}}
    return Trace(meta=meta, frames=frames[:n])


def _deferred_attack_ids(db: CardDB) -> set[int]:
    from cgpy.chain import def_for, is_deferred
    return {aid for aid in db.attacks
            if is_deferred(def_for(f"attack:{aid}"))}


def _chaos_tail(rec: _Recorder, rng: random.Random, steps: int,
                avoid_attacks: set[int] = frozenset()) -> int:
    """Keep playing chaos after the goal so checkup ticks / promotions / EOT flows land in the record,
    steering clear of deferred attacks. Returns the terminal result (or -1)."""
    for _ in range(steps):
        cur = rec.obs.get("current") or {}
        res = cur.get("result", -1)
        if res is not None and res != -1:
            return res
        sel = rec.obs.get("select")
        if sel is None:
            return -1
        choice = chaos_choice(sel, rng)
        opts = sel.get("option") or []
        if (sel.get("context") == 0 and choice
                and opts[choice[0]].get("type") == 13
                and opts[choice[0]].get("attackId") in avoid_attacks):
            safe = [i for i, o in enumerate(opts)
                    if o.get("type") != 13 or o.get("attackId") not in avoid_attacks]
            choice = [rng.choice(safe)]
        rec(choice)
    return (rec.obs.get("current") or {}).get("result", -1)


def capture_attack(db: CardDB, card_id: int, attack_id: int, seed: int):
    """Drive to `attack_id` via the audit drive-shell (recording every step), fire it,
    resolve its sub-decisions, then a chaos tail. The proven driver — not re-derived."""
    from cg.game import battle_finish, battle_select, battle_start

    pool = _plain_pool(db)
    live = _live_pool(db)
    chain = evolution_chain(card_id, pool)
    own_type = int(db.card(card_id).energyType) or 3
    cost = [int(e) for e in db.attacks[attack_id].energies]
    fill = [e or own_type for e in cost] or [own_type]
    # NO fodder in the attacker's deck (the audit convention): a fodder basic could win the setup
    # Active Spot and the drive-shell only evolves the Active. Snipe targets live on the DEFENDER.
    own = build_side_deck(chain, fill)
    opp_body = bench_fodder(live, set(chain), n=3)
    def_chain = [opp_body[0]]
    opp = build_side_deck(def_chain, [0], opp_body[1:])

    rng = random.Random(seed)
    for attempt in range(6):
        obs, start = battle_start(list(own), list(opp))
        if start.errorPlayer >= 0:
            battle_finish()
            raise ValueError(f"illegal generated deck (errorType {start.errorType})")
        rec = _Recorder(battle_select, obs)
        try:
            pre = _drive_to_attack(rec, obs, attack_id=attack_id, atk_chain=chain,
                                   def_chain=def_chain, cost=cost, extra_energy=0,
                                   delay_turns=0, cards=pool, max_steps=_MAX_STEPS,
                                   bench_patience=6)
            rec([_find_attack_opt(pre, attack_id)])
            for _ in range(32):                    # the attack's own sub-decisions
                cur = rec.obs.get("current") or {}
                sel = rec.obs.get("select")
                if (cur.get("result", -1) != -1 or sel is None
                        or sel.get("context") == 0):
                    break
                rec(_sub_select(rec.obs))
            winner = _chaos_tail(rec, rng, _TAIL_STEPS, _deferred_attack_ids(db))
            rec.seal()
            # _finish_trace reads visualize_data during the return expression — before
            # the finally's battle_finish releases the native battle.
            return _finish_trace(db, rec.frames, own, opp, card_id, seed, winner)
        except _SetupMiss:
            if attempt == 5:
                raise
        finally:
            battle_finish()
    raise RuntimeError("unreachable")


def capture_card(card_id: int, seed: int, *, attack_id: int | None = None,
                 body_id: int | None = None):
    """One recorded native game biased around `card_id` → Trace (parity-trace/1). Pokémon targets with
    a specific --attack go through the audit drive-shell; everything else uses the chaos policy."""
    import json

    from capture_match import strip_obs
    from cg.game import battle_finish, battle_select, battle_start

    db = CardDB.load()
    if attack_id is not None:
        return capture_attack(db, card_id, attack_id, seed)

    own, opp, chain = build_decks(db, card_id, body_id)
    attack_ids = (list(db.card(card_id).attacks)
                  if db.card(card_id).cardType == int(CardType.POKEMON) else [])
    rng = random.Random(seed)
    policy = target_policy(db, card_id, chain, attack_ids, rng)

    obs, start = battle_start(list(own), list(opp))
    if start.errorPlayer >= 0:
        battle_finish()
        raise ValueError(f"illegal generated deck (seat {start.errorPlayer}, "
                         f"errorType {start.errorType})")
    rec = _Recorder(battle_select, obs)
    try:
        winner = -1
        goal_seen_at: int | None = None
        for step in range(_MAX_STEPS):
            cur = rec.obs.get("current") or {}
            res = cur.get("result", -1)
            if res is not None and res != -1:
                winner = res
                break
            if rec.obs.get("select") is None:
                break
            for log in rec.obs.get("logs") or []:
                # goal: the target ATTACK fired — or, for attackless targets, the card
                # hit the board (playing an attack-target's card is a precondition)
                if attack_ids:
                    if log.get("type") == 15 and log.get("attackId") in attack_ids:
                        goal_seen_at = goal_seen_at or step
                elif (log.get("type") in (10, 11, 12)
                        and log.get("cardId") == card_id):
                    goal_seen_at = goal_seen_at or step
            if goal_seen_at is not None and step - goal_seen_at > _TAIL_STEPS:
                break
            rec(policy(rec.obs))
        rec.seal()
        return _finish_trace(db, rec.frames, own, opp, card_id, seed, winner)
    finally:
        battle_finish()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Capture per-card micro-traces (M4).")
    ap.add_argument("card", type=int, help="target cardId")
    ap.add_argument("--attack", type=int, default=None,
                    help="target one attackId (default: all the card's attacks)")
    ap.add_argument("--body", type=int, default=None,
                    help="carrying basic for trainer targets (typed gates: Spikemuth "
                         "Gym wants a Marnie's line, Surfing Beach a {W} line)")
    ap.add_argument("-n", "--games", type=int, default=1)
    ap.add_argument("--seed", type=int, default=9000)
    ap.add_argument("--out", default=str(REPO / "data" / "parity"))
    ap.add_argument("--prefix", default=None)
    args = ap.parse_args(argv)

    prefix = args.prefix or f"card{args.card}"
    out = Path(args.out)
    for i in range(args.games):
        seed = args.seed + i
        tr = capture_card(args.card, seed, attack_id=args.attack, body_id=args.body)
        path = out / f"{prefix}_{seed}.trace.json.gz"
        tr.save(path)
        r = tr.meta["result"]
        print(f"wrote {path}  frames={r['steps']} winner={r['winner']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
